#!/usr/bin/env python3
"""Add a tried 3D recipe to scene.js and its item to the table.

Try it first (``recipe-try.py``) and look at the picture. This writes the
builder before the render section of ``src/infragram/iso3d/scene.js`` and
one ``item(...)`` line at the end of the table in ``scripts/build/iso-icons.py``,
then prints what follows: the install (every item re-renders when scene.js
changes), the node classes, the inventory, the ink table, the gates.

Usage::

    PYTHONPATH=src python scripts/tools/recipe-add.py buffer_tank.js --id buffer-tank --name "Buffer tank" --family facility --arg 4 --alias "thermal store"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))

from infragram.iso3d.recipes import NEXT_STEPS, RecipeError, add_recipe  # noqa: E402


def _arg(text: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("source", type=Path, help="the tried builder, a .js file")
    parser.add_argument(
        "--id",
        required=True,
        help="the item id, lower-case words joined by hyphens (the class is Iso<Name>)",
    )
    parser.add_argument("--name", required=True, help="the item's name, as the caption shows it")
    parser.add_argument(
        "--family",
        required=True,
        help="compute, storage, network, security, facility, client, platform, operations, industrial or energy",
    )
    parser.add_argument(
        "--arg",
        action="append",
        default=[],
        type=_arg,
        help="a knob value the item passes, in order (repeat)",
    )
    parser.add_argument("--alias", action="append", default=[], help="a search alias (repeat)")
    options = parser.parse_args(argv)
    try:
        written = add_recipe(
            options.source.read_text(encoding="utf-8"),
            item_id=options.id,
            name=options.name,
            family=options.family,
            args=tuple(options.arg),
            aliases=tuple(options.alias),
        )
    except RecipeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for path in written:
        print(f"wrote {path.relative_to(ROOT)}")
    print(NEXT_STEPS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
