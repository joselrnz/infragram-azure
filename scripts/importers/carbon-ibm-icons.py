#!/usr/bin/env python3
"""Rebuild the IBM library from IBM's Carbon icons.

The IBM library was mingrammer/diagrams' IBM node set: PNGs that are, for many
services, cropped fragments of larger artwork, which IBM's terms do not let
anyone repair. Carbon (``@carbon/icons``, Apache-2.0) is IBM's own icon set,
the one IBM's architecture diagrams draw with: whole, consistent line icons.

Each service keeps its id, file path and node class; its artwork is the Carbon
icon a reviewed table names (``ibm-carbon-map.json`` beside this script:
service -> Carbon icon, with the basis and the reason for every generic pick).
A service the table maps to nothing has no honest icon in Carbon and leaves
the library, since a near-miss states something false.

    python scripts/importers/carbon-ibm-icons.py --carbon <unpacked @carbon/icons>

``--carbon`` is the unpacked npm package (``npm pack @carbon/icons@11.89.0``):
nothing is fetched by this script. A run that would drop or add an icon the
catalog lists is refused unless ``--force`` says the table is meant to.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
        / "scripts"
    ),
)
from lib.catalog_guard import refusal

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
LIBRARY = ROOT / "skills" / "infragram-azure" / "assets" / "icons" / "vendors" / "ibm"
MAP = Path(__file__).with_name("ibm-carbon-map.json")
VERSION = "11.89.0"
PACKAGE_URL = f"https://www.npmjs.com/package/@carbon/icons/v/{VERSION}"
SOURCE_URL = (
    f"https://github.com/carbon-design-system/carbon/tree/%40carbon/icons%40{VERSION}"
    "/packages/icons/src/svg/32"
)
TERMS_URL = "https://github.com/carbon-design-system/carbon/blob/main/LICENSE"
_SVG = re.compile(r"<svg\b[^>]*>(.*)</svg>", re.S)
#: Illustrator's export wrapper, which a few Carbon files still carry: a
#: ``<switch>`` whose first branch is an empty ``<foreignObject>`` asking for
#: Illustrator's extensions. Only the drawing branch is kept.
_ILLUSTRATOR = re.compile(r"</?switch>|<foreignObject\b[^>]*/>", re.S)
#: What a shipped icon never carries (tests/unit/test_untrusted_documents.py).
_UNSAFE = re.compile(r"<script|<foreignObject|\bon[a-z]+\s*=|javascript:", re.I)


def artwork(carbon: Path, name: str) -> tuple[bytes, bytes]:
    """The Carbon icon as shipped, and the same paths in this library's wrapper.

    Carbon's paths carry no fill: they draw in the wrapper's current colour,
    which the renderers set to the theme's ink."""
    source = (carbon / "svg" / "32" / f"{name}.svg").read_bytes()
    body = _SVG.search(source.decode("utf-8"))
    if body is None:
        raise SystemExit(f"{name}.svg is not an SVG")
    inner = re.sub(r"<title>.*?</title>", "", body.group(1), flags=re.S)
    inner = _ILLUSTRATOR.sub("", inner).strip()
    if _UNSAFE.search(inner):
        raise SystemExit(f"{name}.svg carries markup a shipped icon never does")
    svg = (
        '<svg aria-hidden="true" viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">'
        + inner
        + "</svg>\n"
    ).encode("utf-8")
    return source, svg


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument(
        "--carbon", type=Path, required=True, help="the unpacked @carbon/icons package"
    )
    parser.add_argument("--check", action="store_true", help="say what would change; write nothing")
    parser.add_argument(
        "--force",
        action="store_true",
        help="write even when the run drops or adds icons the catalog lists",
    )
    options = parser.parse_args(argv)
    package = json.loads((options.carbon / "package.json").read_text(encoding="utf-8"))
    if package.get("version") != VERSION or package.get("license") != "Apache-2.0":
        raise SystemExit(
            f"expected @carbon/icons {VERSION} (Apache-2.0), found {package.get('version')}"
        )

    catalog_path = LIBRARY / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    table = {row["slug"]: row for row in json.loads(MAP.read_text(encoding="utf-8"))}
    kept: list[dict] = []
    dropped: list[str] = []
    writes: list[tuple[Path, bytes]] = []
    for record in catalog["icons"]:
        row = table.get(record["id"])
        if row is None:
            raise SystemExit(f"{record['id']} is not in {MAP.name}; review it before importing")
        if row["carbon"] == "none":
            dropped.append(record["id"])
            continue
        source, svg = artwork(options.carbon, row["carbon"])
        writes.append((LIBRARY / record["file"], svg))
        carbon = {"icon": row["carbon"], "basis": row["basis"]}
        if row.get("note"):
            carbon["note"] = row["note"]
        kept.append(
            {
                **{
                    key: record[key]
                    for key in ("id", "name", "class_name", "aliases", "category", "file")
                },
                "source_path": f"svg/32/{row['carbon']}.svg",
                "sha256": hashlib.sha256(svg).hexdigest(),
                "source_sha256": hashlib.sha256(source).hexdigest(),
                "source_url": f"{SOURCE_URL}/{row['carbon']}.svg",
                "source_release": (
                    f"@carbon/icons {VERSION}; the 32 px icon's paths, unaltered, "
                    "in this library's SVG wrapper"
                ),
                "terms_url": TERMS_URL,
                "carbon": carbon,
            }
        )

    print(
        f"IBM      {len(kept)} icons from Carbon {VERSION}; "
        f"{len(dropped)} services with no honest icon leave the library"
    )
    for slug in dropped:
        print(f"DROPPED  {slug}")
    if options.check:
        return 0
    refused = refusal(catalog_path, [icon["id"] for icon in kept], force=options.force)
    if refused:
        print(refused, file=sys.stderr)
        return 1
    for target, svg in writes:
        target.write_bytes(svg)
    for slug in dropped:
        (LIBRARY / next(r["file"] for r in catalog["icons"] if r["id"] == slug)).unlink(
            missing_ok=True
        )
    catalog.update(
        {
            "generated_by": "scripts/importers/carbon-ibm-icons.py from a reviewed service -> Carbon table",
            "source": {
                "url": PACKAGE_URL,
                "release": f"@carbon/icons {VERSION}",
                "terms": TERMS_URL,
                "label": "IBM Cloud",
            },
            "counts": {"icons": len(kept)},
            "icons": kept,
        }
    )
    catalog_path.write_text(
        json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
