"""Provider-qualified component catalogs independent from editor markup."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from ..paths import skill_assets, skill_references
from ..registries.icons import IconSet
from .aliases import load_default_alias_overlay
from .categories import (
    UnknownCategoryError,
    load_default_provider_mappings,
)
from .providers import ProviderDescriptor, load_default_provider_registry
from .specs import (
    _AWS_BOUNDARY_IDS,
    ARCHITECTURE_BOUNDARY_GROUPS,
    ARCHITECTURE_BOUNDARY_SPECS,
    ARCHITECTURE_FRAME_PRESETS,
    CLOUDFLARE_COMPONENT_SPECS,
    CUSTOM_COMPONENT_SPECS,
    ONPREM_COMPONENT_SPECS,
    SHARED_PRIMITIVE_SPECS,
    PrimitiveComponentSpec,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..models.topology import TopologyElement

# Neutral primitives are shared by every provider library.  The SVG artwork is
# stored once in references/primitive-icons.md with its upstream attribution;
# editor exports embed the resolved SVG bytes, so generated HTML stays offline.


# Cloudflare is a first-class, discoverable provider library rather than a
# handful of shared cards hidden among neutral components. These are every
# reviewed Cloudflare artwork set currently shipped in the logo catalog.


# Local/on-premises names are deliberately operational rather than vendor
# branded.  They reuse the same primitive artwork while exposing a dedicated
# provider library for datacenter, office, lab, and edge topologies.


@lru_cache(maxsize=1)
def _primitive_icon_document() -> str:
    return (skill_references() / "primitive-icons.md").read_text(encoding="utf-8")


#: The ink the built-in line icons are painted in. An SVG loaded through
#: <img> cannot inherit the page's currentColor, so the token is resolved
#: here, once, to the near-black the captions use: a grey read as disabled.
PRIMITIVE_INK = "#16191f"
BRAND_SILHOUETTE_INK = PRIMITIVE_INK


@cache
def primitive_icon_svg(icon_id: str) -> bytes:
    """Resolve one neutral primitive from the shipped, attributed gallery.

    Cached for every id: each miss searches the whole gallery, and every
    library's sidebar asks for the same shared primitives again.
    """

    if icon_id.startswith("logo:"):
        relative = icon_id.removeprefix("logo:")
        if not re.fullmatch(r"[a-z0-9-]+/[a-z0-9-]+", relative):
            raise KeyError(f"invalid Infragram logo icon: {icon_id}")
        path = skill_assets() / "icons" / "logos" / f"{relative}.svg"
        if not path.is_file():
            raise KeyError(f"unknown Infragram logo icon: {icon_id}")
        return path.read_bytes()

    svg = _primitive_icon_index().get(icon_id)
    if svg is None:
        raise KeyError(f"unknown Infragram primitive icon: {icon_id}")
    return svg.strip().replace("currentColor", PRIMITIVE_INK).encode("utf-8")


#: One gallery entry: its ``### id`` heading, then the first ``svg`` block
#: after it, before the next heading.
_GALLERY_ENTRY = re.compile(
    r"^### (?P<id>\S+)\s*$(?:(?!^### ).)*?^```svg\s*$\n(?P<svg>.*?)\n^```\s*$",
    flags=re.DOTALL | re.MULTILINE,
)


@lru_cache(maxsize=1)
def _primitive_icon_index() -> dict[str, str]:
    """Every primitive's SVG by id, read from the gallery in one pass: a
    search of the whole gallery per icon cost about a second an export."""

    index: dict[str, str] = {}
    for entry in _GALLERY_ENTRY.finditer(_primitive_icon_document()):
        index.setdefault(entry["id"], entry["svg"])
    return index


# Infragram-owned, provider-aware architecture frames.  These are drawn by the
# editor rather than copied from a vendor stencil, so they remain editable and
# portable in self-contained HTML exports.


# Provider-specific starter hierarchies. Location and ownership frames are not
# forced into a single universal tree: Azure resource groups can hold resources
# from several regions, while Google VPC networks are global and subnets are
# regional. Presets use only stable, useful architecture containment.


def architecture_boundary_group(service_id: str) -> str:
    """Return the provider gallery that owns a reusable architecture frame."""

    if service_id in _AWS_BOUNDARY_IDS or "-aws-" in service_id:
        return "aws"
    for token, provider in (
        ("-cloudflare-", "cloudflare"),
        ("-azure-", "azure"),
        ("-gcp-", "gcp"),
        ("-do-", "digitalocean"),
        ("-oci-", "oracle"),
        ("-ibm-", "ibm"),
        ("-alibaba-", "alibaba"),
        ("-kubernetes-", "kubernetes"),
        ("-hetzner-", "hetzner"),
        ("-onprem-", "onprem"),
        ("-ovh-", "ovhcloud"),
        ("-vultr-", "vultr"),
        ("-akamai-", "akamai"),
        ("-openstack-", "openstack"),
        ("-vmware-", "vmware"),
        ("-proxmox-", "proxmox"),
        ("-databricks-", "databricks"),
        ("-equinix-", "equinix"),
    ):
        if token in service_id:
            return provider
    return "generic"


def architecture_boundary_level(kind: str) -> int:
    """Rank a frame from outer ownership boundary to inner workload group."""

    levels = {
        "cloud": 0,
        "organization": 0,
        "management-group": 1,
        "account": 1,
        "subscription": 1,
        "folder": 1,
        # A team owns projects (DigitalOcean), so it sits with the accounts.
        "team": 1,
        # An environment (prod / staging / dev) wraps everything an account
        # deploys for one stage, so it ranks with the accounts.
        "environment": 1,
        "project": 2,
        "resource-group": 2,
        "compartment": 2,
        "directory": 2,
        "region": 3,
        "location": 3,
        "site": 3,
        "campus": 3,
        "vpc": 4,
        "network": 4,
        # A Cloudflare zone is a domain, not a placement zone: it sits with
        # the networks it fronts. Every other library's `zone` is an
        # availability zone and keeps its own rank below.
        "hub": 4,
        "spoke": 4,
        "management": 4,
        "storage-fabric": 4,
        "zone": 5,
        "closet": 5,
        "subnet-public": 6,
        "subnet-private": 6,
        "dmz": 6,
        "security-zone": 7,
        "security-group": 7,
        # A scaling boundary wraps the instances it grows, so it sits with
        # the other workload groupings rather than with the networks.
        "auto-scaling": 7,
        "firewall": 7,
        "cluster": 7,
        "namespace": 8,
        "node-pool": 8,
        "server-group": 8,
        "group": 8,
    }
    return levels.get(kind, 7)


def architecture_boundary_default_size(kind: str) -> tuple[int, int]:
    """Return a 4 px-grid default size appropriate for a frame's scope."""

    if kind in {"cloud", "organization", "team"}:
        return (520, 360)
    if kind in {"management-group", "account", "subscription", "folder", "environment"}:
        return (480, 320)
    if kind in {
        "project",
        "resource-group",
        "compartment",
        "region",
        "vpc",
        "network",
        "hub",
        "spoke",
        "management",
        "storage-fabric",
        "campus",
    }:
        return (400, 280)
    if kind in {"zone", "location", "site", "dmz"}:
        return (360, 240)
    if kind in {"subnet-public", "subnet-private"}:
        return (256, 144)
    return (320, 200)


