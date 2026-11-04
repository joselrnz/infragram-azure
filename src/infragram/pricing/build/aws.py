"""The AWS price table, from AWS's public price list.

Every rate is read from AWS's own public sources; none needs signing in:

- the AWS Price List bulk API (``pricing.us-east-1.amazonaws.com``): an
  index of offers, each offer's index of regions, and one file per offer and
  region with its products (a usage type, its attributes) and their
  on-demand terms (a rate per unit, in tiers);
- for what lives in the EC2 offer, whose region files are near half a
  gigabyte each, the price files the aws.amazon.com pricing pages read
  (``b0.p.awsstatic.com``): EC2 instance hours per region and operating
  system, EBS volumes, NAT gateways.

Only on-demand rates in US dollars of AWS's standard commercial regions are
kept (no GovCloud, China, sovereign cloud, Local Zone, Wavelength or
Outposts). A tier priced at nothing from zero is the account's free tier,
shared by everything in it, and is left out: an element is priced as if the
free tier were spent. A usage type's region prefix (``USE2-``, ``EU-``) is
removed, so one rule finds a product in every region.
"""

from __future__ import annotations

import datetime
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from .. import PricingError
from . import download_json, write_table

__all__ = ["CALCULATOR", "GLOBAL", "PRICE_LIST", "build", "regions"]

PRICE_LIST = "https://pricing.us-east-1.amazonaws.com"
CALCULATOR = "https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps"
LOCATIONS = "https://b0.p.awsstatic.com/locations/1.0/aws/current/locations.json"
SOURCE = "AWS Price List API (pricing.us-east-1.amazonaws.com)"
PAGES = "AWS pricing pages' price files (b0.p.awsstatic.com)"
#: The region key of what AWS prices once for the world (Route 53 zones,
#: CloudFront, Global Accelerator); the offer files call it ``aws-other``.
GLOBAL = "global"
#: A standard commercial region code: us-east-1, ap-southeast-7; never a
#: Local Zone (us-east-1-bos-1) or Wavelength zone.
_STANDARD = re.compile(r"^[a-z]{2}-[a-z]+-\d$")
_EXCLUDED = ("us-gov-", "cn-", "eusc-")
#: A usage type's leading region token: USE1, EUW1, APS9.
_REGION_TOKEN = re.compile(r"^([A-Z]{2,4}\d)-")
#: The operating systems whose EC2 rates are kept, by the price files' name.
EC2_SYSTEMS = ("Linux", "Windows", "RHEL", "SUSE")


class Product(BaseModel):
    """One product of an offer's region file, with its on-demand rate."""

    family: str
    #: The usage type without its region prefix.
    usage: str
    attributes: dict[str, str]
    unit: str
    #: (from, rate): the on-demand rate from each tier's start, in order.
    tiers: list[tuple[float, float]]


class Read(BaseModel):
    """An offer's region file, reduced."""

    products: list[Product]
    published: str


class Rule(BaseModel):
    """Which product an item of a table service is."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    item: str
    #: Matched in full against the usage type without its region prefix.
    usage: str
    family: str | None = None
    where: dict[str, str] = Field(default_factory=dict)

    def matches(self, product: Product) -> bool:
        if self.family is not None and product.family != self.family:
            return False
        if not re.fullmatch(self.usage, product.usage):
            return False
        # an empty value asks for the attribute's absence
        return all(product.attributes.get(key, "") == value for key, value in self.where.items())


def _rule(item: str, usage: str, family: str | None = None, **where: str) -> Rule:
    return Rule(item=item, usage=usage, family=family, where=where)


# -- reading the sources ------------------------------------------------------


class _Sources:
    """The offers read so far, and what every region is called."""

    def __init__(self, fresh: bool) -> None:
        self.fresh = fresh
        self.indexes: dict[str, dict[str, Any]] = {}
        self.prefixes: dict[str, tuple[str, ...]] = {}
        self.warnings: list[str] = []
        locations = download_json(LOCATIONS, fresh=fresh)
        #: region code -> the names AWS's price files give it.
        self.names: dict[str, list[str]] = {}
        for name, entry in locations.items():
            if isinstance(entry, dict) and entry.get("type") == "AWS Region":
                code = str(entry.get("code") or "")
                names = [name, str(entry.get("label") or name)]
                self.names[code] = list(dict.fromkeys(names))
        self.regions = regions(self.names)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def index(self, offer: str) -> dict[str, Any]:
        if offer not in self.indexes:
            url = f"{PRICE_LIST}/offers/v1.0/aws/{offer}/current/region_index.json"
            self.indexes[offer] = download_json(url, fresh=self.fresh).get("regions", {})
        return self.indexes[offer]

    def prefix(self, region: str) -> tuple[str, ...]:
        """The prefixes a usage type carries in *region*: ``USE2``, ``EU``,
        and the region code itself (KMS writes ``us-east-2-KMS-Keys``)."""
        if region not in self.prefixes:
            found = {region}
            if region != GLOBAL:
                for offer in ("AmazonVPC", "AWSDataTransfer"):
                    raw = self._raw(offer, region)
                    for product in (raw or {}).get("products", {}).values():
                        attributes = product.get("attributes", {})
                        usage = str(attributes.get("usagetype", ""))
                        for marker in ("-PublicIPv4:InUseAddress", "-DataTransfer-Out-Bytes"):
                            if usage.endswith(marker) and (
                                attributes.get("fromRegionCode", region) == region
                            ):
                                found.add(usage[: -len(marker)])
            self.prefixes[region] = tuple(sorted(found, key=len, reverse=True))
        return self.prefixes[region]

    def _file_prefixes(self, raw: dict[str, Any], region: str) -> tuple[str, ...]:
        """The region's prefixes, and any other region token the file writes
        that is no other region's: eu-west-1 is ``EU`` in most files and
        ``EUW1`` in a few, sometimes both in one file."""
        found = set(self.prefix(region))
        if region != GLOBAL:
            foreign = self.foreign(region)
            for product in raw.get("products", {}).values():
                usage = str(product.get("attributes", {}).get("usagetype", ""))
                match = _REGION_TOKEN.match(usage)
                if match and match.group(1) not in foreign:
                    found.add(match.group(1))
        return tuple(sorted(found, key=len, reverse=True))

    def foreign(self, region: str) -> set[str]:
        """Every other standard region's prefixes."""
        return {
            prefix
            for other in self.regions
            if other != region
            for prefix in self.prefix(other)
            if prefix != other
        }

    def _raw(self, offer: str, region: str) -> dict[str, Any] | None:
        key = "aws-other" if region == GLOBAL else region
        entry = self.index(offer).get(key)
        if not entry:
            return None
        return download_json(PRICE_LIST + entry["currentVersionUrl"], fresh=self.fresh)

    def read(self, offer: str, region: str) -> Read | None:
        """*offer*'s products in *region* with an on-demand rate, else None."""
        raw = self._raw(offer, region)
        if raw is None:
            return None
        prefixes = self._file_prefixes(raw, region)
        terms = raw.get("terms", {}).get("OnDemand", {})
        products = []
        for sku, product in raw.get("products", {}).items():
            dimensions = [
                dimension
                for term in terms.get(sku, {}).values()
                for dimension in term.get("priceDimensions", {}).values()
            ]
            tiers = _tiers(dimensions)
            if tiers is None:
                continue
            attributes = {str(k): str(v) for k, v in product.get("attributes", {}).items()}
            products.append(
                Product.model_construct(
                    family=str(product.get("productFamily") or ""),
                    usage=_unprefixed(attributes.get("usagetype", ""), prefixes),
                    attributes=attributes,
                    unit=str(dimensions[0].get("unit", "")),
                    tiers=tiers,
                )
            )
        return Read(products=products, published=str(raw.get("publicationDate", ""))[:10])

    def calculator(self, path: str) -> dict[str, Any] | None:
        """A pricing page's price file, else None where AWS publishes none."""
        try:
            data = download_json(f"{CALCULATOR}/{path}", fresh=self.fresh)
        except PricingError:
            return None
        return data if isinstance(data, dict) else None

    def located(self, data: dict[str, Any], region: str) -> dict[str, Any]:
        """A pricing page file's rows for *region*, found under any of its names."""
        for name in self.names.get(region, []):
            rows = data.get("regions", {}).get(name)
            if isinstance(rows, dict):
                return rows
        return {}


def regions(names: dict[str, list[str]]) -> list[str]:
    """The standard commercial regions among AWS's locations."""
    return sorted(
        code for code in names if _STANDARD.match(code) and not code.startswith(_EXCLUDED)
    )


