"""A wire between two elements: its label, its line, its style and its sides."""

from __future__ import annotations

import difflib
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, PrivateAttr, field_validator, model_validator

from ..models.topology import TopologyElement
from ..themes.colour import HEX_COLOUR

__all__ = ["SIDES", "Edge"]


def _elements(value: Any) -> list[TopologyElement]:
    items = list(value) if isinstance(value, (list, tuple)) else [value]
    for item in items:
        if not isinstance(item, TopologyElement):
            raise TypeError(f"a wire joins nodes and frames, not {type(item).__name__}")
    return items


def _known_corners(value: str | None) -> str | None:
    if value is None:
        return None
    from ..builders import metrics

    if value not in metrics.corner_styles():
        raise ValueError(f"unknown corner style {value!r}; one of {list(metrics.corner_styles())}")
    return value


#: The sides a wire may be told to use. A node has one connection point a
#: side, which both renderers anchor to.
SIDES = ("top", "right", "bottom", "left")


#: The per-wire keys an Edge writes into ``editor_edge_styles``.
_EDGE_STYLE_KEYS = ("arrow", "corners", "source_port", "target_port", "stroke", "width")

#: The keywords ``Edge(...)`` takes, for a "did you mean" on a misspelt one.
_KEYWORDS = (
    "dashed",
    "dotted",
    "kind",
    "both",
    "arrow",
    "corners",
    "leaves",
    "arrives",
    "step",
    "says",
    "flow",
    "color",
    "width",
)


def _refuse_conflicting_parallel_style(
    source: TopologyElement, target: TopologyElement, style: dict[str, str | float]
) -> None:
    """A second wire between the same pair must ask for the style the first has.

    The document keys wire styles by target id, one dict per source, so the
    format cannot hold two styles for two parallel wires. The conflict is
    refused where it is written instead of drawing both wires with whichever
    style was written last.
    """
    if not any(connection.target == target.id for connection in source.connections):
        return
    recorded = (source.attributes.get("editor_edge_styles") or {}).get(target.id) or {}
    existing = {key: recorded[key] for key in _EDGE_STYLE_KEYS if key in recorded}
    if existing != style:
        raise ValueError(
            f"{source.name!r} already has a wire to {target.name!r} with "
            f"{existing or 'no arrow, corner or side choice'}; parallel wires between one pair "
            f"share one arrow, corner style and pair of sides in the document, so this one "
            f"cannot ask for "
            f"{style or 'none'}"
        )


