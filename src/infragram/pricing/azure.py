"""Azure prices: the Azure Retail Prices API (prices.azure.com), no sign-in.

Every price comes from the shipped table (``assets/prices/azure.json``),
which ``scripts/build/price-tables.py azure`` reads from the API: pay as you
go list prices in US dollars, every region, every size and tier the API
lists. A rate is used in the unit the API publishes it in (``1 Hour``,
``10K``, ``1 GB/Month``); a meter with volume tiers is priced tier by tier.
A meter Azure bills the same everywhere is kept once, as ``global``, and a
region without its own rate is priced from it.

What a sizing does not say is priced as the pricer's default and listed
as assumed: a size, a tier, a count, the hours it runs, and for usage
(storage, requests, data processed) a stated quantity.
"""

from __future__ import annotations

import math
import re
from typing import Any

from pydantic import BaseModel, Field

from ..models.topology import TopologyElement
from . import Price, PriceLine, PricingError
from .ask import HOURS, Ask, Coverage, Pricer, line, priced
from .tables import Service

__all__ = ["COVERAGE", "PLANS", "SOURCE", "measure", "region_of", "tiered"]

SOURCE = "Azure Retail Prices API (prices.azure.com)"

#: What separates a region's name from a note beside it in a caption
#: (``East US 2 · primary``, ``Region | West Europe``, ``UK South (DR)``).
_CAPTION_PARTS = re.compile(r"\s*(?:[·•|,;:/()\[\]{}—–]|\s-\s)\s*")


def region_of(ancestors: tuple[TopologyElement, ...]) -> str | None:
    """The caption of the innermost region frame; :func:`where` finds the
    region in it (``East US 2 · primary`` -> ``eastus2``)."""
    for frame in reversed(ancestors):
        if frame.type == "region" and re.search(r"[A-Za-z]", frame.name):
            return frame.name.strip()
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _region_candidates(caption: str) -> list[str]:
    """The whole caption as a region name, then each part of it on its own."""
    found = [_slug(caption)] + [_slug(part) for part in _CAPTION_PARTS.split(caption)]
    return list(dict.fromkeys(name for name in found if name))


# -- units, tiers and lookups ------------------------------------------------------------

_MEASURE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([KM])?\s*/?\s*(.*?)\s*$")
_DIMENSIONS = {
    "": "count",
    "count": "count",
    "api calls": "count",
    "rotation": "count",
    "hour": "hour",
    "hours": "hour",
    "day": "day",
    "month": "month",
    "year": "year",
    "minute": "minute",
    "second": "second",
    "seconds": "second",
    "gb": "GB",
    "gib": "GB",
    "tb": "TB",
    "gb/month": "GB-month",
    "gib/month": "GB-month",
    "tb/month": "TB-month",
    "gb/hour": "GB-hour",
    "gib/hour": "GB-hour",
    "gb hour": "GB-hour",
    "gib hour": "GB-hour",
    "gb second": "GB-second",
    "gb seconds": "GB-second",
    "gib second": "GB-second",
    "iops/month": "month",
}


def measure(unit: str) -> tuple[float, str]:
    """A unit of measure as the API states it -> (how many, of what):
    ``10K`` -> (10000, count), ``1 GB/Month`` -> (1, GB-month), ``1/Day`` -> (1, day)."""
    match = _MEASURE.match(unit)
    if match is None:
        raise PricingError(f"the Azure price table has a unit it cannot read: {unit!r}")
    size = float(match.group(1)) * {"K": 1e3, "M": 1e6}.get(match.group(2) or "", 1.0)
    if match.group(2):
        return size, "count"
    dimension = _DIMENSIONS.get(match.group(3).lower())
    if dimension is None:
        raise PricingError(f"the Azure price table has a unit it cannot read: {unit!r}")
    return size, dimension


def tiered(bands: list[tuple[float, float]], quantity: float) -> float:
    """What *quantity* costs across volume tiers: (from, price) pairs, lowest first."""
    total = 0.0
    for index, (start, price) in enumerate(bands):
        end = bands[index + 1][0] if index + 1 < len(bands) else math.inf
        if quantity > start:
            total += price * (min(quantity, end) - start)
    return total


def _bands(service: Service, region: str, sku: str, meter: str) -> list[tuple[float, float]]:
    for place in (region, "global"):
        node = service.rates.get(place, {}).get(sku, {})
        bands = sorted(
            (float(key.partition("@")[2] or 0), float(value))
            for key, value in node.items()
            if key == meter or key.startswith(f"{meter}@")
        )
        if bands:
            return bands
    raise PricingError(f"{service.title} has no {meter!r} rate for {sku} in {region}")


def has(service: Service, region: str, sku: str, meter: str) -> bool:
    """Whether the table holds *meter* for *sku* in *region*, or for every region."""
    return any(meter in service.rates.get(place, {}).get(sku, {}) for place in (region, "global"))


def operations_sku(service: Service, region: str, sku: str, meter: str) -> str:
    """The sku whose *meter* bills *sku*'s operations. Azure's price list gives
    some read-access redundancies no operation meter of their own and bills
    them on the redundancy they read from, at its rate: Blob Hot RA-GZRS
    writes on the Blob Hot GZRS write meter."""
    if has(service, region, sku, meter) or " RA-" not in sku:
        return sku
    plain = sku.replace(" RA-", " ", 1)
    return plain if has(service, region, plain, meter) else sku


def skus(service: Service, region: str, pattern: str = "{tier}") -> list[str]:
    """The tiers a sku pattern (``Blob {tier} LRS``) takes in *region*, or everywhere."""
    head, _, tail = pattern.partition("{tier}")
    found = {
        name[len(head) : len(name) - len(tail)]
        for place in (region, "global")
        for name in service.rates.get(place, {})
        if name.startswith(head) and name.endswith(tail) and len(name) > len(head) + len(tail)
    }
    return sorted(found)


def where(ask: Ask) -> str:
    """The element's region as the table keys it, checked against the regions
    virtual machines are sold in. A caption with a note beside the name
    (``East US 2 · primary``) is read for the part that names a region."""
    candidates = _region_candidates(ask.region()) or [""]
    region = candidates[0]
    vm = ask.table.services.get("vm")
    if vm is None:
        return region
    known = next((name for name in candidates if name in vm.rates), None)
    if known is not None:
        return known
    near = [name for name in sorted(vm.rates) if name.startswith(region[:4])]
    raise PricingError(
        f"{ask.name}: Azure has no region {region!r}"
        + (f"; it has {', '.join(near[:8])}" if near else "")
    )


def charge(
    service: Service,
    region: str,
    sku: str,
    meter: str,
    *,
    label: str,
    quantity: float,
    unit: str,
    dimension: str,
    per: float = 1.0,
    kind: str = "usage",
    assumed: bool = False,
) -> PriceLine:
    """One line: *quantity* *unit* (each *per* of the meter's *dimension*),
    priced tier by tier from the meter's published unit."""
    stated = service.info.get("unit", {}).get(f"{sku}|{meter}")
    if stated is None:
        raise PricingError(f"{service.title} has no {meter!r} meter for {sku}")
    size, actual = measure(stated)
    if actual != dimension:
        raise PricingError(
            f"{service.title}: {meter} is billed per {stated}, not per {dimension}; "
            "rebuild the price table"
        )
    bands = _bands(service, region, sku, meter)
    amount = tiered(bands, quantity * per / size)
    rate = amount / quantity if quantity else bands[0][1] * per / size
    return line(label, quantity, unit, rate, kind=kind, assumed=assumed)


def run(
    service: Service,
    region: str,
    sku: str,
    meter: str,
    *,
    label: str,
    count: float,
    hours: float,
    units: float = 1.0,
    assumed: bool = False,
) -> PriceLine:
    """A resource billed for the time it runs: per hour, day or month (a meter
    with no time in its unit is a monthly fee), or per GB-hour provisioned."""
    stated = service.info.get("unit", {}).get(f"{sku}|{meter}")
    if stated is None:
        raise PricingError(f"{service.title} has no {meter!r} meter for {sku}")
    dimension = measure(stated)[1]
    amount = count * units
    if dimension == "hour":
        quantity, unit = amount * hours, "hours"
    elif dimension == "day":
        quantity, unit = amount * hours / 24, "days"
    elif dimension in ("month", "count"):
        quantity, unit = amount * hours / HOURS, "months"
    elif dimension == "GB-hour":
        quantity, unit = amount * hours, "GB-hours"
    else:
        raise PricingError(f"{service.title}: {meter} is billed per {stated}, not by time")
    return charge(
        service,
        region,
        sku,
        meter,
        label=label,
        quantity=quantity,
        unit=unit,
        dimension=dimension,
        kind="fixed",
        assumed=assumed,
    )


def _done(
    ask: Ask, lines: list[PriceLine], sizing: dict[str, Any], rate: str, *services: Service
) -> Price:
    published = max((service.published for service in services), default="")
    return priced(ask, lines, sizing=sizing, rate=rate, source=SOURCE, published=published)


# -- plans: a tier and the meters it bills ---------------------------------------------------


class Fee(BaseModel):
    """One meter a plan bills."""

    label: str
    #: The meter's name in the table; ``{tier}`` is the chosen tier.
    meter: str
    #: Fixed: the sizing key that multiplies it (units, nodes); usage: the quantity.
    key: str = ""
    default: float = 1.0
    usage: bool = False
    #: Usage: the unit the quantity is stated in, and how many of the meter's
    #: own measure one of it is (1e6 for ``1M operations`` against a ``10K`` meter).
    unit: str = ""
    per: float = 1.0
    dimension: str = "count"
    #: Fixed: units included before this meter bills.
    included: float = 0.0
    #: A tier without this meter skips it; a required meter that is missing is an error.
    optional: bool = False


class Plan(BaseModel):
    """A service priced by a tier and the meters that tier bills."""

    service: str
    title: str
    #: The table's sku for a tier: ``{tier}``, or ``Prefix {tier}``.
    sku: str = "{tier}"
    tiers: list[str] = Field(default_factory=list)
    tier_default: str = ""
    fees: list[Fee]
    #: Takes a count and the hours a month it runs.
    runs: bool = True
    note: str = ""
    #: The tiers the note is true of; every tier when empty.
    note_tiers: list[str] = Field(default_factory=list)


def _plan_pricer(plan: Plan) -> Pricer:
    def price(ask: Ask) -> Price:
        service = ask.table.service(plan.service)
        region = where(ask)
        if len(plan.tiers) == 1:
            tier = plan.tiers[0]
        else:
            tier = ask.take(
                "tier",
                plan.tier_default,
                kind=str,
                choices=plan.tiers or skus(service, region, plan.sku),
            )
        sku = plan.sku.format(tier=tier)
        count = ask.count() if plan.runs else 1
        hours = ask.hours() if plan.runs else HOURS
        sizing: dict[str, Any] = {"region": region}
        if len(plan.tiers) != 1:
            sizing["tier"] = tier
        if plan.runs:
            sizing.update(count=count, hours=hours)
        lines: list[PriceLine] = []
        for fee in plan.fees:
            meter = fee.meter.format(tier=tier)
            if not has(service, region, sku, meter):
                if fee.optional:
                    continue
                raise PricingError(f"{ask.name}: {plan.title} {tier} is not sold in {region}")
            value = ask.amount(fee.key, fee.default) if fee.key else 1.0
            if fee.key:
                sizing[fee.key] = value
            if fee.usage:
                if value:
                    lines.append(
                        charge(
                            service,
                            region,
                            sku,
                            meter,
                            label=fee.label,
                            quantity=value,
                            unit=fee.unit,
                            dimension=fee.dimension,
                            per=fee.per,
                            assumed=ask.was_assumed(fee.key),
                        )
                    )
                continue
            units = max(0.0, value - fee.included)
            if units:
                label = fee.label if units == 1 else f"{fee.label} x {units:g}"
                lines.append(
                    run(
                        service,
                        region,
                        sku,
                        meter,
                        label=label,
                        count=count,
                        hours=hours,
                        units=units,
                        assumed=ask.was_assumed(fee.key, "tier", "count", "hours"),
                    )
                )
        named = plan.title if len(plan.tiers) == 1 else f"{plan.title}, {tier}"
        noted = plan.note and (not plan.note_tiers or tier in plan.note_tiers)
        rate = f"{named}, pay as you go" + (f"; {plan.note}" if noted else "")
        return _done(ask, lines, sizing, rate, service)

    return price


def _usage(label: str, meter: str, key: str, default: float, unit: str, **more: Any) -> Fee:
    return Fee(label=label, meter=meter, key=key, default=default, unit=unit, usage=True, **more)


_MILLION = {"per": 1e6, "dimension": "count"}
_THOUSAND = {"per": 1e3, "dimension": "count"}
_GB = {"dimension": "GB"}

