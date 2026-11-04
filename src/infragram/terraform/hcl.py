"""HCL, written the way ``terraform fmt`` writes it.

The emitter builds blocks, attributes and comments; this module turns them
into text. The output is canonical as ``terraform fmt`` leaves it, so an
emitted tree passes ``terraform fmt -check`` without ever running Terraform:

- two spaces of indent per level;
- the ``=`` of consecutive single-line attributes aligned, a group broken by
  a blank line, a comment, a nested block or a value that spans lines;
- an object is written one key per line, a list of scalars on one line.

Values are Python scalars, lists and dicts, :class:`Raw` for an expression
written as is (``var.region``, ``aws_vpc.this.id``, ``merge(...)``), and
:class:`Block` for a nested block. A string is a template: it is quoted and
its ``${...}`` interpolations are kept. Text taken from a diagram goes through
:func:`literal` first, so a caption holding ``${`` stays text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from pydantic import ConfigDict, Field

from .model import Record

__all__ = [
    "BLANK",
    "Attr",
    "Bare",
    "Block",
    "Comment",
    "Raw",
    "identifier",
    "literal",
    "quote",
    "render",
]

#: An argument name or object key that needs no quotes.
_BARE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class Raw(Record):
    """An expression written exactly as given."""

    model_config = ConfigDict(frozen=True)

    text: str


class Bare(str):
    """An object key written as it is, never quoted: a provider configuration
    in a module call's ``providers`` (``aws.eu_west_1 = aws.eu_west_1``)."""


class Comment(Record):
    """A ``#`` comment line; a long text is wrapped to the line length."""

    model_config = ConfigDict(frozen=True)

    text: str


class _Blank:
    def __repr__(self) -> str:
        return "BLANK"


#: A blank line between two items of a body.
BLANK = _Blank()


class Attr(Record):
    """``name = value``."""

    name: str
    value: object


class Block(Record):
    """``type "label" ... { body }``."""

    type: str
    labels: tuple[str, ...] = ()
    body: list[object] = Field(default_factory=list)

    def add(self, *items: object) -> Block:
        self.body.extend(items)
        return self


def identifier(text: str) -> str:
    """A Terraform identifier for a name: letters, digits, underscores and
    dashes, starting with a letter or an underscore."""

    name = re.sub(r"[^A-Za-z0-9_]+", "_", text.strip()).strip("_").lower()
    name = re.sub(r"_+", "_", name)
    if not name:
        return "unnamed"
    if not (name[0].isalpha() or name[0] == "_"):
        name = f"n_{name}"
    return name


def literal(text: str) -> str:
    """Text that is never a template: ``${`` and ``%{`` written as ``$${``
    and ``%%{``, which Terraform reads back as the characters themselves."""

    return text.replace("${", "$${").replace("%{", "%%{")


def quote(text: str) -> str:
    """A quoted HCL string; ``${...}`` interpolations are kept as written."""

    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


#: What marks a :class:`Bare` key through an :class:`Attr`, whose name is a plain string.
_BARE_MARK = "\x00"


def _key(name: str) -> str:
    if name.startswith(_BARE_MARK):
        return name[len(_BARE_MARK) :]
    return name if _BARE_KEY.match(name) else quote(name)


def _scalar(value: object) -> str | None:
    """The one-line text of a scalar, or None for a value that is not one."""

    if isinstance(value, Raw):
        return value.text
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, str):
        return quote(value)
    return None


def _one_line(value: object) -> str | None:
    """The value on one line, or None when it must span lines."""

    text = _scalar(value)
    if text is not None:
        return text
    if isinstance(value, list):
        if not value:
            return "[]"
        items = [_scalar(item) for item in value]
        if all(item is not None for item in items):
            return "[" + ", ".join(items) + "]"  # type: ignore[arg-type]
        return None
    if isinstance(value, dict) and not value:
        return "{}"
    return None


def _value_lines(value: object, indent: int) -> list[str]:
    """A value that spans lines: an object, or a list holding objects."""

    pad = "  " * indent
    if isinstance(value, dict):
        lines = ["{"]
        lines += _body_lines(
            [
                Attr(f"{_BARE_MARK}{key}" if isinstance(key, Bare) else key, item)
                for key, item in value.items()
            ],
            indent + 1,
        )
        lines.append(f"{pad}}}")
        return lines
    if isinstance(value, list):
        lines = ["["]
        for item in value:
            one = _one_line(item)
            if one is not None:
                lines.append(f"{pad}  {one},")
            else:
                inner = _value_lines(item, indent + 1)
                lines.append(f"{pad}  {inner[0]}")
                lines.extend(inner[1:-1])
                lines.append(f"{inner[-1]},")
        lines.append(f"{pad}]")
        return lines
    raise TypeError(f"cannot write {value!r} as HCL")


def _wrap(text: str, width: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    if line:
        lines.append(line)
    return lines or [""]


def _body_lines(items: Sequence[object], indent: int) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    group: list[tuple[str, str]] = []

    def flush() -> None:
        if group:
            width = max(len(name) for name, _ in group)
            lines.extend(f"{pad}{name.ljust(width)} = {text}" for name, text in group)
            group.clear()

    for item in items:
        if isinstance(item, Attr):
            one = _one_line(item.value)
            if one is not None and "\n" not in one:
                group.append((_key(item.name), one))
                continue
            flush()
            if one is not None:
                # an expression written over several lines (a for expression,
                # an object type): its lines after the first keep their own
                # indent, under the attribute's
                first, *rest = one.split("\n")
                lines.append(f"{pad}{_key(item.name)} = {first}")
                lines.extend(f"{pad}{line}" if line.strip() else "" for line in rest)
                continue
            multi = _value_lines(item.value, indent)
            lines.append(f"{pad}{_key(item.name)} = {multi[0]}")
            lines.extend(multi[1:])
            continue
        flush()
        if item is BLANK:
            lines.append("")
        elif isinstance(item, Comment):
            lines.extend(f"{pad}# {line}".rstrip() for line in _wrap(item.text, 76 - len(pad)))
        elif isinstance(item, Block):
            lines.extend(_block_lines(item, indent))
        else:
            raise TypeError(f"cannot write {item!r} in a body")
    flush()
    return lines


def _block_lines(block: Block, indent: int) -> list[str]:
    pad = "  " * indent
    head = " ".join([block.type, *(quote(label) for label in block.labels)])
    if not block.body:
        return [f"{pad}{head} {{}}"]
    return [f"{pad}{head} {{", *_body_lines(block.body, indent + 1), f"{pad}}}"]


def render(items: Iterable[object]) -> str:
    """A file: top-level blocks and comments, one blank line between blocks."""

    lines: list[str] = []
    previous: object = None
    for item in items:
        if isinstance(item, Block):
            if lines and previous is not None and not isinstance(previous, Comment):
                lines.append("")
            lines.extend(_block_lines(item, 0))
        elif isinstance(item, Comment):
            if lines and isinstance(previous, Block):
                lines.append("")
            lines.extend(f"# {line}".rstrip() for line in _wrap(item.text, 78))
        elif item is BLANK:
            lines.append("")
        else:
            raise TypeError(f"cannot write {item!r} at the top of a file")
        previous = item
    return "\n".join(lines) + "\n"
