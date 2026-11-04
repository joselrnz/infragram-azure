"""The static router follows the editor's policy, so both pictures draw the same wire."""

from __future__ import annotations

import importlib

from infragram.builders import metrics
from infragram.builders.architecture import load_theme
from infragram.builders.routing import Point, Rect, Router, nearest
from infragram.builders.scene import Node, Scene, Style

render = importlib.import_module("infragram.builders.render")


def _scene(*nodes: Node) -> Scene:
    scene = Scene(slug="policy", theme=load_theme("azure"), title="Policy", desc="", style=Style())
    for node in nodes:
        scene.root.children.append(node)
    return scene


def _node(name: str, x: int, y: int) -> Node:
    return Node(name=name, ref=name, x=x, y=y, width=208, height=64)


def test_facing_sides_come_from_where_the_nodes_stand() -> None:
    left, right = _node("a", 0, 0), _node("b", 400, 0)
    assert render._inferred_sides(left, right) == ("right", "left")
    assert render._inferred_sides(right, left) == ("left", "right")
    above, below = _node("a", 0, 0), _node("b", 0, 400)
    assert render._inferred_sides(above, below) == ("bottom", "top")
    assert render._inferred_sides(below, above) == ("top", "bottom")


def test_a_clear_plain_path_is_kept_without_a_search() -> None:
    # two cards side by side, offset: one dog-leg through the snapped middle
    a, b = _node("a", 0, 0), _node("b", 500, 120)
    scene = _scene(a, b)
    link = scene.link(a, b)
    route = render._route_uncached(link, scene)
    assert route is not None
    grid = metrics.router()["grid"]
    mid = (a.x + a.width + b.x) / 2
    assert mid % grid == 0 or [p.x for p in route.corners][1] % grid == 0
    xs = [p.x for p in route.corners]
    assert len(route.corners) == 4 and xs[1] == xs[2], "H-V-H through one middle"


def test_a_blocked_plain_path_routes_around_the_card_in_the_way() -> None:
    a, c = _node("a", 0, 0), _node("c", 600, 0)
    blocker = _node("b", 300, -20)  # square across the straight line between them
    scene = _scene(a, blocker, c)
    link = scene.link(a, c)
    route = render._route_uncached(link, scene)
    assert route is not None and len(route.corners) > 2
    box = Rect.around(blocker)
    assert not any(box.blocks(p, q) for p, q in zip(route.corners, route.corners[1:], strict=False))


def test_the_nearest_obstacles_cap_keeps_the_boxes_around_the_span() -> None:
    boxes = [Rect(i * 100, 0, i * 100 + 50, 50) for i in range(60)]
    near = nearest(boxes, Point(0, 25), Point(120, 25), 48)
    assert near is not boxes and len(near) == 48
    assert boxes[0] in near and boxes[1] in near and boxes[59] not in near
    few = boxes[:10]
    assert nearest(few, Point(0, 0), Point(1, 1), 48) is few


def test_the_cap_and_the_grid_are_shared_metrics() -> None:
    table = metrics.router()
    assert table["max_obstacles"] == 48 and table["grid"] == 4
    assert render._ROUTER["max_obstacles"] == table["max_obstacles"]
    from infragram.editor.bundle import runtime_script

    source = runtime_script()
    assert "METRICS.router.max_obstacles" in source


def test_a_prepared_search_uses_the_boxes_as_given() -> None:
    router = Router()
    wall = Rect(90, -100, 110, 100)
    route = router.route_prepared(Point(0, 0), Point(200, 0), [wall])
    assert route is not None and len(route.corners) >= 4
    assert not any(
        wall.blocks(p, q) for p, q in zip(route.corners, route.corners[1:], strict=False)
    )


def test_twin_wires_keep_their_lanes_when_the_lanes_are_clear() -> None:
    a, c = _node("a", 0, 0), _node("c", 600, 120)
    scene = _scene(a, c)
    there, back = scene.link(a, c), scene.link(c, a)
    routes = [render._route_uncached(link, scene) for link in (there, back)]
    assert all(route.shaped for route in routes), "each twin keeps the lane it was given"
    assert routes[0].corners != routes[1].corners


def test_a_twin_whose_lane_runs_through_a_card_is_searched_like_any_wire() -> None:
    # The editor's lane is a preference (connectorPath): a bent lane that
    # enters a card is dropped and the wire routed around it. The static
    # picture kept the lane and drew both twins through the card between.
    a, c = _node("a", 0, 0), _node("c", 600, 0)
    blocker = _node("b", 300, -20)
    scene = _scene(a, blocker, c)
    box = Rect.around(blocker)
    for link in (scene.link(a, c), scene.link(c, a)):
        route = render._route_uncached(link, scene)
        assert not route.shaped
        corners = route.corners
        assert not any(box.blocks(p, q) for p, q in zip(corners, corners[1:], strict=False))


def test_a_wire_goes_around_a_frame_that_holds_neither_end() -> None:
    """A frame between two cards that holds neither is a fence: crossing its
    border costs, and the lanes a clearance or two outside it give the way
    around, so the wire keeps beside it rather than going through."""
    from infragram.builders.routing import fence_crossings

    router = Router()
    start, end = Point(0, 100), Point(400, 100)
    fence = Rect(150, 60, 250, 140)
    straight = router.route_prepared(start, end, [], fences=[fence])
    assert straight is not None
    assert all(
        fence_crossings([fence], a, b) == 0
        for a, b in zip(straight.corners, straight.corners[1:], strict=False)
    )
    assert any(
        abs(c.y - (fence.top - router.clearance)) < 0.01
        or abs(c.y - (fence.bottom + router.clearance)) < 0.01
        for c in straight.corners
    ), straight.corners
    # without the fence, the same two points run straight through
    assert router.route_prepared(start, end, [], fences=[]).corners == (start, end)
    # a border is counted once when a route stops on it and goes on
    assert fence_crossings([fence], Point(100, 100), Point(150, 100)) == 1
    assert fence_crossings([fence], Point(150, 100), Point(200, 100)) == 0
    assert fence_crossings([fence], Point(0, 100), Point(400, 100)) == 2
    assert fence_crossings([fence], Point(0, 20), Point(400, 20)) == 0


def test_a_frame_that_holds_an_end_is_no_fence() -> None:
    from infragram.builders.scene import Cluster

    a, b = _node("a", 40, 40), _node("b", 600, 40)
    scene = _scene(a, b)
    holding = Cluster(label="holds a", x=20, y=20, width=260, height=120)
    between = Cluster(label="between", x=320, y=0, width=200, height=200)
    scene.root.children.extend([holding, between])
    fences = render._fences(scene, a, b)
    assert [(f.left, f.top) for f in fences] == [(320.0, 0.0)]


def test_the_runtime_knows_fences_too() -> None:
    from infragram.editor.bundle import runtime_script

    script = runtime_script()
    for name in ("fenceBoxes", "fenceCrossings", "crossCost"):
        assert name in script, name
    assert metrics.router()["cross_cost"] > 0
