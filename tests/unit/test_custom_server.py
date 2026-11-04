"""custom_server draws its plain server through the 3D recipes.

This edition ships no generated on-premises set, so a custom server is the
``server`` recipe with the set's knobs. The render itself needs Chromium;
these checks stub it and read the spec.
"""

from __future__ import annotations

import pytest

from infragram.author import Diagram
from infragram.iso3d.api import build_spec
from infragram.nodes import iso
from infragram.nodes.custom import CUSTOM_SERVER_SHAPES, custom_server


@pytest.fixture
def specs(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    seen: list[dict] = []

    def render(spec: dict) -> tuple[str, dict, str]:
        seen.append(spec)
        return "<svg/>", {}, "0" * 16

    monkeypatch.setattr(iso, "render_cached", render)
    return seen


def test_a_custom_server_is_the_server_recipe_without_a_badge(specs: list[dict]) -> None:
    with Diagram("Custom server", slug="custom-server"):
        custom_server("DB-01", "PostgreSQL 16", units=2, bays=8, family="storage")
    (spec,) = specs
    assert spec["recipe"] == "server"
    # units, bays per row, rows: the generated set's 2U/8 is two rows of four
    assert spec["args"] == [2, 4, 2]
    assert spec["colour"] == build_spec("server", family="storage")["colour"]
    assert spec["glyph"] == ""


def test_every_listed_shape_builds(specs: list[dict]) -> None:
    with Diagram("Custom servers", slug="custom-servers"):
        for index, (units, bays) in enumerate(CUSTOM_SERVER_SHAPES):
            custom_server(f"S-{index}", units=units, bays=bays)
    assert len(specs) == len(CUSTOM_SERVER_SHAPES)


def test_an_unlisted_shape_or_family_is_refused() -> None:
    with pytest.raises(ValueError, match="no custom server of 3U"):
        custom_server("S", units=3, bays=8)
    with pytest.raises(ValueError, match="unknown family 'teal'"):
        custom_server("S", family="teal")
