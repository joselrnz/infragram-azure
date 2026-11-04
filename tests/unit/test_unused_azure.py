"""What an Azure estate keeps without using, read from Resource Graph rows.

Each rule fires on what ARM states outright and stays quiet on a row that
merely leaves a property out, so a sparse snapshot never calls a resource
unused that is not.
"""

from __future__ import annotations

from typing import Any

import pytest

from infragram.discovery import ImportOptions, blueprint
from infragram.discovery.unused import empty_groups, find_unused
from infragram.pricing import price_project

SUB = "11111111-2222-3333-4444-555555555555"


def rid(kind: str, name: str, group: str = "rg-app") -> str:
    provider, _, rest = kind.partition("/")
    return f"/subscriptions/{SUB}/resourceGroups/{group}/providers/{provider}/{rest}/{name}"


def row(rtype: str, name: str, properties: dict[str, Any] | None = None, **extra) -> dict:
    return {
        "id": rid(rtype, name),
        "name": name,
        "type": rtype,
        "resourceGroup": "rg-app",
        "subscriptionId": SUB,
        "location": "eastus2",
        "properties": properties or {},
        **extra,
    }


def rules(*rows: dict) -> dict[str, str]:
    return {key.rsplit("/", 1)[-1]: found.rule for key, found in find_unused(rows).items()}


VM = "Microsoft.Compute/virtualMachines"
NIC = "Microsoft.Network/networkInterfaces"


@pytest.mark.parametrize(
    ("resource", "rule"),
    [
        (row("Microsoft.Compute/disks", "d1", {"diskState": "Unattached"}), "unattached-disk"),
        (
            row(
                "Microsoft.Network/publicIPAddresses", "ip1", {"publicIPAllocationMethod": "Static"}
            ),
            "unassociated-ip",
        ),
        (row("Microsoft.Network/networkSecurityGroups", "nsg1"), "unassociated-nsg"),
        (row("Microsoft.Network/routeTables", "rt1"), "unassociated-route-table"),
        (row("Microsoft.Network/natGateways", "nat1"), "idle-nat-gateway"),
        (
            row(
                "Microsoft.Network/loadBalancers",
                "lb1",
                {"backendAddressPools": [{"properties": {}}]},
                sku={"name": "Standard"},
            ),
            "empty-load-balancer",
        ),
        (
            row("Microsoft.Network/applicationGateways", "agw1", {"backendAddressPools": []}),
            "empty-application-gateway",
        ),
        (row("Microsoft.Web/serverFarms", "plan1", {"numberOfSites": 0}), "empty-plan"),
        (row("Microsoft.Web/sites", "app1", {"state": "Stopped"}), "stopped-app"),
        (
            row("Microsoft.Compute/availabilitySets", "as1", {"virtualMachines": []}),
            "empty-availability-set",
        ),
        (
            row(
                VM,
                "vm1",
                {"extended": {"instanceView": {"powerState": {"code": "PowerState/deallocated"}}}},
            ),
            "deallocated-vm",
        ),
        (
            row(
                VM,
                "vm2",
                {"extended": {"instanceView": {"powerState": {"code": "PowerState/stopped"}}}},
            ),
            "stopped-vm",
        ),
        (
            row("Microsoft.Network/virtualNetworkGateways", "vgw1", {"gatewayType": "Vpn"}),
            "idle-gateway",
        ),
        (
            row(
                "Microsoft.Network/privateDnsZones",
                "privatelink.blob",
                {"numberOfVirtualNetworkLinks": 0},
            ),
            "unlinked-dns-zone",
        ),
        (
            row(
                "Microsoft.Network/privateEndpoints",
                "pe1",
                {
                    "privateLinkServiceConnections": [
                        {
                            "properties": {
                                "privateLinkServiceConnectionState": {"status": "Disconnected"}
                            }
                        }
                    ]
                },
            ),
            "disconnected-endpoint",
        ),
        (row(NIC, "nic1", {"ipConfigurations": [{}]}), "detached-nic"),
    ],
)
def test_each_rule_marks_what_arm_says_is_unused(resource: dict, rule: str) -> None:
    assert rules(resource) == {resource["name"].lower(): rule}


