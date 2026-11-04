"""Empty state: an icon, a headline and one line saying what to do. Styles: empty_state.css."""

from __future__ import annotations

from html import escape

from ..icons import icon


def empty_state(glyph: str, headline: str, supporting: str) -> str:
    """What a panel shows in place of controls that have nothing to act on."""
    return (
        '<div class="md-empty-state" data-inspector-empty>'
        f'<span class="md-empty-state__icon">{icon(glyph)}</span>'
        f'<strong class="md-empty-state__headline">{escape(headline)}</strong>'
        f'<span class="md-empty-state__supporting">{escape(supporting)}</span>'
        "</div>"
    )


__all__ = ["empty_state"]
