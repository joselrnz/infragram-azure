"""The editor's canvas tokens, read from the stylesheet the page ships.

The editor paints its canvas from a set of tokens on ``body``
(``canvasPalette`` in runtime/08-theme-and-layout.js), one set per workspace
theme. Anything drawn without a browser in the editor's own colours -- the
dark static picture, a wire caption's chip -- reads them here, from the same
file, so the two pictures cannot disagree about a colour.
"""

from __future__ import annotations

import re
from functools import lru_cache

__all__ = ["PALETTE_SELECTORS", "canvas_tokens"]

#: Which block of tokens.css carries each palette.
PALETTE_SELECTORS = {
    "dark": ":root",
    "light": 'body[data-workspace-theme="light"]',
    "darker": 'body[data-workspace-palette="darker"]',
}

#: The tokens every palette must define.
REQUIRED = ("--canvas-bg", "--card-bg", "--text-canvas", "--text-secondary", "--wire-color")


@lru_cache(maxsize=4)
def canvas_tokens(palette: str = "dark") -> dict[str, str]:
    """One palette's canvas tokens: the dark set, overlaid with the palette's own."""
    from . import bundle

    if palette not in PALETTE_SELECTORS:
        raise ValueError(f"unknown palette {palette!r}; one of {sorted(PALETTE_SELECTORS)}")
    text = (bundle.UI / "styles/tokens.css").read_text(encoding="utf-8")
    blocks: dict[str, dict[str, str]] = {}
    for selector, body in re.findall(r"([^{}]*)\{([^{}]*)\}", text):
        # a comment may sit before a selector, and one selector may carry
        # several blocks (:root holds the canvas tokens, the Material roles
        # and the shape scale in three)
        name = selector.split("*/")[-1].strip()
        blocks.setdefault(name, {}).update(re.findall(r"(--[a-z-]+):\s*([^;]+)", body))
    tokens = {**blocks[PALETTE_SELECTORS["dark"]], **blocks[PALETTE_SELECTORS[palette]]}
    missing = sorted(set(REQUIRED) - set(tokens))
    if missing:
        raise ValueError(f"{palette} palette is missing {missing}")
    return {name: value.strip() for name, value in tokens.items()}
