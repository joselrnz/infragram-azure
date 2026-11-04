"""Clicking an element that carries a table opens it in a popup beside the card.

A route table's card stays a card on the canvas; its routes appear only when
someone selects it, and go away with the selection.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from infragram.author import Diagram
from infragram.exports import render_project_html
from infragram.nodes.azure import networking as net
from infragram.nodes.frames import azure as az

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run Chromium editor checks",
)

COLUMNS = ("Prefix", "Next hop type", "Next hop")
ROUTES = [
    ("0.0.0.0/0", "Virtual appliance", "10.0.1.4"),
    ("10.0.0.0/16", "VNet peering", "hub-vnet"),
    ("10.1.0.0/16", "VNet local", "-"),
    ("192.168.0.0/16", "Virtual network gateway", "ExpressRoute"),
]
POPUP = "[data-canvas-popup]"
CARD = '[data-graph-node][data-node-id="rt-spoke-prod"]'


def _page(tmp_path: Path) -> Path:
    with Diagram(
        "Spoke routes", "A route table and a firewall.", slug="spoke-routes", providers=("azure",)
    ) as diagram:
        with az.VNet("spoke-prod 10.1.0.0/16").row():
            firewall = net.Firewalls("Azure Firewall", "10.0.1.4")
            routes = net.RouteTables("rt-spoke-prod", "UDR").table(COLUMNS, ROUTES)
        routes >> firewall
    source = tmp_path / "spoke-routes.html"
    source.write_text(render_project_html(diagram.to_project()), encoding="utf-8")
    return source


def test_selecting_the_card_opens_its_table_and_deselecting_closes_it(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = _page(tmp_path)
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri() + "?fresh=popup")
            page.wait_for_load_state("networkidle")
            popup = page.locator(POPUP)
            assert popup.is_hidden()

            page.locator(CARD).click()
            popup.wait_for(state="visible")
            assert popup.locator("header strong").text_content() == "rt-spoke-prod"
            assert popup.locator("th").all_text_contents() == list(COLUMNS)
            assert popup.locator("tbody tr").count() == len(ROUTES)
            assert popup.locator("tbody tr").first.locator("td").all_text_contents() == list(
                ROUTES[0]
            )

            # Beside the card, never on top of it.
            card, box = page.locator(CARD).bounding_box(), popup.bounding_box()
            assert (
                box["x"] >= card["x"] + card["width"]
                or box["x"] + box["width"] <= card["x"]
                or box["y"] >= card["y"] + card["height"]
                or box["y"] + box["height"] <= card["y"]
            )

            page.keyboard.press("Escape")
            popup.wait_for(state="hidden")

            page.locator(CARD).click()
            popup.wait_for(state="visible")
            popup.locator("[data-popup-close]").click()
            popup.wait_for(state="hidden")
            # The close button dismisses without deselecting the card.
            state = page.evaluate("() => window.infragramEditor.getState()")
            routes = next(node for node in state["nodes"] if node["id"] == "rt-spoke-prod")
            assert routes["attributes"]["table"]["columns"] == list(COLUMNS)
        finally:
            browser.close()


def test_a_card_without_a_table_opens_no_popup(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = _page(tmp_path)
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri() + "?fresh=nopopup")
            page.wait_for_load_state("networkidle")
            page.locator('[data-graph-node][data-node-id="azure-firewall"]').click()
            page.wait_for_timeout(200)
            assert page.locator(POPUP).is_hidden()
        finally:
            browser.close()
