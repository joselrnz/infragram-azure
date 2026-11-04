"""An element can carry a table the editor shows in a popup when it is selected.

The motivating case is a route table: the card on the canvas stays the
vendor's route-table card, and clicking it opens its routes beside it. Nothing
about the table is drawn, so the picture and every export are unchanged.
"""

from __future__ import annotations

import json
import re

import pytest

from infragram.author import Diagram
from infragram.exports import render_project_html, render_project_svg
from infragram.nodes.azure import networking as net
from infragram.nodes.frames import azure as az

COLUMNS = ("Prefix", "Next hop type", "Next hop")
ROUTES = [
    ("0.0.0.0/0", "Virtual appliance", "10.0.1.4"),
    ("10.0.0.0/16", "VNet peering", "hub-vnet"),
    ("10.1.0.0/16", "VNet local", "-"),
]


def _diagram(rows=ROUTES) -> Diagram:
    with Diagram("Routes", "One route table.", slug="routes", providers=("azure",)) as diagram:
        with az.VNet("spoke-prod"):
            net.RouteTables("rt-spoke-prod", "UDR").table(COLUMNS, rows)
    return diagram


def _editor_state(html: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="infragram-editor-state"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_the_table_rides_in_the_elements_attributes() -> None:
    (vnet,) = _diagram().roots
    (routes,) = vnet.children
    assert routes.attributes["table"] == {
        "columns": list(COLUMNS),
        "rows": [list(row) for row in ROUTES],
    }


def test_any_number_of_rows_is_the_same_call() -> None:
    many = [(f"10.{i}.0.0/16", "VNet peering", "hub-vnet") for i in range(40)]
    (vnet,) = _diagram(many).roots
    assert len(vnet.children[0].attributes["table"]["rows"]) == 40


def test_the_editor_page_receives_the_table_and_the_popup() -> None:
    html = render_project_html(_diagram().to_project())
    node = next(item for item in _editor_state(html)["nodes"] if item["name"] == "rt-spoke-prod")
    assert node["attributes"]["table"]["columns"] == list(COLUMNS)
    assert len(node["attributes"]["table"]["rows"]) == len(ROUTES)
    assert "data-canvas-popup" in html
    assert "syncElementPopup" in html


def test_nothing_about_the_table_is_drawn_in_the_picture() -> None:
    """The card stays a card: no route text lands in the static picture."""
    svg = render_project_svg(_diagram().to_project())
    assert "Next hop type" not in svg
    assert "Virtual appliance" not in svg


@pytest.mark.parametrize(
    ("columns", "rows", "message"),
    [
        ((), [], "at least one column"),
        (("Prefix",), [("10.0.0.0/16", "extra")], "more cells than"),
    ],
)
def test_a_malformed_table_fails_where_it_is_written(columns, rows, message) -> None:
    with Diagram("Bad", slug="bad", providers=("azure",)), pytest.raises(ValueError, match=message):
        net.RouteTables("rt-bad", "UDR").table(columns, rows)
