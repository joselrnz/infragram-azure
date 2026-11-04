"""A PNG export draws the arrowheads the SVG draws.

The PNG capture stages a copy of the runtime's SVG export inside the editor
page. When the live diagram stayed in the document, its identical marker ids
won the url(#...) lookup from inside a hidden subtree, and every PNG came out
headless while the SVG kept its heads. The head is measured here: the wire's
last pixels must be taller than the wire itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from infragram import compose
from infragram.exports import export_project
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import general


def _two_glyphs():
    reset_ids()
    internet = shared.networking.PublicInternet("Internet", "public")
    browser = general.Browser("Browser", "client")
    internet.to(browser, label="egress")
    return compose.to_project(
        [internet, browser], slug="arrowheads", title="Arrowheads", description="a.", display="card"
    )


def _wire_profile(png_path: Path) -> tuple[int, int]:
    """(thickness of the wire mid-way, thickness within its last 12 px)."""
    Image = pytest.importorskip("PIL.Image")
    image = Image.open(png_path).convert("RGBA")
    width, height = image.size

    def grey(x: int, y: int) -> bool:
        r, g, b, a = image.getpixel((x, y))
        return a > 120 and r + g + b < 600 and abs(r - b) < 60

    best = (0, 0, 0, 0)
    for y in range(height):
        run = 0
        for x in range(width):
            if grey(x, y):
                run += 1
                if run > best[0]:
                    best = (run, y, x - run + 1, x)
            else:
                run = 0
    length, y, x0, x1 = best
    assert length > 40, "the picture has a horizontal wire"

    def thickness(x: int) -> int:
        ys = [yy for yy in range(max(0, y - 12), min(height, y + 13)) if grey(x, yy)]
        return max(ys) - min(ys) + 1 if ys else 0

    middle = thickness((x0 + x1) // 2)
    head = max(thickness(x) for x in range(max(x0, x1 - 12), x1 + 1))
    return middle, head


def test_png_export_carries_the_arrowhead(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    result = export_project(_two_glyphs(), tmp_path, formats=("html", "png"), scale=2)
    assert result.png is not None and result.png.is_file()
    middle, head = _wire_profile(result.png)
    assert head >= middle + 4, f"the wire ends with a head (wire {middle} px, end {head} px)"
