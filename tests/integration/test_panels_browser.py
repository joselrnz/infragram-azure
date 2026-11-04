"""The editor draws a panel as the static picture does.

A panel's compartments, lines and shape are laid out twice: by Python for
the static picture and by the runtime in the page (builders/panels.py,
14-shapes.js panelLayout). Both read render-metrics.json, so every cell
takes the same share of its row and every line says the same words.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from infragram.author import Diagram, Edge
from infragram.exports import render_project_html, render_project_svg, render_timeout_ms
from infragram.nodes import Box
from infragram.nodes.azure import compute

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run Chromium editor checks",
)


def _project():
    with Diagram(
        "Panels",
        slug="panels",
        display="card",
        tones={"edge": "public edge / ingress", "blocker": "launch blocker"},
    ) as diagram:
        lb = (
            Box("Public regional HTTP load balancer", "one Gateway-owned resource · two size units")
            .tone("edge")
            .section("Public frontend", "HTTPS 443 · Full (strict)", tone="edge")
            .section("DOKS gateway backends", "health-checked targets", tone="private", beside=True)
            .section("Direct origin access must fail", "proof still required", tone="blocker")
        )
        customer = Box("Customer", "HTTPS 443\nStripe only when enabled").shape("ellipse")
        control = Box("Control plane", "managed API").shape("hexagon").tone("managed")
        web = compute.VirtualMachine("Web", "plain card")
        customer >> Edge("HTTPS") >> lb >> web
        lb - control
    return diagram.to_project()


def _static(svg: str) -> dict[str, dict]:
    """Per panel: its cells' widths and every word it draws."""
    panels: dict[str, dict] = {}
    for match in re.finditer(
        r'data-node="([^"]+)" data-display="card" data-panel="">(.*?)\n        </g>', svg, re.DOTALL
    ):
        body = match.group(2)
        panels[match.group(1)] = {
            "cells": [
                float(w)
                for w in re.findall(r'data-panel-cell="" x="[^"]+" y="[^"]+" width="([^"]+)"', body)
            ],
            "texts": re.findall(r">([^<>]+)</text>", body),
        }
    return panels


