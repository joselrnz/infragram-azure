"""The exported page is one file anyone can open, so open it in every engine.

The rest of the browser suite drives Chromium, which is what the gates run and
what most readers use. It cannot answer the question this file asks: does the
page work in the other two engines, opened straight from ``file://`` with no
server? Two bugs found by asking are the reason it exists -- a card under the
pointer that Firefox would not report during a drag, and a colour field that
WebKit does not have, which threw the moment a connector was selected.

Firefox and WebKit are not installed with Chromium; ``python -m playwright
install firefox webkit`` adds them, and these checks skip until they are there.
"""

from __future__ import annotations

import os
import tempfile
from functools import cache
from pathlib import Path

import pytest

from infragram.exports import render_project_html, render_timeout_ms
from infragram.paths import skill_assets
from infragram.projects import CloudProject

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run the engine checks",
)

ENGINES = ("chromium", "firefox", "webkit")


@cache
def _page_file() -> Path:
    # Written once per run, for the three engines to share. A page kept from
    # an earlier run was the editor as it was then, not the one under test.
    source = Path(tempfile.gettempdir()) / f"infragram-engines-{os.getpid()}.html"
    project = CloudProject.load(
        skill_assets() / "templates" / "cloud" / "azure-aks-baseline.infragram.json"
    )
    source.write_text(render_project_html(project, libraries="all"), encoding="utf-8")
    return source


def _middle(page, selector):
    box = page.locator(selector).first.bounding_box()
    assert box, selector
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


