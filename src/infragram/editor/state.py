"""The portable graph the browser edits, built from a placed scene.

:func:`_editor_state` is the one place topology elements and placed scene
geometry are married: every card, frame, wire and layer the runtime needs,
in the order the document declares them.
"""

from __future__ import annotations

from typing import Any, cast

from ..builders.saved_geometry import aligned as _aligned, is_current as _geometry_is_current
from ..builders.scene import GRID, Scene, on_grid, seat_toward
from ..catalog import ARCHITECTURE_BOUNDARY_SPECS, ink, load_default_provider_registry
from ..models.changes import style_of
from ..projects import CloudProject
from ..projects.document import _is_platform
from ..verification import safe_colour
from .artwork import (
    _boundary_component_style,
    _data_uri,
    artwork_bytes,
    frame_visual,
)

#: The sides a wire's end may be pinned to; anything else is "auto".
_PINNED_SIDES = ("top", "right", "bottom", "left")


#: The keys of a stored style that the page writes into a colour attribute
#: (and the draw.io download into a style string).
_PAINT_KEYS = frozenset({"fill", "stroke", "label", "labelColor", "tabFill", "color"})


def _paint_checked(style: dict[str, Any]) -> dict[str, Any]:
    """A stored style without any colour that is not a colour.

    A document is shared as a file: a fill of ``red" onload="...`` came
    from someone else and is dropped, so the card takes the library's look.
    """
    return {
        key: value
        for key, value in style.items()
        if key not in _PAINT_KEYS or value is None or safe_colour(value) is not None
    }


def _pinned_side(element, connection, key: str) -> str:
    """The side the author gave this end, or ``auto`` to let the wire route.

    Kept beside the wire's style in ``editor_edge_styles``, the one bag both
    renderers already read a wire's editor extras from.
    """
    styles = element.attributes.get("editor_edge_styles")
    style = styles.get(connection.target) if isinstance(styles, dict) else None
    side = style.get(key) if isinstance(style, dict) else None
    return side if side in _PINNED_SIDES else "auto"


