"""What holds what, when the source only drew one shape over another.

draw.io, Excalidraw and Visio let a person lay a rectangle behind a set of
icons without making it their container. When the rectangle wholly holds
them, the person meant it as a frame, so the smallest shape that holds
another becomes its parent. Only siblings are compared: a shape the source
already placed in a container stays there.
"""

from __future__ import annotations

from .model import Shape

__all__ = ["nest_by_bounds", "snap"]

#: Shapes that can be drawn behind others as a frame.
_FRAMES = frozenset({"box", "ellipse", "cloud", "hexagon"})


def nest_by_bounds(shapes: list[Shape], slack: float = 2.0) -> None:
    """Give each shape the smallest sibling that wholly holds it as its parent;
    ``slack`` is how far past an edge still counts as inside, in the source's units."""
    siblings: dict[str | None, list[Shape]] = {}
    for shape in shapes:
        siblings.setdefault(shape.parent, []).append(shape)
    for group in siblings.values():
        # each holder with its box, so the box is known to be there
        holders = [
            (s, s.box) for s in group if s.box is not None and s.kind in _FRAMES and s.box.area > 0
        ]
        for shape in group:
            box = shape.box
            if box is None:
                continue
            around = [
                (h, held)
                for h, held in holders
                if h is not shape and held.area > box.area * 1.5 and held.holds(box, slack)
            ]
            if around:
                holder = min(around, key=lambda pair: pair[1].area)[0]
                shape.parent = holder.key
                holder.container = True


def snap(shapes: list[Shape], x: float, y: float, slack: float = 8.0) -> str | None:
    """The smallest drawn shape under a free line end, if any."""
    under = [
        (s, s.box)
        for s in shapes
        if s.box is not None and s.kind != "text" and s.box.has(x, y, slack)
    ]
    if not under:
        return None
    return min(under, key=lambda pair: pair[1].area)[0].key
