from __future__ import annotations

import json
import re

from infragram.editor.shell import library_catalog_from_html
from infragram.exports import render_project_html
from infragram.projects import CloudProject


def hybrid_project() -> CloudProject:
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "hybrid",
            "slug": "global-platform",
            "title": "Global Platform",
            "description": "Azure and Kubernetes services in one workspace.",
            "providers": [{"id": item} for item in ("azure", "kubernetes")],
            "default_library": "all",
            "layers": [
                {
                    "id": f"provider:{provider}",
                    "name": name,
                    "kind": "provider",
                    "provider": provider,
                    "order": index,
                }
                for index, (provider, name) in enumerate(
                    (("azure", "Azure"), ("kubernetes", "Kubernetes"))
                )
            ],
            "topology": {
                "id": "root",
                "name": "Global Platform",
                "type": "group",
                "children": [
                    {
                        "id": "gateway",
                        "name": "Gateway",
                        "type": "service",
                        "component": {
                            "provider": "azure",
                            "service_id": "application-gateways",
                        },
                        "layer_id": "provider:azure",
                        "connections": [{"target": "worker", "kind": "solid"}],
                    },
                    {
                        "id": "worker",
                        "name": "Worker",
                        "type": "service",
                        "component": {"provider": "kubernetes", "service_id": "deploy"},
                        "layer_id": "provider:kubernetes",
                        "connections": [{"target": "database", "kind": "dashed"}],
                    },
                    {
                        "id": "database",
                        "name": "Database",
                        "type": "database",
                        "component": {"provider": "azure", "service_id": "sql-database"},
                        "layer_id": "provider:azure",
                    },
                ],
            },
        }
    )


def _json_script(html: str, element_id: str) -> dict:
    match = re.search(
        rf'<script type="application/json" id="{element_id}"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_editor_state_v3_preserves_provider_identity_layers_and_artwork() -> None:
    html = render_project_html(hybrid_project())
    state = _json_script(html, "infragram-editor-state")
    library = library_catalog_from_html(html)
    artwork = {
        component["qualifiedId"]: component["iconUri"] for component in library["components"]
    }

    assert state["schemaVersion"] == 3
    assert state["projectSlug"] == "global-platform"
    assert state["providers"] == ["azure", "kubernetes"]
    assert [layer["id"] for layer in state["layers"]] == [
        "provider:azure",
        "provider:kubernetes",
    ]
    nodes = {node["id"]: node for node in state["nodes"]}
    assert nodes["gateway"]["layerId"] == "provider:azure"
    assert nodes["worker"]["layerId"] == "provider:kubernetes"
    assert nodes["database"]["layerId"] == "provider:azure"
    assert nodes["worker"]["iconUri"] == artwork["kubernetes:deploy"]
    assert nodes["database"]["iconUri"] == artwork["azure:sql-database"]


def test_inspector_exposes_provider_context_layers_and_arrange_controls() -> None:
    html = render_project_html(hybrid_project())

    assert 'data-inspector-tab="arrange"' in html
    assert 'data-inspector-tab="layers"' in html
    assert "data-inspector-provider" in html
    assert "data-inspector-component" in html
    assert 'data-exact-field="x"' in html
    assert 'data-exact-field="y"' in html
    assert 'data-exact-field="width"' in html
    assert 'data-exact-field="height"' in html
    for action in (
        "align-left",
        "align-center",
        "align-right",
        "align-top",
        "align-middle",
        "align-bottom",
        "distribute-horizontal",
        "distribute-vertical",
    ):
        assert f'data-arrange-action="{action}"' in html
    assert "data-layer-list" in html


def test_runtime_declares_v2_recovery_migration_and_non_exported_guides() -> None:
    html = render_project_html(hybrid_project())

    assert "migrateSavedState" in html
    assert "saved.schemaVersion === 2" in html
    assert "migrated.schemaVersion = 3" in html
    assert "data-alignment-guide-layer" in html
    export_source = html.split("const exportSvg", maxsplit=1)[1]
    assert "[data-alignment-guide-layer]" in export_source
