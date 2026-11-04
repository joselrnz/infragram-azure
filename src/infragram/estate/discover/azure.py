"""A live Azure estate, read-only through the ``az`` CLI.

Every call is a ``list`` or ``show`` on the subscription (or on the resource
groups named). What each returns is written as the ``azurerm`` resource it
would be, with the values the drawing reads: resource group, location, the
subnet a resource sits in (a VM's through its network interface), the
cluster a node pool belongs to, and the network security groups' rules with
the subnets and interfaces each guards.
"""

from __future__ import annotations

from typing import Any

from ..link import link_by_value
from ..model import Estate, Found
from . import CallError, DiscoveryError, Runner, cli_runner, last_segment, tags

__all__ = ["discover_azure"]


def _rule(rule: dict[str, Any]) -> dict[str, Any]:
    """A security rule as a group's ``security_rule`` block writes it."""
    return {
        "name": rule.get("name"),
        "priority": rule.get("priority"),
        "direction": rule.get("direction"),
        "access": rule.get("access"),
        "protocol": rule.get("protocol"),
        "source_address_prefix": rule.get("sourceAddressPrefix"),
        "source_address_prefixes": rule.get("sourceAddressPrefixes") or [],
        "source_application_security_group_ids": [
            g.get("id") for g in rule.get("sourceApplicationSecurityGroups") or []
        ],
        "destination_address_prefix": rule.get("destinationAddressPrefix"),
        "destination_address_prefixes": rule.get("destinationAddressPrefixes") or [],
        "destination_application_security_group_ids": [
            g.get("id") for g in rule.get("destinationApplicationSecurityGroups") or []
        ],
        "destination_port_range": rule.get("destinationPortRange"),
        "destination_port_ranges": rule.get("destinationPortRanges") or [],
    }


def _group(item: dict[str, Any]) -> str | None:
    group = item.get("resourceGroup")
    if group:
        return str(group)
    parts = str(item.get("id", "")).split("/")
    lowered = [p.lower() for p in parts]
    return parts[lowered.index("resourcegroups") + 1] if "resourcegroups" in lowered else None


