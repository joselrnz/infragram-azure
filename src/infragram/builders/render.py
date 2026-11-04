"""Scene -> HTML. The only module in the package that writes markup.

Every dimension, weight and colour comes from ``scene.style`` and
``scene.theme``; nothing here decides what a diagram looks like. Colours are
named by *role* and resolved against the theme, so the same scene renders
correctly on any skin.
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from html import escape
from pathlib import Path

from ..catalog import ink
from ..catalog.fonts import font_style_element
from ..themes import THEME_ROLES
from ..themes.colour import HEX_COLOUR
from ..verification import (
    inner_body,
    root_presentation,
    strip_editor_metadata,
    unsafe_svg_match,
    view_box,
)
from . import arrowheads, captions, metrics, panels
from .crossings import crossing_plan
from .frame_style import frame_glyph_symbol, frame_glyph_symbol_id, frame_paint
from .ink import rgba
from .routing import (
    Point,
    Rail,
    Rect,
    Route,
    Router,
    fence_crossings,
    nearest,
    outward,
    rail_run,
    spread,
)
from .scene import (
    CAPTION_DETAIL_ADVANCE,
    CORNER_BADGE,
    DETAIL_ADVANCE,
    EDGE_BADGE,
    GRID,
    TITLE_ADVANCE,
    TITLE_MIN,
    Cluster,
    Link,
    Node,
    Scene,
    corner_layout,
    corner_row_width,
    edge_layout,
    edge_row_width,
    glyph_square,
)

#: Where the editor draws a card's lines and an icon's caption
#: (render-metrics.json ``card`` and ``icon_node``).
_CARD = metrics.card()
_ICON = metrics.icon_node()


class _Artwork:
    """Anything that draws an icon: a node, a zone, or a zone's corner badge."""

    __slots__ = ("icon",)

    def __init__(self, icon) -> None:
        self.icon = icon


def _drawn_icons(scene: Scene):
    """Every icon in the scene, whatever kind of thing carries it.

    Nodes are not the only things with artwork -- a zone can be titled with
    its own icon. Missing those here emitted <use> references to symbols
    that were never defined.
    """
    yield from scene.root.walk()
    for cluster in scene.root.clusters():
        if cluster.icon is not None:
            yield _Artwork(cluster.icon)
        for badge in cluster.badges:
            yield _Artwork(badge.icon)


#: The filter dark artwork is drawn through on a dark ground: its lightness
#: turned over, its hue kept, so black reads white and a dark slate reads
#: light while a colourful mark stays the colour its vendor drew it. The
#: editor draws the same filter on its own dark canvas.
INK_ON_DARK = "infragram-ink-on-dark"
INK_ON_DARK_FILTER = (
    f'<filter id="{INK_ON_DARK}" color-interpolation-filters="sRGB">'
    '<feColorMatrix type="matrix" values="-1 0 0 0 1 0 -1 0 0 1 0 0 -1 0 1 0 0 0 1 0"/>'
    '<feColorMatrix type="hueRotate" values="180"/></filter>'
)


@lru_cache(maxsize=512)
def _artwork_is_dark(slug: str, markup: str | None, path: str) -> bool:
    """Whether one icon's artwork is too dark for a dark ground.

    Cached on the artwork itself: a drawing places the same icon many times,
    and the answer is a table lookup over bytes that are read from disk.
    """
    source = markup if markup is not None else Path(path).read_text(encoding="utf-8")
    return ink.is_dark(source.encode("utf-8"))


def _dark_icon(icon, scene: Scene) -> bool:
    """A node's icon needs drawing light: the palette is dark and so is it.

    Only a node's icon. A frame's badge sits on the frame's own tab -- often
    a light one -- where turning its lightness over would hide it, and the
    editor leaves it alone there too (14-shapes.js).
    """
    if icon is None or not scene.theme.dark:
        return False
    return _artwork_is_dark(icon.slug, icon.markup, str(icon.path))


def _ink_filter(icon, scene: Scene) -> str:
    return f' filter="url(#{INK_ON_DARK})"' if _dark_icon(icon, scene) else ""


def _symbols(scene: Scene) -> tuple[str, dict[int, str]]:
    """One <symbol> per distinct icon, internal ids namespaced.

    Without namespacing, two icons that both define ``id="a"`` would share
    whichever definition came first once inlined into one document.

    Dedup is by artwork, not by object: every lookup builds a fresh
    ProviderIcon, so keying on identity emitted the same symbol once per
    node that used it -- duplicate ids in one document, and wasted bytes.
    Nor is it by slug alone: packs reuse ids (five libraries each ship an
    ``app-service``), so a second pack's artwork under a slug already
    placed gets its own symbol, ``icon-<slug>-2``, instead of the first
    pack's picture.
    """
    symbols: dict[tuple[str, str], str] = {}
    taken: dict[str, int] = {}
    seen: dict[int, str] = {}
    out: list[str] = []
    # Artwork drawn in a dark ink -- a line icon, a black vendor mark --
    # disappears on a dark ground, so on a dark palette a node's icon is
    # drawn through one filter that turns its lightness over and keeps its
    # hue, exactly as the editor draws it there (08-theme-and-layout.js).
    # Which artwork is dark was measured when the ink table was built
    # (catalog/ink.py).
    darkened = any(_dark_icon(node.icon, scene) for node in scene.root.walk())
    for node in _drawn_icons(scene):
        if node.icon is None:
            continue
        artwork = (
            node.icon.slug,
            node.icon.markup if node.icon.markup is not None else str(node.icon.path),
        )
        if artwork in symbols:
            seen[id(node.icon)] = symbols[artwork]
            continue
        source = (
            node.icon.markup
            if node.icon.markup is not None
            else node.icon.path.read_text(encoding="utf-8")
        )
        box, body = view_box(source), inner_body(source)
        # A stroked glyph carries its style on the root and nowhere else;
        # dropping it turned every neutral outline into a black silhouette.
        paint = root_presentation(source)
        # Inkscape leftovers make the editor's own SVG export unparseable,
        # which silently degraded every PNG of a diagram that used them.
        body = strip_editor_metadata(body) if body else body
        if box is None or body is None:
            raise ValueError(f"unusable icon svg: {node.icon.slug} ({node.icon.path})")
        # Artwork is inlined verbatim into the export, so it is checked here
        # rather than trusted: a pack is third-party data, and the importers
        # that vet it do not run again when someone points a document at a
        # collection of their own.
        unsafe = unsafe_svg_match(source)
        if unsafe is not None:
            raise ValueError(
                f"unsafe icon svg: {node.icon.slug} ({node.icon.path}) contains {unsafe.group(0)!r}"
            )
        base = f"icon-{node.icon.slug}"
        taken[base] = taken.get(base, 0) + 1
        key = base if taken[base] == 1 else f"{base}-{taken[base]}"
        for old in sorted(set(re.findall(r'\bid="([^"]+)"', body)), key=len, reverse=True):
            new = f"{key}-{old}"
            body = (
                body.replace(f'id="{old}"', f'id="{new}"')
                .replace(f"url(#{old})", f"url(#{new})")
                .replace(f'href="#{old}"', f'href="#{new}"')
            )
        seen[id(node.icon)] = symbols[artwork] = key
        out.append(f'          <symbol id="{key}" viewBox="{box}"{paint}>{body}</symbol>')
    # A frame without a badge seats the generic glyph for its kind; one
    # symbol per kind, referenced from every tab that needs it.
    for kind in sorted({cl.kind for cl in scene.root.clusters() if cl.icon is None}):
        out.append("          " + frame_glyph_symbol(kind))
    if darkened:
        out.insert(0, "          " + INK_ON_DARK_FILTER)
    return "\n".join(out), seen


def _fit(text: str, room: float, per_char: float, floor: int = 6) -> str:
    """``text`` cut to the characters that fit ``room`` pixels, with an
    ellipsis, the way the editor truncates a card's title.

    ``per_char`` is pixels per character, the same number the layout reserved
    the room with. It used to be derived here from the type size and one
    shared advance, which silently measured a card's detail line at 5.51 px
    where the layout had reserved 5.2 -- so a detail that fitted was cut. The
    tiny epsilon absorbs the float error in a width that divides exactly.
    """
    budget = max(floor, math.floor(room / per_char + 1e-9))
    return text if len(text) <= budget else text[: budget - 1] + "…"


def _detail_ink(theme) -> str:
    """The colour a card's second line takes.

    ``muted`` carries two jobs -- a wire's colour and a card's detail line --
    which one palette entry can serve on paper and cannot on a dark ground,
    where a wire wants to sit back and small text must not. On a dark
    palette the line takes ``soft``, the palette's secondary text colour,
    which is what the editor paints it (``--text-secondary``).
    """
    return theme["soft"] if getattr(theme, "dark", False) else theme["muted"]


