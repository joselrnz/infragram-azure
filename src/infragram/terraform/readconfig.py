"""A Terraform configuration's files, read into an :class:`~infragram.estate.Estate`.

The path of ``references/terraform.md`` section 3, without running Terraform:

- **Discover.** The root module is the folder given; ``*.tf`` and
  ``*.tf.json`` are its files. A module called with a local ``source`` is
  read the same way, and so is one from a registry or git that
  ``terraform init`` installed (``.terraform/modules/modules.json`` names its
  folder), or a registry module infragram's module cache holds at a version
  its constraint allows. Any other is named in the notes, since only a plan
  or a state shows what it holds.
- **Resolve.** Variables take their defaults, then ``terraform.tfvars``,
  ``*.auto.tfvars`` and the variable files given, then the values given;
  locals are evaluated until they settle. ``count`` and ``for_each`` over
  values the reader knows expand to their instances, a module's too, and a
  ``dynamic`` block to its blocks; over values it does not know, the
  resource stays one element and the notes say so.
- **References.** Every argument keeps the addresses it names. A reference
  through a variable, a local, ``each.`` (a value the reader cannot know) or
  a module output is followed to the resource behind it, across module
  boundaries, so a subnet passed from the root into a module is the subnet
  its instances sit in; and ``element(list, i)`` of what names one counted
  resource is its ``[i]``.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import Field

from ..estate.azapi import as_azurerm
from ..estate.model import Estate, Found
from ..iso3d.cache import cache_root
from .hclread import (
    UNKNOWN,
    Body,
    Expr,
    HclBlock,
    HclError,
    convert,
    element_calls,
    evaluate,
    is_known,
    iterators_read,
    object_entries,
    parse,
    parse_json,
    references,
    symbols,
    type_of,
)
from .model import Record

__all__ = ["ConfigurationError", "read_configuration"]


class ConfigurationError(ValueError):
    """The folder is not a Terraform configuration the reader can follow."""


#: Arguments of a block that are Terraform's own, not the resource's.
_META = frozenset(
    {"count", "for_each", "provider", "depends_on", "lifecycle", "provisioner", "connection"}
)
#: Where an instance's scope keeps what its ``for_each`` names, for ``each.``
#: to name it too (no identifier can read it).
_EACH_NAMES = "for_each names"
#: Where a dynamic block's content keeps what each iterator's ``for_each`` names
_ITERATOR_NAMES = "iterator names"
#: Where ``terraform init`` lists the modules it installed, under the root.
_MANIFEST = Path(".terraform") / "modules" / "modules.json"


def module_cache() -> Path:
    """Infragram's registry module cache: ``<namespace>/<name>/<provider>/<version>/``."""
    return cache_root() / "terraform" / "modules"


def _version(text: str) -> tuple[int, ...] | None:
    parts = text.strip().split(".")
    return tuple(int(part) for part in parts) if all(part.isdigit() for part in parts) else None


def _allows(constraint: str, version: tuple[int, ...]) -> bool:
    """Whether a version meets a constraint as Terraform reads one: ``6.7.3``,
    ``>= 6.0, < 7.0``, ``~> 6.0`` (the last part given may grow)."""
    for clause in constraint.split(","):
        match = re.fullmatch(r"\s*(~>|>=|<=|!=|=|>|<)?\s*([0-9][0-9.]*)\s*", clause)
        if match is None:
            return False
        wanted = _version(match.group(2))
        if wanted is None:
            return False
        op = match.group(1) or "="
        # 6.1 is 6.1.0: both as long as the longer, before they compare
        width = max(len(version), len(wanted))
        padded = version + (0,) * (width - len(version))
        upper = (*wanted[:-2], wanted[-2] + 1) if len(wanted) > 1 else (wanted[0] + 1,)
        wanted = wanted + (0,) * (width - len(wanted))
        if op == "~>":
            if not (padded >= wanted and padded[: len(upper)] < upper):
                return False
        elif not {
            "=": padded == wanted,
            "!=": padded != wanted,
            ">": padded > wanted,
            ">=": padded >= wanted,
            "<": padded < wanted,
            "<=": padded <= wanted,
        }[op]:
            return False
    return True


