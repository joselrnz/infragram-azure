"""Where things were moved in the editor, kept beside the diagram file.

A diagram written in Python is drawn afresh on every compose, so what a
reader moved or resized in the exported editor was lost the next time the
file was composed: two sources of truth, and the file always won. The
editor's placement now travels back:

1. ``infragram layout:save <saved> --for <diagram.py>`` reads what the
   editor saved -- a downloaded ``.infragram.json``, the saved page, or a
   picture that carries its document -- and writes ``<diagram>.layout.json``
   beside the file: each element's ``editor_x``/``editor_y`` (and a frame's
   ``editor_width``/``editor_height``, a card's look), keyed by element id.
2. ``compose`` reads that file when it is there and puts the positions back
   on the elements before drawing. The layout then places only what was
   never placed by hand (builders/saved_geometry.py), so a card added to
   the file since lands where the layout puts it.

An element the file no longer draws is reported, not guessed at. The ids are
the ones the diagram file derives from names, so renaming an element in the
file drops its saved place (reported), which is the honest outcome.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..builders.saved_geometry import FRAME_KEYS, NODE_KEYS

__all__ = ["KEYS", "apply_layout", "layout_path", "saved_layout"]

#: What the file keeps per element: where it is, a frame's size, a card's look.
KEYS = (*NODE_KEYS, *FRAME_KEYS, "editor_display_mode", "editor_card_size")


def layout_path(spec: Path) -> Path:
    """``diagram.py`` -> ``diagram.layout.json``."""
    return spec.with_name(f"{spec.stem}.layout.json")


def saved_layout(project: Any) -> dict[str, dict[str, Any]]:
    """Every element's saved placement, as the layout file keeps it."""
    out: dict[str, dict[str, Any]] = {}
    for element in project.topology.walk():
        kept = {key: element.attributes[key] for key in KEYS if key in element.attributes}
        if any(key in kept for key in NODE_KEYS):
            out[element.id] = kept
    return out


def apply_layout(project: Any, path: Path) -> list[str]:
    """Put the file's placements on the project's elements; return notes on
    what it could not place."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"{path.name}: not read ({error}); the layout places everything"]
    elements = data.get("elements") if isinstance(data, dict) else None
    if not isinstance(elements, dict):
        return [f"{path.name}: no elements; the layout places everything"]
    index = project.topology.index()
    missing = []
    for element_id, placement in elements.items():
        element = index.get(element_id)
        if element is None or not isinstance(placement, dict):
            missing.append(element_id)
            continue
        for key in KEYS:
            if key in placement:
                element.attributes[key] = placement[key]
    if missing:
        shown = ", ".join(missing[:6]) + (
            f" and {len(missing) - 6} more" if len(missing) > 6 else ""
        )
        return [f"{path.name} places {len(missing)} element(s) the file no longer draws: {shown}"]
    return []


def write_layout(project: Any, path: Path) -> int:
    """Write the project's saved placements to *path*; return how many."""
    elements = saved_layout(project)
    path.write_text(
        json.dumps({"version": 1, "elements": elements}, indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return len(elements)
