"""A link on a bare glyph is seated on the drawing (ADR 0006, rule 1).

The ink table records where each icon's drawing begins along 33 lines of
every side. A link is pushed in along its own line to that edge, and one
that falls on a gap in the mark, or whose line meets a decoration first,
slides to the nearest line the drawing reaches. Both renderers do it and the checker
holds them to it.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from infragram import compose
from infragram.catalog import ink
from infragram.exports import render_project_html
from infragram.nodes import infragram as shared, reset_ids

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
PLAIN = "A" * ink.EDGE_LINES
#: The Tabler wifi router as the table measured it: a body drawn from 13/24
#: to 21/24 of the square with its arcs floating above. The seating rules
#: were written against it; the shipped edge-router icon is now a drum with
#: no decoration, so the measurement is kept here for the tests.
WIFI_ROUTER = (
    "..............mmmKIGGGGGGGGGIL...|..............WWWKIGGGGGGGGGIL...|"
    "...mihgggggOMLKIIHGGGGGHIIKLMO...|...LIGGGGGGGGGGGGGGGGGGGGGGGIL..."
)


def _checker():
    spec = importlib.util.spec_from_file_location(
        "project_check", ROOT / "skills/infragram-azure/scripts/project_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _fresh_ids():
    reset_ids()


def _left(line: str) -> str:
    """An edge code whose left side is ``line`` and whose other sides are flush."""
    return "|".join([line, PLAIN, PLAIN, PLAIN])


def _router_project():
    router = shared.networking.EdgeRouter("Edge", "bgp")
    switch = shared.networking.CoreSwitch("Core", "spine")
    router.to(switch, label="")
    return compose.to_project(
        [router, switch], slug="d", title="D", description="d.", display="card"
    )


def _static_svg(project) -> str:
    match = re.search(
        r"<svg[^>]*data-infragram-diagram[^>]*>.*?</svg>", render_project_html(project), re.S
    )
    assert match
    return match.group(0)


def test_depth_follows_a_slope_but_keeps_a_step() -> None:
    slope = _left("B" * 16 + "C" * 17)
    assert ink.edge_depth(slope, "left", 15.5 / 32) == pytest.approx(1.5 / 64)
    step = _left("C" * 16 + "Z" * 17)
    assert ink.edge_depth(step, "left", 15.2 / 32) == pytest.approx(2 / 64)
    assert ink.edge_depth(step, "left", 15.8 / 32) == pytest.approx(25 / 64)


def test_a_line_that_begins_past_the_middle_is_no_seat() -> None:
    """Ink that starts deeper than the middle of the square -- a queue's
    solid bar seen through the gaps of its dotted twins -- is no seat: the
    depth is None and the point stays on the box's own edge, instead of
    being pushed to the square's centre."""
    assert ink.edge_depth(_left("/" * 33), "left", 0.5) is None
    assert ink.usable_middle(_left("/" * 33), "left") is None


def test_a_point_on_a_gap_slides_to_the_nearest_line_with_ink() -> None:
    gap = _left("B" * 10 + "." * 13 + "B" * 10)
    assert ink.inked_along(gap, "left", 0.1) == 0.1
    assert ink.inked_along(gap, "left", 0.5) == pytest.approx(9 / 32)
    assert ink.edge_depth(gap, "left", 9 / 32) == pytest.approx(1 / 64)


def test_a_link_slides_past_a_decoration_to_the_device() -> None:
    """The wifi router's arcs float above its body. A line across them
    meets a detail first, so it is no seat: a link placed at the arcs'
    height slides down to the router's body and seats on its left edge,
    instead of landing on the tip of an arc."""
    code = WIFI_ROUTER
    # The body is drawn from 13/24 to 21/24 of the square's height, its left
    # edge 3/24 in; the arcs sit above it.
    slid = ink.inked_along(code, "left", 0.3)
    assert 13 / 24 - 0.04 <= slid <= 21 / 24
    depth = ink.edge_depth(code, "left", slid)
    assert depth is not None and depth == pytest.approx(3 / 24, abs=0.04)