def _node(node: Node, scene: Scene, icon_ids: dict[int, str]) -> str:
    T, ns = scene.theme, scene.style.node
    # a node is drawn after the layout has sized it
    assert node.width is not None and node.height is not None
    if node.accent:
        # A role name re-reads per skin; a literal hex is brand artwork.
        # Anything else is refused here, by name, rather than as an
        # unparseable pair of hex digits deep inside rgba().
        paint = T.get(node.accent, node.accent)
        if not HEX_COLOUR.match(paint.strip()):
            raise ValueError(
                f"node {node.name!r}: accent {node.accent!r} is neither a theme role "
                f"({', '.join(THEME_ROLES)}) nor a hex colour (#rgb or #rrggbb)"
            )
        border = rgba(paint, ns.accent_alpha)
        fill = rgba(paint, ns.accent_fill_alpha)
    elif node.focal:
        border = T["accent"]
        fill = rgba(T["accent"], ns.focal_alpha)
    else:
        border = rgba(T[ns.border], ns.border_alpha)
        fill = rgba(T["ink"], ns.fill_alpha)
    # A card's own colours, as the editor paints them (editor/state.py
    # carries the same fill and stroke into the page).
    fill, border = node.fill or fill, node.stroke or border
    # A native tooltip on the group: SVG viewers show a <title> on hover, so
    # the exported file explains a card without any script behind it.
    tooltip = escape(" · ".join(part for part in (node.name, node.detail) if part))
    # A bare glyph also carries where its ink begins along every line of each
    # side: its links are seated there, and the checker holds them to it.
    edge_code = _ink_edges(node) if node.icon_only else ""
    edge_attr = f'data-ink-edge="{edge_code}" ' if edge_code else ""
    panel_attr = ' data-panel=""' if node.panel is not None else ""
    lines = [
        f'        <g data-ink="{",".join(f"{v:g}" for v in _ink(node))}" {edge_attr}'
        f'data-node="{escape(node.ref or node.name, quote=True)}" '
        f'data-display="{node.display}"{panel_attr}><title>{tooltip}</title>'
    ]
    if node.panel is not None:
        lines += _panel(node, scene, icon_ids, fill, border)
        lines += _flag(node)
        lines.append("        </g>")
        return "\n".join(lines)
    if node.icon_only:
        # The bare mark, caption beneath, no box: the reference-architecture
        # look. An invisible rect still marks the node's extent, the same as
        # the editor draws, so a wire has an edge to arrive at and a checker
        # has a box to measure. Every number is the editor's
        # (render-metrics.json ``icon_node``).
        left, top, glyph = glyph_square(node, scene.style)
        cx = node.x + node.width / 2
        lines.append(
            f'        <rect x="{node.x}" y="{node.y}" width="{node.width}" height="{node.height}" '
            f'rx="{ns.radius}" fill="none" stroke="none"/>'
        )
        if node.icon is not None:
            lines.append(
                f'        <use href="#{icon_ids[id(node.icon)]}" x="{left:g}" '
                f'y="{top:g}" width="{glyph:g}" height="{glyph:g}" aria-hidden="true"'
                f"{_ink_filter(node.icon, scene)}/>"
            )
        else:
            size = min(40, node.width - 8, node.height - 8)
            lines += _blank_tile(node, scene, size, node.x + (node.width - size) / 2)
        if node.height >= ns.icon_caption_min_height:
            room = node.width - _ICON["caption_pad"]
            lines.append(
                f'        <text x="{cx:g}" y="{top + glyph + _ICON["caption_gap"]:g}" '
                f'fill="{T["ink"]}" font-size="{ns.title_size:g}" font-weight="{_CARD["title_weight"]}" '
                f'font-family="{scene.style.sans}" text-anchor="middle">'
                f"{escape(_fit(node.name, room, ns.title_size * TITLE_ADVANCE, floor=_ICON['caption_min_chars']))}"
                "</text>"
            )
            if node.detail and node.height >= _ICON["detail_min_height"]:
                lines.append(
                    f'        <text x="{cx:g}" y="{top + glyph + _ICON["detail_gap"]:g}" '
                    f'fill="{_detail_ink(T)}" font-size="{ns.icon_detail_size:g}" '
                    f'font-family="{scene.style.sans}" text-anchor="middle">'
                    f"{escape(_fit(node.detail, room, CAPTION_DETAIL_ADVANCE, floor=0))}</text>"
                )
        lines += _flag(node)
        lines.append("        </g>")
        return "\n".join(lines)
    lines += [
        f'        <rect x="{node.x}" y="{node.y}" width="{node.width}" height="{node.height}" '
        f'rx="{ns.radius}" fill="{T["paper"]}"/>',
        f'        <rect x="{node.x}" y="{node.y}" width="{node.width}" height="{node.height}" '
        f'rx="{ns.radius}" fill="{fill}" stroke="{border}" stroke-width="1"/>',
    ]
    # The card's icon lane, both lines and their room: the editor's numbers
    # (render-metrics.json ``card``).
    if node.icon is not None:
        lines.append(
            f'        <use href="#{icon_ids[id(node.icon)]}" x="{node.x + ns.icon_inset}" '
            f'y="{node.y + (node.height - ns.icon_size) / 2:g}" width="{ns.icon_size}" '
            f'height="{ns.icon_size}" aria-hidden="true"{_ink_filter(node.icon, scene)}/>'
        )
    else:
        lines += _blank_tile(node, scene, _CARD["blank"], node.x + _CARD["blank_x"])
    text_x = node.x + ns.text_inset
    middle = node.y + node.height / 2
    room = max(_CARD["min_room"], node.width - ns.text_inset - _CARD["text_end"])
    lines.append(
        f'        <text x="{text_x}" y="{middle + _CARD["title_dy"]:g}" fill="{T["ink"]}" '
        f'font-size="{ns.title_size:g}" font-weight="{_CARD["title_weight"]}" '
        f'font-family="{scene.style.sans}" text-anchor="start">'
        f"{escape(_fit(node.name, room, ns.title_size * TITLE_ADVANCE, floor=_CARD['min_chars']))}</text>"
    )
    if node.detail:
        lines.append(
            f'        <text x="{text_x}" y="{middle + _CARD["detail_dy"]:g}" fill="{_detail_ink(T)}" '
            f'font-size="{ns.detail_size:g}" font-family="{scene.style.sans}" '
            f'text-anchor="start">'
            f"{escape(_fit(node.detail, room, DETAIL_ADVANCE, floor=_CARD['min_chars']))}</text>"
        )
    lines += _flag(node)
    lines.append("        </g>")
    return "\n".join(lines)


def _tone(name: str, scene: Scene) -> tuple[str, str] | None:
    """A named tone's fill and outline, on this canvas."""
    tone = metrics.tones().get(name) if name else None
    if tone is None:
        return None
    return (tone.fill_dark, tone.stroke_dark) if scene.theme.dark else (tone.fill, tone.stroke)


def _outline(shape: str, x: float, y: float, w: float, h: float, radius: float) -> str:
    """The SVG element drawing a panel's shape; the caller adds the paint."""
    if shape == "ellipse":
        return f'<ellipse cx="{x + w / 2:g}" cy="{y + h / 2:g}" rx="{w / 2:g}" ry="{h / 2:g}"'
    if shape == "hexagon":
        inset = metrics.panel().hex_inset
        points = [
            (x + inset, y), (x + w - inset, y), (x + w, y + h / 2),
            (x + w - inset, y + h), (x + inset, y + h), (x, y + h / 2),
        ]  # fmt: skip
        return '<polygon points="' + " ".join(f"{px:g},{py:g}" for px, py in points) + '"'
    if shape == "note":
        fold = metrics.panel().fold
        return (
            f'<path d="M{x:g},{y:g} H{x + w - fold:g} L{x + w:g},{y + fold:g} V{y + h:g} H{x:g} Z"'
        )
    return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="{radius:g}"'


def _panel(node: Node, scene: Scene, icon_ids: dict[int, str], fill: str, border: str) -> list[str]:
    """A panel's box, heading and compartments (builders/panels.py)."""
    panel = node.panel
    assert panel is not None and node.width is not None and node.height is not None
    T, P = scene.theme, metrics.panel()
    sans = scene.style.sans
    x, y, w, h = node.x, node.y, node.width, node.height
    own = _tone(panel.tone, scene)
    if own and not node.fill:
        fill = own[0]
    if own and not node.stroke:
        border = own[1]
    shape = panel.shape
    lines = [
        # an invisible rect marks the panel's extent whatever its shape, as a
        # bare glyph's does: a wire has an edge to arrive at, a checker a box
        f'        <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{P.radius:g}" fill="none" stroke="none"/>',
        f'        {_outline(shape, x, y, w, h, P.radius)} fill="{T["paper"]}"/>',
        f'        {_outline(shape, x, y, w, h, P.radius)} fill="{fill}" stroke="none"/>',
    ]
    inset_x, inset_y = panels.side_insets(panel)
    lane = panels.icon_lane(node.icon is not None)
    if node.icon is not None:
        lines.append(
            # inside the outline: an ellipse's or a hexagon's corner is air
            f'        <use href="#{icon_ids[id(node.icon)]}" x="{x + inset_x + P.icon_x:g}" y="{y + inset_y + P.icon_y:g}" '
            f'width="{P.icon}" height="{P.icon}" aria-hidden="true"{_ink_filter(node.icon, scene)}/>'
        )
    cx = x + w / 2
    room = w - 2 * (inset_x + P.pad_x + lane)
    top = y + inset_y + P.pad_top
    lines.append(
        f'        <text x="{cx:g}" y="{panels.baseline(top, P.title_line, P.title_size):g}" '
        f'fill="{T["ink"]}" font-size="{P.title_size:g}" font-weight="{P.title_weight}" '
        f'font-family="{sans}" text-anchor="middle">'
        f"{escape(panels.fit(node.name, room, P.title_size * TITLE_ADVANCE))}</text>"
    )
    top += P.title_line
    for line in panel.detail_lines:
        lines.append(
            f'        <text x="{cx:g}" y="{panels.baseline(top, P.detail_line, P.detail_size):g}" '
            f'fill="{_detail_ink(T)}" font-size="{P.detail_size:g}" font-family="{sans}" '
            f'text-anchor="middle">{escape(panels.fit(line, room, P.detail_advance))}</text>'
        )
        top += P.detail_line
    top = y + inset_y + panels.heading_height(panel)
    for row in panel.sections:
        height = panels.row_height(row)
        left: float = x
        for index, (cell, width) in enumerate(zip(row, panels.cell_widths(row, w), strict=True)):
            paint = _tone(cell.tone, scene)
            if paint:
                # one unit in from the outline, so a tone never shows past a
                # rounded corner; the outline is drawn over it
                lines.append(
                    f'        <rect data-panel-cell="" x="{left + (1 if index == 0 else 0):g}" '
                    f'y="{top:g}" width="{width - (1 if index == 0 else 0) - (1 if index == len(row) - 1 else 0):g}" '
                    f'height="{height - (1 if top + height >= y + h - 0.5 else 0):g}" fill="{paint[0]}"/>'
                )
            if index:
                lines.append(
                    f'        <line x1="{left:g}" y1="{top:g}" x2="{left:g}" y2="{top + height:g}" '
                    f'stroke="{border}" stroke-width="1"/>'
                )
            middle = left + width / 2
            text_room = width - 2 * P.cell_pad_x
            line_top = top + P.cell_pad_y
            if cell.title:
                lines.append(
                    f'        <text x="{middle:g}" y="{panels.baseline(line_top, P.cell_title_line, P.cell_title_size):g}" '
                    f'fill="{T["ink"]}" font-size="{P.cell_title_size:g}" font-weight="{P.cell_title_weight}" '
                    f'font-family="{sans}" text-anchor="middle">'
                    f"{escape(panels.fit(cell.title, text_room, P.cell_title_size * TITLE_ADVANCE))}</text>"
                )
                line_top += P.cell_title_line
            for text in cell.lines:
                lines.append(
                    f'        <text x="{middle:g}" y="{panels.baseline(line_top, P.cell_line, P.cell_size):g}" '
                    f'fill="{_detail_ink(T)}" font-size="{P.cell_size:g}" font-family="{sans}" '
                    f'text-anchor="middle">{escape(panels.fit(text, text_room, P.cell_advance))}</text>'
                )
                line_top += P.cell_line
            left += width
        lines.append(
            f'        <line x1="{x:g}" y1="{top:g}" x2="{x + w:g}" y2="{top:g}" stroke="{border}" stroke-width="1"/>'
        )
        top += height
    lines.append(
        f'        {_outline(shape, x, y, w, h, P.radius)} fill="none" stroke="{border}" stroke-width="1"/>'
    )
    if shape == "note":
        fold = P.fold
        lines.append(
            f'        <path d="M{x + w - fold:g},{y:g} V{y + fold:g} H{x + w:g}" fill="none" '
            f'stroke="{border}" stroke-width="1"/>'
        )
    return lines


