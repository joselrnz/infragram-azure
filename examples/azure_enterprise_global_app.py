"""Azure enterprise application: global, event-driven, active/active in two regions.

Front Door Premium sends each user to the nearest healthy region. API
Management (classic Premium, a gateway in each region) fronts the AKS
services; an order is written to Azure SQL and announced through a
transactional outbox on Service Bus. Functions handle the commands, publish
domain events to Event Grid in their own region, and Event Hubs carries the
clickstream to Databricks. A platform subscription holds identity,
observability, security and the delivery pipeline.

Each service keeps its own recovery behaviour, and the captions say which:
Cosmos DB takes writes in both regions; Service Bus and Event Hubs Premium
geo-replicate data to one secondary that is promoted on failover; Event Grid
replicates no event data, so each region has its own topic and publishers
fail over client-side; the SQL failover group and Managed Redis active
geo-replication keep Central US current; only API Management's gateways are
regional, its management plane stays in East US 2.

Checked against Microsoft Learn on 2026-11-05: Service Bus geo-replication
(GA, Premium, one secondary, promote; forced promotion may lose data), Event
Hubs geo-replication (GA, Premium and Dedicated), Event Grid reliability (event
data never replicated; namespaces need a custom multi-region design), API
Management multi-region (classic Premium; gateways only), Cosmos DB
multi-region writes, SQL failover groups, Front Door priority and latency
routing, Container Registry geo-replication.
"""

from __future__ import annotations

from pathlib import Path

from infragram.author import Diagram, Edge
from infragram.nodes import Box, Group, infragram as shared
from infragram.nodes.azure import (
    analytics,
    compute,
    containers,
    databases,
    devops,
    identity,
    integration,
    monitor,
    networking as net,
    security,
    storage,
)
from infragram.nodes.frames import azure


def region(name: str, rg: str, cidr: str, role: str):
    """One application region: the spoke network, messaging and data."""
    with azure.Region(name).column().keep_order():
        with azure.ResourceGroup(rg).column().keep_order():
            with azure.VNet(f"spoke · {cidr}").row().keep_order():
                with azure.Subnet("snet-apim"):
                    apim = integration.APIManagementServicesIntegration(
                        "API Management gateway", "classic Premium · 1 unit"
                    ).sizing(tier="Premium", units=1)
                with azure.Subnet("snet-aks"):
                    aks = compute.KubernetesServices(
                        "AKS", "orders · catalog · payments\n6 × D4s v5"
                    ).sizing(tier="Standard", nodes=6, node_size="Standard_D4s_v5")
                with azure.Subnet("snet-func"):
                    func = compute.FunctionApps("Functions", "Flex Consumption · handlers").sizing(
                        plan="flex"
                    )
            with Group("Messaging", "group").row().keep_order():
                bus = integration.AzureServiceBus(
                    "Service Bus Premium", f"orders queue · 1 MU · {role}"
                ).sizing(tier="Premium", units=1)
                hubs = analytics.EventHubs(
                    "Event Hubs Premium", f"clickstream · 1 PU · {role}"
                ).sizing(tier="Premium", units=1)
                grid = integration.EventGridTopics(
                    "Event Grid topic", "domain events · this region"
                )
            with Group("Data", "group").row().keep_order():
                sql = databases.SQLDatabase(
                    "Azure SQL Database",
                    "Business Critical · 2 vCores · failover group"
                    if role == "primary"
                    else "geo-secondary · readable",
                ).sizing(tier="Business Critical", zone_redundant="yes")
                redis = databases.AzureManagedRedis(
                    "Azure Managed Redis", "Balanced B5 · active geo-replication"
                ).sizing(tier="Managed Balanced", sku="B5")
                vault = security.KeyVaults("Key Vault", "per-region keys and secrets")
    return {
        "apim": apim,
        "aks": aks,
        "func": func,
        "bus": bus,
        "hubs": hubs,
        "grid": grid,
        "sql": sql,
        "redis": redis,
        "vault": vault,
    }


