"""Every control in the exported editor does what it says.

A control-by-control review of the chrome: each one is operated the way a
reader would -- a click, a key, a typed value -- and its effect is read back
from the editor's state or the page, not assumed from the click landing. The
controls the other browser suites already drive (the palette drag, frame
presets, zoom-to-fit, the routing toggle's wires, the popup) are exercised
there; this file covers the rest, so no button on the page goes untested.
"""

from __future__ import annotations

import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

import pytest

from infragram.author import Diagram, Edge
from infragram.exports import render_project_html, render_timeout_ms
from infragram.nodes.azure import compute, databases, networking, storage
from infragram.nodes.frames import azure as az

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run Chromium editor checks",
)

STATE = "() => window.infragramEditor.getState()"


def _menu_entry(page, action: str):
    """A right-click menu entry; one under More actions is opened to first."""
    entry = page.locator(f'[data-canvas-context-menu] [data-context-action="{action}"]')
    if entry.evaluate("element => Boolean(element.closest('[data-context-submenu-menu]'))"):
        page.locator("[data-context-submenu-toggle]").click()
    return entry


def _review_page(tmp_path: Path, libraries: str = "project") -> Path:
    """Three standalone cards, a frame holding two more, and two labelled wires."""
    with Diagram(
        "Control review",
        "Every control, operated once.",
        slug="control-review",
        providers=("azure",),
        display="card",
    ) as diagram:
        with az.VNet("vnet-review 10.0.0.0/16").row():
            gateway = networking.ApplicationGateways("Gateway", "WAF v2")
            web = compute.VirtualMachine("Web", "VM scale set")
        api = compute.KubernetesServices("API", "AKS pods")
        sql = databases.SQLDatabase("SQL", "private endpoint")
        blobs = storage.StorageAccounts("Blobs", "private endpoint")
        gateway >> Edge("HTTPS") >> web
        api >> Edge("TDS", dashed=True) >> sql
        api >> blobs
    source = tmp_path / f"control-review-{libraries}.html"
    source.write_text(
        render_project_html(diagram.to_project(), libraries=libraries), encoding="utf-8"
    )
    return source


@contextmanager
def _editor(
    tmp_path: Path,
    *,
    theme: str = "light",
    libraries: str = "project",
    viewport: tuple[int, int] = (1440, 900),
):
    sync_api = pytest.importorskip("playwright.sync_api")
    source = _review_page(tmp_path, libraries)
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": viewport[0], "height": viewport[1]}, accept_downloads=True
            )
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
            page.on(
                "console",
                lambda message: (
                    errors.append(f"console: {message.text}") if message.type == "error" else None
                ),
            )
            page.goto(f"{source.resolve().as_uri()}?fresh={tmp_path.name}&theme={theme}")
            page.wait_for_load_state("load")
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            yield page, errors
            assert not errors, errors
        finally:
            browser.close()


def _state(page) -> dict:
    return page.evaluate(STATE)


def _node(page, name: str) -> dict:
    return next(node for node in _state(page)["nodes"] if node["name"] == name)


def _boundary(page, prefix: str) -> dict:
    return next(item for item in _state(page)["boundaries"] if item["name"].startswith(prefix))


def _edge(page, label: str) -> dict:
    return next(edge for edge in _state(page)["edges"] if edge.get("label") == label)


def _select_node(page, name: str, *, add: bool = False, button: str = "left") -> None:
    """Select for editing with a double click only when not already selected.

    A plain click on an unselected item reads its flow. Shift and right
    clicks retain their normal selection behavior; a second double click
    on an edited item would open its text editor instead.
    """
    node_id = _node(page, name)["id"]
    target = page.locator(f'[data-graph-node][data-node-id="{node_id}"]')
    if add or button != "left" or target.get_attribute("data-selected") == "true":
        target.click(modifiers=["Shift"] if add else None, button=button)
    else:
        target.dblclick()


def _select_edge(page, label: str, *, add: bool = False) -> None:
    edge_id = _edge(page, label)["id"]
    target = page.locator(f'[data-edge-label][data-edge-id="{edge_id}"]')
    if add or target.get_attribute("data-selected") == "true":
        target.click(modifiers=["Shift"] if add else None)
    else:
        target.dblclick()


def _change(page, selector: str, value: str) -> None:
    """Type a value into a field and commit it, as leaving the field does."""
    field = page.locator(selector)
    field.fill(value)
    field.dispatch_event("change")


