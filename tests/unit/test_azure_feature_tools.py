"""Azure inventory remains compatible with the shared import and review tools.

These checks use saved inventory, local Terraform and template-only exports;
they need neither Azure credentials nor a browser.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from infragram.discovery import ImportOptions, blueprint, save_snapshot
from infragram.estate import Card, draw, write_spec
from infragram.estate.tables import LIBRARIES, frame_class, library_of
from infragram.mcp.run import _run
from infragram.mcp.tools import _BY_NAME
from infragram.pricing import price_project
from infragram.projects import CloudProject
from infragram.terraform import terraform_files
from infragram.terraform.mapping import PROVIDERS, load_mapping
from infragram.terraform.readconfig import read_configuration


@pytest.fixture
def inventory() -> dict:
    subscription = "11111111-2222-3333-4444-555555555555"
    group = f"/subscriptions/{subscription}/resourceGroups/rg-app"

    def resource(kind: str, name: str, properties: dict) -> dict:
        return {
            "id": f"{group}/providers/{kind}/{name}",
            "type": kind,
            "name": name,
            "location": "eastus2",
            "resourceGroup": "rg-app",
            "subscriptionId": subscription,
            "properties": properties,
        }

    subnet = f"{group}/providers/Microsoft.Network/virtualNetworks/vnet-app/subnets/app"
    nic = resource(
        "Microsoft.Network/networkInterfaces",
        "nic-app",
        {
            "ipConfigurations": [{"properties": {"subnet": {"id": subnet}}}],
        },
    )
    vm = resource(
        "Microsoft.Compute/virtualMachines",
        "vm-app",
        {
            "hardwareProfile": {"vmSize": "Standard_B2s"},
            "networkProfile": {"networkInterfaces": [{"id": nic["id"]}]},
        },
    )
    nic["properties"]["virtualMachine"] = {"id": vm["id"]}
    nsg = resource(
        "Microsoft.Network/networkSecurityGroups",
        "nsg-app",
        {
            "subnets": [{"id": subnet}],
            "networkInterfaces": [{"id": nic["id"]}],
        },
    )
    network = resource(
        "Microsoft.Network/virtualNetworks",
        "vnet-app",
        {
            "addressSpace": {"addressPrefixes": ["10.0.0.0/16"]},
            "subnets": [
                {"id": subnet, "name": "app", "properties": {"addressPrefix": "10.0.1.0/24"}}
            ],
        },
    )
    return {
        "format": "infragram.azure-snapshot/1",
        "taken": "2026-10-15T10:00:00+00:00",
        "subscriptions": [
            {
                "id": subscription,
                "name": "Production",
                "state": "Enabled",
                "tenantId": "tenant",
                "tenantName": "Contoso",
            }
        ],
        "resourceGroups": [{"id": group, "name": "rg-app", "subscriptionId": subscription}],
        "resources": [network, nic, vm, nsg],
    }


def test_an_nsg_keeps_subnet_and_nic_attachments(inventory: dict) -> None:
    project = blueprint(inventory)[0].to_project()
    root = project.topology
    subnet = root.first(name="app · 10.0.1.0/24")
    nsg = root.first(name="nsg-app")
    vm = root.first(name="vm-app")
    assert [(badge.label, badge.side) for badge in subnet.badges] == [("nsg-app", "corner")]
    assert nsg.attributes["detail"] == "on NIC · vm-app"
    assert any(link.target == vm.id and link.label == "NIC" for link in nsg.connections)


@pytest.mark.parametrize("view", ("network", "groups"))
def test_inventory_projects_round_trip_schema_three(
    inventory: dict, view: str, tmp_path: Path
) -> None:
    project = blueprint(inventory, ImportOptions(view=view))[0].to_project()
    saved = project.save(tmp_path / f"{view}.infragram.json")
    loaded = CloudProject.load(saved)
    assert loaded.schema_version == 3
    assert loaded.topology.first(name="vm-app") is not None
    assert loaded.model_dump(mode="json") == project.model_dump(mode="json")


def test_terraform_support_matches_the_installed_vendor_catalog() -> None:
    assert PROVIDERS == ("azure",)
    assert LIBRARIES == {"azurerm": "azure"}
    assert library_of("azurerm_linux_virtual_machine") == "azure"
    assert library_of("aws_instance") is None
    with pytest.raises(KeyError, match="covers azure"):
        load_mapping("aws")
    # Other vendors in an imported diagram can fall back to a generic frame.
    assert frame_class("aws", "network") is None


def test_azure_inventory_exports_both_terraform_styles(inventory: dict) -> None:
    project = blueprint(inventory)[0].to_project()
    for style in ("resources", "modules"):
        plan, files = terraform_files(project, style=style)
        assert "azure" in plan.providers
        assert set(plan.providers) <= {"azure", "azapi", "azuread"}
        assert {"environments/dev/main.tf", "environments/prod/main.tf"} <= files.keys()
        text = "\n".join(files.values())
        assert re.search(r'source\s*=\s*"hashicorp/azurerm"', text)
        if style == "resources":
            assert 'resource "azurerm_linux_virtual_machine"' in text
        else:
            assert "Azure/avm-" in text
        assert 'resource "aws_' not in text and 'resource "google_' not in text


def test_vm_pricing_uses_the_imported_region_and_capacity(inventory: dict) -> None:
    project = blueprint(inventory)[0].to_project()
    result = price_project(project)
    assert result.priced, result.notes
    price = project.topology.first(name="vm-app").attributes["price"]
    assert price["sizing"]["region"] == "eastus2"
    assert price["sizing"]["size"] == "Standard_B2s"
    assert price["sizing"]["count"] == 1
    assert not {"region", "size", "count"}.intersection(price["assumed"])


def test_local_terraform_import_keeps_azure_nsg_traffic(tmp_path: Path) -> None:
    source = tmp_path / "main.tf"
    source.write_text(
        """
