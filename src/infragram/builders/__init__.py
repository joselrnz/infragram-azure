"""Builders: the generation logic behind the build:* commands.

Three layers, separated so each is testable on its own:

- :mod:`~infragram.builders.scene` - models, visual vocabulary, placement
- :mod:`~infragram.builders.render` - the only module that writes markup
- :mod:`~infragram.builders.architecture` - topology to scene

``index`` builds the merged icon lookup over every artwork collection.
"""

from .architecture import (
    Scene,
    Style,
    build,
    build_topology,
    from_topology,
    load_icon_set,
    load_style,
    load_theme,
)
from .index import build_index
from .render import render, render_svg
from .scene import Canvas, Cluster, Link, LinkStyle, Node, place

__all__ = [
    "Canvas",
    "Cluster",
    "Link",
    "LinkStyle",
    "Node",
    "Scene",
    "Style",
    "build",
    "build_index",
    "build_topology",
    "from_topology",
    "load_icon_set",
    "load_style",
    "load_theme",
    "place",
    "render",
    "render_svg",
]
