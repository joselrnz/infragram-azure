"""One description of how a frame draws, for every renderer.

A frame is drawn by the Python renderer (builders/render.py), by the editor
runtime from the state the shell writes into the page, and as the sidebar's
gallery thumbnail. All three read colour, dash, weight, tab and caption from
this module, never from the theme on their own, so one frame cannot draw
three ways. A caller adds only what is specific to it -- a ``<symbol>`` id or
a data URI for the badge.

The numbers both renderers share -- tab size, glyph inset, caption gap and
baseline -- live in ``assets/catalog/render-metrics.json`` under ``frame``;
the generic glyph for each frame kind lives in
``assets/catalog/frame-glyphs.json``. ``tests/unit/test_frame_parity.py``
renders every frame both ways and compares.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from html import escape

from pydantic import BaseModel, ConfigDict, Field

from ..catalog.ink import on_dark
from ..paths import skill_assets
from .ink import readable as readable_ink, rgba
from .scene import ClusterStyle


class FramePaint(BaseModel):
    """Everything a renderer needs to draw one frame of one kind."""

    model_config = ConfigDict(frozen=True)

    stroke: str
    fill: str
    dash: str | None
    width: float
    radius: int
    tab: int
    #: What the corner tab is painted: the paper, or the frame's own colour.
    tab_fill: str
    #: The ink a mono badge or the generic glyph takes on that tab.
    glyph_ink: str
    #: True when the tab is the paper rather than the frame's own colour. A
    #: coloured tab needs a single-ink glyph to read against it; a paper tab
    #: is white, so the vendor's own full-colour badge keeps its colours.
    paper_tab: bool
    #: The theme's badge for the kind (``collection:slug``), or "" for the
    #: generic glyph.
    badge: str
    label_color: str
    label_font: str
    label_size: float
    label_weight: int | None
    label_tracking: str
    label_case: str
    pad: int


def frame_paint(
    cs: ClusterStyle, theme: Mapping[str, str], kind: str, *, depth: int = 0
) -> FramePaint:
    """Derive one frame's look from the theme's boundary style.

    Colour is the theme's entry for the kind, else the theme's frame colour;
    only a theme that declares neither falls back to the border role faded
    by nesting depth, the one place depth still matters. Fill is ``none``
    unless the theme declares one for the kind.
    """
    declared = cs.color_for(kind)
    if declared:
        stroke = theme.get(declared, declared)
    else:
        stroke = rgba(theme[cs.border_role], cs.border_at(depth))
    declared_fill = cs.fill_for(kind)
    if declared_fill and declared_fill != "none":
        fill_paint = theme.get(declared_fill, declared_fill)
        fill = rgba(fill_paint, cs.fill_tint)
    else:
        fill = "none"
    paper = theme["paper"]
    # A library's own colour on a dark ground: kept while it can be seen,
    # lifted when it cannot (catalog/ink.py on_dark). Without this an AWS
    # cloud frame is navy on near-black -- a border and a title drawn where
    # nobody can read them -- in the picture and on the canvas alike.
    if getattr(theme, "dark", False):
        stroke = on_dark(stroke, paper)
    paper_tab = cs.tab_fill == "paper"
    return FramePaint(
        stroke=stroke,
        fill=fill,
        dash=cs.dash_for(kind),
        width=cs.width_for(kind),
        radius=cs.radius_for(kind),
        tab=cs.tab,
        tab_fill=paper if paper_tab else stroke,
        glyph_ink=stroke if paper_tab else paper,
        paper_tab=paper_tab,
        badge=cs.icon_for(kind),
        label_color=readable_ink(stroke) if declared else theme["soft"],
        label_font=cs.label_font,
        label_size=cs.label_size,
        label_weight=cs.label_weight,
        label_tracking=cs.label_tracking,
        label_case=cs.label_case,
        pad=cs.pad,
    )


class FrameGlyphs(BaseModel):
    """``assets/catalog/frame-glyphs.json``: one stroked mark per frame kind."""

    model_config = ConfigDict(extra="forbid")

    description: str = ""
    view_box: str
    stroke_width: float
    default: str
    glyphs: dict[str, str] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def _glyphs() -> FrameGlyphs:
    path = skill_assets() / "catalog" / "frame-glyphs.json"
    return FrameGlyphs.model_validate_json(path.read_text(encoding="utf-8"))


def frame_glyph_body(kind: str) -> str:
    """The generic glyph's path body for a frame kind (a plain box if none)."""
    doc = _glyphs()
    return doc.glyphs.get(kind, doc.default)


def _glyph_style(paint: str) -> str:
    doc = _glyphs()
    return (
        f'fill="none" stroke="{escape(str(paint), quote=True)}" stroke-width="{doc.stroke_width}" '
        'stroke-linecap="round" stroke-linejoin="round"'
    )


def frame_glyph_svg(kind: str, paint: str) -> str:
    """The generic glyph as a standalone ``<svg>`` (the editor's data URI)."""
    doc = _glyphs()
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{doc.view_box}" {_glyph_style(paint)}>'
        f"{frame_glyph_body(kind)}</svg>"
    )


def frame_glyph_symbol_id(kind: str) -> str:
    """The ``<symbol>`` id the static picture gives a kind's generic glyph."""
    return f"frame-glyph-{kind}"


def frame_glyph_symbol(kind: str) -> str:
    """The generic glyph as a ``<symbol>`` for an SVG's defs, stroked in
    currentColor so the ``<use>`` in each tab sets the ink.

    A symbol and a use, the same construct a vendor badge takes: every tool
    that reads an exported picture -- the checker, the metadata stripper, the
    viewBox parser -- assumes one root element and no nested groups inside a
    frame, and this keeps the cluster layer flat.
    """
    doc = _glyphs()
    return (
        f'<symbol id="{frame_glyph_symbol_id(kind)}" viewBox="{doc.view_box}" '
        f"{_glyph_style('currentColor')}>{frame_glyph_body(kind)}</symbol>"
    )
