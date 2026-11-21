"""Clicking a frame's badge opens what it stands for; hovering shows addresses.

A subnet's NSG badge opens the security group's rules, its route table badge
the routes, exactly as written. Clicking the VNet lists its subnets' tables,
one table for a group two subnets share. The pointer resting on a card or a
frame's title that carries addresses shows them, and so does the right-click
menu; a card without any still shows nothing on hover.
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

NSG = (
    ("Priority", "Name", "Access", "Destination ports"),
    [("200", "allow-sql", "Allow", "1433"), ("100", "worker", "Allow", "*")],
)
ROUTES = (
    ("Name", "Address prefix", "Next hop type", "Next hop IP"),
    [("default-via-firewall", "0.0.0.0/0", "VirtualAppliance", "10.0.1.4")],
)
POPUP = "[data-canvas-popup]"
TIP = "[data-canvas-tooltip]"


def _page(tmp_path: Path) -> Path:
    with Diagram(
        "Spoke", "Two subnets sharing an NSG and a UDR.", slug="spoke", providers=("azure",)
    ) as diagram:
        with az.VNet("vnet-spoke · 10.1.0.0/16").row():
            for name, router in (
                ("snet-a · 10.1.1.0/24", "10.1.1.1"),
                ("snet-b · 10.1.2.0/24", "10.1.2.1"),
            ):
                with (
                    az.Subnet(name)
                    .badge(net.NetworkSecurityGroups, label="nsg-app", table=NSG)
                    .badge(net.RouteTables, label="rt-app", table=ROUTES)
                    .addresses(router=router)
                ):
                    net.Firewalls(f"fw {name[5]}").addresses(private=router[:-1] + "4")
            net.DNSZones("Key Vault")
    source = tmp_path / "spoke.html"
    source.write_text(render_project_html(diagram.to_project()), encoding="utf-8")
    return source


def _frame(page, starts: str):
    return (
        page.locator("[data-graph-boundary]")
        .filter(has=page.locator(f'[data-boundary-title]:text-matches("^{starts}")'))
        .first
    )


def test_badges_frames_hover_and_menu(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = _page(tmp_path)
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(source.resolve().as_uri() + "?fresh=badges")
            page.wait_for_load_state("networkidle")
            page.locator('[data-editor-action="zoom-reset"]').click()
            popup, tip = page.locator(POPUP), page.locator(TIP)

            # the route table badge: its routes, cell for cell, never recased
            subnet = _frame(page, "snet-a")
            subnet.locator('image[data-badge-index="1"]').click()
            popup.wait_for(state="visible")
            assert popup.locator("header strong").text_content() == "Route table · rt-app"
            first = popup.locator("tbody tr").first.locator("td")
            assert first.all_text_contents() == list(ROUTES[1][0])
            assert (
                first.first.evaluate(
                    "cell => getComputedStyle(cell, '::first-letter').textTransform"
                )
                == "none"
            )

            # the NSG badge: its rules in the order written
            subnet.locator('image[data-badge-index="0"]').click()
            page.wait_for_function(
                "() => document.querySelector('[data-canvas-popup] header strong')?.textContent.includes('nsg-app')"
            )
            assert [
                row.locator("td").first.text_content() for row in popup.locator("tbody tr").all()
            ] == ["200", "100"]
            page.keyboard.press("Escape")

            # the VNet: one NSG and one route table, naming both subnets
            _frame(page, "vnet-spoke").locator("[data-boundary-title]").click()
            popup.wait_for(state="visible")
            assert popup.locator("[data-popup-badge-table] h3").all_text_contents() == [
                "Network security group · nsg-app",
                "Route table · rt-app",
            ]
            assert "snet-a" in popup.text_content() and "snet-b" in popup.text_content()
            page.keyboard.press("Escape")

            # hover: a subnet's router, a card's address; a plain card says nothing
            subnet.locator("[data-boundary-title]").hover()
            tip.wait_for(state="visible")
            assert "10.1.1.1" in tip.inner_text()
            page.locator('[data-graph-node][data-node-id="key-vault"]').hover()
            tip.wait_for(state="hidden")

            # right-click: the facts under the menu's title list the addresses
            page.locator('[data-graph-node][data-node-id="fw-a"]').click(button="right")
            facts = page.locator("[data-canvas-context-menu] [data-context-menu-facts]")
            facts.wait_for(state="visible")
            assert "Private" in facts.inner_text() and "10.1.1.4" in facts.inner_text()
        finally:
            browser.close()
