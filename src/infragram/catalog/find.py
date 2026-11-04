"""Find the node and frame classes a diagram file imports, ranked.

The MCP server's ``find_components`` and ``infragram find`` both answer from
here. The search used to list every class whose words matched in
alphabetical order, so "s3" listed twenty S3 resource glyphs and never
``SimpleStorageService``, and "aks" missed ``KubernetesServices``: the names
an architect types live in the curated alias overlay
(``assets/catalog/aliases.json``) that the editor's sidebar already reads,
and nothing ranked the service above the glyphs drawn inside it.

A class matches when every query word starts one of its words -- its name
split at the capitals, its title, its icon id, its library and its aliases
-- and ranks by how it matched:

0. the query is the class name itself ("vpc" finds ``VPC``);
1. the query is one of its aliases, its icon id or its title ("s3", "aks");
2. every word starts a word of its own name, title or icon;
3. only an alias's words make the match.

Within a tier an earlier alias beats a later one (Amazon S3 lists "s3"
first, DigitalOcean Spaces further down), a frame beats a node of the same
name, a service comes before the resource glyphs drawn inside it, the three
large clouds and Kubernetes come before the rest, then the shorter name.

The patterns (``infragram.patterns``: ``MultiAZ``, ``Guardrails``,
``DirectConnectUplink``, the ``Blueprint``...) are found by the same rules
but kept apart (:func:`find_patterns`): mixed into the class ranking they
would move the answers every existing query gives.
"""

from __future__ import annotations

import ast
import functools
import importlib
import inspect
import pkgutil
import re
import types
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

__all__ = [
    "Found",
    "Library",
    "find",
    "find_patterns",
    "libraries",
    "library_classes",
    "node_classes",
    "pattern_classes",
]

#: Where a library sorts when everything else ties: the clouds most diagrams draw first.
_LEAD = ("aws", "azure", "gcp", "kubernetes")
_VENDOR = re.compile(
    r"^(amazon|aws|azure|microsoft|google cloud|google|gcp|ibm|oracle|oci|alibaba cloud)\s+"
)


class Found(BaseModel):
    """One class a diagram file can import."""

    model_config = ConfigDict(frozen=True)

    module: str
    name: str
    title: str
    icon: str = ""
    library: str
    frame: bool = False
    glyph: bool = False
    aliases: tuple[str, ...] = ()

    @property
    def import_line(self) -> str:
        return f"from {self.module} import {self.name}"

    @property
    def category(self) -> str:
        """Where the class sits in its library: a node module is named for its
        sidebar category (``compute``, ``storage``), a frame is a frame, a
        pattern a pattern."""
        if self.frame:
            return "frames"
        if self.library == "patterns":
            return "patterns"
        return self.module.rsplit(".", 1)[1]


def _spoken(name: str) -> str:
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def _stem(word: str) -> str:
    """Enough of a word to find its other forms: "balancer" finds "Load Balancing"."""
    return word if len(word) <= 4 else word[: max(4, len(word) - 3)]


@functools.cache
def node_classes() -> tuple[Found, ...]:
    """Every node and frame class under ``infragram.nodes``, with its aliases.

    Read from the generated modules' source rather than by importing them:
    importing all 600 took twelve seconds, which every ``find`` paid, and the
    source says everything asked here -- the class, its ICON or KIND, its
    TYPE and its docstring. ``tests/unit/test_find.py`` holds the two readings
    to the same classes.
    """
    from .. import nodes
    from .aliases import load_default_alias_overlay

    overlay = load_default_alias_overlay()
    found: list[Found] = []
    for folder in nodes.__path__:
        root = Path(folder)
        for path in sorted(root.rglob("*.py")):
            if path.name.startswith("_") or any(
                part.startswith("_") for part in path.relative_to(root).parts[:-1]
            ):
                continue
            module = "infragram.nodes." + ".".join(path.relative_to(root).with_suffix("").parts)
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, ValueError):
                continue
            parts = module.split(".")
            frame = parts[2] == "frames"
            provider = parts[3] if frame and len(parts) > 3 else parts[2]
            for node in tree.body:
                if not isinstance(node, ast.ClassDef) or node.name.startswith("_"):
                    continue
                values = _constants(node)
                if not (values.get("ICON") or values.get("KIND")):
                    continue
                icon = str(values.get("ICON") or "")
                doc = (ast.get_docstring(node) or "").strip()
                title = str(values.get("TYPE") or (doc.splitlines()[0] if doc else ""))
                found.append(
                    Found(
                        module=module,
                        name=node.name,
                        title=title.strip().rstrip("."),
                        icon=icon,
                        library="frames" if frame else provider,
                        frame=frame,
                        glyph="Resource glyph" in doc,
                        aliases=overlay.for_service(provider, icon) if icon else (),
                    )
                )
    return tuple(found)


