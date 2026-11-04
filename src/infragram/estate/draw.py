"""An estate into a drawing: the frames it is in, the components, the wires.

``references/terraform.md`` section 3, for every reader alike:

- **Frames** are the resources that contain others: networks, subnets,
  resource groups, clusters, and the places they are in (an AWS region and
  zone, an Azure subscription and location, a Google Cloud project). A
  subnet is public when it maps public addresses or routes to an internet
  gateway.
- **Components** sit in the deepest frame their arguments name, directly
  (``subnet_id``) or through a helper they use (an instance's security group
  names its VPC, a database's subnet group its subnets, a VM's network
  interface its subnet).
- **Wires** come from what the resources say about traffic: an AWS security
  group rule from the groups a source wears to the groups a target wears (or
  from the internet), an Azure network security group's inbound rule from a
  range or application security group to what the group guards, a Google
  Cloud firewall rule from ranges, tags or service accounts to the instances
  it targets, a load balancer to its targets, a resource that is only a wire
  (a DNS alias, a subscription, an event source), and any other argument of
  one drawn resource that names another.

Every resource ends up somewhere in the report: drawn, folded into the
resource it belongs to, left out and why, or drawn as its provider's
generic component because the table has no entry for its type yet.
"""

from __future__ import annotations

import ipaddress
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from pydantic import Field

from ..terraform.hclread import UNKNOWN
from ..terraform.mapping import load_mapping
from ..terraform.model import Record
from .model import Estate, Found, walk_values
from .tables import Role, entry_mains, library_of, role_of

__all__ = ["BOX", "Box", "Card", "Drawing", "Wire", "draw"]

#: How deep a frame kind sits: a component goes into the deepest one it names.
_DEPTH = {
    "cloud": 0,
    "subscription": 1,
    "project": 1,
    "region": 2,
    "resource-group": 3,
    "vpc": 4,
    "network": 4,
    "zone": 5,
    "cluster": 6,
    "subnet-public": 7,
    "subnet-private": 7,
}
#: Arguments that say where a resource sits, and so draw no wire.
_PLACEMENT = frozenset(
    {
        "vpc_id",
        "subnet_id",
        "subnet_ids",
        "subnets",
        "subnetwork",
        "network",
        "vnet_subnet_id",
        "virtual_network_subnet_id",
        "virtual_network_name",
        "virtual_network_id",
        "resource_group_name",
        "location",
        "region",
        "availability_zone",
        "zone",
        "private_network",
        "authorized_network",
        "kubernetes_cluster_id",
        "project",
        "cluster",
        "cluster_name",
        "cluster_identifier",
    }
)
#: Arguments that are membership or identity, not traffic.
_NOT_WIRES = frozenset(
    {
        "vpc_security_group_ids",
        "security_groups",
        "security_group_ids",
        "security_group_id",
        "depends_on",
        "provider",
        "role",
        "role_arn",
        "execution_role_arn",
        "task_role_arn",
        "iam_instance_profile",
        "service_role",
        "instance_profile",
        "key_name",
        "tags",
        "labels",
        "launch_template",
        "id",
        "image_id",
        "ami",
        "network_interface_ids",
        "db_subnet_group_name",
        "subnet_group_name",
        "parameter_group_name",
        "option_group_name",
        "service_plan_id",
        "app_service_plan_id",
        "identity_ids",
        "user_assigned_identity_id",
        "principal_id",
    }
)
#: A port's name on a wire's label.
_PORT_NAMES = {
    22: "SSH",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    389: "LDAP",
    443: "HTTPS",
    445: "SMB",
    636: "LDAPS",
    1433: "MSSQL",
    2049: "NFS",
    3306: "MySQL",
    3389: "RDP",
    5432: "PostgreSQL",
    5672: "AMQP",
    6379: "Redis",
    8883: "MQTT",
    9092: "Kafka",
    11211: "Memcached",
    27017: "MongoDB",
}
#: What a component's subtitle is, first known wins.
_DETAILS = (
    ("instance_type",),
    ("instance_class",),
    ("node_type",),
    ("vm_size",),
    ("size",),
    ("sku_name",),
    ("machine_type",),
    ("settings", "tier"),
    ("default_node_pool", "vm_size"),
    ("tier",),
    ("runtime",),
    ("load_balancer_type",),
    ("database_version",),
    ("sku",),
)
#: What a component is priced as (``--prices``), from the values its resource
#: was read with: (library, service) -> (sizing key, path in the values).
_SIZING: dict[tuple[str, str], tuple[tuple[str, tuple[str, ...]], ...]] = {
    ("aws", "ec2"): (("instance_type", ("instance_type",)),),
}
#: What the element's popup table shows besides where it came from.
_ROWS = (
    "cidr_block",
    "address_space",
    "address_prefixes",
    "ip_cidr_range",
    "availability_zone",
    "location",
    "region",
    "instance_type",
    "instance_class",
    "engine",
    "engine_version",
    "runtime",
    "sku_name",
    "vm_size",
    "size",
    "machine_type",
    "database_version",
    "port",
    "protocol",
    "load_balancer_type",
    "internal",
)
#: A frame's own text beside its name: its address range.
_RANGES = (("cidr_block",), ("address_space",), ("address_prefixes",), ("ip_cidr_range",))
#: Resource names that are a module's convention, not a name.
_GENERIC_NAMES = frozenset(
    {"this", "main", "default", "primary", "example", "current", "self", "all"}
)
#: What a relation between two frames (a peering) is drawn as, per library.
_RELATIONS = {"aws": "vpc-peering-connection", "azure": "peerings", "gcp": "virtual-private-cloud"}
#: The library's outermost frame when the estate names none.
_CLOUD = {
    "aws": ("cloud", "AWS Cloud"),
    "azure": ("subscription", "Azure subscription"),
    "gcp": ("project", "Google Cloud project"),
}


class Card(Record):
    key: str
    library: str
    service_id: str
    caption: str
    detail: str = ""
    rows: list[tuple[str, str]] = Field(default_factory=list)
    #: the resources drawn as this card, kept as they are (never copied)
    sources: list[Any] = Field(default_factory=list)
    #: what ``--prices`` prices the card as, read from its resource (EC2's
    #: instance type); the diagram file writes it as ``.sizing(...)``
    sizing: dict[str, Any] = Field(default_factory=dict)
    #: tags a reader sets itself (Kubernetes labels); a card without any
    #: wears its first resource's ``tags``. The diagram file writes ``.tags(...)``
    tags: dict[str, str] = Field(default_factory=dict)
    #: a panel's shape and tone, read from a drawing's own (compose.md,
    #: Panels); the diagram file writes ``.shape(...)`` and ``.tone(...)``
    shape: str = ""
    tone: str = ""

    def worn_tags(self) -> dict[str, str]:
        """The tags the card wears, less ``Name``, which is its caption."""
        if self.tags:
            return dict(self.tags)
        for source in self.sources:
            tags = getattr(source, "values", {}).get("tags")
            if isinstance(tags, dict):
                return {
                    str(key): str(value)
                    for key, value in tags.items()
                    if key != "Name" and isinstance(value, (str, int, float, bool))
                }
        return {}


class FrameBadge(Record):
    """What applies to a frame, drawn on its top-right corner: a subnet's
    network security group or route table, named by the resource."""

    library: str
    service_id: str
    label: str


class Box(Record):
    key: str
    library: str
    kind: str
    caption: str
    children: list[Box | Card] = Field(default_factory=list)
    source: Found | None = None
    #: ``row`` or ``column`` when the import knows the conventional layout
    #: (availability zones side by side), else the composer's own choice.
    flow: str | None = None
    #: corner badges, nearest the corner first
    badges: list[FrameBadge] = Field(default_factory=list)


