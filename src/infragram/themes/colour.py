"""Hex colours taken apart, and the WCAG contrast between two of them.

One reading of ``#rgb`` and ``#rrggbb`` and one luminance for the package.
The frame titles (builders/ink.py) and the dark canvas (catalog/ink.py) each
carried a copy, and the copies differed in where the sRGB curve stops being
linear: 0.03928, the figure WCAG 2.0 printed, and 0.04045, the sRGB
standard's own, which WCAG 2.x now gives. No 8-bit channel falls between the
two -- 10/255 is 0.0392 and 11/255 is 0.0431 -- so every hex colour measures
the same under either, and this keeps the standard's.
"""

from __future__ import annotations

import re

__all__ = ["HEX_COLOUR", "contrast", "hex_rgb", "relative_luminance"]

#: ``#rgb`` or ``#rrggbb``: the forms a renderer is handed and can take apart.
HEX_COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
#: Where the sRGB curve stops being a straight line (IEC 61966-2-1, WCAG 2.x).
_LINEAR_LIMIT = 0.04045


def hex_rgb(colour: str) -> tuple[int, int, int] | None:
    """The red, green and blue, 0 to 255, of a hex colour, or None if it is not one.

    Surrounding space and the ``#`` may be left off, and ``#123`` is
    ``#112233``. Anything else -- a role name, ``rgba()``, ``none`` -- is
    None, so a caller can pass a colour through untouched instead of failing
    on it somewhere inside a render.
    """
    value = str(colour).strip().lstrip("#")
    if len(value) == 3:
        value = "".join(digit * 2 for digit in value)
    if len(value) != 6 or not set(value) <= _HEX_DIGITS:
        return None
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def relative_luminance(colour: str) -> float | None:
    """The sRGB relative luminance of a hex colour, as WCAG defines it, or None."""
    channels = hex_rgb(colour)
    if channels is None:
        return None

    def linear(channel: int) -> float:
        value = channel / 255
        return value / 12.92 if value <= _LINEAR_LIMIT else ((value + 0.055) / 1.055) ** 2.4

    red, green, blue = (linear(channel) for channel in channels)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: str, second: str) -> float | None:
    """The WCAG contrast ratio between two hex colours, 1:1 to 21:1, or None
    if either is not one."""
    one, two = relative_luminance(first), relative_luminance(second)
    if one is None or two is None:
        return None
    return (max(one, two) + 0.05) / (min(one, two) + 0.05)
