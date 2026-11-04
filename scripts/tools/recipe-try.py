#!/usr/bin/env python3
"""Try a candidate 3D recipe: render it, measure it, check where links seat.

The candidate is a file holding one builder in scene.js's form. Nothing in
the package changes; the pictures and the report land in ``--out``. Exit 0
when the render is clean and every side seats a link; 1 when a side is
flagged or the page raised an error, with the report saying which.

Usage::

    PYTHONPATH=src python scripts/tools/recipe-try.py buffer_tank.js --out dist/recipes --arg 4 --family facility --glyph tank
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))

from infragram.iso3d.recipes import RecipeError, try_recipe  # noqa: E402


def _arg(text: str) -> object:
    """A knob value as written on the command line: JSON when it parses, else the text."""
    try:
        return json.loads(text)
    except ValueError:
        return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "source",
        type=Path,
        help="a .js file holding one `R.<name> = (fam, tex, ...) => {...}` builder",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="folder for the picture, the icon and the report (default dist/recipes/<name>)",
    )
    parser.add_argument(
        "--arg",
        action="append",
        default=[],
        type=_arg,
        help="a knob value, in order (repeat; JSON literals or text)",
    )
    parser.add_argument(
        "--family", default="compute", help="the family whose colour and glyph it takes"
    )
    parser.add_argument("--colour", default=None, help="#rrggbb instead of the family colour")
    parser.add_argument("--glyph", default=None, help="a vocabulary glyph for the badge")
    parser.add_argument("--no-badge", action="store_true", help="draw no badge")
    options = parser.parse_args(argv)
    try:
        source = options.source.read_text(encoding="utf-8")
        from infragram.iso3d.recipes import builder_name

        out = options.out or ROOT / "dist" / "recipes" / builder_name(source)
        report = try_recipe(
            source,
            out=out,
            args=tuple(options.arg),
            family=options.family,
            colour=options.colour,
            glyph=options.glyph,
            badge=not options.no_badge,
        )
    except RecipeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(report.summary())
    (out / f"{report.name}.report.json").write_text(
        json.dumps(
            {
                "name": report.name,
                "spec": report.spec,
                "profile": report.profile,
                "edges": report.edges,
                "seats": report.seats,
                "errors": report.errors,
                "ok": report.ok,
            },
            indent=2,
        ),
        encoding="utf-8",
        newline="\n",
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
