"""A badge never dissolves into its own tab.

The badge tab used to be painted in the frame's colour with the glyph forced
to paper on top. That is right for AWS, whose group boxes are white marks on
their own coloured square. Azure's badges are full-colour icons -- and the
Azure frame colours were sampled from those very icons -- so a teal
management-group mark sat on a teal tab, an orange key on an orange tab, cyan
chevrons on a blue tab, and every one of them vanished.

``tab_fill`` on the theme decides: ``frame`` keeps the AWS treatment,
``paper`` leaves the tab white so the icon paints itself. This file holds the
choice for every badged frame in both renderers, and measures that the badge
actually stands apart from whatever it sits on.
"""

from __future__ import annotations

import importlib
import inspect
import re
from collections import Counter
from pathlib import Path

import pytest

import infragram.nodes.frames as frames_package
from infragram.builders.architecture import from_topology, load_icon_set, load_style, load_theme
from infragram.builders.ink import contrast
from infragram.editor.state import _editor_state
from infragram.exports import render_project_svg
from infragram.nodes import infragram as shared, reset_ids
from infragram.patterns import Blueprint

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())

#: Below this a mark is merging into its background. Not a text-contrast
#: claim -- a floor against the exact failure this file was written after.
FLOOR = 1.8


def _badged(group: str) -> list[tuple[type, str]]:
    # The core frames draw with the neutral ``generic`` theme, which declares
    # no badges, so the generic group contributes no case.
    icons = load_style(group).cluster.icons or {}
    module = importlib.import_module(f"infragram.nodes.frames.{group}")
    found = []
    for name in sorted(dir(module)):
        cls = getattr(module, name)
        if (
            inspect.isclass(cls)
            and getattr(cls, "KIND", None)
            and getattr(cls, "FRAME_ID", None)
            and icons.get(cls.KIND)
        ):
            found.append((cls, icons[cls.KIND]))
    return found


def _main_colours(reference: str) -> list[str]:
    """The three colours a badge icon is mostly made of, white and black aside.

    An Azure icon is two-tone -- the VNet mark is a cyan body with a darker
    blue edge -- so legibility is decided by its darkest main colour, not by
    whichever tone happens to cover more area.
    """
    collection, _, slug = reference.partition(":")
    pack = load_icon_set(collection)
    icon = pack[slug] if "#" in slug else pack.find(slug)
    text = icon.path.read_text(encoding="utf-8")
    fills = [c.lower() for c in re.findall(r'fill[=:]\s*"?(#[0-9a-fA-F]{6})', text)]
    fills = [c for c in fills if c not in ("#ffffff", "#000000")]
    return [colour for colour, _ in Counter(fills).most_common(3)]


def _one_frame(cls: type, provider: str):
    reset_ids()
    plan = Blueprint.fresh("tab", "tab", "One frame.")
    plan.kind = "single-cloud"
    plan.providers = (provider,)
    (frame,) = plan.add(cls(cls.LABEL or cls.__name__))
    frame >> shared.compute.PhysicalServer("", "")
    return plan.to_project()


CASES = [(g, cls, ref) for g in frames_package.GROUPS for cls, ref in _badged(g)]


@pytest.mark.parametrize(
    "group,cls,reference", CASES, ids=[f"{g}.{c.__name__}" for g, c, _ in CASES]
)
def test_the_badge_stands_apart_from_its_tab(group: str, cls: type, reference: str) -> None:
    """The static picture: what the tab is painted, and what sits on it."""
    provider = group
    style = load_style(provider)
    theme = load_theme(provider)
    svg = render_project_svg(_one_frame(cls, provider))
    tabs = re.findall(r'<rect x="[\d.]+" y="[\d.]+" width="20" height="20" fill="([^"]+)"/>', svg)
    assert tabs, f"{group}.{cls.__name__} drew no badge tab"
    tab_paint = tabs[0].lower()
    if style.cluster.tab_fill == "paper":
        assert tab_paint == theme["paper"].lower(), f"{group}: paper tab painted {tab_paint}"
        colours = _main_colours(reference)
        if colours:
            best = max(contrast(colour, tab_paint) for colour in colours)
            assert best >= FLOOR, (
                f"{group}.{cls.__name__}: badge {reference} is {colours}, at best "
                f"{best:.1f}:1 against its tab -- it is dissolving again"
            )
    else:
        # A frame tab carries the deck's coloured square, which paints itself.
        assert tab_paint != theme["paper"].lower(), f"{group}: frame tab came out paper"


