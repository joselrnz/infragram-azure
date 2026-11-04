"""Saved positions are trusted only when saved for the looks now drawn.

A card placed by hand that the display rules now draw bare is a 144 x 116
icon node at coordinates chosen for a 208 x 72 card, and it lands on the row
below. When any node with saved geometry resolves to a look other than the one
it was saved under, the whole document's saved geometry is stale and the
layout places it. The shipped templates carry no hand placement at all.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from infragram import compose
from infragram.exports import render_project_html
from infragram.models.topology import Waypoint
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import compute
from infragram.nodes.frames import azure as frames
from infragram.paths import skill_assets

STALE = ("editor_x", "editor_y", "editor_width", "editor_height", "editor_card_size")


@pytest.fixture(autouse=True)
def _fresh_ids():
    reset_ids()


def _state(html: str) -> dict:
    match = re.search(r'<script[^>]*id="infragram-editor-state"[^>]*>(.*?)</script>', html, re.S)
    assert match
    return json.loads(match.group(1))


def _estate():
    subscription = frames.Subscription("Production")
    app = (
        subscription
        >> frames.ResourceGroup("rg-prod")
        >> frames.Subnet("Private")
        >> compute.VirtualMachine("App server", "web")
    )
    users = shared.identity.PublicUsers("Users", "customers")
    users.to(app, label="HTTPS")
    return [users, subscription], users, app


def test_hand_placement_saved_for_cards_is_dropped_when_a_node_now_draws_bare() -> None:
    elements, users, app = _estate()
    # Saved when every node was a card: the users card sat exactly where the
    # app card sits now, which as a 144 x 116 icon node would overlap it.
    users.attributes.update(
        {"editor_x": 400, "editor_y": 200, "editor_card_size": {"width": 208, "height": 72}}
    )
    app.attributes.update({"editor_x": 400, "editor_y": 280})
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    nodes = {node["name"]: node for node in _state(render_project_html(project))["nodes"]}
    assert nodes["Users"]["displayMode"] == "icon"
    assert (nodes["Users"]["x"], nodes["Users"]["y"]) != (400, 200)
    assert (nodes["App server"]["x"], nodes["App server"]["y"]) != (400, 280)
    assert (nodes["Users"]["width"], nodes["Users"]["height"]) == (144, 116)


def test_hand_placement_is_kept_when_every_saved_mode_matches() -> None:
    elements, users, app = _estate()
    # A page the editor saved records the mode per node; matching modes keep
    # the author's placement.
    users.attributes.update({"editor_x": 40, "editor_y": 200, "editor_display_mode": "icon"})
    app.attributes.update({"editor_x": 400, "editor_y": 280, "editor_display_mode": "card"})
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    nodes = {node["name"]: node for node in _state(render_project_html(project))["nodes"]}
    assert (nodes["Users"]["x"], nodes["Users"]["y"]) == (40, 200)
    assert (nodes["App server"]["x"], nodes["App server"]["y"]) == (400, 280)


def test_a_card_pinned_by_the_author_keeps_its_saved_place() -> None:
    elements, users, app = _estate()
    # The author boxed the users node on purpose; its saved geometry is for a
    # card, and a card is what draws, so nothing is stale.
    users.attributes.update({"editor_x": 40, "editor_y": 200, "editor_display_mode": "card"})
    app.attributes.update({"editor_x": 400, "editor_y": 280})
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    nodes = {node["name"]: node for node in _state(render_project_html(project))["nodes"]}
    assert nodes["Users"]["displayMode"] == "card"
    assert (nodes["Users"]["x"], nodes["Users"]["y"]) == (40, 200)


def test_shipped_templates_are_layout_driven() -> None:
    for path in sorted((skill_assets() / "templates").rglob("*.infragram.json")):
        document = json.loads(path.read_text(encoding="utf-8"))

        def walk(element: dict, *, path: Path = path) -> None:
            attributes = element.get("attributes") or {}
            stale = [key for key in STALE if key in attributes]
            assert not stale, f"{path.name}: {element.get('id')} carries saved geometry {stale}"
            for connection in element.get("connections") or []:
                assert "waypoints" not in connection, (
                    f"{path.name}: {element.get('id')} carries saved waypoints"
                )
            for child in element.get("children") or []:
                walk(child, path=path)

        walk(document["topology"])


def _static_nodes(project):
    """Where the static renderer puts each node, by name."""
    from infragram.exports.render import _scene_for

    scene = _scene_for(project)
    return {node.name: node for node in scene.root.walk()}


def test_the_picture_and_the_editor_open_at_the_same_coordinates() -> None:
    """One drawing, two renderers: a saved layout is read by both."""
    elements, users, app = _estate()
    users.attributes.update({"editor_x": 40, "editor_y": 200, "editor_display_mode": "icon"})
    app.attributes.update({"editor_x": 400, "editor_y": 280, "editor_display_mode": "card"})
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    editor = {node["name"]: node for node in _state(render_project_html(project))["nodes"]}
    static = _static_nodes(project)
    for name in ("Users", "App server"):
        assert (static[name].x, static[name].y) == (editor[name]["x"], editor[name]["y"]), name
    assert (static["Users"].x, static["Users"].y) == (40, 200)


def test_stale_geometry_is_laid_out_by_both_renderers_alike() -> None:
    """Saved for looks that are no longer drawn: neither renderer trusts it."""
    elements, users, app = _estate()
    users.attributes.update(
        {"editor_x": 400, "editor_y": 200, "editor_card_size": {"width": 208, "height": 72}}
    )
    app.attributes.update({"editor_x": 400, "editor_y": 280})
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    editor = {node["name"]: node for node in _state(render_project_html(project))["nodes"]}
    static = _static_nodes(project)
    assert (static["Users"].x, static["Users"].y) != (400, 200)
    # Both lay the document out, and land on the same spot; the editor keeps
    # everything on its 4 px grid, so it may round the layout's odd pixel.
    for name in ("Users", "App server"):
        assert abs(static[name].x - editor[name]["x"]) <= 4, name
        assert abs(static[name].y - editor[name]["y"]) <= 4, name


def test_a_template_is_still_laid_out_from_scratch() -> None:
    """Nothing placed by hand means nothing to honour: the layout decides."""
    from infragram.projects import CloudProject

    for path in sorted((skill_assets() / "templates").rglob("*.infragram.json")):
        project = CloudProject.load(path)
        static = _static_nodes(project)
        assert static, path.name
        assert any(node.x or node.y for node in static.values()), path.name


def _wire_path(project) -> str:
    """The static renderer's path for the one wire in these fixtures."""
    from infragram.builders.render import _route_for
    from infragram.exports.render import _scene_for

    scene = _scene_for(project)
    assert len(scene.links) == 1
    route = _route_for(scene.links[0], scene)
    assert route is not None
    return " ".join(f"{round(point.x)},{round(point.y)}" for point in route.corners)


