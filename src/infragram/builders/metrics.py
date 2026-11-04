"""The numbers both renderers must agree on, read from one file.

A document is drawn twice: by this package, and by the editor runtime inside
an exported page. They are separate implementations of the same picture, so
every number that decides where a wire runs or how a card is sized lives in
``assets/catalog/render-metrics.json`` and is read by both. Before this
existed the two had drifted -- the detour margin, the corner radius, the
widest an icon card could grow and the dash patterns all differed -- so the
same document drew differently depending on which renderer produced it.

The editor's values are canonical: every exported SVG and PNG comes from the
editor, so those are the pictures the world already has.

This module is what the Python side reads. The file loads through
:class:`RenderMetrics`, so a missing or mistyped number fails here with its
field name rather than as a ``KeyError`` inside a render. The editor page
carries the same file as a JSON script block, written by the editor shell.
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..paths import skill_assets

__all__ = [
    "CORNER_STYLES",
    "Card",
    "Corners",
    "FrameMetrics",
    "IconNode",
    "LinkDashes",
    "MarkMetrics",
    "PanelMetrics",
    "RenderMetrics",
    "Router",
    "Text",
    "card",
    "corner_radius",
    "corner_styles",
    "frame",
    "icon_node",
    "link_dashes",
    "load",
    "mark",
    "router",
    "runtime_json",
    "spec",
    "spec_path",
    "text",
    "tones",
    "panel",
]


class Corners(BaseModel):
    """How a wire turns a corner: the largest bend radius per style."""

    model_config = ConfigDict(extra="forbid")

    default: str = "sharp"
    rounded: float
    sharp: float
    curved: float
    note: str = ""


class Router(BaseModel):
    """How a wire finds its way: clearance off a card, stubs, detours, corners."""

    model_config = ConfigDict(extra="forbid")

    clearance: float
    stub: float
    #: How far apart wires joining the same pair of components are held.
    lane: float = 16.0
    margin: float
    turn_cost: float
    radius: float
    #: The semicircle and separation at a crossing between unrelated wires.
    crossing_radius: float = 8.0
    crossing_clearance: float = 3.0
    straighten: float
    #: The nearest obstacles a search considers before it falls back to all of them.
    max_obstacles: int = 48
    #: The lattice the plain dog-leg's middle snaps to (the editor's snap grid).
    grid: int = 4
    #: A segment this near a frame's border runs along it.
    rail: float = 4.0
    #: What a pixel run along a frame's border costs, on top of its length.
    rail_cost: float = 3.0
    #: How far along a border the plain path may run before the search runs.
    rail_run: float = 24.0
    #: What crossing the border of a frame that holds neither end of a wire
    #: costs, on top of the step's length.
    cross_cost: float = 0.0
    #: How far apart wires that run along one line are drawn, and the
    #: narrowest spacing worth drawing.
    spread: float = 8.0
    spread_min: float = 4.0
    note: str = ""
    corners: Corners


class IconNode(BaseModel):
    """The bare-glyph card: its box, its glyph, and how wide it may grow."""

    model_config = ConfigDict(extra="forbid")

    width: int
    height: int
    glyph: int
    #: Where the glyph's top sits below the node's top, in a captioned icon node.
    glyph_top: int = 4
    caption_min_height: int
    max_width: int
    #: The name, ``caption_gap`` below the glyph square, cut to
    #: ``max(caption_min_chars, (width - caption_pad) / (size * advance))``.
    caption_gap: float
    caption_pad: float
    caption_min_chars: int
    #: The detail, ``detail_gap`` below the square at ``detail_size``, cut to
    #: ``(width - caption_pad) / detail_advance``, on a node this tall or taller.
    detail_size: float
    detail_gap: float
    detail_advance: float
    detail_min_height: int
    note: str = ""


class LinkDashes(BaseModel):
    """The dash pattern for each line kind a theme does not override."""

    model_config = ConfigDict(extra="forbid")

    dashed: str
    dotted: str


class Card(BaseModel):
    """The card with a text lane: its box, how far Python may grow it, and
    where its icon and its two lines of text sit."""

    model_config = ConfigDict(extra="forbid")

    width: int
    #: The card's height, in both renderers.
    height: int = 64
    max_width: int
    #: The icon square, ``icon_x`` in and centred down; without artwork, a
    #: ``blank`` tile ``blank_x`` in carrying the name's first letter.
    icon: int
    icon_x: int
    blank: int
    blank_x: int
    #: Both lines start at ``text_x`` and keep ``text_end`` clear of the edge.
    text_x: int
    text_end: int
    title_size: float
    title_weight: int
    #: Baselines, from the card's middle.
    title_dy: float
    detail_size: float
    detail_dy: float
    #: Pixels per character of the detail line, at its size.
    detail_advance: float
    #: No line is cut shorter than ``min_chars``, nor measured in less room
    #: than ``min_room``.
    min_chars: int
    min_room: int
    note: str = ""


class Text(BaseModel):
    """The face every label is set in, and the one width estimate."""

    model_config = ConfigDict(extra="forbid")

    family: str
    #: Width per character, in em.
    advance: float
    note: str = ""


class FrameMetrics(BaseModel):
    """The badge tab and the frame defaults both renderers share."""

    model_config = ConfigDict(extra="forbid")

    tab: int
    icon: int
    icon_inset: int
    label_gap: int
    baseline_divisor: float
    #: The one estimate of a title's width, shared by both routers and the
    #: checker: ``max(label_min, len * size * label_advance + label_pad) + tab``.
    label_advance: float
    label_pad: int
    label_min: int
    #: Kinds that draw dashed unless the theme says otherwise: groupings a
    #: diagram invents to aid reading, not perimeters one could point at.
    dashed_kinds: list[str] = Field(default_factory=list)
    #: Line weights a kind takes unless the theme declares one.
    widths: dict[str, float] = Field(default_factory=dict)
    #: The project's frame lines (Presentation.frame_lines): what every
    #: frame's own width is multiplied by, in both renderers.
    line_scales: dict[str, float] = Field(default_factory=lambda: {"thin": 1.0})
    note: str = ""


class FlagMetrics(BaseModel):
    """The word on a card the estate keeps without using, in the card's
    top-right corner: ``label`` in ``ink`` (``ink_dark`` on a dark canvas)."""

    model_config = ConfigDict(extra="forbid")

    label: str
    font: float
    weight: int
    advance: float
    pad: float
    height: float
    inset: float
    radius: float
    fill: str
    stroke: str
    ink: str
    ink_dark: str = ""
    note: str = ""

    def width(self) -> int:
        return math.ceil(len(self.label) * self.font * self.advance + 2 * self.pad)


class MarkMetrics(BaseModel):
    """The provider mark's band: ``gap`` below the drawing, ``height`` tall."""

    model_config = ConfigDict(extra="forbid")

    gap: int
    height: int
    note: str = ""


