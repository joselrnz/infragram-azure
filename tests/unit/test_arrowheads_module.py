"""One arrowhead spec, every consumer (ADR 0006, rule 9).

The numbers live in ``skills/infragram-azure/assets/catalog/arrowheads.json``. The
Python module reads them for the static picture and for the editor page; the
checker reads the same file. These tests hold each consumer to the spec, so a
head can only change in one place.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

from infragram import compose
from infragram.builders import arrowheads
from infragram.exports import render_project_html
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import general

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
SPEC = ROOT / "skills/infragram-azure/assets/catalog/arrowheads.json"


def _checker():
    spec = importlib.util.spec_from_file_location(
        "project_check", ROOT / "skills/infragram-azure/scripts/project_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _project():
    reset_ids()
    internet = shared.networking.PublicInternet("Internet", "public")
    browser = general.Browser("Browser", "client")
    internet.to(browser, label="egress")
    return compose.to_project(
        [internet, browser], slug="heads", title="Heads", description="h.", display="card"
    )


def test_the_spec_is_the_module_s_only_source() -> None:
    data = json.loads(SPEC.read_text(encoding="utf-8"))
    assert arrowheads.spec_path() == SPEC
    assert arrowheads.shaft() == data["shaft"]
    head = arrowheads.head()
    assert head.name == data["default"]
    assert (head.length, head.width) == (
        data["heads"][head.name]["length"],
        data["heads"][head.name]["width"],
    )
    # the shaft leaves room for the head, so the head never sits on a bend
    assert arrowheads.shaft() >= head.length + 2


def test_a_marker_is_a_fixed_size_with_its_tip_carried_past_the_wire_s_end() -> None:
    head = arrowheads.head("triangle")
    markup = arrowheads.marker("arrow-x", "triangle", "#123456")
    assert 'markerUnits="userSpaceOnUse"' in markup
    # the wire stops tip_clear short of the anchor; refX puts the tip back on it
    assert (
        f'refX="{head.length - arrowheads.tip_clear():g}"' in markup
        and f'markerWidth="{head.length:g}"' in markup
    )
    assert f'refY="{head.width / 2:g}"' in markup and f'markerHeight="{head.width:g}"' in markup
    assert 'fill="#123456"' in markup and "{paint}" not in markup
    assert 0 < arrowheads.tip_clear() < head.length
    assert arrowheads.head("no-such-head").name == arrowheads.default_name()
    assert head.label and arrowheads.select_options().count("<option") == len(arrowheads.heads())


def test_the_static_picture_draws_the_spec_s_head() -> None:
    html = render_project_html(_project())
    static = re.search(r"<svg[^>]*data-infragram-diagram[^>]*>.*?</svg>", html, re.S).group(0)
    markers = re.findall(r"<marker\b[^>]*>.*?</marker>", static, re.S)
    assert markers, "the static picture defines its arrowheads"
    for marker in markers:
        marker_id = re.search(r'id="([^"]+)"', marker).group(1)
        paint = re.search(r'(?:fill|stroke)="(#[0-9A-Fa-f]{6})"', marker).group(1)
        assert re.sub(r"\s+", " ", marker) == arrowheads.marker(marker_id, None, paint)


def test_the_editor_page_carries_the_spec_for_the_runtime() -> None:
    html = render_project_html(_project())
    tag = re.search(
        r'<script type="application/json" id="infragram-arrowheads">(.*?)</script>', html, re.S
    )
    assert tag, "the shell writes the arrowhead spec into the page"
    assert json.loads(tag.group(1)) == json.loads(SPEC.read_text(encoding="utf-8"))
    assert html.index('id="infragram-arrowheads"') < html.index("data-infragram-editor"), (
        "the spec precedes the runtime"
    )


def test_the_checker_reads_the_same_spec_and_rejects_a_foreign_head() -> None:
    checker = _checker()
    assert checker.ARROWHEADS == SPEC
    assert checker.arrowhead_length() == arrowheads.head().length
    html = render_project_html(_project())
    static = re.search(r"<svg[^>]*data-infragram-diagram[^>]*>.*?</svg>", html, re.S).group(0)
    errors: list[str] = []
    checker.check_svg(static, errors)
    assert not [e for e in errors if "not the house head" in e], errors
    # the old stroke-scaled head, back in the picture, fails
    foreign = re.sub(
        r'<marker id="(arrow-[^"]+)"[^>]*>',
        r'<marker id="\1" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">',
        static,
    )
    errors = []
    checker.check_svg(foreign, errors)
    assert [e for e in errors if "not the house head" in e and "markerUnits" in e], errors
