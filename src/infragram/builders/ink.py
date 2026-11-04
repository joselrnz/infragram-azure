"""A colour dark enough to read, without losing the colour.

Vendor decks paint a group's title in the group's own border colour, and at
the size a deck draws it that colour is legible. Our titles are 10 px, and at
10 px several deck colours are not: the generic frame's grey is 1.9:1 against
white and the Region teal and public-subnet green sit around 3:1, when 4.5:1
is the floor for text that size.

The border keeps the deck's colour exactly -- that fidelity is documented and
tested. The *text* is darkened until it clears the floor, which keeps the hue
that identifies the frame and makes the word readable. A colour that already
clears it is returned untouched, so nothing that was fine changes.

One implementation, used by both renderers: the static picture calls it
directly, and the editor state carries its result to the runtime, so a title
cannot come out one colour in the fallback picture and another in the export.
"""

from __future__ import annotations

import colorsys

from ..themes.colour import HEX_COLOUR, contrast, hex_rgb, relative_luminance

#: WCAG AA for text below 14 px. Frame titles are 10 px.
MINIMUM_CONTRAST = 4.5

#: How far the search may darken before giving up and returning near-black.
_STEPS = 60


def luminance(colour: str) -> float:
    """Relative luminance under the historical Azure import path."""
    value = relative_luminance(colour)
    if value is None:
        raise ValueError(f"luminance() takes a hex colour, #rgb or #rrggbb; got {colour!r}")
    return value


def _hex(red: float, green: float, blue: float) -> str:
    r, g, b = (round(max(0.0, min(1.0, c)) * 255) for c in (red, green, blue))
    return f"#{r:02x}{g:02x}{b:02x}"


def _strict_rgb(colour: object) -> tuple[int, int, int] | None:
    """The channels of ``#rgb`` or ``#rrggbb`` written in full, or None.

    Stricter than :func:`hex_rgb`, which also reads a colour without its
    ``#``: a renderer is handed a colour as CSS writes it, and anything else
    is a value it should pass through or refuse, not guess at."""
    if not isinstance(colour, str) or not HEX_COLOUR.match(colour.strip()):
        return None
    return hex_rgb(colour)


def readable(colour: str, on: str = "#ffffff", minimum: float = MINIMUM_CONTRAST) -> str:
    """``colour`` darkened just far enough to be read on ``on``.

    Hue and saturation are kept; only lightness moves, and only downwards,
    so the result still says which frame it belongs to. Returns the colour
    unchanged when it already clears ``minimum``, and gives up gracefully on
    anything that is not a plain hex colour.
    """
    channels = _strict_rgb(colour)
    if channels is None:
        return colour
    colour = colour.strip()
    ratio = contrast(colour, on)
    if ratio is None:
        raise ValueError(f"readable() measures against a hex colour, #rgb or #rrggbb; got {on!r}")
    if ratio >= minimum:
        return colour
    hue, lightness, saturation = colorsys.rgb_to_hls(*(channel / 255 for channel in channels))
    for step in range(1, _STEPS + 1):
        candidate = _hex(*colorsys.hls_to_rgb(hue, lightness * (1 - step / _STEPS), saturation))
        # both are hex colours by now, so the ratio is always measured
        if (contrast(candidate, on) or 0.0) >= minimum:
            return candidate
    return "#000000"


def rgba(hex_colour: str, alpha: float) -> str:
    """``#rrggbb`` (or shorthand ``#rgb``) at ``alpha``, as an ``rgba()`` string.

    Anything else -- a CSS colour name, an ``rgb()`` -- is refused by name:
    a named colour used to fail as ``int('re', 16)`` somewhere inside a
    render, with no hint of which value was wrong.
    """
    channels = _strict_rgb(hex_colour)
    if channels is None:
        raise ValueError(f"rgba() takes a hex colour, #rgb or #rrggbb; got {hex_colour!r}")
    r, g, b = channels
    return f"rgba({r},{g},{b},{alpha:g})"
