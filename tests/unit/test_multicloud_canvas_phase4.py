from __future__ import annotations

import json
import re
from pathlib import Path

from infragram.catalog import (
    ARCHITECTURE_BOUNDARY_GROUPS,
    ARCHITECTURE_BOUNDARY_SPECS,
    ARCHITECTURE_FRAME_PRESETS,
)
from infragram.editor import load_sidebar_catalog
from infragram.editor.artwork import artwork_bytes
from infragram.editor.shell import library_catalog_from_html
from infragram.exports import render_project_html
from infragram.projects import CloudProject

ROOT = Path(__file__).parents[2]
TEMPLATE = (
    ROOT
    / "skills"
    / "infragram-azure"
    / "assets"
    / "templates"
    / "cloud"
    / "azure-hub-spoke-landing-zone.infragram.json"
)


def _json_script(html: str, element_id: str) -> dict:
    match = re.search(
        rf'<script type="application/json" id="{element_id}"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def _hybrid_project() -> CloudProject:
    """Both installed libraries in one workspace, with the platform card placed."""
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "hybrid",
            "slug": "aks-platform",
            "title": "AKS platform",
            "description": "An Azure landing zone with a Kubernetes platform inside it.",
            "providers": [{"id": "azure"}, {"id": "kubernetes"}],
            "default_library": "all",
            "topology": {
                "id": "root",
                "name": "AKS platform",
                "type": "group",
                "children": [
                    {
                        "id": "gateway",
                        "name": "Application Gateway",
                        "type": "service",
                        "component": {"provider": "azure", "service_id": "application-gateways"},
                        "connections": [{"target": "kubernetes-platform", "kind": "solid"}],
                    },
                    {
                        "id": "kubernetes-platform",
                        "name": "Kubernetes",
                        "type": "service",
                        "component": {"provider": "kubernetes", "service_id": "kubernetes"},
                        "connections": [{"target": "api", "kind": "dashed"}],
                    },
                    {
                        "id": "api",
                        "name": "API",
                        "type": "service",
                        "component": {"provider": "kubernetes", "service_id": "deploy"},
                    },
                ],
            },
        }
    )


def test_the_landing_zone_does_not_render_a_canvas_legend() -> None:
    project = CloudProject.load(TEMPLATE)
    html = render_project_html(project)

    assert project.presentation.legend == ()
    assert "<!-- Legend strip -->" not in html


def test_editor_places_masked_edge_labels_on_open_connector_segments() -> None:
    html = render_project_html(CloudProject.load(TEMPLATE))

    assert 'class="edge-label-mask"' in html
    assert "const straightHorizontal" in html
    assert "const straightVertical" in html
    assert "side = 'vertical'" in html
    assert 'data-edge-label="${escapeText(item.edge.id)}"' in html
    assert 'data-placement-mode="${labelPosition.mode}"' in html


def test_the_platform_card_uses_the_official_kubernetes_brand_mark() -> None:
    html = render_project_html(_hybrid_project())
    state = _json_script(html, "infragram-editor-state")
    library = library_catalog_from_html(html)

    node = next(item for item in state["nodes"] if item["id"] == "kubernetes-platform")
    component = next(
        item for item in library["components"] if item["qualifiedId"] == "kubernetes:kubernetes"
    )
    artwork = artwork_bytes(component["iconUri"]).decode("utf-8")

    assert node["componentQualifiedId"] == "kubernetes:kubernetes"
    assert node["iconUri"] == component["iconUri"]
    assert "#326ce5" in artwork.casefold()
    assert "viewBox" in artwork


def test_custom_library_includes_interactive_architecture_boundaries_for_every_library() -> None:
    catalog = load_sidebar_catalog("azure")
    custom = next(category for category in catalog.categories if category.id == "custom")
    components = {component.name: component for component in custom.components}

    expected = {
        "Cloud boundary",
        "On-premises site",
        "Azure subscription",
        "Azure virtual network",
        "Azure Kubernetes Service cluster",
        "Kubernetes cluster",
        "Kubernetes namespace",
    }

    assert expected <= set(components)
    assert all(components[name].component_kind == "boundary" for name in expected)
    assert all(components[name].boundary_kind for name in expected)


