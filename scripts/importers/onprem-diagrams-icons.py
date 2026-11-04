#!/usr/bin/env python3
"""Vendor the complete on-premises node set from mingrammer/diagrams.

The upstream MIT-licensed package contains product and technology symbols for
local infrastructure.  This importer pins one upstream commit, discovers the
generated Python node declarations, embeds each exact PNG in a standalone SVG
wrapper, and records source and generated hashes in the provider catalog.
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
DESTINATION = ROOT / "skills" / "infragram-azure" / "assets" / "icons" / "vendors" / "onprem"
CATALOG = DESTINATION / "catalog.json"
COMMIT = "dd0763d939f377c99898951a489e813c0360cd4a"
RELEASE = "v0.25.1"
RAW_ROOT = f"https://raw.githubusercontent.com/mingrammer/diagrams/{COMMIT}"
SOURCE_ROOT = f"https://github.com/mingrammer/diagrams/blob/{COMMIT}"
LICENSE_URL = f"{SOURCE_ROOT}/LICENSE"

CATEGORIES = (
    "aggregator",
    "analytics",
    "auth",
    "cd",
    "certificates",
    "ci",
    "client",
    "compute",
    "container",
    "database",
    "dns",
    "etl",
    "gitops",
    "groupware",
    "iac",
    "identity",
    "inmemory",
    "logging",
    "messaging",
    "mlops",
    "monitoring",
    "network",
    "proxmox",
    "queue",
    "registry",
    "search",
    "security",
    "storage",
    "tracing",
    "vcs",
    "workflow",
)

NODE = re.compile(
    r"^class\s+(?P<class_name>[A-Za-z][A-Za-z0-9_]*)\(_[A-Za-z0-9_]+\):\s*\n"
    r'\s+_icon\s*=\s*"(?P<icon>[^"]+\.png)"',
    flags=re.MULTILINE,
)
ACRONYMS = {
    "Argocd": "Argo CD",
    "Circleci": "CircleCI",
    "Concourseci": "Concourse CI",
    "Crio": "CRI-O",
    "Dbt": "dbt",
    "Github": "GitHub",
    "GithubActions": "GitHub Actions",
    "Gitlab": "GitLab",
    "Gitlabci": "GitLab CI",
    "Haproxy": "HAProxy",
    "K3S": "K3s",
    "Mariadb": "MariaDB",
    "Mongodb": "MongoDB",
    "Mssql": "Microsoft SQL Server",
    "Mysql": "MySQL",
    "Neo4J": "Neo4j",
    "Newrelic": "New Relic",
    "Nifi": "Apache NiFi",
    "Oauth2Proxy": "OAuth2 Proxy",
    "Opnsense": "OPNsense",
    "Pfsense": "pfSense",
    "Postgresql": "PostgreSQL",
    "Powerbi": "Power BI",
    "PrometheusOperator": "Prometheus Operator",
    "Pve": "Proxmox VE",
    "Rabbitmq": "RabbitMQ",
    "Rsyslog": "rsyslog",
    "SyslogNg": "syslog-ng",
    "Teamcity": "TeamCity",
    "Zeromq": "ZeroMQ",
}


#: Further mingrammer packages folded into the Local & On-Premises library:
#: vendor-neutral hardware, operating systems and virtualization from
#: ``generic``, and the self-hosted Elastic stack from ``elastic``. Their ids
#: and categories carry the package prefix so they never collide with the
#: on-prem modules of the same name (``generic/network`` vs ``onprem/network``).
EXTRA_PACKAGES: dict[str, tuple[str, ...]] = {
    "generic": (
        "compute",
        "database",
        "device",
        "network",
        "os",
        "place",
        "storage",
        "virtualization",
    ),
    "elastic": (
        "agent",
        "beats",
        "elasticsearch",
        "enterprisesearch",
        "observability",
        "orchestration",
        "saas",
        "security",
    ),
}


def fetch(url: str) -> bytes:
    if not url.startswith("https://"):
        raise SystemExit(f"icons are fetched over https only, not {url}")
    request = Request(url, headers={"User-Agent": "Infragram on-prem icon importer"})  # noqa: S310 - https, checked above
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS host
        return response.read()


def svg_wrapper(png: bytes) -> bytes:
    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("upstream on-premises icon is not a PNG")
    encoded = base64.b64encode(png).decode("ascii")
    return (
        '<svg aria-hidden="true" viewBox="0 0 256 256" '
        'xmlns="http://www.w3.org/2000/svg">\n'
        f'  <image width="256" height="256" href="data:image/png;base64,{encoded}"/>\n'
        "</svg>\n"
    ).encode()


def display_name(class_name: str) -> str:
    if class_name in ACRONYMS:
        return ACRONYMS[class_name]
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", class_name)
    return spaced.replace("_", " ")


def discover_nodes() -> list[tuple[str, str, str, str]]:
    """Every (package, module, class, icon) the pinned upstream declares."""

    modules = [("onprem", category) for category in CATEGORIES]
    modules += [(package, module) for package, names in EXTRA_PACKAGES.items() for module in names]
    nodes: list[tuple[str, str, str, str]] = []
    for package, module in modules:
        source = fetch(f"{RAW_ROOT}/diagrams/{package}/{module}.py").decode("utf-8")
        matches = NODE.findall(source)
        if not matches:
            raise ValueError(f"no nodes discovered in diagrams/{package}/{module}.py")
        nodes.extend((package, module, class_name, icon) for class_name, icon in matches)
    return nodes


def catalog_category(package: str, module: str) -> str:
    """On-prem modules keep their bare name; other packages carry a prefix."""

    return module if package == "onprem" else f"{package}-{module}"


def import_node(node: tuple[str, str, str, str]) -> dict[str, object]:
    package, module, class_name, icon_name = node
    category = catalog_category(package, module)
    service_id = f"{category}-{Path(icon_name).stem}"
    relative_png = f"resources/{package}/{module}/{icon_name}"
    png = fetch(f"{RAW_ROOT}/{relative_png}")
    svg = svg_wrapper(png)
    relative_svg = f"{category}/{service_id}.svg"
    destination = DESTINATION / relative_svg
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(svg)
    return {
        "id": service_id,
        "name": display_name(class_name),
        "class_name": class_name,
        "aliases": [
            class_name,
            f"diagrams.{package}.{module}.{class_name}",
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


def _upstream(icon_id: str) -> bool:
    """Whether this importer manages an id: the 3D items (``iso-*``) share the
    catalog and belong to scripts/build/iso-render.py --install."""
    return not icon_id.startswith("iso-")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="write the upstream set even where it drops or adds icons the catalog lists",
    )
    force = parser.parse_args(argv).force
    nodes = discover_nodes()
    service_ids = [
        f"{catalog_category(package, module)}-{Path(icon).stem}"
        for package, module, _, icon in nodes
    ]
    if len(service_ids) != len(set(service_ids)):
        raise ValueError("on-premises node discovery produced duplicate service ids")
    refused = refusal(CATALOG, service_ids, owned=_upstream, force=force)
    if refused:
        print(refused, file=sys.stderr)
        return 1
    # the entries another tool installed stay as they are
    kept = (
        [
            icon
            for icon in json.loads(CATALOG.read_text(encoding="utf-8"))["icons"]
            if not _upstream(str(icon["id"]))
        ]
        if CATALOG.is_file()
        else []
    )

    with ThreadPoolExecutor(max_workers=12) as pool:
        icons = list(pool.map(import_node, nodes))
    icons = sorted([*icons, *kept], key=lambda entry: str(entry["id"]))

    catalog = {
        "schema_version": 1,
        "collection": "vendors/onprem",
        "generated_by": (
            "pinned mingrammer/diagrams importer: onprem, generic and elastic node sets"
        ),
        "source": {
            "url": f"{SOURCE_ROOT}/resources",
            "packages": ["onprem", *EXTRA_PACKAGES],
            "release": f"mingrammer/diagrams {RELEASE} ({COMMIT})",
            "terms": LICENSE_URL,
        },
        "counts": {"icons": len(icons)},
        "icons": icons,
    }
    DESTINATION.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps(catalog, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"Imported {len(icons)} on-premises icons into {DESTINATION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
