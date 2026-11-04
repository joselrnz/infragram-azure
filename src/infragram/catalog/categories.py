"""Canonical cloud categories and provider-native normalization rules.

Provider icon packs keep their source taxonomies for provenance. This module
owns the smaller, stable taxonomy exposed by the sidebar, project template,
and every export format.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..paths import skill_assets
from ..utils.text import SLUG as _SLUG, slugify

EXPECTED_CATEGORY_LABELS = (
    "Custom",
    "AI & Machine Learning",
    "Analytics",
    "Compute",
    "Containers",
    "Databases",
    "DevOps",
    "Hybrid & MultiCloud",
    "Identity",
    "Integration",
    "Internet of Things",
    "Energy & Power",
    "Industrial & OT",
    "Facilities & Sites",
    "Governance",
    "Mobile",
    "Networking",
    "Power Platform",
    "Security",
    "Storage",
    "Web",
)

Visibility = Literal["always", "when-populated"]


class UnknownCategoryError(ValueError):
    """Raised when a provider category needs an explicit reviewed mapping."""


def _key(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        # the error the callers catch: an empty vendor category is a mapping
        # that needs reviewing, not a crash
        raise UnknownCategoryError("category keys must be non-empty strings")
    return slugify(value)


class Category(BaseModel):
    """One canonical category, as ``categories.json`` records it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    label: str
    icon: str
    order: int = Field(gt=0)
    visibility: Visibility
    aliases: tuple[str, ...] = ()

    @field_validator("id", "icon")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not _SLUG.fullmatch(value):
            raise ValueError(f"must be a slug, got {value!r}")
        return value

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("label must be a non-empty string")
        return value.strip()

    @field_validator("aliases")
    @classmethod
    def _alias_keys(cls, aliases: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_key(alias) for alias in aliases)


class _CategoryFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    categories: list[Category]


class CategoryCoverage(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: str
    mapped: tuple[str, ...]
    unmapped: tuple[str, ...]


class CategoryRegistry:
    """Validated ordered categories shared by the UI and exports."""

    def __init__(self, categories: tuple[Category, ...]) -> None:
        self.categories = categories
        self.by_id = {category.id: category for category in categories}
        aliases: dict[str, str] = {}
        for category in categories:
            for raw_alias in (category.id, category.label, *category.aliases):
                alias = _key(raw_alias)
                owner = aliases.get(alias)
                if owner is not None and owner != category.id:
                    raise ValueError(
                        f"category alias {raw_alias!r} belongs to both {owner} and {category.id}"
                    )
                aliases[alias] = category.id
        self.aliases = aliases

    @classmethod
    def load(cls, path: Path) -> CategoryRegistry:
        record = _CategoryFile.model_validate_json(path.read_text(encoding="utf-8"))
        ids: set[str] = set()
        icons: set[str] = set()
        orders: set[int] = set()
        for category in record.categories:
            if category.id in ids or category.icon in icons or category.order in orders:
                raise ValueError(f"duplicate category id, icon, or order at {category.id}")
            ids.add(category.id)
            icons.add(category.icon)
            orders.add(category.order)
        categories = sorted(record.categories, key=lambda category: category.order)
        labels = tuple(category.label for category in categories)
        if labels != EXPECTED_CATEGORY_LABELS:
            raise ValueError(
                "category labels/order differ from the approved twenty-one-category contract"
            )
        return cls(tuple(categories))

    def resolve(self, value: str) -> str | None:
        return self.aliases.get(_key(value))

    def visible(
        self, counts: Mapping[str, int], *, show_empty: bool = False
    ) -> tuple[Category, ...]:
        unknown = set(counts) - set(self.by_id)
        if unknown:
            raise ValueError(f"counts contain unknown category ids: {sorted(unknown)}")
        return tuple(
            category
            for category in self.categories
            if show_empty or category.visibility == "always" or counts.get(category.id, 0) > 0
        )


class _RawMapping(BaseModel):
    """One provider's block in ``provider-category-map.json``, as written."""

    model_config = ConfigDict(extra="forbid")

    native_categories: dict[str, str | None] = Field(default_factory=dict)
    service_overrides: dict[str, str] = Field(default_factory=dict)


class _MapFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    providers: dict[str, _RawMapping] = Field(min_length=1)


class _ProviderMapping(BaseModel):
    model_config = ConfigDict(frozen=True)

    native_categories: Mapping[str, str | None]
    service_overrides: Mapping[str, str]


class ProviderCategoryMappings:
    """Strict provider-native to canonical category mappings."""

    def __init__(
        self,
        registry: CategoryRegistry,
        providers: Mapping[str, _ProviderMapping],
    ) -> None:
        self.registry = registry
        self.providers = dict(providers)

    @classmethod
    def load(cls, path: Path, registry: CategoryRegistry) -> ProviderCategoryMappings:
        record = _MapFile.model_validate_json(path.read_text(encoding="utf-8"))
        providers: dict[str, _ProviderMapping] = {}
        for raw_provider, raw_mapping in record.providers.items():
            provider = _key(raw_provider)

            normalized_native: dict[str, str | None] = {}
            for raw_category, target in raw_mapping.native_categories.items():
                key = _key(raw_category)
                if target is not None:
                    target = _key(target)
                    if target not in registry.by_id:
                        raise ValueError(
                            f"provider {provider} maps {key} to unknown category {target}"
                        )
                normalized_native[key] = target

            normalized_overrides: dict[str, str] = {}
            for raw_service, target in raw_mapping.service_overrides.items():
                service = _key(raw_service)
                target = _key(target)
                if target not in registry.by_id:
                    raise ValueError(
                        f"provider {provider} service {service} maps to unknown category {target}"
                    )
                normalized_overrides[service] = target
            providers[provider] = _ProviderMapping(
                native_categories=normalized_native,
                service_overrides=normalized_overrides,
            )
        return cls(registry, providers)

    def normalize(
        self,
        provider: str,
        native_category: str,
        *,
        service_id: str | None = None,
    ) -> str:
        provider_key = _key(provider)
        mapping = self.providers.get(provider_key)
        if mapping is None:
            raise UnknownCategoryError(f"unknown provider: {provider}")
        if service_id:
            override = mapping.service_overrides.get(_key(service_id))
            if override:
                return override

        native_key = _key(native_category)
        if native_key in mapping.native_categories:
            target = mapping.native_categories[native_key]
            if target is None:
                raise UnknownCategoryError(
                    f"{provider_key} category {native_key!r} requires a service override"
                )
            return target

        canonical = self.registry.resolve(native_key)
        if canonical is not None:
            return canonical
        raise UnknownCategoryError(f"{provider_key} category {native_category!r} is not mapped")

    def coverage(
        self, provider: str, native_categories: list[str] | tuple[str, ...]
    ) -> CategoryCoverage:
        mapped: list[str] = []
        unmapped: list[str] = []
        for category in dict.fromkeys(native_categories):
            try:
                self.normalize(provider, category)
            except UnknownCategoryError:
                unmapped.append(category)
            else:
                mapped.append(category)
        return CategoryCoverage(
            provider=_key(provider), mapped=tuple(mapped), unmapped=tuple(unmapped)
        )


@lru_cache(maxsize=1)
def load_default_category_registry() -> CategoryRegistry:
    return CategoryRegistry.load(skill_assets() / "catalog/categories.json")


@lru_cache(maxsize=1)
def load_default_provider_mappings() -> ProviderCategoryMappings:
    registry = load_default_category_registry()
    return ProviderCategoryMappings.load(
        skill_assets() / "catalog/provider-category-map.json", registry
    )
