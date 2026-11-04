"""The Unused tag is one picture in both renderers.

A resource the estate keeps without using carries the tag in its card's
top-right corner. The Python renderer and the editor draw it from the same
numbers (render-metrics.json ``flag``); this holds them to one picture in
both looks, and holds the exported SVG to the checker.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from infragram.cli.user.checker import checker
from infragram.discovery import ImportOptions, blueprint
from infragram.exports import extract_svg, playwright_svg_renderer, render_project_html
from infragram.exports.render import look_variant

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="browser suite; set INFRAGRAM_RUN_BROWSER_TESTS=1",
)

SUB = "11111111-2222-3333-4444-555555555555"
_FLAG = re.compile(
    r'<g data-unused-flag="true">.*?<rect x="([-\d.e]+)" y="([-\d.e]+)" width="([-\d.e]+)" '
    r'height="([-\d.e]+)".*?<text x="([-\d.e]+)" y="([-\d.e]+)"[^>]*>([^<]*)</text></g>',
    re.S,
)
_NODE = re.compile(r'<g data-graph-node[^>]*transform="translate\(([-\d.e]+)[ ,]([-\d.e]+)\)')


def _estate() -> dict:
    def rid(kind: str, name: str) -> str:
        provider, _, rest = kind.partition("/")
        return f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/{provider}/{rest}/{name}"

    def row(kind: str, name: str, properties: dict) -> dict:
        return {
            "id": rid(kind, name),
            "name": name,
            "type": kind,
            "resourceGroup": "rg-app",
            "subscriptionId": SUB,
            "location": "eastus2",
            "properties": properties,
        }

    return {
        "format": "infragram.azure-snapshot/1",
        "taken": "2026-10-27T12:00:00+00:00",
        "subscriptions": [{"id": SUB, "name": "Production", "state": "Enabled"}],
        "resourceGroups": [{"name": "rg-app", "subscriptionId": SUB}],
        "resources": [
            row("Microsoft.Compute/disks", "disk-old", {"diskState": "Unattached"}),
            row("Microsoft.Web/serverFarms", "plan-idle", {"numberOfSites": 0}),
            row("Microsoft.Web/serverFarms", "plan-busy", {"numberOfSites": 3}),
        ],
    }


def _flags_static(svg: str) -> list[tuple]:
    return sorted(
        (
            round(float(x), 2),
            round(float(y), 2),
            float(w),
            float(h),
            round(float(tx), 2),
            round(float(ty), 2),
            text,
        )
        for x, y, w, h, tx, ty, text in _FLAG.findall(svg)
    )


def _flags_editor(svg: str) -> list[tuple]:
    """The editor draws each tag inside its card's group, translated to the card."""
    found = []
    for node in re.split(r"(?=<g data-graph-node)", svg)[1:]:
        at = _NODE.match(node)
        if at is None:
            continue
        dx, dy = float(at.group(1)), float(at.group(2))
        for x, y, w, h, tx, ty, text in _FLAG.findall(node):
            found.append(
                (
                    round(float(x) + dx, 2),
                    round(float(y) + dy, 2),
                    float(w),
                    float(h),
                    round(float(tx) + dx, 2),
                    round(float(ty) + dy, 2),
                    text,
                )
            )
    return sorted(found)


@pytest.mark.parametrize("look", ["icon", "card"])
def test_the_unused_tag_draws_the_same_in_both_renderers(look: str, tmp_path: Path) -> None:
    plan, _ = blueprint(_estate(), ImportOptions(view="groups"))
    project = look_variant(plan.to_project(), look)
    html = render_project_html(project)
    page = tmp_path / "estate.html"
    page.write_text(html, encoding="utf-8", newline="\n")
    out = tmp_path / "estate.svg"
    playwright_svg_renderer(page, out, theme="light", display=None)
    static, editor = extract_svg(html), out.read_text(encoding="utf-8")

    drawn = _flags_static(static)
    assert [flag[-1] for flag in drawn] == ["Unused", "Unused"]
    assert _flags_editor(editor) == drawn
    errors: list[str] = []
    checker().check_svg(editor, errors, project.model_dump(mode="json"))
    assert not errors, errors


def _vm_estate() -> dict:
    def rid(kind: str, name: str) -> str:
        provider, _, rest = kind.partition("/")
        return f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/{provider}/{rest}/{name}"

    def row(kind: str, name: str, properties: dict, **extra) -> dict:
        return {
            "id": rid(kind, name),
            "name": name,
            "type": kind,
            "resourceGroup": "rg-app",
            "subscriptionId": SUB,
            "location": "eastus2",
            "properties": properties,
            **extra,
        }

    vm = "Microsoft.Compute/virtualMachines"
    nic = "Microsoft.Network/networkInterfaces"
    config = rid(nic, "nic-web") + "/ipConfigurations/ip1"
    estate = _estate()
    estate["resources"] = [
        row(vm, "vm-web", {"networkProfile": {"networkInterfaces": [{"id": rid(nic, "nic-web")}]}}),
        row(
            nic,
            "nic-web",
            {
                "ipConfigurations": [
                    {"id": config, "properties": {"privateIPAddress": "10.1.1.4"}}
                ],
                "virtualMachine": {"id": rid(vm, "vm-web")},
            },
        ),
        row(
            "Microsoft.Compute/disks",
            "vm-web_OsDisk",
            {"diskState": "Attached", "osType": "Linux", "diskSizeGB": 128},
            managedBy=rid(vm, "vm-web"),
        ),
        row(
            "Microsoft.Network/publicIPAddresses",
            "pip-web",
            {"publicIPAllocationMethod": "Static", "ipConfiguration": {"id": config}},
        ),
    ]
    return estate


