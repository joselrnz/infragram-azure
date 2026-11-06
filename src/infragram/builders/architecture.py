"""Topology -> Scene: turn a declared estate into a drawable diagram.

This is the mapping layer, and the only one that knows about both worlds::

    TopologyElement    what exists          (models/topology.py)
         |
    from_topology()    this module
         |
    Scene, place()     where it goes        (builders/scene.py)
         |
    render()           what it looks like   (builders/render.py)

The editor's export pipeline uses this for a project's initial placement
(``exports.render_project_html``), and topology-as-code builds use it
directly, so nobody does coordinate arithmetic by hand.

Containment maps straight through: an element with children becomes a
Cluster, a leaf becomes a Node. ``role`` is what the drawing reads for
emphasis and topology -- a ``"hub"`` renders focal and every ``"spoke"``
gets a link back to it -- so hub-and-spoke needs no special element type,
and neither will the next pattern.

Icons resolve from the element's ``type`` against whatever collection the
caller passes, so the same topology draws with Azure service icons, AWS
ones, or plain brand logos without changing a line of it.
"""

from __future__ import annotations

import re
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any, cast

from ..catalog.components import architecture_boundary_default_size
from ..models import ProviderIcon
from ..models.topology import TopologyElement
from ..paths import skill_assets
from ..themes import StepMark, Theme, TypeStyle, theme_manifest
from ..verification import safe_colour
from .panels import panel_of
from .render import render, render_svg
from .saved_geometry import apply_to_scene
from .scene import (
    Canvas,
    Cluster,
    ClusterBadge,
    ClusterStyle,
    Flow,
    Link,
    LinkStyle,
    Node,
    Scene,
    Style,
    place,
    seat_toward,
    size_to_content,
    snap_to_grid,
)

#: The sides a wire's ends may be pinned to (``source_port``/``target_port``).
_SIDES = ("top", "right", "bottom", "left")

__all__ = [
    "Canvas",
    "Cluster",
    "Link",
    "LinkStyle",
    "Node",
    "Scene",
    "Style",
    "build",
    "build_topology",
    "badge_for",
    "detail_for",
    "first_drawn",
    "from_topology",
    "accent_for",
    "icon_for",
    "load_icon_set",
    "load_style",
    "load_theme",
    "place",
    "render",
    "render_svg",
    "reorder_by_connections",
]


def _shared_primitive_icon(text: str) -> ProviderIcon | None:
    """A shared primitive as a ProviderIcon carrying its own markup, looked up
    by component id or gallery icon id; None when the gallery has no such glyph."""
    from ..catalog.components import primitive_icon_svg
    from ..catalog.specs import SHARED_PRIMITIVE_SPECS
    from ..paths import skill_references

    spec = next(
        (s for s in SHARED_PRIMITIVE_SPECS if s.service_id == text or s.icon_id == text), None
    )
    icon_id = spec.icon_id if spec is not None else text
    try:
        markup = primitive_icon_svg(icon_id).decode("utf-8")
    except KeyError:
        return None
    return ProviderIcon(
        slug=f"infragram-{spec.service_id if spec is not None else icon_id}",
        name=spec.name if spec is not None else icon_id,
        category=spec.category_id if spec is not None else "",
        path=skill_references() / "primitive-icons.md",
        aliases=tuple(spec.aliases) if spec is not None else (),
        source_url="",
        source_release="",
        source_path="",
        terms_url="",
        sha256="",
        markup=markup,
    )


def _dynamic_icon(element: TopologyElement, svg: str) -> ProviderIcon:
    """The ProviderIcon of a render the element carries; its ink registered."""
    import hashlib

    from ..catalog import ink

    digest = str(
        element.attributes.get("iso_hash") or hashlib.sha256(svg.encode("utf-8")).hexdigest()
    )
    entry = element.attributes.get("iso_ink")
    if isinstance(entry, dict):
        ink.register(ink.artwork_key(svg.encode("utf-8")), entry.get("profile"), entry.get("edges"))
    return ProviderIcon(
        slug=f"iso3d-{digest[:16]}",
        name=element.name,
        category="iso3d",
        path=Path("iso3d") / f"{digest[:16]}.svg",
        aliases=(),
        source_url="",
        source_release="rendered by spec (infragram.iso3d)",
        source_path="",
        terms_url="",
        sha256=hashlib.sha256(svg.encode("utf-8")).hexdigest(),
        tier="service",
        markup=svg,
    )


