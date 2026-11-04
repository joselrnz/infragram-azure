"""Button: filled, tonal, outlined or text, 32 px. Styles: button.css."""

from __future__ import annotations

from html import escape

from ..html import attributes
from ..icons import icon


def button(
    label: str, *, variant: str = "outlined", attrs: str = "", glyph: str = "", classes: str = ""
) -> str:
    """An M3 button -- filled, tonal, outlined or text -- 32px tall."""
    extra = f" {classes}" if classes else ""
    leading = icon(glyph) if glyph else ""
    return (
        f'<button type="button" class="md-button md-button--{variant}{extra}"{attributes(attrs)}>'
        f"{leading}{escape(label)}</button>"
    )


__all__ = ["button"]
