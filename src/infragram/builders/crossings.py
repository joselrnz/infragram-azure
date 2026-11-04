"""Small crossing bridges on final wire paths, without changing connectivity.

Horizontal wires hop upward; vertical wires are masked at the arc's crown.
Masks preserve transparent exports and do not depend on paint order or theme.
The editor's crossingPlan in 12-routing.js follows this same policy.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from . import arrowheads, metrics
from .routing import Rect

_NUMBER = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?")
_COMMAND = re.compile(r"([MLQHV])([^MLQHV]*)")


@dataclass(frozen=True)
class Segment:
    wire: int
    start: int
    end: int
    a: tuple[float, float]
    b: tuple[float, float]


def _segments(path: str, wire: int) -> list[Segment]:
    # The renderers emit absolute M/L/Q/H/V. Never reinterpret another path.
    if set(re.findall(r"[A-Za-z]", path)) - set("MLQHVeE"):
        return []
    point = (0.0, 0.0)
    segments = []
    for match in _COMMAND.finditer(path):
        values = [float(number) for number in _NUMBER.findall(match[2])]
        if not values:
            continue
        end = (
            (values[0], point[1])
            if match[1] == "H"
            else (point[0], values[0])
            if match[1] == "V"
            else (values[-2], values[-1])
        )
        if match[1] in "LHV" and (point[0] == end[0] or point[1] == end[1]):
            segments.append(Segment(wire, match.start(), match.end(), point, end))
        point = end
    return segments


def crossing_plan(
    wires: Sequence[tuple[str, float]], obstacles: Sequence[Rect] = ()
) -> tuple[list[str], dict[int, list[tuple[float, float, float]]], dict[int, int]]:
    """Paths, underpass mask circles, and bridge counts, indexed by wire.

    Only strict interior crossings count. Leave room off bends and arrowheads,
    avoid nodes/captions/frame titles, and decline crowded crossings rather
    than adding marks that touch. Unsupported and nonorthogonal paths stay put.
    """
    radius = metrics.load().router.crossing_radius
    padding = metrics.load().router.crossing_clearance
    segments = [
        segment for index, (path, _) in enumerate(wires) for segment in _segments(path, index)
    ]
    horizontal = [segment for segment in segments if segment.a[1] == segment.b[1]]
    vertical = [segment for segment in segments if segment.a[0] == segment.b[0]]
    hits: dict[Segment, list[tuple[float, float, float, int]]] = {}
    for h in horizontal:
        for v in vertical:
            if h.wire == v.wire:
                continue
            x, y = v.a[0], h.a[1]
            cut = max(2.5, (wires[h.wire][1] + wires[v.wire][1]) / 2 + 1)
            clearance = radius + max(cut + padding, arrowheads.shaft())
            if not (
                min(h.a[0], h.b[0]) + clearance < x < max(h.a[0], h.b[0]) - clearance
                and min(v.a[1], v.b[1]) + clearance < y < max(v.a[1], v.b[1]) - clearance
            ):
                continue
            reach = Rect(
                x - radius - padding,
                y - radius - cut - padding,
                x + radius + padding,
                y + cut + padding,
            )
            if reach.left < 0 or reach.top < 0:
                continue
            if any(
                reach.left < box.right
                and reach.right > box.left
                and reach.top < box.bottom
                and reach.bottom > box.top
                for box in obstacles
            ):
                continue
            # Another run in the arc's band would create a false junction.
            if any(
                s != h
                and s != v
                and (min(s.a[0], s.b[0]) < reach.right and max(s.a[0], s.b[0]) > reach.left)
                and (min(s.a[1], s.b[1]) < reach.bottom and max(s.a[1], s.b[1]) > reach.top)
                for s in segments
            ):
                continue
            hits.setdefault(h, []).append((x, y, cut, v.wire))
    paths = [path for path, _ in wires]
    masks: dict[int, list[tuple[float, float, float]]] = {}
    counts: dict[int, int] = {}
    replacements: dict[int, list[tuple[int, int, str]]] = {}
    for segment, candidates in hits.items():
        chosen: list[tuple[float, float, float, int]] = []
        for hit in sorted(candidates):
            if not chosen or hit[0] - chosen[-1][0] > 2 * (radius + hit[2] + padding):
                chosen.append(hit)
        direction = 1 if segment.b[0] > segment.a[0] else -1
        parts = []
        for x, y, cut, under in sorted(chosen, reverse=direction < 0):
            parts.append(
                f"L{x - direction * radius:g},{y:g} A{radius:g},{radius:g} 0 0 "
                f"{1 if direction > 0 else 0} {x + direction * radius:g},{y:g}"
            )
            masks.setdefault(under, []).append((x, y - radius, cut))
            counts[segment.wire] = counts.get(segment.wire, 0) + 1
        parts.append(f"L{segment.b[0]:g},{segment.b[1]:g} ")
        replacements.setdefault(segment.wire, []).append(
            (segment.start, segment.end, " ".join(parts))
        )
    for index, edits in replacements.items():
        for start, end, text in sorted(edits, reverse=True):
            paths[index] = paths[index][:start] + text + paths[index][end:]
    return paths, masks, counts
