"""A head sits on a straight shaft (ADR 0006, rule 9).

The static router's path gives up the rounding of the corner before a headed
end before it gives up the shaft under the head; the stub out of a side is
the full 20 px unless a neighbour sits that close; and the checker fails a
head on a bend.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from infragram.builders.routing import Point, Rect, Route, Router

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


def _checker():
    spec = importlib.util.spec_from_file_location(
        "project_check", ROOT / "skills/infragram-azure/scripts/project_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_the_corner_before_a_head_keeps_the_shaft_straight() -> None:
    hook = Route((Point(0, 0), Point(0, 50), Point(12, 50)))
    rounded = hook.to_path(8.0)
    assert "Q0,50" in rounded, "without a shaft to keep, the corner is rounded"
    squared = hook.to_path(8.0, shaft=12.0)
    assert "Q" not in squared and squared.endswith("L0,50 L12,50"), squared
    # A longer last leg keeps its rounding and still leaves the shaft.
    longer = Route((Point(0, 0), Point(0, 50), Point(20, 50))).to_path(8.0, shaft=12.0)
    assert "Q0,50 8,50" in longer, longer


def test_a_headed_end_stops_short_of_its_anchor_by_the_tip_clearance() -> None:
    route = Route((Point(0, 0), Point(0, 50), Point(20, 50)))
    assert route.to_path(8.0, shaft=10.0, tip_clear=2.0).endswith("L18,50")
    assert route.to_path(8.0, shaft=10.0).endswith("L20,50"), "no clearance, no trim"
    both = route.to_path(8.0, shaft=10.0, heads=(True, True), tip_clear=2.0)
    assert both.startswith("M0,2") and both.endswith("L18,50")
    # a leg shorter than the clearance is left alone rather than collapsed
    assert Route((Point(0, 0), Point(2, 0))).to_path(8.0, tip_clear=2.0) == "M0,0 L2,0"


def test_a_head_at_the_start_squares_the_first_corner_instead() -> None:
    route = Route((Point(0, 0), Point(12, 0), Point(12, 50)))
    assert "Q" in route.to_path(8.0, shaft=12.0)  # end head only: first corner rounds
    assert "Q" not in route.to_path(8.0, shaft=12.0, heads=(True, False))


def test_the_stub_is_the_full_length_unless_a_neighbour_is_that_close() -> None:
    router = Router()
    start, end = Point(100, 100), Point(300, 100)
    # A blocker between them forces a detour; the corners nearest the ends
    # are the stub points, 20 px out.
    blocker = Rect(180, 60, 220, 140)
    routed = router.route_between_sides(start, "right", end, "left", [blocker])
    assert routed is not None
    assert routed.corners[1].x == 120 and routed.corners[-2].x == 280
    # A neighbour 24 px beyond the start swallows the full stub: it shortens
    # to the clearance so the wire still leaves the side squarely.
    close = Rect(124, 60, 160, 140)
    routed = router.route_between_sides(start, "right", end, "left", [blocker, close])
    assert routed is not None
    assert routed.corners[1] == Point(112, 100)


def test_the_checker_fails_a_head_on_a_bend() -> None:
    checker = _checker()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">'
        '<g data-graph-node data-node-id="a" data-display-mode="card" transform="translate(20 60)">'
        '<rect data-node-surface width="120" height="80"/></g>'
        '<g data-graph-node data-node-id="b" data-display-mode="card" transform="translate(260 60)">'
        '<rect data-node-surface width="120" height="80"/></g>'
        '<path data-graph-edge data-edge-id="edge-1" data-source-x="140" data-source-y="100" '
        'data-target-x="260" data-target-y="100" d="M140,100 L200,100 L200,60 L256,60 L256,100 L260,100" '
        'fill="none" stroke="#000" marker-end="url(#arrow)"/></svg>'
    )
    errors: list[str] = []
    checker.check_svg(svg, errors)
    heads = [e for e in errors if "arrowhead on a bend" in e]
    assert heads and "4 px of straight wire" in heads[0], errors
    # The same wire with a proper shaft passes.
    long_shaft = re.sub(
        r'd="[^"]*"', 'd="M140,100 L200,100 L200,60 L240,60 L240,100 L260,100"', svg
    )
    errors = []
    checker.check_svg(long_shaft, errors)
    assert not [e for e in errors if "arrowhead on a bend" in e], errors
