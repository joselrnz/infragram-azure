"""The skill package keeps the layout an installing client expects."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
SKILL = ROOT / "skills" / "infragram-azure"
INDEX = SKILL / "assets" / "icons" / "index.json"

REQUIRED_DIRS = ("references", "assets", "scripts")
REQUIRED_FILES = ("SKILL.md",)


def test_skill_directory_has_the_required_layout() -> None:
    assert SKILL.is_dir(), f"skill directory is missing: {SKILL}"
    for name in REQUIRED_FILES:
        assert (SKILL / name).is_file(), f"skill is missing required file: {name}"
    for name in REQUIRED_DIRS:
        assert (SKILL / name).is_dir(), f"skill is missing required directory: {name}/"


def test_every_manifest_skills_path_contains_the_skill() -> None:
    """Every plugin manifest that names a skills root must point at ours."""
    plugin = ROOT
    for manifest_rel in (".codex-plugin/plugin.json", "plugin.json", ".claude-plugin/plugin.json"):
        manifest = json.loads((plugin / manifest_rel).read_text(encoding="utf-8"))
        declared = manifest.get("skills")
        if declared is None:
            continue
        target = (plugin / str(declared).lstrip("./")).resolve()
        assert (target / SKILL.name).is_dir(), (
            f"{manifest_rel} skills path does not contain {SKILL.name}: {declared}"
        )


def test_theme_catalog_names_only_manifests_on_disk() -> None:
    themes = json.loads((SKILL / "assets" / "themes" / "catalog.json").read_text(encoding="utf-8"))
    for relative in themes["providers"]:
        assert (SKILL / "assets" / "themes" / relative).is_file(), (
            f"themes/catalog.json names a missing manifest: {relative}"
        )


def test_icon_index_count_matches_its_entries() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    assert index["counts"]["total"] == len(index["icons"]), (
        "icons/index.json count does not match its entries"
    )


def test_committed_icon_index_equals_a_fresh_build() -> None:
    """The index is generated from the themes and the icon collections; a
    stale committed copy ships icons the tree no longer has, or hides ones
    it does. Build into scratch and compare, never into the tree."""
    from infragram.builders.index import build_index

    with tempfile.TemporaryDirectory(prefix="icon-index-") as temp_dir:
        _path, fresh = build_index(Path(temp_dir) / "index.json")
    committed = json.loads(INDEX.read_text(encoding="utf-8"))
    if committed != fresh:
        fresh_ids = {icon["id"] for icon in fresh["icons"]}
        committed_ids = {icon["id"] for icon in committed["icons"]}
        added = sorted(fresh_ids - committed_ids)[:10]
        gone = sorted(committed_ids - fresh_ids)[:10]
        raise AssertionError(
            "skills/infragram-azure/assets/icons/index.json is stale: a fresh build differs "
            f"({fresh['counts']['total']} icons built, {committed['counts']['total']} committed; "
            f"new {added or 'none'}, gone {gone or 'none'}). Run `infragram build:index` and commit the result."
        )