#: What a miss looks like from any collection: an unknown id or alias
#: (KeyError), an id that fails the slug rule or escapes the pack
#: (ValueError), or a collection object with no ``find`` (AttributeError).
_LOOKUP_MISSES = (KeyError, ValueError, AttributeError)


def _lookup(pack, text: str) -> ProviderIcon | None:
    """One icon from ``pack`` by ``text``, or None when it has none.

    ``slug#variant`` resolves only through ``__getitem__``, so that is tried
    first when the text carries a variant; ``find`` (id, display name, or a
    curated alias) is always tried after it.
    """
    attempts = [lambda: pack[text]] if "#" in text else []
    attempts.append(lambda: pack.find(text))
    for attempt in attempts:
        try:
            return attempt()
        except _LOOKUP_MISSES:
            continue
    return None


def _component_icon(component) -> ProviderIcon | None:
    """The artwork a component reference names: ``icon_ref`` when it carries
    one (``aws:elastic-load-balancing``), else the provider's collection and
    service id. A shared primitive resolves from the gallery."""
    reference = component.icon_ref or f"{component.provider}:{component.service_id}"
    collection, _, slug = reference.partition(":")
    if not slug:
        collection, slug = component.provider, reference
    if collection == "infragram":
        return _shared_primitive_icon(slug)
    try:
        pack = load_icon_set(collection)
    except KeyError:
        pack = None
    if pack is not None:
        found = _lookup(pack, slug)
        if found is not None:
            return found
    return _catalog_artwork(component.provider, component.service_id)


def _catalog_artwork(provider: str, service_id: str) -> ProviderIcon | None:
    """The artwork the editor's sidebar gives a component the vendor pack
    does not carry: the neutral on-premises components, a provider's own
    mark. Asking the same catalog keeps the static picture and the page on
    one drawing."""
    import hashlib

    from ..editor.artwork import artwork_bytes
    from ..editor.sidebar import load_sidebar_catalog

    try:
        catalog = load_sidebar_catalog(provider)
    except (KeyError, ValueError, FileNotFoundError):
        return None
    for category in catalog.categories:
        for component in category.components:
            if (
                component.id != service_id
                or component.provider_id != provider
                or not component.icon_uri
            ):
                continue
            raw = artwork_bytes(component.icon_uri)
            if not raw:
                return None
            try:
                markup = raw.decode("utf-8")
            except UnicodeDecodeError:
                return None
            if not markup.lstrip().startswith("<svg"):
                return None
            return ProviderIcon(
                slug=f"{provider}-{service_id}",
                name=component.name,
                category=component.category_id,
                path=Path(provider) / f"{service_id}.svg",
                aliases=tuple(component.aliases or ()),
                source_url="",
                source_release="the sidebar catalog",
                source_path="",
                terms_url="",
                sha256=hashlib.sha256(markup.encode("utf-8")).hexdigest(),
                markup=markup,
            )
    return None


def icon_for(
    element: TopologyElement, icons=None, *, explicit_only: bool = False
) -> ProviderIcon | None:
    """Best icon for an element, or None when nothing matches.

    An element built from a node class carries its own ``collection``, so it
    resolves without the caller supplying an IconSet -- and one diagram can
    mix vendor artwork with brand logos. A plain TopologyElement falls back
    to the passed collection, looked up by explicit ``icon`` then by type.

    ``explicit_only`` skips the type fallback. Zones use it: a Group's
    ``kind`` is a layout word -- "subnet", "region", "group" -- and some of
    those happen to name real icons, so falling back would decorate every
    container with artwork nobody asked for.
    """
    own = element.attributes.get("collection")
    explicit = element.attributes.get("icon")
    rendered = element.attributes.get("iso_artwork")
    if rendered:
        # a 3D item rendered by spec (infragram.nodes.iso.Iso): the element
        # carries its SVG and its ink measurement, and draws itself
        return _dynamic_icon(element, str(rendered))
    if own == "infragram" and explicit:
        # The shared primitives live in the gallery document, not in a pack;
        # the editor reads them from the sidebar payload and the static
        # picture must draw the same glyph.
        shared = _shared_primitive_icon(str(explicit))
        if shared is not None:
            return shared
    if own:
        try:
            pack = load_icon_set(str(own))
        except KeyError:
            pack = None
        if pack is not None and explicit:
            found = _lookup(pack, str(explicit))
            if found is not None:
                return found

    # An element that names its service only through its component
    # reference -- the document form, and how most shipped templates are
    # written -- draws that component's artwork, the way the editor
    # resolves it from the library payload. Left to the type-name fallback,
    # twenty-four templates drew their cards without icons.
    # Frames keep their own rule (explicit artwork only): their component
    # is the gallery frame, not a mark to draw beside the label.
    if not explicit_only and element.component is not None:
        from_component = _component_icon(element.component)
        if from_component is not None:
            return from_component
    if icons is None or (explicit_only and not explicit):
        return None
    if explicit:
        found = _lookup(icons, str(explicit))
        if found is not None:
            return found
    if explicit_only:
        return None
    try:
        return icons.find(element.type.replace("_", " "))
    except (KeyError, AttributeError):
        return None


