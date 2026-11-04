"""A new 3D recipe from a description: try it, look at it, promote it.

A recipe is one builder in ``scene.js``::

    R.buffer_tank = (fam, tex, legs = 4) => { const g = new THREE.Group(); ...; badge(g, tex, 1.6, 0, 4, 3.1); return g; };

:func:`try_recipe` stages the shipped scene with the candidate added, renders
it in Chromium, measures its ink the way the table is measured, and checks
where links would seat, without touching the package. The report carries a
768 px picture to look at, the 192 px icon as it would ship, the measurement
and the seat verdict per side. :func:`add_recipe` writes a tried builder into
``scene.js`` and its line into the table; the install, the node classes, the
inventory, the ink table and the gates follow as for any shipped item
(``docs/maintainers/3d-recipes.md``).
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..paths import checkout_root
from ..verification import HEX_COLOR
from .measure import entries_for, measure_in_page
from .render import HERE, Renderer, wrap
from .seat import seat_in_page
from .vocabulary import FAMILY_COLOURS, FAMILY_GLYPH, GLYPHS, glyph_paths

MARKER = "/* ----------------------------- render -------------------------------- */"
SIGNATURE = re.compile(r"^R\.(\w+) = \(fam, tex(?:, [^)]*)?\) =>", re.MULTILINE)
SCENE = HERE / "scene.js"
#: The maintainer's table of shipped items; only a checkout of the repository has it.
TABLE = (checkout_root() or HERE) / "scripts" / "build" / "iso-icons.py"
TABLE_END = "#: The shapes a custom server comes in"
_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class RecipeError(ValueError):
    """A candidate that cannot be tried or added, and why."""


def _read(path: Path) -> str:
    with open(path, encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def builder_name(source: str) -> str:
    """The one builder a candidate defines."""
    names = SIGNATURE.findall(source)
    if len(names) != 1:
        found = ", ".join(names) if names else "none"
        raise RecipeError(
            "a candidate defines exactly one builder, `R.<name> = (fam, tex, ...) => {...}`; "
            f"found {found}"
        )
    return names[0]


def with_candidate(scene: str, source: str) -> str:
    """The scene with the candidate builder before the render section."""
    name = builder_name(source)
    if re.search(rf"^R\.{re.escape(name)} = ", scene, re.MULTILINE):
        raise RecipeError(f"scene.js already has a recipe {name!r}; pick another name")
    if scene.count(MARKER) != 1:
        raise RecipeError("scene.js has no render marker to insert before")
    newline = "\r\n" if "\r\n" in scene else "\n"
    block = source.strip().replace("\r\n", "\n").replace("\n", newline) + newline
    return scene.replace(MARKER, block + MARKER, 1)


def stage(source: str, into: Path) -> Path:
    """A folder the renderer can serve: the render page, the library, and
    the shipped scene with the candidate added."""
    into.mkdir(parents=True, exist_ok=True)
    shutil.copy(HERE / "render.html", into / "render.html")
    shutil.copytree(HERE / "lib", into / "lib", dirs_exist_ok=True)
    _write(into / "scene.js", with_candidate(_read(SCENE), source))
    return into


def spec_for(
    recipe: str,
    *,
    args: tuple = (),
    family: str = "compute",
    colour: str | None = None,
    glyph: str | None = None,
    badge: bool = True,
) -> dict:
    """The spec ``scene.js`` builds from, for a recipe the vocabulary does not know yet."""
    if family not in FAMILY_COLOURS:
        raise RecipeError(f"unknown family {family!r}; one of {', '.join(FAMILY_COLOURS)}")
    paint = (colour or FAMILY_COLOURS[family]).strip()
    if not HEX_COLOR.fullmatch(paint):
        raise RecipeError(f"colour must be #rrggbb, not {paint!r}")
    if not badge:
        paths: list[str] = []
    elif glyph is None:
        paths = glyph_paths(FAMILY_GLYPH[family])
    elif glyph in GLYPHS:
        paths = glyph_paths(glyph)
    else:
        raise RecipeError(f"unknown glyph {glyph!r}; one of {', '.join(sorted(GLYPHS))}")
    return {
        "id": f"{recipe}:{json.dumps(list(args))}",
        "recipe": recipe,
        "args": list(args),
        "kwargs": {},
        "colour": paint.lower(),
        "glyph": "|".join(paths),
    }


@dataclass
class Report:
    """What a try found: the pictures, the measurement, the seat per side."""

    name: str
    spec: dict
    picture: Path  # the 768 px render, to look at
    icon: Path  # the 192 px icon as it would ship
    profile: list[float] | None
    edges: str | None
    seats: dict[str, str]
    errors: list[str]

    @property
    def flags(self) -> list[str]:
        return [f"{side} {status}" for side, status in self.seats.items() if status != "ok"]

    @property
    def ok(self) -> bool:
        return not self.errors and not self.flags and self.edges is not None

    def summary(self) -> str:
        lines = [
            f"{'OK' if self.ok else 'FLAGGED'} recipe {self.name}: picture {self.picture}, icon {self.icon}"
        ]
        if self.errors:
            lines.append("  page errors: " + "; ".join(self.errors))
        lines.append(
            "  ink: "
            + (
                "no ink measured"
                if self.edges is None
                else f"profile {self.profile}, edge lines on all four sides"
            )
        )
        lines.append(
            "  seats: " + ", ".join(f"{side} {status}" for side, status in self.seats.items())
        )
        if self.flags:
            lines.append(
                "  a flag means a link would float in air or pierce a thin edge there: "
                "put solid ink at the middle of that side"
            )
        return "\n".join(lines)


def try_recipe(
    source: str,
    *,
    out: Path,
    args: tuple = (),
    family: str = "compute",
    colour: str | None = None,
    glyph: str | None = None,
    badge: bool = True,
) -> Report:
    """Render, measure and seat-check a candidate; writes the pictures under ``out``."""
    name = builder_name(source)
    spec = spec_for(name, args=args, family=family, colour=colour, glyph=glyph, badge=badge)
    out.mkdir(parents=True, exist_ok=True)
    picture, icon = out / f"{name}.png", out / f"{name}.svg"
    with tempfile.TemporaryDirectory(prefix="iso3d-try-") as temp:
        root = stage(source, Path(temp))
        with Renderer(root=root) as renderer:
            big = renderer.page.evaluate("spec => window.iso3d.render(spec)", spec)
            picture.write_bytes(base64.b64decode(big.split(",", 1)[1]))
            svg = wrap(renderer.render(spec))
            icon.write_text(svg, encoding="utf-8", newline="\n")
            measured = measure_in_page(renderer.page, {name: svg.encode("utf-8")})
            edges = measured.get(name)
            profile, code = entries_for(edges) if edges else (None, None)
            seats = seat_in_page(renderer.page, {name: (svg.encode("utf-8"), profile, code)})[name]
            errors = list(renderer.errors)
    return Report(name, spec, picture, icon, profile, code, seats, errors)


def _literal(value: object) -> str:
    return json.dumps(value) if isinstance(value, str) else repr(value)


def table_line(
    item_id: str, name: str, family: str, recipe: str, args: tuple = (), aliases: tuple = ()
) -> str:
    """The table's own form of one item."""
    rendered = "".join(f", {_literal(value)}" for value in args)
    alias_text = ""
    if aliases:
        inner = ", ".join(json.dumps(alias) for alias in aliases) + (
            "," if len(aliases) == 1 else ""
        )
        alias_text = f", aliases=({inner})"
    return f"    item({json.dumps(item_id)}, {json.dumps(name)}, {json.dumps(family)}, {json.dumps(recipe)}{rendered}{alias_text}),"


