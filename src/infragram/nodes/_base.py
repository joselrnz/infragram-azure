"""The two hand-written node types everything generated builds on.

:class:`Element` is the base of every generated service class; :class:`Group`
is the container that draws as a zone rather than an icon. Everything else
under ``nodes/`` is generated from the icon catalogs by
``scripts/tools/generate-nodes.py``.
"""

from __future__ import annotations

import difflib
import weakref
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Literal, cast

from ..models.topology import ComponentRef, TopologyElement
from ..utils.text import slugify
from . import _scope

__all__ = ["ROOT_ID", "Element", "Frame", "Group", "release", "reset_counters", "reset_ids"]

#: The id of the undrawn root a composed document is wrapped in. Reserved:
#: an auto-id never mints it, and compose refuses a user element that took it.
ROOT_ID = "root"

#: Attribute keys a node, group or frame may take by keyword beyond its named
#: parameters: the keys the renderers and the editor read. ``editor_`` keys
#: carry editor state and ``iso`` keys the rendered 3D items. Any other key
#: would be stored and read by nothing, so it is refused as the typo it
#: almost always is; ``attributes={...}`` keeps keys of your own.
_AUTHOR_KEYS = frozenset(
    {
        "accent",
        "arrange",
        "category",
        "collection",
        "detail",
        "flow",
        "height",
        "icon",
        "iso",
        "sections",
        "shape",
        "table",
        "tone",
        "width",
        "x",
        "y",
    }
)
_AUTHOR_PREFIXES = ("editor_", "iso_")


def _checked(owner: str, keywords: dict[str, Any], named: tuple[str, ...]) -> dict[str, Any]:
    """The attribute keywords a constructor was given, refusing unknown ones
    with the nearest real name."""
    own = keywords.pop("attributes", None) or {}
    if not isinstance(own, dict):
        raise TypeError(f"{owner}: attributes= must be a dict, not {type(own).__name__}")
    unknown = sorted(
        key for key in keywords if key not in _AUTHOR_KEYS and not key.startswith(_AUTHOR_PREFIXES)
    )
    if unknown:
        known = sorted({*_AUTHOR_KEYS, *named})
        hints = []
        for key in unknown:
            close = difflib.get_close_matches(key, known, n=1)
            hints.append(f"{key!r}" + (f" (did you mean {close[0]!r}?)" if close else ""))
        raise TypeError(
            f"{owner}() got unknown keyword argument{'s' if len(unknown) > 1 else ''} "
            f"{', '.join(hints)}; keys of your own go in attributes={{...}}"
        )
    return {**own, **keywords}


# Auto-generated ids stay stable for a given construction order, which is what
# the drift checks compare. Two "Azure Bastion" nodes become bastion, bastion-2.
_COUNTS: dict[str, int] = {}
#: Elements alive and not yet part of a closed diagram, by id. An id in use
#: is never minted again, so a node built before a Diagram block keeps its id
#: beside a namesake built inside the block. A closed diagram releases its
#: elements; an element nobody holds drops out on its own.
_LIVE: weakref.WeakValueDictionary[str, TopologyElement] = weakref.WeakValueDictionary()


def _auto_id(name: str) -> str:
    """A readable, unique-per-run id derived from the display name."""
    slug = slugify(name, fallback="node")
    seen = _COUNTS.get(slug, 0)
    if slug == ROOT_ID:
        # "root" names the undrawn root every document is wrapped in
        # (compose.to_project, Diagram.topology, every shipped template), so an
        # element called "Root" is numbered from -2 rather than colliding with it.
        seen = max(seen, 1)
    candidate = slug if not seen else f"{slug}-{seen + 1}"
    while candidate in _LIVE:
        seen += 1
        candidate = f"{slug}-{seen + 1}"
    _COUNTS[slug] = seen + 1
    return candidate


def _register(element: TopologyElement) -> None:
    """Hold the element's id while it lives outside a closed diagram."""
    _LIVE[element.id] = element


def release(elements: Iterable[TopologyElement]) -> None:
    """The elements of a closed diagram: their ids may be minted again."""
    for element in elements:
        if _LIVE.get(element.id) is element:
            del _LIVE[element.id]


