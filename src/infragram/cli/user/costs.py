"""``infragram costs``: what a diagram costs, added up by frame.

It prices the diagram first -- from the shipped price tables by default,
``--prices`` from the cloud's public prices fetched now where it can,
``--no-prices`` not at all (it then adds up the prices the document
carries), and ``--infracost FILE`` from an Infracost breakdown joined by
Terraform address -- and prints the diagram's total, each frame's and each priced
component's; ``--csv`` writes the same as one row each, and ``--json``
prints it as one JSON document (:func:`infragram.pricing.rollup.rollup_json`).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    from pydantic import ValidationError

    from ...compose import ComposeError
    from ...exports import ExportError
    from ...pricing.infracost import apply_breakdown, read_breakdown
    from ...pricing.rollup import rollup, rollup_json
    from .diff import load_any
    from .export_project import print_prices
    from .options import add_price_options

    parser = argparse.ArgumentParser(
        prog="infragram costs",
        description="What a diagram costs, added up by frame: the diagram's total, each "
        "frame's and each priced component's, from the prices it carries or the ones "
        "--prices and --infracost find.",
    )
    parser.add_argument(
        "source",
        type=Path,
        help="a .infragram.json document, a diagram file, or a page or picture that carries "
        "its document",
    )
    add_price_options(parser)
    parser.add_argument(
        "--infracost",
        type=Path,
        default=None,
        metavar="FILE",
        help="an `infracost breakdown --format json` file, joined by Terraform address",
    )
    parser.add_argument(
        "--csv", type=Path, default=None, metavar="FILE", help="also write the rollup as CSV"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="with --csv: replace a file this command did not write, or that was edited since",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the rollup as one JSON document and nothing else on stdout: the total and "
        "each frame's by currency, every priced component with its source and what its price "
        "assumed, what is priced but not drawn, and the notes",
    )
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)
    # with --json, stdout is the JSON document alone: every other line goes to stderr
    said = sys.stderr if options.json else sys.stdout
    try:
        project = load_any(options.source)
        undrawn: list[tuple[str, float, str]] = []
        notes: list[str] = []
        if options.prices in ("table", "live"):
            with contextlib.redirect_stdout(said):
                notes += print_prices(project, options.prices)
        if options.infracost is not None:
            joined = apply_breakdown(project, read_breakdown(options.infracost))
            undrawn, notes = joined.undrawn, notes + joined.notes
    except (ExportError, ComposeError, ValidationError, ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    added = rollup(project, undrawn)
    if options.json:
        print(json.dumps(rollup_json(added, notes), ensure_ascii=False, indent=2))
    else:
        print(added.report())
    for note in notes:
        print(f"NOTE     {note}", file=sys.stderr)
    if options.csv is not None:
        from ...exports.written import write_side_file

        try:
            write_side_file(options.csv, added.csv(), force=options.force)
        except (OSError, ValueError) as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
        print(f"CSV      {options.csv} ({options.csv.stat().st_size} bytes)", file=said)
    return 0
