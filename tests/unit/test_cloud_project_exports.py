from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pydantic import ValidationError

from infragram.builders.architecture import load_icon_set
from infragram.catalog import load_default_provider_registry
from infragram.editor import load_sidebar_catalog
from infragram.editor.shell import library_catalog_from_html
from infragram.exports import (
    ExportError,
    export_project,
    extract_svg,
    make_standalone_svg,
    render_project_html,
    render_project_svg,
)
from infragram.projects import CloudProject


def project_payload() -> dict:
    return {
        "schema_version": 1,
        "slug": "azure-api",
        "title": "Azure API",
        "description": "Client traffic flows through an API to storage.",
        "provider": "azure",
        "presentation": {
            "size": "doc-inline",
            "detail": "balanced",
            "audience": "mixed",
            "eyebrow": "Azure architecture",
        },
        "topology": {
            "id": "root",
            "name": "Azure API",
            "type": "group",
            "children": [
                {
                    "id": "client",
                    "name": "Client",
                    "type": "client",
                    "connections": [{"target": "api", "kind": "solid", "label": "HTTPS"}],
                },
                {
                    "id": "api",
                    "name": "API",
                    "type": "service",
                    "role": "hub",
                    "connections": [{"target": "storage", "kind": "solid", "label": "WRITES"}],
                },
                {
                    "id": "storage",
                    "name": "Storage",
                    "type": "storage",
                },
            ],
        },
    }


def embedded_library(html: str) -> dict:
    return library_catalog_from_html(html)


def test_cloud_project_round_trips_as_a_versioned_template(tmp_path: Path) -> None:
    project = CloudProject.model_validate(project_payload())
    output = tmp_path / "azure-api.infragram.json"

    project.save(output)
    loaded = CloudProject.load(output)

    assert loaded == project
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 3
    assert saved["providers"] == [{"id": "azure", "enabled": True}]
    assert "provider" not in saved


