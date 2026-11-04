#!/usr/bin/env python3
"""Render the on-premises equipment table in real 3D and install the icons.

``scripts/build/iso-icons.py`` holds the table of items -- what exists, in
which family, drawn by which recipe. This script gives each item a real
render: ``infragram/iso3d/scene.js`` builds the hardware procedurally in three.js
(chassis, drive sleds, port rows with link lights, glass doors, lit screens,
cables of each kind), lit and shadowed, from one fixed three-quarter camera
onto a transparent canvas, in headless Chromium. Each render is brought down
to 192 px (a 256-colour PNG) and wrapped in an SVG the way the imported
on-prem artwork is; the editor export percent-encodes such wrappers instead
of base64-ing the PNG a second time, so a library of them stays light.

    PYTHONPATH=src python scripts/build/iso-render.py --out <dir> [--sheet <png>] [--only id ...]
    PYTHONPATH=src python scripts/build/iso-render.py --install

``--install`` puts the renders into the Local & On-Premises collection as the
``iso-<family>`` categories (the same ids and node classes as the flat kit)
and records each icon with the hash of the render spec -- the item's line in
the table plus ``scene.js`` -- so the unit test can tell a stale install from
a fresh one without rendering, and an install renders only the items whose
spec changed. Then run ``scripts/tools/generate-nodes.py``,
``scripts/inventory/build.py`` and ``scripts/tools/ink-profiles.py``.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import sys
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))
from infragram.iso3d.render import (  # noqa: E402
    Renderer,
    spec_hash as _spec_hash,
    wrap,
)
from infragram.iso3d.vocabulary import FAMILY_GLYPH, glyph_paths  # noqa: E402


def table():
    """The generator module: the table, the families, the glyphs, install()."""
    name = "iso_icons"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / "iso-icons.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


#: Which positional argument of a recipe is its glyph, in the table.
GLYPH_ARG = {
    "appliance": 0,
    "cabinet": 0,
    "drum_stack": 1,
    "puck": 0,
    "segment": 0,
    "sensor": 0,
    "din": 0,
    "software": 0,
    "construct": 0,
}


def spec_for(gen, entry) -> dict:
    """What scene.js needs to build one item."""
    args = list(entry.args)
    kwargs = dict(entry.kwargs)
    glyph_name = None
    index = GLYPH_ARG.get(entry.recipe)
    if index is not None and index < len(args):
        glyph_name = args.pop(index)
    glyph_name = glyph_name or FAMILY_GLYPH[entry.family]
    # ``badge=False`` (the custom servers) is not a recipe argument: it
    # means no glyph, so the chassis wears no badge
    if not kwargs.pop("badge", True):
        glyph_name = None
    paths = glyph_paths(glyph_name) if glyph_name else []
    return {
        "id": entry.id,
        "recipe": entry.recipe,
        "args": args,
        "kwargs": kwargs,
        "colour": gen.FAMILIES[entry.family].colour,
        "glyph": "|".join(paths),
    }


def spec_hash(gen, entry) -> str:
    """The hash the catalog records: the item's spec, the builder, the encoding."""
    return _spec_hash(spec_for(gen, entry))


def sheet(done: list, target: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    font = (
        ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 15)
        if Path("C:/Windows/Fonts/segoeui.ttf").exists()
        else ImageFont.load_default()
    )
    cw, ch, cols = 200, 232, 8
    rows = (len(done) + cols - 1) // cols
    page = Image.new("RGB", (cw * cols, ch * rows), "#8d9094")
    draw = ImageDraw.Draw(page)
    for i, (entry, png) in enumerate(done):
        image = Image.open(io.BytesIO(png)).convert("RGBA")
        image.thumbnail((cw - 16, cw - 16))
        x, y = (i % cols) * cw, (i // cols) * ch
        page.paste(image, (x + 8 + (cw - 16 - image.width) // 2, y + 6), image)
        draw.text((x + 8, y + ch - 30), entry.name[:26], fill="#1c2127", font=font)
    page.save(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, help="folder to render PNGs into")
    parser.add_argument("--sheet", type=Path, help="also write a contact sheet PNG here")
    parser.add_argument("--only", nargs="*", default=[], help="render only these item ids")
    parser.add_argument(
        "--install", action="store_true", help="render every item into the on-prem library"
    )
    options = parser.parse_args(argv)
    gen = table()
    if not options.install and options.out is None:
        parser.error("--out or --install is required")
    items = [entry for entry in gen.ITEMS if not options.only or entry.id in options.only]
    done: list = []
    with Renderer() as renderer:
        if options.install:
            catalog = json.loads((gen.COLLECTION / "catalog.json").read_text(encoding="utf-8"))
            current = {record["id"]: record for record in catalog["icons"]}
            kept = 0

            def render(entry):
                nonlocal kept
                digest = spec_hash(gen, entry)
                origin = {
                    "source_path": "scripts/build/iso-render.py",
                    "source_sha256": digest,
                    "source_release": "Infragram original 3D render: scripts/build/iso3d/scene.js (three.js r161), "
                    "headless Chromium, fixed three-quarter camera",
                }
                record = current.get(f"iso-{entry.id}")
                installed = gen.COLLECTION / record["file"] if record else None
                if record and record.get("source_sha256") == digest and installed.is_file():
                    # the same spec through the same builder: the render on disk stands
                    kept += 1
                    return installed.read_text(encoding="utf-8"), origin
                png = renderer.render(spec_for(gen, entry))
                done.append((entry, png))
                return wrap(png), origin

            gen.install(render=render)
            print(f"    rendered {len(done)}, kept {kept} whose spec had not changed")
        else:
            for entry in items:
                png = renderer.render(spec_for(gen, entry))
                target = options.out / entry.family / f"{entry.id}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(png)
                done.append((entry, png))
            print(f"OK: rendered {len(done)} items into {options.out}")
        if renderer.errors:
            print("page errors:", renderer.errors[:5], file=sys.stderr)
            return 1
    if options.sheet and done:
        sheet(done, options.sheet)
        print(f"    sheet: {options.sheet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
