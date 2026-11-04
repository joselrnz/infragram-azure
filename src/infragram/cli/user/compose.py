"""``infragram compose``: run a Python diagram file and export the picture it
describes.

A diagram file is an ordinary Python module written with ``infragram.author``:
``with Diagram(...)`` opens the picture, frames are ``with`` blocks, nodes are
constructed inside them and ``a >> Edge("label") >> b`` wires them. The
``Diagram`` the file closes is exported; a generator that assembles a
:class:`~infragram.projects.CloudProject` or a
:class:`~infragram.patterns.Blueprint` itself may expose it as ``PROJECT``
instead, and an explicit ``PROJECT`` wins. A file that draws several pictures
lists them as ``PROJECTS`` (documents or blueprints, each its own slug), and
every one is exported. ``-`` reads the file from standard input.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import runpy
import sys
import tempfile
from pathlib import Path
from typing import Any

from .options import add_export_options, price_flags

__all__ = ["build_parser", "main", "project_from_spec", "projects_from_spec"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infragram compose",
        description="Run a Python diagram file and export it to HTML, SVG and PNG.",
    )
    parser.add_argument(
        "spec", type=Path, help="the Python diagram file, or - to read it from standard input"
    )
    add_export_options(parser, libraries="drawn")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="draw the file again every time it is saved and show it in a page on 127.0.0.1 "
        "that reloads by itself (HTML only; Ctrl+C stops)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        metavar="N",
        help="with --watch: the page's port (default: any free one)",
    )
    return parser


def project_from_spec(path: Path):
    """The document one diagram file describes (:func:`projects_from_spec`),
    refused when the file lists several: the caller wants one."""
    from ...exports import ExportError

    documents = projects_from_spec(path)
    if len(documents) > 1:
        raise ExportError(
            f"{path.name} describes {len(documents)} diagrams (PROJECTS); "
            "`infragram compose` exports every one"
        )
    return documents[0]


def _document(candidate: Any, path: Path, name: str):
    """A ``PROJECT`` or one of ``PROJECTS`` as a document: a document as it
    is, a blueprint as the document it builds."""
    from ...exports import ExportError
    from ...patterns import Blueprint
    from ...projects import CloudProject

    if isinstance(candidate, CloudProject):
        return candidate
    if isinstance(candidate, Blueprint):
        return candidate.to_project()
    raise ExportError(
        f"{path.name}: {name} holds a {type(candidate).__name__}, not a CloudProject or a Blueprint"
    )


def projects_from_spec(path: Path) -> list:
    """Every document one diagram file describes: its ``PROJECTS``, else its
    ``PROJECT``, else the ``Diagram`` it closes.

    A file that closes no diagram is refused, never handed the diagram some
    other file closed earlier in the same process: that is how a helper
    module in a folder of specs would be exported as its neighbour. Whatever
    the file raises comes back as an :class:`ExportError` that names its line
    and the nearest real name.
    """
    from ...author import latest_diagram
    from ...compose.diagram_file import explain_failure
    from ...exports import ExportError
    from ...projects import CloudProject

    if not path.is_file():
        raise ExportError(f"no such diagram file: {path}")
    previous = latest_diagram()
    folder = str(path.resolve().parent)
    sys.path.insert(0, folder)
    try:
        namespace = runpy.run_path(str(path), run_name="__infragram_spec__")
    except Exception as error:  # whatever the file raised, told from its own lines
        raise ExportError(explain_failure(error, path)) from error
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(folder)
    many = namespace.get("PROJECTS")
    if many is not None:
        if isinstance(many, CloudProject) or not hasattr(many, "__iter__"):
            raise ExportError(f"{path.name}: PROJECTS is a list of documents or blueprints")
        documents = [_document(item, path, "PROJECTS") for item in many]
        if not documents:
            raise ExportError(f"{path.name}: PROJECTS is empty")
        slugs = [document.slug for document in documents]
        repeated = sorted({slug for slug in slugs if slugs.count(slug) > 1})
        if repeated:
            # each writes <slug>.* into the same folder: one would replace the other
            raise ExportError(f"{path.name}: PROJECTS repeats the slug {', '.join(repeated)}")
        return documents
    candidate = namespace.get("PROJECT")
    if candidate is not None:
        return [_document(candidate, path, "PROJECT")]
    closed = latest_diagram()
    if closed is None or closed is previous:
        raise ExportError(f"{path.name} defines no Diagram and no PROJECT; see infragram.author")
    return [closed.to_project()]


def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)
    if str(options.spec) == "-":
        if options.watch:
            print("ERROR: --watch needs a file to watch, not standard input", file=sys.stderr)
            return 2
        source = sys.stdin.read()
        with tempfile.TemporaryDirectory(prefix="infragram-stdin-") as scratch:
            spec = Path(scratch) / "stdin.py"
            spec.write_text(source, encoding="utf-8", newline="\n")
            # a diagram read from standard input imports from the folder the
            # command runs in, as one saved there would
            here = os.getcwd()
            sys.path.insert(0, here)
            try:
                return _compose(spec, options, layout=False)
            finally:
                with contextlib.suppress(ValueError):
                    sys.path.remove(here)
    if options.watch:
        from .watch import watch

        # the page shows what these change; the rest draw only SVG and PNG
        forwarded = (
            ["--libraries", options.libraries]
            + price_flags(options.prices)
            + (["--infracost", str(options.infracost)] if options.infracost else [])
            + (["--view", options.view] if options.view else [])
            + (["--title", options.title] if options.title is not None else [])
            + (["--status", options.status] if options.status is not None else [])
        )
        return watch(options.spec, options.output_dir, forwarded, options.port)
    return _compose(options.spec, options, layout=True)


def _compose(spec: Path, options: argparse.Namespace, *, layout: bool) -> int:
    """Export every document ``spec`` describes; the worst exit status."""
    from pydantic import ValidationError

    from ...compose import ComposeError
    from ...exports import ExportError
    from .export_project import run_export

    try:
        projects = projects_from_spec(spec)
    except (ExportError, ComposeError, ValidationError, ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    status = 0
    for project in projects:
        print(
            f"PROJECT  {project.slug} | {project.kind} | {', '.join(project.provider_ids)} | "
            f"{len(project.topology.index())} elements"
        )
        if layout and len(projects) == 1:
            from ...compose.layout_file import apply_layout, layout_path

            sidecar = layout_path(spec)
            if sidecar.is_file():
                # where the editor left things (layout:save), put back before drawing
                for note in apply_layout(project, sidecar):
                    print(f"NOTE     {note}", file=sys.stderr)
                print(f"LAYOUT   placed from {sidecar.name}")
        status = max(status, run_export(project, options))
    return status
