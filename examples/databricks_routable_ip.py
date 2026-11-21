"""Azure Databricks on routable IP space, hub and spoke.

The workspace is VNet-injected into a spoke whose address space comes from the
corporate IP plan (10.120.0.0/21), so it is routable end to end: on-premises
users and data sources reach the clusters, and the clusters reach them, over
ExpressRoute with no NAT in between. Secure cluster connectivity (no public IP)
keeps every node private. Back-end Private Link carries the cluster-to-control
plane relay; front-end Private Link in the hub carries the users' browser and
API traffic. A route table sends 0.0.0.0/0 to the hub's Azure Firewall, which
allow-lists the few public FQDNs (package mirrors) the clusters still need.

Through the skill's launcher, from the plugin folder::

    python skills/infragram-azure/scripts/infragram.py compose examples/databricks_routable_ip.py \
        --formats template,html,svg,png --output-dir dist

The exported editor page is examples/databricks_routable_ip.html.
"""

from __future__ import annotations

from infragram.author import Diagram, Edge
from infragram.nodes import Group, infragram as shared
from infragram.nodes.azure import (
    analytics as az_analytics,
    databases,
    identity,
    networking,
    other,
    security,
    storage,
)
from infragram.nodes.databricks import devtools, governance, platform
from infragram.nodes.frames import azure as az, databricks as dbx, generic

# The security group both Databricks subnets share: the rules Databricks
# requires for VNet injection, then the one this design adds for on-prem SQL.
NSG_COLUMNS = (
    "Priority",
    "Name",
    "Direction",
    "Access",
    "Protocol",
    "Source",
    "Source ports",
    "Destination",
    "Destination ports",
)
NSG_RULES = [
    (
        "100",
        "Microsoft.Databricks-workspaces_UseOnly_databricks-worker-to-worker-inbound",
        "Inbound",
        "Allow",
        "*",
        "VirtualNetwork",
        "*",
        "VirtualNetwork",
        "*",
    ),
    (
        "100",
        "Microsoft.Databricks-workspaces_UseOnly_databricks-worker-to-databricks-webapp",
        "Outbound",
        "Allow",
        "TCP",
        "VirtualNetwork",
        "*",
        "AzureDatabricks",
        "443, 3306, 8443-8451",
    ),
    (
        "101",
        "Microsoft.Databricks-workspaces_UseOnly_databricks-worker-to-sql",
        "Outbound",
        "Allow",
        "TCP",
        "VirtualNetwork",
        "*",
        "Sql",
        "3306",
    ),
    (
        "102",
        "Microsoft.Databricks-workspaces_UseOnly_databricks-worker-to-storage",
        "Outbound",
        "Allow",
        "TCP",
        "VirtualNetwork",
        "*",
        "Storage",
        "443",
    ),
    (
        "103",
        "Microsoft.Databricks-workspaces_UseOnly_databricks-worker-to-worker-outbound",
        "Outbound",
        "Allow",
        "*",
        "VirtualNetwork",
        "*",
        "VirtualNetwork",
        "*",
    ),
    (
        "104",
        "Microsoft.Databricks-workspaces_UseOnly_databricks-worker-to-eventhub",
        "Outbound",
        "Allow",
        "TCP",
        "VirtualNetwork",
        "*",
        "EventHub",
        "9093",
    ),
    (
        "200",
        "allow-onprem-sql",
        "Outbound",
        "Allow",
        "TCP",
        "VirtualNetwork",
        "*",
        "10.20.4.15",
        "1433",
    ),
]
# The user-defined routes (UDRs): everything leaves through the hub firewall.
ROUTE_COLUMNS = ("Name", "Address prefix", "Next hop type", "Next hop IP")
DBX_ROUTES = [
    ("default-via-firewall", "0.0.0.0/0", "VirtualAppliance", "10.100.0.68"),
    ("onprem-via-firewall", "10.0.0.0/8", "VirtualAppliance", "10.100.0.68"),
]
GATEWAY_ROUTES = [
    ("dbx-spoke-via-firewall", "10.120.0.0/21", "VirtualAppliance", "10.100.0.68"),
]

