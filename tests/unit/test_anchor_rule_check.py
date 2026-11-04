"""The picture checker enforces "a wire touches what is drawn" (ADR 0006).

The six cases the guidelines draw are composed here, rendered by the static
renderer and read by the shipped checker: every wire end must meet its node
at the card's edge or at the glyph's own edge or the caption's underside. A
wire moved onto the invisible layout box must fail. The editor's pictures are
held to the same rule by the template sweep and the golden pictures.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from infragram import compose
from infragram.exports import render_project_html
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import compute, general, identity
from infragram.nodes.frames import azure as frames

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


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


def _static_svg(project) -> str:
    html = render_project_html(project)
    match = re.search(r"<svg[^>]*data-infragram-diagram[^>]*>.*?</svg>", html, re.S)
    assert match
    return match.group(0)


def _check(svg: str) -> list[str]:
    errors: list[str] = []
    _checker().check_svg(svg, errors)
    return [e for e in errors if "leaves" in e or "arrives at" in e]


def _case_side_by_side():
    # Two bare glyphs: a shared primitive and one of the Azure deck's
    # general icons, which the display rules draw without a card.
    internet = shared.networking.PublicInternet("Internet", "public")
    browser = general.Browser("Browser", "client")
    internet.to(browser, label="")
    return [internet, browser]


def _case_stacked():
    column = frames.Subscription("Column", flow="column")
    users = column >> shared.identity.PublicUsers("Users", "people")
    lb = column >> shared.networking.GenericLoadBalancer("Load balancer", "L7")
    users.to(lb, label="")
    return [column]


def _first_link_start(svg: str) -> tuple[str, str]:
    """The (x, y) text of the first connector path's M command; connectors are
    the paths that carry an arrowhead, unlike frame outlines or markers."""
    match = re.search(r'<path d="M(-?[\d.]+),(-?[\d.]+)[^"]*"[^>]*marker-end', svg)
    assert match, "the picture has a connector"
    return match.group(1), match.group(2)


def _case_card_to_offset_glyph():
    subscription = frames.Subscription("Production")
    vnet = subscription >> frames.ResourceGroup("rg-prod") >> frames.VNet("VNet")
    app = vnet >> frames.Subnet("Private") >> compute.VirtualMachine("App servers", "scale set")
    operators = vnet >> frames.Subnet("Management") >> identity.Users("Operators", "Bastion")
    app.to(operators, label="")
    return [subscription]


def _case_passing_a_third_node():
    row = frames.Subscription("Row", flow="row")
    client = row >> shared.identity.PublicUsers("Client", "browser")
    bastion = row >> shared.security.Firewall("Bastion", "jump host")
    api = row >> compute.FunctionApps("API", "REST")
    client.to(api, label="")
    return [row], bastion


def _case_many_wires_one_side():
    hub = shared.networking.CoreSwitch("Core switch", "spine")
    leaves = [shared.networking.AccessSwitch(f"Leaf {n}", "access") for n in (1, 2, 3, 4)]
    for leaf in leaves:
        hub.to(leaf, label="")
    return [hub, *leaves]


@pytest.mark.parametrize(
    "build",
    [
        _case_side_by_side,
        _case_stacked,
        _case_card_to_offset_glyph,
        _case_many_wires_one_side,
    ],
)
def test_each_drawn_case_passes_the_anchor_rule_in_the_static_picture(build) -> None:
    project = compose.to_project(build(), slug="d", title="D", description="d.", display="card")
    assert _check(_static_svg(project)) == []


def test_a_wire_passing_a_third_node_still_meets_its_ends_on_the_glyph() -> None:
    elements, bastion = _case_passing_a_third_node()
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    svg = _static_svg(project)
    assert _check(svg) == []
    # and the third node keeps its whole box: no wire runs through the bastion's glyph or caption
    errors: list[str] = []
    _checker().check_svg(svg, errors)
    assert not [e for e in errors if bastion.id in e and "runs through" in e]


def test_a_wire_end_in_the_empty_air_of_the_layout_box_fails() -> None:
    project = compose.to_project(
        _case_side_by_side(), slug="d", title="D", description="d.", display="card"
    )
    svg = _static_svg(project)
    checker = _checker()
    picture = checker.read_picture(svg)
    internet = next(node_id for node_id in picture.nodes if node_id.startswith("internet"))
    box = picture.nodes[internet]
    glyph = next(b for b in picture.node_text[internet] if b.label == "glyph")
    # Move the wire's start from the glyph's right edge to the layout box's right edge.
    x, y = _first_link_start(svg)
    assert abs(float(x) - glyph.right) <= 2
    broken = svg.replace(f'<path d="M{x},{y}', f'<path d="M{box.right:g},{y}', 1)
    problems = _check(broken)
    assert problems and "empty air" in problems[0]


def test_a_wire_that_slides_along_the_edge_it_meets_fails() -> None:
    """Rule 8: touching the side is not enough; the wire must run straight
    out of it. Here the same two ends are joined by a wire that climbs the
    source glyph's right edge and comes down the target glyph's left edge."""
    project = compose.to_project(
        _case_side_by_side(), slug="d", title="D", description="d.", display="card"
    )
    svg = _static_svg(project)
    assert _check(svg) == []
    edge = _checker().read_picture(svg).edges[0]
    (x0, y0), (x1, y1) = edge["start"], edge["end"]
    path = re.search(r'<path d="(M[^"]*)"[^>]*marker-end', svg)
    assert path
    sideways = svg.replace(
        path.group(1), f"M{x0:g},{y0:g} L{x0:g},{y0 - 40:g} L{x1:g},{y0 - 40:g} L{x1:g},{y1:g}", 1
    )
    problems = _check(sideways)
    assert any("leaves" in p and "sideways" in p for p in problems)
    assert any("arrives at" in p and "sideways" in p for p in problems)


def test_a_card_wire_that_starts_inside_the_card_fails() -> None:
    subscription = frames.Subscription("Production")
    subnet = subscription >> frames.ResourceGroup("rg-prod") >> frames.Subnet("Private")
    web = subnet >> compute.VirtualMachine("Web", "tier 1")
    app = subnet >> compute.VirtualMachine("App", "tier 2")
    web.to(app, label="")
    project = compose.to_project(
        [subscription], slug="d", title="D", description="d.", display="card"
    )
    svg = _static_svg(project)
    assert _check(svg) == []
    x, y = _first_link_start(svg)
    # Pull the start into the middle of the card it leaves: no longer on an edge.
    box = _checker().read_picture(svg).nodes[web.id]
    inside = svg.replace(
        f'<path d="M{x},{y}',
        f'<path d="M{(box.left + box.right) / 2:g},{(box.top + box.bottom) / 2:g}',
        1,
    )
    problems = _check(inside)
    assert problems and "not at the card's edge" in problems[0]
