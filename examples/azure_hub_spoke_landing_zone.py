"""Azure hub-and-spoke landing zone with hybrid connectivity.

Redrawn from the Cloud Adoption Framework's connectivity pattern. One
connectivity subscription holds the hub: ExpressRoute and VPN gateways in the
gateway subnet, Azure Firewall Premium inspecting every north-south and
east-west flow, Bastion for operator access, and the private DNS estate. Two
landing-zone subscriptions peer their spoke networks into the hub and route
0.0.0.0/0 through the firewall. A management subscription watches all of it.
What the drawing has to make legible:

* the corporate data centre reaches Azure over ExpressRoute private peering,
  with a site-to-site VPN as the failover path;
* spokes never talk to each other or to the internet directly: every path
  goes through the hub firewall;
* data services in the spokes are reached over private endpoints only;
* one Log Analytics workspace, Defender for Cloud, Sentinel and Azure Policy
  cover every subscription.

Run from any directory::

    PYTHONPATH="<plugin root>/src" python -m infragram compose \\
        examples/azure_hub_spoke_landing_zone.py --formats template,html,svg,png \\
        --display both --output-dir dist
"""

from __future__ import annotations

from pathlib import Path

from infragram.author import Diagram, Edge
from infragram.nodes import infragram as shared
from infragram.nodes.azure import (
    compute,
    databases,
    identity,
    management_governance as mgmt,
    monitor,
    networking as net,
    other,
    security,
    storage,
)
from infragram.nodes.frames import azure, generic

SLUG = "azure-hub-spoke-landing-zone"
TITLE = "Azure hub-and-spoke landing zone"
DESCRIPTION = (
    "A connectivity subscription hosts the hub: ExpressRoute and VPN gateways, "
    "Azure Firewall Premium, Bastion and private DNS. Production and "
    "development landing zones peer their spokes into the hub and send every "
    "flow through the firewall; data services are reached over private "
    "endpoints. A management subscription holds Log Analytics, Defender for "
    "Cloud, Sentinel, Azure Policy and the Recovery Services vault."
)