def _editor_state(
    project: CloudProject,
    scene: Scene,
    library_payload: dict[str, object],
) -> dict[str, object]:
    """Build the portable browser graph from placed scene geometry."""

    # The payload is the JSON the sidebar reads: its components are a list.
    components = cast("list[object]", library_payload.get("components", []))
    artwork_by_component = {
        str(component["qualifiedId"]): str(component.get("iconUri") or "")
        for component in components
        if isinstance(component, dict) and component.get("qualifiedId")
    }
    tier_by_component = {
        str(component["qualifiedId"]): str(component.get("tier") or "service")
        for component in components
        if isinstance(component, dict) and component.get("qualifiedId")
    }
    default_display_by_component = {
        str(component["qualifiedId"]): str(component.get("defaultDisplay") or "card")
        for component in components
        if isinstance(component, dict) and component.get("qualifiedId")
    }
    layers = [layer.model_dump(mode="json") for layer in project.layers]
    if not layers:
        # Named as the library names itself, as the editor names a layer it
        # adds (ensureProviderLayer): "AWS" and "Local & On-Premises", where
        # title-casing the id gave "Aws" and "Onprem".
        registry = load_default_provider_registry()
        layers = [
            {
                "id": f"provider:{provider.id}",
                "name": registry[provider.id].display_name,
                # The registry classifies every provider: platforms are not
                # clouds, and there is more than one of them. This is the
                # project's selection, so the kind is looked up by id.
                "kind": "platform" if _is_platform(provider.id) else "provider",
                "provider": provider.id,
                "visible": True,
                "locked": False,
                "order": index,
            }
            for index, provider in enumerate(project.providers)
        ]
    layer_by_provider = {
        str(layer["provider"]): str(layer["id"]) for layer in layers if layer.get("provider")
    }
    fallback_layer = str(layers[0]["id"]) if layers else None

    # Frames and cards split by is_frame, not by children: an empty frame the
    # editor saved must come back as a boundary, never as a component card.
    elements = [element for element in project.topology.walk() if not element.is_frame]
    scene_nodes = _aligned(elements, list(scene.root.walk()), "placed scene nodes")

    # Saved positions describe nodes at the size they were saved with. A card
    # placed by hand that the display rules now draw bare is a 144 x 116 icon
    # node at coordinates chosen for a 208 x 72 card, and it lands on the row
    # below. When any node with saved geometry resolves to a look other than
    # the one it was saved under, every saved coordinate in the document is
    # stale together -- a partial re-layout cannot work -- and the layout
    # places the document instead. A page saved by the editor records the
    # mode per node, so its geometry stays trusted until the rules change.
    saved_geometry_current = _geometry_is_current(
        elements, scene_nodes, project.presentation.display
    )

    # Any: a saved value is whatever the document's attributes hold.
    def saved(element, key: str, default: object) -> Any:
        return element.attributes.get(key, default) if saved_geometry_current else default

    boundary_elements = [
        element
        for element in project.topology.walk()
        if element is not project.topology and element.is_frame
    ]
    scene_boundaries = _aligned(
        boundary_elements,
        [cluster for cluster in scene.root.clusters() if cluster is not scene.root],
        "placed scene clusters",
    )

    cs = scene.style.cluster

    def boundary_visual(kind: str, depth: int) -> dict[str, object]:
        """One frame's look, from the derivation every renderer shares.

        The badge artwork comes with it (``frame_visual`` resolves the tab
        glyph), so no frame reads its icon file a second time here."""
        return frame_visual(cs, scene.theme, kind, depth=depth)

    boundaries: list[dict[str, object]] = []
    for element, cluster in zip(boundary_elements, scene_boundaries, strict=True):
        parent = project.topology.parent_of(element)
        x = int(saved(element, "editor_x", cluster.x))
        y = int(saved(element, "editor_y", cluster.y))
        width = int(saved(element, "editor_width", cluster.width))
        height = int(saved(element, "editor_height", cluster.height))
        # A frame placed from a library's gallery belongs to that library --
        # its layer, its "Library" in the inspector -- as the one dropped in
        # the editor does (addBoundary). Credited to the project's first
        # library instead, an AWS frame in an on-premises project sat on the
        # on-premises layer, and hiding the AWS layer left its frames behind.
        # The core frames' ``generic`` gallery is no library of its own.
        frame_library = str(element.attributes.get("editor_frame_group") or "")
        component_provider = (
            element.component.provider
            if element.component is not None
            else frame_library
            if frame_library in project.provider_ids
            else project.provider
        )
        component_qualified_id = (
            element.component.icon_ref if element.component is not None else None
        )
        # Deliberately not artwork_by_component here. A frame component's
        # artwork is its gallery preview -- a 120x72 picture of a framed
        # box, built for the sidebar. Squeezed into the 16px corner tab it
        # renders as an unreadable dark smudge. The tab wants the group's
        # own glyph, which cluster.icon and _boundary_component_style
        # already resolve.
        frame_group = element.attributes.get("editor_frame_group")
        if frame_group:
            # A frame placed from a library gallery keeps that gallery's look
            # (tab, glyph, colour, dash) even when the project's theme has no
            # boundary treatment of its own for the kind, so an on-premises
            # site draws like the catalog frame, not like a plain dotted box.
            visual = _boundary_component_style(str(frame_group), element.type)
        else:
            visual = boundary_visual(element.type, cluster.depth)
        boundary_state = {
            "id": element.id,
            "parentId": parent.id
            if parent is not None and parent is not project.topology
            else None,
            "name": element.name,
            "kind": element.type,
            "x": on_grid(x),
            "y": on_grid(y),
            "width": on_grid(width),
            "height": on_grid(height),
            "minWidth": max(160, cs.pad * 2 + 80),
            "minHeight": max(104, cs.pad * 2 + 56),
            "componentProvider": component_provider,
            "componentQualifiedId": component_qualified_id,
            "layerId": (
                element.layer_id or layer_by_provider.get(component_provider) or fallback_layer
            ),
            "attributes": dict(element.attributes),
            **visual,
        }
        if isinstance(element.attributes.get("editor_style"), dict):
            boundary_state["style"] = _paint_checked(element.attributes["editor_style"])
        if isinstance(element.attributes.get("editor_boundary_style"), dict):
            # A stored style is a cache of the library look, not an override:
            # the theme owns every key the visual carries, so a document saved
            # under an older rule cannot drag stale paint into the picture.
            stored = _paint_checked(element.attributes["editor_boundary_style"])
            boundary_state.update(
                {key: value for key, value in stored.items() if key not in visual}
            )
        if element.attributes.get("editor_frame_group"):
            boundary_state["frameGroup"] = str(element.attributes["editor_frame_group"])
        # Corner badges: what applies to the frame (a subnet's NSG, its route
        # table), drawn on its top-right corner. The spec rides along so a
        # saved page keeps it. A badge whose artwork is missing is not drawn,
        # so specs and drawn badges pair by label, never by position.
        specs = list(element.badges)
        badges = []
        for drawn in cluster.badges:
            spec = next(
                (item for item in specs if item.label == drawn.label and item.side == drawn.side),
                None,
            )
            if spec is None:
                continue
            specs.remove(spec)
            markup = getattr(drawn.icon, "markup", None)
            badges.append(
                {
                    "icon": spec.icon,
                    "collection": spec.collection,
                    "label": spec.label,
                    "side": spec.side,
                    "offset": spec.offset,
                    "iconUri": _data_uri(
                        markup.encode("utf-8") if markup else drawn.icon.path.read_bytes()
                    ),
                }
            )
        if badges:
            boundary_state["badges"] = badges
        for attribute, key in (
            ("editor_order", "order"),
            ("editor_locked", "locked"),
            ("editor_user_group", "userGroup"),
            ("editor_angle", "angle"),
            ("editor_highlight", "highlight"),
            ("editor_flip_x", "flipX"),
            ("editor_flip_y", "flipY"),
        ):
            if attribute in element.attributes:
                boundary_state[key] = element.attributes[attribute]
        if isinstance(element.attributes.get("editor_text_style"), dict):
            boundary_state["textStyle"] = dict(element.attributes["editor_text_style"])
        boundaries.append(boundary_state)

    # Sorted, because a set's iteration order is randomised per process: the
    # same document exported twice produced two different pages, differing
    # only in the order of these keys. Nothing read them in order, so nothing
    # broke -- but an export nobody can reproduce cannot be diffed, cached or
    # checked against the copy somebody else made.
    boundary_styles = {
        kind: boundary_visual(kind, 0)
        for kind in sorted(
            {
                "group",
                "cloud",
                "region",
                "vpc",
                "zone",
                "subnet-public",
                "subnet-private",
                "location",
                "site",
            }
            | {item[3] for item in ARCHITECTURE_BOUNDARY_SPECS}
        )
    }

    nodes: list[dict[str, object]] = []
    # A wire may be aimed at a frame, but only a drawn card can carry an end
    # of one, so the frame resolves to a card inside it. Every card it could
    # seat on is kept, in the author's order, and the placed scene decides
    # which -- the same rule the static renderer seats by (scene.seat_toward).
    seats: dict[str, list[str]] = {}
    for element in project.topology.walk():
        leaves = [candidate.id for candidate in element.walk() if not candidate.is_frame]
        if leaves:
            seats[element.id] = leaves
    placed = {element.id: node for element, node in zip(elements, scene_nodes, strict=True)}

    def _seat(element_id: str | None, toward) -> tuple[str | None, object]:
        """The card this end of a wire sits on, nearest ``toward``, and its node."""
        candidates = seats.get(element_id or "", [])
        if not candidates:
            return None, None
        if len(candidates) == 1:
            return candidates[0], placed.get(candidates[0])
        anchors = [placed[cid] for cid in candidates if cid in placed]
        chosen = seat_toward(anchors, toward)
        if chosen is None:
            return candidates[0], placed.get(candidates[0])
        picked = next((cid for cid in candidates if placed.get(cid) is chosen), candidates[0])
        return picked, placed.get(picked)

    for element, node in zip(elements, scene_nodes, strict=True):
        parent = project.topology.parent_of(element)
        markup = getattr(node.icon, "markup", None) if node.icon else None
        icon_uri = (
            _data_uri(markup.encode("utf-8") if markup else node.icon.path.read_bytes())
            if node.icon
            else ""
        )
        component_id = (
            element.component.service_id
            if element.component is not None
            else node.icon.slug
            if node.icon
            else str(element.attributes.get("icon") or element.type)
        )
        component_provider = (
            element.component.provider if element.component is not None else project.provider
        )
        component_qualified_id = (
            element.component.icon_ref
            if element.component is not None
            else f"{component_provider}:{component_id}"
        )
        if not element.attributes.get("iso_artwork"):
            icon_uri = artwork_by_component.get(component_qualified_id or "", icon_uri)
        x = int(saved(element, "editor_x", node.x))
        y = int(saved(element, "editor_y", node.y))
        card_size = saved(element, "editor_card_size", None)
        if not isinstance(card_size, dict):
            card_size = {}
        # A saved card size describes a card. When the project draws icons,
        # a bare mark must not inherit the wide box a card was stretched to;
        # the scene already sized it for its caption.
        if node.display == "icon":
            card_size = {}
        node_state = {
            "id": element.id,
            "componentId": component_id,
            "componentProvider": component_provider,
            "componentQualifiedId": component_qualified_id,
            "name": element.name,
            "detail": node.detail,
            "type": element.type,
            "category": str(element.attributes.get("category") or "custom"),
            "iconUri": icon_uri,
            # Where this icon's ink starts inside its square, so a wire
            # touches the mark and not the air.
            "ink": ink.profile(artwork_bytes(icon_uri)),
            # ...and where it begins along every line of each side, so a
            # link is seated on the drawing itself, wherever it falls.
            "inkEdges": ink.edges(artwork_bytes(icon_uri)),
            # ...and the sides whose one connection point is set by hand.
            "inkPorts": ink.ports(artwork_bytes(icon_uri)),
            "x": on_grid(x),
            "y": on_grid(y),
            # A card size saved in the editor wins over the scene's default
            # so a widened card reopens widened instead of truncating again.
            "width": int(card_size.get("width") or node.width or scene.style.node.width),
            "height": int(card_size.get("height") or node.height or scene.style.node.height),
            "layerId": (
                element.layer_id or layer_by_provider.get(component_provider) or fallback_layer
            ),
            "boundaryId": (
                parent.id if parent is not None and parent is not project.topology else None
            ),
            "attributes": dict(element.attributes),
        }
        if isinstance(element.attributes.get("editor_style"), dict):
            node_state["style"] = _paint_checked(element.attributes["editor_style"])
        elif style_of(element.attributes):
            # a plan's change paints the card; the static picture reads the
            # same colours (builders/architecture.py _card_colours)
            node_state["style"] = style_of(element.attributes)
        for attribute, key in (
            ("editor_order", "order"),
            ("editor_locked", "locked"),
            ("editor_angle", "angle"),
            ("editor_flip_x", "flipX"),
            ("editor_flip_y", "flipY"),
        ):
            if attribute in element.attributes:
                node_state[key] = element.attributes[attribute]
        if isinstance(element.attributes.get("editor_text_style"), dict):
            node_state["textStyle"] = dict(element.attributes["editor_text_style"])
        # The scene already resolved how this node draws -- its own saved
        # choice, else bare for a resource-tier glyph, else the project's look
        # -- through the one function every renderer uses. Writing the
        # resolved mode (not just the override) means the runtime never has
        # to guess which default a saved page was drawn under.
        node_state["displayMode"] = node.display
        if node.panel is not None:
            # a panel keeps an icon square only for vendor artwork the
            # static picture draws too (builders/panels.py icon_lane)
            node_state["panelIcon"] = node.icon is not None
        node_state["tier"] = tier_by_component.get(str(component_qualified_id or ""), "service")
        node_state["defaultDisplay"] = default_display_by_component.get(
            str(component_qualified_id or ""), "card"
        )
        if isinstance(element.attributes.get("editor_card_size"), dict):
            node_state["cardSize"] = dict(element.attributes["editor_card_size"])
        nodes.append(node_state)

    index = project.topology.index()
    edges: list[dict[str, object]] = []
    for element in project.topology.walk():
        if element.id not in seats:
            continue
        for connection in element.connections:
            target_element = index.get(connection.target)
            if target_element is None:
                continue
            # Same order the static renderer re-seats in: the far end first,
            # against this end's provisional card, then this end against it.
            provisional, provisional_node = _seat(element.id, None)
            target, target_node = _seat(target_element.id, provisional_node)
            source, _ = _seat(element.id, target_node)
            if source is None or target is None or target == source:
                continue
            # The runtime paints a wire from the link-styles block the shell
            # writes (colour by kind, or the workspace ink); it reads only
            # the width and dash carried here.
            link_style = scene.style.link(connection.kind)
            edges.append(
                {
                    "id": f"edge-{len(edges) + 1}",
                    "source": source,
                    "target": target,
                    "sourcePort": _pinned_side(element, connection, "source_port"),
                    "targetPort": _pinned_side(element, connection, "target_port"),
                    "kind": connection.kind,
                    "label": connection.label,
                    "direction": connection.direction,
                    **({"step": connection.step} if connection.step is not None else {}),
                    **({"stepText": connection.step_text} if connection.step_text else {}),
                    **({"stepFlow": connection.step_flow} if connection.step_flow else {}),
                    **(
                        {
                            "waypoints": [
                                {"x": point.x, "y": point.y} for point in connection.waypoints
                            ]
                        }
                        if connection.waypoints
                        else {}
                    ),
                    "width": link_style.width,
                    "dash": link_style.dash,
                    **(
                        {"labelPlacement": connection.label_placement.model_dump(mode="json")}
                        if connection.label_placement is not None
                        and connection.label_placement.mode == "manual"
                        else {}
                    ),
                    **(
                        {
                            # the sides travel as sourcePort/targetPort above
                            "style": {
                                key: value
                                for key, value in element.attributes["editor_edge_styles"][
                                    connection.target
                                ].items()
                                if key not in ("source_port", "target_port")
                            }
                        }
                        if isinstance(element.attributes.get("editor_edge_styles"), dict)
                        and isinstance(
                            element.attributes["editor_edge_styles"].get(connection.target),
                            dict,
                        )
                        else {}
                    ),
                }
            )
    return {
        "schemaVersion": 3,
        "projectSlug": project.slug,
        "provider": project.provider,
        "providers": list(project.provider_ids),
        "layers": layers,
        "canvas": {
            "width": scene.width,
            "height": scene.height,
            "displayMode": project.presentation.display,
            "crossings": project.presentation.crossings,
            "frameLines": project.presentation.frame_lines,
            "grid": GRID,
            "visualGrid": 12,
            "gridSteps": 4,
            "minGridPixels": 10,
            # the grid is there to switch on while placing things, not to
            # sit behind every drawing: a page opens without it
            "showGrid": False,
        },
        "boundaries": boundaries,
        "boundaryStyles": boundary_styles,
        "nodes": nodes,
        "edges": edges,
        # how a numbered step is marked: the theme's main flow and second flow
        "stepColor": scene.theme.step_color,
        "stepMarks": {
            "main": scene.theme.step_mark().model_dump(),
            "second": scene.theme.step_mark(second=True).model_dump(),
        },
    }


#: Which libraries an exported editor embeds. ``project`` ships the project's
#: enabled libraries, any library their starter stacks place components from,
#: and the shared primitives and frames, which keeps a single-library export
#: to a few megabytes; ``all`` ships every installed library so the provider
#: menu can add any of them later, at roughly ten times the size.
