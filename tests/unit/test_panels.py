"""Panels: a box that says more than a name and a detail line.

Compartments, several detail lines, a shape and a tone that means something
(builders/panels.py). Python sizes a panel and both renderers draw it; a
plain card is no panel and draws as it always has.
"""

from __future__ import annotations

import json
import re

import pytest

from infragram.author import Diagram, Edge
from infragram.builders import panels
from infragram.exports import render_project_svg
from infragram.nodes import Box
from infragram.nodes.azure import compute


def _lb() -> Box:
    return (
        Box("Load balancer", "one Gateway-owned resource")
        .tone("edge")
        .section("Public frontend", "HTTPS 443", tone="edge")
        .section("Gateway backends", "health-checked targets", tone="private", beside=True)
        .section("Direct origin access must fail", tone="blocker")
    )


def _project(**options):
    with Diagram("Panels", slug="panels", display="card", **options) as diagram:
        lb = _lb()
        web = compute.VirtualMachine("Web", "plain card")
        customer = Box("Customer", "HTTPS 443\nStripe when enabled").shape("ellipse")
        control = Box("Control plane", "managed API").shape("hexagon").tone("managed")
        contract = Box("Network contract", "default deny").shape("note")
        customer >> Edge("HTTPS") >> lb >> web
        lb - control
        web >> contract
    return diagram.to_project()


def test_compartments_ride_in_the_attributes() -> None:
    project = _project()
    lb = project.topology.first(name="Load balancer")
    assert lb is not None
    assert lb.attributes["tone"] == "edge"
    assert [[cell["title"] for cell in row] for row in lb.attributes["sections"]] == [
        ["Public frontend", "Gateway backends"],
        ["Direct origin access must fail"],
    ]
    assert lb.attributes["sections"][0][1]["tone"] == "private"


def test_a_panel_is_drawn_whole_and_a_plain_card_as_ever() -> None:
    svg = render_project_svg(_project())
    groups = re.findall(
        r'<g data-ink="[^"]*" (?:data-ink-edge="[^"]*" )?data-node="([^"]+)"[^>]*>', svg
    )
    panel_groups = re.findall(r'data-node="([^"]+)" data-display="card" data-panel=""', svg)
    assert "web" in groups and "web" not in panel_groups, "a plain card stays a card"
    assert set(panel_groups) == {"load-balancer", "customer", "control-plane", "network-contract"}
    # three toned compartments, the heading and every line
    assert svg.count("data-panel-cell") == 3
    for text in (
        "Public frontend",
        "Gateway backends",
        "Direct origin access must fail",
        "HTTPS 443",
    ):
        assert f">{text}<" in svg
    # each shape is its own outline
    assert "<ellipse" in svg and "<polygon" in svg
    assert re.search(r'<path d="M[\d.]+,[\d.]+ H[\d.]+ L', svg), "a note folds its corner"
    # several detail lines, one text each
    assert ">Stripe when enabled<" in svg


def test_a_tone_alone_fills_the_box() -> None:
    """compose.md: `.tone(name)` fills the box, with nothing else said."""
    assert panels.panel_of({"tone": "blocker"}, "one line").active
    assert not panels.panel_of({}, "one line").active
    with Diagram("Tone", slug="tone", display="card") as diagram:
        Box("No-go", "no deployment evidence").tone("blocker")
    svg = render_project_svg(diagram.to_project())
    assert 'data-node="no-go" data-display="card" data-panel=""' in svg
    assert panels.metrics.tones()["blocker"].fill in svg


def test_a_box_is_a_box_whatever_it_says() -> None:
    """A Box has no artwork: a plain one is no card with a placeholder icon,
    and a Box with nothing under its name says nothing there."""
    with Diagram("Plain", slug="plain", display="icon") as diagram:
        Box("Plain box", "one line")
        Box("Bare box")
    svg = render_project_svg(diagram.to_project())
    assert 'data-node="plain-box" data-display="card" data-panel=""' in svg
    assert 'data-node="bare-box" data-display="card" data-panel=""' in svg
    assert ">box<" not in svg


