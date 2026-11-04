from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from infragram.catalog import (
    ARCHITECTURE_BOUNDARY_GROUPS,
    ARCHITECTURE_FRAME_PRESETS,
    load_default_provider_registry,
)
from infragram.editor import load_sidebar_catalog
from infragram.exports import playwright_png_renderer, render_project_html, render_timeout_ms
from infragram.projects import CloudProject

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run Chromium editor checks",
)

REGISTERED_LIBRARIES = len(load_default_provider_registry().providers)


def _settled(page) -> None:
    """The page is ready to be driven: loaded, and its editor runtime attached.

    A ``networkidle`` wait is the wrong condition for these pages -- nothing
    is fetched (the faces travel inline), and on a slow runner the runtime
    can attach after the network has gone quiet, so a click landed before
    the handlers were there. The editor object is set last, so it is the
    signal; the budget is the render budget."""
    page.wait_for_load_state("load")
    page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())


def _open_frame_group(page, group: str) -> None:
    """Open a frame gallery group; they all start closed."""
    details = page.locator(f'details.frame-group[data-frame-group="{group}"]')
    if details.get_attribute("open") is None:
        details.locator("> summary").click()


def project(provider: str = "azure") -> CloudProject:
    provider_name = "Kubernetes" if provider == "kubernetes" else "Azure"
    return CloudProject.model_validate(
        {
            "schema_version": 1,
            "slug": f"{provider}-sidebar-e2e",
            "title": f"{provider_name} Sidebar E2E",
            "description": "A browser test diagram.",
            "provider": provider,
            # The controls under test are grabbed at card coordinates.
            "presentation": {"display": "card"},
            "topology": {
                "id": "root",
                "name": "Sidebar E2E",
                "type": "group",
                "children": [
                    {"id": "client", "name": "Client", "type": "client"},
                    {"id": "api", "name": "API", "type": "service"},
                ],
            },
        }
    )


def long_name_project() -> CloudProject:
    """Three cards: a short name, a long one, and one past the width cap."""
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "single-cloud",
            "slug": "card-size-e2e",
            "title": "Card Size E2E",
            "description": "A browser test for text-aware card sizing.",
            "providers": [{"id": "azure"}],
            "default_library": "azure",
            "presentation": {"size": "fit"},
            "topology": {
                "id": "root",
                "name": "Card Size E2E",
                "type": "group",
                "children": [
                    {
                        "id": "short",
                        "name": "VM",
                        "type": "service",
                        "component": {"provider": "azure", "service_id": "virtual-machine"},
                    },
                    {
                        "id": "alb",
                        "name": "Application Load Balancer",
                        "type": "service",
                        "attributes": {"detail": "HTTPS :443"},
                        "component": {"provider": "azure", "service_id": "application-gateways"},
                    },
                    {
                        "id": "endless",
                        "name": "A" * 120,
                        "type": "service",
                        "component": {"provider": "azure", "service_id": "function-apps"},
                    },
                ],
            },
        }
    )


def multi_library_project() -> CloudProject:
    """Several libraries installed, so the sidebar offers all their cards."""
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "hybrid",
            "slug": "alias-search-e2e",
            "title": "Alias Search E2E",
            "description": "A browser test for alias-driven sidebar search.",
            "providers": [{"id": "azure"}, {"id": "kubernetes"}],
            "default_library": "all",
            "presentation": {"size": "fit"},
            "topology": {
                "id": "root",
                "name": "Alias Search E2E",
                "type": "group",
                "children": [
                    {"id": "client", "name": "Client", "type": "client"},
                    {"id": "api", "name": "API", "type": "service"},
                ],
            },
        }
    )


def connector_label_project() -> CloudProject:
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "single-cloud",
            "slug": "connector-label-e2e",
            "title": "Connector Label E2E",
            "description": "A browser test for reusable connector labels.",
            "providers": [{"id": "azure"}],
            "default_library": "azure",
            "topology": {
                "id": "root",
                "name": "Connector Label E2E",
                "type": "group",
                "children": [
                    {
                        "id": "client",
                        "name": "Client",
                        "type": "client",
                        "attributes": {"editor_x": 120, "editor_y": 180},
                        "connections": [
                            {
                                "target": "api",
                                "kind": "solid",
                                "label": "HTTPS",
                            }
                        ],
                    },
                    {
                        "id": "api",
                        "name": "API",
                        "type": "service",
                        "attributes": {"editor_x": 520, "editor_y": 180},
                    },
                ],
            },
        }
    )


