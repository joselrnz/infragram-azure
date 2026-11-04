"""Azure's ownership chain, from the tenant down to a virtual machine.

Nesting is containment: tenant, management group, subscription, resource
group, virtual network, subnets, and the workloads inside them. Every frame
wears Azure's own badge and colour from the theme; nothing here says how
anything is drawn.

Region and availability zone stay out of the chain on purpose: a resource
group may hold resources from several regions, so nesting one inside a
region would state something Azure does not guarantee. Add them as
placement frames only when the diagram is about where things run.

Run from any directory::

    PYTHONPATH="<plugin root>/src" python -m infragram compose examples/azure_tenant_to_vm.py \
        --formats template,html,svg,png --output-dir dist
"""

from __future__ import annotations

from pathlib import Path

from infragram.author import Diagram, Edge
from infragram.nodes.azure import compute, databases, networking, storage
from infragram.nodes.frames import azure as az

with Diagram(
    "Azure hierarchy: tenant to virtual machine",
    "Tenant, management group, subscription, resource group, virtual network and "
    "subnets, each frame carrying Azure's own badge and colour.",
) as diagram:
    with az.Tenant("Contoso - Microsoft Entra tenant"):
        with az.ManagementGroup("Platform management group"):
            with az.Subscription("Production subscription"):
                with az.ResourceGroup("rg-prod-web"):
                    # The one layout hint: subnets side by side, so the
                    # picture reads left to right like the traffic does.
                    with az.VNet("vnet-prod - 10.10.0.0/16").row():
                        with az.Subnet("snet-web - 10.10.1.0/24"):
                            appgw = networking.ApplicationGateways("Application Gateway", "WAF v2")
                            web = compute.VirtualMachine("Web tier", "VM scale set")

                        with az.Subnet("snet-app - 10.10.2.0/24"), az.AKS("aks-prod"):
                            api = compute.KubernetesServices("API workloads", "AKS pods")

                        with az.Subnet("snet-data - 10.10.3.0/24"):
                            sql = databases.SQLDatabase("Azure SQL", "private endpoint")
                            blobs = storage.StorageAccounts("Storage account", "private endpoint")

    appgw >> Edge("HTTPS") >> web
    web >> Edge("internal") >> api
    api >> Edge("TDS 1433", dashed=True) >> sql
    api >> Edge("blob", dashed=True) >> blobs


if __name__ == "__main__":
    print(diagram.export(Path("dist"), formats=("template", "html", "svg", "png")).html)
