"""``infragram recipes``: the vocabulary of the 3D items rendered by spec.

``Iso(..., recipe="server", family="storage", glyph="database", units=3)``
draws what no shipped icon is, from one of the builders behind the 3D set.
Which builders there are, which knobs each takes, and which families,
colours and glyphs there are to dress it in used to be a Python call away
(:mod:`infragram.iso3d.vocabulary`); this lists them, one recipe in detail,
and draws one to an SVG to look at before it goes in a diagram
(``--svg``), through the same :mod:`infragram.iso3d.api` the node uses.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...iso3d.vocabulary import Knob

__all__ = ["main"]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infragram recipes",
        description="List the recipes behind the 3D items a diagram draws by spec "
        "(infragram.nodes.iso.Iso): each builder's knobs with their types, defaults and the "
        "values it tells apart, the families with their colours, and the badge glyphs. Name a "
        "recipe to see it in detail; add --svg to draw it.",
    )
    parser.add_argument("recipe", nargs="?", help="one recipe to show in detail (or to draw)")
    parser.add_argument(
        "--json", action="store_true", help="print the vocabulary, or the one recipe, as JSON"
    )
    draw = parser.add_argument_group(
        "drawing one", "render the recipe to an SVG in headless Chromium (the png extra's browser)"
    )
    draw.add_argument(
        "--svg", type=Path, default=None, metavar="OUT.svg", help="write the rendered item here"
    )
    draw.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KNOB=VALUE",
        help="a knob's value (repeat for more), e.g. --set units=3 --set drivesN=12",
    )
    draw.add_argument("--family", default="compute", help="the family, which picks the colour")
    draw.add_argument(
        "--colour", "--color", dest="colour", default=None, help="#rrggbb, over the family's"
    )
    draw.add_argument(
        "--glyph", default=None, help="the badge: a glyph name, or path data of a 24-unit mark"
    )
    draw.add_argument("--no-badge", action="store_true", help="draw no badge")
    draw.add_argument("--force", action="store_true", help="replace OUT.svg if it exists")
    return parser


def _knobs_json(knobs: tuple[Knob, ...]) -> list[dict[str, Any]]:
    return [knob.model_dump() for knob in knobs]


def _unknown(name: str, table: dict[str, Any]) -> int:
    near = difflib.get_close_matches(name, list(table), n=3)
    hint = f"; did you mean {', '.join(near)}?" if near else "; infragram recipes lists them"
    print(f"ERROR: no recipe {name!r}{hint}", file=sys.stderr)
    return 2


def _usage(recipe: str, knobs: tuple[Knob, ...]) -> str:
    """The Iso call that draws the recipe with its defaults, spelled out as
    Python writes it (``kind="smr"``, ``tall=False``)."""

    def literal(value: object) -> str:
        return json.dumps(value) if isinstance(value, str) else repr(value)

    args = "".join(
        f", {knob.name}={literal(knob.default)}" for knob in knobs if knob.default is not None
    )
    return f'Iso("Name", recipe="{recipe}", family="compute"{args})'


def _list_all() -> None:
    from ...iso3d.vocabulary import FAMILY_COLOURS, FAMILY_GLYPH, GLYPHS, recipe_knobs

    table = recipe_knobs()
    print(
        f"# {len(table)} recipes, each knob as `name: type or values = default`; "
        "infragram recipes NAME shows one, --svg OUT.svg draws it"
    )
    width = max(map(len, table))
    for recipe in sorted(table):
        knobs = ", ".join(knob.signature() for knob in table[recipe])
        print(f"{recipe:<{width}}  {knobs}".rstrip())
    print("\n# families: family=NAME picks the colour and the badge; colour=#rrggbb overrides")
    for family, colour in FAMILY_COLOURS.items():
        print(f"{family:<12} {colour}  badge {FAMILY_GLYPH[family]}")
    print("\n# glyphs: glyph=NAME, or the path data of a 24-unit mark; badge=False draws none")
    print(textwrap.fill(" ".join(sorted(GLYPHS)), width=100))


def _show(recipe: str, knobs: tuple[Knob, ...]) -> None:
    from ...iso3d.vocabulary import FAMILY_COLOURS

    print(f"RECIPE   {recipe}")
    for knob in knobs:
        print(f"KNOB     {knob.signature()}")
    if not knobs:
        print("KNOB     none: the recipe draws one shape")
    if any(len(knob.choices) > 1 for knob in knobs):
        print("NOTE     a text knob's other values draw what the builder draws for the rest")
    print(f"FAMILY   {', '.join(FAMILY_COLOURS)} (default compute); colour=#rrggbb overrides")
    print("GLYPH    a glyph name (infragram recipes lists them), path data, or badge=False")
    print("USE      from infragram.nodes.iso import Iso")
    print(f"         {_usage(recipe, knobs)}")
    print(f"DRAW     infragram recipes {recipe} --svg {recipe}.svg [--set KNOB=VALUE ...]")


def _browser_missing() -> str | None:
    """Why this machine cannot render a 3D item, or None when it can: the
    renderer is three.js in Chromium, driven by Playwright, and brings the
    picture down with Pillow."""
    from importlib.util import find_spec

    from ...exports import browser_missing
    from ...exports.browser import install_hint

    if find_spec("PIL") is None:
        return f"Pillow isn't installed ({install_hint()})"
    return browser_missing()


def _draw(recipe: str, knobs: tuple[Knob, ...], options: argparse.Namespace) -> int:
    from ...iso3d.api import SpecError, build_spec, render_cached
    from ...iso3d.vocabulary import KnobError

    by_name = {knob.name: knob for knob in knobs}
    values: dict[str, object] = {}
    for pair in options.set:
        name, sep, text = pair.partition("=")
        name = name.strip()
        if not sep or not name:
            print(f"ERROR: --set takes KNOB=VALUE, not {pair!r}", file=sys.stderr)
            return 2
        knob = by_name.get(name)
        if knob is None:
            names = ", ".join(by_name) or "none"
            print(
                f"ERROR: recipe {recipe!r} has no knob {name!r}; it takes {names}", file=sys.stderr
            )
            return 2
        try:
            values[name] = knob.parse(text)
        except KnobError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
        if len(knob.choices) > 1 and values[name] not in knob.choices:
            print(
                f"NOTE     {name}={text!r} is not one of {', '.join(map(repr, knob.choices))}; "
                "it draws what the builder draws for the rest",
                file=sys.stderr,
            )
    try:
        spec = build_spec(
            recipe,
            family=options.family,
            colour=options.colour,
            glyph=options.glyph,
            badge=not options.no_badge,
            **values,
        )
    except SpecError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    out: Path = options.svg
    if out.suffix.lower() != ".svg":
        out = out.with_suffix(".svg")
    if out.exists() and not options.force:
        print(f"ERROR: {out} exists (pass --force to replace it)", file=sys.stderr)
        return 2
    missing = _browser_missing()
    if missing:
        print(f"ERROR: drawing a recipe renders it in Chromium: {missing}", file=sys.stderr)
        return 2
    try:
        svg, _, digest = render_cached(spec)
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8", newline="\n")
    print(f"SVG      {out} ({out.stat().st_size} bytes)")
    print(f"         spec {spec['id']}, cached as {digest[:12]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    from ...iso3d.vocabulary import recipe_knobs, summary

    options = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    table = recipe_knobs()
    if options.recipe is None:
        if options.svg is not None:
            print("ERROR: --svg draws one recipe; name it", file=sys.stderr)
            return 2
        if options.json:
            print(json.dumps(summary(), indent=1))
        else:
            _list_all()
        return 0
    knobs = table.get(options.recipe)
    if knobs is None:
        return _unknown(options.recipe, table)
    if options.svg is not None:
        return _draw(options.recipe, knobs, options)
    if options.json:
        print(
            json.dumps(
                {
                    "recipe": options.recipe,
                    "knobs": _knobs_json(knobs),
                    "usage": _usage(options.recipe, knobs),
                },
                indent=1,
            )
        )
        return 0
    _show(options.recipe, knobs)
    return 0