def reset_counters() -> None:
    """Start numbering afresh for a new diagram; ids still in use stay taken."""
    _COUNTS.clear()


def reset_ids() -> None:
    """Forget auto-id counters and every held id. Tests build many trees in one process."""
    _COUNTS.clear()
    _LIVE.clear()


def _wire(sources: Any, targets: Any, *, direction: str, result: Any = None) -> Any:
    """Connect every source to every target; the operator's right operand comes back."""
    source_list = list(sources) if isinstance(sources, (list, tuple)) else [sources]
    target_list = list(targets) if isinstance(targets, (list, tuple)) else [targets]
    if not all(isinstance(item, TopologyElement) for item in (*source_list, *target_list)):
        return NotImplemented
    for source in source_list:
        source.to(*target_list, direction=direction)
    return targets if result is None else result


class _Scoped:
    """A container that is a ``with`` block: whatever is written inside joins it.

    ``row()``, ``column()`` and ``keep_order()`` are the only layout hints,
    and they read as methods on the frame rather than arguments on every line.
    """

    if TYPE_CHECKING:
        attributes: dict[str, Any]  # the element this is mixed into holds them

    def __enter__(self):
        _scope.open_frame(self)
        return self

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        try:
            # Only Group and Frame mix this in, and both are TopologyElements.
            _scope.close_frame(cast(TopologyElement, self))
        except RuntimeError:
            if exc_type is None:
                raise
        return False

    def row(self):
        """Lay this frame's children side by side."""
        self.attributes["flow"] = "row"
        return self

    def column(self):
        """Stack this frame's children."""
        self.attributes["flow"] = "column"
        return self

    def grid(self, columns: int | None = None):
        """Wrap this frame's children into rows, as many columns as bring the
        frame nearest a 16:10 shape. A frame whose axis is left to the layout
        wraps on its own once it holds five or more and runs long."""
        self.attributes["flow"] = "grid"
        if columns is not None:
            if isinstance(columns, bool) or not isinstance(columns, int) or columns < 1:
                raise ValueError("grid columns must be a positive integer")
            self.attributes["grid"] = columns
        else:
            self.attributes.pop("grid", None)
        return self

    def keep_order(self):
        """Keep the children exactly as written instead of moving them towards their wires."""
        self.attributes["arrange"] = "manual"
        return self


