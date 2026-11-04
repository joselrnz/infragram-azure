#!/usr/bin/env python3
"""Regression tests for the data-driven cloud-provider catalog."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))

import infragram  # noqa: E402

CATALOG = ROOT / "skills" / "infragram-azure" / "assets" / "themes" / "catalog.json"


def expect_invalid_tree(module, catalog: dict, manifests: dict[str, dict], message: str) -> None:
    with tempfile.TemporaryDirectory(prefix="provider-tree-") as temp_dir:
        root = Path(temp_dir)
        path = root / "catalog.json"
        path.write_text(json.dumps(catalog), encoding="utf-8")
        for relative, payload in manifests.items():
            payload = json.loads(json.dumps(payload))
            # These fixtures exercise manifest-level failures, not the icon
            # registry. Keep them independent from production role mappings
            # and from asset_ref resolution against the real icons/ tree.
            payload.pop("service_icons", None)
            if isinstance(payload.get("icons"), dict):
                payload["icons"] = {
                    "categories": payload["icons"].get("categories") or ["compute"],
                    "items": [],
                }
            # Library-referenced marks (logos:aws#mono) resolve against the real
            # icons tree, which these fixtures deliberately lack.
            if isinstance(payload.get("mark"), str) and ":" in payload["mark"]:
                payload["mark"] = f"marks/{payload.get('slug', 'fixture')}.svg"
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload), encoding="utf-8")
            mark_rel = payload.get("mark")
            if isinstance(mark_rel, str):
                mark_target = (target.parent / mark_rel).resolve()
                if mark_target.is_relative_to(root.resolve()):
                    mark_target.parent.mkdir(parents=True, exist_ok=True)
                    mark_target.write_text(
                        '<svg viewBox="0 0 24 24"><path d="M2 2h20v20H2z"/></svg>',
                        encoding="utf-8",
                    )
        try:
            module.load_catalog(path, root)
        except ValueError as error:
            if message not in str(error):
                raise AssertionError(f"expected {message!r}, got {error!r}") from error
        else:
            raise AssertionError("invalid provider tree was accepted")


def main() -> int:
    catalog_module = infragram
    providers = catalog_module.load_catalog(CATALOG)
    slugs = [provider.slug for provider in providers]
    if slugs != ["azure", "kubernetes"]:
        raise AssertionError(f"unexpected provider order: {slugs}")

    azure = providers[0]
    if "#ff3621" not in azure.icon_palette:
        raise AssertionError("Azure icon palette must preserve Databricks red")

    marks_dir = CATALOG.parent / "marks"
    icons_dir = CATALOG.parent.parent / "icons"
    for provider in providers:
        if provider.manifest_path != CATALOG.parent / f"{provider.slug}.json":
            raise AssertionError(f"provider manifest is not provider-owned: {provider.slug}")
        # A mark is either theme-owned (marks/<slug>.svg) or a reference into a
        # provenance-tracked artwork library (logos:aws#mono); never a stray file.
        owned = provider.mark_path == marks_dir / f"{provider.slug}.svg"
        if not owned and not provider.mark_path.is_relative_to(icons_dir):
            raise AssertionError(
                f"provider mark is neither theme-owned nor a library reference: {provider.slug}"
            )
        if provider.icon_catalog_path != provider.manifest_path:
            raise AssertionError(
                f"icon registry must be inline in the theme manifest: {provider.slug}"
            )
        if set(provider.icon_categories) != {
            "analytics",
            "compute",
            "containers",
            "data",
            "integration",
            "networking",
            "security",
            "storage",
        }:
            raise AssertionError(f"incomplete infrastructure categories for {provider.slug}")
        if not provider.mark_path.is_file():
            raise AssertionError(f"missing mark for {provider.slug}: {provider.mark_path}")
        mark = provider.mark_path.read_text(encoding="utf-8")
        if owned:
            if not mark.startswith("<svg") or 'viewBox="0 0 24 24"' not in mark:
                raise AssertionError(f"invalid standalone mark for {provider.slug}")
            if any(token in mark for token in (' x="', ' y="', ' width="', ' height="')):
                raise AssertionError(f"mark owns layout instead of the renderer: {provider.slug}")
        elif "<svg" not in mark or "viewBox=" not in mark:
            raise AssertionError(f"library mark is not a scalable standalone SVG: {provider.slug}")

    raw = json.loads(CATALOG.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 2 or not all(
        isinstance(item, str) for item in raw["providers"]
    ):
        raise AssertionError("root catalog must be a schema-v2 ordered manifest index")

    duplicate = {"schema_version": 2, "providers": [raw["providers"][0], raw["providers"][0]]}
    azure_manifest = json.loads((CATALOG.parent / raw["providers"][0]).read_text(encoding="utf-8"))
    expect_invalid_tree(
        catalog_module,
        duplicate,
        {"azure.json": azure_manifest},
        "duplicate provider slug",
    )

    bad_color = json.loads(json.dumps(azure_manifest))
    bad_color["theme"]["paper"] = "navy"
    expect_invalid_tree(
        catalog_module,
        {"schema_version": 2, "providers": ["azure.json"]},
        {"azure.json": bad_color},
        "invalid color",
    )

    bad_icon_color = json.loads(json.dumps(azure_manifest))
    bad_icon_color["icon_palette"] = ["databricks-red"]
    expect_invalid_tree(
        catalog_module,
        {"schema_version": 2, "providers": ["azure.json"]},
        {"azure.json": bad_icon_color},
        "invalid icon color",
    )

    duplicate_icon_color = json.loads(json.dumps(azure_manifest))
    duplicate_icon_color["icon_palette"] = ["#ff3621", "#FF3621"]
    expect_invalid_tree(
        catalog_module,
        {"schema_version": 2, "providers": ["azure.json"]},
        {"azure.json": duplicate_icon_color},
        "duplicate icon color",
    )

    escaped_manifest = json.loads(json.dumps(azure_manifest))
    escaped_manifest["mark"] = "../../outside.svg"
    expect_invalid_tree(
        catalog_module,
        {"schema_version": 2, "providers": ["azure.json"]},
        {"azure.json": escaped_manifest},
        "must stay inside",
    )

    print("PASS: provider catalog separates canvas themes, icon palettes, and marks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ------------------------------------------- the face every label is set in

THEMES = ROOT / "skills" / "infragram-azure" / "assets" / "themes"


def test_no_skin_sets_its_own_face_for_the_drawn_labels() -> None:
    """A skin's ``typography.font`` is applied to ``Style.sans``, which is
    the face *every drawn label* uses -- not only the heading the field is
    documented for.

    The azure skin set it to a stack that restated the default and added a
    ``system-ui`` fallback the HTML wrapper's own rule already appends, so the
    Azure pictures declared one face and the generic and kubernetes skins
    another. The same key had drifted the same way in the full edition, where
    a test pinned the literal and so agreed with the skin instead of catching
    it.
    """
    from infragram.builders.scene import Style

    default = Style().sans
    wrong: list[str] = []
    for path in sorted(THEMES.glob("*.json")):
        if path.stem == "catalog":
            continue
        typography = json.loads(path.read_text(encoding="utf-8")).get("typography") or {}
        font = typography.get("font")
        if font is not None and font != default:
            wrong.append(f"{path.name} sets typography.font to {font!r}, not {default!r}")
    assert not wrong, (
        "\n".join(wrong) + "\n\nA skin may have its own colours and its own artwork. The face"
        " every label is set in is the product's, not the vendor's."
    )
