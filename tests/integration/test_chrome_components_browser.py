"""Every control in the exported page is one of the chrome's components.

The chrome is built from one component set (src/infragram/editor/ui/components):
buttons, icon buttons, segmented buttons, chips, list and navigation items,
tabs, tiles, text fields, switches and checkboxes. This walks a two-library
export through its panels in every theme and holds every visible control to
that contract: it carries an md-* component class, its type sits on the M3
type scale, its corners on the chrome's small shape scale (tokens.css --ui-*),
and its height is the one its component defines at the page's density. A control added without a component,
or a size nudged by hand, fails here with its name.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from infragram.exports import render_project_html
from infragram.projects import CloudProject

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run Chromium editor checks",
)

TEMPLATE = (
    Path(__file__).parents[2]
    / "skills"
    / "infragram-azure"
    / "assets"
    / "templates"
    / "cloud"
    / "azure-aks-baseline.infragram.json"
)

#: label-small 11, body-small and label-medium 12, body-medium, label-large and
#: title-small 14, body-large and title-medium 16, title-large 22.
TYPE_SIZES = {"11px", "12px", "13px", "14px", "16px", "22px"}
TYPE_WEIGHTS = {"400", "500"}
#: none, then --ui-radius-xs (inside a control), --ui-radius (a control),
#: --ui-radius-lg (a panel or a tile), and full for what is round by nature.
CORNERS = {"0px", "4px", "6px", "8px", "9999px"}
HEIGHTS = {
    "md-button": {32},
    "md-icon-button": {32, 40},
    "md-segmented": {28},
    "md-chip": {28},
    "md-list-item": {32, 44, 48, 56},
    # a category row, and the brand row at the sidebar's head
    "md-nav-item": {32, 56},
    "md-tab": {47, 48},
    "md-tile": set(range(72, 97)),
    "md-switch": {20},
    "md-checkbox": {16},
    "md-field__input": {32},
    "md-search": None,
}

_COLLECT = """() => {
  const controls = 'button, [role="tab"], [role="menuitem"], [role="menuitemcheckbox"], summary, input, select, label.provider-option';
  const component = element => {
    const own = [...element.classList].find(name =>
      /^md-(button|icon-button|chip|list-item|nav-item|tab|tile|switch|checkbox|field__input)$/.test(name));
    if (own) return own;
    if (element.parentElement?.classList.contains('md-segmented')) return 'md-segmented';
    if (element.tagName === 'INPUT' && element.closest('.md-search')) return 'md-search';
    return '';
  };
  return [...document.querySelectorAll(controls)]
    .filter(element => !element.closest('svg'))
    .map(element => ({element, box: element.getBoundingClientRect(), style: getComputedStyle(element)}))
    .filter(({box, style}) => box.width && box.height && style.visibility !== 'hidden')
    .map(({element, box, style}) => ({
      component: component(element),
      name: `${element.tagName.toLowerCase()} "${(element.getAttribute('aria-label') || element.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 40)}"`,
      height: Math.round(box.height),
      corner: style.borderTopLeftRadius,
      size: style.fontSize,
      weight: style.fontWeight,
    }));
}"""


def _violations(controls: list[dict], state: str) -> list[str]:
    found = []
    for control in controls:
        where = f"{state}: {control['name']}"
        if not control["component"]:
            found.append(f"{where} is not an md-* component")
            continue
        if control["size"] not in TYPE_SIZES:
            found.append(f"{where} sets type at {control['size']}")
        if control["weight"] not in TYPE_WEIGHTS:
            found.append(f"{where} sets weight {control['weight']}")
        if control["corner"] not in CORNERS:
            found.append(f"{where} has a {control['corner']} corner")
        heights = HEIGHTS[control["component"]]
        if heights is not None and control["height"] not in heights:
            found.append(f"{where} is a {control['component']} {control['height']}px tall")
    return found


@pytest.mark.parametrize("theme", ["light", "dark", "darker"])
def test_every_control_is_a_standard_component(tmp_path: Path, theme: str) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / "components.html"
    source.write_text(
        render_project_html(CloudProject.load(TEMPLATE), libraries="all"), encoding="utf-8"
    )

    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"{source.resolve().as_uri()}?fresh=components&theme={theme}")
            page.wait_for_selector("[data-graph-layer] [data-graph-node]", state="attached")

            violations: list[str] = []
            seen: set[str] = set()

            def audit(state: str) -> None:
                controls = page.evaluate(_COLLECT)
                seen.update(control["component"] for control in controls)
                violations.extend(_violations(controls, state))

            audit("workspace")
            page.locator("[data-download-menu] > summary").click()
            audit("download menu")
            page.keyboard.press("Escape")
            page.locator("[data-theme-toggle]").click()
            audit("theme menu")
            page.keyboard.press("Escape")
            page.locator(".category[data-category-id='custom'] > summary").click()
            page.locator("details.component-section > summary").first.click()
            page.locator("details.frame-group > summary").first.click()
            audit("custom category")
            page.locator(".category[data-category-id='custom'] > summary").click()
            page.locator("[data-provider-menu-trigger]").click()
            audit("library menu")
            page.keyboard.press("Escape")
            page.locator("[data-sidebar-search]").fill("gateway")
            audit("search results")
            page.locator("[data-sidebar-search]").fill("")
            node = page.locator("[data-graph-layer] [data-graph-node]").nth(3)
            # a plain click reads the card's flow; a double click picks it to edit,
            # so the panels show their fields
            node.dblclick()
            for tab in ("diagram", "style", "text", "arrange", "layers"):
                page.locator(f"[data-inspector-tab='{tab}']").click()
                audit(f"{tab} panel")
            page.locator("[data-frame-select]").first.click()
            page.locator("[data-inspector-tab='style']").click()
            audit("frame style")
            page.locator("[data-frame-review-open]").click()
            audit("frame review")
            page.keyboard.press("Escape")
            node.click()
            box = node.bounding_box()
            assert box is not None
            page.mouse.click(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, button="right"
            )
            audit("context menu")
            page.keyboard.press("Escape")

            assert not errors, errors
            assert not violations, "\n".join(violations)
            # the walk reached every kind of control the page is built from
            assert seen >= {
                "md-button",
                "md-icon-button",
                "md-segmented",
                "md-chip",
                "md-list-item",
                "md-nav-item",
                "md-tab",
                "md-tile",
                "md-switch",
                "md-checkbox",
                "md-field__input",
                "md-search",
            }, seen
        finally:
            browser.close()