def _constants(node: ast.ClassDef) -> dict[str, object]:
    """The constant class attributes a generated class sets: ICON, KIND, TYPE."""
    values: dict[str, object] = {}
    for item in node.body:
        target: ast.expr
        value: ast.expr | None
        if isinstance(item, ast.Assign) and len(item.targets) == 1:
            target, value = item.targets[0], item.value
        elif isinstance(item, ast.AnnAssign):
            target, value = item.target, item.value
        else:
            continue
        if isinstance(target, ast.Name) and isinstance(value, ast.Constant):
            values[target.id] = value.value
    return values


def _rank(item: Found, phrase: str, words: list[str]) -> tuple[int, int] | None:
    """The item's tier for the query and, in the alias tier, which alias
    matched (0 the first); None when it does not match."""
    compact = phrase.replace(" ", "")
    title = item.title.casefold()
    if compact == item.name.casefold():
        return 0, 0
    if phrase in {
        item.icon.casefold(),
        item.icon.replace("-", " ").casefold(),
        title,
        _VENDOR.sub("", title),
    }:
        return 1, 0
    aliases = [alias.casefold() for alias in item.aliases]
    if phrase in aliases:
        return 1, aliases.index(phrase)
    own = _words(f"{item.library} {_spoken(item.name)} {item.title} {item.icon}")
    if all(any(token.startswith(word) for token in own) for word in words):
        return 2, 0
    every = own + _words(" ".join(item.aliases))
    if all(any(token.startswith(word) for token in every) for word in words):
        return 3, 0
    return None


def _in_library(item: Found, wanted: str) -> bool:
    """Whether *item* belongs to the library (or module) *wanted* names: its
    library, its module's last name, or any part of its module path -- so
    ``aws`` takes the AWS frames too and ``storage`` every storage module."""
    return (
        not wanted
        or wanted in (item.library, item.module.split(".")[-1])
        or f".{wanted}." in f"{item.module}."
    )


def _search(items: Iterable[Found], query: str, library: str | None) -> list[Found]:
    phrase = " ".join(query.casefold().split())
    if not phrase:
        return []
    words = [_stem(word) for word in phrase.split()]
    wanted = (library or "").casefold()
    ranked: list[tuple[int, int, bool, bool, int, int, str, Found]] = []
    for item in items:
        if not _in_library(item, wanted):
            continue
        matched = _rank(item, phrase, words)
        if matched is None:
            continue
        provider = item.module.split(".")[3] if item.frame else item.library
        lead = _LEAD.index(provider) if provider in _LEAD else len(_LEAD)
        ranked.append((*matched, not item.frame, item.glyph, lead, len(item.name), item.name, item))
    ranked.sort(key=lambda entry: entry[:7])
    return [entry[-1] for entry in ranked]


def find(query: str, library: str | None = None) -> list[Found]:
    """The node and frame classes matching *query*, best first (see the module docstring)."""
    return _search(node_classes(), query, library)


