from __future__ import annotations

from infragram.catalog import ARCHITECTURE_BOUNDARY_SPECS
from infragram.catalog.components import (
    architecture_boundary_default_size,
    architecture_boundary_group,
    architecture_boundary_level,
)
from infragram.editor import load_sidebar_catalog

NEW_CORE_FRAMES = {
    "custom-boundary-environment": "environment",
    "custom-boundary-dmz": "dmz",
    "custom-boundary-hub-network": "hub",
    "custom-boundary-spoke-network": "spoke",
    "custom-boundary-management-network": "management",
    "custom-boundary-storage-fabric": "storage-fabric",
    "custom-boundary-campus": "campus",
    "custom-boundary-wiring-closet": "closet",
}


def test_new_core_frames_are_generic_and_ranked() -> None:
    specs = {spec[0]: spec for spec in ARCHITECTURE_BOUNDARY_SPECS}
    for frame_id, kind in NEW_CORE_FRAMES.items():
        assert frame_id in specs, frame_id
        assert specs[frame_id][3] == kind
        assert architecture_boundary_group(frame_id) == "generic"
        width, height = architecture_boundary_default_size(kind)
        assert width % 4 == 0 and height % 4 == 0
    # An environment wraps accounts' worth of resources; a DMZ is subnet-sized.
    assert architecture_boundary_level("environment") < architecture_boundary_level("hub")
    assert architecture_boundary_level("hub") == architecture_boundary_level("spoke")
    assert architecture_boundary_level("campus") < architecture_boundary_level("closet")
    assert architecture_boundary_level("dmz") == architecture_boundary_level("subnet-private")


def test_new_core_frames_ship_in_every_library_sidebar() -> None:
    for provider in ("azure", "kubernetes"):
        catalog = load_sidebar_catalog(provider)
        frames = {
            component.id: component
            for category in catalog.categories
            for component in category.components
            if component.provider_id == "infragram" and getattr(component, "frame_group", None)
        }
        for frame_id in NEW_CORE_FRAMES:
            assert frames[frame_id].frame_group == "generic", (provider, frame_id)
            assert frames[frame_id].icon_uri.startswith("data:image/svg+xml;base64,")
