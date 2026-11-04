"""The document itself: :class:`CloudProject` and its migrations.

The template stores intent, not rendered coordinates. A provider-aware
renderer turns the topology into a scene, so browser editing, CLI rendering
and hosted exports all consume the same versioned document.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from ..catalog.categories import load_default_provider_mappings
from ..models.topology import TopologyElement
from ..utils.text import SLUG as _SLUG
from .names import ProjectKind
from .parts import Layer, Presentation, ProviderSelection, View

__all__ = ["CloudProject"]


def _is_platform(provider: str) -> bool:
    """Is this provider a platform rather than a cloud?

    The registry knows; asking it means Kubernetes, OpenStack, VMware and
    Proxmox are all classified the same way, which testing one id by hand did
    not do.
    """
    from ..catalog.providers import load_default_provider_registry

    try:
        return load_default_provider_registry()[provider].kind == "platform"
    except (KeyError, OSError):
        return False


class CloudProject(BaseModel):
    """Versioned source document for single-provider and mixed-provider diagrams."""

    schema_version: Literal[3] = 3
    kind: ProjectKind = "single-cloud"
    slug: str
    title: str
    description: str
    template_brief: str = ""
    starter_preset: str | None = None
    providers: tuple[ProviderSelection, ...]
    default_library: str = "all"
    layers: tuple[Layer, ...] = ()
    #: Named parts of the diagram, each drawn on its own with ``--view``
    #: (infragram.projects.views). A view owns no elements.
    views: tuple[View, ...] = ()
    icon_collection: str | None = None
    presentation: Presentation = Field(default_factory=Presentation)
    topology: TopologyElement

    model_config = {"extra": "forbid"}

    @field_validator("slug")
    @classmethod
    def _valid_slug(cls, value: str) -> str:
        if not _SLUG.fullmatch(value):
            raise ValueError("slug must contain lowercase letters, numbers, and hyphens")
        return value

    @field_validator("title", "description")
    @classmethod
    def _non_empty_copy(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("template_brief")
    @classmethod
    def _clean_template_brief(cls, value: str) -> str:
        return value.strip()

    @field_validator("starter_preset")
    @classmethod
    def _valid_starter_preset(cls, value: str | None) -> str | None:
        if value is None:
            return None
        preset = value.strip().casefold()
        if not _SLUG.fullmatch(preset):
            raise ValueError("starter preset must be a slug")
        return preset

    @model_validator(mode="before")
    @classmethod
    def _schema_reference(cls, value: Any) -> Any:
        """``$schema`` names the JSON Schema (projects/schema.py) for an
        editor's completion; it says nothing about the diagram, so it is
        accepted and not kept."""
        if isinstance(value, dict) and "$schema" in value:
            if not isinstance(value["$schema"], str):
                raise ValueError("$schema must be a string naming the document's JSON Schema")
            value = {key: item for key, item in value.items() if key != "$schema"}
        return value

    @model_validator(mode="before")
    @classmethod
    def _migrate_version_two(cls, value: Any) -> Any:
        """Version 2 said nothing about where a drawing stands.

        Version 3 adds ``presentation.status``, ``notes`` and ``drawn``, all
        optional, so a version 2 document is a version 3 document that does
        not say. Nothing is rewritten but the number.
        """
        if not isinstance(value, dict) or value.get("schema_version") != 2:
            return value
        payload = deepcopy(value)
        payload["schema_version"] = 3
        return payload

    @model_validator(mode="before")
    @classmethod
    def _migrate_version_one(cls, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            return value

        payload = deepcopy(value)
        provider = str(payload.pop("provider", "")).strip().casefold()
        payload["schema_version"] = 2
        payload["kind"] = "platform" if _is_platform(provider) else "single-cloud"
        payload["providers"] = [{"id": provider, "enabled": True}]
        payload["default_library"] = provider
        layer_id = f"provider:{provider}"
        payload["layers"] = [
            {
                "id": layer_id,
                "name": provider.replace("-", " ").title(),
                "kind": "platform" if _is_platform(provider) else "provider",
                "provider": provider,
                "visible": True,
                "locked": False,
                "order": 0,
            }
        ]

        def qualify(element: Any) -> None:
            if not isinstance(element, dict):
                return
            attributes = element.get("attributes")
            icon = attributes.get("icon") if isinstance(attributes, dict) else None
            if isinstance(icon, str) and _SLUG.fullmatch(icon.strip().casefold()):
                service_id = icon.strip().casefold()
                element["component"] = {
                    "provider": provider,
                    "service_id": service_id,
                    "icon_ref": f"{provider}:{service_id}",
                }
                element["layer_id"] = layer_id
            for child in element.get("children", []):
                qualify(child)

        qualify(payload.get("topology"))
        return payload

    @model_validator(mode="after")
    def _project_references_resolve(self) -> CloudProject:
        registered = load_default_provider_mappings().providers
        provider_ids = tuple(selection.id for selection in self.providers)
        duplicates = sorted(
            provider for provider in set(provider_ids) if provider_ids.count(provider) > 1
        )
        if duplicates:
            raise ValueError(f"duplicate provider selection: {', '.join(duplicates)}")
        unknown = sorted(set(provider_ids) - set(registered))
        if unknown:
            raise ValueError(f"unsupported cloud provider: {', '.join(unknown)}")
        enabled = tuple(selection.id for selection in self.providers if selection.enabled)
        if not enabled:
            raise ValueError("at least one provider library must be enabled")
        if self.default_library != "all" and self.default_library not in enabled:
            raise ValueError(
                f"default_library must be 'all' or an enabled provider: {self.default_library}"
            )
        if self.kind == "single-cloud" and len(provider_ids) != 1:
            raise ValueError("single-cloud projects require exactly one provider")
        if self.kind == "multicloud" and len(provider_ids) < 2:
            raise ValueError("multicloud projects require at least two providers")

        layer_ids = tuple(layer.id for layer in self.layers)
        duplicate_layers = sorted(
            layer_id for layer_id in set(layer_ids) if layer_ids.count(layer_id) > 1
        )
        if duplicate_layers:
            raise ValueError(f"duplicate layer id: {', '.join(duplicate_layers)}")
        for layer in self.layers:
            if layer.provider is not None and layer.provider not in provider_ids:
                raise ValueError(
                    f"layer {layer.id!r} provider {layer.provider!r} is not enabled in this project"
                )

        view_ids = [view.id for view in self.views]
        repeated = sorted({view_id for view_id in view_ids if view_ids.count(view_id) > 1})
        if repeated:
            raise ValueError(f"duplicate view id: {', '.join(repeated)}")
        for view in self.views:
            if view.extends is not None and view.extends not in view_ids:
                raise ValueError(f"view {view.id!r} extends unknown view {view.extends!r}")

        known = self.topology.index()
        for element in known.values():
            if element.layer_id is not None and element.layer_id not in layer_ids:
                raise ValueError(
                    f"element {element.id!r} references unknown layer {element.layer_id!r}"
                )
            if (
                element.component is not None
                and element.component.provider != "infragram"
                and element.component.provider not in provider_ids
            ):
                raise ValueError(
                    f"component provider {element.component.provider!r} is not enabled in this project"
                )
            for connection in element.connections:
                if connection.target not in known:
                    raise ValueError(
                        f"{element.id!r} connects to unknown target {connection.target!r}"
                    )
        return self

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(selection.id for selection in self.providers)

    @property
    def provider(self) -> str:
        """Primary provider compatibility view for the phase-one editor."""

        if self.default_library != "all":
            return self.default_library
        return next(selection.id for selection in self.providers if selection.enabled)

    def save(self, path: Path) -> Path:
        # newline="\n" so a document written on Windows is byte-identical to
        # one written on Linux. The template is read back by the checker and
        # held to a hash by the gates, and CRLF made one document two files.
        path.write_text(
            self.model_dump_json(indent=2, exclude_none=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        return path

    @classmethod
    def load(cls, path: Path) -> CloudProject:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
