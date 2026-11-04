"""Load and validate Infragram cloud-provider diagram skins.

Parses ``themes/catalog.json`` and each flat theme manifest into the
frozen models in :mod:`infragram.models`, failing loudly on any invalid or
unsafe entry. The optional ``theme.corners`` key ("square" | "rounded" |
"circular") selects the provider's box edge style; omitting it keeps the
default squarish rounded look.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from ..models import SERVICE_ROLES, Provider, ProviderIcon, Service
from ..themes import THEME_ROLES, Theme
from ..verification import HEX_COLOR, SHA256, SLUG, unsafe_svg_match, view_box


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    """Parse a JSON object from *path*, naming the file in every failure."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is not valid JSON ({path}): {error}") from error
    return _object(payload, label)


def _load_theme(entry: dict[str, object], slug: str) -> Theme:
    theme_raw = _object(entry.get("theme"), f"provider {slug} theme")
    colors: dict[str, str] = {}
    for role in THEME_ROLES:
        color = _text(theme_raw.get(role), f"provider {slug} theme.{role}")
        if not HEX_COLOR.fullmatch(color):
            raise ValueError(f"invalid color for provider {slug} theme.{role}: {color!r}")
        colors[role] = color.lower()
    return Theme.from_colors(colors)


def _load_icon_palette(entry: dict[str, object], slug: str) -> tuple[str, ...]:
    palette_raw = entry.get("icon_palette", [])
    if not isinstance(palette_raw, list):
        raise ValueError(f"provider {slug} icon_palette must be an array")
    icon_palette: list[str] = []
    for palette_index, raw_color in enumerate(palette_raw):
        color = _text(raw_color, f"provider {slug} icon_palette[{palette_index}]")
        if not HEX_COLOR.fullmatch(color):
            raise ValueError(f"invalid icon color for provider {slug}: {color!r}")
        normalized = color.lower()
        if normalized in icon_palette:
            raise ValueError(f"duplicate icon color for provider {slug}: {normalized}")
        icon_palette.append(normalized)
    return tuple(icon_palette)


def _load_categories(icon_catalog: dict[str, object], slug: str) -> tuple[str, ...]:
    categories_raw = icon_catalog.get("categories")
    if not isinstance(categories_raw, list) or not categories_raw:
        raise ValueError(f"provider {slug} icon categories must be a non-empty array")
    categories: list[str] = []
    for category_index, raw_category in enumerate(categories_raw):
        category = _text(raw_category, f"provider {slug} categories[{category_index}]")
        if not SLUG.fullmatch(category):
            raise ValueError(f"invalid icon category for provider {slug}: {category!r}")
        if category in categories:
            raise ValueError(f"duplicate icon category for provider {slug}: {category}")
        categories.append(category)
    return tuple(categories)


def _load_collection_catalog(assets_root: Path, collection: str, cache: dict[str, dict]) -> dict:
    """Load and cache icons/<collection>/catalog.json for any collection.

    A collection is a relative directory under the icons root — for example
    ``cloud/aws`` or ``brands``. Nothing here assumes cloud vendors; a theme
    may reference artwork from any provenance-tracked library.
    """
    if collection in cache:
        return cache[collection]
    collection_dir = (assets_root / collection).resolve()
    if not collection_dir.is_relative_to(assets_root):
        raise ValueError(f"icon collection escapes the icons root: {collection!r}")
    catalog_path = collection_dir / "catalog.json"
    if not catalog_path.is_file():
        raise ValueError(f"no icon collection catalog for {collection!r}: {catalog_path}")
    # kept as the plain record this function returns; callers read its keys by name
    catalog: dict[str, Any] = _load_json_object(catalog_path, f"icon collection {collection}")
    catalog["_dir"] = catalog_path.parent
    catalog["_icons_by_id"] = {
        _object(entry, f"icon collection {collection} icon").get("id"): entry
        for entry in catalog.get("icons", [])
        if isinstance(entry, dict)
    }
    cache[collection] = catalog
    return catalog


