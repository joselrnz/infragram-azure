"""A side chosen for a connector's end is kept by both renderers.

A node has one connection point a side (ADR 0006). The editor lets a reader
pin the side each end of a wire uses -- the Text tab's *Leaves from* and
*Arrives at* -- and writes the choice beside the wire's style, in
``editor_edge_styles[<target>]``. It has to survive the trip: the static
renderer anchors the wire there, and the page built from the same document
opens with the same choice in the panel.
"""

from __future__ import annotations

import json
import re

import pytest

from infragram import compose
from infragram.editor.state import _pinned_side
from infragram.exports import render_project_html
from infragram.exports.render import _scene_for
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import compute


@pytest.fixture(autouse=True)
def _fresh_ids():
    reset_ids()


def _pair(**style):
    """Two components and a wire, with whatever style the case pins on it."""
    users = shared.identity.PublicUsers("Users", "customers")
    app = compute.VirtualMachine("App server", "web")
    users.to(app, label="HTTPS")
    if style:
        users.attributes["editor_edge_styles"] = {app.id: dict(style)}
    return (
        compose.to_project(
            [users, app], slug="sides", title="Sides", description="Sides.", display="card"
        ),
        users,
        app,
    )


def _scene_link(project):
    scene = _scene_for(project)
    assert len(scene.links) == 1
    return scene.links[0]


def _editor_edges(html: str) -> list[dict]:
    match = re.search(r'<script[^>]*id="infragram-editor-state"[^>]*>(.*?)</script>', html, re.S)
    assert match
    return json.loads(match.group(1))["edges"]


def test_a_wire_with_no_side_chosen_is_anchored_where_the_nodes_stand() -> None:
    project, _users, _app = _pair()
    link = _scene_link(project)
    assert (link.source_side, link.target_side) == (None, None)
    edge = _editor_edges(render_project_html(project))[0]
    assert (edge["sourcePort"], edge["targetPort"]) == ("auto", "auto")


@pytest.mark.parametrize("side", ["top", "right", "bottom", "left"])
def test_a_side_pinned_on_either_end_reaches_the_static_renderer(side: str) -> None:
    project, _users, _app = _pair(source_port=side, target_port=side)
    link = _scene_link(project)
    assert (link.source_side, link.target_side) == (side, side)


def test_a_pinned_side_opens_in_the_editor_as_that_side() -> None:
    project, _users, app = _pair(source_port="bottom", target_port="top")
    edge = _editor_edges(render_project_html(project))[0]
    assert (edge["sourcePort"], edge["targetPort"]) == ("bottom", "top")
    # and the panel's own reader agrees, element by element
    element = next(item for item in project.topology.walk() if item.connections)
    connection = element.connections[0]
    assert connection.target == app.id
    assert _pinned_side(element, connection, "source_port") == "bottom"
    assert _pinned_side(element, connection, "target_port") == "top"


def test_the_side_is_kept_apart_from_the_wire_style_the_editor_edits() -> None:
    project, _users, _app = _pair(source_port="left", stroke="#c7254e", width=2.0)
    edge = _editor_edges(render_project_html(project))[0]
    assert edge["sourcePort"] == "left"
    assert edge["style"] == {"stroke": "#c7254e", "width": 2.0}, (
        "a side is not a style: the Style panel must not show it as one"
    )


def test_a_side_that_is_not_a_side_is_ignored() -> None:
    project, _users, _app = _pair(source_port="sideways", target_port=None)
    link = _scene_link(project)
    assert (link.source_side, link.target_side) == (None, None)
    edge = _editor_edges(render_project_html(project))[0]
    assert (edge["sourcePort"], edge["targetPort"]) == ("auto", "auto")


def test_a_pinned_side_moves_where_the_wire_meets_its_card() -> None:
    """The wire leaves the side it was given, not the facing one."""
    facing = _scene_link(_pair()[0])
    pinned = _scene_link(_pair(source_port="top")[0])
    assert facing.source_side is None and pinned.source_side == "top"
    from infragram.builders.render import _anchors, _route_for

    project, _users, _app = _pair(source_port="top")
    scene = _scene_for(project)
    link = scene.links[0]
    route = _route_for(link, scene)
    assert route is not None
    top = _anchors(link.source, scene)["top"]
    assert (round(route.corners[0].x), round(route.corners[0].y)) == (round(top.x), round(top.y))


def test_a_side_written_in_python_reaches_the_drawing() -> None:
    """``Edge(..., leaves=...)`` is the same choice the Text tab makes."""
    from infragram.author import Diagram, Edge
    from infragram.nodes.frames import azure as az

    with Diagram("Sides", "Sides.", slug="sides-dsl", providers=("azure",)) as diagram:
        with az.VNet("vnet-demo"):
            gateway = compute.VirtualMachine("Gateway", "WAF")
            web = compute.VirtualMachine("Web", "scale set")
        gateway >> Edge("HTTPS", leaves="bottom", arrives="top") >> web
    project = diagram.to_project()
    link = _scene_link(project)
    assert (link.source_side, link.target_side) == ("bottom", "top")
    edge = _editor_edges(render_project_html(project))[0]
    assert (edge["sourcePort"], edge["targetPort"]) == ("bottom", "top")


def test_a_side_python_does_not_know_is_refused_where_it_is_written() -> None:
    from infragram.author import Edge

    with pytest.raises(ValueError, match="unknown side"):
        Edge("HTTPS", leaves="sideways")


def _routes_between(project) -> list[str]:
    """Every route the static renderer draws, as rounded corner lists."""
    from infragram.builders.render import _route_for
    from infragram.exports.render import _scene_for

    scene = _scene_for(project)
    routes = []
    for link in scene.links:
        route = _route_for(link, scene)
        assert route is not None
        routes.append(" ".join(f"{round(point.x)},{round(point.y)}" for point in route.corners))
    return routes


def test_one_wire_between_two_components_runs_straight() -> None:
    project, _users, _app = _pair()
    assert len(_routes_between(project)) == 1


def test_wires_that_join_the_same_pair_take_a_lane_each() -> None:
    """Both anchors are shared, so the wires part in the middle or not at all."""
    users = shared.identity.PublicUsers("Users", "customers")
    app = compute.VirtualMachine("App server", "web")
    users.to(app, label="HTTPS")
    users.to(app, label="WSS")
    project = compose.to_project(
        [users, app], slug="lanes", title="Lanes", description="Lanes.", display="card"
    )
    routes = _routes_between(project)
    assert len(routes) == 2
    assert routes[0] != routes[1], "two wires on one line read as one wire"
    # they part evenly, one either side of the line a single wire would take
    middles = [
        [float(part) for part in corner.split(",")]
        for route in routes
        for corner in route.split(" ")[1:-1]
    ]
    assert middles, routes
    lanes = sorted({round(point[1]) for point in middles})
    assert len(lanes) >= 2, routes


def test_a_third_wire_takes_the_middle_lane() -> None:
    users = shared.identity.PublicUsers("Users", "customers")
    app = compute.VirtualMachine("App server", "web")
    for label in ("HTTPS", "WSS", "gRPC"):
        users.to(app, label=label)
    project = compose.to_project(
        [users, app], slug="lanes3", title="Lanes", description="Lanes.", display="card"
    )
    routes = _routes_between(project)
    assert len(routes) == 3
    assert len(set(routes)) == 3, routes
