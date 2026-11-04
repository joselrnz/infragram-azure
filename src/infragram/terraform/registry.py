"""The modules style: the same walk, each part through the public registry's module where one fits.

The plain walk (:mod:`.emit`) already writes a component whose table names a
registry module as a call of that module (``module "postgresql" { source =
"terraform-aws-modules/rds/aws" ... }``), and what others read of it as the
module's outputs. What is left is what the tables cannot say alone:

- **A network** is its provider's network module -- the AWS VPC module, the
  Azure Verified Module for a virtual network, the Google network module --
  with its subnets as that module's inputs, and a subnet is what the module
  gives back: ``module.vpc.private_subnets``. An AWS tier drawn in no zone
  frame is two subnets, one a zone, as in the plain style.
- **An AWS security group** is the security group module, a call a component;
  the wires to it stay rules of their own, as the plain style writes them.
- **A Google firewall rule** from a wire is one of the network module's
  ``ingress_rules``.

Everything else -- where a thing sits, its variables, the wires, the load
balancers' target groups and listeners -- is the plain walk's.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ..models.topology import TopologyElement
from ..projects import CloudProject
from .emit import (
    ModuleResource,
    Place,
    Plan,
    Resource,
    _aws_description,
    _Emitter,
    _moved,
)
from .hcl import BLANK, Attr, Block, Comment, Raw, identifier
from .mapping import ComponentRule, ResourceSpec, load_modules
from .model import Record

__all__ = ["plan_registry"]

_NETWORK_MODULES = {"aws": "aws-vpc", "azure": "azure-virtual-network", "gcp": "gcp-network"}
_NETWORK_TYPES = {
    "aws": "aws_vpc",
    "azure": "azurerm_virtual_network",
    "gcp": "google_compute_network",
}
#: What is read of a network module, when its table does not say.
_NETWORK_PATHS = {
    "aws": {"id": "vpc_id", "arn": "vpc_arn", "cidr_block": "vpc_cidr_block"},
    "azure": {"id": "resource_id", "name": "name"},
    "gcp": {"id": "network_id", "self_link": "network_self_link", "name": "network_name"},
}
#: A side's list among the AWS VPC module's outputs, by what is read of a subnet.
_SIDE_OUTPUTS = {
    "id": "{side}_subnets",
    "arn": "{side}_subnet_arns",
    "cidr_block": "{side}_subnets_cidr_blocks",
}


class TierPart(ModuleResource):
    """A subnet the AWS VPC module writes: the ``start``-th of its side's list."""

    side: str = "private"
    start: int = 0


class _Network(Record):
    """A network frame written as its provider's registry module."""

    provider: str
    element: TopologyElement
    place: Place
    part: ModuleResource
    block: Block
    #: AWS, a tier a zone pair: {"side", "start", "cidrs", "element"}
    tiers: list[dict[str, Any]] = Field(default_factory=list)
    #: AWS subnets in zone frames: element id -> (side, index); the zone each index of ``azs`` is
    order: dict[str, tuple[str, int]] = Field(default_factory=dict)
    zones: list[str] | None = None
    explicit: list[dict[str, Any]] = Field(default_factory=list)
    #: Azure and Google Cloud: each subnet's entry
    subnets: list[dict[str, Any]] = Field(default_factory=list)
    nat_gateways: int = 0
    #: Google Cloud: the firewall rules the wires write
    rules: list[dict[str, object]] = Field(default_factory=list)