@pytest.mark.parametrize("engine", ENGINES)
def test_the_exported_page_works_in_this_engine(engine: str) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = _page_file()
    with sync_api.sync_playwright() as playwright:
        try:
            browser = getattr(playwright, engine).launch()
        except Exception as missing:  # noqa: BLE001
            pytest.skip(f"{engine} is not installed: {str(missing)[:60]}")
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
            page.on(
                "console",
                lambda message: (
                    errors.append(f"console: {message.text}") if message.type == "error" else None
                ),
            )
            page.goto(f"{source.resolve().as_uri()}?fresh={engine}")
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            page.evaluate("() => window.infragramEditor.whenSettled()")

            state = page.evaluate("() => window.infragramEditor.getState()")
            assert page.evaluate(
                "() => document.querySelectorAll('[data-graph-node]').length"
            ) == len(state["nodes"]), "every component is drawn"
            assert page.evaluate(
                "() => document.querySelectorAll('[data-graph-edge]').length"
            ) == len(state["edges"]), "every connector is drawn"

            page.locator('[data-editor-action="zoom-reset"]').click()
            page.wait_for_timeout(400)
            # The pointer is driven at real coordinates, so both cards have to
            # be on screen. Which ones are depends on the platform's text
            # metrics -- the cards this once named sit off screen in a Linux
            # container and on screen on Windows -- so the page picks the
            # nearest two unjoined cards that fit together and centres them.
            pair = page.evaluate("""() => {
              const state = window.infragramEditor.getState();
              const joined = new Set(state.edges.flatMap(edge => [
                `${edge.source}|${edge.target}`, `${edge.target}|${edge.source}`]));
              const view = document.querySelector('.canvas-viewport');
              const room = {width: view.clientWidth - 120, height: view.clientHeight - 120};
              let best = null;
              for (const a of state.nodes) {
                for (const b of state.nodes) {
                  if (a.id === b.id || joined.has(`${a.id}|${b.id}`)) continue;
                  const width = Math.max(a.x + a.width, b.x + b.width) - Math.min(a.x, b.x);
                  const height = Math.max(a.y + a.height, b.y + b.height) - Math.min(a.y, b.y);
                  if (width > room.width || height > room.height) continue;
                  // a wire drawn rightwards, from the right-hand port
                  if (b.x <= a.x + a.width) continue;
                  const span = Math.hypot(a.x - b.x, a.y - b.y);
                  if (!best || span < best.span) best = {span, first: a.id, second: b.id};
                }
              }
              return best;
            }""")
            assert pair, "two unjoined cards fit on screen together"
            first, second = pair["first"], pair["second"]
            page.evaluate(
                """([a, b]) => {
              const view = document.querySelector('.canvas-viewport');
              const frame = view.getBoundingClientRect();
              const box = id => document.querySelector(`[data-node-id="${id}"]`).getBoundingClientRect();
              const one = box(a);
              const two = box(b);
              view.scrollLeft += (Math.min(one.left, two.left) + Math.max(one.right, two.right)) / 2
                - (frame.left + view.clientWidth / 2);
              view.scrollTop += (Math.min(one.top, two.top) + Math.max(one.bottom, two.bottom)) / 2
                - (frame.top + view.clientHeight / 2);
            }""",
                [first, second],
            )
            page.wait_for_timeout(300)
            on_screen = page.evaluate(
                """([a, b]) => {
              const frame = document.querySelector('.canvas-viewport').getBoundingClientRect();
              const inside = id => {
                const box = document.querySelector(`[data-node-id="${id}"]`).getBoundingClientRect();
                return box.left >= frame.left && box.right <= frame.right
                  && box.top >= frame.top && box.bottom <= frame.bottom;
              };
              return {first: inside(a), second: inside(b)};
            }""",
                [first, second],
            )
            assert on_screen == {"first": True, "second": True}, on_screen
            page.mouse.move(*_middle(page, f'[data-node-id="{first}"] [data-node-surface]'))
            page.wait_for_timeout(200)

            # the handle dots are scaled by CSS; they must scale about themselves
            placed = page.evaluate(
                """(id) => {
              const group = document.querySelector(`[data-node-id="${id}"] [data-node-port="right"]`);
              const dot = group.querySelector('circle.node-port-dot').getBoundingClientRect();
              const grab = group.querySelector('circle:not(.node-port-dot)').getBoundingClientRect();
              return {dx: Math.abs((dot.x + dot.width / 2) - (grab.x + grab.width / 2)),
                      dy: Math.abs((dot.y + dot.height / 2) - (grab.y + grab.height / 2))}; }""",
                first,
            )
            assert placed["dx"] < 1.5 and placed["dy"] < 1.5, (
                f"the handle dot sits on its port: {placed}"
            )

            # drawing a connector: the card under the pointer must be found
            handle = _middle(
                page, f'[data-node-id="{first}"] [data-node-port="right"] circle.node-port-dot'
            )
            target = _middle(page, f'[data-node-id="{second}"] [data-node-surface]')
            assert page.evaluate(
                """([x, y, id]) => document.elementFromPoint(x, y)
                  ?.closest('[data-graph-node]')?.dataset.nodeId === id""",
                [*target, second],
            ), "the target point belongs to the target card"
            page.mouse.move(*handle)
            page.mouse.down()
            sync_api.expect(page.locator(".canvas-viewport")).to_have_attribute(
                "data-connecting", "true", timeout=render_timeout_ms()
            )
            page.mouse.move((handle[0] + target[0]) / 2, (handle[1] + target[1]) / 2, steps=6)
            page.mouse.move(*target, steps=6)
            # Assert the connection has started before moving, then wait for
            # the target state rather than assuming a fixed render duration.
            sync_api.expect(
                page.locator(f'[data-node-id="{second}"]'), "the card under the pointer lights up"
            ).to_have_attribute("data-connect-target", "true", timeout=render_timeout_ms())
            page.mouse.up()
            assert (
                page.evaluate("() => window.infragramEditor.getState().edges.length")
                == len(state["edges"]) + 1
            ), "and dropping on it connects"

            # dragging a card, which patches the drawing rather than redrawing it
            page.keyboard.press("Escape")  # the toolbar over a selection is not a drag handle
            page.wait_for_timeout(100)
            before = page.evaluate(
                "(id) => window.infragramEditor.getState().nodes.find(n => n.id === id)", first
            )
            spot = _middle(page, f'[data-node-id="{first}"] [data-node-surface]')
            assert page.evaluate(
                """([x, y, id]) => document.elementFromPoint(x, y)
                ?.closest('[data-node-id]')?.dataset.nodeId === id""",
                [*spot, first],
            ), "the card is what the pointer would press"
            page.mouse.move(*spot)
            page.mouse.down()
            for step in range(4):
                page.mouse.move(spot[0] + 18 * (step + 1), spot[1] + 12 * (step + 1))
            page.mouse.up()
            after = page.evaluate(
                "(id) => window.infragramEditor.getState().nodes.find(n => n.id === id)", first
            )
            assert (after["x"], after["y"]) != (before["x"], before["y"]), "the card moves"

            # the chrome a reader touches next
            page.locator('[data-inspector-tab="text"]').click()
            assert (
                page.locator('[data-inspector-tab="text"]').get_attribute("aria-selected") == "true"
            )
            page.locator('[data-editor-action="shortcuts"]').click()
            assert page.locator("[data-shortcut-sheet]").is_visible()
            page.keyboard.press("Escape")
            assert (
                page.evaluate("""() => new XMLSerializer()
                .serializeToString(document.querySelector('[data-infragram-diagram]')).length""")
                > 10000
            ), "the drawing can be serialised, which is what an export does"

            # A click shows a card's flow and a double click selects it. The
            # double click comes as the engine's own dblclick: a press carries
            # no click count every engine agrees on.
            joined = page.evaluate("() => window.infragramEditor.getState().edges[0].source")
            # nothing selected first: the drawing's keyboard, and Escape
            page.evaluate("() => document.querySelector('[data-infragram-diagram]').focus()")
            page.keyboard.press("Escape")
            spot = _middle(page, f'[data-node-id="{joined}"] [data-node-surface]')
            page.mouse.click(*spot)
            assert page.locator('[data-graph-edge][data-focus-edge="true"]').count() >= 1, (
                "its flow"
            )
            assert page.locator('[data-graph-node][data-selected="true"]').count() == 0, (
                "and no selection"
            )
            page.mouse.dblclick(*spot)
            assert (
                page.locator(
                    f'[data-graph-node][data-node-id="{joined}"][data-selected="true"]'
                ).count()
                == 1
            ), "a double click selects it"

            assert not errors, errors
        finally:
            browser.close()
