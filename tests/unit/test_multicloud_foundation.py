from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from infragram.catalog import (
    load_composite_catalog,
    load_default_provider_registry,
)
from infragram.projects import CloudProject


def legacy_project_payload(provider: str = "azure") -> dict:
    return {
        "schema_version": 1,
        "slug": f"{provider}-legacy-api",
        "title": f"{provider.upper()} legacy API",
        "description": "A version-one project that must migrate without data loss.",
        "provider": provider,
        "presentation": {"size": "fit", "detail": "balanced"},
        "topology": {
            "id": "root",
            "name": "Application",
            "type": "group",
            "children": [
                {
                    "id": "api",
                    "name": "API",
                    "type": "service",
                    "attributes": {"icon": "app-services"},
                    "connections": [{"target": "database", "kind": "traffic", "label": "SQL"}],
                },
                {
                    "id": "database",
                    "name": "Database",
                    "type": "database",
                    "attributes": {"icon": "sql-database"},
                },
            ],
        },
    }


def hybrid_project_payload() -> dict:
    return {
        "schema_version": 2,
        "kind": "hybrid",
        "slug": "azure-kubernetes-platform",
        "title": "Azure and Kubernetes platform",
        "description": "A cloud landing zone with a Kubernetes platform and cross-library traffic.",
        "providers": [
            {"id": "azure", "enabled": True},
            {"id": "kubernetes", "enabled": True},
        ],
        "default_library": "all",
        "layers": [
            {
                "id": "provider:azure",
                "name": "Azure",
                "kind": "provider",
                "provider": "azure",
                "order": 10,
            },
            {
                "id": "provider:kubernetes",
                "name": "Kubernetes",
                "kind": "provider",
                "provider": "kubernetes",
                "order": 20,
            },
        ],
        "presentation": {"size": "fit", "detail": "faithful"},
        "topology": {
            "id": "root",
            "name": "Hybrid application",
            "type": "group",
            "children": [
                {
                    "id": "azure-api",
                    "name": "Azure API Management",
                    "type": "service",
                    "component": {
                        "provider": "azure",
                        "service_id": "api-management-services",
                    },
                    "layer_id": "provider:azure",
                    "connections": [
                        {"target": "k8s-deployment", "kind": "private", "label": "HTTPS"}
                    ],
                },
                {
                    "id": "k8s-deployment",
                    "name": "API deployment",
                    "type": "service",
                    "component": {
                        "provider": "kubernetes",
                        "service_id": "deploy",
                    },
                    "layer_id": "provider:kubernetes",
                    "connections": [
                        {"target": "azure-database", "kind": "replication", "label": "EVENTS"}
                    ],
                },
                {
                    "id": "azure-database",
                    "name": "Azure SQL",
                    "type": "database",
                    "component": {
                        "provider": "azure",
                        "service_id": "sql-database",
                        "icon_ref": "azure:sql-database",
                    },
                    "layer_id": "provider:azure",
                },
            ],
        },
    }


def test_version_one_project_migrates_in_memory_without_rewriting_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "legacy.infragram.json"
    original = json.dumps(legacy_project_payload(), indent=2) + "\n"
    source.write_text(original, encoding="utf-8")

    project = CloudProject.load(source)

    assert source.read_text(encoding="utf-8") == original
    assert project.schema_version == 3
    assert project.kind == "single-cloud"
    assert [(item.id, item.enabled) for item in project.providers] == [("azure", True)]
    assert project.default_library == "azure"
    assert project.provider == "azure"
    assert project.layers[0].id == "provider:azure"
    assert project.layers[0].provider == "azure"
    assert project.topology.index()["api"].component.icon_ref == "azure:app-services"
    assert project.topology.index()["api"].layer_id == "provider:azure"


