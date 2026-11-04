"""Parameterised plain 3D servers, drawn by spec.

A grid of plain servers -- no badge, every family colour, seven shapes --
so a diagram can ask for the server it means instead of the nearest named
one::

    from infragram.nodes.custom import custom_server

    db = custom_server("DB-01", "PostgreSQL 16", units=2, bays=8, family="storage")
    gpu = custom_server("GPU-03", "8 × H100", units=4, bays=12)

``units`` and ``bays`` name one of the shapes in ``CUSTOM_SERVER_SHAPES``;
``family`` is the colour: compute (blue, the default), storage (teal),
network (violet), security (red), facility (amber), client (slate),
platform (indigo), operations (cyan), industrial (green), energy (fuchsia).
The full product ships these as a generated icon set; this edition has no
on-premises set, so each is the ``server`` recipe rendered through
:class:`~infragram.nodes.iso.Iso` with the same knobs. Anything else -- a
badge, a different front -- is :class:`~infragram.nodes.iso.Iso` itself.
"""

from __future__ import annotations

from typing import Any

#: (rack units, drive bays) -> (bays per row, rows): the shapes a custom
#: server comes in, as the full product's generated set draws them.
_SHAPES: dict[tuple[int, int], tuple[int, int]] = {
    (1, 0): (0, 0),
    (1, 4): (4, 1),
    (2, 0): (0, 0),
    (2, 8): (4, 2),
    (4, 0): (0, 0),
    (4, 12): (6, 2),
    (4, 24): (6, 4),
}
#: (rack units, drive bays) the custom grid is rendered in.
CUSTOM_SERVER_SHAPES: tuple[tuple[int, int], ...] = tuple(_SHAPES)
FAMILIES = (
    "compute",
    "storage",
    "network",
    "security",
    "facility",
    "client",
    "platform",
    "operations",
    "industrial",
    "energy",
)


def custom_server(
    name: str,
    subtitle: str = "",
    *,
    units: int = 2,
    bays: int = 8,
    family: str = "compute",
    **kwargs: Any,
):
    """The plain server of that shape and colour, as a node in the diagram."""
    if (units, bays) not in _SHAPES:
        raise ValueError(
            f"no custom server of {units}U with {bays} bays; one of "
            + ", ".join(f"{u}U/{b}" for u, b in CUSTOM_SERVER_SHAPES)
        )
    if family not in FAMILIES:
        raise ValueError(f"unknown family {family!r}; one of {', '.join(FAMILIES)}")
    from .iso import Iso

    per_row, rows = _SHAPES[(units, bays)]
    return Iso(
        name,
        subtitle or None,
        recipe="server",
        family=family,
        badge=False,
        units=units,
        drivesN=per_row,
        rows=rows,
        **kwargs,
    )