class _Module(Record):
    path: Path
    #: ``""`` for the root, else ``module.net.`` (with its index when expanded).
    prefix: str
    #: The files, parsed.
    bodies: list[tuple[str, Body]]
    #: The input values the caller gave, and what each input's expression named.
    inputs: dict[str, Any] = Field(default_factory=dict)
    input_refs: dict[str, list[str]] = Field(default_factory=dict)
    #: For an input the caller wrote as an object: what each of its entries named.
    input_keyed: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    #: provider key (``aws``, ``aws.west``) -> its configuration's values, as the caller maps them.
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)
    locals: dict[str, Any] = Field(default_factory=dict)
    local_refs: dict[str, list[str]] = Field(default_factory=dict)
    #: output name -> the addresses its value names (qualified).
    outputs: dict[str, list[str]] = Field(default_factory=dict)
    #: The call's path as ``terraform init`` keys it: ``""``, ``vpc``, ``vpc.subnets``.
    key: str = ""
    #: call name -> what its outputs hold, where that is known without a plan
    module_values: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def blocks(self, kind: str) -> list[tuple[str, HclBlock]]:
        return [(name, block) for name, body in self.bodies for block in body.blocks_of(kind)]

    def scope(self) -> dict[str, Any]:
        return {
            "var": self.variables,
            "local": self.locals,
            "module": self.module_values,
            "path": {"module": str(self.path), "root": ".", "cwd": "."},
            "terraform": {"workspace": "default"},
        }


def _files(folder: Path) -> list[Path]:
    files = sorted([*folder.glob("*.tf"), *folder.glob("*.tf.json")])
    return [path for path in files if path.is_file()]


def _read(path: Path, root: Path) -> tuple[str, Body]:
    text = path.read_text(encoding="utf-8-sig")
    name = os.path.relpath(path, root).replace(os.sep, "/")
    try:
        body = parse_json(text, name) if path.name.endswith(".tf.json") else parse(text, name)
    except HclError as error:
        raise ConfigurationError(str(error)) from error
    return name, body


