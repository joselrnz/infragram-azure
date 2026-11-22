"""A frame's badges carry tables, and any card or frame carries addresses.

The motivating case is a subnet: its NSG badge holds the security group's
rules, its route table badge the user-defined routes, and the subnet itself
says which address its router answers on. Nothing of it is drawn; the editor
shows the rules and routes when a badge (or the frame, or the VNet around it)
is clicked, and the addresses on hover and in the right-click menu.
"""

from __future__ import annotations

import json
import re
import sys

import pytest

from infragram.author import Diagram
from infragram.discovery.azure import (
    NSG_COLUMNS,
    ROUTE_COLUMNS,
    _subnet_router,
    nsg_rules_table,
    route_table_rows,
)
from infragram.exports import render_project_html, render_project_svg
from infragram.models.topology import Badge
from infragram.nodes.azure import networking as net
from infragram.nodes.frames import azure as az
from infragram.paths import skill_assets

ROUTES = [
    ("default-via-firewall", "0.0.0.0/0", "VirtualAppliance", "10.100.0.68"),
    ("onprem-via-firewall", "10.0.0.0/8", "VirtualAppliance", "10.100.0.68"),
]
RULES = [
    (
        "200",
        "allow-onprem-sql",
        "Outbound",
        "Allow",
        "TCP",
        "VirtualNetwork",
        "*",
        "10.20.4.15",
        "1433",
    ),
    (
        "100",
        "worker-to-worker",
        "Inbound",
        "Allow",
        "*",
        "VirtualNetwork",
        "*",
        "VirtualNetwork",
        "*",
    ),
]


def _diagram() -> Diagram:
    with Diagram(
        "Spoke", "One subnet with an NSG and a UDR.", slug="spoke", providers=("azure",)
    ) as diagram:
        with az.VNet("vnet-spoke · 10.1.0.0/16"):
            with (
                az.Subnet("snet-app · 10.1.2.0/24")
                .badge(net.NetworkSecurityGroups, label="nsg-app", table=(NSG_COLUMNS, RULES))
                .badge(net.RouteTables, label="rt-app", table=(ROUTE_COLUMNS, ROUTES))
                .addresses(router="10.1.2.1")
            ):
                net.Firewalls("Azure Firewall").addresses(private="10.100.0.68")
    return diagram


def _subnet(diagram: Diagram):
    (vnet,) = diagram.roots
    return vnet.children[0]