def accent_for(element: TopologyElement, style: Style) -> str:
    """The colour an element should carry, or "" for the default treatment.

    Precedence runs most-specific first: what the call site asked for or the
    class declared (both land in ``attributes["accent"]``), then the skin's
    category map, then nothing.
    """
    explicit = element.attributes.get("accent")
    if explicit:
        return str(explicit)
    roles = style.node.accent_roles
    if not roles:
        return ""
    for key in (
        element.attributes.get("category"),
        element.attributes.get("collection"),
        element.type,
        element.role,
    ):
        if key and str(key) in roles:
            return roles[str(key)]
    return ""


def badge_for(badge, icons=None) -> ClusterBadge | None:
    """One corner badge with its artwork resolved, or None when the artwork
    is missing. A badge that names no collection is looked up in ``icons``,
    the diagram's own library."""
    try:
        if badge.collection:
            icon = load_icon_set(badge.collection).find(badge.icon)
        elif icons is not None:
            icon = icons.find(badge.icon)
        else:
            return None
    except (KeyError, ValueError):
        return None
    return ClusterBadge(icon=icon, label=badge.label, side=badge.side, offset=badge.offset)


def cluster_icon_for(element: TopologyElement, icons, style: Style) -> ProviderIcon | None:
    """Explicit zone artwork, then the provider preset's kind mapping."""
    explicit = icon_for(element, icons, explicit_only=True)
    if explicit is not None:
        return explicit
    reference = style.cluster.icon_for(element.type)
    if not reference:
        return None
    collection, separator, slug = reference.partition(":")
    if not separator or not collection or not slug:
        raise ValueError(
            f"zone icon for {element.type!r} must be collection-qualified; got {reference!r}"
        )
    pack = load_icon_set(collection)
    return pack[slug] if "#" in slug else pack.find(slug)


def display_of(
    element: TopologyElement, default: str = "card", icon: ProviderIcon | None = None
) -> str:
    """How this element draws: its own saved choice, else bare when the
    rules say its component draws bare, else the project's look.

    The rules live in ``assets/catalog/display-defaults.json``:
    resource-tier glyphs, the decks' general icons, actors and endpoints,
    generic hardware and the shared line-art primitives draw bare; service
    tiles, logos and Kubernetes objects keep the card. Every renderer
    resolves through this function, so a node looks the same in the editor,
    in every export and in the static fallback. ``editor_display_mode`` on
    the node still wins.
    """
    from ..catalog.display import default_display

    own = element.attributes.get("editor_display_mode")
    if own in ("card", "icon"):
        return str(own)
    component = element.component
    resolved = default_display(
        component.provider if component is not None else None,
        component.service_id if component is not None else None,
        tier=getattr(icon, "tier", None),
        category=getattr(icon, "category", None),
    )
    return "icon" if resolved == "icon" else default


def _card_colours(element: TopologyElement) -> dict[str, str]:
    """The fill and stroke a card is painted in when the editor would paint
    it so: the author's own (``editor_style``), else a plan's change."""
    from ..models.changes import style_of

    style = element.attributes.get("editor_style")
    style = style if isinstance(style, dict) else style_of(element.attributes) or {}
    # a colour that is not one never reaches an attribute (verification.SAFE_COLOUR)
    return {key: value for key in ("fill", "stroke") if (value := safe_colour(style.get(key)))}


#: Types a document leaves at the generic word: they draw no subtitle.
_GENERIC_TYPES = frozenset({"service", "node", "component", "box"})


