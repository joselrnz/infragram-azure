"""The legend strip is one group, and the export crop names it."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from infragram import exports
from infragram.exports import render_project_svg
from infragram.projects import CloudProject

TEMPLATES = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "infragram-azure"
    / "assets"
    / "templates"
    / "cloud"
)


def test_the_static_picture_groups_its_legend() -> None:
    svg = render_project_svg(CloudProject.load(TEMPLATES / "azure-api.infragram.json"))
    groups = [
        element
        for element in ElementTree.fromstring(svg).iter()
        if "data-legend-strip" in element.attrib
    ]
    assert len(groups) == 1
    assert "LEGEND" in "".join(groups[0].itertext())


def test_the_capture_crops_to_the_legend_strip() -> None:
    assert "[data-legend-strip]" in exports.browser._EDITOR_PNG_CAPTURE
