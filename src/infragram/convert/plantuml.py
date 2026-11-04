"""PlantUML: deployment and component diagrams, C4-PlantUML, and the cloud libraries.

- Elements by keyword (``node``, ``database``, ``cloud``, ``queue``,
  ``actor``, ``component``, ``rectangle`` ...), in every naming form
  (``node "Web" as web``, ``node web as "Web"``, ``[Web] as web``,
  ``:User: as u``); a keyword that opens ``{`` is a frame.
- Relations in every arrow PlantUML draws (``-->``, ``..>``, ``<-->``,
  ``-up->``, ``-[#red,dashed]->``), with ``: labels``; an end nobody
  declared is declared by the relation, as PlantUML does.
- C4-PlantUML macros, read by :mod:`.c4`.
- The cloud libraries' macros (AWS-PlantUML ``Lambda(fn, "Label", "Tech")``,
  ``VPCGroup(vpc, "VPC") {``, Azure-PlantUML ``AzureFunction(...)``,
  Kubernetes-PlantUML, the tupadr3 icon fonts), and sprites in labels
  (``<$Lambda>``): the macro's name is what the shape is, in the library
  the file includes.

Notes, legends, skin parameters and preprocessor lines are passed over.
"""

from __future__ import annotations

import re

from .c4 import C4_MACRO, C4Reader, macro_arguments
from .model import Hint, Link, Shape, Sketch, clean_text, words

__all__ = ["PlantumlError", "read_plantuml"]


class PlantumlError(ValueError):
    """The text is not a PlantUML diagram this reader draws."""


_KEYWORDS = {
    "actor": "actor",
    "person": "actor",
    "agent": "box",
    "artifact": "file",
    "boundary": "box",
    "card": "box",
    "circle": "ellipse",
    "cloud": "cloud",
    "collections": "box",
    "component": "box",
    "control": "box",
    "database": "database",
    "entity": "box",
    "file": "file",
    "folder": "box",
    "frame": "box",
    "hexagon": "hexagon",
    "interface": "ellipse",
    "label": "text",
    "node": "box",
    "package": "box",
    "queue": "queue",
    "rectangle": "box",
    "stack": "box",
    "storage": "storage",
    "usecase": "ellipse",
    "process": "box",
    "action": "box",
}
_ELEMENT = re.compile(
    r"^(?P<kw>" + "|".join(sorted(_KEYWORDS, key=len, reverse=True)) + r")\s+(?P<rest>.+)$"
)
_ENDPOINT = r'"[^"]+"|\[[^\]]+\]|:[^:]+:|\(\)\s*"[^"]+"|\(\)\s*[\w.]+|[\w.$]+'
_RELATION = re.compile(
    rf"^(?P<a>{_ENDPOINT})\s*(?P<l>[<*o#x}}+^|]*)(?P<body>[-.=]+(?:\[[^\]]*\])?"
    rf"(?:up|down|left|right|u|d|l|r)?[-.=]*)(?P<r>[>*o#x{{+^|]*)\s*(?P<b>{_ENDPOINT})\s*"
    rf"(?::\s*(?P<label>.*))?$"
)
_SPRITE = re.compile(r"<\$([\w-]+)(?:\{[^}]*\})?(?:,[^>]*)?>")
_ICON_FONT = re.compile(r"^(?:DEV2?|FA\d?|FAR|FAB|MATERIAL|GOV|WEATHER|OS|SIMPLE|SI)_(.+)$")
_SKIP = re.compile(
    r"^(?:skinparam|hide|show|scale|header|footer|caption|!|allowmixing|"
    r"allow_mixing|sprite|autonumber|newpage|together|remove|set\s|style)\b"
)
_FLOW = {"left to right direction": "row", "top to bottom direction": "column"}
#: A library's helper macros, which colour or explain rather than draw.
_LIBRARY_QUIET = re.compile(
    r"(?:Coloring|Style|Legend|Tag|Sprite|Participant)$|"
    r"^(?:Set|Update|Add|Show|Hide|Lay|LAYOUT|Use|Include)[A-Z_]"
)