@pytest.mark.parametrize(
    "resource",
    [
        # a row that leaves the deciding property out says nothing
        row("Microsoft.Compute/disks", "d-sparse"),
        row(
            "Microsoft.Compute/disks",
            "d-attached",
            {"diskState": "Attached"},
            managedBy=rid(VM, "vm"),
        ),
        row("Microsoft.Network/publicIPAddresses", "ip-sparse"),
        row(
            "Microsoft.Network/publicIPAddresses",
            "ip-used",
            {"publicIPAllocationMethod": "Static", "ipConfiguration": {"id": "x"}},
        ),
        row("Microsoft.Network/networkSecurityGroups", "nsg-on", {"subnets": [{"id": "s"}]}),
        row("Microsoft.Network/loadBalancers", "lb-sparse"),
        row(
            "Microsoft.Network/loadBalancers",
            "lb-used",
            {"backendAddressPools": [{"properties": {"backendIPConfigurations": [{"id": "x"}]}}]},
        ),
        row("Microsoft.Web/serverFarms", "plan-sparse"),
        row("Microsoft.Web/serverFarms", "plan-used", {"numberOfSites": 2}),
        row(
            VM,
            "vm-running",
            {"extended": {"instanceView": {"powerState": {"code": "PowerState/running"}}}},
        ),
        row(
            "Microsoft.Network/virtualNetworkGateways",
            "p2s",
            {"gatewayType": "Vpn", "vpnClientConfiguration": {"x": 1}},
        ),
        row("Microsoft.Network/privateDnsZones", "zone-linked", {"numberOfVirtualNetworkLinks": 1}),
        row(NIC, "nic-sparse"),
        row(NIC, "nic-vm", {"ipConfigurations": [{}], "virtualMachine": {"id": rid(VM, "vm")}}),
    ],
)
def test_a_row_in_use_or_silent_is_never_called_unused(resource: dict) -> None:
    assert rules(resource) == {}


def test_a_nic_or_gateway_another_resource_names_is_in_use() -> None:
    nic = row(NIC, "nic-lb", {"ipConfigurations": [{}]})
    balancer = row(
        "Microsoft.Network/loadBalancers",
        "lb",
        {
            "backendAddressPools": [
                {
                    "properties": {
                        "backendIPConfigurations": [{"id": nic["id"] + "/ipConfigurations/ip1"}]
                    }
                }
            ]
        },
    )
    gateway = row("Microsoft.Network/virtualNetworkGateways", "vgw", {"gatewayType": "Vpn"})
    connection = row(
        "Microsoft.Network/connections", "cn", {"virtualNetworkGateway1": {"id": gateway["id"]}}
    )
    assert rules(nic, balancer, gateway, connection) == {}


def test_an_empty_group_is_found_and_a_managed_one_is_not() -> None:
    groups = [
        {"name": "rg-app", "subscriptionId": SUB},
        {"name": "rg-empty", "subscriptionId": SUB},
        {"name": "MC_aks", "subscriptionId": SUB, "managedBy": "aks"},
    ]
    found = empty_groups(groups, [row("Microsoft.Web/sites", "app")])
    assert [group["name"] for group in found] == ["rg-empty"]


def _snapshot() -> dict:
    disk = row(
        "Microsoft.Compute/disks", "disk-old", {"diskState": "Unattached", "diskSizeGB": 128}
    )
    vm = row(
        VM,
        "vm-off",
        {
            "hardwareProfile": {"vmSize": "Standard_D2s_v5"},
            "extended": {"instanceView": {"powerState": {"code": "PowerState/deallocated"}}},
        },
    )
    return {
        "format": "infragram.azure-snapshot/1",
        "taken": "2026-10-27T12:00:00+00:00",
        "subscriptions": [{"id": SUB, "name": "Production", "state": "Enabled"}],
        "resourceGroups": [
            {
                "name": "rg-app",
                "subscriptionId": SUB,
                "id": f"/subscriptions/{SUB}/resourceGroups/rg-app",
            },
            {
                "name": "rg-empty",
                "subscriptionId": SUB,
                "id": f"/subscriptions/{SUB}/resourceGroups/rg-empty",
            },
        ],
        "resources": [disk, vm],
    }


def test_the_picture_marks_unused_cards_and_draws_unused_plumbing() -> None:
    plan, summary = blueprint(_snapshot(), ImportOptions(view="groups"))
    project = plan.to_project()
    marked = {
        element.name: element.attributes["unused"]["rule"]
        for element in project.topology.walk()
        if "unused" in element.attributes
    }
    # the disk is plumbing, left out unless asked; an unattached one is drawn
    assert marked == {
        "disk-old": "unattached-disk",
        "vm-off": "deallocated-vm",
        "rg-empty": "empty-resource-group",
    }
    assert summary.unused == {"unattached-disk": 1, "deallocated-vm": 1, "empty-resource-group": 1}
    assert any("3 unused" in line for line in summary.lines())