def test_the_page_lays_a_panel_out_as_the_picture_does(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    project = _project()
    static = _static(render_project_svg(project))
    assert set(static) == {"public-regional-http-load-balancer", "customer", "control-plane"}
    source = tmp_path / "panels.html"
    source.write_text(render_project_html(project), encoding="utf-8")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(source.resolve().as_uri() + "?fresh=panels")
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            drawn = page.evaluate(
                """() => Object.fromEntries([...document.querySelectorAll('[data-graph-node]')]
                  .filter(node => node.querySelector('[data-panel]'))
                  .map(node => [node.dataset.nodeId, {
                    cells: [...node.querySelectorAll('[data-panel-cell]')].map(cell => Number(cell.getAttribute('width'))),
                    texts: [...node.querySelectorAll('[data-panel] text')].map(text => text.textContent),
                    shape: node.querySelector('[data-panel] > :first-child').tagName,
                  }]))"""
            )
            assert set(drawn) == set(static)
            for node_id, picture in static.items():
                assert drawn[node_id]["cells"] == picture["cells"], node_id
                assert drawn[node_id]["texts"] == picture["texts"], node_id
            assert drawn["customer"]["shape"] == "ellipse"
            assert drawn["control-plane"]["shape"] == "polygon"
            # the plain card is no panel, and Icons leaves a panel a box
            assert page.locator('[data-graph-node][data-node-id="web"] [data-panel]').count() == 0
            page.evaluate("() => window.infragramEditor.setDisplayMode('icon')")
            assert page.locator("[data-graph-node] [data-panel]").count() == 3
            # the legend says what each tone means
            assert page.locator("[data-diagram-legend] [data-legend-tone]").count() == 2
            assert not errors, errors
        finally:
            browser.close()


def test_the_style_tab_makes_a_card_a_panel_and_undo_takes_it_back(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with Diagram("Box", slug="box", display="card") as diagram:
        # a Box is a box already; a vendor card is the one the Style tab boxes
        compute.VirtualMachine("Network contract", "default deny")
    source = tmp_path / "box.html"
    source.write_text(render_project_html(diagram.to_project()), encoding="utf-8")
    node = '[data-graph-node][data-node-id="network-contract"]'
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(source.resolve().as_uri() + "?fresh=box")
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            before = page.evaluate("() => window.infragramEditor.getState().nodes[0]")
            assert page.locator(f"{node} [data-panel]").count() == 0
            page.locator(node).dblclick()
            page.locator('[data-inspector-tab="style"]').click()
            section = page.locator("[data-node-box-section]")
            assert section.is_visible()
            display = page.locator("[data-node-display-section]")
            assert display.is_visible()
            fonts = page.locator("[data-text-type-section]")
            assert fonts.get_attribute("hidden") is None
            # the Box section fits the inspector: nothing runs past its edge
            assert page.evaluate(
                "() => { const body = document.querySelector('.inspector-body');"
                " return body.scrollWidth <= body.clientWidth; }"
            )
            section.locator('[data-node-shape="note"]').click()
            # a panel is a box in either look, so the card-or-icon choice steps
            # aside, and the Text tab's fonts, which a panel does not take
            assert display.is_hidden()
            assert fonts.get_attribute("hidden") is not None
            assert page.locator("[data-text-type-note]").get_attribute("hidden") is None
            section.locator('[data-node-tone="blocker"]').click()
            area = section.locator("[data-node-sections]")
            area.fill(
                "Ingress | gateway only || [edge] Egress | NAT only\n[blocker] No public NodePort"
            )
            area.press("Tab")
            after = page.evaluate("() => window.infragramEditor.getState().nodes[0]")
            assert after["attributes"]["shape"] == "note"
            assert after["attributes"]["tone"] == "blocker"
            assert after["attributes"]["sections"] == [
                [
                    {"title": "Ingress", "lines": ["gateway only"]},
                    {"title": "Egress", "lines": ["NAT only"], "tone": "edge"},
                ],
                [{"title": "No public NodePort", "lines": [], "tone": "blocker"}],
            ]
            assert after["height"] > before["height"], "it grows to what it carries"
            assert page.locator(f"{node} [data-panel] [data-panel-cell]").count() == 2
            # the text reads back as written, and the saved document keeps it
            assert area.input_value() == (
                "Ingress | gateway only || [edge] Egress | NAT only\n[blocker] No public NodePort"
            )
            saved = page.evaluate("() => window.infragramEditor.exportProject()")
            element = saved["topology"]["children"][0]
            assert element["attributes"]["sections"][1][0]["title"] == "No public NodePort"
            # undo, three times, gives the plain card back at its own size
            for _ in range(3):
                page.keyboard.press("Control+z")
            restored = page.evaluate("() => window.infragramEditor.getState().nodes[0]")
            assert (
                "sections" not in restored["attributes"] and "shape" not in restored["attributes"]
            )
            assert (restored["width"], restored["height"]) == (before["width"], before["height"])
            assert page.locator(f"{node} [data-panel]").count() == 0
            assert not errors, errors
        finally:
            browser.close()


def test_a_description_keeps_its_lines_and_a_panel_keeps_its_rows_inside(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with Diagram("Lines", slug="lines", display="card") as diagram:
        compute.VirtualMachine("Customer", "HTTPS 443")
        (
            Box("Load balancer", "two size units")
            .section("Public frontend", "HTTPS 443", tone="edge")
            .section("Backends", "health-checked", beside=True)
            .section("Direct origin access must fail", tone="blocker")
        )
    source = tmp_path / "lines.html"
    source.write_text(render_project_html(diagram.to_project()), encoding="utf-8")
    state = "(id) => window.infragramEditor.getState().nodes.find(node => node.id === id)"
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(source.resolve().as_uri() + "?fresh=lines")
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            customer = '[data-graph-node][data-node-id="customer"]'
            before = page.evaluate(state, "customer")
            page.locator(customer).dblclick()
            page.locator('[data-inspector-tab="text"]').click()
            detail = page.locator('[data-content-control="detail"]')
            # Shift+Enter starts a line, Enter applies: the card becomes a panel
            detail.click()
            detail.press("End")
            detail.press("Shift+Enter")
            detail.type("  payments only when billing is enabled ")
            detail.press("Enter")
            after = page.evaluate(state, "customer")
            assert after["detail"] == "HTTPS 443\npayments only when billing is enabled"
            assert page.locator(f"{customer} [data-panel]").count() == 1
            # both lines drawn, inside the box it was given
            outline = page.locator(f"{customer} [data-node-surface]").bounding_box()
            lines = page.locator(f"{customer} [data-panel] text").all()
            assert [line.text_content() for line in lines][1:] == after["detail"].splitlines()
            for line in lines:
                drawn = line.bounding_box()
                assert outline["y"] <= drawn["y"]
                assert drawn["y"] + drawn["height"] <= outline["y"] + outline["height"]
            assert (after["width"], after["height"]) != (before["width"], before["height"])
            assert detail.input_value() == after["detail"]
            # a panel shrunk by its corner stops where its rows still fit
            lb = '[data-graph-node][data-node-id="load-balancer"]'
            natural = page.evaluate(state, "load-balancer")
            page.locator(lb).dblclick()
            grip = page.locator('[data-node-resize="se"][data-resize-node-id="load-balancer"]').last
            box = grip.bounding_box()
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.move(box["x"] - 600, box["y"] - 600, steps=8)
            page.mouse.up()
            shrunk = page.evaluate(state, "load-balancer")
            assert shrunk["height"] == natural["height"]
            assert shrunk["width"] == 160
            outline = page.locator(f"{lb} [data-node-surface]").bounding_box()
            for cell in page.locator(f"{lb} [data-panel-cell]").all():
                drawn = cell.bounding_box()
                assert drawn["y"] + drawn["height"] <= outline["y"] + outline["height"] + 1
            # nor does the Arrange tab's height take it smaller
            page.locator('[data-inspector-tab="arrange"]').click()
            height = page.locator('[data-exact-field="height"]')
            height.fill("40")
            height.press("Enter")
            assert page.evaluate(state, "load-balancer")["height"] == natural["height"]
            assert not errors, errors
        finally:
            browser.close()


def test_on_a_phone_return_starts_a_line_and_the_legend_makes_room(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    with Diagram("Phone", slug="phone", display="card", tones={"edge": "public edge"}) as diagram:
        Box("Customer", "HTTPS 443").tone("edge")
    source = tmp_path / "phone.html"
    source.write_text(render_project_html(diagram.to_project()), encoding="utf-8")
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(
                viewport={"width": 412, "height": 860}, is_mobile=True, has_touch=True
            )
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(source.resolve().as_uri() + "?fresh=phone")
            page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())
            legend = page.locator("[data-diagram-legend]")
            assert legend.is_visible()
            page.locator('[data-graph-node][data-node-id="customer"]').dblclick()
            page.locator('[data-inspector-tab="text"]').click()
            # the sheet is open: the legend shrinks to leave the map room
            assert legend.is_visible()
            assert legend.bounding_box()["height"] <= 88
            detail = page.locator('[data-content-control="detail"]')
            detail.click()
            detail.press("End")
            detail.press("Enter")
            detail.type("payments only")
            assert detail.input_value() == "HTTPS 443\npayments only"
            detail.blur()
            node = page.evaluate("() => window.infragramEditor.getState().nodes[0]")
            assert node["detail"] == "HTTPS 443\npayments only"
            assert not errors, errors
        finally:
            browser.close()
