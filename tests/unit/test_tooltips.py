"""Hovering a component explains it, in the page and in the exported SVG.

Two layers, because they serve two readers. The SVG ``<title>`` on every
node is what a viewer with no script shows: the exported ``.svg`` opened in
a browser, an image viewer, or pasted into a document. The page's own
tooltip adds what only the page knows -- component id, frame, layer, and for
a wire, what it joins.
"""

from __future__ import annotations

import re
from pathlib import Path

from infragram.exports import render_project_html
from infragram.projects import CloudProject

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
TEMPLATE = (
    ROOT / "skills/infragram-azure/assets/templates/cloud/azure-web-app-front-door.infragram.json"
)


def test_every_static_node_carries_a_native_title() -> None:
    html = render_project_html(CloudProject.load(TEMPLATE))
    groups = re.findall(r'<g [^>]*data-node="[^"]*" data-display="[a-z]+">(.*?)</g>', html, re.S)
    assert groups, "no static node groups"
    for body in groups:
        title = re.search(r"<title>(.*?)</title>", body, re.S)
        assert title and title.group(1).strip(), "a node group without a title"


def test_the_title_reads_name_then_detail() -> None:
    html = render_project_html(CloudProject.load(TEMPLATE))
    titles = re.findall(
        r'<g [^>]*data-node="[^"]*" data-display="[a-z]+"><title>(.*?)</title>', html
    )
    # Every card of the template has a detail line, so every title has both.
    assert titles and all(" · " in title for title in titles)


def test_the_runtime_draws_its_own_title_and_a_richer_tooltip() -> None:
    html = render_project_html(CloudProject.load(TEMPLATE))
    # the SVG-native layer, added to each node the runtime draws
    assert "const nativeTitle = `<title>${escapeText([node.name, node.detail]" in html
    assert "${nativeTitle}" in html
    # the page layer: an element, its styling, and the pointer wiring
    assert 'data-canvas-tooltip role="tooltip" hidden' in html
    assert ".canvas-tooltip{" in html
    assert "const tooltipRows = (target" in html
    for handler in ("pointerover", "pointermove", "pointerleave", "pointerdown"):
        assert f"diagram.addEventListener('{handler}'" in html


def test_the_tooltip_explains_nodes_wires_and_frames() -> None:
    html = render_project_html(CloudProject.load(TEMPLATE))
    body = html[html.index("const tooltipRows = (target") : html.index("const hideTooltip")]
    for label in (
        "'Component'",
        "'Frame'",
        "'Layer'",
        "'From'",
        "'To'",
        "'Line'",
        "'Inside'",
        "'Contains'",
    ):
        assert label in body, f"tooltip does not carry {label}"


def test_the_tooltip_stays_out_of_the_way_while_dragging() -> None:
    """A tooltip that pops during a drag or a connection covers the target."""
    html = render_project_html(CloudProject.load(TEMPLATE))
    assert "if (event.buttons !== 0 || connection) return hideTooltip();" in html
    assert "diagram.addEventListener('pointerdown', hideTooltip);" in html