def test_connector_label_placement_round_trips_into_editor_state() -> None:
    payload = project_payload()
    payload["topology"]["children"][0]["connections"][0]["label_placement"] = {
        "mode": "manual",
        "dx": 24,
        "dy": -16,
    }

    project = CloudProject.model_validate(payload)
    connection = project.topology.children[0].connections[0]

    assert connection.label_placement is not None
    assert connection.label_placement.mode == "manual"
    assert connection.label_placement.dx == 24
    assert connection.label_placement.dy == -16

    html = render_project_html(project)
    match = re.search(
        r'<script type="application/json" id="infragram-editor-state"[^>]*>'
        r"(.*?)</script>",
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    state = json.loads(match.group(1))
    https_edge = next(edge for edge in state["edges"] if edge["label"] == "HTTPS")
    assert https_edge["labelPlacement"] == {
        "mode": "manual",
        "dx": 24.0,
        "dy": -16.0,
    }


def test_connector_label_placement_rejects_unknown_modes() -> None:
    payload = project_payload()
    payload["topology"]["children"][0]["connections"][0]["label_placement"] = {
        "mode": "floating",
        "dx": 0,
        "dy": 0,
    }

    with pytest.raises(ValidationError, match="label_placement"):
        CloudProject.model_validate(payload)


HUB_SPOKE = (
    Path(__file__).parents[2]
    / "skills"
    / "infragram-azure"
    / "assets"
    / "templates"
    / "cloud"
    / "azure-hub-spoke-landing-zone.infragram.json"
)


def test_hub_spoke_template_preserves_reference_architecture_boundaries() -> None:
    project = CloudProject.load(HUB_SPOKE)
    elements = project.topology.index()

    assert project.provider == "azure"
    assert project.presentation.size == "fit"
    # A core cloud frame holds the Azure subscriptions; the on-premises site
    # is another core frame beside it.
    assert elements["microsoft-azure"].type == "cloud"
    assert elements["corporate-data-centre"].type == "site"
    assert elements["connectivity-subscription"] in elements["microsoft-azure"].children
    assert elements["landing-zones"].type == "environment"
    assert elements["landing-zones"] in elements["microsoft-azure"].children
    assert elements["east-us-2"] in elements["connectivity-subscription"].children
    assert elements["rg-connectivity-hub"] in elements["east-us-2"].children
    assert elements["hub-vnet-10-0-0-0-16"].type == "network"
    assert elements["hub-vnet-10-0-0-0-16"] in elements["rg-connectivity-hub"].children
    assert elements["gatewaysubnet"].type == "subnet-private"
    assert elements["gatewaysubnet"] in elements["hub-vnet-10-0-0-0-16"].children
    assert elements["landing-zone-production"] in elements["landing-zones"].children

    kinds = {
        connection.kind for element in project.topology.walk() for connection in element.connections
    }
    assert kinds == {"solid", "dashed", "dotted"}


def test_interactive_hub_spoke_keeps_boundary_and_editor_layers_separate() -> None:
    html = render_project_html(CloudProject.load(HUB_SPOKE))

    assert 'data-static-cluster-layer="true"' in html
    assert 'data-static-link-layer="true"' in html
    assert 'data-static-node-layer="true"' in html
    assert 'data-static-meta-layer="true"' in html
    assert "[data-static-cluster-layer],[data-static-link-layer],[data-static-node-layer]" in html
    assert "data-graph-boundary" in html
    assert "data-boundary-resize" in html
    assert "addBoundary" in html
    assert "child.dataset.staticLayer = 'true'" not in html


def test_interactive_hub_spoke_embeds_nested_dynamic_boundary_geometry() -> None:
    html = render_project_html(CloudProject.load(HUB_SPOKE))
    match = re.search(
        r'<script type="application/json" id="infragram-editor-state"[^>]*>'
        r"(.*?)</script>",
        html,
        flags=re.DOTALL,
    )

    assert match is not None
    state = json.loads(match.group(1))
    boundaries = {boundary["id"]: boundary for boundary in state["boundaries"]}
    nodes = {node["id"]: node for node in state["nodes"]}

    assert state["schemaVersion"] == 3
    assert {
        "microsoft-azure",
        "corporate-data-centre",
        "connectivity-subscription",
        "east-us-2",
        "rg-connectivity-hub",
        "hub-vnet-10-0-0-0-16",
        "gatewaysubnet",
        "azurefirewallsubnet",
        "landing-zones",
        "landing-zone-production",
        "management-subscription",
    } <= set(boundaries)
    assert boundaries["connectivity-subscription"]["parentId"] == "microsoft-azure"
    assert boundaries["east-us-2"]["parentId"] == "connectivity-subscription"
    assert boundaries["hub-vnet-10-0-0-0-16"]["parentId"] == "rg-connectivity-hub"
    assert boundaries["gatewaysubnet"]["parentId"] == "hub-vnet-10-0-0-0-16"
    assert nodes["expressroute-gateway"]["boundaryId"] == "gatewaysubnet"
    assert nodes["azure-firewall-premium"]["boundaryId"] == "azurefirewallsubnet"
    assert nodes["expressroute-circuit"]["boundaryId"] == "rg-connectivity-hub"
    # Azure's palette is sampled from the deck's own badge icons; the region
    # draws dotted, the way the deck separates placement from ownership.
    assert boundaries["connectivity-subscription"]["stroke"] == "#ffcb12"
    assert boundaries["east-us-2"]["stroke"] == "#ef7100"
    assert boundaries["east-us-2"]["dash"] == "2,3"
    assert boundaries["hub-vnet-10-0-0-0-16"]["stroke"] == "#1490df"
    assert boundaries["gatewaysubnet"]["fill"].startswith("rgba(80,230,255,")
    assert boundaries["east-us-2"]["pad"] == 24
    # The outer cloud frame is Azure's own, drawn in Azure blue; the
    # on-premises frame outside the estate keeps the neutral look.
    assert boundaries["microsoft-azure"]["frameGroup"] == "azure"
    assert boundaries["microsoft-azure"]["stroke"] == "#0078d4"
    assert boundaries["corporate-data-centre"]["stroke"] == "#bdbdbd"
    # An Azure badge is the deck's own icon on a paper tab, painting itself.
    subscription_icon = (
        __import__("base64")
        .b64decode(boundaries["connectivity-subscription"]["iconUri"].partition(",")[2])
        .decode("utf-8")
    )
    assert "currentColor" not in subscription_icon
    assert boundaries["connectivity-subscription"]["tabFill"].lower() == "#ffffff"


def test_interactive_hub_spoke_draws_the_built_in_link_kinds_from_the_shared_table() -> None:
    html = render_project_html(CloudProject.load(HUB_SPOKE))
    state_match = re.search(
        r'<script type="application/json" id="infragram-editor-state"[^>]*>'
        r"(.*?)</script>",
        html,
        flags=re.DOTALL,
    )
    assert state_match is not None
    state = json.loads(state_match.group(1))
    styles = {edge["kind"]: (edge["width"], edge.get("dash")) for edge in state["edges"]}
    # The Azure theme adds no link kinds of its own, so the three built-in
    # ones carry the dashes every renderer reads from render-metrics.json.
    from infragram.builders import metrics

    dashes = metrics.link_dashes()
    assert styles["solid"] == (1.4, None)
    assert styles["dashed"] == (1.0, dashes["dashed"])
    assert styles["dotted"] == (1.2, dashes["dotted"])

    lowest = max(
        int(y) + int(height)
        for y, height in re.findall(
            r'data-static-cluster-layer="true">\s*<rect x="\d+" y="(\d+)" width="\d+" height="(\d+)"',
            html,
        )
    )
    mark = re.search(
        r'<!-- Brand mark -->\s*<svg data-brand-mark="" x="\d+" y="(\d+)" width="\d+" height="(\d+)"',
        html,
    )
    assert mark is not None
    mark_y, _ = (int(value) for value in mark.groups())
    assert lowest + 16 <= mark_y


@pytest.mark.parametrize(
    "provider", [entry.id for entry in load_default_provider_registry().providers]
)
def test_cloud_project_accepts_every_registered_provider(provider: str) -> None:
    payload = project_payload()
    payload["provider"] = provider

    assert CloudProject.model_validate(payload).provider == provider


def test_cloud_project_rejects_unknown_providers() -> None:
    payload = project_payload()
    payload["provider"] = "mystery-cloud"

    with pytest.raises(ValidationError, match="unsupported cloud provider"):
        CloudProject.model_validate(payload)


def test_cloud_project_rejects_connections_to_missing_elements() -> None:
    payload = project_payload()
    payload["topology"]["children"][0]["connections"][0]["target"] = "missing"

    with pytest.raises(ValidationError, match="unknown target"):
        CloudProject.model_validate(payload)


def test_cloud_project_rejects_unversioned_or_future_templates() -> None:
    payload = project_payload()
    payload["schema_version"] = 4

    with pytest.raises(ValidationError, match="schema_version"):
        CloudProject.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("slug", "Not A Slug", "slug must"), ("title", "   ", "must not be empty")],
)
def test_cloud_project_rejects_invalid_identity_fields(
    field: str, value: str, message: str
) -> None:
    payload = project_payload()
    payload[field] = value

    with pytest.raises(ValidationError, match=message):
        CloudProject.model_validate(payload)