def _includes_provider(text: str) -> str | None:
    """The one cloud library a file includes, if exactly one."""
    found = set()
    for include in re.findall(r"!include\w*\s+(\S+)", text):
        lowered = include.lower()
        if "aws" in lowered:
            found.add("aws")
        if "azure" in lowered:
            found.add("azure")
        if "gcp" in lowered or "google" in lowered:
            found.add("gcp")
        if "kubernetes" in lowered or "k8s" in lowered:
            found.add("kubernetes")
    for name in re.findall(r"!define\s+(\w+)Puml", text):
        found.add(
            {
                "AWS": "aws",
                "Azure": "azure",
                "GCP": "gcp",
                "KuberNetes": "kubernetes",
                "Kubernetes": "kubernetes",
            }.get(name, "")
        )
    found.discard("")
    return found.pop() if len(found) == 1 else None


def _macro_hint(name: str, provider: str | None) -> tuple[Hint, bool]:
    """A library macro's name -> (hint, names a frame)."""
    frame = name.endswith("Group") and name != "Group"
    base = name[: -len("Group")] if frame else name
    font = _ICON_FONT.match(base)
    if font:
        return Hint(phrase=words(font.group(1)), raw=name), frame
    for prefix, library in (
        ("Azure", "azure"),
        ("Kubernetes", "kubernetes"),
        ("K8s", "kubernetes"),
        ("KubernetesK8s", "kubernetes"),
        ("GCP", "gcp"),
        ("AWS", "aws"),
    ):
        if base.startswith(prefix) and len(base) > len(prefix):
            return Hint(
                provider=library, phrase=words(base[len(prefix) :]), frame=frame, raw=name
            ), frame
    return Hint(provider=provider, phrase=words(base), frame=frame, raw=name), frame


def _label(text: str) -> tuple[str, str, list[Hint]]:
    hints = [Hint(phrase=words(m.group(1)), raw=m.group(0)) for m in _SPRITE.finditer(text)]
    text = _SPRITE.sub("", text).replace("\\n", "\n")
    text = re.sub(r"</?(?:b|i|u|size[^>]*|color[^>]*|font[^>]*)>", "", text)
    text = re.sub(r"\*\*|//|__", "", text)
    lines = clean_text(text.strip().strip('"')).splitlines()
    return (lines[0] if lines else ""), " ".join(lines[1:]), hints


def _blocks(text: str) -> list[str]:
    """Each ``@startuml ... @enduml`` body; the whole text when it has none."""
    found = re.findall(r"@start(?:uml|c4)\b[^\n]*\n(.*?)@end(?:uml|c4)", text, re.DOTALL)
    return found or [text]


def _statements(text: str) -> list[str]:
    text = re.sub(r"/'.*?'/", "", text, flags=re.DOTALL)
    out: list[str] = []
    skipping: str | None = None
    depth = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("'"):
            continue
        if skipping:
            if skipping == "{":
                depth += line.count("{") - line.count("}")
                if depth <= 0:
                    skipping = None
            elif re.match(skipping, line, re.IGNORECASE):
                skipping = None
            continue
        if re.match(r"^(?:note|hnote|rnote)\b", line, re.IGNORECASE):
            if not (
                ":" in line
                or re.search(r'"\s*as\s+\w+\s*$', line)
                or re.match(r'^\w*note\s+"', line)
            ):
                skipping = r"^end\s*note|^endnote"
            continue
        if re.match(r"^legend\b", line, re.IGNORECASE):
            skipping = r"^end\s*legend|^endlegend"
            continue
        if re.match(r"^(?:skinparam|sprite|style|<style>)\b.*\{\s*$", line) or line == "<style>":
            skipping, depth = "{", line.count("{") - line.count("}")
            if line == "<style>":
                skipping = r"^</style>"
            continue
        if re.match(r"^!(?:procedure|function|unquoted)\b", line):
            skipping = r"^!end(?:procedure|function)"
            continue
        out.append(line)
    return out


