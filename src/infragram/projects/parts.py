"""The pieces a project is made of, beside its topology.

A provider selection is a library the document has installed; a layer groups
for visibility and z-order, independent of containment; the presentation
carries the choices that materially change what is drawn.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..utils.text import SLUG as _SLUG
from .names import (
    _NAMESPACED_ID,
    AudienceName,
    DetailName,
    DisplayName,
    LayerKind,
    SizeName,
)

__all__ = ["Layer", "Presentation", "ProviderSelection", "View", "ViewSelector"]


class ProviderSelection(BaseModel):
    """One provider or platform library installed in a project."""

    id: str
    enabled: bool = True

    model_config = {"extra": "forbid"}

    @field_validator("id")
    @classmethod
    def _valid_provider_id(cls, value: str) -> str:
        provider = value.strip().casefold()
        if not _SLUG.fullmatch(provider):
            raise ValueError("provider id must be a slug")
        return provider


class Layer(BaseModel):
    """Visibility and z-order grouping, independent from containment."""

    id: str
    name: str
    kind: LayerKind = "logical"
    provider: str | None = None
    visible: bool = True
    locked: bool = False
    order: int = Field(default=0, ge=0)

    model_config = {"extra": "forbid"}

    @field_validator("id")
    @classmethod
    def _valid_layer_id(cls, value: str) -> str:
        layer_id = value.strip().casefold()
        if not _NAMESPACED_ID.fullmatch(layer_id):
            raise ValueError("layer id must be a slug or one-level qualified slug")
        return layer_id

    @field_validator("name")
    @classmethod
    def _non_empty_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("layer name must not be empty")
        return name

    @field_validator("provider")
    @classmethod
    def _valid_optional_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        provider = value.strip().casefold()
        if not _SLUG.fullmatch(provider):
            raise ValueError("layer provider must be a slug")
        return provider


class Presentation(BaseModel):
    """Layout and wording choices that materially affect rendering."""

    size: SizeName = "doc-inline"
    detail: DetailName = "balanced"
    audience: AudienceName = "mixed"
    eyebrow: str = "Architecture"
    heading: str = ""
    legend: tuple[tuple[str, str], ...] = ()
    #: What each tone a box is filled with means (``edge`` -> "public edge /
    #: ingress"), in the order the legend lists them (builders/panels.py).
    tones: tuple[tuple[str, str], ...] = ()
    #: Project-wide default for every component; a node may still carry its
    #: own ``editor_display_mode`` and the editor keeps that choice.
    display: DisplayName = "icon"
    #: How unrelated wires cross; a bridge changes their ink, never their topology.
    crossings: Literal["plain", "bridge"] = "plain"
    #: How heavy every frame's border draws: ``thin`` is each kind's own
    #: width, ``medium`` 1.75 times it, ``thick`` 2.5 times it.
    frame_lines: Literal["thin", "medium", "thick"] = "thin"
    #: Where this drawing stands: "CURRENT -- verified 2026-09-07", "TARGET",
    #: "PROPOSED". A diagram of an estate is a claim about that estate on a
    #: day. Kept as document metadata for companion documentation; never
    #: printed in the editor header or exported diagram.
    status: str = ""
    #: Standing warnings that travel with the status: "PRODUCTION NO-GO".
    notes: tuple[str, ...] = ()
    #: The day the drawing was made, as the author writes dates.
    drawn: str = ""

    model_config = {"extra": "forbid"}


class ViewSelector(BaseModel):
    """One thing a view's rule matches; exactly one field is set.

    A frame that matches brings everything inside it, however deep.
    """

    #: ``key=value``: the tags an element wears (``.tags()``, a resource's
    #: tags, a workload's labels).
    tag: str | None = None
    #: The catalog's category of a component: ``networking``, ``databases``.
    category: str | None = None
    #: A shell pattern over the element's name, for a naming convention:
    #: ``*-prod-*``. Case is ignored.
    name: str | None = None
    #: A frame's id: that frame and everything in it.
    within: str | None = None
    #: One element's id, for the exception no rule states.
    id: str | None = None

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _exactly_one(self) -> ViewSelector:
        given = [key for key, value in self.model_dump().items() if value is not None]
        if len(given) != 1:
            raise ValueError(
                "a view's selector sets exactly one of tag, category, name, within, id"
                + (f", not {', '.join(given)}" if given else "")
            )
        if self.tag is not None and "=" not in self.tag:
            raise ValueError(f"a tag selector is key=value, not {self.tag!r}")
        return self


class View(BaseModel):
    """A named part of the diagram, selected by rule and drawn on its own
    (``--view``). It owns no elements: an element is in the view when it
    matches ``include`` (or ``include`` is empty) and nothing in ``exclude``."""

    id: str
    #: What stands at the top of the view's picture; the id when empty.
    title: str = ""
    include: tuple[ViewSelector, ...] = ()
    exclude: tuple[ViewSelector, ...] = ()
    #: The id of a view whose selection this one narrows.
    extends: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _SLUG.fullmatch(value):
            raise ValueError("a view's id must contain lowercase letters, numbers, and hyphens")
        if value == "all":
            raise ValueError("'all' means every view; a view cannot be called that")
        return value
