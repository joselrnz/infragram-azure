"""A panel: a card that says more than a name and a detail line.

Some pictures need a box to carry its own facts: a load balancer's public
front end beside its back ends, with what must never happen under both; a
worker's pods stacked inside it; a control plane drawn as a hexagon and a
customer as an ellipse. A card becomes a panel when its element carries any
of these (all in ``attributes``, so a document needs no new fields):

- ``shape``: ``ellipse``, ``hexagon`` or ``note`` (a folded corner); the
  rectangle is the card's own shape.
- ``sections``: rows of cells, each ``{"title", "lines", "tone"}``, stacked
  under the heading; the cells of one row stand side by side.
- a detail with line breaks: one detail line per line.

``tone`` names a fill that means something (render-metrics.json ``tones``;
the legend says what), on a whole card or on one cell.

Python sizes a panel once, here; the editor draws the size it is given and
lays out its inside by the same rules (14-shapes.js ``panelLayout``), from
the same numbers (render-metrics.json ``panel``), so both renderers draw the
same picture. A plain card is no panel and draws exactly as it always has.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from . import metrics

#: The shapes a card may take besides its own rectangle.
SHAPES = ("rect", "ellipse", "hexagon", "note")
#: The shapes that keep a rectangle's room inside, so compartments fit.
BOXED = ("rect", "note")

_TEXT = metrics.text()
#: Width of a character, in em, of the face every label is set in.
ADVANCE = float(_TEXT["advance"])


@dataclass(frozen=True, slots=True)
class Cell:
    """One compartment: a title and lines, on its own tone or the card's."""

    title: str = ""
    lines: tuple[str, ...] = ()
    tone: str = ""


@dataclass(frozen=True, slots=True)
class Panel:
    """What makes a card a panel; an empty one is a plain card."""

    shape: str = "rect"
    tone: str = ""
    sections: tuple[tuple[Cell, ...], ...] = ()
    #: The detail split into its lines; one line is a plain card's detail.
    detail_lines: tuple[str, ...] = ()
    #: A Box is one whatever it says: it has no artwork for a card to show.
    boxed: bool = False

    @property
    def active(self) -> bool:
        # a tone alone makes one too: the box is filled with it
        return (
            self.boxed
            or self.shape != "rect"
            or bool(self.sections)
            or len(self.detail_lines) > 1
            or bool(self.tone)
        )


def tone_names() -> tuple[str, ...]:
    return tuple(metrics.tones())


def check_tone(tone: str, where: str) -> str:
    """The tone, or a ValueError naming the ones there are."""
    if tone and tone not in metrics.tones():
        raise ValueError(f"{where}: unknown tone {tone!r}; use one of {', '.join(tone_names())}")
    return tone


def cells_of(value: Any, where: str = "sections") -> tuple[tuple[Cell, ...], ...]:
    """The rows a document's ``sections`` attribute holds, checked."""
    if not value:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise ValueError(f"{where}: a list of rows, each a list of cells")
    rows: list[tuple[Cell, ...]] = []
    for row in value:
        if not isinstance(row, Sequence) or isinstance(row, str) or not row:
            raise ValueError(f"{where}: each row is a non-empty list of cells")
        cells = []
        for cell in row:
            if not isinstance(cell, Mapping):
                raise ValueError(f"{where}: a cell is a mapping of title, lines and tone")
            lines = cell.get("lines") or ()
            if isinstance(lines, str):
                lines = (lines,)
            cells.append(
                Cell(
                    title=str(cell.get("title") or ""),
                    lines=tuple(str(line) for line in lines),
                    tone=check_tone(str(cell.get("tone") or ""), where),
                )
            )
        rows.append(tuple(cells))
    return tuple(rows)


