"""Where a wire's caption sits: the editor's placement, step for step.

Every exported picture is the editor's, and the editor places a caption by
one rule (runtime/14-shapes.js: ``automaticEdgeLabel``,
``keepEdgeLabelClearOfNodes``, ``bestAutomaticLabel``, ``resolveEdgeLabel``
and ``edgeLabelMarkup``; runtime/12-routing.js: ``alongPolyline``,
``simplePathCorners``, ``tidyCorners``). The static picture used a search of
its own and set the caption in another size, so one wire read differently
with and without a browser. This is the editor's rule in Python;
tests/integration/test_renderer_parity_browser.py holds the two pictures to
one another.

A caption starts halfway along its wire -- above a level run, beside a
vertical one -- then steps clear of the cards, the frame titles and every
caption placed before it, trying other points along the wire when a step
would carry it too far from the line it names.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, TypeVar, cast

__all__ = [
    "CAPTION_SIZE",
    "CAPTION_WEIGHT",
    "Box",
    "Placer",
    "Spot",
    "along",
    "caption_width",
    "chip",
    "simple_corners",
    "tidy",
]

#: The caption's type: the editor's ``EDGE_TEXT_DEFAULTS``. 11 px in the
#: canvas text colour reads at a glance where 9 px grey was not read;
#: regular, not medium, so a caption stays quieter than the card titles.
CAPTION_SIZE = 11.0
CAPTION_WEIGHT = 400
#: How tall a plain caption's chip is, for placement and drawing alike: its
#: type plus 5 px, never under 14 (the runtime's ``captionHeight``).
CAPTION_TALL = max(14.0, CAPTION_SIZE + 5)
#: Width per character, in em: Inter averages 0.51 and nine captions in ten
#: stay under 0.56, which this plus the chip's 10 px of padding covers.
CAPTION_ADVANCE = 0.55
#: A caption keeps clear of a node's 16 px port targets, and 8 more.
PORT_CLEARANCE = 16 + 8
#: How far a caption may be nudged and still read as sitting on its wire.
NEAR = 24
#: Port clearance is a preference: past this drift from where the caption
#: was asked for, a nearer spot clear of what is drawn wins.
DRIFT = 32
#: How far a nudge may carry a caption away from its wire (across it; along
#: it is free) and leave it reading as beside the wire (``CAPTION_BESIDE``).
BESIDE = 8
#: How far a caption's chip keeps off a frame's border line: a border through
#: the chip reads as a wire through the caption (``RAIL_KEEP``).
RAIL_KEEP = 2.0
#: The points along a wire a caption is tried at, in order.
RATIOS = (0.5, 0.3, 0.7, 0.15, 0.85, 0.4, 0.6)
SHORT_RATIOS = (0.5, 0.3, 0.7)
#: The points a caption is tried at on its own wire, when no spot beside it
#: is clear: nearest the middle first.
LINE_RATIOS = (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8, 0.15, 0.85, 0.1, 0.9)
#: How far a caption on its own wire keeps off a card.
LINE_CLEARANCE = 4
#: The farthest a caption's chip may stand from its own wire and still name
#: it; the checker holds every picture to the same number (CAPTION_REACH).
REACH = 12


class _Point(Protocol):
    # Read-only, so the router's frozen Point fits as well as any plain one.
    @property
    def x(self) -> float: ...
    @property
    def y(self) -> float: ...


#: A corner of whichever point type the caller passes; the helpers that build
#: or keep corners hand back that same type.
_P = TypeVar("_P", bound=_Point)


@dataclass(frozen=True, slots=True)
class Box:
    """Something a caption must keep clear of, as the editor measures it."""

    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class Spot:
    """Where a caption's text is anchored, and how it reads there."""

    x: float
    y: float
    #: ``middle`` above a level run, ``start`` beside a vertical one.
    anchor: str
    side: str


def _js_round(value: float) -> float:
    """``Math.round``: a half goes up, where Python's ``round`` goes to even."""
    return math.floor(value + 0.5)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def caption_width(label: str, size: float = CAPTION_SIZE) -> float:
    """``edgeLabelWidth``: the chip a caption is placed and masked by."""
    return max(24, math.ceil((len(label) * size * CAPTION_ADVANCE + 10) / 4) * 4)


