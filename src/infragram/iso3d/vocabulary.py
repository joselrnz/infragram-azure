"""The vocabulary the 3D set is built from: the glyphs a badge can carry, the
families and their colours, and the recipes scene.js offers with their knobs.

Shared by the build script (``scripts/build/iso-icons.py``), the compose-time
renderer (``infragram.iso``) and the docs, so the one table is the truth.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

#: Family id -> its colour; the sidebar category each family lands in is in the build script.
FAMILY_COLOURS: dict[str, str] = {
    "compute": "#2f6fde",
    "storage": "#0f9d8a",
    "network": "#7c3aed",
    "security": "#d63c3c",
    "facility": "#d97706",
    "client": "#475569",
    "platform": "#4f46e5",
    "operations": "#0891b2",
    "industrial": "#16a34a",
    "energy": "#c026d3",
}

#: The badge an item without a glyph of its own wears: its family's mark.
FAMILY_GLYPH: dict[str, str] = {
    "compute": "cube",
    "storage": "database",
    "network": "arrows",
    "security": "shield",
    "facility": "bolt",
    "client": "person",
    "platform": "helm",
    "operations": "chart",
    "industrial": "gear",
    "energy": "power",
}

#: 24-unit line glyphs, as SVG fragments; a badge draws each ``<path d>`` of one.
GLYPHS = {
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    "key": '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l2 2M14 9l2 2"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
    "bolt": '<path d="M13 2L5 14h6l-1 8 8-12h-6z"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
    "envelope": '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "eye": '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>',
    "wifi": '<path d="M5 10a10 10 0 0 1 14 0M8 13.5a6 6 0 0 1 8 0"/><circle cx="12" cy="17" r="1.2" fill="currentColor"/>',
    "arrows": '<path d="M4 12h16M14 6l6 6-6 6M10 6l-6 6 6 6"/>',
    "wall": '<path d="M3 6h18M3 12h18M3 18h18M9 6v6M15 12v6M15 6v0M9 12v6"/>',
    "fan": '<circle cx="12" cy="12" r="2"/><path d="M12 10c0-5 4-7 6-5-2 1-4 3-6 5zM14 12c5 0 7 4 5 6-1-2-3-4-5-6zM12 14c0 5-4 7-6 5 2-1 4-3 6-5zM10 12c-5 0-7-4-5-6 1 2 3 4 5 6z"/>',
    "flame": '<path d="M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 1-3-1-6 1-9z"/>',
    "battery": '<rect x="3" y="7" width="16" height="10" rx="2"/><path d="M21 10v4M6 10v4M9 10v4M12 10v4"/>',
    "camera": '<rect x="3" y="8" width="13" height="9" rx="2"/><path d="M16 11l5-3v9l-5-3"/>',
    "person": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    "people": '<circle cx="9" cy="8" r="3.5"/><circle cx="17" cy="9" r="3"/><path d="M2 20c0-4 3-6 7-6s7 2 7 6M16 14c3 0 6 2 6 6"/>',
    "cloud": '<path d="M7 18a4 4 0 0 1 0-8 6 6 0 0 1 11.5 1.5A3.5 3.5 0 0 1 18 18z"/>',
    "database": '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "printer": '<path d="M7 9V4h10v5M5 9h14a2 2 0 0 1 2 2v6h-4v4H7v-4H3v-6a2 2 0 0 1 2-2z"/>',
    "phone": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
    "tag": '<path d="M3 12V5a2 2 0 0 1 2-2h7l9 9-9 9z"/><circle cx="8" cy="8" r="1.2" fill="currentColor"/>',
    "chart": '<path d="M4 20h16M6 16l4-5 4 3 5-7"/>',
    "check": '<path d="M5 12l5 5L20 7"/>',
    "code": '<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13 5l-2 14"/>',
    "cube": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
    "helm": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 4v5M12 15v5M4 12h5M15 12h5"/>',
    "branch": '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="9" r="2"/><path d="M6 7v10M18 11c0 4-12 2-12 6"/>',
    "id": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2.5"/><path d="M5 17c0-2 2-3 4-3s4 1 4 3M15 9h3M15 13h3"/>',
    "radio": '<circle cx="12" cy="13" r="2"/><path d="M6 8a8 8 0 0 0 0 10M18 8a8 8 0 0 1 0 10M8.5 10.5a4 4 0 0 0 0 5M15.5 10.5a4 4 0 0 1 0 5"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0"/>',
    "thermo": '<path d="M10 14V5a2 2 0 0 1 4 0v9a4 4 0 1 1-4 0z"/>',
    "power": '<path d="M12 3v9M7 7a7 7 0 1 0 10 0"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="M15 15l5 5"/>',
    "bug": '<circle cx="12" cy="13" r="6"/><path d="M12 7V4M8 9L5 6M16 9l3-3M4 13h2M18 13h2M6 19l2-2M18 19l-2-2"/>',
    "gauge": '<path d="M4 16a8 8 0 1 1 16 0"/><path d="M12 16l4-5"/><circle cx="12" cy="16" r="1.5" fill="currentColor"/>',
    "tape": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2"/><path d="M12 3v7M12 14v7"/>',
    "disc": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>',
    "ticket": '<path d="M3 8a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 0 0-4z"/><path d="M13 6v12" stroke-dasharray="2 2"/>',
    "doc": '<path d="M6 3h8l5 5v13H6z M14 3v5h5 M9 13h6M9 17h6"/>',
    "plug": '<path d="M9 3v5M15 3v5M6 8h12v3a6 6 0 0 1-12 0zM12 17v4"/>',
    "wave": '<path d="M3 12c2-4 4-4 6 0s4 4 6 0 4-4 6 0"/>',
    "kiosk": '<rect x="5" y="3" width="14" height="12" rx="1.5"/><path d="M9 21h6M12 15v6"/>',
    "barcode": '<path d="M4 5v14M8 5v14M11 5v14M14 5v14M17 5v14M20 5v14"/>',
    "nfc": '<path d="M8 8a6 6 0 0 1 0 8M11 6a9 9 0 0 1 0 12M14 4a12 12 0 0 1 0 16"/>',
    "bluetooth": '<path d="M7 7l10 10-5 4V3l5 4L7 17"/>',
    "wrench": '<path d="M14 6a4 4 0 0 0 5 5l-9 9a2 2 0 0 1-3-3l9-9a4 4 0 0 0-2-2z"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "dollar": '<path d="M12 3v18M16 7H10a3 3 0 0 0 0 6h4a3 3 0 0 1 0 6H8"/>',
    "cart": '<circle cx="8" cy="20" r="1.5"/><circle cx="17" cy="20" r="1.5"/><path d="M2 3h3l2 12h12l2-8H6"/>',
    "handshake": '<path d="M3 11l4-4 5 5-2 2M21 11l-4-4-5 5M8 16l3 3M11 13l3 3M14 10l3 3"/>',
    "vault": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="12" cy="12" r="4"/><path d="M12 8v2M12 14v2M8 12h2M14 12h2"/>',
}


_SHAPE = re.compile(r"<(path|rect|circle|ellipse|line|polyline|polygon)\b([^>]*?)/?>")
_ATTR = re.compile(r'(\w+)="([^"]*)"')


def _num(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _shape_path(tag: str, attrs: dict[str, str]) -> str:
    """One basic shape as path data, so a badge draws the whole mark."""
    n = _num

    def f(key: str, default: str = "0") -> float:
        return float(attrs.get(key, default))

    if tag == "path":
        return attrs.get("d", "")
    if tag == "rect":
        x, y, w, h = f("x"), f("y"), f("width"), f("height")
        rx = f("rx", attrs.get("ry", "0"))
        ry = f("ry", n(rx))
        if rx <= 0 or ry <= 0:
            return f"M{n(x)} {n(y)}h{n(w)}v{n(h)}h{n(-w)}z"
        return (
            f"M{n(x + rx)} {n(y)}h{n(w - 2 * rx)}a{n(rx)} {n(ry)} 0 0 1 {n(rx)} {n(ry)}v{n(h - 2 * ry)}"
            f"a{n(rx)} {n(ry)} 0 0 1 {n(-rx)} {n(ry)}h{n(-(w - 2 * rx))}a{n(rx)} {n(ry)} 0 0 1 {n(-rx)} {n(-ry)}"
            f"v{n(-(h - 2 * ry))}a{n(rx)} {n(ry)} 0 0 1 {n(rx)} {n(-ry)}z"
        )
    if tag in ("circle", "ellipse"):
        cx, cy = f("cx"), f("cy")
        rx = f("r") if tag == "circle" else f("rx")
        ry = rx if tag == "circle" else f("ry")
        return f"M{n(cx - rx)} {n(cy)}a{n(rx)} {n(ry)} 0 1 0 {n(2 * rx)} 0a{n(rx)} {n(ry)} 0 1 0 {n(-2 * rx)} 0"
    if tag == "line":
        return f"M{n(f('x1'))} {n(f('y1'))}L{n(f('x2'))} {n(f('y2'))}"
    points = re.findall(r"-?\d*\.?\d+", attrs.get("points", ""))
    pairs = [
        f"{n(float(points[i]))} {n(float(points[i + 1]))}" for i in range(0, len(points) - 1, 2)
    ]
    if not pairs:
        return ""
    return "M" + "L".join(pairs) + ("z" if tag == "polygon" else "")


def glyph_paths(name: str) -> list[str]:
    """The path data of one glyph, for the badge texture: every shape of the
    mark in document order, the basic shapes converted, so the lock keeps
    its body and the database its rim."""
    out = []
    for tag, raw in _SHAPE.findall(GLYPHS[name]):
        data = _shape_path(tag, dict(_ATTR.findall(raw)))
        if data:
            out.append(data)
    return out


SCENE = Path(__file__).resolve().parent / "scene.js"


@lru_cache(maxsize=1)
def recipes() -> dict[str, list[tuple[str, object]]]:
    """Every recipe scene.js offers, with its knobs and their defaults, read from
    the builder signatures (``R.name = (fam, tex, knob = default, ...) =>``)."""
    out: dict[str, list[tuple[str, object]]] = {}
    for name, params in re.findall(
        r"^R\.(\w+) = \(fam, tex(?:, ([^)]*))?\) =>", SCENE.read_text(encoding="utf-8"), re.M
    ):
        knobs: list[tuple[str, object]] = []
        for part in filter(None, (p.strip() for p in params.split(","))):
            key, _, default = part.partition("=")
            default = default.strip()
            value: object = None
            if default in ("true", "false"):
                value = default == "true"
            elif default.startswith(("'", '"')):
                value = default.strip("'\"")
            elif default:
                value = float(default) if "." in default else int(default)
            knobs.append((key.strip(), value))
        out[name] = knobs
    return out


#: A builder's first line: ``R.name = (fam, tex, knob = default, ...) =>``.
_SIGNATURE = re.compile(r"^R\.(\w+) = \(fam, tex(?:, [^)]*)?\) =>")
#: The words a yes/no knob takes on the command line, and what each means.
_TRUTH = {"true": True, "yes": True, "on": True, "1": True}
_TRUTH |= {"false": False, "no": False, "off": False, "0": False}


class KnobError(ValueError):
    """A knob value that is not of the knob's type."""