def _tfvars(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix == ".json":
        try:
            return dict(json.loads(text))
        except (ValueError, TypeError) as error:
            raise ConfigurationError(f"{path}: {error}") from error
    try:
        body = parse(text, str(path))
    except HclError as error:
        raise ConfigurationError(str(error)) from error
    return {name: evaluate(expr) for name, expr in body.attributes.items()}


class _Reader:
    def __init__(self, root: Path, var_files: list[Path], values: dict[str, Any]) -> None:
        self.root = root
        self.var_files = var_files
        self.values = values
        self.found: list[Found] = []
        self.notes: list[str] = []
        #: The variable files read, as the origin names them.
        self.read: list[str] = []
        #: module key -> the folder ``terraform init`` installed it in
        self.installed: dict[str, Path] = {}
        manifest = root / _MANIFEST
        if manifest.is_file():
            try:
                entries = json.loads(manifest.read_text(encoding="utf-8")).get("Modules") or []
            except (ValueError, OSError, AttributeError):
                entries = []
            for entry in entries:
                if isinstance(entry, dict) and entry.get("Key") and entry.get("Dir"):
                    self.installed[str(entry["Key"])] = (root / str(entry["Dir"])).resolve()
        #: registry modules read, and from where: ``terraform init`` or the cache
        self.registry: dict[str, str] = {}
        #: folder -> its files, parsed once however many calls read it
        self.parsed: dict[Path, list[tuple[str, Body]]] = {}

    # ------------------------------------------------------------ modules
    def bodies(self, path: Path) -> list[tuple[str, Body]]:
        if path not in self.parsed:
            files = _files(path)
            if not files:
                raise ConfigurationError(f"{path} holds no *.tf file")
            self.parsed[path] = [_read(file, self.root) for file in files]
        return self.parsed[path]

    def module(
        self,
        path: Path,
        prefix: str,
        inputs: dict[str, Any],
        input_refs: dict[str, list[str]],
        providers: dict[str, dict[str, Any]],
        depth: int,
        key: str = "",
        input_keyed: dict[str, dict[str, list[str]]] | None = None,
    ) -> _Module:
        if depth > 16:
            raise ConfigurationError(f"{path}: modules nest more than 16 deep")
        module = _Module(
            path,
            prefix,
            self.bodies(path),
            dict(inputs),
            dict(input_refs),
            dict(input_keyed or {}),
            dict(providers),
            key=key,
        )
        self.variables(module)
        self.local_values(module)
        self.provider_configs(module)
        self.module_values(module)
        for kind in ("resource", "data"):
            for file, block in module.blocks(kind):
                self.resource(module, file, block, "managed" if kind == "resource" else "data")
        for file, block in module.blocks("module"):
            self.call(module, file, block, depth)
        for _file, block in module.blocks("output"):
            if block.labels and "value" in block.body.attributes:
                module.outputs[block.labels[0]] = self.named(
                    module, block.body.attributes["value"], module.scope()
                )
        return module

    def variables(self, module: _Module) -> None:
        types = {}
        for _file, block in module.blocks("variable"):
            if not block.labels:
                continue
            name = block.labels[0]
            types[name] = type_of(block.body.attributes.get("type"))
            default = block.body.attributes.get("default")
            module.variables[name] = evaluate(default) if default is not None else UNKNOWN
        if module.prefix == "":
            given: dict[str, Any] = {}
            auto = [
                module.path / "terraform.tfvars",
                module.path / "terraform.tfvars.json",
                *sorted(module.path.glob("*.auto.tfvars")),
                *sorted(module.path.glob("*.auto.tfvars.json")),
            ]
            for file in [*(p for p in auto if p.is_file()), *self.var_files]:
                given.update(_tfvars(file))
                self.read.append(file.name if file.parent == module.path else str(file))
            given.update(self.values)
            for name, value in given.items():
                if name not in module.variables:
                    self.notes.append(
                        f"the variable {name} is set but the configuration declares none"
                    )
                module.variables[name] = value
        else:
            module.variables.update(module.inputs)
        # a value takes its declared type: an object's optional attributes
        # their defaults, as modules written for Terraform 1.3 and after expect
        for name, kind in types.items():
            module.variables[name] = convert(module.variables.get(name), kind)

    def module_values(self, module: _Module) -> None:
        """What each module call's outputs hold, where the reader knows it
        without reading what the call writes: a utility module's maps, which
        a resource's ``for_each`` reads (``module.avm_interfaces.lock_azapi``,
        empty unless a lock is asked for). A call repeated by ``count`` or
        ``for_each``, and an output that reads a resource, hold nothing known:
        its inputs, locals and outputs are evaluated strictly, so
        ``try(aws_security_group.this[0].id, "")`` is no empty string and
        ``try(aws_subnet.this[*].id, [])`` no empty list."""
        for _file, block in module.blocks("module"):
            attributes = block.body.attributes
            if not block.labels or "count" in attributes or "for_each" in attributes:
                continue
            child = self.child_folder(module, block)
            if child is None:
                continue
            name = block.labels[0]
            try:
                inner = _Module(
                    child,
                    f"{module.prefix}module.{name}.",
                    self.bodies(child),
                    {
                        arg: evaluate(expr, module.scope(), strict=True)
                        for arg, expr in attributes.items()
                        if arg not in {"source", "version", "providers", *_META}
                    },
                )
            except ConfigurationError:
                continue
            self.variables(inner)
            self.local_values(inner, strict=True)
            values: dict[str, Any] = {}
            for _file, out in inner.blocks("output"):
                expr = out.body.attributes.get("value")
                if out.labels and expr is not None:
                    value = evaluate(expr, inner.scope(), strict=True)
                    if value is not UNKNOWN:
                        values[out.labels[0]] = value
            module.module_values[name] = values

    def local_values(self, module: _Module, strict: bool = False) -> None:
        """Each local's value, and (unless ``strict``, for what a module gives
        its caller) what each names."""
        expressions = {
            name: expr
            for _file, block in module.blocks("locals")
            for name, expr in block.body.attributes.items()
        }
        for name in expressions:
            module.locals[name] = UNKNOWN
        # locals may read each other in any order: evaluate until nothing changes
        for _ in range(len(expressions) + 1):
            changed = False
            for name, expr in expressions.items():
                value = evaluate(expr, module.scope(), strict=strict)
                if value is not UNKNOWN and value != module.locals.get(name):
                    module.locals[name] = value
                    changed = True
            if not changed:
                break
        if strict:
            return
        for _ in range(len(expressions) + 1):
            changed = False
            for name, expr in expressions.items():
                named = self.named(module, expr, module.scope())
                if named != module.local_refs.get(name, []):
                    module.local_refs[name] = named
                    changed = True
            if not changed:
                break

    def provider_configs(self, module: _Module) -> None:
        for _file, block in module.blocks("provider"):
            if not block.labels:
                continue
            values = {
                name: evaluate(expr, module.scope()) for name, expr in block.body.attributes.items()
            }
            alias = values.get("alias")
            key = f"{block.labels[0]}.{alias}" if isinstance(alias, str) else block.labels[0]
            module.providers[key] = values

    # ------------------------------------------------------------ references
    def named(self, module: _Module, expr: Expr, scope: dict[str, Any]) -> list[str]:
        """The qualified addresses ``expr`` names, through variables, locals,
        ``each.`` and module outputs; ``element(list, i)`` of what names one
        counted resource names its ``[i]`` instance."""
        out: list[str] = []
        for address in references(expr, scope):
            if address.startswith("module."):
                out += self.output(module.prefix + address)
            else:
                out.append(module.prefix + address)
        for symbol in symbols(expr):
            kind, name = symbol.split(".", 1)
            if kind == "each":
                # a value read through each. names what the for_each names
                # when the reader cannot know it; a port it knows names nothing
                if not is_known(evaluate(expr, scope)):
                    out += scope.get(_EACH_NAMES, [])
            else:
                out += (module.input_refs if kind == "var" else module.local_refs).get(name, [])
        iterators = scope.get(_ITERATOR_NAMES, {})
        if iterators and not is_known(evaluate(expr, scope)):
            # a dynamic block's content reads its iterator: what its for_each names
            for iterator in iterators_read(expr, iterators):
                out += iterators[iterator]
        out = list(dict.fromkeys(out))
        for listed, position in element_calls(expr):
            inner = self.named(module, Expr(listed), scope)
            index = evaluate(position, scope)
            if (
                len(inner) == 1
                and not inner[0].endswith("]")
                and inner[0] in out
                and isinstance(index, int)
                and not isinstance(index, bool)
            ):
                out[out.index(inner[0])] = f"{inner[0]}[{index}]"
        return list(dict.fromkeys(out))

    module_outputs: dict[str, list[str]]

    def output(self, address: str) -> list[str]:
        """What a module output names; ``[i]`` (or ``["key"]``) of an output
        that names one counted (or repeated) resource is that instance, and
        of an output that holds a module, that module instance, whose own
        outputs an attribute after it reads. An instance of a module read
        once (its ``for_each`` unknown) is that one reading."""
        if address in self.module_outputs:
            return self.module_outputs[address]
        head, dot, attribute = address.rpartition(".")
        if dot and head.endswith("]") and not attribute.endswith("]"):
            held = self.output(head)
            if held == [head]:
                # not read yet: the second pass reads it whole
                return [address]
            out: list[str] = []
            for item in held:
                out += (
                    self.output(f"{item}.{attribute}") if _MODULE_OBJECT.fullmatch(item) else [item]
                )
            return list(dict.fromkeys(out))
        base, index = address, ""
        if address.endswith("]"):
            base, _, index = address[:-1].rpartition("[")
        named = self.module_outputs.get(base) if index else None
        if named is None and index and "." in base and base.rpartition(".")[0].endswith("]"):
            # an index after an attribute of an output's entry or a module
            # instance (``module.network.vpcs["vpc"].private_subnets[1]``):
            # what the attribute names, then that instance of it
            held = self.output(base)
            if held != [base]:
                named = held
        if named is None:
            unkeyed = _MODULE_KEY.sub(r"\1", base)
            if unkeyed == base or unkeyed not in self.module_outputs:
                return [address]
            return self.output(f"{unkeyed}[{index}]" if index else unkeyed)
        if (
            len(named) == 1
            and not named[0].endswith("]")
            and (index.isdigit() or (len(index) > 1 and index[0] == index[-1] == '"'))
        ):
            return [f"{named[0]}[{index}]"]
        return list(named)

    # ------------------------------------------------------------ resources
    def instances(
        self, module: _Module, block: HclBlock, what: str
    ) -> list[tuple[str, dict[str, Any]]]:
        """``(index suffix, scope)`` for each instance of a counted or
        repeated block; one instance when neither, or when unknown."""
        scope = module.scope()
        attributes = block.body.attributes
        if "count" in attributes:
            count = evaluate(attributes["count"], scope)
            if isinstance(count, bool) or not isinstance(count, (int, float)):
                self.notes.append(
                    f"{what}: its count is not known without a plan, so it is drawn once"
                )
                return [("", {**scope, "count": {"index": UNKNOWN}})]
            return [(f"[{i}]", {**scope, "count": {"index": i}}) for i in range(int(count))]
        if "for_each" in attributes:
            each = evaluate(attributes["for_each"], scope)
            names = {_EACH_NAMES: self.named(module, attributes["for_each"], scope)}
            # repeated over an input the caller wrote out, an instance names
            # what its own entry named, when the keys are the caller's
            keyed = [
                module.input_keyed[name]
                for symbol in symbols(attributes["for_each"])
                if symbol.startswith("var.") and (name := symbol[4:]) in module.input_keyed
            ]
            if isinstance(each, dict):
                items = list(each.items())
            elif isinstance(each, list) and all(isinstance(item, str) for item in each):
                items = [(item, item) for item in each]
            else:
                self.notes.append(
                    f"{what}: its for_each is not known without a plan, so it is drawn once"
                )
                return [("", {**scope, **names, "each": {"key": UNKNOWN, "value": UNKNOWN}})]
            return [
                (
                    f'["{key}"]',
                    {
                        **scope,
                        **names,
                        **(
                            {_EACH_NAMES: keyed[0][str(key)]}
                            if len(keyed) == 1 and str(key) in keyed[0]
                            else {}
                        ),
                        "each": {"key": key, "value": value},
                    },
                )
                for key, value in items
            ]
        return [("", scope)]

    def body_values(
        self,
        module: _Module,
        body: Body,
        scope: dict[str, Any],
        path: str,
        refs: dict[str, list[str]],
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, expr in body.attributes.items():
            if not path and name in _META:
                if name == "depends_on":
                    refs["depends_on"] = self.named(module, expr, scope)
                continue
            key = f"{path}.{name}" if path else name
            values[name] = evaluate(expr, scope)
            named = self.named(module, expr, scope)
            if named:
                refs[key] = [*refs.get(key, []), *(a for a in named if a not in refs.get(key, []))]
        for block in body.blocks:
            if not path and block.type in _META:
                continue
            if block.type == "dynamic" and block.labels:
                self.dynamic(module, block, scope, path, values, refs)
                continue
            key = f"{path}.{block.type}" if path else block.type
            values.setdefault(block.type, []).append(
                self.body_values(module, block.body, scope, key, refs)
            )
        return values

    def dynamic(
        self,
        module: _Module,
        block: HclBlock,
        scope: dict[str, Any],
        path: str,
        values: dict[str, Any],
        refs: dict[str, list[str]],
    ) -> None:
        """A ``dynamic`` block: one block per element its ``for_each`` gives,
        its iterator's ``key`` and ``value`` bound in the ``content``. Over
        values the reader does not know, only what the content names."""
        label = block.labels[0]
        key = f"{path}.{label}" if path else label
        iterator = block.body.attributes.get("iterator")
        name = iterator.text.strip() if iterator is not None else label
        for_each = block.body.attributes.get("for_each")
        named: list[str] = []
        if for_each is not None:
            named = self.named(module, for_each, scope)
            if named:
                refs[key] = [*refs.get(key, []), *(a for a in named if a not in refs.get(key, []))]
        each = evaluate(for_each, scope) if for_each is not None else UNKNOWN
        if isinstance(each, dict):
            items: list[tuple[Any, Any]] | None = list(each.items())
        elif isinstance(each, list):
            items = list(enumerate(each))
        else:
            items = None
        # network_configuration.value.security_groups names what the for_each
        # names, [local.network_configuration], when the reader cannot know it
        iterators = {**scope.get(_ITERATOR_NAMES, {}), name: named}
        for inner in block.body.blocks_of("content"):
            if items is None:
                self.body_values(
                    module,
                    inner.body,
                    {**scope, name: {"key": UNKNOWN, "value": UNKNOWN}, _ITERATOR_NAMES: iterators},
                    key,
                    refs,
                )
                continue
            for item_key, item_value in items:
                bound = {
                    **scope,
                    name: {"key": item_key, "value": item_value},
                    _ITERATOR_NAMES: iterators,
                }
                values.setdefault(label, []).append(
                    self.body_values(module, inner.body, bound, key, refs)
                )

    def resource(self, module: _Module, file: str, block: HclBlock, mode: str) -> None:
        if len(block.labels) != 2:
            return
        kind, name = block.labels
        base = f"{module.prefix}{'data.' if mode == 'data' else ''}{kind}.{name}"
        provider_key = kind.split("_", 1)[0]
        chosen = block.body.attributes.get("provider")
        if chosen is not None:
            provider_key = chosen.text.strip()
        config = (
            module.providers.get(provider_key)
            or module.providers.get(provider_key.split(".")[0])
            or {}
        )
        for suffix, scope in self.instances(module, block, base):
            refs: dict[str, list[str]] = {}
            values = self.body_values(module, block.body, scope, "", refs)
            if (
                kind.startswith("google_")
                and values.get("project") is None
                and isinstance(config.get("project"), str)
            ):
                # the provider's project is the resource's, as Terraform gives it
                values["project"] = config["project"]
            region = config.get("region")
            location = values.get("location")
            self.found.append(
                Found(
                    address=base + suffix,
                    type=kind,
                    name=name,
                    values=values,
                    references=refs,
                    source=f"{file}:{block.line}" if block.line else file,
                    region=region
                    if isinstance(region, str)
                    else (location if isinstance(location, str) else None),
                    mode=mode,
                )
            )

    def child_folder(self, module: _Module, block: HclBlock) -> Path | None:
        """The folder a module call reads: a local path, the one ``terraform
        init`` installed, or the module cache's; None when it is none here."""
        name = block.labels[0]
        source = (
            evaluate(block.body.attributes["source"])
            if "source" in block.body.attributes
            else UNKNOWN
        )
        version = (
            evaluate(block.body.attributes["version"])
            if "version" in block.body.attributes
            else None
        )
        if isinstance(source, str) and source.startswith(("./", "../")):
            child = (module.path / source).resolve()
            return child if child.is_dir() else None
        installed = self.installed.get(f"{module.key}.{name}" if module.key else name)
        if installed is not None and installed.is_dir():
            return installed
        return self.cached(source, version if isinstance(version, str) else None)

    def call(self, module: _Module, file: str, block: HclBlock, depth: int) -> None:
        if not block.labels:
            return
        name = block.labels[0]
        source = (
            evaluate(block.body.attributes["source"])
            if "source" in block.body.attributes
            else UNKNOWN
        )
        address = f"{module.prefix}module.{name}"
        key = f"{module.key}.{name}" if module.key else name
        where = f"{file}:{block.line}" if block.line else file
        child = self.child_folder(module, block)
        if child is None:
            if isinstance(source, str) and source.startswith(("./", "../")):
                self.notes.append(f"{address} ({where}): its source {source} is not a folder here")
            else:
                self.notes.append(
                    f"{address} ({where}) comes from {source if isinstance(source, str) else 'an unknown source'}; "
                    "run terraform init in the folder to draw what it makes, or give a plan or a state"
                )
            return
        if not (isinstance(source, str) and source.startswith(("./", "../"))):
            installed = self.installed.get(key)
            self.registry.setdefault(
                str(source),
                "terraform init"
                if installed is not None and installed.is_dir()
                else "the module cache",
            )
        providers = dict(module.providers)
        mapping = block.body.attributes.get("providers")
        if mapping is not None:
            for key, target in _provider_map(mapping.text).items():
                providers[key] = module.providers.get(target, {})
        for suffix, scope in self.instances(module, block, address):
            inputs: dict[str, Any] = {}
            input_refs: dict[str, list[str]] = {}
            input_keyed: dict[str, dict[str, list[str]]] = {}
            for arg, expr in block.body.attributes.items():
                if arg in {"source", "version", "providers", *_META}:
                    continue
                inputs[arg] = evaluate(expr, scope)
                input_refs[arg] = self.named(module, expr, scope)
                entries = object_entries(expr)
                if entries:
                    input_keyed[arg] = {
                        key: self.named(module, Expr(text), scope) for key, text in entries
                    }
            prefix = f"{address}{suffix}."
            try:
                inner = self.module(
                    child, prefix, inputs, input_refs, providers, depth + 1, key, input_keyed
                )
            except ConfigurationError as error:
                self.notes.append(f"{address}: {error}")
                continue
            for output, named in inner.outputs.items():
                self.module_outputs[f"{address}{suffix}.{output}"] = named
                self.module_outputs.setdefault(f"{address}.{output}", []).extend(
                    a for a in named if a not in self.module_outputs.get(f"{address}.{output}", [])
                )

    @staticmethod
    def cached(source: object, constraint: str | None) -> Path | None:
        """A registry module in the module cache, at the newest version its
        constraint allows (any, when it gives none)."""
        if not isinstance(source, str):
            return None
        address, _, subdir = source.partition("//")
        parts = address.removeprefix("registry.terraform.io/").split("/")
        if len(parts) != 3 or not all(re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in parts):
            return None
        base = module_cache().joinpath(*parts)
        if not base.is_dir():
            return None
        versions = sorted(
            (v, folder)
            for folder in base.iterdir()
            if folder.is_dir()
            and (v := _version(folder.name)) is not None
            and (constraint is None or _allows(constraint, v))
        )
        if not versions:
            return None
        folder = versions[-1][1] / subdir if subdir else versions[-1][1]
        return folder if folder.is_dir() else None

    def run(self) -> None:
        self.module_outputs = {}
        # Module outputs are known only once the module is read, and a
        # resource read before the call named the output: a second pass
        # replaces the outputs with what they name.
        self.module(self.root, "", {}, {}, {}, 0)
        for found in self.found:
            for key, addresses in found.references.items():
                resolved = list(addresses)
                # an output may name another module's output: follow it through
                for _ in range(8):
                    step: list[str] = []
                    for address in resolved:
                        step += (
                            self.output(address)
                            if address.split(".", 2)[0] == "module" and not _resource_path(address)
                            else [address]
                        )
                    if step == resolved:
                        break
                    resolved = step
                found.references[key] = list(dict.fromkeys(resolved))


#: A module as a value, or one instance of it: ``module.vnet.module.subnet["web"]``.
_MODULE_OBJECT = re.compile(
    r"(?:module\.[A-Za-z_][\w-]*(?:\[[^\]]*\])?\.)*module\.[A-Za-z_][\w-]*(?:\[[^\]]*\])?"
)
#: A module call's instance key in an address: ``module.sg["api"].``.
_MODULE_KEY = re.compile(r"(module\.[A-Za-z_][\w-]*)\[[^\]]*\](?=\.)")


def _resource_path(address: str) -> bool:
    """``module.a.aws_vpc.main`` names a resource; ``module.a.vpc_id`` an
    output, and so does ``module.a.subnet_ids["x"].id`` (a type has no key)."""
    parts = address.split(".")
    while len(parts) > 2 and parts[0] == "module":
        parts = parts[2:]
    return len(parts) >= 2 and "[" not in parts[0] and ("_" in parts[0] or parts[0] == "data")


def _provider_map(text: str) -> dict[str, str]:
    """``{ aws = aws.west, google.beta = google-beta }`` as a dict of names."""
    inner = text.strip().removeprefix("{").removesuffix("}")
    out: dict[str, str] = {}
    for part in inner.replace(",", "\n").splitlines():
        if "=" in part:
            key, value = (piece.strip() for piece in part.split("=", 1))
            if key and value:
                out[key] = value
    return out


def read_configuration(
    root: Path,
    *,
    var_files: list[Path] | None = None,
    values: dict[str, Any] | None = None,
    title: str | None = None,
) -> Estate:
    """Every resource a configuration declares, as the reader resolves it.

    ``root`` is the root module's folder; ``var_files`` and ``values`` are what
    ``-var-file`` and ``-var`` would give ``terraform plan``.
    """
    from .layout import configuration_root

    root = Path(root).resolve()
    if not root.is_dir():
        raise ConfigurationError(f"{root} is not a folder")
    root = configuration_root(root)
    reader = _Reader(root, [Path(p) for p in var_files or []], dict(values or {}))
    reader.run()
    used = list(reader.read)
    if values:
        used.append(f"{len(values)} value{'s' * (len(values) != 1)} given")
    for place in ("terraform init", "the module cache"):
        read = [source for source, where in reader.registry.items() if where == place]
        if read:
            used.append(f"{len(read)} registry module{'s' * (len(read) != 1)} from {place}")
    origin = f"the Terraform in {root.name}/ ({', '.join(used) or 'no variable file'}; variables otherwise their defaults)"
    estate = Estate(title or root.name, origin, reader.found, reader.notes)
    as_azurerm(estate)
    return estate
