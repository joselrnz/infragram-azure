"""Icon button: standard, 32 px or 40 px, optionally a toggle. Styles: icon_button.css."""

from __future__ import annotations

from html import escape

from ..html import attributes
from ..icons import icon


def icon_button(
    glyph: str,
    label: str,
    *,
    attrs: str = "",
    size: str = "",
    toggle: bool = False,
    classes: str = "",
) -> str:
    """An M3 standard icon button: 32px, or 40px with ``size="sm"``."""
    names = ["md-icon-button"]
    if size:
        names.append(f"md-icon-button--{size}")
    if toggle:
        names.append("md-icon-button--toggle")
    if classes:
        names.append(classes)
    return (
        f'<button type="button" class="{" ".join(names)}" aria-label="{escape(label, quote=True)}" '
        f'title="{escape(label, quote=True)}"{attributes(attrs)}>{icon(glyph)}</button>'
    )


__all__ = ["icon_button"]