# ------------------------------------------------------------------ header
def test_theme_palette_and_download_menu(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        token = "name => getComputedStyle(document.body).getPropertyValue(name).trim()"
        palette = page.locator("[data-theme-menu]")
        toggle = page.locator("[data-theme-toggle]")
        assert toggle.get_attribute("aria-label") == "Theme: Light"
        assert page.locator('[data-theme-choice="light"]').get_attribute("aria-checked") == "true"

        def choose(theme: str) -> None:
            toggle.click()
            assert palette.get_attribute("open") is not None
            page.locator(f'[data-theme-choice="{theme}"]').click()
            assert palette.get_attribute("open") is None, "choosing a theme closes the palette"

        card = "() => document.querySelector('[data-graph-node] [data-node-surface]').getAttribute('fill')"
        choose("dark")
        assert page.locator("body").get_attribute("data-workspace-theme") == "dark"
        assert toggle.get_attribute("aria-label") == "Theme: Dark"
        assert page.evaluate(token, "--md-sys-color-surface") == "#141515"
        dark_card = page.evaluate(card)

        # Darker is dark in every behaviour, on neutral near-black surfaces
        choose("darker")
        body = page.locator("body")
        assert body.get_attribute("data-workspace-theme") == "dark"
        assert body.get_attribute("data-workspace-palette") == "darker"
        assert page.locator('[data-theme-choice="darker"]').get_attribute("aria-checked") == "true"
        assert page.locator('[data-theme-choice="dark"]').get_attribute("aria-checked") == "false"
        assert page.evaluate(token, "--md-sys-color-surface") == "#212121"
        assert page.evaluate(token, "--md-sys-color-surface-container-low") == "#171717"
        assert (
            page.locator(".provider-sidebar").evaluate(
                "element => getComputedStyle(element).backgroundColor"
            )
            == "rgb(23, 23, 23)"
        )
        assert page.evaluate(card) != dark_card, "the canvas repaints in the darker palette"
        assert page.evaluate("localStorage.getItem('infragram-workspace-theme')") == "darker"

        toggle.click()
        page.keyboard.press("Escape")
        assert palette.get_attribute("open") is None, "Escape closes the palette"
        choose("light")
        assert body.get_attribute("data-workspace-palette") == "light"
        assert page.evaluate(token, "--md-sys-color-surface") == "#FFFFFF"

        menu = page.locator("[data-download-menu]")
        summary = menu.locator("> summary")

        summary.click()
        assert menu.get_attribute("open") is not None
        with page.expect_download() as template:
            page.locator("[data-download-template]").click()
        assert template.value.suggested_filename == "control-review.infragram.json"
        document = json.loads(Path(template.value.path()).read_text(encoding="utf-8"))
        assert document["slug"] == "control-review" and document["topology"]["children"]
        assert menu.get_attribute("open") is None, "choosing an item closes the menu"

        summary.click()
        with page.expect_download() as page_download:
            page.locator("[data-download-html]").click()
        assert page_download.value.suggested_filename == "control-review.html"
        saved = Path(page_download.value.path()).read_text(encoding="utf-8")
        assert "data-infragram-editor" in saved
        assert not re.search(r"<details[^>]*data-download-menu[^>]*\sopen", saved), (
            "saved with the menu open"
        )

        summary.click()
        with page.expect_download() as svg:
            page.locator("[data-download-svg]").click()
        assert svg.value.suggested_filename == "control-review.svg"
        assert "<svg" in Path(svg.value.path()).read_text(encoding="utf-8")

        summary.click()
        page.keyboard.press("Escape")
        assert menu.get_attribute("open") is None, "Escape closes the menu"
        summary.click()
        page.locator("[data-document-title]").click()
        assert menu.get_attribute("open") is None, "a press elsewhere closes the menu"


# ----------------------------------------------------------------- toolbar
def test_toolbar_zoom_grid_undo_redo_and_delete(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        value = page.locator("[data-zoom-value]")
        percent = lambda: int(value.inner_text().rstrip("%"))  # noqa: E731
        fitted = percent()
        page.locator('[data-editor-action="zoom-in"]').click()
        assert percent() == fitted + 10
        page.locator('[data-editor-action="zoom-out"]').click()
        assert percent() == fitted
        page.locator('[data-editor-action="zoom-reset"]').click()
        assert percent() == 100
        page.locator('[data-editor-action="zoom-fit"]').click()
        page.evaluate("() => window.infragramEditor.whenSettled()")
        assert percent() == fitted

        zoom_out = page.locator('[data-editor-action="zoom-out"]')
        while zoom_out.is_enabled():
            zoom_out.click()
        assert percent() == 10
        zoom_in = page.locator('[data-editor-action="zoom-in"]')
        while zoom_in.is_enabled():
            zoom_in.click()
        assert percent() == 400
        page.locator('[data-editor-action="zoom-fit"]').click()

        # the grid starts hidden; the toolbar and the inspector both switch it
        grid = page.locator('[data-editor-action="toggle-grid"]')
        assert grid.get_attribute("aria-pressed") == "false"
        assert _state(page)["canvas"]["showGrid"] is False
        grid.click()
        assert grid.get_attribute("aria-pressed") == "true"
        assert page.locator(".diagram-stage").get_attribute("data-grid-visible") == "true"
        assert page.locator("[data-inspector-grid-toggle]").get_attribute("aria-checked") == "true"
        assert _state(page)["canvas"]["showGrid"] is True
        page.locator("[data-inspector-grid-toggle]").click()
        assert grid.get_attribute("aria-pressed") == "false"
        assert _state(page)["canvas"]["showGrid"] is False

        undo = page.locator('[data-editor-action="undo"]')
        redo = page.locator('[data-editor-action="redo"]')
        delete = page.locator('[data-editor-action="delete"]')
        assert undo.is_disabled() and redo.is_disabled()
        assert delete.is_disabled(), "nothing is selected"
        count = len(_state(page)["nodes"])
        _select_node(page, "API")
        assert delete.is_enabled()
        delete.click()
        assert len(_state(page)["nodes"]) == count - 1
        assert undo.is_enabled()
        undo.click()
        assert len(_state(page)["nodes"]) == count
        assert redo.is_enabled()
        redo.click()
        assert len(_state(page)["nodes"]) == count - 1


# ----------------------------------------------------------------- sidebar
def test_sidebar_search_categories_cards_and_rail(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        categories = page.locator("details.category")
        hidden = lambda: {  # noqa: E731
            item.get_attribute("data-category-id") for item in categories.all() if item.is_hidden()
        }
        assert hidden() == {"energy", "industrial", "facilities"}

        search = page.locator("[data-sidebar-search]")
        search.fill("application gateway")
        networking_category = page.locator('details.category[data-category-id="networking"]')
        assert networking_category.get_attribute("open") is not None
        assert networking_category.locator(".component-card:visible").count() >= 1
        assert len(hidden()) > 3, "search hides categories without a match"
        search.fill("")
        assert hidden() == {"energy", "industrial", "facilities"}
        assert networking_category.get_attribute("open") is None, "search closes what it opened"

        compute_category = page.locator('details.category[data-category-id="compute"]')
        compute_category.locator("> summary").click()
        assert compute_category.get_attribute("open") is not None
        cards = compute_category.locator(".component-card")
        assert cards.count() > 0
        cards.nth(0).click()
        assert cards.nth(0).get_attribute("aria-pressed") == "true"
        cards.nth(1).click()
        assert cards.nth(0).get_attribute("aria-pressed") == "false"
        count = len(_state(page)["nodes"])
        cards.nth(1).dblclick()
        assert len(_state(page)["nodes"]) == count + 1, "a double-click places the component"
        compute_category.locator("> summary").click()
        assert compute_category.get_attribute("open") is None

        custom = page.locator('details.category[data-category-id="custom"]')
        custom.locator("> summary").click()
        basics = custom.locator(
            'details.component-section[data-component-section="basic-elements"]'
        )
        basics.locator("> summary").click()
        assert basics.get_attribute("open") is not None
        assert basics.locator(".component-card:visible").count() > 0
        group = custom.locator('details.frame-group[data-frame-group="azure"]')
        group.locator("> summary").click()
        frames = len(_state(page)["boundaries"])
        group.locator(".frame-card").first.dblclick()
        assert len(_state(page)["boundaries"]) == frames + 1, "a frame tile places its frame"
        others = custom.locator(
            'details.component-section[data-component-section="provider-services"]'
        )
        if others.count():
            others.locator("> summary").click()
            service_group = others.locator("details.provider-service-group").first
            service_group.locator("> summary").click()
            assert service_group.locator(".component-card:visible").count() > 0

        brand = page.locator("[data-sidebar-logo-trigger]")
        brand.click()
        page.mouse.move(900, 500)
        page.wait_for_timeout(250)
        assert "sidebar-collapsed" in page.locator("body").get_attribute("class")
        assert round(page.locator(".provider-sidebar").bounding_box()["width"]) == 56
        brand.hover()
        page.wait_for_timeout(250)
        assert round(page.locator(".provider-sidebar").bounding_box()["width"]) == 372, (
            "hover previews"
        )
        brand.click()
        assert "sidebar-collapsed" not in (page.locator("body").get_attribute("class") or "")


def test_library_menu_and_quick_filters(tmp_path: Path) -> None:
    with _editor(tmp_path, libraries="all") as (page, _errors):
        selector = page.locator(".provider-selector")
        assert selector.is_visible(), "three embedded libraries offer a choice"
        trigger = page.locator("[data-provider-menu-trigger]")
        menu = page.locator("[data-provider-menu]")
        summary = page.locator("[data-provider-summary]")
        apply = page.locator("[data-provider-apply]")

        trigger.click()
        assert menu.is_visible() and trigger.get_attribute("aria-expanded") == "true"
        page.locator("[data-provider-clear]").click()
        assert apply.is_disabled()
        page.locator("[data-provider-select-all]").click()
        assert page.locator("[data-provider-option]:checked").count() == 3
        assert apply.is_enabled()
        apply.click()
        assert menu.is_hidden() and summary.inner_text() == "All 3"

        trigger.click()
        page.locator('[data-provider-option="kubernetes"]').uncheck()
        page.keyboard.press("Escape")
        assert menu.is_hidden(), "Escape closes the menu"
        assert summary.inner_text() == "All 3", "and discards what was not applied"
        trigger.click()
        page.locator("[data-document-title]").click()
        assert menu.is_hidden(), "a press elsewhere closes the menu"

        kubernetes = page.locator('[data-provider-quick-filter="kubernetes"]')
        azure = page.locator('[data-provider-quick-filter="azure"]')
        kubernetes.click()
        assert kubernetes.get_attribute("aria-pressed") == "true"
        assert azure.get_attribute("aria-pressed") == "false"
        assert summary.inner_text() == "K8S"
        azure.click()
        assert summary.inner_text() == "Azure"


# --------------------------------------------------------------- inspector
def test_inspector_tabs_collapse_and_diagram_settings(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        for panel in ("style", "text", "arrange", "layers", "diagram"):
            page.locator(f'[data-inspector-tab="{panel}"]').click()
            visible = [
                item.get_attribute("data-inspector-panel")
                for item in page.locator("[data-inspector-panel]").all()
                if item.is_visible()
            ]
            assert visible == [panel]
            assert (
                page.locator(f'[data-inspector-tab="{panel}"]').get_attribute("aria-selected")
                == "true"
            )

        toggle = page.locator("[data-inspector-toggle]")
        toggle.click()
        assert "inspector-collapsed" in page.locator("body").get_attribute("class")
        assert toggle.get_attribute("aria-expanded") == "false"
        assert page.locator(".inspector-body").is_hidden()
        toggle.click()
        assert toggle.get_attribute("aria-expanded") == "true"
        assert page.locator(".inspector-body").is_visible()

        switch = page.locator("[data-inspector-grid-toggle]")
        switch.click()
        assert (
            switch.get_attribute("aria-checked") == "true"
            and _state(page)["canvas"]["showGrid"] is True
        )
        switch.click()
        assert _state(page)["canvas"]["showGrid"] is False

        direct = page.locator('[data-inspector-routing] [data-routing="direct"]')
        around = page.locator('[data-inspector-routing] [data-routing="around"]')
        direct.click()
        assert _state(page)["canvas"]["routeAroundNodes"] is False
        assert (
            direct.get_attribute("aria-pressed") == "true"
            and around.get_attribute("aria-pressed") == "false"
        )
        direct.click()
        assert _state(page)["canvas"]["routeAroundNodes"] is False, (
            "choosing the chosen segment changes nothing"
        )
        around.click()
        assert _state(page)["canvas"]["routeAroundNodes"] is True

        icons = page.locator('[data-inspector-display] [data-project-display="icon"]')
        cards = page.locator('[data-inspector-display] [data-project-display="card"]')
        icons.click()
        assert _state(page)["canvas"]["displayMode"] == "icon"
        assert _node(page, "API").get("displayMode") == "icon"
        assert icons.get_attribute("aria-pressed") == "true"
        cards.click()
        assert _state(page)["canvas"]["displayMode"] == "card"
        assert _node(page, "API").get("displayMode", "card") == "card"

        # Frame lines weigh every frame's border alike, and undo puts them back
        def borders() -> list[float]:
            return [
                float(width)
                for width in page.locator("[data-boundary-surface]").evaluate_all(
                    "nodes => nodes.map(node => node.getAttribute('stroke-width'))"
                )
            ]

        thin = borders()
        thick = page.locator('[data-inspector-frame-lines] [data-frame-lines="thick"]')
        assert page.locator('[data-frame-lines="thin"]').get_attribute("aria-pressed") == "true"
        thick.click()
        assert _state(page)["canvas"]["frameLines"] == "thick"
        assert thick.get_attribute("aria-pressed") == "true"
        assert borders() == [pytest.approx(width * 2.5) for width in thin]
        page.keyboard.press("Control+z")
        assert borders() == thin


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_style_panel_display_and_outline_presets(tmp_path: Path, theme: str) -> None:
    with _editor(tmp_path, theme=theme) as (page, _errors):
        card = page.evaluate(
            "() => getComputedStyle(document.body).getPropertyValue('--card-bg').trim()"
        )
        _select_node(page, "API")
        page.locator('[data-inspector-tab="style"]').click()
        assert page.locator("[data-inspector-selection]").inner_text() == "API"
        assert page.locator("[data-inspector-provider]").inner_text() == "Azure"
        assert page.locator("[data-inspector-component]").inner_text() == "Kubernetes Services"

        icon = page.locator('button[data-display-mode="icon"]')
        icon.click()
        assert (
            _node(page, "API")["displayMode"] == "icon"
            and icon.get_attribute("aria-pressed") == "true"
        )
        page.locator('button[data-display-mode="card"]').click()
        assert _node(page, "API")["displayMode"] == "card"

        api_id = _node(page, "API")["id"]
        surface = page.locator(f'[data-node-id="{api_id}"] [data-node-surface]')
        strokes = {
            "accent-outline": "#479EF5",
            "muted-outline": "#5E87B8",
            "danger-outline": "#E03131",
        }
        for preset, stroke in strokes.items():
            page.locator(f'[data-style-preset="{preset}"]').click()
            assert _node(page, "API")["style"]["stroke"] == stroke
            assert surface.get_attribute("stroke") == stroke
            # an outline preset changes the outline; the card keeps the theme's fill
            assert (surface.get_attribute("fill") or "").upper() == card.upper()
        page.locator('[data-style-preset="neutral"]').click()
        assert not _node(page, "API").get("style"), "neutral returns the card to the theme's look"
        assert (surface.get_attribute("fill") or "").upper() == card.upper()


def test_text_panel_edits_cards_and_connectors(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        _select_node(page, "API")
        page.locator('[data-inspector-tab="text"]').click()
        assert page.locator('[data-content-control="name"]').input_value() == "API"
        _change(page, '[data-content-control="name"]', "API tier")
        assert any(node["name"] == "API tier" for node in _state(page)["nodes"])
        _change(page, '[data-content-control="detail"]', "AKS workloads")
        assert _node(page, "API tier")["detail"] == "AKS workloads"
        _change(page, '[data-content-control="name"]', "")
        assert _node(page, "API tier"), "an empty name is refused"

        page.locator('[data-text-control="fontFamily"]').select_option("Geist Mono")
        page.locator('[data-text-control="fontWeight"]').select_option("500")
        page.locator('[data-text-control="textAlign"]').select_option("center")
        _change(page, '[data-text-control="fontSize"]', "14")
        _change(page, '[data-text-control="opacity"]', "80")
        _change(page, '[data-text-control="textColor"]', "#aa3300")
        assert _node(page, "API tier")["textStyle"] == {
            "fontFamily": "Geist Mono",
            "fontWeight": 500,
            "textAlign": "center",
            "fontSize": 14,
            "opacity": 80,
            "textColor": "#aa3300",
        }

        _select_edge(page, "HTTPS")
        page.locator('[data-inspector-tab="text"]').click()
        assert page.locator("[data-edge-label-section]").is_visible()
        _change(page, '[data-edge-label-control="label"]', "TLS 443")
        edge = _edge(page, "TLS 443")
        page.locator('[data-edge-style-control="kind"]').select_option("dotted")
        page.locator('[data-edge-style-control="direction"]').select_option("both")
        arrows = page.locator('[data-edge-style-control="arrow"] option').all()
        page.locator('[data-edge-style-control="arrow"]').select_option(
            arrows[-1].get_attribute("value")
        )
        corners = page.locator('[data-edge-style-control="corners"] option').all()
        page.locator('[data-edge-style-control="corners"]').select_option(
            corners[-1].get_attribute("value")
        )
        _change(page, '[data-edge-style-control="stroke"]', "#123456")
        _change(page, '[data-edge-style-control="width"]', "2.5")
        edge = _edge(page, "TLS 443")
        assert edge["kind"] == "dotted"
        assert edge["style"]["stroke"] == "#123456" and edge["style"]["width"] == 2.5
        assert page.locator('[data-edge-style-control="direction"]').input_value() == "both"
        assert page.locator('[data-edge-style-control="arrow"]').input_value() == arrows[
            -1
        ].get_attribute("value")
        assert page.locator('[data-edge-style-control="corners"]').input_value() == corners[
            -1
        ].get_attribute("value")

        _change(page, '[data-edge-label-field="dx"]', "24")
        _change(page, '[data-edge-label-field="dy"]', "-12")
        assert _edge(page, "TLS 443")["labelPlacement"] == {"mode": "manual", "dx": 24, "dy": -12}
        reset_place = page.locator("[data-edge-label-reset]")
        assert reset_place.is_enabled()
        reset_place.click()
        assert "labelPlacement" not in _edge(page, "TLS 443")
        assert reset_place.is_disabled()

        page.locator('[data-text-control="fontSize"]').fill("13")
        page.locator('[data-text-control="fontSize"]').dispatch_event("change")
        assert _edge(page, "TLS 443").get("style", {}).get("textStyle"), (
            "the label takes the text style"
        )
        page.locator("[data-edge-text-reset]").click()
        assert not _edge(page, "TLS 443").get("style", {}).get("textStyle")


def test_arrange_panel_geometry_order_alignment_and_containment(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        _select_node(page, "API")
        page.locator('[data-inspector-tab="arrange"]').click()
        assert page.locator("[data-arrange-selection-kind]").inner_text() == "1 component selected"
        _change(page, '[data-exact-field="x"]', "400")
        _change(page, '[data-exact-field="y"]', "320")
        _change(page, '[data-exact-field="width"]', "240")
        _change(page, '[data-exact-field="height"]', "80")
        api = _node(page, "API")
        assert (api["x"], api["y"], api["width"], api["height"]) == (400, 320, 240, 80)

        orders = lambda: {node["name"]: node["order"] for node in _state(page)["nodes"]}  # noqa: E731
        page.locator('[data-arrange-action="to-back"]').click()
        assert orders()["API"] == min(orders().values())
        page.locator('[data-arrange-action="forward"]').click()
        assert orders()["API"] == min(orders().values()) + 1
        page.locator('[data-arrange-action="to-front"]').click()
        assert orders()["API"] == max(orders().values())
        page.locator('[data-arrange-action="backward"]').click()
        assert orders()["API"] == max(orders().values()) - 1

        for action, attribute, expected in (
            ("rotate-90", "angle", 90),
            ("flip-horizontal", "flipX", True),
            ("flip-vertical", "flipY", True),
        ):
            page.locator(f'[data-arrange-action="{action}"]').click()
            assert _node(page, "API")[attribute] == expected, action

        _select_node(page, "SQL", add=True)
        _select_node(page, "Blobs", add=True)
        assert page.locator("[data-arrange-selection-kind]").inner_text() == "3 components selected"
        names = ("API", "SQL", "Blobs")
        pick = lambda key: [_node(page, name)[key] for name in names]  # noqa: E731
        box = lambda: [_node(page, name) for name in names]  # noqa: E731
        page.locator('[data-arrange-action="align-left"]').click()
        assert len(set(pick("x"))) == 1
        page.locator('[data-arrange-action="align-top"]').click()
        assert len(set(pick("y"))) == 1
        page.locator('[data-arrange-action="align-right"]').click()
        assert len({node["x"] + node["width"] for node in box()}) == 1
        page.locator('[data-arrange-action="align-bottom"]').click()
        assert len({node["y"] + node["height"] for node in box()}) == 1
        page.locator('[data-arrange-action="align-center"]').click()
        assert max(pick("x")) - min(pick("x")) <= 80, "centres line up"
        page.locator('[data-arrange-action="align-middle"]').click()
        # The three now overlap. Spread them out, picking whichever card is on
        # top of the stack each time, then distribute.
        stack = page.locator(
            f'[data-graph-node][data-node-id="{_node(page, "SQL")["id"]}"]'
        ).bounding_box()
        for index in range(3):
            x, y = stack["x"] + stack["width"] / 2, stack["y"] + stack["height"] / 2
            selected = page.evaluate(
                """([x, y]) => document.elementFromPoint(x, y)
              ?.closest('[data-graph-node]')?.dataset.selected === 'true'""",
                [x, y],
            )
            (page.mouse.click if selected else page.mouse.dblclick)(x, y)
            assert page.locator("[data-graph-node][data-selected='true']").count() == 1
            _change(page, '[data-exact-field="x"]', str(100 + index * index * 300))
            _change(page, '[data-exact-field="y"]', str(900 + index * index * 200))
        _select_node(page, "API")
        _select_node(page, "SQL", add=True)
        _select_node(page, "Blobs", add=True)
        page.locator('[data-arrange-action="distribute-horizontal"]').click()
        ordered = sorted(box(), key=lambda node: node["x"])
        gaps = [ordered[i + 1]["x"] - (ordered[i]["x"] + ordered[i]["width"]) for i in range(2)]
        assert abs(gaps[0] - gaps[1]) <= 4, gaps
        page.locator('[data-arrange-action="distribute-vertical"]').click()
        ordered = sorted(box(), key=lambda node: node["y"])
        gaps = [ordered[i + 1]["y"] - (ordered[i]["y"] + ordered[i]["height"]) for i in range(2)]
        assert abs(gaps[0] - gaps[1]) <= 4, gaps

        _select_node(page, "API")
        _select_node(page, "SQL", add=True)
        page.locator('[data-arrange-action="group"]').click()
        group = next(item for item in _state(page)["boundaries"] if item.get("userGroup"))
        assert _node(page, "API")["boundaryId"] == group["id"] == _node(page, "SQL")["boundaryId"]
        assert page.locator('[data-arrange-action="ungroup"]').is_enabled()
        page.locator('[data-arrange-action="ungroup"]').click()
        assert not any(item.get("userGroup") for item in _state(page)["boundaries"])
        assert _node(page, "API")["boundaryId"] is None

        _select_node(page, "Gateway")
        detach = page.locator('[data-arrange-action="detach"]')
        assert detach.is_enabled()
        detach.click()
        assert _node(page, "Gateway")["boundaryId"] is None

        vnet = _boundary(page, "vnet-review")
        page.locator('[data-inspector-tab="layers"]').click()
        page.locator(f'[data-frame-select="{vnet["id"]}"]').click()
        page.locator('[data-inspector-tab="arrange"]').click()
        shrink = page.locator('[data-arrange-action="shrink-fit"]')
        assert shrink.is_enabled()
        shrink.click()
        fitted = _boundary(page, "vnet-review")
        web = _node(page, "Web")
        assert fitted["width"] <= vnet["width"] and fitted["x"] <= web["x"]
        assert fitted["x"] + fitted["width"] >= web["x"] + web["width"]

        lock = page.locator('[data-arrange-action="lock"]')
        lock.click()
        assert _boundary(page, "vnet-review")["locked"] is True
        assert page.locator('[data-exact-field="x"]').is_disabled(), (
            "a locked frame's geometry is read-only"
        )
        lock.click()
        assert _boundary(page, "vnet-review")["locked"] is False


def test_layers_panel_frames_and_provider_layers(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        page.locator('[data-inspector-tab="layers"]').click()
        vnet = _boundary(page, "vnet-review")
        select = page.locator(f'[data-frame-select="{vnet["id"]}"]')
        select.click()
        assert (
            page.locator(f'[data-frame-select="{vnet["id"]}"]').get_attribute("aria-pressed")
            == "true"
        )
        assert page.locator(f'[data-boundary-id="{vnet["id"]}"][data-selected="true"]').count() == 1

        lock = page.locator(f'[data-frame-lock="{vnet["id"]}"]')
        lock.click()
        assert _boundary(page, "vnet-review")["locked"] is True
        assert (
            page.locator(f'[data-frame-lock="{vnet["id"]}"]').get_attribute("aria-pressed")
            == "true"
        )
        page.locator(f'[data-frame-lock="{vnet["id"]}"]').click()
        assert _boundary(page, "vnet-review")["locked"] is False

        layer = _state(page)["layers"][0]
        visible = page.locator(f'[data-layer-visible="{layer["id"]}"]')
        shown = page.locator("[data-graph-node]:visible").count()
        visible.uncheck()
        assert (
            next(item for item in _state(page)["layers"] if item["id"] == layer["id"])["visible"]
            is False
        )
        assert page.locator("[data-graph-node]:visible").count() < shown
        page.locator(f'[data-layer-visible="{layer["id"]}"]').check()
        assert page.locator("[data-graph-node]:visible").count() == shown

        page.locator(f'[data-layer-lock="{layer["id"]}"]').click()
        assert (
            next(item for item in _state(page)["layers"] if item["id"] == layer["id"])["locked"]
            is True
        )
        assert (
            page.locator(f'[data-layer-lock="{layer["id"]}"]').get_attribute("aria-pressed")
            == "true"
        )
        page.locator(f'[data-layer-lock="{layer["id"]}"]').click()
        assert (
            next(item for item in _state(page)["layers"] if item["id"] == layer["id"])["locked"]
            is False
        )


def test_inspector_guides_an_empty_selection_counts_the_drawing_and_reads_out_colours(
    tmp_path: Path,
) -> None:
    with _editor(tmp_path) as (page, _errors):
        # the controls and every label of the drawing are set in Inter
        assert page.evaluate(
            "getComputedStyle(document.querySelector('.md-tab')).fontFamily"
        ).startswith("Inter")
        assert page.evaluate("document.fonts.check('500 14px Inter')")
        drawing = page.evaluate(
            "[...document.querySelectorAll('[data-graph-layer] text')]"
            ".map(text => getComputedStyle(text).fontFamily)"
        )
        assert drawing and all(family.startswith("Inter") for family in drawing), set(drawing)

        state = _state(page)
        counts = {
            key: page.locator(f'[data-diagram-stat="{key}"]').inner_text()
            for key in ("nodes", "edges", "boundaries")
        }
        assert counts == {key: str(len(state[key])) for key in counts}, counts

        # nothing selected: each selection panel says what to select instead of disabled controls
        for tab in ("style", "text", "arrange"):
            page.locator(f'[data-inspector-tab="{tab}"]').click()
            panel = page.locator(f'[data-inspector-panel="{tab}"]')
            assert panel.locator("[data-inspector-empty]").is_visible(), tab
            assert panel.locator(".inspector-subsection").first.is_hidden(), tab

        # a selection brings the controls back, and a colour field reads out its value
        _select_node(page, "API")
        page.locator('[data-inspector-tab="text"]').click()
        panel = page.locator('[data-inspector-panel="text"]')
        assert panel.locator("[data-inspector-empty]").is_hidden()
        assert panel.locator('[data-content-control="name"]').input_value() == "API"
        _change(page, '[data-text-control="textColor"]', "#aa3300")
        colour = page.locator('[data-text-control="textColor"] + .md-color-field__value')
        assert colour.inner_text().lower() == "#aa3300"

        # a connector's text is its label: the card's name fields step aside
        _select_edge(page, "HTTPS")
        assert page.locator("[data-content-section]").is_hidden()
        assert page.locator("[data-edge-label-section]").is_visible()
        assert (
            page.locator('[data-edge-style-control="stroke"] + .md-color-field__value')
            .inner_text()
            .startswith("#")
        )

        # the counts follow the drawing
        _select_node(page, "Blobs")
        page.keyboard.press("Delete")
        page.locator('[data-inspector-tab="diagram"]').click()
        assert page.locator('[data-diagram-stat="nodes"]').inner_text() == str(
            len(_state(page)["nodes"])
        )


def test_a_press_on_the_canvas_takes_the_keyboard_from_the_search_box(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        search = page.locator("[data-sidebar-search]")
        search.click()
        search.type("sql")
        assert page.locator('.provider-sidebar[data-searching="true"]').count() == 1
        # while searching, a category over its matches is a heading, not a selected item
        heading = page.locator(".category[open] > summary").first
        assert (
            heading.evaluate("element => getComputedStyle(element).backgroundColor")
            == "rgba(0, 0, 0, 0)"
        )
        search.fill("")
        before = len(_state(page)["nodes"])
        _select_node(page, "SQL")
        assert page.evaluate("document.activeElement?.matches('[data-sidebar-search]')") is False
        page.keyboard.press("Delete")
        assert len(_state(page)["nodes"]) == before - 1, (
            "Delete acts on the selection, not the search text"
        )


# ------------------------------------------------------------ frames
_NEW_OVERLAPS = """(before) => {
  const s = window.infragramEditor.getState();
  const boxes = Object.fromEntries([...s.nodes, ...s.boundaries].map(item => [item.id, {
    x: item.x, y: item.y, w: item.width, h: item.height, p: item.boundaryId || item.parentId || null, name: item.name}]));
  const hit = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  const ids = Object.keys(boxes).filter(id => before[id]);
  const found = [];
  ids.forEach((a, i) => ids.slice(i + 1).forEach(b => {
    if (boxes[a].p === boxes[b].p && hit(boxes[a], boxes[b]) && !hit(before[a], before[b])) {
      found.push(`${boxes[a].name} over ${boxes[b].name}`);
    }
  }));
  const spill = ids.filter(id => {
    const box = boxes[id], frame = box.p && boxes[box.p];
    return frame && (box.x < frame.x || box.y < frame.y
      || box.x + box.w > frame.x + frame.w || box.y + box.h > frame.y + frame.h);
  }).map(id => `${boxes[id].name} outside its frame`);
  return [...found, ...spill];
}"""
_BOXES = """() => { const s = window.infragramEditor.getState();
  return Object.fromEntries([...s.nodes, ...s.boundaries].map(item => [item.id, {
    x: item.x, y: item.y, w: item.width, h: item.height}])); }"""


@pytest.mark.parametrize(
    "name", ["azure-aks-baseline", "azure-hub-spoke-landing-zone", "azure-web-app-front-door"]
)
def test_switching_to_icons_makes_room_instead_of_overlapping(tmp_path: Path, name: str) -> None:
    """A stacked card turned into an icon is taller: its neighbours move down to keep their gap
    and every frame grows around them, so no two components that were apart end up on top of
    each other, and nothing spills out of its frame -- both ways."""
    from infragram.projects import CloudProject

    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / f"{name}.html"
    templates = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "infragram-azure"
        / "assets"
        / "templates"
        / "cloud"
    )
    source.write_text(
        render_project_html(CloudProject.load(templates / f"{name}.infragram.json")),
        encoding="utf-8",
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"{source.resolve().as_uri()}?fresh={tmp_path.name}")
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            before = page.evaluate(_BOXES)
            page.evaluate("window.infragramEditor.setDisplayMode('icon')")
            assert page.evaluate(_NEW_OVERLAPS, before) == []
            page.evaluate("window.infragramEditor.setDisplayMode('card')")
            assert page.evaluate(_NEW_OVERLAPS, before) == []
        finally:
            browser.close()


def _frame_spot(page, frame_id: str) -> dict:
    """A spot on the frame that no card, wire or caption covers."""
    # a zoom or scroll settles over the next frames; measure once it has
    spot = page.evaluate(
        """async (id) => {
      await new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done)));
      const r = document.querySelector(`[data-boundary-id="${id}"] [data-boundary-surface]`).getBoundingClientRect();
      for (let fy = 0.9; fy > 0.1; fy -= 0.05) for (let fx = 0.1; fx < 0.9; fx += 0.05) {
        const x = r.left + r.width * fx, y = r.top + r.height * fy;
        const hit = document.elementFromPoint(x, y);
        if (hit?.closest('[data-graph-boundary]')?.dataset.boundaryId === id
            && !hit.closest('[data-graph-node],[data-graph-edge],[data-edge-hit],[data-edge-label]')) return {x, y};
      }
      return null; }""",
        frame_id,
    )
    assert spot, "the frame shows a free spot to click"
    return spot


def _open_frame_menu(page, frame_id: str) -> None:
    """Right-click the frame itself, not what sits on it."""
    spot = _frame_spot(page, frame_id)
    page.mouse.click(spot["x"], spot["y"], button="right")
    assert page.locator("[data-canvas-context-menu]").is_visible()


def test_frame_highlight_contents_display_and_review(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        vnet = _boundary(page, "vnet-review")
        members = {
            node["id"] for node in _state(page)["nodes"] if node.get("boundaryId") == vnet["id"]
        }
        outside = {
            node["id"]: node.get("displayMode", "card")
            for node in _state(page)["nodes"]
            if node["id"] not in members
        }
        assert len(members) == 2

        # highlight from the context menu: saved on the frame, drawn, exported
        _open_frame_menu(page, vnet["id"])
        _menu_entry(page, "frame-highlight").click()
        assert _boundary(page, "vnet-review").get("highlight") is True
        assert (
            page.locator(f'[data-boundary-id="{vnet["id"]}"] [data-frame-highlight]').count() == 1
        )
        document = json.dumps(page.evaluate("window.infragramEditor.exportProject()"))
        assert (
            document.count('"editor_highlight": true') + document.count('"editor_highlight":true')
            == 1
        )
        assert (
            page.evaluate("window.infragramEditor.exportSvg()").count("data-frame-highlight") == 1
        )

        # the frame's contents as icons, from the context menu: only its own components change
        before = page.evaluate(_BOXES)
        _open_frame_menu(page, vnet["id"])
        _menu_entry(page, "frame-display-icon").click()
        state = _state(page)
        assert {node.get("displayMode") for node in state["nodes"] if node["id"] in members} == {
            "icon"
        }
        assert {
            node["id"]: node.get("displayMode", "card")
            for node in state["nodes"]
            if node["id"] not in members
        } == outside
        assert page.evaluate(_NEW_OVERLAPS, before) == []

        # the review lists the frame's components and drives the same operations
        _open_frame_menu(page, vnet["id"])
        page.locator('[data-context-action="frame-review"]').click()
        review = page.locator("[data-frame-review]")
        assert review.is_visible()
        assert page.locator("[data-frame-review-node]").count() == 2
        assert (
            page.locator("[data-frame-review-summary]").inner_text()
            == "2 components · 0 cards · 2 icons"
        )
        assert page.locator("[data-frame-review-highlight]").get_attribute("aria-pressed") == "true"
        assert page.locator('[data-frame-review-display="icon"]').is_disabled()
        row = page.locator("[data-frame-review-node]").first
        chosen = row.get_attribute("data-frame-review-node")
        row.click()
        assert (
            page.locator("[data-frame-review-node]").first.get_attribute("aria-pressed") == "true"
        )
        assert review.is_visible(), "choosing a component keeps the review open"
        assert page.evaluate("document.activeElement?.dataset.frameReviewNode") == chosen, (
            "the keyboard stays on the row"
        )
        saved = page.evaluate("window.infragramEditor.exportHtml()")
        assert re.search(r'<section class="frame-review" data-frame-review[^>]*\shidden', saved), (
            "a saved page opens without it"
        )
        page.locator('[data-frame-review-display="card"]').click()
        assert {
            node.get("displayMode") for node in _state(page)["nodes"] if node["id"] in members
        } == {"card"}
        assert (
            page.locator("[data-frame-review-summary]").inner_text()
            == "2 components · 2 cards · 0 icons"
        )
        page.locator("[data-frame-review-highlight]").click()
        assert _boundary(page, "vnet-review").get("highlight") is None
        document = json.dumps(page.evaluate("window.infragramEditor.exportProject()"))
        assert "editor_highlight" not in document, (
            "a frame no longer called out carries no highlight"
        )
        page.locator("[data-frame-review-close]").click()
        assert review.is_hidden()

        # the Style panel's frame section drives them too
        page.locator('[data-inspector-tab="layers"]').click()
        page.locator(f'[data-frame-select="{vnet["id"]}"]').click()
        page.locator('[data-inspector-tab="style"]').click()
        section = page.locator("[data-frame-style-section]")
        assert section.is_visible()
        assert page.locator("[data-node-display-section]").is_hidden(), (
            "a frame shows its own section, not the card's"
        )
        page.locator("[data-frame-highlight-toggle]").click()
        assert _boundary(page, "vnet-review").get("highlight") is True
        assert page.locator("[data-frame-highlight-toggle]").get_attribute("aria-checked") == "true"
        page.locator('[data-frame-display="icon"]').click()
        assert page.locator('[data-frame-display="icon"]').get_attribute("aria-pressed") == "true"
        page.locator("[data-frame-review-open]").click()
        assert review.is_visible()
        page.keyboard.press("Escape")
        assert review.is_hidden()

        # the highlight is part of the document: a reload keeps it
        page.reload()
        page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
        assert _boundary(page, "vnet-review").get("highlight") is True


_ICON_OVERLAPS = """() => {
  const s = window.infragramEditor.getState();
  const icons = s.nodes.filter(node => node.displayMode === 'icon');
  const hit = (a, b) => a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
  const found = [];
  icons.forEach((a, i) => icons.slice(i + 1).forEach(b => {
    if ((a.boundaryId || null) === (b.boundaryId || null) && hit(a, b)) found.push(`${a.name} on ${b.name}`);
  }));
  return found;
}"""


def _tangled_page(page, tmp_path: Path) -> Path:
    """The AKS baseline as a reader's browser kept it from a switch made before siblings made
    room: the components of two stacked frames resized into icons about their cards' centres
    and nothing else moved, so each icon lies on the caption of the one above it."""
    from infragram.projects import CloudProject

    templates = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "infragram-azure"
        / "assets"
        / "templates"
        / "cloud"
    )
    source = tmp_path / "laid-out.html"
    laid_out = CloudProject.load(templates / "azure-aks-baseline.infragram.json")
    laid_out.presentation = laid_out.presentation.model_copy(update={"display": "card"})
    source.write_text(render_project_html(laid_out), encoding="utf-8")
    page.goto(f"{source.resolve().as_uri()}?fresh=layout-{tmp_path.name}")
    page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
    document = page.evaluate("window.infragramEditor.exportProject()")

    def tangle(element: dict, inside: bool = False) -> None:
        inside = inside or element.get("name") in (
            "Supply chain and secrets",
            "Observability and governance",
        )
        attributes = element.setdefault("attributes", {})
        if (
            inside
            and not element.get("children")
            and attributes.get("editor_display_mode", "card") == "card"
        ):
            width = float(attributes.get("editor_card_size", {}).get("width") or 208)
            height = float(attributes.get("editor_card_size", {}).get("height") or 64)
            x, y = float(attributes["editor_x"]), float(attributes["editor_y"])
            attributes["editor_card_size"] = {"width": width, "height": height}
            attributes["editor_display_mode"] = "icon"
            attributes["editor_x"] = round(x + width / 2 - 72)
            attributes["editor_y"] = round(y + height / 2 - 58)
        for child in element.get("children") or []:
            tangle(child, inside)

    tangle(document["topology"])
    tangled = tmp_path / "tangled.html"
    tangled.write_text(render_project_html(CloudProject.model_validate(document)), encoding="utf-8")
    return tangled


@pytest.mark.parametrize("how", ["frame", "diagram", "selection"])
def test_choosing_icons_separates_icons_already_on_each_other(tmp_path: Path, how: str) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            source = _tangled_page(page, tmp_path)
            page.goto(f"{source.resolve().as_uri()}?fresh={tmp_path.name}")
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            assert page.evaluate(_ICON_OVERLAPS), "the saved layout starts tangled"
            frames = [
                frame
                for frame in _state(page)["boundaries"]
                if frame["name"] in ("Supply chain and secrets", "Observability and governance")
            ]
            if how == "frame":
                for frame in frames:
                    page.locator('[data-editor-action="zoom-reset"]').click()
                    page.locator(
                        f'[data-boundary-id="{frame["id"]}"] [data-boundary-surface]'
                    ).scroll_into_view_if_needed()
                    _open_frame_menu(page, frame["id"])
                    icons = _menu_entry(page, "frame-display-icon")
                    assert icons.is_enabled(), (
                        "a frame of tangled icons can still be shown as icons"
                    )
                    icons.click()
                    assert (
                        page.locator("[data-snackbar]").inner_text()
                        == f"Overlapping icons in {frame['name']} moved apart"
                    ), "nothing changed mode, so none is counted"
            elif how == "diagram":
                page.locator('[data-inspector-tab="diagram"]').click()
                page.locator('[data-project-display="icon"]').click()
            else:
                tangled = [
                    node
                    for node in _state(page)["nodes"]
                    if node.get("boundaryId") in {frame["id"] for frame in frames}
                ]
                first, *rest = tangled
                _select_node(page, first["name"])
                for node in rest:
                    page.locator(f'[data-graph-node][data-node-id="{node["id"]}"]').click(
                        modifiers=["Shift"], force=True
                    )
                page.locator(f'[data-graph-node][data-node-id="{first["id"]}"]').click(
                    button="right", force=True
                )
                _menu_entry(page, "display-icon").click()
            assert page.evaluate(_ICON_OVERLAPS) == []
            spill = page.evaluate(_NEW_OVERLAPS, page.evaluate(_BOXES))
            assert spill == [], "and nothing is left outside its frame"
        finally:
            browser.close()


def test_icon_only_and_card_with_text_act_on_the_whole_selection(tmp_path: Path) -> None:
    """With several cards selected, Icon only turned the card clicked last into an icon and left
    the rest as cards, and the Style panel's display buttons were disabled. Both act on every
    selected component now, and on the components inside a selected frame."""
    with _editor(tmp_path) as (page, _errors):
        _select_node(page, "API")
        _select_node(page, "SQL", add=True)
        _select_node(page, "SQL", button="right")
        _menu_entry(page, "display-icon").click()
        assert (_node(page, "API").get("displayMode"), _node(page, "SQL").get("displayMode")) == (
            "icon",
            "icon",
        )
        assert _node(page, "Blobs").get("displayMode", "card") == "card", (
            "only the selection changes"
        )

        page.locator('[data-inspector-tab="style"]').click()
        card = page.locator('button[data-display-mode="card"]')
        assert card.is_enabled(), "the Style panel's display acts on a selection of several"
        assert (
            page.locator('button[data-display-mode="icon"]').get_attribute("aria-pressed") == "true"
        )
        card.click()
        assert (_node(page, "API").get("displayMode"), _node(page, "SQL").get("displayMode")) == (
            "card",
            "card",
        )

        # a frame and a card selected together: the frame's contents and the card
        vnet = _boundary(page, "vnet-review")
        page.keyboard.press("Escape")
        page.locator('[data-inspector-tab="layers"]').click()
        page.locator(f'[data-frame-select="{vnet["id"]}"]').click()
        _select_node(page, "Blobs", add=True)
        _select_node(page, "Blobs", button="right")
        _menu_entry(page, "display-icon").click()
        framed = [node for node in _state(page)["nodes"] if node.get("boundaryId") == vnet["id"]]
        assert framed and {node.get("displayMode") for node in framed} == {"icon"}
        assert _node(page, "Blobs").get("displayMode") == "icon"
        assert _node(page, "API").get("displayMode", "card") == "card"


def test_feedback_shows_in_a_snackbar_and_the_selection_toolbar_switches_display(
    tmp_path: Path,
) -> None:
    """What an action did is shown for a few seconds, not only announced: the status line it used
    to reach left the header. Routine reports (selection counts, search counts) stay quiet. The
    floating toolbar switches the selection between icons and cards, and the canvas hint steps
    aside once the canvas has been used."""
    with _editor(tmp_path) as (page, _errors):
        snackbar = page.locator("[data-snackbar]")
        hint = page.locator("[data-editor-help]")
        assert snackbar.is_hidden(), "nothing is reported before anything is done"
        assert hint.evaluate("element => getComputedStyle(element).opacity") == "1"

        _select_node(page, "API")
        assert snackbar.is_hidden(), "selecting is not an action worth a snackbar"
        page.wait_for_function(
            "getComputedStyle(document.querySelector('[data-editor-help]')).opacity === '0'"
        )
        to_icons = page.locator('[data-selection-action="display-icon"]')
        to_cards = page.locator('[data-selection-action="display-card"]')
        assert to_icons.is_visible() and to_cards.is_hidden()
        to_icons.click()
        assert _node(page, "API")["displayMode"] == "icon"
        assert snackbar.is_visible() and snackbar.inner_text() == "API displayed as an icon"
        assert to_cards.is_visible() and to_icons.is_hidden()
        to_cards.click()
        assert _node(page, "API")["displayMode"] == "card"
        assert snackbar.inner_text() == "API displayed as a card"

        # a page saved while the snackbar shows opens without it, and with its hint
        saved = page.evaluate("window.infragramEditor.exportHtml()")
        saved_snackbar = re.search(r"<div [^>]*data-snackbar[^>]*>(.*?)</div>", saved)
        assert saved_snackbar and re.search(
            r"\shidden(=\"\")?[\s>]", saved_snackbar.group(0) + " "
        ), saved_snackbar
        assert "style=" not in saved_snackbar.group(0) and saved_snackbar.group(1) == "", (
            "a saved page never opens on a stale snackbar"
        )
        saved_hint = re.search(r"<p [^>]*data-editor-help[^>]*>", saved).group(0)
        assert "canvas-help--retired" not in saved_hint, "a saved page shows its reader the hint"

        page.locator("[data-sidebar-search]").fill("sql")
        assert snackbar.inner_text() == "API displayed as a card", (
            "search counts are announced, not shown"
        )
        page.wait_for_function("document.querySelector('[data-snackbar]').hidden", timeout=6000)


# ------------------------------------------------------ canvas overlays
def test_selection_toolbar_actions(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        toolbar = page.locator("[data-selection-toolbar]")
        assert toolbar.is_hidden()
        _select_node(page, "Gateway")
        assert toolbar.is_visible()
        assert page.locator('[data-selection-action="detach"]').is_visible(), (
            "a framed card can leave its frame"
        )
        _select_node(page, "SQL")
        assert page.locator('[data-selection-action="detach"]').is_hidden()

        _select_node(page, "Blobs", add=True)
        assert page.locator("[data-selection-count-chip]").inner_text() == "2"
        page.locator('[data-selection-action="align-left"]').click()
        assert _node(page, "SQL")["x"] == _node(page, "Blobs")["x"]
        page.locator('[data-selection-action="align-top"]').click()
        assert _node(page, "SQL")["y"] == _node(page, "Blobs")["y"]
        page.locator('[data-selection-action="to-front"]').click()
        orders = [node["order"] for node in _state(page)["nodes"]]
        assert {_node(page, "SQL")["order"], _node(page, "Blobs")["order"]} == set(
            sorted(orders)[-2:]
        )

        lock = page.locator('[data-selection-action="lock"]')
        lock.click()
        assert _node(page, "SQL")["locked"] is True
        assert lock.get_attribute("aria-pressed") == "true"
        assert page.locator('[data-selection-action="delete"]').is_disabled()
        lock.click()
        assert _node(page, "SQL")["locked"] is False

        page.locator('[data-selection-action="group"]').click()
        assert any(item.get("userGroup") for item in _state(page)["boundaries"])
        _select_node(page, "Gateway")
        page.locator('[data-selection-action="detach"]').click()
        assert _node(page, "Gateway")["boundaryId"] is None

        count = len(_state(page)["nodes"])
        page.locator('[data-selection-action="delete"]').click()
        assert len(_state(page)["nodes"]) == count - 1


def test_context_menu_actions(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        menu = page.locator("[data-canvas-context-menu]")

        def open_on(name: str) -> None:
            _select_node(page, name, button="right")
            assert menu.is_visible()
            box = menu.bounding_box()
            assert box["y"] >= 0 and box["y"] + box["height"] <= 900, "the menu fits the window"
            assert menu.locator('[data-context-action="delete"]').is_visible() or menu.evaluate(
                "element => element.scrollHeight > element.clientHeight"
            )

        def choose(action: str) -> None:
            _menu_entry(page, action).click()
            assert menu.is_hidden(), f"{action} closes the menu"

        open_on("API")
        assert menu.locator("[data-context-menu-title]").inner_text() == "API"
        choose("edit-text")
        assert page.locator('[data-inspector-tab="text"]').get_attribute("aria-selected") == "true"
        page.wait_for_function("document.activeElement?.dataset.contentControl === 'name'")
        open_on("API")
        choose("open-style")
        assert page.locator('[data-inspector-tab="style"]').get_attribute("aria-selected") == "true"
        open_on("API")
        choose("open-arrange")
        assert (
            page.locator('[data-inspector-tab="arrange"]').get_attribute("aria-selected") == "true"
        )

        open_on("API")
        assert (
            menu.locator('[data-context-action="display-card"]').get_attribute("aria-checked")
            == "true"
        )
        choose("display-icon")
        assert _node(page, "API")["displayMode"] == "icon"
        open_on("API")
        assert (
            menu.locator('[data-context-action="display-icon"]').get_attribute("aria-checked")
            == "true"
        )
        choose("display-card")
        assert _node(page, "API")["displayMode"] == "card"

        orders = lambda: {node["name"]: node["order"] for node in _state(page)["nodes"]}  # noqa: E731
        open_on("API")
        choose("to-back")
        assert orders()["API"] == min(orders().values())
        open_on("API")
        choose("forward")
        assert orders()["API"] == min(orders().values()) + 1
        open_on("API")
        choose("to-front")
        assert orders()["API"] == max(orders().values())
        open_on("API")
        choose("backward")
        assert orders()["API"] == max(orders().values()) - 1

        open_on("Gateway")
        choose("detach")
        assert _node(page, "Gateway")["boundaryId"] is None

        _select_node(page, "SQL")
        _select_node(page, "Blobs", add=True)
        open_on("Blobs")
        choose("group")
        group = next(item for item in _state(page)["boundaries"] if item.get("userGroup"))
        _open_frame_menu(page, group["id"])
        assert _menu_entry(page, "ungroup").is_visible()
        assert _menu_entry(page, "shrink-fit").is_visible()
        choose("shrink-fit")
        _open_frame_menu(page, group["id"])
        choose("ungroup")
        assert not any(item.get("userGroup") for item in _state(page)["boundaries"])

        open_on("API")
        choose("lock")
        assert _node(page, "API")["locked"] is True
        open_on("API")
        assert (
            menu.locator('[data-context-action="lock"] .md-list-item__label').inner_text()
            == "Unlock"
        )
        assert menu.locator('[data-context-action="delete"]').is_disabled()
        choose("lock")
        assert _node(page, "API")["locked"] is False
        count = len(_state(page)["nodes"])
        open_on("API")
        choose("delete")
        assert len(_state(page)["nodes"]) == count - 1

        _select_edge(page, "HTTPS")
        edge_id = _edge(page, "HTTPS")["id"]
        page.evaluate(
            f"() => window.infragramEditor.setEdgeLabelPlacement({json.dumps(edge_id)}, {{dx: 30, dy: 10}})"
        )
        page.locator(f'[data-edge-label][data-edge-id="{edge_id}"]').click(button="right")
        assert menu.locator('[data-context-action="reset-label-position"]').is_visible()
        choose("reset-label-position")
        assert "labelPlacement" not in _edge(page, "HTTPS")

        before = _edge(page, "HTTPS")
        page.locator(f'[data-edge-label][data-edge-id="{edge_id}"]').click(button="right")
        assert menu.locator('[data-context-action="edge-reset-route"]').is_disabled(), (
            "nothing moved by hand"
        )
        choose("edge-reverse")
        after = _edge(page, "HTTPS")
        assert (after["source"], after["target"]) == (before["target"], before["source"])
        page.evaluate(
            f"() => window.infragramEditor.setEdgeLabelPlacement({json.dumps(edge_id)}, {{dx: 30, dy: 10}})"
        )
        page.locator(f'[data-edge-label][data-edge-id="{edge_id}"]').click(button="right")
        assert menu.locator('[data-context-action="edge-reset-route"]').is_enabled()
        choose("edge-reset-route")
        assert not {"labelPlacement", "waypoints"} & set(_edge(page, "HTTPS"))


# ------------------------------------------------------ keyboard, layout
def test_keyboard_focus_escape_and_shortcuts(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        page.locator("[data-sidebar-search]").focus()
        page.keyboard.press("Shift+Tab")
        outline = page.evaluate(
            "() => { const style = getComputedStyle(document.activeElement);"
            " return [document.activeElement.dataset.sidebarLogoTrigger !== undefined, style.outlineStyle, style.outlineWidth]; }"
        )
        assert outline == [True, "solid", "2px"], outline

        _select_node(page, "API")
        page.keyboard.press("Escape")
        assert page.locator("[data-graph-node][data-selected='true']").count() == 0
        assert page.locator("[data-selection-toolbar]").is_hidden()

        count = len(_state(page)["nodes"])
        _select_node(page, "API")
        page.keyboard.press("Delete")
        assert len(_state(page)["nodes"]) == count - 1
        page.keyboard.press("Control+z")
        assert len(_state(page)["nodes"]) == count
        page.keyboard.press("Control+Shift+z")
        assert len(_state(page)["nodes"]) == count - 1


def test_narrow_window_keeps_every_control_reachable(tmp_path: Path) -> None:
    with _editor(tmp_path, viewport=(820, 900)) as (page, _errors):
        assert round(page.locator(".provider-sidebar").bounding_box()["width"]) == 48
        assert round(page.locator("[data-right-inspector]").bounding_box()["width"]) == 48
        for selector in (
            '[data-editor-action="undo"]',
            '[data-editor-action="zoom-in"]',
            "[data-theme-toggle]",
        ):
            box = page.locator(selector).bounding_box()
            assert box["height"] >= 44 and box["x"] + box["width"] <= 820, selector
        page.locator("[data-download-menu] > summary").click()
        item = page.locator("[data-download-svg]").bounding_box()
        assert item and item["x"] >= 0 and item["x"] + item["width"] <= 820, (
            "the menu stays on screen"
        )
        page.keyboard.press("Escape")
        page.locator("[data-sidebar-logo-trigger]").click()
        page.wait_for_timeout(250)
        assert page.locator("[data-sidebar-search]").is_visible(), "the rail opens over the canvas"
        page.locator("[data-inspector-toggle]").click()
        page.wait_for_timeout(250)
        assert page.locator("[data-right-inspector]").bounding_box()["width"] >= 48


WIRE_POINT = """(id) => {
  const hit = document.querySelector(`[data-edge-hit="${id}"]`);
  const total = hit.getTotalLength();
  for (const share of [0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8]) {
    const at = hit.getPointAtLength(total * share);
    const m = hit.getScreenCTM();
    const x = at.x * m.a + at.y * m.c + m.e, y = at.x * m.b + at.y * m.d + m.f;
    const top = document.elementFromPoint(x, y);
    if (top && (top.dataset.edgeHit === id || top.dataset.edgeId === id)) return {x, y};
  }
  return null;
}"""


def _middle(page, selector: str) -> tuple[float, float]:
    box = page.locator(selector).first.bounding_box()
    assert box is not None, selector
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _card(page, name: str) -> str:
    return f'[data-node-id="{_node(page, name)["id"]}"] [data-node-surface]'


def _drag(
    page, start: tuple[float, float], end: tuple[float, float], *, release: bool = True
) -> None:
    page.mouse.move(*start)
    page.mouse.down()
    page.mouse.move((start[0] + end[0]) / 2, (start[1] + end[1]) / 2, steps=6)
    page.mouse.move(*end, steps=6)
    if release:
        page.mouse.up()


def test_connectors_are_drawn_by_dragging_and_edited_once_selected(tmp_path: Path) -> None:
    """Like an ETL canvas: drag from a card's handle, drop anywhere on another card."""
    with _editor(tmp_path) as (page, _errors):
        toolbar = page.locator("[data-selection-toolbar]")
        snackbar = page.locator("[data-snackbar]")
        api, gateway, blobs = (_node(page, name)["id"] for name in ("API", "Gateway", "Blobs"))
        count = len(_state(page)["edges"])

        page.mouse.move(*_middle(page, _card(page, "API")))
        middle = _middle(page, _card(page, "API"))
        assert page.evaluate(
            "([x, y]) => !document.elementFromPoint(x, y).closest('[data-node-port]')", list(middle)
        ), "the handles leave the middle of the card free for moving it"
        handle = _middle(
            page, f'[data-node-id="{api}"] [data-node-port="right"] circle.node-port-dot'
        )
        _drag(page, handle, _middle(page, _card(page, "Gateway")), release=False)
        target = page.locator(f'[data-graph-node][data-node-id="{gateway}"]')
        assert target.get_attribute("data-connect-target") == "true", (
            "the card under the pointer lights up"
        )
        # it fades up from whatever dimming it had, so give the transition its 120ms
        page.wait_for_function(
            """id => getComputedStyle(document.querySelector(`[data-graph-node][data-node-id="${id}"]`)).opacity === '1'""",
            arg=gateway,
        )
        assert page.locator("[data-connection-preview]").count() == 1
        assert page.locator(".canvas-viewport").get_attribute("data-connecting") == "true"
        assert toolbar.is_hidden(), "no toolbar floats over the line being drawn"
        page.mouse.up()

        edges = _state(page)["edges"]
        assert len(edges) == count + 1, (
            "a drop on the card body connects; no need to find its handle"
        )
        wire = next(edge for edge in edges if edge["source"] == api and edge["target"] == gateway)
        assert page.locator(".canvas-viewport").get_attribute("data-connecting") is None
        assert snackbar.inner_text() == "Connector added"
        for action in ("edge-edit-label", "edge-reverse", "edge-reset-route", "delete"):
            assert page.locator(f'[data-selection-action="{action}"]').is_visible(), action
        for action in ("align-left", "group", "lock"):
            assert page.locator(f'[data-selection-action="{action}"]').is_hidden(), action
        # it was drawn out of one particular handle, so that side is pinned and
        # Reset route is what hands it back to the router
        assert page.locator('[data-selection-action="edge-reset-route"]').is_enabled()
        assert wire["sourcePort"] == "right", (
            f"drawn from the right handle, not {wire['sourcePort']}"
        )
        assert page.locator(f'[data-edge-end][data-edge-id="{wire["id"]}"]').count() == 2

        page.locator('[data-selection-action="edge-reverse"]').click()
        reversed_wire = _state(page)["edges"][-1]
        assert (reversed_wire["source"], reversed_wire["target"]) == (gateway, api)

        end = _middle(page, f'[data-edge-end="target"][data-edge-id="{wire["id"]}"]')
        _drag(page, end, _middle(page, _card(page, "Blobs")), release=False)
        assert (
            page.locator(f'[data-edge-group="{wire["id"]}"][data-reconnecting="true"]').count() == 1
        )
        assert page.locator("[data-connection-preview]").count() == 1
        page.mouse.up()
        moved = next(edge for edge in _state(page)["edges"] if edge["id"] == wire["id"])
        assert (moved["source"], moved["target"]) == (gateway, blobs)
        assert snackbar.inner_text() == "Connector now ends at Blobs"

        end = _middle(page, f'[data-edge-end="target"][data-edge-id="{wire["id"]}"]')
        _drag(page, end, _middle(page, _card(page, "Gateway")))
        assert (
            next(edge for edge in _state(page)["edges"] if edge["id"] == wire["id"])["target"]
            == blobs
        )
        assert snackbar.inner_text() == "A connector cannot start and end on the same component"

        page.locator('[data-selection-action="edge-edit-label"]').click()
        page.wait_for_function("document.activeElement?.dataset?.edgeLabelControl === 'label'")

        page.mouse.move(*_middle(page, _card(page, "API")))
        handle = _middle(
            page, f'[data-node-id="{api}"] [data-node-port="bottom"] circle.node-port-dot'
        )
        _drag(page, handle, _middle(page, _card(page, "SQL")), release=False)
        page.keyboard.press("Escape")
        page.mouse.up()
        assert len(_state(page)["edges"]) == count + 1, "Escape drops the line being drawn"
        assert page.locator("[data-connection-preview]").count() == 0

        spot = page.evaluate(WIRE_POINT, wire["id"])
        assert spot, "the wire can be reached with the pointer"
        page.mouse.move(spot["x"], spot["y"])
        glow = page.locator(f'[data-edge-group="{wire["id"]}"] [data-graph-edge]').evaluate(
            "element => getComputedStyle(element).filter"
        )
        assert "drop-shadow" in glow, "the wire under the pointer shows it can be clicked"
        _select_wire(page, wire["id"])
        page.keyboard.press("Delete")
        assert len(_state(page)["edges"]) == count
        assert snackbar.inner_text() == "Connector deleted"
        page.keyboard.press("Control+z")
        assert len(_state(page)["edges"]) == count + 1

        _select_wire(page, wire["id"])
        page.locator('[data-selection-action="delete"]').click()
        assert len(_state(page)["edges"]) == count


def test_drawing_a_connector_survives_a_cancelled_gesture_and_respects_a_lock(
    tmp_path: Path,
) -> None:
    """A drag the browser takes away, and a component that refuses to be wired up."""
    with _editor(tmp_path) as (page, _errors):
        api, sql = _node(page, "API")["id"], _node(page, "SQL")["id"]
        count = len(_state(page)["edges"])
        viewport = page.locator(".canvas-viewport")

        page.mouse.move(*_middle(page, _card(page, "API")))
        handle = _middle(
            page, f'[data-node-id="{api}"] [data-node-port="right"] circle.node-port-dot'
        )
        _drag(page, handle, _middle(page, _card(page, "SQL")), release=False)
        assert page.locator("[data-connection-preview]").count() == 1
        # A touch that becomes a scroll, a pen lifted, the window handed away.
        page.evaluate("""() => document.querySelector('[data-infragram-diagram]')
            .dispatchEvent(new PointerEvent('pointercancel', {pointerId: 1, bubbles: true}))""")
        assert page.locator("[data-connection-preview]").count() == 0, (
            "the line goes with the gesture"
        )
        assert viewport.get_attribute("data-connecting") is None, "and so does the crosshair"
        page.mouse.up()
        assert len(_state(page)["edges"]) == count

        # Only the line moves while a connection is drawn: the cards are left alone.
        page.mouse.move(*_middle(page, _card(page, "API")))
        handle = _middle(
            page, f'[data-node-id="{api}"] [data-node-port="right"] circle.node-port-dot'
        )
        _drag(page, handle, _middle(page, _card(page, "SQL")), release=False)
        page.evaluate(
            f"""() => {{ document.querySelector('[data-node-id="{sql}"]').dataset.witness = 'here'; }}"""
        )
        first = page.locator("[data-connection-preview]").get_attribute("d")
        page.mouse.move(*_middle(page, _card(page, "Blobs")), steps=6)
        assert page.locator("[data-connection-preview]").get_attribute("d") != first, (
            "the line follows the pointer"
        )
        assert page.locator(f'[data-node-id="{sql}"]').get_attribute("data-witness") == "here", (
            "the drawing is not rebuilt on every move"
        )
        page.mouse.up()
        assert len(_state(page)["edges"]) == count + 1
        page.keyboard.press("Control+z")

        # A locked component refuses a connector from either end.
        _select_node(page, "SQL")
        page.locator('[data-selection-action="lock"]').click()
        assert _node(page, "SQL")["locked"] is True
        page.mouse.move(*_middle(page, _card(page, "API")))
        handle = _middle(
            page, f'[data-node-id="{api}"] [data-node-port="right"] circle.node-port-dot'
        )
        _drag(page, handle, _middle(page, _card(page, "SQL")), release=False)
        assert (
            page.locator(f'[data-node-id="{sql}"]').get_attribute("data-connect-target") != "true"
        ), "a locked card never offers itself as a target"
        page.mouse.up()
        assert len(_state(page)["edges"]) == count
        assert (
            page.locator("[data-snackbar]").inner_text()
            == "Locked layer · connectors cannot be added"
        )


def test_copy_paste_duplicate_and_cut(tmp_path: Path) -> None:
    """The clipboard: a frame brings what it holds, and a connector its two ends."""
    with _editor(tmp_path) as (page, _errors):
        snackbar = page.locator("[data-snackbar]")
        start = len(_state(page)["nodes"])
        api = _node(page, "API")

        _select_node(page, "API")
        page.keyboard.press("Control+c")
        assert snackbar.inner_text() == "1 component copied"
        page.keyboard.press("Control+v")
        assert len(_state(page)["nodes"]) == start + 1
        copy = _state(page)["nodes"][-1]
        assert copy["name"] == "API" and copy["id"] != api["id"]
        assert (copy["x"], copy["y"]) == (api["x"] + 24, api["y"] + 24), (
            "the copy is offset, not hidden under the original"
        )
        assert copy["boundaryId"] == api["boundaryId"] and copy["locked"] is False
        assert (
            page.locator(f'[data-node-id="{copy["id"]}"]').get_attribute("data-selected") == "true"
        )

        page.keyboard.press("Control+v")
        stepped = _state(page)["nodes"][-1]
        assert (stepped["x"], stepped["y"]) == (api["x"] + 48, api["y"] + 48), (
            "copies step instead of stacking"
        )
        page.keyboard.press("Control+z")
        page.keyboard.press("Control+z")
        assert len(_state(page)["nodes"]) == start

        # two components and the connector between them travel together
        edges = len(_state(page)["edges"])
        _select_node(page, "API")
        _select_node(page, "SQL", add=True)
        page.keyboard.press("Control+c")
        page.keyboard.press("Control+v")
        assert len(_state(page)["nodes"]) == start + 2
        assert len(_state(page)["edges"]) == edges + 1, (
            "the TDS connector is copied with both of its ends"
        )
        pasted = {node["id"] for node in _state(page)["nodes"][-2:]}
        fresh = _state(page)["edges"][-1]
        assert {fresh["source"], fresh["target"]} == pasted, (
            "and it joins the copies, not the originals"
        )
        page.keyboard.press("Control+z")

        # a frame brings what it holds
        frame = _boundary(page, "vnet-review")
        held = [node for node in _state(page)["nodes"] if node["boundaryId"] == frame["id"]]
        assert held, "the review page has a frame with components in it"
        spot = _frame_spot(page, frame["id"])
        selected = page.locator(
            f'[data-graph-boundary][data-boundary-id="{frame["id"]}"]'
        ).get_attribute("data-selected")
        (page.mouse.click if selected == "true" else page.mouse.dblclick)(spot["x"], spot["y"])
        page.keyboard.press("Control+d")
        assert len(_state(page)["nodes"]) == start + len(held)
        twin = [item for item in _state(page)["boundaries"] if item["name"] == frame["name"]][-1]
        assert twin["id"] != frame["id"]
        assert len(
            [node for node in _state(page)["nodes"] if node["boundaryId"] == twin["id"]]
        ) == len(held), "the components land in the new frame, not the old one"
        page.keyboard.press("Control+z")

        # cut takes it away and keeps it for the next paste
        _select_node(page, "Blobs")
        page.keyboard.press("Control+x")
        assert len(_state(page)["nodes"]) == start - 1
        assert snackbar.inner_text() == "1 component cut"
        page.keyboard.press("Control+v")
        assert len(_state(page)["nodes"]) == start
        assert any(node["name"] == "Blobs" for node in _state(page)["nodes"])

        # the toolbar button and the menu offer the same thing
        _select_node(page, "SQL")
        page.locator('[data-selection-action="duplicate"]').click()
        assert len(_state(page)["nodes"]) == start + 1
        page.keyboard.press("Control+z")
        _select_node(page, "SQL", button="right")
        assert page.locator("[data-canvas-context-menu]").is_visible()
        for action in ("duplicate", "copy", "paste"):
            assert _menu_entry(page, action).is_visible(), action
        _menu_entry(page, "duplicate").click()
        assert len(_state(page)["nodes"]) == start + 1
        page.keyboard.press("Control+z")

        # and none of it fires while text is being typed
        _select_node(page, "SQL")
        page.locator('[data-inspector-tab="text"]').click()
        field = page.locator('[data-content-control="name"]')
        field.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Control+c")
        page.keyboard.press("Control+v")
        assert len(_state(page)["nodes"]) == start, "Ctrl+C in a field copies text, not the drawing"


def _longest_wire(page) -> str:
    """The wire with the most room for the pointer: two adjacent cards leave
    barely 20px of wire between them, most of it under their port handles."""
    return page.evaluate("""() => window.infragramEditor.getState().edges
      .map(edge => ({id: edge.id,
        length: document.querySelector(`[data-edge-hit="${edge.id}"]`)?.getTotalLength() || 0}))
      .sort((a, b) => b.length - a.length)[0].id""")


def _edge_by_id(page, edge_id: str) -> dict:
    return next(edge for edge in _state(page)["edges"] if edge["id"] == edge_id)


def _wire_spot(page, edge_id: str) -> dict:
    """A point on the wire that the pointer can reach."""
    spot = page.evaluate(
        """(id) => {
      const hit = document.querySelector(`[data-edge-hit="${id}"]`);
      const total = hit.getTotalLength();
      // the label sits at the middle of the wire, so work outwards from there
      for (let step = 0; step <= 16; step += 1) {
        const share = 0.5 + (step % 2 ? -1 : 1) * 0.05 * Math.ceil(step / 2);
        if (share <= 0.05 || share >= 0.95) continue;
        const at = hit.getPointAtLength(total * share);
        const m = hit.getScreenCTM();
        const x = at.x * m.a + at.y * m.c + m.e, y = at.x * m.b + at.y * m.d + m.f;
        const top = document.elementFromPoint(x, y);
        if (top?.closest('[data-edge-hit]')?.dataset.edgeHit === id) return {x, y};
      }
      return null; }""",
        edge_id,
    )
    assert spot, "the wire can be reached with the pointer"
    return spot


def _select_wire(page, edge_id: str) -> None:
    """Pick a wire through the pointer without double-clicking an edited wire."""
    spot = _wire_spot(page, edge_id)
    selected = page.locator(f'[data-edge-group="{edge_id}"] [data-edge-selection-halo]').count()
    (page.mouse.click if selected else page.mouse.dblclick)(spot["x"], spot["y"])


def test_a_dialog_holds_the_keyboard_while_it_is_open(tmp_path: Path) -> None:
    """Tab off the last control of a dialog and the browser used to walk on
    into the canvas and the sidebar behind it: a reader using the keyboard
    left the dialog without closing it, and a reader using a screen reader was
    read a page the dialog was sitting on top of."""
    with _editor(tmp_path) as (page, _errors):
        nothing = page.locator("[data-inspector-selection]").text_content().strip()
        components = len(_state(page)["nodes"])
        opener = page.locator('[data-editor-action="shortcuts"]')
        opener.click()
        sheet = page.locator("[data-shortcut-sheet]")
        page.wait_for_selector("[data-shortcut-sheet]:not([hidden])")
        assert sheet.get_attribute("aria-modal") == "true", "a modal dialog says so"

        inside = []
        for _ in range(12):
            page.keyboard.press("Tab")
            inside.append(
                page.evaluate(
                    "() => Boolean(document.activeElement?.closest('[data-shortcut-sheet]'))"
                )
            )
        assert all(inside), f"Tab left the dialog on move {inside.index(False) + 1}"
        # Focus staying inside proves nothing on its own: the editor's own Tab
        # used to take the key first -- stepping through the drawing behind the
        # sheet, one component a press -- so focus never moved and this passed
        # while twelve components were selected behind the dialog.
        assert page.locator("[data-inspector-selection]").text_content().strip() == nothing, (
            "Tab stepped through the drawing behind the dialog"
        )
        page.keyboard.press("Delete")
        page.keyboard.press("Control+a")
        assert len(_state(page)["nodes"]) == components, "Delete reached the canvas"
        assert page.locator("[data-inspector-selection]").text_content().strip() == nothing, (
            "Ctrl+A reached the canvas"
        )

        for _ in range(3):
            page.keyboard.press("Shift+Tab")
            assert page.evaluate(
                "() => Boolean(document.activeElement?.closest('[data-shortcut-sheet]'))"
            )

        page.keyboard.press("Escape")
        page.wait_for_selector("[data-shortcut-sheet][hidden]", state="attached")
        assert sheet.get_attribute("aria-modal") is None
        # the keyboard goes back where it came from, not to the top of the page
        assert page.evaluate("() => document.activeElement?.dataset?.editorAction") == "shortcuts"


def test_the_library_menu_gives_the_keyboard_back(tmp_path: Path) -> None:
    """The library menu is a popover on a trigger, not a modal, so it holds no
    Tab and declares no `aria-modal`. It still owes a reader the rest: Escape,
    focus that lands inside what was announced, and focus that comes back.

    Applying used to hide the menu while the Apply button still had focus,
    which drops focus to the document body and loses the reader's place in
    the page entirely.
    """
    with _editor(tmp_path, libraries="all") as (page, _errors):
        trigger = page.locator("[data-provider-menu-trigger]")
        menu = page.locator("[data-provider-menu]")

        trigger.click()
        page.wait_for_selector("[data-provider-menu]:not([hidden])")
        assert trigger.get_attribute("aria-expanded") == "true"
        assert menu.get_attribute("aria-modal") is None, "a popover is not modal"
        assert page.evaluate(
            "() => Boolean(document.activeElement?.closest('[data-provider-menu]'))"
        ), "opening it puts the keyboard in it"

        page.keyboard.press("Escape")
        page.wait_for_selector("[data-provider-menu][hidden]", state="attached")
        assert trigger.get_attribute("aria-expanded") == "false"
        assert page.evaluate(
            "() => Boolean(document.activeElement?.closest('[data-provider-menu-trigger]'))"
        ), "Escape gives the keyboard back to the trigger"

        # applying must not leave focus on a button that is now hidden
        trigger.click()
        page.wait_for_selector("[data-provider-menu]:not([hidden])")
        page.locator("[data-provider-apply]").click()
        page.wait_for_selector("[data-provider-menu][hidden]", state="attached")
        assert page.evaluate("() => document.activeElement?.tagName") != "BODY", (
            "focus fell out of the page when the menu that held it was hidden"
        )
        assert page.evaluate(
            "() => Boolean(document.activeElement?.closest('[data-provider-menu-trigger]'))"
        )


def test_tidy_puts_the_layout_back_the_way_it_was_drawn(tmp_path: Path) -> None:
    """A wire could always be un-pinned one at a time, but once cards had been
    dragged there was no way back to the automatic layout.

    It is a restore, not a second implementation: the page carries what the
    renderer laid out, so tidying cannot drift from the static picture. It
    also has to be one step of undo, not one per card.
    """
    with _editor(tmp_path) as (page, _errors):
        before = page.evaluate(
            "() => window.infragramEditor.getState().nodes.map(node => [node.id, node.x, node.y])"
        )
        node_id = before[0][0]

        box = page.locator(f'[data-graph-node][data-node-id="{node_id}"]').bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + 220, box["y"] + 150, steps=8)
        page.mouse.up()
        moved = page.evaluate(
            "id => { const n = window.infragramEditor.getState().nodes"
            ".find(x => x.id === id); return [n.x, n.y]; }",
            node_id,
        )
        assert moved != list(before[0][1:]), "the drag did not move the card"

        page.locator('[data-editor-action="tidy-layout"]').click()
        page.wait_for_timeout(200)
        assert (
            page.evaluate(
                "() => window.infragramEditor.getState().nodes"
                ".map(node => [node.id, node.x, node.y])"
            )
            == before
        )

        # one action, one step back
        page.locator('[data-editor-action="undo"]').click()
        page.wait_for_timeout(200)
        assert (
            page.evaluate(
                "id => { const n = window.infragramEditor.getState().nodes"
                ".find(x => x.id === id); return [n.x, n.y]; }",
                node_id,
            )
            == moved
        )


def test_tidy_un_pins_a_wire_bent_for_a_layout_that_is_gone(tmp_path: Path) -> None:
    """A pinned wire describes corners in the layout it was bent in. Kept
    through a tidy, it would reach for coordinates nothing sits at any more."""
    with _editor(tmp_path) as (page, _errors):
        wire_id = _longest_wire(page)
        spot = _wire_spot(page, wire_id)
        _select_wire(page, wire_id)
        spot = _wire_spot(page, wire_id)
        _drag(page, (spot["x"], spot["y"]), (spot["x"] + 40, spot["y"] + 80))
        assert _edge_by_id(page, wire_id).get("waypoints"), "the wire did not bend"

        page.locator('[data-editor-action="tidy-layout"]').click()
        page.wait_for_timeout(200)
        assert not _edge_by_id(page, wire_id).get("waypoints"), (
            "a bend outlives the layout it was made in"
        )


def test_a_wire_is_bent_by_dragging_it(tmp_path: Path) -> None:
    """Drag the wire, drag the bend, drop the bend; Reset route undoes the lot."""
    with _editor(tmp_path) as (page, _errors):
        wire_id = _longest_wire(page)
        spot = _wire_spot(page, wire_id)
        _select_wire(page, wire_id)
        assert not _edge_by_id(page, wire_id).get("waypoints"), (
            "selection alone does not bend a wire"
        )
        assert page.locator(f'[data-edge-bend-ghost][data-edge-id="{wire_id}"]').count() >= 1, (
            "a selected wire offers a hollow handle to pull a bend from"
        )

        spot = _wire_spot(page, wire_id)
        _drag(page, (spot["x"], spot["y"]), (spot["x"] + 40, spot["y"] + 80))
        bends = _edge_by_id(page, wire_id).get("waypoints") or []
        assert len(bends) == 1, "dragging the wire bends it"
        assert page.locator(f'[data-edge-bend][data-edge-id="{wire_id}"]').count() == 1

        first = (bends[0]["x"], bends[0]["y"])
        handle = _middle(page, f'[data-edge-bend][data-edge-id="{wire_id}"]')
        _drag(page, handle, (handle[0] + 60, handle[1] + 30))
        moved = _edge_by_id(page, wire_id)["waypoints"][0]
        assert (moved["x"], moved["y"]) != first, "the bend itself can be dragged"
        page.keyboard.press("Control+z")
        assert (
            _edge_by_id(page, wire_id)["waypoints"][0]["x"],
            _edge_by_id(page, wire_id)["waypoints"][0]["y"],
        ) == first, "undo puts the bend back"
        assert page.locator(f'[data-edge-bend][data-edge-id="{wire_id}"]').count() == 1, (
            "and the wire stays selected, so its handles are still there"
        )

        # a hollow handle adds a bend on its own stretch, keeping the order
        ghosts = page.locator(f'[data-edge-bend-ghost][data-edge-id="{wire_id}"]')
        assert ghosts.count() == 2, "one hollow handle per stretch"
        box = ghosts.first.bounding_box()
        _drag(
            page,
            (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2),
            (box["x"] + 50, box["y"] - 60),
        )
        two = _edge_by_id(page, wire_id)["waypoints"]
        assert len(two) == 2 and (two[1]["x"], two[1]["y"]) == first, (
            "the new bend joins ahead of the old one"
        )

        handle = _middle(page, f'[data-edge-bend][data-edge-id="{wire_id}"]')
        page.mouse.dblclick(*handle)
        assert len(_edge_by_id(page, wire_id)["waypoints"]) == 1, "double-clicking a bend drops it"

        # a drag abandoned mid-flight leaves the wire as it was
        before = [(point["x"], point["y"]) for point in _edge_by_id(page, wire_id)["waypoints"]]
        handle = _middle(page, f'[data-edge-bend][data-edge-id="{wire_id}"]')
        page.mouse.move(*handle)
        page.mouse.down()
        page.mouse.move(handle[0] + 80, handle[1] + 80, steps=6)
        page.keyboard.press("Escape")
        page.mouse.up()
        assert [
            (point["x"], point["y"]) for point in _edge_by_id(page, wire_id)["waypoints"]
        ] == before

        # a bend is not licence to draw a diagonal: the wire still turns at
        # right angles, the way every picture check expects
        drawn = page.evaluate(
            """(id) => {
              const path = document.querySelector(`[data-graph-edge][data-edge-id="${id}"]`);
              const total = path.getTotalLength();
              const points = [];
              for (let at = 0; at <= total; at += 4) {
                const point = path.getPointAtLength(at);
                points.push([point.x, point.y]);
              }
              return {d: path.getAttribute('d'), points}; }""",
            wire_id,
        )
        diagonal = [
            (before, after)
            for before, after in zip(drawn["points"], drawn["points"][1:], strict=False)
            # a rounded corner is an arc, so leave the 8px radius its slope
            if abs(before[0] - after[0]) > 0.5
            and abs(before[1] - after[1]) > 0.5
            and ((before[0] - after[0]) ** 2 + (before[1] - after[1]) ** 2) ** 0.5 > 9
        ]
        assert not diagonal, f"{diagonal[:2]} in {drawn['d'][:120]}"

        # Escape may leave the wire unselected. Pick it for editing first;
        # a further double click on the selected wire opens its label.
        _select_wire(page, wire_id)
        assert (
            page.locator(f'[data-edge-group="{wire_id}"] [data-edge-selection-halo]').count() == 1
        )
        spot = _wire_spot(page, wire_id)
        page.mouse.dblclick(spot["x"], spot["y"])
        page.wait_for_function("document.activeElement?.dataset?.edgeLabelControl === 'label'")
        page.keyboard.press("Escape")


def test_each_end_of_a_connector_can_be_given_a_side(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        wire_id = _longest_wire(page)
        _select_wire(page, wire_id)
        page.locator('[data-inspector-tab="text"]').click()
        leaves = page.locator('[data-edge-port-control="sourcePort"]')
        arrives = page.locator('[data-edge-port-control="targetPort"]')
        assert leaves.is_visible() and arrives.is_visible() and leaves.is_enabled()

        leaves.select_option("bottom")
        leaves.dispatch_event("change")
        assert _edge_by_id(page, wire_id)["sourcePort"] == "bottom"
        anchored = page.evaluate(
            """(id) => {
          const drawn = document.querySelector(`[data-graph-edge][data-edge-id="${id}"]`);
          const state = window.infragramEditor.getState();
          const edge = state.edges.find(item => item.id === id);
          const source = state.nodes.find(node => node.id === edge.source);
          return {wire: Number(drawn.dataset.sourceY), bottom: source.y + source.height}; }""",
            wire_id,
        )
        assert abs(anchored["wire"] - anchored["bottom"]) <= 2, "the wire really leaves the bottom"

        # a side chosen by hand counts as a route, so Reset route puts it back
        reset = page.locator('[data-selection-action="edge-reset-route"]')
        assert reset.is_enabled()
        reset.click()
        assert (
            _edge_by_id(page, wire_id)["sourcePort"],
            _edge_by_id(page, wire_id)["targetPort"],
        ) == ("auto", "auto")


def test_several_connectors_are_picked_and_deleted_together(tmp_path: Path) -> None:
    """Shift-click gathers wires the way it gathers cards."""
    with _editor(tmp_path) as (page, _errors):
        halos = page.locator("[data-edge-selection-halo]")
        first, second = _edge(page, "HTTPS")["id"], _edge(page, "TDS")["id"]
        count = len(_state(page)["edges"])

        _select_edge(page, "HTTPS")
        assert halos.count() == 1
        _select_edge(page, "TDS", add=True)
        assert halos.count() == 2, "shift-clicking adds the second wire"
        assert page.locator("[data-inspector-selection]").inner_text() == "2 connectors"
        assert page.locator("[data-edge-end]").count() == 0, "no end to drag while two are picked"
        chip = page.locator("[data-selection-count-chip]")
        assert chip.is_visible() and chip.inner_text() == "2"
        assert page.locator('[data-selection-action="edge-edit-label"]').is_hidden()

        before = {edge["id"]: (edge["source"], edge["target"]) for edge in _state(page)["edges"]}
        page.locator('[data-selection-action="edge-reverse"]').click()
        after = {edge["id"]: (edge["source"], edge["target"]) for edge in _state(page)["edges"]}
        for edge_id in (first, second):
            assert after[edge_id] == (before[edge_id][1], before[edge_id][0]), edge_id
        page.keyboard.press("Control+z")

        _select_edge(page, "HTTPS")
        _select_edge(page, "TDS", add=True)
        page.keyboard.press("Delete")
        assert len(_state(page)["edges"]) == count - 2
        assert page.locator("[data-snackbar]").inner_text() == "2 connectors deleted"
        page.keyboard.press("Control+z")
        assert len(_state(page)["edges"]) == count, "one undo brings both back"

        # shift-clicking one that is already picked takes it out again
        _select_edge(page, "HTTPS")
        _select_edge(page, "TDS", add=True)
        _select_edge(page, "TDS", add=True)
        assert halos.count() == 1


def test_two_connectors_between_the_same_pair_do_not_draw_as_one(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        api, sql = _node(page, "API")["id"], _node(page, "SQL")["id"]
        drawn = page.evaluate(
            """([source, target]) => {
              const state = window.infragramEditor.getState();
              return state.edges
                .filter(edge => (edge.source === source && edge.target === target)
                  || (edge.source === target && edge.target === source))
                .map(edge => document.querySelector(`[data-graph-edge][data-edge-id="${edge.id}"]`)
                  .getAttribute('d')); }""",
            [api, sql],
        )
        assert len(drawn) == 1

        page.evaluate(
            "([source, target]) => window.infragramEditor.connect(source, target)", [api, sql]
        )
        both = page.evaluate(
            """([source, target]) => {
              const state = window.infragramEditor.getState();
              return state.edges
                .filter(edge => (edge.source === source && edge.target === target)
                  || (edge.source === target && edge.target === source))
                .map(edge => document.querySelector(`[data-graph-edge][data-edge-id="${edge.id}"]`)
                  .getAttribute('d')); }""",
            [api, sql],
        )
        assert len(both) == 2
        assert both[0] != both[1], "wires joining the same pair take a lane each"


def test_the_shortcut_sheet_says_what_the_keyboard_does(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        sheet = page.locator("[data-shortcut-sheet]")
        assert sheet.is_hidden()
        page.locator('[data-editor-action="shortcuts"]').click()
        assert sheet.is_visible()
        rows = page.locator(".shortcut-sheet__rows dt")
        assert rows.count() >= 15, f"{rows.count()} shortcuts listed"
        page.keyboard.press("Escape")
        assert sheet.is_hidden()

        page.mouse.click(700, 500)
        page.keyboard.press("?")
        assert sheet.is_visible(), "? opens it from the canvas"
        page.locator("[data-shortcut-sheet-close]").click()
        assert sheet.is_hidden()

        # and it does not butt in while something is being typed
        page.locator("[data-sidebar-search]").click()
        page.keyboard.type("?")
        assert sheet.is_hidden()


def test_redo_answers_to_the_windows_shortcut_as_well(tmp_path: Path) -> None:
    with _editor(tmp_path) as (page, _errors):
        count = len(_state(page)["nodes"])
        _select_node(page, "SQL")
        page.keyboard.press("Control+d")
        assert len(_state(page)["nodes"]) == count + 1
        page.keyboard.press("Control+z")
        assert len(_state(page)["nodes"]) == count
        page.keyboard.press("Control+y")
        assert len(_state(page)["nodes"]) == count + 1, (
            "Ctrl+Y redoes, as it does elsewhere on Windows"
        )


_DRAWING = """() => ({
  cards: [...document.querySelectorAll('[data-graph-node]')]
    .map(group => `${group.dataset.nodeId}:${group.getAttribute('transform')}`),
  wires: [...document.querySelectorAll('[data-graph-edge]')]
    .map(path => `${path.dataset.edgeId}:${path.getAttribute('d')}`),
  ends: [...document.querySelectorAll('[data-edge-terminal]')]
    .map(circle => `${circle.dataset.edgeId}:${circle.getAttribute('cx')},${circle.getAttribute('cy')}`),
})"""


def test_dragging_a_card_draws_what_a_full_redraw_would_draw(tmp_path: Path) -> None:
    """A drag patches the drawing instead of redrawing it; it must not drift."""
    with _editor(tmp_path) as (page, _errors):
        card = _card(page, "API")
        start = _middle(page, card)
        page.mouse.move(*start)
        page.mouse.down()
        for step in range(4):
            page.mouse.move(start[0] + 24 * (step + 1), start[1] + 16 * (step + 1))
        patched = page.evaluate(_DRAWING)
        # draw it all again, with the drag still in flight
        page.evaluate("""() => window.infragramEditor.setRouting(
            window.infragramEditor.getState().canvas.routeAroundNodes !== false)""")
        redrawn = page.evaluate(_DRAWING)
        assert patched["cards"] == redrawn["cards"], "the card sits where the drawing says"
        assert patched["wires"] == redrawn["wires"], "its wires are drawn the same way"
        assert patched["ends"] == redrawn["ends"], "and their ends sit on them"

        page.mouse.up()
        settled = page.evaluate(_DRAWING)
        page.evaluate("""() => window.infragramEditor.setRouting(
            window.infragramEditor.getState().canvas.routeAroundNodes !== false)""")
        assert settled == page.evaluate(_DRAWING), "and the drawing is exact once the card lands"


# ------------------------------------- what floats over a selection stays usable

TOPMOST_AT_CAPTION = """id => {
  const caption = document.querySelector(`[data-edge-label][data-edge-id="${id}"]`);
  const box = caption.getBoundingClientRect();
  const hit = document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2);
  if (caption.contains(hit)) return 'caption';
  return hit ? `${hit.tagName.toLowerCase()}[${[...hit.attributes].map(a => a.name)
    .filter(name => name.startsWith('data-')).join(',')}]` : 'nothing';
}"""


def test_a_selected_wire_keeps_its_caption_clear_of_its_bend_grips(tmp_path: Path) -> None:
    """A grip for adding a bend sits mid-stretch, and automatic placement puts
    a caption mid-run too. On a short plain wire the two coincided: the grip
    was drawn over the caption ("HTTPS" read "HT o PS") and a drag on the
    caption bent the wire instead of moving the caption. In the full edition's
    templates, 27 of 346 labelled wires did this once selected.
    """
    with _editor(tmp_path) as (page, _):
        for label in ("HTTPS", "TDS"):
            wire = _edge(page, label)
            _select_edge(page, label)
            page.wait_for_timeout(250)
            assert _state(page)["edges"], "the fixture has wires"
            assert page.evaluate(TOPMOST_AT_CAPTION, wire["id"]) == "caption", (
                f"a bend grip covers the {label} caption once the wire is selected"
            )
            # A grip is still offered on the stretch: the wire can be bent.
            assert (
                page.locator(f'[data-edge-bend-ghost][data-edge-id="{wire["id"]}"]').count() >= 1
                or page.locator(f'path[data-graph-edge][data-edge-id="{wire["id"]}"]').count() == 1
            )

        # And the caption still moves when dragged -- it does not bend the wire.
        wire = _edge(page, "HTTPS")
        _select_edge(page, "HTTPS")
        page.wait_for_timeout(250)
        caption = page.locator(f'[data-edge-label][data-edge-id="{wire["id"]}"]').bounding_box()
        x, y = caption["x"] + caption["width"] / 2, caption["y"] + caption["height"] / 2
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x + 36, y + 20, steps=8)
        page.mouse.up()
        page.wait_for_timeout(300)
        moved = _edge(page, "HTTPS")
        assert (moved.get("labelPlacement") or {}).get("mode") == "manual", (
            "dragging the caption did not move it"
        )
        assert not moved.get("waypoints"), "dragging the caption bent the wire instead"


def _park_at_edge(page, name: str, edge: str) -> None:
    """Scroll the canvas so a component sits at one edge of what is visible."""
    node_id = _node(page, name)["id"]
    page.evaluate(
        """([id, edge]) => {
      const viewport = document.querySelector('.canvas-viewport');
      const card = document.querySelector(`[data-graph-node][data-node-id="${id}"]`);
      const v = viewport.getBoundingClientRect(), c = card.getBoundingClientRect();
      if (edge === 'left') viewport.scrollLeft += c.left - v.left - 4;
      else viewport.scrollTop += c.top - v.top - 4;
    }""",
        [node_id, edge],
    )
    page.wait_for_timeout(250)


def _inside_the_canvas(page) -> dict:
    return page.evaluate("""() => {
      const v = document.querySelector('.canvas-viewport').getBoundingClientRect();
      const t = document.querySelector('[data-selection-toolbar]').getBoundingClientRect();
      return {left: t.left >= v.left - 0.5, right: t.right <= v.right + 0.5,
              top: t.top >= v.top - 0.5, bottom: t.bottom <= v.bottom + 0.5,
              toolbar: [t.left, t.top, t.right, t.bottom].map(Math.round),
              viewport: [v.left, v.top, v.right, v.bottom].map(Math.round)};
    }""")


def test_the_selection_toolbar_stays_inside_the_canvas(tmp_path: Path) -> None:
    """Centred above what it acts on, the toolbar used to run off the canvas:
    a component by the left edge had the count and both align buttons centred
    behind the sidebar, and one at the top had the toolbar above the view.
    It slides back in, and flips below when there is no room above."""
    with _editor(tmp_path, viewport=(1100, 760)) as (page, _):
        for _ in range(3):
            page.locator('[data-editor-action="zoom-in"]').click()
        page.wait_for_timeout(300)
        _select_node(page, "API")
        page.wait_for_timeout(250)

        _park_at_edge(page, "API", "left")
        # The case being tested: the card really is at the canvas's left edge.
        assert page.evaluate(
            """id => {
          const v = document.querySelector('.canvas-viewport').getBoundingClientRect();
          const c = document.querySelector(`[data-graph-node][data-node-id="${id}"]`).getBoundingClientRect();
          return c.left - v.left < 40;
        }""",
            _node(page, "API")["id"],
        ), "the card could not be brought to the left edge"
        where = _inside_the_canvas(page)
        assert where["left"] and where["right"], f"toolbar off the canvas sideways: {where}"

        _park_at_edge(page, "API", "top")
        where = _inside_the_canvas(page)
        assert where["top"], f"toolbar above the canvas: {where}"


# ------------------------------------------- fixes upstreamed from the full edition


def test_a_press_on_the_canvas_takes_the_keyboard_from_a_focused_button_too(tmp_path: Path) -> None:
    """A focused control owns Delete -- a reader tabbing through the toolbar
    must not delete the selection by pressing it -- so a card clicked after a
    button has to take the keyboard back, or Delete does nothing."""
    with _editor(tmp_path) as (page, _):
        before = len(_state(page)["nodes"])
        page.locator('[data-editor-action="zoom-in"]').click()
        assert page.evaluate("() => document.activeElement?.dataset?.editorAction") == "zoom-in"
        _select_node(page, "Blobs")
        page.keyboard.press("Delete")
        page.wait_for_timeout(250)
        assert len(_state(page)["nodes"]) == before - 1, "Delete went to the button, not the card"


def test_a_click_that_moves_nothing_keeps_the_redo_stack(tmp_path: Path) -> None:
    """Picking something up is not an edit. A press that moved nothing used to
    throw away everything the reader could redo."""
    with _editor(tmp_path) as (page, _):
        redo = page.locator('[data-editor-action="redo"]')
        routing = "() => window.infragramEditor.getState().canvas.routeAroundNodes"
        assert page.evaluate("() => window.infragramEditor.setRouting(false)") is False
        page.locator('[data-editor-action="undo"]').click()
        assert page.evaluate(routing) is not False
        assert redo.is_enabled()

        _select_node(page, "API")
        page.locator(f'[data-graph-node][data-node-id="{_node(page, "API")["id"]}"]').click()
        assert page.locator("[data-inspector-selection]").text_content().strip() == "API"
        assert redo.is_enabled(), "a click that moved nothing wiped the redo stack"
        redo.click()
        assert page.evaluate(routing) is False


def _saved_document(page) -> dict:
    return page.evaluate(
        "() => JSON.parse(localStorage.getItem(window.infragramEditor.getStorageKey()))"
    )


def test_url_overrides_draw_one_visit_and_never_reach_the_saved_document(tmp_path: Path) -> None:
    """?display=, ?routing= and ?grid= draw this visit differently -- that is
    how an exporter gets both looks from one file -- and must never be written
    into what the author saved. The document here says cards, so a saved
    document that comes back "icon" is the visit leaking into it."""
    with _editor(tmp_path) as (page, _):
        source = page.url.split("?")[0]
        page.goto(source + "?fresh=visit&display=icon&routing=direct&grid=1")
        page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
        canvas = _state(page)["canvas"]
        assert canvas["displayMode"] == "icon"
        assert canvas["routeAroundNodes"] is False and canvas["showGrid"] is True

        # Zooming saves the canvas extent; that save must not carry the visit.
        page.locator('[data-editor-action="zoom-in"]').click()
        page.evaluate("() => window.infragramEditor.whenSettled()")
        saved = _saved_document(page)
        assert saved["canvas"]["displayMode"] == "card", "the visit's icons were saved"
        assert saved["canvas"]["routeAroundNodes"] is not False, "the visit's routing was saved"
        assert saved["canvas"]["showGrid"] is not True, "the visit's grid was saved"
        assert {node.get("displayMode", "card") for node in saved["nodes"]} == {"card"}

        # The same workspace opened plainly comes up as it was saved.
        page.goto(source + "?fresh=visit")
        page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
        canvas = _state(page)["canvas"]
        assert canvas["displayMode"] == "card" and canvas["routeAroundNodes"] is not False

        # A choice made by hand during a visit is the author's, and is kept.
        page.goto(source + "?fresh=visit&routing=direct")
        page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
        page.locator('[data-inspector-tab="diagram"]').click()
        page.locator('[data-inspector-routing] [data-routing="around"]').click()
        page.locator('[data-inspector-routing] [data-routing="direct"]').click()
        page.evaluate("() => window.infragramEditor.whenSettled()")
        assert _saved_document(page)["canvas"]["routeAroundNodes"] is False


def test_the_download_panel_fits_a_phone(tmp_path: Path) -> None:
    """On a phone the header holds Inventory, Edit, Download, the theme and the
    mascot, so Download sits mid-row: a panel hung off its right edge ran past
    the screen's left one. It spans the screen under the header instead."""
    with _editor(tmp_path, viewport=(375, 667)) as (page, _):
        page.locator("[data-download-menu] > summary").click()
        box = page.locator(".download-panel").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 375, box
        svg = page.locator("[data-download-svg]").bounding_box()
        assert svg["x"] >= 0 and svg["x"] + svg["width"] <= 375, svg


def test_a_mono_caption_falls_back_to_a_mono_face(tmp_path: Path) -> None:
    """A caption set in Geist Mono that cannot load its face should fall back
    to another monospace one, not to a proportional face that changes every
    width the layout measured."""
    with _editor(tmp_path) as (page, _):
        wire = _edge(page, "HTTPS")
        page.evaluate(
            "id => window.infragramEditor.setEdgeTextStyle(id, {fontFamily: 'Geist Mono'})",
            wire["id"],
        )
        page.wait_for_timeout(250)
        family = page.locator(f'[data-edge-label][data-edge-id="{wire["id"]}"] text').get_attribute(
            "font-family"
        )
        assert family.endswith("monospace"), family
        page.evaluate(
            "id => window.infragramEditor.setEdgeTextStyle(id, {fontFamily: 'Inter'})", wire["id"]
        )
        page.wait_for_timeout(250)
        family = page.locator(f'[data-edge-label][data-edge-id="{wire["id"]}"] text').get_attribute(
            "font-family"
        )
        assert family.endswith("sans-serif"), family
        # a face a drawing saved before Inter, which no page carries now, draws in Inter
        page.evaluate(
            "id => window.infragramEditor.setEdgeTextStyle(id, {fontFamily: 'Roboto'})", wire["id"]
        )
        page.wait_for_timeout(250)
        family = page.locator(f'[data-edge-label][data-edge-id="{wire["id"]}"] text').get_attribute(
            "font-family"
        )
        assert family.startswith("'Inter'"), family


def test_a_page_opened_dark_starts_and_lifts_dark_ink_artwork(tmp_path: Path) -> None:
    """Opening dark measures each icon's ink. Every redraw while measurements
    were still out queued one more redraw per icon, so a page that opened dark
    on many dark-ink icons redrew without end and never started."""
    sync_api = pytest.importorskip("playwright.sync_api")
    from infragram.nodes import infragram as shared

    kinds = [
        shared.compute.BladeChassis,
        shared.compute.ConsoleServer,
        shared.compute.Cooling,
        shared.compute.DesktopClient,
        shared.compute.FailoverPair,
        shared.compute.FireSuppression,
        shared.compute.GPUServer,
        shared.compute.Generator,
        shared.compute.HPCNode,
        shared.compute.HaCluster,
        shared.compute.KVMConsole,
        shared.compute.Mainframe,
        shared.networking.AccessSwitch,
        shared.identity.Administrator,
    ]
    with Diagram("Dark ink", "Monochrome artwork.", slug="dark-ink", display="icon") as diagram:
        nodes = [kind(f"Item {index}") for index, kind in enumerate(kinds)]
        for source_node, target_node in zip(nodes, nodes[1:], strict=False):
            source_node >> target_node
    source = tmp_path / "dark-ink.html"
    source.write_text(render_project_html(diagram.to_project()), encoding="utf-8")
    lifted = "document.querySelectorAll('[data-graph-node] image[filter]').length"
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"{source.resolve().as_uri()}?fresh=dark-ink&theme=dark")
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            page.wait_for_function(f"{lifted} > 0", timeout=render_timeout_ms())
            # the same artwork beside its row in the inventory, lifted alike
            page.locator("[data-inventory-toggle]").click()
            page.wait_for_function(
                "document.querySelectorAll('img.resource-icon[data-ink-dark]').length > 0",
                timeout=render_timeout_ms(),
            )
            filters = page.evaluate(
                "[...document.querySelectorAll('img.resource-icon[data-ink-dark]')]"
                ".map(image => getComputedStyle(image).filter)"
            )
            assert set(filters) == {"invert(1) hue-rotate(180deg)"}, filters
        finally:
            browser.close()
