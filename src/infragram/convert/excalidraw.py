"""Excalidraw scenes: ``.excalidraw`` files and Obsidian's ``.excalidraw.md``.

Rectangles, ellipses and diamonds are shapes, labelled by the text bound
to them; frames are frames; arrows and lines are links, joined by their
bindings or, when drawn loose, by the shape under each end. A group of
drawn pieces with one caption (an icon from an Excalidraw library) is one
shape. Shapes carry no product names, so what each one is comes from its
label. Obsidian keeps the scene as ```` ```json ```` or LZ-compressed
```` ```compressed-json ````; both read.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .model import Bounds, Link, Shape, Sketch, split_label
from .nesting import nest_by_bounds, snap

__all__ = ["ExcalidrawError", "read_excalidraw", "read_excalidraw_text"]


class ExcalidrawError(ValueError):
    """The file holds no Excalidraw scene."""


_KINDS = {
    "rectangle": "box",
    "ellipse": "ellipse",
    "diamond": "diamond",
    "image": "image",
    "embeddable": "box",
    "iframe": "box",
}
_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="


def _lz_base64(text: str) -> str:
    """LZ-String's ``decompressFromBase64``, as Obsidian Excalidraw writes it."""
    text = re.sub(r"\s+", "", text)
    if not text:
        return ""
    reverse = {char: index for index, char in enumerate(_B64)}
    length = len(text)
    state = {"val": reverse[text[0]], "position": 32, "index": 1}

    def read(bits: int) -> int:
        out, power = 0, 1
        for _ in range(bits):
            bit = state["val"] & state["position"]
            state["position"] >>= 1
            if state["position"] == 0:
                state["position"] = 32
                state["val"] = reverse[text[state["index"]]] if state["index"] < length else 0
                state["index"] += 1
            if bit:
                out |= power
            power <<= 1
        return out

    dictionary: dict[int, str] = {0: "0", 1: "1", 2: "2"}
    size, bits, enlarge = 4, 3, 4
    first = read(2)
    if first == 2:
        return ""
    char = chr(read(8 if first == 0 else 16))
    dictionary[3] = char
    word = char
    result = [char]
    while True:
        if state["index"] > length:
            return ""
        code = read(bits)
        if code in (0, 1):
            dictionary[size] = chr(read(8 if code == 0 else 16))
            code = size
            size += 1
            enlarge -= 1
        elif code == 2:
            return "".join(result)
        if enlarge == 0:
            enlarge = 2**bits
            bits += 1
        if code in dictionary:
            entry = dictionary[code]
        elif code == size:
            entry = word + word[0]
        else:
            raise ExcalidrawError("the compressed scene is damaged")
        result.append(entry)
        dictionary[size] = word + entry[0]
        size += 1
        enlarge -= 1
        word = entry
        if enlarge == 0:
            enlarge = 2**bits
            bits += 1


def _scene(text: str) -> dict[str, Any]:
    stripped = text.lstrip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    block = re.search(r"```compressed-json\s*\n(.*?)```", text, re.DOTALL)
    if block:
        return json.loads(_lz_base64(block.group(1)))
    block = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
    if block:
        return json.loads(block.group(1))
    raise ExcalidrawError("no Excalidraw scene in it")


def _bounds(element: dict[str, Any]) -> Bounds:
    x, y = float(element.get("x", 0)), float(element.get("y", 0))
    width, height = float(element.get("width", 0)), float(element.get("height", 0))
    # a shape drawn right to left or bottom to top keeps a negative size
    return Bounds(x=min(x, x + width), y=min(y, y + height), width=abs(width), height=abs(height))