def _resolve_asset_ref(
    icon: dict[str, object],
    icon_slug: str,
    slug: str,
    assets_root: Path | None,
    asset_cache: dict[str, dict],
) -> dict[str, object]:
    """Resolve a qualified ``asset_ref`` against its icon collection.

    ``asset_ref`` names the collection and the icon id in one path-like
    reference — ``cloud/aws/lambda``, ``brands/nginx`` — so a theme can pull
    artwork from any library, not just a cloud vendor that shares its slug.
    Returns a dict with the same keys _load_icon expects from an owned
    ("file"-based) entry, so both shapes converge on one validation path.
    """
    if assets_root is None:
        raise ValueError(
            f"provider {slug} icon {icon_slug} uses asset_ref but no icons root is configured"
        )
    asset_ref = _text(icon.get("asset_ref"), f"provider {slug} icon {icon_slug} asset_ref")
    asset_ref, _, variant = asset_ref.partition("#")
    collection, _, ref_id = asset_ref.rpartition("/")
    if not collection or not ref_id:
        raise ValueError(
            f"provider {slug} icon {icon_slug} asset_ref must be collection-qualified "
            f"(e.g. 'vendors/aws/lambda' or 'logos/nginx#mono'); got {asset_ref!r}"
        )
    vendor_catalog = _load_collection_catalog(assets_root, collection, asset_cache)
    asset_entry = vendor_catalog["_icons_by_id"].get(ref_id)
    if asset_entry is None:
        raise ValueError(f"provider {slug} icon {icon_slug} asset_ref not found: {asset_ref}")
    if "variants" in asset_entry:
        # Logo-style entry: no single file. Require an explicit variant so the
        # digest pin stays reproducible - no silent default fallback.
        variants = _object(asset_entry.get("variants"), f"{asset_ref} variants")
        if not variant:
            allowed = ", ".join(sorted(variants))
            raise ValueError(
                f"provider {slug} icon {icon_slug} must name a variant "
                f"({asset_ref}#<variant>); available: {allowed}"
            )
        if variant not in variants:
            raise ValueError(
                f"provider {slug} icon {icon_slug} unknown variant: {asset_ref}#{variant}"
            )
        digests = asset_entry.get("sha256")
        asset_entry = dict(
            asset_entry,
            file=variants[variant],
            sha256=digests.get(variant) if isinstance(digests, dict) else digests,
        )
    elif variant:
        raise ValueError(
            f"provider {slug} icon {icon_slug} names a variant but {asset_ref} has none"
        )
    source = _object(vendor_catalog.get("source"), f"icon collection {collection} source")
    source_url = _text(source.get("url"), f"icon collection {collection} source.url")
    # The skin owns the diagram-facing category (its own 8-category
    # infrastructure taxonomy); the vendor's pack category is provenance only.
    return {
        "file": asset_entry.get("file"),
        "_base_dir": vendor_catalog["_dir"],
        "category": icon.get("category"),
        "source_url": source_url,
        "source_release": source.get("release") or vendor_catalog["collection"],
        "source_path": asset_entry.get("source_path"),
        "terms_url": source_url,
        "sha256": asset_entry.get("sha256"),
        "name": icon.get("name") or asset_entry.get("name"),
    }