class Wire(Record):
    source: str
    target: str
    label: str = ""
    dashed: bool = False
    #: a head at each end: traffic both ways under one label
    both: bool = False
    #: no head at either end: a line that says two things are joined
    plain: bool = False


#: The service id of a plain box (``infragram.nodes.Box``): no vendor
#: artwork, only what it says.
BOX = "box"


class Drawing(Record):
    title: str
    origin: str
    #: the top-level :class:`Box` and :class:`Card` items, kept as they are
    roots: list[Any]
    wires: list[Wire]
    #: address -> what it was drawn as
    drawn: dict[str, str] = Field(default_factory=dict)
    #: address -> what it was folded into, or why it is not drawn
    folded: dict[str, str] = Field(default_factory=dict)
    left_out: dict[str, str] = Field(default_factory=dict)
    #: type -> how many were drawn as the generic component
    unmapped: Counter[str] = Field(default_factory=Counter)
    notes: list[str] = Field(default_factory=list)
    #: what one read item is called: a Terraform ``resource``, a diagram's ``shape``
    thing: str = "resource"
    #: ``right`` or ``down`` when the source says how the whole picture runs
    direction: str | None = None
    #: a plan's count, ``3 to add, 1 to destroy``, for the band above the drawing
    plan: str = ""
    #: tone -> what it means, for the legend: ``Diagram(tones=...)``
    tones: dict[str, str] = Field(default_factory=dict)

    def walk(self) -> list[Box | Card]:
        out: list[Box | Card] = []

        def visit(item: Box | Card) -> None:
            out.append(item)
            if isinstance(item, Box):
                for child in item.children:
                    visit(child)

        for root in self.roots:
            visit(root)
        return out

    @property
    def description(self) -> str:
        items = self.walk()
        cards = sum(1 for item in items if isinstance(item, Card))
        frames = sum(1 for item in items if isinstance(item, Box))
        return (
            f"Drawn from {self.origin}: {len(self.drawn)} {self.thing}s as {cards} components "
            f"in {frames} frames, with {len(self.wires)} wires."
        )


def _matches(text: str | None, wanted: str) -> bool:
    """Whether an argument's value is the one an ``ignore_when`` names: that
    value, or with a trailing ``*`` any value it begins."""
    if text is None:
        return False
    return text.startswith(wanted[:-1]) if wanted.endswith("*") else text == wanted


def _text(value: Any) -> str | None:
    if value is UNKNOWN or value is None or isinstance(value, (dict, list)):
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    return text or None


def caption_of(found: Found) -> str:
    """The resource's own name: its Name tag, its name, else its address's name."""
    tags = found.values.get("tags")
    if isinstance(tags, dict) and _text(tags.get("Name")):
        return str(_text(tags.get("Name")))
    for key in (
        "name",
        "identifier",
        "cluster_identifier",
        "function_name",
        "bucket",
        "domain_name",
        "display_name",
        "queue_name",
    ):
        text = _text(found.values.get(key))
        if text:
            return text
    index = re.search(r"\[([^\[\]]+)\]$", found.address)
    if found.name in _GENERIC_NAMES:
        # a module's "this" says nothing on a card: the key of the module
        # instance it is in says which one (a module repeated over a map of
        # the diagram's items), else its own key, else its type what it is
        keyed = re.findall(r'module\.[A-Za-z_][\w-]*\["([^"]+)"\]', found.address)
        if keyed:
            # and its own index past the first: two subnets of one network differ
            own = index.group(1).strip('"') if index else "0"
            return keyed[-1] if own == "0" else f"{keyed[-1]}[{own}]"
        if index and index.group(1).startswith('"'):
            return index.group(1).strip('"')
        name = found.type.split("_", 1)[-1].replace("_", " ")
    else:
        name = found.name
    return f"{name}[{index.group(1).strip(chr(34))}]" if index else name


def _first(value: Any) -> str | None:
    if isinstance(value, list):
        return _text(value[0]) if value else None
    return _text(value)


def _detail(found: Found) -> str:
    for path in _DETAILS:
        text = _first(found.value(*path))
        if text:
            return text
    engine = _text(found.values.get("engine"))
    if engine:
        version = _text(found.values.get("engine_version"))
        return f"{engine} {version}" if version else engine
    return ""


def _sizing(library: str, service: str, found: Found) -> dict[str, Any]:
    """What a card is priced as, from its resource, as far as it says."""
    sizing: dict[str, Any] = {}
    for key, path in _SIZING.get((library, service), ()):
        text = _first(found.value(*path))
        if text:
            sizing[key] = text
    return sizing


def _rows(found: Found) -> list[tuple[str, str]]:
    rows = [("Resource", found.address)]
    if found.source:
        rows.append(("Read from", found.source))
    identity = _text(found.values.get("id")) or _text(found.values.get("arn"))
    if identity and identity != found.name and identity not in found.address:
        rows.append(("ID", identity))
    for key in _ROWS:
        value = found.values.get(key)
        text = _first(value) if isinstance(value, list) and len(value) == 1 else _text(value)
        if text:
            rows.append((key.replace("_", " "), text))
    return rows


def _needs_network(library: str, service_id: str) -> bool:
    """Whether the export writes this component only inside a network."""
    from ..terraform.mapping import load_mapping

    rule = load_mapping(library).component(service_id) if service_id else None
    return rule is not None and rule.requires in ("network", "subnet")


def _module_of(address: str) -> str:
    """``module.vpc.aws_subnet.a[0]`` -> ``module.vpc.``; ``""`` at the root."""
    parts, out = address.split("."), ""
    while len(parts) > 2 and parts[0] == "module":
        out += f"module.{parts[1]}."
        parts = parts[2:]
    return re.sub(r"\[[^\]]*\]", "", out)


def _port_label(protocol: Any, low: Any, high: Any) -> str:
    protocol = str(protocol if protocol not in (None, UNKNOWN) else "tcp").lower()
    if protocol in ("-1", "all"):
        return "all traffic"
    if (
        not isinstance(low, (int, float))
        or not isinstance(high, (int, float))
        or isinstance(low, bool)
    ):
        return protocol.upper()
    low, high = int(low), int(high)
    if low == high:
        name = _PORT_NAMES.get(low)
        return f"{name} :{low}" if name else f"{protocol.upper()} :{low}"
    if low == 0 and high >= 65535:
        return f"all {protocol.upper()}"
    return f"{protocol.upper()} {low}-{high}"


def _texts(values: dict[str, Any], *keys: str) -> list[str]:
    """The text of each argument named, one or a list, in order, once each."""
    out: list[str] = []
    for key in keys:
        value = values.get(key)
        for item in value if isinstance(value, list) else [value]:
            text = _text(item)
            if text and text not in out:
                out.append(text)
    return out


def _port_ranges(values: list[str]) -> list[tuple[int, int]]:
    """``["443", "8000-8080"]`` as ``[(443, 443), (8000, 8080)]``."""
    out: list[tuple[int, int]] = []
    for text in values:
        low, _, high = text.partition("-")
        try:
            out.append((int(low), int(high or low)))
        except ValueError:
            continue
    return out


def _allowed(protocol: Any, ports: list[str] | None) -> list[str]:
    """The labels a rule that allows draws: ``HTTPS :443``, ``TCP 8000-8080``,
    ``all TCP`` when ``ports`` is None (every port), the protocol alone when
    the reader could not know the port. ICMP and the like draw nothing: a
    ping is no flow a diagram shows."""
    name = (_text(protocol) or "tcp").lower()
    name = {"6": "tcp", "17": "udp", "132": "sctp"}.get(
        name, name
    )  # Google Cloud takes numbers too
    if name in ("*", "all", "-1"):
        if ports is None:
            return ["all traffic"]
        name = "tcp"
    if name not in ("tcp", "udp", "sctp"):
        return []
    if ports is None:
        return [f"all {name.upper()}"]
    return list(
        dict.fromkeys(_port_label(name, low, high) for low, high in _port_ranges(ports))
    ) or [name.upper()]


