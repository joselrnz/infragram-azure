"""``infragram schema``: the JSON Schema of an ``.infragram.json`` document,
for an editor's completion and checking (see projects/schema.py)."""

from __future__ import annotations

import argparse
import sys

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    from ...projects.schema import schema_path, schema_text

    parser = argparse.ArgumentParser(
        prog="infragram schema",
        description="Print the JSON Schema of an .infragram.json document. Point an editor at it "
        '(VS Code: a "$schema" key in the document, or the json.schemas setting) '
        "for completion and checking while you write one by hand.",
    )
    parser.add_argument(
        "--path",
        action="store_true",
        help="print where the shipped copy is instead of its contents",
    )
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if options.path:
        print(schema_path().resolve())
    else:
        sys.stdout.write(schema_text())
    return 0
