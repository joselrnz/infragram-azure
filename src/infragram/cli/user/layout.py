"""``infragram layout:save``: keep what was moved in the editor beside the
diagram file, so the next ``compose`` draws it where it was left
(compose/layout_file.py)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    from pydantic import ValidationError

    from ...compose.layout_file import layout_path, saved_layout, write_layout
    from ...exports.carry import carried_document
    from ...projects import CloudProject

    parser = argparse.ArgumentParser(
        prog="infragram layout:save",
        description="Keep what was moved or resized in the editor beside a Python diagram file: "
        "read the document the editor saved and write <diagram>.layout.json, which "
        "compose then draws from.",
    )
    parser.add_argument(
        "saved",
        type=Path,
        help="what the editor saved: a downloaded .infragram.json, the saved page, "
        "or an exported SVG or PNG that carries its document",
    )
    parser.add_argument(
        "--for",
        dest="spec",
        type=Path,
        required=True,
        metavar="DIAGRAM.py",
        help="the diagram file the layout belongs to; it lands beside it",
    )
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if not options.saved.is_file():
        print(f"ERROR: no such file: {options.saved}", file=sys.stderr)
        return 2
    try:
        if options.saved.suffix.casefold() == ".json":
            project = CloudProject.load(options.saved)
        else:
            payload = carried_document(options.saved)
            if payload is None:
                print(f"ERROR: {options.saved} carries no document", file=sys.stderr)
                return 2
            project = CloudProject.model_validate(payload)
    except (OSError, ValueError, ValidationError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    target = layout_path(options.spec)
    if not saved_layout(project):
        # refused before anything is written: the layout already beside the file stays
        print(
            f"ERROR: {options.saved} holds no placement the editor saved; move something in the "
            "editor and download the document again",
            file=sys.stderr,
        )
        return 2
    count = write_layout(project, target)
    print(f"LAYOUT   {target} ({count} placed elements); compose {options.spec.name} draws from it")
    return 0
