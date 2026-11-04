#!/usr/bin/env python3
"""Map Infragram's components to draw.io's own stencils, for the .drawio export.

draw.io ships stencils for AWS (``mxgraph.aws4``), Azure (``img/lib/azure2``)
and Kubernetes (``mxgraph.kubernetes``). A component drawn as the native
stencil stays small, restyles in draw.io and survives its Visio export; one
without a match is embedded as Infragram's own artwork. This script builds
the table the exporter reads, ``assets/catalog/drawio-stencils.json``, from
the shape index jgraph/drawio-mcp publishes (``shape-search/search-index.json``,
Apache-2.0), matching names exactly after normalising case and separators --
never by similarity, so a mapping is right or absent. The source commit is
recorded; ``--check`` fails when the committed table differs from a rebuild.

usage: python scripts/build/drawio-stencils.py <search-index.json> <commit> [--check]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))

from infragram.catalog import load_provider_component_catalog  # noqa: E402

OUT = ROOT / "skills" / "infragram-azure" / "assets" / "catalog" / "drawio-stencils.json"


def key(text: str) -> str:
    """Case, separators and a vendor prefix aside: ``Simple_Storage_Service``,
    ``simple-storage-service`` and ``Amazon Simple Storage Service`` agree."""
    text = re.sub(r"^(amazon|aws|azure|microsoft)[ _-]+", "", text.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def stencil_names(items: list[dict]) -> dict[str, dict[str, dict]]:
    """library -> normalised stencil name -> the index entry."""
    out: dict[str, dict[str, dict]] = {"aws": {}, "azure": {}, "kubernetes": {}}
    ambiguous: dict[str, set[str]] = {library: set() for library in out}

    def add(library: str, name: str, item: dict) -> None:
        # one name, two different stencils (Azure's "User Settings" in two
        # categories): which is meant cannot be told, so neither is used
        seen = out[library].get(name)
        if seen is not None and seen["style"] != item["style"]:
            ambiguous[library].add(name)
        out[library].setdefault(name, item)

    for item in items:
        if item.get("type") != "vertex":
            continue
        style = item["style"]
        if (
            (found := re.search(r"resIcon=mxgraph\.aws4\.(\w+)", style))
            and "resourceIcon" in style
            or (found := re.search(r"shape=mxgraph\.aws4\.(\w+);", style + ";"))
            and "group" not in found.group(1)
        ):
            add("aws", key(found.group(1)), item)
        elif found := re.search(r"image=img/lib/azure2/[\w-]+/([\w-]+)\.svg", style):
            add("azure", key(found.group(1)), item)
        elif found := re.search(r"shape=mxgraph\.kubernetes\.icon2?;prIcon=(\w+)", style):
            add("kubernetes", key(found.group(1)), item)
    for library, names in ambiguous.items():
        for name in names:
            out[library].pop(name, None)
    return out


def build(index: Path, commit: str) -> dict:
    stencils = stencil_names(json.loads(index.read_text(encoding="utf-8")))
    components: dict[str, dict] = {}
    for library, names in stencils.items():
        for component in load_provider_component_catalog(library).components:
            match = names.get(key(component.service_id)) or names.get(key(component.name))
            if match is not None:
                components[f"{library}:{component.service_id}"] = {
                    "style": match["style"],
                    "w": match["w"],
                    "h": match["h"],
                    "title": match["title"],
                }
    return {
        "note": "Infragram components drawn as draw.io's own stencils in the .drawio export; built by "
        "scripts/build/drawio-stencils.py from jgraph/drawio-mcp's shape index, exact name "
        "matches only. Anything absent is embedded as Infragram's artwork.",
        "source": {
            "repository": "https://github.com/jgraph/drawio-mcp",
            "path": "shape-search/search-index.json",
            "commit": commit,
            "license": "Apache-2.0",
        },
        "components": dict(sorted(components.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("index", type=Path)
    parser.add_argument("commit")
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    table = build(options.index, options.commit)
    text = json.dumps(table, indent=1, ensure_ascii=False) + "\n"
    if options.check:
        same = OUT.is_file() and OUT.read_text(encoding="utf-8") == text
        print(("OK" if same else "FAIL") + f" drawio stencils: {len(table['components'])} mapped")
        return 0 if same else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    by_library: dict[str, int] = {}
    for qualified in table["components"]:
        by_library[qualified.split(":")[0]] = by_library.get(qualified.split(":")[0], 0) + 1
    print(
        f"wrote {OUT.relative_to(ROOT)}: {len(table['components'])} components mapped {by_library}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
