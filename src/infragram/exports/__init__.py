"""One-way artifact adapters for a canonical :class:`CloudProject` render.

Template -> HTML is the only layout/rendering operation.  SVG is extracted
from that HTML and PNG screenshots the same inline SVG, preventing geometry,
typography, or accessibility drift between formats.

The package is this one job split along the seams it already had:

- :mod:`.errors` -- the one error every path raises;
- :mod:`.presets` -- named output sizes and the style each asks for;
- :mod:`.svg` -- finishing one SVG document, whatever drew it;
- :mod:`.render` -- drawing a document without a browser;
- :mod:`.browser` -- what a headless browser does for an export;
- :mod:`.project` -- writing the artifacts a caller asked for.

Every public name is re-exported here, so ``from infragram.exports import
export_project`` reads and resolves exactly as it did when this was one module.
"""

from __future__ import annotations

from .browser import (
    EDITOR_READY_TIMEOUT_MS,
    EXPORT_THEMES,
    FONT_HOSTS,
    PNG_CONTENT_MARGIN,
    browser_missing,
    editor_page_url,
    playwright_png_renderer,
    playwright_static_png_renderer,
    playwright_svg_renderer,
    prepare_page,
    remote_url,
    render_offline,
    render_timeout_ms,
)
from .errors import ExportError
from .presets import SIZE_PRESETS, SizePreset
from .project import (
    EXPORT_DISPLAYS,
    EXPORT_FORMATS,
    ExportResult,
    PngRenderer,
    SvgRenderer,
    export_many,
    export_project,
    export_project_async,
)
from .render import (
    EXPORT_LIBRARIES,
    look_variant,
    render_project_html,
    render_project_svg,
)
from .svg import (
    DEFAULT_EXPORT_BACKGROUND,
    extract_svg,
    finish_standalone_svg,
    make_standalone_svg,
    resolve_background,
)

__all__ = [
    "DEFAULT_EXPORT_BACKGROUND",
    "EDITOR_READY_TIMEOUT_MS",
    "EXPORT_DISPLAYS",
    "EXPORT_FORMATS",
    "EXPORT_LIBRARIES",
    "EXPORT_THEMES",
    "ExportError",
    "ExportResult",
    "FONT_HOSTS",
    "PNG_CONTENT_MARGIN",
    "PngRenderer",
    "SIZE_PRESETS",
    "SizePreset",
    "SvgRenderer",
    "browser_missing",
    "editor_page_url",
    "export_many",
    "export_project",
    "export_project_async",
    "extract_svg",
    "finish_standalone_svg",
    "look_variant",
    "make_standalone_svg",
    "playwright_png_renderer",
    "playwright_static_png_renderer",
    "playwright_svg_renderer",
    "prepare_page",
    "remote_url",
    "render_offline",
    "render_project_html",
    "render_project_svg",
    "render_timeout_ms",
    "resolve_background",
]