#: The plans, by pricer name.
PLANS: dict[str, Plan] = {
    "keyvault": Plan(
        service="keyvault",
        title="Key Vault",
        tiers=["Standard", "Premium"],
        tier_default="Standard",
        runs=False,
        fees=[
            _usage(
                "Operations", "Operations", "operations_millions", 1, "1M operations", **_MILLION
            ),
            Fee(
                label="HSM-protected keys",
                meter="Premium HSM-protected RSA 2048-bit key",
                key="hsm_keys",
                default=0,
                optional=True,
            ),
        ],
        note="secrets and software keys are billed per operation",
    ),
    "dedicated-hsm": Plan(
        service="keyvault",
        title="Azure Dedicated HSM",
        sku="Dedicated HSM {tier}",
        tiers=["Standard"],
        fees=[Fee(label="HSM instance", meter="Standard Instance")],
    ),
    "eventhubs": Plan(
        service="eventhubs",
        title="Event Hubs",
        tiers=["Basic", "Standard", "Premium", "Dedicated"],
        tier_default="Standard",
        fees=[
            Fee(
                label="Throughput units", meter="{tier} Throughput Unit", key="units", optional=True
            ),
            Fee(
                label="Processing units", meter="{tier} Processing Unit", key="units", optional=True
            ),
            Fee(label="Capacity units", meter="{tier} Capacity Unit", key="units", optional=True),
            _usage(
                "Ingress events",
                "{tier} Ingress Events",
                "events_millions",
                10,
                "1M events",
                optional=True,
                **_MILLION,
            ),
        ],
    ),
    "servicebus": Plan(
        service="servicebus",
        title="Service Bus",
        tiers=["Basic", "Standard", "Premium"],
        tier_default="Standard",
        fees=[
            Fee(label="Base unit", meter="{tier} Base Unit", optional=True),
            Fee(label="Messaging units", meter="{tier} Messaging Unit", key="units", optional=True),
            _usage(
                "Messaging operations",
                "{tier} Messaging Operations",
                "operations_millions",
                1,
                "1M operations",
                optional=True,
                **_MILLION,
            ),
        ],
        note="Standard's first 13M operations a month are free",
        note_tiers=["Standard"],
    ),
    "relay": Plan(
        service="servicebus",
        title="Azure Relay, Hybrid Connections",
        tiers=["Hybrid Connections"],
        fees=[
            Fee(label="Listeners", meter="Hybrid Connections Listener Unit", key="listeners"),
            _usage("Data transfer", "Hybrid Connections Data Transfer", "data_gb", 1, "GB", **_GB),
        ],
    ),
    "eventgrid": Plan(
        service="eventgrid",
        title="Event Grid",
        tiers=["Standard"],
        runs=False,
        fees=[
            _usage(
                "Operations",
                "Standard Operations",
                "operations_millions",
                1,
                "1M operations",
                **_MILLION,
            )
        ],
        note="the first 100,000 operations a month are free",
    ),
    "apim": Plan(
        service="apim",
        title="API Management",
        tiers=[
            "Consumption",
            "Developer",
            "Basic",
            "Standard",
            "Premium",
            "Isolated",
            "Basic v2",
            "Standard v2",
            "Premium v2",
        ],
        tier_default="Developer",
        fees=[
            Fee(label="Units", meter="{tier} Unit", key="units", optional=True),
            _usage(
                "API calls",
                "{tier} Calls",
                "calls_millions",
                1,
                "1M calls",
                optional=True,
                **_MILLION,
            ),
        ],
    ),
    "loganalytics": Plan(
        service="loganalytics",
        title="Log Analytics, Analytics Logs",
        tiers=["Analytics Logs"],
        runs=False,
        fees=[
            _usage(
                "Data ingested", "Analytics Logs Data Ingestion", "ingestion_gb", 10, "GB", **_GB
            ),
            Fee(
                label="Data retained past the included days",
                meter="Analytics Logs Data Retention",
                key="retained_gb",
                default=0,
                usage=True,
                unit="GB-month",
                dimension="GB-month",
            ),
        ],
        note="the first 5 GB ingested a month are free",
    ),
    "appinsights": Plan(
        service="loganalytics",
        title="Application Insights (workspace-based), Analytics Logs",
        tiers=["Analytics Logs"],
        runs=False,
        fees=[
            _usage(
                "Telemetry ingested",
                "Analytics Logs Data Ingestion",
                "ingestion_gb",
                5,
                "GB",
                **_GB,
            )
        ],
        note="billed as its Log Analytics workspace's ingestion; the first 5 GB a month are free",
    ),
    "sentinel": Plan(
        service="sentinel",
        title="Microsoft Sentinel",
        tiers=["Pay-as-you-go"],
        runs=False,
        fees=[_usage("Data analyzed", "Pay-as-you-go Analysis", "ingestion_gb", 10, "GB", **_GB)],
    ),
    "signalr": Plan(
        service="signalr",
        title="Azure SignalR Service",
        tiers=["Standard", "Premium"],
        tier_default="Standard",
        fees=[
            Fee(label="Units", meter="{tier} Unit", key="units"),
            _usage(
                "Messages past the included",
                "{tier} Message",
                "extra_messages_millions",
                0,
                "1M messages",
                **_MILLION,
            ),
        ],
        note="each unit includes 1M messages a day",
    ),
    "webpubsub": Plan(
        service="webpubsub",
        title="Azure Web PubSub",
        tiers=["Standard", "Premium"],
        tier_default="Standard",
        fees=[
            Fee(label="Units", meter="{tier} Unit", key="units"),
            _usage(
                "Messages past the included",
                "{tier} Message",
                "extra_messages_millions",
                0,
                "1M messages",
                **_MILLION,
            ),
        ],
        note="each unit includes 1M messages a day",
    ),
    "search": Plan(
        service="search",
        title="Azure AI Search",
        tiers=[
            "Basic",
            "Standard S1",
            "Standard S2",
            "Standard S3",
            "Storage Optimized L1",
            "Storage Optimized L2",
        ],
        tier_default="Basic",
        fees=[Fee(label="Search units", meter="{tier} Unit", key="search_units")],
        note="search units are replicas x partitions",
    ),
    "notificationhubs": Plan(
        service="notificationhubs",
        title="Notification Hubs",
        tiers=["Free", "Basic", "Standard"],
        tier_default="Basic",
        fees=[
            Fee(label="Namespace", meter="{tier} Unit"),
            _usage(
                "Pushes",
                "{tier} Pushes",
                "pushes_millions",
                1,
                "1M pushes",
                optional=True,
                **_MILLION,
            ),
        ],
    ),
    "iothub": Plan(
        service="iothub",
        title="IoT Hub",
        tiers=["Free", "B1", "B2", "B3", "S1", "S2", "S3"],
        tier_default="S1",
        fees=[Fee(label="Units", meter="{tier} Unit", key="units")],
    ),
    "dps": Plan(
        service="iothub",
        title="IoT Hub Device Provisioning Service",
        sku="DPS {tier}",
        tiers=["S1"],
        runs=False,
        fees=[
            _usage(
                "Operations",
                "S1 Operations",
                "operations_thousands",
                1,
                "1K operations",
                **_THOUSAND,
            )
        ],
    ),
    "streamanalytics": Plan(
        service="streamanalytics",
        title="Stream Analytics",
        tiers=["Standard", "Standard V2", "Dedicated", "Dedicated V2"],
        tier_default="Standard V2",
        fees=[
            Fee(
                label="Streaming units",
                meter="{tier} Streaming Unit",
                key="streaming_units",
                optional=True,
            ),
            Fee(
                label="Streaming units",
                meter="{tier} Streaming Unit/Job",
                key="streaming_units",
                optional=True,
            ),
        ],
    ),
    "appconfig": Plan(
        service="appconfig",
        title="App Configuration",
        tiers=["Free", "Developer", "Standard", "Premium"],
        tier_default="Standard",
        fees=[
            Fee(label="Store", meter="{tier} Instance"),
            Fee(
                label="Replicas",
                meter="{tier} Replica Instance",
                key="replicas",
                default=0,
                optional=True,
            ),
        ],
    ),
    "netapp": Plan(
        service="netapp",
        title="Azure NetApp Files",
        tiers=["Standard", "Premium", "Ultra", "Flexible Service Level"],
        tier_default="Standard",
        fees=[
            Fee(
                label="Capacity pool, GiB",
                meter="{tier} Capacity",
                key="capacity_gib",
                default=1024,
            )
        ],
        note="billed on the pool's provisioned size",
    ),
    "powerbi": Plan(
        service="powerbi",
        title="Power BI Embedded",
        tiers=["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"],
        tier_default="A1",
        fees=[Fee(label="Node", meter="{tier} Node")],
    ),
    "analysisservices": Plan(
        service="analysisservices",
        title="Azure Analysis Services",
        tiers=["Developer", "B1", "B2", "S0", "S1", "S2", "S4", "S8", "S9", "S8 v2", "S9 v2"],
        tier_default="S0",
        fees=[Fee(label="Server", meter="{tier}")],
    ),
    "grafana": Plan(
        service="grafana",
        title="Azure Managed Grafana",
        tiers=["Essential", "Standard"],
        tier_default="Standard",
        fees=[
            Fee(label="Instance", meter="{tier} Node", optional=True),
            Fee(label="Active users", meter="{tier} User", key="users"),
        ],
    ),
    "entrads": Plan(
        service="entrads",
        title="Microsoft Entra Domain Services",
        tiers=["Standard", "Enterprise", "Premium"],
        tier_default="Standard",
        fees=[Fee(label="Managed domain", meter="{tier} User Forest")],
    ),
    "confidentialledger": Plan(
        service="confidentialledger",
        title="Azure confidential ledger",
        tiers=["Standard"],
        fees=[Fee(label="Ledger", meter="Standard Instance")],
    ),
    "digitaltwins": Plan(
        service="digitaltwins",
        title="Azure Digital Twins",
        tiers=["Standard"],
        runs=False,
        fees=[
            _usage(
                "Messages", "Standard Message", "messages_millions", 1, "1M messages", **_MILLION
            ),
            _usage(
                "Operations",
                "Standard Operations",
                "operations_millions",
                1,
                "1M operations",
                **_MILLION,
            ),
            _usage(
                "Query units",
                "Standard Query Units",
                "query_units_millions",
                1,
                "1M query units",
                **_MILLION,
            ),
        ],
    ),
    "iotcentral": Plan(
        service="iotcentral",
        title="IoT Central",
        sku="Standard",
        tiers=["Tier 0", "Tier 1", "Tier 2"],
        tier_default="Tier 1",
        fees=[Fee(label="Devices", meter="Standard {tier}", key="devices", default=10)],
        note="two devices per application are free",
    ),
    "loadtesting": Plan(
        service="apptesting",
        title="Azure Load Testing",
        tiers=["JMeter"],
        fees=[
            Fee(label="Load testing resource", meter="JMeter Load Testing Resource"),
            _usage(
                "Virtual user hours past the included",
                "JMeter Virtual User Additional Usage",
                "extra_virtual_user_hours",
                0,
                "virtual user hours",
                dimension="hour",
            ),
        ],
    ),
    "botservice": Plan(
        service="botservice",
        title="Azure Bot Service",
        tiers=["S1"],
        runs=False,
        fees=[
            _usage(
                "Premium channel messages",
                "S1 Premium Channel Messages",
                "premium_messages_thousands",
                10,
                "1K messages",
                **_THOUSAND,
            )
        ],
        note="standard channels are free",
    ),
    "firewall": Plan(
        service="firewall",
        title="Azure Firewall",
        tiers=["Basic", "Standard", "Premium"],
        tier_default="Standard",
        fees=[
            Fee(label="Deployment", meter="{tier} Deployment"),
            _usage("Data processed", "{tier} Data Processed", "data_gb", 100, "GB", **_GB),
        ],
    ),
    "nat": Plan(
        service="nat",
        title="NAT Gateway",
        tiers=["Standard"],
        fees=[
            Fee(label="Gateway", meter="Standard Gateway"),
            _usage("Data processed", "Standard Data Processed", "data_gb", 100, "GB", **_GB),
        ],
        note="its public IPs bill apart",
    ),
    "bastion": Plan(
        service="bastion",
        title="Azure Bastion",
        tiers=["Basic", "Standard", "Premium"],
        tier_default="Basic",
        fees=[
            Fee(label="Gateway", meter="{tier} Gateway"),
            Fee(
                label="Scale units past the included 2",
                meter="{tier} Additional Gateway",
                key="scale_units",
                default=2,
                included=2,
                optional=True,
            ),
            _usage("Data out", "{tier} Data Transfer Out", "egress_gb", 10, "GB", **_GB),
        ],
        note="the first 5 GB out a month are free",
    ),
    "privateendpoint": Plan(
        service="network",
        title="Private Endpoint",
        sku="PrivateLink {tier}",
        tiers=["Standard"],
        fees=[
            Fee(label="Endpoint", meter="Standard Private Endpoint"),
            _usage(
                "Data processed in",
                "Standard Data Processed - Ingress",
                "ingress_gb",
                50,
                "GB",
                **_GB,
            ),
            _usage(
                "Data processed out",
                "Standard Data Processed - Egress",
                "egress_gb",
                50,
                "GB",
                **_GB,
            ),
        ],
    ),
    "virtualwanhub": Plan(
        service="virtualwan",
        title="Virtual WAN hub",
        tiers=["Standard Hub"],
        fees=[
            Fee(label="Hub", meter="Standard Hub Unit"),
            _usage("Data processed", "Standard Hub Data Processed", "data_gb", 100, "GB", **_GB),
        ],
    ),
    "routeserver": Plan(
        service="routeserver",
        title="Azure Route Server",
        tiers=["Basic"],
        fees=[Fee(label="Route server", meter="Basic Gateway")],
    ),
    "privateresolver": Plan(
        service="dns",
        title="Azure DNS Private Resolver",
        tiers=["Private Resolver"],
        fees=[
            Fee(
                label="Inbound endpoints",
                meter="Private Resolver Inbound Endpoint",
                key="inbound_endpoints",
            ),
            Fee(
                label="Outbound endpoints",
                meter="Private Resolver Outbound Endpoint",
                key="outbound_endpoints",
            ),
            Fee(
                label="Forwarding rulesets",
                meter="Private Resolver DNS Forwarding Ruleset",
                key="rulesets",
                default=0,
            ),
        ],
    ),
    "trafficmanager": Plan(
        service="trafficmanager",
        title="Traffic Manager",
        tiers=["Azure Endpoint"],
        runs=False,
        fees=[
            _usage("DNS queries", "DNS Queries", "queries_millions", 1, "1M queries", **_MILLION),
            Fee(
                label="Endpoint health checks",
                meter="Azure Endpoint Health Checks",
                key="endpoints",
                default=2,
            ),
        ],
    ),
}


# -- virtual machines ----------------------------------------------------------------------


def _vm_key(size: str) -> str:
    """A size as the table keys it: ``Standard_D2s_v5`` -> ``D2s_v5``."""
    name = size.strip()
    return name[len("Standard_") :] if name.lower().startswith("standard_") else name


def _vm_name(key: str) -> str:
    return key if key.startswith("Basic_") else f"Standard_{key}"


def _vm_size(service: Service, region: str, os_name: str, given: str) -> str:
    """The table key for a size, matched without regard to case."""
    key = _vm_key(given)
    for size in service.choices(region, os_name):
        if size.lower() == key.lower():
            return size
    return key


def _vm(
    ask: Ask,
    region: str,
    *,
    size_key: str = "size",
    os_key: str = "os",
    count_key: str = "count",
    default_size: str = "Standard_D2s_v5",
    default_count: int = 1,
    hours: float,
    label: str = "",
) -> tuple[PriceLine, str, Service, dict[str, Any]]:
    """The VM line for a size, an operating system and a count."""
    service = ask.table.service("vm")
    os_name = ask.take(os_key, "Linux", kind=str, choices=("Linux", "Windows"))
    key = _vm_size(service, region, os_name, ask.take(size_key, default_size, kind=str))
    size = _vm_name(key)
    count = ask.count(count_key, default_count)
    rate = service.rate(region, os_name, key)
    item = line(
        f"{label}{size}, {os_name}",
        count * hours,
        "hours",
        rate,
        kind="fixed",
        assumed=ask.was_assumed(size_key, os_key, count_key, "hours"),
    )
    info = service.describe("size", key)
    sizing = {size_key: size, os_key: os_name, count_key: count}
    return item, f"{size} {os_name}" + (f" ({info})" if info else ""), service, sizing


def price_vm(ask: Ask) -> Price:
    """Virtual machines: a size, its operating system, a count and the hours each runs."""
    region = where(ask)
    hours = ask.hours()
    item, what, service, sizing = _vm(ask, region, hours=hours)
    rate = f"Virtual machine, pay as you go, {what}; disks and data out bill apart"
    return _done(ask, [item], {"region": region, **sizing, "hours": hours}, rate, service)


def _vcpus(service: Service, size: str) -> float:
    match = re.match(r"(\d+(?:\.\d+)?) vCPU", service.describe("size", size))
    if match is None:
        raise PricingError(f"the price table does not say how many vCPUs {size} has")
    return float(match.group(1))


#: AKS Automatic bills a surcharge per vCPU-hour by VM family.
_AUTOMATIC_FAMILY = (
    (r"^Standard_(DC|EC)", "Confidential Compute"),
    (r"^Standard_N", "GPU Accelerated"),
    (r"^Standard_H", "High Performance Compute"),
    (r"^Standard_L", "Storage Optimized"),
    (r"^Standard_F", "Compute Optimized"),
    (r"^Standard_(E|M)", "Memory Optimized"),
    (r"^Standard_", "General Purpose"),
)


