"""C4 model macros, as Mermaid's ``C4Context`` diagrams and C4-PlantUML write them.

Both spell the model the same way: ``Person(alias, "Label", "Description")``,
``Container(alias, "Label", "Technology", "Description")``, boundaries and
deployment nodes that open a ``{`` block, and ``Rel(from, to, "Label",
"Technology")`` for a line. A person is a user, a ``*Db`` a database, a
``*Queue`` a queue; a container's technology is a hint to what it runs as
(``PostgreSQL`` is a PostgreSQL database).
"""

from __future__ import annotations

import re

from .model import Hint, Link, Shape, Sketch, clean_text

__all__ = ["C4_MACRO", "C4Reader", "macro_arguments"]

_PEOPLE = {"Person", "Person_Ext"}
_SYSTEMS = {"System", "System_Ext", "SystemDb", "SystemDb_Ext", "SystemQueue", "SystemQueue_Ext"}
_PARTS = {
    f"{base}{suffix}{ext}"
    for base in ("Container", "Component")
    for suffix in ("", "Db", "Queue")
    for ext in ("", "_Ext")
}
_BOUNDARIES = {"Boundary", "Enterprise_Boundary", "System_Boundary", "Container_Boundary"}
_NODES = {"Deployment_Node", "Deployment_Node_L", "Deployment_Node_R", "Node", "Node_L", "Node_R"}
_RELS = {
    "Rel",
    "Rel_Back",
    "Rel_Neighbor",
    "Rel_Back_Neighbor",
    "Rel_U",
    "Rel_Up",
    "Rel_D",
    "Rel_Down",
    "Rel_L",
    "Rel_Left",
    "Rel_R",
    "Rel_Right",
    "BiRel",
    "BiRel_U",
    "BiRel_Up",
    "BiRel_D",
    "BiRel_Down",
    "BiRel_L",
    "BiRel_Left",
    "BiRel_R",
    "BiRel_Right",
    "BiRel_Neighbor",
}
#: Macros that only style or lay out the picture.
_QUIET = re.compile(
    r"^(?:Update\w+|Add\w+Tag|Lay_\w+|LAYOUT_\w+|SHOW_\w+|HIDE_\w+|"
    r"SetDefaultLegendEntries|RoundedBoxShape|EightSidedShape|DashedLine|DottedLine|"
    r"BoldLine|SolidLine|increment|setIndex)$"
)
_ALL = _PEOPLE | _SYSTEMS | _PARTS | _BOUNDARIES | _NODES | _RELS
#: ``Name(args)`` optionally opening a block.
C4_MACRO = re.compile(r"^(?P<name>[A-Za-z_][\w]*)\s*\((?P<args>.*)\)\s*(?P<open>\{)?\s*$")


def macro_arguments(text: str) -> tuple[list[str], dict[str, str]]:
    """``a, "B, c", $tags="x"`` -> ``(["a", "B, c"], {"tags": "x"})``."""
    parts: list[str] = []
    current: list[str] = []
    quote = False
    depth = 0
    for char in text:
        if char == '"':
            quote = not quote
        elif not quote and char in "([":
            depth += 1
        elif not quote and char in ")]":
            depth -= 1
        if char == "," and not quote and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current or parts:
        parts.append("".join(current))
    positional: list[str] = []
    named: dict[str, str] = {}
    for part in parts:
        part = part.strip()
        match = re.match(r"^\$?(\w+)\s*=\s*(.*)$", part)
        if match and (part.startswith("$") or not part.startswith('"')):
            named[match.group(1).lstrip("$")] = match.group(2).strip().strip('"')
        else:
            positional.append(part.strip('"'))
    return positional, named


def _text(value: str) -> str:
    return " ".join(clean_text(value).split())


class C4Reader:
    """Reads C4 statements into a sketch, tracking the open boundaries."""

    def __init__(self, sketch: Sketch) -> None:
        self.sketch = sketch
        self.keys: set[str] = {shape.key for shape in sketch.shapes}

    def handles(self, name: str) -> bool:
        return name in _ALL or bool(_QUIET.match(name))

    def statement(self, name: str, args: str, *, parent: str | None, where: str) -> Shape | None:
        """Read one macro; a shape it makes is returned so a ``{`` can open it."""
        if _QUIET.match(name):
            return None
        positional, named = macro_arguments(args)
        if name in _RELS:
            self._relation(name, positional, named, where)
            return None
        if not positional:
            self.sketch.notes.append(f"{where}: {name}() names nothing")
            return None
        alias = positional[0]
        label = _text(positional[1]) if len(positional) > 1 else alias
        shape = Shape(key=alias, label=label or alias, parent=parent, source=f"{where} ({name})")
        rows: list[tuple[str, str]] = [("C4", name)]
        if name in _PEOPLE:
            shape.kind = "actor"
            description = positional[2] if len(positional) > 2 else named.get("descr", "")
        elif name in _SYSTEMS:
            description = positional[2] if len(positional) > 2 else named.get("descr", "")
        elif name in _PARTS:
            technology = positional[2] if len(positional) > 2 else named.get("techn", "")
            description = positional[3] if len(positional) > 3 else named.get("descr", "")
            if technology:
                shape.detail = _text(technology)
                shape.hints.append(Hint(phrase=_text(technology), raw=f"{name} technology"))
                rows.append(("Technology", _text(technology)))
        elif name in _BOUNDARIES:
            shape.container = True
            description = ""
            kind = positional[2] if len(positional) > 2 else named.get("type", "")
            if kind:
                rows.append(("Type", _text(kind)))
        else:  # a deployment node
            shape.container = True
            kind = positional[2] if len(positional) > 2 else named.get("type", "")
            description = positional[3] if len(positional) > 3 else named.get("descr", "")
            if kind:
                shape.detail = _text(kind)
                shape.hints.append(Hint(phrase=_text(kind), raw=f"{name} type"))
        if "Db" in name:
            shape.kind = "database"
        elif "Queue" in name:
            shape.kind = "queue"
        if description:
            rows.append(("Description", _text(description)))
        if named.get("link"):
            rows.append(("Link", named["link"]))
        shape.rows = rows
        self.add(shape)
        return shape

    def add(self, shape: Shape) -> None:
        if shape.key in self.keys:
            existing = self.sketch.shape(shape.key)
            if existing is not None and not existing.label:
                existing.label = shape.label
            return
        self.keys.add(shape.key)
        self.sketch.shapes.append(shape)

    def _relation(
        self, name: str, positional: list[str], named: dict[str, str], where: str
    ) -> None:
        if len(positional) < 2:
            self.sketch.notes.append(f"{where}: {name}() needs two ends")
            return
        source, target = positional[0], positional[1]
        label = _text(positional[2]) if len(positional) > 2 else _text(named.get("label", ""))
        technology = _text(positional[3]) if len(positional) > 3 else _text(named.get("techn", ""))
        if technology:
            label = f"{label} ({technology})" if label else technology
        if name.startswith("Rel_Back"):
            source, target = target, source
        self.sketch.links.append(
            Link(
                source=source,
                target=target,
                label=label,
                direction="both" if name.startswith("BiRel") else "forward",
                origin=f"{where} ({name})",
            )
        )
