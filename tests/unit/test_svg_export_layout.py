"""The SVG artifact comes from the editor runtime, with a documented static fallback."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from infragram.exports import ExportError, editor_page_url, export_project
from infragram.projects import CloudProject


def test_editor_page_url_carries_static_motion_and_the_requested_theme(tmp_path: Path) -> None:
    page = tmp_path / "diagram.html"

    assert editor_page_url(page).endswith("diagram.html?motion=static")
    assert editor_page_url(page, "light").endswith("diagram.html?motion=static&theme=light")
    assert editor_page_url(page, "dark").endswith("diagram.html?motion=static&theme=dark")
    with pytest.raises(ExportError):
        editor_page_url(page, "sepia")


def test_export_project_rejects_an_unknown_theme(tmp_path: Path) -> None:
    with pytest.raises(ExportError):
        export_project(_project(), tmp_path, formats=("html",), theme="sepia")


def _project() -> CloudProject:
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


def test_svg_export_asks_the_editor_runtime_for_its_layout(tmp_path: Path) -> None:
    calls: list[tuple[Path, Path]] = []

    def fake_renderer(source: Path, output: Path) -> None:
        assert source.is_file()
        calls.append((source, output))
        output.write_text('<svg viewBox="656 516 496 376" xmlns="http://www.w3.org/2000/svg"/>')

    result = export_project(_project(), tmp_path, formats=("svg",), svg_renderer=fake_renderer)

    assert len(calls) == 1
    source, output = calls[0]
    assert (source.name, output.name) == ("one-frame.html", "one-frame.svg")
    assert source.parent == output.parent
    assert source.parent.parent == tmp_path and source.parent.name.startswith(".infragram-")
    assert not source.parent.exists(), "successful exports remove their staging directory"
    assert result.html is None and not (tmp_path / "one-frame.html").exists()
    assert result.svg == tmp_path / "one-frame.svg"
    assert 'viewBox="656 516 496 376"' in result.svg.read_text(encoding="utf-8")
    assert result.notes == ()


def test_svg_export_falls_back_to_the_static_render_with_a_note(tmp_path: Path) -> None:
    def no_browser(source: Path, output: Path) -> None:
        raise ExportError("Playwright isn't installed.")

    result = export_project(_project(), tmp_path, formats=("svg",), svg_renderer=no_browser)

    svg = result.svg.read_text(encoding="utf-8")
    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "viewBox=" in svg
    # The diagram marker belongs to the picture; editor controls and active
    # HTML do not belong in a standalone SVG.
    root = ET.fromstring(svg)
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.get("data-infragram-diagram") == "true"
    for element in root.iter():
        assert element.tag.rsplit("}", 1)[-1] not in {
            "script",
            "foreignObject",
            "button",
            "input",
            "form",
        }
        assert (
            not {"data-editor-action", "data-boundary-resize", "data-resize-handle"}
            & element.attrib.keys()
        )
        assert not any(name.lower().startswith("on") for name in element.attrib)
    assert len(result.notes) == 1
    assert "drawn by the static renderer" in result.notes[0]
    assert "Playwright isn't installed." in result.notes[0]