def price_aks(ask: Ask, default_tier: str = "Free") -> Price:
    """AKS: the cluster's tier fee and its node pool, priced as its VMs."""
    service = ask.table.service("aks")
    region = where(ask)
    tier = ask.take(
        "tier", default_tier, kind=str, choices=("Free", "Standard", "Premium", "Automatic")
    )
    clusters = ask.count()
    hours = ask.hours()
    lines: list[PriceLine] = []
    fee = {
        "Standard": ("Standard", "Standard Uptime SLA"),
        "Premium": ("Standard", "Standard Long Term Support"),
        "Automatic": ("Automatic", "Automatic Hosted Control Plane"),
    }.get(tier)
    if fee is not None:
        lines.append(
            run(
                service,
                region,
                *fee,
                label=f"{tier} tier cluster",
                count=clusters,
                hours=hours,
                assumed=ask.was_assumed("tier", "count", "hours"),
            )
        )
    node, what, vm, sizing = _vm(
        ask,
        region,
        size_key="node_size",
        os_key="node_os",
        count_key="nodes",
        default_count=3,
        hours=hours * clusters,
        label="Nodes, ",
    )
    nodes = sizing["nodes"]
    lines.append(node.model_copy(update={"label": f"{nodes} x {node.label}"}))
    if tier == "Automatic":
        family = next(
            name for pattern, name in _AUTOMATIC_FAMILY if re.match(pattern, sizing["node_size"])
        )
        vcpus = _vcpus(vm, _vm_key(sizing["node_size"]))
        lines.append(
            charge(
                service,
                region,
                "Automatic",
                f"Automatic {family}",
                label=f"Automatic surcharge, {family}, vCPU-hours",
                quantity=vcpus * nodes * hours * clusters,
                unit="vCPU-hours",
                dimension="hour",
                kind="fixed",
                assumed=node.assumed,
            )
        )
    rate = f"AKS {tier} tier; nodes {what}, pay as you go"
    return _done(
        ask,
        lines,
        {"region": region, "tier": tier, "count": clusters, "hours": hours, **sizing},
        rate,
        service,
        vm,
    )


# -- managed disks -------------------------------------------------------------------------

#: The size of each disk tier, in GiB (the managed disks documentation).
_DISK_GIB = {
    1: 4, 2: 8, 3: 16, 4: 32, 6: 64, 10: 128, 15: 256, 20: 512, 30: 1024, 40: 2048,
    50: 4096, 60: 8192, 70: 16384, 80: 32767,
}  # fmt: skip
_DISK_KINDS = {
    "Standard HDD": "S",
    "Standard SSD": "E",
    "Premium SSD": "P",
    "Premium SSD v2": "PremiumV2",
    "Ultra": "Ultra",
}


def price_disk(ask: Ask) -> Price:
    """Managed disks: a tier (P10, E10, S10) or a size that picks the smallest
    tier that holds it; Premium SSD v2 and Ultra by GiB, IOPS and MB/s."""
    service = ask.table.service("disks")
    region = where(ask)
    kind = ask.take("type", "Premium SSD", kind=str, choices=list(_DISK_KINDS))
    redundancy = ask.take("redundancy", "LRS", kind=str, choices=("LRS", "ZRS"))
    count = ask.count()
    hours = ask.hours()
    sizing: dict[str, Any] = {"region": region, "type": kind, "redundancy": redundancy}
    letter = _DISK_KINDS[kind]
    lines: list[PriceLine] = []
    if letter in ("PremiumV2", "Ultra"):
        sku = f"{letter} {redundancy}"
        gib = ask.amount("size_gb", 128)
        iops = ask.amount("iops", 3000)
        throughput = ask.amount("throughput_mbps", 125)
        for meter, label, amount, key in (
            ("capacity", "Capacity, GiB-hours", gib, "size_gb"),
            ("iops", "IOPS-hours", iops, "iops"),
            ("throughput", "MB/s-hours", throughput, "throughput_mbps"),
        ):
            stated = service.info.get("unit", {}).get(f"{sku}|{meter}", "")
            dimension = measure(stated)[1] if stated else "GB-hour"
            lines.append(
                charge(
                    service,
                    region,
                    sku,
                    meter,
                    label=label,
                    quantity=amount * count * hours,
                    unit=label.rsplit(", ", 1)[-1] if ", " in label else label,
                    dimension=dimension,
                    kind="fixed",
                    assumed=ask.was_assumed(key, "count", "hours"),
                )
            )
        sizing.update(size_gb=gib, iops=iops, throughput_mbps=throughput)
        what = f"{kind} {redundancy}, {gib:g} GiB, {iops:g} IOPS, {throughput:g} MB/s"
    else:
        size: float
        if ask.sizing.get("tier") not in (None, ""):
            tier = str(ask.take("tier", kind=str)).strip().upper()
            if not re.fullmatch(rf"{letter}\d+", tier):
                raise PricingError(f"{ask.name}: a {kind} disk tier is {letter}<n>, not {tier!r}")
            size = _DISK_GIB.get(int(tier[1:]), 0)
            sizing["tier"] = tier
        else:
            # a size picks the tier: the tier is not a default of its own
            ask.taken.add("tier")
            size = ask.amount("size_gb", 128)
            fits = [number for number, gib in sorted(_DISK_GIB.items()) if gib >= size]
            if not fits:
                raise PricingError(f"{ask.name}: no {kind} disk holds {size:g} GiB")
            sizing["size_gb"] = size
            tier = f"{letter}{fits[0]}"
            # the smallest tiers are sold only as Premium and Standard SSD
            while not has(service, region, f"{tier} {redundancy}", "disk") and fits[1:]:
                fits = fits[1:]
                tier = f"{letter}{fits[0]}"
            sizing["tier"] = tier
        lines.append(
            run(
                service,
                region,
                f"{tier} {redundancy}",
                "disk",
                label=f"{tier} {redundancy} disk",
                count=count,
                hours=hours,
                assumed=ask.was_assumed("tier", "size_gb", "type", "count", "hours"),
            )
        )
        what = f"{kind} {tier} {redundancy}" + (f" ({size:g} GiB)" if size else "")
    sizing.update(count=count, hours=hours)
    rate = f"Managed disk, {what}; transactions and snapshots bill apart"
    return _done(ask, lines, sizing, rate, service)


# -- storage accounts ----------------------------------------------------------------------


def _storage_redundancy(ask: Ask, service: Service, region: str, pattern: str) -> str:
    return ask.take(
        "redundancy", "LRS", kind=str, choices=skus(service, region, pattern) or ["LRS"]
    )


def price_blob(ask: Ask) -> Price:
    """Blob storage: GB stored a month by access tier and redundancy, and the
    write and read operations."""
    service = ask.table.service("storage")
    region = where(ask)
    tier = ask.take("tier", "Hot", kind=str, choices=("Hot", "Cool", "Cold", "Archive"))
    redundancy = _storage_redundancy(ask, service, region, f"Blob {tier} {{tier}}")
    sku = f"Blob {tier} {redundancy}"
    stored = ask.amount("storage_gb", 100)
    writes = ask.amount("write_operations_millions", 1)
    reads = ask.amount("read_operations_millions", 1)
    lines = [
        charge(
            service,
            region,
            sku,
            "stored",
            label="Data stored",
            quantity=stored,
            unit="GB-month",
            dimension="GB-month",
            assumed=ask.was_assumed("storage_gb"),
        )
    ]
    for meter, label, amount, key in (
        ("write", "Write operations", writes, "write_operations_millions"),
        ("read", "Read operations", reads, "read_operations_millions"),
    ):
        if amount:
            lines.append(
                charge(
                    service,
                    region,
                    operations_sku(service, region, sku, meter),
                    meter,
                    label=label,
                    quantity=amount,
                    unit="1M operations",
                    per=1e6,
                    dimension="count",
                    assumed=ask.was_assumed(key),
                )
            )
    sizing = {
        "region": region,
        "tier": tier,
        "redundancy": redundancy,
        "storage_gb": stored,
        "write_operations_millions": writes,
        "read_operations_millions": reads,
    }
    rate = f"Blob storage (general purpose v2), {tier} {redundancy}; data out bills apart"
    return _done(ask, lines, sizing, rate, service)


def price_files(ask: Ask) -> Price:
    """Azure Files: standard shares by GB stored and operations, premium by GB provisioned."""
    service = ask.table.service("storage")
    region = where(ask)
    tier = ask.take(
        "tier",
        "Transaction optimized",
        kind=str,
        choices=("Transaction optimized", "Hot", "Cool", "Premium"),
    )
    table_tier = {"Transaction optimized": "Standard"}.get(tier, tier)
    redundancy = _storage_redundancy(ask, service, region, f"Files {table_tier} {{tier}}")
    sku = f"Files {table_tier} {redundancy}"
    sizing: dict[str, Any] = {"region": region, "tier": tier, "redundancy": redundancy}
    if tier == "Premium":
        size = ask.amount("provisioned_gb", 100)
        sizing["provisioned_gb"] = size
        lines = [
            charge(
                service,
                region,
                sku,
                "provisioned",
                label="Provisioned share",
                quantity=size,
                unit="GB-month",
                dimension="GB-month",
                kind="fixed",
                assumed=ask.was_assumed("provisioned_gb"),
            )
        ]
    else:
        stored = ask.amount("storage_gb", 100)
        sizing["storage_gb"] = stored
        lines = [
            charge(
                service,
                region,
                sku,
                "stored",
                label="Data stored",
                quantity=stored,
                unit="GB-month",
                dimension="GB-month",
                assumed=ask.was_assumed("storage_gb"),
            )
        ]
        for meter, label, key in (
            ("write", "Write operations", "write_operations_millions"),
            ("read", "Read operations", "read_operations_millions"),
            ("list", "List operations", "list_operations_millions"),
        ):
            amount = ask.amount(key, 1 if meter != "list" else 0.1)
            sizing[key] = amount
            billed = operations_sku(service, region, sku, meter)
            if amount and has(service, region, billed, meter):
                lines.append(
                    charge(
                        service,
                        region,
                        billed,
                        meter,
                        label=label,
                        quantity=amount,
                        unit="1M operations",
                        per=1e6,
                        dimension="count",
                        assumed=ask.was_assumed(key),
                    )
                )
    return _done(ask, lines, sizing, f"Azure Files, {tier} {redundancy}", service)


def _simple_store(kind: str, title: str) -> Pricer:
    def price(ask: Ask) -> Price:
        service = ask.table.service("storage")
        region = where(ask)
        redundancy = _storage_redundancy(ask, service, region, f"{kind} Standard {{tier}}")
        sku = f"{kind} Standard {redundancy}"
        stored = ask.amount("storage_gb", 10)
        writes = ask.amount("write_operations_millions", 1)
        reads = ask.amount("read_operations_millions", 1)
        lines = [
            charge(
                service,
                region,
                sku,
                "stored",
                label="Data stored",
                quantity=stored,
                unit="GB-month",
                dimension="GB-month",
                assumed=ask.was_assumed("storage_gb"),
            )
        ]
        for meter, label, amount, key in (
            ("write", "Write operations", writes, "write_operations_millions"),
            ("read", "Read operations", reads, "read_operations_millions"),
        ):
            billed = operations_sku(service, region, sku, meter)
            if amount and has(service, region, billed, meter):
                lines.append(
                    charge(
                        service,
                        region,
                        billed,
                        meter,
                        label=label,
                        quantity=amount,
                        unit="1M operations",
                        per=1e6,
                        dimension="count",
                        assumed=ask.was_assumed(key),
                    )
                )
        sizing = {
            "region": region,
            "redundancy": redundancy,
            "storage_gb": stored,
            "write_operations_millions": writes,
            "read_operations_millions": reads,
        }
        return _done(ask, lines, sizing, f"{title}, Standard {redundancy}", service)

    return price


# -- databases -----------------------------------------------------------------------------

_SQL_TIERS = ("General Purpose", "Business Critical", "Hyperscale")


def _sql_vcore(
    ask: Ask, service: Service, region: str, kind: str, tiers: tuple[str, ...], vcores_default: int
) -> tuple[list[PriceLine], dict[str, Any], str]:
    tier = ask.take("tier", "General Purpose", kind=str, choices=tiers)
    hardware = ask.take(
        "hardware",
        "Gen5",
        kind=str,
        choices=skus(service, region, f"{kind} {tier} {{tier}}") or ["Gen5"],
    )
    vcores = ask.count("vcores", vcores_default)
    license_ = ask.take("license", "included", kind=str, choices=("included", "ahb"))
    zone = ask.take("zone_redundant", "no", kind=str, choices=("no", "yes"))
    count = ask.count()
    hours = ask.hours()
    stored = ask.amount("storage_gb", 32)
    guess = ask.was_assumed("tier", "hardware", "vcores", "count", "hours")
    lines = [
        run(
            service,
            region,
            f"{kind} {tier} {hardware}",
            "vcore",
            label=f"Compute, {vcores} vCores",
            count=count,
            hours=hours,
            units=vcores,
            assumed=guess,
        )
    ]
    if license_ == "included":
        lines.append(
            run(
                service,
                region,
                f"{kind} {tier} License",
                "vcore",
                label=f"SQL license, {vcores} vCores",
                count=count,
                hours=hours,
                units=vcores,
                assumed=guess or ask.was_assumed("license"),
            )
        )
    if zone == "yes" and has(service, region, f"{kind} {tier} {hardware}", "zone-redundancy"):
        lines.append(
            run(
                service,
                region,
                f"{kind} {tier} {hardware}",
                "zone-redundancy",
                label=f"Zone redundancy, {vcores} vCores",
                count=count,
                hours=hours,
                units=vcores,
            )
        )
    storage_sku = f"{kind} {tier} Storage" + (
        " Zone Redundancy"
        if zone == "yes" and has(service, region, f"{kind} {tier} Storage Zone Redundancy", "gb")
        else ""
    )
    lines.append(
        charge(
            service,
            region,
            storage_sku,
            "gb",
            label="Storage",
            quantity=stored * count,
            unit="GB-month",
            dimension="GB-month",
            kind="fixed",
            assumed=ask.was_assumed("storage_gb", "count"),
        )
    )
    sizing = {
        "region": region,
        "tier": tier,
        "hardware": hardware,
        "vcores": vcores,
        "license": license_,
        "zone_redundant": zone,
        "storage_gb": stored,
        "count": count,
        "hours": hours,
    }
    what = f"{tier}, {hardware}, {vcores} vCores, license {'included' if license_ == 'included' else 'via Azure Hybrid Benefit'}"
    return lines, sizing, what


