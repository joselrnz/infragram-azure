from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from infragram import compose
from infragram.exports import render_project_html
from infragram.nodes import Frame, Group, azure, infragram as shared, kubernetes, reset_ids
from infragram.nodes.azure import compute, databases, networking
from infragram.nodes.frames import (
    azure as azure_frames,
    generic,
    kubernetes as kubernetes_frames,
)
from infragram.projects import CloudProject

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


@pytest.fixture(autouse=True)
def _fresh_ids():
    reset_ids()


def _azure_estate():
    subscription = azure_frames.Subscription("Production subscription")
    vnet = (
        subscription
        >> azure_frames.ResourceGroup("rg-prod")
        >> azure_frames.VNet("vnet-prod 10.10.0.0/16")
    )
    web_subnet = vnet >> azure_frames.Subnet("snet-web")
    app_subnet = vnet >> azure_frames.Subnet("snet-app")
    lb = web_subnet >> networking.LoadBalancers("Load balancer", "HTTPS :443")
    web = app_subnet >> compute.VirtualMachine("Web servers", "scale set")
    db = app_subnet >> databases.SQLDatabase("Azure SQL", "zone redundant")
    users = shared.identity.PublicUsers("Users", "internet")
    users.to(lb, label="HTTPS")
    lb.to(web, label="HTTP")
    web.to(db, label="SQL", direction="both")
    return [users, subscription], {"lb": lb, "web": web, "db": db, "vnet": vnet}


def test_frames_carry_gallery_identity_and_stay_frames_when_empty() -> None:
    vnet = azure_frames.VNet("Prod VNet")
    assert vnet.is_frame
    assert vnet.type == "network"
    assert vnet.component is not None
    assert vnet.component.icon_ref == "infragram:custom-boundary-azure-vnet"
    assert vnet.attributes["editor_frame_group"] == "azure"
    assert isinstance(vnet, Frame)
    dmz = generic.DMZ("DMZ", flow="row")
    assert dmz.type == "dmz" and dmz.attributes["flow"] == "row"
    assert (
        kubernetes_frames.Namespace("payments").component.service_id
        == "custom-boundary-kubernetes-namespace"
    )
    assert azure_frames.Subnet("snet-web").type == "subnet-private"


def test_qualify_writes_components_from_node_classes() -> None:
    zone = Group("Edge", "vnet")
    aks = zone >> azure.KubernetesServices("AKS", "private")
    mainframe = zone >> shared.compute.Mainframe("IBM z16", "z/OS")
    compose.qualify(zone)
    assert aks.component is not None
    assert aks.component.icon_ref == "azure:kubernetes-services"
    assert mainframe.component.icon_ref == "infragram:mainframe"
    assert zone.component is None  # a plain Group stays theme-styled by kind


def test_qualify_rejects_unknown_services_with_a_hint() -> None:
    node = azure.KubernetesServices("AKS")
    node.attributes["icon"] = "kubernetes-servicez"
    with pytest.raises(compose.ComposeError, match="kubernetes-services"):
        compose.qualify(node)


def test_infers_providers_and_kind() -> None:
    elements, _ = _azure_estate()
    project = compose.to_project(
        elements, slug="three-tier", title="Three tier", description="Azure estate."
    )
    assert project.provider_ids == ("azure",)
    assert project.kind == "single-cloud"
    assert project.default_library == "azure"
    assert project.presentation.size == "fit"
    assert project.topology.id == "root" and len(project.topology.children) == 2

    cluster = kubernetes_frames.Cluster("aks-prod")
    cluster >> kubernetes.Deploy("api")
    vnet = azure_frames.VNet("hub") >> azure.Firewalls("Azure Firewall")
    hybrid = compose.to_project([cluster, vnet], slug="hybrid", title="Hybrid", description="x.")
    assert hybrid.kind == "hybrid" and set(hybrid.provider_ids) == {"kubernetes", "azure"}

    workload = kubernetes.Deploy("api")
    platform = compose.to_project(workload, slug="k8s", title="K8s", description="x.")
    assert platform.kind == "platform" and platform.provider_ids == ("kubernetes",)
    assert compose.infer_kind(("azure", "kubernetes")) == "hybrid"


def test_direction_survives_from_dsl_to_document() -> None:
    elements, refs = _azure_estate()
    project = compose.to_project(elements, slug="dir", title="Dir", description="x.")
    web = project.topology.first(id=refs["web"].id)
    assert web is not None
    assert web.connections[0].direction == "both"
    dumped = json.loads(project.model_dump_json())
    assert json.dumps(dumped).count('"direction": "both"') == 1


