"""An Azure snapshot, drawn: frames for where things are, wires for what uses what.

Two views of one snapshot:

``groups``
    Tenant, subscription, resource group, resource. Always true, because it
    is exactly how Azure Resource Manager files things, and it says nothing
    about the network.

``network``
    The same frames down to the resource group, then the virtual networks
    and their subnets, with every resource that has an address placed in the
    subnet it has it in. A VM is found through its network interface, an
    AKS cluster through its node pools, a private endpoint, gateway,
    firewall or App Service integration through the subnet it names. What
    has no address stays in its resource group. Network security groups,
    route tables and NAT gateways sit on the edge of the subnets they apply
    to as badges on each subnet's top-right corner: the NSG's icon on the
    corner point, route table and NAT gateway on the top border beside it,
    each captioned with its name.

When the snapshot holds them, the last fourteen days of changes and the open
security findings go on the card (or frame) of the resource they are about:
a part's on the card that lists it, a subnet's on its subnet, a deleted
resource's on its resource group. The editor lists them, filters by them and
lights them on the map; the exported pictures leave them out.

In both views peered networks are wired to each other (in the network
view through a Peerings card inside each network, because a wire to a frame
lands on the first card the frame holds), a private endpoint
is wired to the resource it reaches, a web app to the App Service plan it
runs on, and (when asked for) any other resource
that names another one in its properties -- a web app its plan, a cluster
its Log Analytics workspace -- is wired to it.

Everything is placed from the snapshot's ids, never from names, and ids are
compared case-insensitively because ARM itself is inconsistent about case.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatchcase
from typing import Any

from ..models.topology import TopologyElement
from ..nodes.azure import networking, other
from ..nodes.frames import azure as az
from ..patterns import Blueprint
from . import arm_types
from .changes import Change, read_changes
from .findings import Finding, read_findings
from .unused import empty_groups, find_unused

__all__ = ["VIEWS", "ImportOptions", "ImportSummary", "blueprint"]

VIEWS = ("network", "groups")

_SUBNET = re.compile(
    r"^/subscriptions/[^/]+/resourcegroups/[^/]+/providers/microsoft\.network/"
    r"virtualnetworks/[^/]+/subnets/[^/]+$"
)
_NIC = re.compile(
    r"^(/subscriptions/[^/]+/resourcegroups/[^/]+/providers/microsoft\.network/"
    r"networkinterfaces/[^/]+)(?:/.*)?$"
)
_ARM_ID = re.compile(r"^/subscriptions/[^/]+/resourcegroups/[^/]+/providers/", re.IGNORECASE)

#: Keys whose subtree names a subnet without the resource being in it: a
#: storage firewall allowing a subnet, a load balancer's backend members.
_NOT_PLACEMENT = frozenset(
    {
        "networkacls",
        "virtualnetworkrules",
        "iprules",
        "backendaddresspools",
        "backendipconfigurations",
        "inboundnatrules",
        "inboundnatpools",
        "loadbalancerbackendaddresses",
        "privateendpointconnections",
    }
)

#: Types that name subnets because they *apply* to them: badges on each
#: subnet's top-right corner, in this order from the corner.
_EDGE_TYPES = (
    "microsoft.network/networksecuritygroups",
    "microsoft.network/routetables",
    "microsoft.network/natgateways",
)

#: Types never placed in a subnet even though they name one.
_UNPLACED = frozenset(
    {
        "microsoft.network/virtualnetworks",
        "microsoft.network/publicipaddresses",
        "microsoft.network/serviceendpointpolicies",
        "microsoft.network/networkwatchers/flowlogs",
        "microsoft.network/privatednszones/virtualnetworklinks",
        *_EDGE_TYPES,
    }
)


@dataclass(frozen=True)
class ImportOptions:
    view: str = "network"
    #: Draw plumbing too: NICs, disks, public IPs, alert rules, extensions.
    everything: bool = False
    #: Draw resource groups another service manages (AKS ``MC_*``, Databricks).
    managed_groups: bool = False
    #: Wire resources to the resources their properties name. Off by default:
    #: on a real estate they cross the whole picture.
    references: bool = False
    #: Resource-group name patterns (``fnmatch``, case-insensitive); empty = all.
    resource_groups: tuple[str, ...] = ()
    #: Resource-type patterns to leave out, e.g. ``microsoft.insights/*``.
    exclude_types: tuple[str, ...] = ()
    #: ``icon`` (bare icons with captions, the default) or ``card``.
    display: str = "icon"


@dataclass
class ImportSummary:
    subscriptions: int = 0
    resource_groups: int = 0
    resources: int = 0
    networks: int = 0
    subnets: int = 0
    placed: int = 0
    attached: int = 0
    outside: int = 0
    wires: int = 0
    hidden: int = 0
    unmapped: dict[str, int] = field(default_factory=dict)
    #: rule -> how many resources (or empty groups) it marked unused
    unused: dict[str, int] = field(default_factory=dict)
    #: changes read, how many cards or frames they went on, how many deletes
    changes: int = 0
    changed: int = 0
    deleted: int = 0
    #: severity ("" for Policy) -> how many findings, and on how many cards or frames
    findings: dict[str, int] = field(default_factory=dict)
    flagged: int = 0
    #: what Azure refused to read -> its reason
    unread: dict[str, str] = field(default_factory=dict)

    def lines(self) -> list[str]:
        text = [
            f"{self.subscriptions} subscription(s), {self.resource_groups} resource group(s), "
            f"{self.resources} resource(s) drawn, {self.hidden} left out as plumbing or filtered",
        ]
        if self.networks:
            text.append(
                f"{self.networks} virtual network(s), {self.subnets} subnet(s), "
                f"{self.placed} resource(s) placed in a subnet, "
                f"{self.attached} NSG/route table/NAT badge(s) on subnet corners"
            )
        if self.outside:
            text.append(
                f"{self.outside} peered network(s) outside this import, drawn as cards "
                "so each peering keeps both ends (read their subscription to draw them fully)"
            )
        text.append(f"{self.wires} wire(s)")
        if self.unused:
            listing = ", ".join(f"{rule} x{count}" for rule, count in sorted(self.unused.items()))
            text.append(f"{sum(self.unused.values())} unused, marked on the picture: {listing}")
        if self.changes:
            text.append(
                f"{self.changes} change(s) in the last 14 days on {self.changed} card(s) or frame(s)"
                + (f", {self.deleted} of them deletes" if self.deleted else "")
            )
        if self.findings:
            listing = ", ".join(
                f"{count} {severity.lower() or 'from Policy'}"
                for severity, count in sorted(
                    self.findings.items(), key=lambda item: _SEVERITIES.index(item[0])
                )
            )
            text.append(
                f"{sum(self.findings.values())} security finding(s) on {self.flagged} "
                f"card(s) or frame(s): {listing}"
            )
        for what, reason in sorted(self.unread.items()):
            first = reason.strip().splitlines()[0] if reason.strip() else "no reason given"
            text.append(f"{what} not read: {first}")
        if self.unmapped:
            listing = ", ".join(f"{name} x{count}" for name, count in sorted(self.unmapped.items()))
            text.append(f"drawn with the generic icon (no mapping yet): {listing}")
        return text


_SEVERITIES = ("High", "Medium", "Low", "")
#: Changes listed on one card; the rest are counted.
_CHANGES_LISTED = 10
#: Findings listed on one card; the rest are counted.
_FINDINGS_LISTED = 20


def _lower(value: Any) -> str:
    return str(value or "").lower()


def _ids_in(value: Any, *, skip: frozenset[str] = frozenset()) -> Iterator[str]:
    """Every ARM id string inside *value*, depth first, in document order."""
    if isinstance(value, str):
        if _ARM_ID.match(value):
            yield value.lower()
    elif isinstance(value, dict):
        for key, inner in value.items():
            if key.lower() not in skip:
                yield from _ids_in(inner, skip=skip)
    elif isinstance(value, list):
        for inner in value:
            yield from _ids_in(inner, skip=skip)


def _parent_id(resource_id: str) -> str | None:
    """``.../servers/a/databases/b`` -> ``.../servers/a``; None for a top-level resource."""
    head, _, tail = resource_id.partition("/providers/")
    parts = tail.split("/")
    # namespace/type/name, then type/name for each level of nesting
    if len(parts) <= 3:
        return None
    return f"{head}/providers/{'/'.join(parts[:-2])}"


def _detail(resource: dict[str, Any], *, with_location: bool = True) -> str:
    props = resource.get("properties") or {}
    sku = resource.get("sku") or {}
    size = (props.get("hardwareProfile") or {}).get("vmSize") if isinstance(props, dict) else None
    first = size or (sku.get("name") if isinstance(sku, dict) else None) or ""
    location = str(resource.get("location") or "") if with_location else ""
    return " · ".join(part for part in (str(first), location) if part)


def _sizing(resource: dict[str, Any]) -> dict[str, Any]:
    """Known VM facts price the inventory's capacity rather than a default VM."""
    kind = resource["type"]
    location = _lower(resource.get("location"))
    if kind not in (
        "microsoft.compute/virtualmachines",
        "microsoft.compute/virtualmachinescalesets",
    ):
        # Every resource is priced where it is, as what ARM says it is: a
        # sizing the pricer would otherwise assume.
        found = _stated(resource)
        if location and location != "global" and "billed_by" not in found:
            found["region"] = location
        return found
    props = resource.get("properties") or {}
    sku = resource.get("sku") or {}
    profile = props.get("virtualMachineProfile") or props
    sizing: dict[str, Any] = {}
    size = (props.get("hardwareProfile") or {}).get("vmSize") or sku.get("name")
    os_type = ((profile.get("storageProfile") or {}).get("osDisk") or {}).get("osType")
    if size:
        sizing["size"] = size
    if os_type:
        sizing["os"] = os_type
    if resource.get("location"):
        sizing["region"] = resource["location"]
    count = sku.get("capacity") if kind.endswith("virtualmachinescalesets") else 1
    if isinstance(count, int) and not isinstance(count, bool) and count > 0:
        sizing["count"] = count
    return sizing