def test_project_renders_canonical_accessible_inline_svg_html() -> None:
    html = render_project_html(CloudProject.model_validate(project_payload()))

    assert html.startswith("<!DOCTYPE html>")
    assert 'class="provider-sidebar" data-testid="provider-sidebar"' in html
    assert '<input type="search"' in html
    assert "data-sidebar-search" in html
    assert html.count('data-category-id="') == 21
    library = embedded_library(html)
    assert (
        sum(component["provider"] in {"azure", "infragram"} for component in library["components"])
        == load_sidebar_catalog("azure").component_count
    )
    assert 'data-library-render-mode="lazy"' in html
    assert 'viewBox="0 0 960 600"' in html
    assert "data-infragram-diagram" in html
    assert "data-graph-layer" in html
    assert 'data-editor-action="undo"' in html
    assert 'data-editor-action="redo"' in html
    assert 'data-editor-action="delete"' in html
    assert 'data-editor-action="zoom-in"' in html
    assert 'data-editor-action="zoom-out"' in html
    assert 'data-editor-action="zoom-fit"' in html
    assert "data-download-html" in html
    assert "data-editor-state" in html
    assert "window.infragramEditor" in html
    assert 'aria-labelledby="azure-api-title azure-api-desc"' in html
    assert '<title id="azure-api-title">Azure API</title>' in html
    assert (
        '<desc id="azure-api-desc">Client traffic flows through an API to storage.</desc>' in html
    )
    assert "<image" not in extract_svg(html)


