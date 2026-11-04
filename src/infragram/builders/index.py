"""Build the merged icon index over every artwork collection and theme.

Logic lives here so it is importable and testable;
``scripts/build/provider-index.py`` is a thin entry point over
:func:`build_index`.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..paths import skill_assets
from ..utils.generated import write_generated_text

ICONS = skill_assets() / "icons"
THEMES = skill_assets() / "themes"


def license_bases() -> dict[str, str]:
    """provider id -> how we came by its artwork, from the provider registry.

    One label for every vendor icon would hide the only distinction that
    matters before publishing: the on-premises set comes from an MIT upstream
    with a per-file hash, AWS ships an asset pack whose own terms permit
    diagram use, and two libraries were fetched off a web page with no grant
    established at all.
    """
    registry = ICONS.parent / "catalog" / "providers.json"
    if not registry.is_file():
        return {}
    doc = json.loads(registry.read_text(encoding="utf-8"))
    return {
        str(record.get("id")): str(record.get("license_basis") or "unrecorded")
        for record in doc.get("providers") or []
    }


def load_families() -> dict[str, str]:
    """member slug -> family name, from the curated logos overlay."""
    overlay_path = ICONS / "logos" / "families.json"
    if not overlay_path.is_file():
        return {}
    overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    for family, spec in overlay.get("families", {}).items():
        for member in spec.get("members", []):
            mapping[member] = family
    return mapping


def theme_entries() -> list[dict]:
    bases = license_bases()
    catalog_path = THEMES / "catalog.json"
    if not catalog_path.is_file():
        return []
    root = json.loads(catalog_path.read_text(encoding="utf-8"))
    entries = []
    for manifest_rel in root["providers"]:
        slug = Path(manifest_rel).stem
        manifest = json.loads((THEMES / manifest_rel).read_text(encoding="utf-8"))
        registry = manifest.get("icons") or {}
        items = registry.get("items", []) if isinstance(registry, dict) else []
        for icon in items:
            # asset_ref is already collection-qualified (vendors/aws/lambda);
            # pass it through verbatim - never re-prefix.
            target = icon.get("asset_ref")
            path = None if target else f"themes/{slug}/{icon.get('file', '')}"
            entries.append(
                {
                    "id": f"themes/{slug}/{icon['id']}",
                    "domain": "theme",
                    "source": f"theme:{slug}",
                    "tier": 0,
                    "name": icon["name"],
                    "aliases": icon.get("aliases", []),
                    "categories": [icon["category"]],
                    "variants": {"default": path} if path else {},
                    "asset_ref": target,
                    "license_status": bases.get(slug, "unrecorded"),
                }
            )
    return entries


def asset_entries(families: dict[str, str]) -> list[dict]:
    bases = license_bases()
    entries = []
    for domain_dir in sorted(p for p in ICONS.iterdir() if p.is_dir()):
        domain = domain_dir.name
        catalogs = sorted(domain_dir.glob("*/catalog.json"))
        if not catalogs and (domain_dir / "catalog.json").is_file():
            catalogs = [domain_dir / "catalog.json"]
        for catalog_path in catalogs:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            collection = catalog_path.parent.name if catalog_path.parent != domain_dir else domain
            prefix = f"{domain}/{collection}" if catalog_path.parent != domain_dir else domain
            for icon in catalog["icons"]:
                if "variants" in icon:  # logo-style entry
                    variants = {k: f"{prefix}/{v}" for k, v in icon["variants"].items()}
                    categories = icon.get("categories", [])
                    license_status = icon.get("license_status", "restricted-review")
                else:  # vendor-pack entry
                    variants = {"default": f"{prefix}/{icon['file']}"}
                    categories = [icon["category"]]
                    license_status = bases.get(collection, "unrecorded")
                entries.append(
                    {
                        "id": f"{prefix}/{icon['id']}",
                        "domain": domain,
                        "source": f"{domain}:{collection}",
                        "tier": 1 if domain == "vendors" else 2,
                        "name": icon["name"],
                        "aliases": icon.get("aliases", []),
                        "categories": categories,
                        "family": families.get(
                            icon["id"], collection if domain == "vendors" else None
                        ),
                        "variants": variants,
                        "asset_ref": None,
                        "license_status": license_status,
                    }
                )
    return entries


def build_index(out: Path | None = None) -> tuple[Path, dict]:
    """Write the merged index; return (path, index) for callers and tests."""
    families = load_families()
    entries = theme_entries() + asset_entries(families)
    entries.sort(key=lambda item: (item["tier"], item["id"]))
    index = {
        "schema_version": 2,
        "generated_by": "scripts/build/provider-index.py",
        "structure": {
            "themes": "themes/<slug>.json - preset with inline icon vocabulary; entries reference icons/ by qualified asset_ref",
            "icons": "icons/<collection> - artwork libraries with provenance (vendors/, logos/)",
        },
        "lookup_rule": "Search id, name, and aliases case-insensitively. Lower tier wins: 0=theme (curated aliases), 1=vendors (official artwork), 2=logos (fallback). 'family' groups related logos (see logos/families.json). license_status says how we came by the artwork: upstream-permissive (an OSS licence grants redistribution), provider-terms (the vendor's own asset-pack terms permit diagram use), permissive (a CC0/MIT logo set), vendor-unverified (fetched from a vendor page with no grant established), original-artwork (tiles drawn for this project from MIT glyphs in the vendor's colour; not the vendor's icons), unrecorded (a bug: every collection must declare one). Check it before redistributing or modifying artwork.",
        "counts": {
            "total": len(entries),
            "by_domain": {
                domain: sum(1 for entry in entries if entry["domain"] == domain)
                for domain in sorted({entry["domain"] for entry in entries})
            },
        },
        "icons": entries,
    }
    out = out or ICONS / "index.json"
    write_generated_text(
        out,
        json.dumps(index, ensure_ascii=False, separators=(",", ":")) + chr(10),
    )
    return out, index