def price_sql_database(ask: Ask) -> Price:
    """Azure SQL Database: provisioned vCores (General Purpose, Business
    Critical, Hyperscale), serverless vCore-hours, or a DTU size."""
    service = ask.table.service("sql")
    region = where(ask)
    model = ask.take("model", "vcore", kind=str, choices=("vcore", "serverless", "dtu"))
    if model == "dtu":
        size = ask.take(
            "sku",
            "S0",
            kind=str,
            choices=sorted(service.choices(region, "DTU") or service.choices("global", "DTU")),
        )
        count = ask.count()
        hours = ask.hours()
        lines = [
            run(
                service,
                region,
                "DTU",
                size,
                label=f"Database, {size}",
                count=count,
                hours=hours,
                assumed=ask.was_assumed("sku", "count", "hours"),
            )
        ]
        sizing = {"region": region, "model": model, "sku": size, "count": count, "hours": hours}
        rate = f"Azure SQL Database, DTU {size}, storage included up to the size's maximum"
        return _done(ask, lines, sizing, rate, service)
    if model == "serverless":
        used = ask.amount("vcore_hours", 730)
        stored = ask.amount("storage_gb", 32)
        lines = [
            charge(
                service,
                region,
                "DB Serverless General Purpose Gen5",
                "vcore",
                label="Compute used, vCore-hours",
                quantity=used,
                unit="vCore-hours",
                dimension="hour",
                assumed=ask.was_assumed("vcore_hours"),
            ),
            charge(
                service,
                region,
                "DB General Purpose Storage",
                "gb",
                label="Storage",
                quantity=stored,
                unit="GB-month",
                dimension="GB-month",
                kind="fixed",
                assumed=ask.was_assumed("storage_gb"),
            ),
        ]
        sizing = {"region": region, "model": model, "vcore_hours": used, "storage_gb": stored}
        rate = "Azure SQL Database serverless, General Purpose Gen5, billed per vCore-second used, license included"
        return _done(ask, lines, sizing, rate, service)
    lines, sizing, what = _sql_vcore(ask, service, region, "DB", _SQL_TIERS, 2)
    sizing["model"] = model
    return _done(ask, lines, sizing, f"Azure SQL Database, {what}", service)


def price_sql_managed_instance(ask: Ask) -> Price:
    """Azure SQL Managed Instance: vCores by tier and hardware, the SQL license, storage."""
    service = ask.table.service("sql")
    region = where(ask)
    lines, sizing, what = _sql_vcore(ask, service, region, "MI", _SQL_TIERS[:2], 4)
    rate = f"Azure SQL Managed Instance, {what}; storage billed on the size reserved"
    return _done(ask, lines, sizing, rate, service)


_FLEX_SKU = re.compile(r"^(?:Standard_)?([DE])(\d+)([a-z]*)_v(\d+)$", re.IGNORECASE)
_BURSTABLE = re.compile(r"^(?:Standard_)?(B\d+m?s)$", re.IGNORECASE)


def _flexible(engine: str, title: str) -> Pricer:
    def price(ask: Ask) -> Price:
        service = ask.table.service("flexible")
        region = where(ask)
        given = ask.take("sku", "Standard_D2ds_v5", kind=str).strip()
        ha = ask.take("high_availability", "no", kind=str, choices=("no", "yes"))
        count = ask.count()
        hours = ask.hours()
        stored = ask.amount("storage_gb", 32)
        copies = 2 if ha == "yes" else 1
        guess = ask.was_assumed("sku", "count", "hours")
        if burst := _BURSTABLE.match(given):
            size = burst.group(1).lower()
            compute = run(
                service,
                region,
                f"{engine} burstable",
                size,
                label=f"Compute, {burst.group(1)}",
                count=count * copies,
                hours=hours,
                assumed=guess,
            )
        elif match := _FLEX_SKU.match(given):
            letter, vcores, suffix, version = match.groups()
            series = f"{letter}{suffix}v{version}".lower()
            compute = run(
                service,
                region,
                f"{engine} {series}",
                "vcore",
                label=f"Compute, {given}, {vcores} vCores",
                count=count * copies,
                hours=hours,
                units=int(vcores),
                assumed=guess,
            )
        else:
            raise PricingError(
                f"{ask.name}: {given!r} is not a flexible server size (like Standard_D2ds_v5 or Standard_B1ms)"
            )
        storage = charge(
            service,
            region,
            f"{engine} storage",
            "gb",
            label="Storage",
            quantity=stored * count * copies,
            unit="GB-month",
            dimension="GB-month",
            kind="fixed",
            assumed=ask.was_assumed("storage_gb", "count"),
        )
        sizing = {
            "region": region,
            "sku": given,
            "high_availability": ha,
            "storage_gb": stored,
            "count": count,
            "hours": hours,
        }
        rate = f"{title}, flexible server, {given}" + (
            ", zone-redundant standby" if ha == "yes" else ""
        )
        return _done(ask, [compute, storage], sizing, rate, service)

    return price


def price_cosmos(ask: Ask) -> Price:
    """Cosmos DB: provisioned RU/s a region (single or multi-region writes)
    or serverless request units, and GB stored."""
    service = ask.table.service("cosmos")
    region = where(ask)
    mode = ask.take("mode", "provisioned", kind=str, choices=("provisioned", "serverless"))
    stored = ask.amount("storage_gb", 10)
    lines: list[PriceLine] = []
    sizing: dict[str, Any] = {"region": region, "mode": mode, "storage_gb": stored}
    if mode == "serverless":
        used = ask.amount("request_units_millions", 10)
        sizing["request_units_millions"] = used
        lines.append(
            charge(
                service,
                region,
                "Serverless",
                "ru-million",
                label="Request units",
                quantity=used,
                unit="1M RUs",
                per=1e6,
                dimension="count",
                assumed=ask.was_assumed("request_units_millions"),
            )
        )
        regions = 1
    else:
        throughput = ask.amount("ru_per_second", 400)
        regions = ask.count("regions")
        writes = ask.take("multi_region_writes", "no", kind=str, choices=("no", "yes"))
        hours = ask.hours()
        sizing.update(
            ru_per_second=throughput, regions=regions, multi_region_writes=writes, hours=hours
        )
        lines.append(
            run(
                service,
                region,
                "Provisioned",
                "ru-multi-write" if writes == "yes" else "ru",
                label=f"Throughput, {throughput:g} RU/s x {regions} region(s), per 100 RU/s",
                count=regions,
                hours=hours,
                units=throughput / 100,
                assumed=ask.was_assumed("ru_per_second", "regions", "hours"),
            )
        )
    lines.append(
        charge(
            service,
            region,
            "Provisioned",
            "gb",
            label="Data stored",
            quantity=stored * regions,
            unit="GB-month",
            dimension="GB-month",
            assumed=ask.was_assumed("storage_gb"),
        )
    )
    rate = f"Azure Cosmos DB, {mode}" + (
        "; autoscale bills 1.5x the RU/s rate" if mode == "provisioned" else ""
    )
    return _done(ask, lines, sizing, rate, service)


_REDIS_DEFAULT = {
    "Basic": "C0",
    "Standard": "C1",
    "Premium": "P1",
    "Enterprise": "E10",
    "Enterprise Flash": "F300",
    "Managed Balanced": "B1",
    "Managed Memory Optimized": "M10",
    "Managed Compute Optimized": "X3",
    "Managed Flash Optimized": "A250",
}


def price_redis(ask: Ask) -> Price:
    """Azure Cache for Redis and Azure Managed Redis: a tier and a size."""
    service = ask.table.service("redis")
    region = where(ask)
    tier = ask.take("tier", "Standard", kind=str, choices=list(_REDIS_DEFAULT))
    size = ask.take(
        "sku",
        _REDIS_DEFAULT[tier],
        kind=str,
        choices=sorted(service.choices(region, tier) or service.choices("global", tier)),
    ).upper()
    count = ask.count()
    hours = ask.hours()
    managed = tier.startswith("Managed")
    nodes = ask.count("nodes", 2) if managed else 1
    item = run(
        service,
        region,
        tier,
        size,
        label=f"{tier} {size}" + (f", {nodes} nodes" if managed else ""),
        count=count,
        hours=hours,
        units=nodes,
        assumed=ask.was_assumed("tier", "sku", "count", "hours", "nodes"),
    )
    sizing = {"region": region, "tier": tier, "sku": size, "count": count, "hours": hours}
    if managed:
        sizing["nodes"] = nodes
    note = "; Azure Managed Redis bills each node, two with high availability" if managed else ""
    return _done(ask, [item], sizing, f"Azure Cache for Redis, {tier} {size}{note}", service)


# -- app platforms ---------------------------------------------------------------------------


def _app_plan(default_sku: str) -> Pricer:
    def price(ask: Ask) -> Price:
        service = ask.table.service("appservice")
        region = where(ask)
        os_name = ask.take("os", "Linux", kind=str, choices=("Linux", "Windows"))
        choices = skus(service, region, f"{os_name} {{tier}}")
        given = ask.take("sku", default_sku, kind=str, choices=choices or [default_sku])
        count = ask.count()
        hours = ask.hours()
        item = run(
            service,
            region,
            f"{os_name} {given}",
            "instance",
            label=f"{given} {os_name} instances",
            count=count,
            hours=hours,
            assumed=ask.was_assumed("sku", "os", "count", "hours"),
        )
        sizing = {"region": region, "os": os_name, "sku": given, "count": count, "hours": hours}
        rate = f"App Service plan, {given}, {os_name}; every app on the plan shares it"
        return _done(ask, [item], sizing, rate, service)

    return price


def price_app_service_extra(meter: str, title: str) -> Pricer:
    def price(ask: Ask) -> Price:
        service = ask.table.service("appservice")
        region = where(ask)
        count = ask.count()
        stated = service.info.get("unit", {}).get(f"Extras|{meter}", "")
        # a certificate's meter is per certificate, sold for a year
        dimension = measure(stated)[1] if stated else ""
        if dimension not in ("year", "count"):
            raise PricingError(f"{title} is not billed per year in the price table")
        lines = [
            charge(
                service,
                region,
                "Extras",
                meter,
                label=title,
                quantity=count / 12,
                unit="years",
                dimension=dimension,
                kind="fixed",
                assumed=ask.was_assumed("count"),
            )
        ]
        return _done(
            ask,
            lines,
            {"region": region, "count": count},
            f"{title}, a year's fee spread over 12 months",
            service,
        )

    return price


def price_static_web_app(ask: Ask) -> Price:
    """Static Web Apps: Free, or Standard per app a month and bandwidth past the included 100 GB."""
    service = ask.table.service("appservice")
    region = where(ask)
    tier = ask.take("tier", "Standard", kind=str, choices=("Free", "Standard"))
    count = ask.count()
    egress = ask.amount("egress_gb", 10)
    sizing = {"region": region, "tier": tier, "count": count, "egress_gb": egress}
    if tier == "Free":
        return _done(ask, [], sizing, "Static Web Apps, Free plan", service)
    place = region
    if not has(service, region, "StaticWebApps Standard", "Standard App"):
        # Static Web Apps runs in a few regions; one the element names but
        # Azure does not host it in is priced from East US 2
        place = "eastus2"
    lines = [
        run(
            service,
            place,
            "StaticWebApps Standard",
            "Standard App",
            label="Standard app",
            count=count,
            hours=HOURS,
            assumed=ask.was_assumed("tier", "count"),
        ),
        charge(
            service,
            place,
            "StaticWebApps Standard",
            "Standard Bandwidth Usage",
            label="Bandwidth",
            quantity=egress,
            unit="GB",
            dimension="GB",
            assumed=ask.was_assumed("egress_gb"),
        ),
    ]
    note = "" if place == region else f"; not hosted in {region}, priced in {place}"
    return _done(ask, lines, sizing, f"Static Web Apps, Standard{note}", service)


#: Functions Premium plans: vCPUs and GiB of memory (the Functions documentation).
_ELASTIC_PREMIUM = {"EP1": (1, 3.5), "EP2": (2, 7.0), "EP3": (4, 14.0)}
#: Logic Apps Standard plans: vCPUs and GiB of memory (the Logic Apps documentation).
_WORKFLOW_STANDARD = {"WS1": (1, 3.5), "WS2": (2, 7.0), "WS3": (4, 14.0)}


def _cores_and_memory(
    service: Service,
    region: str,
    sku: str,
    cpu_meter: str,
    memory_meter: str,
    *,
    vcpus: float,
    memory: float,
    count: int,
    hours: float,
    assumed: bool,
) -> list[PriceLine]:
    return [
        charge(
            service,
            region,
            sku,
            cpu_meter,
            label=f"vCPU-hours, {count} x {vcpus:g} vCPU",
            quantity=vcpus * count * hours,
            unit="vCPU-hours",
            dimension="hour",
            kind="fixed",
            assumed=assumed,
        ),
        charge(
            service,
            region,
            sku,
            memory_meter,
            label=f"Memory GiB-hours, {count} x {memory:g} GiB",
            quantity=memory * count * hours,
            unit="GiB-hours",
            dimension="GB-hour",
            kind="fixed",
            assumed=assumed,
        ),
    ]


def price_functions(ask: Ask) -> Price:
    """Azure Functions: Consumption and Flex Consumption by executions and
    GB-seconds (after the monthly free grant), or a Premium plan's instances."""
    service = ask.table.service("functions")
    region = where(ask)
    plan = ask.take("plan", "consumption", kind=str, choices=("consumption", "flex", "premium"))
    sizing: dict[str, Any] = {"region": region, "plan": plan}
    if plan == "premium":
        size = ask.take("sku", "EP1", kind=str, choices=list(_ELASTIC_PREMIUM))
        count = ask.count()
        hours = ask.hours()
        vcpus, memory = _ELASTIC_PREMIUM[size]
        lines = _cores_and_memory(
            service,
            region,
            "Premium",
            "Premium vCPU Duration",
            "Premium Memory Duration",
            vcpus=vcpus,
            memory=memory,
            count=count,
            hours=hours,
            assumed=ask.was_assumed("sku", "count", "hours"),
        )
        sizing.update(sku=size, count=count, hours=hours)
        return _done(
            ask,
            lines,
            sizing,
            f"Azure Functions Premium plan, {size}, always-ready instances",
            service,
        )
    executions = ask.amount("executions_millions", 1)
    memory_mb = ask.amount("memory_mb", 128 if plan == "consumption" else 2048)
    duration = ask.amount("duration_ms", 200)
    gb_seconds = executions * 1e6 * duration / 1000 * memory_mb / 1024
    sku, time_meter, count_meter = {
        "consumption": ("Standard", "Standard Execution Time", "Standard Total Executions"),
        "flex": ("On Demand", "On Demand Execution Time", "On Demand Total Executions"),
    }[plan]
    lines = [
        charge(
            service,
            region,
            sku,
            count_meter,
            label="Executions",
            quantity=executions,
            unit="1M executions",
            per=1e6,
            dimension="count",
            assumed=ask.was_assumed("executions_millions"),
        ),
        charge(
            service,
            region,
            sku,
            time_meter,
            label=f"Execution time, {memory_mb:g} MB x {duration:g} ms each",
            quantity=gb_seconds,
            unit="GB-seconds",
            dimension="GB-second",
            assumed=ask.was_assumed("executions_millions", "memory_mb", "duration_ms"),
        ),
    ]
    sizing.update(executions_millions=executions, memory_mb=memory_mb, duration_ms=duration)
    title = "Consumption" if plan == "consumption" else "Flex Consumption, on demand"
    return _done(
        ask, lines, sizing, f"Azure Functions {title}, after the monthly free grant", service
    )