def _flag(node: Node) -> list[str]:
    """The word Unused inside a flagged card's top-right corner, as the editor
    draws it (render-metrics.json ``flag``)."""
    if not node.flagged:
        return []
    assert node.width is not None  # drawn after the layout sized it
    tag = metrics.flag()
    width = tag.width()
    left = node.x + node.width - tag.inset - width
    top = node.y + tag.inset
    return [
        f'        <g data-unused-flag="true"><rect x="{left:g}" y="{top:g}" width="{width}" '
        f'height="{tag.height:g}" rx="{tag.radius:g}" fill="{tag.fill}" stroke="{tag.stroke}" '
        f'stroke-width="0.8"/><text x="{left + width / 2:g}" '
        f'y="{top + tag.height / 2 + tag.font * 0.35:g}" fill="{tag.ink}" '
        f'font-size="{tag.font:g}" font-weight="{tag.weight}" '
        f'font-family="\'Inter\',sans-serif" text-anchor="middle">{escape(tag.label)}</text></g>'
    ]


def _blank_tile(node: Node, scene: Scene, size: float, left: float) -> list[str]:
    """What the editor draws for a component with no artwork: a tile with the
    name's first letter, centred down the node."""
    assert node.height is not None  # drawn after the layout sized it
    top = node.y + (node.height - size) / 2
    letter = escape(node.name[:1].upper())
    return [
        f'        <rect x="{left:g}" y="{top:g}" width="{size:g}" height="{size:g}" rx="4" '
        f'fill="{scene.theme["paper"]}"/>',
        f'        <text x="{left + size / 2:g}" y="{node.y + node.height / 2 + 5:g}" '
        f'text-anchor="middle" font-family="{scene.style.sans}" font-size="12" '
        f'font-weight="600" fill="{_detail_ink(scene.theme)}">{letter}</text>',
    ]


def _zone_border(cl: Cluster, radius: int) -> str:
    """The zone outline, whole: every frame seats its label beside a corner
    tab, so there is never a break in the top edge to mask."""
    x, y, w, h = cl.x, cl.y, cl.width, cl.height
    right, bottom = x + w, y + h
    r = max(0, radius)

    def corner(to_x: int, to_y: int) -> str:
        return f"A{r},{r} 0 0 1 {to_x},{to_y}" if r else f"L{to_x},{to_y}"

    return " ".join(
        [
            f"M{x + r},{y}",
            f"H{right - r}",
            corner(right, y + r),
            f"V{bottom - r}",
            corner(right - r, bottom),
            f"H{x + r}",
            corner(x, bottom - r),
            f"V{y + r}",
            corner(x + r, y),
            "Z",
        ]
    )


def _cluster(cl: Cluster, scene: Scene, icon_ids: dict[int, str] | None = None) -> str:
    """A zone: its box, its titled label, and any marks on its border."""
    # A frame placed from another gallery keeps that gallery's look, the
    # way the editor draws it; every other frame draws with the scene's own.
    T = cl.look_theme or scene.theme
    cs = cl.look_style or scene.style.cluster
    ids = icon_ids or {}
    label = cl.label.upper() if cs.label_case == "upper" else cl.label
    # One derivation for both renderers: builders/frame_style.py. The
    # project's frame lines weigh every border alike.
    paint = frame_paint(cs, T, cl.kind, depth=cl.depth)
    if scene.frame_line_scale != 1:
        paint = paint.model_copy(update={"width": round(paint.width * scene.frame_line_scale, 2)})
    radius = paint.radius
    zone_paint = paint.stroke
    zone_fill = paint.fill
    pattern = paint.dash
    outline = f' stroke-dasharray="{pattern}"' if pattern else ""
    # Every frame seats a tab in its corner -- the theme's badge for the
    # kind, else the generic glyph for the kind -- and keeps its outline
    # whole; the caption sits inside beside the tab. The tab already owns
    # the glyph's width, so the caption never reserves it a second time.
    label_x = cl.x + cs.tab + cs.label_icon_gap
    label_y = cl.y + cs.tab / 2 + cs.label_size / cs.label_baseline_divisor
    label_family = scene.style.sans if cs.label_font == "sans" else scene.style.mono
    label_weight = f' font-weight="{cs.label_weight}"' if cs.label_weight is not None else ""

    # A called-out zone: the editor's ring, six units out, in the accent.
    highlight = (
        [
            f'        <rect data-frame-highlight="" x="{cl.x - 6}" y="{cl.y - 6}" width="{cl.width + 12}" '
            f'height="{cl.height + 12}" rx="{radius + 6}" fill="{T["accent"]}" fill-opacity=".07" '
            f'stroke="{T["accent"]}" stroke-width="2.5"/>'
        ]
        if cl.highlight
        else []
    )
    parts = [
        *highlight,
        f'        <rect x="{cl.x}" y="{cl.y}" width="{cl.width}" height="{cl.height}" '
        f'rx="{radius}" fill="{zone_fill}"/>',
        f'        <path d="{_zone_border(cl, radius)}" '
        f'fill="none" stroke="{zone_paint}" '
        f'stroke-width="{paint.width:g}"{outline}/>',
        f'        <text x="{label_x}" y="{label_y:g}" '
        f'fill="{paint.label_color}" '
        f'font-size="{cs.label_size:g}" font-family="{label_family}"{label_weight} '
        f'letter-spacing="{cs.label_tracking}" text-anchor="start">{escape(label)}</text>',
    ]
    # A ``frame`` tab is filled in the zone's own colour and the glyph
    # reverses out of it in paper, so the corner reads as a label seat.
    # A ``paper`` tab stays white and the icon paints itself: Azure's
    # badges are full-colour icons whose own hue the frame was sampled
    # from, and on a frame-coloured tab they disappeared.
    tab_paint = paint.tab_fill
    glyph_ink = paint.glyph_ink
    # The tab sits inside the border, its outer sides on the stroke's
    # inner edge, so the border stays whole around the corner. Drawn at
    # the corner itself it painted out the inner half of the stroke, and
    # a paper tab left the badge looking as if it sat on the line.
    seat = paint.width / 2
    tab_x, tab_y = cl.x + seat, cl.y + seat
    parts.append(
        f'        <rect x="{tab_x:g}" y="{tab_y:g}" width="{cs.tab}" height="{cs.tab}" '
        f'fill="{tab_paint}"/>'
    )
    inset = cs.label_icon_inset
    if cl.icon is not None and id(cl.icon) in ids:
        # Artwork drawn on currentColor takes the ink that contrasts with
        # the tab; artwork that paints its own colours ignores it.
        parts.append(
            f'        <use href="#{ids[id(cl.icon)]}" x="{tab_x + inset:g}" '
            f'y="{tab_y + inset:g}" width="{cs.label_icon}" height="{cs.label_icon}" '
            f'color="{glyph_ink}" fill="{glyph_ink}" aria-hidden="true"/>'
        )
    else:
        # No vendor badge for this kind: the generic glyph, the same one
        # the editor draws, in the same ink.
        parts.append(
            f'        <use href="#{frame_glyph_symbol_id(cl.kind)}" x="{tab_x + inset:g}" '
            f'y="{tab_y + inset:g}" width="{cs.label_icon}" height="{cs.label_icon}" '
            f'color="{glyph_ink}" aria-hidden="true"/>'
        )
    parts += _edge_badges(
        cl,
        [badge for badge in cl.badges if badge.side == "edge" and id(badge.icon) in ids],
        ids,
        scene,
        T,
    )
    parts += _corner_badges(
        cl,
        [badge for badge in cl.badges if badge.side == "corner" and id(badge.icon) in ids],
        ids,
        scene,
        T,
    )
    for badge in cl.badges:
        if badge.side in ("corner", "edge") or id(badge.icon) not in ids:
            continue
        bx, by = badge.anchor(cl)
        size = 18
        if badge.side == "top":
            bx = max(bx, cluster_label_rect(cl, scene.style).right + size / 2)
            bx = min(bx, cl.x + cl.width - size / 2)
        parts.append(
            f'        <use data-frame-badge="" href="#{ids[id(badge.icon)]}" '
            f'x="{bx - size / 2:g}" y="{by - size / 2:g}" '
            f'width="{size}" height="{size}" aria-hidden="true"/>'
        )
    return "\n".join(parts)


def _edge_badges(cl, badges, ids, scene: Scene, T) -> list[str]:
    """A NAT gateway the way Azure's own diagrams draw one: a bar along the
    frame's top border, the icon on that border at its middle, the name just
    under the line to its right."""
    if not badges:
        return []
    c = EDGE_BADGE
    size, font = c["icon"], CORNER_BADGE["font"]
    parts = [
        f'        <rect x="{cl.x}" y="{cl.y}" width="{cl.width}" height="{c["bar"]}" '
        f'fill="{c["color"]}"/>'
    ]
    slots = edge_layout(cl.x, cl.width, [badge.label for badge in badges])
    for badge, (icon_x, text_x) in zip(badges, slots, strict=True):
        parts.append(
            f'        <use data-frame-badge="" href="#{ids[id(badge.icon)]}" x="{icon_x - size / 2:g}" y="{cl.y - size / 2:g}" '
            f'width="{size}" height="{size}" aria-hidden="true"/>'
        )
        if badge.label:
            parts.append(
                f'        <text data-frame-badge-label="" x="{text_x:g}" y="{cl.y + font + CORNER_BADGE["drop"] + c["bar"]:g}" '
                f'fill="{T["ink"]}" font-size="{font}" font-weight="600" '
                f'font-family="{scene.style.sans}">{escape(badge.label)}</text>'
            )
    return parts


def _corner_badges(cl: Cluster, badges, ids: dict[int, str], scene: Scene, T) -> list[str]:
    """Badges the way Azure's reference diagrams seat an NSG on its subnet.

    The first icon sits on the frame's top-right corner point, the rest on
    the top border leftwards from it; each name sits just under the top
    border, immediately left of its icon. A caption written ``Type · name``
    sets the type in the frame's quiet tone. Nothing is painted behind icon
    or caption: the icon hides the line itself.
    """
    c = CORNER_BADGE
    size = c["icon"]
    parts: list[str] = []
    slots = corner_layout(cl.x + cl.width, [badge.label for badge in badges])
    for badge, (icon_x, text_end, _anchor) in zip(badges, slots, strict=True):
        parts.append(
            f'        <use data-frame-badge="" href="#{ids[id(badge.icon)]}" x="{icon_x - size / 2:g}" '
            f'y="{cl.y - size / 2:g}" width="{size}" height="{size}" aria-hidden="true"/>'
        )
        if not badge.label:
            continue
        kind, sep, name = badge.label.partition(" · ")
        if not sep:
            kind, name = "", badge.label
        lead = (
            f'<tspan fill="{T["muted"]}" font-weight="500">{escape(kind + sep)}</tspan>'
            if kind
            else ""
        )
        parts.append(
            f'        <text data-frame-badge-label="" x="{text_end:g}" y="{cl.y + c["font"] + c["drop"]:g}" '
            f'text-anchor="end" fill="{T["ink"]}" font-size="{c["font"]}" font-weight="600" '
            f'font-family="{scene.style.sans}">{lead}{escape(name)}</text>'
        )
    return parts