with Diagram(
    "Azure Databricks on routable IP space",
    "VNet-injected Azure Databricks in a hub-and-spoke landing zone whose spoke uses routable "
    "corporate address space: on-premises users and data sources reach the clusters over "
    "ExpressRoute with no NAT, secure cluster connectivity keeps nodes private, front-end and "
    "back-end Private Link reach the control plane, and egress is forced through Azure Firewall.",
    slug="databricks-routable-ip",
    display="card",
) as diagram:
    with generic.OnPremises("Corporate datacenter · 10.0.0.0/8").column().keep_order():
        users = identity.Users("Analysts and engineers", "corporate network")
        corp_dns = shared.networking.DNSService(
            "Corporate DNS", "forwards privatelink.* zones"
        ).addresses(server="10.0.10.10")
        onprem_sql = databases.SQLServer("SQL Server", "on-prem source · 10.20.4.15").addresses(
            server="10.20.4.15"
        )
        edge = shared.networking.EdgeRouter(
            "Customer edge router", "BGP · advertises 10.0.0.0/8"
        ).addresses(
            ("Router", "10.0.0.1"),
            ("BGP peer, primary", "192.168.100.1"),
            ("BGP peer, secondary", "192.168.100.5"),
        )

    with az.Tenant("Contoso · Microsoft Entra tenant").column():
        with (
            az.Subscription("Connectivity subscription"),
            az.ResourceGroup("rg-connectivity-eus2").row(),
        ):
            circuit = networking.ExpressrouteCircuits(
                "ExpressRoute circuit", "1 Gbps · private peering"
            )
            zones = networking.DNSZones(
                "Private DNS zones", "privatelink.azuredatabricks.net · dfs · vault"
            )
            with az.VNet("vnet-hub-eus2 · 10.100.0.0/22").row():
                with (
                    az.Subnet("GatewaySubnet · 10.100.0.0/27")
                    .badge(
                        networking.RouteTables,
                        label="rt-gateway",
                        table=(ROUTE_COLUMNS, GATEWAY_ROUTES),
                    )
                    .addresses(router="10.100.0.1")
                ):
                    ergw = networking.VirtualNetworkGateways(
                        "ExpressRoute gateway", "ErGw2AZ"
                    ).addresses(("Instance 0", "10.100.0.4"), ("Instance 1", "10.100.0.5"))
                with az.Subnet("AzureFirewallSubnet · 10.100.0.64/26").addresses(
                    router="10.100.0.65"
                ):
                    firewall = networking.Firewalls(
                        "Azure Firewall", "Premium · FQDN allow-list"
                    ).addresses(private="10.100.0.68")
                with az.Subnet("snet-dns-in · 10.100.1.0/28").addresses(router="10.100.1.1"):
                    resolver = networking.DNSPrivateResolver(
                        "DNS Private Resolver", "inbound 10.100.1.4"
                    ).addresses(("Inbound endpoint", "10.100.1.4"))
                with az.Subnet("snet-pe-transit · 10.100.2.0/27").addresses(router="10.100.2.1"):
                    pe_front = other.PrivateEndpoints(
                        "pe-dbx-frontend", "databricks_ui_api"
                    ).addresses(private="10.100.2.4")
                    pe_auth = other.PrivateEndpoints(
                        "pe-dbx-webauth", "browser_authentication"
                    ).addresses(private="10.100.2.5")

        with az.Subscription("Data landing zone subscription"):
            with az.ResourceGroup("rg-dbx-prod-eus2").row():
                with az.VNet(
                    "vnet-dbx-prod · 10.120.0.0/21 · routable, from corporate IPAM"
                ).column():
                    with (
                        az.Subnet("snet-dbx-host · 10.120.0.0/23 · delegated")
                        .badge(
                            networking.NetworkSecurityGroups,
                            label="nsg-dbx",
                            table=(NSG_COLUMNS, NSG_RULES),
                        )
                        .badge(
                            networking.RouteTables,
                            label="rt-dbx",
                            table=(ROUTE_COLUMNS, DBX_ROUTES),
                        )
                        .addresses(router="10.120.0.1")
                    ):
                        with dbx.Compute("Classic compute · no public IP"):
                            driver = platform.ComputeClusters(
                                "Driver node", "host NIC · 10.120.0.x"
                            )
                            workers = platform.ComputeClusters(
                                "Worker nodes", "host NIC · up to 507"
                            )
                    with (
                        az.Subnet("snet-dbx-container · 10.120.2.0/23 · delegated")
                        .badge(
                            networking.NetworkSecurityGroups,
                            label="nsg-dbx",
                            table=(NSG_COLUMNS, NSG_RULES),
                        )
                        .badge(
                            networking.RouteTables,
                            label="rt-dbx",
                            table=(ROUTE_COLUMNS, DBX_ROUTES),
                        )
                        .addresses(router="10.120.2.1")
                    ):
                        executors = platform.DatabricksRuntime(
                            "Spark containers", "container NIC · one per node"
                        )
                    with az.Subnet("snet-pe · 10.120.4.0/26").addresses(router="10.120.4.1"):
                        pe_back = other.PrivateEndpoints(
                            "pe-dbx-backend", "databricks_ui_api · SCC relay"
                        ).addresses(private="10.120.4.4")
                        pe_dfs = other.PrivateEndpoints("pe-adls-dfs", "dfs").addresses(
                            private="10.120.4.5"
                        )
                        pe_kv = other.PrivateEndpoints("pe-kv", "vault").addresses(
                            private="10.120.4.6"
                        )
                with Group("Workspace resources").column().keep_order():
                    workspace_res = az_analytics.AzureDatabricks(
                        "dbw-prod-eus2", "Premium · VNet injected"
                    )
                    adls = storage.StorageAccounts(
                        "ADLS Gen2", "Unity Catalog storage · public access off"
                    )
                    vault = security.KeyVaults("Key Vault", "secret scope")
                    connector = identity.ManagedIdentities("Access connector", "managed identity")

    with Group("Outside the tenant").column():
        with dbx.Account("Databricks account · control plane, East US 2").column():
            with dbx.Workspace("Workspace dbw-prod-eus2"):
                webapp = devtools.Workspace("Web app and REST API", "notebooks · jobs · SQL")
                relay = platform.Databricks("SCC relay", "cluster manager tunnel")
            with dbx.UnityCatalog("Unity Catalog"):
                metastore = governance.UnityCatalog("Metastore eus2", "catalogs · grants · lineage")
        internet = shared.hybrid_multicloud.GenericCloud("Internet", "PyPI · Maven mirrors only")

    # The user's path: a notebook opened from the corporate network.
    (
        users
        >> Edge(
            "HTTPS 443", step=1, says="A user opens the workspace URL from the corporate network"
        )
        >> edge
    )
    (
        edge
        >> Edge(
            "BGP private peering",
            step=2,
            says="The edge router sends it over ExpressRoute private peering",
        )
        >> circuit
    )
    (
        circuit
        >> Edge("ExpressRoute", step=3, says="The ExpressRoute gateway brings it into the hub")
        >> ergw
    )
    (
        ergw
        >> Edge("HTTPS 443", step=4, says="It reaches the front-end private endpoint in the hub")
        >> pe_front
    )
    (
        pe_front
        >> Edge("Private Link", step=5, says="Private Link carries it to the workspace web app")
        >> webapp
    )
    pe_auth >> Edge("Private Link · SSO", dashed=True) >> webapp

    # Name resolution: privatelink zones answered in the hub, forwarded from on-prem.
    corp_dns >> Edge("DNS 53 · conditional forward") >> resolver
    resolver >> Edge("resolves", dotted=True) >> zones

    # The clusters' own traffic.
    (
        driver
        >> Edge(
            "SCC TLS 443",
            step=1,
            flow="Cluster traffic",
            says="Nodes open the secure cluster connectivity tunnel through the back-end endpoint",
        )
        >> pe_back
    )
    (
        pe_back
        >> Edge(
            "Private Link",
            step=2,
            flow="Cluster traffic",
            says="Back-end Private Link reaches the control plane relay",
        )
        >> relay
    )
    (
        workers
        >> Edge(
            "HTTPS 443",
            step=3,
            flow="Cluster traffic",
            says="Delta tables are read and written through the dfs private endpoint",
        )
        >> pe_dfs
    )
    pe_dfs >> Edge("Private Link", leaves="right", arrives="left") >> adls
    workers >> Edge("HTTPS 443") >> pe_kv
    pe_kv >> Edge("Private Link") >> vault
    (
        executors
        >> Edge(
            "TDS 1433 · routed, no NAT",
            step=4,
            flow="Cluster traffic",
            says="Spark reads on-prem SQL Server directly: the spoke is routable, so no NAT is needed",
        )
        >> onprem_sql
    )
    (
        executors
        >> Edge(
            "0.0.0.0/0 via UDR",
            step=5,
            flow="Cluster traffic",
            says="Everything else follows the route table to Azure Firewall",
        )
        >> firewall
    )
    firewall >> Edge("HTTPS 443 · allow-listed FQDNs") >> internet

    # Peering and governance.
    ergw >> Edge("VNet peering · gateway transit", both=True) >> pe_back
    workspace_res >> Edge("control plane", dotted=True) >> webapp
    metastore >> Edge("governs", dotted=True) >> connector
    connector >> Edge("managed identity", dotted=True) >> adls

    workspace_res.table(
        ("Subnet", "CIDR", "Addresses", "Use"),
        [
            ("snet-dbx-host", "10.120.0.0/23", "507 usable", "one host NIC per node"),
            ("snet-dbx-container", "10.120.2.0/23", "507 usable", "one container NIC per node"),
            ("snet-pe", "10.120.4.0/26", "59 usable", "back-end, dfs and vault endpoints"),
            ("spare", "10.120.4.64 - 10.120.7.255", "~960", "a second workspace or growth"),
        ],
    )
    firewall.table(
        ("Rule", "Destination", "Port", "Why"),
        [
            ("allow", "10.0.0.0/8", "any", "on-prem data sources, routed"),
            ("allow", "pypi.org, files.pythonhosted.org", "443", "cluster libraries"),
            ("allow", "repo1.maven.org", "443", "cluster libraries"),
            ("deny", "0.0.0.0/0", "any", "everything else"),
        ],
    )
