from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from infragram.exports import render_project_html
from infragram.models.topology import Connection
from infragram.projects import CloudProject


def _project(direction: str | None) -> CloudProject:
    connection = {"target": "api", "kind": "dashed", "label": "sync"}
    if direction is not None:
        connection["direction"] = direction
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "single-cloud",
            "slug": "edge-direction",
            "title": "Edge direction",
            "description": "Connector style round trip.",
            "providers": [{"id": "azure"}],
            "default_library": "azure",
            "topology": {
                "id": "root",
                "name": "Edge direction",
                "type": "group",
                "children": [
                    {
                        "id": "primary",
                        "name": "Primary",
                        "type": "database",
                        "attributes": {"editor_x": 120, "editor_y": 180},
                        "connections": [connection],
                    },
                    {
                        "id": "api",
                        "name": "Replica",
                        "type": "database",
                        "attributes": {"editor_x": 520, "editor_y": 180},
                    },
                ],
            },
        }
    )


def _editor_edges(html: str) -> list[dict]:
    marker = '"edges":'
    start = html.find(marker)
    assert start >= 0, "editor state edges not found in the rendered page"
    edges, _ = json.JSONDecoder().raw_decode(html[start + len(marker) :].lstrip())
    return edges


def test_connection_direction_defaults_forward_and_rejects_unknown_values() -> None:
    assert Connection(target="x").direction == "forward"
    assert Connection(target="x", direction="both").direction == "both"
    assert Connection(target="x", direction="none").direction == "none"
    with pytest.raises(ValidationError):
        Connection(target="x", direction="backwards")


def test_editor_state_and_inspector_carry_connector_style() -> None:
    html = render_project_html(_project("both"))
    edges = _editor_edges(html)
    assert edges[0]["kind"] == "dashed"
    assert edges[0]["direction"] == "both"
    assert 'data-edge-style-control="kind"' in html
    assert 'data-edge-style-control="direction"' in html
    for option in ("solid", "dashed", "dotted", "forward", "both", "none"):
        assert f'<option value="{option}">' in html

    default_html = render_project_html(_project(None))
    assert _editor_edges(default_html)[0]["direction"] == "forward"


def test_direction_survives_a_project_round_trip() -> None:
    project = _project("none")
    dumped = project.model_dump(mode="json")
    again = CloudProject.model_validate(dumped)
    connection = again.topology.children[0].connections[0]
    assert connection.direction == "none"
    assert connection.kind == "dashed"