@dataclass(frozen=True, slots=True)
class CatalogComponent:
    provider: str
    provider_name: str
    service_id: str
    qualified_id: str
    name: str
    subtitle: str
    category_id: str
    aliases: tuple[str, ...] = ()
    icon_path: Path | None = None
    mapping_status: str = "mapped"
    component_kind: str = "node"
    boundary_kind: str = ""


@dataclass(frozen=True, slots=True)
class ProviderComponentCatalog:
    provider: ProviderDescriptor
    components: tuple[CatalogComponent, ...]


@dataclass(frozen=True, slots=True)
class CompositeCatalog:
    providers: tuple[ProviderDescriptor, ...]
    components: tuple[CatalogComponent, ...]

    def search(self, query: str) -> tuple[CatalogComponent, ...]:
        normalized = " ".join(query.casefold().split())
        if not normalized:
            return ()
        tokens = normalized.split()

        def haystack(component: CatalogComponent) -> str:
            return " ".join(
                (
                    component.provider,
                    component.provider_name,
                    component.service_id,
                    component.qualified_id,
                    component.name,
                    component.subtitle,
                    *component.aliases,
                )
            ).casefold()

        matches = [
            component
            for component in self.components
            if all(token in haystack(component) for token in tokens)
        ]

        def rank(component: CatalogComponent) -> tuple[int, str, str]:
            name = component.name.casefold()
            exact = normalized in {
                component.service_id.casefold(),
                component.qualified_id.casefold(),
                name,
            }
            starts = name.startswith(normalized)
            return (0 if exact else 1 if starts else 2, name, component.qualified_id)

        return tuple(sorted(matches, key=rank))