def test_an_icon_stays_inside_an_ellipse() -> None:
    with Diagram("Icon", slug="icon", display="card") as diagram:
        compute.VirtualMachine("Web", "in an ellipse").shape("ellipse")
    svg = render_project_svg(diagram.to_project())
    node = re.search(
        r'data-node="web".*?<ellipse cx="([\d.]+)" cy="([\d.]+)" rx="([\d.]+)" ry="([\d.]+)"',
        svg,
        re.S,
    )
    icon = re.search(
        r'data-node="web".*?<use href="#[^"]+" x="([\d.]+)" y="([\d.]+)" width="(\d+)"', svg, re.S
    )
    assert node and icon
    cx, cy, rx, ry = map(float, node.groups())
    x, y, size = float(icon[1]), float(icon[2]), float(icon[3])
    for px, py in ((x, y), (x, y + size), (x + size, y), (x + size, y + size)):
        assert ((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 < 1, (
            "every corner of the icon is inside"
        )


def test_the_tones_tell_apart() -> None:
    """Each tone's outline is its own hue, so two fills never read as one."""
    import colorsys

    def hue(colour: str) -> float:
        red, green, blue = (int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5))
        return colorsys.rgb_to_hls(red, green, blue)[0] * 360

    tones = {name: tone for name, tone in panels.metrics.tones().items() if name != "neutral"}
    for name, tone in tones.items():
        for other, paint in tones.items():
            if name < other:
                gap = abs(hue(tone.stroke) - hue(paint.stroke))
                assert min(gap, 360 - gap) >= 20, f"{name} and {other} look alike"


def test_a_panel_grows_to_what_it_carries() -> None:
    plain = panels.Panel(detail_lines=("one", "two"))
    rows = panels.Panel(
        sections=((panels.Cell("A", ("x" * 60,)), panels.Cell("B", ("y",))),),
        detail_lines=("detail",),
    )
    width, height = panels.size("Name", plain, has_icon=False)
    wide, tall = panels.size("Name", rows, has_icon=False)
    assert width % 4 == 0 and height % 4 == 0
    assert wide > width and tall > height
    assert wide >= panels.cell_need(rows.sections[0][0]) + panels.cell_need(rows.sections[0][1])
    ellipse = panels.Panel(shape="ellipse", detail_lines=("one",))
    assert (
        panels.size("Name", ellipse, has_icon=False)[0]
        > panels.size("Name", panels.Panel(detail_lines=("one", "")), has_icon=False)[0] - 1
    )


def test_cells_share_a_row_by_what_they_need_and_fill_it() -> None:
    row = (panels.Cell("Short"), panels.Cell("A much longer title here"), panels.Cell("Mid title"))
    widths = panels.cell_widths(row, 401)
    assert sum(widths) == 401
    assert widths[1] > widths[2] > widths[0]
    assert all(width == int(width) for width in widths[:-1])


def test_a_panel_says_what_is_wrong() -> None:
    with pytest.raises(ValueError, match="unknown tone"):
        Box("x").tone("loud")
    with pytest.raises(ValueError, match="shape is one of"):
        Box("x").shape("star")
    with pytest.raises(ValueError, match="carries no compartments"):
        Box("x").shape("ellipse").section("cell")
    with pytest.raises(ValueError, match="carries no compartments"):
        Box("x").section("cell").shape("hexagon")
    with pytest.raises(ValueError, match="needs a title or a line"):
        Box("x").section()
    with pytest.raises(ValueError, match="unknown tone"):
        Diagram("t", tones={"loud": "?"})


def test_the_legend_says_what_each_tone_means() -> None:
    project = _project(tones={"edge": "public edge / ingress", "blocker": "launch blocker"})
    assert project.presentation.tones == (
        ("edge", "public edge / ingress"),
        ("blocker", "launch blocker"),
    )
    svg = render_project_svg(project)
    assert 'data-legend-tone="edge"' in svg and 'data-legend-tone="blocker"' in svg
    assert ">launch blocker<" in svg


def test_a_panel_stays_a_box_on_an_icon_diagram() -> None:
    with Diagram("Icons", slug="icons", display="icon") as diagram:
        Box("Note", "line one\nline two").shape("note")
        compute.VirtualMachine("Web")
    svg = render_project_svg(diagram.to_project())
    assert re.search(r'data-node="note" data-display="card" data-panel=""', svg)
    assert re.search(r'data-node="web" data-display="icon"', svg)


def test_the_editor_is_told_whether_a_panel_has_artwork() -> None:
    from infragram.exports import render_project_html

    html = render_project_html(_project())
    match = re.search(
        r'<script type="application/json" id="infragram-editor-state"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    state = json.loads(match.group(1))
    nodes = {node["name"]: node for node in state["nodes"]}
    assert nodes["Load balancer"]["panelIcon"] is False
    assert "panelIcon" not in nodes["Web"]
    assert nodes["Load balancer"]["attributes"]["sections"][1][0]["tone"] == "blocker"