def _network(text: Any) -> Network | None:
    try:
        return ipaddress.ip_network(str(text), strict=False)
    except ValueError:
        return None


Network = ipaddress.IPv4Network | ipaddress.IPv6Network
Address = ipaddress.IPv4Address | ipaddress.IPv6Address
#: Sources that stand for anyone, drawn as the internet.
_ANYONE = frozenset({"*", "any", "internet", "0.0.0.0/0", "::/0"})
#: Where Google's load balancers and health checks reach a backend from.
_GOOGLE_FRONT_ENDS = frozenset({"35.191.0.0/16", "130.211.0.0/22"})
#: A subnet frame's address ranges, per cloud.
_SUBNET_RANGES = ("address_prefixes", "address_prefix", "ip_cidr_range", "cidr_block")
#: Google Cloud's managed instance groups, which wear their template's tags.
_INSTANCE_GROUPS = (
    "google_compute_instance_group_manager",
    "google_compute_region_instance_group_manager",
)
#: Azure scale sets: each names its network and application security groups on its own interface.
_SCALE_SETS = (
    "azurerm_linux_virtual_machine_scale_set",
    "azurerm_windows_virtual_machine_scale_set",
    "azurerm_orchestrated_virtual_machine_scale_set",
)
#: A resource's own private address, per cloud.
_PRIVATE_ADDRESSES = frozenset({"private_ip_address", "private_ip", "network_ip"})


def _inside(inner: Network, outer: Network) -> bool:
    """Whether one range lies wholly in another; ranges of two versions never do."""
    if isinstance(inner, ipaddress.IPv4Network) and isinstance(outer, ipaddress.IPv4Network):
        return inner.subnet_of(outer)
    if isinstance(inner, ipaddress.IPv6Network) and isinstance(outer, ipaddress.IPv6Network):
        return inner.subnet_of(outer)
    return False


@dataclass
class _Reach:
    """Where each card sits on the network, for a rule that names a range."""

    #: card key -> the subnet frame it is drawn in, however deep (a node pool
    #: in its cluster in the subnet)
    subnet: dict[str, str]
    #: subnet frame key -> its address ranges
    ranges: dict[str, list[Network]]
    #: card key -> the private addresses its resources hold
    addresses: dict[str, list[Address]]

    def within(self, network: Network) -> list[str]:
        """The cards a range reaches: all in a subnet it holds whole, and each
        whose own address it holds."""
        whole = {
            key for key, ranges in self.ranges.items() if any(_inside(r, network) for r in ranges)
        }
        out = [card for card, place in self.subnet.items() if place in whole]
        out += [
            card
            for card, held in self.addresses.items()
            if card not in out and any(a.version == network.version and a in network for a in held)
        ]
        return out

    def exactly(self, network: Network) -> set[str]:
        """The subnet frames whose own range the range is: it names them."""
        return {key for key, ranges in self.ranges.items() if network in ranges}

    def holds(self, network: Network, cards: list[str]) -> bool:
        """Whether a range holds whole a subnet one of the cards is in: it
        says anything inside may pass, which is no one flow to draw."""
        places = {self.subnet[card] for card in cards if card in self.subnet}
        return any(_inside(r, network) for place in places for r in self.ranges.get(place, []))


def _humanize(path: str) -> str:
    parts = path.split(".")
    word = parts[0] if len(parts) > 1 else parts[-1]
    word = re.sub(r"_(ids?|arns?|names?|urls?|uris?)$", "", word)
    return word.replace("_", " ")