def test_a_bend_is_drawn_once_the_drawing_stands_where_it_was_pinned() -> None:
    """Bends are canvas coordinates: they mean something on that canvas."""
    elements, users, app = _estate()
    users.attributes.update({"editor_x": 40, "editor_y": 200, "editor_display_mode": "icon"})
    app.attributes.update({"editor_x": 400, "editor_y": 280, "editor_display_mode": "card"})
    users.connections[0].waypoints = (Waypoint(x=120, y=420),)
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    assert "120,420" in _wire_path(project)


def test_the_same_bend_is_ignored_when_the_document_was_never_arranged() -> None:
    elements, users, _app = _estate()
    users.connections[0].waypoints = (Waypoint(x=120, y=420),)
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    assert "120,420" not in _wire_path(project), "a corner from another canvas is not a corner here"


def test_a_bent_wire_still_turns_at_right_angles() -> None:
    """A bend is not licence to draw a diagonal: the picture rules hold."""
    elements, users, app = _estate()
    users.attributes.update({"editor_x": 40, "editor_y": 200, "editor_display_mode": "icon"})
    app.attributes.update({"editor_x": 400, "editor_y": 280, "editor_display_mode": "card"})
    users.connections[0].waypoints = (Waypoint(x=120, y=420), Waypoint(x=560, y=430))
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    corners = [
        tuple(float(part) for part in pair.split(",")) for pair in _wire_path(project).split(" ")
    ]
    for before, after in zip(corners, corners[1:], strict=False):
        assert before[0] == after[0] or before[1] == after[1], f"{before}-{after} is a diagonal"
    # and it really goes where it was pinned
    assert any(abs(x - 120) < 1 and abs(y - 420) < 1 for x, y in corners)
    assert any(abs(x - 560) < 1 and abs(y - 430) < 1 for x, y in corners)
