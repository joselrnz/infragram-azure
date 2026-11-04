"""``infragram import:diagram``: a diagram drawn in another tool, as an infragram diagram.

It reads draw.io (``.drawio``, ``.drawio.png``, ``.drawio.svg``, every
page), Mermaid (flowchart, architecture, C4), PlantUML (deployment,
component, C4-PlantUML, the AWS/Azure/Kubernetes libraries), Excalidraw
(``.excalidraw``, Obsidian's ``.excalidraw.md``) and Visio or Lucidchart
(``.vsdx``), or every Mermaid and PlantUML block of a Markdown page. Each
diagram in the file becomes a diagram file the user edits (``<slug>.py``)
beside a report of every shape and what it was drawn as
(``<slug>.import.md``), composed and exported like any other.
``import:drawio`` and ``import:mermaid`` are the same command with the
format fixed. ``references/import-diagrams.md`` is the method.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .import_estate import _common, shown, write_drawing

__all__ = ["import_diagram", "import_drawio", "import_mermaid"]


def _parser(prog: str, fmt: str | None) -> argparse.ArgumentParser:
    from ...convert import FORMATS

    what = {
        "drawio": "a draw.io file (.drawio, .drawio.png, .drawio.svg, .xml)",
        "mermaid": "a Mermaid file (.mmd), or a Markdown page's ```mermaid blocks",
    }.get(fmt or "", "a draw.io, Mermaid, PlantUML, Excalidraw or Visio file, or a Markdown page")
    parser = argparse.ArgumentParser(
        prog=prog,
        description=f"Draw {what} as an infragram diagram: an editable diagram file per diagram, a "
        "report of every shape and what it was drawn as, and the diagram exported.",
    )
    parser.add_argument("source", type=Path, help="the file to read")
    if fmt is None:
        parser.add_argument(
            "--format",
            choices=FORMATS,
            default=None,
            dest="fmt",
            help="what the file is (default: told by its name, then its contents)",
        )
    parser.add_argument(
        "--page",
        action="append",
        default=[],
        metavar="NAME|N",
        help="only this diagram of the file: a draw.io or Visio page, a Markdown block, "
        "by title or 1-based number (repeatable; default: every one)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_only",
        help="list the diagrams the file holds and stop",
    )
    _common(parser)
    return parser


def _main(argv: list[str] | None, prog: str, fmt: str | None) -> int:
    from ...author.diagram import slugify
    from ...convert import DiagramError, draw_sketch, read_diagrams, write_sketch_report

    options = _parser(prog, fmt).parse_args(argv)
    source: Path = options.source
    wanted = fmt or getattr(options, "fmt", None)
    if fmt == "mermaid" and source.suffix.lower() in (".md", ".markdown"):
        wanted = "markdown"
    try:
        sketches = read_diagrams(source, wanted)
    except (DiagramError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if options.list_only:
        for number, sketch in enumerate(sketches, start=1):
            print(
                f"{number:>3}  {sketch.title}  ({sketch.format}: {len(sketch.shapes)} shapes, "
                f"{len(sketch.links)} lines) {sketch.origin}"
            )
        return 0
    if options.page:
        chosen = []
        for page in options.page:
            found = [s for n, s in enumerate(sketches, start=1) if page in (s.title, str(n))]
            if not found:
                print(
                    f"ERROR: {source.name} holds no diagram {page!r}; it holds "
                    + ", ".join(repr(s.title) for s in sketches),
                    file=sys.stderr,
                )
                return 2
            chosen += [s for s in found if s not in chosen]
        sketches = chosen
    if len(sketches) > 1 and (options.spec or options.title):
        print(
            f"ERROR: {source.name} holds {len(sketches)} diagrams; --spec and --title name one, "
            "so pick it with --page",
            file=sys.stderr,
        )
        return 2
    slugs: dict[str, int] = {}
    status = 0
    comments: list[str] = []
    for sketch in sketches:
        if options.title:
            sketch.title = options.title
        drawing = draw_sketch(sketch)
        if not drawing.drawn:
            print(
                f"ERROR: {sketch.origin} holds nothing to draw ({len(sketch.shapes)} shapes read)",
                file=sys.stderr,
            )
            status = status or 2
            continue
        if getattr(options, "comment", None):
            from ...convert.report import sketch_comment

            comments.append(sketch_comment(sketch, drawing))
        slug = slugify(drawing.title)
        slugs[slug] = slugs.get(slug, 0) + 1
        spec = None
        if slugs[slug] > 1:  # two pages of one title
            spec = options.output_dir / f"{slug}-{slugs[slug]}.py"
        command = f"{prog.split()[-1]} {shown(source)}"

        # write_drawing calls report(spec name, date); the defaults bind this page's values
        def report(name: str, date: str, sketch=sketch, drawing=drawing, command=command) -> str:
            return write_sketch_report(sketch, drawing, command=command, date=date, spec=name)

        result = write_drawing(
            drawing,
            options,
            command,
            spec=spec,
            read=f"{len(sketch.shapes)} shapes and {len(sketch.links)} lines from {sketch.origin}",
            report=report,
        )
        status = status or result
    if comments:
        # every page's comment in the one file a CI step posts
        options.comment.parent.mkdir(parents=True, exist_ok=True)
        options.comment.write_text("\n---\n\n".join(comments), encoding="utf-8", newline="\n")
        print(f"COMMENT  {options.comment}")
    return status


def import_diagram(argv: list[str] | None = None) -> int:
    return _main(argv, "infragram import:diagram", None)


def import_drawio(argv: list[str] | None = None) -> int:
    return _main(argv, "infragram import:drawio", "drawio")


def import_mermaid(argv: list[str] | None = None) -> int:
    return _main(argv, "infragram import:mermaid", "mermaid")