def test_editor_state_embeds_initial_nodes_connections_and_icon_artwork() -> None:
    html = render_project_html(CloudProject.model_validate(project_payload()))
    match = re.search(
        r'<script type="application/json" id="infragram-editor-state"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL,
    )

    assert match is not None
    state = json.loads(match.group(1))
    assert state["schemaVersion"] == 3
    assert state["boundaries"] == []
    assert [node["id"] for node in state["nodes"]] == ["client", "api", "storage"]
    assert all(node["boundaryId"] is None for node in state["nodes"])
    assert len(state["edges"]) == 2
    assert state["edges"][0]["source"] == "client"
    assert state["edges"][0]["target"] == "api"
    assert state["nodes"][1]["x"] % 4 == 0
    assert state["nodes"][1]["y"] % 4 == 0


def test_sidebar_keeps_the_approved_category_order_and_embeds_icons() -> None:
    html = render_project_html(CloudProject.model_validate(project_payload()))
    expected = [
        "custom",
        "ai-machine-learning",
        "analytics",
        "compute",
        "containers",
        "databases",
        "devops",
        "hybrid-multicloud",
        "identity",
        "integration",
        "internet-of-things",
        "energy",
        "industrial",
        "facilities",
        "governance",
        "mobile",
        "networking",
        "power-platform",
        "security",
        "storage",
        "web",
    ]

    positions = [html.index(f'data-category-id="{category}"') for category in expected]

    assert positions == sorted(positions)
    assert 'src="data:image/svg+xml;base64,' in html
    qualified = {component["qualifiedId"] for component in embedded_library(html)["components"]}
    assert {"azure:application-gateways", "infragram:custom-annotation"} <= qualified
    assert 'data-category-id="power-platform"' in html


def test_sidebar_uses_real_inline_category_icons_and_a_colored_provider_mark() -> None:
    html = render_project_html(CloudProject.model_validate(project_payload()))
    expected = {
        "custom",
        "ai-machine-learning",
        "analytics",
        "compute",
        "containers",
        "databases",
        "devops",
        "hybrid-multicloud",
        "identity",
        "integration",
        "internet-of-things",
        "energy",
        "industrial",
        "facilities",
        "governance",
        "mobile",
        "networking",
        "power-platform",
        "security",
        "storage",
        "web",
    }

    assert html.count('class="category-icon"') == 21
    assert {value for value in re.findall(r'data-category-icon="([^"]+)"', html)} == expected
    assert html.count('md-expand-icon chevron-icon"') == 21
    assert '<span class="category-glyph"' not in html

    mark = re.search(r'<img class="provider-mark" src="data:image/svg\+xml;base64,([^"]+)"', html)
    assert mark is not None
    decoded = __import__("base64").b64decode(mark.group(1)).decode("utf-8")
    assert 'xmlns="http://www.w3.org/2000/svg"' in decoded
    assert "currentColor" not in decoded
    assert "#0078d4" in decoded
    assert 'viewBox="0 0 96 96"' in decoded
    assert "linearGradient" in decoded


def test_every_shipped_azure_icon_is_hash_tracked_artwork() -> None:
    icons = load_icon_set("azure")

    for slug in ("virtual-machine", "kubernetes-services", "sql-database", "virtual-networks"):
        icon = icons[slug]
        artwork = icon.path.read_text(encoding="utf-8")
        assert hashlib.sha256(icon.path.read_bytes()).hexdigest() == icon.sha256
        assert "<svg" in artwork and "viewBox" in artwork
        assert "<script" not in artwork.casefold()


