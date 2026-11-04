"""A frame hugs what it holds when its contents change size in the editor.

A card is wide and short; the same component drawn as a bare icon is
narrower and taller (the glyph sits above its caption). Switching one
component, or the whole diagram, between the two used to resize only the
components: every frame kept its old box, so a column of icons spilled out
of the frame that had fitted the cards, and going back to cards squeezed the
cards into the frame instead of growing it. The picture exporters never had
the problem because they lay out again for each look; the editor, and the
SVG and HTML it downloads, did.

The contract checked here is containment with padding, in both directions of
the switch, for one component and for the whole diagram.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from infragram.exports import render_project_html, render_timeout_ms

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run Chromium editor checks",
)

#: Every node inside its frame and every frame inside its parent, with the
#: parent's padding on each side. Returns the offenders, so a failure names them.
_CONTAINMENT = """() => {
  const state = window.infragramEditor.getState();
  const frames = new Map(state.boundaries.map(frame => [frame.id, frame]));
  const offenders = [];
  const inside = (child, parent, label) => {
    const pad = Number(parent.pad) || 0;
    const ok = child.x >= parent.x + pad - 1
      && child.y >= parent.y + pad - 1
      && child.x + child.width <= parent.x + parent.width - pad + 1
      && child.y + child.height <= parent.y + parent.height - pad + 1;
    if (!ok) offenders.push({label, child: [child.x, child.y, child.width, child.height],
                             parent: [parent.x, parent.y, parent.width, parent.height, pad]});
  };
  state.nodes.forEach(node => {
    const parent = node.boundaryId ? frames.get(node.boundaryId) : null;
    if (parent) inside(node, parent, `node ${node.id} in ${parent.id}`);
  });
  state.boundaries.forEach(frame => {
    const parent = frame.parentId ? frames.get(frame.parentId) : null;
    if (parent) inside(frame, parent, `frame ${frame.id} in ${parent.id}`);
  });
  return offenders;
}"""


def _settled(page) -> None:
    page.wait_for_load_state("load")
    page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())


def _estate_page(tmp_path: Path) -> Path:
    """Two nested Azure frames holding a row of cards, laid out for cards."""
    from infragram.author import Diagram
    from infragram.nodes import reset_ids
    from infragram.nodes.azure import compute, databases
    from infragram.nodes.frames import azure as az

    reset_ids()
    # "laid out for cards", as the docstring says: the test switches one card
    # to an icon and measures the frame around it.
    with Diagram("Frame fit", "Frames that hug their contents.", display="card") as diagram:
        with az.Subscription("Production subscription"):
            with az.ResourceGroup("rg-prod-app").row():
                compute.VirtualMachine("App VM", "D4s v5")
                compute.VirtualMachine("Worker VM", "D2s v5")
                databases.SQLDatabase("Azure SQL", "Business Critical")
    source = tmp_path / "frame-fit.html"
    source.write_text(render_project_html(diagram.to_project()), encoding="utf-8")
    return source


def test_a_frame_grows_and_shrinks_with_one_component_switched_to_icon(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = _estate_page(tmp_path)
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(source.resolve().as_uri() + "?fresh=frame-fit-one")
            _settled(page)
            assert page.evaluate(_CONTAINMENT) == [], "the laid-out page already overflows"

            state = page.evaluate("() => window.infragramEditor.getState()")
            node = next(item for item in state["nodes"] if item["name"] == "App VM")
            frame_before = next(f for f in state["boundaries"] if f["id"] == node["boundaryId"])

            page.locator(f'[data-node-id="{node["id"]}"]').click(button="right")
            menu = page.get_by_role("menu", name="Canvas actions")
            menu.locator("[data-context-submenu-toggle]").click()
            menu.get_by_role("menuitemcheckbox", name="Icon only").click()

            after_icon = page.evaluate("() => window.infragramEditor.getState()")
            icon = next(item for item in after_icon["nodes"] if item["id"] == node["id"])
            assert icon["displayMode"] == "icon"
            assert icon["height"] > node["height"], "an icon is taller than its card"
            assert page.evaluate(_CONTAINMENT) == [], "the icon spilled out of its frame"
            frame_icon = next(f for f in after_icon["boundaries"] if f["id"] == node["boundaryId"])
            assert frame_icon["height"] > frame_before["height"], (
                "the frame did not grow for the icon"
            )

            page.locator(f'[data-node-id="{node["id"]}"]').click(button="right")
            menu.locator("[data-context-submenu-toggle]").click()
            menu.get_by_role("menuitemcheckbox", name="Card with text").click()
            after_card = page.evaluate("() => window.infragramEditor.getState()")
            card = next(item for item in after_card["nodes"] if item["id"] == node["id"])
            assert card["displayMode"] == "card"
            assert (card["width"], card["height"]) == (node["width"], node["height"]), (
                "the card was squeezed instead of the frame growing"
            )
            assert page.evaluate(_CONTAINMENT) == []
            frame_card = next(f for f in after_card["boundaries"] if f["id"] == node["boundaryId"])
            assert frame_card["height"] < frame_icon["height"], "the frame did not shrink back"
        finally:
            browser.close()


def test_every_frame_fits_when_the_whole_diagram_switches_look(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = _estate_page(tmp_path)
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(source.resolve().as_uri() + "?fresh=frame-fit-all")
            _settled(page)

            page.evaluate("() => window.infragramEditor.setDisplayMode('icon')")
            state = page.evaluate("() => window.infragramEditor.getState()")
            assert all(node["displayMode"] == "icon" for node in state["nodes"])
            assert page.evaluate(_CONTAINMENT) == [], "icons spilled out of their frames"

            page.evaluate("() => window.infragramEditor.setDisplayMode('card')")
            assert page.evaluate(_CONTAINMENT) == [], "cards spilled out after switching back"
        finally:
            browser.close()
