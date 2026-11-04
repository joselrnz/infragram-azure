"""Where an icon's ink begins, so a wire touches the mark and not the air.

A bare glyph is 64 px of artwork, and most artwork keeps air inside its
square: the globe primitive leaves about 14 px on each side, a vendor badge
fills its square. A wire that stops at the square floats in that air.

``assets/catalog/ink-profiles.json`` records two things for every icon that
keeps air inside its square:

* ``profiles``: the ink's bounding box as ``[left, right, top, bottom]``
  insets, fractions of the square. The renderers draw a glyph's box in to
  it and keep other wires out of it.
* ``edges``: where the ink begins along each of 33 lines across every side,
  so a link is seated on the drawing itself, wherever its line falls:
  a round mark's outer links reach in to the curve, and a mark that is
  narrower in the middle is met where it is drawn, not in the air beside it.
  Each side is 33 characters, one per line from the side's start (its top
  for left and right, its left for top and bottom) to its end; a character
  is the depth in 64ths of the square (``A`` is 0, ``/`` is 63) and ``.``
  marks a line that meets no ink, or whose first ink is a detail: a
  separate piece under a third of the largest, such as the wifi arcs over a
  router. A link never lands on a detail or runs through one to reach the
  device; it slides to a line whose first ink is the device. A dashed
  outline is an edge: a line that passes between two dashes of a straight
  dashed edge is held at the dashes' depth and the dashes are recorded as
  the edge. The four sides are joined by ``|``.
* ``ports``: where a side's one connection point sits, for the few drawings
  the rule places badly, as a fraction along the side. A person is a head
  over a body: the middle of a side falls on the neck and slides to the
  chin, so the people glyphs set their left and right ports on the body.
  The tool keeps them by icon name and writes them keyed like the rest.

``scripts/tools/ink-profiles.py`` measures the table. This module is what
the renderers read; the shipped checker reads the same encoding off each
node's ``data-ink-edge`` with its own copy of :func:`edge_depth` (it may
not import this package).
"""

from __future__ import annotations

import colorsys
import hashlib
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..paths import skill_assets
from ..themes.colour import contrast, hex_rgb

#: Lines measured across each side, from its start to its end.
EDGE_LINES = 33
#: One character per line: how deep the ink begins, in 64ths of the square.
EDGE_LEVELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
#: A line that meets no ink, or whose first ink is a detail.
EDGE_NONE = "."
#: A line whose ink begins deeper than the middle of the square is unusable:
#: a link is never seated past the middle, and never pushed to it either.
EDGE_MAX_DEPTH = 0.5
#: How many lines away a line that meets no ink borrows its depth from.
EDGE_REACH = 3
#: Neighbouring lines further apart than this are an edge of the mark, not
#: a slope, so the depth between them is the nearer line's, not a blend.
EDGE_STEP = 3 / 64
#: The order the sides are stored in.
SIDES = ("left", "right", "top", "bottom")


def table_path() -> Path:
    return skill_assets() / "catalog" / "ink-profiles.json"


#: Colours, whitespace and boilerplate, which the editor rewrites when it
#: draws an icon (a primitive is painted in the theme's ink and gains the
#: namespace a data URI needs). The key ignores them, so a recoloured copy
#: still finds its profile: what is measured is the shape, and the shape is
#: what a wire has to touch.
_COLOUR = re.compile(rb"#[0-9a-fA-F]{3,8}|currentColor", re.I)
#: Boilerplate a copy may gain or lose without changing the shape: the
#: namespace a data URI needs, and the hint that hides the mark from readers.
_BOILERPLATE = re.compile(rb'\s(?:xmlns(?::\w+)?|aria-hidden)="[^"]*"')
_SPACE = re.compile(rb"\s+")


def artwork_key(data: bytes) -> str:
    """The table's key for one icon: a hash of its shape, ignoring colour and
    whitespace, so a vendor file, the same artwork inlined as a primitive and
    a recoloured copy of either all share one profile."""
    shape = _SPACE.sub(b" ", _BOILERPLATE.sub(b"", _COLOUR.sub(b"#", data))).strip()
    return hashlib.sha1(shape, usedforsecurity=False).hexdigest()[:12]


#: Below this mean relative luminance, artwork cannot hold 3:1 against the
#: dark canvas (#141414) and both renderers draw it light there. The editor
#: measures the same number in the page for artwork the table never saw.
DARK_INK = 0.12


def tone_key(data: bytes) -> str:
    """The table's key for one icon's *colour*: a hash of the artwork with
    its colours kept, where ``artwork_key`` drops them. How dark a drawing
    is is exactly what colour says, so a recoloured copy of one shape is a
    different entry here and the same entry there."""
    return hashlib.sha1(
        _SPACE.sub(b" ", _BOILERPLATE.sub(b"", data)).strip(), usedforsecurity=False
    ).hexdigest()[:12]


