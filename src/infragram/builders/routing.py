"""Orthogonal routing that goes around node boxes instead of through them.

The naive path is H-V-H through the midpoint between two nodes. That holds
while a diagram has a handful of links and nothing in between; past that it
draws straight across unrelated services. Measured on the multi-region
example with every relationship wired: 62 segments crossing a node box.

Three pieces, each testable on its own:

- :class:`Rect`   an obstacle, and the geometry questions asked of one
- :class:`Route`  a finished corner list, and what it renders to
- :class:`Router` the search, with its costs as configurable attributes

:class:`Router` is a pydantic model held on ``Style``, so a diagram tunes
clearance or turn cost the same way it tunes any other visual decision, and
a caller can substitute a subclass that routes differently.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from . import metrics

#: Shared with the editor runtime; see builders/metrics.py.
_METRICS = metrics.router()

#: A segment within a hundredth of a pixel of a box's edge runs along it
#: rather than into it (the runtime's ``segmentBlocked``).
_ALONG = 0.01

#: A frame's border as the router sees it: ``("h", y, x0, x1)`` for a top or
#: bottom edge, ``("v", x, y0, y1)`` for a side. A wire may cross one; running
#: along it costs extra, or the wire reads as the border and the border as a
#: wire (the runtime's ``frameRails``).
Rail = tuple[str, float, float, float]

__all__ = [
    "Point",
    "Rail",
    "Rect",
    "Route",
    "Router",
    "fence_crossings",
    "nearest",
    "rail_run",
    "spread",
]


@dataclass(frozen=True)
class Point:
    """A position. Immutable so routes can be freely shared."""

    x: float
    y: float

    def toward(self, other: Point, distance: float) -> Point:
        """A point `distance` along the way to *other*, in Manhattan terms."""
        dx, dy = other.x - self.x, other.y - self.y
        span = abs(dx) + abs(dy)
        if span < 0.5 or distance <= 0:
            return self
        ratio = min(1.0, distance / span)
        return Point(self.x + dx * ratio, self.y + dy * ratio)

    def near(self, other: Point, tolerance: float = 0.5) -> bool:
        return abs(self.x - other.x) < tolerance and abs(self.y - other.y) < tolerance


@dataclass(frozen=True)
class Rect:
    """An obstacle the router must not enter."""

    left: float
    top: float
    right: float
    bottom: float

    @classmethod
    def around(cls, node) -> Rect:
        """The box a placed Node occupies."""
        return cls(node.x, node.y, node.x + (node.width or 0), node.y + (node.height or 0))

    def inflate(self, by: float) -> Rect:
        return Rect(self.left - by, self.top - by, self.right + by, self.bottom + by)

    def contains(self, point: Point) -> bool:
        """Whether a point is strictly inside the box, excluding its border."""
        return self.left < point.x < self.right and self.top < point.y < self.bottom

    def blocks(self, start: Point, end: Point) -> bool:
        """Does the axis-aligned segment enter this rect?

        The runtime's ``segmentBlocked``, test for test: a segment within a
        hundredth of a pixel of an edge runs along it, which is what lets a
        path leave and arrive at a node, and anything not level is read as
        upright.
        """
        eps = _ALONG
        if abs(start.y - end.y) < eps:
            lo, hi = (start.x, end.x) if start.x <= end.x else (end.x, start.x)
            return (
                self.top + eps < start.y < self.bottom - eps
                and hi > self.left + eps
                and lo < self.right - eps
            )
        lo, hi = (start.y, end.y) if start.y <= end.y else (end.y, start.y)
        return (
            self.left + eps < start.x < self.right - eps
            and hi > self.top + eps
            and lo < self.bottom - eps
        )

    @property
    def edges_x(self) -> tuple[float, float]:
        """The lanes this box offers: its own edges. A caller passes boxes
        already inflated by the clearance, and a wire may run along an
        edge (``blocks`` is strict), which is where the runtime's
        ``routeCorners`` lays its lanes too."""
        return self.left, self.right

    @property
    def edges_y(self) -> tuple[float, float]:
        return self.top, self.bottom


@dataclass(frozen=True)
class Route:
    """A finished path, as the corners it turns at."""

    corners: tuple[Point, ...]
    #: The sides of the source and the target the wire leaves and arrives
    #: at, so each end can be seated on its drawing along that side.
    sides: tuple[str, str] | None = None
    #: A plain path -- straight, or one dog-leg through the middle -- whose
    #: middle is derived again from the seated ends when it is drawn, the
    #: way the runtime's ``routedPath`` draws it; a searched route keeps its
    #: corners and only its ends move.
    plain: bool = False
    #: Shaped by hand or laned beside its twin: its corners are the author's
    #: or the lane's, and lane spreading (``spread``) leaves them alone.
    shaped: bool = False

    def __len__(self) -> int:
        return len(self.corners)

    def crossings(self, obstacles: Iterable[Rect]) -> int:
        """How many segments enter an obstacle. Zero is the point."""
        boxes = list(obstacles)
        return sum(
            1
            for a, b in zip(self.corners, self.corners[1:], strict=False)
            if any(box.blocks(a, b) for box in boxes)
        )

    def to_path(
        self,
        radius: float = _METRICS["radius"],
        shaft: float = 0.0,
        heads: tuple[bool, bool] = (False, True),
        tip_clear: float = 0.0,
    ) -> str:
        """An SVG path with softened corners, matching the house style.

        ``shaft`` is the straight run an arrowhead needs under it; the corner
        next to a headed end (``heads`` = start, end) gives up its rounding
        before it gives up the shaft, so a bend never runs into the head.
        ``tip_clear`` pulls a headed end that far back from its anchor, so
        the stroke never pokes out of the head's point.
        """
        if len(self.corners) < 2:
            return ""
        corners = list(self.corners)
        if tip_clear > 0:

            def span(a: Point, b: Point) -> float:
                return abs(a.x - b.x) + abs(a.y - b.y)

            if heads[1] and span(corners[-1], corners[-2]) > tip_clear + 1:
                corners[-1] = corners[-1].toward(corners[-2], tip_clear)
            if heads[0] and span(corners[0], corners[1]) > tip_clear + 1:
                corners[0] = corners[0].toward(corners[1], tip_clear)
        parts = [f"M{corners[0].x:g},{corners[0].y:g}"]
        last_corner = len(corners) - 2
        for index, (before, corner, after) in enumerate(
            zip(corners, corners[1:], corners[2:], strict=False), start=1
        ):
            leg_in = max(abs(corner.x - before.x), abs(corner.y - before.y))
            leg_out = max(abs(after.x - corner.x), abs(after.y - corner.y))
            reach = min(radius, leg_in / 2, leg_out / 2)
            if heads[1] and index == last_corner:
                reach = min(reach, max(0.0, leg_out - shaft))
            if heads[0] and index == 1:
                reach = min(reach, max(0.0, leg_in - shaft))
            if reach <= 0:
                parts.append(f"L{corner.x:g},{corner.y:g}")
                continue
            enter, leave = corner.toward(before, reach), corner.toward(after, reach)
            parts.append(f"L{enter.x:g},{enter.y:g}")
            parts.append(f"Q{corner.x:g},{corner.y:g} {leave.x:g},{leave.y:g}")
        last = corners[-1]
        parts.append(f"L{last.x:g},{last.y:g}")
        return " ".join(parts)


_OUTWARD = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}


def nearest(boxes: Sequence[Rect], start: Point, end: Point, cap: int) -> Sequence[Rect]:
    """The ``cap`` obstacles nearest the span between two points, by their
    Manhattan distance to its bounding box; the same list when it fits.

    What the editor runtime does (``nearestObstacles``): a search over a few
    dozen boxes is cheap, one over every card on a busy canvas is not, and
    the boxes far from the span never shape the route. A caller compares the
    result to ``boxes`` by identity to tell whether it was cut.
    """
    if len(boxes) <= cap:
        return boxes
    left, right = min(start.x, end.x), max(start.x, end.x)
    top, bottom = min(start.y, end.y), max(start.y, end.y)

    def distance(box: Rect) -> float:
        return (
            max(0.0, box.left - right)
            + max(0.0, left - box.right)
            + max(0.0, box.top - bottom)
            + max(0.0, top - box.bottom)
        )

    return sorted(boxes, key=distance)[:cap]


def rail_run(rails: Sequence[Rail], band: float, a: Point, b: Point) -> float:
    """How far the segment runs along the rails, within ``band`` of them
    (the runtime's ``railRun``): every rail's overlap, added in order."""
    run = 0.0
    if abs(a.y - b.y) < _ALONG:
        lo, hi = min(a.x, b.x), max(a.x, b.x)
        for axis, at, low, high in rails:
            if axis == "h" and abs(a.y - at) <= band:
                run += max(0.0, min(hi, high) - max(lo, low))
    elif abs(a.x - b.x) < _ALONG:
        lo, hi = min(a.y, b.y), max(a.y, b.y)
        for axis, at, low, high in rails:
            if axis == "v" and abs(a.x - at) <= band:
                run += max(0.0, min(hi, high) - max(lo, low))
    return run


def fence_crossings(fences: Sequence[Rect], a: Point, b: Point) -> int:
    """How many fence borders the segment crosses (the runtime's
    ``fenceCrossings``).

    A fence is a frame that holds neither end of the wire: a wire may cross
    its border, but each crossing costs, or it runs through a group it has
    nothing to do with. A crossing counts where the border lies past the
    segment's low end and up to its high end, so a route that stops on a
    border and goes on counts it once.
    """
    count = 0
    if abs(a.y - b.y) < _ALONG:
        lo, hi = min(a.x, b.x), max(a.x, b.x)
        for fence in fences:
            if fence.top < a.y < fence.bottom:
                count += (lo < fence.left <= hi) + (lo < fence.right <= hi)
    elif abs(a.x - b.x) < _ALONG:
        lo, hi = min(a.y, b.y), max(a.y, b.y)
        for fence in fences:
            if fence.left < a.x < fence.right:
                count += (lo < fence.top <= hi) + (lo < fence.bottom <= hi)
    return count


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def _entered(wire: Sequence[Point], boxes: Sequence[Rect]) -> int:
    """How many (segment, box) pairs of a wire cross into a box."""
    return sum(1 for a, b in zip(wire, wire[1:], strict=False) for box in boxes if box.blocks(a, b))


def _turn(run: tuple[str, float, float, float, int, int], out: list[list[Point] | None]) -> int:
    """Which way a run's wire turns at both its ends, -2 to 2: the lower way
    first, so a group's wires take lanes in an order where they do not cross."""
    axis, line, _, _, w, k = run
    wire = out[w]
    assert wire is not None
    if axis == "v":
        return _sign(wire[k - 1].x - line) + _sign(wire[k + 2].x - line)
    return _sign(wire[k - 1].y - line) + _sign(wire[k + 2].y - line)


def spread(
    wires: Sequence[Sequence[Point] | None],
    boxes: Sequence[Rect],
    rails: Sequence[Rail],
    *,
    gap: float,
    least: float,
    end: float,
    reach: float,
    band: float,
) -> list[tuple[Point, ...] | None]:
    """Wires that run along one line, drawn apart (the runtime's ``spreadWires``).

    Two routes that take the same lane draw one on top of the other, and the
    reader sees one wire where there are two -- or three, up a frame's edge
    beside a column of cards. Every run of a wire but its first and last
    (those meet its cards) is matched against the other wires' runs; runs on
    one line that overlap form a group, and the group is spread ``gap``
    apart across the room the cards (``boxes``) and the frames' borders
    (``rails``) leave either side of the line, within ``reach`` of it --
    closer when the room is narrow, and not at all below ``least``. Wires
    whose ends turn the lower way take the lower lanes, so they do not cross
    in the group. A run alone is moved too when it lies within ``band`` of
    a frame's border, off it to the roomier side. Moving a level run moves only its ends' y and an upright
    run only their x, so the groups apply one after another in any order; a
    group is left as it was if a moved wire would enter a box or leave a
    card along a leg shorter than ``end``. ``None`` stands for a wire that is
    not spread (shaped by hand) and comes back as ``None``.
    """
    out: list[list[Point] | None] = [None if wire is None else list(wire) for wire in wires]
    runs: list[tuple[str, float, float, float, int, int]] = []
    for index, wire in enumerate(out):
        if wire is None:
            continue
        for k in range(1, len(wire) - 2):
            a, b = wire[k], wire[k + 1]
            if abs(a.y - b.y) < _ALONG and abs(a.x - b.x) >= 1:
                runs.append(("h", a.y, min(a.x, b.x), max(a.x, b.x), index, k))
            elif abs(a.x - b.x) < _ALONG and abs(a.y - b.y) >= 1:
                runs.append(("v", a.x, min(a.y, b.y), max(a.y, b.y), index, k))

    # one line, overlapping by more than a pixel, two wires: one group
    root = list(range(len(runs)))

    def top(i: int) -> int:
        while root[i] != i:
            i = root[i]
        return i

    for p, one in enumerate(runs):
        for q in range(p + 1, len(runs)):
            other = runs[q]
            if (
                one[0] == other[0]
                and one[4] != other[4]
                and abs(one[1] - other[1]) < 0.5
                and min(one[3], other[3]) - max(one[2], other[2]) > 1
            ):
                first_root, second_root = top(p), top(q)
                if first_root != second_root:
                    root[max(first_root, second_root)] = min(first_root, second_root)
    groups: dict[int, list[int]] = {}
    for i in range(len(runs)):
        groups.setdefault(top(i), []).append(i)

    for members in groups.values():
        axis, at = runs[members[0]][0], runs[members[0]][1]
        lo = min(runs[i][2] for i in members)
        hi = max(runs[i][3] for i in members)
        low, high = at - reach, at + reach
        for box in boxes:
            if axis == "v" and box.bottom > lo and box.top < hi:
                if box.right <= at:
                    low = max(low, box.right)
                elif box.left >= at:
                    high = min(high, box.left)
            elif axis == "h" and box.right > lo and box.left < hi:
                if box.bottom <= at:
                    low = max(low, box.bottom)
                elif box.top >= at:
                    high = min(high, box.top)
        hugged = False
        under: list[float] = []
        for kind, line, start, stop in rails:
            if kind == axis and stop > lo and start < hi:
                hugged = hugged or abs(line - at) <= band
                if abs(line - at) < 0.5:
                    under.append(line)
                elif line < at:
                    low = max(low, line)
                else:
                    high = min(high, line)
        if len({runs[i][4] for i in members}) < 2 and not hugged:
            continue
        # a border right under the run bounds the side with less room
        for line in under:
            if high - at >= at - low:
                low = max(low, line)
            else:
                high = min(high, line)
        count = len(members)
        step = min(gap, (high - low) / (count + 1))
        if step < least:
            continue

        ordered = sorted(members, key=lambda i: (_turn(runs[i], out), i))
        first = at - step * (count - 1) / 2
        last = first + step * (count - 1)
        shift = 0.0
        if first < low + step:
            shift = low + step - first
        elif last > high - step:
            shift = high - step - last
        moved: dict[int, list[Point]] = {}
        fits = True
        for j, i in enumerate(ordered):
            _, _, _, _, w, k = runs[i]
            wire = moved.get(w) or list(out[w] or [])
            place = first + step * j + shift
            for n in (k, k + 1):
                point = wire[n]
                wire[n] = Point(place, point.y) if axis == "v" else Point(point.x, place)
            moved[w] = wire
        for w, wire in moved.items():
            was = out[w]
            assert was is not None
            for a, b, c, d in (
                (wire[0], wire[1], was[0], was[1]),
                (wire[-1], wire[-2], was[-1], was[-2]),
            ):
                if (
                    abs(b.x - a.x) + abs(b.y - a.y) < end
                    or _sign(b.x - a.x) != _sign(d.x - c.x)
                    or _sign(b.y - a.y) != _sign(d.y - c.y)
                ):
                    fits = False
            if _entered(wire, boxes) > _entered(was, boxes):
                fits = False
        if fits:
            for w, wire in moved.items():
                out[w] = wire
    return [None if wire is None else Router._tidy(wire) for wire in out]


def outward(point: Point, side: str, distance: float) -> Point:
    """The point ``distance`` straight out of ``side`` from an anchor."""
    dx, dy = _OUTWARD[side]
    return Point(point.x + dx * distance, point.y + dy * distance)


#: How many entries a search may pop before it gives up (the runtime's guard).
_SEARCH_GUARD = 40000


class _Heap:
    """The runtime's binary heap in ``routeCorners``, entry for entry.

    Ordered by the first field alone and sifted exactly as the runtime sifts,
    so two routes of equal cost leave it in the same order in both renderers.
    ``heapq`` breaks such ties on the fields after the first -- the cost so
    far, then the cell -- and the static picture took the detour over a card
    where the export took the one under it.
    """

    __slots__ = ("items",)

    def __init__(self, first: tuple) -> None:
        self.items = [first]

    def __bool__(self) -> bool:
        return bool(self.items)

    def push(self, entry: tuple) -> None:
        items = self.items
        items.append(entry)
        i = len(items) - 1
        while i > 0:
            parent = (i - 1) >> 1
            if items[parent][0] <= items[i][0]:
                break
            items[parent], items[i] = items[i], items[parent]
            i = parent

    def pop(self) -> tuple:
        items = self.items
        top = items[0]
        last = items.pop()
        if items:
            items[0] = last
            i = 0
            while True:
                left = i * 2 + 1
                right = left + 1
                small = i
                if left < len(items) and items[left][0] < items[small][0]:
                    small = left
                if right < len(items) and items[right][0] < items[small][0]:
                    small = right
                if small == i:
                    break
                items[small], items[i] = items[i], items[small]
                i = small
        return top


class Router(BaseModel):
    """Searches for an orthogonal path that avoids every obstacle.

    Lanes are drawn from the obstacle edges -- the only coordinates a
    shortest orthogonal path ever turns at -- which keeps the grid small
    and the search complete.
    """

    #: How far a path stays clear of a box.
    clearance: float = _METRICS["clearance"]
    #: How far outside the content a detour may travel when boxed in.
    margin: float = _METRICS["margin"]
    #: Added cost per corner, in pixels. This is what stops the search
    #: stair-stepping across open space instead of running straight.
    turn_cost: float = _METRICS["turn_cost"]
    #: Corner softening on the emitted path.
    radius: float = _METRICS["radius"]
    #: How far a wire runs straight out of its side before it may turn:
    #: room for an arrowhead and its shaft. Beside a neighbour that close
    #: the stub shortens to the clearance, which still fits one gap away.
    stub: float = _METRICS["stub"]
    #: How near a frame's border a segment runs along it, and what each pixel
    #: of such a run costs on top of its length.
    rail: float = _METRICS.get("rail", 4.0)
    rail_cost: float = _METRICS.get("rail_cost", 3.0)
    #: What crossing the border of a frame that holds neither end costs, on
    #: top of the step's length: a wire goes around a group it has nothing to
    #: do with when the way around is not much longer.
    cross_cost: float = _METRICS.get("cross_cost", 0.0)

    def path(self, start: Point, end: Point, obstacles: Sequence[Rect], fallback: str = "") -> str:
        """Route and render in one call, falling back when no route exists.

        A link is never silently dropped: if the search fails, the caller's
        direct path is used instead.
        """
        route = self.route(start, end, obstacles)
        if route is None or len(route) < 2:
            return fallback
        return route.to_path(self.radius) or fallback

    def route(
        self, start: Point, end: Point, obstacles: Sequence[Rect], hard: Sequence[Rect] = ()
    ) -> Route | None:
        """Route public anchor coordinates with the shared prepared search."""
        return self.route_prepared(
            start, end, [box.inflate(self.clearance) for box in obstacles], hard
        )

    def route_between_sides(
        self,
        start: Point,
        start_side: str,
        end: Point,
        end_side: str,
        obstacles: Sequence[Rect],
        hard: Sequence[Rect] = (),
    ) -> Route | None:
        """Route from one anchor to another so the wire leaves its side
        straight out and arrives straight in (ADR 0006, rule 8).

        The search runs between a point one stub outside either anchor and
        the anchors are spliced back on, which makes the first and last
        segments perpendicular to the sides they touch: a wire can never
        slide along a glyph's or a card's border to get in.
        """
        boxes = [*(box.inflate(self.clearance) for box in obstacles), *hard]

        def stub_point(point: Point, side: str) -> Point:
            full = outward(point, side, self.stub)
            if any(box.contains(full) for box in boxes):
                return outward(point, side, self.clearance)
            return full

        def strip(anchor: Point, stub: Point) -> Rect:
            # The strip between an anchor and its stub is hard too, so the
            # search reaches the stub only from outside and the spliced stub
            # never folds back into a one-pixel leg under the head. It stops
            # a pixel short of the stub point, which stays free; hard boxes
            # add no lanes.
            short = stub.toward(anchor, 1.0)
            return Rect(
                min(anchor.x, short.x) - 0.25,
                min(anchor.y, short.y) - 0.25,
                max(anchor.x, short.x) + 0.25,
                max(anchor.y, short.y) + 0.25,
            )

        a, b = stub_point(start, start_side), stub_point(end, end_side)
        routed = self.route(a, b, obstacles, [*hard, strip(start, a), strip(end, b)])
        if routed is None:
            return None
        return Route(self._tidy([start, *routed.corners, end]))

    def route_prepared(
        self,
        start: Point,
        end: Point,
        boxes: Sequence[Rect],
        walls: Sequence[Rect] = (),
        rails: Sequence[Rail] = (),
        fences: Sequence[Rect] = (),
    ) -> Route | None:
        """The corner list between two stub points over boxes the caller
        prepared: every box is used as it comes, for lanes and for blocking,
        and ``walls`` block without adding lanes. This is the search the
        editor runtime runs (``routeCorners``); the renderer (``render.py``,
        ``_route_uncached``) inflates the boxes, places the stubs and walls
        and splices the anchors back on. ``rails`` are the frames' borders:
        a step along one is charged ``rail_cost`` per pixel on top. ``fences``
        are the frames that hold neither end: a step across a border of one
        is charged ``cross_cost`` on top (:func:`fence_crossings`), and each
        that overlaps the span between the two points offers lanes one and two
        clearances outside every border, so the way around it stays beside it
        rather than out past everything."""
        left, right = min(start.x, end.x), max(start.x, end.x)
        top, bottom = min(start.y, end.y), max(start.y, end.y)
        beside = [
            fence
            for fence in fences
            if fence.left <= right
            and fence.right >= left
            and fence.top <= bottom
            and fence.bottom >= top
        ]
        xs, ys = self._lanes(boxes, (start, end), beside)
        if not xs or not ys:
            return None
        blocking = [*boxes, *walls]

        def cell_of(point: Point) -> tuple[int, int]:
            col = min(range(len(xs)), key=lambda i: abs(xs[i] - point.x))
            row = min(range(len(ys)), key=lambda i: abs(ys[i] - point.y))
            return col, row

        source, target = cell_of(start), cell_of(end)
        if source == target:
            return Route((start, end))
        corners = self._search(source, target, xs, ys, blocking, rails, fences)
        if corners is None:
            return None
        return Route(self._tidy([start, *corners, end]))

    # -- internals ------------------------------------------------------
    def _lanes(
        self, boxes: Sequence[Rect], anchors: Sequence[Point], fences: Sequence[Rect] = ()
    ) -> tuple[list[float], list[float]]:
        """Candidate x and y values: every box's edges, plus the anchors, plus
        one and two clearances outside each fence (one may fall on a
        neighbour's border), plus one lane a margin outside everything -- the grid the runtime's ``routeCorners`` lays, value for
        value."""
        xs = {p.x for p in anchors}
        ys = {p.y for p in anchors}
        for box in boxes:
            xs.update(box.edges_x)
            ys.update(box.edges_y)
        for fence in fences:
            for gap in (self.clearance, 2 * self.clearance):
                xs.update((fence.left - gap, fence.right + gap))
                ys.update((fence.top - gap, fence.bottom + gap))
        lanes_x, lanes_y = sorted(xs), sorted(ys)
        if lanes_x and lanes_y:
            lanes_x = [lanes_x[0] - self.margin, *lanes_x, lanes_x[-1] + self.margin]
            lanes_y = [lanes_y[0] - self.margin, *lanes_y, lanes_y[-1] + self.margin]
        return lanes_x, lanes_y

    def _search(
        self,
        source: tuple[int, int],
        target: tuple[int, int],
        xs: list[float],
        ys: list[float],
        boxes: Sequence[Rect],
        rails: Sequence[Rail] = (),
        fences: Sequence[Rect] = (),
    ) -> list[Point] | None:
        """A* over the lane grid. State carries the arrival axis, so a
        change of direction can be charged for."""

        def at(cell: tuple[int, int]) -> Point:
            return Point(xs[cell[0]], ys[cell[1]])

        goal = at(target)

        def remaining(cell: tuple[int, int]) -> float:
            here = at(cell)
            return abs(here.x - goal.x) + abs(here.y - goal.y)

        # A box can block a level step only if the step's lane runs strictly
        # inside the box's height, and an upright one only if its lane runs
        # strictly inside the box's width: the first test of each branch of
        # ``Rect.blocks``, made once per lane here instead of once per step.
        # A step then asks only the boxes its lane crosses, and gets the
        # answer asking all of them would give.
        across_row = [
            [box for box in boxes if box.top + _ALONG < y < box.bottom - _ALONG] for y in ys
        ]
        across_col = [
            [box for box in boxes if box.left + _ALONG < x < box.right - _ALONG] for x in xs
        ]

        # The borders each lane runs along, as (from, to) spans: a level step
        # pays for its overlap with the level ones near its row, an upright
        # step for the upright ones near its column.
        band = self.rail
        along_row = [
            [(low, high) for axis, at, low, high in rails if axis == "h" and abs(y - at) <= band]
            for y in ys
        ]
        along_col = [
            [(low, high) for axis, at, low, high in rails if axis == "v" and abs(x - at) <= band]
            for x in xs
        ]

        # The fence borders each lane crosses: a level step the sides of the
        # fences across its row, an upright step the tops and bottoms of those
        # across its column, by where they lie.
        fence_row = [
            [at for fence in fences if fence.top < y < fence.bottom for at in fence.edges_x]
            for y in ys
        ]
        fence_col = [
            [at for fence in fences if fence.left < x < fence.right for at in fence.edges_y]
            for x in xs
        ]

        start_state = (source, "")
        best: dict[tuple[tuple[int, int], str], float] = {start_state: 0.0}
        came: dict[tuple[tuple[int, int], str], tuple] = {}
        queue = _Heap((remaining(source), 0.0, start_state))

        # The runtime's loop, step for step: a stale entry is dropped before
        # the goal is recognised, the steps are tried right, left, down, up,
        # and the search gives up after as many pops as the runtime allows.
        # Ties between routes of equal cost come out of the heap in the same
        # order, so both renderers draw the same one of them.
        guard = _SEARCH_GUARD
        while queue and guard > 0:
            guard -= 1
            _, spent, state = queue.pop()
            if spent > best.get(state, float("inf")):
                continue
            cell, axis = state
            if cell == target:
                trail = [at(cell)]
                while state in came:
                    state = came[state]
                    trail.append(at(state[0]))
                trail.reverse()
                return trail

            col, row = cell
            for dcol, drow, moved in ((1, 0, "h"), (-1, 0, "h"), (0, 1, "v"), (0, -1, "v")):
                ncol, nrow = col + dcol, row + drow
                if not (0 <= ncol < len(xs) and 0 <= nrow < len(ys)):
                    continue
                here, there = at(cell), Point(xs[ncol], ys[nrow])
                crossed = across_row[row] if abs(here.y - there.y) < _ALONG else across_col[col]
                if any(box.blocks(here, there) for box in crossed):
                    continue
                run = 0.0
                fenced = 0
                if moved == "h":
                    lo, hi = min(here.x, there.x), max(here.x, there.x)
                    for low, high in along_row[row]:
                        run += max(0.0, min(hi, high) - max(lo, low))
                    fenced = sum(1 for at in fence_row[row] if lo < at <= hi)
                else:
                    lo, hi = min(here.y, there.y), max(here.y, there.y)
                    for low, high in along_col[col]:
                        run += max(0.0, min(hi, high) - max(lo, low))
                    fenced = sum(1 for at in fence_col[col] if lo < at <= hi)
                # Added in the runtime's order, so the float sums agree to
                # the last bit and a near-tie cannot tip the other way.
                cost = (
                    spent
                    + abs(there.x - here.x)
                    + abs(there.y - here.y)
                    + (self.turn_cost if axis and axis != moved else 0.0)
                    + run * self.rail_cost
                    + fenced * self.cross_cost
                )
                nxt = ((ncol, nrow), moved)
                if cost < best.get(nxt, float("inf")):
                    best[nxt] = cost
                    came[nxt] = state
                    queue.push((cost + remaining((ncol, nrow)), cost, nxt))
        return None

    @staticmethod
    def _tidy(points: Sequence[Point]) -> tuple[Point, ...]:
        """Drop repeats, then collapse runs that continue along one axis."""
        unique: list[Point] = []
        for point in points:
            if unique and unique[-1].near(point):
                continue
            unique.append(point)
        if len(unique) < 3:
            return tuple(unique)

        kept = [unique[0]]
        for before, corner, after in zip(unique, unique[1:], unique[2:], strict=False):
            flat_x = abs(before.x - corner.x) < 0.5 and abs(corner.x - after.x) < 0.5
            flat_y = abs(before.y - corner.y) < 0.5 and abs(corner.y - after.y) < 0.5
            if not (flat_x or flat_y):
                kept.append(corner)
        kept.append(unique[-1])
        return tuple(kept)