def _editor_state(html: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="infragram-editor-state"[^>]*>(.*?)</script>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def test_a_badge_keeps_its_rows_exactly_as_written() -> None:
    nsg, routes = _subnet(_diagram()).badges
    assert nsg.table == {"columns": list(NSG_COLUMNS), "rows": [list(row) for row in RULES]}
    # in the order given, not sorted by priority
    assert [row[0] for row in nsg.table["rows"]] == ["200", "100"]
    assert routes.table["rows"][0] == list(ROUTES[0])


def test_a_badge_without_a_table_writes_none() -> None:
    """Documents saved before badges carried tables read and write the same."""
    assert "table" not in Badge(icon="route-tables", label="rt").model_dump()
    assert "table" in Badge(icon="route-tables", table={"columns": ["A"], "rows": []}).model_dump()


def test_the_document_round_trips_the_badge_tables_and_addresses() -> None:
    project = _diagram().to_project()
    text = project.model_dump_json()
    again = type(project).model_validate_json(text)
    subnet = again.topology.children[0].children[0]
    assert subnet.badges[1].table["rows"] == [list(row) for row in ROUTES]
    assert subnet.attributes["addresses"] == [["Router", "10.1.2.1"]]


def test_a_badge_table_is_refused_when_a_row_is_wider_than_its_columns() -> None:
    with pytest.raises(ValueError, match="more cells than"):
        az.Subnet("snet").badge(net.RouteTables, label="rt", table=(("Prefix",), [("a", "b")]))
    with pytest.raises(ValueError, match=r"table= takes \(columns, rows\)"):
        az.Subnet("snet").badge(net.RouteTables, label="rt", table="routes")


def test_a_frame_takes_a_table_of_its_own() -> None:
    frame = az.Subnet("snet-app").table(
        ("Property", "Value"), [("Delegation", "Microsoft.Databricks")]
    )
    assert frame.attributes["table"]["rows"] == [["Delegation", "Microsoft.Databricks"]]


def test_addresses_take_keywords_and_pairs_in_order() -> None:
    card = net.Firewalls("fw").addresses(private="10.0.0.4", public_ip="20.1.2.3")
    card.addresses(("BGP peer", "169.254.0.1"), private="10.0.0.5")
    assert card.attributes["addresses"] == [
        ["Private", "10.0.0.5"],
        ["Public ip", "20.1.2.3"],
        ["BGP peer", "169.254.0.1"],
    ]
    with pytest.raises(ValueError, match="needs a label and a value"):
        net.Firewalls("fw").addresses(private=" ")


def test_the_editor_page_receives_the_badge_tables_and_addresses() -> None:
    state = _editor_state(render_project_html(_diagram().to_project()))
    subnet = next(item for item in state["boundaries"] if item["name"].startswith("snet-app"))
    assert [badge["label"] for badge in subnet["badges"]] == ["nsg-app", "rt-app"]
    assert subnet["badges"][1]["table"]["rows"] == [list(row) for row in ROUTES]
    assert subnet["attributes"]["addresses"] == [["Router", "10.1.2.1"]]
    firewall = next(item for item in state["nodes"] if item["name"] == "Azure Firewall")
    assert firewall["attributes"]["addresses"] == [["Private", "10.100.0.68"]]


def test_nothing_of_the_tables_or_addresses_is_drawn() -> None:
    svg = render_project_svg(_diagram().to_project())
    for text in ("default-via-firewall", "VirtualAppliance", "allow-onprem-sql", "10.1.2.1"):
        assert text not in svg


def test_the_file_checker_reads_badge_tables() -> None:
    sys.path.insert(0, str(skill_assets().parent / "scripts"))
    try:
        import project_check
    finally:
        sys.path.pop(0)
    document = json.loads(_diagram().to_project().model_dump_json())
    errors: list[str] = []
    project_check.check_project(document, errors)
    assert not [error for error in errors if "badges" in error]
    badge = document["topology"]["children"][0]["children"][0]["badges"][1]
    badge["table"]["rows"].append(["a", "b", "c", "d", "e"])
    errors = []
    project_check.check_project(document, errors)
    assert any("wider than its columns" in error for error in errors)


# -- Azure discovery ---------------------------------------------------------

NSG = {
    "type": "microsoft.network/networksecuritygroups",
    "properties": {
        "securityRules": [
            {
                "name": "allow-https",
                "properties": {
                    "priority": 300,
                    "direction": "Inbound",
                    "access": "Allow",
                    "protocol": "Tcp",
                    "sourceAddressPrefix": "Internet",
                    "sourcePortRange": "*",
                    "destinationAddressPrefixes": ["10.1.2.4", "10.1.2.5"],
                    "destinationPortRanges": ["443", "8443"],
                },
            },
            {
                "name": "from-web-asg",
                "properties": {
                    "priority": 100,
                    "direction": "Inbound",
                    "access": "Allow",
                    "protocol": "*",
                    "sourceApplicationSecurityGroups": [
                        {
                            "id": "/subscriptions/s/resourceGroups/g/providers/x/applicationSecurityGroups/asg-web"
                        }
                    ],
                    "sourcePortRange": "*",
                    "destinationAddressPrefix": "*",
                    "destinationPortRange": "1433",
                },
            },
        ],
        "defaultSecurityRules": [
            {
                "name": "DenyAllInBound",
                "properties": {
                    "priority": 65500,
                    "direction": "Inbound",
                    "access": "Deny",
                    "protocol": "*",
                    "sourceAddressPrefix": "*",
                    "sourcePortRange": "*",
                    "destinationAddressPrefix": "*",
                    "destinationPortRange": "*",
                },
            }
        ],
    },
}


def test_an_imported_nsg_lists_its_rules_as_arm_holds_them() -> None:
    columns, rows = nsg_rules_table(NSG)
    assert columns == NSG_COLUMNS
    assert rows == [
        [
            "300",
            "allow-https",
            "Inbound",
            "Allow",
            "Tcp",
            "Internet",
            "*",
            "10.1.2.4, 10.1.2.5",
            "443, 8443",
        ],
        ["100", "from-web-asg", "Inbound", "Allow", "*", "asg-web", "*", "*", "1433"],
        ["65500", "DenyAllInBound", "Inbound", "Deny", "*", "*", "*", "*", "*"],
    ]


def test_an_imported_route_table_lists_its_routes_as_written() -> None:
    table = {
        "type": "microsoft.network/routetables",
        "properties": {
            "routes": [
                {
                    "name": "to-fw",
                    "properties": {
                        "addressPrefix": "0.0.0.0/0",
                        "nextHopType": "VirtualAppliance",
                        "nextHopIpAddress": "10.0.1.4",
                    },
                },
                {
                    "name": "local",
                    "properties": {"addressPrefix": "10.1.0.0/16", "nextHopType": "VnetLocal"},
                },
            ]
        },
    }
    assert route_table_rows(table) == (
        ROUTE_COLUMNS,
        [
            ["to-fw", "0.0.0.0/0", "VirtualAppliance", "10.0.1.4"],
            ["local", "10.1.0.0/16", "VnetLocal", ""],
        ],
    )


@pytest.mark.parametrize(
    ("prefix", "router"),
    [
        ("10.1.2.0/24", "10.1.2.1"),
        ("10.100.0.64/26", "10.100.0.65"),
        ("10.0.0.0/16, fd00::/64", "10.0.0.1"),
        ("fd00::/64", ""),
        ("", ""),
        ("not a prefix", ""),
    ],
)
def test_a_subnets_router_is_its_first_host_address(prefix: str, router: str) -> None:
    assert _subnet_router(prefix) == router
