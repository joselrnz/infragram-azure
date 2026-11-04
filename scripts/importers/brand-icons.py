"""Refresh the thesvg brand logos icons/logos ships.

Reads the thesvg clone in the source vault, copies the variant SVGs of the
brands the catalog already lists (``--add SLUG`` adds one more, ``--all``
takes the whole collection), computes SHA-256 digests, classifies each icon's
license, and writes the catalog with per-icon provenance. Only 17 brands are
reviewed to ship, so a run without ``--all`` never brings in the thousands the
collection holds, and ``families.json`` and ``README.md``, written by hand,
are never touched. The brands collection is a
standalone asset collection: it is not listed in themes/catalog.json
and does not participate in the themed skin pipeline.

Usage:
    python scripts/importers/brand-icons.py --source-root scripts/cloud-diagram-sources
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
DEFAULT_SOURCE = REPO_ROOT / "scripts" / "cloud-diagram-sources"
DEST_ROOT = REPO_ROOT / "skills" / "infragram-azure" / "assets" / "icons" / "logos"

UPSTREAM_URL = "https://github.com/glincker/thesvg"

# Cloud vendor service icons ship from the verified official packs via
# scripts/importers/official-icons.py (icons/vendors/<vendor>); thesvg's
# secondhand vendor collections are skipped. assets/brands carries logos only.
SKIP_COLLECTIONS = {"azure", "aws", "gcp", "k8s"}

PERMISSIVE = {
    "CC0-1.0",
    "MIT",
    "Apache-2.0",
    "Unlicense",
    "PD",
    "BSD-2-Clause",
    "BSD-3-Clause",
}
ATTRIBUTION = {"CC-BY-4.0", "CC-BY-3.0", "CC-BY-2.5"}
COPYLEFT_PREFIXES = ("GPL", "LGPL", "AGPL", "MPL", "CC-BY-SA")
NO_DERIVATIVES_PREFIXES = ("CC-BY-ND", "CC-BY-NC-ND")
NON_COMMERCIAL_PREFIXES = ("CC-BY-NC",)

# Tags are case-folded and kebab-cased, then mapped through this table so the
# brands vocabulary lines up with the themed providers' category names.
TAG_SYNONYMS = {
    "devtool": "devtools",
    "dev-tool": "devtools",
    "database": "data",
    "databases": "data",
    "container": "containers",
    "networking-and-cdn": "networking",
}

UNSAFE_PATTERNS = re.compile(
    r"<script|javascript:|onload\s*=|onerror\s*=|<foreignObject|data:text/html",
    re.IGNORECASE,
)


def normalize_tags(raw: list[str] | None) -> list[str]:
    seen: list[str] = []
    for tag in raw or []:
        slug = re.sub(r"[^a-z0-9]+", "-", tag.strip().lower()).strip("-")
        slug = TAG_SYNONYMS.get(slug, slug)
        if slug and slug not in seen:
            seen.append(slug)
    return seen


def classify_license(license_text: str | None) -> str:
    text = (license_text or "").strip()
    if text in PERMISSIVE:
        return "permissive"
    if text in ATTRIBUTION:
        return "attribution"
    if text.startswith(NO_DERIVATIVES_PREFIXES):
        return "no-derivatives"
    if text.startswith(NON_COMMERCIAL_PREFIXES):
        return "non-commercial"
    if text.startswith(COPYLEFT_PREFIXES):
        return "copyleft"
    return "restricted-review"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument(
        "--add", action="append", default=[], metavar="SLUG", help="also import this brand"
    )
    parser.add_argument(
        "--all", action="store_true", help="import every brand the collection holds"
    )
    args = parser.parse_args()
    catalog_path = DEST_ROOT / "catalog.json"
    shipped = (
        json.loads(catalog_path.read_text(encoding="utf-8"))["icons"]
        if catalog_path.is_file()
        else []
    )
    # the brands this run writes, and the entries it carries forward unchanged
    wanted = None if args.all else {str(icon["id"]) for icon in shipped} | set(args.add)
    previous = {str(icon["id"]): icon for icon in shipped}

    thesvg = args.source_root / "multi-cloud" / "thesvg"
    index_path = thesvg / "src" / "data" / "icons.json"
    icons_root = thesvg / "public" / "icons"
    if not index_path.is_file() or not icons_root.is_dir():
        print(f"thesvg source not found under {thesvg}", file=sys.stderr)
        return 1

    commit = "unknown"
    head = thesvg / ".git" / "HEAD"
    if head.is_file():
        ref = head.read_text(encoding="utf-8").strip()
        if ref.startswith("ref: "):
            ref_path = thesvg / ".git" / ref[5:]
            if ref_path.is_file():
                commit = ref_path.read_text(encoding="utf-8").strip()
        else:
            commit = ref

    index = json.loads(index_path.read_text(encoding="utf-8"))
    indexed_slugs = {entry["slug"] for entry in index}

    dest_icons = DEST_ROOT
    dest_icons.mkdir(parents=True, exist_ok=True)

    catalog_icons: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    collection_counts: Counter[str] = Counter()
    skipped_unsafe: list[str] = []
    missing_dirs: list[str] = []
    copied_files = 0

    def import_slug(slug: str, meta: dict | None) -> None:
        nonlocal copied_files
        collection = (meta or {}).get("collection") or "unindexed"
        if collection in SKIP_COLLECTIONS or (wanted is not None and slug not in wanted):
            return
        src_dir = icons_root / slug
        if not src_dir.is_dir():
            missing_dirs.append(slug)
            return
        variants: dict[str, str] = {}
        digests: dict[str, str] = {}
        out_dir = dest_icons / slug
        # this brand's folder is rewritten whole, so a variant upstream dropped goes
        if out_dir.is_dir():
            shutil.rmtree(out_dir)
        for svg in sorted(src_dir.glob("*.svg")):
            content = svg.read_text(encoding="utf-8", errors="replace")
            if UNSAFE_PATTERNS.search(content):
                skipped_unsafe.append(f"{slug}/{svg.name}")
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            dest_file = out_dir / svg.name
            shutil.copyfile(svg, dest_file)
            copied_files += 1
            variant = svg.stem
            variants[variant] = f"{slug}/{svg.name}"
            digests[variant] = sha256_of(dest_file)
        if not variants:
            return
        meta = meta or {}
        license_text = meta.get("license") or "Unknown"
        status = classify_license(license_text)
        status_counts[status] += 1
        collection_counts[collection] += 1
        catalog_icons.append(
            {
                "id": slug,
                "name": meta.get("title") or slug,
                "aliases": meta.get("aliases") or [],
                "categories": normalize_tags(meta.get("categories")),
                "brand_hex": meta.get("hex"),
                "collection": collection,
                "variants": variants,
                "sha256": digests,
                "license": license_text,
                "license_status": status,
                "brand_url": meta.get("url"),
                "source_url": UPSTREAM_URL,
                "source_commit": commit,
                "source_path": f"public/icons/{slug}",
            }
        )

    for entry in index:
        import_slug(entry["slug"], entry)

    for orphan in sorted(
        p.name for p in icons_root.iterdir() if p.is_dir() and p.name not in indexed_slugs
    ):
        import_slug(orphan, None)

    # a brand the catalog ships that upstream no longer has keeps what it had
    written = {item["id"] for item in catalog_icons}
    catalog_icons.extend(
        entry for slug, entry in previous.items() if slug not in written and slug in missing_dirs
    )
    catalog_icons.sort(key=lambda item: item["id"])
    catalog = {
        "schema_version": 1,
        "collection": "logos",
        "generated_by": "scripts/importers/brand-icons.py",
        "source": {
            "url": UPSTREAM_URL,
            "commit": commit,
            "index": "src/data/icons.json",
        },
        "license_statuses": {
            "permissive": "Redistribution and modification permitted (CC0, MIT, Apache-2.0, BSD, ...).",
            "attribution": "Redistribution permitted with attribution (CC-BY).",
            "copyleft": "Redistribution permitted under share-alike/copyleft terms (GPL, MPL, CC-BY-SA, ...).",
            "no-derivatives": "Redistribution permitted; DO NOT recolor, reshape, or modify (CC-BY-ND).",
            "non-commercial": "Non-commercial terms; review before any commercial use.",
            "restricted-review": "Trademark, fair-use, proprietary, or unclear terms; identification use only, review before redistribution.",
        },
        "counts": {
            "icons": len(catalog_icons),
            "files": copied_files,
            "by_status": dict(sorted(status_counts.items())),
            "by_collection": dict(sorted(collection_counts.items())),
        },
        "icons": catalog_icons,
    }
    DEST_ROOT.mkdir(parents=True, exist_ok=True)
    catalog_path = DEST_ROOT / "catalog.json"
    catalog_path.write_text(
        json.dumps(catalog, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"icons imported: {len(catalog_icons)}")
    print(f"files copied:   {copied_files}")
    print(f"by status:      {dict(sorted(status_counts.items()))}")
    print(f"by collection:  {dict(sorted(collection_counts.items()))}")
    if skipped_unsafe:
        print(f"skipped unsafe files ({len(skipped_unsafe)}):")
        for item in skipped_unsafe[:20]:
            print(f"  {item}")
    if missing_dirs:
        print(f"index entries without icon directory ({len(missing_dirs)}): {missing_dirs[:10]}")
    print(f"catalog: {catalog_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
