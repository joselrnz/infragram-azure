"""The full editor/export feature set works with Azure frames and badges.

These checks exercise user input and downloaded files. Root-level browser jobs
run them sequentially, including the touch context, against a self-contained page.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from xml.etree import ElementTree

import pytest

from infragram.author import Diagram, Edge
from infragram.exports import export_project, render_project_html, render_timeout_ms
from infragram.exports.carry import carried_document, page_document
from infragram.nodes import _scope, azure, reset_ids
from infragram.nodes.frames import azure as frames
from infragram.pricing import price_project
from infragram.projects import CloudProject

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run Chromium feature parity checks",
)


def _source(tmp_path: Path, *, priced: bool = False, libraries: str = "project") -> Path:
    _scope.reset()
    reset_ids()
    with Diagram(
        "Azure feature parity", "Azure subnet services", slug="azure-parity", providers=("azure",)
    ) as diagram:
        with frames.VNet("vnet-app").row():
            with (
                frames.PublicSubnet("snet-web")
                .badge(azure.NetworkSecurityGroups, label="NSG · nsg-web")
                .badge(azure.NAT, side="edge", label="nat-web")
            ):
                web = azure.VirtualMachine("vm-web")
            with frames.Subnet("snet-data"):
                database = azure.SQLDatabase("sql-data")
        web >> Edge("SQL") >> database
    project = diagram.to_project()
    if priced:
        machine = project.topology.first(name="vm-web")
        assert machine is not None
        machine.attributes["sizing"] = {
            "size": "Standard_D2s_v5",
            "region": "eastus",
            "os": "Linux",
            "hours": 730,
        }
        prices = price_project(project, source="table", today="2026-10-15")
        assert prices.monthly > 0 and machine.attributes.get("price"), prices.notes
    source = tmp_path / "azure-parity.html"
    source.write_text(render_project_html(project, libraries=libraries), encoding="utf-8")
    return source


def _open(page, source: Path) -> None:
    page.goto(source.resolve().as_uri())
    page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
    assert page.evaluate("window.infragramEditor.failed || null") is None
    page.evaluate("() => window.infragramEditor.whenSettled()")


def _web(page) -> str:
    return page.evaluate(
        "() => window.infragramEditor.getState().nodes.find(node => node.name === 'vm-web').id"
    )


def _centre(page, selector: str) -> tuple[float, float]:
    box = page.locator(selector).bounding_box()
    assert box is not None, selector
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _selected(page) -> list[str]:
    return page.locator('[data-graph-node][data-selected="true"]').evaluate_all(
        "nodes => nodes.map(node => node.dataset.nodeId)"
    )


def test_azure_editing_downloads_and_embedded_documents(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = _source(tmp_path)
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            _open(page, source)
            web = _web(page)
            selector = f'[data-graph-node][data-node-id="{web}"]'
            assert page.locator("[data-boundary-edge-bar]").count() == 1
            assert page.locator("[data-graph-boundary] image[data-frame-badge]").count() == 2
            page.mouse.click(*_centre(page, selector))
            assert _selected(page) == []
            assert page.locator('[data-graph-edge][data-focus-edge="true"]').count() == 1
            page.mouse.dblclick(*_centre(page, selector))
            assert _selected(page) == [web]
            page.mouse.dblclick(*_centre(page, selector))
            name = page.locator('[data-content-control="name"]')
            name.fill("vm-web-edited")
            name.press("Tab")
            page.wait_for_function(
                "id => window.infragramEditor.getState().nodes.find(node => node.id === id).name === 'vm-web-edited'",
                arg=web,
            )
            project = CloudProject.model_validate(
                page.evaluate("() => window.infragramEditor.exportProject()")
            )
            saved_subnet = project.topology.first(name="snet-web")
            assert saved_subnet is not None
            assert {badge.side for badge in saved_subnet.badges} == {"corner", "edge"}
            html = page.evaluate("() => window.infragramEditor.exportHtml()")
            assert "vm-web-edited" in page_document(html)

            downloaded: dict[str, Path] = {}
            for kind in ("svg", "png", "drawio"):
                menu = page.locator("[data-download-menu]")
                if menu.get_attribute("open") is None:
                    menu.locator("summary").click()
                with page.expect_download() as event:
                    page.locator(f"[data-download-{kind}]").click()
                download = event.value
                assert download.failure() is None
                destination = tmp_path / download.suggested_filename
                download.save_as(destination)
                downloaded[kind] = destination
            svg = downloaded["svg"].read_text(encoding="utf-8")
            assert "vm-web-edited" in svg
            assert "data-node-port" not in svg
            assert "vm-web-edited" in downloaded["drawio"].read_text(encoding="utf-8")
            ElementTree.fromstring(svg)
            ElementTree.parse(downloaded["drawio"])
            assert downloaded["png"].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

            def capture_svg(_source, output, display=None):
                shutil.copyfile(downloaded["svg"], output)

            def capture_png(_source, output, scale, display=None):
                shutil.copyfile(downloaded["png"], output)

            result = export_project(
                project,
                tmp_path / "carried",
                formats=("svg", "png"),
                svg_renderer=capture_svg,
                png_renderer=capture_png,
            )
            for artifact in (result.svg, result.png):
                carried = carried_document(artifact)
                restored = CloudProject.model_validate(carried)
                assert restored.topology.first(name="vm-web-edited") is not None
                assert {
                    badge.side for badge in restored.topology.first(name="snet-web").badges
                } == {"corner", "edge"}
        finally:
            browser.close()


def test_azure_phone_tap_reads_flow_and_double_tap_selects(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = _source(tmp_path)
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
                device_scale_factor=1,
            )
            page = context.new_page()
            _open(page, source)
            web = _web(page)
            selector = f'[data-graph-node][data-node-id="{web}"]'
            x, y = _centre(page, selector)
            page.touchscreen.tap(x, y)
            page.wait_for_function(
                "document.querySelector('[data-graph-edge][data-focus-edge=\"true\"]')"
            )
            assert _selected(page) == []
            cdp = context.new_cdp_session(page)
            cdp.send(
                "Input.synthesizeTapGesture",
                {
                    "x": x,
                    "y": y,
                    "duration": 50,
                    "tapCount": 2,
                    "gestureSourceType": "touch",
                },
            )
            page.wait_for_function(
                'id => document.querySelector(`[data-graph-node][data-node-id="${id}"][data-selected="true"]`)',
                arg=web,
            )
            assert _selected(page) == [web]
            assert not page.locator("body").evaluate(
                "body => body.classList.contains('inspector-collapsed')"
            )
            assert page.evaluate("document.documentElement.scrollWidth") == 390
        finally:
            browser.close()


def test_azure_cost_rollup_and_3d_builder_use_the_ported_panels(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = _source(tmp_path, priced=True, libraries="all")
    payload = carried_document(source)
    assert payload is not None
    project = CloudProject.model_validate(payload)
    monthly = round(
        sum(
            float(element.attributes.get("price", {}).get("monthly", 0))
            for element in project.topology.walk()
        ),
        2,
    )
    assert monthly > 0
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            _open(page, source)
            page.locator('[data-inspector-tab="cost"]').click()
            panel = page.locator('[data-inspector-panel="cost"]')
            panel.wait_for(state="visible")
            assert panel.locator(".cost-total").inner_text() == f"≈ ${monthly:,.2f} a month"
            machine = panel.locator("[data-cost-item]", has_text="vm-web")
            machine.locator("summary").click()
            assert machine.locator("tr").count() >= 1
            assert panel.locator("[data-cost-frame]").count() >= 2

            page.locator('[data-bottom-tab="builder"]').click()
            assert page.evaluate("Boolean(window.iso3d && window.iso3d.recipes.includes('server'))")
            page.select_option("[data-iso-recipe]", "server")
            page.fill('[data-iso-knob="units"]', "3")
            page.fill('[data-iso-knob="drivesN"]', "12")
            page.fill("[data-iso-name]", "AZ-Server-3D")
            page.fill("[data-iso-detail]", "Azure appliance")
            page.locator("[data-iso-preview]").click()
            page.wait_for_function(
                "!document.querySelector('[data-iso-add]').disabled",
                timeout=render_timeout_ms(),
            )
            assert (
                page.locator("[data-iso-preview-image]")
                .get_attribute("src")
                .startswith("data:image/svg+xml")
            )
            page.locator("[data-iso-add]").click()
            node = page.locator('[data-graph-node][data-component-id="custom-3d"]')
            node.wait_for(state="visible")
            assert node.get_attribute("data-ink-edge")
            saved = CloudProject.model_validate(
                page.evaluate("() => window.infragramEditor.exportProject()")
            )
            appliance = saved.topology.first(name="AZ-Server-3D")
            assert appliance is not None
            assert appliance.attributes["iso"]["recipe"] == "server"
            assert appliance.attributes["iso"]["args"] == [3, 12]
            assert appliance.attributes["iso_artwork"].startswith("<svg")
        finally:
            browser.close()
