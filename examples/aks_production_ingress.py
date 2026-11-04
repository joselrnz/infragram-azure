"""Production ingress on AKS, drawn with panels.

Shows panels (compose.md, Panels): boxes that carry their own facts as
compartments side by side and stacked, several detail lines, an ellipse for
the customer, a hexagon for the managed control plane, a note for the
network contract, and tones that mean something, which the legend names.
Front Door's public front end stands beside its origin rules, with what
must never happen under both; each node pool's worker carries its pod.

Run from any directory::

    PYTHONPATH="<plugin root>/src" python -m infragram compose \\
        examples/aks_production_ingress.py --formats template,html,svg,png --output-dir dist
"""

from __future__ import annotations

from pathlib import Path

from infragram.author import Diagram, Edge
from infragram.nodes import Box
from infragram.nodes.azure import compute, databases, networking as net, security
from infragram.nodes.frames import azure as az

SLUG = "aks-production-ingress"
TITLE = "AKS production ingress, nodes and pods"
DESCRIPTION = (
    "One public front end through Front Door and an Application Gateway to "
    "AKS, private node pools without public addresses, data over private "
    "endpoints, and egress through a NAT gateway."
)
#: The request path, the control and egress paths.
REQUEST = "#cc7631"
CONTROL = "#4a77ad"
EGRESS = "#7a5cb0"

with Diagram(
    TITLE,
    DESCRIPTION,
    slug=SLUG,
    display="card",
    legend=(("solid", "customer request"), ("dashed", "control, egress or overflow")),
    tones={
        "edge": "public edge / ingress",
        "private": "private network / Kubernetes",
        "internal": "cluster-internal service / managed data",
        "correction": "target correction required",
        "blocker": "launch blocker",
    },
) as diagram:
    customer = (
        Box("1 · Customer", "HTTPS 443\nsigned in with Entra ID").shape("ellipse").tone("internal")
    )
    front_door = (
        net.FrontDoorAndCDNProfiles(
            "2 · Front Door Premium", "WAF · DDoS · rate limits\nthe only public surface"
        )
        .tone("edge")
        .section("Origin = Application Gateway", "over Private Link", tone="edge")
    )
    with az.Subscription("Production"), az.ResourceGroup("rg-prod-app").column():
        control = (
            Box(
                "AKS control plane",
                "managed API · private cluster\nEntra RBAC · authorised IP ranges",
            )
            .shape("hexagon")
            .tone("managed")
        )
        with az.VNet("vnet-prod · 10.20.0.0/16").column().keep_order():
            with az.Subnet("snet-appgw"):
                gateway = (
                    net.ApplicationGateways(
                        "3 · Application Gateway for Containers", "one listener per hostname"
                    )
                    .tone("edge")
                    .section("Public frontend", "HTTPS 443 · WAF policy", tone="edge")
                    .section(
                        "AKS backends", "health-probed pods · TLS kept", tone="private", beside=True
                    )
                    .section(
                        "Direct origin access must fail",
                        "Front Door ID header still needs proof",
                        tone="blocker",
                    )
                )
            with az.Subnet("snet-aks-nodes"):
                workers = [
                    compute.KubernetesServices(f"Node pool {name}", "Standard_D4s_v5 · zones 1-3")
                    .tone("private")
                    .section(
                        "No public IP · Azure CNI overlay",
                        "egress through NAT only",
                        tone="private",
                    )
                    .section(pod, note, tone=tone)
                    for name, pod, note, tone in (
                        ("system", "CoreDNS · metrics-server", "two replicas", "private"),
                        ("app", "web · 3 replicas · :3000", "PDB minAvailable 2", "private"),
                        (
                            "jobs",
                            "export · nightly",
                            "required before production data",
                            "correction",
                        ),
                    )
                ]
            nat = net.NAT("NAT gateway", "outbound static IP only\nnever inbound").tone("managed")
            Box(
                "Network contract", "gateway-only ingress · default deny\nno public node ports"
            ).shape("note").tone("correction")
        with az.VNet("vnet-prod-data"), az.Subnet("snet-endpoints"):
            database = (
                databases.AzureDatabasePostgreSQLServer(
                    "PostgreSQL flexible server", "zone-redundant HA"
                )
                .tone("internal")
                .section("Private endpoint only", "verify-full TLS", tone="internal")
            )
            vault = security.KeyVaults("Key Vault", "workload identity\nCSI secrets driver").tone(
                "internal"
            )
    Box(
        "Current implementation: NO-GO",
        "1. the private cluster and the Gateway exist only in source\n"
        "2. Front Door origin lock and WAF tuning are unproven\n"
        "3. database restore and failover drills are incomplete",
    ).tone("blocker")

    customer >> Edge("HTTPS", color=REQUEST, width=2) >> front_door
    front_door >> Edge("Private Link", color=REQUEST, width=2) >> gateway
    gateway >> Edge("approved route", color=REQUEST, width=2) >> workers[1]
    workers[1] >> Edge("SQL · verify-full", color=REQUEST, width=2) >> database
    workers[1] >> Edge("secrets", dashed=True, color=CONTROL) >> vault
    workers[2] >> Edge("egress", dashed=True, color=EGRESS) >> nat
    gateway - Edge(dotted=True, color=EGRESS) - control


if __name__ == "__main__":
    print(diagram.export(Path("dist"), formats=("template", "html", "svg", "png")).html)
