from __future__ import annotations

import json

import pytest

from infragram.catalog import (
    load_composite_catalog,
    load_default_alias_overlay,
    load_default_provider_registry,
    load_provider_component_catalog,
)
from infragram.paths import skill_assets


def _catalog():
    registry = load_default_provider_registry()
    return load_composite_catalog(tuple(registry.by_id))


def test_alias_overlay_targets_only_shipped_services() -> None:
    overlay = load_default_alias_overlay()
    for provider in ("azure", "kubernetes"):
        shipped = {
            component.service_id
            for component in load_provider_component_catalog(provider).components
        }
        missing = set(overlay.service_ids(provider)) - shipped
        assert not missing, f"{provider} overlay names unknown services: {sorted(missing)}"


def test_alias_overlay_file_is_normalized() -> None:
    raw = json.loads((skill_assets() / "catalog/aliases.json").read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    for provider, services in raw["providers"].items():
        assert list(services) == sorted(services), provider
        for service_id, aliases in services.items():
            assert aliases, f"{provider}:{service_id} has an empty alias list"
            assert len(set(aliases)) == len(aliases), f"{provider}:{service_id} repeats an alias"


def test_big_cloud_libraries_are_searchable_by_common_names() -> None:
    catalog = _catalog()
    expectations = {
        "vnet": "azure:virtual-networks",
        "aks": "azure:kubernetes-services",
        "blob": "azure:storage-accounts",
        "configmap": "kubernetes:cm",
        "statefulset": "kubernetes:sts",
        "daemonset": "kubernetes:ds",
    }
    for query, expected in expectations.items():
        hits = {component.qualified_id for component in catalog.search(query)}
        assert expected in hits, f"{query!r} did not find {expected}: {sorted(hits)[:8]}"


@pytest.mark.parametrize(
    ("provider", "minimum"),
    [("azure", 340), ("kubernetes", 33)],
)
def test_big_libraries_carry_curated_search_aliases(provider: str, minimum: int) -> None:
    components = load_provider_component_catalog(provider).components
    aliased = [component for component in components if component.aliases]
    # Substring search already covers the vendor's own words; the overlay adds
    # the acronyms and synonyms architects actually type.
    assert len(aliased) >= minimum, (
        f"{provider}: only {len(aliased)} of {len(components)} carry aliases"
    )


def test_no_vendor_icon_is_left_uncategorized() -> None:
    catalog = _catalog()
    unmapped = sorted(
        component.qualified_id
        for component in catalog.components
        if component.mapping_status != "mapped"
    )
    assert unmapped == []