@pytest.mark.parametrize("group", sorted({g for g, _, _ in CASES}))
def test_both_renderers_paint_the_tab_the_same(group: str) -> None:
    """The editor state carries the same tab paint the static picture draws."""
    provider = group
    style, theme = load_style(provider), load_theme(provider)
    cls, _ = _badged(group)[0]
    project = _one_frame(cls, provider)
    svg = render_project_svg(project)
    static_tab = re.findall(
        r'<rect x="[\d.]+" y="[\d.]+" width="20" height="20" fill="([^"]+)"/>', svg
    )[0].lower()
    scene = from_topology(
        project.topology,
        theme,
        slug=project.slug,
        title=project.title,
        desc=project.description,
        style=style,
    )
    state = _editor_state(project, scene, {"providers": []})
    editor_tabs = {
        str(b.get("tabFill", "")).lower() for b in state.get("boundaries") or [] if b.get("tabbed")
    }
    assert static_tab in editor_tabs, f"{group}: static {static_tab}, editor {sorted(editor_tabs)}"


@pytest.mark.parametrize(
    "group,cls,reference", CASES, ids=[f"{g}.{c.__name__}" for g, c, _ in CASES]
)
def test_the_tab_seats_inside_the_border(group: str, cls: type, reference: str) -> None:
    """The tab's outer sides lie on the stroke's inner edge, never over it.

    Drawn at the frame corner itself the plate painted out the inner half of
    the border, and a paper plate made the badge look as if it sat on the
    line. So the plate is set in by half the stroke, and the border stays
    whole around the corner.
    """
    provider = group
    style = load_style(provider)
    svg = render_project_svg(_one_frame(cls, provider))
    frame = re.search(
        r'<rect x="(\d+)" y="(\d+)" width="\d+" height="\d+" rx="\d+" fill="[^"]*"/>\s*'
        r'<path d="[^"]*" fill="none" stroke="[^"]*" stroke-width="([\d.]+)"',
        svg,
    )
    assert frame, f"{group}.{cls.__name__}: no frame box"
    x, y, width = int(frame.group(1)), int(frame.group(2)), float(frame.group(3))
    tab = re.search(r'<rect x="([\d.]+)" y="([\d.]+)" width="20" height="20" fill="[^"]+"/>', svg)
    assert tab, f"{group}.{cls.__name__} drew no badge tab"
    assert width == style.cluster.width_for(cls.KIND)
    assert (float(tab.group(1)), float(tab.group(2))) == (x + width / 2, y + width / 2), (
        f"{group}.{cls.__name__}: tab at {tab.groups()} for a frame at ({x}, {y}) "
        f"with a {width:g} px line"
    )


def test_frame_lines_are_one_pixel_unless_the_deck_says_otherwise() -> None:
    """One weight for every library: no shipped deck publishes a heavier line."""
    from infragram.editor.artwork import _boundary_component_style

    for provider in ("azure", "kubernetes", "generic"):
        assert load_style(provider).cluster.width_for("network") == 1.0
        assert _boundary_component_style(provider, "network")["strokeWidth"] == 1.0
    # The house rule keeps one heavier line for an outermost cloud frame.
    assert load_style("generic").cluster.width_for("cloud") == 1.8
    assert _boundary_component_style("generic", "cloud")["strokeWidth"] == 1.8


def test_azure_uses_paper_tabs_and_kubernetes_keeps_the_frame() -> None:
    # Azure's badges are full-colour icons the frame colours were sampled
    # from, so the tab stays paper; the Kubernetes mark is mono and reverses
    # out of a frame-coloured tab the way the deck draws it.
    assert load_style("azure").cluster.tab_fill == "paper"
    assert load_style("kubernetes").cluster.tab_fill == "frame"
    assert load_style("generic").cluster.tab_fill == "frame"
