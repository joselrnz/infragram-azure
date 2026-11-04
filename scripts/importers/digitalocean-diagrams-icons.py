#!/usr/bin/env python3
"""Vendor the complete DigitalOcean node set from mingrammer/diagrams.

The user approved reuse of these MIT-licensed architecture symbols.  Assets
are pinned to one upstream commit, embedded byte-for-byte inside standalone
SVG wrappers, and recorded with both source and generated-file hashes.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
DESTINATION = ROOT / "skills" / "infragram-azure" / "assets" / "icons" / "vendors" / "digitalocean"
CATALOG = DESTINATION / "catalog.json"
COMMIT = "364c61d47884bc0718d07f932f7c1772e82c42b1"
RAW_ROOT = f"https://raw.githubusercontent.com/mingrammer/diagrams/{COMMIT}/resources/digitalocean"
SOURCE_ROOT = f"https://github.com/mingrammer/diagrams/blob/{COMMIT}/resources/digitalocean"
LICENSE_URL = "https://github.com/mingrammer/diagrams/blob/master/LICENSE"


NODES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "compute": (
        ("containers", "DigitalOcean Containers", "Containers"),
        ("docker", "DigitalOcean Docker", "Docker"),
        ("droplet-connect", "DigitalOcean Droplet Connect", "DropletConnect"),
        ("droplet-snapshot", "DigitalOcean Droplet Snapshot", "DropletSnapshot"),
        ("droplet", "DigitalOcean Droplet", "Droplet"),
        ("k8s-cluster", "DigitalOcean Kubernetes Cluster", "K8SCluster"),
        ("k8s-node-pool", "DigitalOcean Kubernetes Node Pool", "K8SNodePool"),
        ("k8s-node", "DigitalOcean Kubernetes Node", "K8SNode"),
    ),
    "database": (
        (
            "dbaas-primary-standby-more",
            "DigitalOcean DBaaS Primary, Standby & Read-only",
            "DbaasPrimaryStandbyMore",
        ),
        ("dbaas-primary", "DigitalOcean DBaaS Primary", "DbaasPrimary"),
        ("dbaas-read-only", "DigitalOcean DBaaS Read-only", "DbaasReadOnly"),
        ("dbaas-standby", "DigitalOcean DBaaS Standby", "DbaasStandby"),
    ),
    "network": (
        ("certificate", "DigitalOcean Certificate", "Certificate"),
        ("domain-registration", "DigitalOcean Domain Registration", "DomainRegistration"),
        ("domain", "DigitalOcean Domain", "Domain"),
        ("firewall", "DigitalOcean Firewall", "Firewall"),
        ("floating-ip", "DigitalOcean Floating IP", "FloatingIp"),
        ("internet-gateway", "DigitalOcean Internet Gateway", "InternetGateway"),
        ("load-balancer", "DigitalOcean Load Balancer", "LoadBalancer"),
        ("managed-vpn", "DigitalOcean Managed VPN", "ManagedVpn"),
        ("vpc", "DigitalOcean VPC", "Vpc"),
    ),
    "storage": (
        ("folder", "DigitalOcean Folder", "Folder"),
        ("space", "DigitalOcean Space", "Space"),
        ("volume-snapshot", "DigitalOcean Volume Snapshot", "VolumeSnapshot"),
        ("volume", "DigitalOcean Volume", "Volume"),
    ),
}

DOKS_BOUNDARY_SVG = b"""<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
  <g stroke="#0069ff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 8V4M15.1 9l2.85-2.85M16 12h4M15.1 15l2.85 2.85M12 16v4M8.9 15l-2.85 2.85M8 12H4M8.9 9 6.05 6.15"/>
    <circle cx="12" cy="12" r="4"/><circle cx="12" cy="2.75" r="1.75"/>
    <circle cx="19.25" cy="4.75" r="1.75"/><circle cx="21.25" cy="12" r="1.75"/>
    <circle cx="19.25" cy="19.25" r="1.75"/><circle cx="12" cy="21.25" r="1.75"/>
    <circle cx="4.75" cy="19.25" r="1.75"/><circle cx="2.75" cy="12" r="1.75"/>
    <circle cx="4.75" cy="4.75" r="1.75"/>
  </g>