def _mark(scene: Scene) -> list[str]:
    """The skin's brand lockup, bottom-left, if it declares one.

    Marks are outline glyphs -- ``fill="none" stroke="currentColor"`` on the
    root element. Those presentation attributes have to travel with the
    body: dropping them leaves paths with no stroke, and SVG's default
    ``fill: black`` fills a shape that was meant to be drawn as a line.
    ``color`` resolves ``currentColor`` to the skin's *ink*, not its accent:
    a lockup is set in the brand's text colour, and half the AWS mark rides
    on currentColor while the smile carries its own orange -- pointing it at
    the accent rendered the wordmark in console blue beside it.
    """
    source = Path(scene.theme.mark) if scene.theme.mark else None
    if source is None or not source.is_file():
        return []
    text = source.read_text(encoding="utf-8")
    body, box = inner_body(text), view_box(text)
    if body is None or box is None:
        return []

    root = re.search(r"<svg\b([^>]*)>", text)
    carried = []
    for attr in ("fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin"):
        found = re.search(rf'\b{attr}="([^"]*)"', root.group(1)) if root else None
        if found:
            carried.append(f'{attr}="{found.group(1)}"')

    for old_id in sorted(set(re.findall(r'id="([^"]+)"', body)), key=len, reverse=True):
        fresh = f"mark-{old_id}"
        body = (
            body.replace(f'id="{old_id}"', f'id="{fresh}"')
            .replace(f"url(#{old_id})", f"url(#{fresh})")
            .replace(f'href="#{old_id}"', f'href="#{fresh}"')
        )

    numbers = [float(v) for v in box.split()]
    ratio = (numbers[3] / numbers[2]) if len(numbers) == 4 and numbers[2] else 1.0
    height = scene.style.mark_height
    width = int(round(height / ratio)) if ratio else height
    x = scene.style.canvas.margin_x
    if (scene.legend or scene.tones) and scene.style.mark_legend_gap:
        # With a legend, the lockup sits in the clear gutter above the divider.
        legend_y = scene.height - scene.style.canvas.legend_offset
        y = legend_y - height - scene.style.mark_legend_gap
    elif scene.style.canvas.fit:
        # Fit framing reserved a band for the mark below the drawing (see
        # ``place``): the mark sits at the top of that band.
        y = scene.height - height - scene.style.canvas.fit_margin
    else:
        y = scene.height - height - 30
    return [
        "",
        "        <!-- Brand mark -->",
        f'        <svg data-brand-mark="" x="{x}" y="{y}" width="{width}" height="{height}" '
        f'viewBox="{box}" color="{scene.theme["ink"]}" '
        f'{" ".join(carried)} aria-hidden="true">{body}</svg>',
    ]


def cluster_label_rect(cl, style) -> Rect:
    """The box a zone's title occupies, which a connector must not cross.

    A line through a frame's interior is ordinary -- something outside has to
    reach something inside. A line through the frame's *name* destroys the
    one piece of text that says what the frame is, so the title is an
    obstacle even though the frame itself is not.

    One formula in both renderers: ``ClusterStyle.title_width`` here and
    ``boundaryLabelBox`` in the runtime, on the numbers render-metrics.json
    carries, clamped to the frame's own width. The box runs from one label
    size above the frame's top edge to the bottom of the corner tab, so it
    covers the text however the baseline falls.
    """
    cs = style.cluster
    label = cl.label.upper() if cs.label_case == "upper" else cl.label
    if not label:
        return Rect(cl.x, cl.y, cl.x, cl.y)
    width = min(cs.title_width(label), max(TITLE_MIN, cl.width))
    return Rect(cl.x, cl.y - cs.label_size, cl.x + width, cl.y + cs.tab)


def cluster_badge_rect(cl) -> Rect:
    """The box occupied by border badges; the runtime uses the same union."""
    c = CORNER_BADGE
    boxes: list[Rect] = []
    corner = [badge.label for badge in cl.badges if badge.side == "corner"]
    edge = [badge.label for badge in cl.badges if badge.side == "edge"]
    if corner:
        right = cl.x + cl.width
        reach = corner_row_width(corner)
        boxes.append(
            Rect(
                right - reach,
                cl.y - c["icon"] / 2,
                right + c["icon"] / 2,
                cl.y + c["font"] + c["drop"] + 3,
            )
        )
    if edge:
        width = edge_row_width(edge)
        x = cl.x + (cl.width - width) / 2
        boxes.append(
            Rect(
                x,
                cl.y - EDGE_BADGE["icon"] / 2,
                x + width,
                cl.y + c["font"] + c["drop"] + EDGE_BADGE["bar"] + 3,
            )
        )
    for badge in cl.badges:
        if badge.side in ("corner", "edge"):
            continue
        x, y = badge.anchor(cl)
        half = 9
        boxes.append(Rect(x - half, y - half, x + half, y + half))
    if not boxes:
        return Rect(cl.x, cl.y, cl.x, cl.y)
    return Rect(
        min(box.left for box in boxes),
        min(box.top for box in boxes),
        max(box.right for box in boxes),
        max(box.bottom for box in boxes),
    )


def _artwork(node) -> bytes | None:
    """The bytes of this node's icon, for looking up its ink."""
    if node.icon is None:
        return None
    markup = getattr(node.icon, "markup", None)
    return markup.encode("utf-8") if markup else node.icon.path.read_bytes()


def _ink(node) -> list[float]:
    """This node's icon ink insets as fractions, or zeros."""
    return ink.profile(_artwork(node)) or [0.0, 0.0, 0.0, 0.0]


def _ink_edges(node) -> str:
    """Where this node's ink begins along every line of each side, in the
    table's encoding, or empty when its artwork fills the square."""
    return ink.edges(_artwork(node)) or ""


def _anchor_box(node, scene: Scene) -> tuple[float, float, float, float]:
    """``(x, y, width, height)`` of an icon-only node's ink: the glyph square
    the node drawing places, drawn in to where the artwork's ink starts, so a
    wire touches the mark and not the air around it. The runtime's
    ``anchorBox``, sum for sum: a route that ties with another is decided
    by the last bit of these numbers, so they are added in its order."""
    left, top, glyph = glyph_square(node, scene.style)
    ink_left, ink_right, ink_top, ink_bottom = (value * glyph for value in _ink(node))
    return (
        left + ink_left,
        top + ink_top,
        max(4, glyph - ink_left - ink_right),
        max(4, glyph - ink_top - ink_bottom),
    )


def _glyph_box(node, scene: Scene) -> Rect:
    """The ink box of an icon-only node (``_anchor_box``) as a rect."""
    x, y, width, height = _anchor_box(node, scene)
    return Rect(x, y, x + width, y + height)


def _anchors(node, scene: Scene) -> dict[str, Point]:
    """The four points a link may leave from or arrive at.

    A card offers its box's mid-edges. An icon-only node is a glyph with a
    caption beneath inside a wider invisible box; a wire that met that box
    would start in empty air, so left, right and top sit on the glyph's own
    edges and bottom sits beneath the caption -- every one of them on the
    ink-inset box's centre line, as the runtime's ``portPoint`` places them
    (a glyph whose ink sits off-centre in its square is met where it is
    drawn).
    """
    width, height = node.width or 0, node.height or 0
    if node.icon_only:
        x, y, box_width, box_height = _anchor_box(node, scene)
        return {
            "right": _slide(
                node,
                scene,
                "right",
                _centred(node, scene, "right", Point(x + box_width, y + box_height * 0.5)),
            ),
            "left": _slide(
                node, scene, "left", _centred(node, scene, "left", Point(x, y + box_height * 0.5))
            ),
            "bottom": Point(x + box_width * 0.5, node.y + height),
            "top": _slide(
                node, scene, "top", _centred(node, scene, "top", Point(x + box_width * 0.5, y))
            ),
        }
    return {
        "right": Point(node.x + width, node.y + height * 0.5),
        "left": Point(node.x, node.y + height * 0.5),
        "bottom": Point(node.x + width * 0.5, node.y + height),
        "top": Point(node.x + width * 0.5, node.y),
    }


def _seat(node, scene: Scene, side: str, point: Point) -> Point:
    """Where a link ending at ``point`` on a bare glyph's box touches the
        drawing: pushed straight in along its own line to where the ink begins
    . The box is the ink's outermost extent, so on a round
        or uneven mark a point on it can sit in air; seated, it sits on the mark.
        A card, the caption's underside, and artwork with no measured edges keep
        the point."""
    if not node.icon_only or side == "bottom":
        return point
    code = _ink_edges(node)
    if not code:
        return point
    left, top, glyph = glyph_square(node, scene.style)
    if glyph <= 0:
        return point
    if side in ("left", "right"):
        depth = ink.edge_depth(code, side, (point.y - top) / glyph)
        if depth is None:
            return point
        x = (
            max(point.x, left + depth * glyph)
            if side == "left"
            else min(point.x, left + glyph - depth * glyph)
        )
        return Point(x, point.y)
    depth = ink.edge_depth(code, "top", (point.x - left) / glyph)
    if depth is None:
        return point
    return Point(point.x, max(point.y, top + depth * glyph))


def _set_port(node, side: str) -> float | None:
    """Where the table puts ``side``'s connection point by hand (a person's
    body, not the neck the rule would pick), as a fraction along it."""
    return (ink.ports(_artwork(node)) or {}).get(side) if node.icon_only else None


def _centred(node, scene: Scene, side: str, point: Point) -> Point:
    """A side's one connection point, moved along the side to the middle of
    the stretch the device's drawing reaches, so a link meets the middle of
    a router's body rather than the middle of its body and arcs together;
    or where the table sets it by hand."""
    if not node.icon_only or side == "bottom":
        return point
    code = _ink_edges(node)
    left, top, glyph = glyph_square(node, scene.style)
    along = _set_port(node, side) if glyph > 0 else None
    if along is None:
        along = ink.usable_middle(code, side) if code and glyph > 0 else None
    if along is None:
        return point
    if side in ("left", "right"):
        return Point(point.x, top + along * glyph)
    return Point(left + along * glyph, point.y)


def _slide(node, scene: Scene, side: str, point: Point) -> Point:
    """An anchor that falls on a gap in the mark -- between two people,
    beside a wifi arc -- moved along its side to the nearest line the
    drawing reaches, so there is ink on its line to seat on. A port the
    table sets by hand stays where it was set."""
    if not node.icon_only or side == "bottom" or _set_port(node, side) is not None:
        return point
    code = _ink_edges(node)
    left, top, glyph = glyph_square(node, scene.style)
    if not code or glyph <= 0:
        return point
    if side in ("left", "right"):
        along = (point.y - top) / glyph
        slid = ink.inked_along(code, side, along)
        return point if slid == along else Point(point.x, top + slid * glyph)
    along = (point.x - left) / glyph
    slid = ink.inked_along(code, side, along)
    return point if slid == along else Point(left + slid * glyph, point.y)


