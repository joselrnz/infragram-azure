"""Measure where every shipped icon's ink begins, so a wire can touch it.

A bare glyph is drawn as 64 px of artwork, and most artwork does not fill
its square: a globe primitive keeps 14 px of air on each side, a vendor
badge fills its square to the edge. A wire that stops at the square floats
in that air. This script rasterises every icon the skill ships and records,
for each side, where the first opaque pixel lies along 33 lines across it:
the outermost of them is that side of the ink's bounding box, and all 33 are
kept so a link is seated on the drawing wherever its line falls. A line
whose first ink is a detail -- a separate piece under a third of the largest,
such as the wifi arcs over a router -- is kept out of the lines, so a link
slides to the device instead of landing on the decoration or running through
it; the dashes of a dashed outline are the exception, and are the edge. Both
renderers read the table (``assets/catalog/ink-profiles.json``) through
``infragram.catalog.ink`` and write each node's lines onto the picture,
where the checker holds every wire end to them;
the key is a hash of the artwork's bytes, so vendor files and inline
primitives share one table and a re-coloured copy of an icon still matches.

Run from the repository root (Playwright with Chromium is needed once)::

    PYTHONPATH=src python scripts/tools/ink-profiles.py            # rebuild the table
    PYTHONPATH=src python scripts/tools/ink-profiles.py --check    # every icon has a profile

The measurement draws each icon the way the renderers do: fitted into a
square with the aspect ratio kept and the artwork centred (``xMidYMid meet``).

``PORTS`` below is the one thing set by hand: where a side's connection point
sits for the drawings the rule places badly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))

from infragram.catalog.ink import (  # noqa: E402  # noqa: E402
    DARK_INK,
    EDGE_LINES,
    artwork_key,
    load_table,
    table_path,
    tone_key,
)
from infragram.iso3d.measure import entries_for, measurable, measure  # noqa: E402
from infragram.paths import skill_assets  # noqa: E402

#: A side's one connection point, set by hand as a fraction along the side,
#: for the drawings where the middle of the stretch the device reaches is the
#: wrong place. A person is a head over a body: the middle of a side falls on
#: the neck and slides up to the chin, so a link met the head. The people
#: glyphs put their left and right ports on the body, at the shoulders; the
#: top stays on the head, where the rule already puts it.
PORTS: dict[str, dict[str, float]] = {
    "user": {"left": 0.75, "right": 0.75},
    "users": {"left": 0.75, "right": 0.75},
    "admin": {"left": 0.75, "right": 0.75},
}


def ports() -> dict[str, dict[str, float]]:
    """``PORTS``, keyed by artwork like the rest of the table."""
    from infragram.catalog.components import primitive_icon_svg

    return {
        artwork_key(primitive_icon_svg(icon)): dict(sides) for icon, sides in sorted(PORTS.items())
    }


def artworks() -> dict[str, bytes]:
    """Every icon the skill ships, keyed by its artwork hash. The key is of
    the shipped bytes; only the copy that is measured gains a namespace."""
    from infragram.catalog.components import primitive_icon_svg
    from infragram.catalog.specs import SHARED_PRIMITIVE_SPECS

    found: dict[str, bytes] = {}
    for path in sorted((skill_assets() / "icons").rglob("*.svg")):
        data = path.read_bytes()
        found[artwork_key(data)] = measurable(data)
    for spec in SHARED_PRIMITIVE_SPECS:
        try:
            data = primitive_icon_svg(spec.icon_id)
        except KeyError:
            continue
        found[artwork_key(data)] = measurable(data)
    return found


def build() -> int:
    items = artworks()
    measured = measure(items)
    # Only icons with air worth crossing: a mark that fills its square needs
    # no entry, and leaving it out keeps the shipped table small.
    profiles: dict[str, list[float]] = {}
    edges: dict[str, str] = {}
    # How dark each piece of artwork is, for the artwork dark enough to need
    # drawing light on a dark canvas. Keyed by colour (tone_key), where a
    # profile is keyed by shape: two colours of one drawing share a profile
    # and read differently on a dark ground.
    tones: dict[str, float] = {}
    for key, value in sorted(measured.items()):
        if value is None:
            continue
        profile, code = entries_for(value)
        if profile is not None:
            profiles[key] = profile
        if code is not None:
            edges[key] = code
        tone = value.get("tone")
        if tone is not None and tone < DARK_INK:
            tones[tone_key(items[key])] = tone
    missing = [key for key, value in measured.items() if value is None]
    table = {
        "description": (
            "Where each shipped icon's ink begins. 'profiles' is the ink's bounding box as fractions of "
            "its square, [left, right, top, bottom]; 'edges' is where the ink begins along 33 lines across "
            "each side, one character per line in 64ths of the square ('A' = 0, '/' = 63, '.' = no ink), "
            "sides joined by '|' in the same order (see src/infragram/catalog/ink.py). Keyed by the sha1 "
            "of the artwork's shape (first 12 hex digits); an icon that fills its square has no entry. "
            "Both renderers seat a wire's end on the ink and the checker holds them to it. "
            "'ports' is where a side's connection point sits for the drawings the rule places badly, as a "
            "fraction along the side, set by hand in scripts/tools/ink-profiles.py (a person's body, not the neck)."
        ),
        "lines": EDGE_LINES,
        "profiles": profiles,
        "edges": edges,
        "tones": tones,
        "ports": ports(),
    }
    table_path().write_text(
        json.dumps(table, indent=1, sort_keys=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"OK: measured {len(profiles)} icons ({len(tones)} too dark for a dark canvas) "
        f"into {table_path().relative_to(ROOT)}"
        + (f"; {len(missing)} drew nothing and have no profile" if missing else "")
    )
    return 0


def check() -> int:
    table = load_table()
    items = artworks()
    measured = measure(items)
    stale = []
    for key, value in measured.items():
        if value is None:
            continue
        profile, code = entries_for(value)
        tone = value.get("tone")
        dark = tone if tone is not None and tone < DARK_INK else None
        if (
            table.profiles.get(key) != profile
            or table.edges.get(key) != code
            or table.tones.get(tone_key(items[key])) != dark
        ):
            stale.append(key)
    if stale:
        print(
            f"FAIL: {len(stale)} of {len(items)} shipped icons have a stale or missing ink "
            "profile; run scripts/tools/ink-profiles.py"
        )
        return 1
    if table.ports != ports():
        print(
            "FAIL: the table's ports are not the ones PORTS sets; run scripts/tools/ink-profiles.py"
        )
        return 1
    print(
        f"OK: the ink profiles match all {len(items)} shipped icons "
        f"({len(table.profiles)} of them have air inside the square)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="verify the table covers every shipped icon"
    )
    options = parser.parse_args(argv)
    return check() if options.check else build()


if __name__ == "__main__":
    sys.exit(main())