class Knob(BaseModel):
    """One of a recipe's knobs: its name, its type, its default, and for a
    text knob the values the builder tells apart."""

    model_config = ConfigDict(frozen=True)

    name: str
    type: Literal["int", "float", "bool", "str", "any"]
    default: bool | int | float | str | None = None
    #: The default first, then the others in the order the builder tests
    #: them. Any other value draws whatever the builder draws for the rest.
    choices: tuple[str, ...] = ()

    def parse(self, text: str) -> object:
        """A value for this knob from the command line's words: a whole
        number, a number, true or false, or the text itself, by the knob's
        type; a knob of any type takes the first of those that fits."""
        word = text.strip()
        folded = word.casefold()
        if self.type == "bool":
            if folded not in _TRUTH:
                raise KnobError(f"{self.name} is true or false, not {text!r}")
            return _TRUTH[folded]
        if self.type == "str":
            return text
        for convert, kind, wanted in ((int, "int", "a whole number"), (float, "float", "a number")):
            if self.type not in (kind, "any"):
                continue
            try:
                return convert(word)
            except ValueError:
                if self.type == kind:
                    raise KnobError(f"{self.name} is {wanted}, not {text!r}") from None
        if folded in ("true", "false"):
            return folded == "true"
        return text

    def signature(self) -> str:
        """The knob as a line reads it: ``units: int = 2``, ``kind: 'smr' | 'unit' = 'unit'``."""
        if isinstance(self.default, bool):
            default = "true" if self.default else "false"
        else:
            default = repr(self.default)
        if len(self.choices) > 1:
            return f"{self.name}: {' | '.join(map(repr, self.choices))} = {default}"
        return f"{self.name}: {self.type} = {default}"