def along(corners: list[_Point], ratio: float) -> tuple[float, float, bool]:
    """``alongPolyline``: the point ``ratio`` of the way along the corners,
    and whether that stretch runs level."""
    lengths = [abs(b.x - a.x) + abs(b.y - a.y) for a, b in zip(corners, corners[1:], strict=False)]
    remaining = sum(lengths) * ratio
    for index, length in enumerate(lengths):
        a, b = corners[index], corners[index + 1]
        if remaining <= length or index == len(lengths) - 1:
            t = max(0.0, min(1.0, remaining / length)) if length else 0.0
            return (a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, abs(b.x - a.x) >= abs(b.y - a.y))
        remaining -= length
    return corners[0].x, corners[0].y, True


def tidy(points: list[_P]) -> list[_P]:
    """``tidyCorners``: repeated points and corners that do not turn dropped."""
    unique = [
        point
        for index, point in enumerate(points)
        if index == 0
        or abs(point.x - points[index - 1].x) > 0.5
        or abs(point.y - points[index - 1].y) > 0.5
    ]
    if len(unique) < 3:
        return unique
    kept = [unique[0]]
    for before, corner, after in zip(unique, unique[1:], unique[2:], strict=False):
        flat_x = abs(before.x - corner.x) < 0.5 and abs(corner.x - after.x) < 0.5
        flat_y = abs(before.y - corner.y) < 0.5 and abs(corner.y - after.y) < 0.5
        if not flat_x and not flat_y:
            kept.append(corner)
    kept.append(unique[-1])
    return kept


def simple_corners(
    start: _P,
    end: _P,
    source_side: str,
    grid: float,
    point: Callable[[float, float], _P] | None = None,
) -> list[_P]:
    """``simplePathCorners``: straight, or one dog-leg through the snapped
    middle. ``point`` builds a corner (the caller's point type)."""
    # a point type is built from its x and y, which the protocol cannot say
    make = point or cast("Callable[[float, float], _P]", type(start))
    if abs(start.y - end.y) < 0.01 or abs(start.x - end.x) < 0.01:
        return [start, end]
    if source_side in ("left", "right"):
        middle = _js_round((start.x + end.x) / 2 / grid) * grid
        return [start, make(middle, start.y), make(middle, end.y), end]
    middle = _js_round((start.y + end.y) / 2 / grid) * grid
    return [start, make(start.x, middle), make(end.x, middle), end]


def chip(theme) -> tuple[str, str, str]:
    """The caption's chip, ink and edge: the editor's card, canvas text and
    border on a light canvas -- a white chip, near-black type, a thin grey
    line -- its paper, ink and a faint ink line on a dark one."""
    if getattr(theme, "dark", False):
        from .ink import rgba

        return theme["paper"], theme["ink"], rgba(theme["ink"], 0.25)
    from ..editor.tokens import canvas_tokens

    tokens = canvas_tokens("light")
    return tokens["--card-bg"], tokens["--text-canvas"], tokens["--border-color"]


def crosses(box: tuple[float, float, float, float], points: list[_Point]) -> bool:
    """Whether a wire's level or upright run passes through the box, 1 px
    in from its edges (the runtime's chipCrossesWire)."""
    x0, y0, w, h = box
    for a, b in zip(points, points[1:], strict=False):
        if (
            abs(a.y - b.y) < 0.01
            and min(a.x, b.x) < x0 + w - 1
            and max(a.x, b.x) > x0 + 1
            and y0 + 1 < a.y < y0 + h - 1
        ):
            return True
        if (
            abs(a.x - b.x) < 0.01
            and min(a.y, b.y) < y0 + h - 1
            and max(a.y, b.y) > y0 + 1
            and x0 + 1 < a.x < x0 + w - 1
        ):
            return True
    return False


def shares_run(
    point: tuple[float, float, bool], own: list[_Point], wires: list[list[_Point]]
) -> bool:
    """Whether another wire runs along the wire at this point: a level run
    through it for a level point, an upright one for an upright point (the
    runtime's sharesRun). Wires leaving one side of a card leave from its one
    point and run together before they part; a caption on that
    trunk names any of them, so it is placed where its own wire runs alone."""
    x, y, horizontal = point
    for wire in wires:
        if wire is own or [(p.x, p.y) for p in wire] == [(p.x, p.y) for p in own]:
            continue
        for a, b in zip(wire, wire[1:], strict=False):
            if (
                horizontal
                and abs(a.y - b.y) < 0.01
                and abs(a.y - y) < 0.5
                and min(a.x, b.x) - 0.5 <= x <= max(a.x, b.x) + 0.5
            ):
                return True
            if (
                not horizontal
                and abs(a.x - b.x) < 0.01
                and abs(a.x - x) < 0.5
                and min(a.y, b.y) - 0.5 <= y <= max(a.y, b.y) + 0.5
            ):
                return True
    return False