#: A managed disk's SKU, as the disk pricer names its kind.
_DISK_SKUS = {
    "premium": "Premium SSD",
    "standardssd": "Standard SSD",
    "standard": "Standard HDD",
    "premiumv2": "Premium SSD v2",
    "ultrassd": "Ultra",
}


def _stated(resource: dict[str, Any]) -> dict[str, Any]:
    """The sizing a resource's own row states, in the keys its pricer reads."""
    kind = resource["type"]
    props = resource.get("properties") or {}
    sku = resource.get("sku") or {}
    name = str(sku.get("name") or "")
    found: dict[str, Any] = {}
    if kind == "microsoft.compute/disks":
        family, _, redundancy = name.partition("_")
        if family.lower() in _DISK_SKUS:
            found["type"] = _DISK_SKUS[family.lower()]
        if redundancy.upper() in ("LRS", "ZRS"):
            found["redundancy"] = redundancy.upper()
        if isinstance(props.get("diskSizeGB"), int) and props["diskSizeGB"] > 0:
            found["size_gb"] = props["diskSizeGB"]
    elif kind == "microsoft.web/serverfarms":
        if re.fullmatch(r"[A-Z]+\d+[a-z0-9]*", name):
            found["sku"] = name
        found["os"] = (
            "Linux"
            if props.get("reserved") or "linux" in _lower(resource.get("kind"))
            else "Windows"
        )
        capacity = sku.get("capacity")
        if isinstance(capacity, int) and capacity > 0:
            found["count"] = capacity
    elif kind == "microsoft.web/sites":
        plan = _lower(props.get("serverFarmId")).rsplit("/", 1)[-1]
        if plan:
            found["billed_by"] = f"its App Service plan {plan}"
    elif kind in ("microsoft.network/publicipaddresses", "microsoft.network/loadbalancers"):
        if name in ("Standard", "Basic"):
            found["tier"] = name
    return found