def detail_for(element: TopologyElement) -> str:
    """Subtitle text: an explicit attribute, else the type and role, headed
    by what a plan does to the element (changes.py)."""
    from ..models.changes import detail_with_change

    explicit = element.attributes.get("detail")
    if explicit:
        return detail_with_change(str(explicit), element.attributes)
    if element.type in _GENERIC_TYPES and not element.role:
        # "service" under a card says nothing its icon and name do not
        return detail_with_change("", element.attributes)
    bits = [element.type.replace("_", " ")]
    if element.role:
        bits.append(element.role)
    return detail_with_change(" · ".join(bits), element.attributes)


def from_topology(
    root: TopologyElement,
    theme: Theme,
    *,
    slug: str,
    title: str,
    desc: str,
    icons=None,
    style: Style | None = None,
    eyebrow: str = "Architecture",
    heading: str = "",
    legend: list[tuple[str, str]] | None = None,
    flow_at_depth: tuple[Flow, ...] = ("column", "row", "column"),
    peer_kind: str = "dotted",
    peer_label: str = "PEERED",
    display: str = "card",
    provider: str = "",
    status: str = "",
    notes: tuple[str, ...] = (),
    drawn_on: str = "",
    crossings: str = "plain",
    frame_lines: str = "thin",
    tones: list[tuple[str, str]] | None = None,
) -> Scene:
    """Map a topology onto a placed Scene, ready to render.

    ``flow_at_depth`` alternates the layout axis by nesting level, which is
    what stops a deep tree collapsing into one very tall column.

    ``display`` is the project-wide default for how a component draws; an
    element's own ``editor_display_mode`` attribute wins over it, so a page
    edited by hand keeps the per-card choices the author made.

    ``provider`` is the library the project opens in. A frame placed from
    another gallery (``editor_frame_group``) keeps that gallery's look, the
    way the editor draws it; frames of the project's own library draw with
    ``style`` and ``theme`` as given.

    A layout the editor saved (``editor_x``/``editor_y``) outranks the
    placement: the picture is the drawing as it was left, while it still
    describes the looks being drawn (builders/saved_geometry.py).
    """
    scene = Scene(
        slug=slug,
        theme=theme,
        title=title,
        desc=desc,
        eyebrow=eyebrow,
        heading=heading,
        status=status,
        notes=tuple(notes),
        drawn_on=drawn_on,
        crossings=crossings,
        frame_lines=frame_lines,
        style=style or Style(),
        legend=list(legend or ()),
        tones=list(tones or ()),
        order={element.id: index for index, element in enumerate(root.walk())},
    )
    drawn: dict[str, Node] = {}

    #: The roles a palette paints the ground and the words with; a gallery's
    #: own theme keeps its colours and takes these from the scene, so a frame
    #: from another library is drawn on the same ground as everything else.
    ground_roles = ("paper", "paper_2", "ink", "muted", "soft")

    def frame_look(group: str) -> tuple[Style, Theme | None]:
        """The style a frame from ``group`` draws with, and the theme when it
        is not the scene's own. The core frames' ``generic`` gallery draws
        with the on-premises look, as the editor's gallery does."""
        library = "onprem" if group == "generic" else group
        if library and library != provider:
            look = load_theme(library)
            if scene.theme.dark:
                # Any: the checker cannot tie each role name to its own field
                ground: dict[str, Any] = {role: scene.theme[role] for role in ground_roles}
                look = replace(look, dark=True, **ground)
            return load_style(library), look
        return scene.style, None

    def build_into(
        parent: Cluster, element: TopologyElement, depth: int, parent_declared: str | None = None
    ) -> None:
        if not element.is_frame:
            icon = icon_for(element, icons)
            detail = detail_for(element)
            # several detail lines, compartments, a shape or a tone make a
            # panel, as a Box always is: a box whatever the diagram's display
            # (panels.py)
            panel = panel_of(element.attributes, detail, boxed=element.type == "box")
            drawn[element.id] = parent.node(
                name=element.name,
                ref=element.id,
                detail=detail,
                icon=icon,
                focal=element.role == "hub",
                accent=accent_for(element, scene.style),
                display="card" if panel.active else display_of(element, display, icon),
                flagged=bool(element.attributes.get("unused")),
                panel=panel if panel.active else None,
                **_card_colours(element),
            )
            return
        forbidden = scene.style.cluster.forbidden_kinds.get(element.type)
        if forbidden:
            raise ValueError(
                f"{element.name!r} uses forbidden zone kind {element.type!r}: {forbidden}"
            )
        # A group may state its own axis. Otherwise the level below a declared
        # axis takes the opposite one, so a row of frames holds columns of
        # cards; without any declaration the depth decides.
        declared = element.attributes.get("flow")
        flow: Flow
        if declared in ("row", "column", "grid"):
            flow = cast(Flow, str(declared))
        elif parent_declared in ("row", "column"):
            flow = "column" if parent_declared == "row" else "row"
        else:
            flow = flow_at_depth[min(depth, len(flow_at_depth) - 1)]
        # A zone keeps its own artwork: a container is still a service; a
        # frame from another gallery keeps that gallery's look.
        group = str(element.attributes.get("editor_frame_group") or "")
        look, look_theme = frame_look(group)
        cluster = parent.cluster(
            element.name,
            flow=flow,
            kind=element.type,
            ref=element.id,
            highlight=bool(element.attributes.get("editor_highlight")),
            group=group,
            look_style=look.cluster if look_theme is not None else None,
            look_theme=look_theme,
            keep_order=element.attributes.get("arrange") == "manual",
            icon=cluster_icon_for(element, icons, look),
            badges=[
                drawn for drawn in (badge_for(badge, icons) for badge in element.badges) if drawn
            ],
            auto=declared not in ("row", "column", "grid"),
            wrap=max(0, int(element.attributes.get("grid") or 0)),
        )
        for child in element.children:
            build_into(
                cluster,
                child,
                depth + 1,
                flow
                if declared in ("row", "column") or parent_declared in ("row", "column")
                else None,
            )
        if not element.children:
            # An empty frame has no content to size it: keep the size the
            # editor saved, else the catalog default for its kind.
            width, height = architecture_boundary_default_size(element.type)
            cluster.width = int(element.attributes.get("editor_width", width))
            cluster.height = int(element.attributes.get("editor_height", height))

    # The root element is a frame, not a box: its children sit side by side,
    # and the levels below take the depth defaults. ``Diagram(direction="down")``
    # stacks them instead; under that declared axis the level below takes the
    # opposite one, so a tier without an axis of its own is a row.
    stacked = root.attributes.get("flow") == "column"
    if stacked:
        scene.root.flow = "column"
    # A top level whose direction nobody declared may wrap when it runs long.
    scene.root.auto = root.attributes.get("flow") not in ("row", "column")
    for child in root.children or [root]:
        build_into(scene.root, child, 0, "column" if stacked else None)

    # Declared links: the other axis. Containment came from >>; these are
    # the arrows that say what talks to what, anywhere in the tree.
    #: Wires with a frame at one end, and the cards each end could seat on.
    frame_seated: list[tuple[Link, list[Node], list[Node]]] = []
    for element in root.walk():
        source = first_drawn(element, drawn)
        if source is None:
            if element.connections:
                # Silently dropping a link loses a fact the author stated.
                raise ValueError(
                    f"{element.name!r} links out but has nothing drawn to seat a wire on; "
                    f"put a node in it or link from a node"
                )
            continue
        for conn in element.connections:
            target_el = root.first(id=conn.target)
            if target_el is None:
                # It happens when .to() captured an id that later changed,
                # or names a node outside this tree.
                raise ValueError(
                    f"{element.name!r} links to unknown id {conn.target!r}; "
                    f"the target is not in this topology"
                )
            if conn.kind not in scene.style.links:
                raise ValueError(
                    f"{element.name!r} links to {target_el.name!r} with unknown kind {conn.kind!r}; "
                    f"this document's libraries know {', '.join(sorted(scene.style.links))}"
                )
            target = first_drawn(target_el, drawn)
            if target is None:
                raise ValueError(
                    f"{element.name!r} links to {target_el.name!r}, which has nothing drawn "
                    f"to seat a wire on; put a node in it or link to a node"
                )
            if target is source:
                raise ValueError(
                    f"{element.name!r} links to {target_el.name!r}, which draws as the same "
                    f"node (a frame and its first node); link between two nodes instead"
                )
            # The wire's editor style names its head, bend, colour, width
            # and pinned sides; both renderers read the same keys. It is not
            # called ``style``: that is this function's own Style argument.
            styles = element.attributes.get("editor_edge_styles")
            found = styles.get(conn.target) if isinstance(styles, dict) else None
            edge_style: dict[str, Any] = found if isinstance(found, dict) else {}
            stroke = edge_style.get("stroke")
            width = edge_style.get("width")
            sides = {
                name: edge_style.get(key) if edge_style.get(key) in _SIDES else None
                for name, key in (("source_side", "source_port"), ("target_side", "target_port"))
            }
            # The connection's own direction and pinned corners travel too,
            # so the static picture wears the heads and turns where the
            # editor does.
            placement = conn.label_placement
            link = scene.link(
                source,
                target,
                kind=conn.kind,
                label=conn.label,
                direction=conn.direction,
                step=conn.step,
                step_text=conn.step_text,
                step_flow=conn.step_flow,
                waypoints=tuple((point.x, point.y) for point in conn.waypoints),
                label_offset=(
                    (placement.dx, placement.dy)
                    if placement is not None and placement.mode == "manual"
                    else None
                ),
                arrow=edge_style.get("arrow"),
                corners=edge_style.get("corners"),
                stroke=safe_colour(stroke),
                width=float(width) if isinstance(width, (int, float)) and 0 < width <= 40 else None,
                **sides,
            )
            # Which card a frame-aimed wire lands on is only knowable once
            # everything is placed, so remember the candidates for later.
            ends = (drawn_within(element, drawn), drawn_within(target_el, drawn))
            if len(ends[0]) > 1 or len(ends[1]) > 1:
                frame_seated.append((link, *ends))

    # A drawing tells two flows apart, its main one and one named second.
    flows = sorted(
        {link.step_flow for link in scene.links if link.step is not None and link.step_flow}
    )
    if len(flows) > 1:
        raise ValueError(
            f"steps name {len(flows)} second flows ({', '.join(map(repr, flows))}): "
            f"a drawing tells its main flow and one named second flow apart"
        )

    hub = root.first(role="hub")
    if hub is not None:
        hub_node = first_drawn(hub, drawn)
        for spoke in root.find(role="spoke"):
            target = first_drawn(spoke, drawn)
            if hub_node is not None and target is not None and target is not hub_node:
                scene.link(hub_node, target, kind=peer_kind, label=peer_label)

    scene = place(scene)
    # Pull connected siblings towards each other so wires run between
    # neighbours instead of across a card. Two rounds settle the usual tree;
    # the author's top-level order is the story and is never touched.
    for _ in range(2):
        if not reorder_by_connections(scene):
            break
        scene = place(scene)
    # What a reader moved in the editor outranks all of that: the picture is
    # the drawing as it was left (builders/saved_geometry.py).
    if apply_to_scene(root, scene, display=display):
        scene.saved_layout = True
        scene = size_to_content(scene)
    # The editor opens every drawing on its grid, and every export is the
    # editor's picture; the static one stands on the same grid.
    snap_to_grid(scene)
    # Last, so the nearest card is nearest in the picture as it finally stands.
    _reseat_frame_links(frame_seated)
    return scene


