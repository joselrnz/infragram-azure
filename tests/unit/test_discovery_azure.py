"""Drawing a live Azure estate: the snapshot reader and both views of it.

Nothing here calls Azure. The session is driven through a fake ``az``, and
the views are built from a snapshot shaped like Resource Graph's own rows:
lower-case types, ids in whatever case ARM felt like, properties nested the
way the real ones are. What has to hold is where each resource lands --
subnet or resource group -- and which wires and badges it brings.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from infragram.discovery import (
    AzureCliError,
    AzureSession,
    ImportOptions,
    arm_types,
    blueprint,
    load_snapshot,
    save_snapshot,
)
from infragram.nodes import reset_ids

SUB = "11111111-2222-3333-4444-555555555555"
TENANT = "99999999-8888-7777-6666-555555555555"


def rid(group: str, provider: str, *path: str) -> str:
    return f"/subscriptions/{SUB}/resourceGroups/{group}/providers/{provider}/{'/'.join(path)}"


def subnet_id(group: str, vnet: str, subnet: str) -> str:
    return rid(group, "Microsoft.Network", "virtualNetworks", vnet, "subnets", subnet)


def resource(
    group: str,
    provider: str,
    kind_path: str,
    name: str,
    *,
    kind: str = "",
    properties: dict | None = None,
    sku: dict | None = None,
    location: str = "eastus2",
) -> dict:
    return {
        "id": rid(group, provider, *kind_path.split("/")[:1], name, *kind_path.split("/")[1:]),
        "name": name,
        "type": f"{provider}/{kind_path}".lower(),
        "kind": kind,
        "location": location,
        "resourceGroup": group.lower(),
        "subscriptionId": SUB,
        "tenantId": TENANT,
        "sku": sku,
        "managedBy": "",
        "tags": {"env": "prod"},
        "properties": properties or {},
    }


def vnet(
    group: str, name: str, prefix: str, subnets: dict[str, str], peer: str | None = None
) -> dict:
    props = {
        "addressSpace": {"addressPrefixes": [prefix]},
        "subnets": [
            {"id": subnet_id(group, name, s), "name": s, "properties": {"addressPrefix": p}}
            for s, p in subnets.items()
        ],
        "virtualNetworkPeerings": [],
    }
    if peer:
        props["virtualNetworkPeerings"].append(
            {
                "name": "peer",
                "properties": {
                    "remoteVirtualNetwork": {"id": peer.replace("resourceGroups", "RESOURCEGROUPS")}
                },
            }
        )
    return resource(group, "Microsoft.Network", "virtualNetworks", name, properties=props)


def snapshot() -> dict:
    hub_id = rid("rg-hub", "Microsoft.Network", "virtualNetworks", "vnet-hub")
    app_id = rid("rg-app", "Microsoft.Network", "virtualNetworks", "vnet-app")
    workspace = resource("rg-app", "Microsoft.OperationalInsights", "workspaces", "log-prod")
    storage = resource(
        "rg-app",
        "Microsoft.Storage",
        "storageAccounts",
        "stprod",
        kind="StorageV2",
        sku={"name": "Standard_ZRS"},
        properties={
            "networkAcls": {
                "virtualNetworkRules": [{"id": subnet_id("rg-app", "vnet-app", "snet-web")}]
            }
        },
    )
    nic = resource(
        "rg-app",
        "Microsoft.Network",
        "networkInterfaces",
        "nic-web",
        properties={
            "ipConfigurations": [
                {"properties": {"subnet": {"id": subnet_id("rg-app", "vnet-app", "snet-web")}}}
            ]
        },
    )
    server = resource("rg-app", "Microsoft.Sql", "servers", "sql-prod")
    database = dict(
        resource("rg-app", "Microsoft.Sql", "servers", "sql-prod"),
        id=server["id"] + "/databases/orders",
        name="orders",
        type="microsoft.sql/servers/databases",
        sku={"name": "GP_Gen5_2"},
    )
    master = dict(database, id=server["id"] + "/databases/master", name="master")
    plan = resource("rg-app", "Microsoft.Web", "serverfarms", "plan-prod", sku={"name": "P1v3"})
    return {
        "format": "infragram.azure-snapshot/1",
        "taken": "2026-09-29T12:00:00+00:00",
        "subscriptions": [
            {
                "id": SUB,
                "name": "Production",
                "state": "Enabled",
                "tenantId": TENANT,
                "tenantName": "Contoso",
            }
        ],
        "resourceGroups": [
            {
                "id": f"/subscriptions/{SUB}/resourceGroups/rg-hub",
                "name": "rg-hub",
                "subscriptionId": SUB,
            },
            {
                "id": f"/subscriptions/{SUB}/resourceGroups/rg-app",
                "name": "rg-app",
                "subscriptionId": SUB,
            },
            {
                "id": f"/subscriptions/{SUB}/resourceGroups/MC_rg-app_aks",
                "name": "MC_rg-app_aks",
                "subscriptionId": SUB,
                "managedBy": rid(
                    "rg-app", "Microsoft.ContainerService", "managedClusters", "aks-prod"
                ),
            },
        ],
        "resources": [
            vnet(
                "rg-hub",
                "vnet-hub",
                "10.0.0.0/16",
                {"AzureFirewallSubnet": "10.0.1.0/26", "snet-pe": "10.0.2.0/24"},
                peer=app_id,
            ),
            vnet(
                "rg-app",
                "vnet-app",
                "10.1.0.0/16",
                {"snet-web": "10.1.1.0/24", "snet-aks": "10.1.2.0/23"},
                peer=hub_id,
            ),
            resource(
                "rg-hub",
                "Microsoft.Network",
                "azureFirewalls",
                "afw-hub",
                properties={
                    "ipConfigurations": [
                        {
                            "properties": {
                                "subnet": {
                                    "id": subnet_id("rg-hub", "vnet-hub", "AzureFirewallSubnet")
                                }
                            }
                        }
                    ]
                },
            ),
            resource(
                "rg-hub",
                "Microsoft.Network",
                "privateEndpoints",
                "pe-stprod",
                properties={
                    "subnet": {"id": subnet_id("rg-hub", "vnet-hub", "snet-pe")},
                    "privateLinkServiceConnections": [
                        {
                            "properties": {
                                "privateLinkServiceId": storage["id"],
                                "groupIds": ["blob"],
                            }
                        }
                    ],
                },
            ),
            resource(
                "rg-app",
                "Microsoft.Network",
                "networkSecurityGroups",
                "nsg-web",
                properties={"subnets": [{"id": subnet_id("rg-app", "vnet-app", "snet-web")}]},
            ),
            resource("rg-app", "Microsoft.Network", "networkSecurityGroups", "nsg-orphan"),
            nic,
            resource("rg-app", "Microsoft.Compute", "disks", "vm-web_OsDisk"),
            resource(
                "rg-app",
                "Microsoft.Compute",
                "virtualMachines",
                "vm-web",
                properties={
                    "hardwareProfile": {"vmSize": "Standard_D2s_v5"},
                    "networkProfile": {"networkInterfaces": [{"id": nic["id"].upper()}]},
                },
            ),
            resource(
                "rg-app",
                "Microsoft.ContainerService",
                "managedClusters",
                "aks-prod",
                properties={
                    "agentPoolProfiles": [
                        {"vnetSubnetID": subnet_id("rg-app", "vnet-app", "snet-aks")}
                    ],
                    "addonProfiles": {
                        "omsagent": {"config": {"logAnalyticsWorkspaceResourceID": workspace["id"]}}
                    },
                },
            ),
            workspace,
            storage,
            server,
            database,
            master,
            plan,
            resource(
                "rg-app",
                "Microsoft.Web",
                "sites",
                "app-prod",
                kind="app,linux",
                properties={"serverFarmId": plan["id"]},
            ),
            resource(
                "rg-app",
                "Microsoft.Web",
                "sites",
                "func-prod",
                kind="functionapp,linux",
                properties={"serverFarmId": plan["id"]},
            ),
            resource("rg-app", "Microsoft.Contoso", "widgets", "widget-1"),
            resource(
                "MC_rg-app_aks",
                "Microsoft.Compute",
                "virtualMachineScaleSets",
                "aks-nodepool1-vmss",
            ),
        ],
    }


@pytest.fixture(autouse=True)
def _fresh_ids():
    reset_ids()
    yield
    reset_ids()


def build(**options):
    plan, summary = blueprint(snapshot(), ImportOptions(**options))
    return plan.to_project().topology, summary


def parent_name(root, name: str) -> str:
    element = root.first(name=name)
    assert element is not None, f"{name!r} is not drawn"
    return root.parent_of(element).name


def wires(root) -> list[tuple[str, str, str, str, str]]:
    index = root.index()
    return [
        (element.name, index[c.target].name, c.kind, c.label, c.direction)
        for element in root.walk()
        for c in element.connections
    ]


# -- network view ---------------------------------------------------------


def test_the_frames_follow_tenant_subscription_group_network_subnet() -> None:
    root, summary = build()
    assert parent_name(root, "Production") == "Contoso"
    assert parent_name(root, "rg-app") == "Production"
    assert parent_name(root, "vnet-app · 10.1.0.0/16") == "rg-app"
    assert parent_name(root, "snet-web · 10.1.1.0/24") == "vnet-app · 10.1.0.0/16"
    assert (summary.networks, summary.subnets) == (2, 4)


def test_resources_with_an_address_sit_in_their_subnet() -> None:
    root, summary = build()
    assert (
        parent_name(root, "vm-web") == "snet-web · 10.1.1.0/24"
    )  # through its NIC, id upper-cased
    assert parent_name(root, "aks-prod") == "snet-aks · 10.1.2.0/23"  # through its node pool
    assert parent_name(root, "afw-hub") == "AzureFirewallSubnet · 10.0.1.0/26"
    assert parent_name(root, "pe-stprod") == "snet-pe · 10.0.2.0/24"
    assert summary.placed == 4


def test_a_firewall_rule_naming_a_subnet_does_not_move_a_resource_into_it() -> None:
    root, _ = build()
    assert parent_name(root, "stprod") == "rg-app"


def test_a_subnet_nsg_is_a_named_badge_on_the_subnet_corner() -> None:
    root, summary = build()
    subnet = root.first(name="snet-web · 10.1.1.0/24")
    assert [(b.icon, b.label, b.side) for b in subnet.badges] == [
        ("network-security-groups", "nsg-web", "corner")
    ]
    assert root.first(name="nsg-web") is None  # a badge, not a card
    assert parent_name(root, "nsg-orphan") == "rg-app"  # applies to nothing
    assert summary.attached == 1


def test_corner_badges_go_nsg_first_then_route_table_then_nat() -> None:
    data = snapshot()
    web = subnet_id("rg-app", "vnet-app", "snet-web")
    for provider_type, name in (("natGateways", "ng-egress"), ("routeTables", "rt-spoke")):
        data["resources"].append(
            resource(
                "rg-app",
                "Microsoft.Network",
                provider_type,
                name,
                properties={"subnets": [{"id": web}]},
            )
        )
    root = blueprint(data)[0].to_project().topology
    subnet = root.first(name="snet-web · 10.1.1.0/24")
    assert [b.label for b in subnet.badges] == ["nsg-web", "rt-spoke", "ng-egress"]


def test_corner_badges_reach_the_editor_and_the_picture(tmp_path: Path) -> None:
    plan, _ = blueprint(snapshot())
    result = plan.export(tmp_path, formats=("html", "svg"))
    page = result.html.read_text(encoding="utf-8")
    assert '"badges":[{"icon":"network-security-groups"' in page
    assert '"label":"nsg-web","side":"corner"' in page
    assert ">nsg-web</text>" in result.svg.read_text(encoding="utf-8")


def test_plumbing_and_managed_groups_stay_out_unless_asked() -> None:
    root, _ = build()
    for name in ("nic-web", "vm-web_OsDisk", "master", "MC_rg-app_aks", "aks-nodepool1-vmss"):
        assert root.first(name=name) is None, name
    root, _ = build(everything=True, managed_groups=True)
    assert parent_name(root, "nic-web") == "snet-web · 10.1.1.0/24"
    assert parent_name(root, "vm-web_OsDisk") == "rg-app"
    assert parent_name(root, "aks-nodepool1-vmss") == "MC_rg-app_aks"


def test_a_web_app_and_its_plan_name_each_other_and_sit_together() -> None:
    root, _ = build()
    app = root.first(name="app-prod")
    plan = root.first(name="plan-prod")
    assert dict(app.attributes["table"]["rows"])["Runs on"] == "plan-prod"
    assert app.attributes["runs_on"] == "plan-prod"
    assert dict(plan.attributes["table"]["rows"])["Hosts"] == "app-prod, func-prod"
    assert plan.attributes["hosts"] == ["app-prod", "func-prod"]
    # each app is placed right after its plan, so the wire between them is short
    siblings = [child.name for child in root.parent_of(plan).children if not child.is_frame]
    at = siblings.index("plan-prod")
    assert siblings[at + 1 : at + 3] == ["app-prod", "func-prod"]


def test_peering_private_links_and_references_become_wires() -> None:
    root, _ = build(references=True)
    drawn = wires(root)
    # Two sides, one wire, between the Peerings cards inside each network.
    assert [w for w in drawn if w[3] == "peering"] == [
        ("vnet-app peering", "vnet-hub peering", "solid", "peering", "both")
    ]
    assert parent_name(root, "vnet-hub peering") == "vnet-hub · 10.0.0.0/16"
    assert ("pe-stprod", "stprod", "dashed", "blob", "forward") in drawn
    assert ("app-prod", "plan-prod", "dashed", "runs on", "forward") in drawn
    assert ("aks-prod", "log-prod", "dashed", "", "forward") in drawn
    assert ("sql-prod", "orders", "dashed", "", "forward") in drawn  # parent to child
    # By default only what places or reaches: peering, private link, an app
    # to the plan it runs on, parent to child.
    root, _ = build()
    assert sorted((w[0], w[1]) for w in wires(root)) == [
        ("app-prod", "plan-prod"),
        ("func-prod", "plan-prod"),
        ("pe-stprod", "stprod"),
        ("sql-prod", "orders"),
        ("vnet-app peering", "vnet-hub peering"),
    ]


def test_kind_picks_the_icon_and_unknown_types_fall_back() -> None:
    root, summary = build()
    assert root.first(name="func-prod").attributes["icon"] == "function-apps"
    assert root.first(name="app-prod").attributes["icon"] == "app-services"
    assert (
        root.first(name="vm-web").attributes["detail"] == "Standard_D2s_v5"
    )  # one region: not repeated
    assert summary.unmapped == {"microsoft.contoso/widgets": 1}
    assert root.first(name="widget-1").attributes["icon"] == "all-resources"


def test_every_drawn_resource_carries_its_arm_facts() -> None:
    root, _ = build()
    rows = dict(root.first(name="vm-web").attributes["table"]["rows"])
    assert rows["Type"] == "microsoft.compute/virtualmachines"
    assert rows["Resource group"] == "rg-app"
    assert rows["tag: env"] == "prod"


# -- groups view ----------------------------------------------------------


def test_the_groups_view_files_everything_by_resource_group() -> None:
    root, summary = build(view="groups")
    for name in ("vm-web", "aks-prod", "nsg-web", "vnet-app", "stprod"):
        assert parent_name(root, name) == "rg-app", name
    assert parent_name(root, "pe-stprod") == "rg-hub"
    assert summary.networks == 0 and summary.attached == 0
    assert root.first(name="vnet-app peering") is None
    assert [w for w in wires(root) if w[3] == "peering"] == [
        ("vnet-app", "vnet-hub", "solid", "peering", "both")
    ]


def test_a_resource_group_filter_keeps_only_matching_groups() -> None:
    root, summary = build(resource_groups=("RG-H*",))
    assert parent_name(root, "rg-hub") == "Production"
    # rg-app only as the far end of the hub's peering, outside the import
    assert parent_name(root, "rg-app") == "Production · filtered out"
    assert root.first(name="vm-web") is None
    assert parent_name(root, "pe-stprod") == "snet-pe · 10.0.2.0/24"
    assert summary.resource_groups == 1


def test_an_excluded_type_is_left_out() -> None:
    root, _ = build(exclude_types=("microsoft.sql/*",))
    assert root.first(name="sql-prod") is None and root.first(name="orders") is None


def test_both_views_export_a_valid_picture(tmp_path: Path) -> None:
    for view in ("network", "groups"):
        plan, _ = blueprint(snapshot(), ImportOptions(view=view))
        result = plan.export(tmp_path, formats=("template", "svg"))
        assert result.svg.read_text(encoding="utf-8").lstrip().startswith("<")
        assert (
            json.loads(result.template.read_text(encoding="utf-8"))["slug"]
            == f"azure-production-{view}"
        )


def test_every_mapped_class_exists() -> None:
    paths = set(arm_types.TYPES.values()) | {
        p for kinds in arm_types.BY_KIND.values() for p in kinds.values()
    }
    for path in sorted(paths | {arm_types.FALLBACK}):
        module, _, name = path.rpartition(".")
        assert hasattr(__import__(f"infragram.nodes.azure.{module}", fromlist=[name]), name), path
    assert set(arm_types.TYPES) >= arm_types.PLUMBING


# -- the az session -------------------------------------------------------


class FakeAz:
    def __init__(self, pages: list[dict]) -> None:
        self.pages = list(pages)
        self.bodies: list[dict] = []

    def __call__(self, args):
        if args[:2] == ["account", "show"]:
            return json.dumps(
                {
                    "id": SUB,
                    "name": "Production",
                    "tenantId": TENANT,
                    "tenantDisplayName": "Contoso",
                    "state": "Enabled",
                }
            )
        if args[:2] == ["account", "list"]:
            return json.dumps(
                [
                    {"id": SUB, "name": "Production", "state": "Enabled", "tenantId": TENANT},
                    {"id": "other", "name": "Sandbox", "state": "Disabled", "tenantId": TENANT},
                ]
            )
        if args[0] == "rest":
            body = args[args.index("--body") + 1]
            self.bodies.append(json.loads(Path(body[1:]).read_text(encoding="utf-8")))
            return json.dumps(self.pages.pop(0))
        raise AssertionError(args)


def test_the_session_picks_the_current_subscription_or_the_named_ones() -> None:
    session = AzureSession(FakeAz([]))
    assert [s["name"] for s in session.resolve()] == ["Production"]
    assert session.resolve()[0]["tenantName"] == "Contoso"
    assert [s["id"] for s in session.resolve(["sandbox"])] == ["other"]
    assert [s["name"] for s in session.resolve(every=True)] == ["Production"]
    with pytest.raises(AzureCliError, match="no subscription matches 'nope'"):
        session.resolve(["nope"])


def test_resource_graph_is_read_page_by_page() -> None:
    fake = FakeAz([{"data": [{"id": "a"}], "$skipToken": "next"}, {"data": [{"id": "b"}]}])
    rows = AzureSession(fake).query("resources", [SUB])
    assert rows == [{"id": "a"}, {"id": "b"}]
    assert fake.bodies[0]["subscriptions"] == [SUB]
    assert "$skipToken" not in fake.bodies[0]["options"]
    assert fake.bodies[1]["options"]["$skipToken"] == "next"


def test_a_management_group_reads_the_enabled_subscriptions_under_it() -> None:
    fake = FakeAz(
        [
            {
                "data": [
                    {"id": "sub-b", "name": "Spoke", "tenantId": TENANT, "state": "Enabled"},
                    {"id": "sub-a", "name": "Hub", "tenantId": TENANT, "state": "Enabled"},
                    {"id": "sub-c", "name": "Old", "tenantId": TENANT, "state": "Disabled"},
                ]
            }
        ]
    )
    chosen = AzureSession(fake).under_management_groups(["mg-platform", " mg-platform "])
    assert [entry["name"] for entry in chosen] == ["Hub", "Spoke"]
    assert fake.bodies[0]["managementGroups"] == ["mg-platform"]
    assert "subscriptions" not in fake.bodies[0]
    with pytest.raises(AzureCliError, match="no enabled subscription under management group"):
        AzureSession(FakeAz([{"data": []}])).under_management_groups(["mg-empty"])


def test_a_snapshot_round_trips(tmp_path: Path) -> None:
    path = save_snapshot(snapshot(), tmp_path / "estate.json")
    assert load_snapshot(path) == json.loads(json.dumps(snapshot()))
    (tmp_path / "other.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="not an Azure snapshot"):
        load_snapshot(tmp_path / "other.json")


def test_the_command_draws_both_views_from_a_saved_snapshot(tmp_path: Path, capsys) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "export" / "azure.py"
    spec = importlib.util.spec_from_file_location("_export_azure_script", script)
    command = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(command)
    source = save_snapshot(snapshot(), tmp_path / "estate.json")
    code = command.main(
        [
            "--from-snapshot",
            str(source),
            "--view",
            "both",
            "--formats",
            "template,svg",
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    assert code == 0, capsys.readouterr().err
    written = {p.name for p in (tmp_path / "out").iterdir()}
    assert {
        "azure-production-groups.infragram.json",
        "azure-production-groups.svg",
        "azure-production-network.infragram.json",
        "azure-production-network.svg",
    } <= written
    assert "4 resource(s) placed in a subnet" in capsys.readouterr().out


#: A file of the user's own that --snapshot-out names by mistake.
MINE = '{"mine": true}\n'


def test_snapshot_out_refuses_a_file_this_tool_did_not_write(tmp_path: Path, capsys) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "export" / "azure.py"
    spec = importlib.util.spec_from_file_location("_export_azure_script", script)
    command = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(command)
    source = save_snapshot(snapshot(), tmp_path / "estate.json")
    notes = tmp_path / "notes.json"
    notes.write_text(MINE, encoding="utf-8")
    args = [
        "--from-snapshot",
        str(source),
        "--formats",
        "template",
        "--output-dir",
        str(tmp_path / "out"),
        "--snapshot-out",
        str(notes),
    ]
    assert command.main(args) == 2
    assert "refusing to overwrite" in capsys.readouterr().err
    assert notes.read_text(encoding="utf-8") == MINE
    assert not (tmp_path / "out").exists(), "refused before anything was written"
    assert command.main([*args, "--force"]) == 0, capsys.readouterr().err
    assert load_snapshot(notes) == load_snapshot(source)
    # the file it wrote is its own now: the next run replaces it without --force
    assert command.main(args) == 0, capsys.readouterr().err


# -- networks in other subscriptions --------------------------------------

HUB_SUB = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def hub_elsewhere(*, read: bool) -> dict:
    """The hub network moved to a connectivity subscription, read or not."""
    data = snapshot()
    old = f"/subscriptions/{SUB}/resourceGroups/rg-hub"
    new = f"/subscriptions/{HUB_SUB}/resourceGroups/rg-hub"
    data = json.loads(re.sub(re.escape(old), new, json.dumps(data), flags=re.IGNORECASE))
    for row in (*data["resources"], *data["resourceGroups"]):
        if row.get("resourceGroup", row.get("name")) == "rg-hub":
            row["subscriptionId"] = HUB_SUB
    if read:
        data["subscriptions"].append(
            {
                "id": HUB_SUB,
                "name": "Connectivity",
                "state": "Enabled",
                "tenantId": TENANT,
                "tenantName": "Contoso",
            }
        )
    else:
        data["resources"] = [r for r in data["resources"] if r["subscriptionId"] != HUB_SUB]
        data["resourceGroups"] = [
            g for g in data["resourceGroups"] if g["subscriptionId"] != HUB_SUB
        ]
    return data


def test_a_peer_in_a_subscription_that_was_read_draws_in_full() -> None:
    plan, summary = blueprint(hub_elsewhere(read=True), ImportOptions())
    root = plan.to_project().topology
    assert parent_name(root, "rg-hub") == "Connectivity"
    assert parent_name(root, "Connectivity") == "Contoso"
    assert ("vnet-app peering", "vnet-hub peering", "solid", "peering", "both") in wires(root)
    assert summary.outside == 0


def test_a_peer_in_a_subscription_that_was_not_read_keeps_its_end() -> None:
    for view, source in (("network", "vnet-app peering"), ("groups", "vnet-app")):
        reset_ids()
        plan, summary = blueprint(hub_elsewhere(read=False), ImportOptions(view=view))
        root = plan.to_project().topology
        assert parent_name(root, "vnet-hub") == "rg-hub"
        assert parent_name(root, "rg-hub") == f"Subscription {HUB_SUB} · not read"
        assert (
            parent_name(root, f"Subscription {HUB_SUB} · not read") == root.name
        )  # not in the tenant
        assert (source, "vnet-hub", "solid", "peering", "both") in wires(root)
        assert summary.outside == 1


def test_a_peer_the_filter_left_out_says_so() -> None:
    root, summary = build(resource_groups=("rg-app",))
    assert parent_name(root, "rg-hub") == "Production · filtered out"
    assert summary.outside == 1


def test_icons_are_the_default_look() -> None:
    plan, _ = blueprint(snapshot())
    assert plan.display == "icon"
    plan, _ = blueprint(snapshot(), ImportOptions(display="card"))
    assert plan.display == "card"


def test_captions_name_the_region_only_when_there_are_several() -> None:
    data = snapshot()
    next(r for r in data["resources"] if r["name"] == "widget-1")["location"] = "westeurope"
    plan, _ = blueprint(data)
    root = plan.to_project().topology
    assert root.first(name="vm-web").attributes["detail"] == "Standard_D2s_v5 · eastus2"
    assert root.first(name="widget-1").attributes["detail"] == "westeurope"


def test_a_frame_with_many_loose_services_is_a_grid() -> None:
    root, _ = build()
    assert root.first(name="rg-app").attributes["grid"] == 3  # 9 loose: 3 x 3
    assert "grid" not in root.first(name="snet-web · 10.1.1.0/24").attributes  # 2 loose


def test_the_grid_lays_rows_and_gives_a_frame_its_own_row() -> None:
    from infragram.builders.scene import Cluster, Style

    style = Style()
    frame = Cluster(label="rg", wrap=3)
    cards = [frame.node(f"n{i}") for i in range(5)]
    inner = frame.cluster("vnet")
    inner.node("vm")
    frame.measure(style)
    frame.position(0, 0, style)
    rows = sorted({card.y for card in cards})
    assert len(rows) == 2  # 3 + 2
    assert [card.x for card in cards[:2]] == [cards[3].x, cards[4].x]  # columns line up
    assert inner.y > max(rows)  # the frame below, alone


def test_an_injected_databricks_workspace_sits_in_its_private_subnet() -> None:
    data = snapshot()
    vnet_id = rid("rg-app", "Microsoft.Network", "virtualNetworks", "vnet-app")
    data["resources"].append(
        resource(
            "rg-app",
            "Microsoft.Databricks",
            "workspaces",
            "dbw-prod",
            properties={
                "parameters": {
                    "customVirtualNetworkId": {"value": vnet_id},
                    "customPublicSubnetName": {"value": "snet-web"},
                    "customPrivateSubnetName": {"value": "snet-aks"},
                }
            },
        )
    )
    plan, _ = blueprint(data)
    root = plan.to_project().topology
    assert parent_name(root, "dbw-prod") == "snet-aks · 10.1.2.0/23"


def test_a_refused_read_says_which_role_is_missing(monkeypatch) -> None:
    from infragram.discovery import azcli

    class Done:
        returncode, stdout = 1, ""
        stderr = 'ERROR: Forbidden({"error":{"code":"AccessDenied"}})'

    monkeypatch.setattr(azcli.shutil, "which", lambda _name: "az")
    monkeypatch.setattr(azcli.subprocess, "run", lambda *a, **k: Done())
    with pytest.raises(AzureCliError, match="Azure Resource Graph query failed: .*Reader"):
        azcli._default_runner(["rest", "--method", "post"])


def test_every_nsg_says_where_it_is_attached() -> None:
    data = snapshot()
    nic = next(r for r in data["resources"] if r["name"] == "nic-web")
    data["resources"].append(
        resource(
            "rg-app",
            "Microsoft.Network",
            "networkSecurityGroups",
            "nsg-vm-web",
            properties={"networkInterfaces": [{"id": nic["id"]}]},
        )
    )
    for view in ("network", "groups"):
        reset_ids()
        plan, _ = blueprint(data, ImportOptions(view=view))
        root = plan.to_project().topology
        assert ("nsg-vm-web", "vm-web", "dashed", "NIC", "forward") in wires(root), view
    reset_ids()
    root = blueprint(data)[0].to_project().topology
    assert [b.label for b in root.first(name="snet-web · 10.1.1.0/24").badges] == ["nsg-web"]
    assert parent_name(root, "nsg-vm-web") == "snet-web · 10.1.1.0/24"
    assert root.first(name="nsg-vm-web").attributes["detail"] == "on NIC · vm-web"


def test_a_group_emptied_into_subnets_is_not_drawn_but_an_empty_one_is() -> None:
    data = snapshot()
    data["resourceGroups"].append(
        {
            "id": f"/subscriptions/{SUB}/resourceGroups/rg-vms",
            "name": "rg-vms",
            "subscriptionId": SUB,
        }
    )
    data["resourceGroups"].append(
        {
            "id": f"/subscriptions/{SUB}/resourceGroups/rg-empty",
            "name": "rg-empty",
            "subscriptionId": SUB,
        }
    )
    for row in data["resources"]:
        if row["name"] == "vm-web":
            row["resourceGroup"] = "rg-vms"
    root = blueprint(data)[0].to_project().topology
    assert root.first(name="rg-vms") is None
    assert parent_name(root, "vm-web") == "snet-web · 10.1.1.0/24"
    assert root.first(name="rg-empty") is not None
    reset_ids()
    root = blueprint(data, ImportOptions(view="groups"))[0].to_project().topology
    assert parent_name(root, "vm-web") == "rg-vms"


def test_an_empty_subnet_widens_so_its_badges_never_cover_its_name() -> None:
    from infragram.builders.architecture import load_icon_set
    from infragram.builders.scene import (
        Cluster,
        ClusterBadge,
        Style,
        corner_row_width,
    )

    style = Style()
    shield = load_icon_set("azure").find("network-security-groups")
    subnet = Cluster(
        label="snet-dbw-host · 10.40.0.0/22",
        width=160,
        height=104,
        badges=[
            ClusterBadge(icon=shield, side="corner", label="NSG · nsg-dbw"),
            ClusterBadge(icon=shield, side="corner", label="NAT gateway · ng-dbw-egress"),
        ],
    )
    width, _ = subnet.measure(style)
    badges_left = width - corner_row_width(["NSG · nsg-dbw", "NAT gateway · ng-dbw-egress"])
    assert badges_left >= subnet._title_width(style)


def test_a_resource_in_several_subnets_says_so() -> None:
    data = snapshot()
    aks = next(r for r in data["resources"] if r["name"] == "aks-prod")
    aks["properties"]["agentPoolProfiles"].append(
        {"vnetSubnetID": subnet_id("rg-app", "vnet-app", "snet-web")}
    )
    root = blueprint(data)[0].to_project().topology
    assert parent_name(root, "aks-prod") == "snet-aks · 10.1.2.0/23"  # drawn once, in the first
    assert root.first(name="aks-prod").attributes["detail"] == "in 2 subnets"


def test_the_first_badge_sits_on_the_corner_point() -> None:
    from infragram.builders.scene import CORNER_BADGE, corner_layout

    first, second = corner_layout(500, ["nsg-web", "ng-egress"])
    icon = CORNER_BADGE["icon"]
    assert first == (
        500,
        500 - icon / 2 - CORNER_BADGE["gap"],
        "end",
    )  # on the corner, name to its left
    assert second[0] + icon / 2 < first[1] - len("nsg-web") * 5  # the next icon clears that name


def test_a_nat_gateway_sits_on_the_top_edge_with_a_bar(tmp_path: Path) -> None:
    data = snapshot()
    web = subnet_id("rg-app", "vnet-app", "snet-web")
    data["resources"].append(
        resource(
            "rg-app",
            "Microsoft.Network",
            "natGateways",
            "ng-egress",
            properties={"subnets": [{"id": web}]},
        )
    )
    plan, _ = blueprint(data)
    subnet = plan.to_project().topology.first(name="snet-web · 10.1.1.0/24")
    assert [(b.label, b.side) for b in subnet.badges] == [
        ("nsg-web", "corner"),
        ("ng-egress", "edge"),
    ]
    result = plan.export(tmp_path, formats=("html", "svg"))
    svg = result.svg.read_text(encoding="utf-8")
    assert 'fill="#50c8e8"' in svg and ">ng-egress</text>" in svg
    assert '"label":"ng-egress","side":"edge"' in result.html.read_text(encoding="utf-8")
