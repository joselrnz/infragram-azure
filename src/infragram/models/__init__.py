"""Core domain models for the infragram tooling.

Every model is a frozen dataclass: validation happens once at load time (in
:mod:`infragram.registries`) and the rest of the tooling consumes immutable
values. Theme models live in :mod:`infragram.themes` and are re-exported
here for convenience.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..themes import Theme

#: The four node roles every provider architecture example renders, in
#: left-to-right drawing order. Provider manifests must define all four.
SERVICE_ROLES = ("entry", "app", "object_store", "database")


@dataclass(frozen=True)
class Service:
    """One labeled node in a provider architecture example."""

    name: str
    detail: str


@dataclass(frozen=True)
class ProviderIcon:
    """One registered SVG icon.

    The provenance fields are not decoration: provider artwork often carries
    terms separate from the repository license, so every icon records where
    it came from, which release, and under which terms, plus the sha256 that
    proves the on-disk bytes still match what was reviewed.
    """

    slug: str
    name: str
    category: str
    path: Path
    aliases: tuple[str, ...]
    source_url: str
    source_release: str
    source_path: str
    terms_url: str
    sha256: str
    #: Which tier of the vendor deck drew this: ``service`` (a coloured
    #: tile), ``resource`` (a line glyph for a thing inside a service) or
    #: ``group`` (a container shape). None for decks that draw one tier.
    tier: str | None = None
    #: For a resource glyph, the id of the service it belongs to, when that
    #: service ships too. Empty otherwise. Resolved by catalog.tiers, which
    #: says why the pairing matters.
    parent_service: str = ""
    #: The artwork itself, for icons that live in a gallery document rather
    #: than a file of their own (the shared primitives). None means read
    #: ``path``.
    markup: str | None = None


@dataclass(frozen=True)
class Provider:
    """A fully validated provider skin.

    Built only by :func:`infragram.registries.load_catalog`, which resolves
    and checks every path, color, and icon digest first, so consumers can
    treat each field as trustworthy.
    """

    slug: str
    name: str
    title: str
    manifest_path: Path
    mark_path: Path
    icon_catalog_path: Path
    icon_categories: tuple[str, ...]
    icons: dict[str, ProviderIcon]
    icon_aliases: dict[str, str]
    service_icon_slugs: dict[str, str]
    service_icon_paths: dict[str, Path]
    theme: Theme
    icon_palette: tuple[str, ...]
    services: dict[str, Service]