def _load_icon(
    raw_icon: object,
    icon_index: int,
    icons_dir: Path,
    categories: tuple[str, ...],
    slug: str,
    known: dict[str, ProviderIcon],
    assets_root: Path | None,
    asset_cache: dict[str, dict],
) -> ProviderIcon:
    icon = _object(raw_icon, f"provider {slug} icons[{icon_index}]")
    icon_slug = _text(icon.get("id"), f"provider {slug} icons[{icon_index}].id")
    if not SLUG.fullmatch(icon_slug) or icon_slug in known:
        raise ValueError(f"invalid or duplicate icon id for provider {slug}: {icon_slug!r}")

    if "asset_ref" in icon:
        resolved = _resolve_asset_ref(icon, icon_slug, slug, assets_root, asset_cache)
        # the collection catalog's own directory, a Path set when it was loaded
        base_dir = cast(Path, resolved["_base_dir"])
    else:
        resolved = icon
        base_dir = icons_dir

    category = _text(resolved.get("category"), f"provider {slug} icon {icon_slug} category")
    if category not in categories:
        raise ValueError(f"provider {slug} icon {icon_slug} uses undeclared category {category}")
    icon_relative = Path(_text(resolved.get("file"), f"provider {slug} icon {icon_slug} file"))
    icon_path = (base_dir / icon_relative).resolve()
    if not icon_path.is_relative_to(base_dir):
        raise ValueError(
            f"provider {slug} icon {icon_slug} must reference a local SVG: file escapes {base_dir}"
        )
    if icon_path.suffix.lower() != ".svg":
        raise ValueError(
            f"provider {slug} icon {icon_slug} must reference a local SVG: "
            f"unexpected extension {icon_path.suffix!r}"
        )
    if not icon_path.is_file():
        raise ValueError(
            f"provider {slug} icon {icon_slug} must reference a local SVG: missing file {icon_path}"
        )
    data = icon_path.read_bytes()
    svg = data.decode("utf-8")
    lowered = svg.lower()
    # Asked of the same extractor the renderer uses, so the gate and the
    # thing it guards cannot disagree about what a usable icon is.
    if "<svg" not in lowered or view_box(svg) is None or unsafe_svg_match(svg):
        raise ValueError(f"provider {slug} icon {icon_slug} is not a safe standalone SVG")
    digest = _text(resolved.get("sha256"), f"provider {slug} icon {icon_slug} sha256").lower()
    if not SHA256.fullmatch(digest) or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"provider {slug} icon {icon_slug} sha256 does not match")
    aliases_raw = icon.get("aliases", [])
    if not isinstance(aliases_raw, list):
        raise ValueError(f"provider {slug} icon {icon_slug} aliases must be an array")
    aliases = tuple(
        _text(alias, f"provider {slug} icon {icon_slug} alias").casefold() for alias in aliases_raw
    )
    return ProviderIcon(
        slug=icon_slug,
        name=_text(resolved.get("name"), f"provider {slug} icon {icon_slug} name"),
        category=category,
        path=icon_path,
        aliases=aliases,
        source_url=_text(
            resolved.get("source_url"), f"provider {slug} icon {icon_slug} source_url"
        ),
        source_release=_text(
            resolved.get("source_release"), f"provider {slug} icon {icon_slug} source_release"
        ),
        source_path=_text(
            resolved.get("source_path"), f"provider {slug} icon {icon_slug} source_path"
        ),
        terms_url=_text(resolved.get("terms_url"), f"provider {slug} icon {icon_slug} terms_url"),
        sha256=digest,
    )


def _load_icons(
    icon_catalog: dict[str, object],
    icons_dir: Path,
    categories: tuple[str, ...],
    slug: str,
    assets_root: Path | None,
    asset_cache: dict[str, dict],
) -> tuple[dict[str, ProviderIcon], dict[str, str]]:
    icons_raw = icon_catalog.get("icons", [])
    if not isinstance(icons_raw, list):
        raise ValueError(f"provider {slug} icons must be an array")
    icons: dict[str, ProviderIcon] = {}
    icon_aliases: dict[str, str] = {}
    seen_hashes: set[str] = set()
    for icon_index, raw_icon in enumerate(icons_raw):
        provider_icon = _load_icon(
            raw_icon, icon_index, icons_dir, categories, slug, icons, assets_root, asset_cache
        )
        if provider_icon.sha256 in seen_hashes:
            raise ValueError(
                f"provider {slug} contains duplicate icon artwork: {provider_icon.slug}"
            )
        seen_hashes.add(provider_icon.sha256)
        icons[provider_icon.slug] = provider_icon
        for alias in (
            provider_icon.slug.casefold(),
            provider_icon.name.casefold(),
            *provider_icon.aliases,
        ):
            owner = icon_aliases.get(alias)
            if owner is not None and owner != provider_icon.slug:
                raise ValueError(f"provider {slug} icon alias collision: {alias!r}")
            icon_aliases[alias] = provider_icon.slug
    return icons, icon_aliases


