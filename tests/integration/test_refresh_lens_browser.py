"""A refreshed diagram lights what changed since the last read.

Two reads a day apart, the second drawn with --refresh: the canvas menu
offers the lens, it lights the card added and the card changed, and the
status names what was removed, which has no card left to light. A page drawn
from one read offers no such lens.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from test_discovery_azure import snapshot  # noqa: E402
from test_refresh_azure import _later  # noqa: E402

from infragram.discovery import ImportOptions, blueprint  # noqa: E402
from infragram.discovery.refresh import carry_layout, compare, mark  # noqa: E402
from infragram.exports import render_project_html  # noqa: E402

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run Chromium editor checks",
)

LENS = '[data-context-action="lens-refresh"]'


def _page(tmp_path: Path, *, refreshed: bool) -> Path:
    settings = ImportOptions(view="network")
    earlier, _ = blueprint(snapshot(), settings, slug="refresh")
    if not refreshed:
        project = earlier.to_project()
    else:
        plan, _ = blueprint(_later(), settings, slug="refresh")
        project = plan.to_project()
        carry_layout(earlier.to_project(), project)
        mark(project, compare(_later(), earlier=snapshot()))
    source = tmp_path / f"refresh-{refreshed}.html"
    source.write_text(render_project_html(project), encoding="utf-8")
    return source


def _menu(page) -> None:
    box = page.locator("[data-infragram-diagram]").bounding_box()
    page.mouse.click(box["x"] + 6, box["y"] + 6, button="right")


@pytest.mark.parametrize("refreshed", [True, False])
def test_the_lens_lights_what_changed_and_names_what_went(tmp_path: Path, refreshed: bool) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = _page(tmp_path, refreshed=refreshed)
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(source.resolve().as_uri() + "?fresh=refresh")
            page.wait_for_load_state("networkidle")
            _menu(page)
            if not refreshed:
                assert page.locator(LENS).is_hidden()
                return
            entry = page.locator(LENS)
            assert entry.is_visible()
            entry.click()
            lit = page.evaluate(
                "[...document.querySelectorAll('[data-graph-node]')]"
                ".filter(node => node.dataset.focusDimmed === 'false')"
                ".map(node => node.getAttribute('aria-label')).sort()"
            )
            assert lit == ["kv-prod", "stprod"]
            status = page.locator("[data-snackbar]").inner_text()
            assert "1 added, 1 changed, 1 removed: log-prod" in status
            _menu(page)
            assert page.locator(LENS).get_attribute("aria-checked") == "true"
            assert errors == []
        finally:
            browser.close()