class Placer:
    """The captions of one picture, placed in wire order: each keeps clear of
    the cards, the frame titles and every caption placed before it, and
    off the frames' borders.

    ``blockers`` are in the editor's order -- the cards and glyphs in
    document order, then the frame titles -- because a caption steps off
    the first one it lands on. ``width`` and ``height`` bound the canvas a
    caption may stand on. ``rails`` are the frames' borders as lines (a box
    with no height or no width): a caption keeps ``RAIL_KEEP`` off them, not
    the port clearance a card asks for.
    """

    def __init__(
        self,
        blockers: list[Box],
        *,
        grid: float,
        width: float = math.inf,
        height: float = math.inf,
        wires: list[list[_Point]] | None = None,
        rails: list[Box] | None = None,
    ) -> None:
        self.blockers = list(blockers)
        self.rails = list(rails or [])
        self.placed: list[Box] = []
        #: Every wire's corners, as its caption is placed along them: a
        #: numbered chip is kept off all of them.
        self.wires = list(wires or [])
        self.grid = grid
        self.width, self.height = width, height

    def _snap(self, value: float) -> float:
        return _js_round(value / self.grid) * self.grid

    def automatic(
        self,
        start: _Point,
        end: _Point,
        source_side: str,
        corners: list[_Point],
        kind: str,
        source: Box,
        target: Box,
    ) -> Spot:
        """``automaticEdgeLabel``: where a caption is asked for."""
        level = abs(start.y - end.y) < 0.01
        upright = abs(start.x - end.x) < 0.01
        x, y = (start.x + end.x) / 2, start.y - 12
        anchor, side = "middle", "horizontal"
        if upright:
            x, y = start.x + 12, (start.y + end.y) / 2 + 3
            anchor, side = "start", "vertical"
        elif not level and source_side in ("left", "right"):
            x, y = self._snap((start.x + end.x) / 2) + 12, (start.y + end.y) / 2 + 3
            anchor, side = "start", "vertical"
        elif not level:
            x, y = (start.x + end.x) / 2, self._snap((start.y + end.y) / 2) - 12
        if not level and not upright and len(corners) > 2:
            spot_x, spot_y, horizontal = along(corners, 0.5)
            if horizontal:
                x, y, anchor, side = self._snap(spot_x), spot_y - 12, "middle", "horizontal"
            else:
                x, y, anchor, side = spot_x + 12, self._snap(spot_y) + 3, "start", "vertical"
        # Every kind's caption starts on its own wire: a circuit's ("vif") or a
        # tunnel's ("vpn") used to stand a fixed distance above or below the
        # cards, wherever the wire ran, and named no line.
        return Spot(x, y, anchor, side)

    def clear_of_nodes(
        self,
        width: float,
        x: float,
        y: float,
        side: str,
        clearance: float = PORT_CLEARANCE,
        lead: float = 0.0,
        tall: float = CAPTION_TALL,
    ) -> tuple[float, float, bool]:
        """``keepEdgeLabelClearOfNodes``: stepped off whatever it lands on,
        up to four times; the last value says whether it is still blocked.
        ``lead`` is how much wider the chip is than its text: a numbered
        step's circle, left of the text. Above a level run the chip reaches
        that much further left; beside a vertical wire it reaches right (the
        text moves right by it), so the circle never sits on the wire."""
        half = width / 2
        low = 4 if side == "vertical" else half + lead
        high = width - 4 + lead if side == "vertical" else half
        # the chip stands ``above`` the text's baseline and ``below`` it:
        # 11 and 3 for a plain caption, more for a numbered one's circle
        above, below = tall / 2 + 4, tall / 2 - 4
        x = _clamp(x, low, self.width - high)
        y = _clamp(y, above + 1, self.height - below - 1)
        # each blocker with the room kept around it: a card's port clearance,
        # a frame border's RAIL_KEEP
        blockers = [(box, clearance) for box in (*self.blockers, *self.placed)] + [
            (rail, RAIL_KEEP) for rail in self.rails
        ]

        def hits(px: float, py: float, blocker: tuple[Box, float]) -> bool:
            box, keep = blocker
            return (
                px + high > box.x - keep
                and px - low < box.x + box.width + keep
                and py + below > box.y - keep
                and py - above < box.y + box.height + keep
            )

        for _ in range(4):
            found = next((blocker for blocker in blockers if hits(x, y, blocker)), None)
            if found is None:
                break
            hit, keep = found
            asked_x, asked_y = x, y
            candidates = [
                (self._snap(hit.x - keep - high), y),
                (self._snap(hit.x + hit.width + keep + low), y),
                (x, self._snap(hit.y - keep - below)),
                (x, self._snap(hit.y + hit.height + keep + above)),
            ]
            scored = []
            for cx, cy in candidates:
                cx, cy = (
                    _clamp(cx, low, self.width - high),
                    _clamp(cy, above + 1, self.height - below - 1),
                )
                scored.append(
                    (
                        sum(1 for box in blockers if hits(cx, cy, box)),
                        math.hypot(cx - asked_x, cy - asked_y),
                        cx,
                        cy,
                    )
                )
            _, _, x, y = min(scored, key=lambda item: (item[0], item[1]))
        return x, y, any(hits(x, y, box) for box in blockers)

    def best(
        self,
        width: float,
        automatic: Spot,
        corners: list[_Point],
        lead: float = 0.0,
        tall: float = CAPTION_TALL,
    ) -> Spot:
        """``bestAutomaticLabel``: near the asked-for spot if that is clear,
        else the nearest clear point along the wire, asking for less room
        around the ports before settling far from the line."""

        def drift(x: float, y: float) -> float:
            return math.hypot(x - automatic.x, y - automatic.y)

        def named(x: float, y: float, side: str) -> bool:
            # the chip within REACH of its own wire (the runtime's nearOwnWire)
            left = x - 4 if side == "vertical" else x - width / 2 - lead
            top, right, bottom = y - tall / 2 - 4, left + width + lead, y + tall / 2 - 4
            for a, b in zip(corners, corners[1:], strict=False):
                dx = max(left - max(a.x, b.x), 0.0, min(a.x, b.x) - right)
                dy = max(top - max(a.y, b.y), 0.0, min(a.y, b.y) - bottom)
                if math.hypot(dx, dy) <= REACH:
                    return True
            return False

        def beside(ratio: float) -> Spot:
            x, y, horizontal = along(corners, ratio)
            return (
                Spot(x, y - 12, "middle", "horizontal")
                if horizontal
                else Spot(x + 10, y + 3, "start", "vertical")
            )

        def on_wire(ratios: tuple[float, ...], clearance: float, near: float | None) -> Spot | None:
            for ratio in ratios:
                spot = beside(ratio)
                x, y, blocked = self.clear_of_nodes(
                    width, spot.x, spot.y, spot.side, clearance, lead, tall
                )
                if not blocked and (
                    near is None
                    or (math.hypot(x - spot.x, y - spot.y) <= near and named(x, y, spot.side))
                ):
                    return Spot(x, y, spot.anchor, spot.side)
            return None

        def away(x: float, y: float, spot: Spot) -> float:
            # how far a nudge carried the caption off its wire; along it is free
            return abs(y - spot.y) if spot.side == "horizontal" else abs(x - spot.x)

        def onto(x: float, y: float, spot: Spot, left: bool = False) -> bool:
            # nudged toward its wire until the chip comes within 2 px of it:
            # the wire runs 12 px below a level caption's anchor, 10 px left
            # of a vertical one's -- or, for a chip on its left, 2 px right of
            # the chip's right edge as asked (the runtime's ontoWire)
            if spot.side == "horizontal":
                return y + tall / 2 - 4 > spot.y + 10
            if left:
                return x > spot.x
            return x - 4 < spot.x - 8

        def left_of(spot: Spot) -> Spot:
            # the same chip on the wire's other side: its right edge 6 px left
            # of the wire, as its left edge is 6 px right of it on the right
            return Spot(spot.x - 12 - width - lead, spot.y, spot.anchor, spot.side)

        def on_a_wire(x: float, y: float, side: str) -> bool:
            # a numbered chip is kept off every drawn line; a plain one keeps
            # to its placement as before
            if not lead:
                return False
            left = x - 4 if side == "vertical" else x - width / 2 - lead
            box = (left, y - tall / 2 - 4, width + lead, tall)
            return any(crosses(box, wire) for wire in self.wires)

        def beside_wire(ratios: tuple[float, ...], clearance: float) -> Spot | None:
            for ratio in ratios:
                right = beside(ratio)
                # a numbered chip with no clear spot right of a vertical wire
                # tries its left (the runtime's besideOnWire)
                sides = [(right, False)]
                if lead and right.side == "vertical":
                    sides.append((left_of(right), True))
                for spot, left in sides:
                    x, y, blocked = self.clear_of_nodes(
                        width, spot.x, spot.y, spot.side, clearance, lead, tall
                    )
                    if (
                        not blocked
                        and math.hypot(x - spot.x, y - spot.y) <= NEAR
                        and away(x, y, spot) <= BESIDE
                        and named(x, y, spot.side)
                        and not onto(x, y, spot, left)
                        and not on_a_wire(x, y, spot.side)
                    ):
                        return Spot(x, y, spot.anchor, spot.side)
            return None

        def on_line() -> Spot | None:
            # Nothing clear beside the wire: the chip centred on the wire
            # itself, breaking the line it names, where that is clear of the
            # cards, the borders and the captions before it, off every other
            # wire and off a run it shares (the runtime's onOwnWire). Read as
            # the wire's own; a caption pushed off it reads as no wire's.
            own = [(p.x, p.y) for p in corners]
            others = [wire for wire in self.wires if [(p.x, p.y) for p in wire] != own]
            # points along the wire, then the middle of each of its legs: a
            # short level leg between stacked cards has room where the long
            # run up a frame's edge has none
            points = [along(corners, ratio) for ratio in LINE_RATIOS] + [
                ((a.x + b.x) / 2, (a.y + b.y) / 2, abs(b.x - a.x) >= abs(b.y - a.y))
                for a, b in zip(corners, corners[1:], strict=False)
            ]
            for x, y, horizontal in points:
                if shares_run((x, y, horizontal), corners, self.wires):
                    continue
                # the chip's middle on the wire: it stands 4 px above the anchor
                spot = Spot(x, y + 4, "middle", "horizontal")
                nx, ny, blocked = self.clear_of_nodes(
                    width, spot.x, spot.y, spot.side, LINE_CLEARANCE, lead, tall
                )
                box = (nx - width / 2 - lead, ny - tall / 2 - 4, width + lead, tall)
                # nudged, the chip must still cover its wire's point, 2 px in
                if (
                    blocked
                    or not box[0] + 2 < x < box[0] + box[2] - 2
                    or not box[1] + 2 < y < box[1] + box[3] - 2
                ):
                    continue
                if any(crosses(box, wire) for wire in others):
                    continue
                return Spot(nx, ny, spot.anchor, spot.side)
            return None

        def near_line() -> Spot | None:
            # Still nothing: a chip a few pixels off the wire, either side of
            # it and along it, where nothing is drawn and no other wire runs
            # -- the nearest such spot, so long as it names the wire (the
            # runtime's nearOwnWireSpot). Nudged spots are not taken: each is
            # where it was asked for or not at all.
            own = [(p.x, p.y) for p in corners]
            others = [wire for wire in self.wires if [(p.x, p.y) for p in wire] != own]
            points = [along(corners, ratio) for ratio in LINE_RATIOS] + [
                ((a.x + b.x) / 2, (a.y + b.y) / 2, abs(b.x - a.x) >= abs(b.y - a.y))
                for a, b in zip(corners, corners[1:], strict=False)
            ]
            for gap in (2, 6, 10):
                for x, y, horizontal in points:
                    if horizontal:
                        middles = [
                            (x + along_by, y + side * (tall / 2 + gap))
                            for side in (-1, 1)
                            for along_by in (0.0, -width / 2, width / 2)
                        ]
                    else:
                        middles = [
                            (x + side * ((width + lead) / 2 + gap), y + along_by)
                            for side in (1, -1)
                            for along_by in (0.0, -tall, tall)
                        ]
                    for mx, my in middles:
                        ax, ay = mx + lead / 2, my + 4
                        nx, ny, blocked = self.clear_of_nodes(
                            width, ax, ay, "horizontal", LINE_CLEARANCE, lead, tall
                        )
                        if blocked or math.hypot(nx - ax, ny - ay) > 0.5:
                            continue
                        box = (nx - width / 2 - lead, ny - tall / 2 - 4, width + lead, tall)
                        if any(crosses(box, wire) for wire in others):
                            continue
                        if named(nx, ny, "horizontal"):
                            return Spot(nx, ny, "middle", "horizontal")
            return None

        first_x, first_y, first_blocked = self.clear_of_nodes(
            width, automatic.x, automatic.y, automatic.side, lead=lead, tall=tall
        )
        settled = Spot(first_x, first_y, automatic.anchor, automatic.side)
        # Where the wire runs alone, when it shares a run with another: a
        # caption there names this wire and no other.
        alone = tuple(
            ratio for ratio in RATIOS if not shares_run(along(corners, ratio), corners, self.wires)
        )
        trunk = len(alone) < len(RATIOS) and bool(alone)
        mid_alone = not trunk or not shares_run(along(corners, 0.5), corners, self.wires)
        if (
            mid_alone
            and not first_blocked
            and drift(first_x, first_y) <= NEAR
            and away(first_x, first_y, automatic) <= BESIDE
            and named(first_x, first_y, automatic.side)
            and not onto(first_x, first_y, automatic)
            and not on_a_wire(first_x, first_y, automatic.side)
        ):
            return settled
        if trunk:
            for clearance in (PORT_CLEARANCE, 8, 4):
                spot = beside_wire(alone, clearance)
                if spot is not None:
                    return spot
        # A caption beside its wire before one pushed off it: along the whole
        # wire with full port room, then its middle with less (the runtime's
        # ``besideOnWire``). 11 px captions pushed more of them off than 9 px
        # ones did, and 16 to 24 px off reads as another wire's.
        for ratios, clearance in ((RATIOS, PORT_CLEARANCE), (SHORT_RATIOS, 8), (SHORT_RATIOS, 4)):
            spot = beside_wire(ratios, clearance)
            if spot is not None:
                return spot
        first_named = named(first_x, first_y, automatic.side)
        if not first_blocked and drift(first_x, first_y) <= NEAR and first_named:
            return settled
        spot = on_wire(RATIOS, PORT_CLEARANCE, NEAR)
        if spot is not None:
            return spot
        if not first_blocked and drift(first_x, first_y) <= DRIFT and first_named:
            return settled
        for clearance in (8, 4):
            x, y, blocked = self.clear_of_nodes(
                width, automatic.x, automatic.y, automatic.side, clearance, lead, tall
            )
            if not blocked and drift(x, y) <= DRIFT and named(x, y, automatic.side):
                return Spot(x, y, automatic.anchor, automatic.side)
        for clearance in (8, 4):
            spot = on_wire(SHORT_RATIOS, clearance, NEAR)
            if spot is not None:
                return spot
        # Only a spot far off the wire is left: beside it, clear of what is
        # drawn alone, wins -- a numbered caption's 24 px chip on a 28 px hop
        # between stacked glyphs has no room for port clearance, and settled
        # a hundred pixels away on the frame's edge.
        spot = beside_wire(SHORT_RATIOS, 0) or on_line() or near_line()
        if spot is not None:
            return spot
        if not first_blocked:
            return settled
        spot = on_wire(RATIOS, PORT_CLEARANCE, None) or on_wire(SHORT_RATIOS, 0, None)
        return spot or settled

    def place(
        self,
        label: str,
        start: _Point,
        end: _Point,
        source_side: str,
        corners: list[_Point],
        kind: str,
        source: Box,
        target: Box,
        manual: tuple[float, float] | None = None,
        lead: float = 0.0,
        tall: float = CAPTION_TALL,
    ) -> Spot:
        """``resolveEdgeLabel``: a caption the author moved keeps its offset
        from the automatic spot, stepped clear of what it lands on; any other
        takes the best automatic spot. Either way it blocks the next one."""
        width = caption_width(label)
        automatic = self.automatic(start, end, source_side, corners, kind, source, target)
        if manual is not None:
            x, y, _ = self.clear_of_nodes(
                width,
                automatic.x + manual[0],
                automatic.y + manual[1],
                automatic.side,
                lead=lead,
                tall=tall,
            )
            spot = Spot(x, y, "middle", "horizontal")
        else:
            spot = self.best(width, automatic, corners, lead, tall)
        self.placed.append(
            Box(
                spot.x - 4 if spot.side == "vertical" else spot.x - width / 2 - lead,
                spot.y - tall / 2 - 4,
                width + lead,
                tall,
            )
        )
        return spot