def _bodies(scene: str) -> dict[str, str]:
    """Each builder's source, from its signature to the ``};`` that closes it:
    one line for a one-line builder, else up to the first line that is only
    ``};``."""
    lines = scene.replace("\r\n", "\n").split("\n")
    out: dict[str, str] = {}
    index = 0
    while index < len(lines):
        match = _SIGNATURE.match(lines[index])
        if not match:
            index += 1
            continue
        end = index
        if not lines[index].rstrip().endswith("};"):
            end += 1
            while end < len(lines) and lines[end].rstrip() != "};":
                end += 1
        out[match.group(1)] = "\n".join(lines[index : end + 1])
        index = end + 1
    return out


def _choices(scene: str, body: str, knob: str) -> list[str]:
    """The text values a builder tests *knob* against, in the order it tests
    them: ``kind === 'smr'`` (and ``!==``), ``['laptop', ...].includes(kind)``,
    and a lookup table's keys where it reads ``UNIT[unit]``."""
    name = re.escape(knob)
    found: list[str] = []
    for match in re.finditer(
        rf"\b{name}\s*[!=]==?\s*'([^']*)'|'([^']*)'\s*[!=]==?\s*{name}\b", body
    ):
        found.append(match.group(1) if match.group(1) is not None else match.group(2))
    for match in re.finditer(rf"\[([^\[\]]*)\]\.includes\({name}\)", body):
        found += re.findall(r"'([^']*)'", match.group(1))
    for match in re.finditer(rf"\b([A-Z][A-Z0-9_]*)\[{name}\]", body):
        table = re.search(
            rf"^const {re.escape(match.group(1))} = \{{(.*?)\}};", scene, re.MULTILINE | re.DOTALL
        )
        if table:
            found += re.findall(r"(?:^|[{,])\s*'?(\w[\w-]*)'?\s*:", table.group(1), re.MULTILINE)
    return found