def price_logic_app(ask: Ask) -> Price:
    """Logic Apps: Consumption by actions, or a Standard plan's vCPU and memory."""
    service = ask.table.service("logicapps")
    region = where(ask)
    plan = ask.take("plan", "consumption", kind=str, choices=("consumption", "standard"))
    sizing: dict[str, Any] = {"region": region, "plan": plan}
    if plan == "standard":
        size = ask.take("sku", "WS1", kind=str, choices=list(_WORKFLOW_STANDARD))
        count = ask.count()
        hours = ask.hours()
        vcpus, memory = _WORKFLOW_STANDARD[size]
        lines = _cores_and_memory(
            service,
            region,
            "Standard",
            "Standard vCPU Duration",
            "Standard Memory Duration",
            vcpus=vcpus,
            memory=memory,
            count=count,
            hours=hours,
            assumed=ask.was_assumed("sku", "count", "hours"),
        )
        sizing.update(sku=size, count=count, hours=hours)
        return _done(ask, lines, sizing, f"Logic Apps Standard, {size}", service)
    lines = []
    for meter, label, key, default in (
        ("Consumption Built-in Actions", "Built-in actions", "actions", 100_000),
        (
            "Consumption Standard Connector Actions",
            "Standard connector calls",
            "standard_connector_calls",
            10_000,
        ),
        (
            "Consumption Enterprise Connector Actions",
            "Enterprise connector calls",
            "enterprise_connector_calls",
            0,
        ),
    ):
        amount = ask.amount(key, default)
        sizing[key] = amount
        if amount:
            lines.append(
                charge(
                    service,
                    region,
                    "Consumption",
                    meter,
                    label=label,
                    quantity=amount,
                    unit="actions",
                    dimension="count",
                    assumed=ask.was_assumed(key),
                )
            )
    return _done(ask, lines, sizing, "Logic Apps Consumption, per action", service)


def price_integration_account(ask: Ask) -> Price:
    service = ask.table.service("logicapps")
    region = where(ask)
    tier = ask.take("tier", "Basic", kind=str, choices=("Basic", "Standard", "Premium"))
    count = ask.count()
    hours = ask.hours()
    item = run(
        service,
        region,
        f"Integration Account {tier}",
        f"{tier} Unit",
        label=f"{tier} integration account",
        count=count,
        hours=hours,
        assumed=ask.was_assumed("tier", "count", "hours"),
    )
    sizing = {"region": region, "tier": tier, "count": count, "hours": hours}
    return _done(ask, [item], sizing, f"Logic Apps integration account, {tier}", service)


def price_container_apps(ask: Ask) -> Price:
    """Container Apps: Consumption by vCPU-seconds, GiB-seconds and requests
    (before the monthly free grant), or a Dedicated plan's workload profile."""
    service = ask.table.service("containerapps")
    region = where(ask)
    plan = ask.take("plan", "consumption", kind=str, choices=("consumption", "dedicated"))
    sizing: dict[str, Any] = {"region": region, "plan": plan}
    if plan == "dedicated":
        vcpus = ask.amount("vcpu", 4)
        memory = ask.amount("memory_gib", 16)
        nodes = ask.count("nodes")
        hours = ask.hours()
        guess = ask.was_assumed("vcpu", "memory_gib", "nodes", "hours")
        lines = [
            run(
                service,
                region,
                "Dedicated",
                "Dedicated Plan Management",
                label="Plan management",
                count=1,
                hours=hours,
                assumed=ask.was_assumed("hours"),
            ),
            charge(
                service,
                region,
                "Dedicated",
                "Dedicated vCPU Usage",
                label=f"vCPU-hours, {nodes} x {vcpus:g}",
                quantity=vcpus * nodes * hours,
                unit="vCPU-hours",
                dimension="hour",
                kind="fixed",
                assumed=guess,
            ),
            charge(
                service,
                region,
                "Dedicated",
                "Dedicated Memory Usage",
                label=f"Memory GiB-hours, {nodes} x {memory:g}",
                quantity=memory * nodes * hours,
                unit="GiB-hours",
                dimension="hour",
                kind="fixed",
                assumed=guess,
            ),
        ]
        sizing.update(vcpu=vcpus, memory_gib=memory, nodes=nodes, hours=hours)
        return _done(ask, lines, sizing, "Azure Container Apps, Dedicated plan", service)
    vcpus = ask.amount("vcpu", 0.5)
    memory = ask.amount("memory_gib", 1)
    replicas = ask.amount("replicas", 1)
    active = ask.amount("active_hours", HOURS)
    requests = ask.amount("requests_millions", 1)
    seconds = replicas * active * 3600
    guess = ask.was_assumed("vcpu", "memory_gib", "replicas", "active_hours")
    lines = [
        charge(
            service,
            region,
            "Standard",
            "Standard vCPU Active Usage",
            label=f"vCPU-seconds, {replicas:g} x {vcpus:g} vCPU",
            quantity=vcpus * seconds,
            unit="vCPU-seconds",
            dimension="second",
            assumed=guess,
        ),
        charge(
            service,
            region,
            "Standard",
            "Standard Memory Active Usage",
            label=f"Memory GiB-seconds, {replicas:g} x {memory:g} GiB",
            quantity=memory * seconds,
            unit="GiB-seconds",
            dimension="GB-second",
            assumed=guess,
        ),
    ]
    if requests:
        lines.append(
            charge(
                service,
                region,
                "Standard",
                "Standard Requests",
                label="Requests",
                quantity=requests,
                unit="1M requests",
                per=1e6,
                dimension="count",
                assumed=ask.was_assumed("requests_millions"),
            )
        )
    sizing.update(
        vcpu=vcpus,
        memory_gib=memory,
        replicas=replicas,
        active_hours=active,
        requests_millions=requests,
    )
    return _done(
        ask,
        lines,
        sizing,
        "Azure Container Apps, Consumption, before the monthly free grant",
        service,
    )


def price_container_instances(ask: Ask) -> Price:
    """Container Instances: vCPU and memory for the hours a container group runs."""
    service = ask.table.service("aci")
    region = where(ask)
    os_name = ask.take("os", "Linux", kind=str, choices=("Linux", "Windows"))
    vcpus = ask.amount("vcpu", 1)
    memory = ask.amount("memory_gb", 1.5)
    count = ask.count()
    hours = ask.hours()
    guess = ask.was_assumed("vcpu", "memory_gb", "count", "hours")
    lines = [
        charge(
            service,
            region,
            "Standard",
            "Standard vCPU Duration",
            label=f"vCPU-hours, {count} x {vcpus:g} vCPU",
            quantity=vcpus * count * hours,
            unit="vCPU-hours",
            dimension="hour",
            kind="fixed",
            assumed=guess,
        ),
        charge(
            service,
            region,
            "Standard",
            "Standard Memory Duration",
            label=f"Memory GB-hours, {count} x {memory:g} GB",
            quantity=memory * count * hours,
            unit="GB-hours",
            dimension="GB-hour",
            kind="fixed",
            assumed=guess,
        ),
    ]
    if os_name == "Windows":
        lines.append(
            charge(
                service,
                region,
                "Standard",
                "Standard Windows Software Duration",
                label="Windows software, vCPU-seconds",
                quantity=vcpus * count * hours * 3600,
                unit="vCPU-seconds",
                dimension="second",
                kind="fixed",
                assumed=guess,
            )
        )
    sizing = {
        "region": region,
        "os": os_name,
        "vcpu": vcpus,
        "memory_gb": memory,
        "count": count,
        "hours": hours,
    }
    return _done(ask, lines, sizing, f"Azure Container Instances, {os_name}", service)


#: Storage each registry tier includes, GiB (the Container Registry documentation).
_REGISTRY_INCLUDED = {"Basic": 10, "Standard": 100, "Premium": 500}


def price_container_registry(ask: Ask) -> Price:
    """Container Registry: a tier's daily fee, storage past what it includes, geo-replicas."""
    service = ask.table.service("acr")
    region = where(ask)
    tier = ask.take("tier", "Standard", kind=str, choices=list(_REGISTRY_INCLUDED))
    count = ask.count()
    hours = ask.hours()
    stored = ask.amount("storage_gb", _REGISTRY_INCLUDED[tier])
    replicas = ask.amount("replicas", 0) if tier == "Premium" else 0
    lines = [
        run(
            service,
            region,
            tier,
            f"{tier} Registry Unit",
            label=f"{tier} registry",
            count=count,
            hours=hours,
            assumed=ask.was_assumed("tier", "count", "hours"),
        )
    ]
    extra = max(0.0, stored - _REGISTRY_INCLUDED[tier])
    if extra:
        lines.append(
            charge(
                service,
                region,
                tier,
                "Data Stored",
                label="Storage past the included",
                quantity=extra * count,
                unit="GB-month",
                dimension="GB-month",
                assumed=ask.was_assumed("storage_gb"),
            )
        )
    if replicas:
        lines.append(
            run(
                service,
                region,
                "Premium",
                "Premium Registry Replication Unit",
                label="Geo-replicas",
                count=count,
                hours=hours,
                units=replicas,
            )
        )
    sizing = {"region": region, "tier": tier, "count": count, "hours": hours, "storage_gb": stored}
    if tier == "Premium":
        sizing["replicas"] = replicas
    return _done(ask, lines, sizing, f"Azure Container Registry, {tier}", service)


# -- networking ------------------------------------------------------------------------------


def price_app_gateway(ask: Ask) -> Price:
    """Application Gateway v2: the fixed hourly fee and capacity units; or
    Application Gateway for Containers."""
    service = ask.table.service("appgateway")
    region = where(ask)
    tier = ask.take(
        "tier",
        "Standard_v2",
        kind=str,
        choices=("Basic_v2", "Standard_v2", "WAF_v2", "AGC", "AGC_WAF"),
    )
    count = ask.count()
    hours = ask.hours()
    units = ask.amount("capacity_units", 1)
    guess = ask.was_assumed("tier", "count", "hours")
    sizing: dict[str, Any] = {
        "region": region,
        "tier": tier,
        "count": count,
        "hours": hours,
        "capacity_units": units,
    }
    if tier.startswith("AGC"):
        sku = f"{tier} Standard"
        frontends = ask.amount("frontends", 1)
        associations = ask.amount("associations", 1)
        lines = [
            run(
                service,
                region,
                sku,
                "Standard AGC",
                label="Gateway for Containers",
                count=count,
                hours=hours,
                assumed=guess,
            ),
            run(
                service,
                region,
                sku,
                "Standard Frontend",
                label="Frontends",
                count=count,
                hours=hours,
                units=frontends,
                assumed=ask.was_assumed("frontends"),
            ),
            run(
                service,
                region,
                sku,
                "Standard Association",
                label="Associations",
                count=count,
                hours=hours,
                units=associations,
                assumed=ask.was_assumed("associations"),
            ),
            run(
                service,
                region,
                sku,
                "Standard Capacity Units",
                label="Capacity units",
                count=count,
                hours=hours,
                units=units,
                assumed=ask.was_assumed("capacity_units"),
            ),
        ]
        sizing.update(frontends=frontends, associations=associations)
    else:
        plan = "Basic" if tier == "Basic_v2" else "Standard"
        sku = f"{tier} {plan}"
        lines = [
            run(
                service,
                region,
                sku,
                f"{plan} Fixed Cost",
                label="Gateway, fixed",
                count=count,
                hours=hours,
                assumed=guess,
            ),
            run(
                service,
                region,
                sku,
                f"{plan} Capacity Units",
                label=f"Capacity units x {units:g}",
                count=count,
                hours=hours,
                units=units,
                assumed=ask.was_assumed("capacity_units"),
            ),
        ]
    return _done(ask, lines, sizing, f"Application Gateway {tier}", service)


def price_load_balancer(ask: Ask) -> Price:
    """Load Balancer: rules (the first five in the hourly fee), data processed."""
    service = ask.table.service("loadbalancer")
    region = where(ask)
    tier = ask.take("tier", "Standard", kind=str, choices=("Standard", "Gateway", "Global"))
    count = ask.count()
    hours = ask.hours()
    data = ask.amount("data_gb", 100)
    guess = ask.was_assumed("tier", "count", "hours")
    sizing: dict[str, Any] = {
        "region": region,
        "tier": tier,
        "count": count,
        "hours": hours,
        "data_gb": data,
    }
    if tier == "Gateway":
        lines = [
            run(
                service,
                region,
                "Gateway",
                "Gateway",
                label="Gateway load balancer",
                count=count,
                hours=hours,
                assumed=guess,
            ),
        ]
        meter = "Gateway Data Processed"
    else:
        rules = ask.amount("rules", 5)
        sizing["rules"] = rules
        lines = [
            run(
                service,
                region,
                tier,
                f"{tier} Included LB Rules and Outbound Rules",
                label="First 5 rules",
                count=count,
                hours=hours,
                assumed=guess,
            )
        ]
        if rules > 5:
            lines.append(
                run(
                    service,
                    region,
                    tier,
                    f"{tier} Overage LB Rules and Outbound Rules",
                    label="Rules past 5",
                    count=count,
                    hours=hours,
                    units=rules - 5,
                )
            )
        meter = f"{tier} Data Processed"
    if data:
        lines.append(
            charge(
                service,
                region,
                tier,
                meter,
                label="Data processed",
                quantity=data,
                unit="GB",
                dimension="GB",
                assumed=ask.was_assumed("data_gb"),
            )
        )
    return _done(ask, lines, sizing, f"Load Balancer {tier}", service)


def _zone(ask: Ask) -> tuple[str, str]:
    given = ask.take(
        "zone", "Zone 1", kind=str, choices=[f"Zone {number}" for number in range(1, 9)]
    )
    return given, given.lower().replace(" ", "")


def price_front_door(ask: Ask) -> Price:
    """Front Door Standard or Premium: the base fee, requests and data out, by
    the billing zone the traffic is served from."""
    service = ask.table.service("frontdoor")
    zone_name, zone = _zone(ask)
    named = next(
        (t for t in ("Premium", "Standard") if re.search(rf"\b{t}\b", ask.name, re.IGNORECASE)),
        None,
    )
    if named is not None and ask.sizing.get("tier") in (None, ""):
        # The label states the tier ("Azure Front Door Premium"): not assumed.
        ask.taken.add("tier")
        tier = named
    else:
        tier = ask.take("tier", "Standard", kind=str, choices=("Standard", "Premium"))
    count = ask.count()
    requests = ask.amount("requests_millions", 1)
    egress = ask.amount("egress_gb", 100)
    lines = [
        run(
            service,
            zone,
            tier,
            f"{tier} Base Fees",
            label=f"{tier} profile",
            count=count,
            hours=HOURS,
            assumed=ask.was_assumed("tier", "count"),
        ),
        charge(
            service,
            zone,
            tier,
            f"{tier} Requests",
            label="Requests",
            quantity=requests,
            unit="1M requests",
            per=1e6,
            dimension="count",
            assumed=ask.was_assumed("requests_millions", "zone"),
        ),
        charge(
            service,
            zone,
            tier,
            f"{tier} Data Transfer Out",
            label="Data out to clients",
            quantity=egress,
            unit="GB",
            dimension="GB",
            assumed=ask.was_assumed("egress_gb", "zone"),
        ),
    ]
    sizing = {
        "zone": zone_name,
        "tier": tier,
        "count": count,
        "requests_millions": requests,
        "egress_gb": egress,
    }
    return _done(ask, lines, sizing, f"Azure Front Door {tier}, {zone_name}", service)


