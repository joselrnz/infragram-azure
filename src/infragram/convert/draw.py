"""A sketch into a drawing: frames, cards and wires the diagram file writes.

- A shape that holds drawn shapes is a frame (:func:`.match.match_frame`);
  one without a label holds nothing a person named, so its shapes move up
  to its own parent. A text shape inside an unlabelled one is its label.
- Every other shape is a card (:func:`.match.match_component`); an
  unlabelled plain shape nothing links to is decoration and is left out,
  as is text standing on its own.
- A line is a wire when both its ends are drawn; its label, dash and
  arrowheads come along. Two lines saying the same thing are one wire.

Nothing is placed: the composer lays the picture out, as it does every
diagram file, and the report says where every shape went.
"""

from __future__ import annotations

from collections import Counter

from ..estate.draw import BOX, Box, Card, Drawing, Wire
from .match import match_component, match_frame, name_of, providers_named
from .model import Shape, Sketch

__all__ = ["draw_sketch"]

_DIRECTIONS = {"row": "right", "column": "down"}


class _Drawer:
    def __init__(self, sketch: Sketch) -> None:
        self.sketch = sketch
        self.shapes = {shape.key: shape for shape in sketch.shapes}
        self.children: dict[str | None, list[Shape]] = {}
        for shape in sketch.shapes:
            parent = (
                shape.parent if shape.parent in self.shapes and shape.parent != shape.key else None
            )
            # a parent chain that loops is cut where it closes
            seen, cursor = {shape.key}, parent
            while cursor is not None:
                if cursor in seen:
                    parent = None
                    break
                seen.add(cursor)
                nxt = self.shapes[cursor].parent
                cursor = nxt if nxt in self.shapes else None
            shape.parent = parent
            self.children.setdefault(parent, []).append(shape)
        self.linked = {link.source for link in sketch.links} | {
            link.target for link in sketch.links
        }
        self.preferred = providers_named(sketch.shapes)
        self.drawing = Drawing(
            sketch.title,
            sketch.origin,
            [],
            [],
            notes=list(sketch.notes),
            thing="shape",
            direction=_DIRECTIONS.get(sketch.flow or ""),
        )
        #: a shape's key -> the key of the element it is drawn as
        self.drawn_as: dict[str, str] = {}

    def where(self, shape: Shape) -> str:
        name = shape.label or shape.kind
        return f"{name} [{shape.source or shape.key}]"

    def build(self, shape: Shape) -> list[Box | Card]:
        kids = self.children.get(shape.key, [])
        texts = [kid for kid in kids if kid.kind == "text" and not self.children.get(kid.key)]
        drawn_kids = [kid for kid in kids if kid not in texts]
        if not shape.label and texts:
            first = min(texts, key=lambda t: (t.box.y, t.box.x) if t.box else (0.0, 0.0))
            shape.label, shape.detail = first.label, shape.detail or first.detail
            texts.remove(first)
            self.drawing.folded[self.where(first)] = f"the label of {shape.label}"
            self.drawn_as[first.key] = shape.key
        for text in texts:
            if text.key in self.linked:
                drawn_kids.append(text)
            else:
                self.drawing.left_out[self.where(text)] = (
                    "text on its own: an annotation, not a component"
                )
        if drawn_kids:
            items = [item for kid in drawn_kids for item in self.build(kid)]
            if not items:
                return self.card(shape)
            if not shape.label:
                self.drawing.folded[self.where(shape)] = (
                    "an unlabelled group: its shapes are drawn in its place"
                )
                return items
            inside: Counter[str] = Counter()
            for item in items:
                self._libraries(item, inside)
            frame = match_frame(shape, inside, self.preferred)
            box = Box(
                key=shape.key,
                library=frame.library,
                kind=frame.kind,
                caption=shape.label,
                children=items,
                flow=shape.flow,
            )
            self.drawn_as[shape.key] = shape.key
            what = f"{frame.library} {frame.kind} frame" if frame.library else "a plain group"
            self.drawing.drawn[self.where(shape)] = f"{what} (by {frame.how})"
            return [box]
        if shape.kind == "text" and shape.key not in self.linked:
            self.drawing.left_out[self.where(shape)] = (
                "text on its own: an annotation, not a component"
            )
            return []
        return self.card(shape)

    def _libraries(self, item: Box | Card, counts: Counter[str]) -> None:
        if isinstance(item, Card):
            counts[item.library] += 1
        else:
            if item.library and item.library != "generic":
                counts[item.library] += 1
            for child in item.children:
                self._libraries(child, counts)

    def card(self, shape: Shape) -> list[Box | Card]:
        if (
            not shape.label
            and not shape.hints
            and shape.key not in self.linked
            and shape.kind in ("box", "ellipse", "diamond", "hexagon", "text", "image")
        ):
            self.drawing.left_out[self.where(shape)] = (
                "an unlabelled shape nothing links to: decoration"
            )
            return []
        match = match_component(shape, self.preferred)
        # A shape drawn as a panel (a fill, an outline, lines of its own) that
        # names no product is a plain Box: a guessed vendor icon in its corner
        # would claim what the source never said.
        if match.generic and (shape.outline or shape.tone or "\n" in shape.detail):
            match = match.model_copy(
                update={
                    "library": "infragram",
                    "service_id": BOX,
                    "how": f"{match.how}; drawn as a plain box, as the source drew it",
                }
            )
        caption = shape.label or (
            shape.key if match.service_id == BOX else name_of(match.library, match.service_id)
        )
        rows = [
            (
                "Drawn from",
                f"{self.sketch.origin}: {shape.source}" if shape.source else self.sketch.origin,
            ),
            ("Matched by", match.how),
            *shape.rows,
        ]
        self.drawn_as[shape.key] = shape.key
        self.drawing.drawn[self.where(shape)] = (
            f"{match.library}:{match.service_id} (by {match.how})"
        )
        if match.generic:
            self.drawing.unmapped[f"{caption} -> {match.service_id}"] += 1
        return [
            Card(
                key=shape.key,
                library=match.library,
                service_id=match.service_id,
                caption=caption,
                detail=shape.detail,
                rows=[(k, v) for k, v in rows if v],
                shape=shape.outline,
                tone=shape.tone,
            )
        ]

    def run(self) -> Drawing:
        for shape in self.children.get(None, []):
            self.drawing.roots += self.build(shape)
        seen: set[tuple[str, str, str, str]] = set()
        for link in self.sketch.links:
            source, target = self.drawn_as.get(link.source), self.drawn_as.get(link.target)
            what = f"the line {link.origin or ''} {link.source} -> {link.target}".replace("  ", " ")
            if source is None or target is None:
                missing = link.source if source is None else link.target
                self.drawing.notes.append(
                    f"{what}: {missing!r} is not drawn, so neither is the line"
                )
                continue
            if source == target:
                continue
            key = (source, target, link.label, link.direction)
            if key in seen:
                continue
            seen.add(key)
            self.drawing.wires.append(
                Wire(
                    source,
                    target,
                    link.label,
                    link.dashed,
                    both=link.direction == "both",
                    plain=link.direction == "none",
                )
            )
        # the legend names the tones the drawing wears, as the source names them
        worn = {item.tone for item in self.drawing.walk() if isinstance(item, Card)}
        self.drawing.tones = {
            tone: meaning for tone, meaning in self.sketch.tones.items() if tone in worn
        }
        return self.drawing


def draw_sketch(sketch: Sketch) -> Drawing:
    """The drawing of one sketch."""
    return _Drawer(sketch).run()
