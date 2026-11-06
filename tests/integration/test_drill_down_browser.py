"""Opening a frame shows it alone, the breadcrumb goes back, a download stays whole.

A region holds a network that holds a subnet, and the users stand outside
them all. Opening the region and then the subnet draws only what each holds;
the wire to the users ends at the open frame's edge with their name, and that
name goes back to where they are. Nothing of it reaches the document or a
download.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from infragram.author import Diagram, Edge
from infragram.exports import render_project_html
from infragram.nodes.azure import compute, networking
from infragram.nodes.frames import azure as az
from infragram.nodes.infragram import identity

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run Chromium editor checks",
)

CRUMBS = "[data-drill-path]"
# a point on a frame's own surface, clear of what it holds and of its badge
FRAME_SPOT = """id => {
  const frame = document.querySelector(`[data-graph-boundary][data-boundary-id="${id}"]`);
  const box = frame.getBoundingClientRect();
  const clear = (x, y) => {
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) return false;
    const hit = document.elementFromPoint(x, y);
    return hit && !hit.closest('[data-graph-node]')
      && hit.closest('[data-graph-boundary]')?.dataset.boundaryId === id;
  };
  for (let inset = 4; inset < 40; inset += 3) {
    for (let along = 0.3; along < 0.95; along += 0.05) {
      for (const [x, y] of [[box.left + inset, box.top + box.height * along],
        [box.right - inset, box.top + box.height * along],
        [box.left + box.width * along, box.bottom - inset]]) {
        if (clear(x, y)) return [x, y];
      }
    }
  }
  return null;
}"""


def _page(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    with Diagram(
        "Drill", "A region, a network, a subnet.", slug="drill", providers=("azure",)
    ) as diagram:
        users = identity.PublicUsers("Customers")
        with az.Region("East US") as region:
            with az.VNet("hub 10.0.0.0/16") as network:
                firewall = networking.Firewalls("Azure Firewall")
                with az.Subnet("app 10.0.1.0/24") as subnet:
                    vm = compute.VirtualMachine("app vm")
        users >> Edge("HTTPS 443") >> firewall >> Edge("8443") >> vm
    project = diagram.to_project()
    source = tmp_path / "drill.html"
    source.write_text(render_project_html(project), encoding="utf-8")
    ids = {
        name: frame.id
        for name, frame in (("region", region), ("network", network), ("subnet", subnet))
    }
    ids.update(users=users.id, firewall=firewall.id, vm=vm.id)
    return source, ids


def _drawn(page) -> set[str]:
    return set(
        page.eval_on_selector_all("[data-graph-node]", "els => els.map(e => e.dataset.nodeId)")
    )


def _open(page, frame_id: str) -> None:
    spot = page.evaluate(FRAME_SPOT, frame_id)
    assert spot, f"no clear point on {frame_id}"
    page.mouse.click(spot[0], spot[1], button="right")
    page.locator('[data-context-action="frame-open"]').click()
    page.wait_for_timeout(300)


def test_two_levels_open_the_breadcrumb_returns_and_downloads_stay_whole(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source, ids = _page(tmp_path)
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(source.resolve().as_uri() + "?fresh=drill")
            page.wait_for_load_state("networkidle")
            assert page.locator(CRUMBS).is_hidden()
            everything = _drawn(page)
            assert {ids["users"], ids["firewall"], ids["vm"]} <= everything
            saved = page.evaluate("() => JSON.stringify(window.infragramEditor.getState())")

            # level one: the region, without the users outside it
            _open(page, ids["region"])
            assert page.locator(CRUMBS).inner_text().split("\n") == ["Whole diagram", "East US"]
            assert _drawn(page) == {ids["firewall"], ids["vm"]}
            stub = page.locator("[data-drill-stub] text", has_text="from Customers")
            assert stub.count() == 1

            # level two: the subnet, with the firewall now outside
            _open(page, ids["subnet"])
            assert page.locator(CRUMBS).inner_text().split("\n") == [
                "Whole diagram",
                "East US",
                "hub 10.0.0.0/16",
                "app 10.0.1.0/24",
            ]
            assert _drawn(page) == {ids["vm"]}
            assert (
                page.locator("[data-drill-stub] text", has_text="from Azure Firewall").count() == 1
            )

            # a download while a frame is open is the whole diagram, and the
            # frame is still open after it
            svg = page.evaluate("() => window.infragramEditor.exportSvg()")
            for node_id in (ids["users"], ids["firewall"], ids["vm"]):
                assert f'data-node-id="{node_id}"' in svg
            assert "data-drill-stub" not in svg
            assert _drawn(page) == {ids["vm"]}

            # a far end's name opens the frame that holds it
            page.locator("[data-drill-stub] text", has_text="from Azure Firewall").click()
            page.wait_for_timeout(300)
            assert page.locator(CRUMBS).inner_text().split("\n")[-1] == "hub 10.0.0.0/16"

            # the breadcrumb goes back up, all the way
            page.locator(f"{CRUMBS} [data-drill-to='1']").click()
            assert page.locator(CRUMBS).inner_text().split("\n")[-1] == "East US"
            page.locator(f"{CRUMBS} [data-drill-to='0']").click()
            assert page.locator(CRUMBS).is_hidden()
            assert _drawn(page) == everything

            # it was a view: the document is as it was
            assert page.evaluate("() => JSON.stringify(window.infragramEditor.getState())") == saved
            assert not errors, errors
        finally:
            browser.close()
