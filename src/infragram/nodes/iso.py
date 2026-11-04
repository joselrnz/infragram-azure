"""A 3D item rendered by spec, for the diagram that needs what no table has.

    from infragram.nodes.iso import Iso

    db = Iso("DB-01", "PostgreSQL 16", recipe="server", family="storage", glyph="database", units=3, drivesN=12)
    smr = Iso("Unit 2", "SMR", recipe="reactor", family="energy", kind="smr")
    plain = Iso("Node", recipe="server", colour="#5b21b6", badge=False, units=1)

The recipes and their knobs are the ones ``scene.js`` offers -- the same
builders behind the shipped set -- listed by
:func:`infragram.iso3d.vocabulary.recipes`. The item renders once, in
headless Chromium, when the node is made; the render and its ink
measurement are cached by spec hash and travel with the element, so the
saved document draws the same in the static picture, the editor and every
export. Links seat on the render like on any shipped icon.
"""

from __future__ import annotations

from ..iso3d.api import build_spec, render_cached
from ._base import Element


class Iso(Element):
    """A rendered 3D item: ``recipe`` names the builder, the knobs shape it."""

    COLLECTION = "infragram"
    ICON = "custom-3d"
    TYPE = "3d"

    def __init__(
        self,
        name: str,
        detail: str | None = None,
        *,
        recipe: str,
        family: str = "compute",
        colour: str | None = None,
        glyph: str | None = None,
        badge: bool = True,
        role: str | None = None,
        id: str | None = None,
        **knobs: object,
    ) -> None:
        spec = build_spec(recipe, family=family, colour=colour, glyph=glyph, badge=badge, **knobs)
        svg, entry, digest = render_cached(spec)
        super().__init__(
            name,
            detail,
            role=role,
            id=id,
            iso=spec,
            iso_hash=digest,
            iso_artwork=svg,
            iso_ink=entry,
        )
