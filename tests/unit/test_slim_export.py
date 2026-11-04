"""An export embeds the project's libraries by default, every library on request."""

from __future__ import annotations

import pytest

from infragram.catalog import load_default_provider_registry
from infragram.editor.shell import library_catalog_from_html
from infragram.exports import ExportError, render_project_html
from infragram.projects import CloudProject


def _library(html: str) -> dict:
    return library_catalog_from_html(html)


def _kubernetes_project() -> CloudProject:
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "platform",
            "slug": "one-deployment",
            "title": "One deployment",
            "description": "A single Kubernetes deployment.",
            "providers": [{"id": "kubernetes", "enabled": True}],
            "default_library": "kubernetes",
            "presentation": {"size": "fit"},
            "topology": {
                "id": "root",
                "name": "One deployment",
                "type": "group",
                "children": [
                    {
                        "id": "api",
                        "name": "API deployment",
                        "type": "service",
                        "component": {
                            "provider": "kubernetes",
                            "service_id": "deploy",
                            "icon_ref": "kubernetes:deploy",
                        },
                        "attributes": {"editor_x": 200, "editor_y": 200},
                    }
                ],
            },
        }
    )


def _azure_project() -> CloudProject:
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "single-cloud",
            "slug": "one-vm",
            "title": "One VM",
            "description": "A single virtual machine.",
            "providers": [{"id": "azure", "enabled": True}],
            "default_library": "azure",
            "presentation": {"size": "fit"},
            "topology": {
                "id": "root",
                "name": "One VM",
                "type": "group",
                "children": [
                    {
                        "id": "vm",
                        "name": "Virtual machine",
                        "type": "service",
                        "component": {
                            "provider": "azure",
                            "service_id": "virtual-machine",
                            "icon_ref": "azure:virtual-machine",
                        },
                        "attributes": {"editor_x": 200, "editor_y": 200},
                    }
                ],
            },
        }
    )


def test_default_export_embeds_only_the_projects_libraries() -> None:
    html = render_project_html(_kubernetes_project())
    library = _library(html)

    assert [provider["id"] for provider in library["providers"]] == ["kubernetes"]
    assert library["selectedProviders"] == ["kubernetes"]
    providers_present = {component["provider"] for component in library["components"]}
    # the library itself plus the shared primitives and frames, nothing else
    assert providers_present == {"kubernetes", "infragram"}
    assert any(component["componentKind"] == "boundary" for component in library["components"])
    # The selector describes its one embedded library and offers no option
    # or quick filter for another library.
    assert 'data-provider-quick-filter="azure"' not in html
    assert html.count('data-provider-option="') == 1
    assert 'data-provider-option="kubernetes"' in html
    assert 'data-provider-option="azure"' not in html
    assert 'data-provider-option="databricks"' not in html
    assert "data-provider-summary>All 1<" in html


def test_all_libraries_export_still_embeds_every_installed_library() -> None:
    registry = load_default_provider_registry()
    slim = render_project_html(_kubernetes_project())
    full = render_project_html(_kubernetes_project(), libraries="all")
    library = _library(full)

    assert [provider["id"] for provider in library["providers"]] == [
        provider.id for provider in registry.providers
    ]
    assert tuple(provider["id"] for provider in library["providers"]) == (
        "azure",
        "kubernetes",
        "databricks",
    )
    assert 'data-provider-quick-filter="azure"' in full
    # the whole point: a single-library export is a fraction of the workspace.
    # The shared primitives and the runtime travel with every page; Azure's
    # 715 official icons are what the Kubernetes-only page leaves behind.
    assert len(full) - len(slim) > 900_000
    assert len(slim) < len(full) * 0.6


def test_a_cloud_export_does_not_carry_the_platform_library_it_does_not_use() -> None:
    # No starter stack of either library places components from the other,
    # so an Azure-only export ships Azure alone.
    library = _library(render_project_html(_azure_project()))

    assert [provider["id"] for provider in library["providers"]] == ["azure"]
    assert library["selectedProviders"] == ["azure"]
    assert not any(component["provider"] == "kubernetes" for component in library["components"])


def test_unknown_libraries_choice_is_rejected() -> None:
    with pytest.raises(ExportError):
        render_project_html(_kubernetes_project(), libraries="some")