class Edge(BaseModel):
    """A wire's label and style, written between two elements.

        a >> Edge("HTTPS") >> b              # a to b
        a << Edge("replicates") << b         # b to a
        a - Edge("peering") - b              # no arrowheads
        a >> Edge("fan out") >> [b, c]       # one to many

    ``dashed`` and ``dotted`` choose the line; ``kind=`` names any kind the
    provider theme defines (AWS: ``vpn``, ``vif``, ``local``). ``both=True``
    puts a head at each end. The plain ``a >> b`` is the same wire without a
    label; ``a.to(b, label=...)`` remains for dense diagrams where operators
    get noisy.

    ``leaves`` and ``arrives`` say which side of each card the wire uses --
    ``top``, ``right``, ``bottom`` or ``left`` -- when where the cards stand
    is not the reading you want::

        gateway >> Edge("HTTPS", leaves="bottom", arrives="top") >> web

    ``color`` and ``width`` restyle one wire -- a hex colour and a stroke
    width in pixels, 0.5 to 8 -- where its kind's own line is not the
    point you are making::

        attacker >> Edge("exfiltration", color="#d13438", width=2.5) >> bucket

    Both renderers draw them; the editor's Line tab shows and changes them.

    ``leaves`` is the end the wire starts from (the right-hand element of
    ``a << Edge(...) << b``, as that wire runs from ``b``). A node has one
    connection point a side, so those are the choices; left out,
    both renderers anchor the wire where the two cards stand. They are the
    Text tab's *Leaves from* and *Arrives at*, and the document's
    ``source_port`` and ``target_port`` in ``editor_edge_styles``.

    An edge is frozen once written: its label, kind, direction and style
    are validated at the line that wrote them and never change afterwards.

    One limit comes from the document: ``arrow``, ``corners``, ``color`` and
    ``width`` are stored per source element keyed by the target's id
    (``editor_edge_styles``), not per wire, and so are the sides, so two
    wires between the same pair share one arrow, corner style, colour, width
    and pair of sides. Writing a second wire
    between a pair whose style differs
    from the first raises at that line rather than silently drawing both
    the same. Labels, line kinds and directions are per wire and free.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = ""
    kind: str = "solid"
    direction: Literal["forward", "both", "none"] = "forward"
    #: The head shape (``arrowheads.json``); None takes the theme's default.
    arrow: str | None = None
    #: The bend style (``render-metrics.json`` ``router.corners``); None takes the default.
    corners: str | None = None
    #: The side of each card the wire leaves and arrives at; None lets both
    #: renderers anchor it where the two cards stand.
    leaves: str | None = None
    arrives: str | None = None
    #: Where the wire comes in a flow told in order: a numbered circle at the
    #: start of its caption, and ``says`` (else the caption) in the step list.
    step: int | None = None
    says: str | None = None
    #: A second flow's name: the step is marked the theme's second way (AWS
    #: lettered, Azure a blue square, Google lettered in green) and listed
    #: under the name. None is the main flow.
    flow: str | None = None
    #: One wire's own colour (hex) and stroke width in px; None takes its kind's.
    color: str | None = None
    width: float | None = None
    _left: Any = PrivateAttr(default=None)

    def __init__(
        self,
        label: str = "",
        *,
        dashed: bool = False,
        dotted: bool = False,
        kind: str | None = None,
        both: bool = False,
        arrow: str | None = None,
        corners: str | None = None,
        leaves: str | None = None,
        arrives: str | None = None,
        step: int | None = None,
        says: str | None = None,
        flow: str | None = None,
        color: str | None = None,
        width: float | None = None,
        **unknown: Any,
    ) -> None:
        if unknown:
            name = next(iter(unknown))
            near = difflib.get_close_matches(name, _KEYWORDS, n=1, cutoff=0.6)
            hint = f"; did you mean {near[0]}=?" if near else f"; it takes {', '.join(_KEYWORDS)}"
            raise TypeError(f"Edge() takes no keyword {name!r}{hint}")
        super().__init__(
            label=label,
            kind=kind or ("dashed" if dashed else "dotted" if dotted else "solid"),
            direction="both" if both else "forward",
            arrow=arrow,
            corners=corners,
            leaves=leaves,
            arrives=arrives,
            step=step,
            says=says,
            flow=flow,
            color=color,
            width=width,
        )

    @model_validator(mode="after")
    def _a_step_numbers_a_caption(self) -> Edge:
        if self.step is not None and not self.label.strip():
            raise ValueError(
                f"Edge(step={self.step}) numbers a caption: give it a label, Edge('push', step=1)"
            )
        if self.step is not None and not 1 <= self.step <= 99:
            raise ValueError(f"Edge(step={self.step}): a step is 1 to 99")
        if self.says is not None and self.step is None:
            raise ValueError("Edge(says=...) is a step's line in the step list: give it a step too")
        if self.flow is not None and self.step is None:
            raise ValueError("Edge(flow=...) names the flow a step belongs to: give it a step too")
        if self.flow is not None and not self.flow.strip():
            raise ValueError(
                "Edge(flow=...) needs a name, Edge('pulls', step=1, flow='At runtime')"
            )
        return self

    @field_validator("arrow")
    @classmethod
    def _known_head(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from ..builders import arrowheads

        if value not in arrowheads.heads():
            raise ValueError(f"unknown arrowhead {value!r}; one of {sorted(arrowheads.heads())}")
        return value

    @field_validator("corners")
    @classmethod
    def _known_corners(cls, value: str | None) -> str | None:
        return _known_corners(value)

    @field_validator("color")
    @classmethod
    def _a_hex_colour(cls, value: str | None) -> str | None:
        if value is not None and not HEX_COLOUR.match(value):
            raise ValueError(f"Edge(color={value!r}): a hex colour, '#d13438' or '#d34'")
        return value

    @field_validator("width")
    @classmethod
    def _a_stroke_width(cls, value: float | None) -> float | None:
        if value is not None and not 0.5 <= value <= 8:
            raise ValueError(f"Edge(width={value}): a stroke width from 0.5 to 8 px")
        return value

    @field_validator("leaves", "arrives")
    @classmethod
    def _known_side(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in SIDES:
            raise ValueError(f"unknown side {value!r}; one of {', '.join(SIDES)}")
        return value

    def _wire(self, sources: Any, targets: Any, direction: str | None = None) -> None:
        style = {
            key: value
            for key, value in (
                ("arrow", self.arrow),
                ("corners", self.corners),
                ("source_port", self.leaves),
                ("target_port", self.arrives),
                ("stroke", self.color),
                ("width", self.width),
            )
            if value
        }
        for source in _elements(sources):
            for target in _elements(targets):
                _refuse_conflicting_parallel_style(source, target, style)
                source.to(
                    target,
                    kind=self.kind,
                    label=self.label,
                    direction=direction or self.direction,  # type: ignore[arg-type]
                    step=self.step,
                    step_text=self.says,
                    step_flow=self.flow,
                )
                if style:
                    styles = source.attributes.setdefault("editor_edge_styles", {})
                    styles.setdefault(target.id, {}).update(style)

    # a >> Edge(...) >> b
    def __rrshift__(self, left: Any) -> Edge:
        self._left = left
        return self

    def __rshift__(self, right: Any) -> Any:
        self._wire(self._left, right)
        return right

    # a << Edge(...) << b   (b to a)
    def __rlshift__(self, left: Any) -> Edge:
        self._left = left
        return self

    def __lshift__(self, right: Any) -> Any:
        self._wire(right, self._left)
        return right

    # a - Edge(...) - b   (no arrowheads)
    def __rsub__(self, left: Any) -> Edge:
        self._left = left
        return self

    def __sub__(self, right: Any) -> Any:
        self._wire(self._left, right, direction="none")
        return right
