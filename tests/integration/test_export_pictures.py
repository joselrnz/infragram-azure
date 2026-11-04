"""Exported pictures: the crop keeps the legend, and an automatic caption sits on its wire."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from infragram.exports import export_project, render_project_html, render_timeout_ms
from infragram.projects import CloudProject

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="browser suite; set INFRAGRAM_RUN_BROWSER_TESTS=1",
)

TEMPLATES = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "infragram-azure"
    / "assets"
    / "templates"
    / "cloud"
)

_LABEL_DISTANCES = """
() => {
  const svg = document.querySelector('[data-infragram-diagram]');
  const out = [];
  svg.querySelectorAll('[data-edge-label]').forEach(label => {
    const text = label.querySelector('text');
    const id = label.dataset.edgeId || label.getAttribute('data-edge-label');
    const wire = svg.querySelector(`[data-graph-edge][data-edge-id="${id}"]`);
    if (!text || !wire) return;
    // the group is translated to the caption's anchor; the text's box sits
    // around its origin, so measure from the box, not from the anchor
    const x = Number(label.dataset.labelX);
    const y = Number(label.dataset.labelY);
    const box = text.getBBox();
    const left = x + box.x, right = left + box.width, top = y + box.y, bottom = top + box.height;
    const total = wire.getTotalLength();
    let best = Infinity;
    for (let step = 0; step <= 200; step += 1) {
      const point = wire.getPointAtLength(total * step / 200);
      const dx = Math.max(left - point.x, 0, point.x - right);
      const dy = Math.max(top - point.y, 0, point.y - bottom);
      best = Math.min(best, Math.hypot(dx, dy));
    }
    // the room the layout reserved for the caption, which is what it placed by
    const reserved = Number(label.querySelector('.edge-label-mask')?.getAttribute('width')) || box.width;
    out.push({id, label: text.textContent, distance: Math.round(best), wire: Math.round(total),
              width: Math.round(box.width), reserved: Math.round(reserved)});
  });
  return out;
}
"""


def _settled(page) -> None:
    page.wait_for_load_state("load")
    page.wait_for_function("window.infragramEditor", timeout=render_timeout_ms())


def test_the_exported_picture_keeps_the_whole_legend(tmp_path: Path) -> None:
    project = CloudProject.load(TEMPLATES / "azure-api.infragram.json")
    assert project.presentation.legend, "the template carries a legend"
    result = export_project(project, tmp_path, formats=("template", "html", "svg"))
    svg = result.svg.read_text(encoding="utf-8")
    box = [float(v) for v in re.search(r'viewBox="([^"]+)"', svg).group(1).split()]
    # the DOM serialises the bare attribute as data-legend-strip=""
    strip = re.search(r'<g data-legend-strip(?:="")?>(.*?)</g>', svg, flags=re.S)
    assert strip is not None, "the legend strip travels as one group"
    lowest = max(float(y) for y in re.findall(r'\sy="([\d.]+)"', strip.group(1)))
    assert box[1] + box[3] >= lowest, (
        f"the crop ends at {box[1] + box[3]} above the legend's last line at {lowest}"
    )
    for _kind, text in project.presentation.legend:
        assert text in strip.group(1)


@pytest.mark.parametrize(
    "name",
    ["azure-web-app-front-door", "azure-aks-baseline", "azure-hub-spoke-landing-zone"],
)
def test_an_automatic_caption_sits_on_its_wire(name: str, tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    source = tmp_path / f"{name}.html"
    source.write_text(
        render_project_html(CloudProject.load(TEMPLATES / f"{name}.infragram.json")),
        encoding="utf-8",
    )
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(source.resolve().as_uri())
            _settled(page)
            distances = page.evaluate(_LABEL_DISTANCES)
        finally:
            browser.close()
    assert distances, "the template has captions"
    # A caption's box sits a few pixels off its wire; a nudge off a card may
    # add a little. Thirty pixels is still beside the wire; a hundred is
    # floating. A caption that cannot fit on its whole wire -- a long name on
    # a short hop between two neighbours -- is allowed the nudge off the
    # pair, as the static picture gives it. It cannot fit when the room the
    # layout reserves for it, with 8 px of port room at each end, is longer
    # than the wire. The reserved room, not the glyphs: the layout places by
    # it, and a face narrower than the reservation must not make a caption
    # that was rightly moved read as one that floats.
    far = [d for d in distances if d["distance"] > (100 if d["reserved"] + 16 >= d["wire"] else 30)]
    # One caption may still be pushed off by a frame title its wire hugs;
    # before 0.1.32 six or seven per template floated in empty space.
    assert len(far) <= 1, far