def _drawn_corners(routed: Route, source, target, scene: Scene) -> tuple[Point, ...]:
    """The corners a route is drawn through, both ends seated on their
    glyphs' drawings along the sides the route left and arrived at
    (the runtime's ``seatEnds``). Routing ran between points on the glyph
    boxes, so the search is untouched. A plain path is derived again from
    the seated ends -- its middle is the middle between where the wire is
    really drawn (``routedPath``) -- while a searched route keeps its
    corners and only its ends move."""
    corners = list(routed.corners)
    if len(corners) < 2 or routed.sides is None:
        return tuple(corners)
    out_side, in_side = routed.sides
    start = _seat(source, scene, out_side, corners[0])
    end = _seat(target, scene, in_side, corners[-1])
    if routed.plain:
        plain = Router._tidy(_simple_corners(start, end, out_side))
        return plain if len(plain) >= 2 else (start, end)
    corners[0], corners[-1] = start, end
    return tuple(corners)


def _own_boxes(node, scene: Scene) -> list[Rect]:
    """What a node's own wire may not cross: a card's box; for an icon-only
    node the glyph and the caption band beneath it, so the wire is free to
    leave and arrive through the air beside the glyph."""
    if not node.icon_only:
        return [Rect.around(node)]
    glyph = _glyph_box(node, scene)
    bottom = node.y + (node.height or 0)
    boxes = [glyph]
    if glyph.bottom + 4 < bottom - 1:
        boxes.append(Rect(node.x, glyph.bottom + 4, node.x + (node.width or 0), bottom))
    return boxes


#: Ports this close to one line are put on one line (a two-pixel jog reads
#: as a mistake); the runtime reads the same number from render-metrics.json
#: (router.straighten, its ROUTE.straighten).
_ROUTER = metrics.router()
STRAIGHTEN = float(_ROUTER["straighten"])


#: One render's routes, keyed by the link that owns them. Routing a link means
#: twelve A* searches over every other node's box, and each link is routed
#: twice -- once to draw the wire, once to place its caption. On a fifty-node
#: template that second pass alone costs forty seconds, and it can only ever
#: return the answer the first pass already found.
_ROUTE_CACHE: dict[tuple[int, int], Route] = {}


def _route_for(link, scene: Scene) -> Route:
    """The routed corners around the other nodes, or the plain path when
    boxed in; never nothing.

    Memoised for the duration of one render: see _ROUTE_CACHE, which
    render_svg empties before it starts. A scene does not move once it is laid
    out, so the same link routes the same way every time it is asked.
    """
    key = (id(scene), id(link))
    if key not in _ROUTE_CACHE:
        _route_all(scene)
    return _ROUTE_CACHE[key]


def _route_all(scene: Scene) -> None:
    """Every wire's route, then the wires that run along one line drawn
    apart (``routing.spread``; the runtime's ``spreadLanes``), into the
    cache. A wire spreading moved keeps the corners it was given and only
    has its ends seated, as a searched route does."""
    routes = [_route_uncached(link, scene) for link in scene.links]
    router = scene.style.router
    spread_out = spread(
        [None if route.shaped else route.corners for route in routes],
        [box for node in _cards(scene) for box in _own_boxes(node, scene)]
        + [
            rect
            for cl in _frames(scene)
            for rect in (cluster_label_rect(cl, scene.style), cluster_badge_rect(cl))
            if rect.right > rect.left
        ],
        _rails(scene),
        gap=float(_ROUTER.get("spread", 8)),
        least=float(_ROUTER.get("spread_min", 4)),
        end=router.clearance,
        reach=router.margin,
        band=router.rail,
    )
    for link, route, corners in zip(scene.links, routes, spread_out, strict=True):
        if corners is not None and corners != route.corners:
            route = Route(corners, sides=route.sides)
        _ROUTE_CACHE[(id(scene), id(link))] = route


SIDES = ("right", "left", "bottom", "top")


def _inferred_sides(source, target) -> tuple[str, str]:
    """The sides a wire leaves and arrives at, read from where the nodes
    stand: facing sides along the longer axis between their centres. What
    the editor infers for a wire whose ports are on auto (inferredSides)."""
    dx = target.cx - source.cx
    dy = target.cy - source.cy
    if abs(dx) >= abs(dy):
        return ("right", "left") if dx >= 0 else ("left", "right")
    return ("bottom", "top") if dy >= 0 else ("top", "bottom")


def _snap(value: float) -> float:
    grid = float(_ROUTER.get("grid", 4))
    return math.floor(value / grid + 0.5) * grid


def _simple_corners(start: Point, end: Point, out_side: str) -> list[Point]:
    """The plain path: straight when the ends line up, else one dog-leg
    through the middle, snapped to the grid, as the editor draws it
    (simplePathCorners)."""
    if abs(start.y - end.y) < 0.01 or abs(start.x - end.x) < 0.01:
        return [start, end]
    if out_side in ("left", "right"):
        mid = _snap((start.x + end.x) / 2)
        return [start, Point(mid, start.y), Point(mid, end.y), end]
    mid = _snap((start.y + end.y) / 2)
    return [start, Point(start.x, mid), Point(end.x, mid), end]


def _stub_point(point: Point, side: str, boxes, router) -> Point:
    """One stub straight out of the side, or one clearance when a neighbour
    sits that close, so the search starts outside every box."""
    full = outward(point, side, router.stub)
    # Inside by more than a hundredth of a pixel, as the runtime's outward asks.
    if any(
        box.left + 0.01 < full.x < box.right - 0.01 and box.top + 0.01 < full.y < box.bottom - 0.01
        for box in boxes
    ):
        return outward(point, side, router.clearance)
    return full


def _strip(anchor: Point, stub: Point) -> Rect:
    """The wall between an anchor and its stub: the search reaches the stub
    only from outside, so the spliced stub never folds back under a head."""
    short = stub.toward(anchor, 1.0)
    return Rect(
        min(anchor.x, short.x) - 0.25,
        min(anchor.y, short.y) - 0.25,
        max(anchor.x, short.x) + 0.25,
        max(anchor.y, short.y) + 0.25,
    )


#: Which way a stub leaves each side, so a bent wire runs out of its
#: side before it turns.
_STUB_OUT = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}


def _bent_corners(
    start: Point,
    end: Point,
    out_side: str,
    in_side: str,
    points: list[Point],
    boxes: list | None = None,
) -> list[Point]:
    """A hand-bent wire, turning at right angles through every pinned corner.

    It runs the stub straight out of its side, elbows through each corner, and
    comes straight into the other side. The editor bends
    the same way (``bentCorners`` in runtime/12-routing.js), so both pictures
    draw one wire.
    """
    stub = float(_ROUTER.get("stub", 20))
    away = _STUB_OUT.get(out_side, _STUB_OUT["right"])
    into = _STUB_OUT.get(in_side, _STUB_OUT["left"])
    chain = [
        start,
        Point(start.x + away[0] * stub, start.y + away[1] * stub),
        *points,
        Point(end.x + into[0] * stub, end.y + into[1] * stub),
        end,
    ]
    corners = [chain[0]]
    horizontal = out_side in ("left", "right")
    for point in chain[1:]:
        previous = corners[-1]
        moves_x = abs(point.x - previous.x) > 0.5
        moves_y = abs(point.y - previous.y) > 0.5
        if moves_x and moves_y:
            # Two ways to turn a corner. Take the one that keeps the wire off
            # whatever stands between; failing that, the one that turns first,
            # so the wire never doubles back along the line it came in on.
            turning, carrying = Point(previous.x, point.y), Point(point.x, previous.y)
            first, second = (turning, carrying) if horizontal else (carrying, turning)

            def clear(elbow: Point, previous: Point = previous, point: Point = point) -> bool:
                return not any(
                    box.blocks(previous, elbow) or box.blocks(elbow, point) for box in (boxes or [])
                )

            corners.append(first if clear(first) or not clear(second) else second)
        elif moves_x or moves_y:
            horizontal = moves_x
        corners.append(point)
    return corners


def _parallel_lane(link, scene: Scene) -> float:
    """How far off the centre line this wire runs, when it is not the only one.

    Wires that join the same two components share both anchors -- a side has
    one connection point -- so they would draw one on top of
    another. Each takes a lane of its own. The editor holds them apart the
    same way (parallelLane in runtime/12-routing.js).
    """

    def pair(item) -> tuple[int, ...]:
        return tuple(sorted((id(item.source), id(item.target))))

    siblings = [item for item in scene.links if pair(item) == pair(link)]
    if len(siblings) < 2:
        return 0.0
    # By identity: two wires with the same ends, kind and label are equal as
    # values, and `index` would hand them both the same lane -- which is the
    # overlap the lanes are here to undo.
    index = next(at for at, item in enumerate(siblings) if item is link)
    return (index - (len(siblings) - 1) / 2) * float(_ROUTER.get("lane", 16))


def _lane_corner(start: Point, end: Point, offset: float) -> list[Point]:
    if not offset:
        return []
    middle = Point((start.x + end.x) / 2, (start.y + end.y) / 2)
    if abs(end.x - start.x) >= abs(end.y - start.y):
        return [Point(middle.x, middle.y + offset)]
    return [Point(middle.x + offset, middle.y)]


def _rails(scene: Scene) -> list[Rail]:
    """Every drawn frame's four borders, in document order: top, bottom,
    left, right (the runtime's ``frameRails``)."""
    return [rail for cl in _frames(scene) for rail in _rails_of(cl)]


def _holds(cl: Cluster, node: Node) -> bool:
    """Whether a frame's box holds a card's, to half a pixel."""
    return (
        node.x >= cl.x - 0.5
        and node.y >= cl.y - 0.5
        and node.x + (node.width or 0) <= cl.x + cl.width + 0.5
        and node.y + (node.height or 0) <= cl.y + cl.height + 0.5
    )


def _fences(scene: Scene, source: Node, target: Node) -> list[Rect]:
    """Every drawn frame that holds neither end of a wire, in document order
    (the runtime's ``fenceBoxes``): a wire crosses one's border only when the
    way around costs more (``Router.cross_cost``)."""
    return [
        Rect(float(cl.x), float(cl.y), float(cl.x + cl.width), float(cl.y + cl.height))
        for cl in _frames(scene)
        if not _holds(cl, source) and not _holds(cl, target)
    ]


def _rails_of(cl: Cluster) -> list[Rail]:
    left, top = float(cl.x), float(cl.y)
    right, bottom = left + cl.width, top + cl.height
    return [
        ("h", top, left, right),
        ("h", bottom, left, right),
        ("v", left, top, bottom),
        ("v", right, top, bottom),
    ]


def _box_rails(boxes: list[Rect]) -> list[Rail]:
    """Each box's four edges as rails: top, bottom, left, right."""
    return [
        rail
        for box in boxes
        for rail in (
            ("h", box.top, box.left, box.right),
            ("h", box.bottom, box.left, box.right),
            ("v", box.left, box.top, box.bottom),
            ("v", box.right, box.top, box.bottom),
        )
    ]


