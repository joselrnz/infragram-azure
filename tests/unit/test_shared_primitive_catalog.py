from __future__ import annotations

import base64

from infragram.catalog import (
    ARCHITECTURE_BOUNDARY_GROUPS,
    SHARED_PRIMITIVE_SPECS,
    load_composite_catalog,
    load_default_provider_registry,
)
from infragram.catalog.components import BRAND_SILHOUETTE_INK, PRIMITIVE_INK
from infragram.editor import load_sidebar_catalog


def _component_map(provider: str, owner: str) -> dict[str, object]:
    catalog = load_sidebar_catalog(provider)
    return {
        component.id: component
        for category in catalog.categories
        for component in category.components
        if component.provider_id == owner
    }


def test_shared_primitive_library_exposes_every_shipped_architecture_icon() -> None:
    # A pinned count, so adding or losing a primitive is a decision somebody
    # made rather than a drift nobody noticed.
    assert len(SHARED_PRIMITIVE_SPECS) == 367
    assert {
        "public-users",
        "browser-client",
        "mobile-client",
        "desktop-client",
        "physical-server",
        "virtual-machine",
        "public-internet",
        "cdn-edge",
        "network-gateway",
        "message-queue",
        "backup-recovery",
        "kubernetes-pod",
        "api-endpoint",
        "ci-cd-pipeline",
        "monitoring",
        "brand-docker",
        "brand-postgres",
        "data-airflow",
        "data-power-bi",
        "language-python",
        "statistics-qgis",
        "format-excel",
        "brand-valkey",
        "brand-redpanda",
    } <= {spec.service_id for spec in SHARED_PRIMITIVE_SPECS}


def test_shared_primitives_are_categorized_and_embedded_in_every_sidebar() -> None:
    for provider in ("azure", "kubernetes"):
        components = _component_map(provider, "infragram")
        for spec in SHARED_PRIMITIVE_SPECS:
            component = components[spec.service_id]
            assert component.category_id == spec.category_id
            assert component.icon_uri.startswith("data:image/svg+xml;base64,")
            decoded = base64.b64decode(component.icon_uri.partition(",")[2])
            assert b"<svg" in decoded
            if not spec.icon_id.startswith("logo:"):
                assert b"currentColor" not in decoded
                # A hairline pictogram takes the Azure accent; a filled brand
                # silhouette is somebody else's mark and keeps the neutral ink.
                root = decoded[: decoded.index(b">") + 1]
                stroked = b'fill="none"' in root and b"stroke=" in root
                expected = PRIMITIVE_INK if stroked else BRAND_SILHOUETTE_INK
                assert expected.encode() in decoded, spec.service_id

        assert components["public-users"].category_id == "identity"
        assert components["browser-client"].category_id == "web"
        assert components["mobile-client"].category_id == "mobile"
        assert components["physical-server"].category_id == "compute"
        assert components["firewall"].category_id == "security"


def test_shared_primitives_are_deduplicated_in_hybrid_catalogs() -> None:
    catalog = load_composite_catalog(("azure", "kubernetes"))
    qualified_ids = [component.qualified_id for component in catalog.components]

    assert qualified_ids.count("infragram:public-users") == 1
    assert qualified_ids.count("infragram:browser-client") == 1
    assert catalog.search("public users")[0].qualified_id == "infragram:public-users"
    assert catalog.search("browser client")[0].qualified_id == "infragram:browser-client"


def test_the_three_installed_libraries_are_what_the_edition_ships() -> None:
    registry = load_default_provider_registry()
    assert tuple(provider.id for provider in registry.providers) == (
        "azure",
        "kubernetes",
        "databricks",
    )

    azure = registry["azure"]
    assert azure.display_name == "Azure" and azure.kind == "cloud" and azure.coverage == "full"

    kubernetes = registry["kubernetes"]
    assert kubernetes.display_name == "Kubernetes"
    assert kubernetes.short_name == "K8S"
    assert kubernetes.kind == "platform"
    assert kubernetes.coverage == "reviewed"


def test_each_installed_library_has_its_own_frame_group_beside_the_core_frames() -> None:
    assert ARCHITECTURE_BOUNDARY_GROUPS == (
        ("generic", "Core frames"),
        ("azure", "Azure"),
        ("kubernetes", "Kubernetes"),
        ("databricks", "Databricks"),
    )
    frames = _component_map("kubernetes", "infragram")
    by_group: dict[str, set[str]] = {}
    for component in frames.values():
        if component.component_kind == "boundary":
            by_group.setdefault(component.frame_group, set()).add(component.id)

    assert {
        "custom-boundary-kubernetes-cluster",
        "custom-boundary-kubernetes-namespace",
        "custom-boundary-kubernetes-node-pool",
        "custom-boundary-kubernetes-workload",
    } == by_group["kubernetes"]
    assert {
        "custom-boundary-azure-tenant",
        "custom-boundary-azure-subscription",
        "custom-boundary-azure-vnet",
        "custom-boundary-azure-aks",
    } <= by_group["azure"]
    assert {
        "custom-boundary-dmz",
        "custom-boundary-environment",
        "custom-boundary-cloud",
    } <= by_group["generic"]
    assert {
        "custom-boundary-databricks-account",
        "custom-boundary-databricks-workspace",
        "custom-boundary-databricks-compute",
        "custom-boundary-databricks-unity-catalog",
    } == by_group["databricks"]