def test_composed_project_renders_with_automatic_placement() -> None:
    elements, refs = _azure_estate()
    project = compose.to_project(elements, slug="placed", title="Placed", description="x.")
    for element in project.topology.walk():
        assert "editor_x" not in element.attributes
    html = render_project_html(project)
    # The graph state is the object that names the project slug; the library
    # payload before it also carries "nodes" (starter stacks), so anchor here.
    anchor = html.index('"projectSlug"')
    state = json.JSONDecoder().raw_decode(html[html.rfind("{", 0, anchor) :])[0]
    boundaries, nodes = state["boundaries"], state["nodes"]
    assert {b["kind"] for b in boundaries} >= {
        "subscription",
        "resource-group",
        "network",
        "subnet-private",
    }
    assert all(b.get("frameGroup") == "azure" for b in boundaries)
    assert all(b["iconUri"] for b in boundaries), "gallery frames should carry their glyphs"
    assert len(nodes) == 4
    assert all(n["iconUri"] for n in nodes), "every node class should resolve artwork"
    assert len({(n["x"], n["y"]) for n in nodes}) == 4, "cards should not stack"
    by_id = {n["id"]: n for n in nodes}
    assert by_id[refs["lb"].id]["componentQualifiedId"] == "azure:load-balancers"


def test_compose_export_defaults_and_root_wrapping(tmp_path: Path) -> None:
    single = shared.compute.Mainframe("IBM z16")
    result = compose.export(
        single,
        tmp_path,
        formats=("template",),
        slug="one",
        title="One",
        description="x.",
        providers=["azure"],
    )
    saved = CloudProject.load(result.template)
    assert saved.topology.children[0].component.icon_ref == "infragram:mainframe"
    assert saved.provider_ids == ("azure",)
    # A purely neutral estate is filed under the Azure library in this
    # edition, and a provider frame alone is enough to name its library.
    neutral = compose.to_project(
        shared.compute.Mainframe("z"), slug="x", title="x", description="x."
    )
    assert neutral.provider_ids == ("azure",) and neutral.kind == "single-cloud"
    framed = compose.to_project(
        kubernetes_frames.Cluster("empty"), slug="y", title="y", description="y."
    )
    assert framed.provider_ids == ("kubernetes",) and framed.kind == "platform"
    with pytest.raises(compose.ComposeError):
        compose.to_project([], slug="z", title="z", description="z.")


@pytest.mark.parametrize("example", sorted((ROOT / "examples").glob("*.py")))
def test_shipped_examples_compose_and_export_a_template(example: Path, tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/export/compose.py"),
            str(example),
            "--formats",
            "template",
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={
            **__import__("os").environ,
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONIOENCODING": "utf-8",
        },
    )
    assert completed.returncode == 0, completed.stderr
    assert re.search(r"^PROJECT ", completed.stdout, re.M), completed.stdout
    template = next(tmp_path.glob("*.infragram.json"))
    project = CloudProject.load(template)
    assert len(project.topology.index()) > 8


def test_layout_orders_siblings_by_their_connections() -> None:
    """In the shipped tenant-to-VM example the Application Gateway sits over
    the web tier it feeds, the three subnets read left to right along the
    traffic (web, app, data), and every card keeps its own artwork id
    through the reorder."""
    import runpy

    from infragram.author import latest_diagram

    spec = runpy.run_path(str(ROOT / "examples/azure_tenant_to_vm.py"), run_name="__spec__")
    project = spec.get("PROJECT") or latest_diagram().to_project()
    html = render_project_html(project)
    anchor = html.index('"projectSlug"')
    state = json.JSONDecoder().raw_decode(html[html.rfind("{", 0, anchor) :])[0]
    x = {node["name"]: node["x"] for node in state["nodes"]}
    y = {node["name"]: node["y"] for node in state["nodes"]}
    # The web subnet stacks: the gateway over the web tier it feeds.
    assert y["Application Gateway"] < y["Web tier"]
    # The subnets sit side by side along the traffic: web, then app, then data.
    assert x["Web tier"] < x["API workloads"] < x["Azure SQL"]
    assert len({(node["x"], node["y"]) for node in state["nodes"]}) == len(state["nodes"])
    # and the pairing survived the layout: every card kept its own artwork id
    ids = {node["name"]: node["componentQualifiedId"] for node in state["nodes"]}
    assert ids["Azure SQL"] == "azure:sql-database" and ids["Web tier"] == "azure:virtual-machine"
    assert ids["Application Gateway"] == "azure:application-gateways"


def test_direction_down_stacks_the_top_level_frames() -> None:
    from infragram.author import Diagram
    from infragram.nodes.frames import generic

    def placed(direction: str | None) -> dict[str, dict]:
        reset_ids()
        options = {"direction": direction} if direction else {}
        with Diagram("Tiers", slug="tiers", providers=("azure",), **options) as diagram:
            with generic.Environment("One").row():
                compute.VirtualMachine("A")
            with generic.Environment("Two").row():
                compute.VirtualMachine("B")
        html = render_project_html(diagram.to_project())
        anchor = html.index('"projectSlug"')
        state = json.JSONDecoder().raw_decode(html[html.rfind("{", 0, anchor) :])[0]
        return {b["name"]: b for b in state["boundaries"]}

    side = placed(None)
    assert side["Two"]["x"] >= side["One"]["x"] + side["One"]["width"], "default: side by side"
    assert side["Two"]["y"] == side["One"]["y"]
    down = placed("down")
    assert down["Two"]["y"] >= down["One"]["y"] + down["One"]["height"], "down: stacked"
    assert down["Two"]["x"] == down["One"]["x"]
