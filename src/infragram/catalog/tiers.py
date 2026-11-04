"""Which service a resource glyph belongs to, and which frame a group box is.

A vendor ships two kinds of artwork. A **service** icon stands for the service
itself. A **resource** glyph is the drawing the vendor places *inside* that
service's group box: Multi AZ inside Amazon RDS, a NAT gateway inside a VPC.
Both become classes, they sit side by side in the same module, and they read
alike -- ``RDSMultiAz`` next to ``RDS``. Reaching for the wrong one produces a
diagram that looks plausible and is wrong, which is how it went unnoticed
twice before this module existed.

The vendor states the answer in the name: ``"Multi AZ (Amazon RDS)"``. This is
the one place that is read, so everything that needs the pairing agrees: the
node generator writes it into each class docstring, and an icon carries it so
a caller can ask at run time.

The convention is AWS's today. A pack that names its resources differently
resolves to nothing, which is the honest result: no claim is better than a
wrong one.

A third kind of artwork sits alongside them. A **group** icon is the box the
vendor draws *around* things -- the Region outline, the VPC outline, the
subnet outline. It ships as a component class like everything else, and its
class name collides with the frame that does the same job: ``Region`` in
``nodes.aws.architecture_group`` beside ``Region`` in ``nodes.frames.aws``.
Placed as a node it draws a flat card that contains nothing, which reads as a
region while modelling none. Detection is the vendor's own ``tier``; the frame
to use instead is read from ``assets/catalog/container-artwork.json``, because
pairing the two by name automatically put the VPC glyph with the Cloud frame.
"""

from __future__ import annotations

import re
from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field

from ..paths import skill_assets

#: A resource glyph names its service in trailing parentheses.
NAMED_SERVICE = re.compile(r"^(?P<own>.*?)\s*\((?P<service>[^)]+)\)\s*$")

#: The tier a catalog entry has when it does not say.
DEFAULT_TIER = "service"

#: The tier the vendor gives artwork meant to be drawn around other things.
CONTAINER_TIER = "group"


def is_resource(entry: dict) -> bool:
    """Is this catalog entry a resource glyph rather than a service icon?"""
    return str(entry.get("tier") or DEFAULT_TIER) == "resource"


def service_names(icons: list[dict]) -> dict[str, dict]:
    """Every service icon in a pack, by the name a resource glyph would cite."""
    return {str(icon.get("name") or ""): icon for icon in icons if not is_resource(icon)}


def parent_service(entry: dict, services: dict[str, dict]) -> dict | None:
    """The service entry a resource glyph belongs to, or None.

    ``None`` covers three honest cases: the entry is a service already, its
    name does not cite one, or the service it cites is not in this pack and so
    is not something a caller could have used instead.
    """
    if not is_resource(entry):
        return None
    match = NAMED_SERVICE.match(str(entry.get("name") or ""))
    return services.get(match.group("service")) if match else None


def is_container(entry: dict) -> bool:
    """Is this catalog entry the box drawn around things, not a thing?"""
    return str(entry.get("tier") or DEFAULT_TIER) == CONTAINER_TIER


class ContainerRow(BaseModel):
    """One group glyph: the frame that replaces it, or the reason none does."""

    model_config = ConfigDict(extra="allow")

    frame: str | None = None
    reason: str = ""


class ContainerArtwork(BaseModel):
    """``assets/catalog/container-artwork.json``, the reviewed table."""

    model_config = ConfigDict(extra="forbid")

    note: str = ""
    fallback: str
    providers: dict[str, dict[str, ContainerRow]] = Field(default_factory=dict)
    frame_counterparts_note: str = ""
    frame_counterparts: dict[str, dict[str, ContainerRow]] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def container_artwork() -> dict:
    """The reviewed table pairing each group icon with the frame to use."""
    path = skill_assets() / "catalog" / "container-artwork.json"
    return ContainerArtwork.model_validate_json(path.read_text(encoding="utf-8")).model_dump()


def container_frame(provider: str, icon_id: str) -> str | None:
    """The frame that replaces a group icon, or None when none fits it.

    ``None`` is a real answer, not a gap: five of AWS's group boxes have no
    frame counterpart, and naming a near-miss would misstate the diagram.
    Callers fall back to ``container_artwork()["fallback"]``.
    """
    row = (container_artwork().get("providers") or {}).get(provider, {}).get(icon_id)
    return (row or {}).get("frame") or None


def container_reason(provider: str, icon_id: str) -> str:
    """Why this glyph is filed as a container, in the table's own words."""
    row = (container_artwork().get("providers") or {}).get(provider, {}).get(icon_id)
    return str((row or {}).get("reason") or "")


def container_advice(provider: str, icon_id: str) -> str:
    """One sentence saying what to place instead of this glyph.

    A frame when one fits. Otherwise the reviewed reason, which says what to
    draw instead -- five of AWS's group boxes have no frame counterpart, and
    naming a near-miss would misstate the diagram.
    """
    frame = container_frame(provider, icon_id)
    if frame:
        return f"To contain, use ``{frame}``."
    reason = container_reason(provider, icon_id)
    return f"No frame ships for it: {reason}." if reason else "No frame ships for it."


# --------------------------------------------------------------------------
# Frame counterparts.
#
# Only AWS files artwork as a group. Every other vendor draws its containment
# concepts as ordinary service icons: Azure ships "Virtual Networks", IBM
# ships "VPC", Oracle ships "VCN". Those are real icons and placing one is
# not an error -- an inventory diagram may want exactly that. But a VNet that
# holds things is a frame, and the icon holds nothing, so each of these says
# which frame to reach for when the intent is containment.
#
# This is a pointer, never a refusal. The checker rejects group artwork; it
# says nothing about these.


def frame_counterpart(provider: str, icon_id: str) -> str | None:
    """The frame to use when this icon is meant to contain something."""
    rows = (container_artwork().get("frame_counterparts") or {}).get(provider, {})
    row = rows.get(icon_id)
    return (row or {}).get("frame") or None


def counterpart_advice(provider: str, icon_id: str) -> str:
    """One sentence pointing at the frame, empty when there is no pairing."""
    frame = frame_counterpart(provider, icon_id)
    return f"This also ships as a frame: to contain resources use ``{frame}``." if frame else ""
