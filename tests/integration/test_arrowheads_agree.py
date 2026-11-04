"""The editor runtime draws the head the spec describes (ADR 0006, rule 9).

The runtime builds its markers from the spec the page carries; the static
renderer builds its markers from the same file through builders/arrowheads.py.
An export through the real browser proves the two agree byte for byte, and
the shipped checker accepts the export's heads.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from infragram import compose
from infragram.builders import arrowheads
from infragram.exports import export_project
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import general

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


def _checker():
    spec = importlib.util.spec_from_file_location(
        "project_check", ROOT / "skills/infragram-azure/scripts/project_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_the_runtime_s_markers_are_the_spec_s_markers(tmp_path: Path) -> None:
    pytest.importorskip("playwright.sync_api")
    reset_ids()
    internet = shared.networking.PublicInternet("Internet", "public")
    browser = general.Browser("Browser", "client")
    internet.to(browser, label="egress")
    project = compose.to_project(
        [internet, browser], slug="agree", title="Agree", description="a.", display="card"
    )
    result = export_project(project, tmp_path, formats=("html", "svg"))
    svg = result.svg.read_text(encoding="utf-8")
    markers = {
        m.group(1): m.group(0)
        for m in re.finditer(
            r'<marker id="(infragram-editor-arrow[^"]*)"[^>]*>.*?</marker>', svg, re.S
        )
    }
    assert set(markers) >= {
        "infragram-editor-arrow",
        "infragram-editor-arrow-open",
        "infragram-editor-arrow-circle",
        "infragram-editor-arrow-diamond",
    }

    # The browser serialises empty elements as <path ...></path>; the Python
    # side writes <path .../>. Same element either way.
    def normal(markup: str) -> str:
        return re.sub(r"></(path|circle)>", "/>", re.sub(r"\s+", " ", markup))

    for marker_id, markup in markers.items():
        name = next((n for n in ("open", "circle", "diamond") if f"-{n}" in marker_id), "triangle")
        assert normal(markup) == normal(arrowheads.marker(marker_id, name, "context-stroke")), (
            marker_id
        )
    errors: list[str] = []
    _checker().check_svg(svg, errors)
    assert not [e for e in errors if "house head" in e or "arrowhead" in e], errors