@lru_cache(maxsize=1)
def recipe_knobs() -> dict[str, tuple[Knob, ...]]:
    """Every recipe with its knobs typed: the type is the default's (a knob
    without one takes any value), and a text knob lists the values its
    builder tells apart, the default first. Read from ``scene.js`` itself,
    as :func:`recipes` is, so it cannot disagree with the builder."""
    scene = SCENE.read_text(encoding="utf-8")
    bodies = _bodies(scene)
    out: dict[str, tuple[Knob, ...]] = {}
    for recipe, knobs in recipes().items():
        typed: list[Knob] = []
        for name, default in knobs:
            kind: Literal["int", "float", "bool", "str", "any"]
            choices: list[str] = []
            value: bool | int | float | str | None = None
            if isinstance(default, bool):
                kind, value = "bool", default
            elif isinstance(default, int):
                kind, value = "int", default
            elif isinstance(default, float):
                kind, value = "float", default
            elif isinstance(default, str):
                kind, value = "str", default
                for choice in [default, *_choices(scene, bodies.get(recipe, ""), name)]:
                    if choice not in choices:
                        choices.append(choice)
            else:
                kind = "any"
            typed.append(Knob(name=name, type=kind, default=value, choices=tuple(choices)))
        out[recipe] = tuple(typed)
    return out


def summary() -> dict[str, Any]:
    """The whole vocabulary as data: every recipe with its knobs, every family
    with its colour and badge glyph, and the glyph names."""
    return {
        "recipes": {
            recipe: [knob.model_dump() for knob in knobs]
            for recipe, knobs in sorted(recipe_knobs().items())
        },
        "families": {
            family: {"colour": colour, "glyph": FAMILY_GLYPH[family]}
            for family, colour in FAMILY_COLOURS.items()
        },
        "glyphs": sorted(GLYPHS),
    }


def runtime_payload() -> dict[str, object]:
    """What the editor page carries for its builder: the families and their
    colours, the family glyphs, every glyph as its path data, and the
    measurer itself, so a render made in the page is measured exactly the
    way the shipped table was."""
    from ..catalog.ink import EDGE_LINES
    from .measure import ALPHA, MAIN, MEASURE_JS, SIZE

    return {
        "families": dict(FAMILY_COLOURS),
        "familyGlyph": dict(FAMILY_GLYPH),
        "glyphs": {name: glyph_paths(name) for name in GLYPHS},
        "measure": MEASURE_JS % (SIZE, ALPHA, EDGE_LINES, MAIN),
        "size": SIZE,
    }