def _plain_hits(
    route: Route,
    boxes: list[Rect],
    rails: list[Rail],
    router: Router,
    link,
    scene: Scene,
    fences: tuple[Rect, ...] | list[Rect] = (),
) -> bool:
    """Whether the plain path must be searched instead: it enters a box, one
    of its segments runs ``rail_run`` along a frame's border or crosses a
    frame that holds neither end -- as routed or as drawn from the seated
    ends, whose middle may sit a few pixels off -- or it leaves or arrives
    along a side instead of straight out of it, a dog-leg whose middle falls
    on an anchor's own line."""
    run = float(_ROUTER.get("rail_run", 24))
    drawn = _drawn_corners(route, link.source, link.target, scene)
    if any(
        rail_run(rails, router.rail, a, b) >= run or fence_crossings(fences, a, b)
        for a, b in zip(drawn, drawn[1:], strict=False)
    ):
        return True
    pairs = list(zip(route.corners, route.corners[1:], strict=False))
    if route.sides and pairs:
        (a, b), (c, d) = pairs[0], pairs[-1]
        out, into = route.sides
        if (abs(a.y - b.y) < 0.5) != (out in ("left", "right")) or (abs(c.y - d.y) < 0.5) != (
            into in ("left", "right")
        ):
            return True
    return any(box.blocks(a, b) for a, b in pairs for box in boxes) or any(
        rail_run(rails, router.rail, a, b) >= run or fence_crossings(fences, a, b) for a, b in pairs
    )


def _route_uncached(link, scene: Scene) -> Route:
    """The corners a wire turns at, with the sides it leaves and arrives on.

    One policy, shared with the editor runtime (connectorPath), so both
    pictures draw the same wire:

    0. Corners the author pinned by hand are the route: the wire runs from
       its anchor through every waypoint in order to the other anchor, and
       nothing is searched.
    1. The sides come from where the nodes stand (facing sides along the
       longer axis), and facing ports within a few pixels of one line are
       put on one line.
    2. The plain path -- straight, or one dog-leg through the snapped
       middle -- is kept when it hits nothing. Most wires end here, and no
       search is paid for.
    3. Otherwise the search runs between a stub outside either anchor, over
       the nearest ``max_obstacles`` boxes first and all of them if that
       fails, so the wire leaves its side straight out and arrives straight
       in (rule 8).
    4. Boxed in on the facing sides, the other sides are tried in the order
       right, left, bottom, top, never a side against itself, and the first
       pair that routes clear wins. An end whose side the author pinned
       (``source_side``/``target_side``) keeps it; only the other end moves.
    5. Boxed in on every pair, the plain path on the facing sides is drawn
       anyway: a link is never silently dropped.

    The corners returned are the anchors on the glyph boxes; the ends are
    seated on the drawing when the path is drawn (``_drawn_corners``), and
    a caption is placed along these unseated corners, as the runtime's
    ``routeCorners`` are.
    """
    router = scene.style.router
    source, target = link.source, link.target
    from_sides, to_sides = _anchors(source, scene), _anchors(target, scene)
    out_side, in_side = _inferred_sides(source, target)
    # A side the author pinned stands, as the editor's sourcePort/targetPort do.
    out_side = link.source_side or out_side
    in_side = link.target_side or in_side
    # Other cards keep their clearance; a frame's title is an obstacle too
    # (cluster_label_rect); the wire's own two cards are hard at their true
    # size, so a wire never runs back through the card it leaves or reaches.
    # In the editor's order -- cards, then frame titles, each in document
    # order -- because the nearest ``max_obstacles`` are taken in that order
    # when two stand equally near.
    others = [
        Rect.around(node).inflate(router.clearance)
        for node in _cards(scene)
        if node is not source and node is not target
    ]
    # each frame's title, then its corner badges, as the editor lists them
    labels = [
        rect.inflate(1.0)
        for cl in _frames(scene)
        for rect in (cluster_label_rect(cl, scene.style), cluster_badge_rect(cl))
        if rect.right > rect.left
    ]
    own = [*_own_boxes(source, scene), *_own_boxes(target, scene)]
    boxes = [*others, *labels, *own]
    rails = _rails(scene)
    # the search also pays to run along the wire's own cards, which it may
    # touch but should not graze: a wire along its card's edge reads as the
    # card's outline, and leaves its caption no room (the runtime's own rails)
    searched_rails = [*rails, *_box_rails(own)]
    # and to cross a frame that holds neither of its ends
    fences = _fences(scene, source, target)
    start, end = from_sides[out_side], to_sides[in_side]
    if {out_side, in_side} <= {"top", "bottom"} and abs(start.x - end.x) <= STRAIGHTEN:
        end = Point(start.x, end.y)
    elif {out_side, in_side} <= {"left", "right"} and abs(start.y - end.y) <= STRAIGHTEN:
        end = Point(end.x, start.y)

    # Corners pinned by hand, on a drawing that stands where the editor left
    # it: the wire turns at right angles through each of them, around the
    # other cards and the frame titles, as the editor draws it (bentCorners).
    # On a layout placed afresh they describe a drawing that is gone, so the
    # wire is routed like any other rather than dragged to stale points.
    if scene.saved_layout and link.waypoints:
        pinned = [Point(float(x), float(y)) for x, y in link.waypoints]
        return Route(
            Router._tidy(_bent_corners(start, end, out_side, in_side, pinned, [*others, *labels])),
            sides=(out_side, in_side),
            shaped=True,
        )

    # A wire that shares both its ends with another takes a lane of its own,
    # or the two draw one on top of the other. A wire nobody has shaped: a
    # pinned bend is the author's and is honoured above.
    lane = _parallel_lane(link, scene)
    if lane:
        bend = _lane_corner(start, end, lane)
        if bend:
            laned = Route(
                Router._tidy(_bent_corners(start, end, out_side, in_side, bend, boxes)),
                sides=(out_side, in_side),
                shaped=True,
            )
            # The lane is only a preference, as in the editor (connectorPath):
            # drawn through a card or along a frame's border, the wire is
            # searched like any other below, and spread with the rest.
            run = float(_ROUTER.get("rail_run", 24))
            drawn = Router._tidy(_drawn_corners(laned, source, target, scene))
            if not any(
                any(box.blocks(a, b) for box in boxes)
                or rail_run(rails, router.rail, a, b) >= run
                or fence_crossings(fences, a, b)
                for a, b in zip(drawn, drawn[1:], strict=False)
            ):
                return laned

    # The plain path, on the anchors as they stand; whether it hits anything
    # is judged here, and it is drawn again from the seated ends.
    simple = Route(
        Router._tidy(_simple_corners(start, end, out_side)), sides=(out_side, in_side), plain=True
    )
    if not _plain_hits(simple, boxes, rails, router, link, scene, fences):
        return simple

    cap = int(_ROUTER.get("max_obstacles", 48))

    def route_sides(anchor_out: Point, out: str, anchor_in: Point, into: str) -> Route | None:
        a, b = (
            _stub_point(anchor_out, out, boxes, router),
            _stub_point(anchor_in, into, boxes, router),
        )
        walls = [_strip(anchor_out, a), _strip(anchor_in, b)]
        near = nearest(boxes, a, b, cap)
        found = router.route_prepared(
            a, b, boxes if near is boxes else [*near, *own], walls, searched_rails, fences
        )
        if found is None and near is not boxes:
            found = router.route_prepared(a, b, boxes, walls, searched_rails, fences)
        if found is None:
            return None
        return Route(Router._tidy([anchor_out, *found.corners, anchor_in]), sides=(out, into))

    routed = route_sides(start, out_side, end, in_side)
    if routed is not None:
        return routed
    # A pinned end keeps its side; only an end left on auto tries the
    # others, as the editor's router does.
    for out in SIDES if link.source_side is None else (out_side,):
        for into in SIDES if link.target_side is None else (in_side,):
            if (out == out_side and into == in_side) or out == into:
                continue
            # The facing anchor keeps its straightened position when it is
            # tried again against another side (the runtime does the same).
            anchor_in = end if into == in_side else to_sides[into]
            found = route_sides(from_sides[out], out, anchor_in, into)
            if found is not None:
                # The editor settles every route before it draws one
                # (renderGraph), and the settled wire is routed again from the
                # sides it moved to: drawn plain there when the plain path is
                # clear, as if it had started on those sides.
                settled = Route(
                    Router._tidy(_simple_corners(from_sides[out], anchor_in, out)),
                    sides=(out, into),
                    plain=True,
                )
                if not _plain_hits(settled, boxes, rails, router, link, scene, fences):
                    return settled
                return found
    # Boxed in on every pair: the plain path on the facing sides, seated
    # like any other, rather than no wire at all.
    return simple


def _heads(link, scene: Scene) -> tuple[bool, bool]:
    """Which ends of a wire wear a head: none for a headless kind, else
    what the connection's direction says."""
    return link.heads if scene.style.link(link.kind).arrow else (False, False)


def _path_for(link, scene: Scene) -> str:
    """The wire as drawn: routed around the other nodes (or plain when
    boxed in), both ends seated, and every headed end kept on the spec's
    straight shaft and stopped short of its tip (rule 9)."""
    routed = _route_for(link, scene)
    corners = _drawn_corners(routed, link.source, link.target, scene)
    heads = _heads(link, scene)
    return Route(corners).to_path(
        metrics.corner_radius(link.corners),
        shaft=arrowheads.shaft(),
        heads=heads,
        tip_clear=arrowheads.tip_clear(),
    )


def _arrow_id(paint: str, head: str | None = None) -> str:
    """A stable marker id for a paint and a head. The editor's suffixes
    (``-open``, ``-circle``, ``-diamond``) name every head but the default,
    so the checker reads which head a wire wears."""
    base = "arrow-" + "".join(ch for ch in paint.lower() if ch.isalnum())
    name = arrowheads.head(head).name
    return base if name == arrowheads.default_name() else f"{base}-{name}"


def _arrow_markers(scene: Scene) -> list[tuple[str, str | None]]:
    """Every distinct (paint, head) pair the scene's wires need, in a stable order."""
    seen: list[tuple[str, str | None]] = []
    for link in scene.links:
        ls = scene.style.link(link.kind)
        if not any(_heads(link, scene)):
            continue
        pair = (link.stroke or ls.color or scene.theme[ls.role], arrowheads.head(link.arrow).name)
        if pair not in seen:
            seen.append(pair)
    return seen