class Element(TopologyElement):
    """Base for every generated node class.

    The three class attributes are filled in by the inheritance chain rather
    than by the caller: ``COLLECTION`` on the vendor package, ``CATEGORY`` on
    the category module, ``ICON`` and ``TYPE`` on the leaf. An instance
    differs only in the name and detail passed at the call site.
    """

    ICON: ClassVar[str] = ""
    TYPE: ClassVar[str] = ""
    COLLECTION: ClassVar[str] = ""
    CATEGORY: ClassVar[str] = ""
    #: Colour, inherited like the icon is. ACCENT names a *theme role*
    #: ("accent", "link", "soft") so it re-reads in every skin; BRAND is a
    #: literal hex for artwork whose colour is the brand, and the generator
    #: fills it in from the catalog. Set either on a category base to tint a
    #: whole category, or pass accent=/brand= to tint one instance.
    ACCENT: ClassVar[str] = ""
    BRAND: ClassVar[str] = ""

    def __init__(
        self,
        name: str,
        detail: str | None = None,
        *,
        role: str | None = None,
        id: str | None = None,
        icon: str | None = None,
        accent: str | None = None,
        brand: str | None = None,
        **attributes: Any,
    ) -> None:
        attrs: dict[str, Any] = _checked(
            type(self).__name__,
            dict(attributes),
            ("detail", "role", "id", "icon", "accent", "brand"),
        )
        if detail is not None:
            attrs["detail"] = detail
        tint = accent or brand or self.ACCENT or self.BRAND
        if tint:
            attrs["accent"] = tint
        chosen = icon or self.ICON
        if chosen:
            attrs["icon"] = chosen
        if self.COLLECTION:
            attrs["collection"] = self.COLLECTION
        if self.CATEGORY:
            attrs["category"] = self.CATEGORY
        super().__init__(
            id=id or _auto_id(name),
            name=name,
            type=self.TYPE or chosen or "node",
            role=role,
            attributes=attrs,
        )
        _register(self)
        _scope.adopt(self)

    def table(self, columns: Sequence[str], rows: Iterable[Sequence[str]] = ()) -> Element:
        """Attach a table the editor shows when this element is selected.

            net.RouteTables("rt-spoke-prod", "UDR").table(
                ("Prefix", "Next hop type", "Next hop"),
                [("0.0.0.0/0", "Virtual appliance", "10.0.1.4"),
                 ("10.0.0.0/16", "VNet peering", "hub-vnet")])

        Nothing is drawn on the canvas: the card stays the card, and clicking
        it opens the table in a popup beside it. The rows are whatever you
        pass, so three routes and thirty are the same call. The table rides in
        the element's attributes, so it survives saving and reopening the page.
        """
        heading = tuple(str(value) for value in columns)
        if not heading:
            raise ValueError(f"{self.name!r}: a table needs at least one column")
        body = [[str(cell) for cell in row] for row in rows]
        wide = [row for row in body if len(row) > len(heading)]
        if wide:
            raise ValueError(
                f"{self.name!r}: {len(wide)} row(s) have more cells than the "
                f"{len(heading)} column(s) declared"
            )
        self.attributes["table"] = {"columns": list(heading), "rows": body}
        return self

    def sizing(self, **values: str | int | float) -> Element:
        """Say what this element is sized as, for the approximate price an
        export writes.

            compute.EC2("Web servers").sizing(instance_type="m6i.large", count=3)
            databases.RDS("Orders").sizing(engine="PostgreSQL", instance_class="db.m6g.large")

        Each service reads its own keys (references/export.md, Prices): a
        size or class, a ``region`` (else the region frame around it), a
        ``count``, ``hours`` a month (730), and for what is billed by use
        the quantities (storage, requests, data out). What is not said is
        priced as the service's default and marked assumed; a key the
        service does not read is refused, never ignored. Nothing is drawn:
        the sizing rides in the element's attributes, and the price shows in
        the page's Cost tab and the card's Details.
        """
        if not values:
            raise ValueError(
                f"{self.name!r}: sizing needs at least one value, like instance_type='t3.small'"
            )
        wrong = sorted(
            key
            for key, value in values.items()
            if isinstance(value, bool) or not isinstance(value, (str, int, float))
        )
        if wrong:
            raise ValueError(
                f"{self.name!r}: a sizing value is text or a number: {', '.join(wrong)}"
            )
        current = self.attributes.get("sizing")
        self.attributes["sizing"] = {**(current if isinstance(current, dict) else {}), **values}
        return self

    def tags(self, tags: Mapping[str, str] | None = None, **more: str) -> Element:
        """Say what tags this element wears, as the cloud's own tags or
        Kubernetes labels read.

            compute.EC2("Web servers").tags(env="prod", team="shop")
            Deploy("api").tags({"app.kubernetes.io/name": "api"})

        Nothing is drawn: the tags ride in the element's attributes, and in
        the page a right-click on the canvas lights the cards that wear one.
        ``import:terraform`` and the ``discover`` commands write them.
        """
        given = {**(tags or {}), **more}
        if not given:
            raise ValueError(f"{self.name!r}: tags needs at least one, like env='prod'")
        wrong = sorted(str(key) for key, value in given.items() if not isinstance(value, str))
        if wrong:
            raise ValueError(f"{self.name!r}: a tag's value is text: {', '.join(wrong)}")
        current = self.attributes.get("tags")
        self.attributes["tags"] = {
            **(current if isinstance(current, dict) else {}),
            **{str(key): value for key, value in given.items()},
        }
        return self

    def change(self, action: str) -> Element:
        """Say what a Terraform plan does to this element -- ``create``,
        ``update``, ``replace`` or ``delete`` -- so the picture shows it:
        the card in the action's colour and a mark on its detail line
        (``+ added``). ``import:terraform`` of a plan writes it for you.
        """
        from ..models.changes import ACTIONS

        if action not in ACTIONS:
            raise ValueError(
                f"{self.name!r}: change is one of {', '.join(ACTIONS)}, not {action!r}"
            )
        self.attributes["change"] = action
        return self

    # -- panels: a box that says more than a name and a detail line ----------
    def tone(self, name: str) -> Element:
        """Fill the box with a tone that means something -- ``edge``,
        ``private``, ``internal``, ``correction``, ``blocker``, ``managed``,
        ``neutral`` -- and say in ``Diagram(tones={...})`` what each means,
        so the legend lists it. A colour set by hand in the editor still wins.
        """
        from ..builders.panels import check_tone

        self.attributes["tone"] = check_tone(name, repr(self.name))
        return self

    def shape(self, name: str) -> Element:
        """Draw the box as an ``ellipse`` (a person, a customer), a
        ``hexagon`` (a managed control plane), a ``note`` (a folded corner,
        for a contract or a caveat) or the ``rect`` it is."""
        from ..builders.panels import BOXED, SHAPES

        if name not in SHAPES:
            raise ValueError(f"{self.name!r}: shape is one of {', '.join(SHAPES)}, not {name!r}")
        if self.attributes.get("sections") and name not in BOXED:
            raise ValueError(f"{self.name!r}: a {name} carries no compartments")
        self.attributes["shape"] = name
        return self

    def section(
        self, title: str = "", *lines: str, tone: str = "", beside: bool = False
    ) -> Element:
        """Add a compartment under the box's name: a title and lines, on a
        tone of its own if given. ``beside=True`` stands it beside the one
        before, in the same row::

            lb.section("Public frontend", "HTTPS 443 · Full (strict)", tone="edge")
            lb.section("Gateway backends", "health-checked targets", tone="private", beside=True)
            lb.section("Direct origin access must fail", tone="blocker")

        The box grows to what it carries, and draws so in the editor and in
        every export.
        """
        from ..builders.panels import BOXED, check_tone

        if self.attributes.get("shape", "rect") not in BOXED:
            raise ValueError(f"{self.name!r}: a {self.attributes['shape']} carries no compartments")
        if not title and not lines:
            raise ValueError(f"{self.name!r}: a compartment needs a title or a line")
        cell = {"title": str(title), "lines": [str(line) for line in lines]}
        if tone:
            cell["tone"] = check_tone(tone, repr(self.name))
        rows = self.attributes.setdefault("sections", [])
        if beside and rows:
            rows[-1].append(cell)
        else:
            rows.append([cell])
        return self

    # -- wires: between nodes, an arrow is a connection ----------------------
    def __rshift__(self, other: Any) -> Any:
        """Between two nodes, a wire from this one to *other* (or to each of a list).

        With a group or frame on the right the older meaning holds: the node
        becomes a zone holding it. A wire to a frame is written with an
        ``Edge`` or ``.to()``.
        """
        items = other if isinstance(other, (list, tuple)) else [other]
        if items and all(isinstance(item, Element) for item in items):
            return _wire(self, other, direction="forward")
        return TopologyElement.__rshift__(self, other)

    def __lshift__(self, other: Any) -> Any:
        """A wire from *other* to this node; the mirror of ``>>``.

        ``a << b`` is ``b >> a``: between two nodes a wire from *b* to *a*,
        and with a group or frame on the right the nesting ``b >> a`` would
        do, this node placed inside it. Anything ``>>`` would refuse (a
        list mixing nodes and frames) is refused here the same way.
        """
        items = other if isinstance(other, (list, tuple)) else [other]
        if items and all(isinstance(item, Element) for item in items):
            return _wire(other, self, direction="forward", result=other)
        if isinstance(other, TopologyElement):
            other._take(self)
            return other
        return NotImplemented

    def __sub__(self, other: Any) -> Any:
        """A wire with no arrowheads."""
        return _wire(self, other, direction="none")