def test_architecture_boundaries_are_grouped_and_use_the_decks_own_styles() -> None:
    project = CloudProject.load(TEMPLATE)
    library = library_catalog_from_html(render_project_html(project))
    frames = {
        component["serviceId"]: component
        for component in library["components"]
        if component["componentKind"] == "boundary"
    }

    # Core frames first, then one group per library, in the catalog's order.
    assert library["frameGroups"] == [
        {"id": group_id, "label": label, "order": order}
        for order, (group_id, label) in enumerate(ARCHITECTURE_BOUNDARY_GROUPS)
    ]
    assert library["frameGroups"][0] == {"id": "generic", "label": "Core frames", "order": 0}
    assert library["frameGroups"][1] == {"id": "azure", "label": "Azure", "order": 1}
    assert library["frameGroups"][2] == {"id": "kubernetes", "label": "Kubernetes", "order": 2}

    cloud = frames["custom-boundary-cloud"]
    subscription = frames["custom-boundary-azure-subscription"]
    region = frames["custom-boundary-azure-region"]
    vnet = frames["custom-boundary-azure-vnet"]
    subnet = frames["custom-boundary-azure-subnet"]
    cluster = frames["custom-boundary-kubernetes-cluster"]

    assert cloud["frameGroup"] == "generic"
    assert cloud["boundaryStyle"]["stroke"] == "#bdbdbd"
    # Light-only: the editor carries no second stroke for a dark canvas.
    assert "darkStroke" not in cloud["boundaryStyle"]
    assert cloud["boundaryStyle"]["strokeWidth"] == 1.8
    # Azure's palette is sampled from the deck's own badge icons.
    assert subscription["boundaryStyle"]["stroke"] == "#ffcb12"
    assert region["boundaryStyle"]["stroke"] == "#ef7100"
    assert region["boundaryStyle"]["dash"] == "2,3"
    assert vnet["boundaryStyle"]["stroke"] == "#1490df"
    assert vnet["boundaryStyle"]["dash"] is None
    assert vnet["boundaryStyle"]["tabbed"] is True
    assert vnet["boundaryStyle"]["iconUri"].startswith("data:image/svg+xml;")
    assert subnet["boundaryStyle"]["fill"].startswith("rgba(80,230,255,")
    assert cluster["boundaryStyle"]["stroke"] == "#326ce5"
    assert vnet["defaultSize"] == {"width": 400, "height": 280}
    assert subnet["hierarchyLevel"] > vnet["hierarchyLevel"]


def test_azure_frames_use_distinct_official_service_icons() -> None:
    project = CloudProject.load(TEMPLATE)
    library = library_catalog_from_html(render_project_html(project))
    azure_frames = [
        component for component in library["components"] if component.get("frameGroup") == "azure"
    ]

    assert len(azure_frames) == 11
    assert all(frame["boundaryStyle"]["tabbed"] for frame in azure_frames)
    icon_uris = {frame["boundaryStyle"]["iconUri"] for frame in azure_frames}
    assert all(uri.startswith("data:image/svg+xml;") for uri in icon_uris)
    # One badge is worn twice, on purpose and on the record: Azure ships a
    # single Subnet mark and a public subnet is a subnet. Every other badge is
    # its own, and the pair is still told apart in the sidebar, because the
    # thumbnail draws the frame -- border and fill -- not the badge alone.
    twice = {
        frame["qualifiedId"]
        for frame in azure_frames
        if sum(
            other["boundaryStyle"]["iconUri"] == frame["boundaryStyle"]["iconUri"]
            for other in azure_frames
        )
        > 1
    }
    assert twice == {
        "infragram:custom-boundary-azure-subnet",
        "infragram:custom-boundary-azure-public-subnet",
    }
    assert len(icon_uris) == len(azure_frames) - 1
    assert len({frame["iconUri"] for frame in azure_frames}) == len(azure_frames)
    for frame in azure_frames:
        preview = artwork_bytes(frame["iconUri"]).decode("utf-8")
        assert "<image " in preview
        assert "data:image/svg+xml;" in preview