def _axis(item: Node | Cluster, flow: str) -> float:
    if flow == "row":
        return item.x + (item.width or 0) / 2
    return item.y + (item.height or 0) / 2


def reorder_by_connections(scene: Scene) -> bool:
    """Sort each nested cluster's children by where their links point.

    A child's key is the mean position, along the cluster's flow axis, of the
    nodes it links to *outside the cluster*; links between siblings do not
    count, because two siblings that only talk to each other would otherwise
    swap places on every pass. A child with no outside links keeps its own
    position, so unlinked siblings stay put relative to each other. The scene
    root and clusters marked ``keep_order`` are left as authored. Returns
    whether any cluster changed.
    """
    partners: dict[int, list[Node]] = {}
    for link in scene.links:
        partners.setdefault(id(link.source), []).append(link.target)
        partners.setdefault(id(link.target), []).append(link.source)
    if not partners:
        return False
    changed = False
    for cluster in scene.root.clusters():
        if cluster is scene.root or cluster.keep_order or len(cluster.children) < 2:
            continue
        # A grid fills left to right, so its children sort along the row.
        flow = "row" if cluster.arranged == "grid" else cluster.flow
        inside = {id(node) for node in cluster.walk()}

        def sort_key(
            indexed: tuple[int, Node | Cluster], *, inside: set[int] = inside, flow: str = flow
        ) -> tuple[float, int]:
            index, child = indexed
            outside = [
                partner
                for node in child.walk()
                for partner in partners.get(id(node), ())
                if id(partner) not in inside
            ]
            if not outside:
                return (_axis(child, flow), index)
            return (sum(_axis(partner, flow) for partner in outside) / len(outside), index)

        # Nothing in it links out: there is nothing to pull, and sorting a grid
        # by its own positions would shuffle its rows.
        if not any(
            id(partner) not in inside
            for node in cluster.walk()
            for partner in partners.get(id(node), ())
        ):
            continue
        ordered = [child for _, child in sorted(enumerate(cluster.children), key=sort_key)]
        if any(a is not b for a, b in zip(ordered, cluster.children, strict=True)):
            cluster.children = ordered
            changed = True
    return changed