class StepMetrics(BaseModel):
    """A numbered step: the circle at the start of a caption, and the list."""

    model_config = ConfigDict(extra="forbid")

    #: How far a numbered caption's chip reaches left of its text's: the
    #: circle and its inset, so placement, the chip and the checker count it.
    lead: int
    radius: float
    inset: float
    number_size: float
    #: How tall a numbered caption's chip is: it holds the circle.
    chip: float
    #: The step list: a panel ``list_gap`` right of the content, ``list_pad``
    #: inside its border, one ``list_row`` a step, its text ``list_size`` px.
    list_gap: int
    list_row: int
    list_size: float
    list_radius: float
    list_pad: int
    note: str = ""


class PanelMetrics(BaseModel):
    """A card that says more than a name and a detail line: several detail
    lines, compartments, or a shape (builders/panels.py lays it out)."""

    model_config = ConfigDict(extra="forbid")

    pad_x: float
    pad_top: float
    pad_bottom: float
    radius: float
    title_size: float
    title_weight: int
    title_line: float
    detail_size: float
    detail_line: float
    detail_advance: float
    cell_title_size: float
    cell_title_weight: int
    cell_title_line: float
    cell_size: float
    cell_line: float
    cell_advance: float
    cell_pad_x: float
    cell_pad_y: float
    icon: int
    icon_x: int
    icon_y: int
    min_width: int
    max_width: int
    fold: float
    hex_inset: float
    ellipse_pad: float
    ellipse_pad_y: float
    note: str = ""