class InkTable(BaseModel):
    """``ink-profiles.json``: artwork key -> bounding-box insets and edge lines."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    #: How many lines each side was measured along; every ``edges`` entry
    #: carries exactly this many characters a side.
    lines: int = EDGE_LINES
    profiles: dict[str, list[float]] = Field(default_factory=dict)
    edges: dict[str, str] = Field(default_factory=dict)
    #: Mean relative luminance per ``tone_key``, for the artwork dark enough
    #: to need drawing light on a dark canvas. Artwork that reads as drawn is
    #: left out, which keeps the shipped table small.
    tones: dict[str, float] = Field(default_factory=dict)
    #: A side's connection point set by hand, as a fraction along the side,
    #: where the middle of the drawing's stretch is the wrong place (a
    #: person's neck): artwork key -> side -> fraction.
    ports: dict[str, dict[str, float]] = Field(default_factory=dict)

    @field_validator("ports")
    @classmethod
    def _ports_on_a_side(cls, ports: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
        for key, sides in ports.items():
            for side, along in sides.items():
                if side not in ("left", "right", "top") or not 0 <= along <= 1:
                    raise ValueError(
                        f"port {key} {side}={along}: a side's port is left, right or "
                        "top, at a fraction from 0 to 1 along it"
                    )
        return ports

    @field_validator("lines")
    @classmethod
    def _at_least_two_lines(cls, lines: int) -> int:
        if lines < 2:
            raise ValueError(f"an ink table needs at least 2 lines a side, has {lines}")
        return lines

    @field_validator("profiles")
    @classmethod
    def _four_sides(cls, profiles: dict[str, list[float]]) -> dict[str, list[float]]:
        for key, insets in profiles.items():
            if len(insets) != len(SIDES):
                raise ValueError(f"profile {key} needs {len(SIDES)} insets, has {len(insets)}")
        return profiles

    @model_validator(mode="after")
    def _four_lines_of_levels(self) -> InkTable:
        """Every edge code is four sides of exactly ``lines`` depths: the
        table's own line count, not a number typed here."""
        allowed = set(EDGE_LEVELS + EDGE_NONE)
        for key, code in self.edges.items():
            parts = code.split("|")
            if len(parts) != len(SIDES) or any(len(part) != self.lines for part in parts):
                raise ValueError(f"edges {key} needs {len(SIDES)} sides of {self.lines} lines")
            if not set(code.replace("|", "")) <= allowed:
                raise ValueError(f"edges {key} carries a character that is not a depth")
        return self


@lru_cache(maxsize=1)
def load_table() -> InkTable:
    """The shipped table, validated. Loud when it is missing or corrupt: a
    silently empty table would seat every link on the air around its glyph
    and the checker would then fail every picture, far from the cause."""
    path = table_path()
    if not path.is_file():
        raise FileNotFoundError(
            f"the ink table is not shipped at {path}; the skill assets are incomplete "
            f"(scripts/tools/ink-profiles.py measures it)"
        )
    try:
        return InkTable.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError(f"the ink table at {path} is corrupt: {error}") from error


#: Icons measured at run time -- renders a diagram asked for by spec -- keyed
#: like the table and consulted before it, so they seat links the same way.
_RUNTIME_PROFILES: dict[str, list[float]] = {}
_RUNTIME_EDGES: dict[str, str] = {}


def register(key: str, profile: list[float] | None, edges: str | None) -> None:
    """Add one icon's measurement for this process; None means 'fills its square'."""
    _RUNTIME_PROFILES.pop(key, None)
    _RUNTIME_EDGES.pop(key, None)
    if profile is not None:
        _RUNTIME_PROFILES[key] = list(profile)
    if edges is not None:
        _RUNTIME_EDGES[key] = edges


def profile(data: bytes | None) -> list[float] | None:
    """The ink insets for one icon's artwork as [left, right, top, bottom],
    or None when the icon fills its square (or is not one the skill ships)."""
    if not data:
        return None
    key = artwork_key(data)
    return _RUNTIME_PROFILES.get(key) or load_table().profiles.get(key)


def edges(data: bytes | None) -> str | None:
    """The icon's edge lines in the table's encoding, or None when it fills
    its square (or is not one the skill ships)."""
    if not data:
        return None
    key = artwork_key(data)
    return _RUNTIME_EDGES.get(key) or load_table().edges.get(key)


def ports(data: bytes | None) -> dict[str, float] | None:
    """The sides whose connection point the table sets by hand, as fractions
    along each side, or None when the rule places them all."""
    if not data:
        return None
    return load_table().ports.get(artwork_key(data))


def on_dark(colour: str, ground: str, floor: float = 3.0) -> str:
    """``colour`` as it is drawn on a dark ``ground``.

    A library's own colour is left exactly as the library set it while it can
    be seen. AWS's cloud navy (#232f3e) on the dark canvas is 1.4:1 -- a
    frame whose border and title are there but invisible -- so a colour under
    ``floor`` is lifted by turning its lightness over and keeping its hue,
    which is what the dark canvas does to dark artwork. Anything that is not
    a plain hex colour (a role name, rgba, "none") is returned untouched.
    """
    channels = hex_rgb(colour)
    ratio = contrast(colour, ground)
    if channels is None or ratio is None or ratio >= floor:
        return colour
    red, green, blue = (channel / 255 for channel in channels)
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    lifted = colorsys.hls_to_rgb(hue, 1 - lightness, saturation)
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in lifted)


