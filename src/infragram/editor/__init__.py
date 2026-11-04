"""Self-contained cloud editor shell around a rendered diagram SVG.

Split by job so each piece stays readable on its own:

- :mod:`.artwork` - data URIs, glyphs and the styling of containment frames
- :mod:`.sidebar` - the component library per provider, and its JSON payload
- :mod:`.state`   - the portable graph the browser edits
- :mod:`.shell`   - the page itself

Only the public names resolve from ``infragram.editor``; a helper an
internal script or test needs is imported from the module that owns it.
"""

from __future__ import annotations

from .shell import EMBEDDED_LIBRARIES, render_editor_html
from .sidebar import (
    SidebarCatalog,
    SidebarCategory,
    SidebarComponent,
    load_sidebar_catalog,
)

__all__ = [
    "EMBEDDED_LIBRARIES",
    "SidebarCatalog",
    "SidebarCategory",
    "SidebarComponent",
    "load_sidebar_catalog",
    "render_editor_html",
]