def test_every_architecture_frame_has_a_visible_semantic_icon() -> None:
    project = CloudProject.load(TEMPLATE)
    library = library_catalog_from_html(render_project_html(project))
    frames = [
        component
        for component in library["components"]
        if component.get("componentKind") == "boundary" and component.get("frameGroup")
    ]

    assert len(frames) == len(ARCHITECTURE_BOUNDARY_SPECS)
    assert all(frame["boundaryStyle"]["tabbed"] for frame in frames)
    assert all(frame["boundaryStyle"]["iconUri"] for frame in frames)
    for group in library["frameGroups"]:
        group_frames = [frame for frame in frames if frame["frameGroup"] == group["id"]]
        assert len({frame["boundaryStyle"]["iconUri"] for frame in group_frames}) >= 3


def test_editor_runtime_declares_nested_custom_sections_and_frame_galleries() -> None:
    html = render_project_html(CloudProject.load(TEMPLATE))

    assert "data-component-section" in html
    assert "architecture-frames" in html
    assert "data-frame-group" in html
    assert "frame-grid" in html
    assert "renderCustomCategory" in html
    assert "const iconOnly = node.displayMode === 'icon'" in html
    assert "const iconY = iconOnly" in html
    assert "const titleY = node.height / 2 - 2" in html
    assert "const detailY = node.height / 2 + 14" in html


def test_editor_declares_compact_frames_provider_presets_and_full_selection_tools() -> None:
    html = render_project_html(CloudProject.load(TEMPLATE))
    library = library_catalog_from_html(html)

    presets = {preset["id"]: preset for preset in library["framePresets"]}
    # Every starter stack the catalog defines reaches the editor, one per library.
    assert set(presets) == {preset["id"] for preset in ARCHITECTURE_FRAME_PRESETS}
    assert set(presets) == {"azure-landing-zone", "kubernetes-workload", "databricks-workspace"}
    assert presets["azure-landing-zone"]["componentIds"] == [
        "custom-boundary-azure-tenant",
        "custom-boundary-azure-management-group",
        "custom-boundary-azure-subscription",
        "custom-boundary-azure-resource-group",
        "custom-boundary-azure-vnet",
        "custom-boundary-azure-subnet",
    ]
    assert "layoutBase" not in presets["azure-landing-zone"]
    assert "frameSizes" not in presets["azure-landing-zone"]
    assert "editableFoundation" not in presets["azure-landing-zone"]
    assert presets["kubernetes-workload"]["componentIds"] == [
        "custom-boundary-kubernetes-cluster",
        "custom-boundary-kubernetes-namespace",
        "custom-boundary-kubernetes-workload",
    ]
    assert presets["kubernetes-workload"]["layoutBase"] == "azure-landing-zone"
    assert presets["kubernetes-workload"]["editableFoundation"] is True
    assert "cluster → namespace → workload" in presets["kubernetes-workload"]["detail"].casefold()

    assert "grid-template-columns:repeat(3,minmax(0,1fr))" in html
    assert "data-selection-toolbar" in html
    assert "data-selection-count-chip" in html
    assert "data-selection-bbox" in html
    assert "data-marquee-selection" in html
    assert "data-frame-tree" in html
    assert 'data-arrange-action="to-front"' in html
    assert "data-arrange-selection-kind" in html
    assert "Align and distribute" in html
    assert 'data-arrange-action="align-left"' in html
    assert 'data-arrange-action="distribute-horizontal"' in html
    assert 'data-arrange-action="detach"' in html
    assert 'data-arrange-action="group"' in html
    assert 'data-editor-action="zoom-reset"' in html
    assert "pinch or wheel to zoom" in html
    assert "middle-drag to pan" in html
    assert "data-panning" in html
    assert "event.button !== 1" in html
    assert 'data-text-control="fontSize"' in html
    assert 'data-content-control="name"' in html
    assert 'data-content-control="detail"' in html
    assert 'data-display-mode="card"' in html
    assert 'data-display-mode="icon"' in html
    assert "node.displayMode === 'icon'" in html
    assert "data-canvas-context-menu" in html
    assert 'aria-label="Canvas actions"' in html
    assert 'data-context-action="edit-text"' in html
    assert 'data-context-action="display-card"' in html
    assert 'data-context-action="display-icon"' in html
    assert 'data-context-action="to-front"' in html
    assert 'data-context-action="detach"' in html
    assert 'data-context-action="lock"' in html
    assert 'data-context-action="delete"' in html
    assert "diagram.addEventListener('contextmenu'" in html
    assert "if (event.button === 2) return" in html
    assert "selectedBoundaryIds" in html
    assert "updateDropTarget" in html
    assert "applyZOrder" in html
    assert "finishMarquee" in html
    assert "boundaryStyle" in html


