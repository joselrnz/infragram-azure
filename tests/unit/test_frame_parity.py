"""Both renderers draw one frame the same way.

For every frame class in every library, render a one-frame project through
the Python renderer and build the editor state for the same project, then
compare what each says about the frame: border colour, weight and dash, the
tab's paint and seat, badge or glyph, and the caption's face, size, weight,
tracking, case and colour. The derivation lives in one place
(``builders/frame_style.py``); this file proves nothing downstream re-derives
it, and that the numbers both read come from ``render-metrics.json``.
"""

from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path

import pytest

import infragram.nodes.frames as frames_package
from infragram.builders import metrics
from infragram.builders.architecture import from_topology, load_style, load_theme
from infragram.builders.scene import ClusterStyle
from infragram.catalog import ARCHITECTURE_BOUNDARY_SPECS, architecture_boundary_group
from infragram.editor.state import _editor_state
from infragram.exports import render_project_svg
from infragram.nodes import infragram as shared, reset_ids
from infragram.patterns import Blueprint

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
FRAME = metrics.frame()


def _frames(group: str) -> list[type]:
    module = importlib.import_module(f"infragram.nodes.frames.{group}")
    return [
        cls
        for name in sorted(dir(module))
        for cls in [getattr(module, name)]
        if inspect.isclass(cls) and getattr(cls, "KIND", None) and getattr(cls, "FRAME_ID", None)
    ]


CASES = [(g, cls) for g in frames_package.GROUPS for cls in _frames(g)]


def _provider(group: str) -> str:
    """The library a one-frame project opens in. The core frames belong to
    no library, so theirs opens in Azure; the frame itself keeps the neutral
    ``generic`` look in both renderers."""
    return "azure" if group == "generic" else group


def _one_frame(cls: type, provider: str):
    reset_ids()
    plan = Blueprint.fresh("parity", "parity", "One frame.")
    plan.kind = "single-cloud"
    plan.providers = (provider,)
    (frame,) = plan.add(cls(cls.LABEL or cls.__name__))
    frame >> shared.compute.PhysicalServer("", "")
    return plan.to_project()


_FRAME_RE = re.compile(
    r'<rect x="(\d+)" y="(\d+)" width="\d+" height="\d+" rx="(\d+)" fill="([^"]*)"/>\s*'
    r'<path d="[^"]*" fill="none" stroke="([^"]+)" stroke-width="([\d.]+)"'
    r'(?: stroke-dasharray="([^"]+)")?/>\s*'
    r'<text x="[\d.]+" y="[\d.]+" fill="([^"]+)" font-size="([\d.]+)" font-family="([^"]+)"'
    r'(?: font-weight="(\d+)")? letter-spacing="([^"]+)" text-anchor="start">([^<]*)</text>'
)
_TAB_RE = re.compile(
    r'<rect x="([\d.]+)" y="([\d.]+)" width="(\d+)" height="\d+" fill="([^"]+)"/>\s*'
    r'(<use href="#(?:icon|frame-glyph)-[^"]+")'
)


@pytest.mark.parametrize("group,cls", CASES, ids=[f"{g}.{c.__name__}" for g, c in CASES])
def test_static_and_editor_describe_the_frame_identically(group: str, cls: type) -> None:
    provider = _provider(group)
    # The look is the gallery's own: a core frame inside an Azure project
    # draws with the generic theme, not the project's.
    style, theme = load_style(group), load_theme(group)
    project = _one_frame(cls, provider)
    svg = render_project_svg(project)
    box = _FRAME_RE.search(svg)
    assert box, f"{group}.{cls.__name__}: no frame box in the static picture"
    x, y, rx, fill, stroke, width, dash, label_fill, label_size, family, weight, tracking, text = (
        box.groups()
    )
    tab = _TAB_RE.search(svg)
    assert tab, f"{group}.{cls.__name__}: no seated tab in the static picture"
    tab_x, tab_y, tab_size, tab_fill, mark = tab.groups()

    scene = from_topology(
        project.topology,
        theme,
        slug=project.slug,
        title=project.title,
        desc=project.description,
        style=style,
    )
    (state,) = _editor_state(project, scene, {"providers": []})["boundaries"]

    assert state["stroke"].lower() == stroke.lower()
    assert state["strokeWidth"] == float(width)
    assert state["dash"] == dash
    assert state["radius"] == int(rx)
    assert state["fill"].lower() == fill.lower()
    assert state["tabbed"] is True
    assert int(tab_size) == FRAME["tab"] == state["tab"]
    assert state["tabFill"].lower() == tab_fill.lower()
    assert (float(tab_x), float(tab_y)) == (int(x) + float(width) / 2, int(y) + float(width) / 2)
    assert state["iconUri"].startswith("data:image/svg+xml")
    badge = bool(style.cluster.icon_for(cls.KIND))
    assert ('href="#icon-' in mark) == badge, f"{group}.{cls.__name__}: badge {badge}, drew {mark}"
    if not badge:
        assert f'<symbol id="frame-glyph-{cls.KIND}"' in svg, (
            f"{group}.{cls.__name__}: glyph symbol missing"
        )
    assert state["labelColor"].lower() == label_fill.lower()
    assert state["labelSize"] == float(label_size)
    assert (state["labelFont"] == "mono") == ("Mono" in family)
    assert state["labelWeight"] == (int(weight) if weight else None)
    assert state["labelTracking"] == tracking
    label = cls.LABEL or cls.__name__
    assert text == (label.upper() if state["labelCase"] == "upper" else label)
    assert state["pad"] == style.cluster.pad


def test_frame_numbers_come_from_the_shared_metrics() -> None:
    cs = ClusterStyle()
    assert (cs.tab, cs.label_icon, cs.label_icon_gap) == (
        FRAME["tab"],
        FRAME["icon"],
        FRAME["label_gap"],
    )
    from infragram.editor.bundle import runtime_script

    runtime = runtime_script()
    assert "METRICS.frame" in runtime
    for literal in ("bx + tab + 5", "labelSize / 2.8", "tabX + 2", "tab - 4"):
        assert literal not in runtime, f"runtime still hard-codes {literal!r}"


def test_the_gallery_table_agrees_with_the_theme_colour() -> None:
    """The sidebar's frame table names a colour per library; it must be the theme's."""
    for component_id, *_rest, paint in ARCHITECTURE_BOUNDARY_SPECS:
        group = architecture_boundary_group(component_id)
        assert paint.lower() == load_style(group).cluster.color.lower(), (component_id, paint)


def test_every_shipped_theme_declares_its_frame_colour() -> None:
    for path in sorted((ROOT / "skills" / "infragram-azure" / "assets" / "themes").glob("*.json")):
        style = load_style(path.stem)
        if style.cluster == ClusterStyle():
            continue  # no boundaries block: the catalog theme
        assert style.cluster.color, f"{path.stem} leaves frames to the depth-faded role"