def price_cdn(ask: Ask) -> Price:
    """Azure CDN from Microsoft (classic): data out by billing zone."""
    service = ask.table.service("cdn")
    zone_name, zone = _zone(ask)
    egress = ask.amount("egress_gb", 100)
    lines = [
        charge(
            service,
            zone,
            "Standard",
            "Standard Data Transfer",
            label="Data out",
            quantity=egress,
            unit="GB",
            dimension="GB",
            assumed=ask.was_assumed("egress_gb", "zone"),
        )
    ]
    return _done(
        ask,
        lines,
        {"zone": zone_name, "egress_gb": egress},
        f"Azure CDN from Microsoft (classic), Standard, {zone_name}",
        service,
    )


_VPN_TIERS = (
    "Basic",
    "VpnGw1",
    "VpnGw2",
    "VpnGw3",
    "VpnGw4",
    "VpnGw5",
    "VpnGw1AZ",
    "VpnGw2AZ",
    "VpnGw3AZ",
    "VpnGw4AZ",
    "VpnGw5AZ",
)


def _vpn_gateway(ask: Ask) -> Price:
    service = ask.table.service("vpn")
    region = where(ask)
    tier = ask.take("tier", "VpnGw1AZ", kind=str, choices=_VPN_TIERS)
    count = ask.count()
    hours = ask.hours()
    tunnels = ask.amount("extra_s2s_tunnels", 0)
    meter = "Basic Gateway" if tier == "Basic" else tier
    lines = [
        run(
            service,
            region,
            tier,
            meter,
            label=f"{tier} gateway",
            count=count,
            hours=hours,
            assumed=ask.was_assumed("tier", "count", "hours"),
        )
    ]
    if tunnels:
        lines.append(
            run(
                service,
                region,
                tier,
                "S2S Connection",
                label="Site-to-site tunnels past the included",
                count=count,
                hours=hours,
                units=tunnels,
            )
        )
    sizing = {
        "region": region,
        "tier": tier,
        "count": count,
        "hours": hours,
        "extra_s2s_tunnels": tunnels,
    }
    return _done(ask, lines, sizing, f"VPN Gateway {tier}; data out bills apart", service)


_ER_GATEWAYS = (
    "ErGw1AZ",
    "ErGw2AZ",
    "ErGw3AZ",
    "ErGwScale",
    "Standard",
    "High Performance",
    "Ultra High Performance",
)


def _expressroute_gateway(ask: Ask) -> Price:
    service = ask.table.service("expressroute")
    region = where(ask)
    tier = ask.take("tier", "ErGw1AZ", kind=str, choices=_ER_GATEWAYS)
    count = ask.count()
    hours = ask.hours()
    meter = f"{tier} Unit" if tier == "ErGwScale" else f"{tier} Gateway"
    units = ask.amount("scale_units", 1) if tier == "ErGwScale" else 1
    item = run(
        service,
        region,
        f"Gateway {tier}",
        meter,
        label=f"{tier} gateway",
        count=count,
        hours=hours,
        units=units,
        assumed=ask.was_assumed("tier", "count", "hours"),
    )
    return _done(
        ask,
        [item],
        {"region": region, "tier": tier, "count": count, "hours": hours},
        f"ExpressRoute gateway {tier}",
        service,
    )


def price_gateway(ask: Ask) -> Price:
    """A virtual network gateway: VPN (the gateway hours and tunnels past the
    included ones) or ExpressRoute (the gateway hours)."""
    kind = ask.take("type", "VPN", kind=str, choices=("VPN", "ExpressRoute"))
    return _vpn_gateway(ask) if kind == "VPN" else _expressroute_gateway(ask)


def price_expressroute_circuit(ask: Ask) -> Price:
    """ExpressRoute circuits: the monthly fee by bandwidth, plan and tier, and
    metered data out, by the billing zone of the peering location."""
    service = ask.table.service("expressroute")
    zone_name, zone = _zone(ask)
    bandwidth = ask.take(
        "bandwidth",
        "1 Gbps",
        kind=str,
        choices=(
            "50 Mbps",
            "100 Mbps",
            "200 Mbps",
            "500 Mbps",
            "1 Gbps",
            "2 Gbps",
            "5 Gbps",
            "10 Gbps",
        ),
    )
    plan = ask.take("plan", "Metered", kind=str, choices=("Metered", "Unlimited"))
    tier = ask.take("tier", "Standard", kind=str, choices=("Local", "Standard", "Premium"))
    count = ask.count()
    egress = ask.amount("egress_gb", 100) if plan == "Metered" else 0
    sku = f"Circuit {bandwidth} {plan} Data"
    if not has(service, zone, sku, f"{tier} {plan} Data {bandwidth} Circuit"):
        raise PricingError(
            f"{ask.name}: ExpressRoute sells no {tier} {plan.lower()} {bandwidth} circuit "
            f"in {zone_name}"
        )
    lines = [
        run(
            service,
            zone,
            sku,
            f"{tier} {plan} Data {bandwidth} Circuit",
            label=f"{tier} {plan} {bandwidth} circuit",
            count=count,
            hours=HOURS,
            assumed=ask.was_assumed("bandwidth", "plan", "tier", "count", "zone"),
        )
    ]
    if egress:
        lines.append(
            charge(
                service,
                zone,
                sku,
                "Metered Data - Data Transfer Out",
                label="Data out",
                quantity=egress,
                unit="GB",
                dimension="GB",
                assumed=ask.was_assumed("egress_gb"),
            )
        )
    sizing = {
        "zone": zone_name,
        "bandwidth": bandwidth,
        "plan": plan,
        "tier": tier,
        "count": count,
        "egress_gb": egress,
    }
    return _done(
        ask, lines, sizing, f"ExpressRoute circuit, {tier} {plan} {bandwidth}, {zone_name}", service
    )


def price_public_ip(ask: Ask) -> Price:
    """Public IP addresses: Standard, Basic (static or dynamic) or Global, per hour."""
    service = ask.table.service("network")
    region = where(ask)
    tier = ask.take("tier", "Standard", kind=str, choices=("Standard", "Basic", "Global"))
    allocation = (
        ask.take("allocation", "Static", kind=str, choices=("Static", "Dynamic"))
        if tier == "Basic"
        else "Static"
    )
    count = ask.count()
    hours = ask.hours()
    item = run(
        service,
        region,
        f"IP {tier}",
        f"{tier} IPv4 {allocation} Public IP",
        label=f"{tier} {allocation.lower()} IPv4 address",
        count=count,
        hours=hours,
        assumed=ask.was_assumed("tier", "count", "hours"),
    )
    return _done(
        ask,
        [item],
        {"region": region, "tier": tier, "allocation": allocation, "count": count, "hours": hours},
        f"Public IP address, {tier}",
        service,
    )


def price_public_ip_prefix(ask: Ask) -> Price:
    service = ask.table.service("network")
    region = where(ask)
    tier = ask.take("tier", "Standard", kind=str, choices=("Standard", "Global"))
    addresses = ask.count("addresses", 16)
    count = ask.count()
    hours = ask.hours()
    meter = "Standard Static IP Addresses" if tier == "Standard" else "Global Static Public IP"
    item = run(
        service,
        region,
        f"Prefix {tier}",
        meter,
        label=f"{addresses} addresses",
        count=count,
        hours=hours,
        units=addresses,
        assumed=ask.was_assumed("addresses", "count", "hours"),
    )
    return _done(
        ask,
        [item],
        {"region": region, "tier": tier, "addresses": addresses, "count": count, "hours": hours},
        f"Public IP prefix, {tier}, per address",
        service,
    )


def price_peering(ask: Ask) -> Price:
    """Virtual network peering: data in and out, within a region or across regions."""
    service = ask.table.service("network")
    region = where(ask)
    scope = ask.take("scope", "regional", kind=str, choices=("regional", "global"))
    data = ask.amount("data_gb", 100)
    sku, words = (
        ("Peering Intra-Region", "Intra-Region")
        if scope == "regional"
        else ("GlobalPeering Inter-Region", "Inter-Region")
    )
    lines = [
        charge(
            service,
            region,
            sku,
            f"{words} Egress",
            label="Data out",
            quantity=data,
            unit="GB",
            dimension="GB",
            assumed=ask.was_assumed("data_gb"),
        ),
        charge(
            service,
            region,
            sku,
            f"{words} Ingress",
            label="Data in",
            quantity=data,
            unit="GB",
            dimension="GB",
            assumed=ask.was_assumed("data_gb"),
        ),
    ]
    return _done(
        ask,
        lines,
        {"region": region, "scope": scope, "data_gb": data},
        f"Virtual network peering, {scope}, each GB billed out and in",
        service,
    )


def price_dns_zone(ask: Ask) -> Price:
    """Azure DNS: hosted zones a month and queries (public or private)."""
    service = ask.table.service("dns")
    region = where(ask)
    kind = ask.take("type", "Public", kind=str, choices=("Public", "Private"))
    zones = ask.amount("zones", 1)
    queries = ask.amount("queries_millions", 1)
    lines = [
        charge(
            service,
            region,
            kind,
            f"{kind} Zone",
            label="Hosted zones",
            quantity=zones,
            unit="zone-months",
            dimension="count",
            kind="fixed",
            assumed=ask.was_assumed("zones"),
        ),
        charge(
            service,
            region,
            kind,
            f"{kind} Queries",
            label="Queries",
            quantity=queries,
            unit="1M queries",
            per=1e6,
            dimension="count",
            assumed=ask.was_assumed("queries_millions"),
        ),
    ]
    return _done(
        ask,
        lines,
        {"type": kind, "zones": zones, "queries_millions": queries},
        f"Azure DNS, {kind.lower()} zones",
        service,
    )


def price_ddos(ask: Ask) -> Price:
    """DDoS Protection: a Network Protection plan (100 public IPs included) or IP Protection per IP."""
    service = ask.table.service("ddos")
    region = where(ask)
    plan = ask.take(
        "plan", "Network Protection", kind=str, choices=("Network Protection", "IP Protection")
    )
    addresses = ask.amount("public_ips", 1 if plan == "IP Protection" else 100)
    hours = ask.hours()
    if plan == "IP Protection":
        lines = [
            run(
                service,
                region,
                "Azure DDoS Protection IP Protection",
                "IP Protection Resource",
                label="Protected IPs",
                count=1,
                hours=hours,
                units=addresses,
                assumed=ask.was_assumed("public_ips", "hours"),
            )
        ]
    else:
        lines = [
            run(
                service,
                region,
                "Network Protection",
                "Network Protection Plan",
                label="Protection plan, 100 IPs included",
                count=1,
                hours=hours,
                assumed=ask.was_assumed("plan", "hours"),
            )
        ]
        if addresses > 100:
            lines.append(
                run(
                    service,
                    region,
                    "Network Protection",
                    "Network Protection Resource",
                    label="Protected IPs past 100",
                    count=1,
                    hours=hours,
                    units=addresses - 100,
                )
            )
    return _done(
        ask,
        lines,
        {"region": region, "plan": plan, "public_ips": addresses, "hours": hours},
        f"Azure DDoS Protection, {plan}",
        service,
    )


# -- analytics and data ------------------------------------------------------------------------


def price_synapse(ask: Ask) -> Price:
    """Synapse: serverless SQL by TB processed, a dedicated SQL pool by DWU
    and TB stored, or Spark by vCore-hours."""
    service = ask.table.service("synapse")
    region = where(ask)
    pool = ask.take("pool", "serverless", kind=str, choices=("serverless", "dedicated", "spark"))
    sizing: dict[str, Any] = {"region": region, "pool": pool}
    if pool == "serverless":
        processed = ask.amount("tb_processed", 1)
        sizing["tb_processed"] = processed
        lines = [
            charge(
                service,
                region,
                "Serverless Standard",
                "Standard Data Processed",
                label="Data processed",
                quantity=processed,
                unit="TB",
                dimension="TB",
                assumed=ask.was_assumed("tb_processed"),
            )
        ]
    elif pool == "dedicated":
        return _dedicated_pool(ask, service, region, sizing)
    else:
        used = ask.amount("vcore_hours", 100)
        sizing["vcore_hours"] = used
        lines = [
            charge(
                service,
                region,
                "Spark vCore",
                "vCore",
                label="Spark vCore-hours",
                quantity=used,
                unit="vCore-hours",
                dimension="hour",
                assumed=ask.was_assumed("vcore_hours"),
            )
        ]
    return _done(ask, lines, sizing, f"Azure Synapse Analytics, {pool} pool", service)


def _dedicated_pool(ask: Ask, service: Service, region: str, sizing: dict[str, Any]) -> Price:
    level = ask.take(
        "dwu", "DW100c", kind=str, choices=skus(service, region, "Dedicated {tier}") or ["DW100c"]
    )
    hours = ask.hours()
    stored = ask.amount("storage_tb", 1)
    lines = [
        run(
            service,
            region,
            f"Dedicated {level}",
            "100 DWUs",
            label=f"{level} pool",
            count=1,
            hours=hours,
            assumed=ask.was_assumed("dwu", "hours"),
        ),
        charge(
            service,
            region,
            "SQL Storage Standard LRS",
            "Standard LRS Data Stored",
            label="Storage",
            quantity=stored,
            unit="TB-month",
            dimension="TB-month",
            kind="fixed",
            assumed=ask.was_assumed("storage_tb"),
        ),
    ]
    sizing.update(dwu=level, hours=hours, storage_tb=stored)
    return _done(
        ask, lines, sizing, f"Dedicated SQL pool (formerly SQL Data Warehouse), {level}", service
    )


def price_dedicated_sql_pool(ask: Ask) -> Price:
    service = ask.table.service("synapse")
    region = where(ask)
    return _dedicated_pool(ask, service, region, {"region": region})


def price_data_factory(ask: Ask) -> Price:
    """Data Factory: activity runs, data movement (DIU-hours) and data flow vCore-hours."""
    service = ask.table.service("datafactory")
    region = where(ask)
    runs = ask.amount("activity_runs_thousands", 1)
    movement = ask.amount("diu_hours", 10)
    flows = ask.amount("data_flow_vcore_hours", 0)
    lines = []
    if runs:
        lines.append(
            charge(
                service,
                region,
                "Cloud",
                "Cloud Orchestration Activity Run",
                label="Activity runs",
                quantity=runs,
                unit="1K runs",
                per=1e3,
                dimension="count",
                assumed=ask.was_assumed("activity_runs_thousands"),
            )
        )
    if movement:
        lines.append(
            charge(
                service,
                region,
                "Cloud",
                "Cloud Data Movement",
                label="Data movement",
                quantity=movement,
                unit="DIU-hours",
                dimension="hour",
                assumed=ask.was_assumed("diu_hours"),
            )
        )
    if flows:
        lines.append(
            charge(
                service,
                region,
                "Data Flow General Purpose vCore",
                "vCore",
                label="Data flows, general purpose",
                quantity=flows,
                unit="vCore-hours",
                dimension="hour",
                assumed=ask.was_assumed("data_flow_vcore_hours"),
            )
        )
    sizing = {
        "region": region,
        "activity_runs_thousands": runs,
        "diu_hours": movement,
        "data_flow_vcore_hours": flows,
    }
    return _done(ask, lines, sizing, "Azure Data Factory, Azure integration runtime", service)