def _grid(frame: TopologyElement) -> None:
    """Loose services in a frame go in a grid, not a tower: about as many
    columns as rows, three to six wide."""
    loose = sum(1 for child in frame.children if not child.is_frame)
    if loose > 3:
        frame.attributes["grid"] = max(3, min(6, math.ceil(math.sqrt(loose))))


def _prefixes(props: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = props.get(key)
        if isinstance(value, dict):
            value = value.get("addressPrefixes")
        if isinstance(value, str) and value:
            return value
        if isinstance(value, list) and value:
            return ", ".join(str(item) for item in value)
    return ""


def _named(name: str, suffix: str) -> str:
    return f"{name} · {suffix}" if suffix else name


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "azure"


class _Builder:
    def __init__(self, snapshot: dict[str, Any], options: ImportOptions) -> None:
        if options.view not in VIEWS:
            raise ValueError(f"view must be one of {VIEWS}, not {options.view!r}")
        self.options = options
        self.summary = ImportSummary()
        self.subscriptions = list(snapshot.get("subscriptions") or [])
        self.all_resources = [
            dict(r, id=_lower(r.get("id")), type=_lower(r.get("type")))
            for r in snapshot.get("resources") or []
        ]
        self.by_id = {r["id"]: r for r in self.all_resources}
        self.groups = self._chosen_groups(snapshot.get("resourceGroups") or [])
        #: What the estate keeps without using, by id; drawn even when its
        #: type is plumbing, since an unattached disk belongs to nothing else.
        self.unused = find_unused(self.all_resources)
        self.empty = {
            f"{_lower(g.get('subscriptionId'))}/{_lower(g.get('name'))}"
            for g in empty_groups(self.groups.values(), self.all_resources)
        }
        #: The last fourteen days of changes, newest first, and the open
        #: findings by resource: neither is there in a snapshot that did not
        #: read them.
        self.taken = str(snapshot.get("taken") or "")
        self.changes: list[Change] = read_changes(snapshot.get("changes") or [])
        found = snapshot.get("findings") or {}
        self.findings: dict[str, list[Finding]] = read_findings(
            found.get("defender") or (), found.get("policy") or (), found.get("names") or ()
        )
        self.summary.unread = {str(k): str(v) for k, v in (snapshot.get("unread") or {}).items()}
        #: Subscriptions Azure would not let the identity read, by lower-cased
        #: id: drawn as not read, never as empty.
        self.unreadable = {
            _lower(sub_id): str(reason)
            for sub_id, reason in (snapshot.get("unreadable") or {}).items()
        }
        self.vnet_frames: dict[str, TopologyElement] = {}
        self.elements: dict[str, TopologyElement] = {}
        self.wired: set[tuple[str, str]] = set()
        #: NSGs, route tables and NAT gateways already drawn in their subnets.
        self.attached: set[str] = set()
        self.peering_cards: dict[str, TopologyElement] = {}
        #: Network interface -> the VM (or other resource) it belongs to.
        self.nic_owner: dict[str, str] = {}
        for resource in self.all_resources:
            if resource["type"] == "microsoft.network/networkinterfaces":
                owner = _lower(
                    ((resource.get("properties") or {}).get("virtualMachine") or {}).get("id")
                )
                if owner in self.by_id:
                    self.nic_owner.setdefault(resource["id"], owner)
            elif resource["type"] not in _EDGE_TYPES:
                for ref in _ids_in(resource.get("properties") or {}, skip=_NOT_PLACEMENT):
                    nic = _NIC.match(ref)
                    if nic and nic.group(1) in self.by_id:
                        self.nic_owner.setdefault(nic.group(1), resource["id"])
        #: The parts a resource carries -- its NICs, its disks, its public IPs
        #: -- as (role, part id), and each part's owner. Listed on the owner's
        #: card always; drawn beside it, wired to it, when plumbing is drawn.
        self.parts: dict[str, list[tuple[str, str]]] = {}
        self.owner_of: dict[str, str] = {}
        for resource in self.all_resources:
            role, owner = self._owner(resource)
            if owner and owner in self.by_id and owner != resource["id"]:
                self.parts.setdefault(owner, []).append((role, resource["id"]))
                self.owner_of[resource["id"]] = owner
        #: A web app's App Service plan, and each plan's apps: the app runs on
        #: the plan and the plan bills for it, so both cards say so and a wire
        #: joins them.
        self.host_of: dict[str, str] = {}
        self.hosted: dict[str, list[str]] = {}
        for resource in self.all_resources:
            if resource["type"] != "microsoft.web/sites":
                continue
            host = _lower((resource.get("properties") or {}).get("serverFarmId"))
            if host in self.by_id and host != resource["id"]:
                self.host_of[resource["id"]] = host
                self.hosted.setdefault(host, []).append(resource["id"])
        #: Resource groups some of whose resources were drawn in a subnet.
        #: One left empty by that is not drawn: its members are elsewhere.
        self.moved_out: set[str] = set()
        #: Captions carry the region only when the estate spans more than one.
        self.many_regions = True
        #: Peered networks the import did not draw, by lower-cased id.
        self.outside: dict[str, TopologyElement] = {}

    # -- what is drawn ----------------------------------------------------
    def _chosen_groups(self, groups: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        chosen: dict[str, dict[str, Any]] = {}
        patterns = [pattern.lower() for pattern in self.options.resource_groups]
        for group in groups:
            name = str(group.get("name") or "")
            if patterns and not any(fnmatchcase(name.lower(), p) for p in patterns):
                continue
            if group.get("managedBy") and not self.options.managed_groups:
                continue
            key = f"{_lower(group.get('subscriptionId'))}/{name.lower()}"
            chosen[key] = group
        return chosen

    def _owner(self, resource: dict[str, Any]) -> tuple[str, str]:
        """(role, owner id) for a part another resource carries, else ("", "")."""
        kind, props = resource["type"], resource.get("properties") or {}
        if kind == "microsoft.network/networkinterfaces":
            return "NIC", self.nic_owner.get(resource["id"], "")
        if kind == "microsoft.compute/disks":
            role = "OS disk" if props.get("osType") else "data disk"
            return role, _lower(resource.get("managedBy"))
        if kind == "microsoft.network/publicipaddresses":
            config = _lower((props.get("ipConfiguration") or {}).get("id"))
            if not config:
                return "", ""
            head, _, tail = config.partition("/providers/")
            holder = f"{head}/providers/{'/'.join(tail.split('/')[:3])}"
            return "public IP", self.nic_owner.get(holder, holder)
        return "", ""

    def _part_line(self, part: dict[str, Any]) -> str:
        """What a part's row on its owner's card says after its name."""
        props, sku = part.get("properties") or {}, part.get("sku") or {}
        if part["type"] == "microsoft.network/networkinterfaces":
            configs = props.get("ipConfigurations") or []
            address = (
                ((configs[0] or {}).get("properties") or {}).get("privateIPAddress")
                if configs
                else ""
            )
            return str(address or "")
        if part["type"] == "microsoft.compute/disks":
            size = props.get("diskSizeGB")
            return " · ".join(
                str(bit) for bit in (sku.get("name"), f"{size} GiB" if size else "") if bit
            )
        return str(props.get("ipAddress") or "")

    def _group_key(self, resource: dict[str, Any]) -> str:
        return f"{_lower(resource.get('subscriptionId'))}/{_lower(resource.get('resourceGroup'))}"

    def _drawable(self, resource: dict[str, Any]) -> bool:
        kind = resource["type"]
        if self._group_key(resource) not in self.groups:
            return False
        if (
            kind in arm_types.PLUMBING
            and not self.options.everything
            and resource["id"] not in self.unused
        ):
            return False
        if any(fnmatchcase(kind, pattern.lower()) for pattern in self.options.exclude_types):
            return False
        return not (
            kind == "microsoft.sql/servers/databases" and _lower(resource.get("name")) == "master"
        )

    # -- placement --------------------------------------------------------
    def subnet_of(self, resource: dict[str, Any]) -> str | None:
        """The subnet a resource is drawn in: the first it has an address in."""
        found = self.subnets_of(resource)
        return found[0] if found else None

    def subnets_of(self, resource: dict[str, Any]) -> list[str]:
        """Every subnet a resource has an address in, in document order: an AKS
        cluster's node pools or a VM's NICs can span several."""
        if resource["type"] in _UNPLACED:
            return []
        if resource["type"] == "microsoft.network/loadbalancers":
            props = {
                "frontendIPConfigurations": (resource.get("properties") or {}).get(
                    "frontendIPConfigurations", []
                )
            }
        else:
            props = resource.get("properties") or {}
        if resource["type"] == "microsoft.databricks/workspaces":
            # VNet injection names the network by id and its subnets by name.
            params = props.get("parameters") or {}
            vnet = _lower((params.get("customVirtualNetworkId") or {}).get("value"))
            subnet = (params.get("customPrivateSubnetName") or {}).get("value")
            if vnet and subnet:
                return [f"{vnet}/subnets/{str(subnet).lower()}"]
        found: list[str] = []
        for ref in _ids_in(props, skip=_NOT_PLACEMENT):
            if _SUBNET.match(ref):
                found.append(ref)
                continue
            nic = _NIC.match(ref)
            if nic and nic.group(1) != resource["id"]:
                owner = self.by_id.get(nic.group(1))
                if owner is not None:
                    found.extend(self.subnets_of(owner))
        return list(dict.fromkeys(found))

    # -- building ---------------------------------------------------------
    def node(self, resource: dict[str, Any]) -> TopologyElement:
        cls = arm_types.node_class(resource["type"], resource.get("kind") or "")
        if arm_types.class_path(resource["type"], resource.get("kind") or "") == arm_types.FALLBACK:
            name = resource["type"]
            self.summary.unmapped[name] = self.summary.unmapped.get(name, 0) + 1
        element = cls(
            str(resource.get("name") or resource["id"].rsplit("/", 1)[-1]),
            _detail(resource, with_location=self.many_regions) or None,
        )
        if sizing := _sizing(resource):
            element.attributes["sizing"] = sizing
        rows = [
            ("Type", resource["type"]),
            ("Resource group", str(resource.get("resourceGroup") or "")),
            ("Location", str(resource.get("location") or "")),
            ("Resource ID", resource["id"]),
        ]
        if resource.get("kind"):
            rows.insert(1, ("Kind", str(resource["kind"])))
        attached = []
        for role, part_id in self.parts.get(resource["id"], []):
            part = self.by_id[part_id]
            line = self._part_line(part)
            rows.append((role, " · ".join(bit for bit in (str(part.get("name")), line) if bit)))
            kind = arm_types.node_class(part["type"], part.get("kind") or "")
            attached.append(
                {
                    "role": role,
                    "name": str(part.get("name")),
                    "id": part_id,
                    "detail": line,
                    "component": f"{kind.COLLECTION}:{kind.ICON}",
                }
            )
        rows += [
            (f"tag: {key}", str(value))
            for key, value in sorted((resource.get("tags") or {}).items())
        ]
        if attached:
            element.attributes["attached"] = attached
        if tags := resource.get("tags"):
            # what the tag lens and the Resources table read
            element.attributes["tags"] = {str(key): str(value) for key, value in tags.items()}
        if host := self.host_of.get(resource["id"]):
            rows.insert(1, ("Runs on", str(self.by_id[host].get("name"))))
            element.attributes["runs_on"] = str(self.by_id[host].get("name"))
        if apps := sorted(
            (str(self.by_id[app].get("name")) for app in self.hosted.get(resource["id"], [])),
            key=str.lower,
        ):
            rows.insert(1, ("Hosts", ", ".join(apps)))
            element.attributes["hosts"] = apps
        if owner := self.owner_of.get(resource["id"]):
            rows.insert(1, ("Attached to", str(self.by_id[owner].get("name"))))
            element.attributes["attached_to"] = str(self.by_id[owner].get("name"))
        if finding := self.unused.get(resource["id"]):
            element.attributes["unused"] = finding.model_dump(exclude={"id"})
            rows.insert(0, ("Unused", finding.reason))
            self.summary.unused[finding.rule] = self.summary.unused.get(finding.rule, 0) + 1
        element.table(("Property", "Value"), rows)
        self.elements[resource["id"]] = element
        return element

    def build(self) -> tuple[list[TopologyElement], ImportSummary]:
        drawn = [r for r in self.all_resources if self._drawable(r)]
        self.summary.hidden = len(self.all_resources) - len(drawn)
        # One region: saying it under every icon is noise; it is in the table.
        self.many_regions = (
            len(
                {
                    _lower(r.get("location"))
                    for r in drawn
                    if r.get("location") and _lower(r.get("location")) != "global"
                }
            )
            > 1
        )
        drawn_ids = {r["id"] for r in drawn}

        def order(r: dict[str, Any]) -> tuple[str, str, int, str]:
            host = self.host_of.get(r["id"])
            if host in drawn_ids:
                plan = self.by_id[host]
                return (
                    arm_types.class_path(plan["type"], plan.get("kind") or ""),
                    _lower(plan.get("name")),
                    1,
                    _lower(r.get("name")),
                )
            return (
                arm_types.class_path(r["type"], r.get("kind") or ""),
                _lower(r.get("name")),
                0,
                "",
            )

        drawn.sort(key=order)

        group_frames: dict[str, TopologyElement] = {}
        for key, group in sorted(self.groups.items()):
            group_frames[key] = az.ResourceGroup(str(group.get("name")))
            if key in self.empty:
                group_frames[key].attributes["unused"] = {
                    "rule": "empty-resource-group",
                    "reason": "holds no resource",
                    "bills": "no",
                }
                self.summary.unused["empty-resource-group"] = (
                    self.summary.unused.get("empty-resource-group", 0) + 1
                )
        self.summary.resource_groups = len(group_frames)

        subnet_frames: dict[str, TopologyElement] = {}
        if self.options.view == "network":
            self._networks(drawn, group_frames, subnet_frames)

        for resource in drawn:
            if (
                resource["type"] == "microsoft.network/virtualnetworks"
                and self.options.view == "network"
            ):
                continue
            if resource["id"] in self.attached:
                continue
            holder = None
            spans = []
            if self.options.view == "network":
                spans = [s for s in self.subnets_of(resource) if s in subnet_frames]
                owner = self.by_id.get(self.owner_of.get(resource["id"], ""))
                if not spans and owner is not None:
                    # a disk or public IP sits with what carries it
                    spans = [s for s in self.subnets_of(owner) if s in subnet_frames][:1]
                holder = subnet_frames[spans[0]] if spans else None
                if holder is not None:
                    self.summary.placed += 1
            if holder is not None:
                self.moved_out.add(self._group_key(resource))
            holder = holder or group_frames[self._group_key(resource)]
            card = self.node(resource)
            if len(spans) > 1:
                # Drawn once, in its first subnet; the caption says it spans more,
                # so the other subnets do not read as empty.
                detail = card.attributes.get("detail")
                card.attributes["detail"] = " · ".join(
                    part for part in (detail, f"in {len(spans)} subnets") if part
                )
            holder.add(card)
            self.summary.resources += 1

        outside = self._outside(drawn)
        self._wires(drawn)
        for frame in (*group_frames.values(), *subnet_frames.values()):
            _grid(frame)
        self._signals(group_frames, subnet_frames)
        return self._roots(group_frames) + outside, self.summary

    # -- changes and findings ---------------------------------------------
    def _stand_in(
        self,
        resource_id: str,
        group_frames: dict[str, TopologyElement],
        subnet_frames: dict[str, TopologyElement],
        seen: frozenset[str] = frozenset(),
    ) -> tuple[TopologyElement | None, bool]:
        """The card or frame a resource's changes and findings go on, and
        whether it is the resource's own: a part goes on the card that lists
        it, a subnet's child on its network, an NSG drawn as a badge on its
        first subnet, a deleted resource on its resource group. Plumbing left
        out of the picture has none."""
        if resource_id in seen:
            return None, False
        seen = seen | {resource_id}
        for drawn in (self.elements, subnet_frames, self.vnet_frames):
            if resource_id in drawn:
                return drawn[resource_id], True
        if resource_id in self.attached:
            props = self.by_id[resource_id].get("properties") or {}
            for subnet in props.get("subnets") or []:
                if (frame := subnet_frames.get(_lower((subnet or {}).get("id")))) is not None:
                    return frame, False
        if owner := self.owner_of.get(resource_id):
            return self._stand_in(owner, group_frames, subnet_frames, seen)[0], False
        head, _, tail = resource_id.partition("/providers/")
        parts = tail.split("/")
        if len(parts) > 3:
            top = f"{head}/providers/{'/'.join(parts[:3])}"
            return self._stand_in(top, group_frames, subnet_frames, seen)[0], False
        if resource_id not in self.by_id:
            # gone (or never read): its resource group, when that is drawn
            bits = resource_id.split("/")
            if len(bits) > 4 and bits[1] == "subscriptions" and bits[3] == "resourcegroups":
                return group_frames.get(f"{bits[2]}/{bits[4]}"), False
        return None, False

    def _signals(
        self,
        group_frames: dict[str, TopologyElement],
        subnet_frames: dict[str, TopologyElement],
    ) -> None:
        """Each change and finding on the card or frame it is about."""
        changes: dict[int, tuple[TopologyElement, list[dict[str, Any]]]] = {}
        for change in self.changes:
            holder, own = self._stand_in(change.target, group_frames, subnet_frames)
            if holder is None:
                continue
            item = change.model_dump(exclude={"target"})
            if not own:
                # said on another's card: the item names what it changed
                item["part"] = change.name
            changes.setdefault(id(holder), (holder, []))[1].append(item)
            self.summary.changes += 1
            self.summary.deleted += change.kind == "Delete"
        for holder, items in changes.values():
            holder.attributes["changes"] = {
                "read": self.taken,
                "count": len(items),
                "items": items[:_CHANGES_LISTED],
            }
        self.summary.changed = len(changes)

        flagged: dict[int, tuple[TopologyElement, list[dict[str, Any]]]] = {}
        for resource_id, findings in self.findings.items():
            holder, own = self._stand_in(resource_id, group_frames, subnet_frames)
            if holder is None:
                continue
            name = resource_id.rsplit("/", 1)[-1]
            original = self.by_id.get(resource_id, {}).get("name") or name
            for finding in findings:
                item = finding.model_dump()
                if not own:
                    item["part"] = str(original)
                flagged.setdefault(id(holder), (holder, []))[1].append(item)
                self.summary.findings[finding.severity] = (
                    self.summary.findings.get(finding.severity, 0) + 1
                )
        for holder, items in flagged.values():
            items.sort(key=lambda item: _SEVERITIES.index(item["severity"]))
            holder.attributes["findings"] = {
                "count": len(items),
                "items": items[:_FINDINGS_LISTED],
            }
        self.summary.flagged = len(flagged)

    def _networks(self, drawn, group_frames, subnet_frames) -> None:
        for vnet in (r for r in drawn if r["type"] == "microsoft.network/virtualnetworks"):
            props = vnet.get("properties") or {}
            frame = az.VNet(_named(str(vnet.get("name")), _prefixes(props, "addressSpace")))
            group_frames[self._group_key(vnet)].add(frame)
            self.vnet_frames[vnet["id"]] = frame
            # a frame has no details table: what it stands for, so a refresh
            # can light a network that changed (discovery/refresh.py)
            frame.attributes["resource_id"] = _lower(vnet["id"])
            subnets = sorted(props.get("subnets") or [], key=lambda s: _lower(s.get("name")))
            if len(subnets) > 1:
                frame.row()
            for subnet in subnets:
                sprops = subnet.get("properties") or {}
                child = az.Subnet(
                    _named(
                        str(subnet.get("name")),
                        _prefixes(sprops, "addressPrefix", "addressPrefixes"),
                    )
                )
                subnet_frames[_lower(subnet.get("id"))] = child
                child.attributes["resource_id"] = _lower(subnet.get("id"))
                frame.add(child)
            self.summary.networks += 1
            self.summary.subnets += len(subnets)

            if self._peers(vnet):
                # A wire to a frame lands on whatever card the frame holds
                # first, so a peering is drawn between cards that stand for it.
                peering = other.Peerings(
                    f"{vnet.get('name')} peering", f"{len(self._peers(vnet))} peer(s)"
                )
                frame.add(peering)
                self.peering_cards[vnet["id"]] = peering

        # What applies to a subnet is a badge on the subnet's top-right
        # corner, where Azure's reference diagrams seat an NSG on its subnet:
        # the NSG on the corner point, then the route table and the NAT
        # gateway leftwards along the top edge, each captioned by name. An
        # NSG can instead sit on a VM's network interface: then it is a card
        # in that VM's subnet, says "on NIC", and is wired to the VM.
        corner: dict[str, list[tuple[int, str, str]]] = {}
        for resource in drawn:
            if resource["type"] not in _EDGE_TYPES:
                continue
            props = resource.get("properties") or {}
            targets = [_lower((s or {}).get("id")) for s in props.get("subnets") or []]
            targets = [t for t in targets if t in subnet_frames]
            for target in targets:
                corner.setdefault(target, []).append(
                    (
                        _EDGE_TYPES.index(resource["type"]),
                        str(resource.get("name")),
                        resource["type"],
                    )
                )
                self.summary.attached += 1
            owners = self._guarded(resource)
            subnet = self.subnet_of(self.by_id[owners[0]]) if owners else None
            if owners:
                card = self.node(resource)
                names = [str(self.by_id[o].get("name")) for o in owners]
                card.attributes["detail"] = (
                    f"on NIC · {names[0]}" if len(names) == 1 else f"on {len(names)} NICs"
                )
                holder = subnet_frames.get(subnet) or group_frames[self._group_key(resource)]
                holder.add(card)
                # A subnet badge describes that attachment, while the card
                # retains the NSG's independent links to guarded NICs.
                if subnet is not None and subnet in subnet_frames and not targets:
                    targets = [subnet]
                self.summary.attached += 1
            if targets or owners:
                self.attached.add(resource["id"])
                self.moved_out.add(self._group_key(resource))
                self.summary.resources += 1
        for target, marks in corner.items():
            for _rank, name, arm_type in sorted(marks):
                # Just the name: the icon says what it is, as in Azure's own
                # diagrams; the editor's table says the rest. A NAT gateway is
                # the subnet's way out, so it sits on the top edge with a bar,
                # the way Azure's NAT gateway diagrams draw it; the rest on the
                # corner.
                side = "edge" if arm_type == "microsoft.network/natgateways" else "corner"
                subnet_frames[target].badge(arm_types.node_class(arm_type), side=side, label=name)

    def _guarded(self, resource: dict[str, Any]) -> list[str]:
        """What an NSG guards through a network interface, in order."""
        owners = [
            self.nic_owner.get(_lower((nic or {}).get("id")))
            for nic in (resource.get("properties") or {}).get("networkInterfaces") or []
        ]
        return list(dict.fromkeys(owner for owner in owners if owner))

    @staticmethod
    def _peers(vnet: dict[str, Any]) -> list[str]:
        """Remote network ids, in the case ARM gave them."""
        found = [
            str(
                ((peering.get("properties") or {}).get("remoteVirtualNetwork") or {}).get("id")
                or ""
            )
            for peering in (vnet.get("properties") or {}).get("virtualNetworkPeerings") or []
        ]
        return [remote for remote in found if remote]

    def _outside(self, drawn: Sequence[dict[str, Any]]) -> list[TopologyElement]:
        """Networks peered from here but not drawn: another subscription, one
        this identity cannot read, or a resource group the filter left out.

        Each gets a card in a subscription and resource group of its own,
        labelled as outside the import, so the peering still has two ends.
        """
        drawn_ids = {r["id"] for r in drawn if r["type"] == "microsoft.network/virtualnetworks"}
        read = {_lower(s.get("id")): str(s.get("name") or "") for s in self.subscriptions}
        frames: dict[str, TopologyElement] = {}
        groups: dict[str, TopologyElement] = {}
        for vnet in (r for r in drawn if r["id"] in drawn_ids):
            for remote in self._peers(vnet):
                key = remote.lower()
                if key in drawn_ids or key in self.outside:
                    continue
                parts = remote.strip("/").split("/")
                if len(parts) < 8:
                    continue
                sub_id, group, name = parts[1], parts[3], parts[-1]
                if sub_id.lower() not in frames:
                    known = read.get(sub_id.lower())
                    label = (
                        f"{known} · filtered out" if known else f"Subscription {sub_id} · not read"
                    )
                    frames[sub_id.lower()] = az.Subscription(label)
                group_key = f"{sub_id.lower()}/{group.lower()}"
                if group_key not in groups:
                    groups[group_key] = az.ResourceGroup(group)
                    frames[sub_id.lower()].add(groups[group_key])
                card = networking.VirtualNetworks(name, "peered · outside this import")
                card.table(
                    ("Property", "Value"), [("Resource ID", remote), ("Subscription", sub_id)]
                )
                groups[group_key].add(card)
                self.outside[key] = card
                self.summary.outside += 1
        return list(frames.values())

    def _link(self, source: TopologyElement, target: TopologyElement, **connection: Any) -> None:
        key = (source.id, target.id)
        if source is target or key in self.wired:
            return
        if connection.get("direction") in ("both", "none") and (target.id, source.id) in self.wired:
            return
        self.wired.add(key)
        source.to(target, **connection)
        self.summary.wires += 1

    def _wires(self, drawn: Sequence[dict[str, Any]]) -> None:
        nodes = self.elements
        # Peerings: network to network, drawn once per pair.
        endpoints = self.peering_cards if self.options.view == "network" else nodes
        for vnet in (r for r in drawn if r["type"] == "microsoft.network/virtualnetworks"):
            source = endpoints.get(vnet["id"])
            for remote in self._peers(vnet):
                target = endpoints.get(remote.lower()) or self.outside.get(remote.lower())
                if source is not None and target is not None:
                    self._link(source, target, label="peering", direction="both")
        # Private endpoints: endpoint to the resource it reaches.
        for endpoint in (r for r in drawn if r["type"] == "microsoft.network/privateendpoints"):
            source = nodes.get(endpoint["id"])
            props = endpoint.get("properties") or {}
            for connection in [
                *(props.get("privateLinkServiceConnections") or []),
                *(props.get("manualPrivateLinkServiceConnections") or []),
            ]:
                cprops = connection.get("properties") or {}
                target = nodes.get(_lower(cprops.get("privateLinkServiceId")))
                if source is not None and target is not None:
                    label = ", ".join(cprops.get("groupIds") or []) or "private link"
                    self._link(source, target, kind="dashed", label=label)
        # An NSG on a network interface guards that one resource.
        for nsg in (r for r in drawn if r["type"] == "microsoft.network/networksecuritygroups"):
            for owner in self._guarded(nsg):
                if nsg["id"] in nodes and owner in nodes:
                    self._link(nodes[nsg["id"]], nodes[owner], kind="dashed", label="NIC")
        # A part to what carries it: a NIC, a disk, a public IP to its VM.
        for part_id, owner in self.owner_of.items():
            if part_id in nodes and owner in nodes:
                role = next(r for r, p in self.parts[owner] if p == part_id)
                self._link(nodes[part_id], nodes[owner], kind="dashed", label=role)
        # A web app to the App Service plan it runs on.
        for app, host in self.host_of.items():
            if app in nodes and host in nodes:
                self._link(nodes[app], nodes[host], kind="dashed", label="runs on")
        # Parent resources to their children: a server to its databases.
        for resource in drawn:
            source = nodes.get(resource["id"])
            parent = _parent_id(resource["id"])
            if source is not None and parent in nodes:
                self._link(nodes[parent], source, kind="dashed")
        if not self.options.references:
            return
        # Property references: a web app to its plan, a cluster to its workspace.
        for resource in drawn:
            source = nodes.get(resource["id"])
            if source is None:
                continue
            parent = _parent_id(resource["id"])
            if resource["type"] in (
                "microsoft.network/privateendpoints",
                "microsoft.network/virtualnetworks",
            ):
                continue
            for ref in _ids_in(resource.get("properties") or {}, skip=_NOT_PLACEMENT):
                if _SUBNET.match(ref) or _NIC.match(ref) or ref == resource["id"]:
                    continue
                target = nodes.get(ref)
                if target is not None and ref != parent:
                    self._link(source, target, kind="dashed")

    def _roots(self, group_frames: dict[str, TopologyElement]) -> list[TopologyElement]:
        by_tenant: dict[str, list[TopologyElement]] = {}
        names: dict[str, str] = {}
        for subscription in self.subscriptions:
            sub_id = _lower(subscription.get("id"))
            children = [
                frame
                for key, frame in sorted(group_frames.items())
                if key.startswith(f"{sub_id}/")
                and not (key in self.moved_out and not frame.children)
            ]
            if self.options.resource_groups and not children:
                continue
            name = str(subscription.get("name") or sub_id)
            if sub_id in self.unreadable:
                # closed to this identity: its frame says so, and the summary why
                frame = az.Subscription(f"{name} · not read")
                frame.attributes["unread"] = (
                    "Azure refused to let the signed-in identity read this subscription; "
                    "it needs at least the Reader role on it"
                )
                self.summary.unread[f"subscription {name}"] = self.unreadable[sub_id]
            else:
                frame = az.Subscription(name)
            frame.add(*children)
            tenant = _lower(subscription.get("tenantId"))
            names.setdefault(tenant, subscription.get("tenantName") or "")
            by_tenant.setdefault(tenant, []).append(frame)
            self.summary.subscriptions += 1
        roots: list[TopologyElement] = []
        for tenant, frames in by_tenant.items():
            if not tenant:
                roots.extend(frames)
                continue
            label = names[tenant] or f"Microsoft Entra tenant {tenant}"
            roots.append(az.Tenant(label).add(*frames))
        return roots


def blueprint(
    snapshot: dict[str, Any],
    options: ImportOptions | None = None,
    *,
    slug: str | None = None,
    title: str | None = None,
    theme: str = "light",
) -> tuple[Blueprint, ImportSummary]:
    """The diagram a snapshot describes, ready to export."""
    options = options or ImportOptions()
    subscriptions = snapshot.get("subscriptions") or []
    if not subscriptions:
        raise ValueError("the snapshot holds no subscription")
    names = [str(s.get("name") or s.get("id")) for s in subscriptions]
    heading = names[0] if len(names) == 1 else f"{len(names)} subscriptions"
    plan = Blueprint.fresh(
        slug or f"azure-{_slug(heading).removeprefix('azure-')}-{options.view}",
        title or f"Azure: {heading} ({options.view} view)",
        "placeholder",
        display=options.display,
        theme=theme,
        providers=("azure",),
    )
    roots, summary = _Builder(snapshot, options).build()
    if not roots:
        raise ValueError("nothing to draw: no resource group matched")
    plan.add(*roots)
    taken = str(snapshot.get("taken") or "")
    try:
        when = datetime.fromisoformat(taken).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        when = taken or "an unknown time"
    plan.description = (
        f"Read from Azure Resource Graph at {when}: {', '.join(names)}. "
        f"{summary.resource_groups} resource group(s) and {summary.resources} resource(s), "
        + (
            "placed by network: virtual networks, subnets and what has an address in them."
            if options.view == "network"
            else "filed by resource group, as Azure Resource Manager holds them."
        )
    )
    return plan, summary
