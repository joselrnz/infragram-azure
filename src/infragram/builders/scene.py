"""Scene models and placement: what gets drawn, and where.

Everything a diagram needs is data on a model -- including its visual
vocabulary. Link weights, dash patterns, type sizes, padding and the
colour *role* each element takes are fields on :class:`Style`, not literals
buried in the renderer, so a caller can change how a diagram looks without
touching markup.

Placement is deterministic arithmetic. A cluster lays its children along one
axis and sizes itself to their bounding box; the canvas then grows to fit
the result rather than clipping it.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any, Literal

from pydantic import BaseModel, Field, PrivateAttr

from ..models import ProviderIcon
from ..themes import Theme
from . import metrics
from .captions import CAPTION_TALL, caption_width
from .panels import Panel, size as panel_size
from .routing import Router

Flow = Literal["row", "column", "grid"]
#: Colour roles resolved against the active Theme, never raw hex.
Role = Literal["ink", "muted", "soft", "accent", "link", "paper", "paper_2"]


# ---------------------------------------------------------------------------
# Visual vocabulary - data, not literals in the renderer
# ---------------------------------------------------------------------------


class LinkStyle(BaseModel):
    """How one class of link is drawn."""

    width: float = 1.2
    dash: str | None = None
    role: Role = "muted"
    #: A literal hex, for link kinds whose colour *is* the meaning -- a
    #: reader has to tell replication from telemetry at a glance. Wins over
    #: `role`; leave empty to stay on the theme and re-read in every skin.
    color: str = ""
    arrow: bool = True


#: Shared with the editor runtime; see builders/metrics.py.
_ICON = metrics.icon_node()
#: Where a captioned icon node's glyph starts below the node's top; the
#: runtime reads the same number (icon_node.glyph_top), so anchors agree.
GLYPH_TOP = int(_ICON.get("glyph_top", 4))
_CARD = metrics.card()
_DASHES = metrics.link_dashes()
_FRAME = metrics.frame()
_MARK = metrics.mark()
_TEXT = metrics.text()
#: How wide one character is. Three places have to agree on these -- the
#: layout that reserves the room, the editor that draws into it, and the
#: static renderer that draws the same card without a browser -- so they are
#: read from render-metrics.json rather than each carrying its own number.
#: A name is measured per point of its size (0.58 em, 6.96 px at 12); a
#: card's detail line and an icon's are flat pixels at their own sizes.
TITLE_ADVANCE = float(_TEXT["advance"])
DETAIL_ADVANCE = float(_CARD["detail_advance"])
CAPTION_DETAIL_ADVANCE = float(_ICON["detail_advance"])


class NodeStyle(BaseModel):
    height: int = _CARD["height"]
    width: int = _CARD["width"]
    #: How wide a card may grow to fit its own text before the renderer
    #: gives up and truncates. Zero keeps every card exactly `width`.
    max_width: int = _CARD["max_width"]
    radius: int = 6
    #: The card's lines and icon, where the editor draws them
    #: (render-metrics.json ``card``).
    title_size: float = _CARD["title_size"]
    detail_size: float = _CARD["detail_size"]
    icon_size: int = _CARD["icon"]
    icon_inset: int = _CARD["icon_x"]
    text_inset: int = _CARD["text_x"]
    #: An icon node's detail line, larger than a card's.
    icon_detail_size: float = _ICON["detail_size"]
    #: Icon display: the bare mark with its caption beneath, no box. Sized so
    #: a 64 px vendor glyph, a one-line name and a detail line fit and the
    #: node carries the weight of the card beside it; the width still grows
    #: to a long name in ``fit`` sizing, the same as a card does.
    icon_width: int = _ICON["width"]
    icon_height: int = _ICON["height"]
    icon_glyph: int = _ICON["glyph"]
    #: A bare glyph this tall or taller carries a caption beneath it, so its
    #: square sits at the top; shorter, the square is centred. The runtime
    #: reads the same number (icon_node.caption_min_height).
    icon_caption_min_height: int = _ICON["caption_min_height"]
    border: Role = "ink"
    border_alpha: float = 0.30
    fill_alpha: float = 0.03
    focal_alpha: float = 0.08
    #: Category or collection -> theme role, so a *skin* can colour whole
    #: categories without touching any class. Lowest precedence: an ACCENT
    #: on the class, or accent=/brand= at the call site, both win over this.
    accent_roles: dict[str, str] = Field(default_factory=dict)
    accent_alpha: float = 0.85
    accent_fill_alpha: float = 0.06


#: Kinds that draw dashed unless the theme says otherwise: groupings a
#: diagram invents to aid reading, not perimeters one could point at in a
#: portal. A real perimeter -- VPC, subnet, account -- draws solid.
FRAME_DASHED = frozenset(_FRAME["dashed_kinds"])
#: Line weights a kind takes unless the theme declares one: the outermost
#: cloud is drawn heavier than the boundaries inside it.
FRAME_WIDTHS: dict[str, float] = dict(_FRAME["widths"])
#: Frame lines: each frame's own width as drawn (thin), or that times 1.75
#: (medium) or 2.5 (thick). The runtime reads the same numbers.
FRAME_LINES: dict[str, float] = dict(_FRAME["line_scales"])
#: A title's obstacle is at least this wide, and this much wider than its
#: text; the runtime reads the same two numbers (frame.label_min, label_pad).
TITLE_MIN = int(_FRAME["label_min"])
TITLE_PAD = int(_FRAME["label_pad"])


class ClusterStyle(BaseModel):
    #: Vendor drawings are square-cornered; a theme rounds a kind through
    #: ``radii``. Both renderers read this same default.
    radius: int = 0
    #: Dash for a kind that is in neither ``dashes`` nor FRAME_DASHED; None
    #: draws solid.
    dash: str | None = None
    #: Dash pattern per zone kind, so the border says what kind of boundary
    #: this is. A real perimeter -- something you could point at in a portal
    #: -- draws solid; a grouping the diagram invented to aid reading draws
    #: dashed. None means solid. Anything unlisted falls back to `dash`.
    #: Border width per zone kind. AWS draws its outermost cloud heavier
    #: than the boundaries inside it.
    widths: dict[str, float] = Field(default_factory=dict)
    #: Corner radius per zone kind. Vendor drawings are square; the house
    #: look is rounded, so this stays empty unless a skin says otherwise.
    radii: dict[str, int] = Field(default_factory=dict)
    #: A filled square seated in the top-left corner, holding the zone's
    #: glyph. When a kind sets one, the border stays whole and the label
    #: sits inside beside the tab -- which is how AWS avoids masking its
    #: own outline at all.
    tab: int = _FRAME["tab"]
    #: Border colour per zone kind. AWS draws a Region in teal, a VPC in
    #: purple and a public subnet in green -- the hue says what kind
    #: of boundary it is, which a single muted stroke cannot. A value may
    #: name a theme role or be a literal hex; unlisted kinds use
    #: `border_role`. Empty by default, so no existing diagram shifts.
    colors: dict[str, str] = Field(default_factory=dict)
    #: The frame colour for every kind ``colors`` does not name: the vendor's
    #: own colour for its frames. A theme role or a literal hex. Declared by
    #: every shipped theme, so frames never fall to the depth-faded role.
    color: str = ""
    #: Fill colour per zone kind. Values may name a theme role or be a
    #: literal hex; ``"none"`` leaves the zone transparent. Empty or
    #: unlisted values retain the depth-based ink fill for compatibility.
    #: This map is independent of ``colors``: a border hue never silently
    #: becomes a fill hue.
    fills: dict[str, str] = Field(default_factory=dict)
    #: Qualified artwork reference per zone kind, such as ``aws:region`` or
    #: ``logos:aws#mono``. This is an explicit skin opt-in; an empty map keeps
    #: a bare Group kind from accidentally summoning similarly named artwork.
    icons: dict[str, str] = Field(default_factory=dict)
    #: Zone kinds a provider cannot render without losing meaning. AWS, for
    #: example, rejects generic ``subnet`` because routability must select a
    #: public or private treatment. Values are actionable error messages.
    forbidden_kinds: dict[str, str] = Field(default_factory=dict)
    #: Dash per zone kind; None means solid. Kinds not listed fall to
    #: FRAME_DASHED, then to ``dash``.
    dashes: dict[str, str | None] = Field(default_factory=dict)
    #: Frame line weight when the theme declares none for the kind. 1.0 is
    #: the weight AWS publishes for its group boxes and draws crisp at every
    #: whole export scale; both renderers read this same default.
    border_width: float = 1.0
    border_role: Role = "muted"
    #: What the badge tab is painted. ``frame`` fills it in the zone's colour
    #: and reverses the glyph out in paper -- right for AWS, whose group boxes
    #: are white marks on their own coloured square. ``paper`` leaves the tab
    #: white and lets the icon paint itself -- right for Azure and
    #: DigitalOcean, whose badges are full-colour icons that vanished against
    #: a tab of the very colour they were sampled from.
    tab_fill: Literal["frame", "paper"] = "frame"
    border_alpha: float = 0.45
    #: Alpha for an explicitly coloured zone fill. It does not vary with
    #: nesting depth because the zone's own hue is already carrying the
    #: distinction; only the border fades by depth, through ``border_at``.
    fill_tint: float = 0.10
    #: Border alpha per nesting level, deepest value reused beyond the last.
    border_alphas: tuple[float, ...] = (0.45, 0.52, 0.60, 0.68, 0.76)
    label_size: float = 10
    #: Captions are set the way the vendor decks set them -- the UI face,
    #: authored case, medium weight -- in both renderers. A theme may still
    #: choose the mono uppercase house style.
    label_font: Literal["mono", "sans"] = "sans"
    label_case: Literal["upper", "preserve"] = "preserve"
    label_weight: int | None = 500
    label_tracking: str = "0"
    #: Advance per character, as a multiple of the label size: the one the
    #: shipped checker measures text with, read from render-metrics.json so
    #: the editor's boundaryLabelBox keeps a title's obstacle the same width.
    label_advance: float = _FRAME["label_advance"]
    label_icon: int = _FRAME["icon"]  # the glyph inside the tab
    label_icon_inset: int = _FRAME["icon_inset"]  # tab edge to the glyph
    label_icon_gap: int = _FRAME["label_gap"]  # tab edge to caption
    #: Places the caption baseline: y = tab / 2 + label size / divisor.
    label_baseline_divisor: float = _FRAME["baseline_divisor"]
    pad: int = 24  # cluster edge to its children
    #: Extra top pad. The label rides the border, so the inset is uniform
    #: and a zone's children align to all four edges equally.
    header: int = 0

    def title_width(self, label: str) -> float:
        """How wide a frame's title reads, tab included: the one estimate
        both routers keep wires out of and the layout keeps a frame at least
        as wide as. The editor's ``boundaryLabelBox`` is the same formula on
        the same numbers (render-metrics.json ``frame``); ``label`` is passed
        already cased the way it draws."""
        if not label:
            return 0.0
        text = len(label) * self.label_size * self.label_advance + TITLE_PAD
        return max(TITLE_MIN, text) + self.tab

    def width_for(self, kind: str) -> float:
        """Border width for a zone kind."""
        return self.widths.get(kind, FRAME_WIDTHS.get(kind, self.border_width))

    def radius_for(self, kind: str) -> int:
        """Corner radius for a zone kind; 0 draws a square corner."""
        return self.radii.get(kind, self.radius)

    def color_for(self, kind: str) -> str:
        """Border colour for a zone kind: its own entry, else the theme's
        frame colour, else "" to fall back to the border role."""
        return self.colors.get(kind, self.color)

    def fill_for(self, kind: str) -> str:
        """Fill colour, ``"none"``, or "" for the depth-based fallback."""
        return self.fills.get(kind, "")

    def icon_for(self, kind: str) -> str:
        """Qualified zone artwork reference, or "" when the skin has none."""
        return self.icons.get(kind, "")

    def dash_for(self, kind: str) -> str | None:
        """The dash pattern for a zone of this kind; None draws solid."""
        if kind in self.dashes:
            return self.dashes[kind]
        if kind in FRAME_DASHED:
            return "5,4"
        return self.dash

    def border_at(self, depth: int) -> float:
        """Border alpha for a nesting level, clamped the same way."""
        if not self.border_alphas:
            return self.border_alpha
        return self.border_alphas[min(max(depth, 0), len(self.border_alphas) - 1)]


class Canvas(BaseModel):
    width: int = 1200
    height: int = 660
    #: Frame tightly around the content instead of holding the gallery's
    #: fixed minimum. Off by default so example cards stay uniform.
    fit: bool = False
    fit_margin: int = 40
    margin_x: int = 32
    content_top: int = 96
    content_bottom: int = 548
    gap: int = 24  # between siblings inside a cluster
    #: A frame whose axis was inferred, not declared, wraps its children into
    #: a grid once it holds ``grid_min`` of them and its one axis would run
    #: past a limit: a column taller than ``column_limit`` times its width, a
    #: row wider than ``row_limit`` times its height. The grid takes the
    #: column count that brings the frame nearest ``grid_aspect`` (width over
    #: height). A frame told ``.grid()`` always wraps.
    grid_min: int = 6
    grid_aspect: float = 1.6
    column_limit: float = 5.0
    row_limit: float = 8.0
    #: The top level's own row limit. A left-to-right chain is often the
    #: point of a diagram, and wrapping it doubles its wires back, so the
    #: top level wraps only a row far longer than a frame would.
    root_row_limit: float = 16.0
    #: The least height a row, or width a column, is measured against: a row
    #: of cards is 48 px tall, and six of them in a line read as a line, not
    #: as a shape eighteen times wider than tall.
    grid_floor: int = 160
    #: The top level wraps only from this many items: fewer, in a line, are
    #: a chain the diagram means.
    root_grid_min: int = 12
    cluster_gap: int = 72  # between top-level clusters
    legend_offset: int = 84  # from the bottom edge
    #: Clear space between the lowest drawn element and the provider mark.
    #: The mark keeps a band of its own below the drawing in both renderers.
    mark_gap: int = _MARK["gap"]


class Style(BaseModel):
    """The whole visual vocabulary, overridable field by field."""

    canvas: Canvas = Field(default_factory=Canvas)
    node: NodeStyle = Field(default_factory=NodeStyle)
    cluster: ClusterStyle = Field(default_factory=ClusterStyle)
    #: How links find their way around nodes. Swap in a subclass,
    #: or tune clearance/turn_cost, per diagram.
    router: Router = Field(default_factory=Router)
    links: dict[str, LinkStyle] = Field(
        default_factory=lambda: {
            "solid": LinkStyle(width=1.4, role="accent"),
            "dotted": LinkStyle(width=1.2, dash=_DASHES["dotted"], role="muted"),
            "dashed": LinkStyle(width=1.0, dash=_DASHES["dashed"], role="soft"),
        }
    )
    #: Every text in a drawing is set in Inter, the face the editor's
    #: controls use too, so a label reads the same in the picture and in the
    #: panel that edits it; one face across the product. Geist Mono remains
    #: for monospaced frame titles and an author who picks it.
    sans: str = "'Inter', sans-serif"
    mono: str = "'Geist Mono', monospace"
    #: The static page's heading, in the same face.
    heading: str = "'Inter', sans-serif"
    #: Height of the skin's brand mark, bottom-left; shared with the editor.
    mark_height: int = _MARK["height"]
    #: Provider opt-in clearance above a legend divider. Zero preserves the
    #: historical bottom-left footer placement for existing skins.
    #: Clear space between a provider lockup and the legend divider. A zero
    #: default placed the lockup in the legend row and caused long wordmarks
    #: (notably Microsoft) to cover the first legend item in PNG/SVG export.
    mark_legend_gap: int = 16
    dot_grid: bool = True
    dot_alpha: float = 0.10

    def link(self, kind: str) -> LinkStyle:
        if kind not in self.links:
            raise KeyError(f"unknown link kind {kind!r}; have {', '.join(sorted(self.links))}")
        return self.links[kind]


# ---------------------------------------------------------------------------
# Scene graph
# ---------------------------------------------------------------------------


class Node(BaseModel):
    """One component box."""

    name: str
    detail: str = ""
    #: The topology element this box draws, so a caller can pair them by
    #: identity after the layout has reordered siblings.
    ref: str = ""
    icon: ProviderIcon | None = None
    focal: bool = False
    #: The card's own fill and outline, as the editor paints them from its
    #: style (a card restyled by hand, a plan's change): they win over the
    #: accent and the default. Empty draws the default.
    fill: str = ""
    stroke: str = ""
    #: A theme role name ("accent") or a literal hex ("#009639"). Empty
    #: means the default border treatment.
    accent: str = ""
    #: ``card`` (a titled box) or ``icon`` (the bare mark, caption beneath).
    display: str = "card"
    #: A resource the estate keeps without using carries a tag in its
    #: top-right corner (render-metrics.json ``flag``).
    flagged: bool = False
    #: Several detail lines, compartments or a shape (builders/panels.py):
    #: None for a plain card.
    panel: Panel | None = None
    width: int | None = None
    height: int | None = None
    x: int = 0
    y: int = 0

    model_config = {"arbitrary_types_allowed": True}

    @property
    def icon_only(self) -> bool:
        return self.display == "icon"

    @property
    def cx(self) -> int:
        return self.x + (self.width or 0) // 2

    @property
    def cy(self) -> int:
        return self.y + (self.height or 0) // 2

    def resolve(self, style: Style) -> None:
        """Fill in any size the caller left to the style.

        A card with a long name grows to fit it rather than rendering as
        "Application Load Ba...". The estimate matches the renderer's own
        character budget, so what fits here fits there; ``max_width`` caps
        the growth and anything past it still truncates.

        Only in ``fit`` mode, where the canvas is sized to its content. A
        fixed document preset is a promise that the diagram fits a given
        box, and widening cards would break it; there, a long name still
        truncates.
        """
        if self.panel is not None:
            # A panel is sized by what it carries, in any canvas: its lines
            # and compartments are the point of it, and the editor draws the
            # size it is given.
            width, height = panel_size(self.name, self.panel, self.icon is not None)
            self.width = self.width or width
            self.height = self.height or height
            return
        if self.icon_only:
            # The caption is centred under the glyph, so only its own width
            # matters; a bare mark never needs the text lane a card has.
            self.height = self.height or style.node.icon_height
            if self.width:
                return
            self.width = style.node.icon_width
            # A bare mark has its own ceiling: the editor caps a glyph card
            # narrower than it would cap a card with a text lane.
            ceiling = max(_ICON["max_width"], self.width)
            if ceiling <= self.width or not style.canvas.fit:
                return
            # Mirrors the runtime's iconNodeWidth: the name at the title size,
            # the detail line at its own advance, the float ceiled to the grid
            # the way the runtime ceils it.
            caption = (
                max(
                    len(self.name) * style.node.title_size * TITLE_ADVANCE,
                    len(self.detail) * CAPTION_DETAIL_ADVANCE,
                )
                + 16
            )
            self.width = min(ceiling, max(self.width, math.ceil(caption / 4) * 4))
            return
        self.height = self.height or style.node.height
        if self.width:
            return
        self.width = style.node.width
        ceiling = max(style.node.max_width, style.node.width)
        if ceiling <= style.node.width or not style.canvas.fit:
            return
        # Mirrors the runtime: both lines start after the icon lane and keep
        # the same margin clear of the right edge.
        end = _CARD["text_end"]
        title = style.node.text_inset + len(self.name) * style.node.title_size * TITLE_ADVANCE + end
        detail = style.node.text_inset + len(self.detail) * DETAIL_ADVANCE + end
        # Ceil the float to the grid, the way the caption above does. Flooring
        # it first threw away the fraction that pushes a card onto the next
        # 4 px step, so text measured to fit was drawn one character short.
        needed = max(title, detail)
        self.width = min(ceiling, max(self.width, math.ceil(needed / 4) * 4))

    def measure(self, style: Style) -> tuple[int, int]:
        self.resolve(style)
        # resolve() leaves neither side unset
        assert self.width is not None and self.height is not None
        return self.width, self.height

    def position(self, x: int, y: int) -> None:
        self.x, self.y = x, y

    def walk(self) -> Iterator[Node]:
        yield self


#: Corner badges: what applies to a frame -- a subnet's NSG or route table --
#: the way Azure's reference diagrams seat an NSG on its subnet. The first
#: badge's icon sits on the frame's top-right corner point, the rest on the
#: top border leftwards from it; each name sits just under the top border,
#: immediately left of its icon; ``drop`` is how far under the line. The
#: editor draws the same geometry (``CORNER_BADGE`` and ``cornerLayout`` in
#: runtime 14-shapes); change both together.
CORNER_BADGE = {"icon": 20, "font": 9, "advance": 0.6, "gap": 3, "spacing": 12, "drop": 1.5}


def _badge_caption_width(label: str) -> int:
    return round(len(label or "") * CORNER_BADGE["font"] * CORNER_BADGE["advance"])


def corner_layout(right: float, labels: list[str]) -> list[tuple[float, float, str]]:
    """Where each corner badge draws, given the frame's right edge: its
    icon's centre x and the x its name ends at (the name is right-aligned)."""
    c = CORNER_BADGE
    slots: list[tuple[float, float, str]] = []
    edge = right + c["icon"] / 2  # the first icon centres on the corner
    for label in labels:
        centre = edge - c["icon"] / 2
        text_end = centre - c["icon"] / 2 - c["gap"]
        slots.append((centre, text_end, "end"))
        edge = text_end - _badge_caption_width(label) - c["spacing"]
    return slots


