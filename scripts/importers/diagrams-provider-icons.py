#!/usr/bin/env python3
"""Vendor a provider node set from mingrammer/diagrams into a library pack.

Usage:
    python scripts/importers/diagrams-provider-icons.py [vendor ...]

Each vendor maps onto one upstream ``diagrams/<set>`` package. The importer
pins one upstream commit, reads the generated Python node declarations of
every category module, embeds each exact PNG in a standalone SVG wrapper, and
records source and generated hashes in the pack catalog - the same contract
the on-premises importer established. With no arguments every configured
vendor is imported.

The MIT license covers the diagrams project's files; each provider's marks
remain subject to that provider's trademark terms, which the provider
registry records.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(
    0,
    str(
        next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
        / "scripts"
    ),
)
from lib.catalog_guard import refusal

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
VENDORS_ROOT = ROOT / "skills" / "infragram-azure" / "assets" / "icons" / "vendors"
COMMIT = "dd0763d939f377c99898951a489e813c0360cd4a"
RELEASE = "v0.25.1"
RAW_ROOT = f"https://raw.githubusercontent.com/mingrammer/diagrams/{COMMIT}"
SOURCE_ROOT = f"https://github.com/mingrammer/diagrams/blob/{COMMIT}"
LICENSE_URL = f"{SOURCE_ROOT}/LICENSE"

#: vendor id -> (upstream set, human label, category modules at the pinned commit)
SETS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "oracle": (
        "oci",
        "Oracle Cloud Infrastructure",
        (
            "compute",
            "connectivity",
            "database",
            "devops",
            "governance",
            "monitoring",
            "network",
            "security",
            "storage",
        ),
    ),
    "alibaba": (
        "alibabacloud",
        "Alibaba Cloud",
        (
            "analytics",
            "application",
            "communication",
            "compute",
            "database",
            "iot",
            "network",
            "security",
            "storage",
            "web",
        ),
    ),
    "openstack": (
        "openstack",
        "OpenStack",
        (
            "adjacentenablers",
            "apiproxies",
            "applicationlifecycle",
            "baremetal",
            "billing",
            "compute",
            "containerservices",
            "deployment",
            "frontend",
            "lifecyclemanagement",
            "monitoring",
            "multiregion",
            "networking",
            "nfv",
            "operations",
            "optimization",
            "orchestration",
            "packaging",
            "sharedservices",
            "storage",
            "user",
            "workloadprovisioning",
        ),
    ),
}

NODE = re.compile(
    r"^class\s+(?P<class_name>[A-Za-z][A-Za-z0-9_]*)\(_[A-Za-z0-9_]+\):\s*\n"
    r'\s+_icon\s*=\s*"(?P<icon>[^"]+\.png)"',
    flags=re.MULTILINE,
)
#: Tokens whose upstream CamelCase spelling should read as the product does.
ACRONYMS = {
    "Ai": "AI",
    "Api": "API",
    "Bm": "BM",
    "Cdn": "CDN",
    "Cli": "CLI",
    "Cpu": "CPU",
    "Db": "DB",
    "Dns": "DNS",
    "Ecs": "ECS",
    "Edr": "EDR",
    "Gpu": "GPU",
    "Hpc": "HPC",
    "Iam": "IAM",
    "Io": "IO",
    "Iot": "IoT",
    "Ip": "IP",
    "Kms": "KMS",
    "Lb": "LB",
    "Ml": "ML",
    "Nas": "NAS",
    "Nat": "NAT",
    "Nfv": "NFV",
    "Oke": "OKE",
    "Oss": "OSS",
    "Rds": "RDS",
    "Sdk": "SDK",
    "Slb": "SLB",
    "Sql": "SQL",
    "Ssl": "SSL",
    "Vcn": "VCN",
    "Vm": "VM",
    "Vpc": "VPC",
    "Vpn": "VPN",
    "Waf": "WAF",
}
#: Upstream ships colored and white variants of every OCI icon; keep the colored set.
SKIP_SUFFIXES = ("-white.png",)
#: Whole-name corrections for upstream class names that misspell or abbreviate a product.
NAME_FIXES = {
    "BM": "Bare Metal",
    "Click House": "ClickHouse",
    "Elatic Map Reduce": "Elastic MapReduce",
    "Vm": "Virtual Machine",
}


def fetch(url: str) -> bytes:
    if not url.startswith("https://"):
        raise SystemExit(f"icons are fetched over https only, not {url}")
    request = Request(url, headers={"User-Agent": "Infragram provider icon importer"})  # noqa: S310 - https, checked above
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS host
        return response.read()


def svg_wrapper(png: bytes) -> bytes:
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("upstream icon is not a PNG")
    encoded = base64.b64encode(png).decode("ascii")
    return (
        '<svg aria-hidden="true" viewBox="0 0 256 256" '
        'xmlns="http://www.w3.org/2000/svg">\n'
        f'  <image width="256" height="256" href="data:image/png;base64,{encoded}"/>\n'
        "</svg>\n"
    ).encode()


def display_name(class_name: str) -> str:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", class_name).replace("_", " ")
    name = " ".join(ACRONYMS.get(token, token) for token in spaced.split())
    return NAME_FIXES.get(name, name)


def discover_nodes(upstream: str, categories: tuple[str, ...]) -> list[tuple[str, str, str]]:
    nodes: list[tuple[str, str, str]] = []
    for category in categories:
        source = fetch(f"{RAW_ROOT}/diagrams/{upstream}/{category}.py").decode("utf-8")
        matches = NODE.findall(source)
        if not matches:
            # Some upstream category modules exist with no leaf nodes yet
            # (OpenStack's adjacentenablers, lifecyclemanagement, operations).
            print(f"  note: diagrams/{upstream}/{category}.py declares no nodes; skipped")
            continue
        for class_name, icon in matches:
            if icon.endswith(SKIP_SUFFIXES):
                continue
            nodes.append((category, class_name, icon))
    if not nodes:
        raise ValueError(f"no nodes discovered for diagrams/{upstream}")
    return nodes


def import_node(vendor: str, upstream: str, node: tuple[str, str, str]) -> dict[str, object]:
    category, class_name, icon_name = node
    service_id = f"{category}-{Path(icon_name).stem}"
    relative_png = f"resources/{upstream}/{category}/{icon_name}"
    png = fetch(f"{RAW_ROOT}/{relative_png}")
    svg = svg_wrapper(png)
    relative_svg = f"{category}/{service_id}.svg"
    destination = VENDORS_ROOT / vendor / relative_svg
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(svg)
    return {
        "id": service_id,
        "name": display_name(class_name),
        "class_name": class_name,
        "aliases": [
            class_name,
            f"diagrams.{upstream}.{category}.{class_name}",
            Path(icon_name).stem,
        ],
        "category": category,
        "file": relative_svg,
        "source_path": relative_png,
        "sha256": hashlib.sha256(svg).hexdigest(),
        "source_sha256": hashlib.sha256(png).hexdigest(),
        "source_url": f"{SOURCE_ROOT}/{relative_png}",
        "source_release": (
            f"mingrammer/diagrams {RELEASE} commit {COMMIT}; exact PNG embedded "
            "in a self-contained SVG wrapper"
        ),
        "terms_url": LICENSE_URL,
    }


def import_vendor(vendor: str, force: bool = False) -> int:
    upstream, label, categories = SETS[vendor]
    nodes = discover_nodes(upstream, categories)
    service_ids = [f"{category}-{Path(icon).stem}" for category, _, icon in nodes]
    if len(service_ids) != len(set(service_ids)):
        raise ValueError(f"{vendor}: node discovery produced duplicate service ids")

    destination = VENDORS_ROOT / vendor
    refused = refusal(destination / "catalog.json", service_ids, force=force)
    if refused:
        raise SystemExit(refused)
    with ThreadPoolExecutor(max_workers=12) as pool:
        icons = list(pool.map(lambda node: import_node(vendor, upstream, node), nodes))
    icons.sort(key=lambda entry: str(entry["id"]))

    catalog = {
        "schema_version": 1,
        "collection": f"vendors/{vendor}",
        "generated_by": "pinned mingrammer/diagrams provider node importer",
        "source": {
            "url": f"{SOURCE_ROOT}/resources/{upstream}",
            "release": f"mingrammer/diagrams {RELEASE} ({COMMIT})",
            "terms": LICENSE_URL,
            "label": label,
        },
        "counts": {"icons": len(icons)},
        "icons": icons,
    }
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "catalog.json").write_text(
        json.dumps(catalog, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Imported {len(icons)} {label} icons into {destination}")
    return len(icons)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "vendors",
        nargs="*",
        metavar="VENDOR",
        help=f"the packs to import (default: all of {', '.join(SETS)})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="write the upstream set even where it drops or adds icons a pack lists",
    )
    options = parser.parse_args(argv)
    vendors = options.vendors or list(SETS)
    unknown = [vendor for vendor in vendors if vendor not in SETS]
    if unknown:
        print(f"unknown vendor(s): {', '.join(unknown)}; known: {', '.join(SETS)}", file=sys.stderr)
        return 2
    total = sum(import_vendor(vendor, options.force) for vendor in vendors)
    print(f"{total} icons across {len(vendors)} vendor pack(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