def add_recipe(
    source: str,
    *,
    item_id: str,
    name: str,
    family: str,
    args: tuple = (),
    aliases: tuple = (),
    scene_path: Path = SCENE,
    table_path: Path = TABLE,
) -> list[Path]:
    """Write a tried builder into the scene and its item into the table."""
    recipe = builder_name(source)
    if family not in FAMILY_COLOURS:
        raise RecipeError(f"unknown family {family!r}; one of {', '.join(FAMILY_COLOURS)}")
    if not _ID.fullmatch(item_id):
        raise RecipeError(f"an item id is lower-case words joined by hyphens, not {item_id!r}")
    table = _read(table_path)
    if re.search(rf"item\({json.dumps(item_id)},", table):
        raise RecipeError(f"the table already has {item_id!r}")
    scene = with_candidate(_read(scene_path), source)
    newline = "\r\n" if "\r\n" in table else "\n"
    anchor = f"{newline}]{newline}{newline}{TABLE_END}"
    if table.count(anchor) != 1:
        raise RecipeError("the table's end was not where it should be; add the line by hand")
    line = table_line(item_id, name, family, recipe, args, aliases)
    _write(scene_path, scene)
    _write(table_path, table.replace(anchor, f"{newline}{line}{anchor}", 1))
    return [scene_path, table_path]


NEXT_STEPS = """\
next, from the repository root:
  PYTHONPATH=src python scripts/build/iso-render.py --install   # renders the set; every item re-renders when scene.js changes
  python scripts/tools/generate-nodes.py                          # the node class
  python scripts/inventory/build.py                               # the inventory
  PYTHONPATH=src python scripts/tools/ink-profiles.py             # the ink table
then the gates (verify:quick, verify:pictures, gen:ink --check, verify:browser)."""
