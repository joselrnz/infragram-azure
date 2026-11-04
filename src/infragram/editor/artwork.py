"""Artwork the editor draws itself: data URIs, glyphs and frame styling.

Everything here turns a catalog fact into pixels the shell can embed. No
markup, no state - just the SVG a category, a provider mark or a containment
frame is drawn with, so the shell and the sidebar share one source of truth.
"""

from __future__ import annotations

import base64
import binascii
import copy
import re
from functools import cache
from html import escape
from urllib.parse import unquote

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from ..builders.architecture import load_icon_set, load_style, load_theme
from ..builders.frame_style import frame_glyph_svg, frame_paint
from ..builders.scene import ClusterStyle
from ..themes import Theme

_CATEGORY_ICON_PATHS = {
    "custom": '<path d="M4 20l4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20z"/><path d="M13.5 7.5l3 3"/>',
    "ai-machine-learning": '<path d="M15.5 13a3.5 3.5 0 0 0-3.5 3.5v1a3.5 3.5 0 0 0 7 0v-1.8"/><path d="M8.5 13a3.5 3.5 0 0 1 3.5 3.5v1a3.5 3.5 0 0 1-7 0v-1.8"/><path d="M17.5 16a3.5 3.5 0 0 0 0-7H17"/><path d="M19 9.3V6.5a3.5 3.5 0 0 0-7 0"/><path d="M6.5 16a3.5 3.5 0 0 1 0-7H7"/><path d="M5 9.3V6.5a3.5 3.5 0 0 1 7 0v10"/>',
    "analytics": '<rect x="4" y="12" width="4" height="8" rx="1"/><rect x="10" y="5" width="4" height="15" rx="1"/><rect x="16" y="9" width="4" height="11" rx="1"/><path d="M3 20h18"/>',
    "compute": '<rect x="3" y="4" width="18" height="13" rx="1.5"/><path d="M8 21h8M10 17v4m4-4v4"/>',
    "containers": '<path fill="currentColor" stroke="none" d="M13.152.682a2.251 2.251 0 0 1 2.269 0l.007.004 6.957 4.276a2.277 2.277 0 0 1 1.126 1.964v7.516c0 .81-.432 1.56-1.133 1.968l-.002.001-11.964 7.037-.004.003c-.706.41-1.578.41-2.284 0l-.026-.015-6.503-4.502a2.268 2.268 0 0 1-1.096-1.943V9.438c0-.392.1-.77.284-1.1l.003-.006.014-.026c.197-.342.48-.627.82-.827h.002L13.152.681Zm.757 1.295h-.001L2.648 8.616l6.248 4.247a.775.775 0 0 0 .758-.01h.001l11.633-6.804-6.629-4.074a.75.75 0 0 0-.75.003ZM8.517 14.33a2.286 2.286 0 0 1-.393-.18l-.023-.014-6.102-4.147v7.003c0 .275.145.528.379.664l.025.014 6.114 4.232V14.33ZM18 9.709l-3.25 1.9v7.548L18 17.245Zm-7.59 4.438-.002.002a2.296 2.296 0 0 1-.391.18v7.612l3.233-1.902v-7.552Zm9.09-5.316v7.532l2.124-1.25a.776.776 0 0 0 .387-.671V7.363Z"/>',
    "databases": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7"/>',
    "devops": '<path d="M9.828 9.172a4 4 0 1 0 0 5.656A10 10 0 0 0 12 12a10 10 0 0 1 2.172-2.828 4 4 0 1 1 0 5.656A10 10 0 0 1 12 12a10 10 0 0 0-2.172-2.828"/><path d="M5.5 8.2l1.7.2-.2 1.7M18.5 15.8l-1.7-.2.2-1.7"/>',
    "hybrid-multicloud": '<circle cx="5" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="12" r="2"/><circle cx="11" cy="12" r="2"/><path d="M7 6l3 4m-3 8l3-4m3-2h4M5 7v10"/>',
    "identity": '<path d="M12 2L3 19l9 3 9-3-9-17z"/><path d="M12 2v20M3 19l9-5 9 5"/>',
    "integration": '<rect x="3" y="3" width="5" height="5" rx="1"/><rect x="16" y="3" width="5" height="5" rx="1"/><rect x="3" y="16" width="5" height="5" rx="1"/><rect x="16" y="16" width="5" height="5" rx="1"/><path d="M8 5.5h8M5.5 8v8M18.5 8v8M8 18.5h8M8 8l8 8m0-8L8 16"/>',
    "internet-of-things": '<circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/><path d="M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.5 5.5a9 9 0 0 0 0 13M18.5 5.5a9 9 0 0 1 0 13"/>',
    "governance": '<path d="M7 20h10M6 6l6-1 6 1M12 3v17"/><path d="M9 12l-3-6l-3 6a3 3 0 0 0 6 0"/><path d="M21 12l-3-6l-3 6a3 3 0 0 0 6 0"/>',
    "mobile": '<rect x="6" y="2" width="12" height="20" rx="2"/><path d="M10 5h4M11 19h2"/>',
    "energy": '<path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z"/>',
    "industrial": '<path d="M3 20V9l5 3V9l5 3V9l5 3v8"/><path d="M3 20h18M7 20v-4h3v4M14 20v-4h3v4"/><path d="M16 9V4h3v8"/>',
    "facilities": '<rect x="4" y="3" width="10" height="18" rx="1"/><path d="M14 9h6v12h-6M7 7h1M10 7h1M7 11h1M10 11h1M7 15h1M10 15h1M17 13h1M17 17h1M9 21v-3"/>',
    "networking": '<circle cx="4" cy="17" r="2"/><circle cx="12" cy="17" r="2"/><circle cx="20" cy="17" r="2"/><circle cx="12" cy="6" r="2"/><path d="M12 8v5M4 15v-2h16v2"/>',
    "power-platform": '<path d="M6 4h12l3 4-5 4H4L1 8l5-4z"/><path d="M4 12h12l3 4-5 4H2l-2-4 4-4z"/>',
    "security": '<path d="M12 3a15 15 0 0 0 8 3c0 7-3 12-8 15C7 18 4 13 4 6a15 15 0 0 0 8-3z"/>',
    "storage": '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M11 6.5h7M11 17.5h7"/>',
    "web": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 4 6 4 9s-1 6-4 9c-3-3-4-6-4-9s1-6 4-9z"/>',
}

