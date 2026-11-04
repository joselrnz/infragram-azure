"""Routed wires in the editor's export meet their nodes squarely (ADR 0006, rule 8).

Two of the drawn cases need routing: a fan-out whose far leaves sit behind
the first, and a wire that has to pass a third node in a row. Unrouted, the
first would slide down the target glyph's left edge and the second run along
the card's border. Both exports are checked by the shipped checker, and the
last segment of every routed wire is measured: it runs straight into the
side it enters, from outside, the way the guideline drawing shows.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from infragram.nodes import reset_ids

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


def _cases():
    sys.path.insert(0, str(ROOT / "examples"))
    import connector_anchoring_cases as cases

    return cases


def _checker():
    spec = importlib.util.spec_from_file_location(
        "project_check", ROOT / "skills/infragram-azure/scripts/project_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _export(build, tmp_path: Path, display: str = "card") -> str:
    pytest.importorskip("playwright.sync_api")
    reset_ids()
    result = build().export(tmp_path, display=display, formats=("html", "svg"), overwrite=True)
    assert result.svg is not None
    return result.svg.read_text(encoding="utf-8")


def _wires(svg: str) -> dict[str, list[tuple[float, float]]]:
    return {edge["id"]: edge["points"] for edge in _checker().read_picture(svg).edges}


def _anchor_errors(svg: str) -> list[str]:
    errors: list[str] = []
    _checker().check_svg(svg, errors)
    return [e for e in errors if "leaves" in e or "arrives at" in e or "sideways" in e]


def _arrives_level_from_the_left(points: list[tuple[float, float]]) -> bool:
    (px, py), (x, y) = points[-2], points[-1]
    return abs(py - y) < 0.01 and px < x


def test_a_fan_out_enters_every_leaf_level_at_its_left_edge(tmp_path: Path) -> None:
    svg = _export(_cases().many_wires_one_side, tmp_path)
    assert _anchor_errors(svg) == []
    wires = _wires(svg)
    assert len(wires) == 4
    for edge_id, points in sorted(wires.items()):
        assert _arrives_level_from_the_left(points), (
            f"{edge_id} enters its leaf from the left: {points[-2:]}"
        )
    # All four wires leave the switch's right side from its one point: a node
    # has one connection point a side, not a row of them (ADR 0006, rule 3).
    starts = {points[0] for points in wires.values()}
    assert len(starts) == 1


def test_a_fan_out_leaves_from_one_point_seated_on_the_switch(tmp_path: Path) -> None:
    """ADR 0006, rules 1 and 3: the four wires share the switch's one right
    side point, and that point is where the switch's drawing begins on its
    line, not the edge of the box around it.

    Request icons explicitly: a forced card now stays a card, including a
    resource-tier switch, and cards are seated on their own border rather
    than on artwork. The other two cases still exercise card routing."""
    svg = _export(_cases().many_wires_one_side, tmp_path, display="icon")
    checker = _checker()
    picture = checker.read_picture(svg)
    assert picture.ink_edges, "the editor's export carries each glyph's edge lines"
    starts = set()
    for edge in picture.edges:
        source, _ = checker._endpoints_of(picture, edge)
        x, y = edge["start"]
        seated = checker._seat_line(picture, source, "right", y)
        assert seated is not None and abs(x - seated) <= 1, (edge["id"], x, seated)
        starts.add((round(x, 1), round(y, 1)))
    assert len(starts) == 1, starts


def test_a_wire_passing_a_third_node_still_enters_level_at_the_far_side(tmp_path: Path) -> None:
    svg = _export(_cases().passing_a_third_node, tmp_path)
    assert _anchor_errors(svg) == []
    (points,) = _wires(svg).values()
    assert _arrives_level_from_the_left(points), f"the API is entered from the left: {points[-2:]}"
    # and the detour goes round the third node rather than through it
    errors: list[str] = []
    _checker().check_svg(svg, errors)
    assert not [e for e in errors if "runs through" in e or "cuts through" in e]
