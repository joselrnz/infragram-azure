"""Vendored brand logos must stay byte-exact and reachable from a card.

`icons/logos/catalog.json` records a sha256 per file and the upstream commit
each came from. That provenance is the only thing standing between a shipped
trademark and a silently edited one, so it is checked rather than trusted.

A primitive reaches one of these through an ``icon_id`` of the form
``logo:<dir>/<file>``, which is the path that puts a real brand mark on a card
instead of a generic glyph.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from infragram.catalog import SHARED_PRIMITIVE_SPECS
from infragram.catalog.components import primitive_icon_svg

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
LOGOS = ROOT / "skills/infragram-azure/assets/icons/logos"
CATALOG = json.loads((LOGOS / "catalog.json").read_text(encoding="utf-8"))


def _entries() -> list[dict]:
    return CATALOG["icons"]


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["id"])
def test_every_logo_matches_its_recorded_digest(entry: dict) -> None:
    for variant, relative in entry["variants"].items():
        path = LOGOS / relative
        assert path.is_file(), f"{entry['id']}: {relative} is catalogued but missing"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == entry["sha256"][variant], (
            f"{entry['id']}/{variant} does not match its recorded sha256."
            " Either the file was edited in place or it was re-imported"
            " without updating the catalog."
        )


@pytest.mark.parametrize("entry", _entries(), ids=lambda e: e["id"])
def test_every_logo_records_where_it_came_from(entry: dict) -> None:
    """A mark with no provenance cannot be relicensed, updated or defended."""
    for field in ("license", "license_status", "source_url", "source_commit"):
        assert entry.get(field), f"{entry['id']}: no {field}"
    assert entry["license_status"] != "restricted-review", (
        f"{entry['id']}: shipped despite unclear terms"
    )
    assert re.fullmatch(r"[0-9a-f]{40}", entry["source_commit"]), (
        f"{entry['id']}: source_commit is not a full commit sha"
    )


def test_the_counts_block_matches_the_icons_it_describes() -> None:
    icons = _entries()
    files = sum(len(entry["variants"]) for entry in icons)
    assert CATALOG["counts"]["icons"] == len(icons)
    assert CATALOG["counts"]["files"] == files


def test_primitives_that_point_at_a_logo_resolve_to_it() -> None:
    """`logo:<dir>/<file>` is how a primitive borrows a real brand mark."""
    pointed = [spec for spec in SHARED_PRIMITIVE_SPECS if spec.icon_id.startswith("logo:")]
    assert pointed, "no primitive uses a vendored logo any more"
    for spec in pointed:
        svg = primitive_icon_svg(spec.icon_id).decode("utf-8")
        assert svg.lstrip().startswith("<svg"), f"{spec.service_id}: not an SVG"
        relative = spec.icon_id.removeprefix("logo:") + ".svg"
        assert any(relative in entry["variants"].values() for entry in _entries()), (
            f"{spec.service_id} points at {relative}, which the logo catalog"
            " does not list, so nothing checks its digest or licence"
        )
