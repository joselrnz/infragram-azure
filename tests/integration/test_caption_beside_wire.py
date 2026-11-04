"""A caption sits beside its wire in the editor's export.

Port clearance is a preference, proximity is the point: on a short wire
between stacked glyphs the only spot with full clearance was past the
neighbour's caption band, outside the frame. The exports are measured here:
the caption's anchor stays within a grid step or two of the wire it names.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from infragram import compose
from infragram.exports import export_project
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import general
from infragram.nodes.frames import azure as frames

NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _export_svg(elements, slug: str, tmp_path: Path) -> str:
    pytest.importorskip("playwright.sync_api")
    project = compose.to_project(elements, slug=slug, title=slug, description="c.", display="card")
    result = export_project(project, tmp_path, formats=("html", "svg"))
    assert result.svg is not None
    return result.svg.read_text(encoding="utf-8")


def _wire(svg: str) -> tuple[tuple[float, float], tuple[float, float]]:
    """Start and end of the first connector: the paths that carry an arrowhead.
    The editor writes M x,y then H x / V y / L x,y runs."""
    match = re.search(r"<path[^>]*marker-end[^>]*>", svg)
    assert match, "the export has a connector"
    d = re.search(r'\sd="([^"]+)"', match.group(0))
    assert d
    x = y = None
    for command, body in re.findall(r"([MLHV])([^MLHV]*)", d.group(1)):
        numbers = [float(n) for n in NUMBER.findall(body)]
        if command in "ML":
            x, y = numbers[-2], numbers[-1]
        elif command == "H":
            x = numbers[-1]
        else:
            y = numbers[-1]
        if command == "M":
            start = (x, y)
    assert x is not None and y is not None
    return start, (x, y)


def _caption(svg: str, label: str) -> tuple[float, float]:
    match = re.search(
        r'<g data-edge-label="[^"]*"[^>]*data-label-x="(-?[\d.]+)"[^>]*data-label-y="(-?[\d.]+)"[^>]*>'
        r"(?:(?!</g>).)*?>" + re.escape(label) + r"</text>",
        svg,
        re.S,
    )
    assert match, f"the export has the caption {label!r}"
    return float(match.group(1)), float(match.group(2))


def test_stacked_glyphs_keep_the_caption_beside_the_short_wire(tmp_path: Path) -> None:
    reset_ids()
    column = frames.Subscription("Stacked", flow="column")
    users = column >> shared.identity.PublicUsers("Users", "people")
    balancer = column >> shared.networking.GenericLoadBalancer("Load balancer", "L7")
    users.to(balancer, label="HTTPS")
    svg = _export_svg([column], "stacked", tmp_path)
    (x0, y0), (x1, y1) = _wire(svg)
    assert abs(x0 - x1) < 0.01, "the wire is vertical"
    label_x, label_y = _caption(svg, "HTTPS")
    assert 0 <= label_x - x0 <= 24, (
        f"the caption starts just right of the wire (wire x {x0}, caption x {label_x})"
    )
    assert abs(label_y - (y0 + y1) / 2) <= 16, (
        f"the caption sits at the wire's middle (middle {(y0 + y1) / 2}, caption y {label_y})"
    )


def test_side_by_side_glyphs_keep_the_caption_over_the_wire(tmp_path: Path) -> None:
    reset_ids()
    internet = shared.networking.PublicInternet("Internet", "public")
    browser = general.Browser("Browser", "client")
    internet.to(browser, label="egress")
    svg = _export_svg([internet, browser], "side-by-side", tmp_path)
    (x0, y0), (x1, y1) = _wire(svg)
    assert abs(y0 - y1) < 0.01, "the wire is level"
    label_x, label_y = _caption(svg, "egress")
    assert abs(label_x - (x0 + x1) / 2) <= 24, (
        f"the caption is centred on the wire (middle {(x0 + x1) / 2}, caption x {label_x})"
    )
    assert 0 < y0 - label_y <= 24, (
        f"the caption sits just above the wire (wire y {y0}, caption y {label_y})"
    )
