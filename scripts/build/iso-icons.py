#!/usr/bin/env python3
"""Draw the isometric on-premises icon set from a spec table.

Every icon is composed from a few isometric primitives -- a box, a slab, a
drum, a rack, a decal on a face -- in the 2:1 projection cloud-diagram tools
draw, lit from the upper left so the top face is brightest and the right
face darkest, standing on a soft ground shadow. Equipment has the fronts it
has in a machine room: charcoal bezels with drive sleds and status lights,
port rows with link lights, display panels, vents. Each icon is painted by
family -- compute, storage, network, security, facility, client, platform,
operations, industrial -- on its top face and details, so a page of them
reads as one system.

The table below is the whole set. Adding an item is adding a line; the
recipes are the vocabulary. Run from the repository root::

    PYTHONPATH=src python scripts/build/iso-icons.py --out <dir>   # draw into a folder
    PYTHONPATH=src python scripts/build/iso-icons.py --sheet <png>  # also a contact sheet
    PYTHONPATH=src python scripts/build/iso-icons.py --install      # the flat kit, into the on-prem library

The set the library ships is the same table rendered in real 3D by
``scripts/build/iso-render.py`` (three.js in headless Chromium); the flat
drawing here is the recipes' reference and the fallback when no browser
is to hand. ``install()`` writes a set into the Local & On-Premises icon
collection as the ``iso-<family>`` categories, records every icon in that
collection's catalog and maps the categories for the sidebar; then run
``scripts/tools/generate-nodes.py``, ``scripts/inventory/build.py`` and
``scripts/tools/ink-profiles.py``.

Original drawings, MIT like the rest of the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(
    0,
    str(
        next(
            path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir()
        )
        / "src"
    ),
)
from infragram.iso3d.vocabulary import FAMILY_COLOURS

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
LF = chr(10)

# 2:1 isometric: x runs right and down, y runs left and down, z runs up.
COS, SIN = math.cos(math.radians(30)), 0.5
SIZE = 64  # the icon square
MARGIN = 2.5  # air kept inside the square on every side
LINE = "#2b3240"  # outline ink, the same on every family
LINE_W = 0.7
GREEN, AMBER, RED = "#22c55e", "#f59e0b", "#ef4444"  # status lights
CHASSIS = ("#3d4556", "#252b36")  # a charcoal bezel, lit top to bottom
CHASSIS_SIDE = ("#4d566a", "#343c4b")
METAL = ("#f1f3f6", "#dfe4ea")
METAL_SIDE = ("#cfd5dd", "#b8c0cb")


def project(x: float, y: float, z: float) -> tuple[float, float]:
    return ((x - y) * COS, (x + y) * SIN - z)


def mix(colour: str, other: str, amount: float) -> str:
    """``amount`` of ``other`` blended into ``colour``."""
    a = tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(other[i : i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(a[i] + (b[i] - a[i]) * amount):02x}" for i in range(3))


@dataclass(frozen=True)
class Family:
    id: str
    colour: str

    @property
    def top(self) -> tuple[str, str]:
        """The lit top face: the family tint, a touch brighter at the back."""
        return (mix(self.colour, "#ffffff", 0.7), mix(self.colour, "#ffffff", 0.54))

    @property
    def left(self) -> tuple[str, str]:
        return ("#f7f9fb", "#e6eaf0")

    @property
    def right(self) -> tuple[str, str]:
        return ("#d6dce4", "#c2c9d3")

    @property
    def accent(self) -> str:
        return self.colour

    @property
    def deep(self) -> str:
        return mix(self.colour, "#000000", 0.3)

    @property
    def pale(self) -> str:
        return mix(self.colour, "#ffffff", 0.45)


FAMILIES = {name: Family(name, colour) for name, colour in FAMILY_COLOURS.items()}

Paint = str | tuple[str, str]  # a flat colour, or (lit, shaded) for a gradient


def fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


class Drawing:
    """Collects SVG elements drawn in world space and their screen extent."""

    def __init__(self, ident: str = "iso") -> None:
        # Gradient ids carry the icon's own id: the static renderer inlines
        # every icon into one document, where a bare "g1" would collide.
        self.ident = ident
        self.parts: list[str] = []
        self.under: list[str] = []  # shadows, drawn behind everything
        self.defs: dict[tuple, str] = {}
        self.xs: list[float] = []
        self.ys: list[float] = []

    # -- paint ----------------------------------------------------------------
    def fill(self, paint: Paint, direction: str = "v") -> str:
        """A fill attribute value: the colour, or a gradient registered once
        per (lit, shaded, direction) and referenced by id."""
        if isinstance(paint, str):
            return paint
        key = (*paint, direction)
        if key not in self.defs:
            self.defs[key] = f"{self.ident}-g{len(self.defs) + 1}"
        return f"url(#{self.defs[key]})"

    def _defs(self) -> str:
        out = []
        for (lit, shaded, direction), gid in self.defs.items():
            x2, y2 = ("0", "1") if direction == "v" else ("1", "0")
            out.append(
                f'<linearGradient id="{gid}" x1="0" y1="0" x2="{x2}" y2="{y2}">'
                f'<stop offset="0" stop-color="{lit}"/><stop offset="1" stop-color="{shaded}"/></linearGradient>'
            )
        return f"<defs>{''.join(out)}</defs>" if out else ""

    def _track(self, points) -> None:
        for px, py in points:
            self.xs.append(px)
            self.ys.append(py)

    def _poly(
        self, corners, paint: Paint, direction: str = "v", stroke: str = LINE, width: float = LINE_W
    ) -> None:
        points = [project(*c) for c in corners]
        self._track(points)
        joined = " ".join(f"{fmt(px)},{fmt(py)}" for px, py in points)
        self.parts.append(
            f'<polygon points="{joined}" fill="{self.fill(paint, direction)}" stroke="{stroke}" '
            f'stroke-width="{fmt(width)}" stroke-linejoin="round"/>'
        )

    # -- primitives ---------------------------------------------------------
    def shadow(self, x: float, y: float, w: float, d: float) -> None:
        """The soft shadow an object throws on the floor. Faint enough that
        the ink measurement, which counts alpha above a quarter, ignores it."""
        cx, cy = project(x + w / 2, y + d / 2, 0)
        rx, ry = (w + d) * COS / 2 * 1.12 + 1, (w + d) * SIN / 2 * 1.12 + 0.8
        self.under.append(
            f'<ellipse cx="{fmt(cx + 0.6)}" cy="{fmt(cy + 0.9)}" rx="{fmt(rx)}" ry="{fmt(ry)}" '
            f'fill="#1f2937" fill-opacity="0.16"/>'
        )
        self._track([(cx - rx, cy), (cx + rx, cy), (cx, cy + ry + 0.9)])

    def box(
        self,
        x: float,
        y: float,
        z: float,
        w: float,
        d: float,
        h: float,
        fam: Family,
        top: Paint | None = None,
        left: Paint | None = None,
        right: Paint | None = None,
        shadow: bool | None = None,
    ) -> None:
        x1, y1, z1 = x + w, y + d, z + h
        if shadow if shadow is not None else z == 0:
            self.shadow(x, y, w, d)
        self._poly([(x, y, z1), (x1, y, z1), (x1, y1, z1), (x, y1, z1)], top or fam.top, "v")
        self._poly([(x, y1, z1), (x1, y1, z1), (x1, y1, z), (x, y1, z)], left or fam.left, "v")
        self._poly([(x1, y, z1), (x1, y1, z1), (x1, y1, z), (x1, y, z)], right or fam.right, "v")
        # a bevel: the lit front edges of the top face catch the light
        a, b, c = project(x, y1, z1), project(x1, y1, z1), project(x1, y, z1)
        self.parts.append(
            f'<path d="M{fmt(a[0])},{fmt(a[1])} L{fmt(b[0])},{fmt(b[1])} L{fmt(c[0])},{fmt(c[1])}" '
            f'fill="none" stroke="#ffffff" stroke-opacity="0.55" stroke-width="0.6" stroke-linejoin="round"/>'
        )

    def slab(
        self, x: float, y: float, z: float, w: float, d: float, fam: Family, h: float = 1.6, **kw
    ) -> None:
        self.box(x, y, z, w, d, h, fam, **kw)

    def cylinder(
        self,
        cx: float,
        cy: float,
        z: float,
        r: float,
        h: float,
        fam: Family,
        top: Paint | None = None,
        body: Paint | None = None,
        shadow: bool | None = None,
    ) -> None:
        """A drum standing on the ground: an ellipse on top, a body lit from the left."""
        if shadow if shadow is not None else z == 0:
            self.shadow(cx - r, cy - r, 2 * r, 2 * r)
        ox, oy = project(cx, cy, z + h)
        rx, ry = r * COS * math.sqrt(2), r * SIN * math.sqrt(2)
        bx, by = project(cx, cy, z)
        body_paint = body or ("#f7f9fb", "#b9c1cc")
        self.parts.append(
            f'<path d="M{fmt(ox - rx)},{fmt(oy)} L{fmt(bx - rx)},{fmt(by)} A{fmt(rx)},{fmt(ry)} 0 0 0 {fmt(bx + rx)},{fmt(by)} '
            f'L{fmt(ox + rx)},{fmt(oy)} Z" fill="{self.fill(body_paint, "h")}" stroke="{LINE}" stroke-width="{fmt(LINE_W)}" stroke-linejoin="round"/>'
        )
        self.parts.append(
            f'<ellipse cx="{fmt(ox)}" cy="{fmt(oy)}" rx="{fmt(rx)}" ry="{fmt(ry)}" '
            f'fill="{self.fill(top or fam.top, "v")}" stroke="{LINE}" stroke-width="{fmt(LINE_W)}"/>'
        )
        self.parts.append(
            f'<ellipse cx="{fmt(ox)}" cy="{fmt(oy)}" rx="{fmt(rx - 0.4)}" ry="{fmt(ry - 0.3)}" '
            f'fill="none" stroke="#ffffff" stroke-opacity="0.5" stroke-width="0.5"/>'
        )
        self._track([(ox - rx, oy - ry), (ox + rx, oy), (bx - rx, by), (bx + rx, by + ry)])

    def stack(
        self, cx: float, cy: float, z: float, r: float, h: float, count: int, fam: Family
    ) -> None:
        """Drums stacked with a small gap: a database, a disk stack."""
        gap = 0.8
        each = (h - gap * (count - 1)) / count
        for i in range(count):
            self.cylinder(cx, cy, z + i * (each + gap), r, each, fam, shadow=i == 0 and z == 0)

    # -- decals: shapes drawn flat on a face ---------------------------------
    def _face_matrix(self, face: str, x: float, y: float, z: float) -> str:
        """The transform that lays a local (a, b) drawing on a face whose
        origin is the world point (x, y, z): the top face (a along x, b along
        y), the left face (+y side: a along x, b downward) or the right face
        (+x side: a along y, b downward)."""
        ex, ey = project(x, y, z)
        if face == "top":
            m = (COS, SIN, -COS, SIN)
        elif face == "left":
            m = (COS, SIN, 0, 1)
        else:
            m = (-COS, SIN, 0, 1)
        return f"matrix({fmt(m[0])} {fmt(m[1])} {fmt(m[2])} {fmt(m[3])} {fmt(ex)} {fmt(ey)})"

    def decal(self, face: str, x: float, y: float, z: float, svg: str) -> None:
        self.parts.append(f'<g transform="{self._face_matrix(face, x, y, z)}">{svg}</g>')

    def rect_on(
        self,
        face: str,
        x: float,
        y: float,
        z: float,
        a: float,
        b: float,
        w: float,
        h: float,
        fill: Paint,
        stroke: str = "none",
        rx: float = 0.0,
        opacity: float = 1.0,
    ) -> None:
        extra = f' fill-opacity="{fmt(opacity)}"' if opacity < 1 else ""
        self.decal(
            face,
            x,
            y,
            z,
            f'<rect x="{fmt(a)}" y="{fmt(b)}" width="{fmt(w)}" height="{fmt(h)}" '
            f'rx="{fmt(rx)}" fill="{self.fill(fill, "v")}" stroke="{stroke}" stroke-width="0.5"{extra}/>',
        )

    def dot_on(
        self, face: str, x: float, y: float, z: float, a: float, b: float, r: float, fill: str
    ) -> None:
        self.decal(
            face, x, y, z, f'<circle cx="{fmt(a)}" cy="{fmt(b)}" r="{fmt(r)}" fill="{fill}"/>'
        )

    def led(
        self, face: str, x: float, y: float, z: float, a: float, b: float, colour: str = GREEN
    ) -> None:
        """A status light: a bright dot with a faint glow."""
        self.decal(
            face,
            x,
            y,
            z,
            f'<circle cx="{fmt(a)}" cy="{fmt(b)}" r="0.9" fill="{colour}" fill-opacity="0.35"/>'
            f'<circle cx="{fmt(a)}" cy="{fmt(b)}" r="0.45" fill="{colour}"/>',
        )

    def lines_on(
        self,
        face: str,
        x: float,
        y: float,
        z: float,
        a: float,
        b: float,
        length: float,
        count: int,
        gap: float,
        colour: str,
        vertical: bool = False,
        width: float = 0.6,
    ) -> None:
        for i in range(count):
            if vertical:
                d = f"M{fmt(a + i * gap)},{fmt(b)} v{fmt(length)}"
            else:
                d = f"M{fmt(a)},{fmt(b + i * gap)} h{fmt(length)}"
            self.decal(
                face,
                x,
                y,
                z,
                f'<path d="{d}" stroke="{colour}" stroke-width="{fmt(width)}" '
                f'stroke-linecap="round" fill="none"/>',
            )

    def vents(
        self,
        face: str,
        x: float,
        y: float,
        z: float,
        a: float,
        b: float,
        w: float,
        h: float,
        colour: str = "#1c212b",
    ) -> None:
        """A grille: rows of short dark slots."""
        rows, cols = max(1, int(h / 1.4)), max(1, int(w / 1.6))
        for r in range(rows):
            for c in range(cols):
                self.rect_on(
                    face, x, y, z, a + c * 1.6, b + r * 1.4, 1.0, 0.7, colour, rx=0.2, opacity=0.8
                )

    def glyph_on(
        self,
        face: str,
        x: float,
        y: float,
        z: float,
        a: float,
        b: float,
        size: float,
        paths: str,
        colour: str,
        width: float = 0.9,
    ) -> None:
        """A 24-unit line glyph laid on a face at (a, b), scaled to ``size``
        world units; ``width`` is the stroke in world units too, so a glyph
        keeps the hairline weight of the rest of the drawing at any size."""
        k = size / 24
        self.decal(
            face,
            x,
            y,
            z,
            f'<g transform="translate({fmt(a)} {fmt(b)}) scale({fmt(k)})" fill="none" stroke="{colour}" '
            f'stroke-width="{fmt(width / k)}" stroke-linecap="round" stroke-linejoin="round">{paths}</g>',
        )

    # -- output -------------------------------------------------------------
    def svg(self) -> str:
        left, right = min(self.xs), max(self.xs)
        top, bottom = min(self.ys), max(self.ys)
        width, height = right - left, bottom - top
        scale = min((SIZE - 2 * MARGIN) / width, (SIZE - 2 * MARGIN) / height)
        tx = (SIZE - width * scale) / 2 - left * scale
        ty = (SIZE - height * scale) / 2 - top * scale
        body = "".join(self.under) + "".join(self.parts)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" aria-hidden="true">{self._defs()}'
            f'<g transform="translate({fmt(tx)} {fmt(ty)}) scale({fmt(scale)})">{body}</g></svg>'
        )


# -- the small line glyphs used as decals (24-unit, original) -----------------
from infragram.iso3d.vocabulary import GLYPHS  # noqa: E402  the badge glyphs live with the renderer


# -- shared front panels ----------------------------------------------------------
def bezel(
    d: Drawing,
    x: float,
    y: float,
    z: float,
    w: float,
    dp: float,
    h: float,
    fam: Family,
    top: Paint | None = None,
) -> None:
    """A rack-mount chassis: family-tinted lid, charcoal front, shaded side."""
    d.box(x, y, z, w, dp, h, fam, top=top or fam.top, left=CHASSIS, right=CHASSIS_SIDE)
    # rack ears: the flanges either end of the front
    d.rect_on("left", x, y + dp, z + h, 0, 0.3, 0.9, h - 0.6, "#1a1f29", rx=0.15)
    d.rect_on("left", x, y + dp, z + h, w - 0.9, 0.3, 0.9, h - 0.6, "#1a1f29", rx=0.15)
    d.vents("right", x + w, y, z + h, 1.6, 1.0, dp - 3.2, h - 2.0, "#1c212b")


def sled(
    d: Drawing,
    x: float,
    y: float,
    z: float,
    a: float,
    b: float,
    w: float,
    h: float,
    fam: Family,
    light: str = GREEN,
) -> None:
    """A hot-swap drive sled on a front: grey face, family latch, a light."""
    d.rect_on("left", x, y, z, a, b, w, h, ("#cfd5dd", "#aeb6c2"), rx=0.25)
    d.rect_on("left", x, y, z, a + 0.25, b + 0.25, 0.7, h - 0.5, fam.accent, rx=0.15)
    d.led("left", x, y, z, a + w - 0.75, b + h / 2, light)


def ports(
    d: Drawing,
    x: float,
    y: float,
    z: float,
    a: float,
    b: float,
    count: int,
    fam: Family,
    gap: float = 2.5,
) -> None:
    """A row of RJ45 ports with their link lights, and an SFP pair at the end."""
    for i in range(count):
        d.rect_on("left", x, y, z, a + i * gap, b + 0.9, 1.8, 1.5, ("#e6eaf0", "#c9d0da"), rx=0.2)
        d.dot_on("left", x, y, z, a + i * gap + 0.45, b + 0.45, 0.28, GREEN if i % 3 else AMBER)
        d.dot_on("left", x, y, z, a + i * gap + 1.35, b + 0.45, 0.28, GREEN)
    sx = a + count * gap + 0.4
    for j in range(2):
        d.rect_on("left", x, y, z, sx + j * 2.4, b + 0.8, 2.0, 1.7, "#7c8796", rx=0.2)
        d.rect_on("left", x, y, z, sx + j * 2.4 + 0.3, b + 1.1, 1.4, 1.1, "#3d4556", rx=0.1)


def screen(
    d: Drawing,
    face: str,
    x: float,
    y: float,
    z: float,
    a: float,
    b: float,
    w: float,
    h: float,
    fam: Family,
) -> None:
    """A lit display with a soft reflection."""
    d.rect_on(face, x, y, z, a, b, w, h, ("#0b1220", "#111a2e"), rx=0.4)
    d.rect_on(
        face,
        x,
        y,
        z,
        a + 0.3,
        b + 0.3,
        w - 0.6,
        h - 0.6,
        (mix(fam.colour, "#ffffff", 0.15), fam.deep),
        rx=0.3,
    )
    d.rect_on(
        face,
        x,
        y,
        z,
        a + 0.6,
        b + 0.6,
        (w - 1.2) * 0.45,
        (h - 1.2) * 0.5,
        "#ffffff",
        rx=0.3,
        opacity=0.14,
    )


# -- recipes: how each kind of device is drawn ----------------------------------
def r_server(
    d: Drawing, fam: Family, units: int = 2, drives: int = 4, rows: int = 0, badge: bool = True
) -> None:
    """A rack server: a charcoal bezel with drive sleds and status lights."""
    w, dp, h = 24, 15, 2.4 * units + 1.2
    bezel(d, 0, 0, 0, w, dp, h, fam)
    for u in range(rows or units):
        b = 0.9 + u * 2.4
        for i in range(drives):
            sled(d, 0, dp, h, 1.5 + i * 4.3, b, 3.8, 1.8, fam)
    d.led("left", 0, dp, h, w - 1.7, 1.1, GREEN)
    d.led("left", 0, dp, h, w - 1.7, 2.3, fam.accent)
    d.rect_on("left", 0, dp, h, 1.3, h - 1.0, w - 2.6, 0.35, fam.accent, rx=0.15, opacity=0.9)


def r_blade(d: Drawing, fam: Family) -> None:
    """One half-height blade on its edge: slim, two sleds up top, latch handles."""
    w, dp, h = 4, 20, 16
    d.box(0, 0, 0, w, dp, h, fam, top=fam.top, left=CHASSIS, right=CHASSIS_SIDE)
    for i in range(2):
        sled(d, 0, dp, h, 0.6, 1.4 + i * 2.6, 2.8, 2.0, fam)
    d.rect_on("left", 0, dp, h, 0.5, 0.2, w - 1.0, 0.9, fam.accent, rx=0.2)
    d.rect_on("left", 0, dp, h, 0.5, h - 1.1, w - 1.0, 0.9, fam.accent, rx=0.2)
    d.vents("left", 0, dp, h, 0.8, 7.5, w - 1.6, 4.5, "#1c212b")
    d.led("left", 0, dp, h, w - 1.0, 13.2, GREEN)
    d.led("left", 0, dp, h, w - 1.0, 12.2, fam.accent)


def r_micro(d: Drawing, fam: Family) -> None:
    """A micro server: a short cube of a chassis with two sleds and a fan."""
    w, dp, h = 12, 14, 10
    d.box(0, 0, 0, w, dp, h, fam, left=("#eef1f5", "#d5dbe3"), right=("#c9d0da", "#aeb6c2"))
    d.rect_on("left", 0, dp, h, 1.0, 1.0, w - 2.0, h - 2.0, CHASSIS, rx=0.4)
    for i in range(2):
        sled(d, 0, dp, h, 1.6 + i * 4.6, 5.8, 4.2, 2.2, fam)
    d.vents("left", 0, dp, h, 6.5, 1.6, 4.0, 3.2, "#3d4556")
    ports(d, 0, dp, h, 1.6, 1.4, 1, fam, gap=2.5)
    d.rect_on("left", 0, dp, h, 1.2, h - 1.5, w - 2.4, 0.35, fam.accent, rx=0.15, opacity=0.9)
    d.led("left", 0, dp, h, w - 1.8, 8.6, GREEN)


def r_tower(d: Drawing, fam: Family) -> None:
    w, dp, h = 10, 17, 22
    d.box(0, 0, 0, w, dp, h, fam, left=("#eef1f5", "#d5dbe3"), right=("#c9d0da", "#aeb6c2"))
    d.rect_on("left", 0, dp, h, 1.2, 1.2, w - 2.4, 6.5, CHASSIS, rx=0.4)
    for i in range(2):
        d.rect_on(
            "left", 0, dp, h, 1.8, 1.8 + i * 2.6, w - 3.6, 1.9, ("#cfd5dd", "#aeb6c2"), rx=0.2
        )
        d.led("left", 0, dp, h, w - 2.6, 2.75 + i * 2.6, GREEN if i else AMBER)
    d.rect_on("left", 0, dp, h, 1.2, 8.2, w - 2.4, 0.35, fam.accent, rx=0.15)
    d.vents("left", 0, dp, h, 1.6, 11, w - 3.2, 8, "#b8c0cb")
    d.dot_on("left", 0, dp, h, w / 2, h - 2.2, 0.75, "#1a1f29")
    d.led("left", 0, dp, h, w / 2, h - 2.2, GREEN)


def r_cluster(d: Drawing, fam: Family, count: int = 3, unit: str = "server") -> None:
    """Stacked units of one kind on a plate: the nodes of one system."""
    w, dp, uh, gap = 24, 15, 3.6 if unit != "gpu" else 6.0, 0.8
    d.slab(
        -1,
        -1,
        0,
        w + 2,
        dp + 2,
        fam,
        h=0.6,
        top=("#5b6470", "#3d4450"),
        left=("#4a525d", "#3d4450"),
        right=("#2f353e", "#262b33"),
    )
    for i in range(count):
        z = 0.6 + i * (uh + gap)
        bezel(d, 0, 0, z, w, dp, uh, fam)
        if unit in ("server", "gpu"):
            for j in range(4 if unit == "server" else 3):
                sled(d, 0, dp, z + uh, 1.5 + j * 4.3, 0.9, 3.8, 1.8, fam)
        elif unit == "shelf":
            for j in range(6):
                sled(d, 0, dp, z + uh, 1.5 + j * 3.5, 0.9, 3.0, 1.8, fam)
        else:
            ports(d, 0, dp, z + uh, 1.5, 0.4, 6, fam)
        d.led("left", 0, dp, z + uh, w - 1.7, 1.1, GREEN)
    top = 0.6 + count * (uh + gap) - gap
    d.slab(-1, -1, top, w + 2, dp + 2, fam, h=0.5)


def r_fabric(d: Drawing, fam: Family) -> None:
    """Spine-leaf: three leaves on the plate, two spines above."""
    d.slab(
        -1,
        -1,
        0,
        80,
        17,
        fam,
        h=0.6,
        top=("#5b6470", "#3d4450"),
        left=("#4a525d", "#3d4450"),
        right=("#2f353e", "#262b33"),
    )
    x: float
    for x in (0, 27, 54):
        bezel(d, x, 0, 0.6, 24, 15, 3.6, fam)
        ports(d, x, 15, 4.2, 1.2, 0.4, 7, fam, gap=2.4)
    for x in (13.5, 40.5):
        bezel(d, x, 0, 10, 24, 15, 3.6, fam)
        ports(d, x, 15, 13.6, 1.2, 0.4, 7, fam, gap=2.4)


def r_drum_row(d: Drawing, fam: Family, count: int = 3, stack: int = 2) -> None:
    """A database cluster: drum stacks side by side."""
    for i in range(count):
        for k in range(stack):
            d.cylinder(7 + i * 16, 7, k * 6.4, 7, 5.6, fam)


def r_rack_row(d: Drawing, fam: Family, count: int = 3) -> None:
    """A row of closed cabinets, each showing its stack through the door."""
    for i in range(count):
        x = i * 12
        d.box(x, 0, 0, 10, 12, 30, fam, top=fam.top, left=CHASSIS, right=CHASSIS_SIDE)
        for u in range(8):
            d.rect_on(
                "left", x, 12, 30, 1.2, 1.5 + u * 3.4, 7.6, 2.6, ("#4a525d", "#3d4450"), rx=0.2
            )
            d.led("left", x, 12, 30, 8.2, 2.6 + u * 3.4, GREEN)


def r_chassis_switch(d: Drawing, fam: Family, cards: int = 4) -> None:
    """A modular switch: a supervisor on top, line cards of ports below."""
    w, dp, h = 26, 17, 3.2 * (cards + 1) + 1.6
    bezel(d, 0, 0, 0, w, dp, h, fam)
    for i in range(cards + 1):
        b = 0.9 + i * 3.2
        d.rect_on("left", 0, dp, h, 1.2, b, w - 5.4, 2.6, ("#4a525d", "#3d4450"), rx=0.2)
        if i:
            ports(d, 0, dp, h, 1.8, b + 0.2, 7, fam, gap=2.4)
        else:
            for j in range(4):
                d.led("left", 0, dp, h, 3 + j * 1.4, b + 1.3, GREEN if j else AMBER)
    d.vents("left", 0, dp, h, w - 3.6, 0.9, 2.4, h - 1.8, "#1c212b")


def r_drive(d: Drawing, fam: Family, kind: str = "hdd") -> None:
    """A bare drive, label up."""
    w, dp, h = (
        (14, 20, 1.6) if kind == "ssd" else (16, 4.4, 0.6) if kind == "nvme" else (20, 29, 5.2)
    )
    d.box(
        0,
        0,
        0,
        w,
        dp,
        h,
        fam,
        top=CHASSIS if kind != "hdd" else ("#e6eaf0", "#d5dbe3"),
        left=CHASSIS if kind != "hdd" else ("#d9dee6", "#c2c9d3"),
        right=CHASSIS_SIDE if kind != "hdd" else ("#b8c0cb", "#a0a9b6"),
    )
    if kind != "nvme":
        d.rect_on("top", 0, 0, h, 1.4, 3, w - 2.8, dp - 6, ("#f4f6f8", "#e2e6eb"), rx=0.4)
        d.rect_on("top", 0, 0, h, 2, 4, w - 4, 0.8, fam.accent, rx=0.2)
    else:
        d.rect_on("top", 0, 0, h, 1, 0.8, 3, 2.8, "#caa23a", rx=0.2)
        for i in range(3):
            d.rect_on("top", 0, 0, h, 5 + i * 3.4, 0.9, 2.6, 2.6, "#1f242b", rx=0.2)


def r_card(d: Drawing, fam: Family) -> None:
    """An expansion card lying flat: PCB, bracket, heat sink, gold edge."""
    d.box(
        2,
        0,
        0,
        18,
        12,
        0.5,
        fam,
        top=("#2f8a4e", "#1f6b3a"),
        left=("#2f8a4e", "#1f6b3a"),
        right=("#1f6b3a", "#175230"),
    )
    d.box(
        0,
        -1,
        0,
        2,
        15,
        0.8,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(
        8,
        3,
        0.5,
        6,
        6,
        2.2,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.rect_on("top", 2, 0, 0.5, 2, 10.5, 12, 1.2, "#caa23a", rx=0.2)
    d.glyph_on("top", 2, 0, 0.5, 13, 1, 4, GLYPHS["cube"], fam.accent, width=0.7)


def r_sfp(d: Drawing, fam: Family, big: bool = False) -> None:
    w, dp = (7, 24) if big else (6, 20)
    d.box(
        0,
        0,
        0,
        w,
        dp,
        3.2,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.rect_on("top", 0, 0, 3.2, 1, 1, w - 2, 5, "#caa23a", rx=0.2)
    d.rect_on("left", 0, dp, 3.2, 0.5, 0.4, w - 1, 1.2, fam.accent, rx=0.3)


def r_display(d: Drawing, fam: Family, wide: bool = False) -> None:
    w, h = (28, 16) if wide else (18, 11)
    if not wide:
        d.slab(w / 2 - 4, 2, 0, 8, 6, fam, h=0.8, top=("#c9d0da", "#b8c0cb"))
        d.box(
            w / 2 - 0.8,
            4,
            0.8,
            1.6,
            1.2,
            4,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
    d.box(0, 4, 4 if not wide else 3, w, 1.2, h, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    screen(d, "left", 0, 5.2, (4 if not wide else 3) + h, 0.8, 0.8, w - 1.6, h - 1.6, fam)


def r_projector(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        16,
        13,
        5,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.dot_on("left", 0, 13, 5, 12.5, 2.5, 1.8, "#1f242b")
    d.dot_on("left", 0, 13, 5, 12.5, 2.5, 1.1, "#3d4a6b")
    d.vents("left", 0, 13, 5, 1.5, 1.5, 7, 2.5, "#b8c0cb")
    d.led("left", 0, 13, 5, 2, 4.2, GREEN)


def r_dock(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 18, 10, 2.8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    ports(d, 0, 10, 2.8, 1.2, 0.3, 4, fam, gap=2.6)
    d.led("left", 0, 10, 2.8, 16.5, 1.4, GREEN)


def r_pos(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 16, 12, 2.4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(0, 6, 2.4, 16, 1.2, 12, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    screen(d, "left", 0, 7.2, 14.4, 0.8, 0.8, 14.4, 10.4, fam)
    d.box(
        17,
        4,
        0,
        5,
        3,
        6.4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.rect_on("top", 17, 4, 6.4, 0.8, 1.2, 3.4, 0.5, "#1f242b", rx=0.2)


def r_key(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 4, 10, 1, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        0,
        10,
        0,
        4,
        3,
        0.9,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.dot_on("top", 0, 0, 1, 2, 3.2, 1.1, fam.accent)
    d.dot_on("top", 0, 0, 1, 2, 3.2, 0.5, GREEN)


def r_smartcard(d: Drawing, fam: Family) -> None:
    d.slab(
        0,
        0,
        0,
        17,
        11,
        fam,
        h=0.4,
        top=("#f4f6f8", "#e2e6eb"),
        left=("#e6eaf0", "#d5dbe3"),
        right=("#d5dbe3", "#c2c9d3"),
    )
    d.rect_on("top", 0, 0, 0.4, 2, 3.2, 2.8, 2.4, "#caa23a", rx=0.3)
    d.rect_on("top", 0, 0, 0.4, 0, 8.6, 17, 1.6, fam.accent)
    d.glyph_on("top", 0, 0, 0.4, 11, 1.5, 4, GLYPHS["id"], fam.deep, width=0.7)


def r_door(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 22, 8, fam, h=0.6, top=("#c9d0da", "#b8c0cb"))
    d.box(
        1,
        3,
        0.6,
        1.4,
        2,
        24,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(
        17,
        3,
        0.6,
        1.4,
        2,
        24,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(2.4, 3.4, 0.6, 14.6, 1.2, 22.5, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.rect_on("left", 2.4, 4.6, 23.1, 5.5, 4, 3.5, 7, ("#9fb3c8", "#7f93a8"), rx=0.3)
    d.dot_on("left", 2.4, 4.6, 23.1, 12.2, 11.5, 0.5, "#dfe4ea")
    d.box(
        19.2,
        3.6,
        0.6,
        2,
        1,
        4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.led("left", 19.2, 4.6, 4.6, 1, 1.2, GREEN)


def r_tile(d: Drawing, fam: Family, kind: str = "perforated") -> None:
    for x, y in ((0, 0), (18, 0), (0, 18), (18, 18)):
        d.box(
            x,
            y,
            0,
            2,
            2,
            6,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.slab(
        -1,
        -1,
        6,
        22,
        22,
        fam,
        h=1.2,
        top=("#dfe4ea", "#c9d0da") if kind == "perforated" else ("#eef1f5", "#dfe4ea"),
    )
    if kind == "perforated":
        for r in range(5):
            for c in range(5):
                d.dot_on("top", -1, -1, 7.2, 3 + c * 4, 3 + r * 4, 0.7, "#8a94a3")


def r_extinguisher(d: Drawing, fam: Family) -> None:
    d.cylinder(5, 5, 0, 4, 16, fam, body=("#ef4444", "#b91c1c"))
    d.cylinder(5, 5, 16, 1.5, 2.5, fam, body=("#dfe4ea", "#aeb6c2"))
    d.box(4, 4, 18.5, 2, 6, 1, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.rect_on("left", 1, 9, 12, 2, 3, 4, 3, "#f4f6f8", rx=0.3)


def r_tank(d: Drawing, fam: Family) -> None:
    d.slab(
        -2,
        -1,
        0,
        30,
        12,
        fam,
        h=0.8,
        top=("#5b6470", "#3d4450"),
        left=("#4a525d", "#3d4450"),
        right=("#2f353e", "#262b33"),
    )
    d.box(2, 1, 0.8, 4, 8, 3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(20, 1, 0.8, 4, 8, 3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        0,
        0,
        3.8,
        26,
        10,
        9,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.cylinder(6, 5, 12.8, 1.6, 1.6, fam, body=("#dfe4ea", "#aeb6c2"))
    d.rect_on("left", 0, 10, 12.8, 21, 2, 1.2, 6, ("#dbeafe", "#93c5fd"), rx=0.3)
    d.rect_on("left", 0, 10, 12.8, 4, 4.2, 14, 0.7, fam.accent, rx=0.2)


def r_transformer(d: Drawing, fam: Family) -> None:
    d.slab(-1, -1, 0, 20, 14, fam, h=0.8, top=("#5b6470", "#3d4450"))
    d.box(2, 0, 0.8, 14, 12, 15, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for i in range(6):
        d.box(
            0,
            1 + i * 1.8,
            0.8,
            2,
            0.6,
            13,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    for i in range(3):
        d.cylinder(5 + i * 4, 6, 15.8, 1.2, 4.5, fam, body=("#f4f6f8", "#c9d0da"))
    d.rect_on("left", 2, 12, 15.8, 4, 6, 6, 4, "#f4f6f8", rx=0.3)
    d.led("left", 2, 12, 15.8, 12, 3, AMBER)


def r_busway(d: Drawing, fam: Family) -> None:
    d.box(0, 4, 14, 40, 3, 3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for x in (2, 19, 36):
        d.box(
            x,
            5,
            17,
            1,
            1,
            6,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    for x in (8, 26):
        d.box(
            x,
            3,
            10,
            5,
            5,
            4,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.led("left", x, 8, 14, 4, 1.5, GREEN)
    d.rect_on("left", 0, 7, 14, 0, 2.2, 40, 0.5, fam.accent)


def r_cart(d: Drawing, fam: Family, kind: str = "crash") -> None:
    if kind == "agv":
        d.box(0, 0, 1.2, 20, 13, 4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        d.rect_on("left", 0, 13, 5.2, 0.5, 0.5, 19, 0.8, fam.accent, rx=0.3)
        for x in (2, 16):
            d.box(
                x,
                -0.5,
                0,
                2.5,
                1.5,
                1.4,
                fam,
                top=("#1f242b", "#111418"),
                left=("#1f242b", "#111418"),
                right=("#111418", "#06080b"),
                shadow=False,
            )
        d.led("left", 0, 13, 5.2, 18.5, 2.5, GREEN)
        return
    for z in (1.5, 8, 15):
        d.slab(0, 0, z, 18, 12, fam, h=0.8, top=("#dfe4ea", "#c9d0da"))
    for x, y in ((0, 0), (17, 0), (0, 11), (17, 11)):
        d.box(
            x,
            y,
            0,
            1,
            1,
            15.8,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.box(3, 4, 16, 12, 1, 8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    screen(d, "left", 3, 5, 24, 0.8, 0.8, 10.4, 6.4, fam)
    d.box(2, 2, 8.8, 14, 5, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)


def r_motor(d: Drawing, fam: Family) -> None:
    d.slab(-1, -1, 0, 20, 12, fam, h=1, top=("#5b6470", "#3d4450"))
    d.box(0, 1, 1, 16, 8, 8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.cylinder(4, 5, 9, 1.8, 3, fam, body=("#dfe4ea", "#aeb6c2"))
    d.vents("left", 0, 9, 9, 1, 1, 14, 6, "#4d566a")
    d.box(
        16,
        3,
        3,
        4,
        4,
        4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.led("left", 0, 9, 9, 14.5, 1, GREEN)


def r_pedestal(d: Drawing, fam: Family) -> None:
    d.slab(-1, -1, 0, 12, 8, fam, h=0.8, top=("#5b6470", "#3d4450"))
    d.box(
        0,
        0,
        0.8,
        10,
        6,
        30,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.rect_on("left", 0, 6, 30.8, 0, 0, 10, 2.2, fam.accent)
    screen(d, "left", 0, 6, 30.8, 1.2, 5, 7.6, 5, fam)
    d.rect_on("left", 0, 6, 30.8, 3, 16, 4, 6, "#1f242b", rx=0.6)
    d.led("left", 0, 6, 30.8, 8.5, 12.5, GREEN)


def r_valve(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        3,
        3,
        30,
        4,
        4,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(11, 2, 2, 8, 6, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.cylinder(15, 5, 8, 1.6, 4, fam, body=("#4d566a", "#343c4b"))
    d.cylinder(15, 5, 12, 4, 1, fam, body=(fam.accent, fam.deep))
    for x in (1, 27):
        d.box(x, 3.5, 0, 2, 3, 3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False)


def r_robot(d: Drawing, fam: Family) -> None:
    d.cylinder(8, 8, 0, 7, 2, fam, body=("#4d566a", "#343c4b"))
    d.cylinder(8, 8, 2, 4.5, 4, fam)
    d.box(6, 6, 6, 4, 4, 12, fam)
    d.box(6, 6, 18, 14, 4, 3.5, fam)
    d.box(17, 6.5, 12, 3, 3, 9.5, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        16.5,
        6,
        10,
        4,
        4,
        2,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )


def r_conveyor(d: Drawing, fam: Family) -> None:
    for x in (2, 32):
        d.box(
            x, 1, 0, 1.5, 1.5, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False
        )
        d.box(
            x, 9, 0, 1.5, 1.5, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False
        )
    d.box(0, 0, 6, 36, 11, 2, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.lines_on("top", 0, 0, 8, 1.5, 1, 9, 12, 2.8, "#aeb6c2", width=0.6)
    d.box(
        8,
        2.5,
        8,
        6,
        6,
        5,
        fam,
        top=("#e2c99b", "#c8a16a"),
        left=("#d6b585", "#b8905c"),
        right=("#b8905c", "#9a7648"),
    )
    d.box(
        22,
        2.5,
        8,
        6,
        6,
        5,
        fam,
        top=("#e2c99b", "#c8a16a"),
        left=("#d6b585", "#b8905c"),
        right=("#b8905c", "#9a7648"),
    )


def r_solar(d: Drawing, fam: Family) -> None:
    for x in (0, 16):
        d.box(x, 0, 0, 2, 2, 8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False)
        d.box(x, 14, 0, 2, 2, 3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False)
    d.slab(
        -1,
        -1,
        8,
        34,
        18,
        fam,
        h=1.2,
        top=("#1e3a8a", "#0f2a52"),
        left=("#1e3a8a", "#0f2a52"),
        right=("#0f2a52", "#0a1c38"),
    )
    d.lines_on("top", -1, -1, 9.2, 1, 3, 32, 4, 3.6, "#dfe4ea", width=0.4)
    d.box(30, 12, 0, 4, 3, 5, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.led("left", 30, 15, 5, 3, 1.5, GREEN)


def _plate(d: Drawing, fam: Family, w: float, dp: float, dark: bool = False) -> None:
    d.slab(
        -1,
        -1,
        0,
        w,
        dp,
        fam,
        h=0.6,
        top=("#5b6470", "#3d4450") if dark else ("#c9cfd6", "#b3bac3"),
        left=("#4a525d", "#3d4450") if dark else ("#bfc5cc", "#a9b0b9"),
        right=("#2f353e", "#262b33") if dark else ("#9aa1aa", "#858c95"),
    )


def _chimney(d: Drawing, fam: Family, x: float, y: float, h: float) -> None:
    d.cylinder(x, y, 0.6, 1.6, h, fam, body=("#dfe4ea", "#aeb6c2"))
    d.cylinder(x, y, h + 0.6, 1.5, 1.2, fam, body=("#ef4444", "#b91c1c"))


def _tower(d: Drawing, fam: Family, x: float, y: float) -> None:
    d.cylinder(x, y, 0.6, 7, 22, fam, body=("#dfe4ea", "#aeb6c2"))
    d.cylinder(x, y, 22.6, 5.5, 2, fam, body=("#f4f6f8", "#c9d0da"))


def r_plant(d: Drawing, fam: Family, kind: str = "coal") -> None:
    _plate(d, fam, 62, 42)
    if kind == "nuclear":
        d.cylinder(14, 14, 0.6, 7.5, 12, fam, body=("#dfe4ea", "#aeb6c2"))
        d.cylinder(14, 14, 12.6, 6, 4, fam, body=("#f4f6f8", "#c9d0da"))
        d.box(
            28,
            6,
            0.6,
            16,
            12,
            8,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        _tower(d, fam, 50, 30)
        _tower(d, fam, 36, 32)
    elif kind == "gas":
        d.box(
            4,
            6,
            0.6,
            30,
            12,
            9,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(
            36,
            8,
            0.6,
            8,
            8,
            6,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(2, 22, 0.6, 10, 10, 13, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        _chimney(d, fam, 26, 28, 24)
    elif kind == "biomass":
        d.box(
            4,
            6,
            0.6,
            20,
            14,
            12,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.cylinder(36, 12, 0.6, 4, 16, fam, body=("#dfe4ea", "#aeb6c2"))
        _chimney(d, fam, 8, 28, 26)
    elif kind == "geo":
        d.box(
            4,
            6,
            0.6,
            18,
            12,
            7,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        for x, y in ((30, 10), (40, 18), (34, 28)):
            d.box(
                x,
                y,
                0.6,
                2,
                2,
                4,
                fam,
                top=("#dfe4ea", "#c2c9d3"),
                left=("#c9d0da", "#aeb6c2"),
                right=("#b8c0cb", "#a0a9b6"),
            )
            d.cylinder(x + 1, y + 1, 4.6, 2, 1.5, fam, body=("#ffffff", "#e6eaf0"))
    else:
        d.box(
            4,
            6,
            0.6,
            22,
            14,
            14,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(
            30,
            8,
            0.6,
            12,
            12,
            8,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        _chimney(d, fam, 8, 28, 30)
        _chimney(d, fam, 14, 28, 30)
        _tower(d, fam, 48, 28)


def r_reactor(d: Drawing, fam: Family, kind: str = "unit") -> None:
    _plate(d, fam, 36, 28)
    if kind == "smr":
        d.box(
            4,
            6,
            0.6,
            12,
            12,
            5,
            fam,
            top=("#c9cfd6", "#b3bac3"),
            left=("#bfc5cc", "#a9b0b9"),
            right=("#9aa1aa", "#858c95"),
        )
        d.cylinder(10, 12, 5.6, 3.2, 6, fam, body=("#dfe4ea", "#aeb6c2"))
        d.box(
            22,
            8,
            0.6,
            8,
            7,
            5,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
    else:
        d.cylinder(12, 12, 0.6, 7.5, 13, fam, body=("#dfe4ea", "#aeb6c2"))
        d.cylinder(12, 12, 13.6, 6, 4, fam, body=("#f4f6f8", "#c9d0da"))
        d.box(
            24,
            4,
            0.6,
            10,
            10,
            9,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        _chimney(d, fam, 30, 20, 20)


def r_dam(d: Drawing, fam: Family, kind: str = "hydro") -> None:
    if kind == "pumped":
        d.cylinder(12, 12, 0, 14, 12, fam, body=("#8fae7c", "#6b8f5a"))
        d.cylinder(12, 12, 12, 7, 2, fam, body=("#c9cfd6", "#b3bac3"))
        d.cylinder(12, 12, 14, 6.5, 0.4, fam, body=("#60a5fa", "#2b7fc4"))
        d.box(
            30,
            20,
            0,
            10,
            8,
            6,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(
            14,
            4,
            12,
            1.2,
            1.2,
            1,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    else:
        d.slab(
            0,
            0,
            0,
            40,
            14,
            fam,
            h=18,
            top=("#c9cfd6", "#b3bac3"),
            left=("#bfc5cc", "#a9b0b9"),
            right=("#9aa1aa", "#858c95"),
        )
        d.slab(
            0,
            14,
            0,
            40,
            20,
            fam,
            h=17,
            top=("#60a5fa", "#2b7fc4"),
            left=("#3b82f6", "#1d4ed8"),
            right=("#2563eb", "#1e40af"),
        )
        d.box(
            10,
            -8,
            0,
            20,
            8,
            6,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        for x in (4, 20, 34):
            d.box(
                x,
                -1,
                6,
                1.4,
                1.4,
                12,
                fam,
                top=("#dfe4ea", "#c2c9d3"),
                left=("#c9d0da", "#aeb6c2"),
                right=("#b8c0cb", "#a0a9b6"),
                shadow=False,
            )


def r_wind(d: Drawing, fam: Family, count: int = 1) -> None:
    xs = (10,) if count == 1 else (4, 16, 28)
    if count > 1:
        _plate(d, fam, 40, 26)
    for x in xs:
        d.cylinder(x, 10, 0.6, 0.9, 20, fam, body=("#f4f6f8", "#c9d0da"))
        d.box(
            x - 1.6,
            8.5,
            20.6,
            3.2,
            3,
            2,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.rect_on("left", x - 1.6, 11.5, 22.6, 1.4, -8, 0.5, 10, "#eef1f5", rx=0.25)
        d.rect_on("left", x - 1.6, 11.5, 22.6, -6, 0.6, 7, 0.5, "#eef1f5", rx=0.25)
        d.rect_on("left", x - 1.6, 11.5, 22.6, 2.4, 0.6, 7, 0.5, "#eef1f5", rx=0.25)


def r_solar_farm(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 48, 34)
    for r in range(3):
        for c in range(3):
            d.slab(
                2 + c * 15,
                2 + r * 10,
                2.6,
                13,
                7,
                fam,
                h=0.5,
                top=("#1e3a8a", "#0f2a52"),
                left=("#1e3a8a", "#0f2a52"),
                right=("#0f2a52", "#0a1c38"),
            )
    d.box(40, 28, 0.6, 4, 3, 3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)


def r_fuelcell(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 12, 9, 15, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.rect_on("left", 0, 9, 15, 1, 4, 6, 9, ("#9fb3c8", "#7f93a8"), rx=0.3)
    d.lines_on("left", 0, 9, 15, 1.2, 4.4, 5.6, 8, 1.0, "#2f8a4e", width=0.4)
    screen(d, "left", 0, 9, 15, 8, 1, 3.4, 2.2, fam)
    d.box(
        2,
        -2,
        15,
        1,
        6,
        1,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )


def r_turbine(d: Drawing, fam: Family, kind: str = "steam") -> None:
    _plate(d, fam, 34, 14, dark=True)
    if kind == "gas":
        d.cylinder(6, 6, 0.6, 3.5, 6, fam, body=("#dfe4ea", "#aeb6c2"))
        d.box(
            9,
            3,
            0.6,
            12,
            6,
            6,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(22, 2, 0.6, 5, 8, 14, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    else:
        d.box(
            2,
            3,
            0.6,
            8,
            6,
            5,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(
            11,
            2,
            0.6,
            9,
            8,
            7,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(21, 3, 0.6, 10, 6, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        d.box(
            4,
            5,
            5.6,
            1.2,
            1.2,
            5,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )


def r_boiler(d: Drawing, fam: Family) -> None:
    d.cylinder(8, 8, 0, 4.5, 2.5, fam, body=("#4d566a", "#343c4b"))
    d.cylinder(8, 8, 2.5, 4, 12, fam, body=("#dfe4ea", "#aeb6c2"))
    d.cylinder(8, 8, 14.5, 2, 1.5, fam, body=("#dfe4ea", "#aeb6c2"))
    _chimney(d, fam, 8, 8, 24)
    d.box(6, 12, 2.5, 4, 4, 4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)


def r_cooling_tower(d: Drawing, fam: Family) -> None:
    d.cylinder(10, 10, 0, 9.5, 1.2, fam, body=("#c9cfd6", "#b3bac3"))
    _tower(d, fam, 10, 10)


def r_genset(d: Drawing, fam: Family, kind: str = "diesel") -> None:
    _plate(d, fam, 24, 10, dark=True)
    d.box(3, 2, 0.6, 8, 6, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.cylinder(15, 5, 0.6, 2.5, 5, fam, body=("#dfe4ea", "#aeb6c2"))
    d.box(0, 1.5, 0.6, 2, 7, 6.5, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.vents("left", 0, 8.5, 7.1, 0.2, 0.6, 1.6, 5.4, "#1c212b")
    d.cylinder(6, 4, 6.6, 0.5, 4, fam, body=("#dfe4ea", "#aeb6c2"))
    if kind == "chp":
        d.box(
            18,
            8,
            0.6,
            4,
            3,
            4,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
    screen(d, "left", 20, 10, 5.6, 0.4, 0.6, 2.4, 1.6, fam)


def r_bess(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 26, 10, 10, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for i in range(4):
        d.rect_on("left", 0, 10, 10, 1 + i * 6.2, 1, 5.4, 7.4, ("#4a525d", "#3d4450"), rx=0.2)
        d.led("left", 0, 10, 10, 2 + i * 6.2, 1.6, GREEN)
    d.rect_on("left", 0, 10, 10, 0.5, 9, 25, 0.6, "#facc15")
    d.box(
        26,
        3,
        3,
        1.2,
        4,
        4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )


def r_pylon(d: Drawing, fam: Family) -> None:
    d.box(
        6,
        6,
        0,
        6,
        6,
        26,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(
        0,
        8,
        16,
        18,
        1,
        0.8,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    d.box(
        2,
        8,
        21,
        14,
        1,
        0.8,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    d.vents("left", 6, 12, 26, 0.5, 1, 5, 24, "#8a94a3")


def r_line(d: Drawing, fam: Family, kind: str = "hv") -> None:
    for x in (0, 30):
        if kind == "mv":
            d.cylinder(x + 2, 6, 0, 0.5, 16, fam, body=("#a67c52", "#8b6b4a"))
            d.box(
                x - 0.5,
                5.5,
                14.6,
                5,
                1,
                0.5,
                fam,
                top=("#a67c52", "#8b6b4a"),
                left=("#a67c52", "#8b6b4a"),
                right=("#8b6b4a", "#6f5439"),
                shadow=False,
            )
        else:
            d.box(
                x,
                4,
                0,
                4,
                4,
                20,
                fam,
                top=("#dfe4ea", "#c2c9d3"),
                left=("#c9d0da", "#aeb6c2"),
                right=("#b8c0cb", "#a0a9b6"),
            )
            d.box(
                x - 3,
                5.5,
                13,
                10,
                1,
                0.8,
                fam,
                top=("#dfe4ea", "#c2c9d3"),
                left=("#c9d0da", "#aeb6c2"),
                right=("#b8c0cb", "#a0a9b6"),
                shadow=False,
            )
    for y in (5.5, 6.0, 6.5):
        d.box(
            4,
            y,
            15 if kind == "hv" else 15.8,
            26,
            0.2,
            0.2,
            fam,
            top=CHASSIS,
            left=CHASSIS,
            right=CHASSIS_SIDE,
            shadow=False,
        )


def r_power_transformer(d: Drawing, fam: Family, s: float = 1, kind: str = "") -> None:
    _plate(d, fam, 20, 14, dark=True)
    d.box(3, 2, 0.6, 12, 9, 8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for i in range(6):
        d.box(
            0,
            2.5 + i * 1.4,
            0.6,
            2.5,
            0.5,
            7,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
        d.box(
            15.5,
            2.5 + i * 1.4,
            0.6,
            2.5,
            0.5,
            7,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.cylinder(9, 3, 9.6, 1.5, 1.5, fam, body=("#4d566a", "#343c4b"))
    for i in range(3):
        d.cylinder(5 + i * 4, 8, 8.6, 0.8, 4.5, fam, body=("#f4f6f8", "#c9d0da"))
    d.led("left", 3, 11, 8.6, 11, 4, AMBER)


def _stand(d: Drawing, fam: Family, w: float) -> None:
    d.box(
        0,
        2,
        0,
        w,
        3,
        0.5,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    for x in (0.5, w - 1.5):
        d.box(
            x,
            2.5,
            0.5,
            1,
            1,
            3,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.box(
        0,
        2,
        3.5,
        w,
        3,
        0.5,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )


def r_breaker_hv(d: Drawing, fam: Family) -> None:
    _stand(d, fam, 16)
    for i in range(3):
        d.cylinder(3 + i * 5, 3.5, 4, 0.7, 6, fam, body=("#c9d0da", "#8a94a3"))
        d.box(
            0.8 + i * 5,
            2.5,
            10,
            4.4,
            2,
            1.6,
            fam,
            top=("#c9d0da", "#8a94a3"),
            left=("#c9d0da", "#8a94a3"),
            right=("#8a94a3", "#6b7482"),
        )
    d.box(
        15,
        6,
        0,
        3,
        3,
        4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )


def r_disconnect(d: Drawing, fam: Family) -> None:
    _stand(d, fam, 16)
    for i in range(3):
        d.cylinder(3 + i * 5, 2, 4, 0.5, 3.6, fam, body=("#c9d0da", "#8a94a3"))
        d.cylinder(3 + i * 5, 5, 4, 0.5, 3.6, fam, body=("#c9d0da", "#8a94a3"))
        d.box(
            2.7 + i * 5,
            1.8,
            7.6,
            0.6,
            3.6,
            0.4,
            fam,
            top=("#d08a4a", "#b87333"),
            left=("#d08a4a", "#b87333"),
            right=("#b87333", "#8f5a28"),
            shadow=False,
        )


def r_arrester(d: Drawing, fam: Family) -> None:
    d.box(
        2,
        2,
        0,
        4,
        4,
        0.6,
        fam,
        top=("#c9cfd6", "#b3bac3"),
        left=("#bfc5cc", "#a9b0b9"),
        right=("#9aa1aa", "#858c95"),
    )
    d.box(
        3,
        3,
        0.6,
        2,
        2,
        4,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.cylinder(4, 4, 4.6, 0.8, 8, fam, body=("#c9d0da", "#8a94a3"))
    d.cylinder(4, 4, 12.6, 1.6, 0.4, fam, body=("#dfe4ea", "#aeb6c2"))
    d.cylinder(4, 4, 13, 0.5, 1.2, fam, body=("#dfe4ea", "#aeb6c2"))


def r_instrument_transformer(d: Drawing, fam: Family) -> None:
    d.box(
        2,
        2,
        0,
        4,
        4,
        0.6,
        fam,
        top=("#c9cfd6", "#b3bac3"),
        left=("#bfc5cc", "#a9b0b9"),
        right=("#9aa1aa", "#858c95"),
    )
    d.box(
        3,
        3,
        0.6,
        2,
        2,
        1.6,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.cylinder(4, 4, 2.2, 0.7, 6.5, fam, body=("#c9d0da", "#8a94a3"))
    d.cylinder(4, 4, 8.7, 1.5, 2.4, fam, body=("#dfe4ea", "#aeb6c2"))


def r_capacitor_bank(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 16, 6)
    for x in (0, 13):
        d.box(
            x,
            2,
            0.6,
            1,
            1,
            12,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    for z in (3, 6.5, 10):
        d.box(
            0,
            1.5,
            z,
            14,
            3,
            0.3,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
        for i in range(4):
            d.box(
                1.5 + i * 3.1,
                1.5,
                z + 0.3,
                2.2,
                1.4,
                2.6,
                fam,
                top=("#dfe4ea", "#c2c9d3"),
                left=("#c9d0da", "#aeb6c2"),
                right=("#b8c0cb", "#a0a9b6"),
            )


def r_shunt_reactor(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 22, 9)
    for i in range(3):
        for k in range(3):
            d.cylinder(4 + i * 7, 4, 2.6 + k * 1.4, 2.2, 1.2, fam, body=("#d08a4a", "#b87333"))
        d.box(
            2 + i * 7,
            2,
            6.8,
            4,
            4,
            0.3,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )


def r_pole(d: Drawing, fam: Family) -> None:
    d.cylinder(4, 4, 0, 0.5, 18, fam, body=("#a67c52", "#8b6b4a"))
    d.box(
        1,
        3.7,
        16.4,
        6,
        0.6,
        0.5,
        fam,
        top=("#a67c52", "#8b6b4a"),
        left=("#a67c52", "#8b6b4a"),
        right=("#8b6b4a", "#6f5439"),
        shadow=False,
    )
    d.cylinder(5.6, 4, 10.5, 1.2, 3.6, fam, body=("#4d566a", "#343c4b"))
    for x in (1.5, 4, 6.5):
        d.cylinder(x, 4, 17, 0.3, 1, fam, body=("#c9d0da", "#8a94a3"))


def r_padmount(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 12, 9, fam, h=0.5, top=("#c9cfd6", "#b3bac3"))
    d.box(
        1.5,
        1.5,
        0.5,
        9,
        6,
        6.5,
        fam,
        top=("#3f8a4c", "#2f6b3a"),
        left=("#3f8a4c", "#2f6b3a"),
        right=("#2f6b3a", "#22502a"),
    )
    d.rect_on("left", 1.5, 7.5, 7, 1, 1, 3.4, 4.8, ("#3f8a4c", "#2f6b3a"), rx=0.2)
    d.rect_on("left", 1.5, 7.5, 7, 4.6, 1, 3.4, 4.8, ("#3f8a4c", "#2f6b3a"), rx=0.2)
    d.rect_on("left", 1.5, 7.5, 7, 6.5, 1.6, 1.6, 1.6, "#facc15", rx=0.2)


def r_rmu(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        12,
        6,
        9,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    for i in range(3):
        d.rect_on("left", 0, 6, 9, 0.8 + i * 3.8, 5, 3.2, 3.4, ("#4a525d", "#3d4450"), rx=0.2)
        d.rect_on("left", 0, 6, 9, 1 + i * 3.8, 1, 2.8, 2.8, ("#f4f6f8", "#e2e6eb"), rx=0.2)
        d.led("left", 0, 6, 9, 3.2 + i * 3.8, 0.8, AMBER if i == 1 else GREEN)


def r_hvdc(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 60, 38)
    d.box(
        2,
        8,
        0.6,
        28,
        16,
        14,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.vents("left", 2, 24, 14.6, 2, 3, 24, 8, "#b8c0cb")
    for y in (4, 20):
        d.box(36, y, 0.6, 12, 9, 8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        d.cylinder(42, y + 3, 9.6, 1.5, 1.5, fam, body=("#4d566a", "#343c4b"))
    for k in range(3):
        d.cylinder(52, 6, 2.6 + k * 1.6, 2.4, 1.3, fam, body=("#d08a4a", "#b87333"))


def r_substation(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 56, 40)
    for x in (4, 20):
        d.box(x, 22, 0.6, 12, 9, 8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        for i in range(3):
            d.cylinder(x + 2 + i * 4, 26, 8.6, 0.8, 4, fam, body=("#f4f6f8", "#c9d0da"))
    for x in (2, 30):
        d.box(
            x,
            4,
            0.6,
            1,
            1,
            16,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.box(
        2,
        4,
        16.6,
        29,
        1,
        0.8,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    for i in range(3):
        d.box(
            38 + i * 6,
            6,
            0.6,
            3,
            3,
            0.5,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
        d.cylinder(39.5 + i * 6, 7.5, 1.1, 0.6, 6, fam, body=("#c9d0da", "#8a94a3"))
    d.box(
        42,
        28,
        0.6,
        9,
        7,
        4.5,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )


def r_busbar(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 24, 10)
    for x in (2, 11, 20):
        d.box(
            x,
            4,
            0.6,
            1,
            1,
            5,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
        for i in range(3):
            d.cylinder(x + 0.5, 2 + i * 2.6, 5.6, 0.4, 2.4, fam, body=("#c9d0da", "#8a94a3"))
    for i in range(3):
        d.box(
            0,
            1.7 + i * 2.6,
            8,
            24,
            0.5,
            0.5,
            fam,
            top=("#d08a4a", "#b87333"),
            left=("#d08a4a", "#b87333"),
            right=("#b87333", "#8f5a28"),
            shadow=False,
        )


def r_pcc(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 10, 8, fam, h=0.4, top=("#c9cfd6", "#b3bac3"))
    d.box(
        2,
        2,
        0.4,
        5,
        3,
        8,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    screen(d, "left", 2, 5, 8.4, 0.8, 1.2, 3.4, 2.0, fam)
    d.rect_on("left", 2, 5, 8.4, 1, 5.5, 3, 1.4, "#facc15", rx=0.2)
    d.cylinder(1.5, 12, 0, 0.4, 16, fam, body=("#a67c52", "#8b6b4a"))


def r_control_room(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 28, 22, fam, h=1.0, top=("#eef1f5", "#dfe4ea"))
    d.box(0, 0, 1, 28, 1.2, 12, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False)
    screen(d, "left", 0, 1.2, 13, 3, 2, 22, 8, fam)
    for x in (3, 11, 19):
        d.box(x, 12, 1, 6, 3, 3.5, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        screen(d, "left", x, 15, 4.5, 0.5, 0.3, 5, 2.8, fam)


def r_vault(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 16, 14, fam, h=0.8, top=("#c9cfd6", "#b3bac3"))
    d.cylinder(5, 7, 0.8, 2.2, 0.3, fam, body=("#dfe4ea", "#aeb6c2"))
    d.rect_on("top", 0, 0, 1.1, 9, 4, 4, 3, ("#c9d0da", "#aeb6c2"), rx=0.3)
    for i in range(3):
        d.cylinder(-1, 3 + i * 2, 0.4, 0.5, 0.4, fam, body=("#fb923c", "#f97316"))


def r_switchgear(d: Drawing, fam: Family, cells: int = 4, kind: str = "lv") -> None:
    w = cells * 4.2
    h = 22 if kind == "mv" else 19
    d.box(
        0,
        0,
        0,
        w,
        12,
        h,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    for i in range(cells):
        x = 0.4 + i * 4.2
        if kind == "mcc":
            for k in range(6):
                d.rect_on(
                    "left", 0, 12, h, x, 1.5 + k * 2.9, 3.4, 2.5, ("#f4f6f8", "#e2e6eb"), rx=0.2
                )
                d.led("left", 0, 12, h, x + 0.5, 2.2 + k * 2.9, GREEN)
        else:
            d.rect_on("left", 0, 12, h, x, 1.5, 3.4, h * 0.42, ("#f4f6f8", "#e2e6eb"), rx=0.2)
            d.rect_on("left", 0, 12, h, x, h * 0.55, 3.4, h * 0.4, ("#f4f6f8", "#e2e6eb"), rx=0.2)
            screen(d, "left", 0, 12, h, x + 0.5, 2.2, 2.4, 1.4, fam)
            d.led("left", 0, 12, h, x + 1, 5, GREEN)
    d.rect_on("left", 0, 12, h, 0.6, h - 1.4, w - 1.2, 0.4, fam.accent, rx=0.15)


def r_wallbox(d: Drawing, fam: Family, kind: str = "panelboard") -> None:
    d.slab(0, 0, 0, 16, 1.2, fam, h=16, top=("#eef1f5", "#dfe4ea"), left=("#f4f6f9", "#e6eaf0"))
    w, h = (5, 5) if kind == "jbox" else (7, 9) if kind == "controller" else (9, 12)
    d.box(3.5, 1.2, 2, w, 3, h, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    if kind == "panelboard":
        for r in range(8):
            for x in (1.2, 4.8):
                d.rect_on(
                    "left",
                    3.5,
                    4.2,
                    2 + h,
                    x + 0.5,
                    1.3 + r * 1.25,
                    1.6,
                    0.7,
                    ("#1f2937", "#111827"),
                    rx=0.15,
                )
    elif kind == "changeover":
        d.dot_on("left", 3.5, 4.2, 2 + h, 4.5, 6, 2.2, "#1f2937")
        d.rect_on("left", 3.5, 4.2, 2 + h, 4.2, 4.2, 0.6, 3.6, "#ef4444", rx=0.2)
        d.led("left", 3.5, 4.2, 2 + h, 1.5, 2, GREEN)
        d.led("left", 3.5, 4.2, 2 + h, 7.5, 2, AMBER)
    elif kind == "controller":
        screen(d, "left", 3.5, 4.2, 2 + h, 1, 1, 5, 3.2, fam)
        d.led("left", 3.5, 4.2, 2 + h, 6, 6.5, GREEN)
    else:
        d.box(
            4.5,
            4.2,
            2 + h,
            1,
            1,
            4,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
        d.box(
            7.5,
            4.2,
            2 + h,
            1,
            1,
            4,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )


def r_rack_ups(d: Drawing, fam: Family) -> None:
    w, dp, h = 24, 15, 8.4
    bezel(d, 0, 0, 0, w, dp, h, fam)
    screen(d, "left", 0, dp, h, 1.5, 1.2, 6, 3.4, fam)
    for i in range(2):
        d.rect_on("left", 0, dp, h, 9 + i * 6.6, 1.4, 6, 3, ("#cfd5dd", "#aeb6c2"), rx=0.25)
        d.led("left", 0, dp, h, 14 + i * 6.6, 2.9, GREEN)
    d.rect_on("left", 0, dp, h, 1.3, h - 1.0, w - 2.6, 0.35, fam.accent, rx=0.15)


def r_batt_rack(d: Drawing, fam: Family, kind: str = "li") -> None:
    if kind == "vrla":
        for x in (0, 11):
            d.box(
                x,
                0,
                0,
                1,
                10,
                13,
                fam,
                top=("#dfe4ea", "#c2c9d3"),
                left=("#c9d0da", "#aeb6c2"),
                right=("#b8c0cb", "#a0a9b6"),
                shadow=False,
            )
        for z in (0.5, 4.5, 8.5):
            d.slab(0, 0, z, 12, 10, fam, h=0.3, top=("#dfe4ea", "#c2c9d3"))
            for i in range(4):
                d.box(
                    1 + i * 2.6,
                    1.5,
                    z + 0.3,
                    2.2,
                    7,
                    3,
                    fam,
                    top=CHASSIS,
                    left=CHASSIS,
                    right=CHASSIS_SIDE,
                )
        return
    d.box(0, 0, 0, 10, 11, 20, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for i in range(8):
        d.rect_on("left", 0, 11, 20, 1, 2.8 + i * 2.0, 8, 1.6, ("#cfd5dd", "#aeb6c2"), rx=0.25)
        d.led("left", 0, 11, 20, 8, 3.6 + i * 2.0, GREEN)
    screen(d, "left", 0, 11, 20, 2.5, 0.6, 5, 1.8, fam)


def r_dc_plant(d: Drawing, fam: Family) -> None:
    for x in (0, 11):
        d.box(
            x,
            0,
            0,
            1,
            11,
            16,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    for z in (1, 4.6):
        d.box(1, 1, z, 10, 9, 2.8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        for i in range(6):
            d.rect_on(
                "left",
                1,
                10,
                z + 2.8,
                0.3 + i * 1.6,
                0.4,
                1.3,
                2.2,
                ("#cfd5dd", "#aeb6c2"),
                rx=0.15,
            )
            d.led("left", 1, 10, z + 2.8, 1.2 + i * 1.6, 0.8, GREEN)
    d.box(1, 1, 8.6, 10, 9, 2.6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for i in range(10):
        d.rect_on("left", 1, 10, 11.2, 0.4 + i * 0.95, 0.8, 0.6, 1.2, "#1f2937", rx=0.1)
    d.box(1, 1, 12, 10, 9, 2, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    screen(d, "left", 1, 10, 14, 1, 0.3, 4, 1.4, fam)


def r_rectifier(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        6,
        16,
        8,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.rect_on("left", 0, 16, 8, 0.6, 3, 4.8, 4.4, ("#3d4556", "#252b36"), rx=0.3)
    d.vents("left", 0, 16, 8, 1, 4, 4, 2.5, "#8a94a3")
    d.led("left", 0, 16, 8, 4.6, 1.2, GREEN)
    d.rect_on("left", 0, 16, 8, 1, 0.6, 2.4, 0.8, ("#cfd5dd", "#aeb6c2"), rx=0.2)


def r_floor_pdu(d: Drawing, fam: Family, kind: str = "pdu") -> None:
    w, dp, h = (8, 8, 18) if kind == "rpp" else (16, 10, 17)
    d.box(
        0,
        0,
        0,
        w,
        dp,
        h,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    doors = 1 if kind == "rpp" else 2
    for i in range(doors):
        x = 0.6 + i * (w / 2)
        d.rect_on("left", 0, dp, h, x, 1, w / doors - 1.2, h - 2, ("#f4f6f8", "#e2e6eb"), rx=0.3)
        for k in range(2):
            d.rect_on(
                "left",
                0,
                dp,
                h,
                x + 0.8,
                2.5 + k * 6.5,
                w / doors - 2.8,
                4.5,
                ("#c9d0da", "#aeb6c2"),
                rx=0.2,
            )
    screen(d, "left", 0, dp, h, 1.2, 1.4, 3.4, 1.8, fam)
    d.led("left", 0, dp, h, w - 1.5, 2, GREEN)


def r_tapoff(d: Drawing, fam: Family) -> None:
    d.box(0, 3, 12, 16, 3, 3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        6,
        2.5,
        8,
        4,
        4,
        4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.led("left", 6, 6.5, 12, 3, 0.8, GREEN)
    d.cylinder(8, 4.5, 6, 0.8, 2, fam, body=("#fde047", "#facc15"))
    d.rect_on("left", 0, 6, 15, 0.3, 2.4, 15.4, 0.4, fam.accent)


def r_pdu_h(d: Drawing, fam: Family) -> None:
    bezel(d, 0, 0, 0, 24, 10, 3.6, fam)
    for i in range(8):
        d.rect_on("left", 0, 10, 3.6, 1.5 + i * 2.2, 1.1, 1.4, 1.4, "#1f2937", rx=0.2)
    screen(d, "left", 0, 10, 3.6, 19.5, 0.9, 3, 1.8, fam)


def r_psu(d: Drawing, fam: Family, count: int = 1) -> None:
    for i in range(count):
        x = i * 8
        d.box(
            x,
            0,
            0,
            7,
            18,
            3.2,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.rect_on("left", x, 18, 3.2, 0.5, 0.5, 2.8, 2.2, ("#3d4556", "#252b36"), rx=0.2)
        d.vents("left", x, 18, 3.2, 0.7, 0.8, 2.4, 1.6, "#8a94a3")
        d.rect_on("left", x, 18, 3.2, 4, 0.6, 1.6, 1.0, "#1f2937", rx=0.15)
        d.led("left", x, 18, 3.2, 6.3, 0.9, GREEN)


def r_ground_bar(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 16, 6, fam, h=0.4, top=("#eef1f5", "#dfe4ea"))
    for x in (2, 13):
        d.cylinder(x + 0.5, 3, 0.4, 0.5, 1.6, fam, body=("#c9d0da", "#8a94a3"))
    d.box(
        1,
        2.2,
        2,
        14,
        1.6,
        0.6,
        fam,
        top=("#d08a4a", "#b87333"),
        left=("#d08a4a", "#b87333"),
        right=("#b87333", "#8f5a28"),
        shadow=False,
    )
    for i in range(6):
        d.dot_on("top", 1, 2.2, 2.6, 1.5 + i * 2.2, 0.8, 0.28, "#22c55e" if i % 2 else "#facc15")


def r_loadbank(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 1.6, 18, 10, 7, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.vents("left", 0, 10, 8.6, 1, 1.2, 16, 4.8, "#1c212b")
    for x in (4, 12):
        d.dot_on("top", 0, 0, 8.6, x + 1, 5, 3, "#4d566a")
        d.dot_on("top", 0, 0, 8.6, x + 1, 5, 2.2, "#8a94a3")
    for x, y in ((1, -0.5), (15, -0.5), (1, 9.5), (15, 9.5)):
        d.box(
            x,
            y,
            0,
            2,
            1,
            1.6,
            fam,
            top=("#1f242b", "#111418"),
            left=("#1f242b", "#111418"),
            right=("#111418", "#06080b"),
            shadow=False,
        )


def r_pump_skid(d: Drawing, fam: Family, kind: str = "water") -> None:
    _plate(d, fam, 22, 12, dark=True)
    if kind == "fuel":
        d.box(2, 3, 0.6, 8, 5, 4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        d.cylinder(15, 6, 0.6, 2.5, 5, fam, body=("#dfe4ea", "#aeb6c2"))
    else:
        for y in (1, 7):
            d.box(2, y, 0.6, 8, 4, 4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
            d.box(
                10,
                y + 1,
                2.6,
                8,
                1.2,
                1.2,
                fam,
                top=("#60a5fa", "#3b82f6"),
                left=("#60a5fa", "#3b82f6"),
                right=("#3b82f6", "#1d4ed8"),
                shadow=False,
            )
    d.box(
        18,
        8,
        0.6,
        2.6,
        3.6,
        0.8,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )


def r_control_panel(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        10,
        5,
        13,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    screen(d, "left", 0, 5, 13, 1, 1.2, 5.5, 3.6, fam)
    for i, c in enumerate(("#22c55e", "#ef4444", "#facc15", "#3b82f6")):
        d.dot_on("left", 0, 5, 13, 1.6 + i * 2, 7, 0.55, c)
    d.dot_on("left", 0, 5, 13, 8, 2.4, 1.1, "#facc15")
    d.dot_on("left", 0, 5, 13, 8, 2.4, 0.8, "#ef4444")
    for i in range(6):
        d.led("left", 0, 5, 13, 1 + i * 0.9, 9.5, GREEN if i % 2 else AMBER)
    d.cylinder(8.5, 2.5, 13, 0.4, 1.8, fam, body=("#ef4444", "#b91c1c"))


def r_ladder(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 12, 1.2, fam, h=22, top=("#eef1f5", "#dfe4ea"), left=("#f4f6f9", "#e6eaf0"))
    for x in (2, 9):
        d.box(
            x,
            1.2,
            0,
            0.6,
            1.2,
            22,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    for k in range(9):
        d.box(
            2,
            1.2,
            1 + k * 2.4,
            7.6,
            1,
            0.4,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    for i, c in enumerate(("#3b82f6", "#f97316", "#111418", "#2dd4bf", "#3b82f6")):
        d.rect_on("left", 2, 2.4, 22, 0.8 + i * 1.3, 0, 0.5, 22, c, rx=0.25)


def r_conduit(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 16, 1.2, fam, h=14, top=("#eef1f5", "#dfe4ea"), left=("#f4f6f9", "#e6eaf0"))
    for i in range(3):
        d.rect_on("left", 0, 1.2, 14, 0.5, 3 + i * 3.2, 10, 0.8, ("#dfe4ea", "#aeb6c2"), rx=0.4)
        d.rect_on("left", 0, 1.2, 14, 10, 0.5, 0.8, 3.3 + i * 3.2, ("#dfe4ea", "#aeb6c2"), rx=0.4)
    d.box(11.5, 1.2, 5, 4, 2, 4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)


def r_cooling_tower_mech(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        18,
        12,
        10,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.vents("left", 0, 12, 10, 1, 2, 16, 6, "#b8c0cb")
    for x in (4.5, 13.5):
        d.cylinder(x, 6, 10, 3.5, 2, fam, body=("#dfe4ea", "#aeb6c2"))
        d.dot_on("top", 0, 0, 12, x, 6, 2.9, "#4d566a")


def r_drycooler(d: Drawing, fam: Family) -> None:
    for x in (0, 10, 20):
        for y in (0, 7):
            d.box(
                x,
                y,
                0,
                0.6,
                0.6,
                2.4,
                fam,
                top=("#dfe4ea", "#c2c9d3"),
                left=("#c9d0da", "#aeb6c2"),
                right=("#b8c0cb", "#a0a9b6"),
                shadow=False,
            )
    d.box(
        0,
        0,
        2.4,
        22,
        8,
        6.5,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.vents("left", 0, 8, 8.9, 0.5, 0.5, 21, 5.5, "#8a94a3")
    for i in range(4):
        d.dot_on("top", 0, 0, 8.9, 3 + i * 5.5, 4, 2.4, "#4d566a")
        d.dot_on("top", 0, 0, 8.9, 3 + i * 5.5, 4, 1.8, "#8a94a3")


def r_rdhx(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 10, 1.4, 22, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.vents("left", 0, 1.4, 22, 0.8, 2, 8.4, 18, "#4d566a")
    d.rect_on("left", 0, 1.4, 22, 2.5, 20.4, 1.2, 1.2, "#3b82f6", rx=0.6)
    d.rect_on("left", 0, 1.4, 22, 6.5, 20.4, 1.2, 1.2, "#f97316", rx=0.6)


def r_cdu(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 10, 11, 20, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.rect_on("left", 0, 11, 20, 1.5, 7, 7, 7, ("#9fb3c8", "#7f93a8"), rx=0.3)
    screen(d, "left", 0, 11, 20, 2, 1.5, 6, 3, fam)
    for i, c in enumerate(("#3b82f6", "#f97316", "#3b82f6", "#f97316")):
        d.cylinder(2.5 + i * 1.8, 3, 20, 0.45, 3.5, fam, body=(c, c))


def r_immersion(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        18,
        9,
        9,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.rect_on("top", 0, 0, 9, 0.8, 0.8, 16.4, 7.4, ("#60a5fa", "#2b7fc4"), rx=0.3)
    d.lines_on("top", 0, 0, 9, 1.6, 1.4, 6.2, 9, 1.65, "#2f8a4e", width=0.35)


def r_manifold(d: Drawing, fam: Family) -> None:
    for x in (1, 12, 23):
        d.box(
            x,
            4,
            0,
            1.5,
            3,
            3,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.box(
        0,
        4.5,
        3,
        26,
        2.4,
        2.4,
        fam,
        top=("#60a5fa", "#3b82f6"),
        left=("#60a5fa", "#3b82f6"),
        right=("#3b82f6", "#1d4ed8"),
    )
    for i in range(6):
        d.cylinder(2.5 + i * 4, 5.7, 5.4, 0.5, 3, fam, body=("#60a5fa", "#3b82f6"))
        d.cylinder(2.5 + i * 4, 5.7, 8.4, 1, 0.5, fam, body=("#ef4444", "#b91c1c"))


def r_economiser(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        20,
        12,
        11,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.vents("left", 0, 12, 11, 1, 1.5, 18, 8, "#b8c0cb")
    d.box(3, 3, 11, 14, 6, 2.5, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(2, 2, 13.5, 16, 8, 0.6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False)


def r_humidifier(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        7,
        6,
        10,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    screen(d, "left", 0, 6, 10, 0.8, 0.8, 5.4, 2, fam)
    d.rect_on("left", 0, 6, 10, 1, 4, 5, 5, ("#9fb3c8", "#7f93a8"), rx=0.3)
    d.box(
        5,
        2,
        10,
        0.8,
        0.8,
        3.5,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    d.cylinder(5.4, 2.4, 13.5, 1.2, 1.0, fam, body=("#ffffff", "#e6eaf0"))


def r_duct(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        4,
        6,
        22,
        3.2,
        3.2,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(
        14,
        7.2,
        6,
        3.2,
        8,
        3.2,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    for x in (4, 11):
        d.box(
            x,
            4,
            5.6,
            3.2,
            3.2,
            0.4,
            fam,
            top=("#f4f6f8", "#e2e6eb"),
            left=("#f4f6f8", "#e2e6eb"),
            right=("#e2e6eb", "#c9d0da"),
            shadow=False,
        )


def r_cylinders(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 16, 5, fam, h=0.5, top=("#5b6470", "#3d4450"))
    for i in range(5):
        d.cylinder(2 + i * 3, 2.5, 0.5, 1.1, 11, fam, body=("#ef4444", "#b91c1c"))
        d.cylinder(2 + i * 3, 2.5, 11.5, 0.4, 1.2, fam, body=("#dfe4ea", "#aeb6c2"))
    d.box(
        0,
        1,
        12.5,
        16,
        0.5,
        0.5,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )


def r_yard(d: Drawing, fam: Family, kind: str = "gen") -> None:
    _plate(d, fam, 44, 28)
    if kind == "fuel":
        for x in (2, 16, 30):
            d.box(
                x,
                6,
                0.6,
                12,
                10,
                8,
                fam,
                top=("#e6eaf0", "#d5dbe3"),
                left=("#d9dee6", "#c2c9d3"),
                right=("#b8c0cb", "#a0a9b6"),
            )
        d.box(
            0,
            0,
            0.6,
            44,
            1,
            2.6,
            fam,
            top=("#c9cfd6", "#b3bac3"),
            left=("#bfc5cc", "#a9b0b9"),
            right=("#9aa1aa", "#858c95"),
            shadow=False,
        )
    else:
        for y in (2, 15):
            d.box(4, y, 0.6, 16, 8, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
            d.cylinder(16, y + 4, 0.6, 2.2, 4, fam, body=("#dfe4ea", "#aeb6c2"))
        d.box(
            28,
            8,
            0.6,
            12,
            8,
            7,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )


def r_shutter(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 24, 1.4, fam, h=18, top=("#eef1f5", "#dfe4ea"), left=("#f4f6f9", "#e6eaf0"))
    d.rect_on("left", 0, 1.4, 18, 5, 0, 14, 9, ("#4a525d", "#3d4450"), rx=0.2)
    d.lines_on("left", 0, 1.4, 18, 5, 0.6, 14, 8, 1.0, "#2f353e", width=0.35)
    d.cylinder(12, 0.7, 16, 1.4, 1.4, fam, body=("#dfe4ea", "#aeb6c2"))
    d.rect_on("left", 0, 1.4, 18, 5, 8.6, 14, 0.5, "#facc15")


def r_camera_ir(d: Drawing, fam: Family) -> None:
    d.box(
        3,
        3,
        0,
        2,
        2,
        5,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(0, 0, 5, 8, 12, 4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        -0.5,
        -0.5,
        9,
        9,
        13,
        0.5,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    d.dot_on("left", 0, 12, 9, 4, 2, 1.6, "#1f2937")
    d.dot_on("left", 0, 12, 9, 4, 2, 1.0, "#3d4a6b")


def r_transmitter(d: Drawing, fam: Family, kind: str = "pressure") -> None:
    if kind == "level":
        d.cylinder(6, 6, 0, 5, 4, fam, body=("#dfe4ea", "#aeb6c2"))
        d.cylinder(6, 6, 4, 0.5, 2.5, fam, body=("#dfe4ea", "#aeb6c2"))
    else:
        d.box(
            0,
            5,
            1,
            12,
            2,
            2,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.cylinder(6, 6, 3, 0.4, 3, fam, body=("#dfe4ea", "#aeb6c2"))
    d.cylinder(6, 6, 6.5, 1.6, 2, fam, body=("#4d566a", "#343c4b"))
    d.dot_on("left", 4.4, 7.6, 8.5, 1.6, 1, 1.1, "#f4f6f8")
    d.led("left", 4.4, 7.6, 8.5, 2.8, 0.4, GREEN)


def r_flowmeter(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        5,
        1.5,
        16,
        2.2,
        2.2,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(
        5,
        4.4,
        0.9,
        6,
        3.4,
        3.4,
        fam,
        top=("#60a5fa", "#3b82f6"),
        left=("#60a5fa", "#3b82f6"),
        right=("#3b82f6", "#1d4ed8"),
    )
    d.box(6.5, 5, 4.3, 3, 2.4, 2.6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    screen(d, "left", 6.5, 7.4, 6.9, 0.4, 0.5, 2.2, 1.4, fam)


def r_damper(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        2,
        10,
        6,
        8,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.lines_on("left", 0, 6, 10, 0.5, 1, 9, 4, 1.9, "#4d566a", width=0.9)
    d.box(10, 2, 4, 2.4, 2, 3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.led("left", 10, 4, 7, 1.2, 0.8, GREEN)


def r_fanwall(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        18,
        2.4,
        12,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    for r in range(2):
        for c in range(3):
            d.dot_on("left", 0, 2.4, 12, 3 + c * 6, 3 + r * 6, 2.5, "#4d566a")
            d.dot_on("left", 0, 2.4, 12, 3 + c * 6, 3 + r * 6, 1.9, "#8a94a3")
            d.dot_on("left", 0, 2.4, 12, 3 + c * 6, 3 + r * 6, 0.5, "#1f2937")


def r_compressor(d: Drawing, fam: Family) -> None:
    d.box(1, 3, 0, 14, 5, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(2, 5, 6, 5, 3, 3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        9,
        5,
        6,
        3,
        3,
        2.6,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.lines_on("left", 9, 8, 8.6, 0.2, 0.3, 2.6, 4, 0.5, "#dfe4ea", width=0.3)
    d.dot_on("left", 1, 8, 6, 12, 2, 0.7, "#f4f6f8")


def r_phe(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 16, 6, fam, h=0.6, top=("#5b6470", "#3d4450"))
    for x in (0.5, 14):
        d.box(x, 0.5, 0.6, 1.5, 5, 10, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        2,
        0.8,
        0.6,
        12,
        4.4,
        9,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.lines_on("left", 2, 5.2, 9.6, 0.2, 0.4, 11.6, 14, 0.6, "#8a94a3", width=0.25)
    for i, c in enumerate(("#f97316", "#3b82f6", "#3b82f6", "#f97316")):
        d.dot_on("left", 0.5, 5.5, 10.6, 0.75, 2 + i * 2.2, 0.55, c)


def r_fittings(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        5,
        2,
        14,
        1.8,
        1.8,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(
        5,
        4.4,
        2,
        2.6,
        3,
        3,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(
        5.6,
        5,
        5,
        1.4,
        1.8,
        5,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.cylinder(6.3, 5.9, 10, 1.4, 2.4, fam, body=("#4d566a", "#343c4b"))
    d.box(
        13,
        5,
        2,
        1.8,
        1.8,
        7,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.cylinder(2.5, 5.9, 3.8, 0.9, 0.4, fam, body=("#ef4444", "#b91c1c"))


def r_console_desk(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 3, 22, 8, fam, h=0.5, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for x in (0.5, 20):
        d.box(
            x,
            1,
            0,
            1.5,
            6,
            3,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    for x in (1, 8, 15):
        d.box(x, 0.5, 3.5, 6, 0.8, 4.5, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        screen(d, "left", x, 1.3, 8, 0.4, 0.4, 5.2, 3.7, fam)
    d.rect_on("top", 0, 0, 3.5, 6, 5, 6, 2, ("#dfe4ea", "#c9d0da"), rx=0.3)


def r_eng_workstation(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 3, 18, 8, fam, h=0.5, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for x in (0.5, 16):
        d.box(
            x,
            1,
            0,
            1.5,
            6,
            3,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    for x in (1, 8):
        d.box(x, 0.5, 3.5, 6, 0.8, 4.5, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        screen(d, "left", x, 1.3, 8, 0.4, 0.4, 5.2, 3.7, fam)
    d.box(15, 1, 0, 3, 6, 9, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.rect_on("top", 0, 0, 3.5, 4, 5, 6, 2, ("#dfe4ea", "#c9d0da"), rx=0.3)


def r_mast(d: Drawing, fam: Family, kind: str = "lattice") -> None:
    if kind == "small":
        d.cylinder(4, 4, 0, 0.4, 14, fam, body=("#dfe4ea", "#aeb6c2"))
        d.box(
            3.2,
            3.2,
            12,
            1.6,
            1.6,
            3,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        return
    _plate(d, fam, 12, 12)
    if kind == "monopole":
        d.cylinder(5, 5, 0.6, 0.9, 26, fam, body=("#f4f6f8", "#c9d0da"))
    else:
        d.box(
            3,
            3,
            0.6,
            4,
            4,
            26,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.vents("left", 3, 7, 26.6, 0.3, 1, 3.4, 24, "#8a94a3")
    for x, y in ((1.5, 2), (7, 1.5), (4.5, 8)):
        d.box(
            x,
            y,
            23,
            1.6,
            1,
            3.6,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.box(
        7,
        7,
        0.6,
        4,
        3,
        4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )


def r_dish(d: Drawing, fam: Family, big: bool = False) -> None:
    r = 7 if big else 3.5
    d.box(
        r - 1,
        r - 1,
        0,
        2,
        2,
        r * 0.7,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.cylinder(r, r, r * 0.7, r, 1.0, fam, body=("#f4f6f8", "#c9d0da"))
    d.cylinder(r, r, r * 0.7 + 1, r * 0.75, 0.6, fam, body=("#e6eaf0", "#d5dbe3"))
    d.cylinder(r, r, r * 0.7 + 1.6, 0.4, r * 0.6, fam, body=("#dfe4ea", "#aeb6c2"))
    if big:
        d.box(
            r * 1.9,
            r * 0.6,
            0,
            8,
            6,
            4,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )


def r_street_cabinet(d: Drawing, fam: Family, kind: str = "fdh") -> None:
    d.slab(0, 0, 0, 11, 7, fam, h=1.2, top=("#c9cfd6", "#b3bac3"))
    d.box(
        1,
        1,
        1.2,
        9,
        5,
        11,
        fam,
        top=("#a3b394", "#8a9a7a"),
        left=("#a3b394", "#8a9a7a"),
        right=("#8a9a7a", "#6f7d62"),
    )
    d.rect_on("left", 1, 6, 12.2, 0.6, 1, 3.6, 9, ("#a3b394", "#8a9a7a"), rx=0.2)
    d.rect_on("left", 1, 6, 12.2, 4.8, 1, 3.6, 9, ("#a3b394", "#8a9a7a"), rx=0.2)
    if kind == "dslam":
        d.box(10, 2, 1.2, 1.5, 3, 9, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)


def r_closure(d: Drawing, fam: Family) -> None:
    for x in (0, 20):
        d.cylinder(x + 1, 3, 0, 0.4, 14, fam, body=("#a67c52", "#8b6b4a"))
    d.box(
        0,
        2.8,
        12,
        22,
        0.3,
        0.3,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    d.box(7, 1.5, 8, 7, 3, 3.2, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.cylinder(14.5, 3, 8, 1.6, 3.2, fam, body=("#dfe4ea", "#aeb6c2"))


def r_reel(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        12,
        3,
        0.4,
        fam,
        top=("#a67c52", "#8b6b4a"),
        left=("#a67c52", "#8b6b4a"),
        right=("#8b6b4a", "#6f5439"),
    )
    for y in (0.5, 5.5):
        d.box(
            1,
            y,
            0.4,
            10,
            0.6,
            10,
            fam,
            top=("#a67c52", "#8b6b4a"),
            left=("#a67c52", "#8b6b4a"),
            right=("#8b6b4a", "#6f5439"),
        )
    d.box(
        2.5,
        1.1,
        1.5,
        7,
        4.4,
        7.8,
        fam,
        top=("#fb923c", "#f97316"),
        left=("#fb923c", "#f97316"),
        right=("#f97316", "#c2410c"),
    )


def r_building(d: Drawing, fam: Family, kind: str = "office") -> None:
    _plate(d, fam, 30, 22)
    if kind == "hq":
        d.box(
            2,
            4,
            0.6,
            12,
            12,
            30,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(
            15,
            6,
            0.6,
            10,
            10,
            12,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.lines_on("left", 2, 16, 30.6, 1, 2, 10, 8, 3.2, "#9fb3c8", width=1.2)
    elif kind == "warehouse":
        d.box(
            1,
            3,
            0.6,
            28,
            16,
            10,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        for x in (4, 12, 20):
            d.rect_on("left", 1, 19, 10.6, x, 5, 4, 5, ("#4a525d", "#3d4450"), rx=0.2)
    elif kind == "factory":
        d.box(
            1,
            3,
            0.6,
            26,
            16,
            9,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        _chimney(d, fam, 24, 6, 18)
        d.lines_on("top", 1, 3, 9.6, 1, 1, 24, 4, 3.6, "#4d566a", width=1.4)
    elif kind == "hospital":
        d.box(
            2,
            4,
            0.6,
            24,
            12,
            14,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.rect_on("left", 2, 16, 14.6, 10.5, 2, 3, 1, "#ef4444")
        d.rect_on("left", 2, 16, 14.6, 11.5, 1, 1, 3, "#ef4444")
    elif kind == "store":
        d.box(
            3,
            4,
            0.6,
            20,
            14,
            7,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.rect_on("left", 3, 18, 7.6, 1, 4, 18, 2.6, ("#9fb3c8", "#7f93a8"), rx=0.2)
        d.rect_on("left", 3, 18, 7.6, 0, 1, 20, 1.4, fam.accent)
    elif kind == "house":
        d.box(
            6,
            6,
            0.6,
            12,
            10,
            7,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(5, 5, 7.6, 14, 12, 3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    elif kind == "gatehouse":
        d.box(
            8,
            8,
            0.6,
            6,
            5,
            5,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(
            14,
            9,
            2.6,
            10,
            0.4,
            0.4,
            fam,
            top=("#ef4444", "#b91c1c"),
            left=("#ef4444", "#b91c1c"),
            right=("#b91c1c", "#7f1d1d"),
            shadow=False,
        )
    elif kind == "central-office":
        d.box(
            2,
            4,
            0.6,
            22,
            14,
            12,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(
            20,
            6,
            12.6,
            3,
            3,
            12,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    elif kind == "pop":
        d.box(
            6,
            6,
            0.6,
            12,
            8,
            6,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.cylinder(9, 9, 6.6, 2.2, 0.8, fam, body=("#f4f6f8", "#c9d0da"))
    elif kind == "dc":
        d.box(
            1,
            3,
            0.6,
            28,
            18,
            9,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        for x in (4, 11, 18):
            d.box(
                x,
                6,
                9.6,
                5,
                5,
                2.4,
                fam,
                top=("#dfe4ea", "#c2c9d3"),
                left=("#c9d0da", "#aeb6c2"),
                right=("#b8c0cb", "#a0a9b6"),
                shadow=False,
            )
    else:
        d.box(
            4,
            4,
            0.6,
            18,
            12,
            16,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.lines_on("left", 4, 16, 16.6, 1, 1.5, 16, 5, 2.8, "#9fb3c8", width=1.0)


def r_container_dc(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 26, 9, 10, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for x in (2, 10, 18):
        d.box(
            x,
            -1.6,
            2,
            4,
            1.6,
            4,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.rect_on("left", 0, 9, 10, 0.5, 8.5, 25, 0.6, "#facc15")
    d.vents("right", 26, 0, 10, 1, 1, 8, 7, "#1c212b")


def r_fence_run(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 28, 8)
    for x in range(0, 27, 4):
        d.box(
            x,
            3.5,
            0.6,
            0.4,
            0.4,
            6,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.rect_on("left", 0, 3.9, 6.6, 0, 0.3, 26.5, 5.4, ("#c9d0da", "#aeb6c2"), opacity=0.45)


def r_vehicle(d: Drawing, fam: Family, kind: str = "van") -> None:
    if kind == "tanker":
        d.box(
            0,
            1,
            0,
            5,
            5,
            4,
            fam,
            top=(fam.accent, fam.deep),
            left=(fam.accent, fam.deep),
            right=(fam.deep, fam.deep),
        )
        d.box(
            5.5,
            1.5,
            1.5,
            14,
            4,
            4.4,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
    elif kind == "box":
        d.box(
            0,
            1,
            0,
            5,
            5,
            4,
            fam,
            top=(fam.accent, fam.deep),
            left=(fam.accent, fam.deep),
            right=(fam.deep, fam.deep),
        )
        d.box(
            5.5,
            0.6,
            0,
            14,
            5.8,
            6,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
    elif kind == "trailer":
        d.slab(0, 1, 1, 12, 5, fam, h=0.8, top=("#5b6470", "#3d4450"))
        d.box(2, 1.5, 1.8, 8, 4, 4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    elif kind == "car":
        d.box(
            0,
            1,
            0,
            10,
            4.4,
            2,
            fam,
            top=(fam.accent, fam.deep),
            left=(fam.accent, fam.deep),
            right=(fam.deep, fam.deep),
        )
        d.box(
            2.5,
            1.3,
            2,
            5,
            3.8,
            1.6,
            fam,
            top=("#9fb3c8", "#7f93a8"),
            left=("#9fb3c8", "#7f93a8"),
            right=("#7f93a8", "#5f7388"),
        )
    else:
        d.box(
            0,
            1,
            0,
            12,
            4.8,
            4.5,
            fam,
            top=(fam.accent, fam.deep),
            left=(fam.accent, fam.deep),
            right=(fam.deep, fam.deep),
        )
        d.rect_on("left", 0, 5.8, 4.5, 8.5, 0.5, 3, 1.6, ("#9fb3c8", "#7f93a8"), rx=0.2)
    for x in (1.5, 8):
        d.box(
            x,
            0,
            0,
            2,
            1,
            1.8,
            fam,
            top=("#1f242b", "#111418"),
            left=("#1f242b", "#111418"),
            right=("#111418", "#06080b"),
            shadow=False,
        )


def r_forklift(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        1,
        0,
        6,
        4,
        3,
        fam,
        top=("#fde047", "#facc15"),
        left=("#fde047", "#facc15"),
        right=("#facc15", "#ca8a04"),
    )
    d.box(1, 1.5, 3, 3, 3, 4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(6, 1.6, 0, 0.6, 2.8, 8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        6.6,
        1.2,
        0,
        4,
        3.6,
        0.4,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    d.box(
        7,
        1.5,
        0.4,
        3,
        3,
        3,
        fam,
        top=("#e2c99b", "#c8a16a"),
        left=("#d6b585", "#b8905c"),
        right=("#b8905c", "#9a7648"),
    )


def r_drone(d: Drawing, fam: Family) -> None:
    d.box(4, 4, 5, 3, 3, 1, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for x, y in ((0, 0), (8, 0), (0, 8), (8, 8)):
        d.box(
            x + 1,
            y + 1,
            5.3,
            1,
            1,
            0.5,
            fam,
            top=CHASSIS,
            left=CHASSIS,
            right=CHASSIS_SIDE,
            shadow=False,
        )
        d.cylinder(x + 1.5, y + 1.5, 5.8, 1.6, 0.1, fam, body=("#c9d0da", "#aeb6c2"))
    d.cylinder(5.5, 5.5, 4.2, 0.5, 0.8, fam, body=("#1f242b", "#111418"))


def r_crawler(d: Drawing, fam: Family) -> None:
    for y in (0, 5):
        d.box(
            0,
            y,
            0,
            8,
            1.2,
            1.6,
            fam,
            top=("#1f242b", "#111418"),
            left=("#1f242b", "#111418"),
            right=("#111418", "#06080b"),
        )
    d.box(1, 1.2, 1.2, 6, 3.8, 1.6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.cylinder(2.5, 3, 2.8, 0.25, 3, fam, body=("#dfe4ea", "#aeb6c2"))
    d.box(1.8, 2.4, 5.8, 1.4, 1.2, 1, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)


def r_bench(d: Drawing, fam: Family, kind: str = "scope") -> None:
    d.box(
        0,
        0,
        0,
        12,
        9,
        6,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    if kind == "psu":
        screen(d, "left", 0, 9, 6, 0.8, 0.8, 4.4, 1.8, fam)
        screen(d, "left", 0, 9, 6, 6.2, 0.8, 4.4, 1.8, fam)
        for i in range(4):
            d.dot_on("left", 0, 9, 6, 1.5 + i * 2.8, 4.4, 0.45, "#ef4444" if i % 2 else "#1f2937")
    else:
        screen(d, "left", 0, 9, 6, 0.7, 0.7, 7, 4.2, fam)
        for i in range(4):
            d.dot_on("left", 0, 9, 6, 9 + (i % 2) * 1.6, 1.6 + (i // 2) * 1.6, 0.5, "#1f2937")


def r_handheld(d: Drawing, fam: Family, kind: str = "tester") -> None:
    d.box(
        0,
        0,
        0,
        5,
        2,
        10,
        fam,
        top=("#fde047", "#facc15") if kind == "meter" else CHASSIS,
        left=("#fde047", "#facc15") if kind == "meter" else CHASSIS,
        right=("#facc15", "#ca8a04") if kind == "meter" else CHASSIS_SIDE,
    )
    screen(d, "left", 0, 2, 10, 0.6, 0.8, 3.8, 3.4, fam)
    for r in range(3):
        for c in range(3):
            d.rect_on(
                "left",
                0,
                2,
                10,
                0.7 + c * 1.3,
                5 + r * 1.3,
                0.9,
                0.8,
                ("#f4f6f8", "#e2e6eb"),
                rx=0.15,
            )


def r_toolcase(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 14, 9, 4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(0, 9, 0, 14, 1, 9, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False)
    for i in range(4):
        d.rect_on(
            "top",
            0,
            0,
            4,
            1 + i * 3.2,
            1.5,
            2.4,
            6,
            ("#dfe4ea", "#aeb6c2") if i % 2 else ("#ef4444", "#b91c1c"),
            rx=0.3,
        )


def r_soldering(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        7,
        5,
        4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    screen(d, "left", 0, 5, 4, 0.6, 0.5, 3, 1.2, fam)
    d.cylinder(10, 2.5, 0, 0.7, 2.2, fam, body=("#dfe4ea", "#aeb6c2"))
    d.box(8.5, 2, 2.2, 5, 1, 0.8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False)


def r_meeting(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 24, 20, fam, h=1.0, top=("#eef1f5", "#dfe4ea"))
    d.box(0, 0, 1, 24, 1.2, 12, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False)
    screen(d, "left", 0, 1.2, 13, 5, 2, 14, 7, fam)
    d.cylinder(12, 11, 1, 6, 3.4, fam, body=("#a67c52", "#8b6b4a"))
    for x, y in ((4, 6), (20, 6), (4, 16), (20, 16), (12, 18.5)):
        d.box(
            x - 0.8,
            y - 0.8,
            1,
            1.6,
            1.6,
            1.6,
            fam,
            top=CHASSIS,
            left=CHASSIS,
            right=CHASSIS_SIDE,
            shadow=False,
        )


def r_videobar(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 16, 3.5, 2.8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.dot_on("left", 0, 3.5, 2.8, 8, 1.4, 0.8, "#1f2937")
    d.led("left", 0, 3.5, 2.8, 14.5, 1.4, GREEN)


def r_confphone(d: Drawing, fam: Family) -> None:
    d.cylinder(6, 6, 0, 5, 1.6, fam, body=("#3d4556", "#252b36"))
    screen(d, "top", 3, 4, 1.6, 0, 0, 5, 2.4, fam)
    d.led("top", 0, 0, 1.6, 9.5, 6, GREEN)


def r_headset(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 8, 4, fam, h=0.5, top=("#dfe4ea", "#c2c9d3"))
    d.cylinder(1.5, 2, 0.5, 1.4, 2.5, fam, body=("#3d4556", "#252b36"))
    d.cylinder(6.5, 2, 0.5, 1.4, 2.5, fam, body=("#3d4556", "#252b36"))
    d.box(
        1.5, 1.6, 3, 5, 0.8, 0.8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False
    )


def r_shredder(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 7, 6, 10, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        -0.3,
        -0.3,
        10,
        7.6,
        6.6,
        2.2,
        fam,
        top=("#1f242b", "#111418"),
        left=("#1f242b", "#111418"),
        right=("#111418", "#06080b"),
    )
    d.rect_on("left", 0, 6, 10, 1, 1.5, 5, 5.5, ("#9fb3c8", "#7f93a8"), rx=0.3)
    d.lines_on("left", 0, 6, 10, 1.4, 2, 4.2, 6, 0.8, "#f4f6f8", width=0.3)


def r_pinpad(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 5, 2, 10, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    screen(d, "left", 0, 2, 10, 0.5, 0.6, 4, 2.6, fam)
    for r in range(4):
        for c in range(3):
            d.rect_on(
                "left",
                0,
                2,
                10,
                0.7 + c * 1.3,
                4 + r * 1.3,
                0.9,
                0.8,
                ("#f4f6f8", "#e2e6eb") if not (r == 3 and c == 2) else "#22c55e",
                rx=0.15,
            )


def r_media(d: Drawing, fam: Family, kind: str = "usb") -> None:
    if kind == "usb":
        d.box(0, 0, 0, 3, 8, 1.4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        d.box(
            0.4,
            8,
            0.1,
            2.2,
            3,
            1.0,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.rect_on("top", 0, 0, 1.4, 0.4, 1, 2.2, 5, fam.accent, rx=0.3)
    elif kind == "sd":
        d.slab(0, 0, 0, 5, 6.5, fam, h=0.4, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        d.rect_on("top", 0, 0, 0.4, 0.5, 5, 4, 1.2, "#caa23a", rx=0.1)
        d.rect_on("top", 0, 0, 0.4, 0.8, 1, 3.4, 2.6, ("#f4f6f8", "#e2e6eb"), rx=0.2)
    elif kind == "disc":
        d.cylinder(5, 5, 0, 5, 0.3, fam, body=("#e6eaf0", "#c9d0da"))
        d.cylinder(5, 5, 0.3, 1.2, 0.2, fam, body=("#f4f6f8", "#e2e6eb"))
    else:
        d.box(0, 0, 0, 8, 12, 2, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        d.rect_on("top", 0, 0, 2, 0.8, 1, 6.4, 9, ("#4a525d", "#3d4450"), rx=0.5)
        d.led("top", 0, 0, 2, 7, 10.8, GREEN)


def r_safe(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 10, 9, 12, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.dot_on("left", 0, 9, 12, 3, 5, 1.4, "#c9d0da")
    d.dot_on("left", 0, 9, 12, 7, 7, 1.0, "#dfe4ea")
    d.rect_on("left", 0, 9, 12, 5.8, 6.8, 0.4, 3.2, "#dfe4ea", rx=0.2)
    screen(d, "left", 0, 9, 12, 5.5, 1.5, 3, 1.6, fam)


def r_shelving(d: Drawing, fam: Family, kind: str = "spares") -> None:
    for x, y in ((0, 0), (14, 0), (0, 6), (14, 6)):
        d.box(
            x,
            y,
            0,
            0.5,
            0.5,
            14,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    for z in (0.5, 5, 9.5):
        d.slab(0, 0, z, 14.5, 6.5, fam, h=0.3, top=("#dfe4ea", "#c2c9d3"))
        for i in range(4):
            paint = (
                (("#e2c99b", "#c8a16a"), ("#d6b585", "#b8905c"), ("#b8905c", "#9a7648"))
                if (kind == "spares" or i % 2)
                else (("#f4f6f8", "#e2e6eb"), ("#e6eaf0", "#d5dbe3"), ("#d5dbe3", "#c2c9d3"))
            )
            d.box(
                0.8 + i * 3.4,
                1,
                z + 0.3,
                2.8,
                4.5,
                3.4,
                fam,
                top=paint[0],
                left=paint[1],
                right=paint[2],
            )


def r_turnstile(d: Drawing, fam: Family, kind: str = "tripod") -> None:
    _plate(d, fam, 16, 14)
    if kind == "speed":
        for x in (1, 11):
            d.box(
                x,
                1,
                0.6,
                3,
                12,
                5,
                fam,
                top=("#dfe4ea", "#c2c9d3"),
                left=("#c9d0da", "#aeb6c2"),
                right=("#b8c0cb", "#a0a9b6"),
            )
            d.led("top", x, 1, 5.6, 1.5, 6, GREEN if x < 5 else "#ef4444")
        d.rect_on("left", 4, 7, 5.6, 0, 0.5, 7, 3.4, ("#9fb3c8", "#7f93a8"), rx=0.3, opacity=0.6)
        return
    d.box(
        6,
        4,
        0.6,
        3,
        5,
        10,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    for i in range(3):
        d.box(
            9,
            6 + i * 0.6,
            8 - i * 1.5,
            4 - i,
            0.5,
            0.5,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )


def r_barrier(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 24, 8)
    d.box(1, 3, 0.6, 3, 2.5, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        4,
        3.8,
        5,
        18,
        0.6,
        0.6,
        fam,
        top=("#f4f6f8", "#e2e6eb"),
        left=("#f4f6f8", "#e2e6eb"),
        right=("#e2e6eb", "#c9d0da"),
        shadow=False,
    )
    for x in (6, 11, 16):
        d.box(
            x,
            3.75,
            5.05,
            2,
            0.7,
            0.7,
            fam,
            top=("#ef4444", "#b91c1c"),
            left=("#ef4444", "#b91c1c"),
            right=("#b91c1c", "#7f1d1d"),
            shadow=False,
        )
    d.led("left", 1, 5.5, 6.6, 1.5, 0.8, "#ef4444")


def r_bollards(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 20, 6)
    for i in range(5):
        d.cylinder(2 + i * 4, 3, 0.6, 0.6, 4.2, fam, body=("#dfe4ea", "#aeb6c2"))
        d.cylinder(2 + i * 4, 3, 3, 0.65, 0.6, fam, body=("#fde047", "#facc15"))


def r_floodlight(d: Drawing, fam: Family) -> None:
    d.cylinder(5, 5, 0, 0.5, 20, fam, body=("#dfe4ea", "#aeb6c2"))
    d.box(
        1.5,
        4.5,
        19,
        7,
        1,
        0.5,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    for x in (1, 6):
        d.box(
            x,
            4,
            17.5,
            2.4,
            1.6,
            1.8,
            fam,
            top=("#fff6c8", "#fde68a"),
            left=("#fff6c8", "#fde68a"),
            right=CHASSIS_SIDE,
            shadow=False,
        )


def r_water_tower(d: Drawing, fam: Family) -> None:
    for x, y in ((2, 2), (10, 2), (2, 10), (10, 10)):
        d.box(
            x,
            y,
            0,
            0.6,
            0.6,
            16,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.cylinder(6.3, 6.3, 14, 5, 7, fam, body=("#f4f6f8", "#c9d0da"))
    d.cylinder(6.3, 6.3, 21, 5.2, 1.5, fam, body=("#4d566a", "#343c4b"))


def r_wallunit(d: Drawing, fam: Family, kind: str = "intercom") -> None:
    d.slab(0, 0, 0, 12, 1.2, fam, h=12, top=("#eef1f5", "#dfe4ea"), left=("#f4f6f9", "#e6eaf0"))
    if kind == "exit":
        d.box(
            3,
            1.2,
            8.5,
            6,
            0.8,
            2.6,
            fam,
            top=("#2fa86a", "#1f8a4c"),
            left=("#2fa86a", "#1f8a4c"),
            right=("#1f8a4c", "#166536"),
        )
        d.rect_on("left", 3, 2, 11.1, 1, 0.6, 1.2, 1.5, "#f4f6f8", rx=0.2)
        d.rect_on("left", 3, 2, 11.1, 2.8, 1.1, 2.2, 0.4, "#f4f6f8")
        return
    if kind == "light":
        d.box(
            4,
            1.2,
            8.5,
            4,
            1.2,
            1.6,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        for x in (1.5, 8):
            d.box(
                x,
                1.2,
                8.7,
                2,
                1.4,
                1.2,
                fam,
                top=("#fff6c8", "#fde68a"),
                left=("#fff6c8", "#fde68a"),
                right=CHASSIS_SIDE,
                shadow=False,
            )
        return
    if kind not in ("intercom", "keys", "firstaid", "aed", "firepanel"):
        _generic(
            d, fam, kind
        )  # the batch-8 kinds (siren, lock, doorbell, panic) have their 3D builder only
        return
    w, h, paint = {
        "intercom": (3, 5, "steel"),
        "keys": (6, 7, "dark"),
        "firstaid": (5, 5, "light"),
        "aed": (4.5, 5.5, "green"),
        "firepanel": (6, 7, "red"),
    }[kind]
    tones = {
        "steel": STEEL_T,
        "dark": DARK_T,
        "light": LIGHT_T,
        "green": (("#2fa86a", "#1f8a4c"), ("#2fa86a", "#1f8a4c"), ("#1f8a4c", "#166536")),
        "red": (("#ef4444", "#b91c1c"), ("#ef4444", "#b91c1c"), ("#b91c1c", "#7f1d1d")),
    }[paint]
    d.box(6 - w / 2, 1.2, 3.5, w, 1.6, h, fam, top=tones[0], left=tones[1], right=tones[2])
    if kind == "firstaid":
        d.rect_on("left", 6 - w / 2, 2.8, 3.5 + h, w / 2 - 1.1, h / 2 - 0.35, 2.2, 0.7, "#22a55b")
        d.rect_on("left", 6 - w / 2, 2.8, 3.5 + h, w / 2 - 0.35, h / 2 - 1.1, 0.7, 2.2, "#22a55b")
    elif kind == "firepanel":
        screen(d, "left", 6 - w / 2, 2.8, 3.5 + h, 0.8, 0.8, 4.4, 1.6, fam)
        for i in range(4):
            d.led("left", 6 - w / 2, 2.8, 3.5 + h, 1.2 + i * 1.2, 4, GREEN if i < 3 else AMBER)
    elif kind == "intercom":
        d.vents("left", 6 - w / 2, 2.8, 3.5 + h, 0.5, 0.5, 2, 1.6, "#4d566a")
        d.dot_on("left", 6 - w / 2, 2.8, 3.5 + h, 1.5, 3.5, 0.4, "#1f2937")
    elif kind == "aed":
        d.rect_on(
            "left",
            6 - w / 2,
            2.8,
            3.5 + h,
            0.6,
            0.8,
            3.3,
            3.6,
            ("#9fb3c8", "#7f93a8"),
            rx=0.3,
            opacity=0.7,
        )
    else:
        for r in range(4):
            for c in range(5):
                d.rect_on(
                    "left",
                    6 - w / 2,
                    2.8,
                    3.5 + h,
                    0.7 + c,
                    0.8 + r * 1.5,
                    0.5,
                    0.8,
                    ("#fde047", "#ef4444", "#3b82f6")[c % 3],
                    rx=0.1,
                )


STEEL_T = (("#dfe4ea", "#c2c9d3"), ("#c9d0da", "#aeb6c2"), ("#b8c0cb", "#a0a9b6"))
DARK_T = (CHASSIS, CHASSIS, CHASSIS_SIDE)
LIGHT_T = (("#e6eaf0", "#d5dbe3"), ("#d9dee6", "#c2c9d3"), ("#b8c0cb", "#a0a9b6"))


def r_hosereel(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 10, 1.2, fam, h=12, top=("#eef1f5", "#dfe4ea"), left=("#f4f6f9", "#e6eaf0"))
    d.box(
        3.5,
        1.2,
        4,
        3,
        1.8,
        0.5,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    d.cylinder(5, 3.8, 3, 3.2, 1.6, fam, body=("#ef4444", "#b91c1c"))
    d.cylinder(5, 3.8, 3.2, 2.4, 1.2, fam, body=("#dc2626", "#991b1b"))


def r_open_rack(d: Drawing, fam: Family, kind: str = "two-post") -> None:
    if kind == "wall":
        d.slab(0, 0, 0, 14, 1.2, fam, h=14, top=("#eef1f5", "#dfe4ea"), left=("#f4f6f9", "#e6eaf0"))
        d.box(2, 1.2, 3, 10, 6, 8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        d.rect_on(
            "left", 2, 7.2, 11, 0.6, 0.6, 8.8, 6.8, ("#9fb3c8", "#7f93a8"), rx=0.3, opacity=0.6
        )
        return
    for x in (0, 11):
        d.box(
            x,
            4,
            0,
            0.8,
            1.5,
            22,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    for z in (2, 6, 10, 14):
        bezel(d, 0.8, 0, z, 10.4, 6, 3, fam)
        ports(d, 0.8, 6, z + 3, 0.5, 0.3, 4, fam, gap=2.2)


def r_cable_manager(d: Drawing, fam: Family) -> None:
    bezel(d, 0, 0, 0, 24, 6, 3.6, fam)
    for i in range(6):
        d.rect_on("left", 0, 6, 3.6, 1.5 + i * 3.6, 0.5, 1.6, 2.6, "#1f2937", rx=0.6)


def r_splice(d: Drawing, fam: Family, kind: str = "tray") -> None:
    if kind == "tray":
        d.box(
            0,
            0,
            0,
            10,
            7,
            1.2,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
    else:
        d.box(0, 0, 0, 10, 7, 1.2, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for i in range(6):
        d.rect_on(
            "top",
            0,
            0,
            1.2,
            1 + i * 1.5,
            1,
            0.6,
            5,
            ("#fb923c", "#2dd4bf", "#3b82f6", "#facc15", "#111418", "#caa23a")[i],
            rx=0.3,
        )


def r_outlet(d: Drawing, fam: Family, kind: str = "wall") -> None:
    if kind == "floor":
        d.slab(0, 0, 0, 10, 10, fam, h=0.4, top=("#eef1f5", "#dfe4ea"))
        d.box(
            2.5,
            2.5,
            0.4,
            5,
            5,
            0.6,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.rect_on("top", 2.5, 2.5, 1, 1, 1.5, 1.2, 1, "#1f2937", rx=0.1)
        d.rect_on("top", 2.5, 2.5, 1, 2.8, 1.5, 1.2, 1, "#1f2937", rx=0.1)
        return
    d.slab(0, 0, 0, 10, 1.2, fam, h=10, top=("#eef1f5", "#dfe4ea"), left=("#f4f6f9", "#e6eaf0"))
    d.box(
        3,
        1.2,
        3,
        4,
        0.6,
        4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    d.rect_on("left", 3, 1.8, 7, 0.6, 1.4, 1.2, 1.1, "#1f2937", rx=0.15)
    d.rect_on("left", 3, 1.8, 7, 2.2, 1.4, 1.2, 1.1, "#1f2937", rx=0.15)


def r_vessel(d: Drawing, fam: Family, kind: str = "reactor") -> None:
    if kind == "column":
        d.cylinder(4, 4, 0, 3, 2, fam, body=("#4d566a", "#343c4b"))
        d.cylinder(4, 4, 2, 2.5, 26, fam, body=("#dfe4ea", "#aeb6c2"))
        for z in (8, 16, 24):
            d.cylinder(4, 4, z, 2.7, 0.4, fam, body=("#4d566a", "#343c4b"))
        return
    for x, y in ((1, 1), (7, 1), (1, 7), (7, 7)):
        d.box(
            x,
            y,
            0,
            0.8,
            0.8,
            4,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.cylinder(4.4, 4.4, 3, 4, 9, fam, body=("#dfe4ea", "#aeb6c2"))
    d.cylinder(4.4, 4.4, 12, 3, 1.5, fam, body=("#e6eaf0", "#c9d0da"))
    d.box(3.6, 3.6, 13.5, 1.6, 1.6, 2.2, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)


def r_pipeline(d: Drawing, fam: Family) -> None:
    for x in (1, 11, 21):
        d.box(
            x, 3, 0, 1.4, 1.4, 2.4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False
        )
    d.box(
        0,
        2.6,
        2.4,
        30,
        2.4,
        2.4,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(13, 2, 2, 4, 3.6, 3.6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.cylinder(15, 3.8, 5.6, 1.6, 0.8, fam, body=(fam.accent, fam.deep))


def r_crane(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 30, 16)
    for x, y in ((1, 1), (27, 1), (1, 13), (27, 13)):
        d.box(
            x,
            y,
            0.6,
            1,
            1,
            16,
            fam,
            top=("#fde047", "#facc15"),
            left=("#fde047", "#facc15"),
            right=("#facc15", "#ca8a04"),
            shadow=False,
        )
    for y in (1, 13):
        d.box(
            1,
            y,
            16.6,
            27,
            1,
            1.2,
            fam,
            top=("#fde047", "#facc15"),
            left=("#fde047", "#facc15"),
            right=("#facc15", "#ca8a04"),
            shadow=False,
        )
    d.box(10, 2, 16, 3, 11, 1.8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        10,
        6,
        0.6,
        4,
        4,
        3,
        fam,
        top=("#e2c99b", "#c8a16a"),
        left=("#d6b585", "#b8905c"),
        right=("#b8905c", "#9a7648"),
    )


def r_weighbridge(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 32, 16)
    d.slab(4, 4, 0.6, 22, 8, fam, h=0.8, top=("#5b6470", "#3d4450"))
    r_vehicle(d, fam, "box")
    d.box(
        27,
        10,
        0.6,
        4,
        4,
        6,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )


def r_silo(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 24, 12)
    for x in (5, 17):
        d.cylinder(x, 6, 0.6, 4.2, 16, fam, body=("#dfe4ea", "#aeb6c2"))
        d.cylinder(x, 6, 16.6, 3, 2, fam, body=("#4d566a", "#343c4b"))


def r_water_treatment(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 32, 24)
    for x in (7, 21):
        d.cylinder(x, 8, 0.6, 5.5, 3, fam, body=("#c9cfd6", "#b3bac3"))
        d.cylinder(x, 8, 3.6, 5.1, 0.3, fam, body=("#60a5fa", "#2b7fc4"))
    d.box(10, 16, 0.6, 8, 5, 4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.box(
        22,
        17,
        0.6,
        6,
        5,
        4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )


def _strand(
    d: Drawing, fam: Family, x: float, y: float, z: float, n: int, horizontal: bool = False
) -> None:
    for i in range(n):
        if horizontal:
            d.cylinder(x + i * 0.6, y, z, 0.35, 0.3, fam, body=("#c9d0da", "#8a94a3"))
        else:
            d.cylinder(x, y, z - i * 0.5, 0.35, 0.3, fam, body=("#c9d0da", "#8a94a3"))


def r_hv_tower(d: Drawing, fam: Family, kind: str = "tension") -> None:
    if kind == "lightning":
        d.box(
            3,
            3,
            0,
            2,
            2,
            0.6,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.cylinder(4, 4, 0.6, 0.5, 30, fam, body=("#dfe4ea", "#aeb6c2"))
        d.cylinder(4, 4, 30.6, 0.15, 4, fam, body=("#d08a4a", "#b87333"))
        return
    if kind == "guyed":
        d.box(
            3,
            3,
            0,
            2,
            2,
            26,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(
            -3,
            3.5,
            25,
            14,
            1,
            0.8,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
        for x in (-2, 4, 10):
            _strand(d, fam, x, 4, 24.5, 6)
        return
    r_pylon(d, fam)
    for x in (-2, 16):
        _strand(d, fam, x, 8, 16.5, 7, horizontal=True)


def r_insulator_string(d: Drawing, fam: Family, kind: str = "suspension") -> None:
    d.box(
        0,
        3,
        14,
        8,
        1,
        1,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    if kind == "tension":
        _strand(d, fam, 0.5, 3.5, 13.5, 10, horizontal=True)
        d.box(
            6.5,
            3.4,
            13,
            8,
            0.3,
            0.3,
            fam,
            top=CHASSIS,
            left=CHASSIS,
            right=CHASSIS_SIDE,
            shadow=False,
        )
    else:
        _strand(d, fam, 4, 3.5, 13.5, 10)
        d.box(
            -2,
            3.4,
            8.2,
            12,
            0.3,
            0.3,
            fam,
            top=CHASSIS,
            left=CHASSIS,
            right=CHASSIS_SIDE,
            shadow=False,
        )


def r_conductor_bundle(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 30, 8)
    for y, z in ((2, 5), (5, 5), (2, 8), (5, 8)):
        d.box(
            0,
            y,
            z,
            28,
            0.35,
            0.35,
            fam,
            top=CHASSIS,
            left=CHASSIS,
            right=CHASSIS_SIDE,
            shadow=False,
        )
    for x in (4, 14, 24):
        d.box(
            x,
            1.8,
            4.8,
            0.4,
            3.6,
            3.6,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )


def r_line_trap(d: Drawing, fam: Family) -> None:
    d.box(
        2,
        2,
        0,
        3,
        3,
        0.6,
        fam,
        top=("#c9cfd6", "#b3bac3"),
        left=("#bfc5cc", "#a9b0b9"),
        right=("#9aa1aa", "#858c95"),
    )
    d.cylinder(3.5, 3.5, 0.6, 0.6, 5, fam, body=("#c9d0da", "#8a94a3"))
    d.cylinder(3.5, 3.5, 5.6, 2.3, 5, fam, body=("#d08a4a", "#b87333"))
    d.cylinder(3.5, 3.5, 10.6, 2.5, 0.3, fam, body=("#dfe4ea", "#aeb6c2"))


def r_cable_end(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 10, 8)
    d.box(
        2,
        2,
        0.6,
        2,
        2,
        4,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.cylinder(3, 3, 4.6, 0.8, 9, fam, body=("#c9d0da", "#8a94a3"))
    d.cylinder(3, 3, 13.6, 0.5, 1.5, fam, body=("#dfe4ea", "#aeb6c2"))
    d.box(
        3,
        -1,
        0,
        0.8,
        0.8,
        4,
        fam,
        top=("#1f242b", "#111418"),
        left=("#1f242b", "#111418"),
        right=("#111418", "#06080b"),
        shadow=False,
    )


def r_joint_bay(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 26, 14)
    d.slab(3, 4, 0.6, 20, 6, fam, h=0.4, top=("#a67c52", "#8b6b4a"))
    for y in (5, 7, 9):
        d.box(
            3,
            y,
            1,
            20,
            0.6,
            0.6,
            fam,
            top=("#1f242b", "#111418"),
            left=("#1f242b", "#111418"),
            right=("#111418", "#06080b"),
            shadow=False,
        )
        d.box(
            9 + (y - 5),
            y - 0.3,
            0.9,
            4,
            1.2,
            1.2,
            fam,
            top=CHASSIS,
            left=CHASSIS,
            right=CHASSIS_SIDE,
            shadow=False,
        )


def r_cable_tunnel(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        16,
        12,
        6,
        fam,
        top=("#c9cfd6", "#b3bac3"),
        left=("#bfc5cc", "#a9b0b9"),
        right=("#9aa1aa", "#858c95"),
    )
    d.cylinder(8, 6, 6, 6, 0.8, fam, body=("#c9cfd6", "#b3bac3"))
    for y in (1, 10):
        for z in (1.5, 3, 4.5):
            d.box(
                0.5,
                y,
                z,
                15,
                0.5,
                0.5,
                fam,
                top=("#1f242b", "#111418"),
                left=("#1f242b", "#111418"),
                right=("#111418", "#06080b"),
                shadow=False,
            )


def r_riser_pole(d: Drawing, fam: Family) -> None:
    r_pole(d, fam)
    d.cylinder(5.2, 4.8, 0, 0.6, 8, fam, body=("#dfe4ea", "#aeb6c2"))
    for x in (2.4, 4, 5.6):
        d.cylinder(x, 5.2, 12, 0.4, 2.4, fam, body=("#c9d0da", "#8a94a3"))


def r_pole_equipment(d: Drawing, fam: Family, kind: str = "recloser") -> None:
    r_pole(d, fam)
    if kind == "recloser":
        d.box(4.5, 3, 10.5, 3.4, 2.4, 2.8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        for x in (5, 6.2, 7.4):
            d.cylinder(x, 4, 13.3, 0.25, 1.6, fam, body=("#c9d0da", "#8a94a3"))
    elif kind == "capacitor":
        d.box(
            1.5,
            3,
            11.5,
            5,
            2.6,
            0.3,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
        for x in (1.8, 3.4, 5):
            d.box(
                x,
                3.4,
                11.8,
                1.2,
                0.9,
                2.6,
                fam,
                top=("#dfe4ea", "#c2c9d3"),
                left=("#c9d0da", "#aeb6c2"),
                right=("#b8c0cb", "#a0a9b6"),
            )
    elif kind == "regulator":
        d.cylinder(6, 4, 10, 1.4, 4.2, fam, body=("#4d566a", "#343c4b"))
        for x in (5.3, 6.7):
            d.cylinder(x, 4, 14.2, 0.25, 1.6, fam, body=("#c9d0da", "#8a94a3"))
    else:
        d.box(
            1,
            3.7,
            13.2,
            6,
            0.45,
            0.45,
            fam,
            top=("#a67c52", "#8b6b4a"),
            left=("#a67c52", "#8b6b4a"),
            right=("#8b6b4a", "#6f5439"),
            shadow=False,
        )
        for x in (1.6, 4, 6.4):
            d.cylinder(x, 4, 11.5, 0.22, 2.6, fam, body=("#c9d0da", "#8a94a3"))
    d.box(
        1.5,
        3.3,
        7.5,
        1.6,
        1.0,
        2.6,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )


def r_line_sensor(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 22, 6)
    d.box(0, 2.8, 7, 22, 0.3, 0.3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False)
    d.cylinder(11, 3, 6.2, 1.0, 2.4, fam, body=("#3d4556", "#252b36"))
    d.led("left", 10, 4, 7.4, 1, 0.6, "#ef4444")


def r_streetlight(d: Drawing, fam: Family) -> None:
    d.box(
        3,
        3,
        0,
        2.2,
        2.2,
        0.4,
        fam,
        top=("#c9cfd6", "#b3bac3"),
        left=("#bfc5cc", "#a9b0b9"),
        right=("#9aa1aa", "#858c95"),
    )
    d.cylinder(4, 4, 0.4, 0.4, 16, fam, body=("#dfe4ea", "#aeb6c2"))
    d.box(
        4,
        3.6,
        17,
        4,
        0.5,
        0.4,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    d.box(
        7, 3.2, 17, 3.2, 1.2, 0.5, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False
    )
    d.box(
        4,
        3.4,
        2,
        1.2,
        0.9,
        2.6,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )


def r_kiosk_substation(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 16, 10, fam, h=0.6, top=("#c9cfd6", "#b3bac3"))
    d.box(
        1,
        1,
        0.6,
        14,
        8,
        8,
        fam,
        top=("#a3b394", "#8a9a7a"),
        left=("#a3b394", "#8a9a7a"),
        right=("#8a9a7a", "#6f7d62"),
    )
    for x, w in ((1.5, 4), (6, 5), (11.5, 3)):
        d.rect_on("left", 1, 9, 8.6, x, 1, w, 6, ("#a3b394", "#8a9a7a"), rx=0.2)


def r_mobile_substation(d: Drawing, fam: Family) -> None:
    d.slab(0, 1, 0.9, 26, 7, fam, h=0.9, top=("#5b6470", "#3d4450"))
    x: float
    for x in (17, 20, 23):
        d.box(
            x,
            0,
            0,
            2,
            1.2,
            1.8,
            fam,
            top=("#1f242b", "#111418"),
            left=("#1f242b", "#111418"),
            right=("#111418", "#06080b"),
            shadow=False,
        )
    d.box(2, 2, 1.8, 8, 5, 5, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for x in (12, 14.6, 17.2):
        d.cylinder(x, 2.5, 1.8, 0.45, 4.5, fam, body=("#c9d0da", "#8a94a3"))
        d.cylinder(x, 6.5, 1.8, 0.45, 4.5, fam, body=("#c9d0da", "#8a94a3"))
    d.box(
        20,
        2,
        1.8,
        3,
        5,
        4.4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )


def r_gantry(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 28, 18)
    for x in (2, 24):
        d.box(
            x,
            2,
            0.6,
            2,
            2,
            18,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
    d.box(
        2,
        2,
        17.6,
        24,
        1.5,
        1,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )
    for x in (8, 14, 20):
        _strand(d, fam, x, 2.7, 17, 8)


def r_ngr(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        8,
        6,
        0.4,
        fam,
        top=("#c9cfd6", "#b3bac3"),
        left=("#bfc5cc", "#a9b0b9"),
        right=("#9aa1aa", "#858c95"),
    )
    d.box(
        0.5,
        0.5,
        0.4,
        7,
        5,
        8,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.vents("left", 0.5, 5.5, 8.4, 0.4, 0.6, 6.2, 7, "#5a6068")
    d.cylinder(4, 3, 8.4, 0.4, 2.2, fam, body=("#c9d0da", "#8a94a3"))


def r_facts(d: Drawing, fam: Family, kind: str = "statcom") -> None:
    _plate(d, fam, 42, 28)
    if kind == "series":
        for x, y in ((6, 6), (28, 6), (6, 20), (28, 20)):
            d.cylinder(x, y, 0.6, 0.6, 7, fam, body=("#c9d0da", "#8a94a3"))
        d.slab(4, 4, 7.6, 26, 18, fam, h=0.6, top=("#dfe4ea", "#c2c9d3"))
        for i in range(3):
            for k in range(4):
                d.box(
                    6 + i * 8,
                    6 + k * 4,
                    8.2,
                    2.5,
                    1.5,
                    2.6,
                    fam,
                    top=("#dfe4ea", "#c2c9d3"),
                    left=("#c9d0da", "#aeb6c2"),
                    right=("#b8c0cb", "#a0a9b6"),
                )
    elif kind == "svc":
        d.box(
            2,
            4,
            0.6,
            16,
            12,
            10,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        for i in range(3):
            for k in range(3):
                d.cylinder(24 + i * 6, 8, 2.6 + k * 1.4, 1.9, 1.2, fam, body=("#d08a4a", "#b87333"))
    elif kind == "condenser":
        d.box(
            4,
            8,
            0.6,
            22,
            9,
            1.2,
            fam,
            top=("#c9cfd6", "#b3bac3"),
            left=("#bfc5cc", "#a9b0b9"),
            right=("#9aa1aa", "#858c95"),
        )
        d.box(6, 9, 1.8, 12, 7, 7, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        d.cylinder(21, 12.5, 1.8, 1.8, 4, fam, body=("#dfe4ea", "#aeb6c2"))
    else:
        d.box(2, 4, 0.6, 18, 8, 9, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        for i in range(3):
            for k in range(3):
                d.cylinder(26 + i * 5, 8, 2.6 + k * 1.2, 1.5, 1.0, fam, body=("#d08a4a", "#b87333"))
        d.box(24, 16, 0.6, 8, 6, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)


def r_gen_breaker(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 16, 10)
    d.box(3, 2, 0.6, 9, 6, 8, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for y in (2.5, 4.5, 6.5):
        d.box(
            -2,
            y,
            5,
            5,
            1.6,
            1.6,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
        d.box(
            12,
            y,
            5,
            5,
            1.6,
            1.6,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    screen(d, "left", 3, 8, 8.6, 2.5, 1.5, 3.5, 2, fam)


def r_bus_duct(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 32, 12)
    for x in (2, 14, 26):
        d.box(
            x, 2, 0.6, 1, 8, 4.4, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE, shadow=False
        )
    for y in (1.5, 4.5, 7.5):
        d.box(
            0,
            y,
            4.6,
            30,
            2.4,
            2.4,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )


def r_plant_equipment(d: Drawing, fam: Family, kind: str = "condenser") -> None:
    _plate(d, fam, 36, 26)
    if kind in ("condenser", "feedpump", "deaerator"):
        d.box(
            4,
            8,
            0.6,
            18,
            7,
            6,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(8, 9, 6.6, 6, 5, 3, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        d.box(24, 9, 0.6, 8, 5, 5, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    elif kind in ("intake", "floating", "offshore"):
        d.slab(0, 0, 0.6, 34, 12, fam, h=0.3, top=("#60a5fa", "#2b7fc4"))
        if kind == "offshore":
            d.cylinder(16, 6, 0.9, 1.6, 6, fam, body=("#fde047", "#facc15"))
            d.cylinder(16, 6, 6.9, 0.9, 20, fam, body=("#f4f6f8", "#c9d0da"))
        elif kind == "floating":
            for c in range(4):
                d.slab(
                    2 + c * 8,
                    2,
                    0.9,
                    7,
                    7,
                    fam,
                    h=1.6,
                    top=("#1e3a8a", "#0f2a52"),
                    left=("#1e3a8a", "#0f2a52"),
                    right=("#0f2a52", "#0a1c38"),
                )
        else:
            d.box(
                4,
                14,
                0.6,
                12,
                8,
                7,
                fam,
                top=("#e6eaf0", "#d5dbe3"),
                left=("#d9dee6", "#c2c9d3"),
                right=("#b8c0cb", "#a0a9b6"),
            )
    elif kind in ("coal", "fgd", "hrsg", "compressor", "lng", "h2storage"):
        d.box(
            4,
            6,
            0.6,
            22,
            14,
            12,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        if kind in ("fgd", "hrsg"):
            _chimney(d, fam, 28, 12, 26)
        if kind == "lng":
            d.cylinder(16, 13, 0.6, 11, 14, fam, body=("#f4f6f8", "#c9d0da"))
    else:
        d.box(
            6,
            8,
            0.6,
            14,
            10,
            8,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.box(22, 10, 0.6, 8, 6, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        d.box(
            6,
            4,
            4,
            22,
            2.4,
            2.4,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )


def r_riser(d: Drawing, fam: Family) -> None:
    for z in (0, 6, 12):
        d.slab(0, 0, z, 14, 8, fam, h=0.5, top=("#c9cfd6", "#b3bac3"))
    d.box(2, 5, 0.5, 1.6, 1.2, 18, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    for z in (2, 8, 14):
        d.box(
            2,
            3.5,
            z,
            2.2,
            1.6,
            1.8,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )


def r_meter_bank(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 16, 1.2, fam, h=12, top=("#eef1f5", "#dfe4ea"), left=("#f4f6f9", "#e6eaf0"))
    for r in range(2):
        for c in range(4):
            d.box(
                1 + c * 3.6,
                1.2,
                1.5 + r * 5,
                2.8,
                1.2,
                3.6,
                fam,
                top=("#e6eaf0", "#d5dbe3"),
                left=("#d9dee6", "#c2c9d3"),
                right=("#b8c0cb", "#a0a9b6"),
                shadow=False,
            )
            screen(d, "left", 1 + c * 3.6, 2.4, 5.1 + r * 5, 0.5, 0.4, 1.8, 0.9, fam)


def r_pfc_panel(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        8,
        6,
        16,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.rect_on("left", 0, 6, 16, 0.8, 4, 6.4, 8, ("#9fb3c8", "#7f93a8"), rx=0.3, opacity=0.6)
    for r in range(3):
        for c in range(3):
            d.dot_on("left", 0, 6, 16, 2 + c * 2, 5.5 + r * 2.4, 0.6, "#c9d0da")
    screen(d, "left", 0, 6, 16, 1.5, 1, 5, 2, fam)


def r_harmonic_filter(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 16, 10)
    for i in range(3):
        for k in range(3):
            d.cylinder(3 + i * 5, 3, 1.4 + k * 1.2, 1.5, 1.0, fam, body=("#d08a4a", "#b87333"))
        d.box(
            2 + i * 5,
            6,
            0.6,
            2.4,
            1.4,
            3.2,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
        )


def r_isolation_transformer(d: Drawing, fam: Family) -> None:
    d.box(0, 0, 0, 7, 5, 6, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
    d.lines_on("left", 0, 5, 6, 0.5, 1, 6, 8, 0.5, "#c9d0da", width=0.25)
    d.box(
        2,
        1.5,
        6,
        3,
        2,
        1.4,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
        shadow=False,
    )


def r_earth_pit(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 12, 12, fam, h=0.4, top=("#a67c52", "#8b6b4a"))
    d.box(
        4,
        4,
        0.4,
        4,
        4,
        1.0,
        fam,
        top=("#c9cfd6", "#b3bac3"),
        left=("#bfc5cc", "#a9b0b9"),
        right=("#9aa1aa", "#858c95"),
    )
    d.rect_on("top", 4, 4, 1.4, 0.4, 0.4, 3.2, 3.2, ("#4a3a2c", "#3a2f24"), rx=0.2)
    d.cylinder(6, 6, 1.4, 0.2, 1.2, fam, body=("#d08a4a", "#b87333"))


def r_air_terminal(d: Drawing, fam: Family) -> None:
    d.box(
        0,
        0,
        0,
        16,
        12,
        6,
        fam,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    for x, y in ((1, 1), (15, 1), (1, 11), (15, 11)):
        d.cylinder(x, y, 6, 0.1, 4.5, fam, body=("#d08a4a", "#b87333"))
    d.box(
        1,
        1,
        6.2,
        14,
        0.15,
        0.15,
        fam,
        top=("#d08a4a", "#b87333"),
        left=("#d08a4a", "#b87333"),
        right=("#b87333", "#8f5a28"),
        shadow=False,
    )
    d.box(
        1,
        11,
        6.2,
        14,
        0.15,
        0.15,
        fam,
        top=("#d08a4a", "#b87333"),
        left=("#d08a4a", "#b87333"),
        right=("#b87333", "#8f5a28"),
        shadow=False,
    )


def r_charging_plaza(d: Drawing, fam: Family) -> None:
    _plate(d, fam, 40, 22)
    for i in range(4):
        d.box(
            2 + i * 9,
            3,
            0.6,
            3,
            2,
            8,
            fam,
            top=("#e6eaf0", "#d5dbe3"),
            left=("#d9dee6", "#c2c9d3"),
            right=("#b8c0cb", "#a0a9b6"),
        )
        d.rect_on("left", 2 + i * 9, 5, 8.6, 0, 0, 3, 0.8, fam.accent)
    for x in (0, 18, 36):
        d.box(
            x,
            1,
            0.6,
            1,
            1,
            9,
            fam,
            top=("#dfe4ea", "#c2c9d3"),
            left=("#c9d0da", "#aeb6c2"),
            right=("#b8c0cb", "#a0a9b6"),
            shadow=False,
        )
    d.slab(
        -1,
        0,
        9.6,
        40,
        12,
        fam,
        h=0.5,
        top=("#1e3a8a", "#0f2a52"),
        left=("#1e3a8a", "#0f2a52"),
        right=("#0f2a52", "#0a1c38"),
    )
    r_vehicle(d, fam, "car")


def _generic(d: Drawing, fam: Family, seed: str, tall: bool = False) -> None:
    """A flat stand-in for a batch-7 builder: a plate, a body and a drum,
    sized from the kind so sibling kinds still differ on the sheet."""
    n = sum(ord(ch) for ch in seed)
    w, dp = 14 + n % 9, 10 + n % 7
    h = (12 + n % 9) if tall else (5 + n % 6)
    _plate(d, fam, w + 4, dp + 4)
    d.box(
        1,
        1,
        0.6,
        w * 0.6,
        dp,
        h,
        fam,
        top=("#dfe4ea", "#c2c9d3"),
        left=("#c9d0da", "#aeb6c2"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.cylinder(
        w * 0.6 + 3 + (w * 0.4 - 4) / 2,
        1 + dp / 2,
        0.6,
        min(3.5, w * 0.16),
        h * 0.8,
        fam,
        body=(fam.pale, fam.deep),
    )


def r_nuclear_part(d: Drawing, fam: Family, kind: str = "steam_gen") -> None:
    _generic(
        d, fam, kind, tall=kind in ("steam_gen", "pressuriser", "stack", "ash_silo", "dry_cask")
    )


def r_re_detail(d: Drawing, fam: Family, kind: str = "csp") -> None:
    _generic(d, fam, kind, tall=kind in ("csp", "met_mast", "monopile", "jacket", "offshore_sub"))


def r_grid_gear(d: Drawing, fam: Family, kind: str = "gis") -> None:
    if kind in ("sectionaliser", "lbs", "service_drop"):
        r_pole(d, fam)
    else:
        _generic(d, fam, kind, tall=kind == "gis")


def r_home_energy(d: Drawing, fam: Family, kind: str = "panel") -> None:
    _generic(d, fam, kind)


def r_hvac(d: Drawing, fam: Family, kind: str = "rtu") -> None:
    _generic(d, fam, kind)


def r_fire_gear(d: Drawing, fam: Family, kind: str = "pump") -> None:
    _generic(d, fam, kind, tall=kind == "riser")


def r_building_part(d: Drawing, fam: Family, kind: str = "elevator") -> None:
    _generic(d, fam, kind, tall=kind == "elevator")


def r_osp(d: Drawing, fam: Family, kind: str = "manhole") -> None:
    if kind == "strand":
        r_pole(d, fam)
    else:
        _generic(d, fam, kind)


def r_radio(d: Drawing, fam: Family, kind: str = "dwdm") -> None:
    if kind in ("dwdm", "edfa", "ptp", "pmu"):
        r_server(d, fam, 1)
    else:
        _generic(d, fam, kind, tall=kind in ("microwave", "sector", "gps"))


def r_process(d: Drawing, fam: Family, kind: str = "pump") -> None:
    _generic(d, fam, kind, tall=kind in ("cyclone", "flare", "sphere", "furnace", "press"))


def r_workplace(d: Drawing, fam: Family, kind: str = "all_in_one") -> None:
    _generic(d, fam, kind)


def r_rack(d: Drawing, fam: Family, filled: int = 5) -> None:
    """A 42U cabinet, doors off: rails, a stack of servers, blanks below."""
    w, dp, h = 15, 15, 36
    d.box(0, 0, 0, w, dp, h, fam, left=("#2e3542", "#1c212b"), right=("#3d4556", "#252b36"))
    d.rect_on("left", 0, dp, h, 1.2, 1.2, w - 2.4, h - 2.4, "#0f131a", rx=0.4)
    d.rect_on("left", 0, dp, h, 1.2, 1.2, 0.6, h - 2.4, "#4d566a")
    d.rect_on("left", 0, dp, h, w - 1.8, 1.2, 0.6, h - 2.4, "#4d566a")
    b = 2.0
    for i in range(filled):
        units = 2 if i % 3 == 1 else 1
        uh = 2.2 * units
        d.rect_on("left", 0, dp, h, 2.0, b, w - 4.0, uh - 0.3, CHASSIS, rx=0.25)
        for j in range(3):
            d.rect_on(
                "left",
                0,
                dp,
                h,
                2.6 + j * 2.6,
                b + 0.45,
                2.1,
                uh - 1.2,
                ("#cfd5dd", "#aeb6c2"),
                rx=0.2,
            )
        d.led("left", 0, dp, h, w - 3.0, b + uh / 2 - 0.15, GREEN if i % 2 else fam.accent)
        b += uh
    while b < h - 3:
        d.rect_on("left", 0, dp, h, 2.0, b, w - 4.0, 1.9, "#1c212b", rx=0.25)
        d.vents("left", 0, dp, h, 2.6, b + 0.5, w - 5.2, 1.0, "#2e3542")
        b += 2.2
    d.rect_on("top", 0, 0, h, 2, 2, w - 4, dp - 4, "#1a1f29", rx=0.5, opacity=0.35)


def r_blade_chassis(d: Drawing, fam: Family) -> None:
    w, dp, h = 26, 15, 11
    bezel(d, 0, 0, 0, w, dp, h, fam)
    for i in range(8):
        a = 1.6 + i * 2.85
        d.rect_on("left", 0, dp, h, a, 1.2, 2.3, h - 3.4, ("#cfd5dd", "#aeb6c2"), rx=0.25)
        d.rect_on("left", 0, dp, h, a + 0.35, 1.5, 1.6, 1.0, fam.accent, rx=0.15)
        d.led("left", 0, dp, h, a + 1.15, h - 2.9, GREEN if i % 4 else AMBER)
    d.vents("left", 0, dp, h, 1.6, h - 1.9, w - 3.2, 1.0, "#1c212b")


def r_switch(d: Drawing, fam: Family, count: int = 8, tall: bool = False) -> None:
    w, dp, h = 26, 11, 3.4 if not tall else 6.2
    bezel(d, 0, 0, 0, w, dp, h, fam)
    rows = 2 if tall else 1
    for r in range(rows):
        ports(d, 0, dp, h, 1.6, 0.35 + r * 2.8, count, fam, gap=2.3)
    d.led("left", 0, dp, h, w - 1.6, 1.0, GREEN)
    d.rect_on("left", 0, dp, h, w - 4.2, 0.6, 1.6, 0.5, fam.accent, rx=0.1)


def r_router(d: Drawing, fam: Family) -> None:
    d.cylinder(9, 9, 0, 9, 8, fam, body=("#e8ecf1", "#9aa5b4"))
    ox, oy = project(9, 9, 5.2)
    rx, ry = 9 * COS * math.sqrt(2), 9 * SIN * math.sqrt(2)
    d.parts.append(
        f'<path d="M{fmt(ox - rx)},{fmt(oy)} A{fmt(rx)},{fmt(ry)} 0 0 0 {fmt(ox + rx)},{fmt(oy)}" '
        f'fill="none" stroke="{fam.accent}" stroke-width="1.1" stroke-opacity="0.9"/>'
    )
    d.glyph_on("top", 2.5, 2.5, 8, 0, 0, 13, GLYPHS["arrows"], fam.deep, width=1.0)


def r_firewall(d: Drawing, fam: Family) -> None:
    w, dp, h = 22, 9, 14
    d.box(0, 0, 0, w, dp, h, fam, left=("#f3d9d9", "#e6bcbc"), right=("#c9a4a4", "#b08a8a"))
    for row in range(4):
        b = 1 + row * 3.2
        offset = 1.6 if row % 2 else 0
        for i in range(5):
            a = 0.8 + offset + i * 4.2
            if a + 3.4 <= w - 0.6:
                d.rect_on(
                    "left",
                    0,
                    dp,
                    h,
                    a,
                    b,
                    3.4,
                    2.4,
                    (mix(fam.colour, "#ffffff", 0.08), fam.deep),
                    rx=0.3,
                )
    d.led("left", 0, dp, h, w - 1.5, h - 1.0, GREEN)


def r_appliance(d: Drawing, fam: Family, glyph: str, count: int = 4) -> None:
    """A 1U box with a glyph on top: the generic 'this device does X'."""
    w, dp, h = 24, 15, 4.2
    bezel(d, 0, 0, 0, w, dp, h, fam)
    if count:
        ports(d, 0, dp, h, 1.6, 0.6, count, fam, gap=2.3)
    else:
        d.vents("left", 0, dp, h, 1.8, 1.2, 8, 2.0, "#1c212b")
    d.led("left", 0, dp, h, w - 1.6, 1.2, GREEN)
    d.glyph_on("top", 5.5, 2.2, h, 0, 0, 10.5, GLYPHS[glyph], fam.deep, width=0.95)


def r_cabinet(d: Drawing, fam: Family, glyph: str) -> None:
    """A tall floor unit -- UPS, cooling, generator -- with a display on its front."""
    w, dp, h = 15, 13, 28
    d.box(0, 0, 0, w, dp, h, fam, left=METAL, right=METAL_SIDE)
    d.rect_on(
        "left",
        0,
        dp,
        h,
        1.2,
        1.2,
        w - 2.4,
        h - 2.4,
        ("#e9edf2", "#d5dbe3"),
        stroke="#b8c0cb",
        rx=0.8,
    )
    screen(d, "left", 0, dp, h, 2.4, 2.4, w - 4.8, 5.0, fam)
    d.glyph_on("left", 0, dp, h, 3.2, 8.6, 8.6, GLYPHS[glyph], fam.accent, width=0.95)
    d.led("left", 0, dp, h, w - 3.4, 3.6, GREEN)
    d.led("left", 0, dp, h, w - 3.4, 5.4, fam.accent)
    d.vents("left", 0, dp, h, 2.6, 18.5, w - 5.2, 7.0, "#aeb6c2")


def r_disk_shelf(d: Drawing, fam: Family, rows: int = 2, cols: int = 6) -> None:
    w, dp, h = 26, 15, 2.5 * rows + 1.6
    bezel(d, 0, 0, 0, w, dp, h, fam)
    for r in range(rows):
        for c in range(cols):
            sled(
                d,
                0,
                dp,
                h,
                1.6 + c * 3.75,
                0.8 + r * 2.5,
                3.3,
                2.0,
                fam,
                GREEN if (r + c) % 5 else AMBER,
            )


def r_drum_stack(
    d: Drawing, fam: Family, count: int = 3, glyph: str | None = None, wide: bool = False
) -> None:
    if wide:
        d.stack(12, 12, 0, 12, 8, count, fam)
        if glyph:
            d.glyph_on("top", 5.5, 5.5, 8, 0, 0, 13, GLYPHS[glyph], fam.deep, width=0.95)
        return
    d.stack(8, 8, 0, 8, 15, count, fam)
    if glyph:
        d.glyph_on("top", 2.5, 2.5, 15, 0, 0, 11, GLYPHS[glyph], fam.deep, width=0.95)


def r_nas(d: Drawing, fam: Family) -> None:
    w, dp, h = 13, 15, 13
    d.box(0, 0, 0, w, dp, h, fam, left=CHASSIS, right=CHASSIS_SIDE)
    for i in range(4):
        a = 1.3 + i * 2.7
        d.rect_on("left", 0, dp, h, a, 1.4, 2.2, 8.4, ("#cfd5dd", "#aeb6c2"), rx=0.3)
        d.rect_on("left", 0, dp, h, a + 0.35, 1.7, 1.5, 0.8, fam.accent, rx=0.15)
        d.led("left", 0, dp, h, a + 1.1, 9.2, GREEN if i % 3 else AMBER)
    d.led("left", 0, dp, h, w / 2, h - 1.3, fam.accent)
    d.vents("right", w, 0, h, 1.6, 1.4, dp - 3.2, h - 2.8, "#1c212b")


def r_tape_library(d: Drawing, fam: Family) -> None:
    w, dp, h = 17, 15, 26
    d.box(0, 0, 0, w, dp, h, fam, left=METAL, right=METAL_SIDE)
    d.rect_on(
        "left",
        0,
        dp,
        h,
        1.2,
        1.2,
        w - 2.4,
        h - 2.4,
        ("#e9edf2", "#d5dbe3"),
        stroke="#b8c0cb",
        rx=0.6,
    )
    screen(d, "left", 0, dp, h, 2.2, 2.2, w - 4.4, 3.6, fam)
    d.rect_on("left", 0, dp, h, 2.2, 6.8, w - 4.4, h - 9.4, ("#1c212b", "#0f131a"), rx=0.5)
    for r in range(4):
        for c in range(3):
            d.rect_on(
                "left",
                0,
                dp,
                h,
                3.2 + c * 3.9,
                7.8 + r * 4.0,
                3.1,
                3.2,
                (mix(fam.colour, "#ffffff", 0.35), fam.accent),
                rx=0.35,
            )
            d.rect_on(
                "left",
                0,
                dp,
                h,
                3.7 + c * 3.9,
                8.4 + r * 4.0,
                2.1,
                1.2,
                "#ffffff",
                rx=0.2,
                opacity=0.6,
            )


def r_laptop(d: Drawing, fam: Family, broken: bool = False) -> None:
    d.slab(
        0,
        0,
        0,
        18,
        13,
        fam,
        h=1.3,
        top=("#e6eaf0", "#d5dbe3"),
        left=("#d9dee6", "#c2c9d3"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(
        0,
        0,
        1.3,
        18,
        1.2,
        11.5,
        fam,
        top=("#c9d0da", "#b8c0cb"),
        left=("#e9edf2", "#d5dbe3"),
        right=("#c2c9d3", "#aeb6c2"),
    )
    if broken:
        d.rect_on("left", 0, 1.2, 12.8, 1.1, 1.0, 15.8, 9.4, "#12151a", rx=0.4)
        d.lines_on("left", 0, 1.2, 12.8, 3.0, 4.2, 11.0, 2, 1.8, "#e2e8f0", width=0.5)
        d.led("left", 0, 1.2, 12.8, 16.2, 11.4, RED)
    else:
        screen(d, "left", 0, 1.2, 12.8, 1.1, 1.0, 15.8, 9.4, fam)
    d.rect_on("top", 0, 0, 1.3, 2.4, 3.2, 13.2, 6.4, ("#cfd5dd", "#b8c0cb"), rx=0.4)
    d.lines_on("top", 0, 0, 1.3, 3.0, 3.9, 12.0, 4, 1.35, "#9aa5b4", width=0.5)
    d.rect_on("top", 0, 0, 1.3, 6.4, 10.2, 5.2, 2.0, ("#dfe4ea", "#c9d0da"), rx=0.3)


def r_desktop(d: Drawing, fam: Family) -> None:
    d.box(
        2,
        0,
        0,
        14,
        1.4,
        11,
        fam,
        top=("#c9d0da", "#b8c0cb"),
        left=("#e9edf2", "#d5dbe3"),
        right=("#c2c9d3", "#aeb6c2"),
        shadow=False,
    )
    screen(d, "left", 2, 1.4, 11, 0.9, 0.9, 12.2, 9.2, fam)
    d.box(
        7,
        4,
        0,
        4,
        8,
        1.2,
        fam,
        top=("#d9dee6", "#c9d0da"),
        left=("#c9d0da", "#b8c0cb"),
        right=("#b8c0cb", "#a0a9b6"),
    )
    d.box(18, 0, 0, 5, 12, 15, fam, left=CHASSIS, right=CHASSIS_SIDE)
    d.led("left", 18, 12, 15, 2.5, 2.0, GREEN)
    d.rect_on("left", 18, 12, 15, 1.2, 3.6, 2.6, 0.6, fam.accent, rx=0.15)
    d.vents("left", 18, 12, 15, 1.2, 9, 2.6, 4.5, "#1c212b")


def r_phone(d: Drawing, fam: Family, kind: str = "generic") -> None:
    if kind == "tablet":
        d.box(
            0,
            0,
            0,
            12,
            1.3,
            16,
            fam,
            top=("#c9d0da", "#b8c0cb"),
            left=("#e9edf2", "#d5dbe3"),
            right=("#c2c9d3", "#aeb6c2"),
        )
        screen(d, "left", 0, 1.3, 16, 1.0, 1.0, 10.0, 14.0, fam)
        return
    if kind == "rugged":
        d.box(0, 0, 0, 8, 2.4, 15, fam, top=CHASSIS, left=CHASSIS, right=CHASSIS_SIDE)
        screen(d, "left", 0, 2.4, 15, 1.0, 2.0, 6.0, 9.0, fam)
        d.rect_on("top", 0, 0, 15, 2.5, 0.6, 3.0, 1.0, "#06080b", rx=0.2)
        d.rect_on("left", 0, 2.4, 15, 0.6, 12.4, 6.8, 1.6, fam.accent, rx=0.3)
        return
    d.box(
        0,
        0,
        0,
        7,
        1.3,
        14,
        fam,
        top=("#c9d0da", "#b8c0cb"),
        left=("#e9edf2", "#d5dbe3"),
        right=("#c2c9d3", "#aeb6c2"),
    )
    screen(d, "left", 0, 1.3, 14, 0.6, 1.0, 5.8, 12.0, fam)
    if kind == "ios":
        d.rect_on("left", 0, 1.3, 14, 2.4, 1.3, 2.2, 0.7, "#05070a", rx=0.35)
    elif kind == "android":
        d.dot_on("left", 0, 1.3, 14, 3.5, 1.6, 0.32, "#05070a")


def r_ap(d: Drawing, fam: Family) -> None:
    d.cylinder(9, 9, 0, 8.5, 2.4, fam, top=("#ffffff", "#e6eaf0"), body=("#e9edf2", "#aeb6c2"))
    ox, oy = project(9, 9, 2.4)
    d.parts.append(
        f'<ellipse cx="{fmt(ox)}" cy="{fmt(oy)}" rx="{fmt(6.2 * COS * math.sqrt(2))}" ry="{fmt(6.2 * SIN * math.sqrt(2))}" '
        f'fill="none" stroke="{fam.accent}" stroke-width="0.7" stroke-opacity="0.6"/>'
    )
    d.glyph_on("top", 4, 4, 2.4, 0, 0, 10, GLYPHS["wifi"], fam.accent, width=1.0)
    d.led("top", 9, 13.5, 2.4, 0, 0, GREEN)


def r_camera(d: Drawing, fam: Family) -> None:
    d.box(0, 4, 0, 12, 6.5, 6.5, fam, left=("#eceff3", "#d5dbe3"), right=("#c2c9d3", "#aeb6c2"))
    d.cylinder(
        14.2,
        7.2,
        0.6,
        3.1,
        5.3,
        fam,
        top=("#1f2937", "#0b1220"),
        body=("#e6eaf0", "#9aa5b4"),
        shadow=False,
    )
    d.dot_on("top", 14.2, 7.2, 5.9, 0, 0, 1.4, "#3b82f6")
    d.dot_on("top", 14.2, 7.2, 5.9, -0.5, -0.5, 0.45, "#ffffff")
    d.led("left", 0, 10.5, 6.5, 1.6, 1.4, fam.accent)
    d.vents("left", 0, 10.5, 6.5, 3.6, 2.6, 7, 2.0, "#aeb6c2")


def r_puck(d: Drawing, fam: Family, glyph: str) -> None:
    d.cylinder(7, 7, 0, 7, 3.2, fam, body=("#e9edf2", "#aeb6c2"))
    d.glyph_on("top", 2.5, 2.5, 3.2, 0, 0, 9, GLYPHS[glyph], fam.accent, width=1.0)


def r_panel(d: Drawing, fam: Family, count: int = 12, rows: int = 2) -> None:
    w, dp, h = 26, 7, 2.6 * rows + 0.6
    bezel(d, 0, 0, 0, w, dp, h, fam)
    per = count // rows
    for r in range(rows):
        for i in range(per):
            a = 1.6 + i * ((w - 3.2) / per)
            d.rect_on("left", 0, dp, h, a, 0.6 + r * 2.6, 1.6, 1.5, ("#e6eaf0", "#c9d0da"), rx=0.2)
            d.rect_on(
                "left", 0, dp, h, a + 0.35, 0.9 + r * 2.6, 0.9, 0.6, fam.accent, rx=0.1, opacity=0.9
            )


def r_pdu(d: Drawing, fam: Family) -> None:
    w, dp, h = 4, 4.5, 32
    d.box(0, 0, 0, w, dp, h, fam, left=CHASSIS, right=CHASSIS_SIDE)
    for i in range(8):
        d.rect_on("left", 0, dp, h, 0.8, 1.6 + i * 3.6, 2.4, 2.3, ("#e6eaf0", "#c9d0da"), rx=0.3)
        d.dot_on("left", 0, dp, h, 1.5, 2.75 + i * 3.6, 0.3, "#1a1f29")
        d.dot_on("left", 0, dp, h, 2.5, 2.75 + i * 3.6, 0.3, "#1a1f29")
    d.led("left", 0, dp, h, w / 2, 0.8, fam.accent)


CABLE_COLOUR = {
    "copper": "#3b82f6",
    "fibre": "#f97316",
    "dac": "#111418",
    "power": "#111418",
    "aqua": "#2dd4bf",
}


def r_cable(d: Drawing, fam: Family, kind: str = "copper") -> None:
    """A patch cable lying on the floor between two plugs."""
    points = [project(2 + i * 1.5, 8 + 3.2 * math.sin(i * 0.9), 0.4) for i in range(17)]
    path = "M" + " L".join(f"{fmt(px)},{fmt(py)}" for px, py in points)
    d.under.append(
        f'<path d="{path}" fill="none" stroke="#1f2937" stroke-opacity="0.16" stroke-width="3" transform="translate(0.5 1.2)"/>'
    )
    d.parts.append(
        f'<path d="{path}" fill="none" stroke="{LINE}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    d.parts.append(
        f'<path d="{path}" fill="none" stroke="{CABLE_COLOUR.get(kind, fam.accent)}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
    )
    d.parts.append(
        f'<path d="{path}" fill="none" stroke="#ffffff" stroke-opacity="0.35" stroke-width="0.5" stroke-linecap="round" transform="translate(-0.3 -0.4)"/>'
    )
    for px, py in points:
        d.xs.append(px)
        d.ys.append(py)
    d.box(0, 6.5, 0, 3, 3, 2.2, fam, left=("#e6eaf0", "#c9d0da"), shadow=False)
    d.box(
        25,
        6.5 + 3.2 * math.sin(16 * 0.9),
        0,
        3,
        3,
        2.2,
        fam,
        left=("#e6eaf0", "#c9d0da"),
        shadow=False,
    )


def r_person(d: Drawing, fam: Family, many: bool = False, kind: str = "") -> None:
    d.cylinder(
        9,
        9,
        0,
        9,
        1.8,
        fam,
        top=(mix(fam.colour, "#ffffff", 0.85), mix(fam.colour, "#ffffff", 0.7)),
    )
    d.glyph_on(
        "top", 2.5, 2.5, 1.8, 0, 0, 13, GLYPHS["people" if many else "person"], fam.deep, width=1.0
    )


def r_cloud(d: Drawing, fam: Family) -> None:
    d.slab(0, 0, 0, 22, 16, fam, h=1.6)
    d.glyph_on("top", 2, 1, 1.6, 0, 0, 18, GLYPHS["cloud"], fam.accent, width=0.9)


def r_room(d: Drawing, fam: Family) -> None:
    """A closet or cage: a floor tile with two walls and a rack inside."""
    d.slab(0, 0, 0, 26, 22, fam, h=1.2, top=("#eef1f5", "#dfe4ea"))
    d.box(
        0,
        0,
        1.2,
        26,
        1.5,
        16,
        fam,
        top=("#c9d0da", "#b8c0cb"),
        left=("#f4f6f9", "#e6eaf0"),
        shadow=False,
    )
    d.box(
        0,
        0,
        1.2,
        1.5,
        22,
        16,
        fam,
        top=("#c9d0da", "#b8c0cb"),
        right=("#e6eaf0", "#d5dbe3"),
        shadow=False,
    )
    d.box(
        6,
        6,
        1.2,
        8,
        8,
        14,
        fam,
        left=("#2e3542", "#1c212b"),
        right=("#3d4556", "#252b36"),
        shadow=False,
    )
    for i in range(4):
        d.rect_on("left", 6, 14, 15.2, 1.0, 1.2 + i * 3.1, 6.0, 2.4, CHASSIS, rx=0.25)
        d.led("left", 6, 14, 15.2, 6.3, 2.4 + i * 3.1, GREEN)


def r_segment(d: Drawing, fam: Family, glyph: str | None = None) -> None:
    """A network segment or zone: a floor tile with a badge."""
    d.slab(0, 0, 0, 24, 18, fam, h=1.4)
    d.rect_on("top", 0, 0, 1.4, 1.5, 1.5, 21, 15, "none", stroke=fam.accent, rx=1)
    if glyph:
        d.glyph_on("top", 5, 2, 1.4, 0, 0, 14, GLYPHS[glyph], fam.accent, width=0.9)


def r_software(d: Drawing, fam: Family, glyph: str, kind: str = "") -> None:
    r_puck(d, fam, glyph)


def r_construct(d: Drawing, fam: Family, glyph: str | None = None, kind: str = "") -> None:
    r_segment(d, fam, glyph)


def r_sensor(d: Drawing, fam: Family, glyph: str) -> None:
    d.box(0, 0, 0, 8, 8, 5, fam, left=("#eceff3", "#d5dbe3"), right=("#c2c9d3", "#aeb6c2"))
    d.glyph_on("top", 1, 1, 5, 0, 0, 6, GLYPHS[glyph], fam.accent, width=0.85)
    d.led("left", 0, 8, 5, 6.6, 3.8, GREEN)


def r_din(d: Drawing, fam: Family, glyph: str) -> None:
    """A DIN-rail module: a small deep box with terminal rows."""
    w, dp, h = 8, 10, 9
    d.box(0, 0, 0, w, dp, h, fam, left=("#eceff3", "#d5dbe3"), right=("#c2c9d3", "#aeb6c2"))
    for i in range(3):
        d.rect_on("left", 0, dp, h, 0.9 + i * 2.4, 6.5, 1.6, 1.6, "#1f2937", rx=0.2)
        d.dot_on("left", 0, dp, h, 1.7 + i * 2.4, 7.3, 0.35, "#94a3b8")
    d.glyph_on("left", 0, dp, h, 1.5, 0.8, 5, GLYPHS[glyph], fam.accent, width=0.85)
    d.led("left", 0, dp, h, w - 1.2, 1.2, GREEN)


# -- the set ---------------------------------------------------------------------
@dataclass(frozen=True)
class Item:
    id: str
    name: str
    family: str
    recipe: str
    args: tuple = ()
    kwargs: tuple = ()
    aliases: tuple = ()


def item(id, name, family, recipe, *args, aliases=(), **kwargs) -> Item:
    return Item(id, name, family, recipe, args, tuple(sorted(kwargs.items())), tuple(aliases))


ITEMS: list[Item] = [
    # -- compute ------------------------------------------------------------
    item("rack-server", "Rack server", "compute", "server", 2, aliases=("server", "2u")),
    item("rack-server-1u", "Rack server (1U)", "compute", "server", 1, 3, aliases=("pizza box",)),
    item("rack-server-4u", "Rack server (4U)", "compute", "server", 4, 5),
    item("tower-server", "Tower server", "compute", "tower"),
    item("blade-chassis", "Blade chassis", "compute", "blade_chassis"),
    item(
        "blade-server", "Blade server", "compute", "blade", aliases=("blade", "half-height blade")
    ),
    item("micro-server", "Micro server", "compute", "micro", aliases=("microserver",)),
    item(
        "storage-server",
        "Storage server (4U, 24 bays)",
        "compute",
        "server",
        4,
        6,
        rows=4,
        aliases=("jbod server",),
    ),
    item("mini-pc", "Mini PC", "compute", "sensor", "cube", aliases=("nuc", "small form factor")),
    item(
        "hypervisor-cluster",
        "Hypervisor cluster",
        "compute",
        "cluster",
        3,
        "server",
        aliases=("vm cluster", "vsphere cluster", "proxmox cluster", "esxi cluster"),
    ),
    item(
        "hpc-cluster",
        "HPC cluster",
        "compute",
        "cluster",
        4,
        "server",
        aliases=("compute cluster", "batch cluster"),
    ),
    item(
        "gpu-cluster",
        "GPU cluster",
        "compute",
        "cluster",
        2,
        "gpu",
        aliases=("ai cluster", "training cluster"),
    ),
    item(
        "hci-cluster",
        "Hyperconverged cluster",
        "compute",
        "cluster",
        3,
        "appliance",
        aliases=("hci cluster",),
    ),
    item(
        "hyperconverged-node",
        "Hyperconverged node",
        "compute",
        "appliance",
        "cube",
        6,
        aliases=("hci",),
    ),
    item("hypervisor-host", "Hypervisor host", "compute", "appliance", "cube", 4),
    item("virtual-machine", "Virtual machine", "compute", "puck", "cube", aliases=("vm",)),
    item("container-host", "Container host", "compute", "appliance", "helm", 4),
    item("kubernetes-node", "Kubernetes node", "compute", "appliance", "helm", 6),
    item("gpu-server", "GPU server", "compute", "server", 4, 3, aliases=("ai node",)),
    item("hpc-node", "HPC node", "compute", "server", 2, 6),
    item("mainframe", "Mainframe", "compute", "rack", 7),
    item("unix-server", "UNIX server", "compute", "tower"),
    item("windows-server", "Windows server", "compute", "server", 2, 4),
    item("edge-server", "Edge server", "compute", "appliance", "bolt", 2),
    item("single-board-computer", "Single-board computer", "compute", "sensor", "code"),
    item("vdi-host", "VDI host", "compute", "appliance", "kiosk", 4),
    item("web-server", "Web server", "compute", "appliance", "globe", 4),
    item("application-server", "Application server", "compute", "appliance", "code", 4),
    item("database-server", "Database server", "compute", "drum_stack", 3, "database"),
    item("mail-server", "Mail server", "compute", "appliance", "envelope", 4),
    item("print-server", "Print server", "compute", "appliance", "printer", 2),
    item("file-transfer-server", "SFTP / file transfer server", "compute", "appliance", "doc", 4),
    item("license-server", "License server", "compute", "appliance", "key", 2),
    item("update-server", "Patch / update server", "compute", "appliance", "check", 4),
    item("repository-mirror", "Package mirror", "compute", "appliance", "cube", 4),
    item("pxe-server", "PXE / boot server", "compute", "appliance", "power", 2),
    item("config-management", "Configuration management", "compute", "appliance", "wrench", 4),
    item("log-server", "Log server", "compute", "appliance", "list", 4),
    item("message-broker", "Message broker", "compute", "appliance", "envelope", 6),
    # -- storage ------------------------------------------------------------
    item("storage-array", "Storage array", "storage", "disk_shelf", 2, 6, aliases=("san array",)),
    item("all-flash-array", "All-flash array", "storage", "disk_shelf", 1, 8),
    item("disk-shelf", "Disk shelf / JBOD", "storage", "disk_shelf", 3, 6, aliases=("jbod",)),
    item("nas", "NAS filer", "storage", "nas", aliases=("network attached storage",)),
    item(
        "storage-cluster",
        "Storage cluster",
        "storage",
        "cluster",
        3,
        "shelf",
        aliases=("ceph", "gluster", "vsan", "scale-out storage", "software-defined storage"),
    ),
    item(
        "database-cluster",
        "Database cluster",
        "storage",
        "drum_row",
        3,
        2,
        aliases=("db cluster", "replica set", "galera", "always on"),
    ),
    item("das", "Direct-attached storage", "storage", "disk_shelf", 1, 4, aliases=("das",)),
    item("san-switch", "SAN fabric switch", "storage", "switch", 8, aliases=("fibre channel",)),
    item("storage-controller", "Storage controller", "storage", "appliance", "gear", 6),
    item("iscsi-target", "iSCSI target", "storage", "appliance", "database", 4),
    item("tape-library", "Tape library", "storage", "tape_library"),
    item("tape-drive", "Tape drive", "storage", "appliance", "tape", 0),
    item("object-storage-appliance", "Object-storage appliance", "storage", "disk_shelf", 2, 4),
    item("backup-appliance", "Backup appliance", "storage", "appliance", "arrows", 4),
    item("backup-server", "Backup server", "storage", "server", 2, 4),
    item("dedup-appliance", "Deduplication appliance", "storage", "appliance", "check", 4),
    item("file-server", "File server", "storage", "appliance", "folder", 4),
    item("database", "Database", "storage", "drum_stack", 3, "database"),
    item("data-warehouse", "Data warehouse", "storage", "drum_stack", 4, None),
    item("cache", "Cache", "storage", "drum_stack", 1, "bolt"),
    item("replication", "Replication", "storage", "drum_stack", 2, "arrows"),
    item("archive", "Archive", "storage", "drum_stack", 2, "clock"),
    item("optical-jukebox", "Optical jukebox", "storage", "tape_library"),
    # -- network ------------------------------------------------------------
    item("core-router", "Core router", "network", "router"),
    item("edge-router", "Edge router", "network", "router"),
    item("wan-router", "WAN / branch router", "network", "appliance", "arrows", 4),
    item("sd-wan-edge", "SD-WAN edge", "network", "appliance", "cloud", 4),
    item("core-switch", "Core switch", "network", "switch", 8, tall=True),
    item("distribution-switch", "Distribution switch", "network", "switch", 8, tall=True),
    item("access-switch", "Access switch", "network", "switch", 8),
    item("top-of-rack-switch", "Top-of-rack switch", "network", "switch", 8),
    item("poe-switch", "PoE switch", "network", "switch", 8),
    item("switch-stack", "Switch stack", "network", "server", 3, 0),
    item(
        "chassis-switch",
        "Chassis switch",
        "network",
        "chassis_switch",
        4,
        aliases=("modular switch", "core chassis"),
    ),
    item(
        "spine-leaf-fabric",
        "Spine-leaf fabric",
        "network",
        "fabric",
        aliases=("clos", "leaf-spine", "fabric", "evpn"),
    ),
    item(
        "ha-pair",
        "HA pair",
        "network",
        "cluster",
        2,
        "appliance",
        aliases=("active/passive", "active-passive", "high availability"),
    ),
    item(
        "load-balancer-pair",
        "Load balancer pair",
        "network",
        "cluster",
        2,
        "appliance",
        aliases=("adc pair",),
    ),
    item(
        "dns-cluster",
        "DNS cluster",
        "network",
        "cluster",
        3,
        "appliance",
        aliases=("resolver cluster", "anycast dns"),
    ),
    item("industrial-switch", "Industrial switch", "network", "din", "arrows"),
    item("load-balancer", "Load balancer", "network", "appliance", "arrows", 6, aliases=("adc",)),
    item("reverse-proxy", "Reverse proxy", "network", "appliance", "globe", 4),
    item("forward-proxy", "Forward proxy", "network", "appliance", "eye", 4),
    item("dns-server", "DNS server", "network", "appliance", "tag", 4),
    item("dhcp-server", "DHCP server", "network", "appliance", "list", 4),
    item("ntp-server", "NTP server", "network", "appliance", "clock", 2),
    item("ipam", "IPAM / DCIM", "network", "appliance", "search", 2),
    item("nms", "Network management", "network", "appliance", "chart", 4),
    item("packet-broker", "Packet broker", "network", "switch", 8),
    item("network-tap", "Network TAP", "network", "panel", 4, 1),
    item("patch-panel", "Patch panel", "network", "panel", 24, 2),
    item("fibre-patch-panel", "Fibre patch panel", "network", "panel", 12, 1),
    item("media-converter", "Media converter", "network", "sensor", "arrows"),
    item("network-cable", "Network cable", "network", "cable"),
    item(
        "copper-patch-cable",
        "Copper patch cable (Cat6)",
        "network",
        "cable",
        "copper",
        aliases=("rj45", "ethernet cable"),
    ),
    item(
        "fibre-patch-cable",
        "Fibre patch cable (LC)",
        "network",
        "cable",
        "fibre",
        aliases=("fiber", "lc", "om4"),
    ),
    item("dac-cable", "DAC / twinax cable", "network", "cable", "dac", aliases=("sfp+", "twinax")),
    item(
        "console-cable", "Console cable", "network", "cable", "aqua", aliases=("serial", "rollover")
    ),
    item("wireless-access-point", "Wireless access point", "network", "ap"),
    item("wlan-controller", "WLAN controller", "network", "appliance", "wifi", 4),
    item("wireless-bridge", "Point-to-point bridge", "network", "puck", "radio"),
    item("cellular-gateway", "4G / 5G gateway", "network", "puck", "radio"),
    item("modem", "Modem / ONT", "network", "sensor", "wave"),
    item("isp-uplink", "ISP uplink", "network", "cloud"),
    item("wan-link", "WAN / MPLS circuit", "network", "cloud"),
    item("satellite-terminal", "Satellite terminal", "network", "puck", "radio"),
    item("vpn-gateway", "VPN gateway", "network", "appliance", "lock", 4),
    item("vpn-concentrator", "VPN concentrator", "network", "appliance", "lock", 8),
    item("pbx", "PBX", "network", "appliance", "phone", 4),
    item("ip-phone", "IP desk phone", "network", "sensor", "phone"),
    item(
        "session-border-controller", "Session border controller", "network", "appliance", "phone", 6
    ),
    item("subnet", "Subnet", "network", "segment"),
    item("vlan", "VLAN", "network", "segment", "tag"),
    item("dmz", "DMZ", "network", "segment", "shield"),
    item("internet", "Internet", "network", "cloud"),
    # -- security -----------------------------------------------------------
    item(
        "firewall-cluster",
        "Firewall cluster",
        "security",
        "cluster",
        2,
        "firewall",
        aliases=("firewall ha", "active/active", "firewall pair"),
    ),
    item("perimeter-firewall", "Perimeter firewall", "security", "firewall"),
    item("internal-firewall", "Internal firewall", "security", "firewall"),
    item("ngfw", "Next-generation firewall", "security", "appliance", "wall", 6),
    item("utm", "UTM appliance", "security", "appliance", "shield", 4),
    item("ids-ips", "IDS / IPS", "security", "appliance", "eye", 4),
    item("waf", "Web application firewall", "security", "appliance", "wall", 4),
    item("ddos-mitigation", "DDoS mitigation", "security", "appliance", "shield", 8),
    item("zero-trust-gateway", "Zero-trust access", "security", "appliance", "id", 4),
    item("jump-host", "Bastion / jump host", "security", "appliance", "key", 2),
    item("pam", "Privileged access management", "security", "appliance", "vault", 4),
    item("hsm", "Hardware security module", "security", "appliance", "key", 0),
    item("pki", "PKI / certificate authority", "security", "appliance", "check", 2),
    item("siem", "SIEM", "security", "appliance", "bell", 6),
    item("soar", "SOAR", "security", "appliance", "gear", 4),
    item(
        "email-security-gateway", "Email security gateway", "security", "appliance", "envelope", 4
    ),
    item("secure-web-gateway", "Secure web gateway", "security", "appliance", "globe", 4),
    item("sandbox", "Malware sandbox", "security", "appliance", "bug", 2),
    item("vulnerability-scanner", "Vulnerability scanner", "security", "appliance", "search", 4),
    item("honeypot", "Honeypot", "security", "puck", "bug"),
    item("data-diode", "Data diode", "security", "sensor", "arrows"),
    item("nac", "Network access control", "security", "appliance", "id", 8),
    item("radius-server", "RADIUS / TACACS+ server", "security", "appliance", "key", 4),
    item("badge-reader", "Badge reader", "security", "sensor", "id"),
    item("security-camera", "Security camera", "security", "camera"),
    item("nvr", "Video recorder (NVR)", "security", "appliance", "camera", 4),
    item("alarm-panel", "Intrusion alarm panel", "security", "sensor", "bell"),
    item("domain-controller", "Domain controller", "security", "appliance", "id", 4),
    item("identity-provider", "Identity provider / SSO", "security", "appliance", "person", 4),
    item("mfa-server", "MFA server", "security", "appliance", "check", 2),
    item("kerberos-kdc", "Kerberos KDC", "security", "appliance", "ticket", 2),
    # -- facility -----------------------------------------------------------
    item("rack", "Rack / cabinet", "facility", "rack", 6),
    item("empty-rack", "Empty rack", "facility", "rack", 0),
    item("cage", "Colocation cage", "facility", "room"),
    item("mdf-idf", "MDF / IDF closet", "facility", "room"),
    item("datacenter", "Datacenter", "facility", "room"),
    item("ups", "UPS", "facility", "cabinet", "battery"),
    item("battery-bank", "Battery bank", "facility", "cabinet", "battery"),
    item("pdu", "PDU", "facility", "pdu"),
    item("generator", "Generator", "facility", "cabinet", "bolt"),
    item("utility-power", "Utility power", "facility", "cabinet", "power"),
    item("ats", "Automatic transfer switch", "facility", "cabinet", "arrows"),
    item("cooling", "CRAC / CRAH cooling", "facility", "cabinet", "fan"),
    item("chiller", "Chiller", "facility", "cabinet", "thermo"),
    item("in-row-cooling", "In-row cooling", "facility", "cabinet", "fan"),
    item("fire-suppression", "Fire suppression", "facility", "cabinet", "flame"),
    item("environmental-sensor", "Environmental sensor", "facility", "sensor", "thermo"),
    item("kvm-console", "KVM console", "facility", "laptop"),
    item("console-server", "Console / terminal server", "facility", "appliance", "code", 8),
    item("cable-tray", "Cable tray", "facility", "panel", 6, 1),
    item(
        "rack-row",
        "Rack row",
        "facility",
        "rack_row",
        3,
        aliases=("row of racks", "pod", "hot aisle"),
    ),
    item(
        "power-cable",
        "Power cable (IEC C13)",
        "facility",
        "cable",
        "power",
        aliases=("c13", "c14", "power cord"),
    ),
    item("kvm-switch", "KVM switch", "facility", "appliance", "kiosk", 4),
    item("cross-connect", "Cross-connect / meet-me room", "facility", "panel", 12, 2),
    # -- client -------------------------------------------------------------
    item("workstation", "Workstation", "client", "desktop"),
    item(
        "laptop-broken",
        "Broken laptop",
        "client",
        "laptop",
        broken=True,
        aliases=("failed laptop", "faulty device", "out of service", "broken"),
    ),
    item(
        "phone-ios",
        "iPhone-style phone",
        "client",
        "phone",
        "ios",
        aliases=("iphone", "ios", "apple phone"),
    ),
    item(
        "phone-android",
        "Android phone (Galaxy-style)",
        "client",
        "phone",
        "android",
        aliases=("android", "samsung", "galaxy", "pixel"),
    ),
    item("laptop", "Laptop", "client", "laptop"),
    item("thin-client", "Thin client", "client", "desktop"),
    item("mobile-device", "Phone / tablet", "client", "phone"),
    item("printer", "Printer / MFP", "client", "appliance", "printer", 0),
    item("scanner", "Document scanner", "client", "appliance", "doc", 0),
    item("kiosk", "Kiosk / signage", "client", "desktop"),
    item("user", "User", "client", "person"),
    item("users", "Users / staff", "client", "person", True),
    item("administrator", "Administrator", "client", "person"),
    item("video-conferencing", "Room video system", "client", "camera"),
    # -- platform (software that runs on the boxes) ---------------------------
    item("kubernetes-cluster", "Kubernetes cluster", "platform", "construct", "helm", "k8s"),
    item(
        "kubernetes-control-plane",
        "Kubernetes control plane",
        "platform",
        "cluster",
        3,
        "server",
        aliases=("control plane", "masters", "etcd quorum"),
    ),
    item(
        "kubernetes-worker-pool",
        "Kubernetes worker pool",
        "platform",
        "cluster",
        4,
        "server",
        aliases=("node pool", "workers", "worker nodes"),
    ),
    item("container", "Container", "platform", "software", "cube", "container"),
    item("virtual-network", "Virtual network", "platform", "construct", "arrows", "vnet"),
    item("service-mesh", "Service mesh", "platform", "construct", "branch", "mesh"),
    item("api-gateway", "API gateway", "platform", "appliance", "code", 4),
    item("ci-cd-pipeline", "CI/CD pipeline", "platform", "appliance", "branch", 2),
    item("artifact-registry", "Artifact registry", "platform", "drum_stack", 2, "cube"),
    item("secrets-vault", "Secrets vault", "platform", "appliance", "vault", 2),
    item("orchestrator", "Orchestrator", "platform", "appliance", "gear", 4),
    item("git-server", "Git server", "platform", "appliance", "branch", 4),
    # -- operations -----------------------------------------------------------
    item("monitoring-server", "Monitoring server", "operations", "appliance", "chart", 4),
    item("monitoring-probe", "Monitoring probe", "operations", "sensor", "gauge"),
    item("syslog-collector", "Syslog collector", "operations", "appliance", "list", 4),
    item("flow-collector", "NetFlow / sFlow collector", "operations", "appliance", "wave", 4),
    item("itsm", "ITSM / service desk", "operations", "appliance", "ticket", 2),
    item("cmdb", "CMDB / asset inventory", "operations", "drum_stack", 2, "list"),
    item("alerting", "Alerting / on-call", "operations", "software", "bell", "alerting"),
    item("dashboard", "Dashboard", "operations", "desktop"),
    item("wan-optimiser", "WAN optimiser", "operations", "appliance", "gauge", 4),
    item("content-cache", "Content cache", "operations", "appliance", "bolt", 4),
    # -- industrial / IoT -----------------------------------------------------
    item("plc", "PLC", "industrial", "din", "gear"),
    item("scada", "SCADA / RTU", "industrial", "appliance", "gauge", 2),
    item("hmi", "HMI panel", "industrial", "desktop"),
    item("historian", "Historian", "industrial", "drum_stack", 2, "clock"),
    item("industrial-firewall", "Industrial firewall", "industrial", "din", "wall"),
    item("iot-gateway", "IoT gateway", "industrial", "puck", "radio"),
    item("sensor", "Sensor", "industrial", "sensor", "thermo"),
    item("rfid-reader", "RFID / NFC reader", "industrial", "sensor", "nfc"),
    item("barcode-scanner", "Barcode scanner", "industrial", "sensor", "barcode"),
    item("bluetooth-beacon", "Bluetooth beacon", "industrial", "puck", "bluetooth"),
    item("lpwan-radio", "LPWAN radio", "industrial", "puck", "radio"),
    item("plug-load", "Smart plug / load", "industrial", "sensor", "plug"),
]

ITEMS += [
    # databases and data stores
    item(
        "relational-database",
        "Relational database",
        "storage",
        "drum_stack",
        3,
        "list",
        aliases=("sql", "rdbms", "postgres-style", "mysql-style"),
    ),
    item(
        "document-database",
        "Document database",
        "storage",
        "drum_stack",
        3,
        "doc",
        aliases=("nosql", "document store", "json store"),
    ),
    item(
        "key-value-store",
        "Key-value store",
        "storage",
        "drum_stack",
        2,
        "key",
        aliases=("kv store",),
    ),
    item(
        "time-series-database",
        "Time-series database",
        "storage",
        "drum_stack",
        3,
        "chart",
        aliases=("tsdb", "metrics database"),
    ),
    item(
        "graph-database",
        "Graph database",
        "storage",
        "drum_stack",
        3,
        "branch",
        aliases=("graph store",),
    ),
    item(
        "search-index",
        "Search index",
        "storage",
        "drum_stack",
        3,
        "search",
        aliases=("full-text search", "search engine"),
    ),
    item(
        "vector-database",
        "Vector database",
        "storage",
        "drum_stack",
        3,
        "wave",
        aliases=("embeddings store", "vector store"),
    ),
    item(
        "ledger-database",
        "Ledger database",
        "storage",
        "drum_stack",
        3,
        "check",
        aliases=("immutable ledger", "append-only"),
    ),
    item(
        "columnar-database",
        "Columnar database",
        "storage",
        "drum_stack",
        4,
        "list",
        aliases=("column store", "analytics database"),
    ),
    item("olap-cube", "OLAP cube", "storage", "drum_stack", 2, "cube", aliases=("analytics cube",)),
    item(
        "in-memory-database",
        "In-memory database",
        "storage",
        "drum_stack",
        2,
        "bolt",
        aliases=("memory grid", "imdb"),
    ),
    item(
        "distributed-sql",
        "Distributed SQL",
        "storage",
        "drum_row",
        3,
        1,
        aliases=("newsql", "multi-node sql"),
    ),
    item(
        "sharded-database",
        "Sharded database",
        "storage",
        "drum_row",
        4,
        1,
        aliases=("shards", "horizontal partitioning"),
    ),
    item(
        "primary-replica",
        "Primary and replica",
        "storage",
        "drum_row",
        2,
        2,
        aliases=("read replica", "standby", "hot standby"),
    ),
    item(
        "multi-master",
        "Multi-master database",
        "storage",
        "drum_row",
        3,
        3,
        aliases=("active-active database",),
    ),
    item(
        "data-lake",
        "Data lake",
        "storage",
        "drum_stack",
        1,
        "wave",
        wide=True,
        aliases=("lake", "raw zone"),
    ),
    item(
        "lakehouse",
        "Lakehouse",
        "storage",
        "drum_stack",
        2,
        "folder",
        wide=True,
        aliases=("delta lake", "iceberg tables"),
    ),
    item(
        "object-store",
        "Object store",
        "storage",
        "drum_stack",
        2,
        "cube",
        wide=True,
        aliases=("s3-compatible", "bucket store"),
    ),
    item(
        "backup-vault",
        "Backup vault",
        "storage",
        "cabinet",
        "vault",
        aliases=("air-gapped backup",),
    ),
    item(
        "immutable-storage",
        "Immutable storage",
        "storage",
        "cabinet",
        "lock",
        aliases=("worm storage", "object lock"),
    ),
    item(
        "database-proxy",
        "Database proxy",
        "storage",
        "appliance",
        "arrows",
        6,
        aliases=("connection pooler", "pgbouncer-style", "proxysql-style"),
    ),
    item(
        "embedded-database",
        "Embedded database",
        "storage",
        "sensor",
        "database",
        aliases=("sqlite-style", "local db"),
    ),
    item(
        "hdd-drive",
        "Hard disk drive",
        "storage",
        "drive",
        "hdd",
        aliases=("hdd", "3.5-inch drive", "spinning disk"),
    ),
    item(
        "ssd-drive",
        "Solid-state drive",
        "storage",
        "drive",
        "ssd",
        aliases=("ssd", "2.5-inch drive", "flash drive"),
    ),
    item("nvme-drive", "NVMe drive", "storage", "drive", "nvme", aliases=("m.2", "nvme ssd")),
    item(
        "jbof", "Flash shelf (JBOF)", "storage", "disk_shelf", 1, 8, aliases=("jbof", "nvme shelf")
    ),
    item(
        "storage-gateway",
        "Storage gateway",
        "storage",
        "appliance",
        "cloud",
        4,
        aliases=("cloud storage gateway", "file gateway"),
    ),
    item(
        "raid-controller",
        "RAID controller",
        "storage",
        "card",
        aliases=("raid card", "storage controller card"),
    ),
    item(
        "fibre-channel-hba", "Fibre Channel HBA", "storage", "card", aliases=("hba", "fc adapter")
    ),
    item(
        "san-director",
        "SAN director",
        "storage",
        "chassis_switch",
        6,
        aliases=("director-class switch",),
    ),
    item(
        "tape-cartridge", "Tape cartridge", "storage", "sensor", "tape", aliases=("lto cartridge",)
    ),
    # compute
    item(
        "bare-metal-host",
        "Bare-metal host",
        "compute",
        "server",
        2,
        8,
        aliases=("bare metal", "dedicated host", "physical server"),
    ),
    item(
        "midrange-system",
        "Midrange system",
        "compute",
        "cabinet",
        "cube",
        aliases=("power system", "as/400-style", "minicomputer"),
    ),
    item(
        "inference-server",
        "Inference server",
        "compute",
        "server",
        2,
        2,
        aliases=("ai inference", "model serving"),
    ),
    item("render-farm", "Render farm", "compute", "cluster", 4, "gpu", aliases=("render nodes",)),
    item(
        "terminal-server",
        "Terminal server",
        "compute",
        "appliance",
        "people",
        6,
        aliases=("rds host", "session host"),
    ),
    # network
    item(
        "sfp-transceiver",
        "SFP transceiver",
        "network",
        "sfp",
        aliases=("sfp", "sfp+", "optic", "gbic"),
    ),
    item(
        "qsfp-transceiver",
        "QSFP transceiver",
        "network",
        "sfp",
        True,
        aliases=("qsfp", "qsfp28", "40g optic", "100g optic"),
    ),
    item(
        "network-adapter",
        "Network adapter",
        "network",
        "card",
        aliases=("nic", "network card", "smartnic"),
    ),
    item(
        "optical-transport",
        "Optical transport (DWDM)",
        "network",
        "appliance",
        "wave",
        6,
        aliases=("dwdm", "wdm", "optical mux"),
    ),
    item(
        "pon-splitter",
        "Optical splitter",
        "network",
        "panel",
        4,
        1,
        aliases=("pon splitter", "fibre splitter"),
    ),
    item(
        "cellular-router",
        "Cellular router",
        "network",
        "appliance",
        "radio",
        4,
        aliases=("lte router", "5g router"),
    ),
    item(
        "poe-injector",
        "PoE injector",
        "network",
        "sensor",
        "bolt",
        aliases=("power injector", "midspan"),
    ),
    item("nat-gateway", "NAT gateway", "network", "appliance", "arrows", 4, aliases=("nat",)),
    item(
        "route-reflector", "Route reflector", "network", "router", aliases=("bgp route reflector",)
    ),
    item(
        "voip-gateway",
        "VoIP gateway",
        "network",
        "appliance",
        "phone",
        4,
        aliases=("sip gateway", "fxo gateway"),
    ),
    item(
        "telepresence-display",
        "Telepresence display",
        "network",
        "display",
        True,
        aliases=("meeting room display", "video bar"),
    ),
    item(
        "global-traffic-manager",
        "Global traffic manager",
        "network",
        "appliance",
        "globe",
        6,
        aliases=("gslb", "dns load balancer"),
    ),
    item(
        "dark-fibre",
        "Dark fibre",
        "network",
        "cable",
        "fibre",
        aliases=("dark fiber", "leased fibre"),
    ),
    item("mesh-node", "Mesh Wi-Fi node", "network", "puck", "wifi", aliases=("mesh access point",)),
    item(
        "network-sensor",
        "Network sensor",
        "security",
        "appliance",
        "eye",
        2,
        aliases=("ndr sensor", "traffic sensor"),
    ),
    item(
        "ip-kvm",
        "IP KVM",
        "facility",
        "appliance",
        "eye",
        2,
        aliases=("kvm over ip", "remote console"),
    ),
    # security
    item(
        "hardware-token",
        "Hardware security key",
        "security",
        "key",
        aliases=("security key", "fido key", "usb token"),
    ),
    item(
        "smart-card",
        "Smart card",
        "security",
        "smartcard",
        aliases=("piv card", "access card", "id badge"),
    ),
    item(
        "biometric-reader",
        "Biometric reader",
        "security",
        "sensor",
        "id",
        aliases=("fingerprint reader", "face reader"),
    ),
    item(
        "security-door",
        "Security door",
        "security",
        "door",
        aliases=("mantrap", "server room door", "secured entrance"),
    ),
    item(
        "soc-workstation",
        "SOC workstation",
        "security",
        "desktop",
        aliases=("analyst workstation", "security console"),
    ),
    item(
        "endpoint-agent",
        "Endpoint agent",
        "security",
        "puck",
        "bug",
        aliases=("edr agent", "antivirus agent"),
    ),
    item(
        "key-management-server",
        "Key management server",
        "security",
        "appliance",
        "key",
        4,
        aliases=("kms", "key manager"),
    ),
    item(
        "threat-intelligence",
        "Threat intelligence feed",
        "security",
        "puck",
        "eye",
        aliases=("threat feed", "ioc feed"),
    ),
    item(
        "air-gapped-host",
        "Air-gapped host",
        "security",
        "tower",
        aliases=("isolated workstation", "offline host"),
    ),
    item(
        "security-guard",
        "Security guard",
        "security",
        "person",
        aliases=("guard", "physical security"),
    ),
    item(
        "log-forwarder",
        "Log forwarder",
        "operations",
        "sensor",
        "list",
        aliases=("log shipper", "agent"),
    ),
    # facility
    item(
        "raised-floor-tile",
        "Raised-floor tile (perforated)",
        "facility",
        "tile",
        "perforated",
        aliases=("floor tile", "perforated tile", "airflow tile"),
    ),
    item(
        "solid-floor-tile",
        "Raised-floor tile (solid)",
        "facility",
        "tile",
        "solid",
        aliases=("solid tile",),
    ),
    item(
        "aisle-containment",
        "Aisle containment",
        "facility",
        "room",
        aliases=("hot aisle", "cold aisle", "containment"),
    ),
    item(
        "smoke-detector",
        "Smoke detector",
        "facility",
        "puck",
        "flame",
        aliases=("vesda", "fire detection"),
    ),
    item(
        "water-leak-sensor",
        "Water leak sensor",
        "facility",
        "sensor",
        "wave",
        aliases=("leak detection",),
    ),
    item(
        "airflow-sensor",
        "Airflow sensor",
        "facility",
        "sensor",
        "fan",
        aliases=("pressure sensor",),
    ),
    item(
        "fire-extinguisher",
        "Fire extinguisher",
        "facility",
        "extinguisher",
        aliases=("extinguisher", "co2 extinguisher"),
    ),
    item("fuel-tank", "Fuel tank", "facility", "tank", aliases=("diesel tank", "day tank")),
    item(
        "transformer",
        "Transformer",
        "facility",
        "transformer",
        aliases=("distribution transformer", "step-down"),
    ),
    item(
        "switchgear",
        "Switchgear",
        "facility",
        "cabinet",
        "power",
        aliases=("main switchboard", "lv switchgear"),
    ),
    item(
        "static-transfer-switch",
        "Static transfer switch",
        "facility",
        "appliance",
        "arrows",
        2,
        aliases=("sts",),
    ),
    item("busway", "Busway", "facility", "busway", aliases=("bus duct", "overhead power")),
    item(
        "blanking-panel",
        "Blanking panel",
        "facility",
        "panel",
        0,
        1,
        aliases=("filler panel", "blank"),
    ),
    item(
        "crash-cart",
        "Crash cart",
        "facility",
        "cart",
        "crash",
        aliases=("kvm cart", "service cart"),
    ),
    item(
        "air-handling-unit",
        "Air handling unit",
        "facility",
        "cabinet",
        "fan",
        aliases=("ahu", "cooling tower"),
    ),
    item("water-pump", "Water pump", "facility", "motor", aliases=("chilled water pump", "pump")),
    item(
        "power-meter",
        "Power meter",
        "facility",
        "din",
        "gauge",
        aliases=("energy meter", "branch circuit monitor"),
    ),
    item(
        "epo-button",
        "Emergency power off",
        "facility",
        "sensor",
        "power",
        aliases=("epo", "kill switch"),
    ),
    item("flywheel-ups", "Flywheel UPS", "facility", "cabinet", "gear", aliases=("rotary ups",)),
    # client
    item("tablet", "Tablet", "client", "phone", "tablet", aliases=("ipad-style", "android tablet")),
    item(
        "rugged-handheld",
        "Rugged handheld",
        "client",
        "phone",
        "rugged",
        aliases=("handheld scanner", "mobile computer", "warehouse scanner"),
    ),
    item("monitor", "Monitor", "client", "display", aliases=("external display", "screen")),
    item("projector", "Projector", "client", "projector", aliases=("beamer",)),
    item(
        "wall-display",
        "Wall display",
        "client",
        "display",
        True,
        aliases=("tv", "digital signage", "large display", "smart tv"),
    ),
    item(
        "docking-station", "Docking station", "client", "dock", aliases=("dock", "port replicator")
    ),
    item(
        "pos-terminal",
        "Point-of-sale terminal",
        "client",
        "pos",
        aliases=("pos", "checkout", "till"),
    ),
    item(
        "label-printer",
        "Label printer",
        "client",
        "sensor",
        "printer",
        aliases=("thermal printer",),
    ),
    item("badge-printer", "Badge printer", "client", "sensor", "id", aliases=("card printer",)),
    item("smartwatch", "Smartwatch", "client", "puck", "clock", aliases=("wearable",)),
    item("guest-user", "Guest", "client", "person", aliases=("visitor", "contractor")),
    item("developer", "Developer", "platform", "person", aliases=("engineer", "sre")),
    # platform
    item(
        "service-registry",
        "Service registry",
        "platform",
        "software",
        "list",
        "registry",
        aliases=("discovery", "consul-style"),
    ),
    item(
        "config-server",
        "Config server",
        "platform",
        "software",
        "gear",
        "config",
        aliases=("configuration service",),
    ),
    item(
        "feature-flags",
        "Feature flags",
        "platform",
        "software",
        "check",
        "flags",
        aliases=("toggles",),
    ),
    item(
        "event-bus",
        "Event bus",
        "platform",
        "construct",
        "wave",
        "bus",
        aliases=("pub/sub", "topic"),
    ),
    item(
        "scheduler",
        "Scheduler",
        "platform",
        "software",
        "clock",
        "scheduler",
        aliases=("cron", "job scheduler"),
    ),
    item(
        "function-runtime",
        "Function runtime",
        "platform",
        "software",
        "code",
        "function",
        aliases=("faas", "serverless"),
    ),
    item(
        "notebook-server",
        "Notebook server",
        "platform",
        "appliance",
        "code",
        4,
        aliases=("jupyter-style", "data science workbench"),
    ),
    item(
        "etl-pipeline",
        "ETL pipeline",
        "platform",
        "appliance",
        "branch",
        6,
        aliases=("data pipeline", "elt"),
    ),
    item(
        "stream-processor",
        "Stream processor",
        "platform",
        "appliance",
        "wave",
        6,
        aliases=("stream processing", "flink-style"),
    ),
    item(
        "search-cluster",
        "Search cluster",
        "platform",
        "cluster",
        3,
        "appliance",
        aliases=("elasticsearch-style", "opensearch-style"),
    ),
    item(
        "message-queue",
        "Message queue",
        "platform",
        "drum_stack",
        2,
        "envelope",
        aliases=("queue", "amqp"),
    ),
    item(
        "event-stream",
        "Event stream",
        "platform",
        "drum_row",
        3,
        1,
        aliases=("kafka-style", "log stream", "partitions"),
    ),
    item(
        "cache-cluster",
        "Cache cluster",
        "platform",
        "drum_row",
        4,
        1,
        aliases=("redis-style cluster", "memcached pool"),
    ),
    item(
        "data-catalog",
        "Data catalog",
        "platform",
        "drum_stack",
        2,
        "tag",
        aliases=("metadata catalog",),
    ),
    item(
        "feature-store",
        "Feature store",
        "platform",
        "drum_stack",
        2,
        "list",
        aliases=("ml features",),
    ),
    item(
        "model-registry",
        "Model registry",
        "platform",
        "drum_stack",
        2,
        "cube",
        aliases=("ml models",),
    ),
    item(
        "build-agent",
        "Build agent",
        "platform",
        "server",
        1,
        2,
        aliases=("ci runner", "build runner"),
    ),
    # operations
    item("status-page", "Status page", "operations", "display", True, aliases=("service status",)),
    item(
        "runbook-automation",
        "Runbook automation",
        "operations",
        "appliance",
        "wrench",
        4,
        aliases=("automation server", "orchestration runner"),
    ),
    item(
        "backup-console",
        "Backup console",
        "operations",
        "appliance",
        "tape",
        2,
        aliases=("backup server console",),
    ),
    item(
        "capacity-planner",
        "Capacity planner",
        "operations",
        "software",
        "chart",
        "capacity",
        aliases=("capacity management",),
    ),
    item(
        "snmp-poller",
        "SNMP poller",
        "operations",
        "appliance",
        "gauge",
        4,
        aliases=("network poller",),
    ),
    item(
        "synthetic-monitor",
        "Synthetic monitor",
        "operations",
        "software",
        "eye",
        "synthetic",
        aliases=("uptime check", "probe"),
    ),
    item(
        "noc-video-wall",
        "NOC video wall",
        "operations",
        "display",
        True,
        aliases=("video wall", "ops wall"),
    ),
    item(
        "change-calendar",
        "Change calendar",
        "operations",
        "software",
        "clock",
        "calendar",
        aliases=("maintenance window",),
    ),
    item(
        "knowledge-base",
        "Knowledge base",
        "operations",
        "appliance",
        "doc",
        4,
        aliases=("wiki", "documentation"),
    ),
    item(
        "collaboration-server",
        "Collaboration server",
        "operations",
        "appliance",
        "people",
        4,
        aliases=("chat server", "team messaging"),
    ),
    item(
        "log-store",
        "Log store",
        "operations",
        "drum_stack",
        3,
        "list",
        aliases=("log archive", "log index"),
    ),
    item(
        "metrics-store",
        "Metrics store",
        "operations",
        "drum_stack",
        2,
        "chart",
        aliases=("tsdb", "prometheus-style"),
    ),
    # industrial
    item(
        "control-valve",
        "Control valve",
        "industrial",
        "valve",
        aliases=("valve", "actuator", "water main valve"),
    ),
    item(
        "electric-motor", "Electric motor", "industrial", "motor", aliases=("motor", "drive motor")
    ),
    item(
        "variable-frequency-drive",
        "Variable-frequency drive",
        "industrial",
        "din",
        "gauge",
        aliases=("vfd", "motor drive"),
    ),
    item("robot-arm", "Robot arm", "industrial", "robot", aliases=("industrial robot", "six-axis")),
    item(
        "conveyor",
        "Conveyor",
        "industrial",
        "conveyor",
        aliases=("conveyor belt", "roller conveyor"),
    ),
    item("industrial-pc", "Industrial PC", "industrial", "micro", aliases=("ipc", "fanless pc")),
    item(
        "edge-ai-box",
        "Edge AI box",
        "industrial",
        "sensor",
        "code",
        aliases=("inference box", "edge compute"),
    ),
    item(
        "opc-ua-server",
        "OPC UA server",
        "industrial",
        "appliance",
        "gear",
        4,
        aliases=("opc server",),
    ),
    item(
        "safety-controller",
        "Safety controller",
        "industrial",
        "din",
        "shield",
        aliases=("safety plc", "sil controller"),
    ),
    item(
        "remote-io", "Remote I/O", "industrial", "din", "list", aliases=("io module", "fieldbus io")
    ),
    item(
        "energy-meter",
        "Energy meter",
        "industrial",
        "sensor",
        "gauge",
        aliases=("smart meter", "power monitor"),
    ),
    item("solar-array", "Solar array", "industrial", "solar", aliases=("pv array", "solar panels")),
    item(
        "solar-inverter",
        "Solar inverter",
        "industrial",
        "appliance",
        "bolt",
        0,
        aliases=("pv inverter",),
    ),
    item(
        "battery-storage",
        "Battery storage",
        "industrial",
        "cabinet",
        "battery",
        aliases=("bess", "energy storage"),
    ),
    item(
        "ev-charger", "EV charger", "industrial", "pedestal", aliases=("charging station", "evse")
    ),
    item(
        "building-management",
        "Building management system",
        "industrial",
        "cabinet",
        "gauge",
        aliases=("bms", "building automation"),
    ),
    item(
        "hvac-controller",
        "HVAC controller",
        "industrial",
        "din",
        "fan",
        aliases=("ahu controller",),
    ),
    item(
        "lighting-controller",
        "Lighting controller",
        "industrial",
        "din",
        "power",
        aliases=("dali", "lighting control"),
    ),
    item(
        "agv",
        "Automated guided vehicle",
        "industrial",
        "cart",
        "agv",
        aliases=("agv", "amr", "mobile robot"),
    ),
    item(
        "field-engineer",
        "Field engineer",
        "industrial",
        "person",
        aliases=("technician", "operator"),
    ),
]

ITEMS += [
    # generation
    item(
        "coal-power-plant",
        "Coal power plant",
        "energy",
        "plant",
        "coal",
        aliases=("thermal power plant", "coal plant"),
    ),
    item(
        "gas-power-plant",
        "Gas power plant",
        "energy",
        "plant",
        "gas",
        aliases=("ccgt", "combined cycle", "gas turbine plant"),
    ),
    item(
        "nuclear-power-plant",
        "Nuclear power plant",
        "energy",
        "plant",
        "nuclear",
        aliases=("npp", "nuclear station"),
    ),
    item(
        "nuclear-reactor",
        "Nuclear reactor",
        "energy",
        "reactor",
        "unit",
        aliases=("reactor unit", "containment"),
    ),
    item(
        "small-modular-reactor",
        "Small modular reactor",
        "energy",
        "reactor",
        "smr",
        aliases=("smr",),
    ),
    item(
        "hydroelectric-dam",
        "Hydroelectric dam",
        "energy",
        "dam",
        "hydro",
        aliases=("hydro plant", "dam", "reservoir"),
    ),
    item(
        "pumped-storage",
        "Pumped-storage station",
        "energy",
        "dam",
        "pumped",
        aliases=("pumped hydro",),
    ),
    item("wind-turbine", "Wind turbine", "energy", "wind", 1, aliases=("turbine",)),
    item("wind-farm", "Wind farm", "energy", "wind", 3, aliases=("wind park",)),
    item("solar-farm", "Solar farm", "energy", "solar_farm", aliases=("pv plant", "solar park")),
    item("geothermal-plant", "Geothermal plant", "energy", "plant", "geo", aliases=("geothermal",)),
    item(
        "biomass-plant",
        "Biomass plant",
        "energy",
        "plant",
        "biomass",
        aliases=("waste-to-energy", "biogas plant"),
    ),
    item(
        "fuel-cell",
        "Fuel cell",
        "energy",
        "fuelcell",
        aliases=("fuel cell stack", "hydrogen fuel cell"),
    ),
    item(
        "steam-turbine",
        "Steam turbine",
        "energy",
        "turbine",
        "steam",
        aliases=("turbine generator",),
    ),
    item("gas-turbine", "Gas turbine", "energy", "turbine", "gas", aliases=("combustion turbine",)),
    item("boiler", "Boiler", "energy", "boiler", aliases=("steam boiler",)),
    item(
        "hyperbolic-cooling-tower",
        "Cooling tower (hyperbolic)",
        "energy",
        "cooling_tower",
        aliases=("natural draft tower",),
    ),
    item(
        "diesel-genset",
        "Diesel generator set",
        "energy",
        "genset",
        "diesel",
        aliases=("genset", "diesel generator", "standby generator"),
    ),
    item(
        "chp-unit",
        "Cogeneration unit (CHP)",
        "energy",
        "genset",
        "chp",
        aliases=("chp", "gas engine", "cogeneration"),
    ),
    item(
        "bess-container",
        "Battery energy storage container",
        "energy",
        "bess",
        aliases=("bess", "battery container", "grid battery"),
    ),
    # transmission and distribution
    item(
        "transmission-tower",
        "Transmission tower",
        "energy",
        "pylon",
        aliases=("pylon", "lattice tower"),
    ),
    item(
        "transmission-line",
        "Transmission line",
        "energy",
        "line",
        "hv",
        aliases=("hv line", "overhead line"),
    ),
    item(
        "substation",
        "Substation",
        "energy",
        "substation",
        aliases=("switching station", "grid substation", "traction substation"),
    ),
    item("switchyard-bus", "Switchyard busbar", "energy", "busbar", aliases=("busbar", "hv bus")),
    item(
        "power-transformer",
        "Power transformer",
        "energy",
        "power_transformer",
        aliases=("hv transformer", "grid transformer"),
    ),
    item(
        "hv-circuit-breaker",
        "HV circuit breaker",
        "energy",
        "breaker_hv",
        aliases=("sf6 breaker", "circuit breaker"),
    ),
    item(
        "disconnect-switch",
        "Disconnect switch",
        "energy",
        "disconnect",
        aliases=("isolator", "disconnector"),
    ),
    item("surge-arrester", "Surge arrester", "energy", "arrester", aliases=("lightning arrester",)),
    item(
        "instrument-transformer",
        "Instrument transformer",
        "energy",
        "instrument_transformer",
        aliases=("ct", "vt", "current transformer", "voltage transformer"),
    ),
    item(
        "capacitor-bank",
        "Capacitor bank",
        "energy",
        "capacitor_bank",
        aliases=("power factor correction",),
    ),
    item("shunt-reactor", "Shunt reactor", "energy", "shunt_reactor", aliases=("reactor bank",)),
    item(
        "utility-pole",
        "Utility pole",
        "energy",
        "pole",
        aliases=("distribution pole", "pole transformer"),
    ),
    item(
        "pad-mounted-transformer",
        "Pad-mounted transformer",
        "energy",
        "padmount",
        aliases=("padmount", "distribution transformer"),
    ),
    item("ring-main-unit", "Ring main unit", "energy", "rmu", aliases=("rmu", "mv switch")),
    item(
        "hvdc-converter",
        "HVDC converter station",
        "energy",
        "hvdc",
        aliases=("hvdc", "converter station"),
    ),
    item(
        "grid-interconnection",
        "Grid interconnection point",
        "energy",
        "pcc",
        aliases=("point of common coupling", "pcc", "utility meter point"),
    ),
    item(
        "grid-control-centre",
        "Grid control centre",
        "energy",
        "control_room",
        aliases=("control room", "dispatch centre"),
    ),
    item(
        "smart-meter",
        "Smart meter",
        "energy",
        "sensor",
        "power",
        aliases=("utility meter", "ami meter"),
    ),
    item("cable-vault", "Cable vault", "energy", "vault", aliases=("manhole", "cable chamber")),
    item(
        "mv-overhead-line",
        "MV overhead line",
        "energy",
        "line",
        "mv",
        aliases=("distribution line", "pole line"),
    ),
    # the building's power chain
    item(
        "mv-feeder-cell",
        "MV incoming feeder",
        "facility",
        "switchgear",
        1,
        "mv",
        aliases=("incomer", "feeder cell"),
    ),
    item(
        "mv-switchgear",
        "MV switchgear",
        "facility",
        "switchgear",
        4,
        "mv",
        aliases=("medium-voltage switchgear",),
    ),
    item(
        "lv-switchboard",
        "LV main switchboard",
        "facility",
        "switchgear",
        5,
        "lv",
        aliases=("msb", "main distribution board"),
    ),
    item(
        "paralleling-switchgear",
        "Generator paralleling switchgear",
        "facility",
        "switchgear",
        3,
        "paralleling",
        aliases=("paralleling gear",),
    ),
    item(
        "changeover-panel",
        "Changeover panel",
        "facility",
        "wallbox",
        "changeover",
        aliases=("manual transfer switch",),
    ),
    item("rack-ups", "Rack-mount UPS", "facility", "rack_ups", aliases=("modular ups",)),
    item(
        "lithium-battery-cabinet",
        "Lithium battery cabinet",
        "facility",
        "batt_rack",
        "li",
        aliases=("li-ion cabinet",),
    ),
    item(
        "vrla-battery-string",
        "VRLA battery string",
        "facility",
        "batt_rack",
        "vrla",
        aliases=("battery rack", "lead-acid string"),
    ),
    item(
        "battery-monitoring",
        "Battery monitoring system",
        "facility",
        "sensor",
        "battery",
        aliases=("bms",),
    ),
    item(
        "dc-power-plant",
        "DC power plant (-48 V)",
        "facility",
        "dc_plant",
        aliases=("rectifier system", "telecom power"),
    ),
    item("rectifier-module", "Rectifier module", "facility", "rectifier", aliases=("rectifier",)),
    item(
        "floor-pdu",
        "Floor PDU",
        "facility",
        "floor_pdu",
        "pdu",
        aliases=("pdu cabinet", "power distribution cabinet"),
    ),
    item(
        "remote-power-panel", "Remote power panel", "facility", "floor_pdu", "rpp", aliases=("rpp",)
    ),
    item(
        "busway-tap-off",
        "Busway tap-off box",
        "facility",
        "tapoff",
        aliases=("tap-off", "plug-in unit"),
    ),
    item("horizontal-rack-pdu", "Rack PDU (horizontal)", "facility", "pdu_h", aliases=("1u pdu",)),
    item(
        "server-psu",
        "Server power supply",
        "facility",
        "psu",
        1,
        aliases=("psu", "power supply unit"),
    ),
    item(
        "redundant-psu-pair",
        "Redundant power supplies",
        "facility",
        "psu",
        2,
        aliases=("dual psu", "1+1 psu"),
    ),
    item("power-whip", "Power whip", "facility", "cable", "whip", aliases=("under-floor whip",)),
    item(
        "high-current-power-cord",
        "High-current power cord",
        "facility",
        "cable",
        "c19",
        aliases=("c19", "l6-30", "c20"),
    ),
    item(
        "earthing-bar",
        "Earthing bar",
        "facility",
        "ground_bar",
        aliases=("grounding bar", "ground bus"),
    ),
    item(
        "surge-protection-device",
        "Surge protection device",
        "facility",
        "din",
        "bolt",
        aliases=("spd",),
    ),
    item(
        "power-quality-analyser",
        "Power quality analyser",
        "facility",
        "appliance",
        "chart",
        2,
        aliases=("pq meter",),
    ),
    item("load-bank", "Load bank", "facility", "loadbank", aliases=("resistive load bank",)),
    item(
        "fuel-transfer-pump",
        "Fuel transfer pump skid",
        "facility",
        "pump_skid",
        "fuel",
        aliases=("fuel polishing",),
    ),
    item(
        "microgrid-controller",
        "Microgrid controller",
        "facility",
        "wallbox",
        "controller",
        aliases=("energy management system",),
    ),
    item(
        "panelboard",
        "Panelboard",
        "facility",
        "wallbox",
        "panelboard",
        aliases=("breaker panel", "distribution board"),
    ),
    item(
        "motor-control-centre",
        "Motor control centre",
        "facility",
        "switchgear",
        4,
        "mcc",
        aliases=("mcc",),
    ),
    item(
        "contactor",
        "Contactor / soft starter",
        "facility",
        "din",
        "arrows",
        aliases=("soft starter",),
    ),
    item(
        "miniature-circuit-breaker",
        "Miniature circuit breaker",
        "facility",
        "din",
        "power",
        aliases=("mcb", "breaker"),
    ),
    item("fuse-holder", "Fuse holder", "facility", "din", "flame", aliases=("fuse",)),
    item(
        "protection-relay",
        "Protection relay",
        "facility",
        "din",
        "shield",
        aliases=("relay", "iec 61850 relay"),
    ),
    item("junction-box", "Junction box", "facility", "wallbox", "jbox", aliases=("jbox",)),
    item(
        "control-panel",
        "Control panel",
        "facility",
        "control_panel",
        aliases=("operator panel", "enclosure"),
    ),
    item("cable-ladder", "Cable ladder", "facility", "ladder", aliases=("vertical cable ladder",)),
    item("conduit-run", "Conduit run", "facility", "conduit", aliases=("conduit",)),
    item(
        "mechanical-cooling-tower",
        "Cooling tower (mechanical)",
        "facility",
        "cooling_tower_mech",
        aliases=("open cooling tower",),
    ),
    item("dry-cooler", "Dry cooler", "facility", "drycooler", aliases=("air-cooled condenser",)),
    item(
        "rear-door-heat-exchanger",
        "Rear-door heat exchanger",
        "facility",
        "rdhx",
        aliases=("rdhx",),
    ),
    item(
        "coolant-distribution-unit",
        "Coolant distribution unit",
        "facility",
        "cdu",
        aliases=("cdu", "liquid cooling"),
    ),
    item(
        "immersion-cooling-tank",
        "Immersion cooling tank",
        "facility",
        "immersion",
        aliases=("immersion cooling",),
    ),
    item(
        "chilled-water-manifold",
        "Chilled-water manifold",
        "facility",
        "manifold",
        aliases=("pipe rack", "header"),
    ),
    item(
        "pump-skid",
        "Pump skid",
        "facility",
        "pump_skid",
        "water",
        aliases=("duty/standby pumps", "pumping station", "irrigation pump"),
    ),
    item(
        "free-cooling-economiser",
        "Free-cooling economiser",
        "facility",
        "economiser",
        aliases=("economizer", "free cooling"),
    ),
    item("humidifier", "Humidifier", "facility", "humidifier", aliases=("steam humidifier",)),
    item("duct-run", "Duct run", "facility", "duct", aliases=("ductwork", "plenum")),
    item(
        "suppression-cylinder-bank",
        "Suppression cylinder bank",
        "facility",
        "cylinders",
        aliases=("inert gas cylinders", "fm-200 bank"),
    ),
    item(
        "pre-action-valve",
        "Pre-action sprinkler valve",
        "facility",
        "valve",
        aliases=("sprinkler valve",),
    ),
    item("generator-yard", "Generator yard", "facility", "yard", "gen", aliases=("gen yard",)),
    item("fuel-farm", "Fuel farm", "facility", "yard", "fuel", aliases=("fuel storage",)),
    item(
        "roller-shutter-door",
        "Roller shutter door",
        "facility",
        "shutter",
        aliases=("loading dock", "plant room door"),
    ),
    # engineering instruments
    item(
        "thermal-camera", "Thermal camera", "industrial", "camera_ir", aliases=("infrared camera",)
    ),
    item(
        "vibration-sensor",
        "Vibration sensor",
        "industrial",
        "sensor",
        "wave",
        aliases=("accelerometer",),
    ),
    item(
        "pressure-transmitter",
        "Pressure transmitter",
        "industrial",
        "transmitter",
        "pressure",
        aliases=("pressure gauge",),
    ),
    item("flow-meter", "Flow meter", "industrial", "flowmeter", aliases=("flowmeter",)),
    item(
        "level-transmitter",
        "Level transmitter",
        "industrial",
        "transmitter",
        "level",
        aliases=("level sensor",),
    ),
    item("actuated-damper", "Actuated damper", "industrial", "damper", aliases=("damper",)),
    item("fan-wall", "Fan wall", "industrial", "fanwall", aliases=("fan array",)),
    item("air-compressor", "Air compressor", "industrial", "compressor", aliases=("compressor",)),
    item(
        "plate-heat-exchanger",
        "Plate heat exchanger",
        "industrial",
        "phe",
        aliases=("heat exchanger",),
    ),
    item(
        "pipe-fittings",
        "Pipe fittings",
        "industrial",
        "fittings",
        aliases=("steam trap", "pipework"),
    ),
    item(
        "operator-console",
        "Operator console",
        "industrial",
        "console_desk",
        aliases=("control desk",),
    ),
    item(
        "engineering-workstation",
        "Engineering workstation",
        "industrial",
        "eng_workstation",
        aliases=("cad workstation",),
    ),
]

ITEMS += [
    # telco and outside plant
    item(
        "cell-tower",
        "Cell tower",
        "network",
        "mast",
        "lattice",
        aliases=("cell site", "base station tower", "broadcast mast", "radio mast"),
    ),
    item("monopole-tower", "Monopole tower", "network", "mast", "monopole", aliases=("monopole",)),
    item("small-cell", "Small cell", "network", "mast", "small", aliases=("pole-mounted cell",)),
    item("satellite-dish", "Satellite dish", "network", "dish", aliases=("vsat", "dish antenna")),
    item(
        "earth-station",
        "Earth station",
        "network",
        "dish",
        True,
        aliases=("teleport", "ground station"),
    ),
    item(
        "olt", "Optical line terminal", "network", "chassis_switch", 4, aliases=("olt", "gpon olt")
    ),
    item("ont", "Optical network terminal", "network", "sensor", "wave", aliases=("ont", "onu")),
    item(
        "fibre-distribution-hub",
        "Fibre distribution hub",
        "network",
        "street_cabinet",
        "fdh",
        aliases=("fdh", "fibre hub"),
    ),
    item(
        "street-cabinet",
        "Street cabinet (DSLAM)",
        "network",
        "street_cabinet",
        "dslam",
        aliases=("dslam", "msan", "roadside cabinet"),
    ),
    item(
        "splice-closure",
        "Splice closure",
        "network",
        "closure",
        aliases=("dome closure", "aerial closure"),
    ),
    item("cable-reel", "Cable reel", "network", "reel", aliases=("cable drum",)),
    item(
        "central-office",
        "Central office",
        "network",
        "building",
        "central-office",
        aliases=("telephone exchange", "co"),
    ),
    item(
        "point-of-presence",
        "Point of presence",
        "network",
        "building",
        "pop",
        aliases=("pop", "cable landing station"),
    ),
    item("splice-tray", "Fibre splice tray", "network", "splice", "tray", aliases=("splice tray",)),
    item(
        "fibre-cassette",
        "Fibre cassette",
        "network",
        "splice",
        "cassette",
        aliases=("mpo cassette",),
    ),
    item(
        "wall-outlet",
        "Network wall outlet",
        "network",
        "outlet",
        "wall",
        aliases=("faceplate", "data outlet"),
    ),
    item("floor-box", "Floor box", "network", "outlet", "floor", aliases=("floor outlet",)),
    item(
        "open-frame-rack",
        "Open-frame rack",
        "network",
        "open_rack",
        "two-post",
        aliases=("two-post rack", "relay rack"),
    ),
    item(
        "wall-mount-rack",
        "Wall-mount rack",
        "network",
        "open_rack",
        "wall",
        aliases=("wall cabinet",),
    ),
    item(
        "cable-manager",
        "Cable manager (1U)",
        "network",
        "cable_manager",
        aliases=("horizontal cable manager",),
    ),
    item(
        "network-engineer",
        "Network engineer",
        "network",
        "person",
        False,
        "laptop",
        aliases=("engineer with laptop",),
    ),
    # buildings and sites
    item(
        "office-building", "Office building", "facility", "building", "office", aliases=("office",)
    ),
    item(
        "headquarters",
        "Headquarters",
        "facility",
        "building",
        "hq",
        aliases=("hq", "head office tower"),
    ),
    item(
        "warehouse",
        "Warehouse",
        "facility",
        "building",
        "warehouse",
        aliases=("distribution centre",),
    ),
    item(
        "factory", "Factory", "facility", "building", "factory", aliases=("plant", "manufacturing")
    ),
    item("hospital", "Hospital", "facility", "building", "hospital", aliases=("clinic",)),
    item(
        "retail-store",
        "Retail store",
        "facility",
        "building",
        "store",
        aliases=("shop", "branch store"),
    ),
    item(
        "home-office",
        "Home office",
        "facility",
        "building",
        "house",
        aliases=("house", "remote worker"),
    ),
    item(
        "gatehouse",
        "Gatehouse",
        "facility",
        "building",
        "gatehouse",
        aliases=("guard post", "security lodge"),
    ),
    item(
        "datacenter-building",
        "Datacenter building",
        "facility",
        "building",
        "dc",
        aliases=("data hall building",),
    ),
    item(
        "container-datacenter",
        "Container datacenter",
        "facility",
        "container_dc",
        aliases=("modular datacenter", "pod"),
    ),
    item(
        "perimeter-fence",
        "Perimeter fence",
        "facility",
        "fence_run",
        aliases=("fence", "security fence"),
    ),
    item(
        "boom-barrier",
        "Boom barrier",
        "facility",
        "barrier",
        aliases=("vehicle barrier", "level crossing"),
    ),
    item("bollards", "Bollards", "facility", "bollards", aliases=("vehicle bollards",)),
    item(
        "floodlight-mast", "Floodlight mast", "facility", "floodlight", aliases=("lighting mast",)
    ),
    item("water-tower", "Water tower", "facility", "water_tower", aliases=("water tank tower",)),
    item(
        "site-manager",
        "Site manager",
        "facility",
        "person",
        False,
        "hardhat",
        aliases=("engineer with hard hat", "contractor"),
    ),
    # physical security and safety
    item(
        "tripod-turnstile",
        "Turnstile",
        "security",
        "turnstile",
        "tripod",
        aliases=("tripod turnstile",),
    ),
    item(
        "speed-gate", "Speed gate", "security", "turnstile", "speed", aliases=("optical turnstile",)
    ),
    item("intercom", "Intercom", "security", "wallunit", "intercom", aliases=("door station",)),
    item("key-cabinet", "Key cabinet", "security", "wallunit", "keys", aliases=("key safe",)),
    item("safe", "Safe", "security", "safe", aliases=("vault safe", "media safe")),
    item(
        "auditor",
        "Auditor",
        "security",
        "person",
        False,
        "clipboard",
        aliases=("inspector", "assessor"),
    ),
    item(
        "first-aid-kit", "First-aid kit", "facility", "wallunit", "firstaid", aliases=("first aid",)
    ),
    item("aed", "Defibrillator (AED)", "facility", "wallunit", "aed", aliases=("aed",)),
    item(
        "fire-alarm-panel",
        "Fire alarm panel",
        "facility",
        "wallunit",
        "firepanel",
        aliases=("facp",),
    ),
    item("exit-sign", "Exit sign", "facility", "wallunit", "exit", aliases=("emergency exit",)),
    item(
        "emergency-light",
        "Emergency light",
        "facility",
        "wallunit",
        "light",
        aliases=("emergency lighting",),
    ),
    item("fire-hose-reel", "Fire hose reel", "facility", "hosereel", aliases=("hose reel",)),
    item(
        "spares-shelving",
        "Spares shelving",
        "facility",
        "shelving",
        "spares",
        aliases=("spares", "parts shelf"),
    ),
    item(
        "archive-shelving",
        "Archive shelving",
        "storage",
        "shelving",
        "archive",
        aliases=("records", "tape shelf"),
    ),
    # vehicles and mobile
    item(
        "fuel-truck",
        "Fuel truck",
        "facility",
        "vehicle",
        "tanker",
        aliases=("tanker", "fuel delivery"),
    ),
    item(
        "service-van", "Service van", "facility", "vehicle", "van", aliases=("field service van",)
    ),
    item(
        "box-truck",
        "Delivery truck",
        "facility",
        "vehicle",
        "box",
        aliases=("box truck", "logistics"),
    ),
    item(
        "mobile-generator",
        "Mobile generator trailer",
        "facility",
        "vehicle",
        "trailer",
        aliases=("towable generator",),
    ),
    item("fleet-car", "Fleet car", "facility", "vehicle", "car", aliases=("company car", "ev")),
    item("forklift", "Forklift", "industrial", "forklift", aliases=("lift truck",)),
    item("drone", "Drone", "industrial", "drone", aliases=("uav", "quadcopter")),
    item(
        "inspection-robot", "Inspection robot", "industrial", "crawler", aliases=("crawler robot",)
    ),
    # lab and test gear
    item("oscilloscope", "Oscilloscope", "operations", "bench", "scope", aliases=("scope",)),
    item(
        "spectrum-analyser",
        "Spectrum analyser",
        "operations",
        "bench",
        "spectrum",
        aliases=("spectrum analyzer",),
    ),
    item(
        "bench-power-supply",
        "Bench power supply",
        "operations",
        "bench",
        "psu",
        aliases=("lab psu",),
    ),
    item(
        "signal-generator",
        "Signal generator",
        "operations",
        "bench",
        "siggen",
        aliases=("function generator",),
    ),
    item(
        "network-tester",
        "Network tester",
        "network",
        "handheld",
        "tester",
        aliases=("cable tester", "link tester"),
    ),
    item(
        "cable-certifier",
        "Cable certifier",
        "network",
        "handheld",
        "certifier",
        aliases=("certification tester",),
    ),
    item(
        "otdr",
        "OTDR",
        "network",
        "handheld",
        "otdr",
        aliases=("optical time-domain reflectometer",),
    ),
    item("multimeter", "Multimeter", "facility", "handheld", "meter", aliases=("dmm",)),
    item("tool-case", "Tool case", "operations", "toolcase", aliases=("toolkit",)),
    item(
        "soldering-station",
        "Soldering station",
        "operations",
        "soldering",
        aliases=("soldering iron",),
    ),
    # office and collaboration
    item("meeting-room", "Meeting room", "client", "meeting", aliases=("conference room",)),
    item("video-bar", "Video bar", "client", "videobar", aliases=("meeting camera bar",)),
    item("conference-phone", "Conference phone", "client", "confphone", aliases=("speakerphone",)),
    item("headset", "Headset", "client", "headset", aliases=("call centre headset",)),
    item("shredder", "Shredder", "client", "shredder", aliases=("document shredder",)),
    item(
        "payment-terminal",
        "Payment terminal",
        "client",
        "pinpad",
        aliases=("pin pad", "card terminal"),
    ),
    item("atm", "ATM", "client", "pedestal", aliases=("cash machine",)),
    item(
        "help-desk",
        "Help desk",
        "operations",
        "console_desk",
        aliases=("service desk", "support desk"),
    ),
    item(
        "network-operations-centre",
        "Network operations centre",
        "operations",
        "control_room",
        aliases=("noc", "soc room"),
    ),
    # storage media
    item("usb-drive", "USB drive", "storage", "media", "usb", aliases=("usb stick", "thumb drive")),
    item("sd-card", "SD card", "storage", "media", "sd", aliases=("memory card", "microsd")),
    item(
        "optical-disc", "Optical disc", "storage", "media", "disc", aliases=("dvd", "blu-ray", "cd")
    ),
    item(
        "external-drive",
        "External drive",
        "storage",
        "media",
        "hdd",
        aliases=("portable drive", "usb hdd"),
    ),
    item("dba", "Database administrator", "storage", "person", False, "laptop", aliases=("dba",)),
    # virtual constructs
    item(
        "virtual-switch",
        "Virtual switch",
        "platform",
        "construct",
        "arrows",
        "vswitch",
        aliases=("vswitch", "ovs"),
    ),
    item(
        "virtual-router",
        "Virtual router",
        "platform",
        "software",
        "arrows",
        "vrouter",
        aliases=("vrouter",),
    ),
    item(
        "overlay-network",
        "Overlay network",
        "platform",
        "construct",
        "globe",
        "overlay",
        aliases=("vxlan", "overlay"),
    ),
    item("pod", "Pod", "platform", "software", "cube", "pod", aliases=("kubernetes pod",)),
    item(
        "ingress",
        "Ingress",
        "platform",
        "software",
        "globe",
        "ingress",
        aliases=("ingress controller",),
    ),
    item(
        "namespace",
        "Namespace",
        "platform",
        "construct",
        "folder",
        "namespace",
        aliases=("project", "tenant namespace"),
    ),
    item(
        "tenant", "Tenant", "platform", "construct", "people", "tenant", aliases=("multi-tenant",)
    ),
    item(
        "virtual-firewall",
        "Virtual firewall",
        "security",
        "puck",
        "shield",
        aliases=("vfw", "firewall vm"),
    ),
    # process plant
    item(
        "chemical-reactor",
        "Chemical reactor",
        "industrial",
        "vessel",
        "reactor",
        aliases=("reactor vessel", "stirred tank"),
    ),
    item(
        "distillation-column",
        "Distillation column",
        "industrial",
        "vessel",
        "column",
        aliases=("column", "tower"),
    ),
    item("pipeline", "Pipeline", "industrial", "pipeline", aliases=("pipe run",)),
    item("gantry-crane", "Gantry crane", "industrial", "crane", aliases=("overhead crane",)),
    item("weighbridge", "Weighbridge", "industrial", "weighbridge", aliases=("truck scale",)),
    item("silo", "Silo", "industrial", "silo", aliases=("storage silo", "grain elevator")),
    item(
        "water-treatment",
        "Water treatment",
        "industrial",
        "water_treatment",
        aliases=("treatment plant", "wastewater plant", "sewage treatment"),
    ),
]

ITEMS += [
    # the line in detail
    item(
        "tension-tower",
        "Tension tower",
        "energy",
        "hv_tower",
        "tension",
        aliases=("dead-end tower", "angle tower"),
    ),
    item("guyed-tower", "Guyed tower", "energy", "hv_tower", "guyed", aliases=("guyed-v tower",)),
    item(
        "lightning-mast",
        "Lightning mast",
        "energy",
        "hv_tower",
        "lightning",
        aliases=("shield mast",),
    ),
    item(
        "suspension-insulator",
        "Suspension insulator string",
        "energy",
        "insulator_string",
        "suspension",
        aliases=("insulator string", "i-string"),
    ),
    item(
        "tension-insulator",
        "Tension insulator string",
        "energy",
        "insulator_string",
        "tension",
        aliases=("strain insulator",),
    ),
    item(
        "bundled-conductor",
        "Bundled conductor",
        "energy",
        "conductor_bundle",
        aliases=("quad bundle", "spacer damper"),
    ),
    item("line-trap", "Line trap", "energy", "line_trap", aliases=("wave trap", "plc coupling")),
    item(
        "hv-cable-termination",
        "HV cable termination",
        "energy",
        "cable_end",
        aliases=("sealing end", "cable termination"),
    ),
    item(
        "cable-joint-bay",
        "Cable joint bay",
        "energy",
        "joint_bay",
        aliases=("joint bay", "cable joints"),
    ),
    item("cable-tunnel", "Cable tunnel", "energy", "cable_tunnel", aliases=("utility tunnel",)),
    item("riser-pole", "Riser pole", "energy", "riser_pole", aliases=("cable riser", "dip pole")),
    item(
        "recloser",
        "Recloser",
        "energy",
        "pole_equipment",
        "recloser",
        aliases=("auto-recloser", "sectionaliser"),
    ),
    item(
        "pole-capacitor-bank",
        "Pole capacitor bank",
        "energy",
        "pole_equipment",
        "capacitor",
        aliases=("pole-top capacitors",),
    ),
    item(
        "voltage-regulator",
        "Voltage regulator",
        "energy",
        "pole_equipment",
        "regulator",
        aliases=("step voltage regulator",),
    ),
    item(
        "fuse-cutout",
        "Fuse cutout",
        "energy",
        "pole_equipment",
        "cutout",
        aliases=("drop-out fuse",),
    ),
    item(
        "line-fault-indicator",
        "Line fault indicator",
        "energy",
        "line_sensor",
        aliases=("line sensor", "fault passage indicator"),
    ),
    item(
        "kiosk-substation",
        "Kiosk substation",
        "energy",
        "kiosk_substation",
        aliases=("package substation", "unit substation"),
    ),
    item(
        "mobile-substation",
        "Mobile substation",
        "energy",
        "mobile_substation",
        aliases=("trailer substation",),
    ),
    item(
        "line-gantry",
        "Line gantry",
        "energy",
        "gantry",
        aliases=("substation gantry", "terminal gantry"),
    ),
    item(
        "neutral-grounding-resistor",
        "Neutral grounding resistor",
        "energy",
        "ngr",
        aliases=("ngr", "earthing resistor"),
    ),
    item(
        "statcom",
        "STATCOM",
        "energy",
        "facts",
        "statcom",
        aliases=("static synchronous compensator",),
    ),
    item(
        "static-var-compensator",
        "Static VAR compensator",
        "energy",
        "facts",
        "svc",
        aliases=("svc",),
    ),
    item(
        "series-capacitor",
        "Series capacitor bank",
        "energy",
        "facts",
        "series",
        aliases=("series compensation",),
    ),
    item(
        "synchronous-condenser",
        "Synchronous condenser",
        "energy",
        "facts",
        "condenser",
        aliases=("rotating condenser",),
    ),
    item(
        "generator-step-up-transformer",
        "Generator step-up transformer",
        "energy",
        "power_transformer",
        1,
        "gsu",
        aliases=("gsu",),
    ),
    item(
        "phase-shifting-transformer",
        "Phase-shifting transformer",
        "energy",
        "power_transformer",
        1,
        "pst",
        aliases=("pst", "quadrature booster"),
    ),
    item(
        "generator-breaker", "Generator circuit breaker", "energy", "gen_breaker", aliases=("gcb",)
    ),
    item(
        "isolated-phase-bus",
        "Isolated-phase bus duct",
        "energy",
        "bus_duct",
        aliases=("ipb", "bus duct"),
    ),
    item(
        "protection-relay-panel",
        "Protection relay panel",
        "energy",
        "switchgear",
        2,
        "lv",
        aliases=("relay panel", "control panel row"),
    ),
    item(
        "dc-switchboard",
        "DC switchboard",
        "energy",
        "switchgear",
        2,
        "lv",
        aliases=("110 v dc board",),
    ),
    item(
        "substation-battery",
        "Substation battery bank",
        "energy",
        "batt_rack",
        "vrla",
        aliases=("110 v dc battery",),
    ),
    # inside the plant
    item(
        "condenser",
        "Condenser",
        "energy",
        "plant_equipment",
        "condenser",
        aliases=("surface condenser",),
    ),
    item(
        "feedwater-pump",
        "Feedwater pump",
        "energy",
        "plant_equipment",
        "feedpump",
        aliases=("boiler feed pump",),
    ),
    item(
        "deaerator",
        "Deaerator",
        "energy",
        "plant_equipment",
        "deaerator",
        aliases=("feedwater deaerator",),
    ),
    item(
        "cooling-water-intake",
        "Cooling water intake",
        "energy",
        "plant_equipment",
        "intake",
        aliases=("intake structure", "screen house"),
    ),
    item(
        "coal-handling",
        "Coal handling",
        "energy",
        "plant_equipment",
        "coal",
        aliases=("coal yard", "stacker reclaimer"),
    ),
    item(
        "flue-gas-desulphurisation",
        "Flue gas desulphurisation",
        "energy",
        "plant_equipment",
        "fgd",
        aliases=("fgd", "scrubber"),
    ),
    item(
        "hrsg",
        "Heat recovery steam generator",
        "energy",
        "plant_equipment",
        "hrsg",
        aliases=("hrsg",),
    ),
    item(
        "gas-compressor-station",
        "Gas compressor station",
        "energy",
        "plant_equipment",
        "compressor",
        aliases=("compressor station",),
    ),
    item(
        "gas-metering-station",
        "Gas metering station",
        "energy",
        "plant_equipment",
        "metering",
        aliases=("metering skid", "city gate"),
    ),
    item("lng-tank", "LNG tank", "energy", "plant_equipment", "lng", aliases=("lng storage",)),
    item(
        "hydrogen-electrolyser",
        "Hydrogen electrolyser",
        "energy",
        "plant_equipment",
        "electrolyser",
        aliases=("electrolyser", "pem stack"),
    ),
    item(
        "hydrogen-storage",
        "Hydrogen storage",
        "energy",
        "plant_equipment",
        "h2storage",
        aliases=("h2 tubes", "bullet tanks"),
    ),
    item(
        "district-heating",
        "District heating main",
        "energy",
        "plant_equipment",
        "heating",
        aliases=("heat network", "pre-insulated pipe"),
    ),
    item(
        "heat-pump",
        "Heat pump",
        "energy",
        "plant_equipment",
        "heatpump",
        aliases=("air-source heat pump",),
    ),
    item(
        "geothermal-well",
        "Geothermal well",
        "energy",
        "plant_equipment",
        "geowell",
        aliases=("wellhead",),
    ),
    item(
        "offshore-wind-turbine",
        "Offshore wind turbine",
        "energy",
        "plant_equipment",
        "offshore",
        aliases=("monopile turbine",),
    ),
    item(
        "floating-solar",
        "Floating solar",
        "energy",
        "plant_equipment",
        "floating",
        aliases=("floatovoltaics",),
    ),
    item(
        "power-conversion-system",
        "Power conversion system",
        "energy",
        "plant_equipment",
        "pcs",
        aliases=("battery inverter", "pcs"),
    ),
    item(
        "streetlight",
        "Streetlight",
        "facility",
        "streetlight",
        aliases=("street lamp", "smart streetlight"),
    ),
    item(
        "feeder-pillar",
        "Feeder pillar",
        "facility",
        "street_cabinet",
        "fdh",
        aliases=("lv pillar", "distribution pillar"),
    ),
    # power inside the building
    item(
        "rising-main",
        "Rising main",
        "facility",
        "riser",
        aliases=("riser bus duct", "vertical riser"),
    ),
    item(
        "meter-bank",
        "Meter bank",
        "facility",
        "meter_bank",
        aliases=("metering board", "tenant meters"),
    ),
    item(
        "power-factor-correction",
        "Power factor correction panel",
        "facility",
        "pfc_panel",
        aliases=("pfc panel", "capacitor panel"),
    ),
    item(
        "harmonic-filter",
        "Harmonic filter",
        "facility",
        "harmonic_filter",
        aliases=("passive filter",),
    ),
    item(
        "isolation-transformer",
        "Isolation transformer",
        "facility",
        "isolation_transformer",
        aliases=("k-rated transformer",),
    ),
    item(
        "earth-pit",
        "Earth pit",
        "facility",
        "earth_pit",
        aliases=("earthing electrode", "ground rod"),
    ),
    item(
        "lightning-protection",
        "Lightning protection",
        "facility",
        "air_terminal",
        aliases=("air terminal", "lps"),
    ),
    item(
        "ev-charging-plaza",
        "EV charging plaza",
        "facility",
        "charging_plaza",
        aliases=("charging hub", "fleet depot"),
    ),
    item(
        "maintenance-bypass",
        "Maintenance bypass panel",
        "facility",
        "wallbox",
        "changeover",
        aliases=("ups bypass",),
    ),
    # -- batch 7: nuclear and thermal internals ---------------------------------
    item(
        "steam-generator",
        "Steam generator",
        "energy",
        "nuclear_part",
        "steam_gen",
        aliases=("pwr steam generator",),
    ),
    item(
        "pressuriser",
        "Pressuriser",
        "energy",
        "nuclear_part",
        "pressuriser",
        aliases=("pressurizer",),
    ),
    item(
        "reactor-coolant-pump",
        "Reactor coolant pump",
        "energy",
        "nuclear_part",
        "rcp",
        aliases=("rcp",),
    ),
    item(
        "fuel-assembly",
        "Fuel assembly",
        "energy",
        "nuclear_part",
        "fuel_assembly",
        aliases=("fuel bundle",),
    ),
    item("spent-fuel-pool", "Spent fuel pool", "energy", "nuclear_part", "spent_pool"),
    item(
        "dry-cask-storage",
        "Dry cask storage",
        "energy",
        "nuclear_part",
        "dry_cask",
        aliases=("spent fuel cask",),
    ),
    item("turbine-hall", "Turbine hall", "energy", "nuclear_part", "turbine_hall"),
    item(
        "main-stack",
        "Main stack",
        "energy",
        "nuclear_part",
        "stack",
        aliases=("chimney", "flue stack"),
    ),
    item(
        "electrostatic-precipitator",
        "Electrostatic precipitator",
        "energy",
        "nuclear_part",
        "esp",
        aliases=("esp",),
    ),
    item("baghouse", "Baghouse", "energy", "nuclear_part", "baghouse", aliases=("fabric filter",)),
    item("ash-silo", "Ash silo", "energy", "nuclear_part", "ash_silo", aliases=("fly ash silo",)),
    item(
        "cooling-pond",
        "Cooling pond",
        "energy",
        "nuclear_part",
        "cooling_pond",
        aliases=("spray pond",),
    ),
    # -- batch 7: renewables and storage detail ---------------------------------
    item(
        "csp-tower",
        "Concentrated solar tower",
        "energy",
        "re_detail",
        "csp",
        aliases=("csp", "heliostat field"),
    ),
    item(
        "solar-tracker",
        "Solar tracker",
        "energy",
        "re_detail",
        "tracker",
        aliases=("single-axis tracker",),
    ),
    item(
        "combiner-box", "Combiner box", "energy", "re_detail", "combiner", aliases=("dc combiner",)
    ),
    item(
        "inverter-transformer-skid",
        "Inverter transformer skid",
        "energy",
        "re_detail",
        "tx_skid",
        aliases=("mv skid",),
    ),
    item(
        "weather-station",
        "Weather station",
        "energy",
        "re_detail",
        "weather",
        aliases=("pyranometer", "met station"),
    ),
    item(
        "met-mast", "Met mast", "energy", "re_detail", "met_mast", aliases=("meteorological mast",)
    ),
    item(
        "monopile-foundation",
        "Monopile foundation",
        "energy",
        "re_detail",
        "monopile",
        aliases=("monopile",),
    ),
    item(
        "jacket-foundation",
        "Jacket foundation",
        "energy",
        "re_detail",
        "jacket",
        aliases=("offshore jacket",),
    ),
    item(
        "floating-wind-platform",
        "Floating wind platform",
        "energy",
        "re_detail",
        "floating_wind",
        aliases=("floating wind",),
    ),
    item(
        "offshore-substation",
        "Offshore substation",
        "energy",
        "re_detail",
        "offshore_sub",
        aliases=("offshore platform",),
    ),
    item(
        "submarine-cable",
        "Submarine cable",
        "energy",
        "re_detail",
        "subsea_cable",
        aliases=("subsea cable", "export cable"),
    ),
    item(
        "cable-laying-ship",
        "Cable-laying ship",
        "energy",
        "re_detail",
        "cable_ship",
        aliases=("cable ship",),
    ),
    item(
        "tidal-turbine", "Tidal turbine", "energy", "re_detail", "tidal", aliases=("tidal stream",)
    ),
    item(
        "flow-battery",
        "Flow battery",
        "energy",
        "re_detail",
        "flow_battery",
        aliases=("vanadium redox",),
    ),
    item(
        "molten-salt-storage",
        "Molten salt storage",
        "energy",
        "re_detail",
        "molten_salt",
        aliases=("thermal energy storage",),
    ),
    item(
        "compressed-air-storage",
        "Compressed-air storage",
        "energy",
        "re_detail",
        "caes",
        aliases=("caes",),
    ),
    item(
        "grid-flywheel",
        "Grid flywheel",
        "energy",
        "re_detail",
        "flywheel",
        aliases=("flywheel storage",),
    ),
    # -- batch 7: grid hardware and the last mile -------------------------------
    item(
        "gis-hall", "GIS hall", "energy", "grid_gear", "gis", aliases=("gas-insulated switchgear",)
    ),
    item(
        "transformer-yard",
        "Transformer yard",
        "energy",
        "grid_gear",
        "tx_yard",
        aliases=("transformer bay",),
    ),
    item(
        "remote-terminal-unit",
        "Remote terminal unit",
        "energy",
        "grid_gear",
        "rtu",
        aliases=("rtu",),
    ),
    item(
        "phasor-measurement-unit",
        "Phasor measurement unit",
        "energy",
        "grid_gear",
        "pmu",
        aliases=("pmu", "synchrophasor"),
    ),
    item(
        "merging-unit",
        "Merging unit",
        "energy",
        "grid_gear",
        "merging_unit",
        aliases=("iec 61850 merging unit",),
    ),
    item(
        "sectionaliser",
        "Sectionaliser",
        "energy",
        "grid_gear",
        "sectionaliser",
        aliases=("sectionalizer",),
    ),
    item("load-break-switch", "Load-break switch", "energy", "grid_gear", "lbs", aliases=("lbs",)),
    item(
        "network-transformer-vault",
        "Network transformer vault",
        "energy",
        "grid_gear",
        "net_vault",
        aliases=("transformer vault",),
    ),
    item("network-protector", "Network protector", "energy", "grid_gear", "net_protector"),
    item(
        "service-drop",
        "Service drop",
        "energy",
        "grid_gear",
        "service_drop",
        aliases=("triplex drop",),
    ),
    item(
        "meter-socket",
        "Meter socket",
        "energy",
        "grid_gear",
        "meter_socket",
        aliases=("meter base",),
    ),
    item(
        "marker-balls",
        "Marker balls",
        "energy",
        "grid_gear",
        "marker_balls",
        aliases=("aerial marker balls",),
    ),
    # -- batch 7: home energy -----------------------------------------------------
    item(
        "breaker-panel",
        "Breaker panel",
        "energy",
        "home_energy",
        "panel",
        aliases=("consumer unit", "load centre"),
    ),
    item("sub-panel", "Sub-panel", "energy", "home_energy", "subpanel"),
    item(
        "home-transfer-switch",
        "Home transfer switch",
        "energy",
        "home_energy",
        "ats_home",
        aliases=("generator transfer switch",),
    ),
    item(
        "home-battery",
        "Home battery",
        "energy",
        "home_energy",
        "home_battery",
        aliases=("residential battery",),
    ),
    item(
        "home-ev-charger",
        "Home EV charger",
        "energy",
        "home_energy",
        "wallbox_home",
        aliases=("home wallbox",),
    ),
    item("smart-thermostat", "Smart thermostat", "energy", "home_energy", "thermostat"),
    # -- batch 7: building services --------------------------------------------
    item("rooftop-unit", "Rooftop unit", "facility", "hvac", "rtu", aliases=("packaged unit",)),
    item("vav-box", "VAV box", "facility", "hvac", "vav", aliases=("variable air volume",)),
    item(
        "split-condenser",
        "Split-unit condenser",
        "facility",
        "hvac",
        "condenser",
        aliases=("outdoor unit",),
    ),
    item(
        "fan-coil-unit", "Fan coil unit", "facility", "hvac", "fcu", aliases=("ceiling cassette",)
    ),
    item(
        "exhaust-fan", "Exhaust fan", "facility", "hvac", "exhaust", aliases=("roof cowl", "louvre")
    ),
    item(
        "energy-recovery-ventilator",
        "Energy recovery ventilator",
        "facility",
        "hvac",
        "erv",
        aliases=("erv", "heat recovery ventilator"),
    ),
    item("fire-pump", "Fire pump", "facility", "fire_gear", "pump"),
    item(
        "sprinkler-riser",
        "Sprinkler riser",
        "facility",
        "fire_gear",
        "riser",
        aliases=("alarm valve",),
    ),
    item("fire-hydrant", "Fire hydrant", "facility", "fire_gear", "hydrant"),
    item(
        "aspirating-smoke-detector",
        "Aspirating smoke detector",
        "facility",
        "fire_gear",
        "vesda",
        aliases=("vesda",),
    ),
    item("fire-door", "Fire door", "facility", "fire_gear", "fire_door"),
    item("elevator", "Elevator", "facility", "building_part", "elevator", aliases=("lift",)),
    item("loading-dock", "Loading dock", "facility", "building_part", "dock"),
    item(
        "mantrap",
        "Mantrap",
        "facility",
        "building_part",
        "mantrap",
        aliases=("interlock vestibule", "airlock"),
    ),
    item(
        "pa-speaker",
        "PA speaker",
        "facility",
        "building_part",
        "pa_speaker",
        aliases=("public address",),
    ),
    item("backflow-preventer", "Backflow preventer", "facility", "building_part", "backflow"),
    # -- batch 7: outside plant and radio ----------------------------------------
    item("manhole", "Manhole", "network", "osp", "manhole", aliases=("cable chamber",)),
    item("duct-bank", "Duct bank", "network", "osp", "duct_bank", aliases=("conduit bank",)),
    item("telecom-pedestal", "Telecom pedestal", "network", "osp", "pedestal"),
    item(
        "aerial-strand",
        "Aerial strand",
        "network",
        "osp",
        "strand",
        aliases=("lashed cable", "drop wire"),
    ),
    item(
        "demarcation-box", "Demarcation box", "network", "osp", "demarc", aliases=("nid", "demarc")
    ),
    item("dwdm-mux", "DWDM mux", "network", "radio", "dwdm", aliases=("dwdm", "roadm")),
    item("optical-amplifier", "Optical amplifier", "network", "radio", "edfa", aliases=("edfa",)),
    item(
        "microwave-backhaul",
        "Microwave backhaul",
        "network",
        "radio",
        "microwave",
        aliases=("microwave link",),
    ),
    item(
        "sector-antenna",
        "Sector antenna",
        "network",
        "radio",
        "sector",
        aliases=("rru", "remote radio unit"),
    ),
    item("baseband-unit", "Baseband unit", "network", "radio", "bbu", aliases=("bbu",)),
    item(
        "das-node", "DAS node", "network", "radio", "das", aliases=("distributed antenna system",)
    ),
    item("hfc-node", "HFC node", "network", "radio", "hfc", aliases=("fibre node", "cable node")),
    item("gps-antenna", "GPS antenna", "network", "radio", "gps", aliases=("gnss antenna",)),
    item(
        "ptp-grandmaster",
        "PTP grandmaster",
        "network",
        "radio",
        "ptp",
        aliases=("grandmaster clock",),
    ),
    # -- batch 7: process plant and machines -------------------------------------
    item("centrifugal-pump", "Centrifugal pump", "industrial", "process", "pump"),
    item("blower", "Blower", "industrial", "process", "blower", aliases=("centrifugal fan",)),
    item(
        "cyclone-separator",
        "Cyclone separator",
        "industrial",
        "process",
        "cyclone",
        aliases=("cyclone",),
    ),
    item("rotary-kiln", "Rotary kiln", "industrial", "process", "kiln", aliases=("kiln",)),
    item(
        "industrial-furnace",
        "Industrial furnace",
        "industrial",
        "process",
        "furnace",
        aliases=("furnace", "oven"),
    ),
    item(
        "hydraulic-press", "Hydraulic press", "industrial", "process", "press", aliases=("press",)
    ),
    item(
        "cnc-machine", "CNC machine", "industrial", "process", "cnc", aliases=("machining centre",)
    ),
    item(
        "printer-3d",
        "3D printer",
        "industrial",
        "process",
        "printer3d",
        aliases=("additive manufacturing",),
    ),
    item(
        "packaging-line",
        "Packaging line",
        "industrial",
        "process",
        "packaging",
        aliases=("case sealer",),
    ),
    item(
        "palletiser",
        "Palletiser",
        "industrial",
        "process",
        "palletiser",
        aliases=("palletizer", "palletising robot"),
    ),
    item(
        "pallet-rack",
        "Pallet rack",
        "industrial",
        "process",
        "pallet_rack",
        aliases=("pallet racking",),
    ),
    item(
        "rail-tank-car",
        "Rail tank car",
        "industrial",
        "process",
        "rail_tank",
        aliases=("tank wagon",),
    ),
    item(
        "pumpjack",
        "Pumpjack",
        "industrial",
        "process",
        "pumpjack",
        aliases=("oil well", "nodding donkey"),
    ),
    item("flare-stack", "Flare stack", "industrial", "process", "flare"),
    item(
        "lpg-sphere",
        "LPG sphere",
        "industrial",
        "process",
        "sphere",
        aliases=("horton sphere", "storage sphere"),
    ),
    item(
        "clarifier", "Clarifier", "industrial", "process", "clarifier", aliases=("settling tank",)
    ),
    item(
        "desalination-train",
        "Desalination train",
        "industrial",
        "process",
        "desal",
        aliases=("reverse osmosis",),
    ),
    item(
        "centre-pivot",
        "Centre-pivot irrigation",
        "industrial",
        "process",
        "pivot",
        aliases=("irrigation pivot",),
    ),
    # -- batch 7: people, vehicles, workplace -----------------------------------
    item(
        "lineworker",
        "Lineworker",
        "energy",
        "person",
        False,
        "lineworker",
        aliases=("line crew", "linesman"),
    ),
    item(
        "control-room-operator", "Control room operator", "industrial", "person", False, "operator"
    ),
    item("service-technician", "Service technician", "facility", "person", False, "technician"),
    item(
        "threat-actor",
        "Threat actor",
        "security",
        "person",
        False,
        "threat",
        aliases=("attacker", "hacker"),
    ),
    item(
        "executive",
        "Executive",
        "client",
        "person",
        False,
        "executive",
        aliases=("ciso", "manager"),
    ),
    item(
        "customer", "Customer", "client", "person", False, "customer", aliases=("public", "shopper")
    ),
    item("courier", "Courier", "client", "person", False, "courier", aliases=("delivery",)),
    item(
        "bucket-truck",
        "Bucket truck",
        "energy",
        "vehicle",
        "bucket",
        aliases=("line truck", "aerial lift"),
    ),
    item("fire-engine", "Fire engine", "facility", "vehicle", "fire", aliases=("fire truck",)),
    item("crane-truck", "Crane truck", "industrial", "vehicle", "crane", aliases=("mobile crane",)),
    item("electric-bus", "Electric bus", "energy", "vehicle", "bus", aliases=("e-bus",)),
    item("all-in-one-pc", "All-in-one PC", "client", "workplace", "all_in_one"),
    item(
        "vr-headset", "VR headset", "client", "workplace", "vr_headset", aliases=("mixed reality",)
    ),
    item("whiteboard", "Whiteboard", "client", "workplace", "whiteboard"),
]

#: The shapes a custom server comes in: (units, drive bays, bays per row, rows).
CUSTOM_SERVER_SHAPES = (
    (1, 0, 0, 0),
    (1, 4, 4, 1),
    (2, 0, 0, 0),
    (2, 8, 4, 2),
    (4, 0, 0, 0),
    (4, 12, 6, 2),
    (4, 24, 6, 4),
)
ITEMS += [
    item(
        f"custom-server-{family}-{units}u-{bays}",
        (f"Custom server {units}U, {bays} bays" if bays else f"Custom server {units}U, blank front")
        + f" \u00b7 {family}",
        family,
        "server",
        units,
        per_row,
        rows=rows,
        badge=False,
        aliases=(f"{units}u", "custom", "generic server"),
    )
    for family in FAMILIES
    for units, bays, per_row, rows in CUSTOM_SERVER_SHAPES
]

ITEMS += [
    # -- batch 8: transport, marine, rail, air ----------------------------
    item(
        "traffic-light",
        "Traffic light",
        "facility",
        "traffic_light",
        "road",
        aliases=("traffic signal", "stoplight"),
    ),
    item(
        "railway-signal",
        "Railway signal",
        "facility",
        "traffic_light",
        "rail",
        aliases=("rail signal", "colour light signal"),
    ),
    item(
        "container-ship",
        "Container ship",
        "facility",
        "ship",
        "container",
        aliases=("cargo ship", "freighter", "vessel"),
    ),
    item("ferry", "Ferry", "facility", "ship", "ferry", aliases=("passenger ferry", "ro-ro")),
    item(
        "oil-tanker",
        "Oil tanker",
        "energy",
        "ship",
        "tanker",
        aliases=("tanker ship", "lng carrier", "crude carrier"),
    ),
    item(
        "locomotive",
        "Locomotive",
        "facility",
        "train",
        "loco",
        aliases=("train", "freight train", "diesel locomotive"),
    ),
    item("tram", "Tram", "facility", "train", "tram", aliases=("light rail", "streetcar", "metro")),
    item(
        "railway-station",
        "Railway station",
        "facility",
        "building",
        "station",
        aliases=("train station", "metro station", "platform"),
    ),
    item(
        "airliner",
        "Airliner",
        "facility",
        "aircraft",
        "jet",
        aliases=("aircraft", "aeroplane", "airplane", "cargo plane"),
    ),
    item(
        "helicopter",
        "Helicopter",
        "facility",
        "aircraft",
        "helicopter",
        aliases=("air ambulance", "rotorcraft"),
    ),
    item(
        "control-tower",
        "Airport control tower",
        "facility",
        "building",
        "atc",
        aliases=("atc tower", "airport", "terminal"),
    ),
    item("helipad", "Helipad", "facility", "helipad", aliases=("heliport", "landing pad")),
    item(
        "road-bridge",
        "Road bridge",
        "facility",
        "bridge",
        "beam",
        aliases=("bridge", "beam bridge", "viaduct"),
    ),
    item(
        "suspension-bridge",
        "Suspension bridge",
        "facility",
        "bridge",
        "suspension",
        aliases=("cable bridge",),
    ),
    item(
        "container-crane",
        "Container crane",
        "industrial",
        "port_crane",
        aliases=("ship-to-shore crane", "port crane", "quay crane", "harbour"),
    ),
    item("lighthouse", "Lighthouse", "facility", "lighthouse", aliases=("beacon tower", "coast")),
    item(
        "satellite",
        "Satellite",
        "network",
        "satellite",
        aliases=("comms satellite", "leo satellite", "geo satellite", "spacecraft"),
    ),
    item(
        "radome",
        "Radome",
        "network",
        "radome",
        aliases=("radar dome", "weather radar", "tracking station"),
    ),
    item("bus-stop", "Bus stop", "facility", "bus_stop", aliases=("bus shelter", "transit stop")),
    item(
        "fuel-station",
        "Fuel station",
        "facility",
        "fuel_station",
        aliases=("petrol station", "gas station", "forecourt", "service station"),
    ),
    # -- batch 8: vehicles -------------------------------------------------
    item(
        "ambulance",
        "Ambulance",
        "facility",
        "vehicle",
        "ambulance",
        aliases=("paramedic", "emergency vehicle"),
    ),
    item(
        "police-car",
        "Police car",
        "security",
        "vehicle",
        "police",
        aliases=("patrol car", "squad car"),
    ),
    item(
        "tractor",
        "Tractor",
        "industrial",
        "vehicle",
        "tractor",
        aliases=("farm tractor", "agriculture"),
    ),
    item(
        "dump-truck",
        "Dump truck",
        "industrial",
        "vehicle",
        "dump",
        aliases=("tipper", "haul truck", "quarry truck"),
    ),
    item(
        "excavator",
        "Excavator",
        "industrial",
        "vehicle",
        "excavator",
        aliases=("digger", "backhoe", "earthmover"),
    ),
    item(
        "mixer-truck",
        "Concrete mixer truck",
        "industrial",
        "vehicle",
        "mixer",
        aliases=("cement mixer", "ready-mix"),
    ),
    item(
        "refuse-truck",
        "Refuse truck",
        "facility",
        "vehicle",
        "refuse",
        aliases=("garbage truck", "bin lorry", "waste collection"),
    ),
    item(
        "ob-van",
        "Outside-broadcast van",
        "network",
        "vehicle",
        "ob",
        aliases=("ob van", "satellite truck", "sng truck", "news van"),
    ),
    # -- batch 8: the town and the site ---------------------------------------
    item(
        "school",
        "School",
        "facility",
        "building",
        "school",
        aliases=("campus building", "university", "college"),
    ),
    item(
        "apartment-block",
        "Apartment block",
        "facility",
        "building",
        "apartment",
        aliases=("residential block", "flats", "condominium"),
    ),
    item(
        "bank-branch",
        "Bank branch",
        "facility",
        "building",
        "bank",
        aliases=("bank", "branch office"),
    ),
    item("hotel", "Hotel", "facility", "building", "hotel", aliases=("lodging", "resort")),
    item(
        "parking-garage",
        "Parking garage",
        "facility",
        "building",
        "garage",
        aliases=("car park", "multi-storey", "parking structure"),
    ),
    item(
        "shopping-mall",
        "Shopping mall",
        "facility",
        "building",
        "mall",
        aliases=("retail centre", "shopping centre"),
    ),
    item(
        "fire-station",
        "Fire station",
        "facility",
        "building",
        "firestation",
        aliases=("firehouse",),
    ),
    item("stadium", "Stadium", "facility", "stadium", aliases=("arena", "sports ground", "venue")),
    item(
        "greenhouse",
        "Greenhouse",
        "industrial",
        "building",
        "greenhouse",
        aliases=("glasshouse", "vertical farm", "farm"),
    ),
    item(
        "drilling-rig",
        "Drilling rig",
        "energy",
        "derrick",
        aliases=("derrick", "oil rig", "drill rig", "well pad"),
    ),
    item(
        "mine-headframe",
        "Mine headframe",
        "industrial",
        "headframe",
        aliases=("mine shaft", "headgear", "winding tower", "mine"),
    ),
    item(
        "locker-bank",
        "Locker bank",
        "facility",
        "shelving",
        "locker",
        aliases=("lockers", "parcel locker", "changing room"),
    ),
    item(
        "vending-machine",
        "Vending machine",
        "facility",
        "cabinet",
        "cart",
        aliases=("snack machine", "kiosk"),
    ),
    # -- batch 8: alarms, access and the home -----------------------------------
    item(
        "siren",
        "Siren",
        "security",
        "wallunit",
        "siren",
        aliases=("alarm sounder", "strobe", "beacon sounder"),
    ),
    item(
        "smart-lock",
        "Smart lock",
        "security",
        "wallunit",
        "lock",
        aliases=("door lock", "electronic lock", "access control reader", "keypad"),
    ),
    item(
        "video-doorbell",
        "Video doorbell",
        "security",
        "wallunit",
        "doorbell",
        aliases=("doorbell camera", "smart doorbell"),
    ),
    item(
        "panic-button",
        "Panic button",
        "security",
        "wallunit",
        "panic",
        aliases=("duress button", "emergency stop", "e-stop"),
    ),
    item(
        "smart-speaker",
        "Smart speaker",
        "client",
        "puck",
        "wave",
        aliases=("voice assistant", "smart home hub"),
    ),
    item(
        "robot-vacuum",
        "Robot vacuum",
        "client",
        "puck",
        "fan",
        aliases=("robot cleaner", "smart home robot"),
    ),
    item(
        "set-top-box",
        "Set-top box",
        "client",
        "appliance",
        "disc",
        2,
        aliases=("streaming box", "media player", "decoder"),
    ),
]

# A recipe takes the drawing and the family, then whatever its item passes.
RECIPES: dict[str, Callable[..., None]] = {
    "server": r_server,
    "blade": r_blade,
    "micro": r_micro,
    "tower": r_tower,
    "cluster": r_cluster,
    "fabric": r_fabric,
    "drum_row": r_drum_row,
    "rack_row": r_rack_row,
    "chassis_switch": r_chassis_switch,
    "drive": r_drive,
    "card": r_card,
    "sfp": r_sfp,
    "display": r_display,
    "projector": r_projector,
    "dock": r_dock,
    "pos": r_pos,
    "key": r_key,
    "smartcard": r_smartcard,
    "door": r_door,
    "tile": r_tile,
    "extinguisher": r_extinguisher,
    "tank": r_tank,
    "transformer": r_transformer,
    "busway": r_busway,
    "cart": r_cart,
    "motor": r_motor,
    "pedestal": r_pedestal,
    "valve": r_valve,
    "robot": r_robot,
    "conveyor": r_conveyor,
    "solar": r_solar,
    "plant": r_plant,
    "reactor": r_reactor,
    "dam": r_dam,
    "wind": r_wind,
    "solar_farm": r_solar_farm,
    "fuelcell": r_fuelcell,
    "turbine": r_turbine,
    "boiler": r_boiler,
    "cooling_tower": r_cooling_tower,
    "genset": r_genset,
    "bess": r_bess,
    "pylon": r_pylon,
    "line": r_line,
    "power_transformer": r_power_transformer,
    "breaker_hv": r_breaker_hv,
    "disconnect": r_disconnect,
    "arrester": r_arrester,
    "instrument_transformer": r_instrument_transformer,
    "capacitor_bank": r_capacitor_bank,
    "shunt_reactor": r_shunt_reactor,
    "pole": r_pole,
    "padmount": r_padmount,
    "rmu": r_rmu,
    "hvdc": r_hvdc,
    "substation": r_substation,
    "busbar": r_busbar,
    "pcc": r_pcc,
    "control_room": r_control_room,
    "vault": r_vault,
    "switchgear": r_switchgear,
    "wallbox": r_wallbox,
    "rack_ups": r_rack_ups,
    "batt_rack": r_batt_rack,
    "dc_plant": r_dc_plant,
    "rectifier": r_rectifier,
    "floor_pdu": r_floor_pdu,
    "tapoff": r_tapoff,
    "pdu_h": r_pdu_h,
    "psu": r_psu,
    "ground_bar": r_ground_bar,
    "loadbank": r_loadbank,
    "pump_skid": r_pump_skid,
    "control_panel": r_control_panel,
    "ladder": r_ladder,
    "conduit": r_conduit,
    "cooling_tower_mech": r_cooling_tower_mech,
    "drycooler": r_drycooler,
    "rdhx": r_rdhx,
    "cdu": r_cdu,
    "immersion": r_immersion,
    "manifold": r_manifold,
    "economiser": r_economiser,
    "humidifier": r_humidifier,
    "duct": r_duct,
    "cylinders": r_cylinders,
    "yard": r_yard,
    "shutter": r_shutter,
    "camera_ir": r_camera_ir,
    "transmitter": r_transmitter,
    "flowmeter": r_flowmeter,
    "damper": r_damper,
    "fanwall": r_fanwall,
    "compressor": r_compressor,
    "phe": r_phe,
    "fittings": r_fittings,
    "console_desk": r_console_desk,
    "eng_workstation": r_eng_workstation,
    "mast": r_mast,
    "dish": r_dish,
    "street_cabinet": r_street_cabinet,
    "closure": r_closure,
    "reel": r_reel,
    "building": r_building,
    "container_dc": r_container_dc,
    "fence_run": r_fence_run,
    "vehicle": r_vehicle,
    "forklift": r_forklift,
    "drone": r_drone,
    "crawler": r_crawler,
    "bench": r_bench,
    "handheld": r_handheld,
    "toolcase": r_toolcase,
    "soldering": r_soldering,
    "meeting": r_meeting,
    "videobar": r_videobar,
    "confphone": r_confphone,
    "headset": r_headset,
    "shredder": r_shredder,
    "pinpad": r_pinpad,
    "media": r_media,
    "safe": r_safe,
    "shelving": r_shelving,
    "turnstile": r_turnstile,
    "barrier": r_barrier,
    "bollards": r_bollards,
    "floodlight": r_floodlight,
    "water_tower": r_water_tower,
    "wallunit": r_wallunit,
    "hosereel": r_hosereel,
    "open_rack": r_open_rack,
    "cable_manager": r_cable_manager,
    "splice": r_splice,
    "outlet": r_outlet,
    "vessel": r_vessel,
    "pipeline": r_pipeline,
    "crane": r_crane,
    "weighbridge": r_weighbridge,
    "silo": r_silo,
    "water_treatment": r_water_treatment,
    "hv_tower": r_hv_tower,
    "insulator_string": r_insulator_string,
    "conductor_bundle": r_conductor_bundle,
    "line_trap": r_line_trap,
    "cable_end": r_cable_end,
    "joint_bay": r_joint_bay,
    "cable_tunnel": r_cable_tunnel,
    "riser_pole": r_riser_pole,
    "pole_equipment": r_pole_equipment,
    "line_sensor": r_line_sensor,
    "streetlight": r_streetlight,
    "kiosk_substation": r_kiosk_substation,
    "mobile_substation": r_mobile_substation,
    "gantry": r_gantry,
    "ngr": r_ngr,
    "facts": r_facts,
    "gen_breaker": r_gen_breaker,
    "bus_duct": r_bus_duct,
    "plant_equipment": r_plant_equipment,
    "riser": r_riser,
    "meter_bank": r_meter_bank,
    "pfc_panel": r_pfc_panel,
    "harmonic_filter": r_harmonic_filter,
    "isolation_transformer": r_isolation_transformer,
    "earth_pit": r_earth_pit,
    "air_terminal": r_air_terminal,
    "charging_plaza": r_charging_plaza,
    "nuclear_part": r_nuclear_part,
    "re_detail": r_re_detail,
    "grid_gear": r_grid_gear,
    "home_energy": r_home_energy,
    "hvac": r_hvac,
    "fire_gear": r_fire_gear,
    "building_part": r_building_part,
    "osp": r_osp,
    "radio": r_radio,
    "process": r_process,
    "workplace": r_workplace,
    "rack": r_rack,
    "blade_chassis": r_blade_chassis,
    "switch": r_switch,
    "router": r_router,
    "firewall": r_firewall,
    "appliance": r_appliance,
    "cabinet": r_cabinet,
    "disk_shelf": r_disk_shelf,
    "drum_stack": r_drum_stack,
    "nas": r_nas,
    "tape_library": r_tape_library,
    "laptop": r_laptop,
    "desktop": r_desktop,
    "phone": r_phone,
    "ap": r_ap,
    "camera": r_camera,
    "puck": r_puck,
    "panel": r_panel,
    "pdu": r_pdu,
    "cable": r_cable,
    "person": r_person,
    "cloud": r_cloud,
    "room": r_room,
    "segment": r_segment,
    "sensor": r_sensor,
    "software": r_software,
    "construct": r_construct,
    "din": r_din,
}


def draw(entry: Item) -> str:
    drawing = Drawing(f"iso-{entry.id}")
    recipe = RECIPES.get(entry.recipe)
    if recipe is None:
        # a recipe added with `infragram recipe:add` has its 3D builder only;
        # the flat kit draws a generic stand-in for it
        _generic(drawing, FAMILIES[entry.family], entry.recipe)
    else:
        recipe(drawing, FAMILIES[entry.family], *entry.args, **dict(entry.kwargs))
    return drawing.svg()


def write_set(out: Path) -> list[tuple[Item, Path]]:
    written = []
    for entry in ITEMS:
        folder = out / f"iso-{entry.family}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{entry.id}.svg"
        path.write_text(draw(entry) + "\n", encoding="utf-8", newline="\n")
        written.append((entry, path))
    return written


def sheet(written: list[tuple[Item, Path]], target: Path) -> None:
    """A contact sheet of the whole set, drawn by Chromium: the icons at the
    size a diagram draws them (64 px) and at 2x, with their names."""
    from playwright.sync_api import sync_playwright

    cells = "".join(
        f'<figure><div class="ico">{path.read_text(encoding="utf-8")}</div>'
        f"<figcaption>{entry.name}<span>{entry.family}</span></figcaption></figure>"
        for entry, path in written
    )
    html = f"""<meta charset="utf-8"><style>
    body{{margin:0;background:#f4f5f7;font-family:Segoe UI,sans-serif}}
    main{{display:grid;grid-template-columns:repeat(8,148px);gap:10px;padding:16px}}
    figure{{margin:0;background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:8px 4px 6px;text-align:center}}
    .ico{{width:96px;height:96px;margin:0 auto}}.ico svg{{width:100%;height:100%}}
    figcaption{{font-size:11px;color:#16191f;line-height:1.25;margin-top:4px}}
    figcaption span{{display:block;color:#7a8399;font-size:10px}}</style><main>{cells}</main>"""
    page = target.with_suffix(".html")
    page.write_text(html, encoding="utf-8", newline="\n")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        tab = browser.new_page(viewport={"width": 1300, "height": 900})
        tab.goto(page.resolve().as_uri())
        tab.wait_for_load_state("networkidle")
        tab.screenshot(path=str(target), full_page=True)
        browser.close()


#: Where each family sits in the sidebar's canonical categories.
SIDEBAR_CATEGORY = {
    "compute": "compute",
    "storage": "storage",
    "network": "networking",
    "security": "security",
    "facility": "facilities",
    "client": "compute",
    "platform": "containers",
    "operations": "analytics",
    "industrial": "industrial",
    "energy": "energy",
}
COLLECTION = ROOT / "skills/infragram-azure/assets/icons/vendors/onprem"
CATEGORY_MAP = ROOT / "skills/infragram-azure/assets/catalog/provider-category-map.json"


def flat(entry: Item) -> tuple[str, dict]:
    """The flat isometric drawing of one item, and how the catalog records it."""
    return draw(entry) + LF, {
        "source_path": "scripts/build/iso-icons.py",
        "source_release": "Infragram original isometric drawing, generated by scripts/build/iso-icons.py",
    }


def install(render=None) -> int:
    """Put the set into the on-prem collection and record it in its catalog.

    ``render(entry)`` returns the icon's SVG text and the catalog fields that
    say where it came from; the flat drawing by default, the three.js render
    when scripts/build/iso-render.py installs.
    """
    render = render or flat
    catalog_path = COLLECTION / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    kept = [entry for entry in catalog["icons"] if not entry["category"].startswith("iso-")]
    for folder in COLLECTION.glob("iso-*"):
        for old in folder.glob("*.svg"):
            old.unlink()
    added = []
    for entry in ITEMS:
        category = f"iso-{entry.family}"
        slug = f"iso-{entry.id}"
        path = COLLECTION / category / f"{slug}.svg"
        path.parent.mkdir(parents=True, exist_ok=True)
        svg, origin = render(entry)
        path.write_text(svg, encoding="utf-8", newline=LF)
        added.append(
            {
                "id": slug,
                "name": f"{entry.name} (3D)",
                "class_name": "".join(part.capitalize() for part in slug.split("-")),
                "aliases": [entry.name, *entry.aliases, "3d", "isometric"],
                "category": category,
                "file": f"{category}/{slug}.svg",
                "sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
                "source_url": "",
                "terms_url": "MIT; see LICENSE at the repository root",
                **origin,
            }
        )
    catalog["icons"] = kept + added
    catalog["counts"]["icons"] = len(catalog["icons"])
    catalog_path.write_text(json.dumps(catalog, indent=1) + "\n", encoding="utf-8", newline=LF)
    mapping = json.loads(CATEGORY_MAP.read_text(encoding="utf-8"))
    native = mapping["providers"]["onprem"]["native_categories"]
    for family, canonical in SIDEBAR_CATEGORY.items():
        native[f"iso-{family}"] = canonical
    mapping["providers"]["onprem"]["native_categories"] = dict(sorted(native.items()))
    CATEGORY_MAP.write_text(json.dumps(mapping, indent=1) + "\n", encoding="utf-8", newline=LF)
    print(
        f"OK: installed {len(added)} isometric icons into {COLLECTION.relative_to(ROOT)} "
        f"({len(catalog['icons'])} icons in the collection now)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, help="folder to draw the set into")
    parser.add_argument("--sheet", type=Path, help="also write a contact sheet PNG here")
    parser.add_argument(
        "--install",
        action="store_true",
        help="draw the flat kit into the on-prem library (iso-render.py installs the 3D renders)",
    )
    options = parser.parse_args(argv)
    if options.install:
        return install()
    if options.out is None:
        parser.error("--out or --install is required")
    written = write_set(options.out)
    families: dict[str, int] = {}
    for entry, _ in written:
        families[entry.family] = families.get(entry.family, 0) + 1
    print(
        f"OK: drew {len(written)} icons into {options.out} -- "
        + ", ".join(f"{k} {v}" for k, v in families.items())
    )
    if options.sheet:
        sheet(written, options.sheet)
        print(f"    sheet: {options.sheet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