#: Edge badges (``side="edge"``): what a frame reaches the outside through --
#: a subnet's NAT gateway -- the way Azure's NAT gateway diagrams draw it: a
#: bar along the frame's top border, marking the subnet it serves, and the
#: icon on that border at its middle, named just under the line to its right.
#: The editor draws the same geometry (``EDGE_BADGE`` in runtime 14-shapes).
EDGE_BADGE: dict[str, Any] = {"icon": 20, "bar": 3, "gap": 3, "spacing": 16, "color": "#50c8e8"}


def edge_layout(left: float, width: float, labels: list[str]) -> list[tuple[float, float]]:
    """Each edge badge's icon centre x and the x its name starts at; one
    badge centres on the top border, several spread from the middle."""
    c = EDGE_BADGE
    spans = [c["icon"] + c["gap"] + _badge_caption_width(label) for label in labels]
    total = sum(spans) + c["spacing"] * max(0, len(spans) - 1)
    x = left + (width - total) / 2
    slots = []
    for span in spans:
        slots.append((x + c["icon"] / 2, x + c["icon"] + c["gap"]))
        x += span + c["spacing"]
    return slots


def edge_row_width(labels: list[str]) -> int:
    if not labels:
        return 0
    c = EDGE_BADGE
    return round(
        sum(c["icon"] + c["gap"] + _badge_caption_width(label) for label in labels)
        + c["spacing"] * (len(labels) - 1)
    )


