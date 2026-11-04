"""A highlighted frame is part of the drawing, in both renderers.

The editor saves a call-out as ``editor_highlight`` on the frame's element.
The static renderer must draw the same accent ring, the editor must come up
with the frame highlighted, and a document that never used it must not
change: no ring, and the shipped golden pictures stay put.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from xml.etree import ElementTree

from infragram.exports import render_project_html, render_project_svg
from infragram.projects import CloudProject

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "infragram-azure"
    / "assets"
    / "templates"
    / "cloud"
    / "azure-aks-baseline.infragram.json"
)


def _highlighted(name: str) -> CloudProject:
    document = json.loads(TEMPLATE.read_text(encoding="utf-8"))

    def mark(element: dict) -> bool:
        if element.get("name") == name and element.get("children"):
            element.setdefault("attributes", {})["editor_highlight"] = True
            return True
        return any(mark(child) for child in element.get("children") or [])

    assert mark(document["topology"]), name
    return CloudProject.model_validate(document)


def test_the_static_picture_draws_a_highlighted_frame() -> None:
    assert "data-frame-highlight" not in render_project_svg(CloudProject.load(TEMPLATE))
    svg = render_project_svg(_highlighted("Supply chain and secrets"))
    assert svg.count("data-frame-highlight") == 1
    rings = [
        element
        for element in ElementTree.fromstring(svg).iter()
        if "data-frame-highlight" in element.attrib
    ]
    assert len(rings) == 1
    assert rings[0].attrib["stroke-width"] == "2.5" and rings[0].attrib["fill-opacity"] == ".07"


def test_the_editor_opens_with_the_frame_highlighted() -> None:
    html = render_project_html(_highlighted("Supply chain and secrets"))
    state = json.loads(
        re.search(
            r'<script type="application/json" id="infragram-editor-state" data-editor-state>(.*?)</script>',
            html,
            re.S,
        ).group(1)
    )
    highlighted = [frame["name"] for frame in state["boundaries"] if frame.get("highlight")]
    assert highlighted == ["Supply chain and secrets"]