def test_azure_sidebar_lists_every_reviewed_service_in_the_full_canonical_category_set() -> None:
    catalog = load_sidebar_catalog("azure")
    reviewed = load_icon_set("azure")
    html = render_project_html(CloudProject.model_validate(project_payload()))
    sidebar_ids = {
        component.id for category in catalog.categories for component in category.components
    }

    # the complete Azure Public Service Icons set, every one a service tile
    assert len(reviewed) == 715
    assert {icon.slug for icon in reviewed} <= sidebar_ids
    assert catalog.component_count > len(reviewed)
    assert all(
        component.mapping_status == "mapped"
        for category in catalog.categories
        for component in category.components
    )
    assert len(catalog.categories) == 21
    assert "Power Platform" in [category.label for category in catalog.categories]
    library = embedded_library(html)
    assert (
        sum(component["provider"] in {"azure", "infragram"} for component in library["components"])
        == catalog.component_count
    )
    assert 'data-provider-label="Azure Diagrams"' in html
    assert 'data-category-id="power-platform"' in html
    assert catalog.categories[17].id == "power-platform"
    assert catalog.categories[17].components != ()
    assert "No components in the selected libraries" in html
    assert sum(
        component["componentKind"] == "boundary" and component["provider"] in {"azure", "infragram"}
        for component in library["components"]
    ) == sum(
        component.component_kind == "boundary"
        for category in catalog.categories
        for component in category.components
    )
    assert {
        "custom-section",
        "custom-boundary-azure-tenant",
        "custom-boundary-azure-management-group",
        "custom-boundary-azure-subscription",
        "custom-boundary-azure-resource-group",
        "custom-boundary-azure-region",
        "custom-boundary-azure-zone",
        "custom-boundary-azure-vnet",
        "custom-boundary-azure-subnet",
        "custom-boundary-azure-aks",
    } <= sidebar_ids

    mark = re.search(r'<img class="provider-mark" src="data:image/svg\+xml;base64,([^"]+)"', html)
    assert mark is not None
    decoded = __import__("base64").b64decode(mark.group(1)).decode("utf-8")
    assert "#0078d4" in decoded


def test_cloud_categories_use_clear_semantic_icons_for_ai_governance_devops_and_containers() -> (
    None
):
    html = render_project_html(CloudProject.model_validate(project_payload()))

    assert 'data-category-icon="ai-machine-learning" data-category-icon-kind="brain"' in html
    assert 'data-category-icon="analytics" data-category-icon-kind="bar-chart"' in html
    assert 'data-category-icon="governance" data-category-icon-kind="governance-scale"' in html
    assert 'data-category-icon="devops" data-category-icon-kind="ci-cd"' in html
    assert 'data-category-icon="containers" data-category-icon-kind="github-container"' in html
    assert '<path d="M15.5 13a3.5 3.5 0 0 0-3.5 3.5v1a3.5 3.5 0 0 0 7 0v-1.8"/>' in html
    assert '<path d="M9 12l-3-6l-3 6a3 3 0 0 0 6 0"/>' in html
    assert '<path d="M9.828 9.172a4 4 0 1 0 0 5.656' in html
    assert (
        '<path fill="currentColor" stroke="none" d="M13.152.682a2.251 2.251 0 0 1 2.269 0' in html
    )
    assert '<path d="M9.5 4.5A3.5 3.5 0 0 0 6 8v.7' not in html
    assert '<path d="M5 4v16M5 7h8' not in html
    assert '<path d="M3 7l6 5-6 5V7' not in html
    assert '<path d="M12 2l5 3v6l-5 3' not in html
    assert ".category>summary:hover .category-icon" in html
    # an open category takes Material's active indicator, not a tinted glyph
    assert ".category[open]>summary{background:var(--md-sys-color-surface-container-high)" in html