def read_excalidraw_text(text: str, *, name: str) -> Sketch:
    """The scene a ``.excalidraw`` or ``.excalidraw.md`` text holds."""
    try:
        scene = _scene(text)
    except (json.JSONDecodeError, KeyError, IndexError) as error:
        raise ExcalidrawError(f"{name}: not an Excalidraw scene ({error})") from error
    elements = [
        e for e in scene.get("elements", []) if isinstance(e, dict) and not e.get("isDeleted")
    ]
    sketch = Sketch(title=name, origin=name, format="excalidraw")
    by_id = {e.get("id"): e for e in elements}
    bound_text: dict[str, list[str]] = {}
    for element in elements:
        if element.get("type") == "text" and element.get("containerId"):
            bound_text.setdefault(element["containerId"], []).append(
                element.get("originalText") or element.get("text") or ""
            )
    # a library icon: one outermost group of drawn pieces with one caption
    alias: dict[str, str] = {}
    groups: dict[str, list[dict[str, Any]]] = {}
    for element in elements:
        if element.get("groupIds") and element.get("type") not in ("arrow", "line"):
            groups.setdefault(element["groupIds"][-1], []).append(element)
    for group, members in groups.items():
        labelled = [m for m in members if m.get("id") in bound_text]
        drawn = [m for m in members if m.get("type") != "text"]
        if len(labelled) >= 2 or len(drawn) < 2:
            continue  # a person's grouping of labelled shapes, or one shape and its caption
        free = [
            m.get("originalText") or m.get("text") or ""
            for m in members
            if m.get("type") == "text" and not m.get("containerId")
        ]
        label = "\n".join(bound_text.get(labelled[0]["id"], []) if labelled else free)
        boxes = [_bounds(m) for m in members]
        left, top = min(b.x for b in boxes), min(b.y for b in boxes)
        right = max(b.x + b.width for b in boxes)
        bottom = max(b.y + b.height for b in boxes)
        caption, detail = split_label(label)
        sketch.shapes.append(
            Shape(
                key=f"group:{group}",
                label=caption,
                detail=detail,
                kind="image",
                box=Bounds(x=left, y=top, width=right - left, height=bottom - top),
                source=f"group {group} ({len(members)} pieces)",
            )
        )
        for member in members:
            alias[member["id"]] = f"group:{group}"
    for element in elements:
        key = element.get("id", "")
        kind = element.get("type")
        if key in alias:
            continue
        if kind in ("frame", "magicframe"):
            sketch.shapes.append(
                Shape(
                    key=key,
                    label=element.get("name") or "Frame",
                    container=True,
                    box=_bounds(element),
                    source=f"frame {key}",
                )
            )
        elif kind in _KINDS:
            caption, detail = split_label("\n".join(bound_text.get(key, [])))
            link = element.get("link")
            sketch.shapes.append(
                Shape(
                    key=key,
                    label=caption,
                    detail=detail,
                    kind=_KINDS[kind],
                    box=_bounds(element),
                    rows=[("Link", link)] if link else [],
                    source=f"{kind} {key}",
                )
            )
        elif kind == "text" and not element.get("containerId"):
            caption, detail = split_label(element.get("originalText") or element.get("text"))
            if caption:
                sketch.shapes.append(
                    Shape(
                        key=key,
                        label=caption,
                        detail=detail,
                        kind="text",
                        box=_bounds(element),
                        source=f"text {key}",
                    )
                )
    for shape in sketch.shapes:
        member = by_id.get(shape.key) or {}
        frame = member.get("frameId")
        if frame and frame in by_id:
            shape.parent = frame
    nest_by_bounds(sketch.shapes)
    for element in elements:
        if element.get("type") not in ("arrow", "line"):
            continue
        ends: list[str | None] = []
        points = element.get("points") or [[0, 0], [0, 0]]
        for binding, point in (
            (element.get("startBinding"), points[0]),
            (element.get("endBinding"), points[-1]),
        ):
            target = (binding or {}).get("elementId")
            if isinstance(target, str):
                target = alias.get(target, target)
            if (
                target in by_id
                and by_id[target].get("type") == "text"
                and by_id[target].get("containerId")
            ):
                target = by_id[target]["containerId"]
            if target is None or sketch.shape(target) is None:
                target = snap(
                    sketch.shapes,
                    float(element.get("x", 0)) + point[0],
                    float(element.get("y", 0)) + point[1],
                )
            ends.append(target)
        label = " ".join(
            t for t in split_label("\n".join(bound_text.get(element.get("id", ""), []))) if t
        )
        source, target = ends
        if source is None or target is None or source == target:
            if element.get("type") == "arrow":
                sketch.notes.append(
                    f"the arrow {element.get('id')}{f' ({label})' if label else ''} "
                    "does not join two shapes"
                )
            continue
        start = element.get("startArrowhead") is not None
        end = element.get("endArrowhead") is not None
        if start and not end:
            source, target = target, source
        sketch.links.append(
            Link(
                source=source,
                target=target,
                label=label,
                dashed=element.get("strokeStyle") in ("dashed", "dotted"),
                direction="both" if start and end else "forward" if start or end else "none",
                origin=f"{element.get('type')} {element.get('id')}",
            )
        )
    return sketch


def read_excalidraw(path: Path) -> Sketch:
    name = re.sub(r"(?:\.excalidraw)?(?:\.json|\.md)?$", "", path.name, flags=re.IGNORECASE)
    return read_excalidraw_text(path.read_text(encoding="utf-8-sig"), name=name)
