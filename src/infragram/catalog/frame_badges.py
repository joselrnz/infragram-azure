"""The reviewed record of what every frame wears in its tab, as a model.

``assets/catalog/frame-badges.json`` names, for each library, the frame
kinds that carry the vendor's own artwork and, for every other kind, the
reason it is blank. Tests hold the themes to it and the frame gallery reads
it; loading it through a model means a malformed record fails here, with a
field name, rather than somewhere inside a test.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field

from ..paths import skill_assets

__all__ = ["FrameBadgeRecord", "LibraryBadges", "frame_badges"]


class LibraryBadges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: A library-level remark (AWS: how the deck files its group boxes).
    note: str = ""
    #: kind -> ``collection:slug`` of the vendor artwork the tab carries.
    badges: dict[str, str] = Field(default_factory=dict)
    #: kind -> why this kind is deliberately unbadged.
    blank: dict[str, str] = Field(default_factory=dict)
    #: kind -> why a badge that is not the vendor's own group box is allowed.
    reasons: dict[str, str] = Field(default_factory=dict)
    #: kind -> the recorded exception to the library's rule (AWS Organization).
    exceptions: dict[str, str] = Field(default_factory=dict)


class FrameBadgeRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = ""
    source_of_truth: str = ""
    libraries: dict[str, LibraryBadges]


@lru_cache(maxsize=1)
def frame_badges() -> FrameBadgeRecord:
    path = skill_assets() / "catalog" / "frame-badges.json"
    return FrameBadgeRecord.model_validate_json(path.read_text(encoding="utf-8"))
