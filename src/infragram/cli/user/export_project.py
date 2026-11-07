"""``infragram export:project``: a ``.infragram.json`` document to HTML, SVG and
PNG, and on request its Terraform skeleton."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .options import (
    add_export_options,
    apply_render_settings,
    chosen_formats,
    export_keywords,
    with_overrides,
)

__all__ = [
    "build_parser",
    "main",
    "planned_formats",
    "price_for_export",
    "print_infracost",
    "print_prices",
    "run_export",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infragram export:project",
        description="Render a .infragram.json project to HTML, SVG and PNG.",
    )
    parser.add_argument(
        "source",
        type=Path,
        help="the .infragram.json document, or an exported SVG, PNG or page that carries one",
    )
    add_export_options(parser, libraries="project")
    return parser


def print_prices(project, source: str = "table") -> list[str]:
    """Price what can be priced into the document before it is drawn; print
    each price, and return the notes on what could not be."""
    from ...pricing import price_project

    result = price_project(project, source=source)
    for element_id, price in result.priced:
        assumed = f"; assumed {', '.join(price.assumed)}" if price.assumed else ""
        usage = f", {price.currency} {price.usage:,.2f} of it usage" if price.usage else ""
        print(
            f"PRICED   {element_id}: {price.currency} {price.monthly:,.2f} a month "
            f"({price.rate}{usage}{assumed})"
        )
    counted = len(result.priced) + len(result.unpriced) + len(result.notes)
    if result.priced:
        currency = result.priced[0][1].currency
        free = f", {len(result.free)} free" if result.free else ""
        print(
            f"PRICED   {len(result.priced)} of {counted} cloud components{free}: about "
            f"{currency} {result.monthly:,.2f} a month, on-demand list prices; the page's "
            "Cost tab breaks it down"
        )
    notes = list(result.notes)
    if result.unpriced:
        names = [f"{name} ({component.split(':', 1)[1]})" for _, name, component in result.unpriced]
        shown = ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
        notes.append(f"not priced (the page's Cost tab says why): {shown}")
    return notes


def print_infracost(project, path: Path) -> list[str]:
    """Price the components drawn from the resources an Infracost breakdown
    prices; print each price and the total, and return the notes."""
    from ...pricing.infracost import apply_breakdown, read_breakdown
    from ...pricing.rollup import rollup

    result = apply_breakdown(project, read_breakdown(path))
    for element_id, price in result.priced:
        print(
            f"PRICED   {element_id}: {price.currency} {price.monthly:,.2f} a month "
            f"(Infracost: {price.sizing['resources']})"
        )
    totals = rollup(project, result.undrawn).totals
    if result.priced or result.undrawn:
        shown = " + ".join(f"{currency} {amount:,.2f}" for currency, amount in totals.items())
        undrawn = f", {len(result.undrawn)} priced but not drawn" if result.undrawn else ""
        print(
            f"PRICED   {len(result.priced)} components by {path.name}{undrawn}: {shown} a month; "
            "`infragram costs` adds it up by frame"
        )
    return list(result.notes)


def price_for_export(project, options: argparse.Namespace) -> list[str]:
    """Price the document as ``--prices`` and ``--infracost`` ask, before it is
    drawn; the notes on what could not be. Infracost's price wins where both price."""
    notes: list[str] = []
    prices = getattr(options, "prices", "table")
    if prices in ("table", "live"):
        notes += print_prices(project, prices)
    if getattr(options, "infracost", None) is not None:
        notes += print_infracost(project, options.infracost)
    return notes


def planned_formats(options: argparse.Namespace) -> tuple[tuple[str, ...], list[str]]:
    """The formats to write, and a note when the default PNG cannot be: a PNG
    asked for by name fails in the export instead, before anything is written."""
    from ...exports import browser_missing

    formats, explicit = chosen_formats(options.formats)
    if "png" in formats and not explicit:
        missing = browser_missing()
        if missing:
            return tuple(name for name in formats if name != "png"), [f"no PNG written: {missing}"]
    return formats, []


def run_export(project, options: argparse.Namespace) -> int:
    """Export ``project`` as ``options`` ask -- the whole of it, or the view
    ``--view`` names -- print what was written, and return the exit status: 0
    written (and verified when asked), 1 written but failing verification, 2
    refused before anything was written."""
    wanted = getattr(options, "view", None)
    if not wanted:
        return _export_one(project, options, [])
    from ...projects.views import ViewError, resolve, select

    try:
        if wanted == "all":
            if not project.views:
                raise ViewError(f"{project.title!r} declares no views; name a frame or a rule")
            views = list(project.views)
        else:
            views = [resolve(project, wanted)]
        selections = [(view, *select(project, view)) for view in views]
    except ViewError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    status = 0
    for view, selected, notes in selections:
        components = sum(1 for element in selected.topology.walk() if not element.children)
        print(
            f"VIEW     {view.id}: {components} of "
            f"{sum(1 for element in project.topology.walk() if not element.children)} components"
        )
        status = max(status, _export_one(selected, options, notes))
    return status


def _export_one(project, options: argparse.Namespace, view_notes: list[str]) -> int:
    from ...compose import ComposeError, export
    from ...exports import ExportError
    from .checker import checker

    formats, notes = planned_formats(options)
    notes = view_notes + notes
    try:
        apply_render_settings(options)
        notes = price_for_export(project, options) + notes
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    project = with_overrides(project, options)
    try:
        result = export(
            project,
            options.output_dir,
            formats=formats,
            overwrite=options.force,
            check=checker().check_path if options.verify else None,
            comments=getattr(options, "comments", None),
            **export_keywords(options),
        )
    except (ExportError, ComposeError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    for label in ("template", "html", "svg", "png", "drawio", "svg_icons", "png_icons"):
        path = getattr(result, label)
        if path is not None:
            print(f"{label.upper():8} {path} ({path.stat().st_size} bytes)")
    for folder in (result.terraform, result.terraform_modules):
        if folder is not None and folder.is_file():
            print(f"TERRAFORM {folder} ({folder.stat().st_size} bytes)")
        elif folder is not None:
            files = sum(1 for path in folder.rglob("*") if path.is_file())
            print(f"TERRAFORM {folder} ({files} files)")
    for note in (*notes, *result.notes):
        print(f"NOTE     {note}", file=sys.stderr)
    clean = True
    for name, ok, message in result.checks:
        print(message if name in message else f"{message} [{name}]")
        clean = clean and ok
    if not clean:
        print("ERROR: the export did not pass verification", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    from pydantic import ValidationError

    from ...projects import CloudProject
    from ...projects.comments import find_comments, page_comments

    options = build_parser().parse_args(argv)
    if not options.source.is_file():
        print(f"ERROR: no such document: {options.source}", file=sys.stderr)
        return 2
    try:
        if options.source.suffix.casefold() in (".svg", ".png", ".html", ".htm"):
            from ...exports.carry import carried_document

            payload = carried_document(options.source)
            if payload is None:
                print(
                    f"ERROR: {options.source} carries no document (exported with --no-embed, "
                    "or not by infragram)",
                    file=sys.stderr,
                )
                return 2
            project = CloudProject.model_validate(payload)
        else:
            project = CloudProject.load(options.source)
        # the comments beside the document, else those a page already carries
        options.comments = find_comments(options.source.parent, project.slug)
        if options.comments is None and options.source.suffix.casefold() in (".html", ".htm"):
            options.comments = page_comments(options.source.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if options.comments is not None:
        print(f"COMMENTS {len(options.comments.comments)} carried into the page")
    return run_export(project, options)
