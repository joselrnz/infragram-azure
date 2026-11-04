"""Views: the page's regions, each composed from the primitives in ``components``."""

from __future__ import annotations

from .canvas import canvas
from .drawer import drawer
from .header import header
from .inspector import inspector, template_brief
from .page import page
from .sidebar import shows_provider_mark, sidebar, uses_multicloud_brand

__all__ = [
    "canvas",
    "drawer",
    "header",
    "inspector",
    "page",
    "shows_provider_mark",
    "sidebar",
    "template_brief",
    "uses_multicloud_brand",
]
