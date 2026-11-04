"""Attribute access over an icon collection, grouped by service category.

Two levels, the way a reader thinks about a vendor's catalogue::

    azure.compute.VirtualMachine        category, then icon
    azure.VirtualMachine                flat, when the name is unambiguous
    azure.find("vnet")                  curated aliases from the catalog
    azure["virtual-machine"]            by literal id

Case disambiguates the two levels: category slugs are lowercase
(``azure.compute``), icon names are CapitalCase (``azure.VirtualMachine``).

Nothing is generated. With 1,352 vendor icons and 4,896 logos, emitting a
class per icon would be a large generated surface that drifts from the
catalog the moment an importer runs -- the exact failure mode this
repository has already been bitten by. The catalog stays the single source
of truth and this is a thin accessor over it.

The cost is that names resolve at runtime, so a typo fails when the builder
runs rather than when you type it. ``find()`` and the suggestions in the
AttributeError soften that.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path

from ..models import ProviderIcon
from ..verification import SLUG
from .naming import class_name

_class_name = class_name


class _Icons:
    """Shared attribute/lookup behaviour over a fixed set of catalog entries."""

    def __init__(self, label: str, root: Path, entries: dict[str, dict]) -> None:
        self._label = label
        self._root = root
        self._entries = entries
        # Resolved once: resolving is a system call per path on Windows, and
        # a page looks up thousands of icons in the same few packs.
        self._resolved_root = root.resolve()
        self._contained_paths: dict[str, Path] = {}
        self._by_class = {_class_name(slug): slug for slug in entries}
        # Built once: a resource glyph names the service it belongs to, and
        # the pairing is looked up per icon. See catalog.tiers.
        from ..catalog import tiers

        self._service_names = tiers.service_names(list(entries.values()))

    @property
    def classes(self) -> dict[str, str]:
        """CamelCase class name -> icon id, the naming node classes reuse."""
        return dict(self._by_class)

    def record(self, slug: str) -> dict:
        """The raw catalog entry for an icon id."""
        return self._entries[slug]

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return (self[slug] for slug in self._entries)

    def __dir__(self) -> list[str]:
        return sorted(self._by_class)

    #: Preference order when a logo entry offers several variants.
    VARIANT_ORDER = ("default", "color", "mono", "light", "dark", "icon", "wordmark")

    def _parent_of(self, entry: dict) -> str:
        """The service a resource glyph belongs to, by the one shared rule."""
        from ..catalog import tiers

        service = tiers.parent_service(entry, self._service_names)
        return str(service.get("id") or "") if service else ""

    def _contained(self, relative: str) -> Path:
        """A file the catalog names, proved to be inside the collection.

        The catalog is data like any other, so a `file` entry that climbs out
        of the pack would otherwise read an arbitrary file and inline it into
        an export as artwork.
        """
        known = self._contained_paths.get(relative)
        if known is not None:
            return known
        resolved = (self._root / relative).resolve()
        if not resolved.is_relative_to(self._resolved_root):
            raise ValueError(f"{self._label}: {relative!r} escapes the collection")
        self._contained_paths[relative] = resolved
        return resolved

    def __getitem__(self, key: str) -> ProviderIcon:
        """``slug`` or ``slug#variant`` for collections that ship variants."""
        slug, _, variant = key.partition("#")
        entry = self._entries.get(slug)
        if entry is None:
            raise KeyError(f"{self._label} has no icon id {slug!r}")
        if not SLUG.fullmatch(slug):
            raise ValueError(f"invalid icon id in {self._label}: {slug!r}")
        relative, digest = self._file_of(entry, slug, variant)
        return ProviderIcon(
            slug=slug if not variant else f"{slug}-{variant}",
            name=entry.get("name", slug),
            category=entry.get("category", ""),
            path=self._contained(relative),
            aliases=tuple(entry.get("aliases", ())),
            source_url=entry.get("source_url", ""),
            source_release=entry.get("source_release", ""),
            source_path=entry.get("source_path", ""),
            terms_url=entry.get("terms_url", ""),
            sha256=digest,
            tier=entry.get("tier") or None,
            parent_service=self._parent_of(entry),
        )

    def _file_of(self, entry: dict, slug: str, variant: str) -> tuple[str, str]:
        """Resolve one file from either catalog shape.

        Vendor packs carry a single ``file``; logo entries carry ``variants``
        keyed by name, with ``sha256`` as a mapping rather than a string.
        """
        if "file" in entry:
            if variant:
                raise KeyError(f"{self._label}: {slug!r} has no variants")
            return entry["file"], entry.get("sha256", "")

        variants = entry.get("variants") or {}
        if not variants:
            raise KeyError(f"{self._label}: {slug!r} has neither file nor variants")
        if variant:
            if variant not in variants:
                raise KeyError(
                    f"{self._label}: {slug!r} has no variant {variant!r}; "
                    f"available: {', '.join(sorted(variants))}"
                )
            chosen = variant
        else:
            chosen = next((v for v in self.VARIANT_ORDER if v in variants), sorted(variants)[0])
        digests = entry.get("sha256")
        digest = digests.get(chosen, "") if isinstance(digests, dict) else (digests or "")
        return variants[chosen], digest

    def variants(self, slug: str) -> list[str]:
        """Variant names available for an entry, empty for single-file icons."""
        entry = self._entries.get(slug)
        if entry is None:
            raise KeyError(f"{self._label} has no icon id {slug!r}")
        return sorted(entry.get("variants") or {})

    def _resolve_class(self, name: str) -> ProviderIcon:
        slug = self._by_class.get(name)
        if slug is not None:
            return self[slug]
        close = difflib.get_close_matches(name, self._by_class, n=3, cutoff=0.6)
        hint = f"; did you mean {', '.join(close)}?" if close else ""
        raise AttributeError(f"{self._label} has no icon {name!r}{hint}")


