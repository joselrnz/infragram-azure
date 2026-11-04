"""The house arrowheads: one spec, read by every renderer and by the checker.

The numbers live in ``skills/infragram-azure/assets/catalog/arrowheads.json`` -- a
skill asset, so the shipped checker (standard library only) reads the same
file the Python renderer reads, and the editor runtime receives it through
the page the shell writes. Change a head there and every picture follows;
no renderer knows a number of its own.

A head is a fixed size whatever the stroke (``markerUnits="userSpaceOnUse"``)
and its tip sits exactly on the node's edge. ``shaft`` is the straight wire a
path keeps under a head so a bend never runs into it. ``tip_clear`` is how
far short of the tip the wire stops, so the stroke never pokes out of the
point where the head is thinner than the line; the marker's ``refX`` moves
the same amount, which puts the tip back exactly on the anchor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..paths import skill_assets


def spec_path() -> Path:
    return skill_assets() / "catalog" / "arrowheads.json"


@dataclass(frozen=True)
class Head:
    """One arrowhead shape: its frame and the element drawn inside it."""

    name: str
    #: What the inspector calls it.
    label: str
    #: Along the wire, tip included.
    length: float
    #: Across the wire.
    width: float
    #: The marker's inner element, with ``{paint}`` for the wire colour.
    markup: str

    def marker(self, marker_id: str, paint: str, tip_clear: float = 0.0) -> str:
        """The ``<marker>`` element, byte for byte what the editor runtime
        writes from the same spec (its ``markerMarkup``). The wire ends
        ``tip_clear`` short of the anchor, so the tip sits that far past the
        path's end: ``refX`` is the length less the clearance."""
        return (
            f'<marker id="{marker_id}" markerUnits="userSpaceOnUse" '
            f'markerWidth="{self.length:g}" markerHeight="{self.width:g}" '
            f'refX="{self.length - tip_clear:g}" refY="{self.width / 2:g}" orient="auto-start-reverse">'
            f"{self.markup.replace('{paint}', paint)}</marker>"
        )


@lru_cache(maxsize=1)
def spec() -> dict:
    return json.loads(spec_path().read_text(encoding="utf-8"))


def shaft() -> float:
    """Straight wire kept under a head, in px."""
    return float(spec()["shaft"])


def tip_clear() -> float:
    """How far short of the tip the wire stops, in px."""
    return float(spec().get("tip_clear", 0))


def default_name() -> str:
    return str(spec()["default"])


def heads() -> dict[str, Head]:
    return {
        name: Head(
            name,
            str(entry.get("label", name.title())),
            float(entry["length"]),
            float(entry["width"]),
            str(entry["markup"]),
        )
        for name, entry in spec()["heads"].items()
    }


def head(name: str | None = None) -> Head:
    """The named head, or the default when the name is unknown or None."""
    table = heads()
    return table.get(name or "", table[default_name()])


def marker(marker_id: str, name: str | None, paint: str) -> str:
    """The ``<marker>`` element for one head in one paint."""
    return head(name).marker(marker_id, paint, tip_clear())


def select_options() -> str:
    """The inspector's arrowhead choices, in spec order."""
    return "".join(f'<option value="{h.name}">{h.label}</option>' for h in heads().values())


def runtime_json() -> str:
    """The spec as the editor page carries it, safe inside a script tag."""
    # The shell owns the one escaping; imported here, not at the top, because
    # the shell imports this module.
    from ..editor.shell import script_safe

    return script_safe(json.dumps(spec(), separators=(",", ":")))