@pytest.mark.parametrize("provider", ["azure", "kubernetes"])
def test_every_infrastructure_provider_uses_the_shared_workspace_theme(
    provider: str,
) -> None:
    payload = project_payload()
    payload["provider"] = provider
    payload["topology"] = {
        "id": "root",
        "name": "Infrastructure",
        "type": "group",
        "children": [
            {"id": "client", "name": "Client", "type": "client"},
            {"id": "service", "name": "Service", "type": "service"},
        ],
    }

    html = render_project_html(CloudProject.model_validate(payload))

    # Diagrams are only ever seen on white, so the workspace opens light.
    # Both palettes still ship: the toggle and ?theme= switch between them.
    assert '<body data-workspace-theme="light">' in html
    # the chrome's roles: dark on :root, light on the body (Plane's palette)
    assert "--md-sys-color-surface-container-low:#0E0F10" in html
    assert "--md-sys-color-surface-container-low:#F4F5F5" in html
    assert "--md-sys-color-primary-container:#006399" in html
    assert "--canvas-bg:#141414" in html
    assert "--diagram-surface:#141414" in html
    assert "data-theme-toggle" in html
    assert 'aria-label="Theme: Light"' in html
    assert 'aria-label="Infrastructure components"' in html


def test_sidebar_collapses_to_an_icon_rail_and_previews_from_the_provider_logo() -> None:
    html = render_project_html(CloudProject.model_validate(project_payload()))

    assert 'id="provider-sidebar"' in html
    assert 'class="md-nav-item provider-brand"' in html
    assert "data-sidebar-logo-trigger" in html
    assert 'aria-controls="provider-sidebar"' in html
    assert 'aria-expanded="true"' in html
    assert 'class="provider-name"' in html
    assert 'class="sidebar-state-icon" data-sidebar-control-icon' in html
    assert '<rect x="1.75" y="2.25" width="12.5" height="11.5" rx="2"/>' in html
    assert '<path d="M5.75 2.25v11.5"/>' in html
    assert '<path d="M10 3L5 8l5 5"/>' not in html
    assert "body.sidebar-collapsed .workspace{grid-template-columns:56px minmax(0,1fr)}" in html
    assert "body.sidebar-collapsed.sidebar-preview .provider-sidebar" in html
    assert "sidebarLogoTrigger.addEventListener('pointerenter'" in html
    assert "sidebar.addEventListener('pointerleave'" in html
    assert "data-sidebar-toggle" not in html
    assert 'class="document-title"' not in html


def test_sidebar_hides_scrollbar_chrome_without_disabling_scrolling() -> None:
    html = render_project_html(CloudProject.model_validate(project_payload()))

    assert "--canvas-bg:#141414" in html
    assert (
        "flex-direction:column;border-right:1px solid var(--md-sys-color-outline-variant);background:var(--md-sys-color-surface-container-low)"
        in html
    )
    assert (
        ".editor-main{position:relative;display:grid;grid-template-rows:auto minmax(0,1fr) auto;min-width:0"
        in html
    )
    assert "background-color:var(--canvas-bg)" in html
    assert ".category-list{min-height:0;overflow:auto" in html
    assert "scrollbar-width:none" in html
    assert ".category-list::-webkit-scrollbar{width:0;height:0}" in html


def test_sidebar_component_icons_do_not_precede_the_export_diagram_svg() -> None:
    html = render_project_html(CloudProject.model_validate(project_payload()))
    svg = extract_svg(html)

    assert '<title id="azure-api-title">Azure API</title>' in svg
    assert "provider-sidebar" not in svg


def test_presentation_and_fit_presets_change_the_rendered_canvas() -> None:
    slide = project_payload()
    slide["presentation"]["size"] = "slide-16x9"
    slide_html = render_project_html(CloudProject.model_validate(slide))

    fitted = project_payload()
    fitted["presentation"]["size"] = "fit"
    fit_html = render_project_html(CloudProject.model_validate(fitted))

    assert 'viewBox="0 0 1280 720"' in slide_html
    assert 'font-size="16"' in slide_html
    assert 'viewBox="0 0 960 600"' not in fit_html


def test_fixed_preset_rejects_content_that_would_grow_the_canvas() -> None:
    payload = project_payload()
    payload["topology"]["children"] = [
        {"id": f"node-{index}", "name": f"Node {index}", "type": "service"} for index in range(6)
    ]

    with pytest.raises(ExportError, match="exceeds doc-inline"):
        render_project_html(CloudProject.model_validate(payload))


