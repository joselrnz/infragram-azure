"""A live Azure estate read in one Azure Resource Graph query, through ``az rest``.

The ``az ... list`` reader (:mod:`.azure`) makes a call per kind of resource,
and one more per network (its peerings) and per SQL server (its databases).
Resource Graph returns every resource of the subscription, with the same
properties, in one paged query that needs no CLI extension and no extra
permission beyond the Reader role the list calls already need.

Nothing here draws or maps anything. :class:`GraphRunner` answers the list
calls the reader makes from the rows the query returned, flattened the way
the CLI flattens them (each level's ``properties`` merged into it), so the
reader, its Terraform types and every value it writes are the same whichever
way the estate was read.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from ..model import Estate
from . import CallError, DiscoveryError, Runner, cli_runner
from .azure import discover_azure

__all__ = ["COMMAND_TYPES", "GraphRunner", "discover_azure_graph", "flatten"]

RESOURCE_GRAPH = (
    "https://management.azure.com/providers/Microsoft.ResourceGraph/resources"
    "?api-version=2022-10-01"
)

#: The ``az`` list call the reader makes, and the resource types it lists.
COMMAND_TYPES: dict[str, tuple[str, ...]] = {
    "network vnet": ("microsoft.network/virtualnetworks",),
    "network nic": ("microsoft.network/networkinterfaces",),
    "vm": ("microsoft.compute/virtualmachines",),
    "vmss": ("microsoft.compute/virtualmachinescalesets",),
    "aks": ("microsoft.containerservice/managedclusters",),
    "webapp": ("microsoft.web/sites",),
    "functionapp": ("microsoft.web/sites",),
    "sql server": ("microsoft.sql/servers",),
    "storage account": ("microsoft.storage/storageaccounts",),
    "keyvault": ("microsoft.keyvault/vaults",),
    "network application-gateway": ("microsoft.network/applicationgateways",),
    "network lb": ("microsoft.network/loadbalancers",),
    "network private-endpoint": ("microsoft.network/privateendpoints",),
    "redis": ("microsoft.cache/redis",),
    "cosmosdb": ("microsoft.documentdb/databaseaccounts",),
    "acr": ("microsoft.containerregistry/registries",),
    "monitor log-analytics workspace": ("microsoft.operationalinsights/workspaces",),
    "network nsg": ("microsoft.network/networksecuritygroups",),
    "network asg": ("microsoft.network/applicationsecuritygroups",),
    "network route-table": ("microsoft.network/routetables",),
    "sql db": ("microsoft.sql/servers/databases",),
}

_TYPES = sorted({kind for kinds in COMMAND_TYPES.values() for kind in kinds})
RESOURCES_QUERY = (
    "resources | where type in~ ("
    + ", ".join(f"'{kind}'" for kind in _TYPES)
    + ") | project id, name, type, kind, location, resourceGroup, subscriptionId, sku, tags,"
    " properties"
)
GROUPS_QUERY = (
    "resourcecontainers | where type =~ 'microsoft.resources/subscriptions/resourcegroups'"
    " | project id, name, location, resourceGroup = name, subscriptionId, tags, properties"
)
_PAGE = 1000


def flatten(value: Any) -> Any:
    """ARM's shape as the CLI prints it: each level's ``properties`` merged in."""
    if isinstance(value, list):
        return [flatten(item) for item in value]
    if not isinstance(value, dict):
        return value
    out = {key: flatten(item) for key, item in value.items() if key != "properties"}
    inner = value.get("properties")
    if isinstance(inner, dict):
        for key, item in inner.items():
            out.setdefault(key, flatten(item))
    return out


def _cli_spelling(row: dict[str, Any]) -> dict[str, Any]:
    """Where the CLI's output and Resource Graph's spell a field differently."""
    for pool in row.get("agentPoolProfiles") or []:
        if "vnetSubnetID" in pool and "vnetSubnetId" not in pool:
            pool["vnetSubnetId"] = pool["vnetSubnetID"]
    return row


class GraphRunner:
    """A runner the ``az`` reader can use unchanged: list calls are answered
    from one Resource Graph read, anything else goes to the real ``az``."""

    def __init__(self, run: Runner, subscription: str) -> None:
        self._run = run
        self.subscription = subscription
        rows = [_cli_spelling(flatten(row)) for row in self._query(RESOURCES_QUERY)]
        self.by_type: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            self.by_type.setdefault(str(row.get("type", "")).lower(), []).append(row)
        self.groups = [flatten(row) for row in self._query(GROUPS_QUERY)]

    def _query(self, query: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            options: dict[str, Any] = {"resultFormat": "objectArray", "$top": _PAGE}
            if token:
                options["$skipToken"] = token
            body = {"subscriptions": [self.subscription], "query": query, "options": options}
            # The body goes through a file: on Windows az is a batch file, and
            # cmd.exe mangles the quotes of a JSON argument.
            with tempfile.TemporaryDirectory(prefix="infragram-graph-") as scratch:
                path = Path(scratch) / "body.json"
                path.write_text(json.dumps(body), encoding="utf-8")
                page = (
                    self._run(
                        [
                            "rest",
                            "--method",
                            "post",
                            "--url",
                            RESOURCE_GRAPH,
                            "--body",
                            f"@{path}",
                            "--output",
                            "json",
                            "--only-show-errors",
                        ]
                    )
                    or {}
                )
            rows.extend(page.get("data") or [])
            token = page.get("$skipToken")
            if not token:
                return rows

    def __call__(self, args: list[str]) -> Any:
        if "list" not in args:
            return self._run(args)
        command = " ".join(args[: args.index("list")])
        flags = {args[i]: args[i + 1] for i in range(len(args) - 1) if args[i].startswith("--")}
        if command == "group":
            return self.groups
        if command == "network vnet peering":
            name, group = flags.get("--vnet-name", ""), flags.get("--resource-group", "")
            for network in self.by_type.get("microsoft.network/virtualnetworks", []):
                if (
                    network.get("name") == name
                    and str(network.get("resourceGroup")).lower() == group.lower()
                ):
                    return network.get("virtualNetworkPeerings") or []
            return []
        if command == "sql db":
            server, group = flags.get("--server", ""), flags.get("--resource-group", "")
            prefix = (
                f"/resourcegroups/{group.lower()}/providers/microsoft.sql/servers/{server.lower()}/"
            )
            return [
                row
                for row in self.by_type.get("microsoft.sql/servers/databases", [])
                if prefix in str(row.get("id", "")).lower()
            ]
        kinds = COMMAND_TYPES.get(command)
        if kinds is None:
            raise CallError(f"az {command} list", "not answered from Resource Graph")
        rows = [row for kind in kinds for row in self.by_type.get(kind, [])]
        if command in ("webapp", "functionapp"):
            want_function = command == "functionapp"
            rows = [
                row
                for row in rows
                if ("functionapp" in str(row.get("kind", "")).lower()) == want_function
            ]
        return rows


def discover_azure_graph(
    *,
    subscription: str | None = None,
    groups: list[str] | None = None,
    runner: Runner | None = None,
) -> Estate:
    """:func:`.azure.discover_azure`, with the estate read in one Resource Graph query."""
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
        graph = GraphRunner(run, str(subscription or account.get("id") or ""))
    except CallError as error:
        raise DiscoveryError(
            f"Azure Resource Graph cannot read the subscription: {error.message} (the signed-in "
            "identity needs at least the Reader role; az account show says who that is)"
        ) from error
    estate = discover_azure(subscription=subscription, groups=groups, runner=graph)
    estate.notes.append("read in one Azure Resource Graph query (az rest)")
    return estate