class CategoryView(_Icons):
    """One service category within a collection: ``azure.compute``."""

    def __getattr__(self, name: str) -> ProviderIcon:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._resolve_class(name)

    def __repr__(self) -> str:
        return f"<{self._label}: {len(self)} icons>"


class IconSet(_Icons):
    """A vendor collection, addressable flat or by category."""

    def __init__(self, collection: str, root: Path) -> None:
        catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
        entries = {entry["id"]: entry for entry in catalog["icons"]}
        super().__init__(collection, root, entries)
        self._collection = collection

        self._categories: dict[str, dict[str, dict]] = {}
        for slug, entry in entries.items():
            self._categories.setdefault(entry.get("category", "uncategorised"), {})[slug] = entry

        # Alias -> id, built in catalog order. Packs share names between
        # entries freely (the on-premises library alone has hundreds of
        # tiles that answer to one word), so the first entry in the
        # catalog to claim a name keeps it: ``find`` is deterministic, and
        # ``alias_collisions`` reports every name claimed more than once.
        self._aliases: dict[str, str] = {}
        self._collisions: dict[str, list[str]] = {}
        for slug, entry in entries.items():
            for alias in (slug, entry.get("name", ""), *entry.get("aliases", ())):
                if not alias:
                    continue
                key = alias.casefold()
                owner = self._aliases.setdefault(key, slug)
                if owner != slug:
                    losers = self._collisions.setdefault(key, [owner])
                    if slug not in losers:
                        losers.append(slug)

    @property
    def categories(self) -> list[str]:
        return sorted(self._categories)

    def category(self, name: str) -> CategoryView:
        # Category slugs are kebab-case on disk, so accept the underscore
        # spelling too: azure.management_governance -> "management-governance".
        slug = name if name in self._categories else name.replace("_", "-")
        entries = self._categories.get(slug)
        if entries is None:
            close = difflib.get_close_matches(slug, self._categories, n=3, cutoff=0.6)
            hint = f"; did you mean {', '.join(close)}?" if close else ""
            raise KeyError(f"{self._collection} has no category {name!r}{hint}")
        return CategoryView(f"{self._collection}.{slug}", self._root, entries)

    def alias_collisions(self) -> dict[str, list[str]]:
        """Every name more than one entry answers to, with the ids that
        claim it in catalog order: the first is the one ``find`` returns."""
        return {alias: list(ids) for alias, ids in self._collisions.items()}

    def find(self, query: str) -> ProviderIcon:
        """Resolve by id, display name, or a curated alias.

        Case-insensitive. When several entries answer to the name, the
        first in catalog order wins, every time (see ``alias_collisions``);
        an id is always unambiguous, so pass one when it matters.
        """
        slug = self._aliases.get(query.strip().casefold())
        if slug is None:
            close = difflib.get_close_matches(query.casefold(), self._aliases, n=3, cutoff=0.6)
            hint = f"; closest: {', '.join(close)}" if close else ""
            raise KeyError(f"{self._collection}: nothing matches {query!r}{hint}")
        return self[slug]

    def __getattr__(self, name: str) -> ProviderIcon | CategoryView:
        if name.startswith("_"):
            raise AttributeError(name)
        # lowercase reads as a category, CapitalCase as an icon
        if name[:1].islower():
            return self.category(name)
        return self._resolve_class(name)

    def __dir__(self) -> list[str]:
        return sorted([*self._by_class, *(c.replace("-", "_") for c in self._categories)])

    def __repr__(self) -> str:
        return (
            f"<IconSet {self._collection!r}: {len(self)} icons "
            f"in {len(self._categories)} categories>"
        )