def test_connector_labels_drag_edit_reset_and_round_trip_exports(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "connector-label.html"
    source.write_text(render_project_html(connector_label_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri() + "?fresh=labels")
            _settled(page)

            label = page.locator("[data-edge-label]").first
            assert label.get_attribute("data-edge-id") == "edge-1"
            before = label.bounding_box()
            page.mouse.move(before["x"] + before["width"] / 2, before["y"] + before["height"] / 2)
            page.mouse.down()
            # Drop the label clear of both cards. A label that lands on one is
            # pushed off it, and a pushed label cannot demonstrate the
            # following-the-wire behaviour this test is about.
            page.mouse.move(
                before["x"] + before["width"] / 2 + 48,
                before["y"] + before["height"] / 2 + 72,
            )
            page.mouse.up()

            moved = page.evaluate("() => window.infragramEditor.getState().edges[0]")
            assert moved["labelPlacement"]["mode"] == "manual"
            assert moved["labelPlacement"]["dx"] != 0
            assert moved["labelPlacement"]["dy"] != 0
            assert "labelX" not in moved
            assert "labelY" not in moved

            page.locator('[data-inspector-tab="text"]').click()
            label_input = page.locator('[data-edge-label-control="label"]')
            assert label_input.is_enabled()
            label_input.fill("STRICT TLS")
            label_input.press("Enter")
            assert page.locator("[data-edge-label] text").text_content() == "STRICT TLS"

            page.locator("[data-edge-label]").first.click()
            before_nudge = page.evaluate("() => window.infragramEditor.getState().edges[0]")
            page.keyboard.press("ArrowLeft")
            nudged = page.evaluate("() => window.infragramEditor.getState().edges[0]")
            assert nudged["labelPlacement"]["dx"] == before_nudge["labelPlacement"]["dx"] - 1

            label_x_before_node_move = float(
                page.locator("[data-edge-label]").first.get_attribute("data-label-x")
            )
            client = page.locator('[data-node-id="client"]')
            client_box = client.bounding_box()
            page.mouse.move(
                client_box["x"] + client_box["width"] / 2,
                client_box["y"] + client_box["height"] / 2,
            )
            page.mouse.down()
            page.mouse.move(
                client_box["x"] + client_box["width"] / 2 + 64,
                client_box["y"] + client_box["height"] / 2,
            )
            page.mouse.up()
            label_x_after_node_move = float(
                page.locator("[data-edge-label]").first.get_attribute("data-label-x")
            )
            after_node_move = page.evaluate("() => window.infragramEditor.getState().edges[0]")
            assert label_x_after_node_move > label_x_before_node_move
            assert after_node_move["labelPlacement"]["mode"] == "manual"

            page.locator("[data-edge-label]").first.click()
            label_box = page.locator("[data-edge-label]").first.bounding_box()
            api_box = page.locator('[data-node-id="api"]').bounding_box()
            overlaps_api = not (
                label_box["x"] + label_box["width"] <= api_box["x"] - 6
                or label_box["x"] >= api_box["x"] + api_box["width"] + 6
                or label_box["y"] + label_box["height"] <= api_box["y"] - 6
                or label_box["y"] >= api_box["y"] + api_box["height"] + 6
            )
            assert not overlaps_api, (
                label_box,
                api_box,
                after_node_move["labelPlacement"],
                page.locator("[data-edge-label]").first.get_attribute("data-label-x"),
                page.evaluate("() => window.infragramEditor.getState().nodes"),
            )
            page.screenshot(path=str(tmp_path / "connector-label-manual.png"))

            exported_project = page.evaluate("() => window.infragramEditor.exportProject()")
            connection = exported_project["topology"]["children"][0]["connections"][0]
            assert connection["label"] == "STRICT TLS"
            assert connection["label_placement"] == after_node_move["labelPlacement"]
            CloudProject.model_validate(exported_project)

            exported_svg = page.evaluate("() => window.infragramEditor.exportSvg()")
            assert 'data-edge-label="edge-1"' in exported_svg
            assert "data-edge-hit" not in exported_svg
            assert "data-edge-selection-halo" not in exported_svg
            assert 'class="edge-label-mask"' in exported_svg
            assert 'stroke="transparent"' in exported_svg

            exported_html = page.evaluate("() => window.infragramEditor.exportHtml()")
            exported = tmp_path / "connector-label-exported.html"
            exported.write_text(exported_html, encoding="utf-8")
            page.evaluate("() => localStorage.clear()")
            page.goto(exported.resolve().as_uri() + "?fresh=roundtrip")
            _settled(page)
            reloaded = page.evaluate("() => window.infragramEditor.getState().edges[0]")
            assert reloaded["label"] == "STRICT TLS"
            assert reloaded["labelPlacement"] == after_node_move["labelPlacement"]

            page.locator("[data-edge-label]").first.click(button="right")
            page.get_by_role("menuitem", name="Reset label position").click()
            reset = page.evaluate("() => window.infragramEditor.getState().edges[0]")
            assert "labelPlacement" not in reset
            assert (
                page.locator("[data-edge-label]").first.get_attribute("data-placement-mode")
                == "auto"
            )

            page.screenshot(path=str(tmp_path / "connector-label-interaction.png"))
        finally:
            browser.close()


#: Both installed libraries on one canvas. The edition ships a cloud and a
#: platform, so the mixed-library project is a hybrid rather than a
#: multicloud one, and Kubernetes takes a platform layer.
BOTH_LIBRARY_LAYERS = [
    {"id": "provider:azure", "name": "Azure", "kind": "provider", "provider": "azure", "order": 0},
    {
        "id": "platform:kubernetes",
        "name": "Kubernetes",
        "kind": "platform",
        "provider": "kubernetes",
        "order": 1,
    },
]


def multicloud_project() -> CloudProject:
    payload = {
        "schema_version": 2,
        "kind": "hybrid",
        "slug": "multicloud-sidebar-e2e",
        "title": "Multicloud Sidebar E2E",
        "description": "Azure and Kubernetes browser test diagram.",
        "providers": [{"id": provider} for provider in ("azure", "kubernetes")],
        "default_library": "all",
        "layers": BOTH_LIBRARY_LAYERS,
        "topology": {
            "id": "root",
            "name": "Multicloud Sidebar E2E",
            "type": "group",
            "children": [
                {"id": "client", "name": "Client", "type": "client"},
                {"id": "api", "name": "API", "type": "service"},
            ],
        },
    }
    return CloudProject.model_validate(payload)


#: The storage key the mixed-library workspace saves under.
BOTH_LIBRARY_SLUG = "multicloud-sidebar-e2e"


def both_library_workspace(tmp_path: Path, name: str) -> Path:
    """A canvas carrying both installed libraries, written as a page.

    The full product shipped a mixed-provider template to open these tests
    on. This edition ships two libraries and no mixed-library template, so
    the workspace is built here instead and exported with every library
    embedded, which is what enabling one from the provider menu needs.
    """

    source = tmp_path / f"{name}.html"
    source.write_text(render_project_html(multicloud_project(), libraries="all"), encoding="utf-8")
    return source


def multicloud_layer_project() -> CloudProject:
    payload = {
        "schema_version": 2,
        "kind": "hybrid",
        "slug": "multicloud-layer-e2e",
        "title": "Multicloud Layer E2E",
        "description": "Azure and Kubernetes layer and arrange browser test diagram.",
        "providers": [{"id": provider} for provider in ("azure", "kubernetes")],
        "default_library": "all",
        "layers": BOTH_LIBRARY_LAYERS,
        "topology": {
            "id": "root",
            "name": "Multicloud Layer E2E",
            "type": "group",
            "children": [
                {
                    "id": "gateway",
                    "name": "Gateway",
                    "type": "service",
                    "component": {
                        "provider": "azure",
                        "service_id": "application-gateways",
                    },
                    "layer_id": "provider:azure",
                    "connections": [{"target": "worker", "kind": "solid"}],
                },
                {
                    "id": "worker",
                    "name": "Worker",
                    "type": "service",
                    "component": {"provider": "kubernetes", "service_id": "pod"},
                    "layer_id": "platform:kubernetes",
                    "connections": [{"target": "database", "kind": "dashed"}],
                },
                {
                    "id": "database",
                    "name": "Database",
                    "type": "database",
                    "component": {"provider": "azure", "service_id": "sql-database"},
                    "layer_id": "provider:azure",
                },
            ],
        },
    }
    return CloudProject.model_validate(payload)


def test_multicloud_provider_selector_filters_libraries_without_touching_canvas(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "multicloud-sidebar.html"
    # the provider menu can only add libraries the page embeds
    source.write_text(render_project_html(multicloud_project(), libraries="all"), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri())
            _settled(page)

            # Two libraries on one canvas is a hybrid, not a multicloud
            # project, so it wears its own library's mark, not the
            # multicloud one.
            assert page.locator("[data-multicloud-mark]").count() == 0
            assert page.locator(".provider-name strong").inner_text() == "Azure Diagrams"
            assert page.locator(".provider-context").inner_text() == "Infragram Azure"
            assert page.locator("[data-provider-option]").count() == REGISTERED_LIBRARIES
            assert page.locator("[data-provider-summary]").inner_text() == "Azure + K8S"
            assert page.locator("[data-graph-node]").count() == 2
            assert page.locator(".provider-sidebar [data-component-id]").count() == 0

            page.locator("[data-provider-menu-trigger]").click()
            page.locator("[data-provider-clear]").click()
            assert page.locator("[data-provider-apply]").is_disabled()
            page.locator("[data-provider-select-all]").click()
            assert page.locator("[data-provider-option]:checked").count() == REGISTERED_LIBRARIES
            page.locator("[data-provider-apply]").click()
            # every installed library, Databricks too
            assert (
                page.locator("[data-provider-summary]").inner_text()
                == f"All {REGISTERED_LIBRARIES}"
            )
            assert page.locator("[data-graph-node]").count() == 2

            page.locator("[data-provider-menu-trigger]").click()
            page.locator("[data-provider-menu-trigger]").press("Escape")
            assert not page.locator("[data-provider-menu]").is_visible()
            assert (
                page.locator("[data-provider-menu-trigger]").get_attribute("aria-expanded")
                == "false"
            )

            page.locator('[data-provider-quick-filter="kubernetes"]').click()
            assert page.locator("[data-provider-summary]").inner_text() == "K8S"
            page.locator("[data-sidebar-search]").fill("Pod")
            result = page.locator('[data-component-qualified-id="kubernetes:pod"]')
            assert result.is_visible()
            assert result.locator(".provider-badge").inner_text() == "K8S"
            assert page.locator("[data-graph-node]").count() == 2

            exported = page.evaluate("window.infragramEditor.exportProject()")
            CloudProject.model_validate(exported)
            # The project combines a cloud and platform libraries, so changing
            # the visible library keeps its hybrid classification.
            assert exported["kind"] == "hybrid"
            assert len(exported["providers"]) == REGISTERED_LIBRARIES
            assert [
                provider["id"] for provider in exported["providers"] if provider["enabled"]
            ] == ["kubernetes"]
            assert exported["default_library"] == "kubernetes"
        finally:
            browser.close()


@pytest.mark.parametrize(
    "filename",
    [
        "azure-aks-baseline.infragram.json",
        "azure-web-app-front-door.infragram.json",
    ],
)
def test_new_provider_workspaces_keep_the_standard_sidebar_and_interactions(
    tmp_path: Path,
    filename: str,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    template = (
        Path(__file__).parents[2]
        / "skills"
        / "infragram-azure"
        / "assets"
        / "templates"
        / "cloud"
        / filename
    )
    source = tmp_path / filename.replace(".infragram.json", ".html")
    source.write_text(render_project_html(CloudProject.load(template)), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri())
            _settled(page)

            assert page.locator("details[data-category-id]").count() == 21
            library = page.evaluate("() => window.infragramEditor.getLibraryCatalog()")
            selected_provider = library["selectedProviders"][0]
            assert (
                sum(
                    component["provider"] in {selected_provider, "infragram"}
                    for component in library["components"]
                )
                == load_sidebar_catalog(selected_provider).component_count
            )
            assert page.locator(".component-card[draggable='true']").count() == 0
            assert page.locator(".provider-mark").is_visible()
            # The workspace opens light, and the palette says so.
            assert page.locator("[data-theme-toggle]").get_attribute("aria-label") == "Theme: Light"
            assert (
                page.locator(".provider-sidebar").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(244, 245, 245)"
            )
            assert (
                page.locator(".canvas-viewport").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(229, 231, 235)"
            )

            page.locator("[data-theme-toggle]").click()
            page.locator('[data-theme-choice="dark"]').click()
            assert page.locator("body").get_attribute("data-workspace-theme") == "dark"
            assert (
                page.locator(".provider-sidebar").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(14, 15, 16)"
            )

            before_nodes = page.locator("[data-graph-node]").count()
            page.locator("[data-sidebar-search]").fill("Load Balancer")
            page.locator('.component-card[data-component-id="generic-load-balancer"]').drag_to(
                page.locator("svg[data-infragram-diagram]"),
                target_position={"x": 480, "y": 140},
            )
            assert (
                page.locator('[data-graph-node][data-component-id="generic-load-balancer"]').count()
                == 1
            )
            assert page.locator("[data-graph-node]").count() == before_nodes + 1
        finally:
            browser.close()


def test_saved_canvas_refreshes_provider_artwork_without_losing_user_layout(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    template = (
        Path(__file__).parents[2]
        / "skills"
        / "infragram-azure"
        / "assets"
        / "templates"
        / "cloud"
        / "azure-web-app-front-door.infragram.json"
    )
    source = tmp_path / "azure-saved-canvas.html"
    source.write_text(render_project_html(CloudProject.load(template)), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri())
            _settled(page)

            fresh_icons = page.evaluate(
                """() => Object.fromEntries(
                    window.infragramEditor.getState().nodes
                      .filter(node => node.iconUri)
                      .map(node => [node.componentId, node.iconUri])
                )"""
            )
            saved_x = page.evaluate(
                """() => {
                    const stale = 'data:image/svg+xml;base64,PHN2Zy8+';
                    const state = window.infragramEditor.getState();
                    const appService = state.nodes.find(node => node.id === 'app-service');
                    appService.x += 40;
                    appService.iconUri = stale;
                    state.nodes.push({
                      ...appService,
                      id: 'virtual-machine-user-node',
                      componentId: 'virtual-machine',
                      name: 'Azure Virtual Machine',
                      detail: 'Compute',
                      x: appService.x,
                      y: appService.y + 120,
                      iconUri: stale,
                    });
                    localStorage.setItem(
                      'infragram-editor:azure-web-app-front-door',
                      JSON.stringify(state),
                    );
                    return appService.x;
                }"""
            )

            page.reload()
            _settled(page)
            restored = page.evaluate("() => window.infragramEditor.getState()")
            nodes = {node["id"]: node for node in restored["nodes"]}

            assert nodes["app-service"]["x"] == saved_x
            # fresh_icons is keyed by component id, which for this node is the
            # Azure service "app-services", not the node's own id.
            assert nodes["app-service"]["iconUri"] == fresh_icons["app-services"]
            assert (
                nodes["virtual-machine-user-node"]["iconUri"]
                != "data:image/svg+xml;base64,PHN2Zy8+"
            )
            assert page.locator('[data-node-id="app-service"] image').count() == 1
            assert page.locator('[data-node-id="virtual-machine-user-node"] image').count() == 1
            page.screenshot(path=str(tmp_path / "azure-refreshed-node-artwork.png"))
        finally:
            browser.close()


def test_fresh_workspace_query_does_not_restore_the_legacy_saved_canvas(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = both_library_workspace(tmp_path, "multicloud-fresh-workspace")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            page.goto(source.resolve().as_uri())
            _settled(page)
            original_x = page.evaluate("() => window.infragramEditor.getState().nodes[0].x")
            saved_x = page.evaluate(
                """() => {
                    const state = window.infragramEditor.getState();
                    state.nodes[0].x += 444;
                    localStorage.setItem(
                      'infragram-editor:multicloud-sidebar-e2e',
                      JSON.stringify(state),
                    );
                    return state.nodes[0].x;
                }"""
            )
            page.reload()
            _settled(page)
            assert page.evaluate("() => window.infragramEditor.getState().nodes[0].x") == saved_x

            page.goto(f"{source.resolve().as_uri()}?fresh=1")
            _settled(page)
            assert page.evaluate("() => window.infragramEditor.getState().nodes[0].x") == original_x
            assert (
                page.evaluate("() => window.infragramEditor.getStorageKey()")
                == "infragram-editor:multicloud-sidebar-e2e:fresh:1"
            )
            assert page.locator("[data-local-state]").inner_text() == "Fresh workspace"

            page.locator('details[data-category-id="custom"] > summary').click()
            _open_frame_group(page, "azure")
            preset = page.locator('[data-frame-preset="azure-landing-zone"]')
            assert "Azure landing zone starter" in preset.inner_text()
            preset.click()
            frames = page.evaluate(
                """() => window.infragramEditor.getState().boundaries
                  .filter(frame => frame.frameGroup === 'azure')"""
            )
            assert len(frames) == 6
            for parent, child in zip(frames, frames[1:], strict=False):
                assert child["parentId"] == parent["id"]
        finally:
            browser.close()


def test_theme_control_is_in_the_header_and_editor_chrome_uses_ui_fonts(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "header-theme-control.html"
    source.write_text(render_project_html(project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri())
            _settled(page)

            header = page.locator("[data-editor-header]")
            assert header.locator("[data-theme-toggle]").count() == 1
            assert page.locator(".provider-sidebar [data-theme-toggle]").count() == 0
            assert page.locator(".sidebar-footer").count() == 0
            assert page.locator(".drawer-status").count() == 0
            assert page.locator("[data-search-status]").get_attribute("class") == "sr-only"

            for selector in (
                ".document-copy small",
                ".zoom-value",
            ):
                font_family = page.locator(selector).evaluate(
                    "element => getComputedStyle(element).fontFamily"
                )
                assert "Mono" not in font_family
                assert "monospace" not in font_family

            page.locator("[data-theme-toggle]").click()
            page.locator('[data-theme-choice="dark"]').click()
            assert page.locator("body").get_attribute("data-workspace-theme") == "dark"
            page.screenshot(path=str(tmp_path / "theme-control-in-header.png"))
        finally:
            browser.close()


def test_sidebar_logo_hover_previews_and_click_pins_the_collapsed_icon_rail(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "collapsible-sidebar.html"
    source.write_text(render_project_html(project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            # This test is about the dark palette, so it asks for that look.
            page.goto(source.resolve().as_uri() + "?theme=dark")
            _settled(page)
            sidebar = page.get_by_test_id("provider-sidebar")
            brand = page.locator("[data-sidebar-logo-trigger]")
            sidebar_control_icon = page.locator("[data-sidebar-control-icon]")
            category_icon = page.locator(".category-icon").first
            category_list = page.locator(".category-list")

            assert round(sidebar.bounding_box()["width"]) == 372
            assert sidebar_control_icon.is_visible()
            sidebar_background = sidebar.evaluate(
                "element => getComputedStyle(element).backgroundColor"
            )
            assert sidebar_background == "rgb(14, 15, 16)"
            assert (
                page.locator("body").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(14, 15, 16)"
            )
            assert (
                page.locator(".search-box").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(20, 21, 21)"
            )
            assert (
                page.locator(".canvas-viewport").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(20, 20, 20)"
            )
            assert (
                page.locator("svg[data-infragram-diagram]").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(20, 20, 20)"
            )
            theme_toggle = page.locator("[data-theme-toggle]")
            assert page.locator("body").get_attribute("data-workspace-theme") == "dark"
            assert theme_toggle.get_attribute("aria-label") == "Theme: Dark"
            theme_toggle.click()
            page.locator('[data-theme-choice="light"]').click()
            assert page.locator("body").get_attribute("data-workspace-theme") == "light"
            assert theme_toggle.get_attribute("aria-label") == "Theme: Light"
            assert (
                page.locator(".provider-sidebar").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(244, 245, 245)"
            )
            theme_toggle.click()
            page.locator('[data-theme-choice="dark"]').click()
            assert page.locator("body").get_attribute("data-workspace-theme") == "dark"
            assert (
                category_list.evaluate("element => getComputedStyle(element).scrollbarWidth")
                == "none"
            )
            # the categories' 32 px rows fit a tall window: a short one scrolls them
            page.set_viewport_size({"width": 1440, "height": 560})
            category_list.hover()
            page.mouse.wheel(0, 640)
            page.wait_for_timeout(100)
            assert category_list.evaluate("element => element.scrollTop") > 0
            category_list.evaluate("element => { element.scrollTop = 0; }")
            page.set_viewport_size({"width": 1440, "height": 960})
            page.wait_for_timeout(100)
            brand.click()
            page.wait_for_timeout(180)
            assert "sidebar-collapsed" in page.locator("body").get_attribute("class")
            assert round(sidebar.bounding_box()["width"]) == 56
            assert (
                sidebar.evaluate("element => getComputedStyle(element).backgroundColor")
                == sidebar_background
            )
            assert page.locator(".provider-mark").is_visible()
            assert category_icon.is_visible()
            assert not sidebar_control_icon.is_visible()
            assert not page.locator(".provider-name").is_visible()
            assert not page.locator("[data-sidebar-search]").is_visible()
            collapsed_canvas_x = round(page.locator(".canvas-viewport").bounding_box()["x"])
            page.screenshot(path=str(tmp_path / "sidebar-collapsed.png"))

            category_icon.hover()
            page.wait_for_timeout(180)
            assert round(sidebar.bounding_box()["width"]) == 56

            page.locator(".provider-mark").hover()
            page.wait_for_timeout(180)
            assert "sidebar-preview" in page.locator("body").get_attribute("class")
            assert round(sidebar.bounding_box()["width"]) == 372
            assert page.locator(".provider-name").is_visible()
            assert sidebar_control_icon.is_visible()
            assert page.locator("[data-sidebar-search]").is_visible()
            assert round(page.locator(".canvas-viewport").bounding_box()["x"]) == collapsed_canvas_x
            page.screenshot(path=str(tmp_path / "sidebar-logo-hover.png"))

            page.locator(".canvas-viewport").hover(position={"x": 600, "y": 700})
            page.wait_for_timeout(180)
            assert "sidebar-preview" not in (page.locator("body").get_attribute("class") or "")
            assert round(sidebar.bounding_box()["width"]) == 56

            page.locator(".canvas-viewport").click(position={"x": 600, "y": 700})
            brand.evaluate("element => element.focus()")
            page.wait_for_timeout(180)
            assert "sidebar-preview" in page.locator("body").get_attribute("class")
            page.locator(".canvas-viewport").click(position={"x": 600, "y": 700})
            page.wait_for_timeout(180)
            assert "sidebar-preview" not in (page.locator("body").get_attribute("class") or "")

            page.locator(".provider-mark").hover()
            brand.click()
            page.wait_for_timeout(180)
            assert "sidebar-collapsed" not in (page.locator("body").get_attribute("class") or "")
            assert round(sidebar.bounding_box()["width"]) == 372
            page.locator(".canvas-viewport").hover(position={"x": 600, "y": 700})
            page.wait_for_timeout(180)
            assert round(sidebar.bounding_box()["width"]) == 372
        finally:
            browser.close()


def test_sidebar_search_filters_components_without_replacing_the_canvas(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "editor.html"
    source.write_text(render_project_html(project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            # This test is about the dark palette, so it asks for that look.
            page.goto(source.resolve().as_uri() + "?theme=dark")
            _settled(page)

            assert page.get_by_test_id("provider-sidebar").is_visible()
            assert page.locator("details[data-category-id]").count() == 21
            assert page.locator("svg.category-icon[data-category-icon]").count() == 21
            library = page.evaluate("() => window.infragramEditor.getLibraryCatalog()")
            assert (
                sum(
                    component["provider"] in {"azure", "infragram"}
                    for component in library["components"]
                )
                == load_sidebar_catalog("azure").component_count
            )
            assert page.locator(".component-card[data-component-id]").count() == 0
            assert page.locator("svg[data-infragram-diagram]").count() == 1
            assert page.locator("[data-graph-node]").count() == 2

            compute = page.locator('details[data-category-id="compute"]')
            compute.locator("summary").click()
            assert compute.get_attribute("open") is not None
            assert compute.locator(".component-card:visible").count() > 0
            component_list = compute.locator("[data-component-list]")
            first_card = compute.locator(".component-card:visible").first
            list_box = component_list.bounding_box()
            card_box = first_card.bounding_box()
            assert list_box is not None and card_box is not None
            # a category's components sit a step in from it
            assert card_box["x"] - list_box["x"] <= 24
            assert (list_box["x"] + list_box["width"]) - (card_box["x"] + card_box["width"]) <= 10
            assert (
                first_card.evaluate("element => getComputedStyle(element).backgroundColor")
                == "rgba(0, 0, 0, 0)"
            )
            assert (
                first_card.evaluate("element => getComputedStyle(element).color")
                == "rgb(228, 230, 231)"
            )
            compute.locator("summary").click()
            assert compute.get_attribute("open") is None

            page.locator("[data-sidebar-search]").fill("Application Gateway")

            visible = page.locator("[data-component-id]:visible")
            assert visible.count() >= 1
            assert visible.count() < 10
            assert page.locator('[data-component-id="application-gateways"]').is_visible()
            assert (
                page.locator('details[data-category-id="networking"]').get_attribute("open")
                is not None
            )
            assert page.locator("svg[data-infragram-diagram]").is_visible()

            page.locator("[data-sidebar-search]").fill("")
            assert page.locator(".provider-sidebar [data-component-id]").count() == 0
        finally:
            browser.close()


def test_canvas_grid_is_adaptive_toggleable_and_excluded_from_clean_svg_exports(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "adaptive-grid.html"
    source.write_text(render_project_html(project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri())
            _settled(page)

            # the grid opens hidden and is a press away
            grid_toggle = page.locator('[data-editor-action="toggle-grid"]')
            assert grid_toggle.get_attribute("aria-pressed") == "false"
            assert (
                page.locator("[data-editor-grid]").evaluate(
                    "element => getComputedStyle(element).display"
                )
                == "none"
            )
            grid_toggle.click()

            assert (
                page.locator(".canvas-viewport").evaluate(
                    "element => getComputedStyle(element).backgroundImage"
                )
                == "none"
            )
            assert (
                page.locator(".diagram-stage").evaluate(
                    "element => getComputedStyle(element).backgroundImage"
                )
                != "none"
            )
            pattern = page.locator("#infragram-editor-grid")
            assert pattern.get_attribute("data-grid-steps") == "4"
            assert pattern.locator("[data-grid-minor]").count() == 1
            assert pattern.locator("[data-grid-major]").count() == 1

            def grid_metrics() -> dict[str, float]:
                return page.evaluate(
                    """() => {
                        const svg = document.querySelector('[data-infragram-diagram]');
                        const pattern = document.querySelector('#infragram-editor-grid');
                        const state = window.infragramEditor.getState();
                        const scale = svg.getBoundingClientRect().width / state.canvas.width;
                        return {
                          snap: state.canvas.grid,
                          visible: Number(pattern.dataset.visibleStep),
                          screen: Number(pattern.dataset.visibleStep) * scale,
                        };
                    }"""
                )

            initial = grid_metrics()
            assert initial["visible"] % initial["snap"] == 0
            assert initial["visible"] >= initial["snap"] * 3
            assert initial["screen"] >= 4

            for _ in range(4):
                page.locator('[data-editor-action="zoom-out"]').click()
            zoomed_out = grid_metrics()
            assert zoomed_out["visible"] >= initial["visible"]
            assert zoomed_out["screen"] >= 4

            assert grid_toggle.get_attribute("aria-pressed") == "true"
            grid_toggle.click()
            assert grid_toggle.get_attribute("aria-pressed") == "false"
            assert (
                page.locator("[data-editor-grid]").evaluate(
                    "element => getComputedStyle(element).display"
                )
                == "none"
            )
            assert (
                page.locator(".diagram-stage").evaluate(
                    "element => getComputedStyle(element).backgroundImage"
                )
                == "none"
            )

            exported_svg = page.evaluate("() => window.infragramEditor.exportSvg()")
            assert "data-editor-grid" not in exported_svg
            assert "infragram-editor-grid" not in exported_svg

            grid_toggle.click()
            page.locator('[data-editor-action="zoom-fit"]').click()
            page.screenshot(path=str(tmp_path / "adaptive-major-minor-grid.png"))
        finally:
            browser.close()


def test_multicloud_grid_fills_the_viewport_and_grows_past_its_current_edge(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = both_library_workspace(tmp_path, "expandable-multicloud-grid")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            # the grid opens hidden: shown for this visit, to measure it
            page.goto(source.resolve().as_uri() + "?grid=1")
            _settled(page)

            viewport_box = page.locator(".canvas-viewport").bounding_box()
            diagram_box = page.locator("[data-infragram-diagram]").bounding_box()
            grid_box = page.locator("[data-editor-grid]").bounding_box()
            assert viewport_box is not None and diagram_box is not None and grid_box is not None
            assert diagram_box["width"] >= viewport_box["width"] - 2
            assert diagram_box["height"] >= viewport_box["height"] - 2
            assert abs(grid_box["width"] - diagram_box["width"]) < 2
            assert abs(grid_box["height"] - diagram_box["height"]) < 2

            before = page.evaluate("() => window.infragramEditor.getState().canvas")
            added_id = page.evaluate(
                """before => window.infragramEditor.addNode({
                    id: 'edge-service',
                    qualifiedId: 'azure:edge-service',
                    provider: 'azure',
                    name: 'Edge service',
                    detail: 'growth check',
                    category: 'compute',
                    iconUri: ''
                }, {x: before.width + 240, y: before.height + 160})""",
                before,
            )
            after = page.evaluate("() => window.infragramEditor.getState()")
            added = next(node for node in after["nodes"] if node["id"] == added_id)
            assert after["canvas"]["width"] > before["width"]
            assert after["canvas"]["height"] > before["height"]
            assert added["x"] > before["width"]
            assert added["y"] > before["height"]
            assert added["x"] + added["width"] <= after["canvas"]["width"]
            assert added["y"] + added["height"] <= after["canvas"]["height"]

            page.locator('[data-editor-action="zoom-fit"]').click()
            page.screenshot(path=str(tmp_path / "expandable-multicloud-grid.png"))
        finally:
            browser.close()


def test_drawio_shell_uses_the_shared_dark_palette_and_docked_panels(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "drawio-shell.html"
    source.write_text(render_project_html(project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            # This test is about the dark palette, so it asks for that look.
            page.goto(source.resolve().as_uri() + "?theme=dark")
            _settled(page)

            assert page.locator("[data-editor-header]").is_visible()
            assert page.locator("[data-document-title]").text_content() == "Azure Sidebar E2E"
            assert page.locator("[data-right-inspector]").is_visible()
            assert page.locator("[data-bottom-drawer]").is_visible()
            # the Cost tab shows only on a page with something priced; this one has none
            assert page.locator("[data-inspector-tab]:visible").all_text_contents() == [
                "Diagram",
                "Style",
                "Text",
                "Arrange",
                "Layers",
            ]
            assert page.locator("[data-bottom-tab]").all_text_contents() == [
                "Examples",
                "3D builder",
                "Resources",
            ]

            tokens = page.evaluate(
                """() => {
                    const styles = getComputedStyle(document.documentElement);
                    const names = [
                      '--canvas-bg', '--card-bg', '--control-bg', '--text-canvas',
                      '--text-secondary', '--border-color', '--wire-color',
                      '--wire-selected', '--handle-color', '--accent',
                      '--accent-muted', '--error-color',
                    ];
                    return Object.fromEntries(names.map(name => [
                      name, styles.getPropertyValue(name).trim().toUpperCase(),
                    ]));
                }"""
            )
            # The palette the runtime paints the drawing with. The chrome's
            # own surfaces are Material 3 roles; these twelve are not, and
            # retinting one repaints every picture.
            assert tokens == {
                "--canvas-bg": "#141414",
                "--card-bg": "#2C2E33",
                "--control-bg": "#2E2E2E",
                "--text-canvas": "#F8F8F8",
                "--text-secondary": "#C9C9C9",
                "--border-color": "#424242",
                "--wire-color": "#8A8A8A",
                "--wire-selected": "#D2D2D2",
                "--handle-color": "#BEBEBE",
                "--accent": "#479EF5",
                "--accent-muted": "#5E87B8",
                "--error-color": "#E03131",
            }
            assert (
                page.locator(".provider-sidebar").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(14, 15, 16)"
            )
            assert (
                page.locator("[data-editor-header]").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgba(0, 0, 0, 0)"
            )
            assert (
                page.locator("[data-right-inspector]").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(20, 21, 21)"
            )
            assert (
                page.locator(".search-box").evaluate(
                    "element => getComputedStyle(element).backgroundColor"
                )
                == "rgb(20, 21, 21)"
            )

            undo_box = page.locator('[data-editor-action="undo"]').bounding_box()
            zoom_box = page.locator('[data-editor-action="zoom-out"]').bounding_box()
            assert undo_box is not None and zoom_box is not None
            assert abs(undo_box["y"] - zoom_box["y"]) < 2

            inspector = page.locator("[data-right-inspector]")
            canvas = page.locator(".canvas-viewport")
            expanded_width = inspector.bounding_box()["width"]
            canvas_before = canvas.bounding_box()["width"]
            page.locator("[data-inspector-toggle]").click()
            page.wait_for_timeout(180)
            assert inspector.get_attribute("data-collapsed") == "true"
            assert inspector.bounding_box()["width"] < expanded_width
            assert canvas.bounding_box()["width"] > canvas_before
            page.locator("[data-inspector-toggle]").click()

            drawer = page.locator("[data-bottom-drawer]")
            collapsed_height = drawer.bounding_box()["height"]
            assert drawer.get_attribute("data-expanded") == "false"
            page.locator("[data-bottom-toggle]").click()
            page.wait_for_timeout(180)
            assert drawer.get_attribute("data-expanded") == "true"
            assert drawer.bounding_box()["height"] > collapsed_height + 120
            assert page.locator("[data-bottom-panel='examples']").is_visible()
            page.screenshot(path=str(tmp_path / "drawio-shell-expanded.png"))
            page.get_by_role("tab", name="3D builder").click()
            assert page.locator("[data-bottom-panel='builder']").is_visible()
        finally:
            browser.close()


def test_style_inspector_updates_selected_graph_items_with_undo_and_export(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "style-inspector.html"
    source.write_text(render_project_html(project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            # This test is about the dark palette, so it asks for that look.
            page.goto(source.resolve().as_uri() + "?theme=dark")
            _settled(page)

            api = page.locator('[data-graph-node][data-node-id="api"]')
            # a single click only shows a card's flow; a double click selects it
            api.dblclick()
            page.get_by_role("tab", name="Style").click()
            assert page.locator("[data-inspector-selection]").text_content() == "API"
            page.locator('[data-style-preset="accent-outline"]').click()

            styled = next(
                node
                for node in page.evaluate("() => window.infragramEditor.getState().nodes")
                if node["id"] == "api"
            )
            # A preset is an outline: it sets the stroke and leaves the card
            # its theme's fill.
            assert styled["style"] == {"stroke": "#479EF5"}
            surface = page.locator('[data-node-id="api"] [data-node-surface]')
            assert surface.get_attribute("fill") == "#2C2E33"
            assert surface.get_attribute("stroke") == "#479EF5"

            exported_project = page.evaluate("() => window.infragramEditor.exportProject()")
            api_export = next(
                node for node in exported_project["topology"]["children"] if node["id"] == "api"
            )
            assert api_export["attributes"]["editor_style"] == {"stroke": "#479EF5"}

            page.locator('[data-editor-action="undo"]').click()
            restored = next(
                node
                for node in page.evaluate("() => window.infragramEditor.getState().nodes")
                if node["id"] == "api"
            )
            assert "style" not in restored
            # still selected after the step back, so ringed in the accent;
            # let go of it and it is drawn in the plain border
            page.keyboard.press("Escape")
            assert surface.get_attribute("stroke") == "#424242"

            page.evaluate("() => window.infragramEditor.connect('client', 'api')")
            assert page.locator("[data-inspector-selection]").text_content() == "Connector"
            page.locator('[data-style-preset="muted-outline"]').click()
            edge_state = page.evaluate("() => window.infragramEditor.getState().edges[0]")
            assert edge_state["style"] == {"stroke": "#5E87B8"}
            # A styled edge keeps its own stroke while selected; selection is
            # shown by the halo, so the preset stays visible as it is applied.
            assert page.locator("[data-graph-edge]").get_attribute("stroke") == "#5E87B8"
            assert page.locator("[data-edge-selection-halo]").count() == 1

            edge_export = page.evaluate("() => window.infragramEditor.exportProject()")
            client_export = next(
                node for node in edge_export["topology"]["children"] if node["id"] == "client"
            )
            assert client_export["attributes"]["editor_edge_styles"] == {
                "api": {"stroke": "#5E87B8"}
            }

            exported_html = page.evaluate("() => window.infragramEditor.exportHtml()")
            assert "data-right-inspector" in exported_html
            assert "data-bottom-drawer" in exported_html
            exported_svg = page.evaluate("() => window.infragramEditor.exportSvg()")
            assert "data-right-inspector" not in exported_svg
            assert "data-bottom-drawer" not in exported_svg
        finally:
            browser.close()


def test_aws_category_icons_align_and_toggle_every_service_group(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "aws-sidebar.html"
    source.write_text(render_project_html(project("azure")), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri())
            _settled(page)
            categories = page.locator("details[data-category-id]")
            icons = page.locator("svg.category-icon[data-category-icon]")

            assert categories.count() == 21
            assert icons.count() == 21
            library = page.evaluate("() => window.infragramEditor.getLibraryCatalog()")
            assert (
                sum(
                    component["provider"] in {"azure", "infragram"}
                    for component in library["components"]
                )
                == load_sidebar_catalog("azure").component_count
            )
            assert page.locator(".component-card[data-component-id]").count() == 0
            assert page.locator('[data-category-id="power-platform"]').count() == 1
            icon_x = icons.evaluate_all(
                "elements => elements.filter(element => element.getClientRects().length)"
                ".map(element => Math.round(element.getBoundingClientRect().x))"
            )
            assert len(set(icon_x)) == 1
            page.screenshot(path=str(tmp_path / "aws-sidebar-aligned.png"))

            ai = page.locator('[data-category-id="ai-machine-learning"]')
            ai_icon = ai.locator('[data-category-icon-kind="brain"]')
            assert page.locator('[data-category-icon-kind="governance-scale"]').count() == 1
            assert page.locator('[data-category-icon-kind="ci-cd"]').count() == 1
            assert page.locator('[data-category-icon-kind="github-container"]').count() == 1
            ai_icon.hover()
            assert ai_icon.evaluate("element => getComputedStyle(element).transform") != "none"

            for index in range(categories.count()):
                category = categories.nth(index)
                # only the retired physical-world 3D set filled these rows; no
                # library this edition embeds can, so the sidebar leaves them out
                if category.get_attribute("data-category-id") in {
                    "energy",
                    "industrial",
                    "facilities",
                }:
                    assert category.is_hidden()
                    continue
                icon = category.locator(".category-icon")
                icon.click()
                assert category.get_attribute("open") is not None
                assert category.locator(".component-card").count() > 0
                icon.click()
                assert category.get_attribute("open") is None

            ai_icon.click()
            assert ai.get_attribute("open") is not None
            assert ai.locator('[data-component-id="ai-foundry"]').count() == 1
            page.screenshot(path=str(tmp_path / "aws-ai-category.png"))
        finally:
            browser.close()


def test_palette_nodes_drag_move_connect_undo_and_delete(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "interactive-editor.html"
    source.write_text(render_project_html(project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri())
            _settled(page)
            canvas = page.locator("svg[data-infragram-diagram]")

            page.locator("[data-sidebar-search]").fill("Application Gateway")
            palette_node = page.locator('[data-component-id="application-gateways"]')
            # Content-based Fit keeps the seed diagram at a readable scale. Drop
            # into open workspace so the new card does not cover the API card.
            palette_node.drag_to(canvas, target_position={"x": 700, "y": 450})

            dropped = page.locator('[data-graph-node][data-component-id="application-gateways"]')
            assert dropped.count() == 1
            assert page.locator("[data-graph-node]").count() == 3

            api = page.locator('[data-graph-node][data-node-id="api"]')
            before_transform = api.get_attribute("transform")
            before_path = (
                page.locator("[data-graph-edge]").first.get_attribute("d")
                if page.locator("[data-graph-edge]").count()
                else ""
            )
            box = api.bounding_box()
            assert box is not None
            page.mouse.move(box["x"] + 60, box["y"] + 30)
            page.mouse.down()
            page.mouse.move(box["x"] + 140, box["y"] + 78, steps=8)
            page.mouse.up()
            assert api.get_attribute("transform") != before_transform

            # a card shows its connection dots under the pointer, hidden otherwise
            client_port = page.locator('[data-node-id="client"] [data-node-port="right"]')
            dropped_port = dropped.locator('[data-node-port="left"]')
            page.locator('[data-node-id="client"] [data-node-surface]').hover(force=True)
            start = client_port.bounding_box()
            dropped.locator("[data-node-surface]").hover(force=True)
            end = dropped_port.bounding_box()
            assert start is not None and end is not None
            assert start["width"] >= 16
            assert end["width"] >= 16
            # over the card first, as a pointer comes to its dot
            page.locator('[data-node-id="client"] [data-node-surface]').hover(force=True)
            page.mouse.move(
                start["x"] + start["width"] / 2 - 6, start["y"] + start["height"] / 2, steps=4
            )
            page.mouse.down()
            page.mouse.move(
                (start["x"] + end["x"]) / 2,
                (start["y"] + end["y"]) / 2,
                steps=4,
            )
            assert page.locator("[data-connection-preview]").count() == 1
            page.mouse.move(end["x"] + end["width"] / 2 + 6, end["y"] + end["height"] / 2, steps=8)
            page.mouse.up()

            assert page.locator("[data-graph-edge]").count() == 1
            edge = page.locator("[data-graph-edge]").first
            assert edge.get_attribute("d").startswith("M")
            # the new wire turns, with the square elbows every wire gets by default
            assert "Q" not in edge.get_attribute("d") and edge.get_attribute("d").count("L") >= 2, (
                edge.get_attribute("d")
            )
            terminal_geometry = page.evaluate(
                """() => {
                    const state = window.infragramEditor.getState();
                    const edge = document.querySelector('[data-graph-edge]');
                    const source = state.nodes.find(node => node.id === 'client');
                    const target = state.nodes.find(node => node.componentId === 'application-gateways');
                    return {
                      sourceX: Number(edge.dataset.sourceX),
                      sourceY: Number(edge.dataset.sourceY),
                      targetX: Number(edge.dataset.targetX),
                      targetY: Number(edge.dataset.targetY),
                      expectedSourceX: source.x + source.width,
                      expectedSourceY: source.y + source.height / 2,
                      expectedTargetX: target.x,
                      expectedTargetY: target.y + target.height / 2,
                    };
                }"""
            )
            assert terminal_geometry["sourceX"] == terminal_geometry["expectedSourceX"]
            assert terminal_geometry["sourceY"] == terminal_geometry["expectedSourceY"]
            assert terminal_geometry["targetX"] == terminal_geometry["expectedTargetX"]
            assert terminal_geometry["targetY"] == terminal_geometry["expectedTargetY"]
            page.screenshot(path=str(tmp_path / "connection-hit-area-and-terminals.png"))

            page.locator('[data-editor-action="undo"]').click()
            assert page.locator("[data-graph-edge]").count() == 0
            page.locator('[data-editor-action="redo"]').click()
            assert page.locator("[data-graph-edge]").count() == 1

            page.locator("[data-edge-hit]").first.click()
            page.locator('[data-editor-action="delete"]').click()
            assert page.locator("[data-graph-edge]").count() == 0
            assert page.evaluate("() => window.infragramEditor.getState().nodes.length") == 3
            exported_project = page.evaluate("() => window.infragramEditor.exportProject()")
            assert len(exported_project["topology"]["children"]) == 3
            assert (
                CloudProject.model_validate(exported_project)
                .topology.index()
                .get("application-gateways")
                is not None
            )
            exported_html = page.evaluate("() => window.infragramEditor.exportHtml()")
            assert "application-gateways" in exported_html
            assert "data-infragram-editor" in exported_html
            exported_svg = page.evaluate("() => window.infragramEditor.exportSvg()")
            assert "data-node-port" not in exported_svg
            assert "data-edge-terminal" not in exported_svg
            if before_path:
                assert page.locator("[data-graph-edge]").count() == 0
        finally:
            browser.close()


def test_aws_boundaries_move_resize_nest_export_and_keep_connections_attached(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    template = (
        Path(__file__).parents[2]
        / "skills"
        / "infragram-azure"
        / "assets"
        / "templates"
        / "cloud"
        / "azure-hub-spoke-landing-zone.infragram.json"
    )
    source = tmp_path / "azure-dynamic-boundaries.html"
    boundaries = CloudProject.load(template)
    boundaries.presentation = boundaries.presentation.model_copy(update={"display": "card"})
    source.write_text(render_project_html(boundaries), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            page.goto(source.resolve().as_uri())
            _settled(page)
            assert page.locator("[data-graph-boundary]").count() == 24

            before = page.evaluate("() => window.infragramEditor.getState()")
            cloud = page.locator('[data-boundary-id="microsoft-azure"]')
            cloud_box = cloud.bounding_box()
            assert cloud_box is not None
            # the right border: the firewall-logs wire runs down the left margin
            grab_x = cloud_box["x"] + cloud_box["width"] - 2
            page.mouse.move(grab_x, cloud_box["y"] + cloud_box["height"] / 2)
            page.mouse.down()
            page.mouse.move(
                grab_x + 40,
                cloud_box["y"] + cloud_box["height"] / 2 + 24,
                steps=8,
            )
            page.mouse.up()

            after_move = page.evaluate("() => window.infragramEditor.getState()")
            before_boundaries = {item["id"]: item for item in before["boundaries"]}
            moved_boundaries = {item["id"]: item for item in after_move["boundaries"]}
            before_nodes = {item["id"]: item for item in before["nodes"]}
            moved_nodes = {item["id"]: item for item in after_move["nodes"]}
            dx = (
                moved_boundaries["microsoft-azure"]["x"] - before_boundaries["microsoft-azure"]["x"]
            )
            dy = (
                moved_boundaries["microsoft-azure"]["y"] - before_boundaries["microsoft-azure"]["y"]
            )
            assert (dx, dy) != (0, 0)
            for boundary_id in (
                "connectivity-subscription",
                "east-us-2",
                "rg-connectivity-hub",
                "hub-vnet-10-0-0-0-16",
                "gatewaysubnet",
                "azurefirewallsubnet",
            ):
                assert (
                    moved_boundaries[boundary_id]["x"] - before_boundaries[boundary_id]["x"] == dx
                )
                assert (
                    moved_boundaries[boundary_id]["y"] - before_boundaries[boundary_id]["y"] == dy
                )
            assert (
                moved_nodes["expressroute-gateway"]["x"] - before_nodes["expressroute-gateway"]["x"]
                == dx
            )
            assert (
                moved_nodes["expressroute-gateway"]["y"] - before_nodes["expressroute-gateway"]["y"]
                == dy
            )
            # the on-premises site is a sibling frame, not a child: it stays put
            assert (
                moved_boundaries["corporate-data-centre"]["x"]
                == before_boundaries["corporate-data-centre"]["x"]
            )

            handle = page.locator('[data-boundary-resize="se"][data-boundary-id="microsoft-azure"]')
            handle.scroll_into_view_if_needed()
            handle_box = handle.bounding_box()
            assert handle_box is not None
            old_width = moved_boundaries["microsoft-azure"]["width"]
            old_height = moved_boundaries["microsoft-azure"]["height"]
            page.mouse.move(
                handle_box["x"] + handle_box["width"] / 2,
                handle_box["y"] + handle_box["height"] / 2,
            )
            page.mouse.down()
            page.mouse.move(handle_box["x"] + 64, handle_box["y"] + 44, steps=8)
            page.mouse.up()
            resized = page.evaluate("() => window.infragramEditor.getState()")
            resized_cloud = next(
                item for item in resized["boundaries"] if item["id"] == "microsoft-azure"
            )
            assert resized_cloud["width"] > old_width
            assert resized_cloud["height"] > old_height

            page.locator("[data-sidebar-search]").fill("Azure virtual network")
            page.locator('[data-component-id="custom-boundary-azure-vnet"]').dblclick()
            assert page.locator("[data-graph-boundary]").count() == 25
            # the template already draws a hub VNet and two spoke VNets
            assert page.locator('[data-graph-boundary][data-boundary-kind="network"]').count() == 4

            attached = page.evaluate(
                """() => [...document.querySelectorAll('[data-graph-edge]')].every(edge => {
                    const state = window.infragramEditor.getState();
                    const source = state.nodes.find(item => item.id === edge.dataset.source);
                    if (!source) return true;
                    const sx = Number(edge.dataset.sourceX);
                    const sy = Number(edge.dataset.sourceY);
                    return Math.abs(source.x - sx) < 0.01
                      || Math.abs(source.x + source.width - sx) < 0.01
                      || Math.abs(source.y - sy) < 0.01
                      || Math.abs(source.y + source.height - sy) < 0.01;
                })"""
            )
            assert attached

            exported = page.evaluate("() => window.infragramEditor.exportProject()")
            validated = CloudProject.model_validate(exported)
            elements = validated.topology.index()
            assert elements["connectivity-subscription"] in elements["microsoft-azure"].children
            assert elements["east-us-2"] in elements["connectivity-subscription"].children
            assert elements["gatewaysubnet"] in elements["hub-vnet-10-0-0-0-16"].children
            assert elements["expressroute-gateway"] in elements["gatewaysubnet"].children
            assert elements["microsoft-azure"].attributes["editor_width"] == resized_cloud["width"]

            exported_svg = page.evaluate("() => window.infragramEditor.exportSvg()")
            assert "data-static-cluster-layer" not in exported_svg
            assert "data-boundary-resize" not in exported_svg
            assert exported_svg.count("data-graph-boundary") == 25
            page.screenshot(path=str(tmp_path / "azure-dynamic-boundaries.png"), full_page=True)
        finally:
            browser.close()


def test_locked_frame_explains_unlock_step_and_then_deletes(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = both_library_workspace(tmp_path, "locked-frame-delete-flow")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 960})
            page.goto(f"{source.resolve().as_uri()}?fresh=1")
            _settled(page)
            page.locator('details[data-category-id="custom"] > summary').click()
            _open_frame_group(page, "azure")
            page.locator('[data-frame-preset="azure-landing-zone"]').click()

            graph_frame = page.locator('[data-graph-boundary][data-selected="true"]')
            frame_id = graph_frame.get_attribute("data-boundary-id")
            assert frame_id
            selection_lock = page.locator('[data-selection-action="lock"]')
            selection_lock.click()

            assert graph_frame.get_attribute("data-locked") == "true"
            assert graph_frame.get_attribute("data-selected") == "true"
            delete_buttons = page.locator(
                '[data-editor-action="delete"], [data-selection-action="delete"]'
            )
            assert delete_buttons.count() == 2
            assert all(delete_buttons.nth(index).is_disabled() for index in range(2))

            # The lock is an icon toggle repainted by a re-render that can land
            # a frame after the state itself changes, so wait for its state
            # rather than sampling it once.
            sync_api.expect(selection_lock).to_have_attribute("aria-pressed", "true")
            sync_api.expect(selection_lock).to_have_attribute("aria-label", "Unlock selection")

            before_count = page.locator("[data-graph-boundary]").count()
            # The Lock button still has focus, and a focused control owns
            # Delete; this is about the canvas key, so hand focus back.
            page.evaluate("() => document.activeElement.blur()")
            page.keyboard.press("Delete")
            assert page.locator("[data-graph-boundary]").count() == before_count
            assert graph_frame.get_attribute("data-selected") == "true"
            assert "unlock" in page.locator("[data-search-status]").inner_text().casefold()

            selection_lock.click()
            assert graph_frame.get_attribute("data-locked") == "false"
            sync_api.expect(selection_lock).to_have_attribute("aria-pressed", "false")
            assert all(delete_buttons.nth(index).is_enabled() for index in range(2))
            page.locator('[data-editor-action="delete"]').click()
            assert page.locator(f'[data-boundary-id="{frame_id}"]').count() == 0
            assert page.locator("[data-graph-boundary]").count() == before_count - 1
        finally:
            browser.close()


def test_multicloud_custom_palette_builds_nested_aws_foundation_and_preserves_styles(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = both_library_workspace(tmp_path, "multicloud-frame-library")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            page.goto(source.resolve().as_uri())
            _settled(page)
            page.locator('details[data-category-id="custom"] > summary').click()

            custom = page.locator('details[data-category-id="custom"]')
            assert custom.locator('[data-component-section="basic-elements"]').count() == 1
            frames = custom.locator('[data-component-section="architecture-frames"]')
            assert frames.count() == 1
            assert frames.get_attribute("open") is not None
            assert custom.locator('[data-component-section="provider-services"]').count() == 1
            # Core frames plus one group per library that defines frames.
            assert custom.locator("details.frame-group").count() == len(
                ARCHITECTURE_BOUNDARY_GROUPS
            )
            azure_group = custom.locator('details.frame-group[data-frame-group="azure"]')
            _open_frame_group(page, "azure")
            assert azure_group.get_attribute("open") is not None
            assert azure_group.locator(".frame-card").count() == 11
            # The gallery lists the starter stack's frames first, in stack
            # order, then the rest from the outermost boundary inwards.
            assert azure_group.locator(".frame-card").evaluate_all(
                "cards => cards.map(card => card.dataset.componentId)"
            ) == [
                "custom-boundary-azure-tenant",
                "custom-boundary-azure-management-group",
                "custom-boundary-azure-subscription",
                "custom-boundary-azure-resource-group",
                "custom-boundary-azure-vnet",
                "custom-boundary-azure-subnet",
                "custom-boundary-azure-cloud",
                "custom-boundary-azure-region",
                "custom-boundary-azure-zone",
                "custom-boundary-azure-public-subnet",
                "custom-boundary-azure-aks",
            ]
            assert custom.locator(".component-card:visible").count() == 11
            preset = azure_group.locator('[data-frame-preset="azure-landing-zone"]')
            assert preset.count() == 1
            assert "Azure landing zone starter" in preset.inner_text()
            assert "Site-to-Site" not in preset.inner_text()
            page.screenshot(path=str(tmp_path / "multicloud-organized-frame-library.png"))

            preset.click()

            state = page.evaluate("() => window.infragramEditor.getState()")
            added = {
                boundary["kind"]: boundary
                for boundary in state["boundaries"]
                if boundary.get("frameGroup") == "azure"
            }
            assert len(added) == 6
            assert added["organization"]["parentId"] is None
            assert added["management-group"]["parentId"] == added["organization"]["id"]
            assert added["subscription"]["parentId"] == added["management-group"]["id"]
            assert added["resource-group"]["parentId"] == added["subscription"]["id"]
            assert added["network"]["parentId"] == added["resource-group"]["id"]
            assert added["subnet-private"]["parentId"] == added["network"]["id"]
            for parent_kind, child_kind in (
                ("organization", "management-group"),
                ("management-group", "subscription"),
                ("subscription", "resource-group"),
                ("resource-group", "network"),
                ("network", "subnet-private"),
            ):
                parent = added[parent_kind]
                child = added[child_kind]
                pad = parent["pad"]
                assert child["x"] >= parent["x"] + pad - 1
                assert child["y"] >= parent["y"] + pad - 1
                assert child["x"] + child["width"] <= parent["x"] + parent["width"] - pad + 1
                assert child["y"] + child["height"] <= parent["y"] + parent["height"] - pad + 1
            assert added["organization"]["stroke"] == "#005ba1"
            assert added["management-group"]["stroke"] == "#37c2b1"
            assert added["subscription"]["stroke"] == "#ffcb12"
            # the deck draws the tenant dashed
            assert added["organization"]["dash"] == "5,4"
            assert added["network"]["stroke"] == "#1490df"
            assert added["subnet-private"]["stroke"] == "#1490df"
            assert "tenant → management group" in preset.inner_text().casefold()

            rendered_vnet = page.locator(
                f'[data-boundary-id="{added["network"]["id"]}"] [data-boundary-surface]'
            )
            assert rendered_vnet.get_attribute("stroke") == "#1490df"
            exported = page.evaluate("() => window.infragramEditor.exportProject()")
            validated = CloudProject.model_validate(exported)
            exported_vnet = next(
                element
                for element in validated.topology.walk()
                if element.id == added["network"]["id"]
            )
            assert exported_vnet.attributes["editor_frame_group"] == "azure"
            assert exported_vnet.attributes["editor_boundary_style"]["stroke"] == "#1490df"

            page.locator('details[data-category-id="custom"] > summary').click()
            page.locator('[data-editor-action="zoom-fit"]').click()
            page.screenshot(path=str(tmp_path / "multicloud-nested-aws-foundation.png"))
        finally:
            browser.close()


def test_frame_preset_drag_drop_positions_and_moves_nested_stack_as_one(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = both_library_workspace(tmp_path, "multicloud-draggable-frame-preset")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            page.goto(f"{source.resolve().as_uri()}?fresh=1")
            _settled(page)
            page.locator('details[data-category-id="custom"] > summary').click()
            _open_frame_group(page, "azure")
            preset = page.locator('[data-frame-preset="azure-landing-zone"]')
            assert preset.get_attribute("draggable") == "true"

            diagram = page.locator("svg[data-infragram-diagram]")
            preset.drag_to(diagram, target_position={"x": 360, "y": 360})
            state = page.evaluate("() => window.infragramEditor.getState()")
            frames = [frame for frame in state["boundaries"] if frame.get("frameGroup") == "azure"]
            assert len(frames) == 6
            assert frames[0]["parentId"] is None
            for parent, child in zip(frames, frames[1:], strict=False):
                assert child["parentId"] == parent["id"]
            assert frames[0]["x"] + frames[0]["width"] / 2 < state["canvas"]["width"] / 2
            assert (
                page.locator(
                    f'[data-boundary-id="{frames[0]["id"]}"][data-selected="true"]'
                ).count()
                == 1
            )

            before = {frame["id"]: (frame["x"], frame["y"], frame["parentId"]) for frame in frames}
            outer = page.locator(f'[data-graph-boundary][data-boundary-id="{frames[0]["id"]}"]')
            box = outer.bounding_box()
            assert box is not None
            edges_before = len(page.evaluate("() => window.infragramEditor.getState().edges"))
            # Take hold of the frame's own border band, clear of its resize
            # handles: those sit on the corners and the edge midpoints, and
            # catching one resizes the frame instead of moving it.
            start_x = box["x"] + 8
            start_y = box["y"] + box["height"] * 0.75
            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x + 120, start_y + 80, steps=6)
            page.mouse.up()

            moved = {
                frame["id"]: frame
                for frame in page.evaluate(
                    """() => window.infragramEditor.getState().boundaries
                      .filter(frame => frame.frameGroup === 'azure')"""
                )
            }
            deltas = {
                (
                    moved[frame_id]["x"] - position[0],
                    moved[frame_id]["y"] - position[1],
                )
                for frame_id, position in before.items()
            }
            assert len(deltas) == 1
            assert next(iter(deltas)) != (0, 0)
            assert all(
                moved[frame_id]["parentId"] == position[2] for frame_id, position in before.items()
            )
            # Moving frames must not disturb the wiring.
            assert (
                len(page.evaluate("() => window.infragramEditor.getState().edges")) == edges_before
            )
            page.screenshot(path=str(tmp_path / "draggable-azure-foundation-stack.png"))
        finally:
            browser.close()


def test_nested_frame_can_detach_and_accept_an_additional_subnet(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = both_library_workspace(tmp_path, "multicloud-detachable-nested-frame")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            page.goto(f"{source.resolve().as_uri()}?fresh=1")
            _settled(page)
            page.locator('details[data-category-id="custom"] > summary').click()
            _open_frame_group(page, "azure")
            page.locator('[data-frame-preset="azure-landing-zone"]').click()
            page.wait_for_timeout(100)

            initial = page.evaluate("() => window.infragramEditor.getState()")
            aws_frames = [
                frame for frame in initial["boundaries"] if frame.get("frameGroup") == "azure"
            ]
            # The Azure landing zone nests six frames; this test drives the
            # outer five. Their sizes follow from each frame's own default and
            # its parent's padding, so the contract checked here is the
            # containment below, not a pinned pixel size.
            cloud, region, vpc, zone, public_subnet = aws_frames[:5]

            # The hierarchy tree must expose every nested frame for direct selection.
            page.locator('[data-inspector-tab="layers"]').click()
            page.locator(f'[data-frame-select="{vpc["id"]}"]').click()
            assert (
                page.locator(f'[data-boundary-id="{vpc["id"]}"][data-selected="true"]').count() == 1
            )

            # A contextual Detach action moves only the selected frame up one level.
            detach = page.locator('[data-selection-action="detach"]')
            detach.wait_for(state="visible")
            assert detach.is_enabled()
            detach.click()
            detached = page.evaluate("() => window.infragramEditor.getState()")
            by_id = {frame["id"]: frame for frame in detached["boundaries"]}
            assert by_id[vpc["id"]]["parentId"] == cloud["id"]
            assert by_id[zone["id"]]["parentId"] == vpc["id"]
            assert by_id[public_subnet["id"]]["parentId"] == zone["id"]
            assert by_id[region["id"]]["parentId"] == cloud["id"]

            # Mouse hit-testing chooses the deepest visible frame, even where an
            # outer cloud surface overlaps it in the SVG stacking order.
            zone_surface = page.locator(
                f'[data-boundary-id="{zone["id"]}"] [data-boundary-surface]'
            )
            zone_box = zone_surface.bounding_box()
            assert zone_box is not None
            page.mouse.dblclick(
                zone_box["x"] + zone_box["width"] / 2,
                zone_box["y"] + 12,
            )
            selected_frame_ids = page.locator(
                '[data-graph-boundary][data-selected="true"]'
            ).evaluate_all("frames => frames.map(frame => frame.dataset.boundaryId)")
            assert selected_frame_ids == [zone["id"]]

            # The selected Azure child frame can be expanded directly with a
            # visible side handle; its subnet remains nested and fixed.
            resize = page.locator(f'[data-boundary-resize="e"][data-boundary-id="{zone["id"]}"]')
            resize_box = resize.bounding_box()
            assert resize_box is not None
            resize_hit = page.evaluate(
                """point => {
                    const hit = document.elementFromPoint(point.x, point.y)
                    const handle = hit?.closest('[data-boundary-resize]');
                    return handle ? {
                      id: handle.dataset.boundaryId,
                      direction: handle.dataset.boundaryResize,
                    } : {
                      tag: hit?.tagName || null,
                      surface: hit?.hasAttribute('data-boundary-surface') || false,
                      parent: hit?.closest('[data-graph-boundary]')?.dataset.boundaryId || null,
                    };
                }""",
                {
                    "x": resize_box["x"] + resize_box["width"] / 2,
                    "y": resize_box["y"] + resize_box["height"] / 2,
                },
            )
            assert resize_hit == {"id": zone["id"], "direction": "e"}
            page.mouse.move(
                resize_box["x"] + resize_box["width"] / 2,
                resize_box["y"] + resize_box["height"] / 2,
            )
            page.mouse.down()
            page.mouse.move(
                resize_box["x"] + resize_box["width"] / 2 + 80,
                resize_box["y"] + resize_box["height"] / 2,
                steps=6,
            )
            page.mouse.up()
            resized = page.evaluate("() => window.infragramEditor.getState()")
            resized_by_id = {frame["id"]: frame for frame in resized["boundaries"]}
            # The landing zone nests each frame flush inside its parent, so an
            # outward drag is clamped at the parent's inner edge instead of
            # growing the stack; the frame keeps its left edge and its child.
            assert resized_by_id[zone["id"]]["width"] <= zone["width"] + 1
            assert resized_by_id[zone["id"]]["x"] == zone["x"]
            assert resized_by_id[public_subnet["id"]]["parentId"] == zone["id"]
            assert (
                resized_by_id[public_subnet["id"]]["x"],
                resized_by_id[public_subnet["id"]]["y"],
            ) == (public_subnet["x"], public_subnet["y"])

            # Individual frame cards remain draggable, so another subnet can be
            # dropped into an existing availability-zone frame.
            private_card = page.locator('[data-component-id="custom-boundary-azure-subnet"]')
            assert private_card.get_attribute("draggable") == "true"
            private_id = page.evaluate(
                """zone => window.infragramEditor.addBoundary({
                    id: 'custom-boundary-azure-subnet',
                    qualifiedId: 'infragram:custom-boundary-azure-subnet',
                    provider: 'infragram',
                    name: 'Azure subnet',
                    componentKind: 'boundary',
                    boundaryKind: 'subnet-private',
                    frameGroup: 'azure',
                    defaultSize: {width: 256, height: 144},
                  }, {
                    x: zone.x + zone.width - 20,
                    y: zone.y + zone.height - 20,
                  })""",
                resized_by_id[zone["id"]],
            )
            updated = page.evaluate("() => window.infragramEditor.getState()")
            private_subnets = [
                frame for frame in updated["boundaries"] if frame["kind"] == "subnet-private"
            ]
            # The landing zone already lays one subnet down, so the one added
            # here is the second; what this checks is where it landed.
            added_subnet = next(frame for frame in private_subnets if frame["id"] == private_id)
            assert added_subnet["parentId"] == zone["id"]

            # Standalone/nested frame components expose the same eight mouse
            # resize handles as starter-foundation frames. Shrink the private
            # subnet from its southeast corner so it remains inside the parent.
            page.locator(f'[data-frame-select="{private_id}"]').click()
            assert (
                page.locator(f'[data-boundary-resize][data-boundary-id="{private_id}"]').count()
                == 8
            )
            southeast = page.locator(
                f'[data-boundary-resize="se"][data-boundary-id="{private_id}"]'
            )
            southeast.scroll_into_view_if_needed()
            southeast_box = southeast.bounding_box()
            assert southeast_box is not None
            assert page.evaluate(
                """point => {
                    const hit = document.elementFromPoint(point.x, point.y);
                    return {
                      direction: hit?.closest('[data-boundary-resize]')?.dataset.boundaryResize || null,
                      boundary: hit?.closest('[data-graph-boundary]')?.dataset.boundaryId || null,
                      tag: hit?.tagName || null,
                    };
                }""",
                {
                    "x": southeast_box["x"] + southeast_box["width"] / 2,
                    "y": southeast_box["y"] + southeast_box["height"] / 2,
                },
            ) == {"direction": "se", "boundary": private_id, "tag": "rect"}
            page.mouse.move(
                southeast_box["x"] + southeast_box["width"] / 2,
                southeast_box["y"] + southeast_box["height"] / 2,
            )
            page.mouse.down()
            page.mouse.move(
                southeast_box["x"] + southeast_box["width"] / 2 - 48,
                southeast_box["y"] + southeast_box["height"] / 2 - 24,
                steps=5,
            )
            page.mouse.up()
            resized_private = next(
                frame
                for frame in page.evaluate("() => window.infragramEditor.getState().boundaries")
                if frame["id"] == private_id
            )
            assert resized_private["x"] == added_subnet["x"]
            assert resized_private["y"] == added_subnet["y"]
            assert resized_private["width"] < added_subnet["width"]
            assert resized_private["height"] < added_subnet["height"]
            assert resized_private["parentId"] == zone["id"]
            page.screenshot(path=str(tmp_path / "nested-frame-detach-and-add-subnet.png"))
        finally:
            browser.close()


def test_multicloud_fit_reframes_content_after_sidebar_layout_changes(tmp_path: Path) -> None:
    # the fit frames the cards, the frames and the brand mark under them
    sync_api = pytest.importorskip("playwright.sync_api")
    source = both_library_workspace(tmp_path, "multicloud-responsive-fit")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            page.goto(source.resolve().as_uri())
            _settled(page)
            page.locator('[data-editor-action="zoom-fit"]').click()
            page.evaluate("() => window.infragramEditor.whenSettled()")

            before = page.evaluate(
                """() => ({
                    zoom: Number(document.querySelector('[data-zoom-value]').textContent.replace('%', '')),
                    viewportWidth: document.querySelector('.canvas-viewport').clientWidth,
                })"""
            )
            page.locator("[data-sidebar-logo-trigger]").click()
            # Wait for the state the assertions describe, not for a fixed
            # time: a slow machine finishes the grid transition and the refit
            # later than a fast one, and the end state is what is promised.
            page.wait_for_function(
                """() => {
                    // The grid transition reports interpolated columns until it
                    // ends; the collapsed layout is the one the assertions are
                    // about, so wait for its final 56 px column first.
                    const columns = getComputedStyle(document.querySelector('.workspace')).gridTemplateColumns;
                    if (!columns.startsWith('56px')) return false;
                    const viewport = document.querySelector('.canvas-viewport');
                    const viewportRect = viewport.getBoundingClientRect();
                    const items = [...document.querySelectorAll(
                      '[data-graph-node],[data-graph-boundary],[data-brand-mark]'
                    )].map(item => item.getBoundingClientRect());
                    if (!items.length) return false;
                    const left = Math.min(...items.map(item => item.left));
                    const right = Math.max(...items.map(item => item.right));
                    const top = Math.min(...items.map(item => item.top));
                    const bottom = Math.max(...items.map(item => item.bottom));
                    return Math.abs((left + right) / 2 - (viewportRect.left + viewportRect.right) / 2) < 8
                      && Math.abs((top + bottom) / 2 - (viewportRect.top + viewportRect.bottom) / 2) < 8;
                }""",
                timeout=8000,
            )
            # The wait above saw the collapsed layout centred once; the refit the
            # transition end asks for may still be two frames from landing on a
            # slow machine. Read the end state only once no fit is pending, and
            # only when it is still.
            read_state = """() => {
                    const viewport = document.querySelector('.canvas-viewport');
                    const viewportRect = viewport.getBoundingClientRect();
                    const items = [...document.querySelectorAll(
                      '[data-graph-node],[data-graph-boundary],[data-brand-mark]'
                    )].map(item => item.getBoundingClientRect());
                    const left = Math.min(...items.map(item => item.left));
                    const right = Math.max(...items.map(item => item.right));
                    const top = Math.min(...items.map(item => item.top));
                    const bottom = Math.max(...items.map(item => item.bottom));
                    return {
                      zoom: Number(document.querySelector('[data-zoom-value]').textContent.replace('%', '')),
                      viewportWidth: viewport.clientWidth,
                      contentCenter: (left + right) / 2,
                      viewportCenter: (viewportRect.left + viewportRect.right) / 2,
                      contentMiddle: (top + bottom) / 2,
                      viewportMiddle: (viewportRect.top + viewportRect.bottom) / 2,
                    };
                }"""
            for _attempt in range(20):
                page.evaluate("() => window.infragramEditor.whenSettled()")
                after = page.evaluate(read_state)
                centred = (
                    abs(after["contentCenter"] - after["viewportCenter"]) < 8
                    and abs(after["contentMiddle"] - after["viewportMiddle"]) < 8
                )
                if centred:
                    break
                page.wait_for_timeout(50)

            assert after["viewportWidth"] > before["viewportWidth"] + 250
            # Collapsing the sidebar widens the viewport, so a refit can only
            # zoom in; how far depends on how much this canvas carries, and
            # the contract is the reframing, checked by the centring below.
            assert after["zoom"] >= before["zoom"]
            assert abs(after["contentCenter"] - after["viewportCenter"]) < 8
            assert abs(after["contentMiddle"] - after["viewportMiddle"]) < 8
            page.screenshot(path=str(tmp_path / "multicloud-responsive-fit.png"))
        finally:
            browser.close()


def test_service_nodes_resize_with_mouse_and_keep_edges_attached(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    # This one needs a canvas whose nodes already carry edges, so the resize
    # can be checked to keep them attached.
    source = tmp_path / "multicloud-node-resize.html"
    source.write_text(render_project_html(multicloud_layer_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            page.goto(f"{source.resolve().as_uri()}?fresh=1")
            _settled(page)
            node = page.locator('[data-graph-node][data-node-id="gateway"]')
            surface = node.locator("[data-node-surface]")
            box = surface.bounding_box()
            assert box is not None
            page.mouse.dblclick(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            assert page.locator('[data-node-resize][data-resize-node-id="gateway"]').count() == 3

            before = page.evaluate("() => window.infragramEditor.getState()")
            before_node = next(item for item in before["nodes"] if item["id"] == "gateway")
            edge = next(item for item in before["edges"] if item["source"] == "gateway")
            before_path = page.locator(
                f'[data-graph-edge][data-edge-id="{edge["id"]}"]'
            ).get_attribute("d")

            east = page.locator('[data-node-resize="e"][data-resize-node-id="gateway"]')
            east_box = east.bounding_box()
            assert east_box is not None
            page.mouse.move(
                east_box["x"] + east_box["width"] / 2,
                east_box["y"] + east_box["height"] / 2,
            )
            page.mouse.down()
            page.mouse.move(
                east_box["x"] + east_box["width"] / 2 + 80,
                east_box["y"] + east_box["height"] / 2,
                steps=6,
            )
            page.mouse.up()

            after = page.evaluate("() => window.infragramEditor.getState()")
            after_node = next(item for item in after["nodes"] if item["id"] == "gateway")
            after_path = page.locator(
                f'[data-graph-edge][data-edge-id="{edge["id"]}"]'
            ).get_attribute("d")
            assert after_node["x"] == before_node["x"]
            assert after_node["height"] == before_node["height"]
            assert after_node["width"] > before_node["width"]
            assert len(after["edges"]) == len(before["edges"])
            assert after_path != before_path
            page.screenshot(path=str(tmp_path / "multicloud-node-resize.png"))
        finally:
            browser.close()


def test_every_provider_starter_builds_a_clean_nested_frame_chain(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = both_library_workspace(tmp_path, "all-provider-frame-starters")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for preset in ARCHITECTURE_FRAME_PRESETS:
                context = browser.new_context(viewport={"width": 1500, "height": 960})
                page = context.new_page()
                page.goto(source.resolve().as_uri())
                _settled(page)
                page.locator('details[data-category-id="custom"] > summary').click()
                group = page.locator(f'details.frame-group[data-frame-group="{preset["group"]}"]')
                if group.get_attribute("open") is None:
                    group.locator("> summary").click()
                group.locator(f'[data-frame-preset="{preset["id"]}"]').click()

                state = page.evaluate("() => window.infragramEditor.getState()")
                frames = [
                    boundary
                    for boundary in state["boundaries"]
                    if boundary.get("frameGroup") == preset["group"]
                ]
                assert len(frames) == len(preset["componentIds"]), preset["id"]
                assert frames[0]["parentId"] is None
                if preset["id"] != "azure-landing-zone":
                    assert all(frame.get("editableFoundation") is True for frame in frames), preset[
                        "id"
                    ]
                page.locator('[data-inspector-tab="layers"]').click()
                editable_frame = frames[-2] if len(frames) > 1 else frames[0]
                page.locator(f'[data-frame-select="{editable_frame["id"]}"]').click()
                assert (
                    page.locator(
                        f'[data-boundary-resize][data-boundary-id="{editable_frame["id"]}"]'
                    ).count()
                    == 8
                ), preset["id"]
                if preset.get("layout") == "detached":
                    assert all(frame["parentId"] is None for frame in frames)
                    assert len({(frame["x"], frame["y"]) for frame in frames}) == len(frames)
                    context.close()
                    continue
                placements = preset.get("framePlacements")
                expected_pairs = (
                    [
                        (frames[placement["parentIndex"]], frames[index])
                        for index, placement in enumerate(placements)
                        if placement.get("parentIndex") is not None
                    ]
                    if placements
                    else list(zip(frames, frames[1:], strict=False))
                )
                for parent, child in expected_pairs:
                    assert child["parentId"] == parent["id"], preset["id"]
                    pad = parent.get("pad", 0)
                    assert child["x"] >= parent["x"] + pad - 1, preset["id"]
                    assert child["y"] >= parent["y"] + pad - 1, preset["id"]
                    assert child["x"] + child["width"] <= (
                        parent["x"] + parent["width"] - pad + 1
                    ), preset["id"]
                    assert child["y"] + child["height"] <= (
                        parent["y"] + parent["height"] - pad + 1
                    ), preset["id"]
                if preset.get("nodes"):
                    expected_node_ids = [node["qualifiedId"] for node in preset["nodes"]]
                    rendered_nodes = [
                        node
                        for node in state["nodes"]
                        if node["componentQualifiedId"] in expected_node_ids
                    ]
                    assert len(rendered_nodes) == len(expected_node_ids)
                    for placement in preset["nodes"]:
                        matches = [
                            node
                            for node in rendered_nodes
                            if node["componentQualifiedId"] == placement["qualifiedId"]
                        ]
                        assert matches
                        expected_boundary_id = (
                            frames[placement["parentFrameIndex"]]["id"]
                            if placement.get("parentFrameIndex") is not None
                            else None
                        )
                        assert all(node["boundaryId"] == expected_boundary_id for node in matches)
                    if preset.get("connections"):
                        rendered_node_ids = {node["id"] for node in rendered_nodes}
                        rendered_connections = [
                            edge
                            for edge in state["edges"]
                            if edge["source"] in rendered_node_ids
                            and edge["target"] in rendered_node_ids
                        ]
                        assert len(rendered_connections) == len(preset["connections"])
                        assert {edge["label"] for edge in rendered_connections} == {
                            connection["label"] for connection in preset["connections"]
                        }
                if preset["id"] in {"azure-landing-zone", "kubernetes-workload"}:
                    page.locator('[data-editor-action="zoom-fit"]').click()
                    page.screenshot(path=str(tmp_path / f"{preset['id']}-validated.png"))
                context.close()
        finally:
            browser.close()


def test_starter_nodes_support_content_editing_and_card_or_icon_display(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = both_library_workspace(tmp_path, "editable-starter-node-modes")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(f"{source.resolve().as_uri()}?fresh=1")
            _settled(page)
            page.locator('details[data-category-id="custom"] > summary').click()
            group = page.locator('details.frame-group[data-frame-group="kubernetes"]')
            if group.get_attribute("open") is None:
                group.locator("> summary").click()
            group.locator('[data-frame-preset="kubernetes-workload"]').click()

            # The Kubernetes starter lays down frames and no components, so
            # the node this test edits is dragged in from the library.
            page.locator("[data-sidebar-search]").fill("Pod")
            page.locator('.component-card[data-component-id="pod"]:visible').first.drag_to(
                page.locator("svg[data-infragram-diagram]"),
                target_position={"x": 700, "y": 460},
            )
            node_id = page.evaluate("() => window.infragramEditor.getState().nodes.at(-1).id")
            page.locator(f'[data-node-id="{node_id}"]').click()
            page.locator('[data-inspector-tab="text"]').click()
            name = page.get_by_label("Name", exact=True)
            detail = page.get_by_label("Description")
            assert name.input_value() == "Pod"

            name.fill("Ingress pod")
            name.press("Enter")
            detail.fill("rollout of the web front end")
            detail.press("Enter")
            state = page.evaluate("() => window.infragramEditor.getState()")
            edited = next(item for item in state["nodes"] if item["id"] == node_id)
            assert edited["name"] == "Ingress pod"
            assert edited["detail"] == "rollout of the web front end"

            card_before = next(
                item
                for item in page.evaluate("() => window.infragramEditor.getState()")["nodes"]
                if item["id"] == node_id
            )
            page.locator('[data-inspector-tab="style"]').click()
            page.get_by_role("button", name="Icon only").click()
            icon_state = page.evaluate("() => window.infragramEditor.getState()")
            icon_node = next(item for item in icon_state["nodes"] if item["id"] == node_id)
            assert icon_node["displayMode"] == "icon"
            assert icon_node["height"] == 116 and icon_node["width"] >= 144
            assert (
                page.locator(f'[data-node-id="{node_id}"]').get_attribute("data-display-mode")
                == "icon"
            )

            page.get_by_role("button", name="Card with text").click()
            card_state = page.evaluate("() => window.infragramEditor.getState()")
            card_node = next(item for item in card_state["nodes"] if item["id"] == node_id)
            assert card_node["displayMode"] == "card"
            # Back to the size the card had before the icon round trip.
            assert (card_node["width"], card_node["height"]) == (
                card_before["width"],
                card_before["height"],
            )
            page.screenshot(path=str(tmp_path / "editable-card-icon-modes.png"))
        finally:
            browser.close()


def test_right_click_menu_exposes_applicable_actions_for_nodes_and_frames(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = both_library_workspace(tmp_path, "canvas-context-menu")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(f"{source.resolve().as_uri()}?fresh=1")
            _settled(page)
            page.locator('details[data-category-id="custom"] > summary').click()
            group = page.locator('details.frame-group[data-frame-group="kubernetes"]')
            if group.get_attribute("open") is None:
                group.locator("> summary").click()
            group.locator('[data-frame-preset="kubernetes-workload"]').click()

            # The starter lays down frames and no components, so the node the
            # menu acts on is dragged in from the library.
            page.locator("[data-sidebar-search]").fill("Pod")
            page.locator('.component-card[data-component-id="pod"]:visible').first.drag_to(
                page.locator("svg[data-infragram-diagram]"),
                target_position={"x": 700, "y": 460},
            )
            node_id = page.evaluate("() => window.infragramEditor.getState().nodes.at(-1).id")
            page.locator(f'[data-node-id="{node_id}"]').click(button="right")
            menu = page.get_by_role("menu", name="Canvas actions")
            assert menu.is_visible()
            assert menu.get_by_role("menuitem", name="Edit text").is_visible()
            menu.locator("[data-context-submenu-toggle]").click()
            menu.get_by_role("menuitemcheckbox", name="Icon only").click()
            state = page.evaluate("() => window.infragramEditor.getState()")
            node = next(item for item in state["nodes"] if item["id"] == node_id)
            assert node["displayMode"] == "icon"

            page.locator(f'[data-node-id="{node_id}"]').click(button="right")
            menu.locator("[data-context-submenu-toggle]").click()
            menu.get_by_role("menuitemcheckbox", name="Card with text").click()
            state = page.evaluate("() => window.infragramEditor.getState()")
            node = next(item for item in state["nodes"] if item["id"] == node_id)
            assert node["displayMode"] == "card"

            # A frame is a boundary, not a card, so it offers no display mode.
            frame_id = page.evaluate(
                """() => window.infragramEditor.getState().boundaries
                     .find(frame => frame.frameGroup === 'kubernetes').id"""
            )
            # The frame's centre is covered by the frames nested inside it, and
            # its top-left corner is covered by its own badge tab, so aim just
            # below the badge and inside the border.
            page.locator(f'[data-boundary-id="{frame_id}"] [data-boundary-surface]').click(
                button="right", position={"x": 8, "y": 30}
            )
            assert menu.get_by_role("menuitemcheckbox", name="Icon only").is_hidden()
            menu.get_by_role("menuitem", name="Edit text").click()
            assert (
                page.locator('[data-inspector-tab="text"]').get_attribute("aria-selected") == "true"
            )
            assert page.get_by_label("Name", exact=True).input_value() == "Kubernetes cluster"
        finally:
            browser.close()


def test_dragging_a_nested_frame_out_detaches_one_level_and_keeps_children_aligned(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = both_library_workspace(tmp_path, "nested-frame-detach")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(source.resolve().as_uri())
            _settled(page)
            ids = page.evaluate(
                """() => {
                    const library = window.infragramEditor.getLibraryCatalog();
                    const frame = id => library.components.find(item => item.serviceId === id);
                    const cloudDefinition = frame('custom-boundary-cloud');
                    const cloud = window.infragramEditor.addBoundary(
                      {...cloudDefinition, defaultSize: {width: 1000, height: 700}},
                      {x: 1100, y: 800}
                    );
                    const vpc = window.infragramEditor.addBoundary(
                      frame('custom-boundary-azure-vnet'), {x: 1100, y: 800}
                    );
                    const subnet = window.infragramEditor.addBoundary(
                      frame('custom-boundary-azure-subnet'), {x: 1100, y: 800}
                    );
                    const lambda = library.components.find(
                      item => item.qualifiedId === 'azure:function-apps'
                    );
                    const node = window.infragramEditor.addNode(lambda, {x: 1100, y: 800});
                    return {cloud, vpc, subnet, node};
                }"""
            )
            page.locator('[data-editor-action="zoom-fit"]').click()
            before = page.evaluate("() => window.infragramEditor.getState()")
            before_frame = next(
                boundary for boundary in before["boundaries"] if boundary["id"] == ids["subnet"]
            )
            before_node = next(node for node in before["nodes"] if node["id"] == ids["node"])
            relative = (
                before_node["x"] - before_frame["x"],
                before_node["y"] - before_frame["y"],
            )

            surface = page.locator(f'[data-boundary-id="{ids["subnet"]}"] [data-boundary-surface]')
            cloud_surface = page.locator(
                f'[data-boundary-id="{ids["cloud"]}"] [data-boundary-surface]'
            )
            box = surface.bounding_box()
            cloud_box = cloud_surface.bounding_box()
            viewport = page.locator(".canvas-viewport").bounding_box()
            assert box is not None and cloud_box is not None and viewport is not None
            hit = page.evaluate(
                """id => {
                    const surface = document.querySelector(
                      '[data-boundary-id="' + id + '"] [data-boundary-surface]'
                    );
                    const rect = surface.getBoundingClientRect();
                    for (let y = rect.bottom - 8; y >= rect.top + 8; y -= 10) {
                      for (let x = rect.left + 8; x <= rect.right - 8; x += 10) {
                        const element = document.elementFromPoint(x, y);
                        if (element?.closest('[data-graph-boundary]')?.dataset.boundaryId === id
                            && !element.closest('[data-graph-node]')) {
                          return {x, y};
                        }
                      }
                    }
                    return null;
                }""",
                ids["subnet"],
            )
            assert hit is not None
            page.mouse.move(hit["x"], hit["y"])
            page.mouse.down()
            page.mouse.move(
                cloud_box["x"] + 20 + hit["x"] - box["x"],
                cloud_box["y"] + 40 + hit["y"] - box["y"],
                steps=8,
            )
            page.mouse.up()

            after = page.evaluate("() => window.infragramEditor.getState()")
            cloud = next(
                boundary for boundary in after["boundaries"] if boundary["id"] == ids["cloud"]
            )
            frame = next(
                boundary for boundary in after["boundaries"] if boundary["id"] == ids["subnet"]
            )
            vpc = next(boundary for boundary in after["boundaries"] if boundary["id"] == ids["vpc"])
            node = next(node for node in after["nodes"] if node["id"] == ids["node"])
            assert frame["parentId"] == cloud["id"], {
                "before": (before_frame["x"], before_frame["y"], before_frame["parentId"]),
                "after": (frame["x"], frame["y"], frame["parentId"]),
                "cloud": (cloud["x"], cloud["y"], cloud["width"], cloud["height"]),
                "viewport": viewport,
                "surface": box,
            }
            assert node["boundaryId"] == frame["id"]
            assert (
                node["x"] - frame["x"],
                node["y"] - frame["y"],
            ) == relative
            pad = cloud.get("pad", 0)
            assert frame["x"] >= cloud["x"] + pad - 1
            assert frame["y"] >= cloud["y"] + pad - 1
            assert frame["x"] + frame["width"] <= cloud["x"] + cloud["width"] - pad + 1
            assert frame["y"] + frame["height"] <= cloud["y"] + cloud["height"] - pad + 1
            assert (
                frame["x"] + frame["width"] <= vpc["x"]
                or vpc["x"] + vpc["width"] <= frame["x"]
                or frame["y"] + frame["height"] <= vpc["y"]
                or vpc["y"] + vpc["height"] <= frame["y"]
            )
            page.screenshot(path=str(tmp_path / "nested-frame-detach-validated.png"))
        finally:
            browser.close()


def test_editor_png_export_keeps_the_diagram_background_transparent(tmp_path: Path) -> None:
    image_module = pytest.importorskip("PIL.Image")
    source = tmp_path / "editor.html"
    output = tmp_path / "diagram.png"
    source.write_text(render_project_html(project()), encoding="utf-8")

    playwright_png_renderer(source, output, 1)

    with image_module.open(output) as image:
        assert image.mode == "RGBA"
        assert image.getextrema()[3][0] == 0
        assert not any(
            red == 41 and green == 43 and blue == 47 and alpha > 0
            for red, green, blue, alpha in getattr(image, "get_flattened_data", image.getdata)()
        )


def test_a_high_degree_node_meets_every_wire_on_a_side_at_one_point(tmp_path: Path) -> None:
    """ADR 0006, rule 3: ten wires leaving one side share that side's one
    connection point instead of fanning along the edge like a circuit board;
    they still reach ten separate targets."""
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "high-degree-editor.html"
    source.write_text(render_project_html(project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri())
            _settled(page)
            page.evaluate(
                """() => {
                    for (let index = 0; index < 10; index += 1) {
                        const id = window.infragramEditor.addNode(
                            {id: `target-${index}`, name: `Target ${index}`, detail: 'stress', category: 'custom'},
                            {x: 760, y: 80 + index * 48}
                        );
                        window.infragramEditor.connect('api', id, 'right', 'left');
                    }
                }"""
            )

            ends = page.locator("[data-graph-edge]").evaluate_all(
                """elements => elements.map(element => [
                    Number(element.dataset.sourceX), Number(element.dataset.sourceY),
                    Number(element.dataset.targetX), Number(element.dataset.targetY),
                ])"""
            )
            assert len(ends) == 10
            assert len({(sx, sy) for sx, sy, _, _ in ends}) == 1, (
                "every wire leaves from the one right-side point"
            )
            assert len({(tx, ty) for _, _, tx, ty in ends}) == 10, "and each reaches its own target"
            assert page.locator("[data-edge-terminal]").count() == 20
        finally:
            browser.close()


def test_multicloud_layers_control_visibility_locking_and_export_without_data_loss(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "multicloud-layers.html"
    source.write_text(render_project_html(multicloud_layer_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri())
            _settled(page)

            state = page.evaluate("() => window.infragramEditor.getState()")
            assert state["schemaVersion"] == 3
            assert state["providers"] == ["azure", "kubernetes"]
            assert [node["layerId"] for node in state["nodes"]] == [
                "provider:azure",
                "platform:kubernetes",
                "provider:azure",
            ]

            library = page.evaluate("() => window.infragramEditor.getLibraryCatalog()")
            artwork = {
                component["qualifiedId"]: component["iconUri"]
                for component in library["components"]
            }
            nodes = {node["id"]: node for node in state["nodes"]}
            assert nodes["worker"]["iconUri"] == artwork["kubernetes:pod"]
            assert nodes["database"]["iconUri"] == artwork["azure:sql-database"]

            page.locator('[data-inspector-tab="layers"]').click()
            page.locator('[data-layer-visible="platform:kubernetes"]').uncheck()
            assert page.locator('[data-node-id="worker"]').count() == 0
            hidden_state = page.evaluate("() => window.infragramEditor.getState()")
            assert len(hidden_state["nodes"]) == 3
            assert (
                next(
                    layer
                    for layer in hidden_state["layers"]
                    if layer["id"] == "platform:kubernetes"
                )["visible"]
                is False
            )
            page.locator('[data-layer-visible="platform:kubernetes"]').check()
            assert page.locator('[data-node-id="worker"]').count() == 1

            page.locator('[data-layer-lock="platform:kubernetes"]').click()
            before = page.evaluate(
                "() => window.infragramEditor.getState().nodes.find(node => node.id === 'worker')"
            )
            worker = page.locator('[data-node-id="worker"]')
            box = worker.bounding_box()
            assert box is not None
            page.mouse.move(box["x"] + 20, box["y"] + 20)
            page.mouse.down()
            page.mouse.move(box["x"] + 100, box["y"] + 76)
            page.mouse.up()
            after = page.evaluate(
                "() => window.infragramEditor.getState().nodes.find(node => node.id === 'worker')"
            )
            assert (after["x"], after["y"]) == (before["x"], before["y"])

            exported = page.evaluate("() => window.infragramEditor.exportProject()")
            validated = CloudProject.model_validate(exported)
            assert validated.topology.index()["worker"].layer_id == "platform:kubernetes"
            assert (
                next(layer for layer in exported["layers"] if layer["id"] == "platform:kubernetes")[
                    "locked"
                ]
                is True
            )
        finally:
            browser.close()


def test_multiselect_arrange_exact_fields_alignment_guides_and_alt_snap_bypass(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "multicloud-arrange.html"
    source.write_text(render_project_html(multicloud_layer_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri())
            _settled(page)

            page.locator('[data-node-id="gateway"]').dblclick()
            page.locator('[data-node-id="worker"]').click(modifiers=["Shift"])
            page.locator('[data-node-id="database"]').click(modifiers=["Shift"])
            assert page.locator('[data-graph-node][data-selected="true"]').count() == 3
            page.locator('[data-inspector-tab="arrange"]').click()
            page.locator('[data-arrange-action="align-top"]').click()
            aligned = page.evaluate(
                "() => window.infragramEditor.getState().nodes.map(node => node.y)"
            )
            assert len(set(aligned)) == 1

            page.locator('[data-node-id="gateway"]').dblclick()
            page.locator('[data-inspector-tab="arrange"]').click()
            x_field = page.locator('[data-exact-field="x"]')
            x_field.fill("124")
            x_field.press("Enter")
            gateway = page.evaluate(
                "() => window.infragramEditor.getState().nodes.find(node => node.id === 'gateway')"
            )
            assert gateway["x"] == 124

            node = page.locator('[data-node-id="gateway"] [data-node-surface]')
            box = node.bounding_box()
            assert box is not None
            page.mouse.move(box["x"] + 24, box["y"] + 24)
            page.mouse.down()
            page.mouse.move(box["x"] + 111, box["y"] + 24)
            assert page.locator("[data-alignment-guide]").count() >= 1
            page.mouse.up()
            assert page.locator("[data-alignment-guide]").count() == 0

            before_alt = page.evaluate(
                "() => window.infragramEditor.getState().nodes.find(node => node.id === 'gateway')"
            )
            moved = page.locator('[data-node-id="gateway"] [data-node-surface]')
            moved_box = moved.bounding_box()
            assert moved_box is not None
            page.keyboard.down("Alt")
            page.mouse.move(moved_box["x"] + 24, moved_box["y"] + 24)
            page.mouse.down()
            page.mouse.move(moved_box["x"] + 31, moved_box["y"] + 29)
            page.mouse.up()
            page.keyboard.up("Alt")
            after_alt = page.evaluate(
                "() => window.infragramEditor.getState().nodes.find(node => node.id === 'gateway')"
            )
            assert (after_alt["x"] - before_alt["x"]) % 4 != 0 or (
                after_alt["y"] - before_alt["y"]
            ) % 4 != 0
        finally:
            browser.close()


def test_frame_alignment_distribution_and_zoom_preserve_contained_geometry(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "frame-alignment-and-zoom.html"
    source.write_text(render_project_html(multicloud_layer_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(source.resolve().as_uri())
            _settled(page)

            ids = page.evaluate(
                """() => {
                    const library = window.infragramEditor.getLibraryCatalog();
                    const frame = library.components.find(
                      item => item.serviceId === 'custom-boundary-azure-vnet'
                    );
                    const service = library.components.find(
                      item => item.qualifiedId === 'azure:function-apps'
                    );
                    const centers = [
                      {x: 500, y: 500},
                      {x: 1300, y: 900},
                      {x: 2300, y: 650},
                    ];
                    const frames = [];
                    const nodes = [];
                    centers.forEach(point => {
                      frames.push(window.infragramEditor.addBoundary(frame, point));
                      nodes.push(window.infragramEditor.addNode(service, point));
                    });
                    window.infragramEditor.connect(nodes[0], nodes[1], 'right', 'left');
                    window.infragramEditor.connect(nodes[1], nodes[2], 'right', 'left');
                    return {frames, nodes};
                }"""
            )
            page.locator('[data-editor-action="zoom-fit"]').click()

            before = page.evaluate("() => window.infragramEditor.getState()")
            before_frames = {
                frame["id"]: frame for frame in before["boundaries"] if frame["id"] in ids["frames"]
            }
            before_nodes = {
                node["id"]: node for node in before["nodes"] if node["id"] in ids["nodes"]
            }
            relative = {
                node_id: (
                    before_nodes[node_id]["x"] - before_frames[frame_id]["x"],
                    before_nodes[node_id]["y"] - before_frames[frame_id]["y"],
                )
                for frame_id, node_id in zip(ids["frames"], ids["nodes"], strict=True)
            }

            for index, frame_id in enumerate(ids["frames"]):
                surface = page.locator(f'[data-boundary-id="{frame_id}"] [data-boundary-surface]')
                if index:
                    surface.click(position={"x": 8, "y": 8}, modifiers=["Shift"])
                else:
                    surface.dblclick(position={"x": 8, "y": 8})

            page.locator('[data-inspector-tab="arrange"]').click()
            assert page.locator("[data-arrange-selection-kind]").inner_text() == "3 frames selected"
            align = page.locator('[data-arrange-action="align-top"]')
            distribute = page.locator('[data-arrange-action="distribute-horizontal"]')
            assert align.is_enabled()
            assert distribute.is_enabled()
            align.click()
            distribute.click()

            after = page.evaluate("() => window.infragramEditor.getState()")
            after_frames = [frame for frame in after["boundaries"] if frame["id"] in ids["frames"]]
            after_frames.sort(key=lambda frame: frame["x"])
            assert len({frame["y"] for frame in after_frames}) == 1
            horizontal_gaps = [
                after_frames[index + 1]["x"]
                - (after_frames[index]["x"] + after_frames[index]["width"])
                for index in range(2)
            ]
            assert abs(horizontal_gaps[0] - horizontal_gaps[1]) <= 1

            after_frames_by_id = {frame["id"]: frame for frame in after_frames}
            after_nodes = {
                node["id"]: node for node in after["nodes"] if node["id"] in ids["nodes"]
            }
            for frame_id, node_id in zip(ids["frames"], ids["nodes"], strict=True):
                assert after_nodes[node_id]["boundaryId"] == frame_id
                assert (
                    after_nodes[node_id]["x"] - after_frames_by_id[frame_id]["x"],
                    after_nodes[node_id]["y"] - after_frames_by_id[frame_id]["y"],
                ) == relative[node_id]

            arranged_edges = [
                edge
                for edge in after["edges"]
                if edge["source"] in ids["nodes"] and edge["target"] in ids["nodes"]
            ]
            assert len(arranged_edges) == 2
            for edge_state in arranged_edges:
                edge = page.locator(
                    f'[data-graph-edge][data-edge-id="{edge_state["id"]}"]'
                ).evaluate(
                    """edge => ({
                        sourceX: Number(edge.dataset.sourceX),
                        sourceY: Number(edge.dataset.sourceY),
                        targetX: Number(edge.dataset.targetX),
                        targetY: Number(edge.dataset.targetY),
                    })"""
                )
                source_node = after_nodes[edge_state["source"]]
                target_node = after_nodes[edge_state["target"]]
                assert edge == {
                    "sourceX": source_node["x"] + source_node["width"],
                    "sourceY": source_node["y"] + source_node["height"] / 2,
                    "targetX": target_node["x"],
                    "targetY": target_node["y"] + target_node["height"] / 2,
                }

            # An explicitly selected child of a selected frame moves exactly once.
            page.keyboard.press("Escape")
            page.locator(
                f'[data-boundary-id="{ids["frames"][0]}"] [data-boundary-surface]'
            ).dblclick(position={"x": 8, "y": 8})
            page.locator(f'[data-node-id="{ids["nodes"][0]}"]').click(modifiers=["Shift"])
            page.locator(f'[data-boundary-id="{ids["frames"][1]}"] [data-boundary-surface]').click(
                position={"x": 8, "y": 8}, modifiers=["Shift"]
            )
            assert (
                page.locator("[data-arrange-selection-kind]").inner_text()
                == "2 frames + 1 component selected"
            )
            nested_before = page.evaluate("() => window.infragramEditor.getState()")
            frame_before = next(
                frame for frame in nested_before["boundaries"] if frame["id"] == ids["frames"][0]
            )
            node_before = next(
                node for node in nested_before["nodes"] if node["id"] == ids["nodes"][0]
            )
            page.locator('[data-arrange-action="align-left"]').click()
            nested_after = page.evaluate("() => window.infragramEditor.getState()")
            frame_after = next(
                frame for frame in nested_after["boundaries"] if frame["id"] == ids["frames"][0]
            )
            node_after = next(
                node for node in nested_after["nodes"] if node["id"] == ids["nodes"][0]
            )
            assert (
                node_after["x"] - frame_after["x"],
                node_after["y"] - frame_after["y"],
            ) == (
                node_before["x"] - frame_before["x"],
                node_before["y"] - frame_before["y"],
            )

            zoom_value = page.locator("[data-zoom-value]")
            page.locator('[data-editor-action="zoom-reset"]').click()
            assert zoom_value.inner_text() == "100%"
            page.locator('[data-editor-action="zoom-out"]').click()
            assert zoom_value.inner_text() == "90%"
            page.locator('[data-editor-action="zoom-in"]').click()
            assert zoom_value.inner_text() == "100%"
            page.keyboard.press("Control+-")
            assert zoom_value.inner_text() == "90%"
            page.keyboard.press("Control++")
            assert zoom_value.inner_text() == "100%"

            viewport = page.locator(".canvas-viewport")
            viewport_box = viewport.bounding_box()
            assert viewport_box is not None
            page.mouse.move(
                viewport_box["x"] + viewport_box["width"] / 2,
                viewport_box["y"] + viewport_box["height"] / 2,
            )
            # one notch (120 px) zooms by a share of the zoom, not a fixed tenth
            page.mouse.wheel(0, 120)
            assert zoom_value.inner_text() == "85%"
            page.mouse.wheel(0, -120)
            assert zoom_value.inner_text() == "100%"

            # Draw.io-style middle-button panning moves the viewport only. It must
            # never mutate components, frames, terminals, or connected edges.
            geometry_before_pan = page.evaluate(
                """() => {
                    const state = window.infragramEditor.getState();
                    return {nodes: state.nodes, boundaries: state.boundaries, edges: state.edges};
                }"""
            )
            scroll_before = viewport.evaluate(
                """element => {
                    element.scrollLeft = Math.min(500, element.scrollWidth - element.clientWidth);
                    element.scrollTop = Math.min(360, element.scrollHeight - element.clientHeight);
                    return {left: element.scrollLeft, top: element.scrollTop};
                }"""
            )
            page.mouse.move(
                viewport_box["x"] + viewport_box["width"] / 2,
                viewport_box["y"] + viewport_box["height"] / 2,
            )
            page.mouse.down(button="middle")
            assert viewport.get_attribute("data-panning") == "true"
            page.mouse.move(
                viewport_box["x"] + viewport_box["width"] / 2 + 96,
                viewport_box["y"] + viewport_box["height"] / 2 + 72,
            )
            page.mouse.up(button="middle")
            assert viewport.get_attribute("data-panning") is None
            scroll_after = viewport.evaluate(
                "element => ({left: element.scrollLeft, top: element.scrollTop})"
            )
            assert scroll_after["left"] < scroll_before["left"]
            assert scroll_after["top"] < scroll_before["top"]
            assert (
                page.evaluate(
                    """() => {
                    const state = window.infragramEditor.getState();
                    return {nodes: state.nodes, boundaries: state.boundaries, edges: state.edges};
                }"""
                )
                == geometry_before_pan
            )

            for _ in range(9):
                page.keyboard.press("Control+-")
            assert zoom_value.inner_text() == "10%"
            page.locator('[data-editor-action="zoom-fit"]').click()
            page.screenshot(path=str(tmp_path / "frame-alignment-validated.png"))
        finally:
            browser.close()


def test_mobile_canvas_supports_responsive_touch_pan_and_pinch_zoom(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "mobile-canvas.html"
    source.write_text(render_project_html(multicloud_layer_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 390, "height": 844},
            has_touch=True,
            is_mobile=True,
            device_scale_factor=2,
        )
        try:
            page = context.new_page()
            page.goto(f"{source.resolve().as_uri()}?fresh=mobile-contract")
            _settled(page)
            # The compact layout is applied without a transition, but a slow
            # machine may not have laid the page out yet at network idle.
            page.wait_for_function(
                "() => document.querySelector('.canvas-viewport').getBoundingClientRect().width >= 240",
                timeout=8000,
            )

            layout = page.evaluate(
                """() => ({
                    viewportWidth: window.innerWidth,
                    pageWidth: document.documentElement.scrollWidth,
                    workspaceWidth: document.querySelector('.workspace').getBoundingClientRect().width,
                    canvasWidth: document.querySelector('.canvas-viewport').getBoundingClientRect().width,
                })"""
            )
            assert layout["pageWidth"] <= layout["viewportWidth"]
            assert layout["workspaceWidth"] <= layout["viewportWidth"]
            assert layout["canvasWidth"] >= 240

            # A phone's screen is all drawing: no library rail beside it and no
            # inspector under it until something is selected for editing.
            assert not page.locator(".right-inspector").is_visible()
            sidebar = page.locator('[data-testid="provider-sidebar"]')
            sidebar_trigger = page.locator("[data-sidebar-logo-trigger]")
            # the drawer slides; these wait for it to finish sliding
            sidebar_rect = "document.querySelector('[data-testid=\"provider-sidebar\"]').getBoundingClientRect()"
            assert sidebar_trigger.get_attribute("aria-expanded") == "false"
            closed = sidebar.bounding_box()
            assert closed["x"] + closed["width"] <= 0, "the library is off-screen, not a rail"

            # The library is a drawer the toolbar's Components button opens.
            page.locator('[data-editor-action="library"]').click()
            page.wait_for_function(f"() => {sidebar_rect}.left >= 0")
            assert "sidebar-collapsed" not in page.evaluate("() => document.body.className")
            assert sidebar_trigger.get_attribute("aria-expanded") == "true"
            assert sidebar.bounding_box()["width"] >= 300
            assert page.locator("[data-sidebar-search]").is_visible()
            sidebar_trigger.click()
            page.wait_for_function(f"() => {sidebar_rect}.right <= 0")
            assert sidebar_trigger.get_attribute("aria-expanded") == "false"

            # A phone's toolbar is dense: its buttons are 40 px wide, and as
            # tall as a finger needs.
            for action in ("library", "zoom-out", "zoom-in", "zoom-fit"):
                box = page.locator(f'[data-editor-action="{action}"]').bounding_box()
                assert box is not None
                assert box["width"] == 40
                assert box["height"] >= 40

            viewport = page.locator(".canvas-viewport")
            viewport_box = viewport.bounding_box()
            assert viewport_box is not None
            # The phone's toolbar leaves out the 100% button; the shortcut
            # still sets the zoom that makes the drawing wider than the screen.
            page.keyboard.press("Control+0")
            assert page.locator("[data-zoom-value]").inner_text() == "100%"
            page.wait_for_timeout(50)

            geometry_before = page.evaluate(
                """() => {
                    const state = window.infragramEditor.getState();
                    return {nodes: state.nodes, boundaries: state.boundaries, edges: state.edges};
                }"""
            )
            scroll_before = viewport.evaluate(
                """element => {
                    element.scrollLeft = Math.min(560, element.scrollWidth - element.clientWidth);
                    element.scrollTop = Math.min(420, element.scrollHeight - element.clientHeight);
                    return {left: element.scrollLeft, top: element.scrollTop};
                }"""
            )
            assert scroll_before["left"] > 0
            assert scroll_before["top"] > 0

            client = context.new_cdp_session(page)
            pan_x = viewport_box["x"] + viewport_box["width"] * 0.72
            pan_y = viewport_box["y"] + viewport_box["height"] * 0.72
            client.send(
                "Input.dispatchTouchEvent",
                {
                    "type": "touchStart",
                    "touchPoints": [{"x": pan_x, "y": pan_y, "id": 11}],
                },
            )
            client.send(
                "Input.dispatchTouchEvent",
                {
                    "type": "touchMove",
                    "touchPoints": [{"x": pan_x + 72, "y": pan_y + 56, "id": 11}],
                },
            )
            client.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            page.wait_for_timeout(50)
            scroll_after = viewport.evaluate(
                "element => ({left: element.scrollLeft, top: element.scrollTop})"
            )
            assert scroll_after["left"] < scroll_before["left"]
            assert scroll_after["top"] < scroll_before["top"]
            assert (
                page.evaluate(
                    """() => {
                    const state = window.infragramEditor.getState();
                    return {nodes: state.nodes, boundaries: state.boundaries, edges: state.edges};
                }"""
                )
                == geometry_before
            )

            zoom_before = page.locator("[data-zoom-value]").inner_text()
            pinch_scroll_before = viewport.evaluate(
                "element => ({left: element.scrollLeft, top: element.scrollTop})"
            )
            pinch_x = viewport_box["x"] + viewport_box["width"] / 2
            pinch_y = viewport_box["y"] + viewport_box["height"] / 2
            client.send(
                "Input.dispatchTouchEvent",
                {
                    "type": "touchStart",
                    "touchPoints": [
                        {"x": pinch_x - 36, "y": pinch_y, "id": 21},
                        {"x": pinch_x + 36, "y": pinch_y, "id": 22},
                    ],
                },
            )
            client.send(
                "Input.dispatchTouchEvent",
                {
                    "type": "touchMove",
                    "touchPoints": [
                        {"x": pinch_x - 52, "y": pinch_y + 18, "id": 21},
                        {"x": pinch_x + 100, "y": pinch_y + 18, "id": 22},
                    ],
                },
            )
            client.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            page.wait_for_timeout(100)
            assert int(page.locator("[data-zoom-value]").inner_text().rstrip("%")) > int(
                zoom_before.rstrip("%")
            )
            pinch_scroll_after = viewport.evaluate(
                "element => ({left: element.scrollLeft, top: element.scrollTop})"
            )
            assert pinch_scroll_after != pinch_scroll_before
            assert (
                page.evaluate(
                    """() => {
                    const state = window.infragramEditor.getState();
                    return {nodes: state.nodes, boundaries: state.boundaries, edges: state.edges};
                }"""
                )
                == geometry_before
            )
            page.screenshot(path=str(tmp_path / "mobile-touch-validated.png"))
        finally:
            context.close()
            browser.close()


def test_frames_multiselect_marquee_z_order_group_detach_lock_and_focus_highlight(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "multicloud-selection-arrange.html"
    source.write_text(render_project_html(multicloud_layer_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(source.resolve().as_uri())
            _settled(page)

            # A contain-mode marquee selects all three visible nodes and shows one set bbox.
            boxes = page.locator("[data-graph-node]").evaluate_all(
                "nodes => nodes.map(node => { const r = node.getBoundingClientRect(); return {left:r.left,top:r.top,right:r.right,bottom:r.bottom}; })"
            )
            start_x = min(box["left"] for box in boxes) - 8
            start_y = min(box["top"] for box in boxes) - 8
            end_x = max(box["right"] for box in boxes) + 8
            end_y = max(box["bottom"] for box in boxes) + 8
            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(end_x, end_y, steps=6)
            assert page.locator("[data-marquee-selection]").count() == 1
            page.mouse.up()
            assert page.locator('[data-graph-node][data-selected="true"]').count() == 3
            assert page.locator("[data-selection-bbox]").count() == 1
            page.locator("[data-selection-toolbar]").wait_for(state="visible")
            assert page.locator("[data-selection-toolbar]").is_visible()
            assert page.locator("[data-selection-count-chip]").text_content() == "3"

            # Grouping wraps the selection in an editable semantic frame.
            page.locator('[data-selection-action="group"]').click()
            grouped = page.evaluate("() => window.infragramEditor.getState()")
            group = next(
                boundary for boundary in grouped["boundaries"] if boundary.get("userGroup")
            )
            assert {node["boundaryId"] for node in grouped["nodes"]} == {group["id"]}

            # Detach moves one level up rather than throwing the node to an unrelated root.
            page.locator('[data-node-id="gateway"]').dblclick()
            page.locator('[data-inspector-tab="arrange"]').click()
            page.locator('[data-arrange-action="detach"]').click()
            detached = page.evaluate(
                "() => window.infragramEditor.getState().nodes.find(node => node.id === 'gateway')"
            )
            assert detached["boundaryId"] is None

            # Item-level locking survives rendering and prevents geometry changes.
            arrange = page.locator('[data-inspector-panel="arrange"]')
            arrange.locator('[data-arrange-action="lock"]').click()
            before = page.evaluate(
                "() => window.infragramEditor.getState().nodes.find(node => node.id === 'gateway')"
            )
            # the card itself, not its box with the connection dots beside it
            gateway = page.locator('[data-node-id="gateway"] [data-node-surface]')
            box = gateway.bounding_box()
            assert box is not None
            page.mouse.move(box["x"] + 20, box["y"] + 20)
            page.mouse.down()
            page.mouse.move(box["x"] + 90, box["y"] + 70)
            page.mouse.up()
            after = page.evaluate(
                "() => window.infragramEditor.getState().nodes.find(node => node.id === 'gateway')"
            )
            assert (after["x"], after["y"]) == (before["x"], before["y"])

            # Z-order stays inside the node band and is persisted.
            arrange.locator('[data-arrange-action="lock"]').click()
            unlocked = page.evaluate(
                "() => window.infragramEditor.getState().nodes.find(node => node.id === 'gateway')"
            )
            assert unlocked.get("locked") is False
            arrange.locator('[data-arrange-action="to-front"]').click()
            ordered = page.evaluate("() => window.infragramEditor.getState().nodes")
            gateway = next(node for node in ordered if node["id"] == "gateway")
            siblings = [
                node
                for node in ordered
                if node.get("layerId") == gateway.get("layerId")
                and node.get("boundaryId") == gateway.get("boundaryId")
            ]
            assert gateway["order"] == max(node["order"] for node in siblings)

            # Search highlights matching canvas nodes and dims non-matches.
            page.locator("[data-sidebar-search]").fill("Worker")
            assert page.locator('[data-node-id="worker"][data-search-match="true"]').count() == 1
            assert page.locator('[data-node-id="database"][data-search-dimmed="true"]').count() == 1

            # Shift selection includes provider frames, and frames remain below the node band.
            page.evaluate(
                """() => {
                    const library = window.infragramEditor.getLibraryCatalog();
                    const frame = library.components.find(item => item.serviceId === 'custom-boundary-azure-vnet');
                    window.infragramEditor.addBoundary(frame, {x: 980, y: 640});
                }"""
            )
            page.locator('[data-node-id="worker"]').dblclick()
            page.locator('[data-graph-boundary][data-boundary-kind="network"]').click(
                modifiers=["Shift"]
            )
            assert page.locator('[data-graph-node][data-selected="true"]').count() == 1
            assert page.locator('[data-graph-boundary][data-selected="true"]').count() == 1
            page.screenshot(path=str(tmp_path / "multicloud-selection-arrange-validated.png"))
        finally:
            browser.close()


def test_schema_two_browser_recovery_migrates_to_v3_without_losing_geometry(
    tmp_path: Path,
) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "schema-two-recovery.html"
    source.write_text(render_project_html(project("azure")), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri())
            _settled(page)
            saved_x = page.evaluate(
                """() => {
                    const state = window.infragramEditor.getState();
                    state.schemaVersion = 2;
                    delete state.projectSlug;
                    delete state.providers;
                    delete state.layers;
                    state.nodes[0].x += 28;
                    state.nodes.forEach(node => {
                      delete node.layerId;
                      delete node.componentProvider;
                      delete node.componentQualifiedId;
                    });
                    localStorage.setItem('infragram-editor:azure-sidebar-e2e', JSON.stringify(state));
                    return state.nodes[0].x;
                }"""
            )
            page.reload()
            _settled(page)

            restored = page.evaluate("() => window.infragramEditor.getState()")
            assert restored["schemaVersion"] == 3
            assert restored["projectSlug"] == "azure-sidebar-e2e"
            assert restored["nodes"][0]["x"] == saved_x
            assert restored["nodes"][0]["layerId"] == "provider:azure"
            assert restored["nodes"][0]["componentProvider"] == "azure"
            assert restored["nodes"][0]["componentQualifiedId"].startswith("azure:")
        finally:
            browser.close()


def test_connector_line_style_and_direction_edit_and_round_trip(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "connector-style.html"
    source.write_text(render_project_html(connector_label_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri() + "?fresh=edge-style")
            _settled(page)

            edge = page.locator('[data-graph-edge][data-edge-id="edge-1"]')
            assert edge.get_attribute("marker-end")
            assert edge.get_attribute("marker-start") is None
            assert edge.get_attribute("stroke-dasharray") is None

            # Scripted change: dashed line with arrowheads at both ends.
            changed = page.evaluate(
                "() => window.infragramEditor.setEdgeStyle('edge-1', {kind: 'dashed', direction: 'both'})"
            )
            assert changed["kind"] == "dashed"
            assert changed["direction"] == "both"
            edge = page.locator('[data-graph-edge][data-edge-id="edge-1"]')
            assert edge.get_attribute("stroke-dasharray") == "5 4"
            assert edge.get_attribute("marker-start")
            assert edge.get_attribute("marker-end")

            exported = page.evaluate("() => window.infragramEditor.exportProject()")
            client = next(
                element for element in exported["topology"]["children"] if element["id"] == "client"
            )
            assert client["connections"][0]["kind"] == "dashed"
            assert client["connections"][0]["direction"] == "both"

            # Inspector: selecting the connector shows its style, and the
            # selects drive the same change as the API.
            page.locator('[data-edge-hit="edge-1"]').dblclick(force=True)
            page.locator('[data-inspector-tab="text"]').click()
            kind_select = page.locator('[data-edge-style-control="kind"]')
            direction_select = page.locator('[data-edge-style-control="direction"]')
            assert kind_select.is_enabled() and direction_select.is_enabled()
            assert kind_select.input_value() == "dashed"
            assert direction_select.input_value() == "both"
            direction_select.select_option("none")
            kind_select.select_option("dotted")
            state_edge = page.evaluate("() => window.infragramEditor.getState().edges[0]")
            assert state_edge["direction"] == "none"
            assert state_edge["kind"] == "dotted"
            edge = page.locator('[data-graph-edge][data-edge-id="edge-1"]')
            assert edge.get_attribute("marker-end") is None
            assert edge.get_attribute("marker-start") is None
            assert edge.get_attribute("stroke-dasharray") == "2 3"

            # Static export follows the edge: no arrowheads, dotted stroke.
            svg = page.evaluate("() => window.infragramEditor.exportSvg()")
            exported_edge = re.search(r'<path[^>]*data-edge-id="edge-1"[^>]*>', svg)
            assert exported_edge, svg[:400]
            assert "marker-" not in exported_edge.group(0)
            assert 'stroke-dasharray="2 3"' in exported_edge.group(0)

            # Undo restores the previous style in one step per change.
            page.locator('[data-editor-action="undo"]').click()
            assert (
                page.evaluate("() => window.infragramEditor.getState().edges[0].kind") == "dashed"
            )

            exported = page.evaluate("() => window.infragramEditor.exportProject()")
            client = next(
                element for element in exported["topology"]["children"] if element["id"] == "client"
            )
            assert client["connections"][0]["direction"] == "none"
            assert "direction" not in json.dumps(exported).replace('"direction": "none"', "")
        finally:
            browser.close()


def test_sidebar_search_finds_components_by_their_common_names(tmp_path: Path) -> None:
    """An architect types "vnet", "aks" or "kms", not the publisher's name."""
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "alias-search.html"
    source.write_text(render_project_html(multi_library_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri() + "?fresh=alias-search")
            _settled(page)

            search = page.locator("[data-sidebar-search]")
            for query, component_id in (
                ("vnet", "virtual-networks"),
                ("aks", "kubernetes-services"),
                ("kv", "key-vaults"),
                ("blob", "storage-accounts"),
                ("configmap", "cm"),
                ("mainframe", "mainframe"),
            ):
                search.fill(query)
                card = page.locator(
                    f'.component-card[data-component-id="{component_id}"]:visible'
                ).first
                assert card.count() == 1, f"{query!r} did not surface {component_id}"
                assert card.is_visible(), f"{query!r} left {component_id} hidden"

            # The alias matches, and the card it reveals is the real component:
            # dragging it onto the canvas adds that service, not a placeholder.
            search.fill("kv")
            canvas = page.locator("svg[data-infragram-diagram]")
            before = page.locator("[data-graph-node]").count()
            page.locator('.component-card[data-component-id="key-vaults"]:visible').first.drag_to(
                canvas, target_position={"x": 620, "y": 420}
            )
            assert page.locator("[data-graph-node]").count() == before + 1
            added = page.evaluate("() => window.infragramEditor.getState().nodes.at(-1)")
            assert added["componentQualifiedId"] == "azure:key-vaults"

            search.fill("no-such-service-anywhere")
            assert page.locator(".component-card[data-component-id]:visible").count() == 0
        finally:
            browser.close()


def test_long_card_names_are_not_truncated_in_the_export(tmp_path: Path) -> None:
    """A card grows to fit its own name, so the SVG shows it whole."""
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "card-size.html"
    source.write_text(render_project_html(long_name_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri() + "?fresh=card-size")
            _settled(page)

            drawn = page.evaluate(
                """() => Array.from(
                    document.querySelectorAll('[data-graph-node]'),
                    node => ({
                        id: node.dataset.nodeId,
                        texts: Array.from(node.querySelectorAll('text'), t => t.textContent),
                    }),
                )"""
            )
            by_id = {item["id"]: item["texts"] for item in drawn}
            assert "Application Load Balancer" in by_id["alb"]
            assert not any("…" in text for text in by_id["alb"]), by_id["alb"]
            # A name past the cap still truncates rather than growing forever.
            assert any("…" in text for text in by_id["endless"]), by_id["endless"]
            state = page.evaluate("() => window.infragramEditor.getState().nodes")
            widths = {node["id"]: node["width"] for node in state}
            assert widths["alb"] > widths["short"]
            assert widths["endless"] <= 416
        finally:
            browser.close()


def blocked_route_project() -> CloudProject:
    """Two connected cards with a third sitting on the straight line."""
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "single-cloud",
            "slug": "routing-e2e",
            "title": "Routing E2E",
            "description": "A browser test for connectors that go around cards.",
            "providers": [{"id": "azure"}],
            "default_library": "azure",
            "presentation": {"size": "fit"},
            "topology": {
                "id": "root",
                "name": "Routing E2E",
                "type": "group",
                "children": [
                    {
                        "id": "left",
                        "name": "Left",
                        "type": "service",
                        "attributes": {"editor_x": 80, "editor_y": 300},
                        "component": {"provider": "azure", "service_id": "virtual-machine"},
                        "connections": [{"target": "right", "kind": "solid", "label": "traffic"}],
                    },
                    {
                        "id": "blocker",
                        "name": "In the way",
                        "type": "service",
                        "attributes": {"editor_x": 460, "editor_y": 300},
                        "component": {"provider": "azure", "service_id": "function-apps"},
                    },
                    {
                        "id": "right",
                        "name": "Right",
                        "type": "service",
                        "attributes": {"editor_x": 840, "editor_y": 300},
                        "component": {"provider": "azure", "service_id": "sql-database"},
                    },
                ],
            },
        }
    )


#: Samples a drawn connector and counts the points that land inside a card
#: that is not one of its own endpoints.
_CROSSINGS = """() => {
  const state = window.infragramEditor.getState();
  let hits = 0;
  document.querySelectorAll('[data-graph-edge]').forEach(path => {
    const edge = state.edges.find(item => item.id === path.dataset.edgeId);
    const skip = new Set([edge.source, edge.target]);
    const length = path.getTotalLength();
    for (let i = 0; i <= 200; i += 1) {
      const point = path.getPointAtLength(length * i / 200);
      if (state.nodes.some(node => !skip.has(node.id)
        && point.x > node.x + 1 && point.x < node.x + node.width - 1
        && point.y > node.y + 1 && point.y < node.y + node.height - 1)) { hits += 1; break; }
    }
  });
  return hits;
}"""


def test_connectors_route_around_cards_in_the_way(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "routing.html"
    source.write_text(render_project_html(blocked_route_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri() + "?fresh=routing")
            _settled(page)

            assert page.evaluate(_CROSSINGS) == 0, "a wire still runs through the card"

            # The inspector toggle turns it off, and the wire goes straight
            # through again: the routed path is a choice, not a rewrite.
            page.locator('[data-inspector-tab="diagram"]').click()
            around = page.locator('[data-inspector-routing] [data-routing="around"]')
            direct = page.locator('[data-inspector-routing] [data-routing="direct"]')
            assert around.get_attribute("aria-pressed") == "true"
            direct.click()
            assert direct.get_attribute("aria-pressed") == "true"
            assert around.get_attribute("aria-pressed") == "false"
            assert page.evaluate(_CROSSINGS) == 1
            around.click()
            assert page.evaluate(_CROSSINGS) == 0

            # The routed wire survives an SVG export.
            svg = page.evaluate("() => window.infragramEditor.exportSvg()")
            assert svg.count("data-graph-edge") == 1
            corners = svg[svg.index("data-graph-edge") :]
            assert corners.count("Q") >= 2, "the exported wire lost its detour"
        finally:
            browser.close()


def test_routing_can_be_pinned_by_hand_and_survives_a_round_trip(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "waypoints.html"
    source.write_text(render_project_html(blocked_route_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri() + "?fresh=waypoints")
            _settled(page)

            edge_id = page.evaluate("() => window.infragramEditor.getState().edges[0].id")
            # Pin the wire above the blocker instead of below it.
            page.evaluate(
                "id => window.infragramEditor.setEdgeWaypoints(id, [{x: 560, y: 180}])",
                edge_id,
            )
            assert page.evaluate(_CROSSINGS) == 0
            drawn = page.get_attribute("[data-graph-edge]", "d")
            assert ",180" in drawn or ",184" in drawn, drawn

            exported = page.evaluate("() => window.infragramEditor.exportProject()")
            left = next(
                element for element in exported["topology"]["children"] if element["id"] == "left"
            )
            assert left["connections"][0]["waypoints"] == [{"x": 560, "y": 180}]

            # Reopening the exported document keeps the pinned corner.
            reopened = CloudProject.model_validate(exported)
            page.set_content(render_project_html(reopened))
            _settled(page)
            again = page.evaluate("() => window.infragramEditor.getState().edges[0].waypoints")
            assert again == [{"x": 560, "y": 180}]

            page.evaluate("id => window.infragramEditor.setEdgeWaypoints(id, [])", edge_id)
            assert page.evaluate("() => window.infragramEditor.getState().edges[0].waypoints") in (
                None,
                [],
            )
        finally:
            browser.close()


def test_routing_is_off_when_the_url_asks_for_direct_wires(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "routing-param.html"
    source.write_text(render_project_html(blocked_route_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri() + "?fresh=direct&routing=simple")
            _settled(page)
            assert page.evaluate(_CROSSINGS) == 1
            assert (
                page.locator('[data-inspector-routing] [data-routing="direct"]').get_attribute(
                    "aria-pressed"
                )
                == "true"
            )
        finally:
            browser.close()


@pytest.mark.parametrize(
    "slug",
    ["azure-aks-baseline", "azure-api", "azure-hub-spoke-landing-zone", "azure-web-app-front-door"],
)
def test_shipped_templates_draw_no_wire_through_a_card(slug: str, tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    templates = Path(__file__).parents[2] / "skills/infragram-azure/assets/templates/cloud"
    project = CloudProject.load(templates / f"{slug}.infragram.json")
    source = tmp_path / f"{slug}.html"
    source.write_text(render_project_html(project), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(source.resolve().as_uri() + f"?fresh={slug}-routing")
            _settled(page)
            assert page.evaluate(_CROSSINGS) == 0
        finally:
            browser.close()


def test_connector_line_colour_width_and_arrowhead_are_editable(tmp_path: Path) -> None:
    """A link says what kind of traffic it is: colour, weight, arrowhead."""
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "link-style.html"
    source.write_text(render_project_html(connector_label_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri() + "?fresh=link-style")
            _settled(page)

            page.locator('[data-edge-hit="edge-1"]').dblclick(force=True)
            page.locator('[data-inspector-tab="text"]').click()

            arrow = page.locator('[data-edge-style-control="arrow"]')
            stroke = page.locator('[data-edge-style-control="stroke"]')
            width = page.locator('[data-edge-style-control="width"]')
            assert arrow.is_enabled() and stroke.is_enabled() and width.is_enabled()
            assert arrow.input_value() == "triangle"

            arrow.select_option("diamond")
            stroke.fill("#c7254e")
            stroke.dispatch_event("change")
            width.fill("2.4")
            width.dispatch_event("change")

            # the edge is selected, so it draws with the selected marker
            drawn = page.locator('[data-graph-edge][data-edge-id="edge-1"]')
            assert drawn.get_attribute("marker-end") == (
                "url(#infragram-editor-arrow-diamond-selected)"
            )
            assert drawn.get_attribute("stroke") == "#c7254e"
            assert drawn.get_attribute("stroke-width") == "2.4"

            for shape in ("open", "circle", "triangle"):
                arrow.select_option(shape)
                suffix = "" if shape == "triangle" else f"-{shape}"
                assert page.locator('[data-graph-edge][data-edge-id="edge-1"]').get_attribute(
                    "marker-end"
                ) == (f"url(#infragram-editor-arrow{suffix}-selected)")

            # deselecting drops back to the plain marker of the same shape
            page.locator("svg[data-infragram-diagram]").click(position={"x": 40, "y": 40})
            assert (
                page.locator('[data-graph-edge][data-edge-id="edge-1"]').get_attribute("marker-end")
                == "url(#infragram-editor-arrow)"
            )

            # the choices survive an export and come back on reopen
            exported = page.evaluate("() => window.infragramEditor.exportProject()")
            client = next(
                element for element in exported["topology"]["children"] if element["id"] == "client"
            )
            style = client["attributes"]["editor_edge_styles"]["api"]
            assert style["stroke"] == "#c7254e" and style["width"] == 2.4
            assert style["arrow"] == "triangle"

            page.set_content(render_project_html(CloudProject.model_validate(exported)))
            _settled(page)
            again = page.evaluate("() => window.infragramEditor.getState().edges[0].style")
            assert again["stroke"] == "#c7254e" and again["arrow"] == "triangle"
        finally:
            browser.close()


def test_connector_labels_are_styled_from_the_text_tab(tmp_path: Path) -> None:
    """The label is type: it gets a font, a size, a weight and a colour."""
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "label-style.html"
    source.write_text(render_project_html(connector_label_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.goto(source.resolve().as_uri() + "?fresh=label-style")
            _settled(page)

            text = page.locator("[data-edge-label] text")
            assert text.get_attribute("font-size") == "11", "the default label should be readable"

            page.locator('[data-edge-hit="edge-1"]').dblclick(force=True)
            page.locator('[data-inspector-tab="text"]').click()

            size = page.locator('[data-text-control="fontSize"]')
            colour = page.locator('[data-text-control="textColor"]')
            weight = page.locator('[data-text-control="fontWeight"]')
            align = page.locator('[data-text-control="textAlign"]')
            for control in (size, colour, weight):
                sync_api.expect(control).to_be_enabled(timeout=render_timeout_ms())
            assert align.is_disabled(), "a connector label has no alignment"
            assert size.input_value() == "11"

            size.fill("14")
            size.dispatch_event("change")
            colour.fill("#c7254e")
            colour.dispatch_event("change")
            weight.select_option("600")

            text = page.locator("[data-edge-label] text")
            assert text.get_attribute("font-size") == "14"
            assert text.get_attribute("fill") == "#c7254e"
            assert text.get_attribute("font-weight") == "600"

            # the mask behind the label grows with the type, so the wire
            # never shows through the words
            mask = page.locator("[data-edge-label] .edge-label-mask")
            assert float(mask.get_attribute("height")) >= 14

            page.locator("[data-edge-text-reset]").click()
            assert page.locator("[data-edge-label] text").get_attribute("font-size") == "11"

            # a styled label survives the round trip
            page.evaluate("() => window.infragramEditor.setEdgeTextStyle('edge-1', {fontSize: 12})")
            exported = page.evaluate("() => window.infragramEditor.exportProject()")
            client = next(
                element for element in exported["topology"]["children"] if element["id"] == "client"
            )
            assert client["attributes"]["editor_edge_styles"]["api"]["textStyle"]["fontSize"] == 12
        finally:
            browser.close()


def test_badge_tab_seats_inside_the_frame_border(tmp_path: Path) -> None:
    """The runtime's badge plate sits inside the stroke, not over it.

    Half the stroke width in from the frame corner, so the border stays whole
    and the badge never looks as if it sat on the line; the plate is paper for
    an Azure frame and the icon keeps its 2 px margin inside the plate.
    """
    sync_api = pytest.importorskip("playwright.sync_api")
    template = (
        Path(__file__).parents[2]
        / "skills"
        / "infragram-azure"
        / "assets"
        / "templates"
        / "cloud"
        / "azure-aks-baseline.infragram.json"
    )
    source = tmp_path / "azure-aks-baseline.html"
    source.write_text(render_project_html(CloudProject.load(template)), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            page.goto(source.resolve().as_uri() + "?fresh=1")
            _settled(page)
            seats = page.evaluate(
                """() => [...document.querySelectorAll('[data-graph-boundary]')]
                    .filter(group => group.querySelector('[data-boundary-tab]'))
                    .map(group => {
                      const surface = group.querySelector('[data-boundary-surface]');
                      const tab = group.querySelector('[data-boundary-tab]');
                      const image = group.querySelector('image');
                      return {
                        id: group.dataset.boundaryId,
                        x: Number(surface.getAttribute('x')),
                        y: Number(surface.getAttribute('y')),
                        stroke: Number(surface.getAttribute('stroke-width')),
                        tabX: Number(tab.getAttribute('x')),
                        tabY: Number(tab.getAttribute('y')),
                        tabFill: tab.getAttribute('fill'),
                        iconX: Number(image.getAttribute('x')),
                      };
                    })"""
            )
        finally:
            browser.close()

    assert {seat["id"] for seat in seats} >= {
        "workload-subscription",
        "west-europe",
        "rg-aks-spoke",
        "platform-services",
    }
    for seat in seats:
        assert seat["stroke"] == 1.0, seat
        assert seat["tabX"] == seat["x"] + seat["stroke"] / 2, seat
        assert seat["tabY"] == seat["y"] + seat["stroke"] / 2, seat
        assert seat["iconX"] == seat["tabX"] + 2, seat
    plates = {seat["id"]: seat["tabFill"].casefold() for seat in seats}
    # Azure frames take a paper plate, because the vendor's badge paints its
    # own colours there; a core frame has no vendor badge and keeps the
    # frame-coloured plate with the generic glyph reversed out of it.
    assert plates["workload-subscription"] == plates["west-europe"] == "#ffffff", plates
    assert plates["rg-aks-spoke"] == "#ffffff", plates
    assert plates["platform-services"] == "#bdbdbd", plates


def test_exported_picture_seats_the_provider_mark_below_the_drawing(tmp_path: Path) -> None:
    """The editor's own export places the provider mark in its band."""
    sync_api = pytest.importorskip("playwright.sync_api")
    template = (
        Path(__file__).parents[2]
        / "skills"
        / "infragram-azure"
        / "assets"
        / "templates"
        / "cloud"
        / "azure-hub-spoke-landing-zone.infragram.json"
    )
    source = tmp_path / "azure-hub-spoke-landing-zone.html"
    source.write_text(render_project_html(CloudProject.load(template)), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1720, "height": 1040})
            page.goto(source.resolve().as_uri() + "?fresh=1")
            _settled(page)
            seat = page.evaluate(
                """() => {
                    const doc = new DOMParser().parseFromString(window.infragramEditor.exportSvg(), 'image/svg+xml');
                    const mark = doc.querySelector('[data-brand-mark]');
                    // Geometry from the editor state: a node's rect is positioned by
                    // its group's transform, so its own x and y read relative.
                    const state = window.infragramEditor.getState();
                    const boxes = [...state.boundaries, ...state.nodes]
                      .map(item => ({x: item.x, y: item.y, w: item.width, h: item.height}));
                    const view = doc.documentElement.getAttribute('viewBox').split(/\\s+/).map(Number);
                    return {
                      mark: mark && {x: Number(mark.getAttribute('x')), y: Number(mark.getAttribute('y')),
                                     h: Number(mark.getAttribute('height'))},
                      lowest: Math.max(...boxes.map(b => b.y + b.h)),
                      left: Math.min(...boxes.map(b => b.x)),
                      viewBottom: view[1] + view[3],
                    };
                }"""
            )
        finally:
            browser.close()

    assert seat["mark"], "the export lost the provider mark"
    assert seat["mark"]["y"] >= seat["lowest"] + 16, seat
    assert seat["mark"]["x"] == seat["left"], seat
    assert seat["mark"]["y"] + seat["mark"]["h"] <= seat["viewBottom"], seat


def test_exported_wires_bend_by_their_corner_style(tmp_path: Path) -> None:
    """The editor's export turns a wire's corners the way its style says:
    no curve for sharp, the house radius for rounded, a wider one for curved."""
    import re

    from infragram.author import Diagram, Edge
    from infragram.builders import metrics
    from infragram.nodes import Group, _scope
    from infragram.nodes.azure import compute, databases

    sync_api = pytest.importorskip("playwright.sync_api")

    def widest_bend(d: str) -> float:
        # The run from the point before a Q to its control point is the bend radius.
        best, last = 0.0, None
        for token in re.findall(r"[MLQHV][^MLQHV]*", d):
            values = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", token[1:])]
            if token[0] == "Q" and last is not None and len(values) >= 4:
                best = max(best, abs(values[0] - last[0]) + abs(values[1] - last[1]))
                last = (values[2], values[3])
            elif values:
                last = (values[-2], values[-1])
        return best

    paths: dict[str, str] = {}
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for style in ("rounded", "sharp", "curved"):
                _scope.reset()
                # A at the top left, C at the bottom right: both legs of the
                # wire are long, so the bend is never clamped by a short leg.
                with Diagram(f"Bend {style}", providers=("azure",)) as diagram:
                    with Group("Zone", "group").column():
                        with Group("Top", "group").row().keep_order():
                            a = compute.VirtualMachine("A", "source")
                            compute.VirtualMachine("T1", "spacer")
                            compute.VirtualMachine("T2", "spacer")
                        with Group("Bottom", "group").row().keep_order():
                            compute.VirtualMachine("B1", "spacer")
                            compute.VirtualMachine("B2", "spacer")
                            c = databases.SQLDatabase("C", "target")
                    a >> Edge(style, corners=style) >> c
                source = tmp_path / f"bend-{style}.html"
                source.write_text(render_project_html(diagram.to_project()), encoding="utf-8")
                page = browser.new_page(viewport={"width": 1400, "height": 900})
                page.goto(source.resolve().as_uri() + "?fresh=1")
                _settled(page)
                paths[style] = page.evaluate(
                    """() => {
                        const doc = new DOMParser().parseFromString(window.infragramEditor.exportSvg(), 'image/svg+xml');
                        return doc.querySelector('[data-graph-edge]').getAttribute('d');
                    }"""
                )
                page.close()
        finally:
            browser.close()

    assert "Q" not in paths["sharp"], paths["sharp"]
    rounded, curved = widest_bend(paths["rounded"]), widest_bend(paths["curved"])
    assert rounded == metrics.corner_radius("rounded"), paths["rounded"]
    assert curved > rounded, (rounded, curved, paths["curved"])


def test_fit_takes_in_the_step_list(tmp_path: Path) -> None:
    """A flow's steps stand right of the drawing; fitting the page to the
    screen keeps every step's line inside the canvas."""
    import runpy

    sync_api = pytest.importorskip("playwright.sync_api")
    root = Path(__file__).resolve().parents[2]
    example = runpy.run_path(str(root / "examples" / "azure_web_app_front_door.py"), run_name="t")
    source = tmp_path / "steps.html"
    source.write_text(render_project_html(example["diagram"].to_project()), encoding="utf-8")

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(source.as_uri())
            _settled(page)
            page.evaluate("() => window.infragramEditor.whenSettled()")
            page.locator('[data-editor-action="zoom-fit"]').click()
            page.wait_for_timeout(300)
            inside = page.evaluate("""() => {
              const list = document.querySelector('[data-step-list]').getBoundingClientRect();
              const view = document.querySelector('.canvas-viewport').getBoundingClientRect();
              return [list.left >= view.left, list.right <= view.right,
                      list.top >= view.top, list.bottom <= view.bottom];
            }""")
            assert inside == [True, True, True, True], inside
        finally:
            browser.close()
