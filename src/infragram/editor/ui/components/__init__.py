"""Primitive components: each is a function of its props that returns markup.

Styles sit beside them (``button.css`` beside ``button.py``); primitives
without a builder here (chip, list, nav item, tile, tabs, search, switch,
checkbox, card, menu, tooltip, badge) are styled in their ``.css`` and written
inline by the views and the runtime.
"""

from __future__ import annotations

from .button import button
from .empty_state import empty_state
from .field import color_input, field, select, text_input
from .icon_button import icon_button
from .segmented import segmented

__all__ = [
    "button",
    "color_input",
    "empty_state",
    "field",
    "icon_button",
    "segmented",
    "select",
    "text_input",
]
