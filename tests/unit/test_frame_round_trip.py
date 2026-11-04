"""Frames the editor saved with nothing inside them must reopen as frames."""

from __future__ import annotations

import base64
import json
import re

import pytest

from infragram.catalog import architecture_boundary_default_size
from infragram.catalog.components import architecture_boundary_level
from infragram.editor.shell import library_catalog_from_html
from infragram.exports import render_project_html
from infragram.models.topology import TopologyElement
from infragram.projects import CloudProject


def _json_script(html: str, element_id: str) -> dict:
    match = re.search(
        rf'<script type="application/json" id="{element_id}"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def _frame(
    element_id: str,
    kind: str,
    name: str,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    children: list[dict] | None = None,
    group: str = "azure",
) -> dict:
    # Exactly what the editor's exportProject() writes for a placed frame:
    # the kind as type, the saved geometry, the gallery it came from and its
    # resolved paint, and no component reference.
    return {
        "id": element_id,
        "name": name,
        "type": kind,
        "attributes": {
            "editor_x": x,
            "editor_y": y,
            "editor_width": width,
            "editor_height": height,
            "editor_frame_group": group,
            "editor_boundary_style": {"stroke": "#479ef5", "fill": "none", "tabbed": True},
        },
        "children": list(children or []),
    }


def _project(children: list[dict]) -> CloudProject:
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "single-cloud",
            "slug": "frames-only",
            "title": "Frames only",
            "description": "A frame stack with nothing placed inside it yet.",
            "providers": [{"id": "azure", "enabled": True}],
            "default_library": "azure",
            "presentation": {"size": "fit", "display": "card"},
            "topology": {
                "id": "root",
                "name": "Frames only",
                "type": "group",
                "children": children,
            },
        }
    )


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"children": [{"id": "web", "name": "Web", "type": "service"}]}, True),
        (
            {
                "component": {
                    "provider": "infragram",
                    "service_id": "custom-boundary-azure-vnet",
                    "icon_ref": "infragram:custom-boundary-azure-vnet",
                }
            },
            True,
        ),
        ({"attributes": {"editor_frame_group": "azure"}}, True),
        ({"attributes": {"editor_boundary_style": {"stroke": "#1490df"}}}, True),
        ({}, False),
        ({"attributes": {"editor_width": 400, "editor_height": 280}}, False),
    ],
)
def test_is_frame_reads_children_or_an_explicit_frame_signal(payload: dict, expected: bool) -> None:
    element = TopologyElement.model_validate(
        {"id": "vnet", "name": "VNet", "type": "network", **payload}
    )

    assert element.is_frame is expected