def is_dark(data: bytes | None, limit: float = DARK_INK) -> bool:
    """Whether this artwork is too dark to read on a dark canvas.

    Measured artwork answers from the table; anything else answers no, which
    is what a renderer without a measurement should assume -- the editor
    measures it in the page instead (08-theme-and-layout.js).
    """
    if not data:
        return False
    tone = load_table().tones.get(tone_key(data))
    return tone is not None and tone < limit


def edge_depth(code: str | None, side: str, along: float) -> float | None:
    """How deep into the square, as a fraction of it, the ink begins on
    ``side`` at ``along`` of the way from the side's start to its end.

    Between two measured lines the depth is interpolated, unless they differ
    by more than a step, where the nearer line's depth is the drawn one. A
    line that meets no ink -- the gap between two parts of a mark -- borrows
    the shallower of its nearest measured neighbours, so a link there still
    ends beside the drawing. None when the icon has no edges or nothing is
    near.
    """
    if not code or side not in SIDES:
        return None
    parts = code.split("|")
    if len(parts) != len(SIDES):
        return None
    line = parts[SIDES.index(side)]
    count = len(line)
    if count < 2:
        return None

    def level(index: int) -> float | None:
        # A line whose ink begins past the middle of the square is no seat
        # either: it slides, or the point stays on the box's own edge.
        if index < 0 or index >= count or line[index] == EDGE_NONE:
            return None
        found = EDGE_LEVELS.find(line[index])
        return None if found < 0 or found / 64 > EDGE_MAX_DEPTH else found / 64

    position = min(1.0, max(0.0, along)) * (count - 1)
    low = int(position)
    high = min(low + 1, count - 1)
    a, b = level(low), level(high)
    depth: float | None
    if a is not None and b is not None:
        if abs(a - b) > EDGE_STEP:
            depth = a if position - low < 0.5 else b
        else:
            depth = a + (b - a) * (position - low)
    elif a is not None:
        depth = a
    elif b is not None:
        depth = b
    else:
        depth = None
        for step in range(1, EDGE_REACH + 1):
            near = [value for value in (level(low - step), level(high + step)) if value is not None]
            if near:
                depth = min(near)
                break
        if depth is None:
            return None
    return min(depth, EDGE_MAX_DEPTH)


def inked_along(code: str | None, side: str, along: float) -> float:
    """``along``, or the nearest measured line to it whose ink begins short
    of the square's middle. A link that falls on a gap in a mark -- between
    two people, beside a wifi arc -- has no drawing on its own line to
    touch, so it moves along the side to the drawing nearest it."""
    if not code or side not in SIDES:
        return along
    parts = code.split("|")
    if len(parts) != len(SIDES):
        return along
    line = parts[SIDES.index(side)]
    count = len(line)
    if count < 2:
        return along

    def depth_at(index: int) -> float | None:
        found = EDGE_LEVELS.find(line[index]) if line[index] != EDGE_NONE else -1
        return found / 64 if 0 <= found <= 64 * EDGE_MAX_DEPTH else None

    def inked(index: int) -> bool:
        return depth_at(index) is not None

    position = min(1.0, max(0.0, along)) * (count - 1)
    low = int(position)
    high = min(low + 1, count - 1)
    here, there = depth_at(low), depth_at(high)
    if here is not None and there is not None:
        # Between two lines a step apart -- the end of a bar beside a mast --
        # the point sits on the nearer line itself, so its seat is that
        # line's own edge and not a depth borrowed from beside the air.
        if abs(here - there) > EDGE_STEP:
            return (low if position - low < 0.5 else high) / (count - 1)
        return along
    lines = [index for index in range(count) if inked(index)]
    if not lines:
        return along
    nearest = min(lines, key=lambda index: (abs(index - position), index))
    return nearest / (count - 1)


def usable_middle(code: str | None, side: str) -> float | None:
    """The middle of the stretch of ``side`` the device's drawing reaches --
    from the first to the last line whose first ink is the device, short of
    the square's middle -- as a fraction along the side; None when no line
    is usable. A side's one connection point sits there, so a link meets the
    middle of a router's body, not the middle of its body and arcs together."""
    if not code or side not in SIDES:
        return None
    parts = code.split("|")
    if len(parts) != len(SIDES):
        return None
    line = parts[SIDES.index(side)]
    count = len(line)
    usable = [
        index
        for index in range(count)
        if line[index] != EDGE_NONE and 0 <= EDGE_LEVELS.find(line[index]) <= 64 * EDGE_MAX_DEPTH
    ]
    if count < 2 or not usable:
        return None
    # On a measured line, so the seat is that line's exact depth rather than
    # a blend of two neighbours on a curve. A half rounds to the later line.
    return (usable[0] + usable[-1] + 1) // 2 / (count - 1)