_CATEGORY_ICON_KINDS = {
    "ai-machine-learning": "brain",
    "analytics": "bar-chart",
    "containers": "github-container",
    "devops": "ci-cd",
    "governance": "governance-scale",
}

#: What ``urllib.parse.quote(text, safe="/+=:;,")`` leaves as it is: the
#: unreserved characters and the safe ones. Every other byte of the UTF-8
#: text is written as %XX, which is what quote does one byte at a time -- in
#: Python, and a PNG wrapper is tens of kilobytes of base64.
_QUOTED = re.compile(rb"[^A-Za-z0-9_.~/+=:;,-]+")


def _percent_encoded(text: str) -> str:
    """``quote(text, safe="/+=:;,")``, byte for byte, without a call per byte."""

    return _QUOTED.sub(
        lambda run: "".join(f"%{byte:02X}" for byte in run.group()).encode("ascii"),
        text.encode("utf-8"),
    ).decode("ascii")


def _data_uri(data: bytes) -> str:
    if b"<svg" in data:
        text = data.decode("utf-8")
        opening = re.search(r"<svg\b[^>]*>", text)
        if opening is not None and "xmlns=" not in opening.group(0):
            text = (
                text[: opening.start()]
                + opening.group(0).replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
                + text[opening.end() :]
            )
        data = text.encode("utf-8")
        # a wrapper around a PNG already carries base64: percent-encode the
        # wrapper instead of base64-ing the whole thing again (a third bigger)
        if "data:image/png;base64," in text:
            return "data:image/svg+xml;charset=utf-8," + _percent_encoded(text)
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def artwork_bytes(icon_uri: str) -> bytes | None:
    """The SVG behind an icon data URI, whichever way ``_data_uri`` wrote it."""
    if icon_uri.startswith("data:image/svg+xml;charset=utf-8,"):
        return unquote(icon_uri.split(",", 1)[1]).encode("utf-8")
    if not icon_uri.startswith("data:image/svg+xml;base64,"):
        return None
    try:
        return base64.b64decode(icon_uri.split(",", 1)[1])
    except (ValueError, binascii.Error):
        return None


def _glyph_uri(glyph: str, *, foreground: str = "#607d8b") -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        f'<rect x="1" y="1" width="30" height="30" rx="4" fill="none" '
        f'stroke="{foreground}" stroke-width="1.5"/>'
        f'<text x="16" y="21" text-anchor="middle" fill="{foreground}" '
        'font-family="system-ui,sans-serif" font-size="14" font-weight="600">'
        f"{escape(glyph)}</text></svg>"
    )
    return _data_uri(svg.encode("utf-8"))