def first_drawn(element: TopologyElement, drawn: dict[str, Node]) -> Node | None:
    """The node drawn for this element, or its first drawn descendant."""
    for candidate in element.walk():
        node = drawn.get(candidate.id)
        if node is not None:
            return node
    return None


def drawn_within(element: TopologyElement, drawn: dict[str, Node]) -> list[Node]:
    """Every node drawn for this element or inside it, in the author's order.

    One for a node, several for a frame: the candidates a wire aimed at that
    frame could seat on.
    """
    return [node for candidate in element.walk() if (node := drawn.get(candidate.id)) is not None]


def _reseat_frame_links(seated: list[tuple[Link, list[Node], list[Node]]]) -> None:
    """Move each frame-aimed wire onto the nearest card, now that all are placed.

    Nothing moves as a result -- the cards are where the layout left them and
    only the wire's ends change -- so this runs last, after the reordering
    passes and after any geometry the reader saved.
    """
    for link, sources, targets in seated:
        if len(targets) > 1:
            seat = seat_toward(targets, link.source)
            if seat is not None and seat is not link.source:
                link.target = seat
        if len(sources) > 1:
            seat = seat_toward(sources, link.target)
            if seat is not None and seat is not link.target:
                link.source = seat


#: Where the shipped skill keeps its themes and icon collections.
#: Resolved rather than counted, and overridable for installed copies.
SKILL_ASSETS = skill_assets()