def price_databricks(ask: Ask) -> Price:
    """Databricks: DBU-hours at the workload's rate, and the cluster's VMs
    (``nodes`` of ``node_size``, each running ``node_hours``)."""
    service = ask.table.service("databricks")
    region = where(ask)
    tier = ask.take("tier", "Premium", kind=str, choices=("Standard", "Premium"))
    workloads = sorted(
        {name[len(tier) + 1 :] for name in skus(service, region) if name.startswith(f"{tier} ")}
    )
    workload = ask.take("workload", "Jobs Compute", kind=str, choices=workloads or ["Jobs Compute"])
    dbus = ask.amount("dbu_hours", 100)
    sku = f"{tier} {workload}"
    lines = [
        charge(
            service,
            region,
            sku,
            f"{sku} DBU",
            label=f"DBUs, {workload}",
            quantity=dbus,
            unit="DBU-hours",
            dimension="hour",
            assumed=ask.was_assumed("tier", "workload", "dbu_hours"),
        )
    ]
    vm_hours = ask.amount("node_hours", 100)
    sizing: dict[str, Any] = {
        "region": region,
        "tier": tier,
        "workload": workload,
        "dbu_hours": dbus,
        "node_hours": vm_hours,
    }
    services = [service]
    if vm_hours:
        node, what, vm, more = _vm(
            ask,
            region,
            size_key="node_size",
            os_key="node_os",
            count_key="nodes",
            default_size="Standard_DS3_v2",
            default_count=2,
            hours=vm_hours,
            label="Cluster VMs, ",
        )
        lines.append(node)
        sizing.update(more)
        services.append(vm)
    return _done(
        ask, lines, sizing, f"Azure Databricks {tier}, {workload}; VMs pay as you go", *services
    )


def price_data_explorer(ask: Ask) -> Price:
    """Data Explorer: the engine nodes as VMs and the per-vCore markup."""
    service = ask.table.service("dataexplorer")
    region = where(ask)
    hours = ask.hours()
    node, what, vm, sizing = _vm(
        ask,
        region,
        size_key="node_size",
        os_key="node_os",
        count_key="nodes",
        default_size="Standard_E2ads_v5",
        default_count=2,
        hours=hours,
        label="Engine nodes, ",
    )
    nodes = sizing["nodes"]
    vcpus = _vcpus(vm, _vm_key(sizing["node_size"]))
    markup = charge(
        service,
        region,
        "Standard",
        "Standard Engine Cluster Markup",
        label="Engine markup, vCPU-hours",
        quantity=vcpus * nodes * hours,
        unit="vCPU-hours",
        dimension="hour",
        kind="fixed",
        assumed=node.assumed,
    )
    return _done(
        ask,
        [node, markup],
        {"region": region, "hours": hours, **sizing},
        f"Azure Data Explorer, engine {what}",
        service,
        vm,
    )


_BACKUP_KINDS = (
    "Azure VM",
    "SQL Server in Azure VM",
    "SAP HANA on Azure VM",
    "Azure Files",
    "Azure Blob",
    "Azure Kubernetes",
    "PostgreSQL",
    "On Premises Server",
)


#: What a Recovery Services vault does when it replicates rather than backs up.
SITE_RECOVERY = "Site Recovery"


def price_site_recovery(ask: Ask) -> Price:
    """Azure Site Recovery: each VM a vault replicates to Azure, a month."""
    service = ask.table.service("site-recovery")
    region = where(ask)
    instances = ask.amount("instances", 1)
    lines = [
        run(
            service,
            region,
            "Azure",
            "VM Replicated to Azure",
            label="VMs replicated to Azure",
            count=1,
            hours=HOURS,
            units=instances,
            assumed=ask.was_assumed("instances"),
        )
    ]
    sizing = {"region": region, "protects": SITE_RECOVERY, "instances": instances}
    return _done(
        ask,
        lines,
        sizing,
        "Azure Site Recovery, per VM replicated to Azure a month (each VM's first 31 days "
        "free); its replica disks and cache storage bill apart",
        service,
    )


def price_backup(ask: Ask) -> Price:
    """Azure Backup: protected instances a month and the backup storage used;
    a vault that replicates VMs (``protects: Site Recovery``) is Site Recovery."""
    kind = ask.take("protects", "Azure VM", kind=str, choices=(*_BACKUP_KINDS, SITE_RECOVERY))
    if kind == SITE_RECOVERY:
        return price_site_recovery(ask)
    service = ask.table.service("backup")
    region = where(ask)
    instances = ask.amount("instances", 1)
    redundancy = ask.take("redundancy", "GRS", kind=str, choices=("LRS", "ZRS", "GRS", "RA-GRS"))
    stored = ask.amount("storage_gb", 100)
    lines = [
        run(
            service,
            region,
            kind,
            f"{kind} Protected Instance",
            label=f"Protected {kind} instances",
            count=1,
            hours=HOURS,
            units=instances,
            assumed=ask.was_assumed("protects", "instances"),
        ),
        charge(
            service,
            region,
            "Standard",
            f"Standard {redundancy} Data Stored",
            label="Backup storage",
            quantity=stored,
            unit="GB-month",
            dimension="GB-month",
            assumed=ask.was_assumed("storage_gb", "redundancy"),
        ),
    ]
    sizing = {
        "region": region,
        "protects": kind,
        "instances": instances,
        "redundancy": redundancy,
        "storage_gb": stored,
    }
    return _done(
        ask,
        lines,
        sizing,
        f"Azure Backup, {kind}; the instance fee grows with its size past 500 GB",
        service,
    )


# -- coverage --------------------------------------------------------------------------------


def _same(pricer: Pricer, *ids: str) -> dict[str, Pricer]:
    return dict.fromkeys(ids, pricer)


_PRICERS: dict[str, Pricer] = {
    **_same(price_vm, "virtual-machine", "vm-scale-sets", "automanaged-vm", "azure-sql-vm"),
    **_same(price_aks, "kubernetes-services", "kubernetes-services-containers"),
    "aks-automatic": lambda ask: price_aks(ask, "Automatic"),
    **_same(price_disk, "disks", "ssd"),
    **_same(price_blob, "storage-accounts", "blob-block", "storage-container"),
    **_same(price_files, "files", "azure-fileshares", "storage-azure-files", "managed-file-shares"),
    "storage-queue": _simple_store("Queue", "Queue storage"),
    "table": _simple_store("Table", "Table storage"),
    **_same(
        price_sql_database, "sql-database", "azure-sql", "sql-elastic-pools", "managed-database"
    ),
    **_same(
        price_sql_managed_instance, "sql-managed-instance", "instance-pools", "instance-pools-other"
    ),
    **_same(
        _flexible("PostgreSQL", "Azure Database for PostgreSQL"),
        "azure-database-postgresql-server",
        "arc-postgresql",
    ),
    "azure-database-mysql-server": _flexible("MySQL", "Azure Database for MySQL"),
    **_same(price_cosmos, "azure-cosmos-db", "azure-cosmos-db-iot"),
    **_same(price_redis, "cache-redis", "cache", "azure-managed-redis"),
    **_same(
        _app_plan("P1v3"),
        "app-services-compute",
        "app-services-containers",
        "app-services-mobile",
        "app-service-plans",
        "app-service-plans-web",
        "app-services",
        "app-services-web",
        "server-farm",
        "website-power",
        "agentic-web-apps",
    ),
    **_same(_app_plan("I1v2"), "app-service-environments", "app-service-environments-web"),
    **_same(
        price_app_service_extra(
            "Standard SSL - 1 Year Certificate", "App Service certificate, Standard"
        ),
        "app-service-certificates",
        "app-service-certificates-web",
    ),
    **_same(
        price_app_service_extra("Custom Domain", "App Service domain"),
        "app-service-domains",
        "app-service-domains-web",
    ),
    "static-apps": price_static_web_app,
    **_same(price_functions, "function-apps", "function-apps-iot", "storage-functions"),
    **_same(price_logic_app, "logic-apps", "logic-apps-iot", "workflow"),
    "integration-accounts": price_integration_account,
    **_same(price_container_apps, "worker-container-app"),
    **_same(price_container_instances, "container-instances", "container-instances-containers"),
    "container-registries": price_container_registry,
    **_same(price_app_gateway, "application-gateways", "application-gateway-containers"),
    **_same(price_load_balancer, "load-balancers", "load-balancer-hub"),
    **_same(price_front_door, "front-door-and-cdn-profiles", "front-door-and-cdn-profiles-web"),
    **_same(price_cdn, "cdn-profiles", "cdn-profiles-networking"),
    **_same(price_gateway, "virtual-network-gateways"),
    "expressroute-circuits": price_expressroute_circuit,
    **_same(price_public_ip, "public-ip-addresses"),
    "public-ip-prefixes": price_public_ip_prefix,
    "peerings": price_peering,
    **_same(price_dns_zone, "dns-zones", "dns-multistack"),
    "ddos-protection-plans": price_ddos,
    **_same(price_synapse, "azure-synapse-analytics", "azure-synapse-analytics-databases"),
    **_same(price_dedicated_sql_pool, "sql-data-warehouses", "sql-data-warehouses-integration"),
    **_same(
        price_data_factory,
        "data-factories",
        "data-factories-databases",
        "data-factories-integration",
    ),
    "azure-databricks": price_databricks,
    **_same(
        price_data_explorer,
        "azure-data-explorer-clusters",
        "azure-data-explorer-clusters-databases",
    ),
    **_same(
        price_backup,
        "backup-vault",
        "azure-backup-center",
        "recovery-services-vaults",
        "recovery-services-vaults-storage",
        "recovery-services-vaults-migrate",
    ),
}
_PLAN_IDS: dict[str, tuple[str, ...]] = {
    "keyvault": ("key-vaults",),
    "dedicated-hsm": ("dedicated-hsm",),
    "eventhubs": ("event-hubs", "event-hubs-iot", "event-hub-clusters", "event-hub-clusters-iot"),
    "servicebus": ("azure-service-bus",),
    "relay": ("relays",),
    "eventgrid": ("event-grid-topics", "event-grid-domains", "partner-topic", "system-topic"),
    "apim": (
        "api-management-services",
        "api-management-services-integration",
        "api-management-services-web",
    ),
    "loganalytics": (
        "log-analytics-workspaces",
        "log-analytics-workspaces-monitor",
        "log-analytics-workspaces-management-governance",
    ),
    "appinsights": (
        "application-insights",
        "application-insights-monitor",
        "application-insights-management-governance",
    ),
    "sentinel": ("azure-sentinel",),
    "signalr": ("signalr",),
    "webpubsub": ("pubsub",),
    "search": (
        "cognitive-search",
        "cognitive-search-app-services",
        "cognitive-search-web",
        "serverless-search",
    ),
    "notificationhubs": (
        "notification-hubs",
        "notification-hubs-iot",
        "notification-hubs-mobile",
        "notification-hub-namespaces",
        "notification-hub-namespaces-web",
    ),
    "iothub": ("iot-hub",),
    "dps": ("device-provisioning-services",),
    "streamanalytics": ("stream-analytics-jobs", "stream-analytics-jobs-iot"),
    "appconfig": ("app-configuration",),
    "netapp": ("azure-netapp-files",),
    "powerbi": ("power-bi-embedded",),
    "analysisservices": ("analysis-services",),
    "grafana": ("azure-managed-grafana",),
    "entrads": ("entra-domain-services",),
    "confidentialledger": ("confidential-ledgers",),
    "digitaltwins": ("digital-twins",),
    "iotcentral": ("iot-central-applications",),
    "loadtesting": ("azure-load-testing", "load-testing", "load-test", "azure-app-testing"),
    "botservice": ("bot-services",),
    "firewall": ("firewalls",),
    "nat": ("nat",),
    "bastion": ("bastions",),
    "privateendpoint": ("private-endpoints", "private-link", "resource-management-private-link"),
    "virtualwanhub": ("virtual-wan-hub",),
    "routeserver": ("virtual-router",),
    "privateresolver": ("dns-private-resolver",),
    "trafficmanager": ("traffic-manager-profiles", "atm-multistack"),
}
for _name, _ids in _PLAN_IDS.items():
    _PRICERS.update(dict.fromkeys(_ids, _plan_pricer(PLANS[_name])))


def _why(reason: str, *ids: str) -> dict[str, str]:
    return dict.fromkeys(ids, reason)


