"""A two-region AKS fleet behind one Front Door.

Both regions run the same workloads. Front Door picks the healthy one, each
cluster keeps its own ingress and node pools, and the data tier fails over
between them. The Kubernetes frames are drawn inside the Azure ones, because
each cluster runs in that region's network.
"""

from pathlib import Path

from infragram.author import Diagram, Edge
from infragram.nodes import Group, infragram as shared
from infragram.nodes.azure import (
    containers,
    databases,
    devops,
    networking,
    security,
    storage,
)
from infragram.nodes.frames import azure as az, kubernetes as k8s
from infragram.nodes.kubernetes import resources as kr


def region(name: str, cidr: str, tier: str):
    """One region: a VNet, a cluster with two node pools, and its data tier."""
    with az.Region(name).column().keep_order():
        with az.VNet(f"vnet-{tier} · {cidr}").row().keep_order():
            with az.Subnet("snet-ingress"):
                gateway = networking.ApplicationGateways("App Gateway", "WAF v2 · TLS")
            with az.Subnet("snet-nodes"):
                with k8s.Cluster(f"aks-{tier}").column().keep_order():
                    with k8s.NodePool("system pool · 3 nodes"):
                        ingress = kr.Ing("ingress-nginx", "internal LB")
                    with k8s.Namespace("orders").row().keep_order():
                        api = kr.Deploy("orders-api", "6 replicas · HPA")
                        worker = kr.Sts("orders-worker", "stateful · 3")
            with generic_subnet(tier):
                sql = databases.SQLDatabase("Azure SQL", "business critical")
                blobs = storage.StorageAccounts("Storage", "ZRS")
    return gateway, ingress, api, worker, sql, blobs


def generic_subnet(tier: str):
    return az.Subnet(f"snet-data-{tier}")


with Diagram(
    "Multi-region AKS fleet",
    "Two clusters, one front door, data that fails over.",
    slug="aks-fleet",
    providers=("azure", "kubernetes"),
    direction="down",
) as diagram:
    with Group("", "group").row().keep_order():
        users = shared.identity.PublicUsers("Customers", "worldwide")
        with Group("", "group").column().keep_order():
            with Group("Global edge", "group").row().keep_order():
                door = networking.FrontDoorAndCDNProfiles("Front Door", "anycast · health probes")
                dns = networking.DNSZones("Azure DNS", "contoso.com")
            with az.Subscription("Workload subscription").row().keep_order():
                primary = region("East US 2 · primary", "10.10.0.0/16", "eus2")
                standby = region("West Europe · standby", "10.20.0.0/16", "weu")
            with Group("Platform services", "group").row().keep_order():
                registry = containers.ContainerRegistries("Container Registry", "geo-replicated")
                vault = security.KeyVaults("Key Vault", "per-region replica")
                pipeline = devops.AzureDevOps("Azure DevOps", "one deploy, both clusters")

    p_gw, p_ing, p_api, p_worker, p_sql, p_blob = primary
    s_gw, s_ing, s_api, s_worker, s_sql, s_blob = standby

    users >> Edge("HTTPS 443") >> door
    dns >> Edge("CNAME", dashed=True) >> door
    door >> Edge("primary") >> p_gw
    door >> Edge("failover", dashed=True) >> s_gw

    for gw, ing, api, worker, sql, blob in (primary, standby):
        gw >> Edge("TLS") >> ing
        ing >> Edge("route") >> api
        api >> Edge("queue") >> worker
        worker >> Edge("TDS 1433") >> sql
        worker >> Edge("blobs") >> blob

    p_sql >> Edge("geo-replication", dashed=True) >> s_sql
    p_blob >> Edge("object replication", dashed=True) >> s_blob
    registry >> Edge("pull images", dashed=True) >> p_api
    registry >> Edge("pull images", dashed=True) >> s_api
    pipeline >> Edge("deploy") >> registry
    vault >> Edge("secrets", dashed=True) >> p_api
    vault >> Edge("secrets", dashed=True) >> s_api

if __name__ == "__main__":
    print(diagram.export(Path("dist"), display="both").html)