def _parse_element(keyword: str, rest: str) -> tuple[str, str, bool, list[str]]:
    """``"Web" as web <<Server>> #eee {`` -> (alias, label, opens a block, stereotypes)."""
    opens = rest.rstrip().endswith("{")
    rest = rest.rstrip().rstrip("{").strip()
    stereotypes = re.findall(r"<<\s*([^>]+?)\s*>>", rest)
    rest = re.sub(r"<<[^>]*>>", "", rest)
    rest = re.sub(r"\s#[\w#;:.]+\s*$|\s\$\w+=\S+", "", " " + rest).strip()
    for pattern in (
        r'^"(?P<label>[^"]*)"\s+as\s+(?P<alias>\S+)',
        r'^(?P<alias>\S+)\s+as\s+"(?P<label>[^"]*)"',
        r"^\[(?P<label>[^\]]*)\]\s+as\s+(?P<alias>\S+)",
        r"^:(?P<label>[^:]*):\s+as\s+(?P<alias>\S+)",
        r"^(?P<alias>\S+)\s+as\s+(?P<label>\S+)",
    ):
        match = re.match(pattern, rest)
        if match:
            return match.group("alias"), match.group("label"), opens, stereotypes
    match = re.match(r'^"(?P<label>[^"]*)"$|^\[(?P<bracket>[^\]]*)\]$', rest)
    if match:
        label = match.group("label") if match.group("label") is not None else match.group("bracket")
        return label, label, opens, stereotypes
    alias = rest.split()[0] if rest else keyword
    return alias, alias, opens, stereotypes