def corner_row_width(labels: list[str]) -> int:
    """How far the corner badges reach in from the frame's right edge."""
    if not labels:
        return 0
    c = CORNER_BADGE
    reach = c["icon"] / 2 + c["gap"] + _badge_caption_width(labels[0])
    for label in labels[1:]:
        reach += c["spacing"] + c["icon"] + c["gap"] + _badge_caption_width(label)
    return round(reach)


class ClusterBadge(BaseModel):
    """One corner badge as drawn: its artwork resolved, and its name."""

    icon: ProviderIcon
    label: str = ""
    side: Literal["corner", "edge", "top", "bottom", "left", "right"] = "corner"
    offset: float = 0.5

    model_config = {"arbitrary_types_allowed": True}

    def anchor(self, cluster: Cluster) -> tuple[float, float]:
        """Centre point for a badge pinned to a named border side."""
        ratio = min(1.0, max(0.0, self.offset))
        if self.side in ("top", "bottom"):
            return (
                cluster.x + cluster.width * ratio,
                cluster.y if self.side == "top" else cluster.y + cluster.height,
            )
        return (
            cluster.x if self.side == "left" else cluster.x + cluster.width,
            cluster.y + cluster.height * ratio,
        )


class Cluster(BaseModel):
    """A labelled, nestable group. Children lay out along one axis."""

    label: str = ""
    #: The topology element this zone draws; see :attr:`Node.ref`.
    ref: str = ""
    #: Keep the author's child order instead of letting the layout pull
    #: connected children towards each other.
    keep_order: bool = False
    #: What the zone is -- "vnet", "subnet", "group". The border reads it.
    kind: str = ""
    #: Called out (``editor_highlight``): an accent ring and tint around the
    #: zone, drawn the same way by the editor.
    highlight: bool = False
    #: The frame gallery this zone was placed from (``editor_frame_group``):
    #: "aws", "kubernetes", "generic", or empty for a plain group.
    group: str = ""
    #: The look a frame from another gallery keeps -- that gallery's boundary
    #: style and theme -- resolved once when the scene is built. Empty for a
    #: frame that draws with the scene's own style, which is every frame of
    #: the project's own library. The editor resolves the same look through
    #: ``_boundary_component_style``, so both renderers agree on an on-premises
    #: frame placed inside an AWS project.
    look_style: ClusterStyle | None = None
    look_theme: Theme | None = None
    #: Artwork for the zone itself, drawn beside its label.
    icon: ProviderIcon | None = None
    #: What applies to the zone, drawn on its top-right corner.
    badges: list[ClusterBadge] = Field(default_factory=list)
    flow: Flow = "column"
    #: Explicit Azure import grid width; nested frames get a row of their own.
    wrap: int = 0
    #: The axis was inferred from the depth, not declared by the author, so
    #: the layout may wrap a long one into a grid (Canvas.grid_min).
    auto: bool = False
    #: Nesting level among *drawn* clusters. The scene root is -1 because it
    #: is a frame, not a box, so its children are the first drawn level.
    depth: int = 0
    children: list[Node | Cluster] = Field(default_factory=list)
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    model_config = {"arbitrary_types_allowed": True}
    #: Columns of the grid this frame wrapped into at its last measure; 0
    #: while it lays out along one axis.
    _cols: int = PrivateAttr(default=0)
    #: The gap two children ask for, by their indices, because a captioned
    #: wire runs between them: set by ``place`` (``_reserve_caption_room``).
    _widen: dict[tuple[int, int], int] = PrivateAttr(default_factory=dict)
    #: The same for two children one above the other: room for the
    #: caption's height beside the wire between them.
    _lift: dict[tuple[int, int], int] = PrivateAttr(default_factory=dict)

    @property
    def arranged(self) -> Flow:
        """How the children were actually laid out: ``flow``, or ``grid``
        where an inferred axis wrapped."""
        return "grid" if self.wrap or self._cols else self.flow

    def node(self, name: str = "", detail: str = "", **kwargs) -> Node:
        """Add a child node. Positional here, keywords into the model."""
        item = Node(name=name or kwargs.pop("name", ""), detail=detail, **kwargs)
        self.children.append(item)
        return item

    def cluster(self, label: str = "", flow: Flow = "column", **kwargs) -> Cluster:
        item = Cluster(label=label, flow=flow, depth=self.depth + 1, **kwargs)
        self.children.append(item)
        return item

    def _adopt(self, child: Node | Cluster) -> None:
        """Re-depth a subtree built before it knew where it would sit."""
        if isinstance(child, Cluster):
            child.depth = self.depth + 1
            for grandchild in child.children:
                child._adopt(grandchild)

    def __rshift__(self, child: Node | Cluster) -> Node | Cluster:
        """Append and return the child, mirroring TopologyElement."""
        self._adopt(child)
        self.children.append(child)
        return child

    def add(self, *items: Node | Cluster) -> Cluster:
        for item in items:
            self._adopt(item)
        self.children.extend(items)
        return self

    def measure(self, style: Style) -> tuple[int, int]:
        sizes = [child.measure(style) for child in self.children]
        if not sizes:
            # An empty frame keeps whatever size it was given; there is
            # nothing inside it to say otherwise -- except its own title and
            # corner badges, which must still fit side by side.
            self.width = max(self.width, self._corner_min_width(style))
            return self.width, self.height
        gap, pad = style.canvas.gap, style.cluster.pad
        top = pad + (style.cluster.header if self.label else 0)
        self._cols = 0 if self.wrap > 0 else self._grid_columns(sizes, style, top)
        if self.wrap > 0:
            rows = self._grid_rows(sizes, gap)
            inner_w = max(width for width, _, _ in rows)
            inner_h = sum(height for _, height, _ in rows) + gap * (len(rows) - 1)
        elif self._cols:
            col_ws, row_hs = _grid_tracks(sizes, self._cols)
            inner_w = sum(col_ws) + sum(self._across(gap, len(col_ws)))
            inner_h = sum(row_hs) + sum(self._down(gap, len(row_hs), self._cols))
        elif self.flow == "row":
            inner_w = sum(w for w, _ in sizes) + sum(self._across(gap, len(sizes)))
            inner_h = max(h for _, h in sizes)
        else:
            inner_w = max(w for w, _ in sizes)
            inner_h = sum(h for _, h in sizes) + sum(self._down(gap, len(sizes), 1))
        self.width = max(
            inner_w + pad * 2, self._title_width(style) + pad, self._corner_min_width(style)
        )
        self.height = inner_h + top + pad
        return self.width, self.height

    def _grid_rows(
        self, sizes: list[tuple[int, int]], gap: int
    ) -> list[tuple[int, int, list[tuple[Node | Cluster, int, int]]]]:
        """The grid's rows: (width, height, [(child, cell width, child height)])."""
        cell = max(
            (
                w
                for child, (w, _) in zip(self.children, sizes, strict=True)
                if not isinstance(child, Cluster)
            ),
            default=0,
        )
        rows: list[tuple[int, int, list[tuple[Node | Cluster, int, int]]]] = []
        shelf: list[tuple[Node | Cluster, int, int]] = []

        def close() -> None:
            if shelf:
                width = sum(w for _, w, _ in shelf) + gap * (len(shelf) - 1)
                rows.append((width, max(h for _, _, h in shelf), list(shelf)))
                shelf.clear()

        for child, (w, h) in zip(self.children, sizes, strict=True):
            if isinstance(child, Cluster):
                close()
                shelf.append((child, w, h))
                close()
                continue
            shelf.append((child, cell, h))
            if len(shelf) == self.wrap:
                close()
        close()
        return rows

    def _across(self, gap: int, cols: int) -> list[int]:
        """The gap after each column but the last: ``gap``, or wider where a
        captioned wire runs between two children side by side, so its
        caption stands between them instead of on a card or a border."""
        gaps = [gap] * max(0, cols - 1)
        for (a, b), room in self._widen.items():
            (row_a, col_a), (row_b, col_b) = divmod(a, cols), divmod(b, cols)
            if row_a == row_b and abs(col_a - col_b) == 1:
                gaps[min(col_a, col_b)] = max(gaps[min(col_a, col_b)], room)
        return gaps

    def _down(self, gap: int, rows: int, cols: int) -> list[int]:
        """The gap after each row but the last: ``gap``, or taller where a
        captioned wire runs between two children one above the other."""
        gaps = [gap] * max(0, rows - 1)
        for (a, b), room in self._lift.items():
            (row_a, col_a), (row_b, col_b) = divmod(a, cols), divmod(b, cols)
            if col_a == col_b and abs(row_a - row_b) == 1:
                gaps[min(row_a, row_b)] = max(gaps[min(row_a, row_b)], room)
        return gaps

    def _grid_columns(self, sizes: list[tuple[int, int]], style: Style, top: int) -> int:
        """The grid's column count, or 0 to lay out along ``flow``.

        A declared ``grid`` always wraps; an inferred axis wraps once the
        frame holds ``grid_min`` children and its one axis runs past the
        limit. The count is the one that brings the whole frame, padding and
        title included, nearest ``grid_aspect``; the smaller count wins a tie.
        """
        canvas, pad, gap = style.canvas, style.cluster.pad, style.canvas.gap
        if self.flow != "grid":
            if not self.auto or len(sizes) < canvas.grid_min:
                return 0
            floor = canvas.grid_floor
            if self.flow == "row":
                long = sum(w for w, _ in sizes) + gap * (len(sizes) - 1)
                if long <= canvas.row_limit * max(floor, *(h for _, h in sizes)):
                    return 0
            else:
                long = sum(h for _, h in sizes) + gap * (len(sizes) - 1)
                if long <= canvas.column_limit * max(floor, *(w for w, _ in sizes)):
                    return 0
        title = max(self._title_width(style) + pad, self._corner_min_width(style))
        best, best_score = 1, math.inf
        for cols in range(1, len(sizes) + 1):
            col_ws, row_hs = _grid_tracks(sizes, cols)
            width = max(sum(col_ws) + gap * (cols - 1) + pad * 2, title)
            height = sum(row_hs) + gap * (len(row_hs) - 1) + top + pad
            score = abs(math.log(width / height / canvas.grid_aspect))
            if score < best_score - 1e-9:
                best, best_score = cols, score
        return best

    def _corner_min_width(self, style: Style) -> int:
        """The title owns the top-left, corner badges the top-right: wide
        enough that the two never meet. 0 without corner badges."""
        corner = [badge.label for badge in self.badges if badge.side == "corner"]
        edge = [badge.label for badge in self.badges if badge.side == "edge"]
        if not corner and not edge:
            return 0
        pad = style.cluster.pad
        if not edge:
            return self._title_width(style) + corner_row_width(corner) + pad
        # The edge row centres on the frame: each half must hold its side of
        # it, the title on the left and the corner badges on the right.
        half = edge_row_width(edge) / 2 + EDGE_BADGE["spacing"]
        return round(
            2 * max(self._title_width(style) + half, corner_row_width(corner) + half + pad)
        )

    def _title_width(self, style: Style) -> int:
        """How wide the title chip draws, by the renderer's own arithmetic.

        A frame narrower than its title has the title band across its whole
        top edge, so nothing can enter from above without crossing the name.
        Measuring the chip here keeps the frame at least that wide.
        """
        if not self.label:
            return 0
        cs = style.cluster
        label = self.label.upper() if cs.label_case == "upper" else self.label
        return math.ceil(cs.title_width(label))

    def position(self, x: int, y: int, style: Style) -> None:
        self.x, self.y = x, y
        gap, pad = style.canvas.gap, style.cluster.pad
        top = y + pad + (style.cluster.header if self.label else 0)
        inner_w = self.width - pad * 2
        inner_h = self.height - pad - (top - y)
        cx, cy = x + pad, top
        if self.wrap > 0:
            sizes = [child.measure(style) for child in self.children]
            rows = self._grid_rows(sizes, gap)
            # Card rows share one set of columns, so a short last row lines
            # up under the full ones; a frame's row is centred on its own.
            grid_w = max(
                (w for w, _, cells in rows if not isinstance(cells[0][0], Cluster)), default=0
            )
            for row_w, row_h, cells in rows:
                span = row_w if isinstance(cells[0][0], Cluster) else grid_w
                left = cx + (inner_w - span) // 2
                for child, cell_w, h in cells:
                    w = child.measure(style)[0]
                    _place_child(child, left + (cell_w - w) // 2, cy + (row_h - h) // 2, style)
                    left += cell_w + gap
                cy += row_h + gap
            return
        if self._cols:
            sizes = [child.measure(style) for child in self.children]
            col_ws, row_hs = _grid_tracks(sizes, self._cols)
            gaps = self._across(gap, len(col_ws))
            downs = self._down(gap, len(row_hs), self._cols)
            # The tracks sit centred in the frame, which may be wider than
            # them for its title; each child centres in its cell.
            left = x + pad + (inner_w - sum(col_ws) - sum(gaps)) // 2
            for index, (child, (w, h)) in enumerate(zip(self.children, sizes, strict=True)):
                row, col = divmod(index, self._cols)
                cell_x = left + sum(col_ws[:col]) + sum(gaps[:col])
                cell_y = top + sum(row_hs[:row]) + sum(downs[:row])
                _place_child(
                    child, cell_x + (col_ws[col] - w) // 2, cell_y + (row_hs[row] - h) // 2, style
                )
            return
        gaps = [*self._across(gap, len(self.children)), 0]
        downs = [*self._down(gap, len(self.children), 1), 0]
        for index, child in enumerate(self.children):
            w, h = child.measure(style)
            if self.flow == "row":
                _place_child(child, cx, top + (inner_h - h) // 2, style)
                cx += w + gaps[index]
            else:
                _place_child(child, cx + (inner_w - w) // 2, cy, style)
                cy += h + downs[index]

    def walk(self) -> Iterator[Node]:
        for child in self.children:
            yield from child.walk()

    def clusters(self) -> Iterator[Cluster]:
        yield self
        for child in self.children:
            if isinstance(child, Cluster):
                yield from child.clusters()


def _grid_tracks(sizes: list[tuple[int, int]], cols: int) -> tuple[list[int], list[int]]:
    """Column widths and row heights of a row-major grid of *sizes*."""
    col_ws = [0] * min(cols, len(sizes))
    row_hs = [0] * math.ceil(len(sizes) / cols)
    for index, (w, h) in enumerate(sizes):
        row, col = divmod(index, cols)
        col_ws[col] = max(col_ws[col], w)
        row_hs[row] = max(row_hs[row], h)
    return col_ws, row_hs


def _root_columns(root: Cluster, sizes: list[tuple[int, int]], canvas: Canvas) -> int:
    """The top level's grid columns, or 0 to keep its row or column.

    The rule a frame follows, from ``root_grid_min`` items and past
    ``root_row_limit``, with the top level's own gap: a diagram whose direction was not declared wraps a
    long row of top-level frames and cards into rows. The count is the one
    nearest ``grid_aspect``; the smaller count wins a tie.
    """
    gap, floor = canvas.cluster_gap, canvas.grid_floor
    if not root.auto or len(sizes) < canvas.root_grid_min:
        return 0
    if root.flow == "column":
        long = sum(h for _, h in sizes) + gap * (len(sizes) - 1)
        if long <= canvas.column_limit * max(floor, *(w for w, _ in sizes)):
            return 0
    else:
        long = sum(w for w, _ in sizes) + gap * (len(sizes) - 1)
        if long <= canvas.root_row_limit * max(floor, *(h for _, h in sizes)):
            return 0
    best, best_score = 1, math.inf
    for cols in range(1, len(sizes) + 1):
        col_ws, row_hs = _grid_tracks(sizes, cols)
        width = sum(col_ws) + gap * (cols - 1)
        height = sum(row_hs) + gap * (len(row_hs) - 1)
        score = abs(math.log(width / height / canvas.grid_aspect))
        if score < best_score - 1e-9:
            best, best_score = cols, score
    return best


def _place_child(child: Node | Cluster, x: int, y: int, style: Style) -> None:
    if isinstance(child, Cluster):
        child.position(x, y, style)
    else:
        child.position(x, y)


class Link(BaseModel):
    """A connector between two nodes. `kind` names a LinkStyle."""

    source: Node
    target: Node
    label: str = ""
    kind: str = "solid"
    #: The head shape (``arrowheads.json``) and the bend style
    #: (``render-metrics.json`` ``router.corners``) the wire's editor style
    #: chose; None means each table's default.
    arrow: str | None = None
    corners: str | None = None
    #: A colour and width the wire's editor style chose over its kind's;
    #: None means the kind's own.
    stroke: str | None = None
    width: float | None = None
    #: Which ends carry a head: ``forward`` (source to target), ``both``, or
    #: ``none`` for an undirected association. The editor reads the same
    #: word (edgeHeads).
    direction: Literal["forward", "both", "none"] = "forward"
    #: Corners the author pinned by hand, on the editor's canvas. Read only
    #: when the scene stands where the editor left it (``Scene.saved_layout``).
    waypoints: tuple[tuple[float, float], ...] = ()
    #: The side each end leaves from and arrives at, when the author chose
    #: one: "top", "right", "bottom", "left". None means the wire is anchored
    #: where the two nodes stand, as the editor's 'auto' does.
    source_side: str | None = None
    target_side: str | None = None
    #: Where the author moved the caption, as an offset from where it would
    #: stand (``label_placement`` in the document, mode ``manual``).
    label_offset: tuple[float, float] | None = None
    #: Where the wire comes in a flow told in order: a numbered circle at the
    #: start of its caption, and ``step_text`` (else the label) in the list.
    step: int | None = None
    step_text: str | None = None
    #: The second flow's name when the step is in it; None is the main flow.
    step_flow: str | None = None

    @property
    def heads(self) -> tuple[bool, bool]:
        """(start, end): which ends of the wire wear a head."""
        return self.direction == "both", self.direction != "none"


def seat_toward(candidates: list[Node], toward: Node | None) -> Node | None:
    """Of the nodes drawn inside one frame, the one a wire should sit on.

    A wire may be aimed at a frame (``node >> Edge("x") >> vpc``), but only
    something drawn can carry an end of it, so the frame resolves to a node
    inside itself. Taking the first one was arbitrary -- it depended on the
    order the author happened to write the children in -- so the wire could
    set off across the whole frame to reach a card on the far side, cutting
    through the cards in between. The checker then objected to the picture
    rather than to the choice that made it.

    The nearest child is the one a reader would have drawn it to. Both
    renderers seat wires through here, so the HTML and the static picture
    agree about which card a frame's wire lands on.
    """
    if not candidates:
        return None
    if toward is None or len(candidates) == 1:
        return candidates[0]
    return min(candidates, key=lambda node: (node.cx - toward.cx) ** 2 + (node.cy - toward.cy) ** 2)


class Scene(BaseModel):
    title: str
    desc: str
    theme: Theme
    slug: str
    eyebrow: str = "Architecture"
    heading: str = ""
    #: Where the drawing stands, what stands with it, and when it was made.
    #: Drawn in the top band and written onto the SVG root; see
    #: projects.parts.Presentation.
    status: str = ""
    notes: tuple[str, ...] = ()
    drawn_on: str = ""
    crossings: str = "plain"
    #: How heavy every frame's border draws; see FRAME_LINES.
    frame_lines: str = "thin"
    style: Style = Field(default_factory=Style)
    root: Cluster = Field(default_factory=lambda: Cluster(flow="row", depth=-1))
    links: list[Link] = Field(default_factory=list)
    legend: list[tuple[str, str]] = Field(default_factory=list)
    #: What each tone a box is filled with means, for the legend.
    tones: list[tuple[str, str]] = Field(default_factory=list)

    @property
    def frame_line_scale(self) -> float:
        """What every frame's own border width is drawn at a multiple of."""
        return FRAME_LINES.get(self.frame_lines, 1.0)

    @property
    def steps(self) -> list[tuple[int, str]]:
        """The main flow's numbered steps, in order, once each: a number two
        wires share is told by the first."""
        return self._told(None)

    @property
    def second_flow(self) -> tuple[str, list[tuple[int, str]]] | None:
        """The second flow's name and its steps, told like ``steps``; None
        when every step is in the main flow. Two flows are the most a
        drawing tells apart (a third is refused when the scene is built)."""
        names = [link.step_flow for link in self.links if link.step is not None and link.step_flow]
        return (names[0], self._told(names[0])) if names else None

    def _told(self, flow: str | None) -> list[tuple[int, str]]:
        told: dict[int, str] = {}
        for link in self.links:
            if link.step is not None and link.step_flow == flow and link.step not in told:
                told[link.step] = link.step_text or link.label
        return sorted(told.items())

    #: Each element's place in the document (its id to its index): the order
    #: the editor lists cards and frames in, which is the order a caption
    #: meets them when it steps clear. The layout reorders siblings; this
    #: does not move.
    order: dict[str, int] = Field(default_factory=dict)
    width: int = 0
    height: int = 0
    #: True when the drawing stands where the editor saved it, so coordinates
    #: written on the editor's canvas -- a wire's bends -- mean what they say.
    saved_layout: bool = False

    model_config = {"arbitrary_types_allowed": True}

    def cluster(self, label: str = "", flow: Flow = "column") -> Cluster:
        return self.root.cluster(label, flow)

    def node(self, name: str = "", detail: str = "", **kwargs) -> Node:
        return self.root.node(name, detail, **kwargs)

    def link(self, source: Node, target: Node, **kwargs) -> Link:
        """Connect two nodes; `kind` selects a LinkStyle from the Style."""
        item = Link(source=source, target=target, **kwargs)
        self.links.append(item)
        return item


Cluster.model_rebuild()
Scene.model_rebuild()


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------

#: The editor's snap grid (render-metrics.json ``router.grid``).
GRID = int(metrics.router()["grid"])


def on_grid(value: float) -> int:
    """*value* on the editor's grid, rounded as the editor state rounds it:
    Python's own rounding, so 150 lands on 152 and 394 on 392."""
    return round(value / GRID) * GRID


def snap_to_grid(scene: Scene) -> Scene:
    """Stand every frame and card on the editor's grid.

    The editor opens a drawing with each frame's box and each card's corner
    on its grid (editor/state.py), and every exported picture is the
    editor's. A layout that centred a card at x=150 drew it there in the
    static picture and at 152 in the export; standing both on one grid makes
    them one picture. A card keeps its size, as it does in the editor.
    """
    for cluster in scene.root.clusters():
        cluster.x, cluster.y = on_grid(cluster.x), on_grid(cluster.y)
        cluster.width, cluster.height = on_grid(cluster.width), on_grid(cluster.height)
    for node in scene.root.walk():
        node.x, node.y = on_grid(int(node.x)), on_grid(int(node.y))
    return scene


def size_to_content(scene: Scene) -> Scene:
    """Grow the canvas around content that was moved after it was placed.

    A layout saved by hand puts cards where the reader left them, which may
    be past the edge the layout sized the canvas to. The canvas grows rather
    than clipping, as it does when it is placed.
    """
    canvas = scene.style.canvas
    items: list[Node | Cluster] = [
        *scene.root.walk(),
        *(c for c in scene.root.clusters() if c is not scene.root),
    ]
    right = max((item.x + (item.width or 0) for item in items), default=0)
    bottom = max((item.y + (item.height or 0) for item in items), default=0)
    margin = canvas.fit_margin if canvas.fit else canvas.margin_x
    scene.width = max(scene.width, int(right + margin))
    scene.height = max(scene.height, int(bottom + margin))
    return scene


#: Room kept either side of a caption that stands between two children side
#: by side: a card's port clearance at its narrowest, and some.
CAPTION_ROOM = 12
#: Room kept above and below a caption beside a wire between two children
#: one above the other: a card's clearance and a frame border's, with the
#: snap grid's slack.
CAPTION_LIFT = 6


def _reserve_caption_room(scene: Scene) -> None:
    """Ask each frame for room between two children side by side that a
    captioned wire joins, so the caption fits between them.

    Siblings stand ``Canvas.gap`` apart: a corridor narrower than most
    captions, so a caption on a wire between them was pushed onto a card, a
    frame's border, or far off its wire. The two children are the ones the
    wire's ends sit in, under the nearest frame that holds both -- the top
    level too, whose ``cluster_gap`` is wide but not as wide as every
    caption once it keeps off both borders.
    """
    parents: dict[int, tuple[Cluster, int]] = {}
    for cluster in scene.root.clusters():
        cluster._widen, cluster._lift = {}, {}
        for index, child in enumerate(cluster.children):
            parents[id(child)] = (cluster, index)

    def holders(item: Node | Cluster) -> list[tuple[Cluster, int]]:
        found = []
        while id(item) in parents:
            cluster, index = parents[id(item)]
            found.append((cluster, index))
            item = cluster
        return found

    for link in scene.links:
        if not link.label:
            continue
        theirs = {id(cluster): index for cluster, index in holders(link.target)}
        for cluster, index in holders(link.source):
            other = theirs.get(id(cluster))
            if other is None:
                continue
            if other != index:
                numbered = link.step is not None
                lead = metrics.step()["lead"] if numbered else 0
                tall = metrics.step()["chip"] if numbered else CAPTION_TALL
                room = math.ceil(caption_width(link.label) + lead + CAPTION_ROOM * 2)
                lift = math.ceil(tall + CAPTION_LIFT * 2)
                # a frame's title rides its top border and reaches up into
                # the gap above it by its own height
                lower = cluster.children[max(index, other)]
                if isinstance(lower, Cluster) and lower.label:
                    lift += math.ceil(scene.style.cluster.label_size)
                pair = (min(index, other), max(index, other))
                cluster._widen[pair] = max(cluster._widen.get(pair, 0), room)
                cluster._lift[pair] = max(cluster._lift.get(pair, 0), lift)
            break


def place(scene: Scene) -> Scene:
    """Measure bottom-up, size the canvas to the content, then position.

    The canvas grows rather than clipping: a fixed viewBox that is too small
    silently cuts off whole clusters, which is worse than a wider diagram.
    """
    style, canvas = scene.style, scene.style.canvas
    _reserve_caption_room(scene)
    sizes = [child.measure(style) for child in scene.root.children]
    # The root's children sit side by side unless the diagram stacked them
    # (``Diagram(direction="down")`` sets the root cluster's flow to column).
    stacked = scene.root.flow == "column"
    cols = _root_columns(scene.root, sizes, canvas)
    if cols:
        col_ws, row_hs = _grid_tracks(sizes, cols)
        across = scene.root._across(canvas.cluster_gap, len(col_ws))
        total_w = sum(col_ws) + sum(across)
        total_h = sum(row_hs) + canvas.cluster_gap * (len(row_hs) - 1)
    elif stacked:
        total_w = max((w for w, _ in sizes), default=0)
        total_h = sum(h for _, h in sizes) + canvas.cluster_gap * (len(sizes) - 1)
    else:
        across = scene.root._across(canvas.cluster_gap, len(sizes))
        total_w = sum(w for w, _ in sizes) + sum(across)
        total_h = max((h for _, h in sizes), default=0)

    if canvas.fit:
        # Tight framing: the canvas is the content plus one margin, so a
        # small diagram does not float in a 1200-wide field.
        scene.width = total_w + canvas.fit_margin * 2
        footer = canvas.fit_margin
        if getattr(scene.theme, "mark", ""):
            # The provider mark has a band of its own below the drawing, so
            # an outermost frame never runs through the lockup.
            footer = max(footer, canvas.mark_gap + style.mark_height + canvas.fit_margin)
        if scene.legend or scene.tones:
            # The provider mark sits above the legend divider. Reserve both
            # lanes below the topology so fit-mode boundaries never run
            # behind the mark or legend.
            footer = max(
                footer,
                canvas.legend_offset + style.mark_height + style.mark_legend_gap + canvas.gap,
            )
        scene.height = canvas.content_top + total_h + footer
    else:
        scene.width = max(canvas.width, total_w + canvas.margin_x * 2)
        content_h = canvas.content_bottom - canvas.content_top
        scene.height = canvas.height + max(0, total_h - content_h)

    content_h = canvas.content_bottom - canvas.content_top
    # Horizontal centring is on the outermost extent, always.
    x = (scene.width - total_w) // 2
    band_mid = (
        canvas.content_top + total_h // 2
        if canvas.fit
        else canvas.content_top + max(content_h, total_h) // 2
    )
    if cols:
        # The top level wrapped like a long frame: row-major, each item
        # centred in its cell, the cells cluster_gap apart.
        col_ws, row_hs = _grid_tracks(sizes, cols)
        top = band_mid - total_h // 2
        for index, (child, (w, h)) in enumerate(zip(scene.root.children, sizes, strict=True)):
            row, col = divmod(index, cols)
            cell_x = x + sum(col_ws[:col]) + sum(across[:col])
            cell_y = top + sum(row_hs[:row]) + canvas.cluster_gap * row
            _place_child(
                child, cell_x + (col_ws[col] - w) // 2, cell_y + (row_hs[row] - h) // 2, style
            )
        return scene
    if stacked:
        y = band_mid - total_h // 2
        for child, (w, h) in zip(scene.root.children, sizes, strict=True):
            _place_child(child, x + (total_w - w) // 2, y, style)
            y += h + canvas.cluster_gap
        return scene
    for index, (child, (w, h)) in enumerate(zip(scene.root.children, sizes, strict=True)):
        _place_child(child, x, band_mid - h // 2, style)
        x += w + ([*across, 0][index])
    return scene


def glyph_square(node: Node, style: Style | None = None) -> tuple[float, float, float]:
    """The square a bare glyph's artwork is drawn in, as ``(left, top, size)``:
    the runtime's ``glyphSquare``. A captioned node (as tall as the caption
    minimum) seats the square at the top with the caption beneath; a shorter
    one centres it."""
    ns = style.node if style is not None else NodeStyle()
    width, height = node.width or 0, node.height or 0
    captioned = height >= ns.icon_caption_min_height
    size = min(ns.icon_glyph, width - 8, (height - 34 if captioned else height) - 8)
    top = node.y + GLYPH_TOP if captioned else node.y + (height - size) / 2
    return node.x + (width - size) / 2, top, size
