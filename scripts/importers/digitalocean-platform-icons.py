#!/usr/bin/env python3
"""Import the icon vocabulary used by DigitalOcean's Platform docs page.

The page mixes product, platform-governance, navigation, and support artwork.
This importer intentionally lists every ``/images/icons/*.svg`` asset exposed
by https://docs.digitalocean.com/platform/ so additions remain reviewable and
the catalog keeps deterministic source paths and SHA-256 provenance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import TypedDict
from urllib.request import Request, urlopen

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
DESTINATION = ROOT / "skills" / "infragram-azure" / "assets" / "icons" / "vendors" / "digitalocean"
CATALOG = DESTINATION / "catalog.json"
BASE_URL = "https://docs.digitalocean.com/images/icons/"
TERMS_URL = "https://www.digitalocean.com/legal/trademark-guidelines"


class PlatformIcon(TypedDict):
    """One Platform-page asset as this importer lists it."""

    id: str
    name: str
    category: str
    source_name: str
    aliases: list[str]


def icon(
    slug: str,
    name: str,
    category: str,
    source_name: str,
    *aliases: str,
) -> PlatformIcon:
    return {
        "id": slug,
        "name": name,
        "category": category,
        "source_name": source_name,
        "aliases": list(aliases),
    }


PLATFORM_ICONS = (
    icon(
        "accounts",
        "DigitalOcean Accounts",
        "integration",
        "accounts.7c3a46a4e139957c37b1ba530846464f3b7432b7bc00793db0d8e788940ddf69.svg",
    ),
    icon(
        "ai-assistant",
        "DigitalOcean AI Assistant",
        "ai",
        "ai-assistant.94496a3010f5c6549b9cd7c8412f61958b4e1b1cb7da8cea0ca7bfc622d27cef.svg",
        "control panel assistant",
    ),
    icon(
        "billing",
        "DigitalOcean Billing",
        "integration",
        "billing.357b31651da85802e1aa1c9f0b19cda7b26d5c971352f7176d1a130b21e088b7.svg",
    ),
    icon(
        "community",
        "DigitalOcean Community",
        "integration",
        "community.e52948b16b3479e4da950fbd790f94f478c598797f6b149a928ed5861c56d088.svg",
        "developer tools",
    ),
    icon(
        "ddos",
        "DigitalOcean DDoS Protection",
        "security",
        "ddos.d1d685c82e43143a4973f4dca8fb250b84dc76297607557c229c58e1916db549.svg",
    ),
    icon(
        "resource-limits",
        "DigitalOcean Resource Limits",
        "governance",
        "default.09205e3f8a46d107d3fe9c819ca920f186df235ea36143c514811a9a37dcb4ad.svg",
        "team limits",
        "product limits",
    ),
    icon(
        "platform-logomark",
        "DigitalOcean Platform Mark",
        "integration",
        "digitalocean-logomark.fbe7ea61f6bde3a4d8848d2e3d241a26db3d79d7adc9c651104c68bd1d212c82.svg",
        "trust platform",
        "service status",
    ),
    icon(
        "ip-ranges",
        "DigitalOcean IP Ranges",
        "networking",
        "dns.cb34d0653affb99d6826d0a3c70bdb8311ae7f51ca44810ae41cb1deb2e03a71.svg",
        "csv",
        "network ranges",
    ),
    icon(
        "organizations",
        "DigitalOcean Organizations",
        "governance",
        "organizations.ae95392d02268a2e13ef28b6aabf1b35b6a0a5a9ef64517fedf080075500cefd.svg",
        "consolidated billing",
    ),
    icon(
        "product-lifecycle",
        "DigitalOcean Product Lifecycle",
        "governance",
        "product-lifecycle.420c79b20e1d85e7a00a3dbb1734dc5c65ceaac5449c3ed8c34ad37cc88ffd9b.svg",
        "release stage",
    ),
    icon(
        "regional-availability",
        "DigitalOcean Regional Availability",
        "governance",
        "regional-availability.32459447c00bfdb1c07abebcc0fdd721a4cbd93143cb616b0fbe5c629e4a938c.svg",
        "datacenter availability",
    ),
    icon(
        "release-notes",
        "DigitalOcean Release Notes",
        "devops",
        "release-notes.5fbb164636ab961df9e08f892a39623e2bf7848be659fb300d6b0bab87a060dd.svg",
        "changelog",
    ),
    icon(
        "service-level-agreements",
        "DigitalOcean Service-Level Agreements",
        "governance",
        "slas.1b124ea38fb251987cabe77aae688f5c00fa72130222aca6073b34a82f26bfe2.svg",
        "sla",
    ),
    icon(
        "support-plans",
        "DigitalOcean Support Plans",
        "integration",
        "support-plans.91273ef64796cbf92aa09b42996c4fd5bae614b3ce3dd81c685d8da10c28f209.svg",
    ),
    icon(
        "support",
        "DigitalOcean Support",
        "integration",
        "support.91273ef64796cbf92aa09b42996c4fd5bae614b3ce3dd81c685d8da10c28f209.svg",
        "support ticket",
    ),
    icon(
        "teams",
        "DigitalOcean Teams",
        "governance",
        "teams.d6932e5b476fcbbdf1fecec304776ef06c1a04d23174de1c0e6b349d96add59f.svg",
        "team members",
        "team settings",
    ),
)

# DigitalOcean intentionally reuses two Platform-page SVGs. Keep one catalog
# asset per artwork and retain the other page concepts as searchable aliases.
DUPLICATE_TO = {
    "resource-limits": "projects",
    "support-plans": "support",
}


def fetch(source_name: str) -> bytes:
    request = Request(  # noqa: S310 - BASE_URL is a fixed https address
        BASE_URL + source_name,
        headers={"User-Agent": "Infragram DigitalOcean platform icon importer"},
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS host
        data = response.read()
    lowered = data.lower()
    if b"<svg" not in lowered or b"<script" in lowered or b"onload=" in lowered:
        raise ValueError(f"unsafe or invalid SVG: {source_name}")
    return data


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args(argv)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    by_id = {entry["id"]: entry for entry in catalog["icons"]}

    for raw in PLATFORM_ICONS:
        source_name = str(raw["source_name"])
        data = fetch(source_name)
        digest = hashlib.sha256(data).hexdigest()
        expected = source_name.rsplit(".", 2)[-2]
        if digest != expected:
            raise ValueError(f"DigitalOcean asset digest mismatch for {source_name}: {digest}")

        category = str(raw["category"])
        canonical_id = DUPLICATE_TO.get(str(raw["id"]))
        if canonical_id:
            canonical = by_id[canonical_id]
            if canonical["sha256"] != digest:
                raise ValueError(f"expected {raw['id']} to reuse {canonical_id} artwork")
            aliases = {
                *canonical.get("aliases", []),
                str(raw["name"]),
                *map(str, raw["aliases"]),
            }
            canonical["aliases"] = sorted(aliases, key=str.casefold)
            additional = set(canonical.get("additional_source_paths", []))
            additional.add(f"images/icons/{source_name}")
            canonical["additional_source_paths"] = sorted(additional)
            by_id.pop(str(raw["id"]), None)
            stale = DESTINATION / category / f"{raw['id']}.svg"
            if stale.is_file():
                stale.unlink()
            continue

        target = DESTINATION / category / f"{raw['id']}.svg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        existing = by_id.get(str(raw["id"]), {})
        aliases = {
            *existing.get("aliases", []),
            *map(str, raw["aliases"]),
        }
        record = {
            "id": raw["id"],
            "name": raw["name"],
            "aliases": sorted(aliases, key=str.casefold),
            "category": category,
            "file": target.relative_to(DESTINATION).as_posix(),
            "source_path": f"images/icons/{source_name}",
            "sha256": digest,
            "source_url": "https://docs.digitalocean.com/platform/",
            "source_release": "DigitalOcean Platform documentation icon set",
            "terms_url": TERMS_URL,
        }
        if existing.get("additional_source_paths"):
            record["additional_source_paths"] = existing["additional_source_paths"]
        by_id[str(raw["id"])] = record

    icons = sorted(by_id.values(), key=lambda entry: str(entry["id"]))
    catalog["generated_by"] = (
        "hand-curated; official icons from docs.digitalocean.com, four "
        "community icons retained with their own provenance"
    )
    catalog["counts"]["icons"] = len(icons)
    catalog["icons"] = icons
    CATALOG.write_text(
        json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"Imported {len(PLATFORM_ICONS)} Platform page icons; {len(icons)} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
