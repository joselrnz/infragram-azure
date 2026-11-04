"""What changed lately and what a review would raise, on the cards they concern.

Nothing here calls Azure. The rows are shaped like Resource Graph's own
``resourcechanges``, ``securityresources`` and ``policyresources`` rows, and
the session is driven through a fake ``az``. What has to hold: Azure's own
bookkeeping is not called a change, a finding raised through several
assignments is one finding, and each lands on the card or frame a reader
would look at -- a NIC's on its VM, a subnet's on its subnet, a deleted
resource's on its resource group.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infragram.discovery import AzureCliError, AzureSession, ImportOptions, blueprint
from infragram.discovery.changes import read_changes
from infragram.discovery.findings import read_findings
from infragram.nodes import reset_ids

SUB = "11111111-2222-3333-4444-555555555555"
TAKEN = "2026-10-30T09:00:00+00:00"


def rid(*path: str) -> str:
    return f"/subscriptions/{SUB}/resourceGroups/rg-app/providers/{'/'.join(path)}"


VNET = rid("Microsoft.Network", "virtualNetworks", "vnet-app")
SUBNET = f"{VNET}/subnets/snet-web"
VM = rid("Microsoft.Compute", "virtualMachines", "vm-web")
NIC = rid("Microsoft.Network", "networkInterfaces", "nic-web")
NSG = rid("Microsoft.Network", "networkSecurityGroups", "nsg-web")
STORAGE = rid("Microsoft.Storage", "storageAccounts", "stprod")
GONE = rid("Microsoft.Compute", "disks", "Disk-Old")


def row(resource_id: str, properties: dict) -> dict:
    parts = resource_id.split("/providers/")[1].split("/")
    return {
        "id": resource_id,
        "name": parts[-1],
        "type": f"{parts[0]}/{parts[1]}".lower(),
        "location": "eastus2",
        "resourceGroup": "rg-app",
        "subscriptionId": SUB,
        "properties": properties,
    }


def change(target: str, kind: str, when: str, changes: dict | None = None, **extra) -> dict:
    return {
        "targetId": target,
        "changeType": kind,
        "changeTime": when,
        "changes": changes,
        **extra,
    }


def moved(before, after, category: str = "User") -> dict:
    return {"previousValue": before, "newValue": after, "changeCategory": category}


def estate() -> dict:
    return {
        "format": "infragram.azure-snapshot/1",
        "taken": TAKEN,
        "subscriptions": [{"id": SUB, "name": "Production", "state": "Enabled"}],
        "resourceGroups": [{"name": "rg-app", "subscriptionId": SUB}],
        "resources": [
            row(
                VNET,
                {
                    "addressSpace": {"addressPrefixes": ["10.1.0.0/16"]},
                    "subnets": [
                        {
                            "id": SUBNET,
                            "name": "snet-web",
                            "properties": {"addressPrefix": "10.1.1.0/24"},
                        }
                    ],
                },
            ),
            row(VM, {"networkProfile": {"networkInterfaces": [{"id": NIC}]}}),
            row(
                NIC,
                {
                    "virtualMachine": {"id": VM},
                    "ipConfigurations": [{"properties": {"subnet": {"id": SUBNET}}}],
                },
            ),
            row(NSG, {"subnets": [{"id": SUBNET}]}),
            row(STORAGE, {"networkAcls": {"defaultAction": "Allow"}}),
        ],
        "changes": [
            change(
                STORAGE,
                "Update",
                "2026-10-29T14:02:11.123Z",
                {"properties.networkAcls.defaultAction": moved("Deny", "Allow")},
                changedBy="alice@contoso.com",
                clientType="Azure Portal",
            ),
            change(STORAGE, "Update", "2026-10-28T10:00:00Z", {"etag": moved("a", "b")}),
            change(
                NIC, "Update", "2026-10-27T08:00:00Z", {"properties.dnsSettings": moved("", "x")}
            ),
            change(SUBNET, "Update", "2026-10-26T08:00:00Z", {"properties.nsg": moved("", NSG)}),
            change(
                NSG, "Update", "2026-10-25T08:00:00Z", {"properties.securityRules[0]": moved(1, 2)}
            ),
            change(GONE, "Delete", "2026-10-24T08:00:00Z"),
            change(VM, "Create", "2026-10-20T08:00:00Z"),
        ],
        "findings": {
            "defender": [
                {
                    "id": f"{STORAGE}/providers/Microsoft.Security/assessments/aaa",
                    "title": "Storage accounts should restrict network access",
                    "severity": "Medium",
                    "remediation": "Set the  default action to Deny.",
                },
                {
                    "id": "ignored",
                    "resourceId": STORAGE.upper(),
                    "title": "Storage account public access should be disallowed",
                    "severity": "High",
                },
                {
                    "id": f"{SUBNET}/providers/Microsoft.Security/assessments/bbb",
                    "title": "Subnets should be associated with a network security group",
                    "severity": "Low",
                },
            ],
            "policy": [
                {
                    "resourceId": VM,
                    "assignmentId": "/providers/assignments/one",
                    "assignment": "one",
                    "definitionId": "/providers/definitions/backup",
                    "definition": "0123abcd-0000-0000-0000-000000000000",
                },
                {
                    "resourceId": VM,
                    "assignmentId": "/providers/assignments/two",
                    "definitionId": "/providers/definitions/backup",
                    "definition": "0123abcd-0000-0000-0000-000000000000",
                },
                {
                    "resourceId": VM,
                    "definition": "0f1e2d3c-0000-0000-0000-000000000000",
                    "reference": "vmShouldUseManagedDisks",
                },
            ],
            "names": [
                {"id": "/providers/assignments/one", "name": "Security baseline"},
                {"id": "/providers/definitions/backup", "name": "Azure Backup should be enabled"},
            ],
        },
    }


@pytest.fixture(autouse=True)
def _fresh_ids():
    reset_ids()
    yield
    reset_ids()


def element(root, name: str):
    found = [item for item in root.walk() if item.name.split(" · ")[0] == name]
    assert found, f"{name!r} is not drawn"
    return found[0]


# -- the rows -------------------------------------------------------------


def test_changes_read_newest_first_without_azures_own_bookkeeping() -> None:
    changes = read_changes(estate()["changes"])
    assert [(c.name, c.kind) for c in changes] == [
        ("stprod", "Update"),
        ("nic-web", "Update"),
        ("snet-web", "Update"),
        ("nsg-web", "Update"),
        ("Disk-Old", "Delete"),
        ("vm-web", "Create"),
    ]
    first = changes[0]
    assert first.when == "2026-10-29T14:02:11Z"
    assert (first.by, first.client) == ("alice@contoso.com", "Azure Portal")
    assert [(p.path, p.before, p.after) for p in first.properties] == [
        ("properties.networkAcls.defaultAction", "Deny", "Allow")
    ]
    assert changes[-2].target == GONE.lower()


def test_a_change_names_its_first_properties_cut_to_a_line() -> None:
    many = {f"properties.p{i}": moved("x" * 300, i) for i in range(8)}
    many["properties.a"] = moved(1, 2, category="System")
    (one,) = read_changes([change(STORAGE, "Update", "2026-10-29T00:00:00Z", many)])
    assert len(one.properties) == 5 and one.more == 4
    assert all(p.path != "properties.a" for p in one.properties)
    assert len(one.properties[0].before) == 120 and one.properties[0].before.endswith("…")


def test_findings_are_named_ranked_and_never_counted_twice() -> None:
    found = estate()["findings"]
    by_resource = read_findings(found["defender"], found["policy"], found["names"])
    storage = by_resource[STORAGE.lower()]
    assert [(f.severity, f.title) for f in storage] == [
        ("High", "Storage account public access should be disallowed"),
        ("Medium", "Storage accounts should restrict network access"),
    ]
    assert storage[1].detail == "Set the default action to Deny."
    assert [f.severity for f in by_resource[SUBNET.lower()]] == ["Low"]
    vm = by_resource[VM.lower()]
    assert [(f.source, f.title, f.detail) for f in vm] == [
        ("Policy", "Azure Backup should be enabled", "Assigned as Security baseline"),
        ("Policy", "Vm should use managed disks", ""),
    ]


# -- on the picture -------------------------------------------------------


def test_each_change_goes_on_the_card_or_frame_it_concerns() -> None:
    plan, summary = blueprint(estate(), ImportOptions(view="network"))
    root = plan.to_project().topology

    storage = element(root, "stprod").attributes["changes"]
    assert storage["read"] == TAKEN and storage["count"] == 1
    assert storage["items"][0]["by"] == "alice@contoso.com"
    assert "part" not in storage["items"][0]
    # the NIC is not drawn: its change is the VM's, naming the NIC
    vm = element(root, "vm-web").attributes["changes"]["items"]
    assert [(item["kind"], item.get("part")) for item in vm] == [
        ("Update", "nic-web"),
        ("Create", None),
    ]
    # the subnet's own change, and the NSG drawn as a badge on it
    subnet = element(root, "snet-web").attributes["changes"]["items"]
    assert [item.get("part") for item in subnet] == [None, "nsg-web"]
    # the deleted disk has no card: its resource group says it went
    (gone,) = element(root, "rg-app").attributes["changes"]["items"]
    assert (gone["kind"], gone["part"]) == ("Delete", "Disk-Old")

    assert (summary.changes, summary.changed, summary.deleted) == (6, 4, 1)
    assert "6 change(s) in the last 14 days on 4 card(s) or frame(s), 1 of them deletes" in (
        summary.lines()
    )


def test_each_finding_goes_on_its_card_worst_first() -> None:
    plan, summary = blueprint(estate(), ImportOptions(view="network"))
    root = plan.to_project().topology
    storage = element(root, "stprod").attributes["findings"]
    assert storage["count"] == 2
    assert [item["severity"] for item in storage["items"]] == ["High", "Medium"]
    assert element(root, "snet-web").attributes["findings"]["items"][0]["severity"] == "Low"
    assert summary.flagged == 3
    assert (
        "5 security finding(s) on 3 card(s) or frame(s): 1 high, 1 medium, 1 low, 2 from Policy"
        in summary.lines()
    )


def test_in_the_groups_view_a_subnets_change_is_its_networks() -> None:
    plan, _ = blueprint(estate(), ImportOptions(view="groups"))
    root = plan.to_project().topology
    items = element(root, "vnet-app").attributes["changes"]["items"]
    assert [item.get("part") for item in items] == ["snet-web"]


def test_a_snapshot_without_them_draws_as_before() -> None:
    old = {key: value for key, value in estate().items() if key not in ("changes", "findings")}
    plan, summary = blueprint(old, ImportOptions(view="network"))
    root = plan.to_project().topology
    assert not any("changes" in e.attributes or "findings" in e.attributes for e in root.walk())
    assert not any("change" in line or "finding" in line for line in summary.lines())


# -- the read -------------------------------------------------------------


class FakeAz:
    """Answers each Resource Graph query by the table it reads."""

    def __init__(self, refuse: str = "") -> None:
        self.refuse = refuse
        self.tables: list[str] = []

    def __call__(self, args):
        body = json.loads(Path(args[args.index("--body") + 1][1:]).read_text(encoding="utf-8"))
        table = body["query"].split()[0]
        self.tables.append(table)
        if table == self.refuse:
            raise AzureCliError("Azure Resource Graph query failed: AuthorizationFailed")
        rows = {
            "resourcechanges": [change(STORAGE, "Delete", "2026-10-29T00:00:00Z")],
            "resourcecontainers": [{"name": "rg-app", "subscriptionId": SUB}],
        }
        return json.dumps({"data": rows.get(table, [])})


def test_the_snapshot_reads_changes_and_findings_too() -> None:
    fake = FakeAz()
    taken = AzureSession(fake).snapshot([{"id": SUB, "name": "Production"}])
    assert fake.tables == [
        "resourcecontainers",
        "resources",
        "resourcechanges",
        "securityresources",
        "policyresources",
        "policyresources",
    ]
    assert taken["changes"][0]["changeType"] == "Delete"
    assert set(taken["findings"]) == {"defender", "policy", "names"}
    assert "unread" not in taken


def test_a_refused_extra_is_noted_and_the_rest_kept() -> None:
    taken = AzureSession(FakeAz(refuse="securityresources")).snapshot(
        [{"id": SUB, "name": "Production"}]
    )
    assert "findings" not in taken and "changes" in taken
    assert "AuthorizationFailed" in taken["unread"]["findings"]
    snapshot = dict(estate(), unread=taken["unread"])
    _, summary = blueprint(snapshot, ImportOptions(view="groups"))
    assert any(line.startswith("findings not read: ") for line in summary.lines())
    skipped = AzureSession(FakeAz()).snapshot(
        [{"id": SUB, "name": "Production"}], changes=False, findings=False
    )
    assert "changes" not in skipped and "findings" not in skipped


# -- a subscription the identity may not read ------------------------------

CLOSED = "99999999-0000-0000-0000-000000000000"


class TwoSubscriptions:
    """Resource Graph as it answers for an open and a closed subscription:
    asked of both, it quietly answers for the open one; asked of the closed
    one alone, it refuses."""

    def __call__(self, args):
        body = json.loads(Path(args[args.index("--body") + 1][1:]).read_text(encoding="utf-8"))
        if body["subscriptions"] == [CLOSED]:
            raise AzureCliError(
                "Azure Resource Graph query failed: Azure refused the read: the signed-in "
                "identity needs at least the Reader role on the subscription"
            )
        if "resourcegroups" in body["query"]:
            return json.dumps({"data": [{"name": "rg-app", "subscriptionId": SUB}]})
        return json.dumps({"data": []})


def test_a_subscription_azure_will_not_read_is_drawn_as_not_read() -> None:
    chosen = [{"id": SUB, "name": "Production"}, {"id": CLOSED, "name": "Closed"}]
    taken = AzureSession(TwoSubscriptions()).snapshot(chosen, changes=False, findings=False)
    assert list(taken["unreadable"]) == [CLOSED]
    plan, summary = blueprint(taken, ImportOptions(view="groups"))
    names = [element.name for element in plan.to_project().topology.walk()]
    assert "Closed · not read" in names and "Production" in names
    assert any(
        line.startswith("subscription Closed not read: ") and "Reader role" in line
        for line in summary.lines()
    )
