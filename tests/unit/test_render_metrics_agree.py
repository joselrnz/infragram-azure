"""Both renderers read one set of numbers.

A document is drawn twice: by this package, and by the editor runtime inside
an exported page. They are separate implementations of the same picture, and
they had drifted -- the detour margin, the corner radius, the widest an icon
card could grow and both dash patterns all differed, so the same document drew
differently depending on which renderer produced it. These tests fail if a
number is typed into either renderer again instead of read from the file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from infragram.builders import metrics
from infragram.builders.routing import Router
from infragram.builders.scene import Style
from infragram.editor.bundle import runtime_script

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
RUNTIME = runtime_script()


def test_the_python_renderer_takes_its_numbers_from_the_file() -> None:
    router, icon, dashes = metrics.router(), metrics.icon_node(), metrics.link_dashes()
    live = Router()
    assert (live.clearance, live.stub, live.margin, live.turn_cost, live.radius) == (
        router["clearance"],
        router["stub"],
        router["margin"],
        router["turn_cost"],
        router["radius"],
    )
    style = Style()
    # The two ceilings are different things: a card with a text lane grows
    # further than a bare glyph, and only the Python renderer grows one.
    assert style.node.max_width == metrics.card()["max_width"]
    assert style.node.width == metrics.card()["width"]
    assert style.node.icon_width == icon["width"]
    assert style.node.icon_height == icon["height"]
    assert style.node.icon_glyph == icon["glyph"]
    assert style.links["dashed"].dash == dashes["dashed"]
    assert style.links["dotted"].dash == dashes["dotted"]


def test_the_editor_runtime_reads_the_file_rather_than_repeating_it() -> None:
    """The runtime must name the spec, not the values."""
    assert "infragram-render-metrics" in RUNTIME, "the runtime reads the block the shell writes"
    for expression in (
        "METRICS.router.clearance",
        "METRICS.router.stub",
        "METRICS.router.margin",
        "METRICS.router.turn_cost",
        "METRICS.router.radius",
        "METRICS.router.straighten",
        "METRICS.icon_node.width",
        "METRICS.icon_node.max_width",
        "METRICS.link_dashes.dashed",
        "METRICS.link_dashes.dotted",
    ):
        assert expression in RUNTIME, f"the runtime should read {expression}"
    # And the old literals must be gone, or a future edit will silently split
    # the two renderers again.
    icon, dashes = metrics.icon_node(), metrics.link_dashes()
    for literal in (
        f"maxWidth: {icon['max_width']}",
        f"'{dashes['dashed']}'",
        f"'{dashes['dotted']}'",
    ):
        assert literal not in RUNTIME, f"{literal} is typed into the runtime instead of read"


def test_the_page_carries_the_same_numbers_the_package_uses() -> None:
    from infragram import compose
    from infragram.exports import render_project_html
    from infragram.nodes import infragram as shared, reset_ids
    from infragram.nodes.azure import general

    reset_ids()
    internet = shared.networking.PublicInternet("Internet", "public")
    browser = general.Browser("Browser", "client")
    internet.to(browser, label="egress")
    html = render_project_html(
        compose.to_project(
            [internet, browser], slug="m", title="M", description="m.", display="card"
        )
    )
    block = re.search(r'id="infragram-render-metrics">(.*?)</script>', html, re.S)
    assert block, "the shell writes the metrics into the page"
    assert json.loads(block.group(1)) == metrics.spec()


def test_an_icon_card_is_as_wide_in_the_picture_as_in_the_editor() -> None:
    """The picture sizes an icon card from its caption the way the editor's
    iconNodeWidth does, rounding included.

    The picture truncated the caption to a whole number before rounding up to
    the grid; the editor rounds the fraction up. On any caption a fraction
    above a multiple of four they came out 4px apart -- Cosmos DB's 184.2 was
    184 in the picture and 188 in the editor -- so four cards of the AKS
    baseline, and every wire that meets them, sat differently in the two.
    """
    import math

    from infragram.builders.scene import Node

    # The editor's formula, as the runtime writes it.
    assert "Math.ceil(caption / 4) * 4" in RUNTIME
    icon = metrics.icon_node()
    style = Style()
    style.canvas.fit = True
    apart = []
    for length in range(70):
        node = Node(id=f"n{length}", name="Name", detail="d" * length, display="icon")
        node.measure(style)
        caption = max(len("Name") * style.node.title_size * 0.58, length * 5.8) + 16
        editor = min(icon["max_width"], max(icon["width"], math.ceil(caption / 4) * 4))
        if node.width != editor:
            apart.append((length, node.width, editor))
    assert not apart, f"(detail length, picture, editor): {apart}"