class _RegistryEmitter(_Emitter):
    def __init__(self, project: CloudProject) -> None:
        super().__init__(project, "modules")

    # ------------------------------------------------------------ networks
    def network_resources(
        self, place: Place, element: TopologyElement, provider: str, specs: list[ResourceSpec]
    ) -> Resource:
        key = _NETWORK_MODULES[provider]
        module = load_modules().modules[key]
        self.use_provider(provider)
        self.use_module(key)
        name = self.root.claim("module", self.noun(element), identifier(element.id))
        part = ModuleResource(
            _NETWORK_TYPES[provider],
            name,
            self.root,
            outputs=module.outputs,
            sensitive=list(module.sensitive),
            paths=_NETWORK_PATHS[provider],
        )
        block = Block("module", (name,), [])
        section = self.section(provider, "network")
        self.root.add(section, Comment(f"{element.name}{self.detail(element)}"), block)
        self.section_of[element.id] = section
        self.written[element.id] = {"main": part}
        record = _Network(provider=provider, element=element, place=place, part=part, block=block)
        if provider == "aws" and any(
            zone is not None for _s, zone in self.network_subnets(element)
        ):
            fitted = self.fit_subnets(element)
            if fitted is None:
                self.notes.append(
                    f"{element.name}: the VPC module puts each kind's subnets across the zones "
                    "in turn, and this network's cannot be so placed, so its zones are the "
                    "module's: check each subnet's zone"
                )
                for side in ("public", "private"):
                    of_side = [
                        s for s, _z in self.network_subnets(element) if s.type == f"subnet-{side}"
                    ]
                    record.order.update({s.id: (side, i) for i, s in enumerate(of_side)})
            else:
                record.order, record.zones = fitted
        self.module_networks[element.id] = record
        return part

    def fit_subnets(
        self, network: TopologyElement
    ) -> tuple[dict[str, tuple[str, int]], list[str] | None] | None:
        """Each subnet's place in the VPC module's lists, and the zone each
        index of ``azs`` is: the module puts ``public_subnets[i]`` and
        ``private_subnets[i]`` in ``azs[i]``, so a subnet of each kind at an
        index they share sits in one zone. ``None`` when the frames cannot be
        so placed; the zones are the data source's when a subnet sits in no
        zone frame."""
        subnets = self.network_subnets(network)
        sides = {
            side: [(s, z) for s, z in subnets if s.type == f"subnet-{side}"]
            for side in ("public", "private")
        }
        order: dict[str, tuple[str, int]] = {}
        if not subnets or any(zone is None for _s, zone in subnets):
            for side, pairs in sides.items():
                order.update({s.id: (side, i) for i, (s, _z) in enumerate(pairs)})
            return order, None
        zones = list(dict.fromkeys(zone.id for _s, zone in subnets if zone is not None))
        periodic = self.fit_periodic(sides, zones)
        if periodic is not None:
            return periodic
        # the frames hold a side's subnets unevenly across the zones: the
        # only placement left names a zone again in ``azs``
        left = {
            side: {zone: [s for s, z in pairs if z is not None and z.id == zone] for zone in zones}
            for side, pairs in sides.items()
        }
        short, long = sorted(
            ("public", "private"), key=lambda side: (len(sides[side]), side == "private")
        )
        sequence: list[str] = []
        cursor = 0

        def take(side: str, zone: str) -> None:
            order[left[side][zone].pop(0).id] = (
                side,
                sum(1 for v in order.values() if v[0] == side),
            )

        while any(left[short].values()):
            for step in range(len(zones)):
                zone = zones[(cursor + step) % len(zones)]
                if left[short][zone] and left[long][zone]:
                    break
            else:
                return None
            take(short, zone)
            take(long, zone)
            sequence.append(zone)
            cursor = zones.index(zone) + 1
        while any(left[long].values()):
            for step in range(len(zones)):
                zone = zones[(cursor + step) % len(zones)]
                if left[long][zone]:
                    break
            take(long, zone)
            sequence.append(zone)
            cursor = zones.index(zone) + 1
        return order, sequence

    @staticmethod
    def fit_periodic(
        sides: dict[str, list[tuple[TopologyElement, TopologyElement | None]]], zones: list[str]
    ) -> tuple[dict[str, tuple[str, int]], list[str]] | None:
        """The placement that names each zone once in ``azs``: the VPC module
        reads a side's ``i``-th subnet's zone as ``element(azs, i)``, which
        wraps, so a side of ``k`` subnets over ``n`` zones puts ``k // n`` in
        each zone and one more in the first ``k % n``. One order of the zones
        must fit both sides; ``None`` when the frames hold them otherwise."""
        count = {
            side: {
                zone: sum(1 for _s, z in pairs if z is not None and z.id == zone) for zone in zones
            }
            for side, pairs in sides.items()
        }
        # the zones with one more of a side come first, of both sides when one
        # such set holds the other; ties keep the drawing's order
        ranked = sorted(
            zones,
            key=lambda zone: (-count["public"][zone], -count["private"][zone], zones.index(zone)),
        )
        n = len(ranked)
        for side, pairs in sides.items():
            q, r = divmod(len(pairs), n)
            if [count[side][zone] for zone in ranked] != [q + (j < r) for j in range(n)]:
                return None
        order: dict[str, tuple[str, int]] = {}
        for side, pairs in sides.items():
            queue = {
                zone: [s for s, z in pairs if z is not None and z.id == zone] for zone in ranked
            }
            for i in range(len(pairs)):
                order[queue[ranked[i % n]].pop(0).id] = (side, i)
        return order, ranked

    def subnet_frame(
        self, element: TopologyElement, place: Place, provider: str, specs: list[ResourceSpec]
    ) -> Place:
        record = (
            self.module_networks.get(place.network_element.id)
            if place.network_element is not None
            else None
        )
        if record is None:
            return super().subnet_frame(element, place, provider, specs)
        assert isinstance(record, _Network) and place.network_element is not None
        vpc = record.part.name
        side = "public" if element.type == "subnet-public" else "private"
        if provider == "aws" and element.id not in record.order:
            # a tier: two subnets, one a zone, at the end of its side's list
            start = sum(2 for tier in record.tiers if tier["side"] == side)
            record.tiers.append(
                {
                    "side": side,
                    "start": start,
                    "element": element,
                    "cidrs": self.tier_cidrs(place.network_element, element),
                }
            )
            subnet: Resource = TierPart(
                "aws_subnet",
                vpc,
                self.root,
                side=side,
                start=start,
                paths={
                    attr: f"{out.format(side=side)}[{start}]" for attr, out in _SIDE_OUTPUTS.items()
                },
            )
        elif provider == "aws":
            side, index = record.order[element.id]
            record.explicit.append(
                {
                    "side": side,
                    "index": index,
                    "zone": place.zone,
                    "zone_id": self.zone_of(element),
                    "cidr": self.cidr_input(self.root, element),
                }
            )
            subnet = TierPart(
                "aws_subnet",
                vpc,
                self.root,
                side=side,
                start=index,
                paths={
                    attr: f"{out.format(side=side)}[{index}]" for attr, out in _SIDE_OUTPUTS.items()
                },
            )
        elif provider == "azure":
            key = self.noun(element)
            cidr = self.cidr_input(self.root, element)
            record.subnets.append(
                {
                    "key": key,
                    "name": self.placeholder("caption_id", place, element, {}, "azure"),
                    "cidr": cidr,
                }
            )
            subnet = ModuleResource(
                "azurerm_subnet",
                vpc,
                self.root,
                paths={"id": f'subnets["{key}"].resource_id', "name": f'subnets["{key}"].name'},
                values={"address_prefixes": [cidr]},
            )
        else:
            key = self.noun(element)
            region = self.region_of(place, "gcp")
            region_text = f"${{{region.text}}}" if isinstance(region, Raw) else str(region)
            names = self.locals.setdefault(f"{self.noun(record.element)}_subnet_names", {})
            assert isinstance(names, dict)
            names[key] = self.name_expr(place, element, "lower63")
            cidr = self.cidr_input(self.root, element)
            record.subnets.append(
                {
                    "key": key,
                    "cidr": cidr,
                    "region": region,
                    "local": f"local.{self.noun(record.element)}_subnet_names.{key}",
                }
            )
            step = f'subnets["{region_text}/${{local.{self.noun(record.element)}_subnet_names.{key}}}"]'
            subnet = ModuleResource(
                "google_compute_subnetwork",
                vpc,
                self.root,
                paths={
                    "id": f"{step}.id",
                    "self_link": f"{step}.self_link",
                    "name": f"{step}.name",
                },
                values={"ip_cidr_range": cidr},
            )
        self.subnets[place.network_element.id].append((subnet, element.type, place.zone))
        many = provider == "aws" and element.id not in record.order
        name = self.frame_name(element, "id", many=many)
        self.root.outputs[name] = self.output_of(name, subnet, element, many)
        self.written[element.id] = {"main": subnet}
        self.section_of[element.id] = self.section(provider, "network")
        return _moved(place, subnet=subnet, subnet_kind=element.type)

    def output_of(self, name: str, subnet: Resource, element: TopologyElement, many: bool) -> Any:
        from .emit import Output

        if many and isinstance(subnet, TierPart):
            value = Raw(
                f"slice(module.{subnet.name}.{subnet.side}_subnets, {subnet.start}, {subnet.start + 2})"
            )
            return Output(name, value, f"The ids of {element.name}, one a zone.")
        return Output(name, subnet.ref("id"), f"The id of {element.name}.")

    def zone_of(self, subnet: TopologyElement) -> str | None:
        parent = self.parent.get(subnet.id)
        while parent is not None and parent.type != "zone":
            parent = self.parent.get(parent.id)
        return parent.id if parent is not None else None

    def placeholder(
        self,
        token: str,
        place: Place,
        element: TopologyElement,
        written: dict[str, Resource],
        provider: str,
    ) -> object:
        head = token.partition(":")[0]
        base, _, attribute = head.partition(".")
        record = (
            self.module_networks.get(place.network_element.id)
            if place.network_element is not None
            else None
        )
        if base == "subnets" and isinstance(record, _Network) and provider == "aws":
            subnets = [s for s in self.sibling_subnets(place) if isinstance(s, TierPart)]
            attr = attribute or "id"
            out = _SIDE_OUTPUTS.get(attr, "{side}_subnets")
            if subnets and not record.explicit:
                side = subnets[0].side
                tiers = [t for t in record.tiers if t["side"] == side]
                if len(subnets) == len(tiers):
                    return Raw(f"module.{record.part.name}.{out.format(side=side)}")
                parts = [
                    f"slice(module.{record.part.name}.{out.format(side=side)}, {s.start}, {s.start + 2})"
                    for s in subnets
                ]
                return Raw(parts[0] if len(parts) == 1 else f"concat({', '.join(parts)})")
        return super().placeholder(token, place, element, written, provider)

    def module_gateway(
        self, record: Any, element: TopologyElement, place: Place, rule: ComponentRule
    ) -> None:
        """An internet or NAT gateway the VPC module writes itself."""
        if rule.plumbing == "nat_gateway":
            path = f"natgw_ids[{record.nat_gateways}]"
            record.nat_gateways += 1
            self.notes.append(
                f"{element.name}: written by the VPC module of {record.element.name} "
                "(enable_nat_gateway)"
            )
        else:
            path = "igw_id"
            self.notes.append(f"{element.name}: written by the VPC module of {record.element.name}")
        part = record.part
        self.written[element.id] = {
            "main": ModuleResource(f"aws_{rule.plumbing}", part.name, self.root, paths={"id": path})
        }
        self.placed[element.id] = (place, rule)

    def finish_module_networks(self) -> None:
        for record in self.module_networks.values():
            assert isinstance(record, _Network)
            module = load_modules().modules[_NETWORK_MODULES[record.provider]]
            place, element = record.place, record.element
            body: list[object] = [Attr("source", module.source), Attr("version", module.version)]
            provider_name = self.mapping(record.provider).terraform.name
            if place.alias:
                body.append(
                    Attr("providers", {provider_name: Raw(f"{provider_name}.{place.alias}")})
                )
            body.append(BLANK)
            if record.provider == "aws":
                body += self.vpc_arguments(record)
            elif record.provider == "azure":
                body += [
                    Attr("name", self.placeholder("caption_id", place, element, {}, "azure")),
                    Attr("location", self.location_of(place)),
                    Attr("parent_id", place.resource_group_id),
                    Attr("address_space", [self.cidr_input(self.root, element)]),
                ]
                if record.subnets:
                    body.append(
                        Attr(
                            "subnets",
                            {
                                s["key"]: {"name": s["name"], "address_prefixes": [s["cidr"]]}
                                for s in record.subnets
                            },
                        )
                    )
                body += [Attr("enable_telemetry", False), BLANK, Attr("tags", Raw("local.tags"))]
            else:
                body += [
                    Attr("project_id", self.project_of(place)),
                    Attr("network_name", self.name_expr(place, element, "lower63")),
                    Attr("routing_mode", "GLOBAL"),
                ]
                if record.subnets:
                    body.append(
                        Attr(
                            "subnets",
                            [
                                {
                                    "subnet_name": Raw(s["local"]),
                                    "subnet_ip": s["cidr"],
                                    "subnet_region": s["region"],
                                }
                                for s in record.subnets
                            ],
                        )
                    )
                if record.rules:
                    body.append(Attr("ingress_rules", record.rules))
            record.block.body[:] = body

    def vpc_arguments(self, record: _Network) -> list[object]:
        place, element = record.place, record.element
        body: list[object] = [
            Attr("name", self.name_expr(place, element)),
            Attr("cidr", self.cidr_input(self.root, element)),
        ]
        sides: dict[str, object] = {}
        #: how many subnets each side's list holds, and how many zones ``azs`` names
        lengths: dict[str, int] = {}
        # the module reads a subnet's zone as element(azs, i), which wraps: the
        # two zones local.azs holds serve a side of any length, and a slice of
        # it never asks for more zones than it holds
        zone_count = 2
        if record.explicit:
            by_side = {
                side: sorted(
                    (s for s in record.explicit if s["side"] == side), key=lambda s: s["index"]
                )
                for side in ("public", "private")
            }
            if record.zones is not None and all(s.get("zone") is not None for s in record.explicit):
                zone_of = {s["zone_id"]: s["zone"] for s in record.explicit}
                azs: object = [zone_of[zone] for zone in record.zones]
                zone_count = len(record.zones)
            else:
                azs = self.zones_local(place.alias)
            sides = {
                side: [s["cidr"] for s in subnets] for side, subnets in by_side.items() if subnets
            }
            lengths = {side: len(subnets) for side, subnets in by_side.items()}
        else:
            azs = self.zones_local(place.alias)
            for side in ("public", "private"):
                tiers = [t["cidrs"] for t in record.tiers if t["side"] == side]
                lengths[side] = 2 * len(tiers)
                if tiers:
                    sides[side] = (
                        tiers[0]
                        if len(tiers) == 1
                        else Raw(f"concat({', '.join(t.text for t in tiers)})")
                    )
        body.append(Attr("azs", azs))
        for side in ("public", "private"):
            if side in sides:
                body.append(Attr(f"{side}_subnets", sides[side]))
        if record.nat_gateways and "public" in sides:
            # one NAT gateway a zone is length(azs) of them, and the module
            # writes no public subnet at all when fewer than length(azs)
            per_zone = (
                record.nat_gateways > 1
                and lengths.get("public", 0) >= zone_count >= record.nat_gateways
            )
            body += [
                BLANK,
                Attr("enable_nat_gateway", True),
                Attr("single_nat_gateway", record.nat_gateways == 1),
                Attr("one_nat_gateway_per_az", per_zone),
            ]
        elif record.nat_gateways:
            self.notes.append(
                f"{element.name}: its NAT gateway needs a public subnet the diagram "
                "does not draw, so the VPC module writes none"
            )
        return body

    # ------------------------------------------------------------ AWS security groups
    def security_group(self, place: Place, element: TopologyElement) -> None:
        assert place.network is not None
        key = "aws-security-group"
        module = load_modules().modules[key]
        self.use_module(key)
        name = self.root.claim("module", f"{self.noun(element)}_sg")
        group = ModuleResource(
            "aws_security_group",
            name,
            self.root,
            outputs=module.outputs,
            sensitive=list(module.sensitive),
        )
        section = self.section("aws", "security")
        before = len(self.root.files.get(section, []))
        self.root.add(
            section,
            Comment(
                f"{element.name}: its own security group; the wires to it are its ingress rules."
            ),
            Block(
                "module",
                (name,),
                [
                    Attr("source", module.source),
                    Attr("version", module.version),
                    *(
                        [Attr("providers", {"aws": Raw(f"aws.{place.alias}")})]
                        if place.alias
                        else []
                    ),
                    BLANK,
                    Attr("name", self.name_expr(place, element)),
                    Attr("description", _aws_description(f"{element.name}{self.detail(element)}")),
                    Attr("vpc_id", place.network.ref("id")),
                    # the wires' rules are resources beside the group: the
                    # module must not revert them as rules made out of band
                    Attr("enable_exclusive_rules", False),
                    BLANK,
                    Attr(
                        "egress_rules",
                        {
                            "all": {
                                "description": "All outbound traffic",
                                "ip_protocol": "-1",
                                "cidr_ipv4": "0.0.0.0/0",
                            }
                        },
                    ),
                ],
            ),
        )
        self.security_group_of[element.id] = group
        self.group_network[group.address] = (
            place.network_element.id if place.network_element else None
        )
        self.security_items[element.id] = self.root.files[section][before:]

    def unwrite_security_group(self, place: Place, element: TopologyElement) -> None:
        added = {id(item) for item in self.security_items.pop(element.id, [])}
        section = self.section("aws", "security")
        self.root.files[section] = [
            item for item in self.root.files[section] if id(item) not in added
        ]
        self.root.release("module", f"{self.noun(element)}_sg")

    def egress_rule(self, unit: Any, group: Resource) -> None:
        if isinstance(group, ModuleResource):
            return  # the security group module writes its way out itself
        super().egress_rule(unit, group)


def plan_registry(project: CloudProject) -> Plan:
    """The modules style's plan for a document."""
    return _RegistryEmitter(project).run()
