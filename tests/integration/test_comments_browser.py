"""Comments on a card and a frame survive a rename and a reload, download,
and come back through an export; no picture carries them (ADR 0009).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from infragram.author import Diagram, Edge
from infragram.cli.user import export_project as export_command
from infragram.nodes.azure import compute, databases
from infragram.nodes.frames import azure as az

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run Chromium editor checks",
)

PANEL = "[data-comments-panel]"
TOGGLE = "[data-comments-toggle]"
# a point on a frame's own surface, clear of what it holds
FRAME_SPOT = """id => {
  const frame = document.querySelector(`[data-graph-boundary][data-boundary-id="${id}"]`);
  const box = frame.getBoundingClientRect();
  for (let inset = 4; inset < 40; inset += 3) {
    for (let along = 0.3; along < 0.95; along += 0.05) {
      const x = box.left + box.width * along, y = box.bottom - inset;
      const hit = document.elementFromPoint(x, y);
      if (hit && !hit.closest('[data-graph-node]')
        && hit.closest('[data-graph-boundary]')?.dataset.boundaryId === id) return [x, y];
    }
  }
  return null;
}"""


def _document(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    with Diagram(
        "Review", "Two cards in a network.", slug="review", providers=("azure",)
    ) as diagram:
        with az.VNet("app 10.1.0.0/16") as network:
            vm = compute.VirtualMachine("vm-app")
            database = databases.SQLDatabase("sqldb-orders")
        vm >> Edge("TDS 1433") >> database
    source = tmp_path / "review.infragram.json"
    diagram.to_project().save(source)
    return source, {"network": network.id, "vm": vm.id}


def _export(source: Path, out: Path) -> Path:
    assert (
        export_command.main([str(source), "--formats", "html,svg,drawio", "--output-dir", str(out)])
        == 0
    )
    return out / "review.html"


def _comment(page, text: str, author: str = "") -> None:
    """Add comment from the open menu, write it, and close the panel again:
    it floats over the map, where the next right-click goes."""
    page.locator('[data-context-action="comment-add"]').click()
    if author:
        page.locator(f"{PANEL} [data-comment-author]").fill(author)
        page.locator(f"{PANEL} [data-comment-author]").dispatch_event("change")
    page.locator(f"{PANEL} [data-comment-text]").fill(text)
    page.locator(f"{PANEL} [data-comment-submit]").click()
    page.locator(f"{PANEL} [data-comments-close]").click()


def test_comments_survive_a_rename_and_a_reload_and_come_back_through_an_export(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source, ids = _document(tmp_path)
    page_path = _export(source, tmp_path / "first")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960}, accept_downloads=True)
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(page_path.resolve().as_uri() + "?fresh=comments")
            page.wait_for_load_state("networkidle")
            page.evaluate("() => window.infragramEditor.whenSettled()")

            # on the card
            card = page.locator(f'[data-graph-node][data-node-id="{ids["vm"]}"]')
            box = card.bounding_box()
            assert box is not None
            page.mouse.click(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, button="right"
            )
            _comment(page, "Is this VM still needed?", author="Ana")
            # on the frame
            spot = page.evaluate(FRAME_SPOT, ids["network"])
            assert spot, "no clear point on the frame"
            page.mouse.click(spot[0], spot[1], button="right")
            _comment(page, "Peer this with the hub.")
            assert page.locator("[data-comment-marker]").count() == 2
            assert page.locator(f"{TOGGLE} [data-comments-count]").inner_text() == "2"

            # renamed in the editor: the id stays, the comment follows
            card.dblclick()
            page.locator('[data-inspector-tab="text"]').click()
            page.locator('[data-content-control="name"]').fill("vm-api")
            page.locator('[data-content-control="name"]').press("Enter")
            page.reload()
            page.wait_for_load_state("networkidle")
            page.locator(TOGGLE).click()
            threads = page.locator(f"{PANEL} [data-comment-thread]")
            assert threads.count() == 2
            titles = page.locator(f"{PANEL} [data-comment-reveal]").all_inner_texts()
            assert sorted(titles) == ["app 10.1.0.0/16", "vm-api"]

            # the file a reviewer sends back
            with page.expect_download() as caught:
                page.locator(f"{PANEL} [data-comments-download]").click()
            downloaded = caught.value
            assert downloaded.suggested_filename == "review.comments.json"
            sidecar = source.parent / "review.comments.json"
            downloaded.save_as(sidecar)
            saved = json.loads(sidecar.read_text(encoding="utf-8"))
            assert saved["format"] == "infragram.comments/1" and saved["slug"] == "review"
            by_text = {item["text"]: item for item in saved["comments"]}
            assert by_text["Is this VM still needed?"]["anchor"] == {
                "kind": "node",
                "id": ids["vm"],
                "name": "vm-api",
            }
            assert by_text["Is this VM still needed?"]["author"] == "Ana"

            # a page saved from the editor carries none of this reader's
            # comments: they are the browser's until downloaded
            saved_page = page.evaluate("() => window.infragramEditor.exportHtml()")
            assert "still needed" not in saved_page and "Peer this" not in saved_page
            # no marker on the card (the runtime's own source names the attribute)
            assert f'data-comment-item="{ids["vm"]}"' not in saved_page

            # no picture carries a comment, even with markers on the canvas
            svg = page.evaluate("() => window.infragramEditor.exportSvg()")
            assert "data-comment-marker" not in svg and "still needed" not in svg
            assert not errors, errors
        finally:
            browser.close()

    # an export beside that file carries the comments into a fresh page
    second = _export(source, tmp_path / "second")
    html = second.read_text(encoding="utf-8")
    assert 'id="infragram-comments"' in html and "Is this VM still needed?" in html
    svg = (tmp_path / "second" / "review.svg").read_text(encoding="utf-8")
    assert "still needed" not in svg and "infragram-comments" not in svg
    drawio = (tmp_path / "second" / "review.drawio").read_text(encoding="utf-8")
    assert "still needed" not in drawio
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(second.resolve().as_uri() + "?fresh=carried")
            page.wait_for_load_state("networkidle")
            assert page.locator(f"{TOGGLE} [data-comments-count]").inner_text() == "2"
            assert page.locator("[data-comment-marker]").count() == 2
            # carried comments are the file's: this page offers no delete for them
            page.locator(TOGGLE).click()
            assert page.locator(f"{PANEL} [data-comment-delete]").count() == 0
        finally:
            browser.close()