_VIEWBOX = re.compile(
    r'viewBox="\s*([-\d.]+)[\s,]+([-\d.]+)[\s,]+([-\d.]+)[\s,]+([-\d.]+)\s*"', re.IGNORECASE
)
_RECT = re.compile(r"<rect\b[^>]*?(?:/>|>\s*</rect>)", re.IGNORECASE | re.DOTALL)


def _strip_background_plate(artwork: str) -> str:
    """Drop a rect that covers the whole viewBox: the icon's colour plate.

    Official group icons (AWS Region, VPC, subnets) are a white glyph on a
    coloured plate. A frame tab is already a coloured surface, and recolouring
    the plate to the tab's paint would erase the glyph into a blank square.
    """

    box = _VIEWBOX.search(artwork)
    if box is None:
        return artwork
    width, height = float(box.group(3)), float(box.group(4))

    def covers(value: str, extent: float) -> bool:
        value = value.strip()
        if value.endswith("%"):
            return float(value[:-1]) >= 100
        try:
            return float(value.removesuffix("px")) >= extent
        except ValueError:
            return False

    def is_plate(rect: str) -> bool:
        attributes = dict(re.findall(r'\b([\w:-]+)="([^"]*)"', rect))
        try:
            x = float(attributes.get("x") or 0)
            y = float(attributes.get("y") or 0)
        except ValueError:
            return False
        return (
            x <= 0
            and y <= 0
            and covers(attributes.get("width", "0"), width)
            and covers(attributes.get("height", "0"), height)
        )

    return _RECT.sub(lambda match: "" if is_plate(match.group(0)) else match.group(0), artwork)


def _boundary_icon_uri(reference: str, paint: str, *, repaint: bool = True) -> str:
    if not reference or ":" not in reference:
        return ""
    collection, _, slug = reference.partition(":")
    try:
        pack = load_icon_set(collection)
        icon = pack[slug] if "#" in slug else pack.find(slug)
    except (KeyError, ValueError):
        return ""
    artwork = _strip_background_plate(icon.path.read_text(encoding="utf-8"))
    artwork = artwork.replace("currentColor", paint)
    # A tab painted the frame's own colour needs a single-ink glyph to read
    # against it, so provider artwork is normalized to that ink while keeping
    # the official geometry. A paper tab is white and the vendor's badge is
    # meant to paint itself there, so its own colours survive: flattening them
    # drew Azure's cyan resource-group cube as a grey one, and disagreed with
    # the static renderer, which never flattened it.
    if repaint:
        artwork = re.sub(
            r'(?i)\b(fill|stroke)=("|\')(?!none\2|transparent\2|url\()[^"\']+\2',
            lambda match: f"{match.group(1)}={match.group(2)}{paint}{match.group(2)}",
            artwork,
        )
        # An icon that declares no paint at all inherits SVG's default fill,
        # which is black: the Kubernetes mark is one, and it drew as a black
        # wheel on Google Cloud's blue tab while every other badge was white.
        # Painting the root lets anything unfilled take the tab's ink; a
        # child that names its own paint still wins.
        if not re.search(r"(?i)<svg\b[^>]*\bfill=", artwork):
            artwork = re.sub(r"(?i)<svg\b", f'<svg fill="{paint}"', artwork, count=1)
    return _data_uri(artwork.encode("utf-8"))


@cache
def _boundary_semantic_icon_uri(kind: str, paint: str = "#ffffff") -> str:
    """The generic glyph for a frame kind, from assets/catalog/frame-glyphs.json."""

    return _data_uri(frame_glyph_svg(kind, paint).encode("utf-8"))