@functools.cache
def pattern_classes() -> tuple[Found, ...]:
    """Every public class of ``infragram.patterns`` a diagram file builds
    with, imported from where the docs import it: the package for what the
    package itself exports (``Blueprint``, ``Pattern``), else its module
    (``infragram.patterns.aws``). An exception is not something to build
    with, and a type alias is not a class."""
    from .. import patterns

    found: list[Found] = []
    seen: set[type] = set()
    modules = [patterns] + [
        importlib.import_module(f"{patterns.__name__}.{info.name}")
        for info in pkgutil.iter_modules(patterns.__path__)
        if not info.name.startswith("_")
    ]
    for module in modules:
        for name in getattr(module, "__all__", ()):
            value = getattr(module, name, None)
            if (
                not inspect.isclass(value)
                or isinstance(value, types.GenericAlias)
                or issubclass(value, BaseException)
                or value in seen
            ):
                continue
            seen.add(value)
            doc = inspect.getdoc(value) or ""
            found.append(
                Found(
                    module=module.__name__,
                    name=name,
                    title=doc.splitlines()[0].strip().rstrip(".") if doc else "",
                    library="patterns",
                )
            )
    return tuple(found)


def find_patterns(query: str, library: str | None = None) -> list[Found]:
    """The pattern classes matching *query*, ranked like :func:`find`.

    *library* narrows them the way it narrows classes: ``patterns`` is all of
    them, ``aws`` the AWS patterns, ``hybrid`` the hybrid ones."""
    return _search(pattern_classes(), query, library)


def library_classes(library: str) -> list[Found]:
    """Every class *library* names, the way ``find --library`` narrows a
    search -- the library's nodes and its frames (``frames`` is every frame,
    ``patterns`` the patterns) -- by module, then name. Empty for no such
    library."""
    wanted = library.casefold().strip()
    if not wanted:
        return []
    pool = pattern_classes() if wanted == "patterns" else node_classes()
    return sorted(
        (item for item in pool if _in_library(item, wanted)),
        key=lambda item: (item.module, item.name),
    )


#: The libraries that are not a provider's, by what they hold.
_OWN_LIBRARIES = {
    "infragram": "Shared components (every library offers them)",
    "logos": "Brand logos",
    "iso": "3D items rendered by spec (infragram recipes)",
    "frames": "Every frame, each library's and the generic ones",
    "patterns": "Patterns and the Blueprint (infragram.patterns)",
}


class Library(BaseModel):
    """One library ``find --library`` takes: its id, name and what it holds."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    nodes: int = 0
    frames: int = 0
    patterns: int = 0


def libraries() -> list[Library]:
    """Every library a class can be found in: the installed providers in the
    registry's order, then the shared ones, frames and patterns."""
    from .providers import load_default_provider_registry

    nodes: dict[str, int] = {}
    frames: dict[str, int] = {}
    for item in node_classes():
        if item.frame:
            provider = item.module.split(".")[3]
            frames[provider] = frames.get(provider, 0) + 1
        else:
            nodes[item.library] = nodes.get(item.library, 0) + 1
    registry = load_default_provider_registry()
    providers = list(
        registry.providers.values() if isinstance(registry.providers, dict) else registry.providers
    )
    out = [
        Library(
            id=provider.id,
            name=provider.display_name,
            nodes=nodes.pop(provider.id, 0),
            frames=frames.get(provider.id, 0),
        )
        for provider in providers
    ]
    listed = {library.id for library in out}
    for library_id in ("infragram", "logos", "iso", *sorted(set(nodes) - set(_OWN_LIBRARIES))):
        if library_id in nodes and library_id not in listed:
            out.append(
                Library(
                    id=library_id,
                    name=_OWN_LIBRARIES.get(library_id, library_id),
                    nodes=nodes[library_id],
                )
            )
    out.append(Library(id="frames", name=_OWN_LIBRARIES["frames"], frames=sum(frames.values())))
    out.append(
        Library(id="patterns", name=_OWN_LIBRARIES["patterns"], patterns=len(pattern_classes()))
    )
    return out