class Tone(BaseModel):
    """A named fill that means something (the legend says what): its fill
    and outline on a light canvas, and on a dark one."""

    model_config = ConfigDict(extra="forbid")

    fill: str
    stroke: str
    fill_dark: str
    stroke_dark: str


class RenderMetrics(BaseModel):
    """Everything in ``render-metrics.json``; unknown keys are refused."""

    model_config = ConfigDict(extra="forbid")

    description: str = ""
    router: Router
    icon_node: IconNode
    link_dashes: LinkDashes
    card: Card
    frame: FrameMetrics
    flag: FlagMetrics
    mark: MarkMetrics
    step: StepMetrics
    text: Text
    panel: PanelMetrics
    tones: dict[str, Tone]


def spec_path() -> Path:
    return skill_assets() / "catalog" / "render-metrics.json"


@lru_cache(maxsize=1)
def load() -> RenderMetrics:
    """The validated metrics."""
    return RenderMetrics.model_validate_json(spec_path().read_text(encoding="utf-8"))


def spec() -> dict:
    """The metrics as a plain dict, the shape the editor page carries."""
    return load().model_dump()


def router() -> dict:
    """Clearance, stub, detour margin, turn cost, corner radius, straighten."""
    return dict(spec()["router"])


def icon_node() -> dict:
    """The bare-glyph card: its box, its glyph, and how wide it may grow."""
    return dict(spec()["icon_node"])


def card() -> dict:
    """The card with a text lane: its width, and how far Python may grow it."""
    return dict(spec()["card"])


def text() -> dict:
    """The face every label is set in, and its width per character in em."""
    return dict(spec()["text"])


def link_dashes() -> dict:
    """The dash pattern for each line kind a theme does not override."""
    return dict(spec()["link_dashes"])


def mark() -> dict:
    """The provider mark's band: ``gap`` below the drawing, ``height`` tall."""
    return dict(spec()["mark"])


def panel() -> PanelMetrics:
    """A card with several detail lines, compartments or a shape."""
    return load().panel


def tones() -> dict[str, Tone]:
    """The named fills a card or a compartment may take."""
    return dict(load().tones)


def flag() -> FlagMetrics:
    """The tag on a card the estate keeps without using."""
    return load().flag


def step() -> dict:
    """A numbered step: the caption's ``lead``, the circle's ``radius``,
    ``inset`` and ``number_size``, and the list's ``list_gap``, ``list_row``,
    ``list_size`` and ``list_radius``."""
    return dict(spec()["step"])


def frame() -> dict:
    """The badge tab and frame defaults: ``tab``, ``icon``, ``icon_inset``,
    ``label_gap``, ``baseline_divisor``, ``label_advance``, ``label_pad``,
    ``label_min``, ``dashed_kinds``, ``widths``."""
    return dict(spec()["frame"])


CORNER_STYLES = ("rounded", "sharp", "curved")


def corner_styles() -> tuple[str, ...]:
    """The bend styles a wire may take, in inspector order."""
    return CORNER_STYLES


def corner_radius(name: str | None = None) -> float:
    """The largest bend radius for a corner style; the default for None or an unknown name."""
    table = load().router.corners
    chosen = name if name in CORNER_STYLES else table.default
    return float(getattr(table, chosen))


def runtime_json() -> str:
    """The spec as the editor page carries it, safe inside a script tag."""
    # The shell owns the one escaping; imported here, not at the top, because
    # the shell imports this module.
    from ..editor.shell import script_safe

    return script_safe(json.dumps(spec(), separators=(",", ":")))
