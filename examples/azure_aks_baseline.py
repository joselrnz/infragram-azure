"""AKS production baseline: a private cluster in a spoke, egress through the hub.

Redrawn from the AKS baseline reference architecture. The cluster sits in its
own spoke network with a private API server; Application Gateway with WAF is
the only public entry, and it forwards to an internal load balancer fronting
the ingress controller on the user node pool. Images come from a private
Container Registry, secrets from Key Vault, both over private endpoints, and
every outbound flow leaves through Azure Firewall in the hub. What the drawing
has to make legible:

* one public entry (Application Gateway + WAF), one private API server;
* system and user node pools separated, the user pool autoscaling;
* registry, vault and database reached over private endpoints only;
* egress is forced through the hub firewall with FQDN allow-lists;
* workload identity, Azure Policy, Defender for Containers and Container
  insights cover the cluster.

Run from any directory::

    PYTHONPATH="<plugin root>/src" python -m infragram compose \\
        examples/azure_aks_baseline.py --formats template,html,svg,png \\
        --display both --output-dir dist
"""

from __future__ import annotations

from pathlib import Path

from infragram.author import Diagram, Edge
from infragram.nodes import infragram as shared
from infragram.nodes.azure import (
    compute,
    containers,
    databases,
    identity,
    management_governance as mgmt,
    monitor,
    networking as net,
    other,
    security,
)
from infragram.nodes.frames import azure, generic

SLUG = "azure-aks-baseline"
TITLE = "AKS production baseline"
DESCRIPTION = (
    "A private AKS cluster in its own spoke: Application Gateway with WAF is "
    "the only public entry and forwards to an internal load balancer in front "
    "of the ingress controller. System and user node pools are separated, "
    "images and secrets come from Container Registry and Key Vault over "
    "private endpoints, Cosmos DB is reached the same way, and every outbound "
    "flow leaves through Azure Firewall in the hub. Workload identity, Azure "
    "Policy, Defender for Containers and Container insights watch the cluster."
)

with Diagram(TITLE, DESCRIPTION, slug=SLUG) as diagram:
    customers = shared.identity.PublicUsers("Customers", "HTTPS")
    developers = shared.identity.Administrator("Platform team", "GitHub Actions · kubectl")
    internet = shared.networking.PublicInternet("Internet", "allow-listed FQDNs")

    with azure.Subscription("Workload subscription").column():
        with azure.Region("West Europe").column().keep_order():
            # --- the spoke that holds the cluster -------------------------
            with azure.ResourceGroup("rg-aks-spoke").column():
                with azure.VNet("Spoke VNet · 10.240.0.0/16").row():
                    with azure.Subnet("snet-applicationgateway"):
                        appgw = net.ApplicationGateways(
                            "Application Gateway", "WAF v2 · TLS termination · zone redundant"
                        )
                    with azure.Subnet("snet-clusternodes").column():
                        with azure.AKS("AKS cluster · private API server").row():
                            system_pool = compute.KubernetesServices(
                                "System node pool", "3 nodes · zones 1-3 · CoreDNS, metrics"
                            )
                            user_pool = compute.KubernetesServices(
                                "User node pool", "autoscale 3-12 · workloads"
                            )
                            ingress_lb = net.LoadBalancers(
                                "Internal load balancer", "ingress-nginx · private IP"
                            )
                    with azure.Subnet("snet-privatelinkendpoints").column():
                        endpoints = other.PrivateEndpoints(
                            "Private endpoints", "ACR · Key Vault · Cosmos DB"
                        )

            # --- platform services and the hub, in a row beneath the spoke --
            with generic.Zone("Platform services").row().keep_order():
                with azure.ResourceGroup("rg-aks-shared").row():
                    with generic.Zone("Supply chain and secrets").column().keep_order():
                        registry = containers.ContainerRegistries(
                            "Container Registry", "Premium · private link · geo-replication"
                        )
                        vault = security.KeyVaults("Key Vault", "TLS certs · secrets · RBAC")
                        cosmos = databases.AzureCosmosDB(
                            "Cosmos DB", "serverless · private endpoint"
                        )
                        workload_identity = identity.ManagedIdentities(
                            "Workload identity", "federated · per namespace"
                        )
                    with generic.Zone("Observability and governance").column().keep_order():
                        insights = monitor.LogAnalyticsWorkspacesMonitor(
                            "Log Analytics", "Container insights · Prometheus"
                        )
                        app_insights = monitor.ApplicationInsightsMonitor(
                            "Application Insights", "distributed tracing"
                        )
                        policy = mgmt.Policy(
                            "Azure Policy for AKS", "baseline initiative · gatekeeper"
                        )
                        defender = security.MicrosoftDefenderForCloud(
                            "Defender for Containers", "image scanning · runtime alerts"
                        )

                # --- the hub that owns egress -----------------------------
                with azure.ResourceGroup("rg-hub").column():
                    with (
                        azure.VNet("Hub VNet · 10.200.0.0/24"),
                        azure.Subnet("AzureFirewallSubnet"),
                    ):
                        firewall = net.Firewalls("Azure Firewall", "egress · FQDN rules for AKS")

    # --- what talks to what ---------------------------------------------
    customers >> Edge("HTTPS 443") >> appgw
    appgw >> Edge("re-encrypt · health probes") >> ingress_lb
    ingress_lb >> Edge("ingress-nginx") >> user_pool
    system_pool >> Edge("CoreDNS · metrics", dotted=True) >> user_pool
    user_pool >> Edge("private DNS") >> endpoints
    endpoints >> Edge("image pull", dotted=True) >> registry
    endpoints >> Edge("CSI secrets store", dotted=True) >> vault
    endpoints >> Edge("SQL API", dotted=True) >> cosmos
    user_pool >> Edge("VNet peering · UDR 0.0.0.0/0 · egress", dashed=True) >> firewall
    firewall >> Edge("allow-listed FQDNs") >> internet
    developers >> Edge("push images · OIDC") >> registry
    developers >> Edge("kubectl · private API server", dotted=True) >> system_pool
    user_pool >> Edge("token exchange", dotted=True) >> workload_identity
    workload_identity >> Edge("RBAC", dotted=True) >> vault
    system_pool >> Edge("logs · metrics", dotted=True) >> insights
    user_pool >> Edge("traces", dotted=True) >> app_insights
    policy >> Edge("admission control", dotted=True) >> user_pool
    defender >> Edge("runtime protection", dotted=True) >> user_pool
    defender >> Edge("scan on push", dotted=True) >> registry


if __name__ == "__main__":
    print(diagram.export(Path("dist"), display="both").html)