_MARK_VARIANT_ORDER = ("default", "color", "mono", "light", "dark", "icon", "wordmark")


def _resolve_catalog_mark(
    reference: str,
    slug: str,
    assets_root: Path | None,
    asset_cache: dict[str, dict],
) -> Path:
    """Resolve a ``collection:id[#variant]`` mark against the shared icon libraries.

    A theme may take its mark from a provenance-tracked artwork collection
    (``logos:aws#mono``) instead of shipping a copy under ``marks/`` - the same
    spelling the editor uses for provider tabs and frame icons.
    """
    if assets_root is None:
        raise ValueError(f"provider {slug} mark {reference!r} needs an icons root to resolve")
    collection, _, rest = reference.partition(":")
    ref_id, _, variant = rest.partition("#")
    if not collection or not ref_id:
        raise ValueError(f"provider {slug} mark must be collection:id[#variant]; got {reference!r}")
    try:
        catalog = _load_collection_catalog(assets_root, collection, asset_cache)
    except ValueError:
        catalog = _load_collection_catalog(assets_root, f"vendors/{collection}", asset_cache)
    entry = catalog["_icons_by_id"].get(ref_id)
    if entry is None:
        raise ValueError(f"provider {slug} mark not found in {collection}: {ref_id}")
    if "variants" in entry:
        variants = _object(entry.get("variants"), f"{reference} variants")
        chosen = variant or next((name for name in _MARK_VARIANT_ORDER if name in variants), "")
        if chosen not in variants:
            raise ValueError(f"provider {slug} mark has no variant {variant!r}: {reference}")
        relative = _text(variants[chosen], f"{reference} variant file")
    else:
        if variant:
            raise ValueError(
                f"provider {slug} mark names a variant but {collection}:{ref_id} has none"
            )
        relative = _text(entry.get("file"), f"{reference} file")
    return (catalog["_dir"] / relative).resolve()


