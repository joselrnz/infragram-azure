"""Provider-library descriptors shared by projects, catalogs, and editor shells."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..paths import skill_assets
from ..utils.text import SLUG as _SLUG
from .categories import ProviderCategoryMappings, load_default_provider_mappings

ProviderKind = Literal["cloud", "platform", "on-prem"]
Coverage = Literal["full", "reviewed"]


class ProviderDescriptor(BaseModel):
    """One installed library, as ``providers.json`` records it."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str
    display_name: str = Field(min_length=1)
    short_name: str = Field(min_length=1)
    kind: ProviderKind
    coverage: Coverage
    source_url: str
    terms_url: str
    terms: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    #: What the reviewed artwork may be redistributed under, in the vendor's words.
    license_basis: str = ""
    #: The name this library wears on a chip in the editor chrome -- the
    #: library selector's summary line and its quick filters. ``short_name``
    #: is the badge on a component card and is an abbreviation ("AZ", "DO",
    #: "K8S"); most read as a name too, and where one does not, this says
    #: what to show instead. Empty means the badge is fine.
    chip_name: str = ""
    #: Whether the sidebar offers this library a one-click filter. Three of
    #: the nineteen do, and which three used to be a tuple inside the view.
    quick_filter: bool = False

    @property
    def chip(self) -> str:
        """The name a chip wears: its own, or the badge abbreviation."""
        return self.chip_name or self.short_name

    @field_validator("id")
    @classmethod
    def _slug(cls, value: str) -> str:
        value = value.casefold()
        if not _SLUG.fullmatch(value):
            raise ValueError(f"invalid provider id: {value!r}")
        return value

    @field_validator("kind", "coverage", mode="before")
    @classmethod
    def _lower(cls, value: object) -> object:
        return value.strip().casefold() if isinstance(value, str) else value

    @field_validator("source_url", "terms_url")
    @classmethod
    def _https(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("source and terms URLs must use HTTPS")
        return value


class _RegistryFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    providers: list[ProviderDescriptor] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> _RegistryFile:
        seen: set[str] = set()
        for provider in self.providers:
            if provider.id in seen:
                raise ValueError(f"duplicate provider descriptor: {provider.id}")
            seen.add(provider.id)
        return self


class ProviderRegistry:
    """Validated ordered provider descriptors for installed libraries."""

    def __init__(self, providers: tuple[ProviderDescriptor, ...]) -> None:
        self.providers = providers
        self.by_id = {provider.id: provider for provider in providers}

    def __getitem__(self, provider_id: str) -> ProviderDescriptor:
        try:
            return self.by_id[provider_id.strip().casefold()]
        except KeyError as error:
            raise KeyError(f"unknown provider: {provider_id}") from error

    @classmethod
    def load(
        cls,
        path: Path,
        mappings: ProviderCategoryMappings | None = None,
    ) -> ProviderRegistry:
        record = _RegistryFile.model_validate_json(path.read_text(encoding="utf-8"))
        ids = {provider.id for provider in record.providers}
        mappings = mappings or load_default_provider_mappings()
        mapped_ids = set(mappings.providers)
        if ids != mapped_ids:
            missing = sorted(mapped_ids - ids)
            extra = sorted(ids - mapped_ids)
            raise ValueError(
                f"provider descriptors differ from category mappings; missing={missing}, extra={extra}"
            )
        return cls(tuple(record.providers))


@lru_cache(maxsize=1)
def load_default_provider_registry() -> ProviderRegistry:
    return ProviderRegistry.load(skill_assets() / "catalog" / "providers.json")


__all__ = [
    "Coverage",
    "ProviderDescriptor",
    "ProviderKind",
    "ProviderRegistry",
    "load_default_provider_registry",
]