def _shared_components() -> tuple[CatalogComponent, ...]:
    primitives = tuple(
        CatalogComponent(
            provider="infragram",
            provider_name="Infragram",
            service_id=service_id,
            qualified_id=f"infragram:{service_id}",
            name=name,
            subtitle=subtitle,
            category_id="custom",
            component_kind=component_kind,
            boundary_kind=boundary_kind,
        )
        for service_id, name, subtitle, component_kind, boundary_kind in CUSTOM_COMPONENT_SPECS
    )
    boundaries = tuple(
        CatalogComponent(
            provider="infragram",
            provider_name="Infragram",
            service_id=service_id,
            qualified_id=f"infragram:{service_id}",
            name=name,
            subtitle=subtitle,
            category_id="custom",
            component_kind="boundary",
            boundary_kind=boundary_kind,
        )
        for service_id, name, subtitle, boundary_kind, _glyph, _paint in ARCHITECTURE_BOUNDARY_SPECS
    )
    shared_icons = tuple(
        CatalogComponent(
            provider="infragram",
            provider_name="Infragram",
            service_id=spec.service_id,
            qualified_id=f"infragram:{spec.service_id}",
            name=spec.name,
            subtitle=spec.subtitle,
            category_id=spec.category_id,
            aliases=spec.aliases,
        )
        for spec in SHARED_PRIMITIVE_SPECS
    )
    return primitives + boundaries + shared_icons


#: Libraries whose platform is itself placeable, not just its services: the
#: Kubernetes mark stands for the cluster the rest of the library runs on.
#: The artwork is the theme's mark rather than an entry in a vendor icon
#: pack, which is why the card has to be added by hand on both catalog paths.
PLATFORM_CARDS: dict[str, dict[str, object]] = {
    "kubernetes": {
        "service_id": "kubernetes",
        "name": "Kubernetes",
        "subtitle": "Platform",
        "category_id": "containers",
        "aliases": ("k8s", "cluster", "platform"),
        "mark": "kubernetes.svg",
    },
}


def _platform_card(provider: ProviderDescriptor) -> tuple[CatalogComponent, ...]:
    """The platform card for a library that has one, else nothing.

    The card used to be added only when a library had no vendor pack, so the
    shipped Kubernetes pack meant it never ran and ``kubernetes:kubernetes``
    was missing from the catalog while the sidebar and the inventory both
    offered it.
    """
    card = PLATFORM_CARDS.get(provider.id)
    if card is None:
        return ()
    service_id = str(card["service_id"])
    return (
        CatalogComponent(
            provider=provider.id,
            provider_name=provider.display_name,
            service_id=service_id,
            qualified_id=f"{provider.id}:{service_id}",
            name=str(card["name"]),
            subtitle=str(card["subtitle"]),
            category_id=str(card["category_id"]),
            aliases=tuple(card["aliases"]),  # type: ignore[arg-type]
            icon_path=skill_assets() / "themes" / "marks" / str(card["mark"]),
        ),
    )