resource "azurerm_resource_group" "app" {
  name = "rg-app"
  location = "eastus2"
}
resource "azurerm_virtual_network" "app" {
  name = "vnet-app"
  resource_group_name = azurerm_resource_group.app.name
  address_space = ["10.0.0.0/16"]
}
resource "azurerm_subnet" "app" {
  name = "app"
  resource_group_name = azurerm_resource_group.app.name
  virtual_network_name = azurerm_virtual_network.app.name
  address_prefixes = ["10.0.1.0/24"]
}
resource "azurerm_network_interface" "app" {
  name = "nic-app"
  resource_group_name = azurerm_resource_group.app.name
  ip_configuration {
    subnet_id = azurerm_subnet.app.id
  }
}
resource "azurerm_linux_virtual_machine" "app" {
  name = "vm-app"
  resource_group_name = azurerm_resource_group.app.name
  size = "Standard_B2s"
  network_interface_ids = [azurerm_network_interface.app.id]
}
resource "azurerm_network_security_group" "app" {
  name = "nsg-app"
  resource_group_name = azurerm_resource_group.app.name
  security_rule {
    name = "ssh"
    priority = 100
    direction = "Inbound"
    access = "Allow"
    protocol = "Tcp"
    source_address_prefix = "Internet"
    destination_address_prefix = "*"
    destination_port_range = "22"
  }
}
resource "azurerm_subnet_network_security_group_association" "app" {
  subnet_id = azurerm_subnet.app.id
  network_security_group_id = azurerm_network_security_group.app.id
}
""",
        encoding="utf-8",
    )
    drawing = draw(read_configuration(tmp_path))
    assert any(
        isinstance(item, Card) and item.service_id == "virtual-machine" for item in drawing.walk()
    )
    assert any(wire.source == "internet" and wire.label == "SSH :22" for wire in drawing.wires)
    spec = write_spec(drawing, command="import:terraform", date="2026-10-15", filename="app.py")
    compile(spec, "app.py", "exec")


def test_mcp_rejects_discovery_for_an_uninstalled_vendor() -> None:
    result = _run(_BY_NAME["discover"], {"cloud": "aws"})
    assert result.failed
    assert "azure, kubernetes" in result.text


def test_mcp_exports_both_views_from_a_snapshot_without_azure(
    inventory: dict, tmp_path: Path
) -> None:
    source = save_snapshot(inventory, tmp_path / "snapshot.json")
    output = tmp_path / "out"
    result = _run(
        _BY_NAME["export_azure"],
        {
            "from_snapshot": str(source),
            "view": "both",
            "formats": "template",
            "output_dir": str(output),
            "verify": True,
        },
    )
    assert not result.failed, result.text
    files = sorted(output.glob("*.infragram.json"))
    assert len(files) == 2
    assert {json.loads(path.read_text(encoding="utf-8"))["schema_version"] for path in files} == {3}
    assert {entry["kind"] for entry in result.data["files"]} >= {"TEMPLATE"}


def test_an_empty_subscription_writes_its_page_and_no_picture(tmp_path: Path) -> None:
    """A subscription with nothing in it has no picture to draw: the page and
    the template show the frames that were read, and verification passes
    rather than failing on an SVG without a component."""
    subscription = "11111111-2222-3333-4444-555555555555"
    empty = {
        "format": "infragram.azure-snapshot/1",
        "taken": "2026-10-27T12:00:00+00:00",
        "subscriptions": [{"id": subscription, "name": "Empty", "state": "Enabled"}],
        "resourceGroups": [
            {
                "id": f"/subscriptions/{subscription}/resourceGroups/rg-empty",
                "name": "rg-empty",
                "subscriptionId": subscription,
            }
        ],
        "resources": [],
    }
    source = save_snapshot(empty, tmp_path / "snapshot.json")
    output = tmp_path / "out"
    result = _run(
        _BY_NAME["export_azure"],
        {
            "from_snapshot": str(source),
            "formats": "template,svg,png",
            "output_dir": str(output),
            "verify": True,
        },
    )
    assert not result.failed, result.text
    assert sorted(path.suffix for path in output.iterdir()) == [".json"]
    assert "no resources to draw" in result.text
