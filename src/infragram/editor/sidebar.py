"""The component library the editor offers: catalogs and the payload.

One :class:`SidebarCatalog` per provider, built from that provider's icon
pack or component specs plus the shared primitives and the frame gallery,
and :func:`_library_payload`, the JSON the browser filters and drags from.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from pydantic import BaseModel, ConfigDict, SkipValidation

from ..builders.architecture import load_icon_set
from ..catalog import (
    ARCHITECTURE_BOUNDARY_GROUPS,
    ARCHITECTURE_BOUNDARY_SPECS,
    ARCHITECTURE_FRAME_PRESETS,
    CLOUDFLARE_COMPONENT_SPECS,
    ONPREM_COMPONENT_SPECS,
    SHARED_PRIMITIVE_SPECS,
    UnknownCategoryError,
    architecture_boundary_default_size,
    architecture_boundary_group,
    architecture_boundary_level,
    load_default_alias_overlay,
    load_default_category_registry,
    load_default_provider_mappings,
    load_default_provider_registry,
    primitive_icon_svg,
)
from ..catalog.display import default_display
from ..paths import skill_assets
from ..themes import theme_manifest
from .artwork import (
    _boundary_component_style,
    _boundary_preview_uri,
    _data_uri,
    _glyph_uri,
)

_CUSTOM = (
    ("custom-annotation", "Annotation", "Add annotations and notes", "A", "node", ""),
    ("custom-label", "Label", "Add labels", "T", "node", ""),
    ("custom-resource", "Custom Resource", "Add custom resources", "+", "node", ""),
    ("custom-section", "Section", "Add section boundaries", "▦", "boundary", "group"),
    ("custom-shape", "Shape", "Add basic shapes", "◇", "node", ""),
    ("custom-3d", "3D render", "An item rendered by spec, not by name", "3", "node", ""),
)


@dataclass(frozen=True, slots=True)
class SidebarComponent:
    id: str
    name: str
    subtitle: str
    category_id: str
    icon_uri: str
    provider_id: str = ""
    mapping_status: str = "mapped"
    component_kind: str = "node"
    boundary_kind: str = ""
    frame_group: str = ""
    hierarchy_level: int = 0
    default_width: int = 0
    default_height: int = 0
    boundary_style: dict[str, object] | None = None
    #: ``service``, ``resource`` or ``group``: which tier of the deck drew it.
    tier: str = "service"
    #: The category as the vendor deck files it (``general``, ``iot``), before
    #: mapping onto the sidebar's canonical set; the display rules read it.
    native_category: str = ""
    #: Extra words the sidebar search should match: the catalog's own aliases
    #: plus the curated overlay, so "kms", "vnet" and "configmap" find the
    #: card the same way they find the component in the Python catalog.
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SidebarCategory:
    id: str
    label: str
    components: tuple[SidebarComponent, ...]


class SidebarCatalog(BaseModel):
    """One library's sidebar: its name, its mark and its categories.

    ``provider_mark_dark_uri`` is the mark for the dark themes when the
    library draws it differently there (AWS's wordmark is navy on white and
    white on dark); empty when one mark serves both.
    """

    model_config = ConfigDict(frozen=True)

    provider: str
    provider_name: str
    provider_mark_uri: str
    provider_mark_dark_uri: str = ""
    # built from the catalogs by this module, thousands of components: not validated again
    categories: SkipValidation[tuple[SidebarCategory, ...]]

    @property
    def component_count(self) -> int:
        return sum(len(category.components) for category in self.categories)


def _provider_mark_uri(provider: str, manifest: dict, *, dark: bool = False) -> str:
    """The library's mark as a data URI; with ``dark``, the dark themes'
    mark when the manifest gives it a colour of its own (``mark_color_dark``),
    else empty."""
    dark_color = manifest.get("mark_color_dark")
    if dark and not (isinstance(dark_color, str) and dark_color):
        return ""
    mark = manifest.get("mark", "")
    if not isinstance(mark, str) or not mark:
        return ""
    is_catalog_ref = ":" in mark
    if is_catalog_ref:
        collection, _, slug = mark.partition(":")
        try:
            pack = load_icon_set(collection)
            icon = pack[slug] if "#" in slug else pack.find(slug)
            path = icon.path
        except (KeyError, ValueError):
            return ""
    else:
        path = skill_assets() / "themes" / mark
    if not path.is_file():
        return ""
    artwork = path.read_text(encoding="utf-8")
    mark_color = dark_color if dark else manifest.get("mark_color")
    if isinstance(mark_color, str) and mark_color:
        artwork = artwork.replace("currentColor", mark_color)
    elif not is_catalog_ref:
        accent = str((manifest.get("theme") or {}).get("accent") or "#0078d4")
        artwork = artwork.replace("currentColor", accent)
    return _data_uri(artwork.encode("utf-8"))


#: How a vendor's icon folder reads as a card's subtitle, where title case
#: alone would get it wrong ("Ai Machine Learning", "Iot", "Generic Os").
_FOLDER_TITLES = {
    "ai": "AI",
    "ai-machine-learning": "AI & Machine Learning",
    "app-services": "App Services",
    "devops": "DevOps",
    "dns": "DNS",
    "elastic-saas": "Elastic SaaS",
    "generic-os": "Generic OS",
    "hybrid-multicloud": "Hybrid & MultiCloud",
    "iot": "Internet of Things",
    "management-governance": "Management & Governance",
}

#: Folders that only sort a vendor's files. They say nothing about the
#: service, so its card is subtitled with the category it is listed under.
_SORTING_FOLDERS = frozenset({"general", "menu", "new-icons", "other"})


def _folder_subtitle(folder: str, category_label: str) -> str:
    if folder in _SORTING_FOLDERS:
        return category_label
    return _FOLDER_TITLES.get(folder) or folder.replace("-", " ").title()


# One entry per library, for the life of the process: a bound below the
# library count evicts each catalog just before a page asks for it again.
@cache
def load_sidebar_catalog(provider: str) -> SidebarCatalog:
    """Load every reviewed component for one provider into canonical groups."""

    registry = load_default_category_registry()
    mappings = load_default_provider_mappings()
    alias_overlay = load_default_alias_overlay()
    manifest = theme_manifest(provider)
    grouped: dict[str, list[SidebarComponent]] = {
        category.id: [] for category in registry.categories
    }
    category_labels = {category.id: category.label for category in registry.categories}
    for component_id, name, subtitle, glyph, component_kind, boundary_kind in _CUSTOM:
        grouped["custom"].append(
            SidebarComponent(
                id=component_id,
                name=name,
                subtitle=subtitle,
                category_id="custom",
                icon_uri=_glyph_uri(glyph),
                provider_id="infragram",
                component_kind=component_kind,
                boundary_kind=boundary_kind,
            )
        )
    for spec in SHARED_PRIMITIVE_SPECS:
        grouped[spec.category_id].append(
            SidebarComponent(
                id=spec.service_id,
                name=spec.name,
                subtitle=spec.subtitle,
                category_id=spec.category_id,
                icon_uri=_data_uri(primitive_icon_svg(spec.icon_id)),
                provider_id="infragram",
                aliases=spec.aliases,
            )
        )
    for component_id, name, subtitle, boundary_kind, glyph, _paint in ARCHITECTURE_BOUNDARY_SPECS:
        frame_group = architecture_boundary_group(component_id)
        style = _boundary_component_style(frame_group, boundary_kind)
        default_width, default_height = architecture_boundary_default_size(boundary_kind)
        grouped["custom"].append(
            SidebarComponent(
                id=component_id,
                name=name,
                subtitle=subtitle,
                category_id="custom",
                icon_uri=_boundary_preview_uri(glyph, style),
                provider_id="infragram",
                component_kind="boundary",
                boundary_kind=boundary_kind,
                frame_group=frame_group,
                hierarchy_level=architecture_boundary_level(boundary_kind),
                default_width=default_width,
                default_height=default_height,
                boundary_style=style,
                aliases=("frame", "boundary", boundary_kind.replace("-", " ")),
            )
        )

    try:
        icons = load_icon_set(provider)
    except KeyError as error:
        # Every shipped library has its vendor catalog. One without it is an
        # incomplete install, and four placeholder cards would hide that.
        reason = error.args[0] if error.args else ""
        raise KeyError(f"library {provider!r} has no vendor icon catalog: {reason}") from error
    provider_components: list[SidebarComponent] = []
    if provider == "kubernetes":
        provider_components.append(
            SidebarComponent(
                id="kubernetes",
                name="Kubernetes",
                subtitle="Platform",
                category_id="containers",
                icon_uri=_provider_mark_uri(provider, manifest),
                provider_id=provider,
            )
        )
    if provider == "onprem":
        existing_ids = {component.id for component in provider_components}
        provider_components.extend(
            SidebarComponent(
                id=spec.service_id,
                name=spec.name,
                subtitle=spec.subtitle,
                category_id=spec.category_id,
                icon_uri=_data_uri(primitive_icon_svg(spec.icon_id)),
                provider_id="onprem",
                aliases=spec.aliases,
            )
            for spec in ONPREM_COMPONENT_SPECS
            if spec.service_id not in existing_ids
        )
    for icon in icons:
        mapping_status = "mapped"
        try:
            category_id = mappings.normalize(provider, icon.category, service_id=icon.slug)
        except UnknownCategoryError:
            # Keep every reviewed component visible while making the
            # classification debt explicit in the UI and DOM contract.
            category_id = "custom"
            mapping_status = f"unmapped:{icon.category}"
        provider_components.append(
            SidebarComponent(
                id=icon.slug,
                name=icon.name,
                subtitle=_folder_subtitle(icon.category, category_labels.get(category_id, "")),
                category_id=category_id,
                icon_uri=_data_uri(icon.path.read_bytes()),
                provider_id=provider,
                mapping_status=mapping_status,
                aliases=alias_overlay.merge(provider, icon.slug, icon.aliases),
                tier=icon.tier or "service",
                native_category=icon.category,
            )
        )
    if provider == "cloudflare":
        # The four reviewed product marks sit beside the drawn service
        # tiles, the same way the Python catalog lists them. A tile that
        # took a mark's id wins: the drawn artwork is the reviewed one.
        existing_ids = {component.id for component in provider_components}
        provider_components.extend(
            SidebarComponent(
                id=spec.service_id,
                name=spec.name,
                subtitle=spec.subtitle,
                category_id=spec.category_id,
                icon_uri=_data_uri(primitive_icon_svg(spec.icon_id)),
                provider_id="cloudflare",
                aliases=spec.aliases,
            )
            for spec in CLOUDFLARE_COMPONENT_SPECS
            if spec.service_id not in existing_ids
        )

    for component in provider_components:
        grouped[component.category_id].append(component)
    counts = {category.id: len(grouped[category.id]) for category in registry.categories}
    categories = tuple(
        SidebarCategory(
            id=category.id,
            label=category.label,
            components=tuple(sorted(grouped[category.id], key=lambda item: item.name.casefold())),
        )
        # Every provider uses the same Infragram infrastructure navigation contract.
        # Empty groups remain visible so switching providers never changes the
        # sidebar's category order or interaction model.
        for category in registry.visible(counts, show_empty=True)
    )
    return SidebarCatalog(
        provider=provider,
        provider_name=str(manifest.get("name") or provider.title()),
        provider_mark_uri=_provider_mark_uri(provider, manifest),
        provider_mark_dark_uri=_provider_mark_uri(provider, manifest, dark=True),
        categories=categories,
    )


def _library_payload(
    catalogs: tuple[SidebarCatalog, ...],
    selected: tuple[str, ...],
) -> dict[str, object]:
    registry = load_default_provider_registry()
    shared = (
        {item[0] for item in _CUSTOM}
        | {item[0] for item in ARCHITECTURE_BOUNDARY_SPECS}
        | {spec.service_id for spec in SHARED_PRIMITIVE_SPECS}
    )
    seen: set[str] = set()
    components: list[dict[str, object]] = []
    for catalog in catalogs:
        for category in catalog.categories:
            for component in category.components:
                component_provider = component.provider_id or (
                    "infragram" if component.id in shared else catalog.provider
                )
                qualified_id = f"{component_provider}:{component.id}"
                if qualified_id in seen:
                    continue
                seen.add(qualified_id)
                provider_name = (
                    "Infragram" if component_provider == "infragram" else catalog.provider_name
                )
                components.append(
                    {
                        "provider": component_provider,
                        "providerName": provider_name,
                        "serviceId": component.id,
                        "qualifiedId": qualified_id,
                        "name": component.name,
                        "subtitle": component.subtitle,
                        "categoryId": component.category_id,
                        "iconUri": component.icon_uri,
                        "mappingStatus": component.mapping_status,
                        "componentKind": component.component_kind,
                        "boundaryKind": component.boundary_kind,
                        "frameGroup": component.frame_group,
                        "hierarchyLevel": component.hierarchy_level,
                        "tier": component.tier,
                        # How the document would draw it, so a drop from the
                        # sidebar lands the same way.
                        "defaultDisplay": default_display(
                            component_provider,
                            component.id,
                            tier=component.tier,
                            category=component.native_category or component.category_id,
                        ),
                        "defaultSize": {
                            "width": component.default_width,
                            "height": component.default_height,
                        }
                        if component.component_kind == "boundary"
                        else None,
                        "boundaryStyle": component.boundary_style,
                        "search": " ".join(
                            (
                                provider_name,
                                component.name,
                                component.subtitle,
                                component.native_category.replace("-", " "),
                                component.id,
                                qualified_id,
                                component.frame_group,
                                *component.aliases,
                            )
                        ).casefold(),
                    }
                )
    categories = load_default_category_registry()
    return {
        "schemaVersion": 1,
        "selectedProviders": list(selected),
        # How many libraries are installed, so a search that finds nothing
        # can say the page carries fewer and how to get the rest.
        "installedProviders": len(registry.providers),
        # Only the embedded libraries are offered: the provider menu, quick
        # filters and summary all read this list.
        "providers": [
            {
                "id": registry[catalog.provider].id,
                "displayName": registry[catalog.provider].display_name,
                "shortName": registry[catalog.provider].short_name,
                # The badge on a component card is an abbreviation; the chip
                # in the library selector is a name. Most libraries use the
                # same string for both, and the ones that do not say so.
                "chipName": registry[catalog.provider].chip,
                "quickFilter": registry[catalog.provider].quick_filter,
                "kind": registry[catalog.provider].kind,
                "coverage": registry[catalog.provider].coverage,
                "markUri": catalog.provider_mark_uri,
            }
            for catalog in catalogs
        ],
        "categories": [
            {"id": category.id, "label": category.label} for category in categories.categories
        ],
        "frameGroups": [
            {"id": group_id, "label": label, "order": order}
            for order, (group_id, label) in enumerate(ARCHITECTURE_BOUNDARY_GROUPS)
        ],
        "framePresets": [dict(preset) for preset in ARCHITECTURE_FRAME_PRESETS],
        "components": components,
    }