@cache
def load_provider_component_catalog(provider_id: str) -> ProviderComponentCatalog:
    registry = load_default_provider_registry()
    try:
        provider = registry[provider_id]
    except KeyError as error:
        raise ValueError(f"unknown provider: {provider_id}") from error

    vendor_root = skill_assets() / "icons" / "vendors" / provider.id
    if not (vendor_root / "catalog.json").is_file():
        # Every shipped library has its vendor catalog. One without it is an
        # incomplete install, and four placeholder cards would hide that.
        raise ValueError(
            f"library {provider.id!r} has no vendor icon catalog at {vendor_root / 'catalog.json'}"
        )

    mappings = load_default_provider_mappings()
    aliases = load_default_alias_overlay()
    icons = IconSet(provider.id, vendor_root)
    components: list[CatalogComponent] = list(_platform_card(provider))
    for icon in icons:
        mapping_status = "mapped"
        try:
            category_id = mappings.normalize(
                provider.id,
                icon.category,
                service_id=icon.slug,
            )
        except UnknownCategoryError:
            category_id = "custom"
            mapping_status = f"unmapped:{icon.category}"
        components.append(
            CatalogComponent(
                provider=provider.id,
                provider_name=provider.display_name,
                service_id=icon.slug,
                qualified_id=f"{provider.id}:{icon.slug}",
                name=icon.name,
                subtitle=icon.category.replace("-", " ").title(),
                category_id=category_id,
                aliases=aliases.merge(provider.id, icon.slug, icon.aliases),
                icon_path=icon.path,
                mapping_status=mapping_status,
            )
        )
    if provider.id == "onprem":
        existing_ids = {component.service_id for component in components}
        components.extend(
            CatalogComponent(
                provider=provider.id,
                provider_name=provider.display_name,
                service_id=spec.service_id,
                qualified_id=f"{provider.id}:{spec.service_id}",
                name=spec.name,
                subtitle=spec.subtitle,
                category_id=spec.category_id,
                aliases=spec.aliases,
            )
            for spec in ONPREM_COMPONENT_SPECS
            if spec.service_id not in existing_ids
        )
    if provider.id == "cloudflare":
        # the four reviewed product marks sit beside the drawn service tiles
        existing_ids = {component.service_id for component in components}
        components.extend(
            CatalogComponent(
                provider=provider.id,
                provider_name=provider.display_name,
                service_id=spec.service_id,
                qualified_id=f"{provider.id}:{spec.service_id}",
                name=spec.name,
                subtitle=spec.subtitle,
                category_id=spec.category_id,
                aliases=spec.aliases,
            )
            for spec in CLOUDFLARE_COMPONENT_SPECS
            if spec.service_id not in existing_ids
        )
    return ProviderComponentCatalog(
        provider=provider,
        components=tuple(sorted(components, key=lambda item: item.name.casefold())),
    )


@cache
def component_categories(provider: str) -> dict[str, str]:
    """service id -> canonical category, for one library's components.

    Empty for a name that is no installed library: the readers ask about
    whatever a document names, and a component they cannot place simply has
    no category rather than stopping the view or the review.
    """
    try:
        catalog = load_provider_component_catalog(provider)
    except (ValueError, KeyError, OSError):
        return {}
    return {component.service_id: component.category_id for component in catalog.components}


def component_category(element: TopologyElement) -> str:
    """The canonical category of the catalog component an element draws, or
    "" when it draws none."""
    component = element.component
    if component is None:
        return ""
    return component_categories(component.provider).get(component.service_id, "")


def _normalize_selection(providers: Iterable[str] | None) -> tuple[str, ...]:
    registry = load_default_provider_registry()
    selected = (
        tuple(provider.id for provider in registry.providers)
        if providers is None
        else tuple(str(provider).strip().casefold() for provider in providers)
    )
    duplicates = sorted(provider for provider in set(selected) if selected.count(provider) > 1)
    if duplicates:
        raise ValueError(f"duplicate provider selection: {', '.join(duplicates)}")
    unknown = sorted(set(selected) - set(registry.by_id))
    if unknown:
        raise ValueError(f"unknown provider: {', '.join(unknown)}")
    if not selected:
        raise ValueError("at least one provider must be selected")
    return selected


@lru_cache(maxsize=64)
def _load_composite_catalog(selected: tuple[str, ...]) -> CompositeCatalog:
    provider_catalogs = tuple(load_provider_component_catalog(item) for item in selected)
    components = (
        *_shared_components(),
        *(component for catalog in provider_catalogs for component in catalog.components),
    )
    qualified_ids = [component.qualified_id for component in components]
    if len(qualified_ids) != len(set(qualified_ids)):
        raise ValueError("composite catalog contains duplicate qualified component ids")
    return CompositeCatalog(
        providers=tuple(catalog.provider for catalog in provider_catalogs),
        components=tuple(components),
    )


def load_composite_catalog(
    providers: Sequence[str] | None = None,
) -> CompositeCatalog:
    """Load provider-qualified components for a selected library set."""

    return _load_composite_catalog(_normalize_selection(providers))


__all__ = [
    "ARCHITECTURE_BOUNDARY_GROUPS",
    "ARCHITECTURE_BOUNDARY_SPECS",
    "CLOUDFLARE_COMPONENT_SPECS",
    "ARCHITECTURE_FRAME_PRESETS",
    "CUSTOM_COMPONENT_SPECS",
    "ONPREM_COMPONENT_SPECS",
    "PrimitiveComponentSpec",
    "SHARED_PRIMITIVE_SPECS",
    "CatalogComponent",
    "CompositeCatalog",
    "ProviderComponentCatalog",
    "architecture_boundary_default_size",
    "architecture_boundary_group",
    "architecture_boundary_level",
    "load_composite_catalog",
    "load_provider_component_catalog",
    "primitive_icon_svg",
]