def panel_of(attributes: Mapping[str, Any], detail: str, *, boxed: bool = False) -> Panel:
    """The panel an element's attributes describe (inactive for a plain card).

    ``boxed`` is a Box's: a panel even when it says only a name and a line.
    """
    shape = str(attributes.get("shape") or "rect")
    if shape not in SHAPES:
        raise ValueError(f"unknown shape {shape!r}; use one of {', '.join(SHAPES)}")
    sections = cells_of(attributes.get("sections"))
    if sections and shape not in BOXED:
        raise ValueError(f"a {shape} carries no compartments; only {' and '.join(BOXED)} do")
    return Panel(
        shape=shape,
        tone=check_tone(str(attributes.get("tone") or ""), "tone"),
        sections=sections,
        detail_lines=tuple(line for line in detail.split("\n")) if detail else (),
        boxed=boxed,
    )


# --------------------------------------------------------------------- sizes


def _text(text: str, size: float, advance: float | None = None) -> float:
    """How wide a line is drawn: per character, at the face's advance."""
    return len(text) * (advance if advance is not None else size * ADVANCE)


def cell_need(cell: Cell) -> float:
    """How wide a cell's own text asks it to be, in whole pixels, so its
    floored share of a row is never a fraction short of it."""
    P = metrics.panel()
    widest = max(
        [_text(cell.title, P.cell_title_size)]
        + [_text(line, 0, P.cell_advance) for line in cell.lines]
    )
    return math.ceil(widest + 2 * P.cell_pad_x)


def cell_height(cell: Cell) -> float:
    P = metrics.panel()
    return (
        2 * P.cell_pad_y + (P.cell_title_line if cell.title else 0) + len(cell.lines) * P.cell_line
    )


def row_height(row: Sequence[Cell]) -> float:
    return max(cell_height(cell) for cell in row)


def heading_height(panel: Panel) -> float:
    P = metrics.panel()
    return P.pad_top + P.title_line + len(panel.detail_lines) * P.detail_line + P.pad_bottom


def side_insets(panel: Panel) -> tuple[float, float]:
    """How much wider and taller the shape is than the room inside it."""
    P = metrics.panel()
    if panel.shape == "ellipse":
        return P.ellipse_pad, P.ellipse_pad_y
    if panel.shape == "hexagon":
        return P.hex_inset, 0.0
    return 0.0, 0.0


def icon_lane(has_icon: bool) -> float:
    P = metrics.panel()
    return P.icon_x + P.icon if has_icon else 0.0


def size(name: str, panel: Panel, has_icon: bool) -> tuple[int, int]:
    """The width and height a panel is drawn at, on the 4 px grid."""
    P = metrics.panel()
    inset_x, inset_y = side_insets(panel)
    heading = max(
        [_text(name, P.title_size)]
        + [_text(line, 0, P.detail_advance) for line in panel.detail_lines]
    )
    need = heading + 2 * (P.pad_x + icon_lane(has_icon))
    for row in panel.sections:
        need = max(need, sum(cell_need(cell) for cell in row))
    width = min(P.max_width, max(P.min_width, need + 2 * inset_x))
    height = heading_height(panel) + sum(row_height(row) for row in panel.sections) + 2 * inset_y
    return math.ceil(width / 4) * 4, math.ceil(height / 4) * 4


def cell_widths(row: Sequence[Cell], width: float) -> list[float]:
    """Each cell's share of a row ``width`` wide, by what its text needs:
    floored, the last cell taking what is left (14-shapes.js does the same)."""
    needs = [cell_need(cell) for cell in row]
    total = sum(needs)
    shares = [math.floor(need * width / total + 1e-9) for need in needs[:-1]]
    return [*shares, width - sum(shares)]


def baseline(top: float, line: float, size: float) -> float:
    """Where a line's text sits in its line box."""
    return top + line / 2 + size * 0.35


def fit(text: str, room: float, advance: float) -> str:
    """The text, cut with an ellipsis where it would overrun ``room``."""
    budget = max(1, math.floor(room / advance + 1e-9))
    return text if len(text) <= budget else text[: budget - 1] + "…"
