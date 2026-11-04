"""A layout the editor saved, read by both renderers or by neither.

What a reader moves in the editor is written back into the document:
``editor_x`` and ``editor_y`` on every element, and ``editor_width`` and
``editor_height`` on a frame. Those coordinates are the drawing as it was
left, so the page, the picture and the editor all start from them; the
layout places only what was never placed by hand.

Saved positions describe nodes at the size they were saved with. A card
placed by hand that the display rules now draw bare is a 144 x 116 icon node
at coordinates chosen for a 208 x 72 card, and it lands on the row below.
When any node with saved geometry resolves to a look other than the one it
was saved under, every saved coordinate in the document is stale together --
a partial re-layout cannot work -- and the layout places the document
instead. A page the editor saved records the mode per node, so its geometry
stays trusted until the rules change.

The shipped templates carry no hand placement at all
(``tests/unit/test_saved_geometry_trust.py``), so they are laid out here as
they always were.
"""

from __future__ import annotations

from typing import Any

#: Where a saved layout is written, per element.
NODE_KEYS = ("editor_x", "editor_y")
#: A frame keeps its own size too; a card's comes from its look.
FRAME_KEYS = ("editor_width", "editor_height")


def aligned(elements: list, placed: list, what: str) -> list:
    """Placed scene items in the order of their topology elements.

    The layout may reorder siblings to shorten wires, so items are paired by
    the ``ref`` each carries back to its element; a scene without refs (built
    by hand) still pairs positionally.
    """
    if len(elements) != len(placed):
        raise ValueError(f"topology elements and {what} must remain aligned")
    by_ref = {getattr(item, "ref", ""): item for item in placed if getattr(item, "ref", "")}
    if len(by_ref) != len(placed):
        return placed
    try:
        return [by_ref[element.id] for element in elements]
    except KeyError as error:
        raise ValueError(f"{what} do not cover element {error.args[0]!r}") from error


def has_saved_geometry(element: Any) -> bool:
    return any(key in element.attributes for key in NODE_KEYS)


def is_current(elements: list, nodes: list, display: str) -> bool:
    """Whether the saved coordinates still describe what is drawn now."""
    return all(
        str(element.attributes.get("editor_display_mode") or display) == node.display
        for element, node in zip(elements, nodes, strict=True)
        if has_saved_geometry(element)
    )


def _int(value: Any, fallback: float) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


def apply_to_scene(root: Any, scene: Any, *, display: str) -> bool:
    """Move a placed scene onto the coordinates the editor saved.

    Returns whether anything was moved: nothing to move, or geometry that no
    longer describes the looks being drawn, leaves the layout alone.
    """
    elements = [element for element in root.walk() if not element.is_frame]
    frames = [element for element in root.walk() if element is not root and element.is_frame]
    if not any(has_saved_geometry(element) for element in (*elements, *frames)):
        return False
    nodes = aligned(elements, list(scene.root.walk()), "placed scene nodes")
    if not is_current(elements, nodes, display):
        return False
    clusters = aligned(
        frames,
        [item for item in scene.root.clusters() if item is not scene.root],
        "placed scene frames",
    )
    for element, node in zip(elements, nodes, strict=True):
        if not has_saved_geometry(element):
            continue
        node.x = _int(element.attributes.get("editor_x", node.x), node.x)
        node.y = _int(element.attributes.get("editor_y", node.y), node.y)
        # A card stretched by hand keeps the size it was given, as it does when
        # the editor opens the same document. A size saved for a card says
        # nothing about a bare icon, whose box is its glyph and caption.
        size = element.attributes.get("editor_card_size")
        if isinstance(size, dict) and node.display != "icon":
            node.width = _int(size.get("width", node.width), node.width)
            node.height = _int(size.get("height", node.height), node.height)
    for element, cluster in zip(frames, clusters, strict=True):
        if not has_saved_geometry(element):
            continue
        cluster.x = _int(element.attributes.get("editor_x", cluster.x), cluster.x)
        cluster.y = _int(element.attributes.get("editor_y", cluster.y), cluster.y)
        cluster.width = _int(element.attributes.get("editor_width", cluster.width), cluster.width)
        cluster.height = _int(
            element.attributes.get("editor_height", cluster.height), cluster.height
        )
    return True


__all__ = [
    "FRAME_KEYS",
    "NODE_KEYS",
    "aligned",
    "apply_to_scene",
    "has_saved_geometry",
    "is_current",
]
