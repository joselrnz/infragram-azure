"""Curated search aliases layered over the vendor icon catalogs.

Vendor packs arrive with the names their publishers use ("Key Management
Service", "cm", "Hetzner Storage Box").  Architects search with the words they
say ("kms", "configmap", "backup space").  The overlay in
``assets/catalog/aliases.json`` records those words per provider and service
so the sidebar and :meth:`CompositeCatalog.search` find the right card without
rewriting any imported catalog.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..paths import skill_assets


def _key(value: str) -> str:
    return " ".join(value.strip().casefold().split())


class _AliasFile(BaseModel):
    """``aliases.json`` as written: provider -> service id -> words."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    providers: dict[str, dict[str, list[str]]] = Field(default_factory=dict)

    @field_validator("providers")
    @classmethod
    def _aliases_are_words(
        cls, providers: dict[str, dict[str, list[str]]]
    ) -> dict[str, dict[str, list[str]]]:
        for provider, services in providers.items():
            for service_id, aliases in services.items():
                if not all(alias.strip() for alias in aliases):
                    raise ValueError(
                        f"aliases for {provider}:{service_id} must be non-empty strings"
                    )
        return providers


class AliasOverlay(BaseModel):
    """Provider -> service id -> extra search aliases, every key normalised."""

    model_config = ConfigDict(frozen=True)

    providers: Mapping[str, Mapping[str, tuple[str, ...]]] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> AliasOverlay:
        raw = _AliasFile.model_validate_json(path.read_text(encoding="utf-8"))
        providers: dict[str, dict[str, tuple[str, ...]]] = {}
        for provider, services in raw.providers.items():
            providers[_key(provider)] = {
                _key(service_id): tuple(dict.fromkeys(_key(alias) for alias in aliases))
                for service_id, aliases in services.items()
            }
        return cls(providers=providers)

    def for_service(self, provider: str, service_id: str) -> tuple[str, ...]:
        return self.providers.get(_key(provider), {}).get(_key(service_id), ())

    def merge(self, provider: str, service_id: str, aliases: tuple[str, ...]) -> tuple[str, ...]:
        """Catalog aliases first, curated ones after, duplicates dropped."""

        extra = self.for_service(provider, service_id)
        if not extra:
            return tuple(aliases)
        seen = {_key(alias) for alias in aliases}
        merged = list(aliases)
        for alias in extra:
            if alias not in seen:
                seen.add(alias)
                merged.append(alias)
        return tuple(merged)

    def service_ids(self, provider: str) -> tuple[str, ...]:
        return tuple(self.providers.get(_key(provider), {}))


@lru_cache(maxsize=1)
def load_default_alias_overlay() -> AliasOverlay:
    return AliasOverlay.load(skill_assets() / "catalog/aliases.json")