# fmt: off
_FREE: dict[str, str] = {
    **_why(
        "a generic icon, not an Azure resource",
        "aquila", "azure-a", "breeze", "ceres", "controls", "controls-horizontal", "counter",
        "cubes", "download", "error", "fiji", "file", "folder-blank", "folder-website", "gear",
        "globe-error", "globe-success", "globe-warning", "heart", "image", "information",
        "location", "media", "media-file", "power", "power-up", "recent", "search",
        "search-grid", "toolbox", "browser", "production-ready-database", "ftp",
        "input-output", "sonic-dash",
    ),
    **_why(
        "a development concept, not a billed Azure resource",
        "backlog", "branch", "bug", "builds", "code", "commit", "extensions", "module",
        "powershell", "process-explorer", "versions", "tfs-vc-repository",
        "toolchain-orchestrator", "dev-console", "devops-starter", "cloudtest",
        "targets-management", "workspace-gateway", "osconfig",
    ),
    **_why(
        "an on-site device or tool drawn for context; Azure bills nothing for it",
        "defender-cm-local-manager", "defender-dcs-controller",
        "defender-distributer-control-system", "defender-engineering-station",
        "defender-external-management", "defender-freezer-monitor", "defender-historian",
        "defender-hmi", "defender-industrial-packaging-system", "defender-industrial-printer",
        "defender-industrial-robot", "defender-industrial-scale-system", "defender-marquee",
        "defender-meter", "defender-plc", "defender-pneumatic-device",
        "defender-programable-board", "defender-relay", "defender-robot-controller",
        "defender-rtu", "defender-sensor", "defender-slot", "defender-web-guiding-system",
        "azure-stack-hci-sizer", "vpnclientwindows", "storage-explorer", "azurite",
    ),
    **_why(
        "a management or portal feature with no charge of its own",
        "activity-log", "activity-log-monitor", "advisor", "all-resources",
        "app-compliance-automation", "azure-lighthouse", "azure-quotas",
        "azure-sustainability", "blueprints", "compliance", "compliance-center",
        "cost-alerts", "cost-analysis", "cost-budgets", "cost-export", "cost-management",
        "cost-management-and-billing", "cost-management-and-billing-management-governance",
        "cost-management-and-billing-migrate", "customer-lockbox-for-microsoft-azure",
        "dashboard-hub", "diagnostics-settings", "diagnostics-settings-monitor", "education",
        "feature-previews", "free-services", "guide", "help-and-support", "icm-troubleshooting",
        "journey-hub", "landing-zone", "launch-portal", "learn", "managed-applications-center",
        "management-groups", "management-portal", "marketplace", "marketplace-management",
        "metrics", "metrics-monitor", "mission-landing-zone", "monitor", "monitor-monitor",
        "my-customers", "operation-log-classic", "policy", "preview-features",
        "quickstart-center", "region-management", "resiliency", "resource-explorer",
        "resource-graph-explorer", "resource-group-list", "resource-groups",
        "resource-linked", "resources-provider", "service-catalog-mad", "service-health",
        "service-providers", "solutions", "subscriptions", "tag", "tags", "troubleshoot",
        "user-privacy", "azure-monitor-dashboard", "azure-workbooks", "azure-workbooks-monitor",
        "workbooks", "dashboard", "change-analysis", "change-analysis-monitor", "auto-scale",
        "log-analytics-query-pack", "log-streaming", "monitor-health-models", "applens",
        "azure-hybrid-center", "edge-management", "azure-edge-hardware-center",
        "tenant-status", "identity-secure-score", "azure-support-center-blue",
        "azure-migrate", "resource-mover", "azure-storage-mover", "hybrid-connectivity-hub",
        "express-route-traffic-collector", "network-security-hub", "network-foundation-hub",
        "service-groups", "sql-database-fleet-manager", "sql-server-registries",
        "azure-database-migration-services", "azure-database-migration-services-migration",
        "code-optimization",
    ),
    **_why(
        "data collection rules are free; the data they send bills in its Log Analytics workspace",
        "data-collection-rules",
    ),
    **_why(
        "Network Watcher itself is free; flow logs and connection tests bill by use",
        "network-watcher", "network-watcher-networking",
    ),
    **_why(
        "a networking resource Azure does not charge for",
        "virtual-networks", "subnet", "network-interfaces", "network-security-groups",
        "application-security-groups", "route-tables", "route-filters",
        "service-endpoint-policies", "local-network-gateways", "local-network-gateways-other",
        "connections", "ip-groups", "custom-ip-prefix", "ddos-custom-policy",
        "private-link-service", "private-link-services", "private-link-services-networking",
        "peering-service", "network-security-perimeters", "virtual-wans",
        "on-premises-data-gateways", "connected-cache",
    ),
    **_why(
        "free; the VMs, disks and storage it places or describes bill",
        "availability-sets", "proximity-placement-groups", "maintenance-configuration",
        "scheduled-actions", "compute-fleet", "disk-encryption-sets", "host-groups",
        "azure-compute-galleries", "azure-compute-galleries-other", "shared-image-galleries",
        "image-definitions", "image-versions", "vm-image-version", "images",
        "community-images", "vm-app-definitions", "vm-app-versions", "image-templates",
        "batch-accounts", "batch-accounts-containers", "service-fabric-clusters",
        "service-fabric-clusters-containers", "managed-service-fabric", "managed-devops-pools",
        "azure-center-for-sap", "virtual-instance-for-sap", "central-service-instance-for-sap",
        "database-instance-for-sap", "azure-monitors-for-sap-solutions",
        "azure-hpc-workbenches", "devtest-labs", "azure-deployment-environments",
        "azure-machine-learning", "machine-learning", "azure-linux", "rtos",
    ),
    **_why(
        "no charge with an eligible Microsoft 365 or Windows license; session hosts bill as VMs",
        "azure-virtual-desktop", "host-pools", "application-group", "workspaces",
    ),
    **_why(
        "a Foundry hub or project has no charge of its own; the models and tools it calls bill",
        "ai-foundry", "ai-studio", "foundry-project", "foundry-application",
        "foundry-control-plane", "foundry-labs", "foundry-local",
    ),
    **_why(
        "a container platform feature with no charge of its own; the cluster's nodes bill",
        "aks-istio", "aks-network-policy", "kubernetes-fleet-manager", "kubernetes-hub",
        "azure-container-storage", "arc-kubernetes",
    ),
    **_why(
        "a Consumption environment has no charge of its own; its apps bill",
        "container-apps-environments",
    ),
    **_why(
        "free; billed as the operations on the topic it belongs to",
        "event-grid-subscriptions", "event-grid-subscriptions-iot", "partner-namespace",
        "partner-registration",
    ),
    **_why(
        "free; Logic Apps bills the connector calls and runs",
        "api-connections", "api-connections-integration", "api-connections-web",
        "logic-apps-custom-connector", "logic-apps-template", "integration-environments",
        "business-process-tracking",
    ),
    **_why(
        "runs on its App Service plan at no extra charge",
        "web-jobs", "web-slots", "website-staging",
    ),
    **_why(
        "an identity or security object with no charge of its own",
        "users", "groups", "app-registrations", "app-registrations-other",
        "enterprise-applications", "managed-identities", "entra-managed-identities",
        "entra-identity-roles-and-administrators", "entra-identity-custom-roles",
        "administrative-units", "tenant-properties", "user-settings", "user-settings-security",
        "user-subscriptions", "multi-tenancy", "security", "devices", "entra-connect",
        "entra-connect-sync", "verifiable-credentials", "verification-as-a-service",
        "entra-verified-id", "azureattestation", "keys", "ssh-keys", "resource-guard",
    ),
    **_why(
        "Microsoft Entra ID Free comes with every subscription; P1 and P2 are per-user licenses",
        "entra-id",
    ),
    **_why(
        "a logical container with no charge of its own; the databases or instances in it bill",
        "sql-server", "virtual-clusters",
    ),
    **_why(
        "free to use; the resources it creates, connects or manages bill",
        "azure-cloud-shell", "azure-dev-tunnels", "template-specs", "templates",
        "update-management-center", "automation-accounts", "azure-arc", "arc-machines",
        "machinesazurearc", "scvmm-management-servers", "wac", "wac-installer",
        "iot-edge", "industrial-iot", "azure-firewall-manager", "azure-firewall-policy",
        "ai-gateway", "windows-notification-services",
    ),
}

_RETIRED = "retired by Microsoft; no longer sold"
_PER_CALL = (
    "billed per call, character, image or audio hour at a rate that depends on the "
    "feature used; no default usage fits"
)
_LICENSE = (
    "licensed per user through Microsoft Entra ID P1/P2 or Microsoft 365, not priced by "
    "the Azure Retail Prices API"
)
_INTUNE = "licensed per user or device through Microsoft Intune and Microsoft 365"
_NO_PRICE = "no public list price applies to this item on its own"

_UNPRICED: dict[str, str] = {
    **_why(
        "billed per model token (input and output), at a rate per model; no fixed size to price",
        "azure-openai", "foundry-models", "foundry-agent-service", "azure-ai-foundry-iq",
    ),
    **_why(
        _PER_CALL,
        "cognitive-services", "cognitive-services-decisions", "cognitive-services-web",
        "computer-vision", "content-safety", "custom-vision", "face-apis", "form-recognizers",
        "immersive-readers", "language", "speech-services", "translator-text",
        "azure-applied-ai-services", "azure-object-understanding", "azure-video-indexer",
        "content-moderators", "azure-communication-services", "azure-maps-accounts",
        "anomaly-detector", "personalizers",
    ),
    **_why(
        _RETIRED,
        "metrics-advisor", "metrics-advisor-compute", "qna-makers", "language-understanding",
        "video-analyzers", "batch-ai", "bonsai", "machine-learning-studio-classic-web-services",
        "machine-learning-studio-web-service-plans", "machine-learning-studio-workspaces",
        "machine-learning-studio-classic-web-services-iot",
        "machine-learning-studio-web-service-plans-iot",
        "machine-learning-studio-workspaces-iot", "genomics", "genomics-accounts",
        "data-lake-analytics", "data-lake-store-gen1", "data-lake-storage-gen1",
        "hdi-aks-cluster", "cloud-services-classic", "virtual-machines-classic",
        "os-images-classic", "vm-images-classic", "disks-classic",
        "container-services-deprecated", "mesh-applications", "abs-member",
        "azure-blockchain-service", "blockchain-applications", "consortium",
        "azure-token-service", "azure-database-mariadb-server", "azure-sql-edge",
        "azure-sql-server-stretch-databases", "azure-sql-server-stretch-databases-integration",
        "azure-data-catalog", "biz-talk", "integration-service-environments", "scheduler",
        "scheduler-job-collections", "storsimple-device-managers",
        "storsimple-device-managers-storage", "storsimple-data-managers",
        "virtual-visits-builder", "open-supply-chain-platform", "connected-vehicle-platform",
        "time-series-data-sets", "time-series-insights-access-policies",
        "time-series-insights-environments", "time-series-insights-event-sources",
        "mindaro", "mobile-engagement", "remote-rendering", "spatial-anchor-accounts",
        "public-ip-addresses-classic", "reserved-ip-addresses-classic",
        "virtual-networks-classic", "storage-accounts-classic", "internet-analyzer-profiles",
        "mobile-networks", "azure-media-service", "disk-pool", "azure-hcp-cache",
        "test-base", "azure-orbital",
    ),
    **_why(
        _LICENSE,
        "entra-id-governance", "entra-id-protection", "entra-privleged-identity-management",
        "entra-internet-access", "entra-private-access", "entra-global-secure-access",
        "entra-identity-licenses", "entra-identity-licenses-other", "identity-governance",
        "conditional-access", "multi-factor-authentication", "multifactor-authentication",
        "azure-information-protection", "azure-information-protection-security",
        "entra-identity-risky-signins", "entra-identity-risky-users", "entra-workload-id",
        "exchange-on-premises-access", "api-proxy", "active-directory-connect-health",
        "entra-connect-health",
    ),
    **_why(
        _INTUNE,
        "intune", "intune-app-protection", "intune-for-education", "intune-trends",
        "client-apps", "device-compliance", "device-configuration", "device-enrollment",
        "device-security-apple", "device-security-google", "device-security-windows",
        "ebooks", "entra-identity-roles-and-administrators-intune", "exchange-access",
        "mobile", "security-baselines", "software-updates", "endpoint-analytics",
        "managed-desktop", "universal-print", "engage-center-connect",
    ),
    **_why(
        "licensed per user or per app through Microsoft Power Platform, not Azure",
        "power-platform", "power-platform-integration", "power-platform-mobile",
        "power-platform-web",
    ),
    **_why(
        "billed per monthly active user past the free allowance; no default user count fits",
        "azure-ad-b2c", "external-id", "external-id-modified", "external-identities",
    ),
    **_why(
        "a pricing commitment, not a resource; the export prices pay as you go",
        "reservations", "reserved-capacity", "savings-plans", "azure-consumption-commitment",
    ),
    **_why(
        "Spot prices move with demand and the VM can be evicted; there is no list price",
        "spot-vm", "spot-vmss",
    ),
    **_why(
        "sold by its publisher through Azure Marketplace, not by Azure's list prices",
        "oracle-database", "sendgrid-accounts", "software-as-a-service",
    ),
    **_why(
        "sold to network operators or large customers by agreement; no public list price",
        "azure-operator-5g-core", "azure-operator-insights", "azure-operator-nexus",
        "azure-operator-service-manager", "azure-programmable-connectivity",
        "azure-communications-gateway", "azure-network-function-manager",
        "azure-network-function-manager-functions", "modular-data-center",
        "disconnected-operations",
    ),
    **_why(
        "billed per dedicated host by host type; the host prices are not in the table",
        "hosts", "azure-vmware-solution", "avs-vm", "bare-metal-infrastructure",
    ),
    **_why(
        "billed as the VMs reserved, used or not; price the reserved VMs as virtual machines",
        "capacity-reservation-groups",
    ),
    **_why(
        "billed per GB of changed data kept a month; not modelled",
        "disks-snapshots", "restore-points", "restore-points-collections",
    ),
    **_why(
        "billed per page blob size provisioned and its operations; not modelled",
        "blob-page",
    ),
    **_why(
        "billed per role instance at Cloud Services rates; not in the table",
        "cloud-services-extended-support",
    ),
    **_why(
        "Azure Spring Apps is being retired, and is billed per vCPU and GB group; not modelled",
        "azure-spring-apps", "azure-spring-apps-web",
    ),
    **_why(
        "billed per worker vCPU license on top of its VMs; the license rate is not in the table",
        "azure-red-hat-openshift",
    ),
    **_why(
        "billed per vCore license on servers you run; the Arc license rates are not modelled",
        "arc-sql-managed-instance", "arc-sql-server", "arc-data-services",
    ),
    **_why(
        "billed per physical core a month on hardware you own; not modelled",
        "azure-local", "stack-hci-premium",
    ),
    **_why(
        "billed per node size and disk; not modelled",
        "hd-insight-clusters", "managed-instance-apache-cassandra",
        "azure-database-postgresql-server-group", "azure-documentdb", "ssis-lift-and-shift-ir",
    ),
    **_why(
        "Azure Health Data Services bill per GB stored and per request; not modelled",
        "fhir-service", "azure-api-for-fhir", "medtech-service",
    ),
    **_why(
        "billed per device, order or day kept; no default fits",
        "data-box", "data-box-storage", "azure-databox-gateway",
        "azure-databox-gateway-iot", "azure-databox-gateway-migrate",
        "azure-databox-gateway-storage", "import-export-jobs", "windows10-core-services",
        "azure-sphere", "device-update-iot-hub",
    ),
    **_why(
        "billed per use (executions, minutes, targets, users or queries); not modelled",
        "azure-chaos-studio", "storage-actions", "dns-security-policy", "edge-actions",
        "promethus", "alerts", "web-test", "azure-iot-operations", "azure-monitor-pipeline",
        "elastic-job-agents", "azure-data-sharing", "data-shares", "data-share-invitations",
        "microsoft-defender-easm", "microsoft-defender-for-cloud", "microsoft-defender-for-iot",
        "extendedsecurityupdates", "storage-sync-services", "elastic-san",
        "web-application-firewall-policies-waf", "network-managers", "ip-address-manager",
        "lab-accounts", "lab-services", "microsoft-dev-box", "azure-devops", "api-center",
        "expressroute-direct", "vnet-appliance", "edge-storage-accelerator",
        "workload-orchestration", "planetary-computer-pro", "azure-experimentation-studio",
        "microsoft-discovery",
    ),
    **_why(
        "a template that deploys several resources; price the app and database it creates",
        "web-app-database",
    ),
    **_why(
        _NO_PRICE,
        "stage-maps", "frd-qa", "collaborative-service", "azure-access-point",
        "data-virtualization", "azure-enclaves", "detonation", "ai-at-edge",
        "030777508-icon-service-service-group-relationships", "service-group-relationships",
        "outbound-connection", "storage-hubs", "app-space", "app-space-component",
        "azure-data-transfer",
    ),
}
# fmt: on

COVERAGE = Coverage(
    cloud="azure",
    default_region="eastus",
    region_of=region_of,
    pricers=_PRICERS,
    free=_FREE,
    unpriced=_UNPRICED,
)
