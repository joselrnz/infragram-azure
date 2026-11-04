"""A generic topology model: what the infrastructure *is*, not how it is drawn.

One element type describes every layer of a cloud estate. ``type`` says what
a thing is, ``role`` says what part it plays in a pattern, and ``children``
carries containment::

    subscription >> resource_group >> hub_vnet >> subnet >> vm

``>>`` appends and returns the child, so a chain reads as a hierarchy and a
repeated parent fans out::

    resource_group >> spoke_1
    resource_group >> spoke_2

Keeping ``role`` separate from ``type`` is what keeps the model generic: a
hub and a spoke are both ``type="vnet"``, distinguished only by role, so
hub-and-spoke needs no special class -- and neither will the next pattern.

Being a pydantic model means a topology can round-trip through JSON, so it
can come from somewhere other than a hand-written script: an Azure Resource
Graph export, Terraform state, a discovery job. ``index()`` gives the id
lookup that makes those sources addressable.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from ..utils.text import SLUG as _SLUG


class ComponentRef(BaseModel):
    """Stable provider-qualified identity for a catalog-backed component."""

    provider: str
    service_id: str
    icon_ref: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("provider", "service_id")
    @classmethod
    def _valid_slug(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not _SLUG.fullmatch(normalized):
            raise ValueError("component provider and service_id must be slugs")
        return normalized

    @model_validator(mode="after")
    def _qualified_icon_ref(self) -> ComponentRef:
        expected_prefix = f"{self.provider}:"
        if self.icon_ref is None:
            self.icon_ref = f"{expected_prefix}{self.service_id}"
        elif not self.icon_ref.startswith(expected_prefix):
            raise ValueError(
                f"icon_ref must use provider prefix {self.provider}: {self.icon_ref!r}"
            )
        return self


class LabelPlacement(BaseModel):
    """Editor-neutral placement metadata for a connector label.

    Manual coordinates are offsets from the renderer's automatic label anchor,
    so a label follows its connector when connected nodes move or resize.
    """

    mode: Literal["auto", "manual"] = "auto"
    dx: float = 0
    dy: float = 0

    model_config = {"extra": "forbid"}


class Waypoint(BaseModel):
    """One corner a connector is pinned through, in canvas coordinates."""

    x: float
    y: float

    model_config = {"extra": "forbid"}


class Connection(BaseModel):
    """A declared link from one element to another, by id.

    Containment is ``>>``; this is the other axis -- what talks to what.
    Stored by target id rather than by object so the tree stays a tree and
    a link can point anywhere in it, including across branches.
    """

    target: str
    kind: str = "solid"
    label: str = ""
    #: Corners the author pinned by hand. Empty means the renderer routes
    #: the wire itself, around whatever is in the way.
    waypoints: tuple[Waypoint, ...] = ()
    label_placement: LabelPlacement | None = None
    #: Arrowheads: ``forward`` (source → target, the default), ``both``, or
    #: ``none`` for an undirected association such as a replication pair.
    direction: Literal["forward", "both", "none"] = "forward"
    #: Where the wire comes in a flow told in order (1, 2, 3 ...): a numbered
    #: circle at the start of its caption, and a line of the step list.
    step: int | None = Field(default=None, ge=1, le=99)
    #: What the step list says of it; its caption when it says nothing.
    step_text: str | None = None
    #: The name of a second flow this step belongs to (``Edge(flow=...)``):
    #: marked the theme's second way and listed under the name. None is the
    #: diagram's main flow.
    step_flow: str | None = None

    # Like every other model in the document: a misspelt key is an error at
    # load time, not a wire quietly drawn without the setting.
    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def _a_step_numbers_a_caption(self) -> Connection:
        if self.step is not None and not self.label.strip():
            raise ValueError("a step numbers a wire's caption: give the wire a label")
        if self.step_flow is not None and (self.step is None or not self.step_flow.strip()):
            raise ValueError(
                "step_flow names the flow a step belongs to: give the wire a step and the flow a name"
            )
        return self


#: Historical public name for the serialized badge key.
RETIRED_BADGES = "badges"


class Badge(BaseModel):
    """What applies to a frame, drawn on its top-right corner: a subnet's
    network security group or route table, the way Azure's reference
    diagrams seat an NSG on its subnet.

    The first badge's icon sits on the corner point, the rest on the top
    border leftwards from it, each name just under the line to the left of
    its icon. A label written ``Type · name`` sets the type in the frame's
    quiet tone. Both renderers draw it (``CORNER_BADGE`` in builders/scene.py
    and runtime 14-shapes).
    """

    model_config = {"extra": "forbid"}

    icon: str
    #: The icon set it is found in; empty looks in the diagram's own library.
    collection: str = ""
    label: str = ""
    #: ``edge`` keeps Azure NAT gateway bars; the named sides preserve
    #: documents authored before corner badges were introduced.
    side: Literal["corner", "edge", "top", "bottom", "left", "right"] = "top"
    offset: float = 0.5


class TopologyElement(BaseModel):
    id: str
    name: str
    type: str
    role: str | None = None
    component: ComponentRef | None = None
    layer_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    children: list[TopologyElement] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)
    #: A frame's corner badges (:class:`Badge`); written only when there are some.
    badges: list[Badge] = Field(default_factory=list)

    # Like every other model in the document: a misspelt key ("conections",
    # "chidren") is an error at load time, not content quietly dropped.
    model_config = {"extra": "forbid"}

    @model_serializer(mode="wrap")
    def _badges_only_when_there_are_some(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        """An element with no badges writes no ``badges`` key, so a document
        saved before badges came back reads the same after."""
        data = handler(self)
        if isinstance(data, dict) and not data.get(RETIRED_BADGES):
            data.pop(RETIRED_BADGES, None)
        return data

    # -- construction --------------------------------------------------
    def __rshift__(self, child: TopologyElement) -> TopologyElement:
        """Append *child* and return it, so chains read as hierarchy.

        Anything that is not an element -- an ``author.Edge`` -- is left to
        the right operand, and a child already present is not added twice,
        so the ``with`` form and this form may meet without duplicating.
        """
        if not isinstance(child, TopologyElement):
            return NotImplemented
        self._take(child)
        return child

    def add(self, *children: TopologyElement) -> TopologyElement:
        """Append several children and return *self*, for fan-out."""
        for child in children:
            self._take(child)
        return self

    def _take(self, child: TopologyElement) -> None:
        """Make *child* ours: out of any scope that adopted it, in here once."""
        from ..nodes import _scope  # lazy: nodes imports this module

        if child is not self:
            _scope.claim(child)
        if not any(existing is child for existing in self.children):
            self.children.append(child)
            _scope.hold(child, self.children)

    def badge(
        self, source: Any, *, side: str = "corner", offset: float = 0.5, label: str = ""
    ) -> TopologyElement:
        """Pin a corner, NAT edge, or named-border mark to this frame. Returns *self*.

        ``source`` is a node class, an instance of one, or a plain ``"slug"``
        / ``"collection:slug"`` string; ``label`` is the name beside it::

            with azure_frames.Subnet("snet-web").badge(azure.NetworkSecurityGroups, label="nsg-web"):
                ...
        """
        if side not in {"corner", "edge", "top", "bottom", "left", "right"}:
            raise ValueError(f"unknown frame badge side: {side!r}")
        icon = getattr(source, "ICON", "")
        collection = getattr(source, "COLLECTION", "")
        if not icon:
            collection, _, icon = str(source).rpartition(":")
        if not icon:
            raise ValueError(f"badge(): {source!r} names no icon")
        self.badges.append(
            Badge(icon=icon, collection=collection, label=label, side=side, offset=offset)
        )
        return self

    def to(
        self,
        *targets: TopologyElement,
        kind: str = "solid",
        label: str = "",
        direction: Literal["forward", "both", "none"] = "forward",
        label_placement: LabelPlacement | None = None,
        step: int | None = None,
        step_text: str | None = None,
        step_flow: str | None = None,
    ) -> TopologyElement:
        """Draw a link from this element to each target. Returns *self*.

        Returning self keeps chains readable and distinct from ``>>``::

            gateway.to(balancer, kind="traffic")
            registry.to(replica_a, replica_b, kind="replication")
            primary.to(secondary, kind="dashed", label="sync", direction="both")
        """
        for target in targets:
            self.connections.append(
                Connection(
                    target=target.id,
                    kind=kind,
                    label=label,
                    direction=direction,
                    label_placement=label_placement,
                    step=step,
                    step_text=step_text,
                    step_flow=step_flow,
                )
            )
        return self

    # -- traversal and indexing ----------------------------------------
    def walk(self) -> Iterator[TopologyElement]:
        """Depth-first over this element and everything beneath it."""
        yield self
        for child in self.children:
            yield from child.walk()

    def index(self) -> dict[str, TopologyElement]:
        """Every element by id."""
        return {element.id: element for element in self.walk()}

    def find(self, **criteria: Any) -> list[TopologyElement]:
        """Elements matching every given field, e.g. ``find(role="spoke")``."""
        return [
            element
            for element in self.walk()
            if all(getattr(element, key, None) == value for key, value in criteria.items())
        ]

    def first(self, **criteria: Any) -> TopologyElement | None:
        matches = self.find(**criteria)
        return matches[0] if matches else None

    def parent_of(self, target: TopologyElement) -> TopologyElement | None:
        for element in self.walk():
            if any(child is target for child in element.children):
                return element
        return None

    @property
    def is_frame(self) -> bool:
        """Drawn as a containment boundary rather than a component card.

        Anything with children is a frame. A childless element is still one
        when it carries a frame signal: a ``custom-boundary`` component, or
        the ``editor_frame_group`` / ``editor_boundary_style`` attributes the
        editor writes for every frame it places. That keeps an empty frame a
        frame across save-and-reopen instead of collapsing it into a node.
        """
        if self.children:
            return True
        if self.component is not None and self.component.service_id.startswith("custom-boundary"):
            return True
        return bool(self.attributes.get("editor_frame_group")) or isinstance(
            self.attributes.get("editor_boundary_style"), dict
        )

    def depth(self) -> int:
        return 1 + max((child.depth() for child in self.children), default=0)

    def tree(self, prefix: str = "") -> str:
        """Render the hierarchy as text - handy in tests and REPLs."""
        lines = [self.name]
        for index, child in enumerate(self.children):
            last = index == len(self.children) - 1
            tee, ext = ("└── ", "    ") if last else ("├── ", "│   ")
            block = child.tree(prefix + ext).splitlines()
            lines.append(prefix + tee + block[0])
            lines.extend(block[1:])
        return "\n".join(lines)

    @model_validator(mode="after")
    def _unique_ids(self) -> TopologyElement:
        """A duplicate id means two things claim the same identity."""
        seen: set[str] = set()
        for element in self.walk():
            if element.id in seen:
                raise ValueError(f"duplicate topology id: {element.id!r}")
            seen.add(element.id)
        return self

    def __repr__(self) -> str:
        role = f" role={self.role!r}" if self.role else ""
        kids = f" children={len(self.children)}" if self.children else ""
        return f"<{self.type} {self.id!r}{role}{kids}>"


__all__ = [
    "RETIRED_BADGES",
    "Badge",
    "ComponentRef",
    "Connection",
    "LabelPlacement",
    "TopologyElement",
    "Waypoint",
]