def load_theme(name: str, assets: Path | None = None) -> Theme:
    """Read a provider canvas theme by slug."""
    root = assets or SKILL_ASSETS
    manifest = theme_manifest(name, root)
    # A skin may state its own heading treatment; most inherit the default.
    type_style = TypeStyle(**manifest["typography"]) if manifest.get("typography") else None
    # A mark may be a path under themes/, or a "collection:slug" reference
    # to real brand artwork -- the same spelling badges and zone icons use.
    # "brand" is the lockup drawn on a diagram; "mark" is the small glyph
    # the provider catalog uses, and is a themes-relative path by contract.
    mark = str(manifest.get("brand") or manifest.get("mark") or "")
    if ":" in mark:
        collection, _, slug = mark.partition(":")
        try:
            pack = load_icon_set(collection)
            # "#variant" only resolves through __getitem__; find() is by name.
            found = pack[slug] if "#" in slug else pack.find(slug)
            mark = str(found.path)
        except (KeyError, ValueError):
            mark = ""
    elif mark:
        mark = str((root / "themes" / mark).resolve())
    return Theme.from_colors(
        manifest["theme"],
        type=type_style,
        # Pictures sit on plain paper, as every vendor's own reference
        # diagrams do; a theme may still ask for the dot field.
        dots=bool(manifest.get("dots", False)),
        mark=mark,
        step=str(manifest.get("step_color") or ""),
        step_second=StepMark.model_validate(manifest["step_second"])
        if manifest.get("step_second")
        else None,
    )


def load_style(name: str, assets: Path | None = None) -> Style:
    """Read a provider's topology style, including boundary semantics.

    Provider manifests are the durable source of truth. A provider without a
    ``boundaries`` block receives the house defaults; AWS owns a complete
    boundary preset so new ``theme="aws"`` builds cannot drift into generic
    grey nesting or lose the Region/subnet tabs.
    """
    root = assets or SKILL_ASSETS
    manifest = theme_manifest(name, root)
    raw = manifest.get("boundaries")
    if raw is None:
        return Style()
    if not isinstance(raw, dict):
        raise ValueError(f"provider {name!r} boundaries must be an object")
    cluster = ClusterStyle(**raw)
    for kind, reference in cluster.icons.items():
        collection, separator, slug = reference.partition(":")
        if not separator or not collection or not slug:
            raise ValueError(
                f"provider {name!r} boundary icon {kind!r} must be collection-qualified"
            )
        pack = load_icon_set(collection, root)
        try:
            pack[slug] if "#" in slug else pack.find(slug)
        except (KeyError, ValueError) as error:
            raise ValueError(
                f"provider {name!r} boundary icon {kind!r} does not resolve: {reference}"
            ) from error
    typography = manifest.get("typography", {})
    if typography is not None and not isinstance(typography, dict):
        raise ValueError(f"provider {name!r} typography must be an object")
    font = typography.get("font") if typography and cluster.label_font == "sans" else None
    raw_style = manifest.get("style", {})
    if raw_style is not None and not isinstance(raw_style, dict):
        raise ValueError(f"provider {name!r} style must be an object")
    style_fields = dict(raw_style or {})
    raw_links = style_fields.pop("links", None)
    if font:
        style_fields["sans"] = font
    style = Style(cluster=cluster, **style_fields)
    if raw_links is not None:
        if not isinstance(raw_links, dict):
            raise ValueError(f"provider {name!r} style links must be an object")
        for kind, link_style in raw_links.items():
            if not isinstance(link_style, dict):
                raise ValueError(f"provider {name!r} link style {kind!r} must be an object")
            style.links[str(kind)] = LinkStyle(**link_style)
    return style


