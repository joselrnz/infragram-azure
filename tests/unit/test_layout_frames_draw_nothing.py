"""A frame with no name arranges what is inside it and draws nothing.

The static renderer has always worked this way -- ``builders/render.py`` emits
a cluster only ``if cl.label`` -- and it is what makes a nameless frame useful:
a container that puts an actor beside a stack of steps, or a row of frames
inside a column, without drawing a box nobody asked for.

The runtime drew the box. So a page and the picture of that page disagreed
about how many frames the diagram had, which is the one thing these two
renderers may never do. This checks both halves of the fix: the runtime marks
such a frame, and its own export drops it.
"""

from __future__ import annotations

from pathlib import Path

from infragram.author import Diagram, Edge
from infragram.editor.bundle import runtime_script
from infragram.exports import render_project_svg
from infragram.nodes import Group, reset_ids
from infragram.nodes.azure import compute, networking

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
MARKER = "data-boundary-arranges"


def _diagram():
    reset_ids()
    with Diagram(
        "Layout frames",
        "An actor beside a stack of steps.",
        slug="layout-frames",
        providers=("azure",),
        direction="down",
    ) as diagram:
        with Group("", "group").row().keep_order():
            gateway = networking.ApplicationGateways("Gateway", "WAF v2")
            with Group("", "group").column().keep_order():
                with Group("Tier one", "group"):
                    web = compute.VirtualMachine("Web", "scale set")
                with Group("Tier two", "group"):
                    worker = compute.VirtualMachine("Worker", "scale set")
        gateway >> Edge("HTTPS") >> web
        web >> Edge("queue") >> worker
    return diagram.to_project()


def test_the_static_renderer_draws_no_box_for_a_nameless_frame() -> None:
    project = _diagram()
    nameless = [
        element.id
        for element in project.topology.walk()
        if element.is_frame and not element.name.strip()
    ]
    assert len(nameless) == 2, "the fixture needs two layout frames"

    svg = render_project_svg(project, "#ffffff")
    for frame_id in nameless:
        assert f'"{frame_id}"' not in svg, f"{frame_id} was drawn"
    # the named frames around them are drawn, so this is not an empty picture
    assert "Tier one" in svg and "Tier two" in svg


def test_the_runtime_marks_a_nameless_frame_and_drops_it_on_export() -> None:
    """Both halves, in the bundle the page actually ships."""
    runtime = runtime_script()
    assert f"' {MARKER}'" in runtime or f'"{MARKER}"' in runtime or MARKER in runtime, (
        "the runtime no longer marks a nameless frame"
    )
    # 29-downloads' own strip list is what the exporter is handed
    strip = next(
        line
        for line in runtime.splitlines()
        if "data-connection-preview]" in line and "querySelectorAll" in line
    )
    assert MARKER in strip, "a marked frame is not stripped from the runtime's export"


def test_the_marker_is_not_mistaken_for_an_executable_attribute() -> None:
    """The first name for this was ``data-boundary-layout-only``, and the
    shipped checker rejected every picture that carried it: ``only=`` begins
    with the letters of an event handler. It was right to -- an attribute that
    reads like one has no business in a drawing somebody will open."""
    from infragram.verification import unsafe_svg_match

    assert unsafe_svg_match('data-boundary-layout-only="true"'), (
        "the screen no longer catches the name this was called first"
    )
    assert not unsafe_svg_match(f'{MARKER}="true"'), f"{MARKER} still trips the screen"