def test_every_provider_frame_preset_references_its_own_shipped_boundary_components() -> None:
    library = library_catalog_from_html(render_project_html(_hybrid_project()))
    frames = {
        component["serviceId"]: component
        for component in library["components"]
        if component["componentKind"] == "boundary"
    }

    for preset in library["framePresets"]:
        component_ids = preset["componentIds"]
        assert len(component_ids) == len(set(component_ids)), preset["id"]
        assert all(component_id in frames for component_id in component_ids), preset["id"]
        assert all(
            frames[component_id]["frameGroup"] == preset["group"] for component_id in component_ids
        ), preset["id"]
        hierarchy = [frames[component_id]["hierarchyLevel"] for component_id in component_ids]
        assert all(isinstance(level, int) and level >= 0 for level in hierarchy)
        assert hierarchy[0] <= hierarchy[-1]


def test_every_shipped_sidebar_component_has_decodable_svg_artwork() -> None:
    for provider in ("azure", "kubernetes"):
        for category in load_sidebar_catalog(provider).categories:
            for component in category.components:
                artwork = artwork_bytes(component.icon_uri)
                assert artwork is not None and b"<svg" in artwork, (
                    provider,
                    category.id,
                    component.id,
                )


def test_runtime_declares_an_expandable_world_and_content_based_fit() -> None:
    html = render_project_html(_hybrid_project())

    assert "ensureCanvasExtent" in html
    assert "syncCanvasGeometry" in html
    assert "data-inspector-canvas" in html
    assert "contentBounds" in html
    assert "ResizeObserver" in html
    fit_source = html.split("const fitZoom", maxsplit=1)[1].split(
        "\n\n  document.querySelectorAll('[data-editor-action]')", maxsplit=1
    )[0]
    # the fit measures the content, plus the step list beside it
    assert "const bounds = fitBounds();" in fit_source
    fit_bounds = html.split("const fitBounds", maxsplit=1)[1].split("const fitZoom", maxsplit=1)[0]
    assert "contentBounds()" in fit_bounds and "[data-step-list]" in fit_bounds
    assert "preserveFit: true" in fit_source
    assert "requestAnimationFrame(() => requestAnimationFrame" in fit_source
    assert "if (!bounds)" in fit_source
    assert "maxNameChars" in html
    qualified = {
        component["qualifiedId"] for component in library_catalog_from_html(html)["components"]
    }
    for qualified_id in (
        "kubernetes:ing",
        "kubernetes:deploy",
        "kubernetes:svc",
        "kubernetes:pvc",
        "azure:application-gateways",
    ):
        assert qualified_id in qualified
