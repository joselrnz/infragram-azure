"""Writing a diagram as described builds the same document as assembling it.

Nesting is containment, an arrow is a wire, and ``infragram compose`` finds
the diagram a file wrote. The older forms keep working underneath.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from infragram.author import Diagram, Edge, latest_diagram, slugify
from infragram.nodes import Group, _scope, reset_ids
from infragram.nodes.azure import compute, databases, networking, storage
from infragram.nodes.frames import azure as az
from infragram.patterns import Blueprint
from infragram.projects import CloudProject

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


@pytest.fixture(autouse=True)
def _clean_scopes():
    _scope.reset()
    reset_ids()
    yield
    _scope.reset()


def _shape(element) -> tuple:
    """What the picture depends on: id, name, kind, children and wires."""
    wires = tuple((c.target, c.kind, c.label, c.direction) for c in element.connections)
    return (
        element.id,
        element.name,
        element.type,
        wires,
        tuple(_shape(child) for child in element.children),
    )


def _azure_described() -> CloudProject:
    with Diagram("Azure hierarchy: tenant to subnet", "The ownership chain.") as diagram:
        with az.Tenant("Contoso - Microsoft Entra tenant"):
            with az.ManagementGroup("Platform management group"):
                with az.Subscription("Production subscription"):
                    with az.ResourceGroup("rg-prod-web"):
                        with az.VNet("vnet-prod - 10.10.0.0/16"):
                            with az.Subnet("snet-web - 10.10.1.0/24"):
                                appgw = networking.ApplicationGateways(
                                    "Application Gateway", "WAF v2"
                                )
                                web = compute.VirtualMachine("Web tier", "VM scale set")
                            with az.Subnet("snet-app - 10.10.2.0/24"), az.AKS("aks-prod"):
                                api = compute.KubernetesServices("API workloads", "AKS pods")
                            with az.Subnet("snet-data - 10.10.3.0/24"):
                                sql = databases.SQLDatabase("Azure SQL", "private endpoint")
                                blobs = storage.StorageAccounts(
                                    "Storage account", "private endpoint"
                                )
        appgw >> Edge("HTTPS") >> web
        web >> Edge("internal") >> api
        api >> Edge("TDS 1433", dashed=True) >> sql
        api >> Edge("blob", dashed=True) >> blobs
    return diagram.to_project()


def _azure_assembled() -> CloudProject:
    reset_ids()
    plan = Blueprint.fresh(
        "azure-hierarchy-tenant-to-subnet",
        "Azure hierarchy: tenant to subnet",
        "The ownership chain.",
    )
    plan.kind = "single-cloud"
    plan.providers = ("azure",)
    (tenant,) = plan.add(az.Tenant("Contoso - Microsoft Entra tenant"))
    mg = tenant >> az.ManagementGroup("Platform management group")
    sub = mg >> az.Subscription("Production subscription")
    rg = sub >> az.ResourceGroup("rg-prod-web")
    vnet = rg >> az.VNet("vnet-prod - 10.10.0.0/16")
    web_subnet = vnet >> az.Subnet("snet-web - 10.10.1.0/24")
    appgw = web_subnet >> networking.ApplicationGateways("Application Gateway", "WAF v2")
    web = web_subnet >> compute.VirtualMachine("Web tier", "VM scale set")
    app_subnet = vnet >> az.Subnet("snet-app - 10.10.2.0/24")
    aks = app_subnet >> az.AKS("aks-prod")
    api = aks >> compute.KubernetesServices("API workloads", "AKS pods")
    data_subnet = vnet >> az.Subnet("snet-data - 10.10.3.0/24")
    sql = data_subnet >> databases.SQLDatabase("Azure SQL", "private endpoint")
    blobs = data_subnet >> storage.StorageAccounts("Storage account", "private endpoint")
    plan.link(appgw, web, label="HTTPS")
    plan.link(web, api, label="internal")
    plan.link(api, sql, label="TDS 1433", kind="dashed")
    plan.link(api, blobs, label="blob", kind="dashed")
    return plan.to_project()


def test_the_described_diagram_is_the_assembled_document() -> None:
    described, assembled = _azure_described(), _azure_assembled()
    assert described.slug == assembled.slug == "azure-hierarchy-tenant-to-subnet"
    assert described.kind == assembled.kind == "single-cloud"
    assert [p.id for p in described.providers] == [p.id for p in assembled.providers] == ["azure"]
    assert _shape(described.topology) == _shape(assembled.topology)


def test_nesting_is_containment_and_two_frames_in_one_with_nest_in_order() -> None:
    with Diagram("Nest") as diagram:
        with az.VNet("vnet") as vnet:
            with az.Subnet("snet"), az.AKS("aks") as aks:
                pod = compute.KubernetesServices("pods")
    (root,) = diagram.roots
    assert root is vnet
    (subnet,) = vnet.children
    assert subnet.type == "subnet-private"
    assert subnet.children == [aks]
    assert aks.children == [pod]


def test_between_nodes_the_arrow_is_a_wire_in_every_direction() -> None:
    with Diagram("Wires"):
        with Group("Zone", "group"):
            a = compute.VirtualMachine("A")
            b = compute.VirtualMachine("B")
            c = compute.VirtualMachine("C")
            d = compute.VirtualMachine("D")
        assert (a >> b) is b
        a << c  # c to a
        a - d  # no arrowheads
        a >> Edge("fan out", dashed=True) >> [b, c]
    assert [(w.target, w.kind, w.label, w.direction) for w in a.connections] == [
        ("b", "solid", "", "forward"),
        ("d", "solid", "", "none"),
        ("b", "dashed", "fan out", "forward"),
        ("c", "dashed", "fan out", "forward"),
    ]
    assert [(w.target, w.direction) for w in c.connections] == [("a", "forward")]
    assert b.connections == []


def test_reverse_edge_and_both_heads() -> None:
    with Diagram("Reverse"):
        with Group("Zone", "group"):
            primary = compute.VirtualMachine("Primary")
            replica = compute.VirtualMachine("Replica")
        primary << Edge("replicates") << replica
        primary >> Edge("peering", both=True) >> replica
    assert [(w.target, w.label, w.direction) for w in replica.connections] == [
        ("primary", "replicates", "forward")
    ]
    assert [(w.target, w.label, w.direction) for w in primary.connections] == [
        ("replica", "peering", "both")
    ]


def test_frames_still_nest_with_the_old_operator_and_never_twice() -> None:
    vnet = az.VNet("vnet")
    subnet = vnet >> az.Subnet("snet")
    vm = subnet >> compute.VirtualMachine("Host")
    assert vnet.children == [subnet] and subnet.children == [vm]
    subnet >> vm
    assert subnet.children == [vm]


def test_layout_hints_are_methods_not_arguments() -> None:
    with Diagram("Hints", direction="right") as diagram:
        with az.VNet("vnet").row():
            with az.Subnet("ordered").keep_order():
                compute.VirtualMachine("Host")
    (vnet,) = diagram.roots
    assert vnet.attributes["flow"] == "row"
    assert vnet.children[0].attributes["arrange"] == "manual"
    assert diagram.topology().attributes["flow"] == "row"


def test_slug_providers_and_kind_are_inferred() -> None:
    project = _azure_described()
    assert project.slug == slugify("Azure hierarchy: tenant to subnet")
    assert project.description == "The ownership chain."
    assert project.default_library == "azure"
    assert project.presentation.display == "icon"


def test_an_empty_diagram_says_so() -> None:
    from infragram.compose import ComposeError

    with Diagram("Nothing") as diagram:
        pass
    with pytest.raises(ComposeError, match="no elements"):
        diagram.to_project()


def test_the_compose_command_picks_up_the_diagram_a_file_wrote(tmp_path: Path) -> None:
    spec = tmp_path / "spec.py"
    spec.write_text(
        "from infragram.author import Diagram, Edge\n"
        "from infragram.nodes.frames import azure as az\n"
        "from infragram.nodes.azure import compute\n"
        "with Diagram('One frame, one host'):\n"
        "    with az.ResourceGroup('rg'):\n"
        "        compute.VirtualMachine('Host', 'one')\n",
        encoding="utf-8",
    )
    runner_path = ROOT / "scripts" / "export" / "compose.py"
    loader = importlib.util.spec_from_file_location("compose_runner", runner_path)
    runner = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(runner)
    namespace = runner.load_spec(spec)
    project = runner.project_from(namespace)
    assert isinstance(project, CloudProject)
    assert project.slug == "one-frame-one-host"
    assert [element.type for element in project.topology.walk()][1:] == [
        "resource-group",
        "virtual-machine",
    ] or project.topology.children[0].type == "resource-group"
    assert latest_diagram() is not None


@pytest.mark.parametrize("name", sorted(p.name for p in (ROOT / "examples").glob("*.py")))
def test_every_shipped_example_builds_and_passes_the_picture_checks(name: str) -> None:
    from infragram.exports import render_project_svg

    runner_path = ROOT / "scripts" / "export" / "compose.py"
    loader = importlib.util.spec_from_file_location("compose_runner", runner_path)
    runner = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(runner)
    namespace = runner.load_spec(ROOT / "examples" / name)
    project = runner.project_from(namespace)
    assert len(list(project.topology.walk())) > 8
    checker_path = ROOT / "skills" / "infragram-azure" / "scripts" / "project_check.py"
    spec = importlib.util.spec_from_file_location("project_check", checker_path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    errors: list[str] = []
    checker.check_svg(render_project_svg(project), errors, project.model_dump(mode="json"))
    assert not errors, errors


def test_explicit_placement_takes_a_node_back_from_the_open_frame() -> None:
    from infragram.nodes.azure import compute

    with Diagram("Claim") as diagram:
        with Group("Outer", "group") as outer:
            inner = Group("Inner", "group")
            node = compute.VirtualMachine("Host")  # adopted by Outer on construction
            inner >> node  # explicitly placed: leaves Outer
    assert outer.children == [inner]
    assert inner.children == [node]
    assert diagram.roots == [outer]


def test_a_pattern_attached_inside_a_frame_nests_once() -> None:
    from infragram.patterns import Pattern

    class Tier(Pattern):
        """One subnet holding a web tier and its database, built once."""

        def __init__(self, name: str, letter: str) -> None:
            super().__init__(name)
            self.letter = letter

        def build(self):
            subnet = az.Subnet(f"snet-{self.letter}")
            self.part("web", subnet >> compute.VirtualMachine("Web servers", "scale set"))
            self.part("db", subnet >> databases.SQLDatabase("Azure SQL", "zone redundant"))
            return subnet

    with Diagram("Pattern in a frame") as diagram:
        with az.VNet("vnet-prod 10.10.0.0/16").row() as vnet:
            tiers = [Tier("Tier A", "a").attach(vnet), Tier("Tier B", "b").attach(vnet)]
        tiers[0]["web"] >> Edge("SQL") >> tiers[0]["db"]
    project = diagram.to_project()
    seen: dict[str, int] = {}
    for element in project.topology.walk():
        seen[element.id] = seen.get(element.id, 0) + 1
    assert all(count == 1 for count in seen.values()), {k: v for k, v in seen.items() if v > 1}
    assert [child.type for child in vnet.children] == ["subnet-private", "subnet-private"]
    assert all(len(child.children) == 2 for child in vnet.children)
    assert diagram.roots == [vnet]