class FrameVisual(BaseModel):
    """One frame's look as the editor runtime reads it, in the runtime's camelCase."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    stroke: str
    fill: str
    dash: str | None
    stroke_width: float
    radius: int
    tabbed: bool = True
    tab: int
    tab_fill: str
    icon_uri: str
    label_color: str
    label_font: str
    label_size: float
    label_weight: int | None
    label_tracking: str
    label_case: str
    pad: int


def frame_visual(cs: ClusterStyle, theme: Theme, kind: str, *, depth: int = 0) -> dict[str, object]:
    """One frame's look as the editor runtime reads it.

    The derivation is ``frame_paint``; this adds the badge as a data URI --
    the theme's artwork for the kind in the ink that contrasts with the tab,
    else the generic glyph for the kind in that same ink -- and names the
    keys the runtime expects. ``state.py`` calls it for a project's frames,
    ``_boundary_component_style`` for the library gallery, so the canvas,
    the sidebar and the Python renderer describe a frame identically.
    """

    paint = frame_paint(cs, theme, kind, depth=depth)
    icon_uri = (
        _boundary_icon_uri(paint.badge, paint.glyph_ink, repaint=not paint.paper_tab)
        if paint.badge
        else ""
    ) or _boundary_semantic_icon_uri(kind, paint.glyph_ink)
    visual = FrameVisual(
        stroke=paint.stroke,
        fill=paint.fill,
        dash=paint.dash,
        stroke_width=paint.width,
        radius=paint.radius,
        tabbed=True,
        tab=paint.tab,
        tab_fill=paint.tab_fill,
        icon_uri=icon_uri,
        label_color=paint.label_color,
        label_font=paint.label_font,
        label_size=paint.label_size,
        label_weight=paint.label_weight,
        label_tracking=paint.label_tracking,
        label_case=paint.label_case,
        pad=paint.pad,
    ).model_dump(by_alias=True)
    if not getattr(theme, "dark", False):
        # What this frame looks like on a dark canvas, derived here so the
        # canvas and the picture cannot answer differently: a colour that
        # cannot be seen on the dark ground is lifted (catalog/ink.py), and
        # the badge is repainted in the ink its lifted tab takes.
        from ..exports.palette import dark as dark_theme

        night = frame_visual(cs, dark_theme(theme), kind, depth=depth)
        # Only what the dark ground changes, laid over the light values by
        # the runtime (14-shapes.js): carrying the whole look again cost
        # 87 KB on an AWS page. The badge is the weight of it, and it is
        # worth carrying only for a frame whose tab changed colour -- on a
        # tab that did not, the badge a reader already sees still reads.
        night = {key: value for key, value in night.items() if visual.get(key) != value}
        if "tabFill" not in night:
            night.pop("iconUri", None)
        visual["dark"] = night
    return visual


def _boundary_component_style(provider: str, kind: str) -> dict[str, object]:
    """A library frame's look, from that library's theme.

    The theme is the one source of a frame's colour (a test holds the
    sidebar's table to it); the generic library draws with the on-premises
    theme.
    """

    return copy.deepcopy(_library_frame_visual(provider, kind))


@cache
def _library_frame_visual(provider: str, kind: str) -> dict[str, object]:
    """Worked out once per library and kind: every library's sidebar carries
    the same frame gallery, and each frame reads its theme and badge."""

    name = "onprem" if provider in ("generic", "") else provider
    return frame_visual(load_style(name).cluster, load_theme(name), kind)


def _boundary_preview_uri(label: str, style: dict[str, object]) -> str:
    stroke = str(style["stroke"])
    fill = str(style["fill"])
    dash = (
        f' stroke-dasharray="{escape(str(style["dash"]), quote=True)}"' if style.get("dash") else ""
    )
    tab = ""
    label_x = 7
    if style.get("tabbed"):
        icon_uri = str(style.get("iconUri") or "")
        icon = (
            f'<image href="{escape(icon_uri, quote=True)}" x="4" y="9" '
            'width="12" height="12" preserveAspectRatio="xMidYMid meet"/>'
            if icon_uri
            else ""
        )
        tab = f'<rect x="2" y="7" width="16" height="16" fill="{stroke}"/>{icon}'
        label_x = 22
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 72">'
        f'<rect x="2" y="7" width="116" height="63" rx="{style["radius"]}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{style["strokeWidth"]}"{dash}/>'
        f'{tab}<rect x="{label_x - 3}" y="2" width="52" height="12" fill="#242424"/>'
        f'<text x="{label_x}" y="11" fill="{stroke}" font-family="system-ui,sans-serif" '
        f'font-size="7" font-weight="650">{escape(label)}</text></svg>'
    )
    return _data_uri(svg.encode("utf-8"))


def _category_icon(category_id: str) -> str:
    paths = _CATEGORY_ICON_PATHS[category_id]
    kind = _CATEGORY_ICON_KINDS.get(category_id, category_id)
    return (
        f'<svg class="category-icon" data-category-icon="{category_id}" '
        f'data-category-icon-kind="{kind}" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
        f"{paths}</svg>"
    )