def test_provider_mark_clears_the_legend_footer() -> None:
    payload = project_payload()
    payload["presentation"]["size"] = "doc-wide"
    payload["presentation"]["legend"] = [["solid", "Request flow"]]

    html = render_project_html(CloudProject.model_validate(payload))
    mark = re.search(
        r"<!-- Brand mark -->\s*<svg data-brand-mark=\"\" x=\"\d+\" y=\"(\d+)\" "
        r"width=\"\d+\" height=\"(\d+)\"",
        html,
    )

    assert mark is not None
    mark_y, mark_height = (int(value) for value in mark.groups())
    legend_y = 720 - 84
    assert mark_y + mark_height <= legend_y - 12


def test_a_drawing_of_shared_parts_alone_carries_no_vendor_mark() -> None:
    """A homelab or another cloud's estate drawn from shared parts falls back
    to the first provider for its theme; the vendor's lockup there would
    credit a vendor the picture does not show."""
    from infragram.author import Diagram, Edge
    from infragram.nodes import infragram as shared
    from infragram.nodes.frames import generic

    with Diagram("Shared parts only", slug="shared-parts-only") as diagram:
        with generic.Cloud("Another cloud"):
            browser = shared.web.BrowserClient("Browser")
            edge = shared.networking.CDNEdge("Edge")
        browser >> Edge("HTTPS") >> edge
    project = diagram.to_project()
    drawn = re.compile(r"<svg data-brand-mark=")

    assert not drawn.search(render_project_html(project))
    assert not drawn.search(render_project_svg(project))
    # a drawing that names its provider with plain cards keeps the mark
    assert drawn.search(render_project_html(CloudProject.model_validate(project_payload())))


def test_frame_lines_weigh_every_frame_alike_in_every_export() -> None:
    """``presentation.frame_lines`` multiplies each frame's own width: the
    static picture, the editor page's state and draw.io all draw it."""
    from infragram.builders.scene import FRAME_LINES
    from infragram.exports.drawio import render_project_drawio

    border = re.compile(
        r'rx="[\d.]+" fill="[^"]*"/>\s*<path d="[^"]*" fill="none" stroke="[^"]*" '
        r'stroke-width="([\d.]+)"'
    )
    template = Path(__file__).parents[2] / "skills/infragram-azure/assets/templates/cloud"
    thin = CloudProject.model_validate_json(
        (template / "azure-aks-baseline.infragram.json").read_text(encoding="utf-8")
    )
    thick = thin.model_copy(
        update={"presentation": thin.presentation.model_copy(update={"frame_lines": "thick"})}
    )
    widths = [float(width) for width in border.findall(render_project_svg(thin))]
    assert widths, "the picture draws its frames"
    assert [float(width) for width in border.findall(render_project_svg(thick))] == [
        pytest.approx(width * FRAME_LINES["thick"]) for width in widths
    ]
    assert '"frameLines":"thick"' in render_project_html(thick).replace(" ", "")
    drawio = re.compile(r"container=1;[^\"]*strokeWidth=([\d.]+);")
    assert [float(width) for width in drawio.findall(render_project_drawio(thick))] == [
        pytest.approx(float(width) * FRAME_LINES["thick"])
        for width in drawio.findall(render_project_drawio(thin))
    ]
    with pytest.raises(ValidationError):
        CloudProject.model_validate({**project_payload(), "presentation": {"frame_lines": "heavy"}})


def test_extract_svg_returns_only_the_first_diagram() -> None:
    html = '<main><svg viewBox="0 0 4 4"><title>A</title></svg><svg><title>B</title></svg></main>'

    assert extract_svg(html) == '<svg viewBox="0 0 4 4"><title>A</title></svg>'


def test_extract_svg_rejects_non_diagram_html() -> None:
    with pytest.raises(ExportError, match="does not contain an SVG"):
        extract_svg("<html><body>Nothing here</body></html>")


def test_standalone_svg_is_well_formed_accessible_xml() -> None:
    html = render_project_html(CloudProject.model_validate(project_payload()))

    svg = make_standalone_svg(html)
    root = ET.fromstring(svg)
    children = list(root)

    assert svg.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.attrib["viewBox"] == "0 0 960 600"
    assert children[0].tag == "{http://www.w3.org/2000/svg}title"
    assert "fonts.googleapis.com" not in svg, "the faces travel with the picture"
    assert svg.count("@font-face{font-family:'Inter'") == 2, "latin and latin-ext"
    assert "data:font/woff2;base64," in svg
    assert svg.count("<defs>") == 1


