"""Import official vendor icon packs into icons/vendors/<vendor>.

All vendor definitions (source root, URL, release, archive, terms) live in
icons/vendors/sources.json — add or change a vendor there, not here.
The only code per vendor is a small parser for its pack layout, selected by
the manifest's "format" field. Every icon lands with category, stable id,
relative path, source provenance, usage terms, and SHA-256.

A vendor's "supplements" add icons its main pack lacks from another official
set of the same vendor -- Microsoft's Entra architecture icons into Azure --
each listed by file, with its own provenance. A full import applies them;
``--supplements`` merges them into the vendor's existing catalog alone, so
adding one never needs the main pack's archive on hand.

Usage:
    python scripts/importers/official-icons.py            # all vendors
    python scripts/importers/official-icons.py aws gcp    # subset
    python scripts/importers/official-icons.py --supplements azure
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
VAULT = REPO_ROOT / "scripts" / "cloud-diagram-sources"
DEST = REPO_ROOT / "skills" / "infragram-azure" / "assets" / "icons" / "vendors"
SOURCES = DEST / "sources.json"

AZURE_FILENAME = re.compile(r"^(\d+)-icon-service-(.+)\.svg$")
AWS_FILENAME = re.compile(r"^Arch_(.+)_64\.svg$")
#: The deck's second tier. A service is a coloured tile (Arch_*_64); the things
#: inside a service -- a NAT gateway, an EC2 instance, a VPC endpoint -- are
#: line glyphs (Res_<Service>_<Resource>_48). Both ship in one package.
AWS_RESOURCE_FILENAME = re.compile(r"^Res_(.+)_48\.svg$")
#: The deck's group shapes (Region, subnets, Auto Scaling group ...): the small
#: glyphs a frame's corner tab carries. Light variants only; the theme
#: reverses them out of the tab colour itself.
AWS_GROUP_FILENAME = re.compile(r"^(?!.*_Dark)(.+)_32\.svg$")
#: The deck's general icons -- user, client, internet, server, documents --
#: are resource glyphs too, shipped in Light and Dark variants under
#: Res_General-Icons (Res_<Name>_48_Light.svg). The light one is the drawing
#: on paper; the dark one is for slides on black and is not imported.
AWS_GENERAL_FILENAME = re.compile(r"^Res_(.+)_48_Light\.svg$")
#: Resource folders that are named differently from their service folders.
AWS_RESOURCE_CATEGORIES = {
    "iot": "internet-of-things",
    "management-governance": "management-tools",
}


def kebab(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# Each parser yields (icon_id, display_name, category, source_file, extra).
def parse_azure_v24(root: Path, spec: dict) -> Iterator[tuple[str, str, str, Path, dict]]:
    seen: dict[str, str] = {}
    for svg in sorted(root.rglob("*.svg")):
        category = kebab(svg.parent.name)
        match = AZURE_FILENAME.match(svg.name)
        base = kebab(match.group(2) if match else svg.stem)
        icon_id = base
        if icon_id in seen:
            if seen[icon_id] == category:
                continue
            icon_id = f"{base}-{category}"
            if icon_id in seen:
                continue
        seen[icon_id] = category
        name = (match.group(2) if match else svg.stem).replace("-", " ")
        extra = {"service_number": match.group(1)} if match else {}
        yield icon_id, name, category, svg, extra


def parse_aws_arch(root: Path, spec: dict) -> Iterator[tuple[str, str, str, Path, dict]]:
    """Both tiers of the AWS deck, services first so they own the bare ids.

    ``root`` is the icon package. Services come from
    ``Architecture-Service-Icons_*`` as before. Resources come from
    ``Resource-Icons_*``: their id is the service and resource together
    (``vpc-nat-gateway``), their name reads "NAT Gateway (Amazon VPC)", and
    they file under the same category as their service. A resource whose id
    would collide with a service's (``ec2-auto-scaling``) takes
    ``-resource``.
    """
    seen: set[str] = set()
    for svg in sorted(root.rglob("*_64.svg")):
        if "__MACOSX" in svg.parts or "Resource-Icons" in svg.parts:
            continue
        match = AWS_FILENAME.match(svg.name)
        if not match:
            continue
        raw = match.group(1)
        category = kebab(svg.parent.parent.name.removeprefix("Arch_"))
        base = kebab(re.sub(r"^(Amazon|AWS)-", "", raw))
        icon_id = base if base and base not in seen else kebab(raw)
        if icon_id in seen:
            continue
        seen.add(icon_id)
        yield icon_id, raw.replace("-", " "), category, svg, {}
    for svg in sorted(root.rglob("*_48.svg")):
        if "__MACOSX" in svg.parts or "Resource-Icons" not in str(svg):
            continue
        match = AWS_RESOURCE_FILENAME.match(svg.name)
        if not match:
            continue
        raw = match.group(1)
        folder = kebab(svg.parent.name.removeprefix("Res_"))
        category = AWS_RESOURCE_CATEGORIES.get(folder, folder)
        service, _, resource = raw.partition("_")
        icon_id = kebab(re.sub(r"^(Amazon|AWS)-", "", raw))
        if icon_id in seen:
            icon_id = f"{icon_id}-resource"
        if icon_id in seen:
            continue
        seen.add(icon_id)
        name = (
            f"{resource.replace('-', ' ')} ({service.replace('-', ' ')})"
            if resource
            else raw.replace("-", " ")
        )
        yield icon_id, name, category, svg, {"tier": "resource"}
    for svg in sorted(root.rglob("*_48_Light.svg")):
        if "__MACOSX" in svg.parts or "Res_General-Icons" not in svg.parts:
            continue
        match = AWS_GENERAL_FILENAME.match(svg.name)
        if not match:
            continue
        raw = match.group(1)
        icon_id = f"general-{kebab(re.sub(r'^(Amazon|AWS)-', '', raw))}"
        if icon_id in seen:
            continue
        seen.add(icon_id)
        yield (
            icon_id,
            f"{raw.replace('-', ' ')} (General)",
            "general-icons",
            svg,
            {"tier": "resource"},
        )
    for svg in sorted(root.rglob("*_32.svg")):
        if "__MACOSX" in svg.parts or "Architecture-Group-Icons" not in str(svg):
            continue
        match = AWS_GROUP_FILENAME.match(svg.name)
        if not match:
            continue
        raw = match.group(1)
        icon_id = kebab(re.sub(r"^(Amazon|AWS)-", "", raw))
        if icon_id in seen:
            icon_id = f"{icon_id}-group"
        if icon_id in seen:
            continue
        seen.add(icon_id)
        yield icon_id, raw.replace("-", " "), "architecture-group", svg, {"tier": "group"}


def parse_gcp_products(root: Path, spec: dict) -> Iterator[tuple[str, str, str, Path, dict]]:
    seen: set[str] = set()

    core_root = root / spec["core_products_subdir"]
    for product_dir in sorted(p for p in core_root.iterdir() if p.is_dir()):
        svg_dir = product_dir / "SVG"
        candidates = sorted(svg_dir.glob("*.svg")) if svg_dir.is_dir() else []
        if not candidates:
            continue
        preferred = [c for c in candidates if "color" in c.name.lower()] or candidates
        icon_id = kebab(product_dir.name)
        seen.add(icon_id)
        yield icon_id, product_dir.name, "core-products", preferred[0], {}

    legacy_root = root / spec["legacy_subdir"]
    for product_dir in sorted(p for p in legacy_root.iterdir() if p.is_dir()):
        candidates = sorted(product_dir.glob("*.svg"))
        if not candidates:
            continue
        base = kebab(product_dir.name)
        # The legacy set redraws products that also ship a current core-product
        # icon. Keep both: the current one owns the bare id, the legacy artwork
        # stays addressable as <product>-legacy.
        icon_id = f"{base}-legacy" if base in seen else base
        if icon_id in seen:
            continue
        seen.add(icon_id)
        name = product_dir.name.replace("_", " ").replace("-", " ")
        yield icon_id, name, "legacy", candidates[0], {}


def parse_k8s_community(root: Path, spec: dict) -> Iterator[tuple[str, str, str, Path, dict]]:
    for svg in sorted(root.rglob("*.svg")):
        if svg.parent.name != "unlabeled":
            continue
        category = kebab(svg.parent.parent.name)
        yield kebab(svg.stem), svg.stem.replace("-", " "), category, svg, {}


#: The logos' names, as their projects write them.
DATABRICKS_LOGOS = {
    "apache-iceberg": "Apache Iceberg",
    "apache-spark": "Apache Spark",
    "delta-lake": "Delta Lake",
    "delta-sharing": "Delta Sharing",
    "mlflow": "MLflow",
    "terraform": "Terraform",
    "unity-catalog": "Unity Catalog",
}


def parse_databricks_icons(root: Path, spec: dict) -> Iterator[tuple[str, str, str, Path, dict]]:
    """The Databricks architecture icon set: its catalog.json lists every
    product with its slug, name, category and the name it had before
    ("formerly Delta Live Tables (DLT)"), which a search should still find."""
    catalog = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    for product in catalog["products"]:
        aka = product.get("aka") or ""
        former = re.sub(r"^.*?\bformerly\s+", "", aka, flags=re.IGNORECASE) if aka else ""
        aliases = [
            part.strip(" .")
            for part in re.split(r"\s+/\s+|\s*\(\s*|\)\s*", former)
            if part.strip(" .")
        ]
        yield (
            product["slug"],
            product["name"],
            product["category"],
            root / "svg" / f"{product['slug']}.svg",
            {"aliases": aliases},
        )
    # the full-colour logos the set keeps beside its icons (the Databricks one is
    # the platform icon already)
    for logo in sorted((root / "logos").glob("*.svg")):
        if logo.stem == "databricks":
            continue
        name = DATABRICKS_LOGOS.get(logo.stem, logo.stem.replace("-", " ").title())
        yield f"logo-{logo.stem}", f"{name} logo", "logos", _with_view_box(logo), {}


def parse_listed_icons(root: Path, spec: dict) -> Iterator[tuple[str, str, str, Path, dict]]:
    """A supplement's icons, each named in its spec by file: its id, name,
    aliases, and the category it joins (the spec's own, else ``category``).
    A set whose files carry no service number or layout of their own --
    Microsoft's Entra icons -- is listed, not parsed."""
    for file, icon in spec["icons"].items():
        svg = root / file
        if not svg.is_file():
            raise FileNotFoundError(f"supplement icon {file!r} not found in {root}")
        yield (
            icon["id"],
            icon["name"],
            icon.get("category") or spec["category"],
            _with_view_box(svg, "normalized"),
            {"aliases": icon.get("aliases", [])},
        )


def _with_view_box(svg: Path, folder: str = "logos-normalized") -> Path:
    """The SVG as the renderer reads one: no XML prolog, and a viewBox from
    its width and height when it has none (two of the logos size themselves
    that way). Written beside the source, which stays as it came."""
    text = svg.read_text(encoding="utf-8")
    text = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", text)
    root = re.search(r"<svg\b[^>]*>", text)
    if root and "viewBox" not in root.group(0):
        width = re.search(r'\bwidth="([\d.]+)', root.group(0))
        height = re.search(r'\bheight="([\d.]+)', root.group(0))
        if width and height:
            tag = root.group(0).replace(
                "<svg", f'<svg viewBox="0 0 {width.group(1)} {height.group(1)}"', 1
            )
            text = text.replace(root.group(0), tag, 1)
    out = svg.parent.parent / folder / svg.name
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    return out


PARSERS = {
    "azure-v24": parse_azure_v24,
    "aws-arch": parse_aws_arch,
    "gcp-products": parse_gcp_products,
    "k8s-community": parse_k8s_community,
    "databricks-icons": parse_databricks_icons,
    "listed-icons": parse_listed_icons,
}


def _entries(icons_dir: Path, parser, root: Path, spec: dict) -> list[dict]:
    """Copy what a parser yields into the collection and describe each icon."""
    icons = []
    for icon_id, name, category, src, extra in parser(root, spec):
        out_dir = icons_dir / category
        out_dir.mkdir(parents=True, exist_ok=True)
        dest_file = out_dir / f"{icon_id}.svg"
        shutil.copyfile(src, dest_file)
        icons.append(
            {
                "id": icon_id,
                "name": name,
                "aliases": [],
                "category": category,
                "file": f"{category}/{icon_id}.svg",
                **extra,
                "source_path": src.relative_to(VAULT).as_posix(),
                "sha256": hashlib.sha256(dest_file.read_bytes()).hexdigest(),
            }
        )
    return icons


def _supplement(vendor: str, icons_dir: Path, supplement: dict) -> list[dict]:
    parser = PARSERS.get(supplement["format"])
    if parser is None:
        raise ValueError(f"vendor {vendor}: unknown supplement format {supplement['format']!r}")
    root = VAULT / supplement["root"]
    if not root.is_dir():
        raise FileNotFoundError(f"vendor {vendor}: supplement root not found at {root}")
    return _entries(icons_dir, parser, root, supplement)


def _provenance(spec: dict) -> dict:
    source = {key: spec[key] for key in ("url", "release", "archive", "terms")}
    if spec.get("supplements"):
        source["supplements"] = [
            {key: item[key] for key in ("url", "release", "archive", "terms")}
            for item in spec["supplements"]
        ]
    return source


def _write_catalog(vendor: str, spec: dict, icons: list[dict], indent: int | None = None) -> None:
    icons.sort(key=lambda item: (item["category"], item["id"]))
    ids = [icon["id"] for icon in icons]
    doubled = sorted({icon_id for icon_id in ids if ids.count(icon_id) > 1})
    if doubled:
        raise ValueError(
            f"vendor {vendor}: a supplement repeats ids the pack has: {', '.join(doubled)}"
        )
    by_category = Counter(icon["category"] for icon in icons)
    catalog = {
        "schema_version": 1,
        "collection": f"vendors/{vendor}",
        "generated_by": "scripts/importers/official-icons.py",
        "source": _provenance(spec),
        "counts": {"icons": len(icons), "by_category": dict(sorted(by_category.items()))},
        "icons": icons,
    }
    out = DEST / vendor / "catalog.json"
    text = (
        json.dumps(catalog, ensure_ascii=False, indent=indent)
        if indent
        else json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    )
    out.write_text(text + "\n", encoding="utf-8", newline="\n")
    print(f"assets/cloud/{vendor}: {len(icons)} icons in {len(by_category)} categories")


def import_supplements(vendor: str, spec: dict) -> None:
    """Merge the vendor's supplements into its existing catalog: the
    supplements' earlier icons are replaced, the main pack's kept."""
    icons_dir = DEST / vendor
    existing = (icons_dir / "catalog.json").read_text(encoding="utf-8")
    catalog = json.loads(existing)
    listed = {icon["id"] for item in spec.get("supplements", []) for icon in item["icons"].values()}
    kept = [icon for icon in catalog["icons"] if icon["id"] not in listed]
    for icon in catalog["icons"]:
        if icon not in kept:
            (icons_dir / icon["file"]).unlink(missing_ok=True)
    added = [
        entry
        for item in spec.get("supplements", [])
        for entry in _supplement(vendor, icons_dir, item)
    ]
    # keep the file as it was written (an older import indented it), so the
    # merge's diff is the merge
    _write_catalog(vendor, spec, kept + added, indent=1 if existing.startswith("{\n") else None)


def import_vendor(vendor: str, spec: dict) -> None:
    parser = PARSERS.get(spec["format"])
    if parser is None:
        raise ValueError(f"vendor {vendor}: unknown format {spec['format']!r}")
    root = VAULT / spec["root"]
    if not root.is_dir():
        raise FileNotFoundError(f"vendor {vendor}: source root not found at {root}")

    icons_dir = DEST / vendor
    if icons_dir.exists():
        shutil.rmtree(icons_dir)

    icons = _entries(icons_dir, parser, root, spec)
    icons += [
        entry
        for item in spec.get("supplements", [])
        for entry in _supplement(vendor, icons_dir, item)
    ]
    if spec.get("license_file"):
        # a licence whose notice must travel with the copies (MIT) ships beside them
        shutil.copyfile(root / spec["license_file"], icons_dir / "LICENSE")
    _write_catalog(vendor, spec, icons)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "vendors",
        nargs="*",
        metavar="VENDOR",
        help="the vendors to import (default: every one the manifest defines)",
    )
    parser.add_argument(
        "--supplements",
        action="store_true",
        help="merge only the vendors' supplements into their existing catalogs",
    )
    options = parser.parse_args(argv)
    manifest = json.loads(SOURCES.read_text(encoding="utf-8"))
    vendors = manifest["vendors"]
    picks = options.vendors or list(vendors)
    for vendor in picks:
        if vendor not in vendors:
            print(
                f"unknown vendor {vendor}; manifest defines: {', '.join(vendors)}", file=sys.stderr
            )
            return 1
        if options.supplements:
            import_supplements(vendor, vendors[vendor])
        else:
            import_vendor(vendor, vendors[vendor])
    return 0


if __name__ == "__main__":
    sys.exit(main())
