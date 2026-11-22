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

from collections.abc import Iterable, Iterator, Sequence
from typing import Any, Literal, Self

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


def table_payload(
    owner: str, columns: Sequence[str], rows: Iterable[Sequence[str]]
) -> dict[str, Any]:
    """The ``{"columns": [...], "rows": [[...]]}`` a table rides in.

    Cells are kept exactly as given, as text and in the order given: the
    editor shows a route table's routes or a security group's rules the way
    they were written, never sorted or reformatted. A row may be shorter than
    the heading (its last cells stay empty), never longer.
    """
    heading = [str(value) for value in columns]
    if not heading:
        raise ValueError(f"{owner!r}: a table needs at least one column")
    body = [[str(cell) for cell in row] for row in rows]
    wide = [row for row in body if len(row) > len(heading)]
    if wide:
        raise ValueError(
            f"{owner!r}: {len(wide)} row(s) have more cells than the "
            f"{len(heading)} column(s) declared"
        )
    return {"columns": heading, "rows": body}


def _table_argument(owner: str, table: Any) -> dict[str, Any] | None:
    """A badge's ``table=``: ``(columns, rows)`` or an already built payload."""
    if table is None:
        return None
    if isinstance(table, dict):
        return table_payload(owner, table.get("columns") or (), table.get("rows") or ())
    try:
        columns, rows = table
    except (TypeError, ValueError):
        raise ValueError(
            f"{owner!r}: table= takes (columns, rows), for example "
            '(("Priority", "Name", "Access"), [("100", "allow-https", "Allow")])'
        ) from None
    return table_payload(owner, columns, rows)


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
    #: What the badge stands for, row by row: a security group's rules, a
    #: route table's routes. Nothing is drawn; clicking the badge in the
    #: editor opens it. Written only when there is one.
    table: dict[str, list[Any]] | None = None

    @field_validator("table")
    @classmethod
    def _table_shape(cls, value: dict[str, list[Any]] | None) -> dict[str, list[Any]] | None:
        if value is None:
            return None
        return table_payload("badge", value.get("columns") or (), value.get("rows") or ())

    @model_serializer(mode="wrap")
    def _table_only_when_there_is_one(self, handler: SerializerFunctionWrapHandler) -> Any:
        """A badge with no table writes no ``table`` key, so documents saved
        before badges carried tables read and write the same."""
        data = handler(self)
        if isinstance(data, dict) and data.get("table") is None:
            data.pop("table", None)
        return data


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
        self,
        source: Any,
        *,
        side: str = "corner",
        offset: float = 0.5,
        label: str = "",
        table: Any = None,
    ) -> Self:
        """Pin a corner, NAT edge, or named-border mark to this frame. Returns *self*.

        ``source`` is a node class, an instance of one, or a plain ``"slug"``
        / ``"collection:slug"`` string; ``label`` is the name beside it::

            with azure_frames.Subnet("snet-web").badge(azure.NetworkSecurityGroups, label="nsg-web"):
                ...

        ``table=(columns, rows)`` says what the badge stands for -- an NSG's
        rules, a route table's routes. Nothing is drawn: clicking the badge
        in the editor opens the table, rows exactly as written, and clicking
        the frame (or the VNet around a subnet) lists it with the others.
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
            Badge(
                icon=icon,
                collection=collection,
                label=label,
                side=side,
                offset=offset,
                table=_table_argument(label or icon, table),
            )
        )
        return self

    def table(self, columns: Sequence[str], rows: Iterable[Sequence[str]] = ()) -> Self:
        """Attach a table the editor shows when this element is selected.

            net.RouteTables("rt-spoke-prod", "UDR").table(
                ("Prefix", "Next hop type", "Next hop"),
                [("0.0.0.0/0", "Virtual appliance", "10.0.1.4"),
                 ("10.0.0.0/16", "VNet peering", "hub-vnet")])

        Nothing is drawn on the canvas: the card stays the card, and clicking
        it opens the table in a popup beside it. A frame takes one too, and
        clicking the frame opens it. The rows are whatever you pass, exactly
        as written, so three routes and thirty are the same call. The table
        rides in the element's attributes, so it survives saving and
        reopening the page.
        """
        self.attributes["table"] = table_payload(self.name, columns, rows)
        return self

    def addresses(self, *pairs: tuple[str, str], **named: str) -> Self:
        """Say which IP addresses this element answers on.

            az.Subnet("snet-app · 10.1.2.0/24").addresses(router="10.1.2.1")
            net.Firewalls("Azure Firewall").addresses(private="10.0.1.4", public="20.1.2.3")
            edge.addresses(("BGP peer", "169.254.0.1"))

        A keyword's name is the label (``router`` reads Router, ``public_ip``
        Public ip); a ``(label, address)`` pair says a label no keyword can.
        Nothing is drawn: the editor lists them when the pointer rests on the
        card or frame, under the right-click menu's title, and in its popup.
        Calling it again adds to what is there; a label given twice keeps the
        last address.
        """
        found: dict[str, str] = {
            str(label): str(value) for label, value in (self.attributes.get("addresses") or [])
        }
        for label, value in pairs:
            found[str(label)] = str(value)
        for key, value in named.items():
            words = key.replace("_", " ").strip()
            found[words[:1].upper() + words[1:]] = str(value)
        empty = [label for label, value in found.items() if not label or not value.strip()]
        if empty:
            raise ValueError(f"{self.name!r}: an address needs a label and a value ({empty})")
        self.attributes["addresses"] = [[label, value] for label, value in found.items()]
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