class _Reader:
    def __init__(self, sketch: Sketch, provider: str | None) -> None:
        self.sketch = sketch
        self.provider = provider
        self.c4 = C4Reader(sketch)
        self.stack: list[str | None] = []
        self.shapes: dict[str, Shape] = {}

    @property
    def parent(self) -> str | None:
        return next((key for key in reversed(self.stack) if key), None)

    def add(self, shape: Shape) -> Shape:
        existing = self.shapes.get(shape.key) or self.sketch.shape(shape.key)
        if existing is not None:
            return existing
        self.shapes[shape.key] = shape
        self.c4.add(shape)
        return shape

    def endpoint(self, text: str) -> str:
        """The key of a relation's end, declaring it when nobody did."""
        text = text.strip()
        if text in self.shapes or self.sketch.shape(text):
            return text
        kind = "box"
        if text.startswith("["):
            label = text[1:-1]
        elif text.startswith(":"):
            label, kind = text[1:-1], "actor"
        elif text.startswith("()"):
            label, kind = text[2:].strip().strip('"'), "ellipse"
        else:
            label = text.strip('"')
        for key, shape in self.shapes.items():
            if shape.label == label and (text.startswith(("[", ":", '"', "()"))):
                return key
        caption, detail, hints = _label(label)
        self.add(
            Shape(
                key=text,
                label=caption or label,
                detail=detail,
                kind=kind,
                hints=hints,
                parent=self.parent,
                source=f"named by a relation: {text}",
            )
        )
        return text

    def statement(self, line: str, number: int) -> None:
        where = f"line {number}"
        if line in _FLOW:
            self.sketch.flow = _FLOW[line]  # type: ignore[assignment]
            return
        if line.startswith("title "):
            self.sketch.title = _label(line[6:])[0]
            return
        if line == "}":
            if self.stack:
                self.stack.pop()
            return
        if line == "{":
            return
        if _SKIP.match(line):
            if line.startswith("together") and line.endswith("{"):
                self.stack.append(None)
            return
        macro = C4_MACRO.match(line)
        if macro:
            name = macro.group("name")
            if self.c4.handles(name):
                shape = self.c4.statement(
                    name, macro.group("args"), parent=self.parent, where=where
                )
                if shape is not None:
                    self.shapes[shape.key] = shape
                    self._sprites(shape)
            elif _LIBRARY_QUIET.search(name):
                shape = None
            else:
                shape = self.library_macro(name, macro.group("args"), where)
            if macro.group("open"):
                self.stack.append(shape.key if shape else None)
            return
        relation = _RELATION.match(line)
        if relation and not _ELEMENT.match(line):
            self.relation(relation, where)
            return
        element = _ELEMENT.match(line)
        shortcut = re.match(r"^(?P<rest>(?:\[[^\]]+\]|:[^:]+:)(?:\s+as\s+\S+)?.*)$", line)
        matched = element or shortcut
        if matched:
            keyword = (
                element.group("kw")
                if element
                else ("actor" if line.startswith(":") else "component")
            )
            rest = matched.group("rest")
            alias, label, opens, stereotypes = _parse_element(keyword, rest)
            caption, detail, hints = _label(label)
            kind = _KEYWORDS[keyword]
            for stereotype in stereotypes:
                sprite = re.match(r"^\$([\w-]+)$", stereotype.strip())
                if sprite:
                    hints.append(Hint(phrase=words(sprite.group(1)), raw=stereotype))
                elif stereotype.strip():
                    hints.append(Hint(phrase=words(stereotype), raw=f"<<{stereotype}>>"))
            shape = self.add(
                Shape(
                    key=alias,
                    label=caption or alias,
                    detail=detail,
                    kind=kind,
                    hints=hints,
                    parent=self.parent,
                    container=opens,
                    source=f"{where} ({keyword})",
                )
            )
            if opens:
                shape.container = True
                self.stack.append(shape.key)
            return
        self.sketch.notes.append(f"{where}: passed over {line!r}")

    def _sprites(self, shape: Shape) -> None:
        caption, detail, hints = _label(shape.label)
        if hints:
            shape.label = caption or shape.label
            shape.hints += hints

    def library_macro(self, name: str, args: str, where: str) -> Shape | None:
        positional, named = macro_arguments(args)
        if not positional:
            self.sketch.notes.append(f"{where}: {name}() names nothing")
            return None
        hint, frame = _macro_hint(name, self.provider)
        alias = positional[0]
        label = positional[1] if len(positional) > 1 else named.get("label", alias)
        caption, detail, hints = _label(label)
        technology = positional[2] if len(positional) > 2 else named.get("techn", "")
        kind = "box"
        if _ICON_FONT.match(name) and technology in _KEYWORDS:
            # tupadr3 icon macros take the element keyword third
            kind, technology = _KEYWORDS[technology], ""
        rows = [("Macro", name)]
        description = positional[3] if len(positional) > 3 else named.get("descr", "")
        if description:
            rows.append(("Description", clean_text(description)))
        shape = self.add(
            Shape(
                key=alias,
                label=caption or alias,
                detail=detail or clean_text(technology),
                kind=kind,
                hints=[hint, *hints],
                parent=self.parent,
                container=frame,
                rows=rows,
                source=f"{where} ({name})",
            )
        )
        return shape

    def relation(self, match: re.Match[str], where: str) -> None:
        body = match.group("body")
        style = re.search(r"\[([^\]]*)\]", body)
        options = style.group(1).lower() if style else ""
        if "hidden" in options:
            return
        line_part = re.sub(r"\[[^\]]*\]", "", body)
        left, right = match.group("l"), match.group("r")
        a = self.endpoint(match.group("a"))
        b = self.endpoint(match.group("b"))
        forward, backward = ">" in right, "<" in left
        if backward and not forward:
            a, b = b, a
        caption, detail, _ = _label(match.group("label") or "")
        self.sketch.links.append(
            Link(
                source=a,
                target=b,
                label=" ".join(t for t in (caption, detail) if t),
                dashed="." in line_part or "dashed" in options or "dotted" in options,
                direction="both"
                if forward and backward
                else "forward"
                if forward or backward
                else "none",
                origin=where,
            )
        )


def read_plantuml(text: str, *, name: str, origin: str | None = None) -> list[Sketch]:
    """Every ``@startuml`` diagram a text holds."""
    blocks = _blocks(text)
    sketches: list[Sketch] = []
    provider = _includes_provider(text)
    for index, block in enumerate(blocks, start=1):
        statements = _statements(block)
        if not statements:
            continue
        if statements[0].startswith(("participant", "activate")) or any(
            re.match(r"^(?:participant|activate|alt|loop|state|class)\b", s) for s in statements[:5]
        ):
            raise PlantumlError(f"{name}: a sequence, class or state diagram draws no architecture")
        label = name if len(blocks) == 1 else f"{name} {index}"
        sketch = Sketch(title=label, origin=origin or label, format="plantuml")
        reader = _Reader(sketch, provider)
        for number, statement in enumerate(statements, start=1):
            reader.statement(statement, number)
        sketches.append(sketch)
    if not sketches:
        raise PlantumlError(f"{name}: no diagram in it")
    return sketches
