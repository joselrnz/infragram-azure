"""The ``with`` block a diagram is written inside, and what it exports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models.topology import TopologyElement
from ..nodes import _scope
from ..nodes._base import release, reset_counters
from ..projects import CloudProject, DisplayName, ProjectKind, View, ViewSelector
from ..utils.text import slugify as _slugify
from .edge import _known_corners

__all__ = ["Diagram", "Direction", "latest_diagram", "slugify"]


Direction = Literal["down", "right"]


def slugify(text: str) -> str:
    """A file-safe slug from a title: ``"Azure: tenant to VM"`` -> ``azure-tenant-to-vm``."""
    return _slugify(text)[:64].rstrip("-") or "diagram"


def _tone_meanings(
    tones: Mapping[str, str] | Iterable[tuple[str, str]],
) -> tuple[tuple[str, str], ...]:
    """What each tone means, checked against the tones there are."""
    from ..builders.panels import check_tone

    pairs = tones.items() if isinstance(tones, Mapping) else tones
    return tuple((check_tone(str(name), "tones"), str(meaning)) for name, meaning in pairs)


class Diagram(BaseModel):
    """The picture being written. Open it, write frames and nodes inside.

    Everything not given is inferred: the slug from the title, the providers
    from the frames and nodes used, the kind from the providers. ``direction``
    lays the top-level frames side by side (``"right"``, and the default) or
    stacks them (``"down"``); below that the layout alternates on its own, and
    a frame's ``.row()`` or ``.column()`` overrides one level when you mean it.

    Every setting is validated when it is set, at construction or by a later
    assignment, so a bad value fails at the line that wrote it.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    title: str
    description: str = ""
    slug: str = ""
    providers: tuple[str, ...] = ()
    kind: ProjectKind | None = None
    display: DisplayName = "icon"
    direction: Direction | None = None
    #: The bend every wire takes unless its Edge says otherwise.
    corners: str | None = None
    crossings: Literal["plain", "bridge"] = "plain"
    frame_lines: Literal["thin", "medium", "thick"] = "thin"
    legend: tuple[tuple[str, str], ...] = ()
    #: What each tone means, for the legend: {"edge": "public edge / ingress"}.
    tones: tuple[tuple[str, str], ...] = ()
    eyebrow: str = "Architecture"
    heading: str = ""
    #: Where this drawing stands, what stands with it, and the day it was
    #: made. Saved as document metadata, outside the rendered diagram.
    status: str = ""
    notes: tuple[str, ...] = ()
    drawn: str = ""
    #: The top-level frames and nodes, in the order they were written.
    roots: list[TopologyElement] = Field(default_factory=list)
    #: The named parts ``--view`` draws on their own (:meth:`view`).
    views: list[View] = Field(default_factory=list)

    def __init__(
        self,
        title: str,
        description: str = "",
        *,
        slug: str | None = None,
        providers: Sequence[str] | None = None,
        kind: ProjectKind | None = None,
        display: DisplayName = "icon",
        direction: Direction | None = None,
        corners: str | None = None,
        crossings: Literal["plain", "bridge"] = "plain",
        frame_lines: Literal["thin", "medium", "thick"] = "thin",
        legend: Iterable[tuple[str, str]] = (),
        tones: Mapping[str, str] | Iterable[tuple[str, str]] = (),
        eyebrow: str = "Architecture",
        heading: str = "",
        status: str = "",
        notes: Iterable[str] = (),
        drawn: str = "",
    ) -> None:
        super().__init__(
            title=title,
            description=description or title,
            slug=slug or slugify(title),
            providers=tuple(providers or ()),
            kind=kind,
            display=display,
            direction=direction,
            corners=corners,
            crossings=crossings,
            frame_lines=frame_lines,
            legend=tuple(tuple(item) for item in legend),
            tones=_tone_meanings(tones),
            eyebrow=eyebrow,
            heading=heading,
            status=status,
            notes=tuple(notes),
            drawn=drawn,
        )

    @field_validator("corners")
    @classmethod
    def _known_corners(cls, value: str | None) -> str | None:
        return _known_corners(value)

    def __enter__(self) -> Diagram:
        # numbering starts afresh for this diagram; an id held by an element
        # built outside the block stays taken, so add() cannot collide
        reset_counters()
        _scope.open_diagram(self)
        return self

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        try:
            _scope.close_diagram(self)
        except RuntimeError:
            if exc_type is None:
                raise
        finally:
            # a closed diagram's ids are free for the next one
            release(element for root in self.roots for element in root.walk())
        return False

    def add(self, *elements: TopologyElement) -> Diagram:
        """Adopt elements built outside the block as top-level roots."""
        for element in elements:
            if not any(existing is element for existing in self.roots):
                self.roots.append(element)
        return self

    def view(
        self,
        id: str,
        title: str = "",
        *,
        include: Iterable[str | TopologyElement] = (),
        exclude: Iterable[str | TopologyElement] = (),
        extends: str | None = None,
    ) -> Diagram:
        """Name a part of the diagram that ``--view`` draws on its own.

            diagram.view("network", "Network", include=["category:networking"])
            diagram.view("prod", "Production", include=["name:*prod*"])
            diagram.view("hub", include=[hub_vnet], exclude=["tag:env=dev"])

        A rule is ``tag:key=value``, ``category:<category>``, ``name:<pattern>``
        (the naming convention), ``id:<element id>``, or a frame or element of
        this diagram. A frame brings everything inside it. One frame alone
        needs no view: ``--view`` takes a frame's id or caption as it is.
        """

        def selectors(rules: Iterable[str | TopologyElement]) -> tuple[ViewSelector, ...]:
            out = []
            for rule in rules:
                if isinstance(rule, TopologyElement):
                    key = "within" if rule.children else "id"
                    out.append(ViewSelector(**{key: rule.id}))
                    continue
                kind, colon, value = str(rule).partition(":")
                if not colon or kind not in ("tag", "category", "name", "within", "id"):
                    raise ValueError(
                        f"view {id!r}: a rule is tag:key=value, category:..., name:..., id:... "
                        f"or a frame, not {rule!r}"
                    )
                out.append(ViewSelector(**{kind: value.strip()}))
            return tuple(out)

        if any(view.id == id for view in self.views):
            raise ValueError(f"view {id!r} is already defined")
        self.views.append(
            View(
                id=id,
                title=title,
                include=selectors(include),
                exclude=selectors(exclude),
                extends=extends,
            )
        )
        return self

    def topology(self) -> TopologyElement:
        """The undrawn root holding the top-level frames and nodes."""
        from ..compose import ComposeError, undrawn_root

        if not self.roots:
            raise ComposeError(f"{self.title!r} has no elements; write them inside the with block")
        root = undrawn_root(list(self.roots), self.title)
        if self.direction:
            root.attributes["flow"] = "row" if self.direction == "right" else "column"
        if self.corners:
            # The diagram's bend applies to every wire that did not choose its own.
            for element in root.walk():
                for connection in element.connections:
                    styles = element.attributes.setdefault("editor_edge_styles", {})
                    styles.setdefault(connection.target, {}).setdefault("corners", self.corners)
        return root

    def to_project(self) -> CloudProject:
        """The project document every export renders."""
        from .. import compose

        return compose.to_project(
            self.topology(),
            slug=self.slug,
            title=self.title,
            description=self.description,
            providers=self.providers or None,
            kind=self.kind,
            display=self.display,
            legend=self.legend,
            tones=self.tones,
            eyebrow=self.eyebrow,
            heading=self.heading,
            status=self.status,
            notes=self.notes,
            drawn=self.drawn,
            crossings=self.crossings,
            frame_lines=self.frame_lines,
            views=self.views,
        )

    def export(self, output_dir: str | Path, **kwargs: Any):
        """Export the document; the same as ``infragram compose`` on the file."""
        from .. import compose

        return compose.export(self.to_project(), Path(output_dir), **kwargs)


def latest_diagram() -> Diagram | None:
    """The diagram most recently closed in this process (what ``compose`` exports)."""
    return _scope.latest_diagram()
