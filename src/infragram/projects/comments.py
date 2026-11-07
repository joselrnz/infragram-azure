"""Comments on a diagram: a file beside the document, carried into its page.

ADR 0009. A reviewer comments on cards, frames and wires in the exported page;
**Download comments** gives them a ``<slug>.comments.json`` to send back or
commit beside the ``.infragram.json``. An export finds that file beside the
document it draws (or in the page it is given) and carries it into the page it
writes. Nothing here reaches the network, and the SVG, PNG and draw.io never
carry a comment.

A comment anchors to an element by kind and id, and remembers the element's
name, so a page can still place it after the id changes (a Python diagram that
renamed a card without ``id=``); one that matches neither is shown as detached,
never dropped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "COMMENTS_FORMAT",
    "Anchor",
    "Comment",
    "Comments",
    "comments_path",
    "find_comments",
    "page_comments",
]

COMMENTS_FORMAT: Final = "infragram.comments/1"


class Anchor(BaseModel):
    """What a comment is about: one card, frame or wire."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["node", "boundary", "edge"]
    id: str = Field(min_length=1, max_length=200)
    #: the element's name (a wire's label) when the comment was made
    name: str = Field(default="", max_length=300)


class Comment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^c-[a-z0-9-]{4,60}$")
    anchor: Anchor
    author: str = Field(default="", max_length=80)
    text: str = Field(min_length=1, max_length=4000)
    #: when it was written, ISO 8601
    at: str = Field(min_length=10, max_length=40)


class Comments(BaseModel):
    """A ``<slug>.comments.json``: every comment on one document."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["infragram.comments/1"] = COMMENTS_FORMAT
    slug: str = Field(min_length=1, max_length=200)
    comments: list[Comment] = Field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> Comments:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def page_json(self) -> str:
        """The JSON a page carries, compact."""
        return json.dumps(self.model_dump(), separators=(",", ":"), ensure_ascii=False)


def comments_path(folder: Path, slug: str) -> Path:
    """Where the comments on the document *slug* sit, in *folder*."""
    return folder / f"{slug}.comments.json"


def find_comments(folder: Path, slug: str) -> Comments | None:
    """The comments file beside a document, or None when there is none.

    A file that is there but is not a comments file for this document is an
    error, not a silence: a reviewer's comments should never vanish quietly.
    """
    path = comments_path(folder, slug)
    if not path.is_file():
        return None
    found = Comments.load(path)
    if found.slug != slug:
        raise ValueError(f"{path.name} holds comments on {found.slug!r}, not {slug!r}")
    return found


def page_comments(html: str) -> Comments | None:
    """The comments a page carries, or None."""
    import re
    from html import unescape

    match = re.search(
        r'<script type="application/json" id="infragram-comments">(.*?)</script>', html, re.S
    )
    if match is None:
        return None
    raw = match.group(1)
    try:
        return Comments.model_validate_json(raw)
    except ValueError:
        return Comments.model_validate_json(unescape(raw))
