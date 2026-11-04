"""Diagrams from other tools into infragram diagram files.

``infragram import:diagram`` reads a draw.io, Mermaid, PlantUML, Excalidraw
or Visio file (or every Mermaid and PlantUML block of a Markdown page),
matches each shape to a library component, and writes the diagram file the
composer draws, beside a report of where every shape went:

- :mod:`.drawio`, :mod:`.mermaid`, :mod:`.plantuml` (with :mod:`.c4`),
  :mod:`.excalidraw` and :mod:`.visio` read their format into a
  :class:`~.model.Sketch`;
- :mod:`.match` says which component or frame each shape is;
- :mod:`.draw` makes the drawing :func:`infragram.estate.write_spec` writes,
  and :mod:`.report` the report.

``references/import-diagrams.md`` is the method, for people and agents.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .draw import draw_sketch
from .drawio import DrawioError, read_drawio
from .excalidraw import ExcalidrawError, read_excalidraw, read_excalidraw_text
from .mermaid import MermaidError, read_mermaid
from .model import Sketch
from .plantuml import PlantumlError, read_plantuml
from .report import write_sketch_report
from .visio import VisioError, read_visio

__all__ = [
    "FORMATS",
    "DiagramError",
    "detect_format",
    "draw_sketch",
    "read_diagrams",
    "write_sketch_report",
]

#: The formats ``--format`` names; ``markdown`` reads a page's fenced blocks.
FORMATS = ("drawio", "mermaid", "plantuml", "excalidraw", "visio", "markdown")
# A Visio part that is not XML, or declares an entity, is the file's fault
# like any other; draw.io words its own.
_ERRORS = (DrawioError, MermaidError, PlantumlError, ExcalidrawError, VisioError, ET.ParseError)


class DiagramError(ValueError):
    """The file is not a diagram any reader draws."""


_SUFFIXES = (
    (".drawio.png", "drawio"),
    (".drawio.svg", "drawio"),
    (".drawio.xml", "drawio"),
    (".drawio", "drawio"),
    (".dio", "drawio"),
    (".excalidraw.md", "excalidraw"),
    (".excalidraw.json", "excalidraw"),
    (".excalidraw", "excalidraw"),
    (".mmd", "mermaid"),
    (".mermaid", "mermaid"),
    (".puml", "plantuml"),
    (".plantuml", "plantuml"),
    (".pu", "plantuml"),
    (".iuml", "plantuml"),
    (".wsd", "plantuml"),
    (".vsdx", "visio"),
    (".md", "markdown"),
    (".markdown", "markdown"),
)
_MERMAID_START = re.compile(
    r"^\s*(?:---.*?---\s*)?(?:%%.*\n\s*)*(?:flowchart|graph|architecture|C4\w+)\b", re.DOTALL
)


def detect_format(path: Path) -> str:
    """The format a file is written in, by its name and then its first bytes."""
    name = path.name.lower()
    if name.endswith(".vsd"):
        raise DiagramError(
            f"{path.name} is Visio's older binary format: save it as .vsdx and import that"
        )
    for suffix, found in _SUFFIXES:
        if name.endswith(suffix):
            if (
                found == "markdown"
                and "excalidraw-plugin"
                in path.read_text(encoding="utf-8-sig", errors="replace")[:400]
            ):
                return "excalidraw"
            return found
    head = path.read_bytes()[:4096]
    if head.startswith(b"\x89PNG") or head.startswith(b"PK"):
        return "drawio" if head.startswith(b"\x89PNG") else "visio"
    text = head.decode("utf-8", errors="replace").lstrip("﻿")
    if "<mxfile" in text or "<mxGraphModel" in text or 'content="&lt;mxfile' in text:
        return "drawio"
    if text.lstrip().startswith("@start"):
        return "plantuml"
    if '"type": "excalidraw"' in text or '"type":"excalidraw"' in text:
        return "excalidraw"
    if _MERMAID_START.match(text):
        return "mermaid"
    raise DiagramError(
        f"cannot tell what {path.name} is; name its format with --format ({', '.join(FORMATS)})"
    )


def _stem(path: Path) -> str:
    name = path.name
    for suffix, _ in _SUFFIXES:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


_FENCE = re.compile(
    r"^(?P<fence>```+|~~~+)\s*(?P<lang>mermaid|plantuml|puml)\b[^\n]*\n(?P<body>.*?)^(?P=fence)\s*$",
    re.MULTILINE | re.DOTALL,
)


def _markdown(path: Path, text: str) -> list[Sketch]:
    """Every Mermaid and PlantUML block of a Markdown page, titled by its heading."""
    stem = _stem(path)
    sketches: list[Sketch] = []
    passed: list[str] = []
    blocks = list(_FENCE.finditer(text))
    for number, block in enumerate(blocks, start=1):
        headings = re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", text[: block.start()], re.MULTILINE)
        title = headings[-1] if headings else f"{stem} {number}" if len(blocks) > 1 else stem
        line = text[: block.start()].count("\n") + 1
        origin = f"{path.name}, the {block.group('lang')} block at line {line}"
        try:
            if block.group("lang") == "mermaid":
                found = [read_mermaid(block.group("body"), name=title, origin=origin)]
            else:
                found = read_plantuml(block.group("body"), name=title, origin=origin)
        except (MermaidError, PlantumlError) as error:
            passed.append(f"line {line}: {error}")
            continue
        sketches += found
    if not sketches:
        detail = "; ".join(passed) if passed else "no ```mermaid or ```plantuml block in it"
        raise DiagramError(f"{path.name}: nothing to draw ({detail})")
    for sketch in sketches:
        sketch.notes += [f"passed over the block at {note}" for note in passed]
    return sketches


def read_diagrams(path: Path, fmt: str | None = None) -> list[Sketch]:
    """Every diagram one file holds: one per draw.io or Visio page, per PlantUML
    ``@startuml``, per Markdown block; one for a Mermaid or Excalidraw file."""
    if not path.is_file():
        raise DiagramError(f"no such file: {path}")
    fmt = fmt or detect_format(path)
    try:
        if fmt == "drawio":
            return read_drawio(path)
        if fmt == "visio":
            return read_visio(path)
        if fmt == "excalidraw":
            if path.suffix.lower() == ".md":
                return [
                    read_excalidraw_text(path.read_text(encoding="utf-8-sig"), name=_stem(path))
                ]
            return [read_excalidraw(path)]
        text = path.read_text(encoding="utf-8-sig")
        if fmt == "mermaid":
            return [read_mermaid(text, name=_stem(path), origin=path.name)]
        if fmt == "plantuml":
            return read_plantuml(text, name=_stem(path), origin=path.name)
        if fmt == "markdown":
            return _markdown(path, text)
    except _ERRORS as error:
        raise DiagramError(str(error)) from error
    except UnicodeDecodeError as error:
        raise DiagramError(f"{path.name} is not text in UTF-8: {error}") from error
    raise DiagramError(f"unknown format {fmt!r}; one of {', '.join(FORMATS)}")
