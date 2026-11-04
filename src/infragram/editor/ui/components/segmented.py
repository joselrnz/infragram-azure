"""Segmented button: one choice of a few, 32 px. Styles: segmented.css."""

from __future__ import annotations

from html import escape

from ..html import attributes


def segmented(
    label_id: str, options: tuple[tuple[str, str, str, bool], ...], *, attrs: str = ""
) -> str:
    """An M3 segmented button; each option is (label, attrs, title, selected)."""
    buttons = "".join(
        f'<button type="button" aria-pressed="{"true" if selected else "false"}" '
        f'title="{escape(title, quote=True)}" {option_attrs}>{escape(label)}</button>'
        for label, option_attrs, title, selected in options
    )
    return f'<div class="md-segmented" role="group" aria-labelledby="{label_id}"{attributes(attrs)}>{buttons}</div>'


__all__ = ["segmented"]