class Group(TopologyElement, _Scoped):
    """A container that draws as a zone.

    Subscriptions, resource groups, virtual networks, regions -- the things
    that hold other things. ``kind`` is what the drawing calls it.

    Pass ``icon=`` to title the zone with its own artwork::

        Group("Azure Virtual Network", "vnet", icon=networking.VirtualNetworks)

    A generated node class used as a container does this for free: give it
    children and it becomes a zone, keeping the icon it already carries.
    """

    def __init__(
        self,
        name: str,
        kind: str = "group",
        *,
        role: str | None = None,
        id: str | None = None,
        accent: str | None = None,
        icon: Any = None,
        flow: str | None = None,
        **attributes: Any,
    ) -> None:
        attrs = _checked(
            type(self).__name__, dict(attributes), ("kind", "role", "id", "accent", "icon", "flow")
        )
        if flow:
            attrs["flow"] = flow
        if accent:
            attrs["accent"] = accent
        if icon is not None:
            # A node class, an instance of one, or a plain slug string.
            slug = getattr(icon, "ICON", "")
            collection = getattr(icon, "COLLECTION", "")
            if not slug:
                text = str(icon)
                collection, _, slug = text.rpartition(":")
            attrs["icon"] = slug
            if collection:
                attrs["collection"] = collection
        super().__init__(
            id=id or _auto_id(name),
            name=name,
            type=kind,
            role=role,
            attributes=attrs,
        )
        _register(self)
        _scope.adopt(self)


