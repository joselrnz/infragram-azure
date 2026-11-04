#!/usr/bin/env python3
"""Provider icon suite: registry contract and the Azure service artwork.

One catalog-driven run over both installed libraries: aliases, provenance,
hashes, and SVG safety for every registered icon, then the four example
service roles the Azure theme draws. The browser-based selection-overlay test
stays separate (it needs Playwright).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))

from infragram import SERVICE_ROLES, load_catalog  # noqa: E402

CATALOG = ROOT / "skills/infragram-azure/assets/themes/catalog.json"


@pytest.fixture
def providers() -> dict:
    """The catalog keyed by slug, as main() builds it for the script path."""
    return {provider.slug: provider for provider in load_catalog(CATALOG)}


def test_service_registry(providers) -> None:
    """Aliases, provenance, hashes, and SVG safety for every registered icon."""
    assert set(providers) == {"azure", "kubernetes", "databricks"}
    minimums = {"azure": 12}
    expected_aliases = {
        "azure": {
            "vnet": "virtual-network",
            "aks": "kubernetes-service",
            "blob": "storage-accounts",
        },
    }

    for slug, minimum in minimums.items():
        provider = providers[slug]
        assert len(provider.icons) >= minimum, (
            f"{slug} needs at least {minimum} registered service icons"
        )
        for query, expected in expected_aliases[slug].items():
            assert provider.icons[provider.icon_aliases[query.casefold()]].slug == expected, (
                f"{slug} alias {query!r}"
            )

    for provider in providers.values():
        for icon in provider.icons.values():
            assert icon.category in provider.icon_categories
            assert icon.path.is_file() and icon.path.suffix.lower() == ".svg"
            assert hashlib.sha256(icon.path.read_bytes()).hexdigest() == icon.sha256
            assert icon.source_url.startswith("https://")
            assert icon.terms_url.startswith("https://")
            svg = icon.path.read_text(encoding="utf-8")
            lowered = svg.lower()
            assert "<svg" in lowered and "viewbox=" in lowered
            assert "<script" not in lowered and "<foreignobject" not in lowered
            assert "javascript:" not in lowered

    for provider in providers.values():
        for role, path in provider.service_icon_paths.items():
            assert (
                path
                == provider.icons[
                    provider.icon_aliases[provider.service_icon_slugs[role].casefold()]
                ].path
            )

    print("PASS: provider service registry contract")


def test_azure_icons(providers) -> None:
    """Azure ships one self-contained, on-palette icon per service role."""
    provider = providers["azure"]
    if tuple(provider.service_icon_paths) != SERVICE_ROLES:
        raise AssertionError(f"unexpected Azure icon roles: {tuple(provider.service_icon_paths)}")
    for role, path in provider.service_icon_paths.items():
        if not path.is_file():
            raise AssertionError(f"missing {role} icon: {path}")
        source = path.read_text(encoding="utf-8").casefold()
        # Official artwork ships at its own viewBox; the renderer scales it
        # through the <symbol> viewBox, so the contract is "standalone,
        # scalable, on-brand" - not one fixed size.
        if "<svg" not in source or "viewbox=" not in source:
            raise AssertionError(f"invalid standalone {role} icon: {path.name}")
        palette = {color.casefold() for color in provider.icon_palette}
        if not any(color in source for color in palette):
            raise AssertionError(f"{role} icon uses no declared Azure palette color: {path.name}")

    print("PASS: Azure service icons are self-contained and on-palette")


def main() -> int:
    providers = {provider.slug: provider for provider in load_catalog(CATALOG)}
    test_service_registry(providers)
    test_azure_icons(providers)
    print("PASS: provider suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