def _load_provider(
    root: Path,
    raw_manifest: object,
    index: int,
    seen: set[str],
    assets_root: Path | None,
    asset_cache: dict[str, dict],
) -> Provider:
    manifest_relative = Path(_text(raw_manifest, f"providers[{index}]"))
    manifest_path = (root / manifest_relative).resolve()
    if not manifest_path.is_relative_to(root):
        raise ValueError(f"provider manifest must stay inside {root}")
    if not manifest_path.is_file():
        raise ValueError(f"provider manifest does not exist: {manifest_path}")
    entry = _load_json_object(manifest_path, f"providers[{index}] manifest")
    if entry.get("schema_version") != 1:
        raise ValueError(f"provider manifest schema_version must be 1: {manifest_path}")
    slug = _text(entry.get("slug"), f"providers[{index}].slug")
    if not SLUG.fullmatch(slug):
        raise ValueError(f"invalid provider slug: {slug!r}")
    if slug in seen:
        raise ValueError(f"duplicate provider slug: {slug}")
    seen.add(slug)

    theme = _load_theme(entry, slug)
    icon_palette = _load_icon_palette(entry, slug)

    provider_dir = manifest_path.parent
    if manifest_path.stem != slug:
        raise ValueError(f"provider {slug} manifest must be named {slug}.json")
    mark_text = _text(entry.get("mark"), f"provider {slug} mark")
    if ":" in mark_text:
        mark_path = _resolve_catalog_mark(mark_text, slug, assets_root, asset_cache)
    else:
        mark_path = (provider_dir / Path(mark_text)).resolve()
        if not mark_path.is_relative_to(provider_dir):
            raise ValueError(f"provider {slug} mark must stay inside {provider_dir}")

    # The registry is inline: the theme file is the whole manifest, and
    # "items" may be left out by a skin that offers no icon vocabulary yet.
    # The separate icon-catalog file a manifest could once name is gone; no
    # theme used it, so a manifest that still does is refused by name.
    icons_raw = entry.get("icons")
    if not isinstance(icons_raw, dict):
        raise ValueError(
            f'provider {slug} icons must be an object: {{"categories": [...], "items": [...]}}'
        )
    icon_catalog: dict[str, object] = {
        "categories": icons_raw.get("categories"),
        "icons": icons_raw.get("items", []),
    }
    icon_catalog_path = manifest_path
    icons_dir = provider_dir
    categories = _load_categories(icon_catalog, slug)
    icons, icon_aliases = _load_icons(
        icon_catalog, icons_dir, categories, slug, assets_root, asset_cache
    )

    service_icon_paths: dict[str, Path] = {}
    service_icon_slugs: dict[str, str] = {}
    service_icons_raw = _object(entry.get("service_icons", {}), f"provider {slug} service_icons")
    if service_icons_raw and set(service_icons_raw) != set(SERVICE_ROLES):
        raise ValueError(f"provider {slug} service_icons must define every service role")
    for role in SERVICE_ROLES:
        if role not in service_icons_raw:
            continue
        icon_slug = _text(service_icons_raw[role], f"provider {slug} service_icons.{role}")
        if icon_slug not in icons:
            raise ValueError(f"provider {slug} service icon is not registered: {icon_slug}")
        service_icon_slugs[role] = icon_slug
        service_icon_paths[role] = icons[icon_slug].path

    if not mark_path.is_file():
        raise ValueError(f"provider {slug} mark does not exist: {mark_path}")
    services_raw = _object(entry.get("services"), f"provider {slug} services")
    services: dict[str, Service] = {}
    for role in SERVICE_ROLES:
        service_raw = _object(services_raw.get(role), f"provider {slug} services.{role}")
        services[role] = Service(
            name=_text(service_raw.get("name"), f"provider {slug} services.{role}.name"),
            detail=_text(service_raw.get("detail"), f"provider {slug} services.{role}.detail"),
        )

    return Provider(
        slug=slug,
        name=_text(entry.get("name"), f"provider {slug} name"),
        title=_text(entry.get("title"), f"provider {slug} title"),
        manifest_path=manifest_path,
        mark_path=mark_path,
        icon_catalog_path=icon_catalog_path,
        icon_categories=categories,
        icons=icons,
        icon_aliases=icon_aliases,
        service_icon_slugs=service_icon_slugs,
        service_icon_paths=service_icon_paths,
        theme=theme,
        icon_palette=icon_palette,
        services=services,
    )


def load_catalog(
    catalog_path: Path, provider_root: Path | None = None, assets_root: Path | None = None
) -> tuple[Provider, ...]:
    """Return validated providers in their declared display order.

    *assets_root* is the shared ``icons/`` directory that owns vendor icon
    libraries under ``assets_root/cloud/<vendor>``. Skin icon entries may
    reference those by id via ``asset_ref`` instead of shipping a local copy.
    Defaults to ``<catalog root>/../icons`` (skins live in ``skins/``, the
    artwork in the sibling ``icons/``).
    """
    catalog_path = catalog_path.resolve()
    root = (provider_root or catalog_path.parent).resolve()
    if assets_root is None:
        candidate = root.parent / "icons"
        assets_root = candidate if candidate.is_dir() else None
    payload = _load_json_object(catalog_path, "catalog")
    if payload.get("schema_version") != 2:
        raise ValueError("catalog schema_version must be 2")
    entries = payload.get("providers")
    if not isinstance(entries, list) or not entries:
        raise ValueError("catalog providers must be a non-empty array")

    providers: list[Provider] = []
    seen: set[str] = set()
    asset_cache: dict[str, dict] = {}
    for index, raw_manifest in enumerate(entries):
        providers.append(_load_provider(root, raw_manifest, index, seen, assets_root, asset_cache))
    return tuple(providers)