def test_a_vms_attached_parts_expand_and_collapse_on_the_canvas(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms

    plan, _ = blueprint(_vm_estate(), ImportOptions(view="groups"))
    page_file = tmp_path / "vm.html"
    page_file.write_text(
        render_project_html(plan.to_project(), libraries="project"), encoding="utf-8", newline="\n"
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(page_file.resolve().as_uri())
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate("window.infragramEditor.failed || null") is None
            page.evaluate("() => window.infragramEditor.whenSettled()")
            state = "window.infragramEditor.getState()"
            vm = page.evaluate(f"() => {state}.nodes.find(n => n.name === 'vm-web').id")
            # the parts are plumbing: not on the map until asked for
            assert page.evaluate(f"() => {state}.nodes.length") == 1
            # an inventory opens in review; Edit brings the popup back on select
            assert page.evaluate("document.body.classList.contains('review-mode')")
            page.locator("[data-edit-mode]").click()
            page.evaluate("() => window.infragramEditor.whenSettled()")
            page.wait_for_timeout(300)

            card = page.locator(f'[data-graph-node][data-node-id="{vm}"]').bounding_box()
            assert card is not None
            page.mouse.click(card["x"] + card["width"] / 2, card["y"] + card["height"] / 2)
            popup = page.locator("[data-canvas-popup] [data-popup-attached]")
            assert "Attached (3)" in popup.inner_text()
            page.locator("[data-popup-parts]").click()
            parts = page.evaluate(
                f"() => {state}.nodes.filter(n => n.attributes?.partOf === '{vm}')"
                ".map(n => [n.name, n.attributes.role])"
            )
            assert sorted(parts) == [
                ["nic-web", "NIC"],
                ["pip-web", "public IP"],
                ["vm-web_OsDisk", "OS disk"],
            ]
            wires = page.evaluate(
                f"() => {state}.edges.filter(e => e.target === '{vm}').map(e => [e.kind, e.label])"
            )
            assert sorted(wires) == [
                ["dashed", "NIC"],
                ["dashed", "OS disk"],
                ["dashed", "public IP"],
            ]
            assert page.locator("[data-popup-parts]").get_attribute("aria-pressed") == "true"

            # a part says what carries it, and leads back to it
            nic = page.evaluate(f"() => {state}.nodes.find(n => n.name === 'nic-web').id")
            box = page.locator(f'[data-graph-node][data-node-id="{nic}"]').bounding_box()
            assert box is not None
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.locator("[data-popup-owner]").click()
            assert page.locator("[data-popup-parts]").get_attribute("aria-pressed") == "true"

            page.locator("[data-popup-parts]").click()
            assert page.evaluate(f"() => {state}.nodes.length") == 1
            assert page.evaluate(f"() => {state}.edges.length") == 0
        finally:
            browser.close()


def test_the_resources_table_filters_sorts_and_downloads(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms
    from infragram.pricing import price_project

    plan, _ = blueprint(_estate(), ImportOptions(view="groups"))
    project = plan.to_project()
    price_project(project)
    page_file = tmp_path / "estate.html"
    page_file.write_text(
        render_project_html(project, libraries="project"), encoding="utf-8", newline="\n"
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            page.goto(page_file.resolve().as_uri())
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate("window.infragramEditor.failed || null") is None
            # docked under the map, where every column shows
            page.locator('[data-dock-side="bottom"]').click()
            rows = page.locator("[data-resource-row]")
            # three cards; the resource group is in use, so it is no row of its own
            assert rows.count() == 3
            # most costly first
            names = rows.locator("td:first-child strong").all_inner_texts()
            assert names[0] in ("plan-idle", "plan-busy")
            page.locator("[data-resource-filters-toggle]").click()
            page.locator('[data-resource-only="unused"]').click()
            page.keyboard.press("Escape")
            assert sorted(rows.locator("td:first-child strong").all_inner_texts()) == [
                "disk-old",
                "plan-idle",
            ]
            assert "2 unused" in page.locator("[data-resource-summary]").inner_text()
            page.locator("[data-resource-search]").fill("disk")
            assert rows.locator("td:first-child strong").all_inner_texts() == ["disk-old"]
            with page.expect_download() as download:
                page.locator("[data-resource-csv]").click()
            raw = Path(download.value.path()).read_bytes()
            assert raw.startswith(b"\xef\xbb\xbf"), "a spreadsheet reads it as UTF-8"
            lines = raw.decode("utf-8-sig").strip().splitlines()
            assert lines[0].startswith("Name,Type,Resource group")
            assert (
                len(lines) == 2
                and lines[1].startswith("disk-old,")
                and "unattached-disk" in lines[1]
            )
            rows.first.click()
            selected = page.evaluate("() => window.infragramEditor.getState()")
            assert selected is not None
            assert page.locator('[data-graph-node][data-selected="true"]').count() == 1
        finally:
            browser.close()


def test_the_savings_view_ranks_the_actions_and_downloads(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms
    from infragram.pricing import price_project

    plan, _ = blueprint(_estate(), ImportOptions(view="groups"))
    project = plan.to_project()
    price_project(project)
    page_file = tmp_path / "savings.html"
    page_file.write_text(
        render_project_html(project, libraries="project"), encoding="utf-8", newline="\n"
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            page.goto(page_file.resolve().as_uri())
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate("window.infragramEditor.failed || null") is None
            page.locator('[data-dock-side="bottom"]').click()
            page.locator('[data-resource-view="savings"]').click()
            savings = page.locator("[data-resource-savings]")
            assert savings.is_visible()
            # the two unused resources, each as the action that removes it
            rows = savings.locator("[data-saving-row]")
            assert rows.count() == 2
            actions = rows.locator("td:first-child strong").all_inner_texts()
            assert sorted(actions) == ["Delete or scale in the plan", "Delete the disk"]
            with page.expect_download() as download:
                savings.locator("[data-savings-csv]").click()
            lines = Path(download.value.path()).read_text(encoding="utf-8-sig").strip().splitlines()
            assert lines[0].startswith("Action,Resource,Type,Resource group,Why,Saves a month")
            # most saved first, in the page and the file alike
            assert [line.split(",")[0] for line in lines[1:]] == actions
            # a row picks its card on the map
            rows.first.click()
            assert page.locator('[data-graph-node][data-selected="true"]').count() == 1
            # the view is remembered
            page.reload()
            page.wait_for_function("window.infragramEditor")
            assert page.locator("[data-resource-savings]").is_visible()
        finally:
            browser.close()


def test_an_app_and_the_plan_it_runs_on_name_and_pick_each_other(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms

    estate = _estate()
    plan_id = next(r["id"] for r in estate["resources"] if r["name"] == "plan-busy")
    estate["resources"].append(
        {
            "id": plan_id.replace("serverFarms/plan-busy", "sites/app-busy"),
            "name": "app-busy",
            "type": "Microsoft.Web/sites",
            "resourceGroup": "rg-app",
            "subscriptionId": SUB,
            "location": "eastus2",
            "properties": {"serverFarmId": plan_id},
        }
    )
    plan, _ = blueprint(estate, ImportOptions(view="groups"))
    page_file = tmp_path / "runs-on.html"
    page_file.write_text(
        render_project_html(plan.to_project(), libraries="project"), encoding="utf-8", newline="\n"
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(page_file.resolve().as_uri())
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate("window.infragramEditor.failed || null") is None
            # one wire on the map, said in words
            edges = page.evaluate("() => window.infragramEditor.getState().edges")
            assert [(e["source"], e["target"], e.get("label")) for e in edges] == [
                ("app-busy", "plan-busy", "runs on")
            ]
            page.locator('[data-dock-side="bottom"]').click()
            drawer = page.locator("[data-bottom-drawer]")
            page.evaluate(
                """() => { const g = document.querySelector('[data-bottom-drawer] [data-resource-groupby]');
                g.value = 'tied'; g.dispatchEvent(new Event('change', {bubbles: true})); }"""
            )
            groups = drawer.locator(".resource-group-row").all_inner_texts()
            assert any(group.startswith("Tied to plan-busy") for group in groups)
            # the app says what it runs on and who bills it; its plan's name picks the plan
            drawer.locator('[data-resource-row="app-busy"]').click()
            strip = page.locator("[data-resource-selected]")
            assert "Runs on\nplan-busy" in strip.inner_text()
            assert "Billed through plan-busy" in strip.inner_text()
            strip.locator('[data-pick-resource="plan-busy"]').first.click()
            assert (
                drawer.locator('[data-resource-row="plan-busy"]').get_attribute("data-selected")
                == "true"
            )
            assert "Hosts\napp-busy" in strip.inner_text()
        finally:
            browser.close()


def test_the_inventory_docks_beside_or_under_the_map_and_remembers(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms

    plan, _ = blueprint(_vm_estate(), ImportOptions(view="groups"))
    page_file = tmp_path / "dock.html"
    page_file.write_text(
        render_project_html(plan.to_project(), libraries="project"), encoding="utf-8", newline="\n"
    )
    body = "document.body"
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(page_file.resolve().as_uri())
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate("window.infragramEditor.failed || null") is None
            # wide screen, an inventory: docked beside the map, in review
            assert page.evaluate(f"{body}.dataset.dock") == "right"
            assert page.evaluate(f"{body}.classList.contains('review-mode')")
            assert page.locator("[data-resource-dock] [data-resource-row]").count() == 1
            assert page.locator("[data-resource-summary]").inner_text().startswith("1 resource")

            # selecting the card brings its row and the selected strip, no popup
            vm = page.evaluate("() => window.infragramEditor.getState().nodes[0].id")
            box = page.locator(f'[data-graph-node][data-node-id="{vm}"]').bounding_box()
            assert box is not None
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            assert page.locator("[data-canvas-popup]").is_hidden()
            assert (
                page.locator(f'[data-resource-row="{vm}"]').get_attribute("data-selected") == "true"
            )
            strip = page.locator("[data-resource-selected]")
            assert "vm-web" in strip.inner_text()
            strip.locator("[data-selected-parts]").click()
            assert (
                page.evaluate(
                    "() => window.infragramEditor.getState().nodes.filter(n => n.attributes?.partOf).length"
                )
                == 3
            )

            # another drawer tab leaves the table beside the map where it is
            page.evaluate("document.querySelector('[data-bottom-tab=\"examples\"]').click()")
            assert page.locator("[data-resource-dock] [data-resource-row]").first.is_visible()
            # and while a dialog is open, "/" is the dialog's, not the search's
            page.keyboard.press("?")
            page.locator("[data-shortcut-sheet]").wait_for(state="visible")
            page.keyboard.press("/")
            assert not page.evaluate(
                "document.activeElement?.matches('[data-resource-search]') || false"
            )
            page.keyboard.press("Escape")
            page.locator("[data-shortcut-sheet]").wait_for(state="hidden")
            page.keyboard.press("/")
            assert page.evaluate("document.activeElement?.matches('[data-resource-search]')")
            page.keyboard.press("Escape")

            # the divider, by keyboard; then under the map; then the table alone
            before = page.evaluate(f"getComputedStyle({body}).getPropertyValue('--dock-right')")
            page.locator('[data-dock-divider="right"]').focus()
            page.keyboard.press("ArrowLeft")
            after = page.evaluate(f"getComputedStyle({body}).getPropertyValue('--dock-right')")
            assert (
                int(after.strip().removesuffix("px")) == int(before.strip().removesuffix("px")) + 24
            )
            page.locator('[data-dock-side="bottom"]').click()
            assert page.evaluate(f"{body}.dataset.dock") == "bottom"
            assert page.locator("[data-bottom-drawer] [data-resource-row]").count() >= 1
            assert page.locator("[data-resource-dock]").is_hidden()
            page.locator('[data-dock-mode="table"]').click()
            assert page.locator(".editor-workbench").is_hidden()
            assert page.locator("[data-bottom-drawer] [data-resource-row]").first.is_visible()
            # one switch of three: the table alone is pressed instead of the side
            assert (
                page.locator('[data-dock-side="bottom"]').get_attribute("aria-pressed") == "false"
            )
            page.locator('[data-dock-side="bottom"]').click()
            assert page.locator(".editor-workbench").is_visible()
            assert page.locator('[data-dock-mode="table"]').get_attribute("aria-pressed") == "false"

            # Edit leaves review; all of it is remembered
            page.locator("[data-edit-mode]").click()
            assert not page.evaluate(f"{body}.classList.contains('review-mode')")
            page.reload()
            page.wait_for_function("window.infragramEditor")
            assert page.evaluate(f"{body}.dataset.dock") == "bottom"
            assert page.evaluate(f"{body}.dataset.dockMode") == "split"
            assert not page.evaluate(f"{body}.classList.contains('review-mode')")
            page.locator("[data-dock-close]").click()
            assert page.evaluate(f"{body}.dataset.dock || ''") == ""
            assert page.locator("[data-inventory-toggle]").get_attribute("aria-pressed") == "false"
        finally:
            browser.close()


def test_the_table_shows_one_line_rows_and_keeps_a_column_choice_per_dock(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms

    estate = _estate()
    # a resource group that holds nothing: a row of its own, counted apart
    estate["resourceGroups"].append({"name": "rg-old", "subscriptionId": SUB})
    plan, _ = blueprint(estate, ImportOptions(view="groups"))
    page_file = tmp_path / "columns.html"
    page_file.write_text(
        render_project_html(plan.to_project(), libraries="project"), encoding="utf-8", newline="\n"
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(page_file.resolve().as_uri())
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate("window.infragramEditor.failed || null") is None
            page.locator('[data-dock-side="bottom"]').click()
            page.locator('[data-dock-mode="table"]').click()
            drawer = page.locator("[data-bottom-drawer]")
            rows = drawer.locator("[data-resource-row]")
            # three resources and the empty group: four rows, and the count says which is which
            assert rows.count() == 4
            summary = drawer.locator("[data-resource-summary]").inner_text()
            assert summary.startswith("3 resources · 1 empty group")
            # one line a row, and every column while there is room for it
            heights = rows.evaluate_all(
                "rows => rows.map(row => row.getBoundingClientRect().height)"
            )
            assert max(heights) <= 37
            assert drawer.locator("thead th:visible").all_inner_texts() == [
                "Name",
                "Type",
                "Group",
                "Location",
                "Attached",
                "A month",
                "Unused",
                "Tags",
            ]

            # Display: Tags ticked off, and still off after a reload
            drawer.locator("[data-resource-display-toggle]").click()
            drawer.locator('[data-column="tags"]').click()
            page.keyboard.press("Escape")
            assert drawer.locator("[data-resource-display-panel]").is_hidden()
            assert drawer.locator('thead th[data-col="tags"]').is_hidden()
            page.reload()
            page.wait_for_function("window.infragramEditor")
            assert drawer.locator('thead th[data-col="tags"]').is_hidden()
            assert drawer.locator('thead th[data-col="type"]').is_visible()

            # a picked row opens its details beside the table; no row moves
            before = rows.evaluate_all("rows => rows.map(row => row.getBoundingClientRect().top)")
            rows.nth(1).click()
            assert drawer.locator("[data-resource-selected]").is_visible()
            after = rows.evaluate_all("rows => rows.map(row => row.getBoundingClientRect().top)")
            assert after == before

            # beside the map the table has its own choice: the narrow default,
            # the cost and status first after the name, the rest scrolling in
            # sideways under the frozen name; the page itself does not scroll
            page.locator('[data-dock-side="right"]').click()
            dock = page.locator("[data-resource-dock]")
            heads = dock.locator("[data-resource-table] thead th").evaluate_all(
                "ths => ths.filter(th => getComputedStyle(th).display !== 'none').map(th => th.dataset.col)"
            )
            assert heads == ["name", "monthly", "unused", "type", "group", "location"]
            cells = dock.locator("[data-resource-row]").first.evaluate(
                "row => [...row.children].filter(td => getComputedStyle(td).display !== 'none').map(td => td.dataset.col)"
            )
            assert cells == heads
            assert dock.locator("[data-resource-wrap]").evaluate(
                "w => w.scrollWidth > w.clientWidth"
            )
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
        finally:
            browser.close()


def test_on_a_phone_the_picked_row_stays_clear_of_its_details(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms

    estate = _estate()
    for index in range(12):
        estate["resources"].append(
            {
                "id": f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Compute/disks/disk-{index:02}",
                "name": f"disk-{index:02}",
                "type": "Microsoft.Compute/disks",
                "resourceGroup": "rg-app",
                "subscriptionId": SUB,
                "location": "eastus2",
                "properties": {"diskState": "Attached"},
            }
        )
    plan, _ = blueprint(estate, ImportOptions(view="groups"))
    page_file = tmp_path / "phone.html"
    page_file.write_text(
        render_project_html(plan.to_project(), libraries="project"), encoding="utf-8", newline="\n"
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": 412, "height": 780}, is_mobile=True, has_touch=True
            )
            page.goto(page_file.resolve().as_uri())
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate("window.infragramEditor.failed || null") is None
            if page.locator("[data-inventory-toggle]").get_attribute("aria-pressed") != "true":
                page.locator("[data-inventory-toggle]").click()
            page.locator('[data-dock-mode="table"]:visible').click()
            page.wait_for_timeout(300)  # the drawer eases to its height
            # the table alone: no editing bar over it, and it reaches the foot of the screen
            assert page.locator(".editor-header>.editor-toolbar").is_hidden()
            bottom = page.evaluate(
                "document.querySelector('.resource-panel').getBoundingClientRect().bottom"
            )
            assert bottom >= 780 - 12
            rows = page.locator("[data-resource-rows] [data-resource-row]")
            row = rows.nth(rows.count() - 2)
            row.scroll_into_view_if_needed()
            row.tap()
            sheet = page.locator("[data-resource-selected]")
            assert sheet.is_visible()
            page.wait_for_timeout(100)
            assert (
                row.bounding_box()["y"] + row.bounding_box()["height"] <= sheet.bounding_box()["y"]
            )
            # the browser's bar comes back: the sheet refits, the row stays clear of it
            page.set_viewport_size({"width": 412, "height": 720})
            page.wait_for_timeout(200)
            assert (
                row.bounding_box()["y"] + row.bounding_box()["height"] <= sheet.bounding_box()["y"]
            )
            assert sheet.bounding_box()["y"] + sheet.bounding_box()["height"] <= 720 + 1
            assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
        finally:
            browser.close()


def test_the_table_sorts_from_display_totals_and_clears_its_search(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms
    from infragram.pricing import price_project

    plan, _ = blueprint(_estate(), ImportOptions(view="groups"))
    project = plan.to_project()
    price_project(project)
    page_file = tmp_path / "sort.html"
    page_file.write_text(
        render_project_html(project, libraries="project"), encoding="utf-8", newline="\n"
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(page_file.resolve().as_uri())
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate("window.infragramEditor.failed || null") is None
            page.locator('[data-dock-side="bottom"]').click()
            drawer = page.locator("[data-bottom-drawer]")
            names = drawer.locator("[data-resource-row] td:first-child strong")

            # Display sorts by any column; choosing it again turns the order round
            drawer.locator("[data-resource-display-toggle]").click()
            drawer.locator('[data-sort-value="name"]').click()
            assert names.all_inner_texts() == ["disk-old", "plan-busy", "plan-idle"]
            assert "A to Z" in drawer.locator('[data-sort-value="name"]').inner_text()
            drawer.locator('[data-sort-value="name"]').click()
            assert names.all_inner_texts() == ["plan-idle", "plan-busy", "disk-old"]
            page.keyboard.press("Escape")

            # the totals row says what the rows cost; the count leaves the money to it
            total = drawer.locator("[data-foot-total]").inner_text()
            assert total.startswith("$")
            assert "$" not in drawer.locator("[data-resource-summary]").inner_text()

            # / goes to the search; its cross and the count's Clear empty it
            page.mouse.click(800, 300)
            page.keyboard.press("/")
            page.keyboard.type("disk")
            assert names.all_inner_texts() == ["disk-old"]
            assert drawer.locator("[data-resource-search-clear]").is_visible()
            assert drawer.locator("[data-foot-total]").inner_text() != total
            drawer.locator("[data-resource-search-clear]").click()
            assert names.count() == 3
            assert drawer.locator("[data-resource-search-clear]").is_hidden()
            drawer.locator("[data-resource-search]").fill("plan")
            summary = drawer.locator("[data-resource-summary]")
            assert summary.inner_text().startswith("2 of 3 resources")
            summary.locator("[data-resource-clear-all]").click()
            assert names.count() == 3
            assert drawer.locator("[data-resource-search]").input_value() == ""
            assert summary.locator("[data-resource-clear-all]").count() == 0
        finally:
            browser.close()


def test_open_details_grows_the_details_column_and_keeps_the_map_clear(tmp_path: Path) -> None:
    """Under the map the inventory's details column is where a card's whole
    story goes: Open details lists its price worked out and its table there,
    under its name, rather than in a popup squeezed over the map; and a card
    picked on the map brings its row out from under the totals."""
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms

    estate = _estate()
    for index in range(12):
        estate["resources"].append(
            {
                "id": f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/Microsoft.Compute/disks/disk-{index:02}",
                "name": f"disk-{index:02}",
                "type": "Microsoft.Compute/disks",
                "resourceGroup": "rg-app",
                "subscriptionId": SUB,
                "location": "eastus2",
                "properties": {"diskState": "Attached"},
            }
        )
    plan, _ = blueprint(estate, ImportOptions(view="groups"))
    page_file = tmp_path / "details.html"
    page_file.write_text(
        render_project_html(plan.to_project(), libraries="project"), encoding="utf-8", newline="\n"
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 840, "height": 900})
            page.goto(page_file.resolve().as_uri())
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate("window.infragramEditor.failed || null") is None
            if page.locator("[data-inventory-toggle]").get_attribute("aria-pressed") != "true":
                page.locator("[data-inventory-toggle]").click()
            page.wait_for_timeout(300)  # the drawer eases to its height
            # the last row, picked on the map, is brought out from under the totals
            name = page.locator("[data-resource-rows] [data-resource-row]").last.get_attribute(
                "data-resource-row"
            )
            page.locator(f'[data-graph-node][data-node-id="{name}"]').click()
            page.wait_for_timeout(100)
            row = page.locator(f'[data-resource-rows] [data-resource-row="{name}"]').bounding_box()
            totals = page.locator("[data-resource-foot] td").first.bounding_box()
            assert row["y"] + row["height"] <= totals["y"] + 1

            page.locator(
                '[data-resource-rows] [data-resource-row]:not([data-resource-kind="boundary"])'
            ).first.click()
            details = page.locator("[data-selected-details]")
            assert details.get_attribute("aria-expanded") == "false"
            details.click()
            more = page.locator("[data-selected-more]")
            assert more.is_visible() and details.inner_text() == "Hide details"
            # what the popup held: the card's own table, where to read about it
            assert more.locator(
                "[data-popup-table], [data-popup-price], [data-popup-links]"
            ).count()
            assert page.locator("[data-canvas-popup]").is_hidden(), "nothing covers the map"
            head = page.locator(".resource-selected-head").bounding_box()
            assert more.bounding_box()["y"] >= head["y"] + head["height"], "the name stays on top"
            details.click()
            assert page.locator("[data-selected-more]").count() == 0
        finally:
            browser.close()


def test_on_a_phone_the_details_sheet_steps_between_its_sizes(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms

    plan, _ = blueprint(_vm_estate(), ImportOptions(view="groups"))
    page_file = tmp_path / "sheet.html"
    page_file.write_text(
        render_project_html(plan.to_project(), libraries="project"), encoding="utf-8", newline="\n"
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": 412, "height": 780}, is_mobile=True, has_touch=True
            )
            page.goto(page_file.resolve().as_uri())
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate("window.infragramEditor.failed || null") is None
            if page.locator("[data-inventory-toggle]").get_attribute("aria-pressed") != "true":
                page.locator("[data-inventory-toggle]").click()
            page.wait_for_timeout(300)  # the drawer eases to its height
            page.locator("[data-resource-row]").first.tap()
            sheet = page.locator("[data-resource-selected]")
            handle = sheet.locator("[data-sheet-handle]")
            assert sheet.get_attribute("data-sheet") == "half"
            half = sheet.bounding_box()["height"]
            # pressed, it steps on; at a peek it shows the name and the handle only
            while sheet.get_attribute("data-sheet") != "peek":
                handle.click()
            assert sheet.bounding_box()["height"] < half
            assert sheet.locator("h3").is_visible()
            # the actions and facts lie below the peek's edge, out of sight
            peek_bottom = sheet.bounding_box()["y"] + sheet.bounding_box()["height"]
            assert (
                sheet.locator(".resource-selected-actions").bounding_box()["y"] >= peek_bottom - 1
            )
            # dragged up, it settles on a bigger size
            box = handle.bounding_box()
            x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            page.mouse.move(x, y)
            page.mouse.down()
            page.mouse.move(x, y - 260, steps=8)
            page.mouse.up()
            assert sheet.get_attribute("data-sheet") in ("half", "full")
            assert sheet.bounding_box()["height"] >= half - 1
            # the arrow keys too
            handle.focus()
            page.keyboard.press("ArrowDown")
            page.keyboard.press("ArrowDown")
            assert sheet.get_attribute("data-sheet") == "peek"

            # the name's row drags it too: up to grow it, down past the peek to close it
            def drag_name(by: float) -> None:
                name = sheet.locator("h3").bounding_box()
                x, y = name["x"] + 20, name["y"] + name["height"] / 2
                page.mouse.move(x, y)
                page.mouse.down()
                page.mouse.move(x, y + by / 2, steps=6)
                page.mouse.move(x, y + by, steps=6)
                page.mouse.up()

            drag_name(-260)
            assert sheet.get_attribute("data-sheet") in ("half", "full")
            drag_name(400)
            assert sheet.is_hidden()
            assert page.locator('[data-resource-row][data-selected="true"]').count() == 0
            # picked again, it opens at half
            page.locator("[data-resource-row]").first.tap()
            assert sheet.get_attribute("data-sheet") == "half"
        finally:
            browser.close()


def test_on_a_phone_the_inventory_and_the_inspector_take_turns(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms

    plan, _ = blueprint(_estate(), ImportOptions(view="groups"))
    page_file = tmp_path / "turns.html"
    page_file.write_text(
        render_project_html(plan.to_project(), libraries="project"), encoding="utf-8", newline="\n"
    )
    shown = """sel => { const e = document.querySelector(sel); const b = e && e.getBoundingClientRect();
      return Boolean(b && b.height && getComputedStyle(e).display !== 'none'); }"""
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": 412, "height": 780}, is_mobile=True, has_touch=True
            )
            page.goto(page_file.resolve().as_uri())
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate("window.infragramEditor.failed || null") is None
            page.locator("[data-inventory-toggle]").click()
            page.wait_for_timeout(300)  # the drawer eases to its height
            assert page.evaluate(shown, ".bottom-drawer")
            # Edit, out of review and back: the inventory keeps the sheet, and
            # the library's drawer stays shut
            for _ in range(2):
                page.locator("[data-edit-mode]").click()
            assert not page.evaluate(shown, ".right-inspector")
            assert page.evaluate(shown, ".bottom-drawer")
            assert page.evaluate("document.body.classList.contains('sidebar-collapsed')")
            # a card opened for editing takes the sheet; the inventory closes
            page.evaluate(
                """() => { const node = window.infragramEditor.getState().nodes[0];
                document.querySelector(`[data-graph-node][data-node-id="${node.id}"]`)
                  .dispatchEvent(new MouseEvent('dblclick', {bubbles: true})); }"""
            )
            page.wait_for_timeout(300)
            assert page.evaluate(shown, ".right-inspector")
            assert not page.evaluate(shown, ".bottom-drawer")
            assert page.locator("[data-inventory-toggle]").get_attribute("aria-pressed") == "false"
            # the inventory again: the inspector's sheet folds away
            page.locator("[data-inventory-toggle]").click()
            page.wait_for_timeout(300)
            assert page.evaluate(shown, ".bottom-drawer")
            assert not page.evaluate(shown, ".right-inspector")

            # a card tapped on the map: no info popup over the inventory, whose
            # sheet says what the card is, its row clear of the header and totals
            node = page.evaluate("() => window.infragramEditor.getState().nodes[1].id")
            card = page.locator(f'[data-graph-node][data-node-id="{node}"]').bounding_box()
            page.touchscreen.tap(card["x"] + card["width"] / 2, card["y"] + card["height"] / 2)
            page.wait_for_timeout(300)
            assert not page.evaluate(shown, "[data-canvas-popup]")
            assert page.evaluate(shown, "[data-resource-selected]")
            row = page.locator(f'[data-resource-rows] [data-resource-row="{node}"]').bounding_box()
            head = page.locator(".resource-panel thead th").first.bounding_box()
            foot = page.locator(".resource-panel tfoot td").first.bounding_box()
            assert row["y"] >= head["y"] + head["height"] - 1
            assert row["y"] + row["height"] <= foot["y"] + 1
        finally:
            browser.close()


def test_beside_the_map_on_a_1366_screen_the_inspector_stays_on_it(tmp_path: Path) -> None:
    """Editing with the table beside the map: the map, the table and the
    inspector asked for more than a 1366 px screen leaves after the library,
    so the inspector ran off its right edge and the page scrolled sideways;
    and the dock's switches covered the Savings tab. The map gives way."""
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms

    plan, _ = blueprint(_vm_estate(), ImportOptions(view="groups"))
    page_file = tmp_path / "narrow.html"
    page_file.write_text(
        render_project_html(plan.to_project(), libraries="project"), encoding="utf-8", newline="\n"
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1366, "height": 768})
            page.goto(page_file.resolve().as_uri() + "?fresh=narrow")
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            page.locator('[data-dock-side="right"]').click()
            page.locator("[data-edit-mode]").click()
            assert not page.evaluate("document.body.classList.contains('review-mode')")
            # the library open too, as a page that is not an inventory opens
            if page.evaluate("document.body.classList.contains('sidebar-collapsed')"):
                page.locator("[data-sidebar-logo-trigger]").click()
            if page.evaluate("document.body.classList.contains('inspector-collapsed')"):
                page.locator("[data-inspector-toggle]").click()
            assert page.evaluate(
                "!document.body.matches('.sidebar-collapsed, .inspector-collapsed')"
            )
            page.wait_for_timeout(300)
            box = page.evaluate(
                """() => {
                  const edge = selector => document.querySelector(selector).getBoundingClientRect();
                  return {
                    scroll: document.documentElement.scrollWidth - innerWidth,
                    inspector: edge('[data-right-inspector]').right,
                    map: edge('.canvas-pane').width,
                    savings: edge('.resource-dock [data-resource-view="savings"]').right,
                    switches: edge('.resource-dock .resource-dock-controls').left,
                  };
                }"""
            )
            assert box["scroll"] <= 0, box
            assert box["inspector"] <= 1366, box
            assert box["map"] >= 240, box
            assert box["savings"] <= box["switches"], box
        finally:
            browser.close()


def test_names_sort_naturally_formulas_stay_text_and_savings_pick_hidden_rows(
    tmp_path: Path,
) -> None:
    """vm-2 sorts before vm-10; a name a spreadsheet would run (=...) is
    written to the CSV as text; and a saving's row picks its resource even
    while the Resources search hides that row."""
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.exports import render_timeout_ms
    from infragram.pricing import price_project

    plan, _ = blueprint(_estate(), ImportOptions(view="groups"))
    project = plan.to_project()
    price_project(project)
    names = {"plan-busy": "vm-10", "plan-idle": "vm-2", "disk-old": "=disk-old"}
    for element in project.topology.walk():
        if element.name in names:
            element.name = names[element.name]
    page_file = tmp_path / "natural.html"
    page_file.write_text(
        render_project_html(project, libraries="project"), encoding="utf-8", newline="\n"
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            page.goto(page_file.resolve().as_uri() + "?fresh=natural")
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            page.locator('[data-dock-side="bottom"]').click()
            rows = page.locator("[data-resource-row]")
            page.locator('[data-resource-sort="name"]').click()
            shown = rows.locator("td:first-child strong").all_inner_texts()
            assert shown.index("vm-2") < shown.index("vm-10"), shown
            header = page.locator('th:has([data-resource-sort="name"])')
            assert header.get_attribute("aria-sort") == "ascending"
            with page.expect_download() as download:
                page.locator("[data-resource-csv]").click()
            raw = Path(download.value.path()).read_bytes()
            assert raw.startswith(b"\xef\xbb\xbf"), "a spreadsheet reads it as UTF-8"
            lines = raw.decode("utf-8-sig").splitlines()
            assert any(line.startswith("'=disk-old,") for line in lines), lines

            # the search hides the plan; its saving still picks it
            page.locator("[data-resource-search]").fill("disk")
            assert "vm-2" not in rows.locator("td:first-child strong").all_inner_texts()
            page.locator('[data-resource-view="savings"]').click()
            page.locator("[data-saving-row]", has_text="vm-2").click()
            picked = page.evaluate(
                "() => [...document.querySelectorAll('[data-graph-node][data-selected=\"true\"]')]"
                ".map(node => node.getAttribute('aria-label'))"
            )
            assert picked == ["vm-2"], picked
            assert (
                page.locator("[data-saving-row]", has_text="vm-2").get_attribute("data-selected")
                == "true"
            )
        finally:
            browser.close()
