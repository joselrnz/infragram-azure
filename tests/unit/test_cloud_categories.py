"""Contract tests for the provider-neutral cloud sidebar taxonomy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infragram.catalog.categories import (
    EXPECTED_CATEGORY_LABELS,
    UnknownCategoryError,
    load_default_category_registry,
    load_default_provider_mappings,
)

ROOT = Path(__file__).resolve().parents[2]


def test_default_registry_preserves_the_approved_sidebar_order() -> None:
    registry = load_default_category_registry()

    assert [category.label for category in registry.categories] == list(EXPECTED_CATEGORY_LABELS)
    assert len(registry.categories) == 21
    assert registry.categories[0].id == "custom"
    assert registry.categories[-1].id == "web"


def test_category_identity_order_and_icons_are_unique() -> None:
    registry = load_default_category_registry()

    assert len({category.id for category in registry.categories}) == 21
    assert len({category.order for category in registry.categories}) == 21
    assert len({category.icon for category in registry.categories}) == 21
    assert all(category.order % 10 == 0 for category in registry.categories)


def test_registry_matches_every_registered_provider_theme() -> None:
    mappings = load_default_provider_mappings()
    theme_catalog = json.loads(
        (ROOT / "skills/infragram-azure/assets/themes/catalog.json").read_text(encoding="utf-8")
    )
    theme_slugs = {Path(filename).stem for filename in theme_catalog["providers"]}

    assert set(mappings.providers) == theme_slugs


@pytest.mark.parametrize(
    ("provider", "native_category", "service_id", "expected"),
    [
        ("azure", "management-governance", None, "governance"),
        ("azure", "app-services", None, "web"),
        ("azure", "general", "subscriptions", "governance"),
        ("azure", "iot", None, "internet-of-things"),
        ("kubernetes", "resources", None, "containers"),
        ("kubernetes", "infrastructure-components", None, "containers"),
    ],
)
def test_provider_native_categories_normalize_to_the_shared_contract(
    provider: str,
    native_category: str,
    service_id: str | None,
    expected: str,
) -> None:
    mappings = load_default_provider_mappings()

    assert mappings.normalize(provider, native_category, service_id=service_id) == expected


def test_service_override_wins_over_a_broad_provider_category() -> None:
    mappings = load_default_provider_mappings()

    # The Azure deck's General folder is a grab bag: without an override it
    # lands in custom, and the reviewed overrides file its services properly.
    assert mappings.normalize("azure", "general", service_id="subscriptions") == "governance"
    assert mappings.normalize("azure", "general", service_id="cache") == "databases"
    assert mappings.normalize("azure", "general") == "custom"


def test_unknown_categories_fail_loudly_instead_of_falling_back() -> None:
    mappings = load_default_provider_mappings()

    with pytest.raises(UnknownCategoryError, match="not mapped"):
        mappings.normalize("azure", "totally-new-service-family")
    with pytest.raises(UnknownCategoryError, match="unknown provider"):
        mappings.normalize("unknown-cloud", "compute")


def test_visible_categories_keep_order_and_hide_empty_conditional_rows() -> None:
    registry = load_default_category_registry()

    assert [category.id for category in registry.visible({})] == ["custom"]
    assert [
        category.id
        for category in registry.visible({"compute": 2, "power-platform": 1, "storage": 3})
    ] == ["custom", "compute", "power-platform", "storage"]
    assert len(registry.visible({}, show_empty=True)) == 21


def test_coverage_report_names_unmapped_native_categories() -> None:
    mappings = load_default_provider_mappings()

    report = mappings.coverage("azure", ["compute", "management-governance", "new-provider-bucket"])

    assert report.mapped == ("compute", "management-governance")
    assert report.unmapped == ("new-provider-bucket",)
