"""What a diagram from another tool holds: shapes, what holds them, the links.

Every reader (draw.io, Mermaid, PlantUML, Excalidraw, Visio) fills the same
:class:`Sketch`, in the source's own terms, so one matching step and one
drawing step serve them all. A shape keeps what its tool said it is (a
stencil, an icon, a macro, a shape family) as :class:`Hint` records; which
component that means is :mod:`.match`'s question, not the reader's.
"""

from __future__ import annotations

import html
import re
from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["Bounds", "Hint", "Link", "Shape", "Sketch", "clean_text", "split_label", "words"]

#: The shape families the readers name; ``text`` is an annotation, never a
#: component, and ``box`` says nothing beyond "a shape".
Kind = Literal[
    "box",
    "database",
    "actor",
    "cloud",
    "queue",
    "file",
    "storage",
    "text",
    "ellipse",
    "diamond",
    "hexagon",
    "image",
    "cache",
]


class Hint(BaseModel):
    """What a shape's own tool calls it: ``Hint(provider="aws", phrase="lambda function")``.

    ``provider`` is a library the source names outright (a draw.io
    ``mxgraph.aws4`` stencil, an ``AWS-PlantUML`` macro); ``None`` is a phrase
    that could be anyone's (a C4 technology, a ``logos:redis`` icon).
    ``frame`` marks a phrase that names a container (an AWS VPC group).
    """

    provider: str | None = None
    phrase: str
    frame: bool = False
    #: where the phrase came from, for the popup: ``mxgraph.aws4.lambda_function``
    raw: str = ""


class Bounds(BaseModel):
    """A shape's place on the source's canvas, where it has one."""

    x: float
    y: float
    width: float
    height: float

    def holds(self, other: Bounds, slack: float = 2.0) -> bool:
        return (
            other.x >= self.x - slack
            and other.y >= self.y - slack
            and other.x + other.width <= self.x + self.width + slack
            and other.y + other.height <= self.y + self.height + slack
        )

    def has(self, x: float, y: float, slack: float = 8.0) -> bool:
        return (
            self.x - slack <= x <= self.x + self.width + slack
            and self.y - slack <= y <= self.y + self.height + slack
        )

    @property
    def area(self) -> float:
        return max(self.width, 0.0) * max(self.height, 0.0)


class Shape(BaseModel):
    """One node, group or annotation of the source."""

    #: unique within the sketch: the source's own id
    key: str
    label: str = ""
    detail: str = ""
    #: the key of the shape holding this one, if any
    parent: str | None = None
    #: the source drew it as holding others (a swimlane, a subgraph, a group)
    container: bool = False
    kind: Kind = "box"
    hints: list[Hint] = Field(default_factory=list)
    #: the component the source says outright (``aws:ec2``): a .drawio file
    #: Infragram exported names each element's, so it reads back exactly
    component: str | None = None
    #: the shape's own properties (draw.io data, C4 descriptions), for the popup
    rows: list[tuple[str, str]] = Field(default_factory=list)
    #: where it was read: ``page Network, cell 7``
    source: str = ""
    box: Bounds | None = None
    #: ``row`` or ``column`` when the source says how its children run
    flow: Literal["row", "column"] | None = None
    #: the panel shape the source drew it as (compose.md, Panels): a Mermaid
    #: ``((circle))`` is an ellipse, ``{{hexagon}}`` a hexagon
    outline: Literal["", "ellipse", "hexagon", "note"] = ""
    #: the panel tone its fill reads as (render-metrics.json ``tones``)
    tone: str = ""


class Link(BaseModel):
    """A line between two shapes."""

    source: str
    target: str
    label: str = ""
    dashed: bool = False
    direction: Literal["forward", "both", "none"] = "forward"
    #: where it was read, for the report
    origin: str = ""


class Sketch(BaseModel):
    """One diagram one file holds: a draw.io page, a Mermaid block."""

    title: str
    #: where it was read, in a phrase: ``network.drawio, page "Prod"``
    origin: str
    #: ``drawio``, ``mermaid``, ``plantuml``, ``excalidraw`` or ``visio``
    format: str
    shapes: list[Shape] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    #: what the reader passed over, for the report
    notes: list[str] = Field(default_factory=list)
    #: ``row`` or ``column`` for the whole diagram (a Mermaid ``flowchart LR``)
    flow: Literal["row", "column"] | None = None
    #: tone -> what the source's own class names say it means, for the legend
    tones: dict[str, str] = Field(default_factory=dict)

    def shape(self, key: str) -> Shape | None:
        for shape in self.shapes:
            if shape.key == key:
                return shape
        return None


_TAGS = re.compile(r"<[^>]+>")
_BREAKS = re.compile(r"<\s*br\s*/?\s*>|</\s*(?:div|p|li|h\d)\s*>", re.IGNORECASE)


def clean_text(text: str | None) -> str:
    """A label as plain lines: HTML tags and entities gone, breaks kept as newlines."""
    if not text:
        return ""
    out = _BREAKS.sub("\n", text.replace("\\n", "\n"))
    out = _TAGS.sub("", out)
    out = html.unescape(out).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in out.splitlines()]
    return "\n".join(line for line in lines if line)


def split_label(text: str | None) -> tuple[str, str]:
    """A label's first line as the caption, the rest as the detail."""
    lines = clean_text(text).splitlines()
    if not lines:
        return "", ""
    return lines[0], " ".join(lines[1:])


_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def words(text: str) -> str:
    """``Lambda_Function``, ``lambda-function``, ``LambdaFunction`` -> ``lambda function``."""
    spaced = _CAMEL.sub(" ", text)
    return " ".join(re.sub(r"[^0-9A-Za-z]+", " ", spaced).lower().split())
