"""The component inventory accounts for everything the libraries ship and stays current."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
BUILDER = ROOT / "scripts" / "inventory" / "build.py"


@pytest.fixture(scope="module")
def inventory_module():
    spec = importlib.util.spec_from_file_location("inventory_build", BUILDER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def built(inventory_module):
    inventory, problems = inventory_module.build_inventory()
    return inventory, problems


def test_every_component_has_decodable_artwork(built) -> None:
    _inventory, problems = built
    assert problems == []


def test_inventory_covers_every_library_and_its_frames(built) -> None:
    inventory, _ = built
    providers = json.loads(
        (ROOT / "skills/infragram-azure/assets/catalog/providers.json").read_text(encoding="utf-8")
    )["providers"]

    assert [library["id"] for library in inventory["libraries"]] == [p["id"] for p in providers]
    assert inventory["totals"]["libraries"] == len(providers)
    # every library has frames and a starter stack; full libraries carry
    # hundreds of icons
    assert all(library["frames"] for library in inventory["libraries"])
    assert all(library["starter_stack"] for library in inventory["libraries"])
    by_id = {library["id"]: library for library in inventory["libraries"]}
    assert by_id["azure"]["icons"] >= 700 and by_id["azure"]["kind"] == "cloud"
    assert by_id["kubernetes"]["kind"] == "platform" and by_id["kubernetes"]["icons"] >= 30
    assert all(library["mark_only"] is False for library in inventory["libraries"])
    assert inventory["totals"]["frames"] == len(inventory["core_frames"]) + sum(
        len(library["frames"]) for library in inventory["libraries"]
    )
    assert inventory["totals"]["templates"] == len(
        list((ROOT / "skills/infragram-azure/assets/templates/cloud").glob("*.infragram.json"))
    )


def test_committed_inventory_is_current(inventory_module, built) -> None:
    inventory, _ = built
    assert inventory_module.check(inventory) == []


def test_docs_page_shows_a_picture_of_every_library(inventory_module, built) -> None:
    inventory, _ = built
    page = inventory_module.render_docs_markdown(inventory)
    images = set(inventory_module.referenced_images(page))

    assert (
        "frames-tabs.png" in images
        and "icons-shared.png" in images
        and "frames-generic.png" in images
    )
    for library in inventory["libraries"]:
        if not library["mark_only"]:
            assert f"icons-{library['id']}.png" in images, library["id"]
        if library["frames"]:
            assert f"frames-{library['id']}.png" in images, library["id"]
    # the pictures the page embeds exist in the docs folder
    docs = ROOT / "docs" / "inventory"
    missing = sorted(image for image in images if not (docs / image).exists())
    assert missing == []


def test_check_reports_a_stale_inventory(inventory_module, built, tmp_path: Path) -> None:
    inventory, _ = built
    stale = json.loads(json.dumps(inventory))
    stale["libraries"][0]["components"].pop()
    stale["libraries"][0]["icons"] -= 1
    stale["totals"]["vendor_icons"] -= 1
    json_path = tmp_path / "inventory.json"
    json_path.write_text(json.dumps(stale), encoding="utf-8")
    markdown_path = tmp_path / "inventory.md"
    markdown_path.write_text(inventory_module.render_markdown(inventory), encoding="utf-8")

    errors = inventory_module.check(inventory, json_path, markdown_path)

    assert any("out of date" in error for error in errors)
    assert any(inventory["libraries"][0]["id"] in error for error in errors)
