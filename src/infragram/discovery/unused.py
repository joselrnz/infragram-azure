"""Resources an estate pays for, or keeps, without using them.

Read from the same Resource Graph rows the picture is drawn from, so a saved
snapshot finds the same ones offline and nothing extra is asked of Azure.
Each rule names one way a resource sits unused -- a disk attached to nothing,
a public IP no one answers on, a plan with no apps -- and a rule only fires
on what ARM states outright (``diskState: Unattached``, an empty
``backendAddressPools``), never on a property that is merely missing, so a
sparse row is not called unused.

What a finding costs is not decided here: the picture prices every card from
its own table, and the inventory adds up what the unused ones cost.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any

from pydantic import BaseModel

__all__ = ["Unused", "empty_groups", "find_unused"]

_ARM_ID = re.compile(r"^/subscriptions/[^/]+/resourcegroups/[^/]+/providers/", re.IGNORECASE)


class Unused(BaseModel):
    """One resource the estate keeps without using."""

    id: str
    #: A short code a filter can key on: ``unattached-disk``, ``empty-plan``.
    rule: str
    #: What is unused about it, said to a reader.
    reason: str
    #: Whether it still bills while unused: ``yes``, ``disks`` (a deallocated
    #: VM bills only its disks) or ``no`` (free, but clutter or a broken link).
    bills: str = "yes"


def _lower(value: Any) -> str:
    return str(value or "").lower()


def _ids_in(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        if _ARM_ID.match(value):
            yield value.lower()
    elif isinstance(value, dict):
        for inner in value.values():
            yield from _ids_in(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _ids_in(inner)


def _top(resource_id: str) -> str:
    """``.../networkInterfaces/nic/ipConfigurations/x`` -> ``.../networkInterfaces/nic``."""
    head, _, tail = resource_id.partition("/providers/")
    parts = tail.split("/")
    return f"{head}/providers/{'/'.join(parts[:3])}" if len(parts) > 3 else resource_id


def _has(props: dict[str, Any], *keys: str) -> bool:
    """Every key is there: the row says something about it, empty or not."""
    return all(key in props for key in keys)


def _empty(props: dict[str, Any], key: str) -> bool:
    return not props.get(key)


def _pools_empty(pools: Any, *members: str) -> bool:
    return isinstance(pools, list) and all(
        not any((pool.get("properties") or {}).get(member) for member in members)
        for pool in pools
        if isinstance(pool, dict)
    )


def _power(resource: dict[str, Any]) -> str:
    extended = (resource.get("properties") or {}).get("extended") or {}
    return _lower(((extended.get("instanceView") or {}).get("powerState") or {}).get("code"))


def find_unused(resources: Iterable[dict[str, Any]]) -> dict[str, Unused]:
    """Every unused resource among *resources*, by lower-cased id."""
    rows = [dict(r, id=_lower(r.get("id")), type=_lower(r.get("type"))) for r in resources]
    # what anything else names: a NIC a VM lists, a gateway a connection
    # joins; a reference to a part (a NIC's IP configuration in a load
    # balancer's pool) names the resource it belongs to
    named: set[str] = set()
    for row in rows:
        for ref in _ids_in(row.get("properties") or {}):
            owner = _top(ref)
            if owner != row["id"]:
                named.add(owner)
    found: dict[str, Unused] = {}

    def flag(row: dict[str, Any], rule: str, reason: str, bills: str = "yes") -> None:
        found[row["id"]] = Unused(id=row["id"], rule=rule, reason=reason, bills=bills)

    for row in rows:
        kind, props = row["type"], row.get("properties") or {}
        if not isinstance(props, dict):
            continue
        if kind == "microsoft.compute/disks":
            if _lower(props.get("diskState")) == "unattached" and not row.get("managedBy"):
                flag(row, "unattached-disk", "attached to no VM; still billed for its size")
        elif kind == "microsoft.network/publicipaddresses":
            if (
                _has(props, "publicIPAllocationMethod")
                and _empty(props, "ipConfiguration")
                and _empty(props, "natGateway")
            ):
                flag(row, "unassociated-ip", "associated with nothing; a Standard IP still bills")
        elif kind == "microsoft.network/networkinterfaces":
            if (
                _has(props, "ipConfigurations")
                and not any(
                    props.get(key)
                    for key in ("virtualMachine", "privateEndpoint", "privateLinkService")
                )
                and not props.get("hostedWorkloads")
                and row["id"] not in named
            ):
                flag(row, "detached-nic", "attached to no VM or endpoint", bills="no")
        elif kind == "microsoft.network/networksecuritygroups":
            if _empty(props, "subnets") and _empty(props, "networkInterfaces"):
                flag(row, "unassociated-nsg", "on no subnet and no NIC: guards nothing", "no")
        elif kind == "microsoft.network/routetables":
            if _empty(props, "subnets"):
                flag(row, "unassociated-route-table", "on no subnet: routes nothing", "no")
        elif kind == "microsoft.network/natgateways":
            if _empty(props, "subnets"):
                flag(row, "idle-nat-gateway", "on no subnet; still billed by the hour")
        elif kind == "microsoft.network/loadbalancers":
            if _has(props, "backendAddressPools") and _pools_empty(
                props["backendAddressPools"],
                "backendIPConfigurations",
                "loadBalancerBackendAddresses",
            ):
                standard = _lower((row.get("sku") or {}).get("name")) != "basic"
                flag(
                    row,
                    "empty-load-balancer",
                    "no backend in any pool"
                    + ("; a Standard balancer still bills" if standard else ""),
                    bills="yes" if standard else "no",
                )
        elif kind == "microsoft.network/applicationgateways":
            if _has(props, "backendAddressPools") and _pools_empty(
                props["backendAddressPools"], "backendAddresses", "backendIPConfigurations"
            ):
                flag(row, "empty-application-gateway", "no backend in any pool; billed by the hour")
        elif kind == "microsoft.web/serverfarms":
            if props.get("numberOfSites") == 0:
                flag(row, "empty-plan", "hosts no app; billed for its tier")
        elif kind == "microsoft.web/sites":
            if _lower(props.get("state")) == "stopped":
                flag(row, "stopped-app", "stopped; its App Service plan still bills", "no")
        elif kind == "microsoft.compute/availabilitysets":
            if _has(props, "virtualMachines") and _empty(props, "virtualMachines"):
                flag(row, "empty-availability-set", "holds no VM", bills="no")
        elif kind == "microsoft.compute/virtualmachines":
            power = _power(row)
            if power == "powerstate/deallocated":
                flag(
                    row,
                    "deallocated-vm",
                    "deallocated: compute is not billed, its disks are",
                    "disks",
                )
            elif power == "powerstate/stopped":
                flag(row, "stopped-vm", "stopped but not deallocated: compute is still billed")
        elif kind == "microsoft.network/virtualnetworkgateways":
            if (
                _has(props, "gatewayType")
                and not props.get("vpnClientConfiguration")
                and row["id"] not in named
            ):
                flag(row, "idle-gateway", "joined by no connection; billed by the hour")
        elif kind == "microsoft.network/privatednszones":
            if props.get("numberOfVirtualNetworkLinks") == 0:
                flag(
                    row,
                    "unlinked-dns-zone",
                    "linked to no virtual network: resolves for no one",
                    "no",
                )
        elif kind == "microsoft.network/privateendpoints":
            links = [
                *(props.get("privateLinkServiceConnections") or []),
                *(props.get("manualPrivateLinkServiceConnections") or []),
            ]
            states = {
                _lower(
                    (
                        (link.get("properties") or {}).get("privateLinkServiceConnectionState")
                        or {}
                    ).get("status")
                )
                for link in links
                if isinstance(link, dict)
            }
            if states and states <= {"disconnected", "rejected"}:
                flag(row, "disconnected-endpoint", "its connection is disconnected; still billed")
    return found


def empty_groups(
    groups: Iterable[dict[str, Any]], resources: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The resource groups nothing lives in, in the order given; groups another
    service manages (AKS ``MC_*``) are its business and left out."""
    used = {(_lower(r.get("subscriptionId")), _lower(r.get("resourceGroup"))) for r in resources}
    return [
        group
        for group in groups
        if not group.get("managedBy")
        and (_lower(group.get("subscriptionId")), _lower(group.get("name"))) not in used
    ]
