"""What changed lately and what a review would raise, in the editor.

An Azure import that read them gives the inventory a Findings and a Changed
column, a filter for each, the details of both beside the table, a Changes
tab that lists every change by day, and two map views on the canvas menu.
A page whose import read neither shows none of it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from infragram.discovery import ImportOptions, blueprint
from infragram.exports import render_project_html

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="browser suite; set INFRAGRAM_RUN_BROWSER_TESTS=1",
)

SUB = "11111111-2222-3333-4444-555555555555"


def rid(kind: str, name: str) -> str:
    provider, _, rest = kind.partition("/")
    return f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/{provider}/{rest}/{name}"


def _estate(*, signals: bool = True) -> dict:
    def row(kind: str, name: str) -> dict:
        return {
            "id": rid(kind, name),
            "name": name,
            "type": kind,
            "resourceGroup": "rg-app",
            "subscriptionId": SUB,
            "location": "eastus2",
            "properties": {},
        }

    storage = rid("Microsoft.Storage/storageAccounts", "stprod")
    vault = rid("Microsoft.KeyVault/vaults", "kv-prod")
    estate = {
        "format": "infragram.azure-snapshot/1",
        "taken": "2026-10-30T09:00:00+00:00",
        "subscriptions": [{"id": SUB, "name": "Production", "state": "Enabled"}],
        "resourceGroups": [{"name": "rg-app", "subscriptionId": SUB}],
        "resources": [
            row("Microsoft.Storage/storageAccounts", "stprod"),
            row("Microsoft.KeyVault/vaults", "kv-prod"),
            row("Microsoft.Web/serverFarms", "plan-prod"),
        ],
    }
    if signals:
        estate["changes"] = [
            {
                "targetId": storage,
                "changeType": "Update",
                "changeTime": "2026-10-29T14:02:00Z",
                "changedBy": "alice@contoso.com",
                "clientType": "Azure Portal",
                "changes": {
                    "properties.networkAcls.defaultAction": {
                        "previousValue": "Deny",
                        "newValue": "Allow",
                    }
                },
            },
            {"targetId": vault, "changeType": "Create", "changeTime": "2026-10-18T08:00:00Z"},
            {
                "targetId": rid("Microsoft.Compute/disks", "disk-old"),
                "changeType": "Delete",
                "changeTime": "2026-10-27T08:00:00Z",
            },
        ]
        estate["findings"] = {
            "defender": [
                {
                    "resourceId": storage,
                    "title": "Storage account public access should be disallowed",
                    "severity": "High",
                },
                {
                    "resourceId": vault,
                    "title": "Key vaults should have deletion protection enabled",
                    "severity": "Medium",
                },
            ]
        }
    return estate


def _open(playwright, tmp_path: Path, estate: dict, width: int = 1440):
    from infragram.exports import render_timeout_ms

    plan, _ = blueprint(estate, ImportOptions(view="groups"))
    page_file = tmp_path / "estate.html"
    page_file.write_text(
        render_project_html(plan.to_project(), libraries="project"), encoding="utf-8", newline="\n"
    )
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": width, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(page_file.resolve().as_uri())
    page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
    if page.locator("[data-inventory-toggle]").get_attribute("aria-pressed") != "true":
        page.locator("[data-inventory-toggle]").click()
    page.wait_for_timeout(300)  # the drawer eases to its height
    return browser, page, errors


def _row(page, name: str):
    """The row named *name*, not one whose group or links say it."""
    named = page.locator(".resource-name strong", has_text=re.compile(f"^{re.escape(name)}$"))
    return page.locator("[data-resource-rows] [data-resource-row]").filter(has=named).first


def test_findings_and_changes_are_listed_filtered_and_detailed(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser, page, errors = _open(playwright, tmp_path, _estate())
        try:
            columns = page.locator("[data-bottom-panel=resources]").get_attribute("data-columns")
            assert "findings" in columns.split() and "changed" in columns.split()
            storage = _row(page, "stprod")
            assert storage.locator('[data-col="findings"]').inner_text() == "1 high"
            assert storage.locator('[data-col="changed"]').inner_text() == "Updated Oct 29"
            assert _row(page, "plan-prod").locator('[data-col="findings"]').inner_text() == ""
            # the deleted disk has no card: its resource group has the row
            assert _row(page, "rg-app").get_attribute("data-resource-kind") == "boundary"

            # sorted worst first, the high finding leads
            page.locator('[data-resource-sort="findings"]').click()
            first = page.locator("[data-resource-rows] [data-resource-row]").first
            assert "stprod" in first.inner_text()

            # filters: what has findings; what changed in the week before the read
            page.locator("[data-resource-filters-toggle]").click()
            findings = page.locator('[data-resource-only="findings"]')
            changed = page.locator('[data-resource-only="changed"]')
            assert findings.is_visible() and changed.is_visible()
            assert findings.locator(".filter-count").inner_text() == "2"
            assert changed.locator(".filter-count").inner_text() == "2"
            changed.click()
            shown = page.locator("[data-resource-rows] [data-resource-row]").all_inner_texts()
            assert len(shown) == 2 and any("stprod" in text for text in shown)
            assert not any("kv-prod" in text for text in shown), "created 12 days before the read"
            changed.click()
            page.keyboard.press("Escape")

            # the details: each finding, and the change with who made it
            storage.click()
            strip = page.locator("[data-resource-selected]")
            text = strip.inner_text()
            assert "Storage account public access should be disallowed" in text
            assert "networkAcls.defaultAction: Deny → Allow" in text
            assert "alice@contoso.com · Azure Portal" in text
            assert errors == []
        finally:
            browser.close()


def test_the_changes_tab_lists_by_day_and_picks_the_card(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser, page, errors = _open(playwright, tmp_path, _estate())
        try:
            tab = page.locator('[data-resource-view="changes"]')
            assert tab.is_visible()
            tab.click()
            view = page.locator("[data-resource-changes]")
            assert view.is_visible() and page.locator("[data-resource-wrap]").is_hidden()
            days = view.locator(".resource-group-row").all_inner_texts()
            assert [day.split()[0].rstrip(",") for day in days] == ["Thu", "Tue", "Sun"]
            rows = view.locator("[data-change-row]")
            assert rows.count() == 3
            assert "Updated stprod" in rows.nth(0).inner_text()
            assert "Deleted disk-old" in rows.nth(1).inner_text()
            assert "on rg-app" in rows.nth(1).inner_text()
            rows.nth(0).click()
            node = page.locator('[data-graph-node][aria-label="stprod"]')
            assert node.get_attribute("data-selected") == "true"
            assert errors == []
        finally:
            browser.close()


def test_the_map_lights_what_has_findings(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser, page, errors = _open(playwright, tmp_path, _estate())
        try:
            box = page.locator("[data-infragram-diagram]").bounding_box()
            page.mouse.click(box["x"] + 6, box["y"] + 6, button="right")
            entry = page.locator('[data-context-action="lens-findings"]')
            assert entry.is_visible()
            assert page.locator('[data-context-action="lens-changes"]').is_visible()
            entry.click()
            lit = page.evaluate(
                "[...document.querySelectorAll('[data-graph-node]')]"
                ".filter(node => node.dataset.focusDimmed === 'false')"
                ".map(node => node.getAttribute('aria-label')).sort()"
            )
            assert lit == ["kv-prod", "stprod"]
            dimmed = page.locator('[data-graph-node][aria-label="plan-prod"]')
            assert dimmed.get_attribute("data-focus-dimmed") == "true"
            assert errors == []
        finally:
            browser.close()


def test_a_page_without_them_shows_none_of_it(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser, page, errors = _open(playwright, tmp_path, _estate(signals=False))
        try:
            columns = page.locator("[data-bottom-panel=resources]").get_attribute("data-columns")
            assert "findings" not in columns.split() and "changed" not in columns.split()
            assert page.locator('[data-resource-view="changes"]').is_hidden()
            page.locator("[data-resource-filters-toggle]").click()
            assert page.locator('[data-resource-only="findings"]').is_hidden()
            assert page.locator('[data-resource-only="changed"]').is_hidden()
            page.keyboard.press("Escape")
            box = page.locator("[data-infragram-diagram]").bounding_box()
            page.mouse.click(box["x"] + 6, box["y"] + 6, button="right")
            assert page.locator('[data-context-action="lens-findings"]').is_hidden()
            assert page.locator('[data-context-action="lens-changes"]').is_hidden()
            assert errors == []
        finally:
            browser.close()


def test_on_a_phone_open_details_gives_them_room_and_hide_gives_it_back(tmp_path: Path) -> None:
    """Under the map on a phone the sheet over the table is short. Opened
    there, the details showed a line at a time and read as nothing
    happening, so Open details makes the sheet as tall as they need, up to
    the whole table, and Hide details puts it back as it was."""
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser, page, errors = _open(playwright, tmp_path, _estate(), width=412)
        try:
            for name in ("stprod", "kv-prod"):
                _row(page, name).click()
                strip = page.locator("[data-resource-selected]")
                before = strip.bounding_box()["height"]
                page.locator("[data-selected-details]").click()
                page.wait_for_timeout(200)
                more = page.locator("[data-selected-more]").bounding_box()
                box = strip.bounding_box()
                assert box["height"] > before + 40, "the sheet grows"
                assert box["y"] + box["height"] - more["y"] >= 120, "the details have room"
                page.locator("[data-selected-details]").click()
                page.wait_for_timeout(200)
                assert page.locator("[data-selected-more]").count() == 0
                assert abs(strip.bounding_box()["height"] - before) <= 2, "and gives it back"
                page.locator("[data-selected-close]").click()
            assert errors == []
        finally:
            browser.close()
