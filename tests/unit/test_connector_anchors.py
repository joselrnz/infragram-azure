"""A wire touches what is drawn (ADR 0006).

A card's wire meets the card's edge. A bare glyph's wire meets the glyph's
own edge -- left, right or top -- or the underside of its caption from below,
never the invisible box around glyph and caption. The static renderer is
checked here; the editor runtime shares the numbers and the picture checker
holds both to them.
"""

from __future__ import annotations

import re

import pytest

from infragram import compose
from infragram.builders.architecture import icon_for
from infragram.catalog.ink import edge_depth, inked_along, ports, usable_middle
from infragram.exports import render_project_html
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import compute
from infragram.nodes.frames import azure as frames


@pytest.fixture(autouse=True)
def _fresh_ids():
    reset_ids()


def _static_svg(html: str) -> str:
    match = re.search(r"<svg[^>]*data-infragram-diagram[^>]*>.*?</svg>", html, re.S)
    assert match, "the page embeds the static diagram"
    return match.group(0)


def _ink_of(svg: str, node_id: str) -> list[float]:
    """The ink insets the renderer recorded for a node: how far inside its
    glyph square the artwork actually starts (ADR 0006, rule 1)."""
    match = re.search(
        rf'<g data-ink="([^"]*)" (?:data-ink-edge="[^"]*" )?data-node="{re.escape(node_id)}"', svg
    )
    assert match, node_id
    return [float(part) for part in match.group(1).split(",")]


def _edges_of(svg: str, node_id: str) -> str:
    """Where the node's ink begins along every line of each side, as the
    renderer recorded it; a link on the glyph is seated there."""
    match = re.search(
        rf'<g data-ink="[^"]*" data-ink-edge="([^"]*)" data-node="{re.escape(node_id)}"', svg
    )
    assert match, node_id
    return match.group(1)


def _node_geometry(svg: str, node_id: str) -> dict:
    group = re.search(
        rf'<g [^>]*data-node="{re.escape(node_id)}" data-display="(\w+)">(.*?)</g>', svg, re.S
    )
    assert group, node_id
    display, body = group.group(1), group.group(2)
    rect = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', body)
    assert rect
    geometry = {
        "display": display,
        "x": float(rect.group(1)),
        "y": float(rect.group(2)),
        "width": float(rect.group(3)),
        "height": float(rect.group(4)),
    }
    glyph = re.search(
        r'<use [^>]*x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"', body
    )
    if glyph:
        geometry["glyph"] = {
            "x": float(glyph.group(1)),
            "y": float(glyph.group(2)),
            "size": float(glyph.group(3)),
        }
    return geometry


def _link_endpoints(svg: str) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """(start, end) of every link path, from its M and its final absolute command."""
    ends = []
    for path in re.findall(r'<path d="(M[^"]+)"[^>]*marker-end', svg):
        numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path)]
        start = (numbers[0], numbers[1])
        # the last command is H x, V y or a point; resolve it against the previous point
        tail = re.findall(r"([MHVLQ])([^MHVLQ]+)", path)
        x, y = start
        for command, args in tail:
            values = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", args)]
            if command == "H":
                x = values[-1]
            elif command == "V":
                y = values[-1]
            else:
                x, y = values[-2], values[-1]
        ends.append((start, (x, y)))
    return ends


def test_a_bare_glyphs_wire_leaves_from_the_glyph_not_the_invisible_box() -> None:
    users = shared.identity.PublicUsers("Users", "customers")
    subscription = frames.Subscription("Production")
    app = (
        subscription
        >> frames.ResourceGroup("rg-prod")
        >> frames.Subnet("Private")
        >> compute.VirtualMachine("App server", "web")
    )
    users.to(app, label="HTTPS")
    project = compose.to_project(
        [users, subscription], slug="d", title="D", description="d.", display="card"
    )
    svg = _static_svg(render_project_html(project))

    node = _node_geometry(svg, users.id)
    assert node["display"] == "icon" and "glyph" in node
    glyph = node["glyph"]
    ((start, end),) = _link_endpoints(svg)[:1]

    # The wire starts on the mark itself at its middle: the artwork keeps air
    # inside the glyph square (this one about a seventh of it a side), and the
    # anchor sits on the ink, not on the square around it -- seated along its
    # own line to where the drawing begins, which on this mark is a little
    # inside the ink's outermost extent.
    ink = _ink_of(svg, users.id)
    box_right = glyph["x"] + glyph["size"] * (1 - ink[1])
    # The side's one point sits at the middle of the stretch of the right side
    # the drawing reaches, and slides off a gap if that middle falls on one.
    edges = _edges_of(svg, users.id)
    artwork = icon_for(users, None)
    assert artwork is not None
    data = (
        artwork.markup.encode("utf-8")
        if getattr(artwork, "markup", None)
        else artwork.path.read_bytes()
    )
    # People have a catalog port on the body; other marks use the middle
    # of the visible stretch, moved off any gap in the measured artwork.
    fixed = (ports(data) or {}).get("right")
    along = fixed if fixed is not None else usable_middle(edges, "right")
    assert along is not None
    seated_along = along if fixed is not None else inked_along(edges, "right", along)
    slid = glyph["y"] + glyph["size"] * seated_along
    assert start[1] == pytest.approx(slid, abs=1)
    depth = edge_depth(edges, "right", (start[1] - glyph["y"]) / glyph["size"])
    # A declared body port stays fixed even where the sampled outline has
    # no depth; the renderer keeps that port on the measured ink box.
    if depth is None:
        assert fixed is not None
        seated = box_right
    else:
        seated = min(box_right, glyph["x"] + glyph["size"] * (1 - depth))
    assert start[0] == pytest.approx(seated, abs=1)
    assert ink[1] > 0 and start[0] < glyph["x"] + glyph["size"] - 1
    # ...and nowhere near the node's box, which is wider than the glyph.
    assert node["width"] > glyph["size"] + 16
    assert start[0] < node["x"] + node["width"] - 8


def test_a_cards_wire_still_meets_the_cards_edge() -> None:
    subscription = frames.Subscription("Production")
    subnet = subscription >> frames.ResourceGroup("rg-prod") >> frames.Subnet("Private")
    web = subnet >> compute.VirtualMachine("Web", "tier 1")
    db = subnet >> compute.VirtualMachine("App", "tier 2")
    web.to(db, label="HTTP")
    project = compose.to_project(
        [subscription], slug="d", title="D", description="d.", display="card"
    )
    svg = _static_svg(render_project_html(project))
    source = _node_geometry(svg, web.id)
    assert source["display"] == "card"
    ((start, _),) = _link_endpoints(svg)[:1]
    on_edge = any(
        abs(start[0] - x) <= 1 for x in (source["x"], source["x"] + source["width"])
    ) or any(abs(start[1] - y) <= 1 for y in (source["y"], source["y"] + source["height"]))
    assert on_edge