with Diagram(
    "Azure enterprise application · global, event-driven, active/active",
    "Front Door Premium routes users to the nearest healthy region; API Management "
    "gateways front AKS services in East US 2 and Central US. Orders are written to "
    "Azure SQL and announced through an outbox on Service Bus; Functions handle "
    "them and publish domain events to each region's Event Grid topic; Event Hubs "
    "streams the clickstream to Databricks. Cosmos DB takes writes in both regions; "
    "Service Bus and Event Hubs geo-replicate to Central US and are promoted on "
    "failover. RTO about 5 min for the messaging, under 1 min for reads.",
    slug="azure-enterprise-global-app",
    direction="down",
) as diagram:
    with Group("People and partners", "group").row().keep_order():
        users = shared.identity.PublicUsers("Customers", "web · mobile")
        partners = shared.identity.PublicUsers("Partner systems", "REST · webhooks")
        sre = shared.identity.Administrator("SRE on call", "runs the failover")
        Box(
            "Recovery targets",
            "Tier 0 · customer-facing\nRTO: reads < 1 min, writes ≈ 5 min\n"
            "RPO: Cosmos < 15 min · SQL, Service Bus seconds",
        ).shape("note")

    with azure.Subscription("Production subscription").row().keep_order():
        east = region("East US 2 · active", "rg-app-eus2", "10.10.0.0/16", "primary")

        with azure.ResourceGroup("rg-global").column().keep_order():
            fd = net.FrontDoorAndCDNProfiles("Front Door Premium", "WAF · latency routing · probes")
            cosmos = databases.AzureCosmosDB(
                "Cosmos DB", "catalog · carts · profiles\nmulti-region writes · 2 regions"
            ).sizing(regions=2, multi_region_writes="yes")
            acr = containers.ContainerRegistries(
                "Container Registry", "Premium · geo-replica in Central US"
            ).sizing(tier="Premium", replicas=1)

        central = region("Central US · active", "rg-app-cus", "10.20.0.0/16", "geo-replica")

    with azure.Subscription("Platform subscription").row().keep_order():
        with azure.ResourceGroup("rg-identity-security").column().keep_order():
            entra = identity.EntraID("Microsoft Entra ID", "workforce · External ID for customers")
            defender = security.MicrosoftDefenderForCloud(
                "Defender for Cloud", "posture · workload protection"
            )
            sentinel = security.AzureSentinel("Microsoft Sentinel", "SIEM · incidents")
        with azure.ResourceGroup("rg-observability").column().keep_order():
            insights = monitor.ApplicationInsightsMonitor(
                "Application Insights", "traces · availability tests"
            )
            logs = monitor.LogAnalyticsWorkspacesMonitor(
                "Log Analytics", "one workspace per region"
            )
        with azure.ResourceGroup("rg-data-platform").column().keep_order():
            databricks = analytics.AzureDatabricks("Azure Databricks", "streaming · Unity Catalog")
            lake = storage.StorageAccounts(
                "Data Lake Storage", "GZRS · bronze · silver · gold"
            ).sizing(redundancy="GZRS")
        with azure.ResourceGroup("rg-delivery").column().keep_order():
            pipelines = devops.AzureDevOps("Azure Pipelines", "build · scan · deploy both regions")

    # The order journey: the main flow
    (
        users
        >> Edge(
            "HTTPS 443",
            step=1,
            says="A customer places an order; Front Door picks the nearest healthy region",
        )
        >> fd
    )
    partners >> Edge("HTTPS 443") >> fd
    (
        fd
        >> Edge(
            "443",
            step=2,
            says="Front Door reaches that region's API Management gateway over Private Link",
        )
        >> east["apim"]
    )
    fd >> Edge("443") >> central["apim"]
    entra >> Edge("OAuth 2.0 tokens", dotted=True) >> fd
    for side in (east, central):
        side["aks"] >> Edge("TLS 10000", dotted=True) >> side["redis"]
        side["aks"] >> Edge("managed identity", dotted=True) >> side["vault"]
        side["aks"] >> Edge("AMQP 5671", dotted=True) >> side["hubs"]
    central["apim"] >> Edge("HTTPS") >> central["aks"]
    (
        east["apim"]
        >> Edge(
            "HTTPS",
            step=3,
            says="The gateway validates the token and calls the orders service on AKS",
        )
        >> east["aks"]
    )
    (
        east["aks"]
        >> Edge(
            "TDS 1433",
            step=4,
            says="The service writes the order and an outbox row in one transaction",
        )
        >> east["sql"]
    )
    (
        east["aks"]
        >> Edge(
            "AMQP 5671", step=5, says="An outbox relay sends OrderPlaced to the Service Bus queue"
        )
        >> east["bus"]
    )
    (
        east["bus"]
        >> Edge(
            "trigger",
            step=6,
            says="Functions take the message: payment, stock, fulfilment, each idempotent",
        )
        >> east["func"]
    )
    (
        east["func"]
        >> Edge(
            "publish",
            step=7,
            says="Handlers publish OrderShipped to this region's Event Grid topic",
        )
        >> east["grid"]
    )
    (
        east["grid"]
        >> Edge("webhook", step=8, says="Event Grid pushes the event to partners' webhooks")
        >> partners
    )
    (
        east["hubs"]
        >> Edge(
            "Kafka 9093",
            step=9,
            says="The clickstream flows from Event Hubs into Databricks streaming",
        )
        >> databricks
    )
    databricks >> Edge("ABFS", dotted=True) >> lake
    east["aks"] >> Edge("SDK · nearest region", dotted=True) >> cosmos
    central["aks"] >> Edge("SDK · nearest region", dotted=True) >> cosmos

    # Running all the time: dashed, no steps
    east["sql"] >> Edge("failover group", dashed=True) >> central["sql"]
    east["bus"] >> Edge("geo-replication", dashed=True) >> central["bus"]
    east["hubs"] >> Edge("geo-replication", dashed=True) >> central["hubs"]
    east["redis"] >> Edge("active geo-replication", dashed=True, both=True) >> central["redis"]
    pipelines >> Edge("deploy · both regions") >> acr
    insights >> Edge("availability tests", dotted=True) >> fd
    defender >> Edge("alerts", dotted=True) >> sentinel
    logs >> Edge("logs", dotted=True) >> sentinel

    # East US 2 fails
    failover = "Region failover"
    (
        fd
        >> Edge(
            "probes fail",
            dashed=True,
            step=1,
            flow=failover,
            says="Front Door's probes to East US 2 fail; every request goes to Central US",
        )
        >> central["apim"]
    )
    (
        insights
        >> Edge("alert", step=2, flow=failover, says="Availability alerts page the SRE on call")
        >> sre
    )
    (
        sre
        >> Edge(
            "promote",
            step=3,
            flow=failover,
            says="The SRE promotes the Service Bus and Event Hubs secondaries in Central US",
        )
        >> central["bus"]
    )
    (
        sre
        >> Edge(
            "fail over",
            step=4,
            flow=failover,
            says="and fails the SQL failover group over (customer-managed policy)",
        )
        >> central["sql"]
    )
    (
        central["bus"]
        >> Edge(
            "trigger",
            step=5,
            flow=failover,
            says="Central US Functions drain the promoted queue; Cosmos DB and Redis needed nothing",
        )
        >> central["func"]
    )
    (
        central["func"]
        >> Edge(
            "publish",
            step=6,
            flow=failover,
            says="Publishers already send to Central US's own Event Grid topic",
        )
        >> central["grid"]
    )

if __name__ == "__main__":
    print(diagram.export(Path("dist"), display="both").html)