def test_a_sides_one_point_is_the_middle_of_the_device_not_of_its_decorations() -> None:
    """The wifi router's body runs from 13/24 to 21/24 of the square's
    height; its arcs sit above it. The left side's one connection point is
    the middle of the body, where a link reads as meeting the router, not
    the middle of body and arcs together, which is the body's top corner."""
    code = WIFI_ROUTER
    middle = ink.usable_middle(code, "left")
    assert middle is not None and middle == pytest.approx(17 / 24, abs=0.04)
    assert ink.inked_along(code, "left", middle) == middle
    assert ink.edge_depth(code, "left", middle) == pytest.approx(3 / 24, abs=0.04)
    assert ink.usable_middle(_left("." * 33), "left") is None


def test_a_dashed_outline_is_the_edge_a_link_seats_on() -> None:
    """Defender Slot's right side is a column of dashes: every line meets a
    dash first, so the dashes are the outline and the link seats on one
    instead of crossing them to reach the solid bar behind."""
    vendors = ROOT / "skills/infragram-azure/assets/icons/vendors/azure"
    code = ink.edges(next(vendors.rglob("*defender-slot*.svg")).read_bytes())
    middle = ink.usable_middle(code, "right")
    assert middle is not None
    slid = ink.inked_along(code, "right", middle)
    assert ink.edge_depth(code, "right", slid) == pytest.approx(0, abs=0.03)


def test_at_a_step_the_point_sits_on_the_nearer_line() -> None:
    """Where two neighbouring lines differ by more than a step -- the end of
    an antenna bar beside its mast -- the point moves onto the nearer line,
    so it seats on that line's own edge rather than in the air beside it."""
    step = _left("C" * 16 + "Z" * 17)
    assert ink.inked_along(step, "left", 15.3 / 32) == pytest.approx(15 / 32)
    assert ink.inked_along(step, "left", 15.7 / 32) == pytest.approx(16 / 32)
    slope = _left("B" * 16 + "C" * 17)
    assert ink.inked_along(slope, "left", 15.3 / 32) == pytest.approx(15.3 / 32)


def test_the_table_records_four_sides_of_33_lines() -> None:
    table = ink.load_table()
    assert table.edges
    for code in table.edges.values():
        parts = code.split("|")
        assert len(parts) == 4 and all(len(part) == ink.EDGE_LINES for part in parts)


def test_the_editor_page_carries_each_glyphs_edges() -> None:
    html = render_project_html(_router_project())
    state = json.loads(
        re.search(
            r'<script type="application/json" id="infragram-editor-state"[^>]*>(.*?)</script>',
            html,
            re.S,
        ).group(1)
    )
    router = next(node for node in state["nodes"] if node["name"] == "Edge")
    assert isinstance(router["inkEdges"], str) and router["inkEdges"].count("|") == 3
    assert "const seat = " in html and "const inkedAlong = " in html


def test_the_checker_holds_a_glyph_wire_to_the_drawing_on_its_own_line() -> None:
    svg = _static_svg(_router_project())
    checker = _checker()
    errors: list[str] = []
    checker.check_svg(svg, errors)
    assert not [e for e in errors if "leaves" in e or "arrives at" in e or "glyph" in e], errors

    picture = checker.read_picture(svg)
    edge = picture.edges[0]
    source, _ = checker._endpoints_of(picture, edge)
    assert source in picture.ink_edges
    x, y = edge["start"]
    after = checker._next_point(edge["points"], True)
    assert checker._anchor_problem(picture, source, x, y, after) is None
    # Four pixels out into the air beside the drawing, or into the drawing,
    # along the wire's own line: neither touches the mark.
    horizontal = abs(after[1] - y) <= 0.5
    for off in (-4.0, 4.0):
        moved = (x + off, y) if horizontal else (x, y + off)
        assert checker._anchor_problem(picture, source, *moved) is not None, moved
