"""A finished picture placed on a canvas of a named size.

A picture is cropped to what it draws: its viewBox is the drawing plus a
margin, whatever the drawing's proportions. ``--size slide-16x9`` asks for
the picture a slide holds instead -- 1280 by 720, the drawing centred and
scaled to fit inside the preset's margin, the ground carried out to the
edges. Nothing is laid out again: the drawing is the one the editor (or the
static renderer) drew, seen through a wider window, so every size shows the
same picture. ``fit``, the default, leaves the crop as it is.

The sizes are the document's presets (:data:`~infragram.exports.presets.SIZE_PRESETS`),
so a size a document names and a size the command line names mean the same
canvas.
"""

from __future__ import annotations

import re

from .errors import ExportError
from .presets import SIZE_PRESETS

__all__ = ["SIZES", "frame_svg", "frame_size"]

#: The sizes a picture can be framed at, ``fit`` (as drawn) first.
SIZES: tuple[str, ...] = ("fit", *(name for name in SIZE_PRESETS if name != "fit"))

_OPEN_SVG = re.compile(r"<svg\b([^>]*)>", re.IGNORECASE)
_VIEWBOX = re.compile(r'\bviewBox\s*=\s*"([^"]+)"')
_GROUND = re.compile(r"<rect\b[^>]*\bdata-export-background=\"\"[^>]*/>")


def frame_size(size: str) -> tuple[int, int, int] | None:
    """The canvas ``size`` names, as (width, height, margin); None for ``fit``."""
    if size not in SIZE_PRESETS:
        raise ExportError(f"unknown size {size!r}; use {', '.join(SIZES)}")
    preset = SIZE_PRESETS[size]
    if preset.width is None or preset.height is None:
        return None
    return preset.width, preset.height, preset.margin


def _number(value: float) -> str:
    """A coordinate as short as it is exact to a hundredth."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def frame_svg(svg: str, size: str) -> str:
    """``svg`` on the canvas ``size`` names: its width and height the preset's,
    its viewBox widened around the drawing so the drawing sits centred inside
    the margin at the largest scale that fits, and the ground rectangle, when
    the picture has one, stretched to the new edges. ``fit`` returns ``svg``
    unchanged."""
    canvas = frame_size(size)
    if canvas is None:
        return svg
    width, height, margin = canvas
    opening = _OPEN_SVG.search(svg)
    box = _VIEWBOX.search(opening.group(1)) if opening else None
    numbers = box.group(1).replace(",", " ").split() if box else []
    if opening is None or len(numbers) != 4:
        raise ExportError("a picture framed to a size needs an <svg> with a viewBox")
    x, y, w, h = (float(number) for number in numbers)
    if w <= 0 or h <= 0:
        raise ExportError(f"the picture's viewBox is empty ({box.group(1) if box else ''})")
    # the drawing's scale on the canvas; the window it is seen through is the
    # canvas in drawing units, centred on the drawing
    scale = min((width - 2 * margin) / w, (height - 2 * margin) / h)
    window_w, window_h = width / scale, height / scale
    left, top = x - (window_w - w) / 2, y - (window_h - h) / 2
    viewbox = " ".join(_number(value) for value in (left, top, window_w, window_h))

    attributes = opening.group(1)
    attributes = _VIEWBOX.sub(f'viewBox="{viewbox}"', attributes, count=1)
    for name, value in (("width", width), ("height", height)):
        pattern = re.compile(rf'(\s){name}\s*=\s*"[^"]*"')
        if pattern.search(attributes):
            attributes = pattern.sub(rf'\g<1>{name}="{value}"', attributes, count=1)
        else:
            attributes += f' {name}="{value}"'
    svg = svg[: opening.start()] + f"<svg{attributes}>" + svg[opening.end() :]

    def stretched(match: re.Match[str]) -> str:
        rect = match.group(0)
        for name, value in (("x", left), ("y", top), ("width", window_w), ("height", window_h)):
            rect = re.sub(rf'(\s){name}="[^"]*"', rf'\g<1>{name}="{_number(value)}"', rect, count=1)
        return rect

    return _GROUND.sub(stretched, svg, count=1)