class Box(Element):
    """A plain box: no vendor artwork, only what it says. For a customer, a
    contract, a caveat or a decision the picture has to carry::

        Box("1 · Customer", "HTTPS 443").shape("ellipse").tone("internal")
        Box("Network contract", "Gateway-only backend ingress").shape("note")

    It is the library's Custom Resource, so the editor treats it as one.
    """

    ICON: ClassVar[str] = "custom-resource"
    TYPE: ClassVar[str] = "box"
    COLLECTION: ClassVar[str] = "infragram"
    CATEGORY: ClassVar[str] = "custom"

    # declared here so a type checker reads the call, as each generated
    # class declares it in its stub
    def __init__(
        self,
        name: str,
        detail: str | None = None,
        *,
        role: str | None = None,
        id: str | None = None,
        icon: str | None = None,
        accent: str | None = None,
        brand: str | None = None,
        **attributes: Any,
    ) -> None:
        super().__init__(
            name, detail, role=role, id=id, icon=icon, accent=accent, brand=brand, **attributes
        )


class Frame(TopologyElement, _Scoped):
    """A containment frame from the shared frame gallery.

    Where :class:`Group` is a plain zone the theme styles by kind, a Frame is
    one of the catalog's provider-aware frames (an Azure VNet or resource
    group, an AKS cluster, a generic DMZ). It carries the frame's
    component id and gallery group, so the editor draws the same tab, glyph
    and colour the sidebar offers, and the exported document round-trips.

    Subclasses are generated per frame group under :mod:`infragram.nodes.frames`.
    A frame is a ``with`` block; whatever is written inside it belongs to it::

        from infragram.nodes.frames import azure

        with azure.VNet("VNet 10.0.0.0/16"):
            with azure.Subnet("snet-app 10.0.1.0/24"):
                ...

    ``.row()`` or ``.column()`` overrides the layout axis for the children;
    the older ``vnet >> azure.Subnet(...)`` form still nests.
    """

    FRAME_ID: ClassVar[str] = ""
    KIND: ClassVar[str] = "group"
    GROUP: ClassVar[str] = "generic"
    LABEL: ClassVar[str] = ""

    def __init__(
        self,
        name: str = "",
        *,
        role: str | None = None,
        id: str | None = None,
        flow: str | None = None,
        **attributes: Any,
    ) -> None:
        attrs: dict[str, Any] = _checked(
            type(self).__name__, dict(attributes), ("role", "id", "flow")
        )
        if flow:
            attrs["flow"] = flow
        attrs["editor_frame_group"] = self.GROUP
        label = name or self.LABEL or self.KIND
        component = (
            ComponentRef(provider="infragram", service_id=self.FRAME_ID) if self.FRAME_ID else None
        )
        super().__init__(
            id=id or _auto_id(label),
            name=label,
            type=self.KIND,
            role=role,
            component=component,
            attributes=attrs,
        )
        _register(self)
        _scope.adopt(self)
