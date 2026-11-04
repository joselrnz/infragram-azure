"""The open scopes an author writes inside.

Nesting is containment: a node or frame constructed while a frame is open
joins that frame, and one constructed while only a diagram is open becomes
one of its roots. Nothing here draws; it only records where a thing was
written. Scripts that never open a scope are untouched, because adoption
only happens while a scope is open, so the older ``parent >> child`` form
keeps working exactly as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from ..models.topology import TopologyElement

__all__ = [
    "adopt",
    "claim",
    "close_diagram",
    "close_frame",
    "latest_diagram",
    "open_diagram",
    "open_frame",
    "reset",
]

_FRAMES: list[TopologyElement] = []  # open frames, innermost last
_DIAGRAMS: list[Any] = []  # open diagrams, innermost last
_LATEST: list[Any] = []  # diagrams closed in this process, most recent last


def _holds(children: list, element: TopologyElement) -> bool:
    # Identity, not equality: two nodes with the same name and detail are two
    # nodes, and a model's == would call them one.
    return any(existing is element for existing in children)


#: The children list (or root list) each adopted element sits in, by the
#: element's identity, so claim() can take it back after its frame closed.
_HOLDERS: dict[int, list] = {}


def hold(element: TopologyElement, holder: list) -> None:
    """Record the list *element* now sits in."""
    _HOLDERS[id(element)] = holder


def adopt(element: TopologyElement) -> None:
    """Give a freshly built element to whatever scope is open, if any."""
    if _FRAMES:
        parent = _FRAMES[-1]
        if parent is not element and not _holds(parent.children, element):
            parent.children.append(element)
            hold(element, parent.children)
    elif _DIAGRAMS:
        roots = _DIAGRAMS[-1].roots
        if not _holds(roots, element):
            hold(element, roots)
            roots.append(element)


def open_frame(frame: TopologyElement) -> None:
    _FRAMES.append(frame)


def close_frame(frame: TopologyElement) -> None:
    if not _FRAMES or _FRAMES[-1] is not frame:
        raise RuntimeError("frames must close in the order they were opened")
    _FRAMES.pop()


def open_diagram(diagram: Any) -> None:
    _DIAGRAMS.append(diagram)


def close_diagram(diagram: Any) -> None:
    if not _DIAGRAMS or _DIAGRAMS[-1] is not diagram:
        raise RuntimeError("diagrams must close in the order they were opened")
    if _FRAMES:
        raise RuntimeError("a frame is still open inside the diagram")
    _DIAGRAMS.pop()
    _LATEST.append(diagram)


def latest_diagram() -> Any | None:
    """The diagram most recently closed in this process, or None."""
    return _LATEST[-1] if _LATEST else None


def claim(element: TopologyElement) -> None:
    """Take an element back from the scope that adopted it.

    Explicit placement wins over implicit adoption: when ``parent >> child``
    or ``parent.add(child)`` names a home for something the open frame or the
    diagram already took in, the element leaves that scope, so a pattern built
    inside a ``with`` block nests once, under the parent it was attached to.
    """
    # the list it was adopted into, even when that frame has since closed,
    # then the open scopes, so the element ends up in one parent only
    holders = [
        _HOLDERS.pop(id(element), None),
        _FRAMES[-1].children if _FRAMES else None,
        _DIAGRAMS[-1].roots if _DIAGRAMS else None,
    ]
    for holder in holders:
        if holder is not None:
            for index, existing in enumerate(holder):
                if existing is element:
                    del holder[index]
                    break


def reset() -> None:
    """Forget every scope. Tests build many diagrams in one process."""
    _FRAMES.clear()
    _DIAGRAMS.clear()
    _LATEST.clear()
    _HOLDERS.clear()
