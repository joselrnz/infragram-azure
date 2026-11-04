"""What each resource type draws as: the export's tables, read the other way.

A provider's table (``assets/terraform/<provider>.json``) says which resources
the export writes for each frame kind and component. Read back, the main
resource of a component is that component, a frame's resource is that frame,
and a component's other resources are part of it. The table's ``import``
section adds what the export never writes: more types, the helpers folded
into their owner, the types that are only a wire, and what is not
architecture at all.
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass, field
from functools import cache

from ..terraform.mapping import EdgeRule, load_mapping

__all__ = [
    "LIBRARIES",
    "Role",
    "TypeTable",
    "component_class",
    "entry_mains",
    "frame_class",
    "library_of",
    "role_of",
    "type_table",
]

#: A Terraform provider's type prefix -> the library it draws in.
LIBRARIES = {"azurerm": "azure"}

#: Providers whose resources are never architecture.
_NOT_ARCHITECTURE = frozenset(
    {
        "random",
        "null",
        "time",
        "tls",
        "local",
        "archive",
        "external",
        "http",
        "template",
        "terraform",
        "cloudinit",
        "azuread",
        "github",
        "tfe",
        "vault",
        "helm",
        "kubernetes",
    }
)


def library_of(resource_type: str) -> str | None:
    """The library a resource type draws in: ``aws_instance`` -> ``aws``."""
    return LIBRARIES.get(resource_type.split("_", 1)[0])


@dataclass(frozen=True)
class Role:
    """What one resource type is to the drawing."""

    #: ``frame``, ``component``, ``part`` (folded into another resource),
    #: ``edge`` (only a wire), ``collapse``, ``ignore``, or ``unmapped``.
    kind: str
    #: The frame kind, or the component's service id.
    value: str = ""
    #: For a part: the arguments naming the resource it belongs to.
    owners: tuple[str, ...] = ()
    edge: EdgeRule | None = None


@dataclass
class TypeTable:
    library: str
    frames: dict[str, str] = field(default_factory=dict)
    components: dict[str, str | None] = field(default_factory=dict)
    parts: set[str] = field(default_factory=set)
    owners: dict[str, tuple[str, ...]] = field(default_factory=dict)
    edges: dict[str, EdgeRule] = field(default_factory=dict)
    collapse: dict[str, str] = field(default_factory=dict)
    ignore: tuple[str, ...] = ()
    fallback: str | None = None

    def role(self, resource_type: str) -> Role:
        owners = self.owners.get(resource_type, ())
        if resource_type in self.components:
            chosen = self.components[resource_type]
            if chosen is None:
                return Role("part", owners=owners)
            return Role("component", chosen)
        if resource_type in self.frames:
            return Role("frame", self.frames[resource_type])
        if resource_type in self.edges:
            return Role("edge", edge=self.edges[resource_type])
        if resource_type in self.parts or resource_type in self.owners:
            return Role("part", owners=owners)
        if resource_type in self.collapse:
            return Role("collapse", self.collapse[resource_type])
        if any(
            resource_type == entry or (entry.endswith("_") and resource_type.startswith(entry))
            for entry in self.ignore
        ):
            return Role("ignore")
        return Role("unmapped", self.fallback or "")


@cache
def type_table(library: str) -> TypeTable:
    """The reverse of ``library``'s export table, with its import section."""
    mapping = load_mapping(library)
    table = TypeTable(library)
    for kind, rule in mapping.frames.items():
        for spec in rule.resources:
            if spec.key == "main":
                # the first kind listed wins: public and private subnets share
                # a type, and the import tells them apart itself
                table.frames.setdefault(spec.type, kind)
            else:
                table.parts.add(spec.type)
    for service_id, component in mapping.components.items():
        for spec in component.resources:
            if spec.key == "main":
                table.components.setdefault(spec.type, service_id)
            else:
                table.parts.add(spec.type)
    rules = mapping.imports
    for resource_type, chosen in rules.components.items():
        table.components[resource_type] = chosen
        table.frames.pop(resource_type, None)
    table.parts -= {t for t, c in table.components.items() if c is not None}
    table.parts -= set(table.frames)
    for resource_type in rules.not_drawn:
        # left out as the ignore list says, though a table writes it
        table.components.pop(resource_type, None)
        table.parts.discard(resource_type)
    table.owners = {t: tuple([o] if isinstance(o, str) else o) for t, o in rules.owners.items()}
    table.edges = dict(rules.edges)
    table.collapse = dict(rules.collapse)
    table.ignore = tuple(rules.ignore)
    table.fallback = rules.fallback
    return table


@cache
def entry_mains(library: str) -> dict[str, frozenset[str]]:
    """A part's type -> the main types of the entries that write it
    (``azurerm_mssql_server`` -> ``azurerm_mssql_database``): what it folds
    into first, before anything else that uses it (a private endpoint)."""
    out: dict[str, set[str]] = {}
    for rule in load_mapping(library).components.values():
        main = next((spec.type for spec in rule.resources if spec.key == "main"), None)
        for spec in rule.resources:
            if main is not None and spec.key != "main":
                out.setdefault(spec.type, set()).add(main)
    return {part: frozenset(mains) for part, mains in out.items()}


def role_of(resource_type: str) -> Role:
    """What a resource of any provider is to the drawing."""
    library = library_of(resource_type)
    if library is None:
        if resource_type.split("_", 1)[0] in _NOT_ARCHITECTURE:
            return Role("ignore")
        return Role("other")
    return type_table(library).role(resource_type)


# ------------------------------------------------------------ the node classes
@cache
def _component_classes(library: str) -> dict[str, tuple[str, str]]:
    """service id -> (category module, class name) in ``infragram.nodes.<library>``."""
    module_name = f"infragram.nodes.{library}"
    try:
        package = importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name == module_name:
            return {}
        raise
    out: dict[str, tuple[str, str]] = {}
    for category in getattr(package, "CATEGORIES", ()):
        module = importlib.import_module(f"infragram.nodes.{library}.{category}")
        for name, cls in vars(module).items():
            icon = getattr(cls, "ICON", "")
            if (
                inspect.isclass(cls)
                and not name.startswith("_")
                and cls.__module__ == module.__name__
                and isinstance(icon, str)
                and icon
            ):
                out.setdefault(icon, (category, name))
    return out


def component_class(library: str, service_id: str) -> tuple[str, str] | None:
    """The node class a component is written as: ``("compute", "EC2")``."""
    return _component_classes(library).get(service_id)


@cache
def _frame_classes(library: str) -> dict[str, str]:
    module_name = f"infragram.nodes.frames.{library}"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name == module_name:
            return {}
        raise
    kinds: dict[str, list[str]] = {}
    for name, cls in vars(module).items():
        if (
            inspect.isclass(cls)
            and not name.startswith("_")
            and cls.__module__ == module.__name__
            and isinstance(kind := getattr(cls, "KIND", None), str)
        ):
            kinds.setdefault(kind, []).append(name)
    # the plainest class of a kind: VPC before SharedVPC
    return {kind: min(names, key=lambda n: (len(n), n)) for kind, names in kinds.items()}


def frame_class(library: str, kind: str) -> str | None:
    """The frame class a kind is written as in ``infragram.nodes.frames.<library>``."""
    classes = _frame_classes(library)
    if kind not in classes and kind.startswith("subnet-"):
        return classes.get("subnet-private") or classes.get("subnet-public")
    return classes.get(kind)
