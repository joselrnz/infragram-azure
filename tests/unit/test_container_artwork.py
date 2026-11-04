"""Group artwork is the box, never a node.

A vendor may ship a third kind of drawing beside its services: the box drawn
*around* things. Placed as a node, such a drawing shows a card labelled
"Region" that holds nothing, which reads as a region while modelling none.
The reviewed table in ``assets/catalog/container-artwork.json`` pairs every
such icon with the frame that does the job, the generated class warns where a
caller meets it, and the shipped checker refuses a document that draws one.

Neither library this edition ships files artwork that way: the Azure deck
and the Kubernetes set are services throughout. The table's ``providers``
block is therefore empty, and these tests hold it there so that importing a
deck that ships group boxes fails until each one is reviewed. The rule
itself -- detection by the vendor's tier, a hand-reviewed pairing -- stays
exactly as it was.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path

from infragram.catalog import tiers
from infragram.nodes._base import Frame as BaseFrame

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
VENDORS = ROOT / "skills/infragram-azure/assets/icons/vendors"
TABLE = ROOT / "skills/infragram-azure/assets/catalog/container-artwork.json"


def _checker():
    spec = importlib.util.spec_from_file_location(
        "project_check", ROOT / "skills/infragram-azure/scripts/project_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _shipped_group_icons() -> dict[str, set[str]]:
    """provider -> every icon id the vendor's own catalog files as a group."""
    found: dict[str, set[str]] = {}
    for catalog in sorted(VENDORS.glob("*/catalog.json")):
        icons = json.loads(catalog.read_text(encoding="utf-8")).get("icons") or []
        ids = {str(i.get("id")) for i in icons if tiers.is_container(i)}
        if ids:
            found[catalog.parent.name] = ids
    return found


def test_the_table_covers_every_piece_of_group_artwork() -> None:
    """Import new artwork filed as a group and this fails until it is reviewed.

    That is the point: the table is written by hand, so the only thing keeping
    it honest is a test that reads the catalogs instead of trusting it.
    """
    shipped = _shipped_group_icons()
    table = json.loads(TABLE.read_text(encoding="utf-8"))["providers"]
    for provider, ids in shipped.items():
        listed = set(table.get(provider) or {})
        assert ids <= listed, f"{provider}: unreviewed group artwork {sorted(ids - listed)}"
        assert listed <= ids, f"{provider}: stale rows for {sorted(listed - ids)}"
    for provider in set(table) - set(shipped):
        assert not table[provider], f"{provider}: rows for a deck that ships no group artwork"


def test_no_shipped_deck_files_artwork_as_a_group_today() -> None:
    """Azure and Kubernetes draw their containment as ordinary service icons
    (see test_frame_counterparts); the table's providers block is empty."""
    assert _shipped_group_icons() == {}
    assert json.loads(TABLE.read_text(encoding="utf-8"))["providers"] == {}


def test_every_frame_the_table_names_is_a_frame_that_ships() -> None:
    """A pointer to a frame that does not exist is worse than no pointer."""
    table = json.loads(TABLE.read_text(encoding="utf-8"))
    named = [
        row["frame"]
        for rows in table["providers"].values()
        for row in rows.values()
        if row.get("frame")
    ]

    def resolve(dotted: str) -> type:
        assert dotted.startswith("frames."), dotted
        _, group, cls = dotted.split(".", 2)
        module = importlib.import_module(f"infragram.nodes.frames.{group}")
        frame = getattr(module, cls, None)
        assert frame is not None, f"{dotted} names no frame"
        assert issubclass(frame, BaseFrame), f"{dotted} is not a frame"
        return frame

    for dotted in named:
        # A provider frame carries the id the editor draws it by.
        assert getattr(resolve(dotted), "FRAME_ID", ""), f"{dotted} carries no frame id"
    # The fallback is the untyped frame itself, which takes any label.
    assert resolve(table["fallback"]) is BaseFrame


def test_the_checker_leaves_an_ordinary_service_alone() -> None:
    """The rule must not fire on the services a real diagram is made of."""
    checker = _checker()
    document = {
        "topology": {
            "id": "root",
            "name": "Root",
            "type": "group",
            "children": [
                {
                    "id": "a",
                    "name": "Web",
                    "type": "service",
                    "component": {"provider": "azure", "service_id": "virtual-machine"},
                },
                {
                    "id": "b",
                    "name": "Database",
                    "type": "service",
                    "component": {"provider": "azure", "service_id": "sql-database"},
                },
                {
                    "id": "c",
                    "name": "API",
                    "type": "service",
                    "component": {"provider": "kubernetes", "service_id": "deploy"},
                },
            ],
        }
    }
    errors: list[str] = []
    assert checker.check_components(document, errors) == 3
    assert errors == []


def test_no_shipped_template_draws_a_group_box_as_a_node() -> None:
    """What the rule protects, checked against everything we ship."""
    checker = _checker()
    templates = sorted((ROOT / "skills/infragram-azure/assets/templates").rglob("*.infragram.json"))
    assert len(templates) >= 4
    for path in templates:
        errors: list[str] = []
        checker.check_components(json.loads(path.read_text(encoding="utf-8")), errors)
        assert errors == [], f"{path.name}: {errors}"
