"""``infragram docs``: the reference documents the skill ships, from the
command line.

The references (``compose.md``, ``frames.md``, ``export.md``, one per
provider library...) are what an agent reads before drawing, and what the
MCP server serves as ``infragram://references/*``; an installed copy keeps
them inside the package, where nobody would look. This lists them with what
each is about, prints one, or says where it is. They are read through
:func:`infragram.paths.skill_references`, so a wheel works with no checkout.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict

__all__ = ["Reference", "main", "references", "resolve"]


class Reference(BaseModel):
    """One reference document: the name ``docs`` takes, its file, and what it is about."""

    model_config = ConfigDict(frozen=True)

    name: str
    path: Path
    title: str


def _title(path: Path) -> str:
    """What a document is about in one line: its first heading, or failing
    that its first sentence."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    words = " ".join(text.split())
    sentence = re.match(r"(.+?[.!?])(?:\s|$)", words)
    return (sentence.group(1) if sentence else words)[:120]


def references() -> dict[str, Reference]:
    """name -> the reference, for every Markdown reference the skill ships:
    ``compose``, ``frames``..., then ``providers/aws`` and the other
    libraries' own."""
    from ...paths import skill_references

    root = skill_references()
    paths = sorted(root.glob("*.md")) + sorted((root / "providers").glob("*.md"))
    out: dict[str, Reference] = {}
    for path in paths:
        name = path.relative_to(root).with_suffix("").as_posix()
        out[name] = Reference(name=name, path=path, title=_title(path))
    return out


def resolve(name: str) -> Reference | None:
    """The reference *name* means: ``compose``, ``compose.md``,
    ``providers/aws``, ``providers\\aws.md``, or a library's own by its id
    alone (``aws``) when no other document has that name."""
    shipped = references()
    key = name.strip().replace("\\", "/").removesuffix(".md").strip("/")
    for candidate in (key, key.casefold(), f"providers/{key.casefold()}"):
        if candidate in shipped:
            return shipped[candidate]
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="infragram docs",
        description="List the reference documents the skill ships, with what each is about; "
        "name one to print it (compose, frames, providers/aws, or just aws).",
    )
    parser.add_argument(
        "name", nargs="?", help="the document to print: compose, compose.md, providers/aws, aws"
    )
    parser.add_argument(
        "--path",
        action="store_true",
        help="print where the document is instead of its contents (with no name: the folder)",
    )
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if options.name is None:
        if options.path:
            from ...paths import skill_references

            print(skill_references().resolve())
            return 0
        shipped = references()
        width = max(map(len, shipped), default=0)
        for name, reference in shipped.items():
            print(f"{name:<{width}}  {reference.title}")
        return 0
    found = resolve(options.name)
    if found is None:
        names = list(references())
        key = options.name.replace("\\", "/").removesuffix(".md")
        near = difflib.get_close_matches(key, names, n=3) or difflib.get_close_matches(
            f"providers/{key}", names, n=3
        )
        hint = f"; did you mean {', '.join(near)}?" if near else "; infragram docs lists them"
        print(f"ERROR: no reference {options.name!r}{hint}", file=sys.stderr)
        return 2
    if options.path:
        print(found.path.resolve())
    else:
        sys.stdout.write(found.path.read_text(encoding="utf-8"))
    return 0
