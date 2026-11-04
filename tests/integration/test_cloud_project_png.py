from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from infragram.exports import (
    PNG_CONTENT_MARGIN,
    export_project,
    playwright_png_renderer,
    render_project_html,
)
from infragram.projects import CloudProject

pytestmark = pytest.mark.skipif(
    os.environ.get("INFRAGRAM_RUN_BROWSER_TESTS") != "1",
    reason="set INFRAGRAM_RUN_BROWSER_TESTS=1 to run Chromium export checks",
)


def _png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _one_frame_project() -> CloudProject:
    # One empty Azure frame far from the origin of the editor canvas. The
    # capture must hold the frame and its margin, not the canvas or the
    # editor chrome around it.
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "single-cloud",
            "slug": "one-frame",
            "title": "One frame",
            "description": "A single VNet frame with nothing inside it.",
            "providers": [{"id": "azure", "enabled": True}],
            "default_library": "azure",
            "presentation": {"size": "fit"},
            "topology": {
                "id": "root",
                "name": "One frame",
                "type": "group",
                "children": [
                    {
                        "id": "vnet",
                        "name": "VNet",
                        "type": "network",
                        "attributes": {
                            "editor_x": 704,
                            "editor_y": 564,
                            "editor_width": 400,
                            "editor_height": 280,
                            "editor_frame_group": "azure",
                        },
                    }
                ],
            },
        }
    )


def test_editor_png_is_cropped_to_the_drawn_content(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    source = tmp_path / "one-frame.html"
    source.write_text(render_project_html(_one_frame_project()), encoding="utf-8")
    output = tmp_path / "one-frame.png"

    playwright_png_renderer(source, output, 1)

    data = output.read_bytes()
    width, height = _png_size(data)
    from infragram.builders import metrics

    mark = metrics.mark()
    expected_width = 400 + 2 * PNG_CONTENT_MARGIN
    # The crop holds the drawn content, the provider mark's band beneath it
    # (one gap, then the mark's drawn artwork, which fills at most its box),
    # and the margin around both.
    band_floor = 280 + mark["gap"] + 2 * PNG_CONTENT_MARGIN
    band_ceiling = band_floor + mark["height"]
    # Strokes and the caption tab add a few pixels; the editor world would add
    # well over a thousand.
    assert expected_width <= width <= expected_width + 24
    assert band_floor < height <= band_ceiling + 24, (width, height)
    assert data[25] in {4, 6}


def test_exports_draw_cards_in_the_requested_theme(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    project = CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "single-cloud",
            "slug": "one-card",
            "title": "One card",
            "description": "A single EC2 card.",
            "providers": [{"id": "azure", "enabled": True}],
            "default_library": "azure",
            "presentation": {"size": "fit", "display": "card"},
            "topology": {
                "id": "root",
                "name": "One card",
                "type": "group",
                "children": [
                    {
                        "id": "web",
                        "name": "Web",
                        "type": "service",
                        "component": {
                            "provider": "azure",
                            "service_id": "virtual-machine",
                            "icon_ref": "azure:virtual-machine",
                        },
                        "attributes": {"editor_x": 200, "editor_y": 200},
                    }
                ],
            },
        }
    )

    light = export_project(project, tmp_path / "light", formats=("svg",)).svg.read_text(
        encoding="utf-8"
    )
    dark = export_project(project, tmp_path / "dark", formats=("svg",), theme="dark").svg.read_text(
        encoding="utf-8"
    )

    # Light: white card, dark text. Dark: the editor's dark card, light text.
    # Compared case-insensitively: the ink travels from the theme manifest,
    # which spells its hex in lower case.
    light_hex, dark_hex = light.lower(), dark.lower()
    assert 'fill="#ffffff"' in light_hex and 'fill="#0f1b2a"' in light_hex
    assert 'fill="#2c2e33"' not in light_hex
    assert 'fill="#2c2e33"' in dark_hex and 'fill="#f8f8f8"' in dark_hex


def test_editor_svg_follows_the_authored_layout(tmp_path: Path) -> None:
    pytest.importorskip("playwright")

    result = export_project(_one_frame_project(), tmp_path, formats=("svg", "png"), scale=1)

    svg = result.svg.read_text(encoding="utf-8")
    assert result.notes == ()
    # The runtime drew it: the frame is a live boundary group, cropped to the
    # same box as the PNG, not the static layout of the HTML source.
    assert "data-graph-boundary" in svg
    match = re.search(r'viewBox="([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+)"', svg)
    assert match is not None
    x, y, width, height = (float(value) for value in match.groups())
    assert 704 - PNG_CONTENT_MARGIN - 4 <= x <= 704 - PNG_CONTENT_MARGIN
    assert 564 - PNG_CONTENT_MARGIN - 4 <= y <= 564 - PNG_CONTENT_MARGIN
    png_width, png_height = _png_size(result.png.read_bytes())
    assert abs(width - png_width) <= 1
    assert abs(height - png_height) <= 1


def test_playwright_png_has_an_alpha_channel(tmp_path: Path) -> None:
    pytest.importorskip("playwright")
    source = tmp_path / "diagram.html"
    source.write_text(
        """<!doctype html>
<html><style>html,body{background:white}svg{display:block;width:20px;height:20px;border:1px solid red}</style>
<body><svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
<title>Alpha</title><rect x="8" y="8" width="24" height="24" fill="#0078d4"/>
</svg></body></html>""",
        encoding="utf-8",
    )
    output = tmp_path / "diagram.png"

    playwright_png_renderer(source, output, 2)

    data = output.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(data[16:20], "big") == 80
    assert int.from_bytes(data[20:24], "big") == 80
    # PNG IHDR colour type: 4 (greyscale+alpha) or 6 (RGBA).
    assert data[25] in {4, 6}