class _Drawer:
    def __init__(self, estate: Estate) -> None:
        self.estate = estate
        self.boxes: dict[str, Box] = {}
        self.cards: dict[str, Card] = {}
        #: drawn key -> the key of the frame it is in ("" at the top)
        self.parent: dict[str, str] = {}
        #: resource address -> the drawn key it became or was folded into
        self.key: dict[str, str] = {}
        self.roles: dict[str, Role] = {}
        self.wires: dict[tuple[str, str], Wire] = {}
        self.drawing = Drawing(estate.title, estate.origin, [], [], notes=list(estate.notes))
        self.by_id: dict[str, Found] = {}
        for found in estate.resources:
            for attribute in ("id", "arn"):
                value = found.values.get(attribute)
                if isinstance(value, str) and value:
                    self.by_id.setdefault(value, found)

    # ------------------------------------------------------------ roles
    def classify(self) -> None:
        for found in self.estate.resources:
            role = role_of(found.type)
            if found.mode == "data" and role.kind != "frame":
                role = Role("ignore")
            library = library_of(found.type)
            when = load_mapping(library).imports.ignore_when.get(found.type) if library else None
            if when and all(
                _matches(_text(found.values.get(key)), value) for key, value in when.items()
            ):
                role = Role("ignore")
            self.roles[found.address] = role

    # ------------------------------------------------------------ frames
    def synthetic(self, key: str, library: str, kind: str, caption: str, parent: str) -> str:
        if key not in self.boxes:
            self.boxes[key] = Box(key, library, kind, caption)
            self.parent[key] = parent
        return key

    def top(self, library: str) -> str:
        kind, caption = _CLOUD[library]
        named = self.named_top(library)
        return self.synthetic(f"top:{library}", library, kind, named or caption, "")

    def named_top(self, library: str) -> str | None:
        if library == "azure":
            for found in self.estate.of_type("azurerm_subscription"):
                return _text(found.values.get("display_name")) or _text(
                    found.values.get("subscription_id")
                )
        return None

    def region_box(self, library: str, region: str | None) -> str:
        top = self.top(library)
        if not region:
            return top
        return self.synthetic(f"region:{library}:{region}", library, "region", region, top)

    def project_box(self, project: str | None) -> str:
        if not project:
            return self.top("gcp")
        return self.synthetic(f"project:{project}", "gcp", "project", f"Project · {project}", "")

    def subnet_kind(self, found: Found) -> str:
        if found.type != "aws_subnet":
            return "subnet-private"
        if found.values.get("map_public_ip_on_launch") is True:
            return "subnet-public"
        for association in self.estate.of_type("aws_route_table_association"):
            if found not in self.estate.targets(association, "subnet_id"):
                continue
            for table in self.estate.targets(association, "route_table_id"):
                # the table's own routes, or route resources that name it
                routes = [
                    table,
                    *(
                        route
                        for route in self.estate.of_type("aws_route")
                        if table in self.estate.targets(route, "route_table_id")
                    ),
                ]
                if any(
                    gateway.type == "aws_internet_gateway"
                    for route in routes
                    for gateway in self.estate.targets(route, "gateway_id")
                ):
                    return "subnet-public"
        return "subnet-private"

    def frame_caption(self, found: Found, kind: str) -> str:
        caption = caption_of(found)
        for path in _RANGES:
            text = _first(found.value(*path))
            if text and text not in caption:
                caption = f"{caption} · {text}"
                break
        if found.mode == "data":
            caption += " (existing)"
        return caption

    def frames(self) -> None:
        found_frames = [f for f in self.estate.resources if self.roles[f.address].kind == "frame"]
        for found in found_frames:
            library = library_of(found.type) or "aws"
            kind = self.roles[found.address].value
            if kind.startswith("subnet"):
                kind = self.subnet_kind(found)
            self.boxes[found.address] = Box(
                found.address, library, kind, self.frame_caption(found, kind), source=found
            )
            self.key[found.address] = found.address
            self.drawing.drawn[found.address] = f"{kind} frame"
        for found in found_frames:
            self.parent[found.address] = self.frame_parent(found)

    def frame_parent(self, found: Found) -> str:
        library = library_of(found.type) or "aws"
        kind = self.boxes[found.address].kind
        if library == "aws":
            if kind == "vpc":
                return self.region_box("aws", found.region)
            if kind.startswith("subnet"):
                vpcs = self.boxes_named(found, ("vpc_id",), ("vpc",))
                if not vpcs:
                    return self.region_box("aws", found.region)
                zone = _text(found.values.get("availability_zone"))
                if zone:
                    return self.synthetic(f"zone:{vpcs[0]}:{zone}", "aws", "zone", zone, vpcs[0])
                return vpcs[0]
            return self.region_box("aws", found.region)
        if library == "azure":
            location = _text(found.values.get("location")) or found.region
            if kind == "resource-group":
                return self.region_box("azure", location)
            if kind == "network":
                groups = self.boxes_named(found, ("resource_group_name",), ("resource-group",))
                return groups[0] if groups else self.region_box("azure", location)
            if kind.startswith("subnet"):
                networks = self.boxes_named(
                    found, ("virtual_network_name", "virtual_network_id"), ("network",)
                )
                if networks:
                    return networks[0]
            if kind == "cluster":
                subnets = self.boxes_named(
                    found, ("vnet_subnet_id",), ("subnet-private", "subnet-public")
                )
                if subnets:
                    return subnets[0]
            groups = self.boxes_named(found, ("resource_group_name",), ("resource-group",))
            return groups[0] if groups else self.region_box("azure", location)
        # Google Cloud: a VPC network is global, its subnets regional
        if kind.startswith("subnet"):
            networks = self.boxes_named(found, ("network",), ("vpc",))
            if networks:
                return networks[0]
        if kind == "cluster":
            networks = self.boxes_named(found, ("subnetwork",), ("subnet-private", "subnet-public"))
            if networks:
                return networks[0]
        return self.project_box(_text(found.values.get("project")))

    def boxes_named(
        self, found: Found, arguments: tuple[str, ...], kinds: tuple[str, ...]
    ) -> list[str]:
        named = [
            t.address
            for t in self.estate.targets(found, *arguments)
            if t.address in self.boxes and self.boxes[t.address].kind in kinds
        ]
        if named or not found.type.endswith(("subnet", "subnetwork")):
            return named
        # A subnet whose network the reader could not follow (a registry
        # module sets it through a local a plan does not expand) belongs to
        # the one network its own module declares, when there is one.
        module = _module_of(found.address)
        alone = [
            key
            for key, box in self.boxes.items()
            if box.kind in kinds and box.source is not None and _module_of(key) == module
        ]
        return alone if len(alone) == 1 else []

    # ------------------------------------------------------------ components
    def container(self, found: Found) -> str:
        """The deepest frame the resource names, directly or through a part it uses."""
        candidates = [
            t.address
            for t in self.estate.targets(found, *_PLACEMENT, "subnet_mapping")
            if t.address in self.boxes
        ]
        for addresses in found.references.values():
            for address in addresses:
                for target in self.estate.resolve(address):
                    if target.address in self.boxes or self.roles.get(
                        target.address, Role("other")
                    ).kind not in ("part", "ignore"):
                        continue
                    candidates += [
                        t.address
                        for t in self.estate.targets(target, *_PLACEMENT)
                        if t.address in self.boxes
                    ]
        if candidates:
            # the frame deepest in the tree as built (a node pool's cluster sits
            # inside the subnet the pool also names), then the deepest kind
            return max(
                candidates, key=lambda key: (self.nesting(key), _DEPTH.get(self.boxes[key].kind, 0))
            )
        library = library_of(found.type) or "aws"
        if _needs_network(library, self.roles[found.address].value):
            # a gateway or an endpoint whose network the reader could not
            # follow sits in the one network its module declares
            module = _module_of(found.address)
            alone = [
                key
                for key, box in self.boxes.items()
                if box.kind in ("vpc", "network")
                and box.source is not None
                and _module_of(key) == module
            ]
            if len(alone) == 1:
                return alone[0]
        if library == "aws":
            return self.region_box("aws", found.region)
        if library == "azure":
            return self.region_box("azure", _text(found.values.get("location")) or found.region)
        return self.project_box(_text(found.values.get("project")))

    def frame_relation(self, wire: Wire) -> None:
        """A wire with a frame at an end is not drawn: both renderers seat such
        a wire on the card inside the frame nearest the other end, where it
        would read as a wire to that card. A card joined to a frame (a transit
        gateway's attachment) says so in its popup; two frames joined (a
        peering) get a card in the first of them that names the other."""
        label = wire.label or "connects"
        source, target = self.boxes.get(wire.source), self.boxes.get(wire.target)
        if source is None or target is None:
            card = self.cards[wire.source] if source is None else self.cards[wire.target]
            frame = target if source is None else source
            assert frame is not None
            row = (label if source is None else f"{label} (from)", frame.caption)
            if row not in card.rows:
                card.rows.append(row)
            self.drawing.notes.append(
                f"{card.caption} {label} {frame.caption}: in its popup, "
                "as a wire cannot end on a frame"
            )
            return
        key = f"relation:{wire.source}:{wire.target}"
        if key in self.cards or f"relation:{wire.target}:{wire.source}" in self.cards:
            return
        service = _RELATIONS.get(source.library)
        if service is None:
            return
        name = target.caption.split(" · ")[0]
        card = Card(
            key,
            source.library,
            service,
            f"{label} to {name}",
            "",
            [("from", source.caption), ("to", target.caption)],
        )
        self.cards[key] = card
        self.parent[key] = source.key
        source.children.append(card)
        self.drawing.notes.append(
            f"{source.caption.split(' · ')[0]} {label} {name}: drawn as a card in "
            f"{source.caption.split(' · ')[0]}, as a wire cannot end on a frame"
        )

    def nesting(self, key: str) -> int:
        depth = 0
        while key:
            key = self.parent.get(key, "")
            depth += 1
        return depth

    def components(self) -> None:
        collapsed: dict[str, Card] = {}
        for found in self.estate.resources:
            role = self.roles[found.address]
            library = library_of(found.type)
            if library is None:
                continue
            if role.kind in ("component", "unmapped"):
                service = role.value
                if role.kind == "unmapped":
                    if not service:
                        self.drawing.left_out[found.address] = f"no mapping for {found.type}"
                        continue
                    self.drawing.unmapped[found.type] += 1
                self.cards[found.address] = Card(
                    found.address,
                    library,
                    service,
                    caption_of(found),
                    found.type if role.kind == "unmapped" else _detail(found),
                    _rows(found),
                    [found],
                    _sizing(library, service, found),
                )
                self.key[found.address] = found.address
                self.parent[found.address] = self.container(found)
                self.drawing.drawn[found.address] = service
            elif role.kind == "collapse":
                place = self.container(found)
                key = f"collapse:{place}:{role.value}"
                card = collapsed.get(key)
                if card is None:
                    card = Card(key, library, role.value, role.value.replace("-", " ").title())
                    collapsed[key] = card
                    self.cards[key] = card
                    self.parent[key] = place
                card.sources.append(found)
                card.rows.append(("Resource", found.address))
                card.detail = (
                    f"{len(card.sources)} {found.type.split('_', 1)[1].replace('_', ' ')}s"
                    if len({s.type for s in card.sources}) == 1
                    else f"{len(card.sources)} resources"
                )
                self.key[found.address] = key
                self.drawing.drawn[found.address] = (
                    f"{role.value} (one card for {len(card.sources)})"
                )

    def default_node_pools(self) -> None:
        """An AKS cluster frame holds its default node pool, as the export writes it."""
        for found in self.estate.of_type("azurerm_kubernetes_cluster"):
            if found.address not in self.boxes:
                continue
            name = _text(found.value("default_node_pool", "name"))
            key = f"{found.address}#default_node_pool"
            self.cards[key] = Card(
                key,
                "azure",
                "kubernetes-services",
                name or "default",
                _first(found.value("default_node_pool", "vm_size")) or "",
                [("Resource", f"{found.address}.default_node_pool"), ("Read from", found.source)],
                [found],
            )
            self.parent[key] = found.address

    # ------------------------------------------------------------ parts
    def parts(self) -> None:
        used_by: dict[str, str] = {}
        for found in self.estate.resources:
            if found.address in self.key:
                for addresses in found.references.values():
                    for address in addresses:
                        for target in self.estate.resolve(address):
                            library = library_of(target.type)
                            if library and found.type in entry_mains(library).get(target.type, ()):
                                # its own entry's main: an SQL server is its database's,
                                # not the private endpoint's that connects to it
                                used_by[target.address] = found.address
                            else:
                                used_by.setdefault(target.address, found.address)
        # a part of a part (a Front Door's origin, of an origin group of the
        # profile) folds once its owner has: until nothing more folds
        pending = [
            found for found in self.estate.resources if self.roles[found.address].kind == "part"
        ]
        while pending:
            rest = []
            for found in pending:
                owners = [
                    t
                    for t in self.estate.targets(found, *self.roles[found.address].owners)
                    if t.address in self.key
                ]
                if owners:
                    self.key[found.address] = self.key[owners[0].address]
                    self.drawing.folded[found.address] = f"part of {owners[0].address}"
                else:
                    rest.append(found)
            if len(rest) == len(pending):
                break
            pending = rest
        for found in self.estate.resources:
            role = self.roles[found.address]
            if role.kind == "part":
                if found.address in self.drawing.folded:
                    continue
                user = used_by.get(found.address)
                if user and user in self.cards:
                    # a wire to it goes to what uses it: a private endpoint
                    # to an SQL server reaches the database on it
                    self.key[found.address] = self.key[user]
                self.drawing.folded[found.address] = (
                    f"used by {user}" if user else "a helper resource nothing drawn uses"
                )
            elif role.kind == "ignore":
                self.drawing.left_out[found.address] = (
                    "a data source"
                    if found.mode == "data"
                    else "not architecture (identity, policy, configuration or a helper)"
                )
            elif role.kind == "other" and found.type == "azapi_resource":
                azure_type = _text(found.values.get("type"))
                self.drawing.left_out[found.address] = (
                    f"an azapi resource of {azure_type.split('@', 1)[0]}, which the import does not draw"
                    if azure_type
                    else "an azapi resource whose Azure type only a plan knows"
                )
            elif role.kind == "other":
                self.drawing.left_out[found.address] = (
                    f"a resource of the {found.provider} provider; this edition draws Azure only"
                )
            elif role.kind == "edge":
                self.drawing.folded[found.address] = "drawn as a wire"

    # ------------------------------------------------------------ wires
    def drawn_key(self, found: Found) -> str | None:
        return self.key.get(found.address)

    def own_card(self, found: Found) -> bool:
        """Whether the resource is drawn as a card of its own."""
        return (
            self.roles[found.address].kind in ("component", "unmapped")
            and found.address in self.cards
        )

    def wire(
        self, source: str | None, target: str | None, label: str, dashed: bool = False
    ) -> None:
        if not source or not target or source == target:
            return
        if source in self.boxes and target in self.boxes and self.inside(source, target):
            return
        existing = self.wires.get((source, target))
        if existing is None:
            self.wires[(source, target)] = Wire(source, target, label, dashed)
            return
        labels = existing.label.split(" · ") if existing.label else []
        if not label or label in labels:
            return
        # one port said twice keeps the name that says more: a load balancer's
        # "HTTP :8080" over its security group's "TCP :8080"
        port = re.search(r":\d+$", label)
        for i, known in enumerate(labels):
            if port and known.endswith(port.group(0)):
                if known.split(" ")[0] in ("TCP", "UDP"):
                    labels[i] = label
                existing.label = " · ".join(labels)
                return
        if len(labels) < 3:
            existing.label = " · ".join([*labels, label])

    def inside(self, a: str, b: str) -> bool:
        for start, end in ((a, b), (b, a)):
            key = self.parent.get(start)
            while key:
                if key == end:
                    return True
                key = self.parent.get(key)
        return False

    def security_group_wires(self) -> None:
        estate = self.estate
        wearers: dict[str, list[str]] = {}
        for found in estate.resources:
            # what is drawn wears a group, and so does it through a part folded
            # into it (an EFS file system through its mount targets); a group
            # wears none, for its own rules name groups too
            key = self.drawn_key(found)
            if (
                key is None
                or key not in self.cards
                or found.type == "aws_security_group"
                or self.roles[found.address].kind not in ("component", "unmapped", "part")
            ):
                continue
            for group in estate.targets(
                found, "vpc_security_group_ids", "security_groups", "security_group_ids"
            ):
                if group.type == "aws_security_group" and key not in wearers.setdefault(
                    group.address, []
                ):
                    wearers[group.address].append(key)
        rules: list[tuple[str, list[str], str]] = []
        for rule in estate.of_type("aws_vpc_security_group_ingress_rule"):
            label = _port_label(
                rule.values.get("ip_protocol"),
                rule.values.get("from_port"),
                rule.values.get("to_port"),
            )
            sources = [g.address for g in estate.targets(rule, "referenced_security_group_id")]
            if (
                rule.values.get("cidr_ipv4") == "0.0.0.0/0"
                or rule.values.get("cidr_ipv6") == "::/0"
            ):
                sources.append("internet")
            for group in estate.targets(rule, "security_group_id"):
                rules.append((group.address, sources, label))
        for rule in estate.of_type("aws_security_group_rule"):
            if rule.values.get("type") != "ingress":
                continue
            label = _port_label(
                rule.values.get("protocol"),
                rule.values.get("from_port"),
                rule.values.get("to_port"),
            )
            sources = [g.address for g in estate.targets(rule, "source_security_group_id")]
            if "0.0.0.0/0" in (rule.values.get("cidr_blocks") or []):
                sources.append("internet")
            for group in estate.targets(rule, "security_group_id"):
                rules.append((group.address, sources, label))
        for group in estate.of_type("aws_security_group"):
            blocks = [b for b in group.values.get("ingress") or [] if isinstance(b, dict)]
            named = estate.targets(group, "security_groups")
            # A configuration knows no group ids: each block's references
            # stand in their place, in the order the blocks name them. The
            # reader keeps them per argument, not per block, so they are
            # shared out by each block's unknown items, when the counts agree
            # (a group named twice is listed once, and then they do not).
            refs = group.references.get("ingress.security_groups", [])
            slots = [
                [i for i in ids if not isinstance(i, str)]
                if isinstance(ids := b.get("security_groups"), list)
                else []
                for b in blocks
            ]
            shared = bool(refs) and sum(len(slot) for slot in slots) == len(refs)
            at = 0
            for block, slot in zip(blocks, slots, strict=True):
                label = _port_label(
                    block.get("protocol"), block.get("from_port"), block.get("to_port")
                )
                sources = []
                ids = block.get("security_groups")
                if isinstance(ids, list) and ids and all(isinstance(i, str) for i in ids):
                    sources += [self.by_id[i].address for i in ids if i in self.by_id]
                elif shared and isinstance(ids, list):
                    sources += [self.by_id[i].address for i in ids if i in self.by_id]
                    for address in refs[at : at + len(slot)]:
                        sources += [
                            g.address
                            for g in estate.resolve(address)
                            if g.type == "aws_security_group" and g is not group
                        ]
                    at += len(slot)
                elif len([b for b in blocks if b.get("security_groups")]) == 1 and block.get(
                    "security_groups"
                ):
                    sources += [g.address for g in named]
                if "0.0.0.0/0" in (block.get("cidr_blocks") or []):
                    sources.append("internet")
                rules.append((group.address, sources, label))
        for target_group, sources, label in rules:
            for source in sources:
                starts = ["internet"] if source == "internet" else wearers.get(source, [])
                for start in starts:
                    for end in wearers.get(target_group, []):
                        self.wire(start, end, label)

    # ------------------------------------------------------------ Azure and Google Cloud rules
    def ancestors(self, key: str) -> list[str]:
        out: list[str] = []
        parent = self.parent.get(key, "")
        while parent:
            out.append(parent)
            parent = self.parent.get(parent, "")
        return out

    def reach(self) -> _Reach:
        subnet: dict[str, str] = {}
        for key in self.cards:
            place = next(
                (
                    a
                    for a in self.ancestors(key)
                    if a in self.boxes and self.boxes[a].kind.startswith("subnet")
                ),
                None,
            )
            if place is not None:
                subnet[key] = place
        ranges = {
            key: [n for text in _texts(box.source.values, *_SUBNET_RANGES) if (n := _network(text))]
            for key, box in self.boxes.items()
            if box.source is not None and box.kind.startswith("subnet")
        }
        addresses: dict[str, list[Address]] = {}
        for found in self.estate.resources:
            card = self.drawn_key(found)
            if card is None or card not in self.cards:
                continue
            for path, value in walk_values(found.values):
                if path.rsplit(".", 1)[-1] in _PRIVATE_ADDRESSES and isinstance(value, str):
                    try:
                        addresses.setdefault(card, []).append(ipaddress.ip_address(value))
                    except ValueError:
                        continue
        return _Reach(subnet, ranges, addresses)

    def cards_of(self, found: list[Found]) -> list[str]:
        """The cards resources are drawn as or folded into (a network interface: its VM)."""
        return [key for f in found if (key := self.drawn_key(f)) and key in self.cards]

    def wires_between(self, sources: list[str], targets: list[str], labels: list[str]) -> int:
        if not labels:
            return 0
        drawn = 0
        for source in dict.fromkeys(sources):
            for target in dict.fromkeys(targets):
                if source != target:
                    for label in labels:
                        self.wire(source, target, label)
                    drawn += 1
        return drawn

    def subnet_badges(self) -> None:
        """What applies to an Azure subnet is a badge on its top-right corner,
        where Azure's reference diagrams seat an NSG on its subnet: the NSG on
        the corner point, the route table beside it, each named by the
        resource. One NSG on two subnets is drawn on each. The NSG's rules
        still draw the wires they allow; an NSG on a network interface alone
        is drawn only as those wires, the way the Terraform export writes a
        machine's rules back (an NSG on its interface)."""
        estate = self.estate
        placed: dict[str, list[tuple[int, str, FrameBadge]]] = {}
        badged: dict[str, list[str]] = {}
        for rank, (association_type, argument, service) in enumerate(
            (
                (
                    "azurerm_subnet_network_security_group_association",
                    "network_security_group_id",
                    "network-security-groups",
                ),
                ("azurerm_subnet_route_table_association", "route_table_id", "route-tables"),
            )
        ):
            for association in estate.of_type(association_type):
                subnets = [
                    s.address
                    for s in estate.targets(association, "subnet_id")
                    if s.address in self.boxes
                ]
                for held in estate.targets(association, argument):
                    for subnet in subnets:
                        badge = FrameBadge("azure", service, caption_of(held))
                        if all(address != held.address for _, address, _ in placed.get(subnet, [])):
                            placed.setdefault(subnet, []).append((rank, held.address, badge))
                            badged.setdefault(held.address, []).append(self.boxes[subnet].caption)
                    if subnets:
                        self.drawing.left_out.pop(association.address, None)
                        self.drawing.folded[association.address] = (
                            "drawn as the badge on its subnet"
                        )
        for subnet, marks in placed.items():
            self.boxes[subnet].badges = [
                badge for _, _, badge in sorted(marks, key=lambda mark: mark[0])
            ]
        for address, subnets in badged.items():
            count = len(dict.fromkeys(subnets))
            said = (
                "a badge on its subnet" if count == 1 else f"a badge on each of its {count} subnets"
            )
            before = self.drawing.folded.get(address, "")
            self.drawing.left_out.pop(address, None)
            self.drawing.folded[address] = (
                f"drawn as {said} and the wires it allows"
                if before == "drawn as the wires it allows"
                else f"drawn as {said}"
            )

    def drawn_as_wires(self, drew: Counter[str]) -> None:
        """A rule, or a group of rules, that drew wires is reported so, not left out."""
        for address in drew:
            if drew[address]:
                self.drawing.left_out.pop(address, None)
                self.drawing.folded[address] = "drawn as the wires it allows"

    def nsg_wires(self) -> None:
        """Azure network security groups: an inbound rule that allows is a
        wire from the internet (``Internet``, ``*``), from what a source range
        reaches or its source application security groups hold, to what the
        group guards (the cards in its subnets, on its network interfaces, and
        the scale sets that name it on theirs),
        narrowed to the destination range or groups it names."""
        estate = self.estate
        if not estate.of_type("azurerm_network_security_group", "azurerm_network_security_rule"):
            return
        reach = self.reach()
        guarded: dict[str, list[str]] = {}
        for association in estate.of_type("azurerm_subnet_network_security_group_association"):
            subnets = {subnet.address for subnet in estate.targets(association, "subnet_id")}
            cards = [card for card, place in reach.subnet.items() if place in subnets]
            for group in estate.targets(association, "network_security_group_id"):
                guarded.setdefault(group.address, []).extend(cards)
        for association in estate.of_type("azurerm_network_interface_security_group_association"):
            cards = self.cards_of(estate.targets(association, "network_interface_id"))
            for group in estate.targets(association, "network_security_group_id"):
                guarded.setdefault(group.address, []).extend(cards)
        members: dict[str, list[str]] = {}
        for association in estate.of_type(
            "azurerm_network_interface_application_security_group_association"
        ):
            cards = self.cards_of(estate.targets(association, "network_interface_id"))
            for group in estate.targets(association, "application_security_group_id"):
                members.setdefault(group.address, []).extend(cards)
        for scale_set in estate.of_type(*_SCALE_SETS):
            cards = self.cards_of([scale_set])
            for group in estate.targets(scale_set, "network_security_group_id"):
                guarded.setdefault(group.address, []).extend(cards)
            for group in estate.targets(scale_set, "application_security_group_ids"):
                members.setdefault(group.address, []).extend(cards)
        by_id = {
            value.lower(): found
            for found in estate.of_type("azurerm_application_security_group")
            if isinstance(value := found.values.get("id"), str)
        }

        def named(
            holder: Found, rule: dict[str, Any], blocks: list[dict[str, Any]], argument: str
        ) -> list[Found]:
            """What one rule's argument names: application security groups by
            id, or what a configuration names by reference."""
            ids = rule.get(argument)
            if isinstance(ids, list) and ids and all(isinstance(i, str) for i in ids):
                return [by_id[i.lower()] for i in ids if i.lower() in by_id]
            # a reference inside a group's inline rules is that rule's only
            # when one rule names any
            if rule is holder.values or (ids and sum(bool(b.get(argument)) for b in blocks) == 1):
                return estate.targets(holder, argument)
            return []

        rules: list[tuple[str, Found, dict[str, Any], list[dict[str, Any]]]] = []
        for group in estate.of_type("azurerm_network_security_group"):
            blocks = [b for b in group.values.get("security_rule") or [] if isinstance(b, dict)]
            rules += [(group.address, group, block, blocks) for block in blocks]
        for security_rule in estate.of_type("azurerm_network_security_rule"):
            for group in estate.targets(
                security_rule, "network_security_group_name", "network_security_group_id"
            ):
                rules.append((group.address, security_rule, security_rule.values, []))
        drew: Counter[str] = Counter()
        for guard, holder, rule, blocks in rules:
            if (_text(rule.get("direction")) or "").lower() != "inbound" or (
                _text(rule.get("access")) or ""
            ).lower() != "allow":
                continue
            ports = _texts(rule, "destination_port_range", "destination_port_ranges")
            labels = _allowed(rule.get("protocol"), None if "*" in ports else ports)
            targets = list(dict.fromkeys(guarded.get(guard, [])))
            destination_groups = named(
                holder, rule, blocks, "destination_application_security_group_ids"
            )
            if destination_groups:
                chosen = {card for g in destination_groups for card in members.get(g.address, [])}
                targets = [card for card in targets if card in chosen]
            destinations = [
                n
                for text in _texts(
                    rule, "destination_address_prefix", "destination_address_prefixes"
                )
                if text.lower() not in _ANYONE and (n := _network(text))
            ]
            if destinations:
                inside = {card for network in destinations for card in reach.within(network)}
                targets = [card for card in targets if card in inside]
            sources: list[str] = []
            for text in _texts(rule, "source_address_prefix", "source_address_prefixes"):
                network = _network(text)
                if text.lower() in _ANYONE:
                    sources.append("internet")
                elif network is not None and not reach.holds(network, targets):
                    sources += reach.within(network)
                elif network is not None and (subnets := reach.exactly(network)):
                    # a subnet's own range names that subnet, as a reference to it does
                    sources += [card for card, place in reach.subnet.items() if place in subnets]
            for source_group in named(
                holder, rule, blocks, "source_application_security_group_ids"
            ):
                sources += members.get(source_group.address, [])
            # a configuration names a subnet's range by reference
            for subnet in named(holder, rule, blocks, "source_address_prefixes") + named(
                holder, rule, blocks, "source_address_prefix"
            ):
                sources += [card for card, place in reach.subnet.items() if place == subnet.address]
            drew[holder.address] += self.wires_between(sources, targets, labels)
        self.drawn_as_wires(drew)

    def firewall_wires(self) -> None:
        """Google Cloud firewall rules: an ingress rule that allows is a wire
        from the internet (``0.0.0.0/0``), from what a source range reaches in
        its network (or the subnetwork whose range it names), or from the
        instances its source tags or service accounts name, to the instances
        its target tags or service accounts name (every instance in its
        network when it names none). A managed instance group wears its
        instance template's tags and accounts."""
        estate = self.estate
        if not estate.of_type("google_compute_firewall"):
            return
        reach = self.reach()

        def tags_of(found: Found) -> set[str]:
            tags = found.values.get("tags")
            if isinstance(tags, dict):  # the API's {"items": [...]}
                tags = tags.get("items")
            return {
                text for tag in (tags if isinstance(tags, list) else []) if (text := _text(tag))
            }

        def accounts(found: Found, argument: str) -> set[str]:
            # an email, or the service account a configuration names
            return set(_texts(found.values, argument)) | set(found.names(argument))

        def service_accounts(found: Found) -> set[str]:
            emails = {
                text
                for block in found.values.get("service_account") or []
                if isinstance(block, dict) and (text := _text(block.get("email")))
            }
            return emails | set(found.names("email"))

        # card -> the tags and service accounts it wears
        worn: dict[str, tuple[set[str], set[str]]] = {}
        for found in estate.of_type("google_compute_instance", *_INSTANCE_GROUPS):
            if not self.own_card(found):
                continue
            wearers = (
                [found]
                if found.type == "google_compute_instance"
                else estate.targets(found, "instance_template")
            )
            worn[found.address] = (
                set().union(*map(tags_of, wearers)),
                set().union(*map(service_accounts, wearers)),
            )

        def chosen(network: str | None, tags: list[str], emails: set[str]) -> list[str]:
            return [
                card
                for card, (wears, runs_as) in worn.items()
                if (network is None or network in self.ancestors(card))
                and (not tags or wears & set(tags))
                and (not emails or runs_as & emails)
            ]

        drew: Counter[str] = Counter()
        for rule in estate.of_type("google_compute_firewall"):
            values = rule.values
            if (_text(values.get("direction")) or "INGRESS").upper() != "INGRESS" or values.get(
                "disabled"
            ) is True:
                continue
            # no ports is every port; ports the reader cannot know, the protocol alone
            labels = [
                label
                for allow in values.get("allow") or []
                if isinstance(allow, dict)
                for label in _allowed(
                    allow.get("protocol"),
                    [] if allow.get("ports") is UNKNOWN else _texts(allow, "ports") or None,
                )
            ]
            networks = [
                t.address for t in estate.targets(rule, "network") if t.address in self.boxes
            ]
            network = networks[0] if networks else None
            targets = chosen(
                network, _texts(values, "target_tags"), accounts(rule, "target_service_accounts")
            )
            sources: list[str] = []
            for text in _texts(values, "source_ranges"):
                source_range = _network(text)
                if text.lower() in _ANYONE:
                    sources.append("internet")
                elif text in _GOOGLE_FRONT_ENDS:
                    # Google's front ends: the load balancers drawn in the network's project
                    sources += [
                        key
                        for key, card in self.cards.items()
                        if card.service_id == "cloud-load-balancing" and key not in sources
                    ]
                elif source_range is not None and not reach.holds(source_range, targets):
                    sources += [
                        card
                        for card in reach.within(source_range)
                        if network is None or network in self.ancestors(card)
                    ]
            # a configuration names a subnetwork's range by reference
            for subnet in estate.targets(rule, "source_ranges"):
                sources += [card for card, place in reach.subnet.items() if place == subnet.address]
            source_tags = _texts(values, "source_tags")
            if source_tags:
                sources += chosen(network, source_tags, set())
            source_accounts = accounts(rule, "source_service_accounts")
            if source_accounts:
                sources += chosen(network, [], source_accounts)
            drew[rule.address] += self.wires_between(sources, targets, labels)
        self.drawn_as_wires(drew)

    def load_balancer_wires(self) -> None:
        estate = self.estate
        members: dict[str, list[str]] = {}
        ports: dict[str, str] = {}
        for group in estate.of_type("aws_lb_target_group", "aws_alb_target_group"):
            ports[group.address] = _port_label(
                group.values.get("protocol"), group.values.get("port"), group.values.get("port")
            )
        for attachment in estate.of_type(
            "aws_lb_target_group_attachment", "aws_alb_target_group_attachment"
        ):
            for group in estate.targets(attachment, "target_group_arn"):
                for target in estate.targets(attachment, "target_id"):
                    key = self.drawn_key(target)
                    if key:
                        members.setdefault(group.address, []).append(key)
        for found in estate.resources:
            key = self.drawn_key(found)
            if key is None or not self.own_card(found):
                continue
            for group in estate.targets(found, "target_group_arns", "target_group_arn"):
                if group.type in (
                    "aws_lb_target_group",
                    "aws_alb_target_group",
                ) and found.type not in (
                    "aws_lb_listener",
                    "aws_alb_listener",
                    "aws_lb_listener_rule",
                ):
                    members.setdefault(group.address, []).append(key)
        for listener in estate.of_type("aws_lb_listener", "aws_alb_listener"):
            for balancer in estate.targets(listener, "load_balancer_arn"):
                start = self.drawn_key(balancer)
                for group in estate.targets(listener, "target_group_arn", "arn"):
                    label = ports.get(group.address) or _port_label(
                        listener.values.get("protocol"),
                        listener.values.get("port"),
                        listener.values.get("port"),
                    )
                    for member in members.get(group.address, []):
                        self.wire(start, member, label)

    def edge_wires(self) -> None:
        for found in self.estate.resources:
            role = self.roles[found.address]
            if role.kind != "edge" or role.edge is None:
                continue
            rule = role.edge
            label = _text(found.values.get(rule.label_from)) if rule.label_from else None
            label = (label or rule.label or "").strip()
            starts = [self.drawn_key(t) for t in self.estate.targets(found, rule.source)]
            ends = [
                self.drawn_key(t)
                for t in self.estate.targets(found, *(p.rsplit(".", 1)[-1] for p in rule.targets))
                if t not in self.estate.targets(found, rule.source)
            ]
            for start in starts:
                for end in ends:
                    self.wire(start, end, label)

    def reference_wires(self) -> None:
        for found in self.estate.resources:
            start = self.drawn_key(found)
            if (
                start is None
                or start in self.boxes
                or self.roles[found.address].kind not in ("component", "unmapped")
            ):
                continue
            for path, addresses in found.references.items():
                leaf = path.rsplit(".", 1)[-1]
                if leaf in _PLACEMENT or leaf in _NOT_WIRES or path.split(".", 1)[0] in _NOT_WIRES:
                    continue
                for address in addresses:
                    for target in self.estate.resolve(address):
                        end = self.drawn_key(target)
                        if (
                            end
                            and end not in self.boxes
                            and end != start
                            and (start, end) not in self.wires
                            and (end, start) not in self.wires
                        ):
                            self.wire(start, end, _humanize(path))

    # ------------------------------------------------------------ the tree
    def assemble(self) -> None:
        if any(wire.source == "internet" for wire in self.wires.values()):
            self.cards["internet"] = Card("internet", "infragram", "public-users", "Internet")
            self.parent["internet"] = ""
        items: dict[str, Box | Card] = {**self.boxes, **self.cards}
        for key, item in items.items():
            parent = self.parent.get(key, "")
            while parent and parent not in items:
                parent = self.parent.get(parent, "")
            if parent:
                box = items[parent]
                assert isinstance(box, Box)
                box.children.append(item)
            else:
                self.drawing.roots.append(item)

        # A frame nothing sits in is dropped when the import made it up (a
        # region, a zone), read it from a data source, or found it as the
        # cloud's own default (a default VPC); a frame the estate declares
        # stays, empty as it is.
        def keep(item: Box | Card) -> bool:
            if isinstance(item, Card):
                return True
            item.children = [child for child in item.children if keep(child)]
            source = item.source
            return bool(item.children) or (
                source is not None
                and source.mode == "managed"
                and source.values.get("is_default") is not True
            )

        self.drawing.roots = [item for item in self.drawing.roots if keep(item)]
        kept = {item.key for item in self.drawing.walk()}
        wires: list[Wire] = []
        for wire in self.wires.values():
            if wire.source not in kept or wire.target not in kept:
                continue
            if wire.source in self.boxes or wire.target in self.boxes:
                self.frame_relation(wire)
                continue
            back = self.wires.get((wire.target, wire.source))
            if back is not None and back.label == wire.label and back.dashed == wire.dashed:
                # both ways under one label is one wire with two heads
                if any(w.source == wire.target and w.target == wire.source for w in wires):
                    continue
                wire.both = True
            wires.append(wire)
        self.drawing.wires = wires

        def order(item: Box | Card) -> tuple[int, int, str, str]:
            # people first, so the layout sets them before what they reach;
            # a public subnet above the private ones, as a network is drawn
            if isinstance(item, Box):
                depth = _DEPTH.get(item.kind, 9) * 2 + (item.kind == "subnet-private")
                return (1, depth, item.caption.lower(), item.key)
            return (0 if item.library == "infragram" else 2, 0, item.caption.lower(), item.key)

        def sort(items: list[Box | Card]) -> list[Box | Card]:
            for item in items:
                if isinstance(item, Box):
                    item.children = sort(item.children)
            return sorted(items, key=order)

        self.drawing.roots = sort(self.drawing.roots)
        for item in self.drawing.walk():
            # zones -- or, with none, subnets -- side by side across the
            # network, tier by tier, so a wire between two of them crosses the
            # gap between them instead of climbing the network's edge
            if (
                isinstance(item, Box)
                and item.kind in ("vpc", "network")
                and (
                    sum(isinstance(c, Box) and c.kind == "zone" for c in item.children) > 1
                    or sum(
                        isinstance(c, Box) and c.kind.startswith("subnet") for c in item.children
                    )
                    > 1
                )
            ):
                item.flow = "row"
            elif isinstance(item, Box) and item.kind == "zone":
                item.flow = "column"
        self.shorten()

    def shorten(self) -> None:
        """Drop the prefix every resource's name shares (``acme-prod-``): the
        title and the popup keep the full names."""
        named = [
            item
            for item in self.drawing.walk()
            if (
                isinstance(item, Card)
                and item.sources
                and item.library != "infragram"
                and not item.key.startswith("collapse:")
            )
            or (isinstance(item, Box) and item.source is not None)
        ]
        captions = [item.caption for item in named]
        if len(captions) < 3:
            return
        # the longest prefix, cut at a separator, that three in four names share
        counts: Counter[str] = Counter()
        for caption in captions:
            for match in re.finditer(r"[-_]", caption):
                counts[caption[: match.end()]] += 1
        shared = [
            p
            for p, n in counts.items()
            if n >= 3
            and (
                (len(p) >= 8 and 2 * n >= len(captions))
                or (len(p) >= 4 and 4 * n >= 3 * len(captions))
            )
        ]
        if not shared:
            return
        prefix = max(shared, key=len)
        for item in named:
            if item.caption.startswith(prefix) and len(item.caption) > len(prefix):
                item.caption = item.caption[len(prefix) :]
        self.drawing.notes.append(
            f"The resources' names begin with {prefix!r}; the captions leave it out."
        )

    def run(self) -> Drawing:
        self.classify()
        self.frames()
        self.components()
        self.default_node_pools()
        self.parts()
        self.security_group_wires()
        self.nsg_wires()
        self.subnet_badges()
        self.firewall_wires()
        self.load_balancer_wires()
        self.edge_wires()
        self.reference_wires()
        self.assemble()
        self.quiet_notes()
        return self.drawing

    def quiet_notes(self) -> None:
        """A reader's note that a count is unknown says nothing of a resource
        the drawing leaves out anyway (a module's role assignments)."""
        left = {address for address in self.drawing.left_out}
        instances: dict[str, list[str]] = {}
        for found in self.estate.resources:
            instances.setdefault(found.base, []).append(found.address)
        kept = []
        for note in self.drawing.notes:
            subject, _, rest = note.partition(": ")
            if (
                rest.startswith(("its count is not known", "its for_each is not known"))
                and instances.get(subject)
                and all(address in left for address in instances[subject])
            ):
                continue
            kept.append(note)
        self.drawing.notes = kept


def draw(estate: Estate) -> Drawing:
    """The drawing of an estate: frames, components, wires, and the report."""
    from ..models.changes import plan_summary

    drawing = _Drawer(estate).run()
    drawing.plan = plan_summary(
        found.change for found in estate.resources if found.mode == "managed"
    )
    return drawing