with Diagram(TITLE, DESCRIPTION, slug=SLUG) as diagram:
    # --- outside Azure ----------------------------------------------------
    with generic.OnPremises("Corporate data centre").column():
        edge = shared.networking.EdgeRouter("Customer edge routers", "BGP · redundant pair")
        servers = shared.compute.PhysicalServer("Legacy application servers", "migrating to spokes")
        dcs = shared.identity.DomainController("Domain controllers", "AD DS")
    operators = shared.identity.Administrator("Platform operators", "Bastion sessions")
    internet = shared.networking.PublicInternet("Internet", "egress via firewall")

    # --- Microsoft Azure: hub on top, landing zones beneath, management last
    with azure.Cloud("Microsoft Azure").column().keep_order():
        # --- connectivity subscription: the hub --------------------------
        with azure.Subscription("Connectivity subscription").column():
            with (
                azure.Region("East US 2"),
                azure.ResourceGroup("rg-connectivity-hub").column().keep_order(),
            ):
                circuit = net.ExpressrouteCircuits(
                    "ExpressRoute circuit", "1 Gbps · private peering"
                )
                with azure.VNet("Hub VNet · 10.0.0.0/16").row().keep_order():
                    with azure.Subnet("GatewaySubnet").column():
                        er_gateway = net.VirtualNetworkGateways(
                            "ExpressRoute gateway", "ErGw2AZ · zone redundant"
                        )
                        vpn_gateway = net.VirtualNetworkGateways(
                            "VPN gateway", "VpnGw2AZ · S2S failover"
                        )
                    with azure.Subnet("AzureFirewallSubnet"):
                        firewall = net.Firewalls(
                            "Azure Firewall Premium", "TLS inspection · IDPS · FQDN rules"
                        )
                    with azure.Subnet("AzureBastionSubnet"):
                        bastion = net.Bastions("Azure Bastion", "Standard · no public IPs on VMs")
                    with azure.Subnet("snet-dns").column():
                        resolver = net.DNSPrivateResolver(
                            "DNS Private Resolver", "inbound + outbound endpoints"
                        )
                        zones = net.DNSZones(
                            "Private DNS zones", "privatelink.* · linked to every VNet"
                        )

        # --- landing zones: the spokes -----------------------------------
        with generic.Environment("Landing zones").row().keep_order():
            with azure.Subscription("Landing zone · production").column():
                with (
                    azure.Region("East US 2"),
                    azure.ResourceGroup("rg-prod-app").column().keep_order(),
                ):
                    with azure.VNet("Spoke VNet · 10.1.0.0/16").row():
                        with azure.Subnet("snet-app").column():
                            prod_lb = net.LoadBalancers(
                                "Internal load balancer", "Standard · zone redundant"
                            )
                            prod_vmss = compute.VMScaleSets(
                                "VM scale set", "app tier · 3-12 instances · zones 1-3"
                            )
                        with azure.Subnet("snet-data").column():
                            prod_pe = other.PrivateEndpoints(
                                "Private endpoints", "SQL · Storage · Key Vault"
                            )
                    prod_sql = databases.SQLDatabase(
                        "Azure SQL Database", "Business Critical · zone redundant"
                    )
                    prod_storage = storage.StorageAccounts(
                        "Storage account", "ZRS · private access only"
                    )
                    prod_kv = security.KeyVaults("Key Vault", "Premium · RBAC")
            with azure.Subscription("Landing zone · development").column():
                with (
                    azure.Region("East US 2"),
                    azure.ResourceGroup("rg-dev-app").column().keep_order(),
                ):
                    with azure.VNet("Spoke VNet · 10.2.0.0/16").row():
                        with azure.Subnet("snet-app"):
                            dev_vms = compute.VirtualMachine(
                                "Dev application VMs", "B-series · auto-shutdown"
                            )
                        with azure.Subnet("snet-data"):
                            dev_pe = other.PrivateEndpoints("Private endpoints", "SQL · Storage")
                    dev_sql = databases.SQLDatabase(
                        "Azure SQL Database", "General Purpose · serverless"
                    )

        # --- management subscription -------------------------------------
        with azure.Subscription("Management subscription").row().keep_order():
            logs = monitor.LogAnalyticsWorkspacesMonitor(
                "Log Analytics workspace", "all diagnostics · 90 days"
            )
            defender = security.MicrosoftDefenderForCloud(
                "Defender for Cloud", "servers · SQL · storage plans"
            )
            sentinel = security.AzureSentinel("Microsoft Sentinel", "analytics rules · SOC")
            policy = mgmt.Policy("Azure Policy", "landing-zone guardrails")
            vault = mgmt.RecoveryServicesVaults(
                "Recovery Services vault", "VM backup · 35-day retention"
            )
            workload_identity = identity.ManagedIdentities(
                "Managed identities", "no credentials in code"
            )

    # --- what talks to what ---------------------------------------------
    edge >> Edge("ExpressRoute private peering") >> circuit
    circuit >> Edge("BGP · 10.0.0.0/8") >> er_gateway
    edge >> Edge("IPsec S2S · failover", dashed=True) >> vpn_gateway
    servers >> edge
    dcs >> edge
    er_gateway >> Edge("UDR · all traffic") >> firewall
    vpn_gateway >> firewall
    firewall >> Edge("egress · allow-list") >> internet
    # Peering is drawn between the things that exchange packets: the firewall
    # and each spoke's entry point, with the route that forces the path.
    firewall >> Edge("VNet peering · UDR 0.0.0.0/0", dashed=True) >> [prod_lb, dev_vms]
    operators >> Edge("RDP/SSH over TLS 443") >> bastion
    bastion >> Edge("private IP only", dotted=True) >> prod_vmss
    prod_lb >> Edge("HTTPS") >> prod_vmss
    prod_vmss >> Edge("private DNS") >> prod_pe
    prod_pe >> Edge(dotted=True) >> [prod_sql, prod_storage, prod_kv]
    dev_vms >> Edge("private DNS") >> dev_pe
    dev_pe >> Edge(dotted=True) >> dev_sql
    resolver >> Edge("resolves privatelink.*", dotted=True) >> zones
    dcs >> Edge("conditional forwarders", dotted=True) >> resolver
    prod_vmss >> Edge("diagnostics", dotted=True) >> logs
    firewall >> Edge("firewall logs", dotted=True) >> logs
    logs >> Edge(dotted=True) >> sentinel
    defender >> Edge(dotted=True) >> prod_sql
    policy >> Edge("deny public IPs · require tags", dotted=True) >> prod_vmss
    policy >> Edge("allowed SKUs · auto-shutdown", dotted=True) >> dev_vms
    vault >> Edge("backup", dotted=True) >> prod_vmss
    prod_vmss >> Edge(dotted=True) >> workload_identity


if __name__ == "__main__":
    print(diagram.export(Path("dist"), display="both").html)