def _links(scene: Scene) -> list[str]:
    T, style = scene.theme, scene.style
    out: list[str] = []
    paths = [_path_for(link, scene) for link in scene.links]
    masks: dict[int, list[tuple[float, float, float]]] = {}
    counts: dict[int, int] = {}
    if scene.crossings == "bridge":
        obstacles = [box for node in _cards(scene) for box in _own_boxes(node, scene)]
        obstacles += [
            box
            for cl in _frames(scene)
            for box in (cluster_label_rect(cl, scene.style), cluster_badge_rect(cl))
            if box
        ]
        for link, spot, width, lead in _placed_captions(scene):
            left = _chip_left(spot, width, lead)
            tall = metrics.step()["chip"] if link.step is not None else captions.CAPTION_TALL
            top = spot.y - tall / 2 - 4
            obstacles.append(Rect(left, top, left + width + lead, top + tall))
        paths, masks, counts = crossing_plan(
            [
                (path, link.width or style.link(link.kind).width)
                for path, link in zip(paths, scene.links, strict=True)
            ],
            obstacles,
        )
    for index, link in enumerate(scene.links):
        ls = style.link(link.kind)
        dash = f' stroke-dasharray="{ls.dash}"' if ls.dash else ""
        # the wire's own editor style wins over its kind's colour and width,
        # so the static picture draws what the page draws
        paint = link.stroke or ls.color or T[ls.role]
        width = link.width or ls.width
        # One marker serves both ends: it is drawn ``auto-start-reverse``,
        # so at the start it points back out of the wire.
        start_head, end_head = _heads(link, scene)
        marker_ref = f"url(#{_arrow_id(paint, link.arrow)})"
        marker = (f' marker-start="{marker_ref}"' if start_head else "") + (
            f' marker-end="{marker_ref}"' if end_head else ""
        )
        mask = ""
        if index in masks:
            mask_id = f"infragram-static-crossing-{index}"
            circles = "".join(
                f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="#000"/>' for x, y, r in masks[index]
            )
            out.append(
                f'<mask id="{mask_id}" maskUnits="userSpaceOnUse" x="0" y="0" '
                f'width="{scene.width}" height="{scene.height}" style="mask-type:luminance">'
                f'<rect width="{scene.width}" height="{scene.height}" fill="#fff"/>'
                f"{circles}</mask>"
            )
            mask = f' mask="url(#{mask_id})"'
        count = f' data-crossing-count="{counts[index]}"' if index in counts else ""
        out.append(
            f'        <path d="{paths[index]}" fill="none" stroke="{paint}" '
            f'stroke-width="{width:g}"{dash}{marker}{mask}{count}/>'
        )
    out += _captions(scene)
    return out


#: One render's placed captions, keyed by the scene, for the same reason
#: and lifetime as _ROUTE_CACHE: the canvas grows to hold them before the
#: picture is written, and the link layer draws them afterwards.
_CAPTION_CACHE: dict[int, list] = {}


def _placed_captions(scene: Scene) -> list[tuple[Link, captions.Spot, float, float]]:
    """Every labelled wire's caption where the editor puts it
    (builders/captions.py), as ``(link, spot, text chip width, step lead)``. A card blocks its
    box and a bare glyph what it draws, in document order as the editor lists
    them, then the frame titles; each caption blocks the ones after it."""
    key = id(scene)
    if key not in _CAPTION_CACHE:
        _CAPTION_CACHE[key] = _place_captions(scene)
    return _CAPTION_CACHE[key]


def _place_captions(scene: Scene) -> list[tuple[Link, captions.Spot, float, float]]:
    blockers = [
        captions.Box(box.left, box.top, box.right - box.left, box.bottom - box.top)
        for node in _cards(scene)
        for box in (_own_boxes(node, scene) if node.icon_only else [Rect.around(node)])
    ]
    for cl in _frames(scene):
        for title in (cluster_label_rect(cl, scene.style), cluster_badge_rect(cl)):
            if title.right > title.left:
                blockers.append(
                    captions.Box(
                        title.left, title.top, title.right - title.left, title.bottom - title.top
                    )
                )

    def along(link) -> tuple[Route, str, list]:
        routed = _route_for(link, scene)
        out_side = (routed.sides or _inferred_sides(link.source, link.target))[0]
        # a plain path is drawn from its seated ends, its middle a few pixels
        # off the one routed between the anchors: the caption names the wire
        # as drawn (the runtime's captionCorners)
        corners = list(
            _drawn_corners(routed, link.source, link.target, scene)
            if routed.plain
            else routed.corners
        )
        if (scene.saved_layout and link.waypoints) or _parallel_lane(link, scene):
            # The editor keeps no route for a wire bent by hand or laned
            # beside its twin, and places the caption along the plain path
            # between the wire's ends.
            corners = captions.tidy(
                captions.simple_corners(routed.corners[0], routed.corners[-1], out_side, GRID)
            )
        return routed, out_side, corners

    # every frame's borders as lines, top, bottom, left, right
    rails = [
        line
        for cl in _frames(scene)
        for line in (
            captions.Box(cl.x, cl.y, cl.width, 0),
            captions.Box(cl.x, cl.y + cl.height, cl.width, 0),
            captions.Box(cl.x, cl.y, 0, cl.height),
            captions.Box(cl.x + cl.width, cl.y, 0, cl.height),
        )
    ]
    # every wire, labelled or not, so a numbered chip keeps off all of them
    placer = captions.Placer(
        blockers, grid=GRID, wires=[along(link)[2] for link in scene.links], rails=rails
    )
    placed = []
    for link in scene.links:
        if not link.label:
            continue
        routed, out_side, corners = along(link)
        start, end = routed.corners[0], routed.corners[-1]
        lead = metrics.step()["lead"] if link.step is not None else 0
        tall = metrics.step()["chip"] if link.step is not None else captions.CAPTION_TALL
        spot = placer.place(
            link.label,
            start,
            end,
            out_side,
            corners,
            link.kind,
            _box_of(link.source),
            _box_of(link.target),
            manual=link.label_offset,
            lead=lead,
            tall=tall,
        )
        placed.append((link, spot, captions.caption_width(link.label), lead))
    return placed


def _chip_left(spot: captions.Spot, width: float, lead: float = 0) -> float:
    """Where a caption's chip starts: centred above a level run, a step's
    circle further left; from just before the anchor beside a vertical one,
    the circle and then the text right of it, off the wire
    (edgeLabelMarkup's maskX)."""
    return spot.x - 4 if spot.side == "vertical" else spot.x - width / 2 - lead


def _hold_captions(scene: Scene) -> None:
    """Grow a canvas sized to its content until every caption's chip stands
    inside it, with the margin a card keeps (``size_to_content``). The
    editor's canvas is larger than its content and its export is cropped to
    what is drawn, captions included; a caption set beside the rightmost
    wire would otherwise hang off the static picture. A fixed size keeps its
    promise, and the checker names a caption it cannot hold."""
    canvas = scene.style.canvas
    if not canvas.fit:
        return
    for link, spot, width, lead in _placed_captions(scene):
        below = (metrics.step()["chip"] / 2 - 4) if link.step is not None else 3
        scene.width = max(
            scene.width, math.ceil(_chip_left(spot, width, lead) + width + lead + canvas.fit_margin)
        )
        scene.height = max(scene.height, math.ceil(spot.y + below + canvas.fit_margin))


def _step_badge(
    mark,
    number: int,
    cx: float,
    cy: float,
    radius: float,
    size: float,
    font: str,
    tag: bool = False,
) -> list[str]:
    """A step's badge: a circle or a square in its flow's colour, its number
    or letter in bold white. ``tag`` marks the one in a caption's chip so the
    checker and the parity test find it and read its caption, not its mark."""
    step_attr = f'data-edge-step="{number}" ' if tag else ""
    if mark.shape == "square":
        shape = (
            f'        <rect {step_attr}data-cx="{cx:g}" data-cy="{cy:g}" x="{cx - radius:g}" '
            f'y="{cy - radius:g}" width="{2 * radius:g}" height="{2 * radius:g}" rx="3" fill="{mark.color}"/>'
        )
    else:
        shape = f'        <circle {step_attr}cx="{cx:g}" cy="{cy:g}" r="{radius:g}" fill="{mark.color}"/>'
    number_attr = f'data-edge-step-number="{number}" ' if tag else ""
    return [
        shape,
        f'        <text {number_attr}x="{cx:g}" y="{cy + size * 0.36:g}" fill="#ffffff" font-size="{size:g}" '
        f'font-weight="700" font-family="{font}" text-anchor="middle">{mark.mark(number)}</text>',
    ]


def _step_rows(scene: Scene) -> list[tuple[str | None, list[tuple[int, str]]]]:
    """The step list's sections: the main flow's steps, then the second
    flow's under its name."""
    rows: list[tuple[str | None, list[tuple[int, str]]]] = []
    if scene.steps:
        rows.append((None, scene.steps))
    if scene.second_flow:
        rows.append(scene.second_flow)
    return rows


def _step_list_box(scene: Scene) -> tuple[float, float, float, float]:
    """Where the step list's panel stands: ``list_gap`` right of everything
    drawn, captions included, level with the top of the drawing; and how big
    it is. A second flow adds its heading, a row tall."""
    step = metrics.step()
    rights: list[float] = [n.x + (n.width or 0) for n in scene.root.walk()]
    rights += [cl.x + cl.width for cl in _frames(scene)]
    rights += [
        _chip_left(spot, width, lead) + width + lead
        for _l, spot, width, lead in _placed_captions(scene)
    ]
    tops = [n.y for n in scene.root.walk()] + [cl.y for cl in _frames(scene)]
    x = max(rights, default=scene.style.canvas.margin_x) + step["list_gap"]
    top = min(tops, default=scene.style.canvas.content_top)
    sections = _step_rows(scene)
    lines = [text for _name, rows in sections for _n, text in rows]
    headings = [name for name, _rows in sections if name]
    longest = max([len(text) for text in lines], default=0)
    width = (
        2 * step["list_pad"]
        + 2 * step["list_radius"]
        + 10
        + math.ceil(longest * step["list_size"] * 0.55)
    )
    width = max(
        width,
        2 * step["list_pad"] + max((math.ceil(len(h) * 12 * 0.6) for h in headings), default=0),
    )
    height = (
        2 * step["list_pad"]
        + 22
        + (len(lines) + len(headings)) * step["list_row"]
        - (step["list_row"] - 2 * step["list_radius"])
    )
    return x, top, width, height


def _hold_steps(scene: Scene) -> None:
    """Grow the canvas to hold the step list beside the drawing."""
    if not _step_rows(scene):
        return
    canvas = scene.style.canvas
    margin = canvas.fit_margin if canvas.fit else canvas.margin_x
    x, top, width, height = _step_list_box(scene)
    scene.width = max(scene.width, math.ceil(x + width + margin))
    scene.height = max(scene.height, math.ceil(top + height + margin))


