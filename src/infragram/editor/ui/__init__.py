"""The editor chrome, laid out the way a component library is.

::

    ui/
      html.py        markup helpers
      icons.py       the glyph set: icon(name)
      styles/        tokens, base, state layers, collapsed rails, responsive
      components/    primitives: a builder (.py) and its styles (.css)
      views/         the page's regions, composed from primitives
        sidebar  header  canvas  inspector/  drawer  page

Every view is a function of its props that returns markup; nothing here
reaches for global state, so a region can be rendered and read on its own.
The stylesheets live beside the views that own them and are assembled in
cascade order by :mod:`..bundle`, which also assembles the runtime modules,
so the exported page stays one self-contained file.

The primitives take the classes they should wear rather than owning one: the
chrome names its controls after where they sit, and this edition ships
nineteen provider libraries, so neither a site's name nor a provider's may
be written into a shared component.
"""

from __future__ import annotations

from . import views
from .components import button, field, icon_button, segmented, select, text_input
from .icons import ICON_PATHS, icon

__all__ = [
    "ICON_PATHS",
    "button",
    "field",
    "icon",
    "icon_button",
    "segmented",
    "select",
    "text_input",
    "views",
]