def test_an_empty_frame_stack_reopens_as_boundaries_not_cards() -> None:
    stack = _frame(
        "tenant",
        "organization",
        "Contoso tenant",
        x=704,
        y=564,
        width=592,
        height=472,
        children=[
            _frame(
                "subscription",
                "subscription",
                "Production",
                x=728,
                y=588,
                width=544,
                height=424,
                children=[
                    _frame(
                        "rg",
                        "resource-group",
                        "rg-prod",
                        x=752,
                        y=612,
                        width=496,
                        height=376,
                        children=[
                            _frame(
                                "vnet",
                                "network",
                                "vnet-prod",
                                x=776,
                                y=636,
                                width=448,
                                height=328,
                                children=[
                                    _frame(
                                        "snet-web",
                                        "subnet-private",
                                        "snet-web",
                                        x=872,
                                        y=728,
                                        width=256,
                                        height=144,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )

    state = _json_script(render_project_html(_project([stack])), "infragram-editor-state")

    assert state["nodes"] == []
    assert [boundary["id"] for boundary in state["boundaries"]] == [
        "tenant",
        "subscription",
        "rg",
        "vnet",
        "snet-web",
    ]
    innermost = state["boundaries"][-1]
    assert innermost["kind"] == "subnet-private"
    assert innermost["frameGroup"] == "azure"
    assert innermost["parentId"] == "vnet"
    assert (innermost["x"], innermost["y"], innermost["width"], innermost["height"]) == (
        872,
        728,
        256,
        144,
    )


def test_an_empty_frame_without_a_saved_size_takes_its_kind_default() -> None:
    frame = {
        "id": "vnet",
        "name": "VNet",
        "type": "network",
        "attributes": {"editor_frame_group": "azure"},
    }

    state = _json_script(render_project_html(_project([frame])), "infragram-editor-state")

    assert state["nodes"] == []
    (boundary,) = state["boundaries"]
    assert (boundary["width"], boundary["height"]) == architecture_boundary_default_size("network")


def test_a_platform_library_project_exports_its_frames() -> None:
    # A Kubernetes-only project: the platform library's frames render on
    # their own, with nothing from a cloud library around them.
    project = CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "platform",
            "slug": "kubernetes-frames",
            "title": "Kubernetes frames",
            "description": "One empty namespace frame from the platform library.",
            "providers": [{"id": "kubernetes", "enabled": True}],
            "default_library": "kubernetes",
            "presentation": {"size": "fit"},
            "topology": {
                "id": "root",
                "name": "Frames",
                "type": "group",
                "children": [
                    {
                        "id": "payments",
                        "name": "payments",
                        "type": "namespace",
                        "attributes": {"editor_frame_group": "kubernetes"},
                    }
                ],
            },
        }
    )

    state = _json_script(render_project_html(project), "infragram-editor-state")

    assert [boundary["id"] for boundary in state["boundaries"]] == ["payments"]
    assert state["nodes"] == []
    (frame,) = state["boundaries"]
    assert frame["frameGroup"] == "kubernetes"
    assert frame["stroke"] == "#326ce5"


def test_official_azure_badges_keep_their_artwork_on_the_tab() -> None:
    html = render_project_html(
        _project(
            [
                _frame(
                    "subscription",
                    "subscription",
                    "Production",
                    x=100,
                    y=100,
                    width=400,
                    height=280,
                )
            ]
        )
    )
    library = library_catalog_from_html(html)
    frames = {
        component["serviceId"]: component
        for component in library["components"]
        if component.get("componentKind") == "boundary"
    }

    for service_id in (
        "custom-boundary-azure-subscription",
        "custom-boundary-azure-resource-group",
        "custom-boundary-azure-vnet",
        "custom-boundary-azure-subnet",
    ):
        uri = frames[service_id]["boundaryStyle"]["iconUri"]
        svg = base64.b64decode(uri.split(",", 1)[1]).decode("utf-8")
        # Azure's badges are the deck's own full-colour icons on a paper tab:
        # real artwork, never a blank plate.
        assert "<path" in svg or "<polygon" in svg, service_id
        assert frames[service_id]["boundaryStyle"]["tabFill"].casefold() == "#ffffff", service_id


def test_public_and_private_subnet_glyphs_differ() -> None:
    html = render_project_html(
        _project(
            [
                _frame(
                    "subscription",
                    "subscription",
                    "Production",
                    x=100,
                    y=100,
                    width=400,
                    height=280,
                )
            ]
        )
    )
    library = library_catalog_from_html(html)
    icons = {
        component["serviceId"]: component["boundaryStyle"]["iconUri"]
        for component in library["components"]
        if component.get("componentKind") == "boundary" and component.get("boundaryStyle")
    }

    assert (
        icons["custom-boundary-public-subnet-generic"]
        != icons["custom-boundary-private-subnet-generic"]
    )


def test_a_team_sits_above_the_projects_it_owns() -> None:
    assert architecture_boundary_level("team") < architecture_boundary_level("project")


def test_a_core_frame_keeps_the_gallery_look_inside_a_provider_project() -> None:
    # The core frames belong to no library. A frame placed from that gallery
    # into an Azure project must still draw as the catalog shows it: tabbed,
    # with the kind's glyph, in the neutral grey, captions as written --
    # not in Azure's blue.
    project = CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "single-cloud",
            "slug": "core-frames",
            "title": "Core frames",
            "description": "One datacenter frame from the core gallery.",
            "providers": [{"id": "azure", "enabled": True}],
            "default_library": "azure",
            "presentation": {"size": "fit"},
            "topology": {
                "id": "root",
                "name": "Core frames",
                "type": "group",
                "children": [
                    {
                        "id": "dc",
                        "name": "Corporate datacenter",
                        "type": "site",
                        "attributes": {"editor_frame_group": "generic"},
                    }
                ],
            },
        }
    )

    state = _json_script(render_project_html(project), "infragram-editor-state")

    (frame,) = state["boundaries"]
    assert frame["tabbed"] is True
    assert frame["iconUri"].startswith("data:image/svg+xml")
    assert frame["labelCase"] == "preserve"
    assert frame["labelFont"] == "sans"
    assert frame["stroke"] == "#bdbdbd"
    assert frame["frameGroup"] == "generic"


def test_a_saved_card_size_reopens_at_that_size() -> None:
    web = {
        "id": "appgw",
        "name": "Application Gateway",
        "type": "service",
        "attributes": {
            "editor_x": 528,
            "editor_y": 332,
            "editor_card_size": {"width": 288, "height": 72},
        },
    }

    state = _json_script(render_project_html(_project([web])), "infragram-editor-state")

    (card,) = state["nodes"]
    assert (card["width"], card["height"]) == (288, 72)
    assert card["cardSize"] == {"width": 288, "height": 72}


def test_a_connection_to_an_empty_frame_is_refused_not_dropped() -> None:
    web = {
        "id": "web",
        "name": "Web",
        "type": "service",
        "attributes": {"editor_x": 120, "editor_y": 120},
        "connections": [{"target": "vnet", "kind": "solid", "label": "PEERS"}],
    }
    frame = _frame("vnet", "network", "VNet", x=400, y=80, width=400, height=280)

    # An empty frame has nothing to seat a wire on. The link used to be
    # dropped without a word; the document is refused with the reason now,
    # since a silently missing wire loses a fact the author stated.
    with pytest.raises(ValueError, match="nothing drawn"):
        render_project_html(_project([web, frame]))