class _Reader:
    def __init__(self, run: Runner, subscription: str | None) -> None:
        self.run = run
        self.subscription = subscription
        self.found: list[Found] = []
        self.notes: list[str] = []
        self.seen: set[str] = set()
        self.ids: set[str] = set()

    def call(self, command: str, *extra: str) -> Any:
        """``az <command> list <extra>``: every call the reader makes lists."""
        args = [*command.split(), "list", *extra, "--output", "json", "--only-show-errors"]
        if self.subscription:
            args += ["--subscription", self.subscription]
        try:
            answer = self.run(args)
        except CallError as error:
            self.notes.append(f"not read: az {command}: {error.message}")
            return []
        return answer if isinstance(answer, list) else []

    def add(self, kind: str, item: dict[str, Any], values: dict[str, Any], source: str) -> None:
        identity = str(item.get("id") or "").lower()
        if identity and identity in self.ids:
            return  # one resource two lists return (a function app is a web app too)
        self.ids.add(identity)
        name = str(item.get("name") or item.get("id"))
        address = f"{kind}.{name}"
        n = 2
        while address in self.seen:
            address = f"{kind}.{name}_{n}"
            n += 1
        self.seen.add(address)
        base = {
            "id": item.get("id"),
            "name": item.get("name"),
            "location": item.get("location"),
            "resource_group_name": _group(item),
            "tags": tags(item.get("tags")),
        }
        self.found.append(
            Found(
                address, kind, name, {**base, **values}, source=source, region=item.get("location")
            )
        )

    def association(
        self, kind: str, owner: dict[str, Any], name: Any, values: dict[str, Any], source: str
    ) -> None:
        """What joins two resources, written as the association resource Terraform keeps it as."""
        self.add(
            kind,
            {
                "name": last_segment(name) or "association",
                "resourceGroup": _group(owner),
                "location": owner.get("location"),
            },
            values,
            source,
        )

    def read(self, groups: list[str]) -> None:
        wanted = {g.lower() for g in groups}

        def mine(item: dict[str, Any]) -> bool:
            return not wanted or (_group(item) or "").lower() in wanted

        for group in self.call("group"):
            if mine({"resourceGroup": group.get("name")}):
                self.add("azurerm_resource_group", group, {}, "az group list")
        for network in filter(mine, self.call("network vnet")):
            self.add(
                "azurerm_virtual_network",
                network,
                {"address_space": (network.get("addressSpace") or {}).get("addressPrefixes", [])},
                "az network vnet list",
            )
            for subnet in network.get("subnets", []):
                prefixes = subnet.get("addressPrefixes") or (
                    [subnet["addressPrefix"]] if subnet.get("addressPrefix") else []
                )
                self.add(
                    "azurerm_subnet",
                    subnet,
                    {"virtual_network_name": network.get("name"), "address_prefixes": prefixes},
                    "az network vnet list",
                )
            for peering in self.call(
                "network vnet peering",
                "--vnet-name",
                str(network.get("name")),
                "--resource-group",
                str(_group(network)),
            ):
                self.add(
                    "azurerm_virtual_network_peering",
                    peering,
                    {
                        "virtual_network_name": network.get("name"),
                        "remote_virtual_network_id": (
                            peering.get("remoteVirtualNetwork") or {}
                        ).get("id"),
                    },
                    "az network vnet peering list",
                )
        for group in filter(mine, self.call("network asg")):
            self.add("azurerm_application_security_group", group, {}, "az network asg list")
        for nic in filter(mine, self.call("network nic")):
            configurations = nic.get("ipConfigurations", [])
            self.add(
                "azurerm_network_interface",
                nic,
                {
                    "ip_configuration": [
                        {
                            "subnet_id": (c.get("subnet") or {}).get("id"),
                            "private_ip_address": c.get("privateIPAddress"),
                        }
                        for c in configurations
                    ]
                },
                "az network nic list",
            )
            for group in {
                g.get("id"): g
                for c in configurations
                for g in c.get("applicationSecurityGroups") or []
            }:
                self.association(
                    "azurerm_network_interface_application_security_group_association",
                    nic,
                    nic.get("name"),
                    {"network_interface_id": nic.get("id"), "application_security_group_id": group},
                    "az network nic list",
                )
        for group in filter(mine, self.call("network nsg")):
            # the rules a group was given; its default rules allow only what
            # is inside the network and the load balancer's probes
            self.add(
                "azurerm_network_security_group",
                group,
                {"security_rule": [_rule(r) for r in group.get("securityRules") or []]},
                "az network nsg list",
            )
            for subnet in group.get("subnets") or []:
                self.association(
                    "azurerm_subnet_network_security_group_association",
                    group,
                    subnet.get("id"),
                    {"subnet_id": subnet.get("id"), "network_security_group_id": group.get("id")},
                    "az network nsg list",
                )
            for nic in group.get("networkInterfaces") or []:
                self.association(
                    "azurerm_network_interface_security_group_association",
                    group,
                    nic.get("id"),
                    {
                        "network_interface_id": nic.get("id"),
                        "network_security_group_id": group.get("id"),
                    },
                    "az network nsg list",
                )
        for table in filter(mine, self.call("network route-table")):
            # drawn as a badge on each subnet it is attached to
            self.add("azurerm_route_table", table, {}, "az network route-table list")
            for subnet in table.get("subnets") or []:
                self.association(
                    "azurerm_subnet_route_table_association",
                    table,
                    subnet.get("id"),
                    {"subnet_id": subnet.get("id"), "route_table_id": table.get("id")},
                    "az network route-table list",
                )
        for vm in filter(mine, self.call("vm")):
            linux = ((vm.get("storageProfile") or {}).get("osDisk") or {}).get(
                "osType", "Linux"
            ) != "Windows"
            self.add(
                "azurerm_linux_virtual_machine" if linux else "azurerm_windows_virtual_machine",
                vm,
                {
                    "size": (vm.get("hardwareProfile") or {}).get("vmSize"),
                    "network_interface_ids": [
                        n.get("id")
                        for n in (vm.get("networkProfile") or {}).get("networkInterfaces", [])
                    ],
                },
                "az vm list",
            )
        for scale in filter(mine, self.call("vmss")):
            profile = (scale.get("virtualMachineProfile") or {}).get("networkProfile") or {}
            subnets = [
                (ip.get("subnet") or {}).get("id")
                for nic in profile.get("networkInterfaceConfigurations", [])
                for ip in nic.get("ipConfigurations", [])
            ]
            self.add(
                "azurerm_linux_virtual_machine_scale_set",
                scale,
                {
                    "sku": (scale.get("sku") or {}).get("name"),
                    "network_interface": [
                        {"ip_configuration": [{"subnet_id": s} for s in subnets if s]}
                    ],
                },
                "az vmss list",
            )
        for cluster in filter(mine, self.call("aks")):
            pools = cluster.get("agentPoolProfiles") or []
            first = pools[0] if pools else {}
            self.add(
                "azurerm_kubernetes_cluster",
                cluster,
                {
                    "default_node_pool": [
                        {
                            "name": first.get("name"),
                            "vm_size": first.get("vmSize"),
                            "vnet_subnet_id": first.get("vnetSubnetId"),
                        }
                    ]
                },
                "az aks list",
            )
            for pool in pools[1:]:
                self.add(
                    "azurerm_kubernetes_cluster_node_pool",
                    {
                        **pool,
                        "id": f"{cluster.get('id')}/agentPools/{pool.get('name')}",
                        "resourceGroup": _group(cluster),
                    },
                    {
                        "kubernetes_cluster_id": cluster.get("id"),
                        "vm_size": pool.get("vmSize"),
                        "vnet_subnet_id": pool.get("vnetSubnetId"),
                    },
                    "az aks list",
                )
        for app in filter(mine, [*self.call("webapp"), *self.call("functionapp")]):
            kind = str(app.get("kind", ""))
            function = "functionapp" in kind
            linux = "linux" in kind
            resource = (
                ("azurerm_linux_function_app" if linux else "azurerm_windows_function_app")
                if function
                else ("azurerm_linux_web_app" if linux else "azurerm_windows_web_app")
            )
            self.add(
                resource,
                app,
                {"virtual_network_subnet_id": app.get("virtualNetworkSubnetId")},
                "az functionapp list" if function else "az webapp list",
            )
        for server in filter(mine, self.call("sql server")):
            self.add("azurerm_mssql_server", server, {}, "az sql server list")
            for db in self.call(
                "sql db",
                "--server",
                str(server.get("name")),
                "--resource-group",
                str(_group(server)),
            ):
                if db.get("name") == "master":
                    continue
                self.add(
                    "azurerm_mssql_database",
                    db,
                    {
                        "server_id": server.get("id"),
                        "sku_name": (db.get("currentSku") or db.get("sku") or {}).get("name"),
                    },
                    "az sql db list",
                )
        for simple, kind in (
            ("storage account", "azurerm_storage_account"),
            ("keyvault", "azurerm_key_vault"),
            ("cosmosdb", "azurerm_cosmosdb_account"),
            ("acr", "azurerm_container_registry"),
            ("monitor log-analytics workspace", "azurerm_log_analytics_workspace"),
        ):
            for item in filter(mine, self.call(simple)):
                self.add(kind, item, {}, f"az {simple} list")
        for cache in filter(mine, self.call("redis")):
            self.add(
                "azurerm_redis_cache", cache, {"subnet_id": cache.get("subnetId")}, "az redis list"
            )
        for gateway in filter(mine, self.call("network application-gateway")):
            self.add(
                "azurerm_application_gateway",
                gateway,
                {
                    "gateway_ip_configuration": [
                        {"subnet_id": (c.get("subnet") or {}).get("id")}
                        for c in gateway.get("gatewayIPConfigurations", [])
                    ]
                },
                "az network application-gateway list",
            )
        for balancer in filter(mine, self.call("network lb")):
            self.add(
                "azurerm_lb",
                balancer,
                {
                    "frontend_ip_configuration": [
                        {"subnet_id": (c.get("subnet") or {}).get("id")}
                        for c in balancer.get("frontendIPConfigurations", [])
                    ]
                },
                "az network lb list",
            )
        for endpoint in filter(mine, self.call("network private-endpoint")):
            self.add(
                "azurerm_private_endpoint",
                endpoint,
                {
                    "subnet_id": (endpoint.get("subnet") or {}).get("id"),
                    "private_service_connection": [
                        {"private_connection_resource_id": c.get("privateLinkServiceId")}
                        for c in endpoint.get("privateLinkServiceConnections", [])
                    ],
                },
                "az network private-endpoint list",
            )


def discover_azure(
    *,
    subscription: str | None = None,
    groups: list[str] | None = None,
    runner: Runner | None = None,
) -> Estate:
    """What the subscription holds (or the resource groups named), as an estate."""
    run = runner or cli_runner("az")
    try:
        account = (
            run(
                [
                    "account",
                    "show",
                    "--output",
                    "json",
                    "--only-show-errors",
                    *(["--subscription", subscription] if subscription else []),
                ]
            )
            or {}
        )
    except CallError as error:
        raise DiscoveryError(f"the az CLI cannot read the subscription: {error.message}") from error
    reader = _Reader(run, subscription or account.get("id"))
    name = account.get("name") or account.get("id") or "Azure subscription"
    reader.found.append(
        Found(
            "azurerm_subscription.current",
            "azurerm_subscription",
            "current",
            {"subscription_id": account.get("id"), "display_name": name},
            source="az account show",
            mode="data",
        )
    )
    reader.read(list(groups or []))
    where = f"the Azure subscription {name}" + (
        f", resource groups {', '.join(groups)}" if groups else ""
    )
    estate = Estate(str(name), f"{where}, read-only", reader.found, reader.notes)
    link_by_value(estate)
    return estate