def _unprefixed(usage: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if usage.startswith(prefix + "-"):
            return usage[len(prefix) + 1 :]
    return usage


def _tiers(dimensions: list[dict[str, Any]]) -> list[tuple[float, float]] | None:
    """The on-demand tiers, without the free tier; None without a USD rate."""
    tiers = []
    for dimension in dimensions:
        price = dimension.get("pricePerUnit", {}).get("USD")
        if price is None:
            continue
        begin = float(dimension.get("beginRange") or 0)
        tiers.append((begin, float(price)))
    if not tiers:
        return None
    tiers.sort()
    if len(tiers) > 1 and tiers[0][0] == 0 and tiers[0][1] == 0:
        # the free tier: what follows it is the rate from the first unit
        tiers = [(0.0, tiers[1][1]), *tiers[2:]]
    return tiers


def _key(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(value)


def _tier_map(tiers: list[tuple[float, float]]) -> dict[str, float]:
    return {_key(begin): rate for begin, rate in tiers}


# -- collecting a service -----------------------------------------------------


def _service(
    title: str,
    keys: list[str],
    rates: dict[str, Any],
    published: str,
    *,
    unit: str,
    source: str = SOURCE,
    info: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "source": source,
        "published": published,
        "unit": unit,
        "keys": keys,
        "rates": rates,
        "info": info or {},
    }


def _metered(
    sources: _Sources,
    offer: str,
    rules: list[Rule],
    *,
    where: Iterable[str] | None = None,
) -> tuple[dict[str, Any], str]:
    """region -> item -> tier start -> rate, for each rule's product."""
    rates: dict[str, Any] = {}
    published = ""
    matched: set[str] = set()
    for region in where if where is not None else sources.regions:
        read = sources.read(offer, region)
        if read is None:
            continue
        published = max(published, read.published)
        items: dict[str, dict[str, float]] = {}
        for rule in rules:
            found = [product for product in read.products if rule.matches(product)]
            if not found:
                continue
            kinds = Counter(tuple(product.tiers) for product in found)
            tiers = list(kinds.most_common(1)[0][0])
            if len(kinds) > 1:
                sources.warn(
                    f"{offer} {region} {rule.item}: {len(kinds)} different rates; kept the "
                    f"most common, {tiers[:2]}, of {[list(k)[:2] for k in kinds][:3]}"
                )
            items[rule.item] = _tier_map(tiers)
            matched.add(rule.item)
        if items:
            rates[region] = items
    for rule in rules:
        if rule.item not in matched:
            sources.warn(f"{offer}: no product is {rule.item} ({rule.usage})")
    return rates, published


def _keyed(
    sources: _Sources,
    offer: str,
    key_of: Callable[[Product], tuple[str, ...] | None],
    *,
    describe: Callable[[Product], tuple[str, str] | None] | None = None,
) -> tuple[dict[str, Any], str, dict[str, str]]:
    """region -> each key of *key_of* -> the first tier's rate."""
    rates: dict[str, Any] = {}
    info: dict[str, str] = {}
    published = ""
    for region in sources.regions:
        read = sources.read(offer, region)
        if read is None:
            continue
        published = max(published, read.published)
        seen: dict[tuple[str, ...], float] = {}
        clashes = 0
        for product in read.products:
            key = key_of(product)
            if key is None or not product.tiers:
                continue
            rate = product.tiers[0][1]
            if key in seen and seen[key] != rate:
                clashes += 1
                rate = max(rate, seen[key])
            seen[key] = rate
            if describe is not None and (words := describe(product)):
                info.setdefault(words[0], words[1])
        if clashes:
            sources.warn(f"{offer} {region}: {clashes} keys with two rates; kept the higher")
        node: dict[str, Any] = {}
        for key, rate in seen.items():
            if rate <= 0:
                continue
            branch = node
            for part in key[:-1]:
                branch = branch.setdefault(part, {})
            branch[key[-1]] = rate
        if node:
            rates[region] = node
    return rates, published, info


def _shape(product: Product, *, vcpu: str = "vcpu", memory: str = "memory") -> str:
    cores = product.attributes.get(vcpu, "")
    size = product.attributes.get(memory, "")
    if size and not size.endswith(("GiB", "GB")):
        size = f"{size} GiB"
    return ", ".join(part for part in (f"{cores} vCPU" if cores else "", size) if part)


# -- EC2, EBS and NAT gateways: the pricing pages' files ----------------------


def _ec2(sources: _Sources) -> dict[str, Any]:
    rates: dict[str, Any] = {}
    info: dict[str, str] = {}
    published = ""
    for region in sources.regions:
        names = sources.names.get(region, [])
        for system in EC2_SYSTEMS:
            data = None
            for name in names:
                data = sources.calculator(
                    f"ec2/USD/current/ec2-ondemand-without-sec-sel/"
                    f"{quote(name, safe='')}/{quote(system, safe='')}/index.json"
                )
                if data is not None:
                    break
            if data is None:
                continue
            published = max(
                published, str(data.get("manifest", {}).get("hawkFilePublicationDate", ""))[:10]
            )
            kept: dict[str, float] = {}
            for row in sources.located(data, region).values():
                if not isinstance(row, dict):
                    continue
                kind = str(row.get("Instance Type", ""))
                try:
                    price = float(row.get("price", ""))
                except ValueError:
                    continue
                if not kind or price <= 0:
                    continue
                if kind in kept and kept[kind] != price:
                    sources.warn(f"EC2 {region} {system} {kind}: two rates")
                kept[kind] = price
                if row.get("vCPU"):
                    info.setdefault(
                        kind, f"{row['vCPU']} vCPU, {row.get('Memory', '')}".strip(", ")
                    )
            if kept:
                rates.setdefault(region, {})[system] = kept
    return _service(
        "EC2 on-demand",
        ["region", "os", "instance_type"],
        rates,
        published,
        unit="hour",
        source=PAGES,
        info={"instance_type": info},
    )


#: The EBS pricing page's rate names -> the table's items.
_EBS = {
    "Storage General Purpose gp3 GB Mo": "gp3",
    "Storage General Purpose gp2 GB Mo": "gp2",
    "Storage Provisioned IOPS io1 GB Mo": "io1",
    "Storage Provisioned IOPS io2 GB month": "io2",
    "Storage Throughput Optimized HDD st1 GB Mo": "st1",
    "Storage Cold HDD sc1 GB Mo": "sc1",
    "Storage Magnetic standard GB Mo": "standard",
    "Provisioned EBS I O Requests standard Volumes per IOs": "standard-io",
    "Provisioned EBS IOPS gp3 Volumes per IOPS Mo": "gp3-iops",
    "Provisioned Throughput gp3 per GiBps mo": "gp3-throughput",
    "Provisioned EBS IOPS io1 Volumes per IOPS Mo": "io1-iops",
    "Storage Snapshot Amazon S3 GB Mo": "snapshot",
    "Storage Snapshot Amazon S3 SnapshotArchiveStorage GB Mo": "snapshot-archive",
}
#: io2 IOPS are priced in three tiers: to 32,000, to 64,000, beyond.
_IO2_TIERS = {
    "Provisioned EBS IOPS io2 Volumes per IOPS Mo": "0",
    "Provisioned EBS IOPS Tier 2 io2 Volumes per IOPS Mo": "32000",
    "Provisioned EBS IOPS Tier 3 io2 Volumes per IOPS Mo": "64000",
}


def _pages_metered(
    sources: _Sources, path: str, names: dict[str, str], tiers: dict[str, tuple[str, str]]
) -> tuple[dict[str, Any], str]:
    data = sources.calculator(path)
    if data is None:
        raise PricingError(f"AWS publishes no {path}")
    published = str(data.get("manifest", {}).get("hawkFilePublicationDate", ""))[:10]
    rates: dict[str, Any] = {}
    for region in sources.regions:
        rows = sources.located(data, region)
        items: dict[str, dict[str, float]] = {}
        for name, row in rows.items():
            if not isinstance(row, dict) or "price" not in row:
                continue
            if name in names:
                items[names[name]] = {"0": float(row["price"])}
            elif name in tiers:
                item, start = tiers[name]
                items.setdefault(item, {})[start] = float(row["price"])
        if items:
            rates[region] = items
    return rates, published


def _ebs(sources: _Sources) -> dict[str, Any]:
    rates, published = _pages_metered(
        sources,
        "ec2/USD/current/ebs.json",
        _EBS,
        {name: ("io2-iops", start) for name, start in _IO2_TIERS.items()},
    )
    return _service(
        "EBS volumes",
        ["region", "item", "from"],
        rates,
        published,
        unit="per item's unit",
        source=PAGES,
    )


def _nat(sources: _Sources) -> dict[str, Any]:
    rates, published = _pages_metered(
        sources,
        "ec2/USD/current/natgateway.json",
        {
            "Hourly charge for NAT Gateways": "hour",
            "Charge for per GB data processed by NatGateways": "gb",
        },
        {},
    )
    return _service(
        "NAT gateway", ["region", "item", "from"], rates, published, unit="hour or GB", source=PAGES
    )


# -- the Price List API: metered services --------------------------------------


def _simple(
    sources: _Sources,
    title: str,
    offer: str,
    rules: list[Rule],
    *,
    unit: str = "per item's unit",
    where: Iterable[str] | None = None,
) -> dict[str, Any]:
    rates, published = _metered(sources, offer, rules, where=where)
    return _service(title, ["region", "item", "from"], rates, published, unit=unit)


def _merge(*services: dict[str, Any]) -> dict[str, Any]:
    """One service from several reads: their items side by side per region."""
    first = dict(services[0])
    rates: dict[str, Any] = {}
    for service in services:
        for region, items in service["rates"].items():
            rates.setdefault(region, {}).update(items)
        first["published"] = max(first["published"], service["published"])
    first["rates"] = rates
    return first


_ELB = [
    _rule("alb-hour", "LoadBalancerUsage", "Load Balancer-Application"),
    _rule("alb-lcu", "LCUUsage", "Load Balancer-Application"),
    _rule("nlb-hour", "LoadBalancerUsage", "Load Balancer-Network"),
    _rule("nlb-lcu", "LCUUsage", "Load Balancer-Network"),
    _rule("gwlb-hour", "LoadBalancerUsage", "Load Balancer-Gateway"),
    _rule("gwlb-lcu", "LCUUsage", "Load Balancer-Gateway"),
    _rule("clb-hour", "LoadBalancerUsage", "Load Balancer"),
    _rule("clb-gb", "DataProcessing-Bytes", "Load Balancer"),
]
_VPC = [
    _rule("public-ipv4", r"PublicIPv4:InUseAddress"),
    _rule("public-ipv4-idle", r"PublicIPv4:IdleAddress"),
    _rule("endpoint-hour", "VpcEndpoint-Hours"),
    _rule("endpoint-gb", "VpcEndpoint-Bytes"),
    _rule("gwlb-endpoint-hour", "VpcEndpoint-GWLBE-Hours"),
    _rule("gwlb-endpoint-gb", "VpcEndpoint-GWLBE-Bytes"),
    _rule("tgw-attachment-hour", "TransitGateway-Hours", attachmentType="VPC"),
    _rule("tgw-gb", "TransitGateway-Bytes", attachmentType="VPC"),
    _rule("vpn-hour", r"VPN-Usage-Hours:ipsec\.1"),
    _rule("vpn-large-hour", r"VPN-large-Usage-Hours:ipsec\.1"),
    _rule("client-vpn-endpoint-hour", "ClientVPN-EndpointHours"),
    _rule("client-vpn-connection-hour", "ClientVPN-ConnectionHours"),
    _rule("traffic-mirroring-hour", "ENI-Mirror"),
    _rule("reachability-analysis", "Analysis-Runs"),
    _rule("access-analysis-eni", "NetworkInterface-Assessment"),
    _rule("lattice-service-hour", "VPCLattice-Service-Hourly"),
    _rule("lattice-gb", "VPCLattice-DataProcessing-Bytes"),
    _rule("lattice-request", "VPCLattice-RequestCount-Charged"),
    _rule("verified-access-app-hour", "VerifiedAccess-App-Hours"),
    _rule("verified-access-connection-hour", "VerifiedAccess-ConnectionHours"),
    _rule("verified-access-gb", "VerifiedAccess-DataProcess-Bytes"),
    _rule("peering-gb", "VpcPeering-Out-Bytes", transferType="Intra Region Peering Outbound"),
    _rule("ipam-ip-hour", "IPAddressManager-IP-Hours"),
    _rule("route-server-endpoint-hour", "RouteServer-EndpointHours"),
]
_DATA_TRANSFER = [
    _rule(
        "internet-out", "DataTransfer-Out-Bytes", transferType="AWS Outbound", toLocation="External"
    ),
    _rule("regional", "DataTransfer-Regional-Bytes"),
]
_S3 = [
    _rule("storage-standard", "TimedStorage-ByteHrs", volumeType="Standard"),
    _rule("storage-intelligent-tiering", "TimedStorage-INT-FA-ByteHrs"),
    _rule("storage-intelligent-tiering-ia", "TimedStorage-INT-IA-ByteHrs"),
    _rule("storage-intelligent-tiering-aia", "TimedStorage-INT-AIA-ByteHrs"),
    _rule("storage-standard-ia", "TimedStorage-SIA-ByteHrs"),
    _rule("storage-one-zone-ia", "TimedStorage-ZIA-ByteHrs"),
    _rule("storage-express-one-zone", "TimedStorage-XZ-ByteHrs"),
    _rule("storage-glacier-instant-retrieval", "TimedStorage-GIR-ByteHrs"),
    _rule("storage-glacier-flexible-retrieval", "TimedStorage-GlacierByteHrs"),
    _rule("write-standard", "Requests-Tier1"),
    _rule("read-standard", "Requests-Tier2"),
    _rule("write-intelligent-tiering", "Requests-INT-Tier1"),
    _rule("read-intelligent-tiering", "Requests-INT-Tier2"),
    _rule("write-standard-ia", "Requests-SIA-Tier1"),
    _rule("read-standard-ia", "Requests-SIA-Tier2"),
    _rule("write-one-zone-ia", "Requests-ZIA-Tier1"),
    _rule("read-one-zone-ia", "Requests-ZIA-Tier2"),
    _rule("write-express-one-zone", "Requests-XZ-Tier1"),
    _rule("read-express-one-zone", "Requests-XZ-Tier2"),
    _rule("write-glacier-instant-retrieval", "Requests-GIR-Tier1"),
    _rule("read-glacier-instant-retrieval", "Requests-GIR-Tier2"),
    _rule("write-glacier-flexible-retrieval", "Requests-GLACIER-Tier1", operation="PutObject"),
    _rule("read-glacier-flexible-retrieval", "Requests-GLACIER-Tier2"),
    _rule("read-glacier-deep-archive", "Requests-GDA-Tier2"),
    _rule("retrieval-standard-ia", "Retrieval-SIA"),
    _rule("retrieval-one-zone-ia", "Retrieval-ZIA"),
    _rule("retrieval-glacier-instant-retrieval", "Retrieval-GIR"),
    _rule("retrieval-express-one-zone", "Retrieval-XZ"),
    _rule("upload-express-one-zone", "Upload-XZ"),
    _rule("monitoring-intelligent-tiering", "Monitoring-Automation-INT"),
    _rule("storage-lens-objects", "StorageAnalytics-ObjCount"),
    _rule("batch-operations-job", "BatchOperations-Jobs"),
    _rule("batch-operations-object", "BatchOperations-Objects"),
    _rule("storage-tables", "Tables-TimedStorage-ByteHrs"),
    _rule("write-tables", "Tables-Requests-Tier1"),
    _rule("read-tables", "Tables-Requests-Tier2"),
    _rule("select-scanned", "Select-Scanned-Bytes"),
    _rule("select-returned", "Select-Returned-Bytes"),
]
_S3_DEEP_ARCHIVE = [
    _rule("storage-glacier-deep-archive", "TimedStorage-GDA-ByteHrs"),
    _rule("write-glacier-deep-archive", "Requests-GDA-Tier1", operation="PutObject"),
]
_LAMBDA = [
    _rule("requests", "Request", group="AWS-Lambda-Requests"),
    _rule("requests-arm", "Request-ARM"),
    _rule("gb-second", "Lambda-GB-Second"),
    _rule("gb-second-arm", "Lambda-GB-Second-ARM"),
    _rule("ephemeral-gb-second", "Lambda-Storage-GB-Second"),
    _rule("ephemeral-gb-second-arm", "Lambda-Storage-GB-Second-ARM"),
    _rule("edge-requests", "Lambda-Edge-Request"),
    _rule("edge-gb-second", "Lambda-Edge-GB-Second"),
]
_FARGATE = [
    _rule("vcpu-hour", r"Fargate-vCPU-Hours:perCPU"),
    _rule("gb-hour", "Fargate-GB-Hours"),
    _rule("arm-vcpu-hour", r"Fargate-ARM-vCPU-Hours:perCPU"),
    _rule("arm-gb-hour", "Fargate-ARM-GB-Hours"),
    _rule("windows-vcpu-hour", r"Fargate-Windows-vCPU-Hours:perCPU"),
    _rule("windows-gb-hour", "Fargate-Windows-GB-Hours"),
    _rule("windows-license-vcpu-hour", r"Fargate-Windows-OS-Hours:perCPU"),
    _rule("ephemeral-gb-hour", "Fargate-EphemeralStorage-GB-Hours"),
    _rule("anywhere-instance-hour", "ECS-Anywhere-Instance-hours"),
]
_EKS = [
    _rule("cluster-hour", r"AmazonEKS-Hours:perCluster"),
    _rule("extended-support-hour", r"AmazonEKS-Hours:extendedSupport"),
    _rule("provisioned-xl-hour", r"AmazonEKS-Hours:XL-ProvisionedTier"),
    _rule("provisioned-2xl-hour", r"AmazonEKS-Hours:2XL-ProvisionedTier"),
    _rule("provisioned-4xl-hour", r"AmazonEKS-Hours:4XL-ProvisionedTier"),
    _rule("provisioned-8xl-hour", r"AmazonEKS-Hours:8XL-ProvisionedTier"),
    _rule("hybrid-vcpu-hour", r"AmazonEKSHybridNodes-Hours:pervCPU"),
    _rule("outposts-cluster-hour", r"AmazonEKS-Local-Outposts-Hours:perCluster"),
]
_DYNAMODB = [
    _rule("read-request", "ReadRequestUnits"),
    _rule("write-request", "WriteRequestUnits"),
    _rule("read-request-ia", "IA-ReadRequestUnits"),
    _rule("write-request-ia", "IA-WriteRequestUnits"),
    _rule("replicated-write-request", "ReplWriteRequestUnits"),
    _rule("read-capacity-hour", "ReadCapacityUnit-Hrs"),
    _rule("write-capacity-hour", "WriteCapacityUnit-Hrs"),
    _rule("read-capacity-hour-ia", "IA-ReadCapacityUnit-Hrs"),
    _rule("write-capacity-hour-ia", "IA-WriteCapacityUnit-Hrs"),
    _rule("storage", "TimedStorage-ByteHrs"),
    _rule("storage-ia", "IA-TimedStorage-ByteHrs"),
    _rule("pitr-storage", "TimedPITRStorage-ByteHrs"),
    _rule("backup-storage", "TimedBackupStorage-ByteHrs"),
    _rule("streams-read", "Streams-Requests"),
]
_API_GATEWAY = [
    _rule("rest-request", "ApiGatewayRequest"),
    _rule("http-request", "ApiGatewayHttpRequest"),
    _rule("websocket-message", "ApiGatewayMessage"),
    _rule("websocket-minute", "ApiGatewayMinute"),
    *(
        _rule(f"cache-{size}", rf"ApiGatewayCacheUsage:{re.escape(size)}GB")
        for size in ("0.5", "1.55", "6.05", "13.5", "28.4", "58.2", "118", "237")
    ),
]
_SQS = [
    _rule("standard-request", "Requests-(RBP|Tier1)", queueType="Standard"),
    _rule("fifo-request", "Requests-FIFO-(RBP|Tier1)"),
]
_SNS = [
    _rule("request", "Requests-Tier1"),
    _rule("fifo-request", "F-Request-Tier1"),
    _rule("delivery-http", "DeliveryAttempts-HTTP"),
    _rule("delivery-email", "DeliveryAttempts-SMTP"),
    _rule("delivery-mobile", "DeliveryAttempts-APNS"),
    _rule("delivery-sqs", "DeliveryAttempts-SQS"),
    _rule("delivery-lambda", "DeliveryAttempts-LAMBDA"),
    _rule("delivery-firehose", "DeliveryAttempts-FIREHOSE"),
]
_SECRETS = [
    _rule("secret", "AWSSecretsManager-Secrets?"),
    _rule("api-request", "AWSSecretsManager-?APIRequests?"),
]
_KMS = [
    _rule("key", "KMS-Keys"),
    _rule("request", "KMS-Requests"),
    _rule("request-asymmetric", "KMS-Requests-Asymmetric"),
]
_CLOUDWATCH = [
    _rule("metric", "CW:MetricMonitorUsage"),
    _rule("alarm", "CW:AlarmMonitorUsage"),
    _rule("alarm-high-resolution", "CW:HighResAlarmMonitorUsage"),
    _rule("alarm-composite", "CW:CompositeAlarmMonitorUsage"),
    _rule("api-request", "CW:Requests"),
    _rule("logs-ingested", "DataProcessing-Bytes", version="Current"),
    _rule("logs-ingested-ia", "DataProcessingIA-Bytes"),
    _rule("logs-stored", "TimedStorage-ByteHrs", version="Current"),
    _rule("logs-scanned", "DataScanned-Bytes"),
    _rule("logs-delivered-s3", "S3-Egress-Bytes"),
    _rule("data-protection-gb", "DataProtection-Bytes"),
    _rule("metric-stream-update", "CW:MetricStreamUsage"),
    _rule("canary-run", "CW:Canary-runs"),
    _rule("rum-event", "CW:RUM-events"),
    _rule("xray-spans-indexed", "XRay-Spans-Indexed"),
]
_CLOUDWATCH_GLOBAL = [_rule("dashboard", "DashboardsUsageHour", version="Extended")]
_WAF = [
    _rule("web-acl", "WebACLV2"),
    _rule("rule", "RuleV2"),
    _rule("request", "RequestV2-Tier1"),
    _rule("bot-control", "AMR-BotControl"),
    _rule("bot-control-request", "AMR-BotControl-Request"),
]
_EFS = [
    _rule("standard", "TimedStorage-ByteHrs"),
    _rule("standard-ia", "IATimedStorage-ByteHrs"),
    _rule("archive", "ArchiveTimedStorage-ByteHrs"),
    _rule("one-zone", "TimedStorage-Z-ByteHrs"),
    _rule("one-zone-ia", "IATimedStorage-Z-ByteHrs"),
    _rule("elastic-read", "ETDataAccess-Bytes", accessType="Read"),
    _rule("elastic-write", "ETDataAccess-Bytes", accessType="Write"),
    _rule("ia-read", "IADataAccess-Bytes", accessType="Read"),
    _rule("provisioned-throughput", "ProvisionedTP-MiBpsHrs"),
]
_ROUTE53_GLOBAL = [
    _rule("hosted-zone", "HostedZone"),
    _rule("query-standard", "DNS-Queries"),
    _rule("query-latency", "LBR-Queries"),
    _rule("query-geo", "Geo-Queries"),
    _rule("query-ip-based", "Cidr-Queries"),
    _rule("health-check-aws", "Health-Check-AWS"),
    _rule("health-check-external", "Health-Check-Non-AWS"),
    _rule("traffic-policy-record", "Traffic-Flow-Policy-Records"),
]
_ROUTE53_REGIONAL = [
    _rule("resolver-endpoint-hour", "ResolverNetworkInterface"),
    _rule("resolver-query", "DNS-Queries"),
    _rule("dns-firewall-query", "DNS-FirewallQueries"),
    _rule("dns-firewall-domain", "DNS-FirewallDomainName"),
    _rule("profile-hour", "DNS-ProfileBasePackage"),
]
_STEP_FUNCTIONS = [
    _rule("state-transition", "StateTransition"),
    _rule("express-request", "StepFunctions-Request"),
    _rule("express-gb-second", "StepFunctions-GB-Second"),
]
_EVENTBRIDGE = [
    _rule("custom-event", "Event-64K-Chunks", operation="PutEvents"),
    _rule("partner-event", "Event-64K-Chunks", operation="ReceivedPartnerEvents"),
    _rule(
        "cross-account-event", "Invocation-64K-Chunks", operation="CrossAccountInvoke-CustomEvent"
    ),
    _rule("api-destination", "Invocation-64K-Chunks", operation="InvokeApiDestination"),
    _rule("pipe-request", "Request-64K-Chunks"),
    _rule("scheduler-invocation", "ScheduledInvocation"),
    _rule("archive-processed", "ArchivedEvents-Bytes"),
    _rule("archive-stored", "TimedStorage-ByteHrs", operation="StandardStorage"),
    _rule("schema-discovery", "Event-8K-Chunks"),
]
_COGNITO = [
    _rule("essentials-mau", "CognitoEssentialsMAU"),
    _rule("lite-mau", "CognitoLiteMAU"),
    _rule("plus-mau", "CognitoPlusMAU"),
    _rule("enterprise-mau", "CognitoEnterpriseMAU"),
    _rule("m2m-token", "CUPM2MTokenRequestsFull"),
]
_GLUE = [
    _rule("etl-dpu-hour", "ETL-DPU-Hour"),
    _rule("etl-flex-dpu-hour", "ETL-Flex-DPU-Hour"),
    _rule("crawler-dpu-hour", "Crawler-DPU-Hour"),
    _rule("ray-mdpu-hour", "ETL-MemOptimized-DPU-Hour"),
    _rule("interactive-dpu-hour", "GlueInteractiveSession-DPU-Hour"),
    _rule("catalog-object", "Catalog-Storage"),
    _rule("catalog-request", "Catalog-Request"),
    _rule("databrew-node-hour", "DBrew-Node-Hour"),
    _rule("databrew-session", "DBrew-Sessions"),
]
_ATHENA = [
    _rule("tb-scanned", "DataScannedInTB"),
    _rule("capacity-dpu-hour", "ReservedCapacityInDPUHours"),
    _rule("spark-dpu-hour", "CodeExecutionInDPUHours"),
]
_KINESIS = [
    _rule("shard-hour", "Storage-ShardHour"),
    _rule("put-payload-unit", "PutRequestPayloadUnits"),
    _rule("extended-shard-hour", "Extended-ShardHour"),
    _rule("efo-consumer-shard-hour", "EnhancedFanoutHour"),
    _rule("efo-gb", "ReadBytes"),
    _rule("on-demand-stream-hour", "OnDemand-StreamHour"),
    _rule("on-demand-in-gb", "OnDemand-BilledIncomingBytes"),
    _rule("on-demand-out-gb", "OnDemand-BilledOutgoingBytes"),
    _rule("on-demand-efo-gb", "OnDemand-BilledOutgoingEFOBytes"),
]
_FIREHOSE = [
    _rule("ingest-gb", "BilledBytes", operation="PutRecordBatch"),
    _rule("format-conversion-gb", "DFCBilledBytes"),
    _rule("vpc-delivery-hour", "Firehose-VpcDelivery-Hours"),
    _rule("vpc-delivery-gb", "Firehose-VpcDelivery-Bytes"),
    _rule("dynamic-partitioning-gb", "DPBytesDelivered"),
]
_ECR = [
    _rule("storage", "TimedStorage-ByteHrs"),
]
_MSK_USAGE = [
    _rule("storage", "Kafka.Storage.GP2"),
    _rule("provisioned-throughput", "Kafka.Throughput"),
    _rule("tiered-storage", "Kafka.Storage.Tiered"),
    _rule("serverless-cluster-hour", "KafkaServerless-ClusterHours"),
    _rule("serverless-partition-hour", "KafkaServerless-PartitionHours"),
    _rule("serverless-in-gb", "KafkaServerless-In-Bytes"),
    _rule("serverless-out-gb", "KafkaServerless-Out-Bytes"),
    _rule("serverless-storage", "KafkaServerless-StorageHours"),
    _rule("connect-mcu-hour", r"Kafka\.mcu\.general"),
    _rule("express-storage", "Express.Storage"),
    _rule("express-in-gb", "Express.In-Bytes"),
]
_MQ_USAGE = [
    _rule("storage-efs", "TimedStorage-ByteHrs", deploymentOption="Multi-AZ"),
    _rule("storage-ebs", "TimedStorage-EBS-ByteHrs"),
]
_REDSHIFT_USAGE = [
    _rule("managed-storage", r"RMS:ra3\.xlplus"),
    _rule("serverless-rpu-hour", "Redshift:ServerlessUsage"),
    _rule("spectrum-tb", "DataScanned"),
    _rule("snapshot", "Redshift:PaidSnapshots"),
]
_OPENSEARCH_USAGE = [
    _rule("gp3", "ES:GP3-Storage"),
    _rule("gp3-iops", "ES:GP3-PIOPS"),
    _rule("gp3-throughput", "ES:GP3-Provisioned-ThroughPut"),
    _rule("gp2", "ES:GP2-Storage"),
    _rule("io1", "ES:PIOPS-Storage"),
    _rule("io1-iops", "ES:PIOPS"),
    _rule("magnetic", "ES:Magnetic-Storage"),
    _rule("managed-storage", "ES:Managed-Storage"),
    _rule("serverless-indexing-ocu-hour", "IndexingOCU"),
    _rule("serverless-search-ocu-hour", "SearchOCU"),
    _rule("serverless-storage", "StorageUsedInS3ByteHour"),
    _rule("ingestion-ocu-hour", "IngestionOCU"),
]
_RDS_USAGE = [
    *(
        _rule(f"{deployment} {volume}", usage, deploymentModel="")
        for deployment, prefix in (
            ("Single-AZ", "RDS:"),
            ("Multi-AZ", "RDS:Multi-AZ-"),
            ("Multi-AZ cluster", "RDS:Multi-AZCluster-"),
        )
        for volume, usage in (
            *((("gp2", f"{prefix}GP2-Storage"),) if "Cluster" not in prefix else ()),
            ("gp3", f"{prefix}GP3-Storage"),
            ("io1", f"{prefix}PIOPS-Storage"),
            ("io2", f"{prefix}PIOPS-Storage-IO2"),
            *((("magnetic", f"{prefix}StorageUsage"),) if "Cluster" not in prefix else ()),
            ("gp3-iops", f"{prefix}GP3-PIOPS"),
            ("io1-iops", f"{prefix}PIOPS"),
            ("io2-iops", f"{prefix}IO2-PIOPS"),
        )
    ),
    _rule("aurora storage", "Aurora:StorageUsage"),
    _rule("aurora-io-optimized storage", "Aurora:IO-OptimizedStorageUsage"),
    _rule("aurora io-request", "Aurora:StorageIOUsage"),
    _rule("aurora-serverless acu-hour", "Aurora:ServerlessV2Usage"),
    _rule("aurora-serverless-io-optimized acu-hour", "Aurora:ServerlessV2IOOptimizedUsage"),
    _rule("backup", "RDS:ChargedBackupUsage"),
    _rule("proxy vcpu-hour", "RDS:ProxyUsage"),
]
_DOCDB_USAGE = [
    _rule("storage", "StorageUsage"),
    _rule("storage-io-optimized", "IO-OptimizedStorageUsage"),
    _rule("io-request", "StorageIOUsage"),
    _rule("backup", "BackupUsage"),
    _rule("serverless-dcu-hour", "DocumentDB:ServerlessUsage"),
    _rule("elastic-storage", "ElasticStorageUsage"),
    _rule("elastic-vcpu-hour", "ElasticCPUUsage"),
]
_NEPTUNE_USAGE = [
    _rule("storage", "StorageUsage"),
    _rule("storage-io-optimized", "IO-OptimizedStorageUsage"),
    _rule("io-request", "StorageIOUsage"),
    _rule("backup", "BackupUsage"),
    _rule("serverless-ncu-hour", "Neptune:ServerlessUsage"),
]
_ELASTICACHE_USAGE = [
    *(
        _rule(f"{engine.lower()} {item}", usage, cacheEngine=engine)
        for engine in ("Redis", "Valkey", "Memcached")
        for item, usage in (
            ("serverless-gb-hour", f"CachedData:{engine}"),
            ("serverless-ecpu", f"ElastiCacheProcessingUnits:{engine}"),
        )
    ),
    _rule("backup", "ElastiCache:BackupUsage"),
]
_MEMORYDB_USAGE = [
    _rule("redis data-written", "DataWritten", engine="Redis"),
    _rule("valkey data-written", "DataWritten:Valkey"),
]
_BACKUP = [
    *(
        _rule(f"{tier}-{name}", f"{tier.title()}Storage-ByteHrs-{usage}", vaulttype="BackupVault")
        for tier in ("warm", "cold")
        for name, usage in (
            ("dynamodb", "DynamoDB"),
            ("efs", "EFS"),
            ("vmware", "VirtualMachine"),
            ("timestream", "Timestream"),
        )
    ),
    _rule("warm-s3", "WarmStorage-ByteHrs-S3", vaulttype="BackupVault"),
]
_SES = [
    _rule("outbound-email", r"Recipients(-EC2)?", recipient="Other"),
    _rule("inbound-email", "Message", recipient="Amazon SES"),
    _rule("inbound-chunk", "ReceivedChunk"),
    _rule("attachment-gb", "AttachmentsSize-Bytes"),
    _rule("dedicated-ip", "DIP-Hours"),
]
_NETWORK_FIREWALL = [
    _rule("endpoint-hour", "Endpoint-Hour"),
    _rule("secondary-endpoint-hour", "Secondary-Endpoint-Hour"),
    _rule("gb", "Traffic-GB-Processed"),
    _rule("advanced-endpoint-hour", "Advanced-Inspection-Endpoint-Hour"),
]
_CLOUDTRAIL = [
    _rule("paid-event", "PaidEventsRecorded"),
    _rule("data-event", "DataEventsRecorded"),
    _rule("insights-event", "InsightsEvents"),
    _rule("lake-ingested-gb", "Ingestion-Bytes"),
    _rule("lake-scanned-gb", "QueryScanned-Bytes"),
]
_CONFIG = [
    _rule("configuration-item", "ConfigurationItemRecorded"),
    _rule("rule-evaluation", "ConfigRuleEvaluations"),
    _rule("conformance-pack-evaluation", "ConformancePackEvaluations"),
]
_XRAY = [
    _rule("trace-stored", "XRay-TracesStored"),
    _rule("trace-accessed", "XRay-TracesAccessed"),
]
_APPSYNC = [
    _rule("request", "GraphQLInvocation"),
    _rule("realtime-message", "GraphQLNotification"),
    _rule("realtime-minute", "ConnectionDuration"),
    _rule("events-operation", "EventAPI-Operation"),
]
_TRANSFER = [
    _rule("sftp-hour", "ProtocolHours", endpoint="SFTP-Protocol-Hours"),
    _rule("ftps-hour", "ProtocolHours", endpoint="FTPS-Protocol-Hours"),
    _rule("ftp-hour", "ProtocolHours", endpoint="FTP-Protocol-Hours"),
    _rule("as2-hour", "ProtocolHours", endpoint="AS2-Hours"),
    _rule("upload-gb", "UploadBytes", data="SFTP-Upload-Bytes"),
    _rule("download-gb", "DownloadBytes", data="SFTP-Download-Bytes"),
    _rule("as2-message", "OutboundMessages"),
]
_DATASYNC = [
    _rule("gb", "Transferred-Bytes"),
    _rule("enhanced-gb", "Transferred-Bytes-Enhanced"),
    _rule("enhanced-task", "Task-Executions-Enhanced"),
]
_APP_RUNNER = [
    _rule("vcpu-hour", "AppRunner-vCPU-hours"),
    _rule("gb-hour", "AppRunner-GB-hours"),
    _rule("provisioned-gb-hour", "AppRunner-Provisioned-GB-hours"),
    _rule("build-minute", "AppRunner-Build-mins"),
    _rule("automatic-deployment", "AppRunner-AutomaticDeployment"),
]
_CODEPIPELINE = [
    _rule("pipeline", "activePipeline"),
    _rule("action-minute", "actionExecutionMinute"),
]
_CODEBUILD = [
    _rule("linux-small-minute", r"Build-Min:Linux:g1\.small"),
    _rule("linux-medium-minute", r"Build-Min:Linux:g1\.medium"),
    _rule("linux-large-minute", r"Build-Min:Linux:g1\.large"),
    _rule("linux-2xlarge-minute", r"Build-Min:Linux:g1\.2xlarge"),
    _rule("arm-small-minute", r"Build-Min:ARM:g1\.small"),
    _rule("arm-large-minute", r"Build-Min:ARM:g1\.large"),
    _rule("windows-medium-minute", r"Build-Min:Windows:g1\.medium"),
]
_CLOUDHSM = [_rule("hsm-hour", "CloudHSMv2Usage")]
_PRIVATE_CA = [
    _rule("general-ca", "PaidPrivateCA"),
    _rule("short-lived-ca", "ShortLivedCertificatePrivateCA"),
    _rule("certificate", "PrivateCertificatesIssued"),
]
_MWAA = [
    _rule("micro-environment-hour", "Airflow-MicroEnvironment"),
    *(
        _rule(f"{size.lower()}-{part.lower()}-hour", f"Airflow-{size}{part}")
        for size in ("Small", "Medium", "Large", "XLarge", "2XLarge")
        for part in ("Environment", "Worker", "Scheduler", "WebServer")
    ),
    _rule("database-storage", "Airflow-StandardDatabaseStorage"),
]
_GRAFANA = [
    _rule("editor-user", "Grafana:EditorUser"),
    _rule("viewer-user", "Grafana:ViewerUser"),
]
_PROMETHEUS = [
    _rule("sample", "AMP:MetricSampleCount"),
    _rule("query-sample", "AMP:QuerySamplesProcessed"),
    _rule("storage", "AMP:MetricStorageByteHrs"),
    _rule("collector-hour", "AMP:CollectorHours"),
]
_KEYSPACES = [
    _rule("read-request", "ReadRequestUnits"),
    _rule("write-request", "WriteRequestUnits"),
    _rule("read-capacity-hour", "ReadCapacityUnit-Hrs"),
    _rule("write-capacity-hour", "WriteCapacityUnit-Hrs"),
    _rule("storage", "TimedStorage-ByteHrs"),
    _rule("pitr-storage", "TimedPITRStorage-ByteHrs"),
]
_TIMESTREAM = [
    _rule("ingested-gb", "DataIngestion-Bytes"),
    _rule("query-tcu-hour", "QueryTCU"),
    _rule("memory-store", "MagneticStore-ByteHrs"),
]
_STORAGE_GATEWAY = [
    _rule("gateway-hour", "Gateway-Hrs"),
    _rule("volume-storage", "Gateway:VolumeUsage"),
    _rule("tape-storage", "Gateway:VTL-Storage"),
    _rule("tape-archive", "Gateway:VTS-Storage"),
    _rule("uploaded-gb", "Uploaded-Bytes"),
]
_CLOUD_MAP = [
    _rule("resource", "Cloud-Map-Resources"),
    _rule("api-call", "Cloud-Map-API-Calls"),
]
_IOT = [
    _rule("connection-minute", "ConnectionMinutes", protocol="MQTT"),
    _rule("message", "Messages", protocol="Any"),
    _rule("shadow-operation", "RegistryAndShadowOperations"),
    _rule("rule-triggered", "RulesTriggered"),
    _rule("action-executed", "ActionsExecuted"),
]
_CLOUD_WAN = [
    _rule("edge-hour", "CloudWAN-CoreNetworkEdge-Hours"),
    _rule("attachment-hour", "CloudWAN-Attachment-Hours", attachmentType="VPC"),
    _rule("peering-hour", "CloudWAN-Peering-Hours"),
    _rule("gb", "CloudWAN-Bytes", attachmentType="VPC"),
]
_RECOVERY_CONTROLLER = [
    _rule("cluster-hour", "Global-Cluster-Hours"),
    _rule("readiness-check-hour", "Global-ReadinessCheck-Hours"),
    _rule("region-switch-plan", "Global-AmazonARCRegionSwitchPlan"),
]
_FLINK = [
    _rule("kpu-hour", "KPU-Hour(-Java)?"),
    _rule("running-storage", "RunningApplicationStorage"),
    _rule("backup", "DurableApplicationBackups"),
]
_DRS = [_rule("server-hour", "DRS-Replication", replicationType="Normal")]
_DMS_USAGE = [
    _rule("Single-AZ storage", "DMS:GP2-Storage"),
    _rule("Multi-AZ storage", "DMS:Multi-AZ-GP2-Storage"),
]
_SHIELD_GLOBAL = [_rule("advanced-month", "Shield-Monthly-Fee")]
_DIRECTORY = [
    _rule("managed-ad-standard-hour", "Std-MicrosoftAD-DC-Usage"),
    _rule("managed-ad-enterprise-hour", "MicrosoftAD-DC-Usage"),
    _rule("simple-ad-small-hour", "Small-SimpleAD-Usage"),
    _rule("simple-ad-large-hour", "Large-SimpleAD-Usage"),
    _rule("ad-connector-small-hour", "Small-Directory-Usage"),
    _rule("ad-connector-large-hour", "Large-ADConnector-Usage"),
]
_EMR_USAGE = [
    _rule("serverless-vcpu-hour", "EMR-SERVERLESS-vCPUHours"),
    _rule("serverless-gb-hour", "EMR-SERVERLESS-MemoryGBHours"),
    _rule("serverless-arm-vcpu-hour", "EMR-SERVERLESS-ARM-vCPUHours"),
    _rule("serverless-arm-gb-hour", "EMR-SERVERLESS-ARM-MemoryGBHours"),
]


# -- the Price List API: services by instance type ----------------------------


def _attr(product: Product, name: str) -> str:
    return product.attributes.get(name, "")


#: RDS engines: (database engine, edition, licence model) -> the table's name.
_RDS_ENGINES = {
    ("PostgreSQL", "", "No license required"): "PostgreSQL",
    ("MySQL", "", "No license required"): "MySQL",
    ("MariaDB", "", "No license required"): "MariaDB",
    ("Aurora PostgreSQL", "", "No license required"): "Aurora PostgreSQL",
    ("Aurora MySQL", "", "No license required"): "Aurora MySQL",
    ("Oracle", "Standard Two", "License included"): "Oracle SE2 (license included)",
    ("Oracle", "Standard Two", "Bring your own license"): "Oracle SE2 (BYOL)",
    ("Oracle", "Enterprise", "Bring your own license"): "Oracle EE (BYOL)",
    ("SQL Server", "Express", "License included"): "SQL Server Express",
    ("SQL Server", "Web", "License included"): "SQL Server Web",
    ("SQL Server", "Standard", "License included"): "SQL Server Standard",
    ("SQL Server", "Enterprise", "License included"): "SQL Server Enterprise",
    ("Db2", "Standard", "Bring your own license"): "Db2 Standard (BYOL)",
    ("Db2", "Advanced", "Bring your own license"): "Db2 Advanced (BYOL)",
}
_RDS_DEPLOYMENTS = {
    "InstanceUsage": "Single-AZ",
    "Multi-AZUsage": "Multi-AZ",
    "MirrorUsage": "Multi-AZ",
    "Multi-AZClusterUsage": "Multi-AZ cluster",
    "InstanceUsageIOOptimized": "Single-AZ",
}


def _rds_key(product: Product) -> tuple[str, ...] | None:
    if product.family != "Database Instance" or _attr(product, "deploymentModel"):
        return None
    usage, _, instance = product.usage.partition(":")
    deployment = _RDS_DEPLOYMENTS.get(usage)
    engine = _RDS_ENGINES.get(
        (
            _attr(product, "databaseEngine"),
            _attr(product, "databaseEdition"),
            _attr(product, "licenseModel"),
        )
    )
    if deployment is None or engine is None or not instance.startswith("db."):
        return None
    if usage == "InstanceUsageIOOptimized":
        engine += " I/O-Optimized"
    return engine, deployment, _instance_class(product, instance)


def _instance_class(product: Product, from_usage: str) -> str:
    """A database instance class by AWS's own name: the usage type shortens
    its size (``db.r6g.2xl``), the instanceType attribute does not
    (``db.r6g.2xlarge``), and that is the name an element gives."""
    return _attr(product, "instanceType") or from_usage


def _engine_node(engine_attr: str, prefix: str) -> Callable[[Product], tuple[str, ...] | None]:
    def key_of(product: Product) -> tuple[str, ...] | None:
        usage, _, node = product.usage.partition(":")
        if usage != "NodeUsage" or not node.startswith(prefix):
            return None
        engine = _attr(product, engine_attr)
        node = node.removesuffix(":Valkey")
        return (engine, node) if engine and not _attr(product, "ssd") else None

    return key_of


def _memorydb_key(product: Product) -> tuple[str, ...] | None:
    usage, _, node = product.usage.partition(":")
    if usage != "NodeUsage" or not node.startswith("db."):
        return None
    return (_attr(product, "engine") or "Redis", node.removesuffix(":Valkey"))


def _storage_mode(storage_usage: str, io_usage: str) -> Callable[[Product], tuple[str, ...] | None]:
    """DocumentDB and Neptune: an instance's rate by its storage mode."""

    def key_of(product: Product) -> tuple[str, ...] | None:
        if product.family != "Database Instance":
            return None
        usage, _, kind = product.usage.partition(":")
        if usage == storage_usage:
            return ("Standard", _instance_class(product, kind))
        if usage == io_usage:
            return ("I/O-Optimized", _instance_class(product, kind))
        return None

    return key_of


def _msk_key(product: Product) -> tuple[str, ...] | None:
    if _attr(product, "operation") != "RunBroker":
        return None
    family = _attr(product, "computeFamily")
    return (
        (f"kafka.{family}",)
        if family and not family.startswith("express.")
        else ((family,) if family else None)
    )


def _mq_key(product: Product) -> tuple[str, ...] | None:
    if (
        product.family != "Broker Instances"
        or _attr(product, "cross-regionDataReplication") == "Yes"
    ):
        return None
    if _attr(product, "operation") != "CreateBroker:0001":
        return None
    kind = _attr(product, "instanceType")
    return (_attr(product, "brokerEngine"), _attr(product, "deploymentOption"), f"mq.{kind}")


def _opensearch_key(product: Product) -> tuple[str, ...] | None:
    if product.usage.startswith("ESInstance:") and _attr(product, "instanceType"):
        return (_attr(product, "instanceType"),)
    return None


def _redshift_key(product: Product) -> tuple[str, ...] | None:
    usage, _, kind = product.usage.partition(":")
    return (kind,) if usage == "Node" and kind else None


def _emr_key(product: Product) -> tuple[str, ...] | None:
    if _attr(product, "softwareType") != "EMR" or not product.usage.startswith("BoxUsage"):
        return None
    kind = _attr(product, "instanceType")
    return (kind,) if kind else None


def _dms_key(product: Product) -> tuple[str, ...] | None:
    usage, _, kind = product.usage.partition(":")
    deployment = {"InstanceUsg": "Single-AZ", "Multi-AZUsg": "Multi-AZ"}.get(usage)
    return (deployment, kind) if deployment and kind.startswith("dms.") else None


def _cloudsearch_key(product: Product) -> tuple[str, ...] | None:
    usage, _, kind = product.usage.partition(":")
    if usage != "SearchInstance" or _attr(product, "cloudSearchVersion") != "2013":
        return None
    return (kind,)


def _dax_key(product: Product) -> tuple[str, ...] | None:
    usage, _, node = product.usage.partition(":")
    return (node,) if usage == "NodeUsage" and node.startswith("dax.") else None


def _direct_connect(sources: _Sources) -> dict[str, Any]:
    """Port hours per region, as most of the region's locations price them."""
    rates: dict[str, Any] = {}
    published = ""
    for region in sources.regions:
        read = sources.read("AWSDirectConnect", region)
        if read is None:
            continue
        published = max(published, read.published)
        votes: dict[str, Counter[float]] = {}
        out: Counter[float] = Counter()
        for product in read.products:
            if (
                product.family == "Direct Connect"
                and "PortUsage" in product.usage
                and "FlatRate" not in product.usage
            ):
                kind = f"{_attr(product, 'connectionType')} {_attr(product, 'capacity')}"
                votes.setdefault(kind, Counter())[product.tiers[0][1]] += 1
            elif (
                product.family == "Data Transfer"
                and _attr(product, "transferType") == "InterRegion Outbound"
                and _attr(product, "fromRegionCode") == region
                and product.usage.endswith("DataXfer-Out")
            ):
                out[product.tiers[0][1]] += 1
        items = {kind: {"0": counter.most_common(1)[0][0]} for kind, counter in votes.items()}
        if out:
            items["data-out"] = {"0": out.most_common(1)[0][0]}
        if items:
            rates[region] = items
    return _service(
        "Direct Connect", ["region", "item", "from"], rates, published, unit="hour or GB"
    )


def _fsx(sources: _Sources) -> dict[str, Any]:
    """FSx: per file system and deployment, storage by type, throughput, IOPS."""
    rates: dict[str, Any] = {}
    published = ""
    for region in sources.regions:
        read = sources.read("AmazonFSx", region)
        if read is None:
            continue
        published = max(published, read.published)
        items: dict[str, dict[str, float]] = {}
        for product in read.products:
            system = _attr(product, "fileSystemType")
            deployment = _attr(product, "deploymentOption")
            if "FileCache" in _attr(product, "operation"):
                if product.family == "Storage" and product.usage.startswith("Storage"):
                    items.setdefault(
                        f"File Cache storage {_attr(product, 'throughputCapacity')}",
                        _tier_map(product.tiers),
                    )
                continue
            if not system or not deployment:
                continue
            if product.family == "Storage" and product.usage.startswith("Storage"):
                kind = _attr(product, "storageType")
                throughput = _attr(product, "throughputCapacity")
                cache = _attr(product, "cacheType")
                if kind == "INT":
                    kind = f"INT {_attr(product, 'storageTier')}"
                if throughput not in ("", "N/A"):
                    kind += f" {throughput}"
                if cache not in ("", "N/A") and not kind.startswith("INT"):
                    kind += f" {cache}"
                item = f"{system} {deployment} storage {kind}"
            elif product.family == "Storage" and "BackupUsage" in product.usage:
                item = f"{system} backup"
            elif product.family == "Provisioned Throughput":
                item = f"{system} {deployment} throughput"
            elif product.family == "Provisioned IOPS":
                item = f"{system} {deployment} iops"
            else:
                continue
            items.setdefault(item, _tier_map(product.tiers))
        if items:
            rates[region] = items
    return _service("FSx", ["region", "item", "from"], rates, published, unit="per item's unit")


def _cloudfront(sources: _Sources) -> dict[str, Any]:
    """CloudFront by where its edge serves: data out and requests per area."""
    read = sources.read("AmazonCloudFront", GLOBAL)
    if read is None:
        raise PricingError("AWS publishes no CloudFront price file")
    areas: dict[str, str] = {}
    for product in read.products:
        if (
            product.usage.endswith("-DataTransfer-Out-Bytes")
            and _attr(product, "toLocation") == "External"
        ):
            code = product.usage.split("-", 1)[0]
            if code != "Global":
                areas[code] = _attr(product, "fromLocation")
    shared = {
        "function": "Executions-CloudFrontFunctions",
        "invalidation": "Invalidations",
        "kvs-read": "KeyValueStore-EdgeReads",
    }
    rates: dict[str, Any] = {}
    for code, area in areas.items():
        items: dict[str, dict[str, float]] = {}
        wanted = {
            "data-out": f"{code}-DataTransfer-Out-Bytes",
            "origin-out": f"{code}-DataTransfer-Out-OBytes",
            "https-request": f"{code}-Requests-Tier2-HTTPS",
            "http-request": f"{code}-Requests-Tier1",
            "https-proxy-request": f"{code}-Requests-HTTPS-Proxy",
            **shared,
        }
        for item, usage in wanted.items():
            found = next((p for p in read.products if p.usage == usage), None)
            if found is not None:
                items[item] = _tier_map(found.tiers)
        rates[area] = items
    return _service(
        "CloudFront", ["area", "item", "from"], rates, read.published, unit="GB or request"
    )


def _global_accelerator(sources: _Sources) -> dict[str, Any]:
    """The fixed hourly fee, and the data transfer premium of the dominant
    direction from the endpoints' area to the clients' (``NA-EU``)."""
    read = sources.read("AWSGlobalAccelerator", GLOBAL)
    if read is None:
        raise PricingError("AWS publishes no Global Accelerator price file")
    items: dict[str, dict[str, float]] = {}
    for product in read.products:
        if product.usage == "Global-Accelerator-fixed-fee":
            items["accelerator-hour"] = _tier_map(product.tiers)
        match = re.fullmatch(r"([A-Z]{2})-([A-Z]{2})-OUT-Bytes-Internet", product.usage)
        if match and _attr(product, "dominantnon-dominant") == "Dominant":
            items[f"premium {match.group(1)}-{match.group(2)}"] = _tier_map(product.tiers)
    return _service(
        "Global Accelerator",
        ["region", "item", "from"],
        {GLOBAL: items},
        read.published,
        unit="hour or GB",
    )


def _instances(
    sources: _Sources,
    title: str,
    offer: str,
    keys: list[str],
    key_of: Callable[[Product], tuple[str, ...] | None],
    *,
    vcpu: str = "vcpu",
    memory: str = "memory",
) -> dict[str, Any]:
    leaf = keys[-1]

    def describe(product: Product) -> tuple[str, str] | None:
        key = key_of(product)
        shape = _shape(product, vcpu=vcpu, memory=memory)
        return (key[-1], shape) if key and shape else None

    rates, published, info = _keyed(sources, offer, key_of, describe=describe)
    return _service(title, ["region", *keys], rates, published, unit="hour", info={leaf: info})


# -- the table ----------------------------------------------------------------


def build(fresh: bool = False) -> Any:
    """Read AWS's sources and write ``assets/prices/aws.json``."""
    sources = _Sources(fresh)
    regional = sources.regions
    services: dict[str, dict[str, Any]] = {}

    def step(name: str, make: Callable[[], dict[str, Any]]) -> None:
        print(f"aws: {name}", file=sys.stderr, flush=True)
        services[name] = make()

    step("ec2", lambda: _ec2(sources))
    step("ebs", lambda: _ebs(sources))
    step("nat-gateway", lambda: _nat(sources))
    step("vpc", lambda: _simple(sources, "VPC", "AmazonVPC", _VPC))
    step(
        "data-transfer",
        lambda: _simple(sources, "Data transfer", "AWSDataTransfer", _DATA_TRANSFER),
    )
    step("elb", lambda: _simple(sources, "Elastic Load Balancing", "AWSELB", _ELB))
    step(
        "s3",
        lambda: _merge(
            _simple(sources, "S3", "AmazonS3", _S3),
            _simple(sources, "S3", "AmazonS3GlacierDeepArchive", _S3_DEEP_ARCHIVE),
        ),
    )
    step("lambda", lambda: _simple(sources, "Lambda", "AWSLambda", _LAMBDA))
    step("fargate", lambda: _simple(sources, "Fargate", "AmazonECS", _FARGATE))
    step("eks", lambda: _simple(sources, "EKS", "AmazonEKS", _EKS))
    step("dynamodb", lambda: _simple(sources, "DynamoDB", "AmazonDynamoDB", _DYNAMODB))
    step("api-gateway", lambda: _simple(sources, "API Gateway", "AmazonApiGateway", _API_GATEWAY))
    step("sqs", lambda: _simple(sources, "SQS", "AWSQueueService", _SQS))
    step("sns", lambda: _simple(sources, "SNS", "AmazonSNS", _SNS))
    step(
        "secrets-manager",
        lambda: _simple(sources, "Secrets Manager", "AWSSecretsManager", _SECRETS),
    )
    step("kms", lambda: _simple(sources, "KMS", "awskms", _KMS))
    step(
        "cloudwatch",
        lambda: _merge(
            _simple(sources, "CloudWatch", "AmazonCloudWatch", _CLOUDWATCH),
            _simple(sources, "CloudWatch", "AmazonCloudWatch", _CLOUDWATCH_GLOBAL, where=[GLOBAL]),
        ),
    )
    step("waf", lambda: _simple(sources, "WAF", "awswaf", _WAF, where=[*regional, GLOBAL]))
    step("efs", lambda: _simple(sources, "EFS", "AmazonEFS", _EFS))
    step("fsx", lambda: _fsx(sources))
    step(
        "route53",
        lambda: _merge(
            _simple(sources, "Route 53", "AmazonRoute53", _ROUTE53_GLOBAL, where=[GLOBAL]),
            _simple(sources, "Route 53", "AmazonRoute53", _ROUTE53_REGIONAL),
        ),
    )
    step("cloudfront", lambda: _cloudfront(sources))
    step("global-accelerator", lambda: _global_accelerator(sources))
    step("shield", lambda: _simple(sources, "Shield", "AWSShield", _SHIELD_GLOBAL, where=[GLOBAL]))
    step("direct-connect", lambda: _direct_connect(sources))
    step(
        "rds",
        lambda: _instances(
            sources, "RDS", "AmazonRDS", ["engine", "deployment", "instance_class"], _rds_key
        ),
    )
    step("rds-usage", lambda: _simple(sources, "RDS storage and usage", "AmazonRDS", _RDS_USAGE))
    step(
        "elasticache",
        lambda: _instances(
            sources,
            "ElastiCache",
            "AmazonElastiCache",
            ["engine", "node_type"],
            _engine_node("cacheEngine", "cache."),
        ),
    )
    step(
        "elasticache-usage",
        lambda: _simple(sources, "ElastiCache usage", "AmazonElastiCache", _ELASTICACHE_USAGE),
    )
    step(
        "memorydb",
        lambda: _instances(
            sources, "MemoryDB", "AmazonMemoryDB", ["engine", "node_type"], _memorydb_key
        ),
    )
    step(
        "memorydb-usage",
        lambda: _simple(sources, "MemoryDB usage", "AmazonMemoryDB", _MEMORYDB_USAGE),
    )
    step(
        "dax",
        lambda: _instances(sources, "DynamoDB Accelerator", "AmazonDAX", ["node_type"], _dax_key),
    )
    step(
        "opensearch",
        lambda: _instances(
            sources,
            "OpenSearch Service",
            "AmazonES",
            ["instance_type"],
            _opensearch_key,
            memory="memoryGib",
        ),
    )
    step(
        "opensearch-usage",
        lambda: _simple(sources, "OpenSearch usage", "AmazonES", _OPENSEARCH_USAGE),
    )
    step(
        "docdb",
        lambda: _instances(
            sources,
            "DocumentDB",
            "AmazonDocDB",
            ["storage", "instance_class"],
            _storage_mode("InstanceUsage", "InstanceUsageIOOptimized"),
        ),
    )
    step("docdb-usage", lambda: _simple(sources, "DocumentDB usage", "AmazonDocDB", _DOCDB_USAGE))
    step(
        "neptune",
        lambda: _instances(
            sources,
            "Neptune",
            "AmazonNeptune",
            ["storage", "instance_class"],
            _storage_mode("InstanceUsage", "InstanceUsageIOOptimized"),
        ),
    )
    step(
        "neptune-usage", lambda: _simple(sources, "Neptune usage", "AmazonNeptune", _NEPTUNE_USAGE)
    )
    step(
        "redshift",
        lambda: _instances(sources, "Redshift", "AmazonRedshift", ["node_type"], _redshift_key),
    )
    step(
        "redshift-usage",
        lambda: _simple(sources, "Redshift usage", "AmazonRedshift", _REDSHIFT_USAGE),
    )
    step(
        "msk",
        lambda: _instances(
            sources, "MSK", "AmazonMSK", ["broker_type"], _msk_key, memory="memoryGib"
        ),
    )
    step("msk-usage", lambda: _simple(sources, "MSK usage", "AmazonMSK", _MSK_USAGE))
    step(
        "mq",
        lambda: _instances(
            sources, "Amazon MQ", "AmazonMQ", ["engine", "deployment", "instance_type"], _mq_key
        ),
    )
    step("mq-usage", lambda: _simple(sources, "Amazon MQ storage", "AmazonMQ", _MQ_USAGE))
    step("emr", lambda: _instances(sources, "EMR", "ElasticMapReduce", ["instance_type"], _emr_key))
    step("emr-usage", lambda: _simple(sources, "EMR Serverless", "ElasticMapReduce", _EMR_USAGE))
    step("kinesis", lambda: _simple(sources, "Kinesis Data Streams", "AmazonKinesis", _KINESIS))
    step("firehose", lambda: _simple(sources, "Data Firehose", "AmazonKinesisFirehose", _FIREHOSE))
    step("ecr", lambda: _simple(sources, "ECR", "AmazonECR", _ECR))
    step(
        "step-functions",
        lambda: _simple(sources, "Step Functions", "AmazonStates", _STEP_FUNCTIONS),
    )
    step("eventbridge", lambda: _simple(sources, "EventBridge", "AWSEvents", _EVENTBRIDGE))
    step("cognito", lambda: _simple(sources, "Cognito", "AmazonCognito", _COGNITO))
    step("backup", lambda: _simple(sources, "AWS Backup", "AWSBackup", _BACKUP))
    step("glue", lambda: _simple(sources, "Glue", "AWSGlue", _GLUE))
    step("athena", lambda: _simple(sources, "Athena", "AmazonAthena", _ATHENA))
    step("ses", lambda: _simple(sources, "SES", "AmazonSES", _SES))
    step(
        "network-firewall",
        lambda: _simple(sources, "Network Firewall", "AWSNetworkFirewall", _NETWORK_FIREWALL),
    )
    step("cloudtrail", lambda: _simple(sources, "CloudTrail", "AWSCloudTrail", _CLOUDTRAIL))
    step("config", lambda: _simple(sources, "Config", "AWSConfig", _CONFIG))
    step("xray", lambda: _simple(sources, "X-Ray", "AWSXRay", _XRAY))
    step("appsync", lambda: _simple(sources, "AppSync", "AWSAppSync", _APPSYNC))
    step("transfer", lambda: _simple(sources, "Transfer Family", "AWSTransfer", _TRANSFER))
    step("datasync", lambda: _simple(sources, "DataSync", "AWSDataSync", _DATASYNC))
    step("app-runner", lambda: _simple(sources, "App Runner", "AWSAppRunner", _APP_RUNNER))
    step("codepipeline", lambda: _simple(sources, "CodePipeline", "AWSCodePipeline", _CODEPIPELINE))
    step("codebuild", lambda: _simple(sources, "CodeBuild", "CodeBuild", _CODEBUILD))
    step("cloudhsm", lambda: _simple(sources, "CloudHSM", "CloudHSM", _CLOUDHSM))
    step("private-ca", lambda: _simple(sources, "Private CA", "AWSCertificateManager", _PRIVATE_CA))
    step(
        "mwaa",
        lambda: _simple(sources, "Managed Workflows for Apache Airflow", "AmazonMWAA", _MWAA),
    )
    step("grafana", lambda: _simple(sources, "Managed Grafana", "AmazonGrafana", _GRAFANA))
    step(
        "prometheus",
        lambda: _simple(sources, "Managed Service for Prometheus", "AmazonPrometheus", _PROMETHEUS),
    )
    step("keyspaces", lambda: _simple(sources, "Keyspaces", "AmazonMCS", _KEYSPACES))
    step("timestream", lambda: _simple(sources, "Timestream", "AmazonTimestream", _TIMESTREAM))
    step(
        "storage-gateway",
        lambda: _simple(sources, "Storage Gateway", "AWSStorageGateway", _STORAGE_GATEWAY),
    )
    step("cloud-map", lambda: _simple(sources, "Cloud Map", "AWSCloudMap", _CLOUD_MAP))
    step("iot-core", lambda: _simple(sources, "IoT Core", "AWSIoT", _IOT))
    step("cloud-wan", lambda: _simple(sources, "Cloud WAN", "AWSCloudWAN", _CLOUD_WAN))
    step(
        "recovery-controller",
        lambda: _simple(
            sources,
            "Application Recovery Controller",
            "AWSR53AppRecoveryController",
            _RECOVERY_CONTROLLER,
            where=[GLOBAL],
        ),
    )
    step(
        "flink",
        lambda: _simple(
            sources, "Managed Service for Apache Flink", "AmazonKinesisAnalytics", _FLINK
        ),
    )
    step(
        "drs",
        lambda: _simple(sources, "Elastic Disaster Recovery", "AWSElasticDisasterRecovery", _DRS),
    )
    step(
        "dms",
        lambda: _instances(
            sources,
            "Database Migration Service",
            "AWSDatabaseMigrationSvc",
            ["deployment", "instance_class"],
            _dms_key,
        ),
    )
    step(
        "dms-usage", lambda: _simple(sources, "DMS storage", "AWSDatabaseMigrationSvc", _DMS_USAGE)
    )
    step(
        "cloudsearch",
        lambda: _instances(
            sources, "CloudSearch", "AmazonCloudSearch", ["instance_type"], _cloudsearch_key
        ),
    )
    step(
        "directory-service",
        lambda: _simple(sources, "Directory Service", "AWSDirectoryService", _DIRECTORY),
    )

    empty = [name for name, service in services.items() if not service["rates"]]
    for name in empty:
        sources.warn(f"{name}: no rates read; left out")
        del services[name]
    for message in sources.warnings:
        print(f"aws: NOTE {message}", file=sys.stderr)
    return write_table("aws", services, read=datetime.date.today().isoformat())
