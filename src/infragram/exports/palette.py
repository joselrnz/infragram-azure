"""The dark canvas, for a picture drawn without a browser.

The editor paints its canvas from twelve tokens on ``body``
(``canvasPalette`` in runtime/08-theme-and-layout.js), one set per theme, and
a dark picture used to be obtainable only by driving that page in Chromium:
``export:project --theme dark`` opened the editor and captured what it drew,
so a machine without a browser could produce the light picture and nothing
else.

The static renderer draws from a :class:`Theme`'s roles instead. This reads
the dark tokens out of the stylesheet the page itself ships -- one source for
both, so a picture drawn here and a canvas drawn there cannot disagree about
what dark looks like -- and maps them onto those roles:

===========  ==========================  =======================================
Role         Token                       What it paints
===========  ==========================  =======================================
``paper``    ``--canvas-bg``             the ground behind the drawing
``paper_2``  ``--card-bg``               a card's face
``ink``      ``--text-canvas``           titles and captions
``muted``    ``--wire-color``            connectors
``soft``     ``--text-secondary``        a card's detail line, legend text
===========  ==========================  =======================================

``muted`` carries two jobs in the static renderer -- a wire's colour and a
card's detail line -- which one entry can serve on paper and cannot here,
where a wire sits back and small text must not. On a dark palette the
renderer paints that line from ``soft`` instead (``_detail_ink`` in
builders/render.py), which is the colour the canvas paints it.

``accent`` and ``link`` are the library's own colours -- a frame's tint, a
link kind that carries meaning -- and are left exactly as the theme has them,
the way the editor leaves them on a dark canvas.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ..editor.tokens import PALETTE_SELECTORS, canvas_tokens
from ..themes import Theme

#: The theme role each canvas token paints, in the static renderer.
ROLE_TOKENS = {
    "paper": "--canvas-bg",
    "paper_2": "--card-bg",
    "ink": "--text-canvas",
    "muted": "--wire-color",
    "soft": "--text-secondary",
}


def dark(theme: Theme, palette: str = "dark") -> Theme:
    """``theme`` as the editor draws it on a dark canvas.

    The dot field behind a drawing is dropped: it is ink at low alpha, which
    on a dark ground reads as dirt rather than as paper.
    """
    tokens = canvas_tokens(palette)
    # Any: the checker cannot tie each role name to its own field
    ground: dict[str, Any] = {role: tokens[token] for role, token in ROLE_TOKENS.items()}
    return replace(
        theme,
        dots=False,
        dark=True,
        **ground,
    )


__all__ = ["PALETTE_SELECTORS", "ROLE_TOKENS", "canvas_tokens", "dark"]