def test_a_deallocated_vm_costs_no_compute_and_keeps_what_it_would() -> None:
    plan, _ = blueprint(_snapshot(), ImportOptions(view="groups"))
    project = plan.to_project()
    price_project(project)
    vm = next(element for element in project.topology.walk() if element.name == "vm-off")
    assert vm.attributes["price"]["monthly"] == 0.0
    assert vm.attributes["unused"]["running_monthly"] > 0
    assert vm.attributes["price"]["rate"].startswith("Deallocated")


def _vm_with_parts() -> dict:
    nic = row(
        NIC,
        "nic-web",
        {
            "ipConfigurations": [
                {
                    "id": rid(NIC, "nic-web") + "/ipConfigurations/ip1",
                    "properties": {"privateIPAddress": "10.1.1.4"},
                }
            ],
            "virtualMachine": {"id": rid(VM, "vm-web")},
        },
    )
    snapshot = _snapshot()
    snapshot["resources"] = [
        row(VM, "vm-web", {"networkProfile": {"networkInterfaces": [{"id": nic["id"]}]}}),
        nic,
        row(
            "Microsoft.Compute/disks",
            "vm-web_OsDisk",
            {"diskState": "Attached", "osType": "Linux", "diskSizeGB": 128},
            sku={"name": "Premium_LRS"},
            managedBy=rid(VM, "vm-web"),
        ),
        row(
            "Microsoft.Network/publicIPAddresses",
            "pip-web",
            {
                "publicIPAllocationMethod": "Static",
                "ipAddress": "20.1.2.3",
                "ipConfiguration": {"id": rid(NIC, "nic-web") + "/ipConfigurations/ip1"},
            },
        ),
    ]
    return snapshot


def test_a_vm_lists_its_nic_disk_and_public_ip() -> None:
    plan, _ = blueprint(_vm_with_parts(), ImportOptions(view="groups"))
    vm = next(e for e in plan.to_project().topology.walk() if e.name == "vm-web")
    rows = dict(vm.attributes["table"]["rows"])
    assert rows["NIC"] == "nic-web · 10.1.1.4"
    assert rows["OS disk"] == "vm-web_OsDisk · Premium_LRS · 128 GiB"
    assert rows["public IP"] == "pip-web · 20.1.2.3"
    assert [part["role"] for part in vm.attributes["attached"]] == ["NIC", "OS disk", "public IP"]


def test_with_plumbing_drawn_each_part_is_wired_to_its_vm() -> None:
    plan, _ = blueprint(_vm_with_parts(), ImportOptions(view="groups", everything=True))
    project = plan.to_project()
    names = {e.id: e.name for e in project.topology.walk()}
    wires = {
        (e.name, names[c.target], c.label) for e in project.topology.walk() for c in e.connections
    }
    assert {
        ("nic-web", "vm-web", "NIC"),
        ("vm-web_OsDisk", "vm-web", "OS disk"),
        ("pip-web", "vm-web", "public IP"),
    } <= wires
    disk = next(e for e in project.topology.walk() if e.name == "vm-web_OsDisk")
    assert disk.attributes["attached_to"] == "vm-web"


def test_prices_follow_what_arm_states_and_an_app_is_not_counted_twice() -> None:
    plan = row(
        "Microsoft.Web/serverFarms",
        "plan",
        {"numberOfSites": 1, "reserved": True},
        sku={"name": "P1v3", "capacity": 2},
    )
    snapshot = _snapshot()
    snapshot["resources"] = [
        plan,
        row("Microsoft.Web/sites", "app", {"serverFarmId": plan["id"]}, kind="app,linux"),
        row(
            "Microsoft.Compute/disks",
            "disk",
            {"diskState": "Unattached", "diskSizeGB": 512},
            sku={"name": "Premium_LRS"},
        ),
        row(
            "Microsoft.Network/publicIPAddresses",
            "ip",
            {"publicIPAllocationMethod": "Static"},
            sku={"name": "Basic"},
        ),
    ]
    blueprint_plan, _ = blueprint(snapshot, ImportOptions(view="groups"))
    project = blueprint_plan.to_project()
    price_project(project)
    by_name = {element.name: element for element in project.topology.walk()}
    assert by_name["plan"].attributes["sizing"] == {
        "sku": "P1v3",
        "os": "Linux",
        "count": 2,
        "region": "eastus2",
    }
    assert by_name["app"].attributes["unpriced"] == "free: billed through its App Service plan plan"
    assert "price" not in by_name["app"].attributes
    disk = by_name["disk"].attributes["price"]
    assert disk["sizing"]["type"] == "Premium SSD" and "size_gb" not in disk["assumed"]
    assert by_name["ip"].attributes["price"]["sizing"]["tier"] == "Basic"