def test_standalone_svg_requires_a_viewbox() -> None:
    with pytest.raises(ExportError, match="viewBox"):
        make_standalone_svg("<svg><title>Missing frame</title></svg>")


def test_standalone_svg_adds_namespace_and_defs_without_moving_the_title() -> None:
    svg = make_standalone_svg(
        '<svg viewBox="0 0 40 40" role="img"><title id="x-title">X</title>'
        '<desc id="x-desc">Example.</desc><rect width="40" height="40"/></svg>'
    )
    root = ET.fromstring(svg)

    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert list(root)[0].tag == "{http://www.w3.org/2000/svg}title"
    assert svg.count("<defs>") == 1


def test_export_project_writes_template_html_and_svg_from_one_render(tmp_path: Path) -> None:
    project = CloudProject.model_validate(project_payload())

    result = export_project(
        project, tmp_path, formats=("template", "html", "svg"), renderer="static"
    )

    assert result.template == tmp_path / "azure-api.infragram.json"
    assert result.html == tmp_path / "azure-api.html"
    assert result.svg == tmp_path / "azure-api.svg"
    assert result.png is None
    assert result.template.is_file()
    assert result.html.is_file()
    assert ET.fromstring(result.svg.read_text(encoding="utf-8")).tag.endswith("svg")


def test_export_project_uses_an_injected_png_renderer(tmp_path: Path) -> None:
    calls: list[tuple[Path, Path, float]] = []

    def fake_renderer(source: Path, output: Path, scale: float) -> None:
        assert source.is_file(), "the HTML is staged before rendering begins"
        calls.append((source, output, scale))
        output.write_bytes(b"PNG")

    project = CloudProject.model_validate(project_payload())
    result = export_project(
        project,
        tmp_path,
        formats=("html", "png"),
        scale=3,
        png_renderer=fake_renderer,
    )

    assert result.png == tmp_path / "azure-api.png"
    assert result.png.read_bytes() == b"PNG"
    assert len(calls) == 1
    source, output, scale = calls[0]
    assert (source.name, output.name, scale) == ("azure-api.html", "azure-api.png", 3)
    assert source.parent == output.parent
    assert source.parent.parent == tmp_path and source.parent.name.startswith(".infragram-")
    assert not source.parent.exists(), "the staging folder is removed after the export commits"
    assert result.html == tmp_path / "azure-api.html" and result.html.is_file()


@pytest.mark.parametrize("scale", [0.5, 0, 4.1])
def test_export_project_rejects_unsafe_png_scales(tmp_path: Path, scale: float) -> None:
    project = CloudProject.model_validate(project_payload())

    with pytest.raises(ExportError, match="between 1 and 4"):
        export_project(project, tmp_path, formats=("png",), scale=scale)


def test_export_project_rejects_unknown_formats(tmp_path: Path) -> None:
    project = CloudProject.model_validate(project_payload())

    with pytest.raises(ExportError, match="unsupported export format"):
        export_project(project, tmp_path, formats=("psd",))


def test_export_project_requires_a_format(tmp_path: Path) -> None:
    project = CloudProject.model_validate(project_payload())

    with pytest.raises(ExportError, match="at least one"):
        export_project(project, tmp_path, formats=())


def test_export_project_protects_existing_artifacts(tmp_path: Path) -> None:
    project = CloudProject.model_validate(project_payload())
    first = export_project(project, tmp_path, formats=("html",))
    original = first.html.read_bytes()

    # A remembered artifact can be regenerated until somebody edits it.
    repeated = export_project(project, tmp_path, formats=("html",))
    assert repeated.html.read_bytes() == original
    repeated.html.write_bytes(original + b"<!-- user edit -->")

    with pytest.raises(ExportError, match="refusing to overwrite"):
        export_project(project, tmp_path, formats=("html",))
    assert repeated.html.read_bytes() == original + b"<!-- user edit -->"

    replaced = export_project(project, tmp_path, formats=("html",), overwrite=True)
    assert replaced.html == tmp_path / "azure-api.html"
    assert replaced.html.read_bytes() == original
