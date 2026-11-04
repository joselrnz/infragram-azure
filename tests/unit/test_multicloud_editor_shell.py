from __future__ import annotations

from html.parser import HTMLParser

from infragram.catalog import load_default_provider_registry
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
                },
                {
                    "id": "provider:kubernetes",
                    "name": "Kubernetes",
                    "kind": "provider",
                    "provider": "kubernetes",
                },
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
                        "connections": [{"target": "worker", "kind": "solid", "label": "HTTPS"}],
                    },
                    {
                        "id": "worker",
                        "name": "Worker",
                        "type": "service",
                        "component": {"provider": "kubernetes", "service_id": "deploy"},
                        "layer_id": "provider:kubernetes",
                        "connections": [
                            {"target": "database", "kind": "dashed", "label": "EVENTS"}
                        ],
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


def _library_payload(html: str) -> dict:
    return library_catalog_from_html(html)


def _elements(html: str, tag: str) -> list[dict[str, str | None]]:
    """Read tag attributes without depending on their order or whitespace."""

    class Elements(HTMLParser):
        found: list[dict[str, str | None]]

        def __init__(self):
            super().__init__()
            self.found = []

        def handle_starttag(self, name, attrs):
            if name == tag:
                self.found.append(dict(attrs))

    parser = Elements()
    parser.feed(html)
    return parser.found


def test_a_hybrid_workspace_is_branded_by_its_cloud_library() -> None:
    # A cloud-plus-platform workspace keeps the cloud's own brand: the
    # neutral multicloud mark is for two clouds, and this edition ships one.
    html = render_project_html(hybrid_project())

    assert 'data-provider-label="Azure Diagrams"' in html
    assert 'data-multicloud-mark="true"' not in html
    assert "<!-- Brand mark -->" in html


def test_provider_library_selector_lists_every_registered_library_and_coverage() -> None:
    # the full workspace export embeds every installed library so the menu can add any
    html = render_project_html(hybrid_project(), libraries="all")

    assert "data-provider-menu-trigger" in html
    # three libraries give a real choice, so the selector shows, naming the two the page selects
    selector = next(
        item
        for item in _elements(html, "section")
        if "provider-selector" in (item.get("class") or "").split()
    )
    assert selector["aria-label"] == "Provider libraries"
    assert "Libraries · <strong data-provider-summary>Azure + K8S</strong>" in html
    assert '<p class="md-menu__header provider-group-label">Cloud providers</p>' in html
    assert '<p class="md-menu__header provider-group-label">Platforms</p>' in html
    registered = load_default_provider_registry().providers
    assert html.count('data-provider-option="') == len(registered) == 3
    options = {
        item["data-provider-option"]: item
        for item in _elements(html, "input")
        if "data-provider-option" in item
    }
    assert set(options) == {"azure", "kubernetes", "databricks"}
    assert "checked" in options["azure"] and "checked" in options["kubernetes"]
    assert "checked" not in options["databricks"]
    # one full library and one reviewed one; no preview ships
    assert 'data-coverage="reviewed"' in html and 'data-coverage="full"' in html
    assert 'data-coverage="preview"' not in html
    quick = {
        item["data-provider-quick-filter"]: item
        for item in _elements(html, "button")
        if "data-provider-quick-filter" in item
    }
    assert quick["azure"]["aria-pressed"] == "true"
    assert quick["kubernetes"]["aria-pressed"] == "true"
    assert "data-provider-apply" in html


def test_offline_library_payload_uses_qualified_ids_and_shared_custom_once() -> None:
    payload = _library_payload(render_project_html(hybrid_project(), libraries="all"))

    assert tuple(provider["id"] for provider in payload["providers"]) == tuple(
        provider.id for provider in load_default_provider_registry().providers
    )
    components = payload["components"]
    qualified = [component["qualifiedId"] for component in components]
    assert "azure:virtual-machine" in qualified
    assert "kubernetes:deploy" in qualified
    assert "kubernetes:kubernetes" in qualified
    assert qualified.count("infragram:custom-annotation") == 1
    assert all(":" in component["qualifiedId"] for component in components)
    assert all(component["iconUri"].startswith("data:image/svg+xml;") for component in components)


def test_sidebar_defers_component_cards_until_a_category_or_search_is_opened() -> None:
    html = render_project_html(hybrid_project())

    assert 'data-library-render-mode="lazy"' in html
    assert 'data-component-list="custom"' in html
    shell = html.split(
        '<script type="application/octet-stream" id="infragram-library-catalog"', maxsplit=1
    )[0]
    assert 'class="component-card" draggable="true"' not in shell
    assert "renderVisibleCatalog" in html
    assert "providerSelection" in html


def test_provider_filter_runtime_keeps_canvas_visibility_separate_from_library_scope() -> None:
    html = render_project_html(hybrid_project())

    assert "applyProviderSelection" in html
    assert "renderVisibleCatalog" in html
    assert (
        "state.nodes = state.nodes.filter"
        not in html.split("const applyProviderSelection", maxsplit=1)[1].split("};", maxsplit=1)[0]
    )
    assert (
        "state.boundaries = state.boundaries.filter"
        not in html.split("const applyProviderSelection", maxsplit=1)[1].split("};", maxsplit=1)[0]
    )