#: A collection is one directory name under the assets tree.
_COLLECTION_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


@cache
def load_icon_set(name: str, assets: Path | None = None):
    """An IconSet for a vendor pack, or for the shared logo collection.

    The name reaches this function from a project document, so it must name a
    collection and nothing else: a separator or a parent reference here would
    walk out of the assets tree and read whatever it landed on.
    """
    from ..registries.icons import IconSet

    if not _COLLECTION_NAME.fullmatch(name or ""):
        raise KeyError(f"invalid icon collection name: {name!r}")
    root = (assets or SKILL_ASSETS).resolve()
    for candidate in (root / "icons" / "vendors" / name, root / "icons" / name):
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            continue
        if (resolved / "catalog.json").is_file():
            return IconSet(name, resolved)
    raise KeyError(f"no icon collection named {name!r} under {root / 'icons'}")


def _merge_provider_style(provider: Style, override: Style | None) -> Style:
    """Overlay caller customization on provider defaults without losing maps."""
    if override is None:
        return provider
    merged = override.model_copy(deep=True)
    generic = ClusterStyle()
    provider_fields = provider.cluster.model_fields_set
    override_fields = override.cluster.model_fields_set
    mapping_fields = ("colors", "fills", "dashes", "widths", "radii", "icons", "forbidden_kinds")
    for field in mapping_fields:
        base_values = dict(getattr(provider.cluster, field))
        override_values = dict(getattr(override.cluster, field))
        if field not in override_fields:
            generic_values = dict(getattr(generic, field))
            override_values = {
                key: value
                for key, value in override_values.items()
                if key not in generic_values or generic_values[key] != value
            }
        base_values.update(override_values)
        setattr(merged.cluster, field, base_values)
    for field in provider_fields - set(mapping_fields):
        if field not in override_fields:
            setattr(merged.cluster, field, getattr(provider.cluster, field))
    # A caller commonly creates Style() only to add link kinds. That must not
    # silently discard the provider's standard type stack (or future explicit
    # top-level provider defaults). Explicit caller fields still win.
    for field in provider.model_fields_set - {"cluster"}:
        if field not in override.model_fields_set:
            setattr(merged, field, getattr(provider, field))
    return merged


def build(scene: Scene, out: Path) -> Path:
    """Write a placed scene through the current static renderer."""
    out.write_text(render(scene), encoding="utf-8", newline="\n")
    return out


def build_topology(
    root: TopologyElement,
    out: Path,
    *,
    slug: str,
    title: str,
    desc: str,
    theme: str | Theme = "azure",
    icons: str | None = None,
    assets: Path | None = None,
    **kwargs,
) -> Path:
    """Topology in, HTML file out.

    Collapses the boilerplate every build script repeated: resolve the theme
    and icon collection by name, map, place, render, write. `icons` defaults
    to the theme name, which is right whenever a skin and a vendor pack share
    a slug.
    """
    assets = assets or SKILL_ASSETS
    resolved = theme if isinstance(theme, Theme) else load_theme(theme, assets)
    requested_style = kwargs.pop("style", None)
    style = requested_style
    if isinstance(theme, str):
        style = _merge_provider_style(load_style(theme, assets), requested_style)
    collection = (
        load_icon_set(icons or (theme if isinstance(theme, str) else ""), assets)
        if (icons or isinstance(theme, str))
        else None
    )
    scene = from_topology(
        root, resolved, slug=slug, title=title, desc=desc, icons=collection, style=style, **kwargs
    )
    return build(scene, out)
