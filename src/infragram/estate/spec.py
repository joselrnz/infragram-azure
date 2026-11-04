"""A drawing written as a diagram file: the form ``infragram compose`` runs.

The import hands the user Python, not a finished picture
(``references/terraform.md`` section 3): frames as ``with`` blocks, components
written inside them with the library's own classes, wires after them. The
layout is the composer's, so nothing in the file places anything by hand, and
a person regroups, recaptions or removes what they like and composes again.
Every element carries a popup table naming the resource it was drawn from.
"""

from __future__ import annotations

import keyword
import re
from collections.abc import Iterable
from functools import cache

from ..author.diagram import slugify
from ..models.changes import combined
from .draw import BOX, Box, Card, Drawing
from .tables import component_class, frame_class

__all__ = ["SpecError", "write_spec"]


class SpecError(ValueError):
    """A drawing names a component or frame no library class draws."""


#: Names the file itself uses, which no element's variable may take.
_TAKEN = frozenset({"Box", "Diagram", "Edge", "Group", "diagram", "shared"})


@cache
def _libraries() -> tuple[str, ...]:
    """Every library a file may import, whose names no element's variable may take."""
    from ..nodes.frames import GROUPS

    return tuple(sorted({*GROUPS, "infragram"}))


def _identifier(text: str, taken: set[str]) -> str:
    base = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower() or "node"
    if base[0].isdigit():
        base = f"n_{base}"
    if keyword.iskeyword(base) or base in _TAKEN:
        base += "_"
    name, n = base, 2
    while name in taken:
        name = f"{base}_{n}"
        n += 1
    taken.add(name)
    return name