def _step_list(scene: Scene) -> list[str]:
    """The step list: a bordered panel, a line a step in order, each behind
    its flow's badge; a second flow's steps follow under its name, as the
    clouds' own drawings key their second flow. The editor keeps it right of
    whatever it draws (placeStepList)."""
    T, style = scene.theme, scene.style
    step = metrics.step()
    x, top, width, height = _step_list_box(scene)
    pad, radius = step["list_pad"], step["list_radius"]
    out = [
        f'        <g data-step-list="" data-drawn-x="{x:g}">',
        f'        <rect x="{x:g}" y="{top:g}" width="{width:g}" height="{height:g}" rx="8" '
        f'fill="{T["paper"]}" stroke="{rgba(T["ink"], 0.16)}" stroke-width="1"/>',
        f'        <text x="{x + pad:g}" y="{top + pad + 10:g}" fill="{T["ink"]}" font-size="12" '
        f'font-weight="700" font-family="{style.sans}">Steps</text>',
    ]
    row = 0
    for name, rows in _step_rows(scene):
        mark = T.step_mark(second=name is not None)
        if name:
            y = top + pad + 22 + row * step["list_row"] + radius + 12 * 0.36
            out.append(
                f'        <text x="{x + pad:g}" y="{y:g}" fill="{T["ink"]}" font-size="12" '
                f'font-weight="700" font-family="{style.sans}">{escape(name)}</text>'
            )
            row += 1
        # a row names its step, so a click on it in the editor shows that
        # step's wires as a click on the wire would (19-canvas-pointer)
        flow = f' data-step-flow="{escape(name)}"' if name else ""
        for number, text in rows:
            cy = top + pad + 22 + radius + row * step["list_row"]
            cx = x + pad + radius
            out.append(f'        <g data-step-row="{number}"{flow}>')
            out += _step_badge(mark, number, cx, cy, radius, step["number_size"], style.sans)
            out.append(
                f'        <text x="{cx + radius + 10:g}" y="{cy + step["list_size"] * 0.36:g}" fill="{T["ink"]}" '
                f'font-size="{step["list_size"]:g}" font-family="{style.sans}">{escape(text)}</text>'
            )
            out.append("        </g>")
            row += 1
    out.append("        </g>")
    return out


def _captions(scene: Scene) -> list[str]:
    """The captions' markup: the editor's chip and type, where it puts them."""
    chip, ink, edge = captions.chip(scene.theme)
    size = captions.CAPTION_SIZE
    out: list[str] = []
    step = metrics.step()
    for link, spot, width, lead in _placed_captions(scene):
        left = _chip_left(spot, width, lead)
        # a numbered caption's chip holds its circle: taller, the same middle
        tall = step["chip"] if link.step is not None else captions.CAPTION_TALL
        top = spot.y - tall / 2 - 4
        out += [
            f'        <rect x="{left:g}" y="{top:g}" width="{width + lead:g}" '
            f'height="{tall:g}" rx="3" fill="{chip}" stroke="{edge}" stroke-width="1"/>',
            f'        <text x="{spot.x + (lead if spot.side == "vertical" else 0):g}" y="{spot.y:g}" '
            f'fill="{ink}" font-size="{size:g}" '
            f'font-weight="{captions.CAPTION_WEIGHT}" font-family="{scene.style.sans}" '
            f'text-anchor="{spot.anchor}">{escape(link.label)}</text>',
        ]
        if link.step is not None:
            # the badge in the chip's lead, left of the text, marked its
            # flow's way (the theme's step_color, or its step_second)
            cx, cy = left + step["inset"] + step["radius"], spot.y - 4
            mark = scene.theme.step_mark(second=link.step_flow is not None)
            out += _step_badge(
                mark,
                link.step,
                cx,
                cy,
                step["radius"],
                step["number_size"],
                scene.style.sans,
                tag=True,
            )
    return out


def _cards(scene: Scene) -> list[Node]:
    """The cards and glyphs in document order, the order the editor lists
    them in: the layout reorders siblings, the document does not."""
    last = len(scene.order)
    return sorted(scene.root.walk(), key=lambda node: scene.order.get(node.ref, last))


def _frames(scene: Scene) -> list[Cluster]:
    """The drawn frames in document order; the root is the canvas, not a frame."""
    last = len(scene.order)
    return sorted(
        (cl for cl in scene.root.clusters() if cl is not scene.root),
        key=lambda cl: scene.order.get(cl.ref, last),
    )


def _box_of(node: Node) -> captions.Box:
    return captions.Box(node.x, node.y, node.width or 0, node.height or 0)


def _legend(scene: Scene) -> list[str]:
    T, style = scene.theme, scene.style
    y = scene.height - style.canvas.legend_offset
    m = style.canvas.margin_x
    # One group, so an export that crops to what is drawn keeps the whole
    # strip: the divider, the heading and every entry. The attribute carries
    # an empty value: a bare attribute is HTML, not XML, and the standalone
    # SVG of any template with a legend was unparseable as an image.
    out = [
        '        <g data-legend-strip="">',
        f'        <line x1="{m}" y1="{y}" x2="{scene.width - m}" y2="{y}" '
        f'stroke="{rgba(T["ink"], 0.12)}" stroke-width="1"/>',
        f'        <text x="{m}" y="{y + 20}" fill="{T["soft"]}" font-size="7" '
        f'font-family="{style.sans}" letter-spacing="0.14em">LEGEND</text>',
    ]
    x = m
    for kind, text in scene.legend:
        ls = style.link(kind)
        dash = f' stroke-dasharray="{ls.dash}"' if ls.dash else ""
        # The swatch is the paint the wires of that kind are drawn in: their
        # own stroke when every one of them sets the same, else the kind's.
        strokes = {link.stroke for link in scene.links if link.kind == kind}
        paint = (
            next(iter(strokes))
            if len(strokes) == 1 and None not in strokes
            else ls.color or T[ls.role]
        )
        out.append(
            f'        <line x1="{x}" y1="{y + 41}" x2="{x + 28}" y2="{y + 41}" '
            f'stroke="{paint}" stroke-width="{ls.width:g}"{dash}/>'
        )
        out.append(
            f'        <text x="{x + 36}" y="{y + 45}" fill="{T["muted"]}" '
            f'font-size="8.5" font-family="{style.sans}">{escape(text)}</text>'
        )
        x += 36 + len(text) * 7 + 48
    # what each tone a box is filled with means: its fill and outline, then
    # the words (builders/panels.py)
    for name, text in scene.tones:
        swatch = _tone(name, scene)
        if swatch is None:
            continue
        out.append(
            f'        <rect data-legend-tone="{escape(name, quote=True)}" x="{x}" y="{y + 35}" '
            f'width="28" height="12" rx="2" fill="{swatch[0]}" stroke="{swatch[1]}" stroke-width="1"/>'
        )
        out.append(
            f'        <text x="{x + 36}" y="{y + 45}" fill="{T["muted"]}" '
            f'font-size="8.5" font-family="{style.sans}">{escape(text)}</text>'
        )
        x += 36 + len(text) * 7 + 48
    out.append("        </g>")
    return out


def render_svg(scene: Scene) -> str:
    # Routes live only as long as the render that asked for them: the
    # cache is keyed by object identity, which is stable only while the
    # objects are alive.
    _ROUTE_CACHE.clear()
    _CAPTION_CACHE.clear()
    _hold_captions(scene)
    _hold_steps(scene)
    T, style = scene.theme, scene.style
    symbols, icon_ids = _symbols(scene)
    parts = [
        f'      <svg viewBox="0 0 {scene.width} {scene.height}" xmlns="http://www.w3.org/2000/svg" role="img"',
        f'           aria-labelledby="{scene.slug}-title {scene.slug}-desc">',
        f'        <title id="{scene.slug}-title">{escape(scene.title)}</title>',
        f'        <desc id="{scene.slug}-desc">{escape(scene.desc)}</desc>',
        "        <defs>",
    ]
    # An arrowhead that does not match its line reads as a different link.
    # Two fixed markers could not cover three roles, let alone a literal
    # colour, so one is emitted per paint the scene actually uses. The head
    # is the house head from assets/catalog/arrowheads.json, the same one
    # the editor draws.
    for paint, head in _arrow_markers(scene):
        parts.append("          " + arrowheads.marker(_arrow_id(paint, head), head, paint))
    if style.dot_grid and scene.theme.dots:
        parts += [
            '          <pattern id="dots" width="16" height="16" patternUnits="userSpaceOnUse">',
            f'            <circle cx="1" cy="1" r="0.9" fill="{rgba(T["ink"], style.dot_alpha)}"/>',
            "          </pattern>",
        ]
    if symbols:
        parts.append(symbols)
    parts.append("        </defs>")
    parts.append("")
    if style.dot_grid and scene.theme.dots:
        parts.append(
            f'        <rect width="{scene.width}" height="{scene.height}" fill="url(#dots)"/>'
        )

    parts += [
        "",
        "        <!-- Clusters: drawn before arrows and nodes -->",
        '        <g data-static-cluster-layer="true">',
    ]
    parts += [
        _cluster(cl, scene, icon_ids)
        for cl in scene.root.clusters()
        if cl is not scene.root and cl.label
    ]
    parts.append("        </g>")
    parts += [
        "",
        "        <!-- Links -->",
        '        <g data-static-link-layer="true">',
        *_links(scene),
        "        </g>",
        "",
        "        <!-- Nodes -->",
        '        <g data-static-node-layer="true">',
    ]
    parts += [_node(n, scene, icon_ids) for n in scene.root.walk()]
    parts.append("        </g>")
    parts.append('        <g data-static-meta-layer="true">')
    if scene.legend or scene.tones:
        parts += ["", "        <!-- Legend strip -->", *_legend(scene)]
    if _step_rows(scene):
        parts += ["", "        <!-- Step list -->", *_step_list(scene)]
    parts += _mark(scene)
    parts.append("        </g>")
    parts.append("      </svg>")
    return "\n".join(parts)


def render(scene: Scene) -> str:
    """A complete, self-contained HTML document for a placed scene."""
    T, style = scene.theme, scene.style
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(scene.title)}</title>
  {font_style_element()}
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --paper: {T["paper"]};
      --paper-2: {T["paper_2"]};
      --ink: {T["ink"]};
      --muted: {T["muted"]};
      --soft: {T["soft"]};
      --accent: {T["accent"]};
      --link: {T["link"]};
    }}
    body {{
      min-height: 100vh;
      padding: 48px 32px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--paper);
      color: var(--ink);
      font-family: {style.sans}, system-ui, sans-serif;
    }}
    .frame {{ width: 100%; max-width: 1280px; }}
    .eyebrow {{
      margin-bottom: 8px;
      color: var(--muted);
      font-family: {style.mono}, ui-monospace, monospace;
      font-size: 12px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
    }}
    h1 {{
      margin-bottom: 24px;
      color: var(--ink);
      font-family: {T.type.font or style.heading};
      font-size: 32px;
      font-weight: {T.type.weight};
      line-height: 1.15;
    }}
    svg {{ width: 100%; min-width: 900px; display: block; }}
  </style>
</head>
<body>
  <div class="frame">
    <p class="eyebrow">{escape(scene.eyebrow)}</p>
    <h1>{escape(scene.heading or scene.title)}</h1>

{render_svg(scene)}
  </div>
</body>
</html>
"""