</svg>
"""


def fetch(url: str) -> bytes:
    if not url.startswith("https://"):
        raise SystemExit(f"icons are fetched over https only, not {url}")
    request = Request(url, headers={"User-Agent": "Infragram DigitalOcean node importer"})  # noqa: S310 - https, checked above
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS host
        data = response.read()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"expected PNG from {url}")
    return data


def svg_wrapper(png: bytes) -> bytes:
    encoded = base64.b64encode(png).decode("ascii")
    return (
        '<svg aria-hidden="true" viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">\n'
        f'  <image width="256" height="256" href="data:image/png;base64,{encoded}"/>\n'
        "</svg>\n"
    ).encode()


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args(argv)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in catalog["icons"]}

    for category, nodes in NODES.items():
        destination_dir = DESTINATION / category
        destination_dir.mkdir(parents=True, exist_ok=True)
        for service_id, name, class_name in nodes:
            relative_png = f"{category}/{service_id}.png"
            png = fetch(f"{RAW_ROOT}/{relative_png}")
            svg = svg_wrapper(png)
            relative_svg = f"{category}/{service_id}.svg"
            (DESTINATION / relative_svg).write_bytes(svg)

            previous = by_id.get(service_id, {})
            # an icon that moved category leaves no copy behind at its old path:
            # three such files once outlived the entries that pointed at them
            stale = str(previous.get("file", ""))
            if stale and stale != relative_svg and (DESTINATION / stale).is_file():
                (DESTINATION / stale).unlink()
            aliases = set(map(str, previous.get("aliases", [])))
            aliases.update(
                (
                    class_name,
                    f"diagrams.digitalocean.{category}.{class_name}",
                )
            )
            by_id[service_id] = {
                "id": service_id,
                "name": name,
                "class_name": class_name,
                "aliases": sorted(aliases, key=str.casefold),
                "category": category,
                "file": relative_svg,
                "source_path": f"resources/digitalocean/{relative_png}",
                "sha256": hashlib.sha256(svg).hexdigest(),
                "source_sha256": hashlib.sha256(png).hexdigest(),
                "source_url": f"{SOURCE_ROOT}/{relative_png}",
                "source_release": (
                    f"mingrammer/diagrams commit {COMMIT}; exact PNG embedded "
                    "in a self-contained SVG wrapper"
                ),
                "terms_url": LICENSE_URL,
            }
            compatibility = {
                "k8s-cluster": ["containers"],
                "load-balancer": ["networking"],
                "vpc": ["networking"],
            }.get(service_id)
            if compatibility:
                by_id[service_id]["compat_categories"] = compatibility
            if service_id == "vpc":
                by_id[service_id]["compat_class_names"] = {"networking": "VPC"}

    boundary_path = DESTINATION / "containers" / "doks-boundary.svg"
    boundary_path.write_bytes(DOKS_BOUNDARY_SVG)
    by_id["doks-boundary"] = {
        "id": "doks-boundary",
        "name": "DigitalOcean DOKS Boundary",
        "aliases": ["DOKS frame", "Kubernetes cluster boundary"],
        "category": "containers",
        "file": "containers/doks-boundary.svg",
        "source_path": "infragram/digitalocean/doks-boundary.svg",
        "sha256": hashlib.sha256(DOKS_BOUNDARY_SVG).hexdigest(),
        "source_url": f"{SOURCE_ROOT}/compute/k8s-cluster.png",
        "source_release": (
            "Infragram boundary glyph retained for white-on-provider tabs; "
            f"derived from the node vocabulary at mingrammer/diagrams commit {COMMIT}"
        ),
        "terms_url": LICENSE_URL,
    }

    catalog["generated_by"] = (
        "hand-curated DigitalOcean docs icons plus pinned mingrammer/diagrams nodes"
    )
    catalog["icons"] = sorted(by_id.values(), key=lambda entry: str(entry["id"]))
    catalog["counts"] = {
        "icons": len(catalog["icons"]),
        "third_party_overrides": sum(
            str(entry.get("source_url", "")).startswith("https://github.com/mingrammer/diagrams")
            for entry in catalog["icons"]
        ),
    }
    CATALOG.write_text(json.dumps(catalog, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