def _docstring(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def _call(module: str, cls: str, args: Iterable[str]) -> str:
    return f"{module}.{cls}({', '.join(args)})"


class _Writer:
    def __init__(self, drawing: Drawing) -> None:
        self.drawing = drawing
        self.lines: list[str] = []
        self.names: dict[str, str] = {}
        #: libraries the cards are drawn from, and the frames
        self.libraries: set[str] = set()
        self.frames: set[str] = set()
        self.groups = False
        self.boxes = False
        taken: set[str] = {f"{lib}_frames" for lib in _libraries()} | set(_libraries())
        ends = {w.source for w in drawing.wires} | {w.target for w in drawing.wires}
        for item in drawing.walk():
            if item.key in ends:
                # the name without the address range a frame's caption carries
                self.names[item.key] = _identifier(item.caption.split(" · ")[0], taken)

    def card(self, card: Card, pad: str) -> None:
        args = [repr(card.caption)]
        if card.detail:
            args.append(repr(card.detail))
        found = (
            ("", "Box")
            if (card.library, card.service_id) == ("infragram", BOX)
            else component_class(card.library, card.service_id)
        )
        if found is None:
            raise SpecError(f"no {card.library} class draws {card.service_id!r}")
        if not found[0]:
            self.boxes = True
            call = f"Box({', '.join(args)})"
        elif card.library == "infragram":
            call = _call(f"shared.{found[0]}", found[1], args)
        else:
            self.libraries.add(card.library)
            call = _call(card.library, found[1], args)
        if card.sizing:
            call += (
                ".sizing("
                + ", ".join(f"{key}={value!r}" for key, value in card.sizing.items())
                + ")"
            )
        if card.shape:
            call += f".shape({card.shape!r})"
        if card.tone:
            call += f".tone({card.tone!r})"
        tags = card.worn_tags()
        if tags:
            call += f".tags({tags!r})"
        change = combined(getattr(source, "change", None) for source in card.sources)
        if change:
            call += f".change({change!r})"
        name = self.names.get(card.key)
        head = f"{pad}{name} = {call}" if name else f"{pad}{call}"
        if not card.rows:
            self.lines.append(head)
            return
        self.lines.append(f'{head}.table(("Attribute", "Value"), [')
        self.lines += [f"{pad}    ({key!r}, {value!r})," for key, value in card.rows]
        self.lines.append(f"{pad}])")

    def badges(self, box: Box) -> str:
        """The frame's corner badges, as ``.badge(...)`` calls on its ``with`` line."""
        calls = ""
        for badge in box.badges:
            found = component_class(badge.library, badge.service_id)
            if found is None:
                raise SpecError(f"no {badge.library} class draws {badge.service_id!r}")
            self.libraries.add(badge.library)
            calls += f".badge({badge.library}.{found[1]}, label={badge.label!r})"
        return calls

    def box(self, box: Box, pad: str) -> None:
        name = self.names.get(box.key)
        alias = f" as {name}" if name else ""
        flow = self.badges(box) + (f".{box.flow}()" if box.flow else "")
        if not box.library:
            # containment no gallery frame names: a plain zone
            self.groups = True
            self.lines.append(f"{pad}with Group({box.caption!r}, {box.kind!r}){flow}{alias}:")
        else:
            cls = frame_class(box.library, box.kind)
            if cls is None:
                raise SpecError(f"no {box.library} frame class draws {box.kind!r}")
            self.frames.add(box.library)
            self.lines.append(
                f"{pad}with {box.library}_frames.{cls}({box.caption!r}){flow}{alias}:"
            )
        if not box.children:
            self.lines.append(f"{pad}    pass")
        for child in box.children:
            self.item(child, pad + "    ")

    def item(self, item: Box | Card, pad: str) -> None:
        if isinstance(item, Box):
            self.box(item, pad)
        else:
            self.card(item, pad)

    def write(self, command: str, date: str, filename: str) -> str:
        drawing = self.drawing
        body_start = len(self.lines)
        for root in drawing.roots:
            self.item(root, "    ")
        if drawing.wires:
            self.lines.append("")
        for wire in drawing.wires:
            args = (
                ([repr(wire.label)] if wire.label else [])
                + (["dashed=True"] if wire.dashed else [])
                + (["both=True"] if wire.both and not wire.plain else [])
            )
            edge = f"Edge({', '.join(args)})"
            arrow = "-" if wire.plain else ">>"
            self.lines.append(
                f"    {self.names[wire.source]} {arrow} {edge} {arrow} {self.names[wire.target]}"
            )
        body = self.lines[body_start:]
        shared = any(
            isinstance(i, Card) and i.library == "infragram" and i.service_id != BOX
            for i in drawing.walk()
        )
        imports = ["from infragram.author import Diagram, Edge"]
        nodes = (
            (["Box"] if self.boxes else [])
            + (["Group"] if self.groups else [])
            + sorted(self.libraries)
            + (["infragram as shared"] if shared else [])
        )
        if nodes:
            imports.append(f"from infragram.nodes import {', '.join(nodes)}")
        imports += [
            f"from infragram.nodes.frames import {lib} as {lib}_frames"
            for lib in sorted(self.frames)
        ]
        slug = slugify(drawing.title)
        header = [
            '"""' + _docstring(drawing.title),
            "",
            _docstring(f"Drawn by `infragram {command}` on {date} from {drawing.origin}."),
            "It is where the diagram starts, not where it ends: regroup, recaption or",
            "remove what you like, then draw it again with",
            "",
            f"    infragram compose {filename}",
            "",
            f"Click an element in the exported page to see the {drawing.thing} it was drawn from.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            *imports,
            "",
            "with Diagram(",
            f"    {drawing.title!r},",
            f"    {drawing.description!r},",
            f"    slug={slug!r},",
            f"    drawn={date!r},",
            *([f"    notes=({('Plan: ' + drawing.plan)!r},),"] if drawing.plan else []),
            *([f"    direction={drawing.direction!r},"] if drawing.direction else []),
            *([f"    tones={drawing.tones!r},"] if drawing.tones else []),
            ") as diagram:",
        ]
        if not body:
            body = ["    pass"]
        return "\n".join(header + body) + "\n"


def write_spec(drawing: Drawing, *, command: str, date: str, filename: str) -> str:
    """The Python diagram file for ``drawing``."""
    return _Writer(drawing).write(command, date, filename)