def test_migrated_project_saves_as_schema_version_three(tmp_path: Path) -> None:
    project = CloudProject.model_validate(legacy_project_payload("azure"))
    output = tmp_path / "migrated.infragram.json"

    project.save(output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 3
    assert payload["kind"] == "single-cloud"
    assert payload["providers"] == [{"id": "azure", "enabled": True}]
    assert "provider" not in payload


def test_azure_and_kubernetes_project_round_trips_with_qualified_components(
    tmp_path: Path,
) -> None:
    project = CloudProject.model_validate(hybrid_project_payload())
    output = tmp_path / "hybrid.infragram.json"

    project.save(output)
    loaded = CloudProject.load(output)

    assert loaded == project
    assert loaded.schema_version == 3
    assert loaded.kind == "hybrid"
    assert loaded.provider_ids == ("azure", "kubernetes")
    assert loaded.topology.index()["azure-api"].component.icon_ref == (
        "azure:api-management-services"
    )
    assert loaded.topology.index()["k8s-deployment"].component.icon_ref == "kubernetes:deploy"
    assert loaded.topology.index()["azure-database"].component.icon_ref == "azure:sql-database"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload["providers"].append({"id": "kubernetes"}), "duplicate provider"),
        (
            # the platform library dropped while a component still draws from it
            lambda payload: payload["providers"].pop(1),
            "not enabled in this project",
        ),
        (
            lambda payload: payload["topology"]["children"][0].update(
                {"layer_id": "provider:missing"}
            ),
            "unknown layer",
        ),
        (
            lambda payload: (
                payload["providers"].pop(1),
                payload["topology"]["children"].pop(1),
                payload["topology"]["children"][0].pop("connections"),
            ),
            "not enabled in this project",
        ),
    ],
)
def test_hybrid_project_rejects_ambiguous_provider_and_layer_references(
    mutation,
    message: str,
) -> None:
    payload = hybrid_project_payload()
    mutation(payload)

    with pytest.raises(ValidationError, match=message):
        CloudProject.model_validate(payload)


def test_component_ref_rejects_mismatched_qualified_icon() -> None:
    payload = hybrid_project_payload()
    payload["topology"]["children"][1]["component"]["icon_ref"] = "azure:deploy"

    with pytest.raises(ValidationError, match="icon_ref must use provider prefix kubernetes"):
        CloudProject.model_validate(payload)


def test_provider_registry_describes_every_installed_library() -> None:
    registry = load_default_provider_registry()

    assert tuple(provider.id for provider in registry.providers) == (
        "azure",
        "kubernetes",
        "databricks",
    )
    assert registry["azure"].display_name == "Azure"
    assert registry["azure"].short_name == "AZ"
    assert registry["azure"].kind == "cloud"
    assert registry["azure"].coverage == "full"
    assert registry["azure"].source_url.startswith("https://learn.microsoft.com/")
    assert registry["azure"].terms
    assert registry["kubernetes"].kind == "platform"
    assert registry["kubernetes"].coverage == "reviewed"
    assert registry["kubernetes"].source_url.startswith("https://github.com/kubernetes/")
    assert registry["databricks"].kind == "platform"
    assert registry["databricks"].coverage == "reviewed"
    assert registry["databricks"].short_name == "DBX"


def test_composite_catalog_qualifies_services_and_deduplicates_custom_shapes() -> None:
    catalog = load_composite_catalog(("azure", "kubernetes"))

    assert tuple(provider.id for provider in catalog.providers) == (
        "azure",
        "kubernetes",
    )
    qualified_ids = {component.qualified_id for component in catalog.components}
    assert "azure:virtual-machine" in qualified_ids
    assert "kubernetes:deploy" in qualified_ids
    assert "kubernetes:kubernetes" in qualified_ids
    assert "infragram:custom-annotation" in qualified_ids
    assert (
        sum(
            component.qualified_id == "infragram:custom-annotation"
            for component in catalog.components
        )
        == 1
    )
    assert all(":" in component.qualified_id for component in catalog.components)
    assert len(catalog.components) > 1_000


def test_composite_catalog_searches_names_aliases_and_provider_names() -> None:
    catalog = load_composite_catalog(("azure", "kubernetes"))

    assert catalog.search("deploy")[0].qualified_id == "kubernetes:deploy"
    assert any(
        result.qualified_id == "azure:kubernetes-services" for result in catalog.search("aks")
    )
    assert any(
        result.qualified_id == "azure:virtual-machine"
        for result in catalog.search("azure virtual machine")
    )


def test_composite_catalog_rejects_duplicate_or_unknown_provider_selection() -> None:
    with pytest.raises(ValueError, match="duplicate provider"):
        load_composite_catalog(("azure", "azure"))

    with pytest.raises(ValueError, match="unknown provider"):
        load_composite_catalog(("mystery-cloud",))
