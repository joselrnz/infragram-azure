"""AWS prices: from AWS's public price list, shipped as a table or read live.

Every AWS component is priced from the shipped table
(``assets/prices/aws.json``, built from the AWS Price List API and the
pricing pages' files by :mod:`infragram.pricing.build.aws`), is free (costs
nothing on its own), or is not priced, with the reason: :data:`COVERAGE`.

EC2 can also be priced live (``--prices live``): the rates
aws.amazon.com/ec2/pricing/on-demand shows, read from the files that page
reads (``b0.p.awsstatic.com``): one small file per region and operating
system, with every instance type's hourly rate, and a list of AWS's
locations that names each region the way the price files do. Nothing needs
signing in. They are public but not a documented API, so a file that
changes shape is reported as a component not priced, never guessed at.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from ..models.topology import TopologyElement
from . import Price, PriceLine, PricingError
from .ask import MAX_COUNT, MAX_HOURS, Ask, Coverage, Pricer, line, priced
from .tables import Service

__all__ = [
    "COVERAGE",
    "DEFAULTS",
    "GLOBAL",
    "OPERATING_SYSTEMS",
    "location_name",
    "price_ec2",
    "price_ec2_table",
    "region_of",
]

#: What an EC2 instance is priced as when its element does not say: the
#: Terraform export's instance type, AWS's first region, a month of hours.
DEFAULTS: dict[str, Any] = {
    "instance_type": "t3.micro",
    "region": "us-east-1",
    "os": "Linux",
    "count": 1,
    "hours": 730,
}
#: The operating systems a price file exists for, by the name a sizing may use.
OPERATING_SYSTEMS = {
    "linux": "Linux",
    "windows": "Windows",
    "rhel": "RHEL",
    "suse": "SUSE",
    "ubuntu pro": "Ubuntu Pro",
}
PRICE_FILE = (
    "https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/"
    "ec2-ondemand-without-sec-sel/{location}/{os}/index.json"
)
LOCATIONS = "https://b0.p.awsstatic.com/locations/1.0/aws/current/locations.json"
#: A region code as AWS lists them: us-east-1, us-gov-west-1, eusc-de-east-1,
#: us-east-2-mci-1; never an availability zone (us-east-1a).
REGION = re.compile(r"\b([a-z]{2,4}(?:-[a-z]+)+-\d+(?:-[a-z]+-\d+)?)\b")
_INSTANCE_TYPE = re.compile(r"^[a-z][a-z0-9-]*\.[a-z0-9-]+$")

Fetch = Callable[[str], bytes]


def region_of(ancestors: tuple[TopologyElement, ...]) -> str | None:
    """The region of the innermost region frame around an element, from its
    caption (``us-east-1``, ``Region · eu-west-1``), as the Terraform export reads it."""
    for frame in reversed(ancestors):
        if frame.type == "region" and (match := REGION.search(frame.name)):
            return match.group(1)
    return None


def _json(fetch: Fetch, url: str) -> Any:
    try:
        value = json.loads(fetch(url))
    except ValueError as error:
        raise PricingError(f"{url} is not the JSON AWS publishes ({error})") from error
    if not isinstance(value, dict):
        raise PricingError(f"{url} is not the JSON AWS publishes (not an object)")
    return value


def location_name(region: str, fetch: Fetch) -> str:
    """The name AWS's price files give *region* (``eu-west-1`` -> ``EU (Ireland)``)."""
    locations = _json(fetch, LOCATIONS)
    for name, entry in locations.items() if isinstance(locations, dict) else ():
        if (
            isinstance(entry, dict)
            and entry.get("code") == region
            and entry.get("type") == "AWS Region"
        ):
            return str(entry.get("name") or name)
    raise PricingError(f"AWS lists no region {region!r}")


def _sizing(
    sizing: dict[str, Any], ancestors: tuple[TopologyElement, ...]
) -> tuple[dict[str, Any], list[str]]:
    values: dict[str, Any] = {}
    assumed: list[str] = []
    unknown = sorted(set(sizing) - set(DEFAULTS))
    if unknown:
        raise PricingError(f"EC2 sizing takes {', '.join(DEFAULTS)}, not {', '.join(unknown)}")
    for key, default in DEFAULTS.items():
        given = sizing.get(key)
        if key == "region" and given in (None, ""):
            given = region_of(ancestors)
        if given in (None, ""):
            values[key] = default
            assumed.append(key)
        else:
            values[key] = given
    if not isinstance(values["instance_type"], str) or not _INSTANCE_TYPE.match(
        values["instance_type"]
    ):
        raise PricingError(
            f"{values['instance_type']!r} is not an EC2 instance type (like t3.micro)"
        )
    if not isinstance(values["region"], str) or not REGION.fullmatch(values["region"]):
        raise PricingError(f"{values['region']!r} is not an AWS region (like us-east-1)")
    os_name = OPERATING_SYSTEMS.get(str(values["os"]).strip().lower())
    if os_name is None:
        raise PricingError(
            f"no EC2 price file for the operating system {values['os']!r}; "
            f"one of {', '.join(OPERATING_SYSTEMS.values())}"
        )
    values["os"] = os_name
    # the same rule as Ask.count and Ask.hours
    count, hours = values["count"], values["hours"]
    if (
        isinstance(count, bool)
        or not isinstance(count, (int, float))
        or not float(count).is_integer()
        or not 1 <= count <= MAX_COUNT
    ):
        raise PricingError(
            f"count must be a whole number of instances, 1 to {MAX_COUNT}, not {count!r}"
        )
    values["count"] = int(count)
    if (
        isinstance(hours, bool)
        or not isinstance(hours, (int, float))
        or not 1 <= hours <= MAX_HOURS
    ):
        raise PricingError(
            f"hours must be the hours a month it runs, 1 to {MAX_HOURS}, not {hours!r}"
        )
    return values, assumed


def price_ec2(
    sizing: dict[str, Any], ancestors: tuple[TopologyElement, ...], *, fetch: Fetch, today: str
) -> Price:
    """The on-demand price of the EC2 instances an element stands for."""
    values, assumed = _sizing(sizing, ancestors)
    location = location_name(values["region"], fetch)
    url = PRICE_FILE.format(location=quote(location, safe=""), os=quote(values["os"], safe=""))
    table = _json(fetch, url)
    try:
        rows = table["regions"][location]
        entries = list(rows.values())
    except (KeyError, TypeError, AttributeError) as error:
        raise PricingError(f"the price file for {location} lists no rates") from error
    rate = next(
        (
            row
            for row in entries
            if isinstance(row, dict) and row.get("Instance Type") == values["instance_type"]
        ),
        None,
    )
    if rate is None:
        raise PricingError(
            f"no on-demand {values['os']} rate for {values['instance_type']} in {values['region']}"
        )
    try:
        hourly = float(rate["price"])
    except (KeyError, TypeError, ValueError) as error:
        raise PricingError(f"the rate for {values['instance_type']} has no price") from error
    manifest = table.get("manifest") if isinstance(table.get("manifest"), dict) else {}
    published = str(manifest.get("hawkFilePublicationDate") or "")[:10]
    return Price(
        monthly=round(hourly * values["hours"] * values["count"], 2),
        hourly=hourly,
        currency=str(manifest.get("currencyCode") or "USD"),
        sizing=values,
        assumed=assumed,
        rate=f"EC2 on-demand, {values['os']}, shared tenancy"
        + (f", {rate.get('vCPU')} vCPU, {rate.get('Memory')}" if rate.get("vCPU") else ""),
        source="AWS price list (aws.amazon.com/ec2/pricing)",
        published=published,
        priced=today,
    )


# -- the table: AWS's price list, read once, priced with no network ----------
#
# The shipped table (``assets/prices/aws.json``) is built by
# :mod:`infragram.pricing.build.aws` from the AWS Price List API and the
# pricing pages' files. Every figure is the on-demand list price in US
# dollars, before the free tier, Savings Plans, reserved or spot rates.

#: The region key of what AWS prices once for the world.
GLOBAL = "global"
_PRICE_LIST = "AWS Price List API"
_BEFORE_FREE_TIER = "list price before the free tier"


class _Bill(BaseModel):
    """One element's price as it is added up, line by line."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    ask: Ask
    service: Service
    region: str
    sizing: dict[str, Any] = Field(default_factory=dict)
    lines: list[PriceLine] = Field(default_factory=list)
    hours_: float | None = None

    @classmethod
    def of(cls, ask: Ask, table: str, *, world: bool = False) -> _Bill:
        service = ask.table.service(table)
        if world:
            # priced once for the world: a region frame around it says nothing
            ask.taken.add("region")
            return cls(ask=ask, service=service, region=GLOBAL)
        region = ask.region()
        if region not in service.rates:
            near = [code for code in sorted(service.rates) if code[:2] == region[:2]]
            raise PricingError(
                f"{service.title} has no prices for region {region!r}"
                + (f"; it has {', '.join(near[:8])}" if near else "")
            )
        return cls(ask=ask, service=service, region=region, sizing={"region": region})

    # -- what the element says, or the default it is priced at

    def take(self, key: str, default: Any, **limits: Any) -> Any:
        value = self.ask.take(key, default, **limits)
        self.sizing[key] = value
        return value

    def number(
        self, key: str, default: float, *, low: float = 0, high: float | None = None
    ) -> float:
        return float(self.take(key, default, kind=(int, float), low=low, high=high))

    def count(self, key: str = "count", default: int = 1) -> int:
        value = self.ask.count(key, default)
        self.sizing[key] = value
        return value

    def given(self, key: str, *, low: float = 0, high: float | None = None) -> float | None:
        """A quantity priced only when the element states it."""
        if self.ask.sizing.get(key) in (None, ""):
            self.ask.taken.add(key)
            return None
        return self.number(key, 0, low=low, high=high)

    def choose(self, key: str, default: str, options: list[str]) -> str:
        if not options:
            word = key.replace("_", " ")
            raise PricingError(f"{self.service.title} offers no {word} in {self.region}")
        return str(self.take(key, default, kind=str, choices=options))

    def hours(self) -> float:
        if self.hours_ is None:
            self.hours_ = self.ask.hours()
            # a whole number of hours reads as one: 730, not 730.0
            self.sizing["hours"] = int(self.hours_) if self.hours_.is_integer() else self.hours_
        return self.hours_

    def assumed(self, *keys: str) -> bool:
        return self.ask.was_assumed(*keys)

    # -- the table's rates

    def tiers(
        self, item: str, *, service: Service | None = None, region: str | None = None
    ) -> list[tuple[float, float]]:
        service = service or self.service
        place = region or self.region
        service.rate(place, item, "0")
        node = service.rates[place][item]
        return sorted((float(start), float(rate)) for start, rate in node.items())

    def has(self, item: str) -> bool:
        return item in self.service.rates.get(self.region, {})

    def items(self) -> list[str]:
        return sorted(self.service.rates.get(self.region, {}))

    # -- lines

    def add(
        self,
        label: str,
        quantity: float,
        unit: str,
        item: str,
        *,
        per: float = 1.0,
        fixed: bool = False,
        keys: tuple[str, ...] = (),
        service: Service | None = None,
        region: str | None = None,
    ) -> None:
        """*quantity* of *unit*, at *item*'s tiered rate; *per* is how many
        of the table's units one *unit* is (a million requests)."""
        if quantity <= 0:
            return
        tiers = self.tiers(item, service=service, region=region)
        self.lines.extend(
            _tiered(label, quantity, unit, tiers, per=per, fixed=fixed, assumed=self.assumed(*keys))
        )

    def running(
        self,
        label: str,
        count: float,
        item: str,
        *,
        keys: tuple[str, ...] = ("count",),
        per_month: bool = False,
    ) -> None:
        """*count* resources billed by the hour (or by the month) all month."""
        if per_month:
            self.add(label, count, "months", item, fixed=True, keys=keys)
            return
        hours = self.hours()
        self.add(label, count * hours, "hours", item, fixed=True, keys=(*keys, "hours"))

    def rate(self, *values: str) -> float:
        return self.service.rate(self.region, *values)

    def price(self, rate: str) -> Price:
        return priced(
            self.ask,
            self.lines,
            sizing=self.sizing,
            rate=rate,
            source=f"{self.service.source}: {self.service.title}",
            published=self.service.published,
        )


def _tiered(
    label: str,
    quantity: float,
    unit: str,
    tiers: list[tuple[float, float]],
    *,
    per: float,
    fixed: bool,
    assumed: bool,
) -> list[PriceLine]:
    kind = "fixed" if fixed else "usage"
    native = quantity * per
    spans: list[tuple[float, float, float, float]] = []
    for index, (start, rate) in enumerate(tiers):
        end = tiers[index + 1][0] if index + 1 < len(tiers) else math.inf
        if index and native <= start:
            break
        spans.append((start, end, min(native, end) - start, rate))
    if len(spans) == 1:
        return [line(label, quantity, unit, spans[0][3] * per, kind=kind, assumed=assumed)]
    return [
        line(
            f"{label} ({_span(start, end, per, unit)})",
            part / per,
            unit,
            rate * per,
            kind=kind,
            assumed=assumed,
        )
        for start, end, part, rate in spans
    ]


def _span(start: float, end: float, per: float, unit: str) -> str:
    def amount(value: float) -> str:
        return f"{value / per:,.6g}"

    if start == 0:
        return f"first {amount(end)} {unit}"
    if math.isinf(end):
        return f"over {amount(start)} {unit}"
    return f"{amount(start)} to {amount(end)} {unit}"


def _described(bill: _Bill, key: str, value: str) -> str:
    words = bill.service.describe(key, value)
    return f", {words}" if words else ""


def _choices(service: Service, *path: str) -> list[str]:
    return service.choices(*path)


#: A size the way AWS's usage types shorten it (``db.r6g.2xl``).
_SHORT_SIZE = re.compile(r"^(db\..+\.)(\d*)xl$")


def _db_class(bill: _Bill, name: str) -> str:
    """A database instance class by AWS's own name (``db.r6g.2xlarge``);
    the short form a usage type writes (``db.r6g.2xl``) is read as it."""
    full = _SHORT_SIZE.sub(r"\1\2xlarge", name)
    if full != name:
        bill.sizing["instance_class"] = full
    return full


def _default(service: Service, path: tuple[str, ...], *preferred: str) -> str:
    """The size priced when the element names none: the first of *preferred*
    the region offers, else its cheapest."""
    options = service.choices(*path)
    found = next((option for option in preferred if option in options), None)
    if found is not None:
        return found
    node: Any = service.rates
    for value in path:
        node = node.get(value, {}) if isinstance(node, dict) else {}
    rated = [(rate, size) for size, rate in node.items() if isinstance(rate, (int, float))]
    return min(rated)[1] if rated else (preferred[0] if preferred else "")


def _first(options: list[str], *preferred: str) -> str:
    return next(
        (option for option in preferred if option in options), options[0] if options else ""
    )


# -- compute ------------------------------------------------------------------

#: EC2 operating systems the table holds, by the name a sizing uses.
_EC2_SYSTEMS = ["Linux", "Windows", "RHEL", "SUSE"]


def _ec2_hours(
    bill: _Bill,
    instance_type: str,
    system: str,
    count: float,
    *,
    label: str = "EC2 instance hours",
    keys: tuple[str, ...] = ("count", "instance_type", "os"),
) -> None:
    ec2 = bill.ask.table.service("ec2")
    rate = ec2.rate(bill.region, system, instance_type)
    hours = bill.hours()
    bill.lines.append(
        line(
            f"{label}, {instance_type}",
            count * hours,
            "hours",
            rate,
            kind="fixed",
            assumed=bill.assumed(*keys, "hours"),
        )
    )


def price_ec2_table(ask: Ask) -> Price:
    """EC2 instances: their type's on-demand hourly rate, an optional root volume."""
    bill = _Bill.of(ask, "ec2")
    system = bill.choose("os", "Linux", _EC2_SYSTEMS)
    instance_type = str(
        bill.take(
            "instance_type",
            _default(bill.service, (bill.region, system), DEFAULTS["instance_type"]),
            kind=str,
        )
    )
    count = bill.count()
    bill.service.rate(bill.region, system, instance_type)
    _ec2_hours(bill, instance_type, system, count)
    volume = bill.given("volume_gb", high=65536)
    if volume:
        ebs = ask.table.service("ebs")
        bill.add(
            "Root volume (gp3)",
            volume * count,
            "GB-month",
            "gp3",
            fixed=True,
            service=ebs,
            keys=("volume_gb",),
        )
    return bill.price(
        f"EC2 on-demand, {system}, shared tenancy{_described(bill, 'instance_type', instance_type)}"
    )


def price_ebs(ask: Ask) -> Price:
    """EBS volumes: GB-months by type, provisioned IOPS and throughput."""
    bill = _Bill.of(ask, "ebs")
    kind = bill.choose("volume_type", "gp3", ["gp3", "gp2", "io1", "io2", "st1", "sc1", "standard"])
    size = bill.number("size_gb", 100, low=1, high=65536)
    count = bill.count()
    bill.add(
        f"{kind} storage", size * count, "GB-month", kind, fixed=True, keys=("size_gb", "count")
    )
    if kind in ("io1", "io2"):
        iops = bill.number("iops", 3000, low=100, high=256000)
        # io2 IOPS tiers are per volume: priced volume by volume
        for _ in range(count if kind == "io2" else 1):
            bill.add(
                f"{kind} provisioned IOPS",
                iops if kind == "io2" else iops * count,
                "IOPS-month",
                f"{kind}-iops",
                fixed=True,
                keys=("iops",),
            )
    elif kind == "gp3":
        extra = bill.given("iops", low=3000, high=80000)
        if extra and extra > 3000:
            bill.add(
                "gp3 IOPS over the included 3,000",
                (extra - 3000) * count,
                "IOPS-month",
                "gp3-iops",
                fixed=True,
            )
        throughput = bill.given("throughput_mbps", low=125, high=2000)
        if throughput and throughput > 125:
            bill.add(
                "gp3 throughput over the included 125 MiB/s",
                (throughput - 125) * count,
                "MiB/s-month",
                "gp3-throughput",
                per=1 / 1024,
                fixed=True,
            )
    return bill.price(f"EBS {kind} volume, on-demand")


def price_ebs_snapshot(ask: Ask) -> Price:
    bill = _Bill.of(ask, "ebs")
    tier = bill.choose("tier", "standard", ["standard", "archive"])
    size = bill.number("size_gb", 100, high=10_000_000)
    bill.add(
        f"EBS snapshot storage ({tier})",
        size,
        "GB-month",
        "snapshot" if tier == "standard" else "snapshot-archive",
        keys=("size_gb",),
    )
    return bill.price("EBS snapshot storage, changed blocks kept")


def price_public_ip(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    count = bill.count("addresses")
    bill.running("Public IPv4 address hours", count, "public-ipv4", keys=("addresses",))
    return bill.price("Public IPv4 address, in use or idle, per hour")


def _emr_fee(bill: _Bill, instance_type: str, count: float) -> None:
    emr = bill.ask.table.service("emr")
    bill.lines.append(
        line(
            f"EMR fee, {instance_type}",
            count * bill.hours(),
            "hours",
            emr.rate(bill.region, instance_type),
            kind="fixed",
            assumed=bill.assumed("count", "instance_type", "hours"),
        )
    )


def price_emr(ask: Ask) -> Price:
    """EMR on EC2: each instance's EC2 rate plus EMR's own per-instance fee."""
    bill = _Bill.of(ask, "emr")
    instance_type = str(
        bill.take(
            "instance_type",
            _default(bill.service, (bill.region,), "m5.xlarge", "m6g.xlarge", "m7g.xlarge"),
            kind=str,
        )
    )
    count = bill.count()
    bill.rate(instance_type)
    _ec2_hours(bill, instance_type, "Linux", count)
    _emr_fee(bill, instance_type, count)
    return bill.price(f"EMR on EC2, on-demand{_described(bill, 'instance_type', instance_type)}")


def price_eks(ask: Ask) -> Price:
    """An EKS cluster's hours by support tier, and its nodes as EC2 when given."""
    bill = _Bill.of(ask, "eks")
    tier = bill.choose("support", "standard", ["standard", "extended"])
    clusters = bill.count("clusters")
    bill.running("EKS cluster hours", clusters, "cluster-hour", keys=("clusters",))
    if tier == "extended":
        bill.running(
            "EKS extended support hours", clusters, "extended-support-hour", keys=("clusters",)
        )
    nodes = bill.given("nodes", high=100000)
    if nodes:
        instance_type = str(bill.take("instance_type", "m5.large", kind=str))
        _ec2_hours(
            bill,
            instance_type,
            "Linux",
            nodes,
            label="Node hours (EC2)",
            keys=("nodes", "instance_type"),
        )
    else:
        bill.ask.taken.add("instance_type")
        if bill.ask.sizing.get("instance_type") not in (None, ""):
            raise PricingError(f"{ask.name}: instance_type prices nodes; say how many nodes too")
    return bill.price(
        f"EKS {tier} support cluster" + (", nodes as EC2 on-demand Linux" if nodes else "")
    )


def price_fargate(ask: Ask) -> Price:
    """Fargate tasks: vCPU-hours and GB-hours, by architecture and OS."""
    bill = _Bill.of(ask, "fargate")
    system = bill.choose("os", "Linux", ["Linux", "Windows"])
    arch = bill.choose("arch", "x86", ["x86", "arm"])
    tasks = bill.count("tasks")
    vcpu = bill.number("vcpu", 0.25, low=0.25, high=16)
    memory = bill.number("memory_gb", 0.5, low=0.5, high=120)
    hours = bill.hours()
    prefix = "windows-" if system == "Windows" else ("arm-" if arch == "arm" else "")
    if system == "Windows" and arch == "arm":
        raise PricingError(f"{ask.name}: Fargate runs Windows on x86 only")
    bill.add(
        "vCPU hours",
        tasks * vcpu * hours,
        "vCPU-hours",
        f"{prefix}vcpu-hour",
        fixed=True,
        keys=("tasks", "vcpu", "hours"),
    )
    bill.add(
        "Memory GB-hours",
        tasks * memory * hours,
        "GB-hours",
        f"{prefix}gb-hour",
        fixed=True,
        keys=("tasks", "memory_gb", "hours"),
    )
    if system == "Windows":
        bill.add(
            "Windows licence vCPU hours",
            tasks * vcpu * hours,
            "vCPU-hours",
            "windows-license-vcpu-hour",
            fixed=True,
            keys=("tasks", "vcpu", "hours"),
        )
    storage = bill.given("storage_gb", low=20, high=200)
    if storage and storage > 20:
        bill.add(
            "Ephemeral storage over the included 20 GB",
            tasks * (storage - 20) * hours,
            "GB-hours",
            "ephemeral-gb-hour",
            fixed=True,
        )
    return bill.price(f"Fargate, {system}, {arch}, on-demand")


def price_ecs_anywhere(ask: Ask) -> Price:
    bill = _Bill.of(ask, "fargate")
    instances = bill.count("instances")
    bill.running(
        "ECS Anywhere instance hours", instances, "anywhere-instance-hour", keys=("instances",)
    )
    return bill.price("ECS Anywhere, per registered instance hour")


def price_lambda(ask: Ask) -> Price:
    """Lambda: requests and GB-seconds of duration, by architecture."""
    bill = _Bill.of(ask, "lambda")
    arch = bill.choose("arch", "x86", ["x86", "arm"])
    requests = bill.number("requests_millions", 1, high=1_000_000)
    memory = bill.number("memory_mb", 128, low=128, high=10240)
    duration = bill.number("duration_ms", 200, low=1, high=900_000)
    suffix = "-arm" if arch == "arm" else ""
    bill.add(
        "Requests",
        requests,
        "1M requests",
        f"requests{suffix}",
        per=1e6,
        keys=("requests_millions",),
    )
    seconds = requests * 1e6 * duration / 1000 * memory / 1024
    bill.add(
        "Duration",
        seconds,
        "GB-seconds",
        f"gb-second{suffix}",
        keys=("requests_millions", "duration_ms", "memory_mb"),
    )
    storage = bill.given("ephemeral_mb", low=512, high=10240)
    if storage and storage > 512:
        extra = requests * 1e6 * duration / 1000 * (storage - 512) / 1024
        bill.add(
            "Ephemeral storage over the included 512 MB",
            extra,
            "GB-seconds",
            f"ephemeral-gb-second{suffix}",
        )
    return bill.price(f"Lambda, {arch}, {_BEFORE_FREE_TIER}")


def price_app_runner(ask: Ask) -> Price:
    bill = _Bill.of(ask, "app-runner")
    instances = bill.count("instances")
    vcpu = bill.number("vcpu", 1, low=0.25, high=4)
    memory = bill.number("memory_gb", 2, low=0.5, high=12)
    hours = bill.hours()
    bill.add(
        "Active vCPU hours",
        instances * vcpu * hours,
        "vCPU-hours",
        "vcpu-hour",
        fixed=True,
        keys=("instances", "vcpu", "hours"),
    )
    bill.add(
        "Active memory GB-hours",
        instances * memory * hours,
        "GB-hours",
        "gb-hour",
        fixed=True,
        keys=("instances", "memory_gb", "hours"),
    )
    return bill.price("App Runner, instances active all their hours")


# -- networking ---------------------------------------------------------------


def price_nat_gateway(ask: Ask) -> Price:
    bill = _Bill.of(ask, "nat-gateway")
    gateways = bill.count("gateways")
    data = bill.number("data_gb", 100, high=1e9)
    bill.running("NAT gateway hours", gateways, "hour", keys=("gateways",))
    bill.add("Data processed", data, "GB", "gb", keys=("data_gb",))
    return bill.price("NAT gateway, per hour and per GB processed")


_LOAD_BALANCERS = {"application": "alb", "network": "nlb", "gateway": "gwlb", "classic": "clb"}


def _load_balancer(default: str) -> Pricer:
    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "elb")
        kind = bill.choose("type", default, list(_LOAD_BALANCERS))
        code = _LOAD_BALANCERS[kind]
        balancers = bill.count("load_balancers")
        bill.running(
            f"{kind.title()} Load Balancer hours",
            balancers,
            f"{code}-hour",
            keys=("load_balancers",),
        )
        if kind == "classic":
            data = bill.number("data_gb", 100, high=1e9)
            bill.add("Data processed", data, "GB", "clb-gb", keys=("data_gb",))
            capacity = "per hour and per GB processed"
        else:
            units = bill.number("capacity_units", 1, high=100000)
            bill.add(
                "Capacity unit hours" if kind != "network" else "NLCU hours",
                units * balancers * bill.hours(),
                "LCU-hours",
                f"{code}-lcu",
                keys=("capacity_units", "load_balancers", "hours"),
            )
            capacity = "per hour and per capacity unit hour"
        return bill.price(f"{kind.title()} Load Balancer, {capacity}")

    return price


def price_vpc_endpoint(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    kind = bill.choose("type", "interface", ["interface", "gateway-load-balancer"])
    prefix = "endpoint" if kind == "interface" else "gwlb-endpoint"
    endpoints = bill.count("endpoints")
    zones = bill.count("zones", 2)
    data = bill.number("data_gb", 10, high=1e9)
    bill.running(
        "Endpoint hours, per zone", endpoints * zones, f"{prefix}-hour", keys=("endpoints", "zones")
    )
    bill.add("Data processed", data, "GB", f"{prefix}-gb", keys=("data_gb",))
    return bill.price(f"PrivateLink {kind} endpoint, per zone hour and per GB")


def price_transit_gateway(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    attachments = bill.count("attachments", 2)
    data = bill.number("data_gb", 100, high=1e9)
    bill.running("Attachment hours", attachments, "tgw-attachment-hour", keys=("attachments",))
    bill.add("Data processed", data, "GB", "tgw-gb", keys=("data_gb",))
    return bill.price("Transit Gateway, per attachment hour and per GB")


def price_transit_gateway_attachment(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    attachments = bill.count("attachments")
    bill.running("Attachment hours", attachments, "tgw-attachment-hour", keys=("attachments",))
    data = bill.given("data_gb", high=1e9)
    if data:
        bill.add("Data processed", data, "GB", "tgw-gb", keys=("data_gb",))
    return bill.price("Transit Gateway attachment, per hour")


def price_site_to_site_vpn(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    size = bill.choose("bandwidth", "standard", ["standard", "large"])
    connections = bill.count("connections")
    bill.running(
        "VPN connection hours",
        connections,
        "vpn-hour" if size == "standard" else "vpn-large-hour",
        keys=("connections",),
    )
    return bill.price(f"Site-to-Site VPN, {size} connection, per hour")


def price_client_vpn(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    associations = bill.count("subnet_associations")
    connection_hours = bill.number("connection_hours", 1760, high=1e8)
    bill.running(
        "Endpoint association hours",
        associations,
        "client-vpn-endpoint-hour",
        keys=("subnet_associations",),
    )
    bill.add(
        "Connection hours",
        connection_hours,
        "hours",
        "client-vpn-connection-hour",
        keys=("connection_hours",),
    )
    return bill.price("Client VPN, per subnet association hour and per connection hour")


def price_traffic_mirroring(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    sessions = bill.count("sources")
    bill.running("Mirrored interface hours", sessions, "traffic-mirroring-hour", keys=("sources",))
    return bill.price("Traffic Mirroring, per source interface hour")


def price_reachability(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    runs = bill.number("analyses", 10, high=1e7)
    bill.add("Analyses", runs, "analyses", "reachability-analysis", keys=("analyses",))
    return bill.price("Reachability Analyzer, per analysis")


def price_access_analyzer(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    interfaces = bill.number("interfaces", 100, high=1e8)
    bill.add(
        "Network interfaces analysed",
        interfaces,
        "interfaces",
        "access-analysis-eni",
        keys=("interfaces",),
    )
    return bill.price("Network Access Analyzer, per interface analysed")


def price_lattice(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    services = bill.count("services")
    data = bill.number("data_gb", 10, high=1e9)
    requests = bill.number("requests_millions", 1, high=1e6)
    bill.running("Service hours", services, "lattice-service-hour", keys=("services",))
    bill.add("Data processed", data, "GB", "lattice-gb", keys=("data_gb",))
    bill.add(
        "Requests", requests, "1M requests", "lattice-request", per=1e6, keys=("requests_millions",)
    )
    return bill.price(f"VPC Lattice, {_BEFORE_FREE_TIER}")


def price_verified_access(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    applications = bill.count("applications")
    data = bill.number("data_gb", 10, high=1e9)
    bill.running(
        "Application hours", applications, "verified-access-app-hour", keys=("applications",)
    )
    bill.add("Data processed", data, "GB", "verified-access-gb", keys=("data_gb",))
    return bill.price("Verified Access, per application hour and per GB")


def price_vpc_peering(ask: Ask) -> Price:
    bill = _Bill.of(ask, "vpc")
    data = bill.number("data_gb", 100, high=1e9)
    bill.add("Data across availability zones", data, "GB", "peering-gb", keys=("data_gb",))
    return bill.price("VPC peering within a region, per GB each way across zones")


def price_network_firewall(ask: Ask) -> Price:
    bill = _Bill.of(ask, "network-firewall")
    endpoints = bill.count("endpoints")
    data = bill.number("data_gb", 100, high=1e9)
    bill.running("Firewall endpoint hours", endpoints, "endpoint-hour", keys=("endpoints",))
    bill.add("Traffic processed", data, "GB", "gb", keys=("data_gb",))
    return bill.price("Network Firewall, per endpoint hour and per GB")


def price_direct_connect(ask: Ask) -> Price:
    bill = _Bill.of(ask, "direct-connect")
    ports = [item for item in bill.items() if item != "data-out"]
    port = bill.choose("port", _first(ports, "Dedicated 1G", "Hosted 1G"), ports)
    count = bill.count("ports")
    data = bill.number("data_out_gb", 100, high=1e9)
    bill.running(f"{port} port hours", count, port, keys=("ports", "port"))
    if bill.has("data-out"):
        bill.add("Data transfer out", data, "GB", "data-out", keys=("data_out_gb",))
    return bill.price(f"Direct Connect {port} port, as most of the region's locations price it")


def price_global_accelerator(ask: Ask) -> Price:
    bill = _Bill.of(ask, "global-accelerator", world=True)
    pairs = sorted(item.split(" ", 1)[1] for item in bill.items() if item.startswith("premium "))
    pair = bill.choose("traffic", "NA-NA", pairs)
    accelerators = bill.count("accelerators")
    data = bill.number("data_gb", 100, high=1e9)
    bill.running("Accelerator hours", accelerators, "accelerator-hour", keys=("accelerators",))
    bill.add(
        f"Data transfer premium, {pair}, dominant direction",
        data,
        "GB",
        f"premium {pair}",
        keys=("data_gb", "traffic"),
    )
    return bill.price("Global Accelerator, fixed hourly fee and data transfer premium")


def price_cloudfront(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cloudfront", world=True)
    areas = sorted(bill.service.rates)
    area = bill.choose("area", "United States", areas)
    bill.region = area
    data = bill.number("data_out_gb", 100, high=1e10)
    requests = bill.number("requests_millions", 1, high=1e7)
    bill.add("Data transfer out to the internet", data, "GB", "data-out", keys=("data_out_gb",))
    bill.add(
        "HTTPS requests",
        requests,
        "1M requests",
        "https-request",
        per=1e6,
        keys=("requests_millions",),
    )
    return bill.price(f"CloudFront pay-as-you-go, served from {area}, {_BEFORE_FREE_TIER}")


def price_cloudfront_functions(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cloudfront", world=True)
    bill.region = "United States"
    invocations = bill.number("invocations_millions", 1, high=1e7)
    bill.add(
        "Function invocations",
        invocations,
        "1M invocations",
        "function",
        per=1e6,
        keys=("invocations_millions",),
    )
    return bill.price(f"CloudFront Functions, {_BEFORE_FREE_TIER}")


def price_route53_zone(ask: Ask) -> Price:
    bill = _Bill.of(ask, "route53", world=True)
    routing = bill.choose("routing", "standard", ["standard", "latency", "geo", "ip-based"])
    zones = bill.count("hosted_zones")
    queries = bill.number("queries_millions", 1, high=1e7)
    bill.add("Hosted zones", zones, "zones", "hosted-zone", fixed=True, keys=("hosted_zones",))
    bill.add(
        f"{routing.title()} queries",
        queries,
        "1M queries",
        f"query-{routing}",
        per=1e6,
        keys=("queries_millions",),
    )
    checks = bill.given("health_checks", high=1e6)
    if checks:
        bill.add("Health checks (AWS endpoints)", checks, "checks", "health-check-aws", fixed=True)
    return bill.price(f"Route 53 hosted zone and queries, {_BEFORE_FREE_TIER}")


def price_route53_resolver(ask: Ask) -> Price:
    bill = _Bill.of(ask, "route53")
    addresses = bill.count("endpoint_ips", 2)
    bill.running(
        "Resolver endpoint IP address hours",
        addresses,
        "resolver-endpoint-hour",
        keys=("endpoint_ips",),
    )
    queries = bill.given("queries_millions", high=1e7)
    if queries:
        bill.add("Queries through the endpoints", queries, "1M queries", "resolver-query", per=1e6)
    return bill.price("Route 53 Resolver endpoints, per IP address hour")


def price_dns_firewall(ask: Ask) -> Price:
    bill = _Bill.of(ask, "route53")
    queries = bill.number("queries_millions", 1, high=1e7)
    bill.add(
        "Queries inspected",
        queries,
        "1M queries",
        "dns-firewall-query",
        per=1e6,
        keys=("queries_millions",),
    )
    domains = bill.given("domains", high=1e9)
    if domains:
        bill.add("Domains in lists", domains, "domains", "dns-firewall-domain", fixed=True)
    return bill.price("Route 53 Resolver DNS Firewall, per query and per listed domain")


def price_waf(ask: Ask) -> Price:
    bill = _Bill.of(ask, "waf")
    acls = bill.count("web_acls")
    rules = bill.number("rules", 5, high=10000)
    requests = bill.number("requests_millions", 1, high=1e7)
    bill.add("Web ACLs", acls, "web ACL-months", "web-acl", fixed=True, keys=("web_acls",))
    bill.add("Rules", rules, "rule-months", "rule", fixed=True, keys=("rules",))
    bill.add(
        "Requests inspected",
        requests,
        "1M requests",
        "request",
        per=1e6,
        keys=("requests_millions",),
    )
    return bill.price("AWS WAF, per web ACL, per rule and per request")


def price_waf_rule(ask: Ask) -> Price:
    bill = _Bill.of(ask, "waf")
    rules = bill.count("rules")
    bill.add("Rules", rules, "rule-months", "rule", fixed=True, keys=("rules",))
    return bill.price("AWS WAF rule or managed rule group, per month")


def price_waf_bot_control(ask: Ask) -> Price:
    bill = _Bill.of(ask, "waf")
    acls = bill.count("web_acls")
    requests = bill.number("requests_millions", 1, high=1e7)
    bill.add(
        "Bot Control subscriptions",
        acls,
        "web ACL-months",
        "bot-control",
        fixed=True,
        keys=("web_acls",),
    )
    bill.add(
        "Requests inspected",
        requests,
        "1M requests",
        "bot-control-request",
        per=1e6,
        keys=("requests_millions",),
    )
    return bill.price(f"AWS WAF Bot Control, common level, {_BEFORE_FREE_TIER}")


def price_shield_advanced(ask: Ask) -> Price:
    bill = _Bill.of(ask, "shield", world=True)
    bill.add("Shield Advanced subscription", 1, "months", "advanced-month", fixed=True)
    return bill.price(
        "Shield Advanced, monthly subscription per organization (data transfer out extra)"
    )


# -- storage ------------------------------------------------------------------

_S3_CLASSES = {
    "Standard": "standard",
    "Intelligent-Tiering": "intelligent-tiering",
    "Standard-IA": "standard-ia",
    "One Zone-IA": "one-zone-ia",
    "Express One Zone": "express-one-zone",
    "Glacier Instant Retrieval": "glacier-instant-retrieval",
    "Glacier Flexible Retrieval": "glacier-flexible-retrieval",
    "Glacier Deep Archive": "glacier-deep-archive",
    "Tables": "tables",
}


def _s3(default: str) -> Pricer:
    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "s3")
        storage_class = bill.choose("storage_class", default, list(_S3_CLASSES))
        code = _S3_CLASSES[storage_class]
        size = bill.number("storage_gb", 100, high=1e10)
        reads = bill.number("read_requests_millions", 1, high=1e7)
        writes = bill.given("write_requests_millions", high=1e7)
        out = bill.number("data_out_gb", 10, high=1e10)
        bill.add(
            f"{storage_class} storage", size, "GB-month", f"storage-{code}", keys=("storage_gb",)
        )
        bill.add(
            "GET and other requests",
            reads,
            "1M requests",
            f"read-{code}",
            per=1e6,
            keys=("read_requests_millions",),
        )
        if writes:
            bill.add(
                "PUT, COPY, POST and LIST requests", writes, "1M requests", f"write-{code}", per=1e6
            )
        if bill.has(f"retrieval-{code}"):
            retrieved = bill.given("retrieved_gb", high=1e10)
            if retrieved:
                bill.add("Data retrieved", retrieved, "GB", f"retrieval-{code}")
        if code == "intelligent-tiering":
            objects = bill.given("objects_thousands", high=1e9)
            if objects:
                bill.add(
                    "Monitoring and automation",
                    objects,
                    "1,000 objects",
                    "monitoring-intelligent-tiering",
                    per=1000,
                )
        transfer = bill.ask.table.service("data-transfer")
        bill.add(
            "Data transfer out to the internet",
            out,
            "GB",
            "internet-out",
            service=transfer,
            keys=("data_out_gb",),
        )
        return bill.price(f"S3 {storage_class}, {_BEFORE_FREE_TIER}")

    return price


def price_efs(default: str) -> Pricer:
    classes = {
        "Standard": "standard",
        "Standard-IA": "standard-ia",
        "Archive": "archive",
        "One Zone": "one-zone",
        "One Zone-IA": "one-zone-ia",
    }

    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "efs")
        storage_class = bill.choose("storage_class", default, list(classes))
        size = bill.number("storage_gb", 100, high=1e10)
        bill.add(
            f"EFS {storage_class} storage",
            size,
            "GB-month",
            classes[storage_class],
            keys=("storage_gb",),
        )
        reads = bill.given("read_gb", high=1e10)
        writes = bill.given("write_gb", high=1e10)
        if reads:
            bill.add("Elastic throughput reads", reads, "GB", "elastic-read")
        if writes:
            bill.add("Elastic throughput writes", writes, "GB", "elastic-write")
        return bill.price(f"EFS {storage_class}, elastic throughput")

    return price


def price_efs_throughput(ask: Ask) -> Price:
    bill = _Bill.of(ask, "efs")
    reads = bill.number("read_gb", 100, high=1e10)
    writes = bill.number("write_gb", 10, high=1e10)
    bill.add("Elastic throughput reads", reads, "GB", "elastic-read", keys=("read_gb",))
    bill.add("Elastic throughput writes", writes, "GB", "elastic-write", keys=("write_gb",))
    return bill.price("EFS elastic throughput, per GB read and written")


_FSX = {
    # file system: (deployment, storage type, storage GB, throughput MiB/s)
    "Windows": ("Single-AZ", "SSD", 32, 32),
    "ONTAP": ("Multi-AZ", "SSD", 1024, 128),
    "OpenZFS": ("Single-AZ", "SSD", 64, 64),
    "Lustre": ("Persistent", "SSD 125", 1200, 0),
}


def _fsx(system: str) -> Pricer:
    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "fsx")
        deployment_default, kind_default, size_default, throughput_default = _FSX[system]
        prefix = f"{system} "
        storage = sorted(
            {
                item[len(prefix) :].split(" storage ")[0]
                for item in bill.items()
                if item.startswith(prefix) and " storage " in item
            }
        )
        deployment = bill.choose("deployment", _first(storage, deployment_default), storage)
        kinds = sorted(
            item.split(" storage ", 1)[1]
            for item in bill.items()
            if item.startswith(f"{prefix}{deployment} storage ")
        )
        kind = bill.choose("storage_type", _first(kinds, kind_default), kinds)
        size = bill.number("storage_gb", size_default, high=1e8)
        bill.add(
            f"{kind} storage",
            size,
            "GB-month",
            f"{prefix}{deployment} storage {kind}",
            fixed=True,
            keys=("storage_gb",),
        )
        if bill.has(f"{prefix}{deployment} throughput") and (
            system != "Lustre" or "throughput_mbps" in ask.sizing
        ):
            throughput = bill.number(
                "throughput_mbps", throughput_default or 64, low=1, high=100000
            )
            bill.add(
                "Throughput capacity",
                throughput,
                "MiB/s-months",
                f"{prefix}{deployment} throughput",
                fixed=True,
                keys=("throughput_mbps",),
            )
        else:
            bill.ask.taken.add("throughput_mbps")
        iops = bill.given("iops", high=1e7)
        if iops and bill.has(f"{prefix}{deployment} iops"):
            bill.add(
                "Provisioned SSD IOPS",
                iops,
                "IOPS-months",
                f"{prefix}{deployment} iops",
                fixed=True,
            )
        backup = bill.given("backup_gb", high=1e9)
        if backup and bill.has(f"{system} backup"):
            bill.add("Backups", backup, "GB-month", f"{system} backup")
        return bill.price(f"FSx for {system}, {deployment}, {kind}")

    return price


def price_backup(ask: Ask) -> Price:
    bill = _Bill.of(ask, "backup")
    names = {item.split("-", 1)[1] for item in bill.items()}
    resources = sorted(names | {"ebs"})
    resource = bill.choose("resource", "ebs", resources)
    tier = bill.choose("tier", "warm", ["warm", "cold"])
    size = bill.number("storage_gb", 100, high=1e10)
    if resource == "ebs":
        ebs = ask.table.service("ebs")
        item = "snapshot" if tier == "warm" else "snapshot-archive"
        bill.add("EBS snapshot storage", size, "GB-month", item, service=ebs, keys=("storage_gb",))
    else:
        bill.add(
            f"{resource} backup storage ({tier})",
            size,
            "GB-month",
            f"{tier}-{resource}",
            keys=("storage_gb",),
        )
    return bill.price(f"AWS Backup, {resource} backups, {tier} storage")


def price_ecr(ask: Ask) -> Price:
    bill = _Bill.of(ask, "ecr")
    size = bill.number("storage_gb", 10, high=1e9)
    bill.add("Image storage", size, "GB-month", "storage", keys=("storage_gb",))
    return bill.price(f"ECR private image storage, {_BEFORE_FREE_TIER}")


def price_storage_gateway(kind: str) -> Pricer:
    items = {"volume": "volume-storage", "tape": "tape-storage"}

    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "storage-gateway")
        size = bill.number("storage_gb", 100, high=1e10)
        bill.add(
            f"{kind.title()} storage in AWS", size, "GB-month", items[kind], keys=("storage_gb",)
        )
        uploaded = bill.given("uploaded_gb", high=1e10)
        if uploaded:
            bill.add("Data written to AWS", uploaded, "GB", "uploaded-gb")
        return bill.price(f"Storage Gateway, {kind} storage")

    return price


def price_datasync(ask: Ask) -> Price:
    bill = _Bill.of(ask, "datasync")
    mode = bill.choose("mode", "basic", ["basic", "enhanced"])
    data = bill.number("data_gb", 100, high=1e10)
    bill.add(
        "Data copied", data, "GB", "gb" if mode == "basic" else "enhanced-gb", keys=("data_gb",)
    )
    return bill.price(f"DataSync, {mode} mode, per GB copied")


def price_transfer_family(default: str) -> Pricer:
    protocols = ["SFTP", "FTPS", "FTP", "AS2"]

    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "transfer")
        protocol = bill.choose("protocol", default, protocols)
        endpoints = bill.count("endpoints")
        bill.running(
            f"{protocol} endpoint hours", endpoints, f"{protocol.lower()}-hour", keys=("endpoints",)
        )
        if protocol == "AS2":
            messages = bill.number("messages_thousands", 1, high=1e7)
            bill.add(
                "AS2 messages",
                messages,
                "1,000 messages",
                "as2-message",
                per=1000,
                keys=("messages_thousands",),
            )
        else:
            up = bill.number("upload_gb", 10, high=1e10)
            down = bill.number("download_gb", 10, high=1e10)
            bill.add("Data uploaded", up, "GB", "upload-gb", keys=("upload_gb",))
            bill.add("Data downloaded", down, "GB", "download-gb", keys=("download_gb",))
        return bill.price(f"Transfer Family {protocol}, per endpoint hour and per GB")

    return price


# -- databases ----------------------------------------------------------------

_RDS_STORAGE = ["gp3", "gp2", "io1", "io2", "magnetic"]


def _rds(
    engine_default: str, deployment_default: str = "Single-AZ", storage_default: str = "gp3"
) -> Pricer:
    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "rds")
        engines = _choices(bill.service, bill.region)
        engine = bill.choose("engine", _first(engines, engine_default), engines)
        deployments = _choices(bill.service, bill.region, engine)
        deployment = bill.choose("deployment", _first(deployments, deployment_default), deployments)
        instance_class = str(
            bill.take(
                "instance_class",
                _default(
                    bill.service,
                    (bill.region, engine, deployment),
                    "db.t3.micro",
                    "db.t4g.micro",
                    "db.t3.small",
                    "db.t3.medium",
                    "db.t4g.medium",
                    "db.m6gd.large",
                    "db.m5d.large",
                    "db.r5.large",
                    "db.m5.large",
                ),
                kind=str,
            )
        )
        instance_class = _db_class(bill, instance_class)
        count = bill.count("instances")
        rate = bill.rate(engine, deployment, instance_class)
        hours = bill.hours()
        bill.lines.append(
            line(
                f"{engine} {deployment} instance hours, {instance_class}",
                count * hours,
                "hours",
                rate,
                kind="fixed",
                assumed=bill.assumed(
                    "instances", "instance_class", "engine", "deployment", "hours"
                ),
            )
        )
        usage = ask.table.service("rds-usage")
        size = bill.number("storage_gb", 20, low=1, high=128000)
        if engine.startswith("Aurora"):
            bill.ask.taken.update({"storage_type", "iops"})
            optimized = engine.endswith("I/O-Optimized")
            storage = "aurora-io-optimized storage" if optimized else "aurora storage"
            bill.add(
                "Aurora storage", size, "GB-month", storage, service=usage, keys=("storage_gb",)
            )
            if not optimized:
                io = bill.given("io_requests_millions", high=1e9)
                if io:
                    bill.add(
                        "I/O requests",
                        io,
                        "1M requests",
                        "aurora io-request",
                        per=1e6,
                        service=usage,
                    )
            else:
                bill.ask.taken.add("io_requests_millions")
        else:
            bill.ask.taken.add("io_requests_millions")
            volume = bill.choose("storage_type", storage_default, _RDS_STORAGE)
            if deployment == "Multi-AZ cluster" and volume in ("gp2", "magnetic"):
                raise PricingError(f"{ask.name}: a Multi-AZ DB cluster stores on gp3, io1 or io2")
            bill.add(
                f"{volume} storage",
                size * count,
                "GB-month",
                f"{deployment} {volume}",
                fixed=True,
                service=usage,
                keys=("storage_gb",),
            )
            if volume in ("io1", "io2"):
                iops = bill.number("iops", 1000, low=1000, high=256000)
                bill.add(
                    f"{volume} provisioned IOPS",
                    iops * count,
                    "IOPS-month",
                    f"{deployment} {volume}-iops",
                    fixed=True,
                    service=usage,
                    keys=("iops",),
                )
            else:
                wanted = bill.given("iops", high=256000)
                included = 3000 if size < 400 or engine.startswith("SQL Server") else 12000
                if volume == "gp3" and wanted and wanted > included:
                    bill.add(
                        f"gp3 IOPS over the included {included:,}",
                        (wanted - included) * count,
                        "IOPS-month",
                        f"{deployment} gp3-iops",
                        fixed=True,
                        service=usage,
                    )
        return bill.price(
            f"RDS {engine}, {deployment}, on-demand{_described(bill, 'instance_class', instance_class)}"
        )

    return price


def price_aurora_serverless(ask: Ask) -> Price:
    bill = _Bill.of(ask, "rds-usage")
    optimized = bill.choose("storage", "standard", ["standard", "io-optimized"]) == "io-optimized"
    capacity = bill.number("acus", 0.5, low=0, high=256)
    size = bill.number("storage_gb", 20, high=128000)
    hours = bill.hours()
    item = "aurora-serverless-io-optimized acu-hour" if optimized else "aurora-serverless acu-hour"
    bill.add(
        "Aurora capacity unit hours",
        capacity * hours,
        "ACU-hours",
        item,
        fixed=True,
        keys=("acus", "hours"),
    )
    bill.add(
        "Aurora storage",
        size,
        "GB-month",
        "aurora-io-optimized storage" if optimized else "aurora storage",
        keys=("storage_gb",),
    )
    return bill.price("Aurora Serverless v2, per ACU hour")


def price_rds_proxy(ask: Ask) -> Price:
    bill = _Bill.of(ask, "rds-usage")
    vcpus = bill.number("vcpus", 2, low=2, high=10000)
    bill.running(
        "Proxy vCPU hours (the database's vCPUs, two at least)",
        vcpus,
        "proxy vcpu-hour",
        keys=("vcpus",),
    )
    return bill.price("RDS Proxy, per vCPU hour of the database behind it")


def _nodes(
    table: str,
    title: str,
    key: str,
    default_node: str,
    *,
    engines: tuple[str, ...] = (),
    engine_default: str = "",
    count_key: str = "nodes",
    count_default: int = 1,
) -> Pricer:
    """A service priced by node hours: ElastiCache, MemoryDB, DAX, Redshift, MSK."""

    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, table)
        path: list[str] = []
        if engines:
            options = [
                engine for engine in engines if engine in _choices(bill.service, bill.region)
            ]
            engine = bill.choose("engine", _first(options, engine_default), options)
            path.append(engine)
        node = str(
            bill.take(key, _default(bill.service, (bill.region, *path), default_node), kind=str)
        )
        count = bill.count(count_key, count_default)
        rate = bill.rate(*path, node)
        bill.lines.append(
            line(
                f"{' '.join(path + [title])} node hours, {node}".strip(),
                count * bill.hours(),
                "hours",
                rate,
                kind="fixed",
                assumed=bill.assumed(count_key, key, "engine", "hours"),
            )
        )
        _extras(bill, table, count)
        return bill.price(f"{' '.join([title, *path])}, on-demand{_described(bill, key, node)}")

    return price


def _extras(bill: _Bill, table: str, count: int) -> None:
    """What a node-priced service bills besides its nodes."""
    ask = bill.ask
    if table == "redshift":
        storage = bill.number("managed_storage_gb", 100, high=1e9)
        node = str(bill.sizing.get("node_type", ""))
        if node.startswith("ra3"):
            usage = ask.table.service("redshift-usage")
            bill.add(
                "Redshift managed storage",
                storage,
                "GB-month",
                "managed-storage",
                service=usage,
                keys=("managed_storage_gb",),
            )
    elif table == "msk":
        usage = ask.table.service("msk-usage")
        node = str(bill.sizing.get("broker_type", ""))
        if node.startswith("express."):
            ask.taken.add("storage_gb")
            data = bill.number("data_in_gb", 100, high=1e10)
            bill.add(
                "Data written", data, "GB", "express-in-gb", service=usage, keys=("data_in_gb",)
            )
        else:
            ask.taken.add("data_in_gb")
            storage = bill.number("storage_gb", 100, low=1, high=16384)
            bill.add(
                "Broker storage",
                storage * count,
                "GB-month",
                "storage",
                fixed=True,
                service=usage,
                keys=("storage_gb",),
            )
    elif table == "memorydb":
        written = bill.given("data_written_gb", high=1e9)
        if written:
            usage = ask.table.service("memorydb-usage")
            engine = str(bill.sizing.get("engine", "Valkey")).lower()
            bill.add("Data written", written, "GB", f"{engine} data-written", service=usage)


def price_elasticache_serverless(ask: Ask, engine_default: str = "Valkey") -> Price:
    bill = _Bill.of(ask, "elasticache-usage")
    engine = bill.choose("engine", engine_default, ["Valkey", "Redis", "Memcached"]).lower()
    data = bill.number("data_gb", 1, low=0.1, high=5000)
    ecpus = bill.number("ecpus_millions", 100, high=1e9)
    bill.add(
        "Data stored",
        data * bill.hours(),
        "GB-hours",
        f"{engine} serverless-gb-hour",
        keys=("data_gb", "hours"),
    )
    bill.add(
        "ElastiCache Processing Units",
        ecpus,
        "1M ECPUs",
        f"{engine} serverless-ecpu",
        per=1e6,
        keys=("ecpus_millions",),
    )
    return bill.price(f"ElastiCache Serverless for {engine.title()}")


def _elasticache_serverless(engine_default: str) -> Pricer:
    return lambda ask: price_elasticache_serverless(ask, engine_default)


def _documents(table: str, title: str, default_class: str, unit: str) -> Pricer:
    """DocumentDB and Neptune: instance hours by storage mode, storage, I/O."""

    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, table)
        modes = _choices(bill.service, bill.region)
        mode = bill.choose("storage", _first(modes, "Standard"), modes)
        instance_class = str(
            bill.take(
                "instance_class",
                _default(bill.service, (bill.region, mode), default_class),
                kind=str,
            )
        )
        instance_class = _db_class(bill, instance_class)
        count = bill.count("instances")
        rate = bill.rate(mode, instance_class)
        bill.lines.append(
            line(
                f"{title} instance hours, {instance_class}",
                count * bill.hours(),
                "hours",
                rate,
                kind="fixed",
                assumed=bill.assumed("instances", "instance_class", "hours"),
            )
        )
        usage = ask.table.service(f"{table}-usage")
        size = bill.number("storage_gb", 10, high=1e6)
        optimized = mode == "I/O-Optimized"
        bill.add(
            "Storage",
            size,
            "GB-month",
            "storage-io-optimized" if optimized else "storage",
            service=usage,
            keys=("storage_gb",),
        )
        io = bill.given("io_requests_millions", high=1e9)
        if io and not optimized:
            bill.add("I/O requests", io, "1M requests", "io-request", per=1e6, service=usage)
        return bill.price(
            f"{title}, {mode} storage, on-demand{_described(bill, 'instance_class', instance_class)}"
        )

    return price


def price_docdb_elastic(ask: Ask) -> Price:
    bill = _Bill.of(ask, "docdb-usage")
    vcpus = bill.number("vcpus", 2, low=2, high=10000)
    size = bill.number("storage_gb", 10, high=1e7)
    bill.running("Shard vCPU hours", vcpus, "elastic-vcpu-hour", keys=("vcpus",))
    bill.add("Storage", size, "GB-month", "elastic-storage", keys=("storage_gb",))
    return bill.price("DocumentDB elastic cluster, per shard vCPU hour")


def price_dynamodb(table_class: str = "standard") -> Pricer:
    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "dynamodb")
        mode = bill.choose("capacity", "on-demand", ["on-demand", "provisioned"])
        klass = bill.choose("table_class", table_class, ["standard", "standard-ia"])
        suffix = "-ia" if klass == "standard-ia" else ""
        if mode == "on-demand":
            ask.taken.update({"read_capacity_units", "write_capacity_units"})
            reads = bill.number("reads_millions", 1, high=1e9)
            writes = bill.number("writes_millions", 1, high=1e9)
            bill.add(
                "Read request units",
                reads,
                "1M units",
                f"read-request{suffix}",
                per=1e6,
                keys=("reads_millions",),
            )
            bill.add(
                "Write request units",
                writes,
                "1M units",
                f"write-request{suffix}",
                per=1e6,
                keys=("writes_millions",),
            )
        else:
            ask.taken.update({"reads_millions", "writes_millions"})
            rcu = bill.number("read_capacity_units", 5, low=1, high=1e7)
            wcu = bill.number("write_capacity_units", 5, low=1, high=1e7)
            hours = bill.hours()
            bill.add(
                "Read capacity unit hours",
                rcu * hours,
                "RCU-hours",
                f"read-capacity-hour{suffix}",
                fixed=True,
                keys=("read_capacity_units", "hours"),
            )
            bill.add(
                "Write capacity unit hours",
                wcu * hours,
                "WCU-hours",
                f"write-capacity-hour{suffix}",
                fixed=True,
                keys=("write_capacity_units", "hours"),
            )
        size = bill.number("storage_gb", 10, high=1e9)
        bill.add("Table storage", size, "GB-month", f"storage{suffix}", keys=("storage_gb",))
        return bill.price(f"DynamoDB {mode}, {klass} table class, {_BEFORE_FREE_TIER}")

    return price


def price_dynamodb_stream(ask: Ask) -> Price:
    bill = _Bill.of(ask, "dynamodb")
    reads = bill.number("read_requests_millions", 1, high=1e9)
    bill.add(
        "Stream read requests",
        reads,
        "1M requests",
        "streams-read",
        per=1e6,
        keys=("read_requests_millions",),
    )
    return bill.price(f"DynamoDB Streams, {_BEFORE_FREE_TIER}")


def price_keyspaces(ask: Ask) -> Price:
    bill = _Bill.of(ask, "keyspaces")
    reads = bill.number("reads_millions", 1, high=1e9)
    writes = bill.number("writes_millions", 1, high=1e9)
    size = bill.number("storage_gb", 1, high=1e9)
    bill.add(
        "Read request units", reads, "1M units", "read-request", per=1e6, keys=("reads_millions",)
    )
    bill.add(
        "Write request units",
        writes,
        "1M units",
        "write-request",
        per=1e6,
        keys=("writes_millions",),
    )
    bill.add("Storage", size, "GB-month", "storage", keys=("storage_gb",))
    return bill.price("Keyspaces on-demand capacity")


def price_timestream(ask: Ask) -> Price:
    bill = _Bill.of(ask, "timestream")
    ingested = bill.number("ingested_gb", 1, high=1e9)
    tcu_hours = bill.number("query_tcu_hours", 10, high=1e9)
    bill.add("Data ingested", ingested, "GB", "ingested-gb", keys=("ingested_gb",))
    bill.add("Query compute", tcu_hours, "TCU-hours", "query-tcu-hour", keys=("query_tcu_hours",))
    return bill.price("Timestream for LiveAnalytics, ingestion and queries")


def price_opensearch(*defaults: str) -> Pricer:
    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "opensearch")
        instance_type = str(
            bill.take("instance_type", _default(bill.service, (bill.region,), *defaults), kind=str)
        )
        nodes = bill.count("nodes")
        rate = bill.rate(instance_type)
        bill.lines.append(
            line(
                f"OpenSearch instance hours, {instance_type}",
                nodes * bill.hours(),
                "hours",
                rate,
                kind="fixed",
                assumed=bill.assumed("nodes", "instance_type", "hours"),
            )
        )
        usage = ask.table.service("opensearch-usage")
        if instance_type.startswith("ultrawarm"):
            # UltraWarm keeps its data in managed storage, priced by the GB
            size = bill.number("storage_gb", 100, high=1e7)
            bill.add(
                "UltraWarm managed storage",
                size,
                "GB-month",
                "managed-storage",
                service=usage,
                keys=("storage_gb",),
            )
            ask.taken.add("volume_type")
        else:
            volume = bill.choose("volume_type", "gp3", ["gp3", "gp2", "io1", "magnetic"])
            size = bill.number("storage_gb", 10, low=10, high=1e6)
            bill.add(
                f"EBS {volume} storage",
                size * nodes,
                "GB-month",
                volume,
                fixed=True,
                service=usage,
                keys=("storage_gb", "nodes"),
            )
        return bill.price(
            f"OpenSearch Service, on-demand{_described(bill, 'instance_type', instance_type)}"
        )

    return price


def price_opensearch_ingestion(ask: Ask) -> Price:
    bill = _Bill.of(ask, "opensearch-usage")
    ocus = bill.number("ocus", 1, low=1, high=1000)
    bill.running("Ingestion OCU hours", ocus, "ingestion-ocu-hour", keys=("ocus",))
    return bill.price("OpenSearch Ingestion, per OCU hour")


# -- integration, analytics, management -----------------------------------------


def _usage(
    table: str, rate: str, *meters: tuple[str, str, str, str, float, float], world: bool = False
) -> Pricer:
    """A service billed only by what it serves: each meter is (sizing key,
    label, unit, table item, default, table units per unit)."""

    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, table, world=world)
        for key, label, unit, item, default, per in meters:
            quantity = bill.number(key, default, high=1e12)
            bill.add(label, quantity, unit, item, per=per, keys=(key,))
        return bill.price(rate)

    return price


def _monthly(
    table: str, rate: str, key: str, label: str, unit: str, item: str, default: int = 1
) -> Pricer:
    """A resource billed by the month, so many of them."""

    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, table)
        count = bill.count(key, default)
        bill.add(label, count, unit, item, fixed=True, keys=(key,))
        return bill.price(rate)

    return price


def _hourly(table: str, rate: str, key: str, label: str, item: str, default: int = 1) -> Pricer:
    """A resource billed by the hour, so many of them all month."""

    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, table)
        count = bill.count(key, default)
        bill.running(label, count, item, keys=(key,))
        return bill.price(rate)

    return price


def price_api_gateway(ask: Ask) -> Price:
    bill = _Bill.of(ask, "api-gateway")
    kind = bill.choose("api_type", "REST", ["REST", "HTTP", "WebSocket"])
    if kind == "WebSocket":
        messages = bill.number("messages_millions", 1, high=1e9)
        minutes = bill.number("connection_minutes_millions", 1, high=1e9)
        bill.add(
            "Messages",
            messages,
            "1M messages",
            "websocket-message",
            per=1e6,
            keys=("messages_millions",),
        )
        bill.add(
            "Connection minutes",
            minutes,
            "1M minutes",
            "websocket-minute",
            per=1e6,
            keys=("connection_minutes_millions",),
        )
        ask.taken.update({"requests_millions", "cache_gb"})
    else:
        ask.taken.add("messages_millions")
        ask.taken.add("connection_minutes_millions")
        requests = bill.number("requests_millions", 1, high=1e9)
        bill.add(
            f"{kind} API requests",
            requests,
            "1M requests",
            "rest-request" if kind == "REST" else "http-request",
            per=1e6,
            keys=("requests_millions",),
        )
        sizes = sorted(
            (item.split("-", 1)[1] for item in bill.items() if item.startswith("cache-")), key=float
        )
        cache = ask.sizing.get("cache_gb")
        ask.taken.add("cache_gb")
        if cache not in (None, ""):
            size = f"{float(cache):g}" if isinstance(cache, (int, float)) else str(cache).strip()
            if size not in sizes:
                raise PricingError(
                    f"{ask.name}: cache_gb {cache!r} is not one of {', '.join(sizes)}"
                )
            bill.sizing["cache_gb"] = size
            bill.running(f"Cache hours, {size} GB", 1, f"cache-{size}", keys=())
    return bill.price(f"API Gateway {kind} API, {_BEFORE_FREE_TIER}")


def price_sqs(ask: Ask) -> Price:
    bill = _Bill.of(ask, "sqs")
    kind = bill.choose("queue_type", "standard", ["standard", "fifo"])
    requests = bill.number("requests_millions", 1, high=1e9)
    bill.add(
        "Requests (64 KB chunks)",
        requests,
        "1M requests",
        f"{kind}-request",
        per=1e6,
        keys=("requests_millions",),
    )
    return bill.price(f"SQS {kind} queue, {_BEFORE_FREE_TIER}")


def price_sns(delivery: str = "") -> Pricer:
    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "sns")
        requests = bill.number("publishes_millions", 1, high=1e9)
        bill.add(
            "Publish requests",
            requests,
            "1M requests",
            "request",
            per=1e6,
            keys=("publishes_millions",),
        )
        if delivery == "http":
            deliveries = bill.number("http_deliveries_millions", 1, high=1e9)
            bill.add(
                "HTTP/S deliveries",
                deliveries,
                "1M deliveries",
                "delivery-http",
                per=1e6,
                keys=("http_deliveries_millions",),
            )
        elif delivery == "email":
            emails = bill.number("email_deliveries_thousands", 1, high=1e9)
            bill.add(
                "Email deliveries",
                emails,
                "1,000 deliveries",
                "delivery-email",
                per=1000,
                keys=("email_deliveries_thousands",),
            )
        return bill.price(f"SNS standard topic, {_BEFORE_FREE_TIER}")

    return price


def price_secrets_manager(ask: Ask) -> Price:
    bill = _Bill.of(ask, "secrets-manager")
    secrets = bill.count("secrets")
    calls = bill.number("api_calls_thousands", 10, high=1e9)
    bill.add("Secrets", secrets, "secret-months", "secret", fixed=True, keys=("secrets",))
    bill.add(
        "API calls",
        calls / 10,
        "10,000 calls",
        "api-request",
        per=10000,
        keys=("api_calls_thousands",),
    )
    return bill.price("Secrets Manager, per secret-month and per API call")


def price_kms(ask: Ask) -> Price:
    bill = _Bill.of(ask, "kms")
    keys = bill.count("keys")
    requests = bill.number("requests_thousands", 10, high=1e9)
    bill.add("Customer managed keys", keys, "key-months", "key", fixed=True, keys=("keys",))
    bill.add(
        "Symmetric requests",
        requests / 10,
        "10,000 requests",
        "request",
        per=10000,
        keys=("requests_thousands",),
    )
    return bill.price(f"KMS, per key-month and per request, {_BEFORE_FREE_TIER}")


def price_cloudwatch(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cloudwatch")
    metrics = bill.number("metrics", 10, high=1e8)
    alarms = bill.number("alarms", 5, high=1e7)
    ingested = bill.number("logs_ingested_gb", 10, high=1e9)
    stored = bill.number("logs_stored_gb", 10, high=1e10)
    bill.add("Custom metrics", metrics, "metric-months", "metric", fixed=True, keys=("metrics",))
    bill.add("Standard alarms", alarms, "alarm-months", "alarm", fixed=True, keys=("alarms",))
    bill.add("Logs ingested", ingested, "GB", "logs-ingested", keys=("logs_ingested_gb",))
    bill.add("Logs stored", stored, "GB-month", "logs-stored", keys=("logs_stored_gb",))
    dashboards = bill.given("dashboards", high=1e5)
    if dashboards:
        bill.add(
            "Dashboards", dashboards, "dashboard-months", "dashboard", fixed=True, region=GLOBAL
        )
    return bill.price(f"CloudWatch metrics, alarms and logs, {_BEFORE_FREE_TIER}")


def price_cloudwatch_alarm(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cloudwatch")
    resolution = bill.choose("resolution", "standard", ["standard", "high", "composite"])
    alarms = bill.count("alarms")
    item = {"standard": "alarm", "high": "alarm-high-resolution", "composite": "alarm-composite"}[
        resolution
    ]
    bill.add(
        f"{resolution.title()} alarms", alarms, "alarm-months", item, fixed=True, keys=("alarms",)
    )
    return bill.price(f"CloudWatch {resolution} alarm, {_BEFORE_FREE_TIER}")


def price_cloudwatch_logs(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cloudwatch")
    log_class = bill.choose("log_class", "standard", ["standard", "infrequent-access"])
    ingested = bill.number("ingested_gb", 10, high=1e9)
    stored = bill.number("stored_gb", 10, high=1e10)
    bill.add(
        "Logs ingested",
        ingested,
        "GB",
        "logs-ingested" if log_class == "standard" else "logs-ingested-ia",
        keys=("ingested_gb",),
    )
    bill.add("Logs stored", stored, "GB-month", "logs-stored", keys=("stored_gb",))
    scanned = bill.given("insights_scanned_gb", high=1e10)
    if scanned:
        bill.add("Logs Insights data scanned", scanned, "GB", "logs-scanned")
    return bill.price(f"CloudWatch Logs, {log_class} class, {_BEFORE_FREE_TIER}")


def price_cloudtrail(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cloudtrail")
    data_events = bill.number("data_events_millions", 1, high=1e9)
    bill.add(
        "Data events recorded",
        data_events,
        "100,000 events",
        "data-event",
        per=100000,
        keys=("data_events_millions",),
    )
    copies = bill.given("management_copies_millions", high=1e9)
    if copies:
        bill.add(
            "Further copies of management events",
            copies * 10,
            "100,000 events",
            "paid-event",
            per=100000,
        )
    return bill.price("CloudTrail; the first copy of management events is free")


def price_cloudtrail_lake(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cloudtrail")
    ingested = bill.number("ingested_gb", 10, high=1e9)
    scanned = bill.number("scanned_gb", 10, high=1e10)
    bill.add("Data ingested and stored", ingested, "GB", "lake-ingested-gb", keys=("ingested_gb",))
    bill.add("Data scanned by queries", scanned, "GB", "lake-scanned-gb", keys=("scanned_gb",))
    return bill.price("CloudTrail Lake, one-year extendable retention pricing")


def price_config(ask: Ask) -> Price:
    bill = _Bill.of(ask, "config")
    items = bill.number("configuration_items", 1000, high=1e9)
    evaluations = bill.number("rule_evaluations", 10000, high=1e10)
    bill.add(
        "Configuration items recorded",
        items,
        "items",
        "configuration-item",
        keys=("configuration_items",),
    )
    bill.add(
        "Rule evaluations",
        evaluations,
        "evaluations",
        "rule-evaluation",
        keys=("rule_evaluations",),
    )
    return bill.price("AWS Config, continuous recording")


def price_synthetics(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cloudwatch")
    runs = bill.number("canary_runs", 8640, high=1e9)
    bill.add("Canary runs", runs, "runs", "canary-run", keys=("canary_runs",))
    return bill.price(
        f"CloudWatch Synthetics, one canary every five minutes by default, {_BEFORE_FREE_TIER}"
    )


def price_glue(item: str, label: str, default: float = 10) -> Pricer:
    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "glue")
        dpu_hours = bill.number("dpu_hours", default, high=1e9)
        bill.add(label, dpu_hours, "DPU-hours", item, keys=("dpu_hours",))
        return bill.price(f"Glue, {label.lower()}")

    return price


def price_glue_catalog(ask: Ask) -> Price:
    bill = _Bill.of(ask, "glue")
    objects = bill.number("objects_thousands", 100, high=1e9)
    requests = bill.number("requests_millions", 1, high=1e9)
    bill.add(
        "Objects stored",
        objects / 100,
        "100,000 objects",
        "catalog-object",
        per=100000,
        keys=("objects_thousands",),
    )
    bill.add(
        "Requests", requests, "1M requests", "catalog-request", per=1e6, keys=("requests_millions",)
    )
    return bill.price(f"Glue Data Catalog, {_BEFORE_FREE_TIER}")


def price_mwaa(ask: Ask) -> Price:
    bill = _Bill.of(ask, "mwaa")
    sizes = ["Micro", "Small", "Medium", "Large", "XLarge", "2XLarge"]
    size = bill.choose("environment", "Small", sizes)
    environments = bill.count("environments")
    bill.running(
        f"{size} environment hours",
        environments,
        f"{size.lower()}-environment-hour",
        keys=("environments", "environment"),
    )
    workers = bill.given("extra_workers", high=1000)
    if workers and bill.has(f"{size.lower()}-worker-hour"):
        bill.running("Additional worker hours", workers, f"{size.lower()}-worker-hour", keys=())
    return bill.price(f"Managed Workflows for Apache Airflow, {size} environment")


def price_directory(default: str) -> Pricer:
    kinds = {
        "Managed AD Standard": "managed-ad-standard-hour",
        "Managed AD Enterprise": "managed-ad-enterprise-hour",
        "Simple AD Small": "simple-ad-small-hour",
        "Simple AD Large": "simple-ad-large-hour",
        "AD Connector Small": "ad-connector-small-hour",
        "AD Connector Large": "ad-connector-large-hour",
    }

    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "directory-service")
        kind = bill.choose("directory", default, list(kinds))
        if kind.startswith("Managed AD"):
            controllers = bill.count("domain_controllers", 2)
            bill.running(
                "Domain controller hours", controllers, kinds[kind], keys=("domain_controllers",)
            )
        else:
            ask.taken.add("domain_controllers")
            bill.running("Directory hours", 1, kinds[kind], keys=())
        return bill.price(f"Directory Service, {kind}")

    return price


def price_iot_core(ask: Ask) -> Price:
    bill = _Bill.of(ask, "iot-core")
    devices = bill.number("devices", 10, high=1e9)
    messages = bill.number("messages_millions", 1, high=1e9)
    minutes = devices * bill.hours() * 60 / 1e6
    bill.add(
        "Connection minutes",
        minutes,
        "1M minutes",
        "connection-minute",
        per=1e6,
        keys=("devices", "hours"),
    )
    bill.add("Messages", messages, "1M messages", "message", per=1e6, keys=("messages_millions",))
    return bill.price("IoT Core, devices connected all month")


def price_cloud_wan(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cloud-wan")
    edges = bill.count("edges")
    attachments = bill.count("attachments", 2)
    data = bill.number("data_gb", 100, high=1e10)
    bill.running("Core network edge hours", edges, "edge-hour", keys=("edges",))
    bill.running("VPC attachment hours", attachments, "attachment-hour", keys=("attachments",))
    bill.add("Data processed", data, "GB", "gb", keys=("data_gb",))
    return bill.price("Cloud WAN, per edge hour, per attachment hour and per GB")


def price_cloud_wan_attachment(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cloud-wan")
    attachments = bill.count("attachments")
    bill.running(
        "Transit Gateway route table attachment hours",
        attachments,
        "peering-hour",
        keys=("attachments",),
    )
    return bill.price("Cloud WAN Transit Gateway route table attachment, per hour")


def price_readiness_checks(ask: Ask) -> Price:
    bill = _Bill.of(ask, "recovery-controller", world=True)
    checks = bill.count("checks")
    bill.running("Readiness check hours", checks, "readiness-check-hour", keys=("checks",))
    return bill.price("Application Recovery Controller readiness checks, per check hour")


def price_routing_controls(ask: Ask) -> Price:
    bill = _Bill.of(ask, "recovery-controller", world=True)
    clusters = bill.count("clusters")
    bill.running("Cluster hours", clusters, "cluster-hour", keys=("clusters",))
    return bill.price("Application Recovery Controller routing control cluster, per hour")


#: What an Application Recovery Controller element is, each priced apart: a
#: routing control cluster by the hour, a Region switch plan by the month, a
#: readiness check by the hour (closed to new customers since 2026-04-30).
_ARC_FEATURES = ("routing controls", "region switch", "readiness checks")


def price_recovery_controller(ask: Ask) -> Price:
    """Application Recovery Controller: the feature it stands for
    (``feature``), routing controls unless it says otherwise."""
    feature = str(ask.take("feature", "routing controls", kind=str, choices=_ARC_FEATURES))
    if feature == "region switch":
        bill = _Bill.of(ask, "recovery-controller", world=True)
        plans = bill.count("plans")
        bill.running(
            "Region switch plans", plans, "region-switch-plan", keys=("plans",), per_month=True
        )
        price = bill.price("Application Recovery Controller Region switch, per plan a month")
    elif feature == "readiness checks":
        price = price_readiness_checks(ask)
    else:
        price = price_routing_controls(ask)
    price.sizing["feature"] = feature
    return price


def price_flink(ask: Ask) -> Price:
    bill = _Bill.of(ask, "flink")
    kpus = bill.number("kpus", 1, low=1, high=10000)
    applications = bill.count("applications")
    bill.running(
        "KPU hours (one more per application to orchestrate it)",
        kpus + applications,
        "kpu-hour",
        keys=("kpus", "applications"),
    )
    bill.add(
        "Running application storage (50 GB per KPU)",
        kpus * 50,
        "GB-month",
        "running-storage",
        fixed=True,
        keys=("kpus",),
    )
    return bill.price("Managed Service for Apache Flink, per KPU hour")


def price_drs(ask: Ask) -> Price:
    bill = _Bill.of(ask, "drs")
    servers = bill.count("servers")
    bill.running("Replicated source server hours", servers, "server-hour", keys=("servers",))
    return bill.price("Elastic Disaster Recovery, per source server hour (staging resources extra)")


def price_dms(ask: Ask) -> Price:
    bill = _Bill.of(ask, "dms")
    deployments = _choices(bill.service, bill.region)
    deployment = bill.choose("deployment", _first(deployments, "Single-AZ"), deployments)
    instance_class = str(
        bill.take(
            "instance_class",
            _default(bill.service, (bill.region, deployment), "dms.t3.medium", "dms.c5.large"),
            kind=str,
        )
    )
    count = bill.count("instances")
    bill.lines.append(
        line(
            f"Replication instance hours, {instance_class}",
            count * bill.hours(),
            "hours",
            bill.rate(deployment, instance_class),
            kind="fixed",
            assumed=bill.assumed("instances", "instance_class", "deployment", "hours"),
        )
    )
    storage = bill.given("storage_gb", high=6144)
    if storage:
        usage = ask.table.service("dms-usage")
        bill.add(
            "Storage beyond what the instance includes",
            storage,
            "GB-month",
            f"{deployment} storage",
            fixed=True,
            service=usage,
        )
    return bill.price(
        f"DMS replication instance, {deployment}{_described(bill, 'instance_class', instance_class)}"
    )


def price_cloudsearch(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cloudsearch")
    instance_type = str(
        bill.take("instance_type", _default(bill.service, (bill.region,), "m1.small"), kind=str)
    )
    count = bill.count("instances")
    bill.lines.append(
        line(
            f"Search instance hours, {instance_type}",
            count * bill.hours(),
            "hours",
            bill.rate(instance_type),
            kind="fixed",
            assumed=bill.assumed("instances", "instance_type", "hours"),
        )
    )
    return bill.price("CloudSearch (2013 API), per search instance hour")


def price_file_cache(ask: Ask) -> Price:
    bill = _Bill.of(ask, "fsx")
    tiers = sorted(
        item.rsplit(" ", 1)[1] for item in bill.items() if item.startswith("File Cache storage ")
    )
    throughput = bill.choose("throughput_tier", _first(tiers, "1000"), tiers)
    size = bill.number("storage_gb", 1200, low=1200, high=1e7)
    bill.add(
        "Cache storage",
        size,
        "GB-month",
        f"File Cache storage {throughput}",
        fixed=True,
        keys=("storage_gb",),
    )
    return bill.price(f"Amazon File Cache, {throughput} MB/s per TiB")


def price_kinesis(ask: Ask) -> Price:
    bill = _Bill.of(ask, "kinesis")
    mode = bill.choose("capacity", "on-demand", ["on-demand", "provisioned"])
    if mode == "on-demand":
        ask.taken.update({"shards", "put_units_millions"})
        streams = bill.count("streams")
        data_in = bill.number("data_in_gb", 10, high=1e10)
        data_out = bill.number("data_out_gb", 10, high=1e10)
        bill.running("Stream hours", streams, "on-demand-stream-hour", keys=("streams",))
        bill.add("Data written", data_in, "GB", "on-demand-in-gb", keys=("data_in_gb",))
        bill.add("Data read", data_out, "GB", "on-demand-out-gb", keys=("data_out_gb",))
    else:
        ask.taken.update({"streams", "data_in_gb", "data_out_gb"})
        shards = bill.count("shards")
        units = bill.number("put_units_millions", 10, high=1e10)
        bill.running("Shard hours", shards, "shard-hour", keys=("shards",))
        bill.add(
            "PUT payload units (25 KB)",
            units,
            "1M units",
            "put-payload-unit",
            per=1e6,
            keys=("put_units_millions",),
        )
    return bill.price(f"Kinesis Data Streams, {mode} capacity")


def price_mq(ask: Ask) -> Price:
    bill = _Bill.of(ask, "mq")
    engines = _choices(bill.service, bill.region)
    engine = bill.choose("engine", _first(engines, "ActiveMQ"), engines)
    deployments = _choices(bill.service, bill.region, engine)
    deployment = bill.choose("deployment", _first(deployments, "Single-AZ"), deployments)
    instance_type = str(
        bill.take(
            "instance_type",
            _default(
                bill.service, (bill.region, engine, deployment), "mq.t3.micro", "mq.m7g.medium"
            ),
            kind=str,
        )
    )
    brokers = bill.count("brokers")
    bill.lines.append(
        line(
            f"{engine} {deployment} broker hours, {instance_type}",
            brokers * bill.hours(),
            "hours",
            bill.rate(engine, deployment, instance_type),
            kind="fixed",
            assumed=bill.assumed("brokers", "instance_type", "engine", "deployment", "hours"),
        )
    )
    usage = ask.table.service("mq-usage")
    size = bill.number("storage_gb", 20, high=1e6)
    item = "storage-efs" if engine == "ActiveMQ" and deployment == "Multi-AZ" else "storage-ebs"
    bill.add(
        "Broker storage", size * brokers, "GB-month", item, service=usage, keys=("storage_gb",)
    )
    return bill.price(
        f"Amazon MQ for {engine}, {deployment}{_described(bill, 'instance_type', instance_type)}"
    )


def price_step_functions(express: bool) -> Pricer:
    def price(ask: Ask) -> Price:
        bill = _Bill.of(ask, "step-functions")
        if express:
            requests = bill.number("requests_millions", 1, high=1e9)
            duration = bill.number("duration_ms", 1000, low=1, high=300_000)
            memory = bill.number("memory_mb", 64, low=64, high=10240)
            bill.add(
                "Workflow requests",
                requests,
                "1M requests",
                "express-request",
                per=1e6,
                keys=("requests_millions",),
            )
            seconds = requests * 1e6 * duration / 1000 * memory / 1024
            bill.add(
                "Duration",
                seconds,
                "GB-seconds",
                "express-gb-second",
                keys=("requests_millions", "duration_ms", "memory_mb"),
            )
            return bill.price("Step Functions Express workflows")
        transitions = bill.number("transitions_thousands", 100, high=1e9)
        bill.add(
            "State transitions",
            transitions,
            "1,000 transitions",
            "state-transition",
            per=1000,
            keys=("transitions_thousands",),
        )
        return bill.price(f"Step Functions Standard workflows, {_BEFORE_FREE_TIER}")

    return price


def price_cognito(ask: Ask) -> Price:
    bill = _Bill.of(ask, "cognito")
    tiers = {"Lite": "lite-mau", "Essentials": "essentials-mau", "Plus": "plus-mau"}
    tier = bill.choose("tier", "Essentials", list(tiers))
    users = bill.number("monthly_active_users", 1000, high=1e9)
    bill.add(
        f"{tier} monthly active users", users, "MAUs", tiers[tier], keys=("monthly_active_users",)
    )
    return bill.price(f"Cognito user pools, {tier} tier, {_BEFORE_FREE_TIER}")


def price_codebuild(ask: Ask) -> Price:
    bill = _Bill.of(ask, "codebuild")
    computes = sorted(
        item.removesuffix("-minute") for item in bill.items() if item.endswith("-minute")
    )
    compute = bill.choose("compute", _first(computes, "linux-small"), computes)
    minutes = bill.number("build_minutes", 100, high=1e9)
    bill.add(
        f"Build minutes, {compute}",
        minutes,
        "minutes",
        f"{compute}-minute",
        keys=("build_minutes",),
    )
    return bill.price(f"CodeBuild on-demand, {compute}, {_BEFORE_FREE_TIER}")


# -- what every AWS component is priced as ----------------------------------


def _or_serverless(provisioned: Pricer, serverless: Pricer) -> Pricer:
    """Priced as *provisioned*, or as *serverless* when the sizing says
    ``serverless: yes``; never assumed, so a drawing that does not say
    keeps its provisioned price."""

    def price(ask: Ask) -> Price:
        if ask.sizing.get("serverless") not in (None, "") and ask.take(
            "serverless", False, kind=bool
        ):
            return serverless(ask)
        ask.taken.add("serverless")
        return provisioned(ask)

    return price


_EC2 = price_ec2_table
_RDS = _rds("PostgreSQL")
_S3 = _s3("Standard")
_FARGATE = price_fargate
_ELASTICACHE = _nodes(
    "elasticache",
    "ElastiCache",
    "node_type",
    "cache.t3.micro",
    engines=("Valkey", "Redis", "Memcached"),
    engine_default="Valkey",
)
_AURORA_POSTGRESQL = _or_serverless(_rds("Aurora PostgreSQL"), price_aurora_serverless)
_AURORA_MYSQL = _or_serverless(_rds("Aurora MySQL"), price_aurora_serverless)
_OPENSEARCH = price_opensearch("t3.small.search", "t3.medium.search")
_EKS = price_eks

_PRICERS: dict[str, Pricer] = {
    # compute
    "ec2": _EC2,
    "ec2-instance": _EC2,
    "ec2-instances": _EC2,
    "ec2-instance-with-cloudwatch": _EC2,
    "ec2-db-instance": _EC2,
    "ec2-elastic-ip-address": price_public_ip,
    "ec2-ami": price_ebs_snapshot,
    "app-runner": price_app_runner,
    "lambda": price_lambda,
    "lambda-lambda-function": price_lambda,
    "iot-lambda-function": price_lambda,
    "fargate": _FARGATE,
    "elastic-container-service": _FARGATE,
    "elastic-container-service-service": _FARGATE,
    "elastic-container-service-task": _FARGATE,
    "ecs-anywhere": price_ecs_anywhere,
    "elastic-kubernetes-service": _EKS,
    "emr": price_emr,
    "emr-cluster": price_emr,
    "emr-hdfs-cluster": price_emr,
    "elastic-container-registry": price_ecr,
    "elastic-container-registry-registry": price_ecr,
    # storage
    "simple-storage-service": _S3,
    "simple-storage-service-bucket": _S3,
    "simple-storage-service-bucket-with-objects": _S3,
    "simple-storage-service-s3-standard": _S3,
    "simple-storage-service-s3-standard-ia": _s3("Standard-IA"),
    "simple-storage-service-s3-one-zone-ia": _s3("One Zone-IA"),
    "simple-storage-service-s3-intelligent-tiering": _s3("Intelligent-Tiering"),
    "simple-storage-service-s3-express-one-zone": _s3("Express One Zone"),
    "simple-storage-service-directory-bucket": _s3("Express One Zone"),
    "simple-storage-service-s3-glacier-instant-retrieval": _s3("Glacier Instant Retrieval"),
    "simple-storage-service-s3-glacier-flexible-retrieval": _s3("Glacier Flexible Retrieval"),
    "simple-storage-service-glacier": _s3("Glacier Flexible Retrieval"),
    "simple-storage-service-glacier-archive": _s3("Glacier Flexible Retrieval"),
    "simple-storage-service-glacier-vault": _s3("Glacier Flexible Retrieval"),
    "simple-storage-service-s3-glacier-deep-archive": _s3("Glacier Deep Archive"),
    "simple-storage-service-s3-tables": _s3("Tables"),
    "elastic-block-store": price_ebs,
    "elastic-block-store-volume": price_ebs,
    "elastic-block-store-volume-gp3": price_ebs,
    "elastic-block-store-multiple-volumes": price_ebs,
    "elastic-block-store-snapshot": price_ebs_snapshot,
    "efs": price_efs("Standard"),
    "elastic-file-system-file-system": price_efs("Standard"),
    "elastic-file-system-efs-standard": price_efs("Standard"),
    "elastic-file-system-efs-intelligent-tiering": price_efs("Standard"),
    "elastic-file-system-efs-standard-infrequent-access": price_efs("Standard-IA"),
    "elastic-file-system-efs-one-zone": price_efs("One Zone"),
    "elastic-file-system-efs-one-zone-infrequent-access": price_efs("One Zone-IA"),
    "elastic-file-system-elastic-throughput": price_efs_throughput,
    "fsx": _fsx("Windows"),
    "fsx-for-wfs": _fsx("Windows"),
    "fsx-for-netapp-ontap": _fsx("ONTAP"),
    "fsx-for-openzfs": _fsx("OpenZFS"),
    "fsx-for-lustre": _fsx("Lustre"),
    "file-cache": price_file_cache,
    "backup": price_backup,
    "backup-backup-vault": price_backup,
    "backup-storage": price_backup,
    "storage-gateway": price_storage_gateway("volume"),
    "storage-gateway-volume-gateway": price_storage_gateway("volume"),
    "storage-gateway-cached-volume": price_storage_gateway("volume"),
    "storage-gateway-noncached-volume": price_storage_gateway("volume"),
    "storage-gateway-tape-gateway": price_storage_gateway("tape"),
    "storage-gateway-virtual-tape-library": price_storage_gateway("tape"),
    "datasync": price_datasync,
    "transfer-family": price_transfer_family("SFTP"),
    "transfer-family-aws-sftp": price_transfer_family("SFTP"),
    "transfer-family-aws-ftps": price_transfer_family("FTPS"),
    "transfer-family-aws-ftp": price_transfer_family("FTP"),
    "transfer-family-aws-as2": price_transfer_family("AS2"),
    "elastic-disaster-recovery": price_drs,
    # databases
    "rds": _RDS,
    "rds-multi-az": _rds("PostgreSQL", "Multi-AZ"),
    "rds-multi-az-db-cluster": _rds("PostgreSQL", "Multi-AZ cluster"),
    "aurora-amazon-rds-instance": _RDS,
    "aurora-amazon-rds-instance-aternate": _RDS,
    # Aurora PostgreSQL and MySQL: provisioned, or Serverless v2 on serverless: yes
    "aurora": _AURORA_POSTGRESQL,
    "aurora-instance": _AURORA_POSTGRESQL,
    "aurora-amazon-aurora-instance-alternate": _AURORA_POSTGRESQL,
    "aurora-postgresql-instance": _AURORA_POSTGRESQL,
    "aurora-postgresql-instance-alternate": _AURORA_POSTGRESQL,
    "aurora-mysql-instance": _AURORA_MYSQL,
    "aurora-mysql-instance-alternate": _AURORA_MYSQL,
    "aurora-mariadb-instance": _rds("MariaDB"),
    "aurora-mariadb-instance-alternate": _rds("MariaDB"),
    "aurora-oracle-instance": _rds("Oracle SE2 (license included)"),
    "aurora-oracle-instance-alternate": _rds("Oracle SE2 (license included)"),
    "aurora-sql-server-instance": _rds("SQL Server Express"),
    "aurora-sql-server-instance-alternate": _rds("SQL Server Express"),
    "aurora-piops-instance": _rds("PostgreSQL", storage_default="io1"),
    "rds-proxy-instance": price_rds_proxy,
    "rds-proxy-instance-alternate": price_rds_proxy,
    "dynamodb": price_dynamodb(),
    "dynamodb-table": price_dynamodb(),
    "dynamodb-global-secondary-index": price_dynamodb(),
    "dynamodb-standard-access-table-class": price_dynamodb(),
    "dynamodb-standard-infrequent-access-table-class": price_dynamodb("standard-ia"),
    "dynamodb-stream": price_dynamodb_stream,
    "dynamodb-amazon-dynamodb-accelerator": _nodes("dax", "DAX", "node_type", "dax.t3.small"),
    # ElastiCache: nodes, or Serverless on serverless: yes (a cache node is always a node)
    "elasticache": _or_serverless(_ELASTICACHE, price_elasticache_serverless),
    "elasticache-cache-node": _ELASTICACHE,
    "elasticache-elasticache-for-valkey": _or_serverless(
        _ELASTICACHE, price_elasticache_serverless
    ),
    "elasticache-elasticache-for-redis": _or_serverless(
        _nodes(
            "elasticache",
            "ElastiCache",
            "node_type",
            "cache.t3.micro",
            engines=("Valkey", "Redis", "Memcached"),
            engine_default="Redis",
        ),
        _elasticache_serverless("Redis"),
    ),
    "elasticache-elasticache-for-memcached": _or_serverless(
        _nodes(
            "elasticache",
            "ElastiCache",
            "node_type",
            "cache.t3.micro",
            engines=("Valkey", "Redis", "Memcached"),
            engine_default="Memcached",
        ),
        _elasticache_serverless("Memcached"),
    ),
    "memorydb": _nodes(
        "memorydb",
        "MemoryDB",
        "node_type",
        "db.t4g.small",
        engines=("Valkey", "Redis"),
        engine_default="Valkey",
    ),
    "documentdb": _documents("docdb", "DocumentDB", "db.t3.medium", "DCU"),
    "documentdb-elastic-clusters": price_docdb_elastic,
    "neptune": _documents("neptune", "Neptune", "db.t3.medium", "NCU"),
    "keyspaces": price_keyspaces,
    "timestream": price_timestream,
    "redshift": _nodes("redshift", "Redshift", "node_type", "ra3.large"),
    "redshift-ra3": _nodes("redshift", "Redshift", "node_type", "ra3.xlplus"),
    "redshift-dense-compute-node": _nodes("redshift", "Redshift", "node_type", "dc2.large"),
    "database-migration-service": price_dms,
    "database-migration-service-database-migration-workflow-or-job": price_dms,
    # analytics
    "athena": _usage(
        "athena",
        "Athena SQL queries, per TB scanned",
        ("tb_scanned", "Data scanned", "TB", "tb-scanned", 0.1, 1),
    ),
    "glue": price_glue("etl-dpu-hour", "ETL job DPU-hours"),
    "glue-crawler": price_glue("crawler-dpu-hour", "Crawler DPU-hours", 1),
    "glue-data-quality": price_glue("etl-dpu-hour", "Data quality DPU-hours", 1),
    "glue-aws-glue-for-ray": price_glue("ray-mdpu-hour", "Ray job M-DPU-hours"),
    "glue-data-catalog": price_glue_catalog,
    "glue-databrew": _usage(
        "glue",
        "Glue DataBrew jobs, per node hour",
        ("node_hours", "Job node-hours", "node-hours", "databrew-node-hour", 10, 1),
    ),
    "kinesis": price_kinesis,
    "kinesis-data-streams": price_kinesis,
    "data-firehose": _usage(
        "firehose",
        "Data Firehose, Direct PUT",
        ("ingested_gb", "Data ingested", "GB", "ingest-gb", 100, 1),
    ),
    "managed-service-for-apache-flink": price_flink,
    "managed-streaming-for-apache-kafka": _nodes(
        "msk", "MSK", "broker_type", "kafka.t3.small", count_key="brokers", count_default=2
    ),
    "msk-amazon-msk-connect": _hourly(
        "msk-usage", "MSK Connect, per MCU hour", "mcus", "MCU hours", "connect-mcu-hour"
    ),
    "opensearch-service": _OPENSEARCH,
    "opensearch-service-data-node": _OPENSEARCH,
    "opensearch-service-cluster-administrator-node": price_opensearch(
        "m6g.large.search", "m7g.large.search", "r6g.large.search"
    ),
    "opensearch-service-ultrawarm-node": price_opensearch("ultrawarm1.medium.search"),
    "opensearch-service-opensearch-ingestion": price_opensearch_ingestion,
    "cloudsearch": price_cloudsearch,
    "managed-workflows-for-apache-airflow": price_mwaa,
    # application integration
    "api-gateway": price_api_gateway,
    "api-gateway-endpoint": price_api_gateway,
    "appsync": _usage(
        "appsync",
        "AppSync GraphQL, per operation",
        ("operations_millions", "Queries and mutations", "1M operations", "request", 1, 1e6),
    ),
    "eventbridge": _usage(
        "eventbridge",
        "EventBridge custom events",
        ("events_millions", "Custom events (64 KB chunks)", "1M events", "custom-event", 1, 1e6),
    ),
    "eventbridge-custom-event-bus": _usage(
        "eventbridge",
        "EventBridge custom events",
        ("events_millions", "Custom events (64 KB chunks)", "1M events", "custom-event", 1, 1e6),
    ),
    "eventbridge-event": _usage(
        "eventbridge",
        "EventBridge custom events",
        ("events_millions", "Custom events (64 KB chunks)", "1M events", "custom-event", 1, 1e6),
    ),
    "eventbridge-saas-partner-event": _usage(
        "eventbridge",
        "EventBridge partner events",
        ("events_millions", "Partner events (64 KB chunks)", "1M events", "partner-event", 1, 1e6),
    ),
    "eventbridge-pipes": _usage(
        "eventbridge",
        "EventBridge Pipes",
        (
            "requests_millions",
            "Pipe requests (64 KB chunks)",
            "1M requests",
            "pipe-request",
            1,
            1e6,
        ),
    ),
    "eventbridge-scheduler": _usage(
        "eventbridge",
        f"EventBridge Scheduler, {_BEFORE_FREE_TIER}",
        (
            "invocations_millions",
            "Scheduled invocations",
            "1M invocations",
            "scheduler-invocation",
            1,
            1e6,
        ),
    ),
    "step-functions": price_step_functions(express=False),
    "express-workflows": price_step_functions(express=True),
    "simple-queue-service": price_sqs,
    "simple-queue-service-queue": price_sqs,
    "simple-notification-service": price_sns(),
    "simple-notification-service-topic": price_sns(),
    "simple-notification-service-email-notification": price_sns("email"),
    "simple-notification-service-http-notification": price_sns("http"),
    "mq": price_mq,
    "mq-broker": price_mq,
    "simple-email-service": _usage(
        "ses",
        "SES outbound email",
        ("emails_thousands", "Emails sent", "1,000 emails", "outbound-email", 10, 1000),
    ),
    "simple-email-service-email": _usage(
        "ses",
        "SES outbound email",
        ("emails_thousands", "Emails sent", "1,000 emails", "outbound-email", 10, 1000),
    ),
    "iot-core": price_iot_core,
    # networking and content delivery
    "vpc-nat-gateway": price_nat_gateway,
    "elastic-load-balancing": _load_balancer("application"),
    "elastic-load-balancing-application-load-balancer": _load_balancer("application"),
    "elastic-load-balancing-network-load-balancer": _load_balancer("network"),
    "elastic-load-balancing-gateway-load-balancer": _load_balancer("gateway"),
    "elastic-load-balancing-classic-load-balancer": _load_balancer("classic"),
    "vpc-endpoints": price_vpc_endpoint,
    "privatelink": price_vpc_endpoint,
    "transit-gateway": price_transit_gateway,
    "transit-gateway-attachment": price_transit_gateway_attachment,
    "site-to-site-vpn": price_site_to_site_vpn,
    "vpc-vpn-connection": price_site_to_site_vpn,
    "client-vpn": price_client_vpn,
    "vpc-traffic-mirroring": price_traffic_mirroring,
    "vpc-reachability-analyzer": price_reachability,
    "vpc-network-access-analyzer": price_access_analyzer,
    "vpc-lattice": price_lattice,
    "vpc-peering-connection": price_vpc_peering,
    "verified-access": price_verified_access,
    "network-firewall": price_network_firewall,
    "network-firewall-endpoints": price_network_firewall,
    "direct-connect": price_direct_connect,
    "global-accelerator": price_global_accelerator,
    "cloudfront": price_cloudfront,
    "cloudfront-download-distribution": price_cloudfront,
    "cloudfront-streaming-distribution": price_cloudfront,
    "cloudfront-functions": price_cloudfront_functions,
    "route-53": price_route53_zone,
    "route-53-hosted-zone": price_route53_zone,
    "route-53-resolver": price_route53_resolver,
    "route-53-resolver-dns-firewall": price_dns_firewall,
    "route-53-readiness-checks": price_readiness_checks,
    "route-53-routing-controls": price_routing_controls,
    "application-recovery-controller": price_recovery_controller,
    "cloud-wan": price_cloud_wan,
    "cloud-wan-core-network-edge": price_cloud_wan,
    "cloud-wan-transit-gateway-route-table-attachment": price_cloud_wan_attachment,
    "cloud-map": _monthly(
        "cloud-map",
        "Cloud Map, per registered resource",
        "resources",
        "Registered resources",
        "resource-months",
        "resource",
        10,
    ),
    "cloud-map-resource": _monthly(
        "cloud-map",
        "Cloud Map, per registered resource",
        "resources",
        "Registered resources",
        "resource-months",
        "resource",
    ),
    # security, identity and compliance
    "waf": price_waf,
    "waf-rule": price_waf_rule,
    "waf-managed-rule": price_waf_rule,
    "waf-filtering-rule": price_waf_rule,
    "waf-bot-control": price_waf_bot_control,
    "waf-bot": price_waf_bot_control,
    "waf-bad-bot": price_waf_bot_control,
    "shield-aws-shield-advanced": price_shield_advanced,
    "key-management-service": price_kms,
    "key-management-service-external-key-store": price_kms,
    "secrets-manager": price_secrets_manager,
    "cloudhsm": _hourly("cloudhsm", "CloudHSM, per HSM hour", "hsms", "HSM hours", "hsm-hour"),
    "private-certificate-authority": _monthly(
        "private-ca",
        "Private CA, general-purpose mode, per CA-month",
        "authorities",
        "Certificate authorities",
        "CA-months",
        "general-ca",
    ),
    "certificate-manager-certificate-authority": _monthly(
        "private-ca",
        "Private CA, general-purpose mode, per CA-month",
        "authorities",
        "Certificate authorities",
        "CA-months",
        "general-ca",
    ),
    "cognito": price_cognito,
    "directory-service": price_directory("Managed AD Standard"),
    "directory-service-aws-managed-microsoft-ad": price_directory("Managed AD Standard"),
    "directory-service-simple-ad": price_directory("Simple AD Small"),
    "directory-service-ad-connector": price_directory("AD Connector Small"),
    # management and developer tools
    "cloudwatch": price_cloudwatch,
    "cloudwatch-alarm": price_cloudwatch_alarm,
    "cloudwatch-logs": price_cloudwatch_logs,
    "cloudwatch-synthetics": price_synthetics,
    "cloudwatch-rum": _usage(
        "cloudwatch",
        f"CloudWatch RUM, {_BEFORE_FREE_TIER}",
        ("events_thousands", "RUM events", "1,000 events", "rum-event", 100, 1000),
    ),
    "cloudwatch-data-protection": _usage(
        "cloudwatch",
        "CloudWatch Logs data protection, per GB scanned",
        ("scanned_gb", "Log data scanned", "GB", "data-protection-gb", 10, 1),
    ),
    "cloudtrail": price_cloudtrail,
    "cloudtrail-cloudtrail-lake": price_cloudtrail_lake,
    "config": price_config,
    "x-ray": _usage(
        "xray",
        f"X-Ray traces, {_BEFORE_FREE_TIER}",
        ("traces_millions", "Traces recorded", "1M traces", "trace-stored", 1, 1e6),
        (
            "retrieved_millions",
            "Traces retrieved or scanned",
            "1M traces",
            "trace-accessed",
            1,
            1e6,
        ),
    ),
    "managed-grafana": _usage(
        "grafana",
        "Managed Grafana, per active user",
        ("editors", "Editor and admin users", "users", "editor-user", 1, 1),
    ),
    "managed-service-for-prometheus": _usage(
        "prometheus",
        f"Managed Service for Prometheus, {_BEFORE_FREE_TIER}",
        ("samples_millions", "Metric samples ingested", "1M samples", "sample", 100, 1e6),
        ("storage_gb", "Metric storage", "GB-month", "storage", 10, 1),
    ),
    "codebuild": price_codebuild,
    "codepipeline": _monthly(
        "codepipeline",
        "CodePipeline V1, per active pipeline-month",
        "pipelines",
        "Active pipelines",
        "pipeline-months",
        "pipeline",
    ),
}

# -- reasons something costs nothing on its own
_CONCEPT = "a concept or label in the drawing, not a billed AWS resource"
_GENERIC = "a generic icon (people, devices, documents, places), not a billed AWS resource"
_TOOL = "a free AWS tool or SDK; what it creates is priced on its own elements"
_SOFTWARE = "software at no charge; the compute it runs on is priced on its own element"
_DEVICE = "an IoT device or concept, not an AWS resource; its messages are priced on IoT Core"
_FEATURE = "a feature at no extra charge; the service it belongs to is priced on its own element"
_INSIDE = "a view of what runs inside a resource; the resource is priced on its own element"
_CONTAINS = "a part of a resource priced on its parent element"
_NETWORK = (
    "costs nothing on its own; traffic through it is priced on the gateways and endpoints it uses"
)
_IAM = "IAM costs nothing; identities, roles and policies are free"
_GOVERNANCE = "costs nothing on its own; the resources it manages are priced on their elements"

_FREE: dict[str, str] = {
    "account": "an AWS account costs nothing on its own",
    "activate": "AWS Activate is a programme of credits, not a billed resource",
    "app-mesh": "App Mesh has no charge; the proxies run on priced compute",
    "app-mesh-mesh": "App Mesh has no charge; the proxies run on priced compute",
    "app-mesh-virtual-gateway": "App Mesh has no charge; the proxies run on priced compute",
    "app-mesh-virtual-node": "App Mesh has no charge; the proxies run on priced compute",
    "app-mesh-virtual-router": "App Mesh has no charge; the proxies run on priced compute",
    "app-mesh-virtual-service": "App Mesh has no charge; the proxies run on priced compute",
    "apache-mxnet-on-aws": _SOFTWARE,
    "application-auto-scaling": "Auto Scaling is free; what it scales is priced on its own elements",
    "application-discovery-service": "Application Discovery Service has no charge",
    "application-discovery-service-aws-agentless-collector": "Application Discovery Service has no charge",
    "application-discovery-service-aws-discovery-agent": "Application Discovery Service has no charge",
    "application-discovery-service-migration-evaluator-collector": "Migration Evaluator has no charge",
    "application-migration-service": "free for 90 days per server; the replication and launched EC2 instances are priced as EC2",
    "artifact": "AWS Artifact has no charge",
    "athena-data-source-connectors": "connectors run as Lambda functions, priced on the Lambda element",
    "auto-scaling": "Auto Scaling is free; the instances it launches are priced on their EC2 elements",
    "auto-scaling-group": "Auto Scaling is free; the instances it launches are priced on their EC2 elements",
    "aurora-trusted-language-extensions-for-postgresql": _FEATURE,
    "aws-compute-optimizer": "Compute Optimizer recommendations are free (enhanced metrics are paid per resource)",
    "backup-aws-backup-for-aws-cloudformation": _FEATURE,
    "backup-aws-backup-support-for-amazon-fsx-for-netapp-ontap": _FEATURE,
    "backup-aws-backup-support-for-amazon-s3": _FEATURE,
    "backup-aws-backup-support-for-vmware-workloads": _FEATURE,
    "backup-backup-plan": "a backup plan costs nothing; the backups it keeps are priced on the vault",
    "backup-compute": _CONCEPT,
    "backup-database": _CONCEPT,
    "backup-gateway": "Backup gateway has no charge; VMware backups are priced on the vault",
    "backup-legal-hold": _FEATURE,
    "backup-recovery-point-objective": _CONCEPT,
    "backup-recovery-time-objective": _CONCEPT,
    "backup-vault-lock": _FEATURE,
    "backup-virtual-machine": _CONCEPT,
    "backup-virtual-machine-monitor": _CONCEPT,
    "batch": "AWS Batch has no charge; the compute it runs is priced on its own elements",
    "bottlerocket": _SOFTWARE,
    "budgets": "budgets are free to watch (action-enabled budgets past two are billed per day)",
    "certificate-manager": "public TLS certificates from ACM are free",
    "chatbot": "Amazon Q Developer in chat applications has no charge",
    "cloud": _CONCEPT,
    "cloud-control-api": _TOOL,
    "cloud-development-kit": _TOOL,
    "cloud-logo": _CONCEPT,
    "cloud-map-namespace": "Cloud Map namespaces cost nothing; registered resources are priced",
    "cloud-map-service": "Cloud Map services cost nothing; registered resources are priced",
    "cloud-wan-segment-network": "segments cost nothing; edges and attachments are priced",
    "cloud9": "Cloud9 has no charge; its EC2 instance is priced as EC2",
    "cloud9-cloud9": "Cloud9 has no charge; its EC2 instance is priced as EC2",
    "cloudformation": "CloudFormation is free for AWS resources; the stack's resources are priced on their elements",
    "cloudformation-change-set": "CloudFormation is free for AWS resources",
    "cloudformation-stack": "CloudFormation is free for AWS resources; the stack's resources are priced on their elements",
    "cloudformation-template": "CloudFormation is free for AWS resources",
    "cloudfront-edge-location": "an edge location is where CloudFront serves from; traffic is priced on the distribution",
    "cloudshell": "CloudShell has no charge",
    "cloudwatch-cross-account-observability": "cross-account observability has no extra charge",
    "cloudwatch-event-event-based": "AWS service events on the default bus are free",
    "cloudwatch-event-time-based": "scheduled rules are free",
    "cloudwatch-rule": "EventBridge rules are free",
    "codedeploy": "CodeDeploy to EC2 and Lambda has no charge (on-premises deployments are billed per update)",
    "command-line-interface": _TOOL,
    "compute-optimizer": "Compute Optimizer recommendations are free (enhanced metrics are paid per resource)",
    "console-mobile-application": _TOOL,
    "control-tower": _GOVERNANCE,
    "corporate-data-center": _GENERIC,
    "corretto": _SOFTWARE,
    "cost-and-usage-report": "the report is free; its files are stored in S3, priced on the bucket",
    "cost-explorer": "Cost Explorer in the console is free (its API is billed per request)",
    "datasync-agent": "the DataSync agent has no charge; data copied is priced on DataSync",
    "dcv": "NICE DCV is free on EC2; the instance is priced as EC2",
    "deep-learning-amis": _SOFTWARE,
    "deep-learning-containers": _SOFTWARE,
    "direct-connect-gateway": "a Direct Connect gateway costs nothing; ports and data are priced",
    "distro-for-opentelemetry": _SOFTWARE,
    "dynamodb-attribute": _CONCEPT,
    "dynamodb-attributes": _CONCEPT,
    "dynamodb-item": _CONCEPT,
    "dynamodb-items": _CONCEPT,
    "ec2-auto-scaling": "Auto Scaling is free; the instances it launches are priced on their EC2 elements",
    "ec2-auto-scaling-resource": "Auto Scaling is free; the instances it launches are priced on their EC2 elements",
    "ec2-aws-microservice-extractor-for-net": _TOOL,
    "ec2-image-builder": "Image Builder has no charge; the build instances and images are priced",
    "ec2-instance-contents": _INSIDE,
    "ec2-rescue": _TOOL,
    "eks-distro": _SOFTWARE,
    "elastic-beanstalk": "Elastic Beanstalk has no charge; the resources it creates are priced on their elements",
    "elastic-beanstalk-application": "Elastic Beanstalk has no charge; the resources it creates are priced on their elements",
    "elastic-beanstalk-deployment": "Elastic Beanstalk has no charge; the resources it creates are priced on their elements",
    "elastic-block-store-amazon-data-lifecycle-manager": "Data Lifecycle Manager has no charge; the snapshots it keeps are priced",
    "elastic-container-registry-image": _CONTAINS,
    "elastic-container-service-container-1": _CONTAINS,
    "elastic-container-service-container-2": _CONTAINS,
    "elastic-container-service-container-3": _CONTAINS,
    "elastic-container-service-copiiot-cli": _TOOL,
    "elastic-container-service-ecs-service-connect": _FEATURE,
    "elastic-fabric-adapter": "an EFA interface costs nothing on its own",
    "emr-emr-engine": _FEATURE,
    "eventbridge-default-event-bus": "AWS service events on the default bus are free",
    "eventbridge-rule": "EventBridge rules are free",
    "eventbridge-schema": "the schema registry is free (schema discovery is billed per event ingested)",
    "eventbridge-schema-registry": "the schema registry is free (schema discovery is billed per event ingested)",
    "file-cache-hybrid-nfs-linked-datasets": _CONTAINS,
    "file-cache-on-premises-nfs-linked-datasets": _CONTAINS,
    "file-cache-s3-linked-datasets": _CONTAINS,
    "general-alert": _GENERIC,
    "general-authenticated-user": _GENERIC,
    "general-camera": _GENERIC,
    "general-chat": _GENERIC,
    "general-client": _GENERIC,
    "general-cold-storage": _GENERIC,
    "general-credentials": _GENERIC,
    "general-data-stream": _GENERIC,
    "general-data-table": _GENERIC,
    "general-database": _GENERIC,
    "general-disk": _GENERIC,
    "general-document": _GENERIC,
    "general-documents": _GENERIC,
    "general-email": _GENERIC,
    "general-firewall": _GENERIC,
    "general-folder": _GENERIC,
    "general-folders": _GENERIC,
    "general-forums": _GENERIC,
    "general-gear": _GENERIC,
    "general-generic-application": _GENERIC,
    "general-git-repository": _GENERIC,
    "general-globe": _GENERIC,
    "general-internet": _GENERIC,
    "general-internet-alt1": _GENERIC,
    "general-internet-alt2": _GENERIC,
    "general-json-script": _GENERIC,
    "general-logs": _GENERIC,
    "general-magnifying-glass": _GENERIC,
    "general-management-console": _GENERIC,
    "general-metrics": _GENERIC,
    "general-mobile-client": _GENERIC,
    "general-multimedia": _GENERIC,
    "general-office-building": _GENERIC,
    "general-programming-language": _GENERIC,
    "general-question": _GENERIC,
    "general-recover": _GENERIC,
    "general-saml-token": _GENERIC,
    "general-sdk": _GENERIC,
    "general-server": _GENERIC,
    "general-servers": _GENERIC,
    "general-shield": _GENERIC,
    "general-source-code": _GENERIC,
    "general-ssl-padlock": _GENERIC,
    "general-tape-storage": _GENERIC,
    "general-toolkit": _GENERIC,
    "general-user": _GENERIC,
    "general-users": _GENERIC,
    "health-dashboard": "the Health Dashboard has no charge",
    "iam-identity-center": "IAM Identity Center has no charge",
    "identity-access-management-add-on": _IAM,
    "identity-access-management-aws-sts": _IAM,
    "identity-access-management-aws-sts-alternate": _IAM,
    "identity-access-management-data-encryption-key": "a data key is generated by KMS; requests are priced on the KMS element",
    "identity-access-management-encrypted-data": _CONCEPT,
    "identity-access-management-iam-access-analyzer": "external access analysis is free (unused access analysis is billed per role or user)",
    "identity-access-management-iam-roles-anywhere": "IAM Roles Anywhere has no charge",
    "identity-access-management-long-term-security-credential": _IAM,
    "identity-access-management-mfa-token": _IAM,
    "identity-access-management-permissions": _IAM,
    "identity-access-management-role": _IAM,
    "identity-access-management-temporary-security-credential": _IAM,
    "identity-and-access-management": _IAM,
    "infrastructure-composer": _TOOL,
    "iot-action": _DEVICE,
    "iot-actuator": _DEVICE,
    "iot-alexa-enabled-device": _DEVICE,
    "iot-alexa-skill": _DEVICE,
    "iot-alexa-voice-service": _DEVICE,
    "iot-certificate": _DEVICE,
    "iot-desired-state": _DEVICE,
    "iot-device-gateway": "the device gateway is part of IoT Core, priced on the IoT Core element",
    "iot-echo": _DEVICE,
    "iot-fire-tv": _DEVICE,
    "iot-fire-tv-stick": _DEVICE,
    "iot-greengrass-artifact": _CONTAINS,
    "iot-greengrass-component": _CONTAINS,
    "iot-greengrass-component-machine-learning": _CONTAINS,
    "iot-greengrass-component-nucleus": _CONTAINS,
    "iot-greengrass-component-private": _CONTAINS,
    "iot-greengrass-component-public": _CONTAINS,
    "iot-greengrass-connector": _CONTAINS,
    "iot-greengrass-deployment": _CONTAINS,
    "iot-greengrass-interprocess-communication": _CONTAINS,
    "iot-greengrass-protocol": _CONTAINS,
    "iot-greengrass-recipe": _CONTAINS,
    "iot-greengrass-stream-manager": _CONTAINS,
    "iot-hardware-board": _DEVICE,
    "iot-http-protocol": _DEVICE,
    "iot-http2-protocol": _DEVICE,
    "iot-lorawan-protocol": _DEVICE,
    "iot-mqtt-protocol": _DEVICE,
    "iot-policy": _DEVICE,
    "iot-reported-state": _DEVICE,
    "iot-rule": _DEVICE,
    "iot-sailboat": _DEVICE,
    "iot-sensor": _DEVICE,
    "iot-servo": _DEVICE,
    "iot-shadow": _DEVICE,
    "iot-thing-bank": _DEVICE,
    "iot-thing-bicycle": _DEVICE,
    "iot-thing-camera": _DEVICE,
    "iot-thing-car": _DEVICE,
    "iot-thing-cart": _DEVICE,
    "iot-thing-coffee-pot": _DEVICE,
    "iot-thing-door-lock": _DEVICE,
    "iot-thing-factory": _DEVICE,
    "iot-thing-freertos-device": _DEVICE,
    "iot-thing-generic": _DEVICE,
    "iot-thing-house": _DEVICE,
    "iot-thing-humidity-sensor": _DEVICE,
    "iot-thing-industrial-pc": _DEVICE,
    "iot-thing-lightbulb": _DEVICE,
    "iot-thing-medical-emergency": _DEVICE,
    "iot-thing-plc": _DEVICE,
    "iot-thing-police-emergency": _DEVICE,
    "iot-thing-relay": _DEVICE,
    "iot-thing-stacklight": _DEVICE,
    "iot-thing-temperature-humidity-sensor": _DEVICE,
    "iot-thing-temperature-sensor": _DEVICE,
    "iot-thing-temperature-vibration-sensor": _DEVICE,
    "iot-thing-thermostat": _DEVICE,
    "iot-thing-travel": _DEVICE,
    "iot-thing-utility": _DEVICE,
    "iot-thing-vibration-sensor": _DEVICE,
    "iot-thing-windfarm": _DEVICE,
    "iot-topic": _DEVICE,
    "freertos": _SOFTWARE,
    "lake-formation": "Lake Formation permissions cost nothing; storage and queries are priced on S3, Glue and Athena",
    "lake-formation-data-lake": "Lake Formation permissions cost nothing; storage and queries are priced on S3, Glue and Athena",
    "launch-wizard": _TOOL,
    "license-manager": "License Manager has no charge",
    "license-manager-application-discovery": "License Manager has no charge",
    "license-manager-license-blending": "License Manager has no charge",
    "local-zones": "a location; what runs there is priced on its own elements",
    "management-console": _TOOL,
    "marketplace-dark": "a storefront; each product is priced by its seller",
    "marketplace-light": "a storefront; each product is priced by its seller",
    "migration-evaluator": "Migration Evaluator has no charge",
    "nitro-enclaves": "Nitro Enclaves have no extra charge; the instance is priced as EC2",
    "neuron": _SOFTWARE,
    "open-3d-engine": _SOFTWARE,
    "opensearch-service-index": _CONTAINS,
    "opensearch-service-observability": _FEATURE,
    "opensearch-service-opensearch-dashboards": _FEATURE,
    "opensearch-service-traces": _FEATURE,
    "organizations": "AWS Organizations has no charge",
    "organizations-account": "an AWS account costs nothing on its own",
    "organizations-management-account": "an AWS account costs nothing on its own",
    "organizations-organizational-unit": "AWS Organizations has no charge",
    "parallel-cluster": _TOOL,
    "private-subnet": "a subnet costs nothing on its own",
    "proton": "Proton has no charge; the infrastructure it deploys is priced on its elements",
    "public-subnet": "a subnet costs nothing on its own",
    "pytorch-on-aws": _SOFTWARE,
    "rds-blue-green-deployments": "no extra charge; the green copy's instances are priced as RDS while they run",
    "rds-optimized-writes": _FEATURE,
    "rds-trusted-language-extensions-for-postgresql": _FEATURE,
    "redshift-auto-copy": _FEATURE,
    "redshift-data-sharing-governance": _FEATURE,
    "redshift-ml": "Redshift ML runs on the cluster's compute (model training through SageMaker is billed there)",
    "redshift-query-editor-v2-0": _FEATURE,
    "redshift-streaming-ingestion": _FEATURE,
    "region": _CONCEPT,
    "repost": "re:Post is free",
    "reserved-instance-reporting": _FEATURE,
    "resource-access-manager": "Resource Access Manager has no charge",
    "resource-explorer": "Resource Explorer has no charge",
    "route-53-resolver-query-logging": "query logging costs nothing itself; the logs are billed where they are delivered",
    "route-53-route-table": _CONCEPT,
    "sagemaker-studio-lab": "SageMaker Studio Lab is free",
    "savings-plans": "a pricing model, not a billed resource",
    "server-contents": _INSIDE,
    "service-management-connector": "the connector has no charge",
    "serverless-application-repository": "the repository has no charge; deployed resources are priced on their elements",
    "shield": "Shield Standard is included at no charge",
    "signer": "Signer has no charge for Lambda code signing",
    "simple-queue-service-message": _CONCEPT,
    "simple-storage-service-general-access-points": "access points cost nothing; requests through them are priced on the bucket",
    "simple-storage-service-object": _CONTAINS,
    "simple-storage-service-s3-object-lock": _FEATURE,
    "simple-storage-service-s3-storage-lens": "Storage Lens free metrics cost nothing (advanced metrics are billed per object monitored)",
    "simple-storage-service-vpc-access-points": "access points cost nothing; requests through them are priced on the bucket",
    "storage-gateway-amazon-fsx-file-gateway": "files are stored in FSx, priced on the FSx element",
    "storage-gateway-amazon-s3-file-gateway": "files are stored as S3 objects, priced on the bucket",
    "storage-gateway-file-gateway": "files are stored as S3 objects, priced on the bucket",
    "sustainability": _CONCEPT,
    "systems-manager": "Systems Manager's core features are free; the paid ones have their own elements",
    "systems-manager-application-manager": "Application Manager has no charge",
    "systems-manager-change-calendar": "Change Calendar has no charge",
    "systems-manager-compliance": "Compliance has no charge",
    "systems-manager-distributor": "Distributor has no charge for AWS packages",
    "systems-manager-documents": "documents cost nothing",
    "systems-manager-inventory": "Inventory has no charge",
    "systems-manager-maintenance-windows": "Maintenance Windows have no charge",
    "systems-manager-parameter-store": "standard parameters are free (advanced parameters are billed per parameter-month)",
    "systems-manager-patch-manager": "Patch Manager has no charge",
    "systems-manager-run-command": "Run Command has no charge",
    "systems-manager-session-manager": "Session Manager has no charge",
    "systems-manager-state-manager": "State Manager has no charge",
    "tensorflow-on-aws": _SOFTWARE,
    "tools-and-sdks": _TOOL,
    "trusted-advisor": "Trusted Advisor is included with the support plan",
    "trusted-advisor-checklist": "Trusted Advisor is included with the support plan",
    "trusted-advisor-checklist-cost": "Trusted Advisor is included with the support plan",
    "trusted-advisor-checklist-fault-tolerant": "Trusted Advisor is included with the support plan",
    "trusted-advisor-checklist-performance": "Trusted Advisor is included with the support plan",
    "trusted-advisor-checklist-security": "Trusted Advisor is included with the support plan",
    "user-notifications": "User Notifications has no charge",
    "virtual-private-cloud": "a VPC costs nothing on its own",
    "virtual-private-cloud-vpc": "a VPC costs nothing on its own",
    "vpc-carrier-gateway": _NETWORK,
    "vpc-customer-gateway": "a customer gateway resource costs nothing; the VPN connection is priced",
    "vpc-elastic-network-adapter": _FEATURE,
    "vpc-elastic-network-interface": "a network interface costs nothing on its own (a public IPv4 address on it is priced)",
    "vpc-internet-gateway": _NETWORK,
    "vpc-network-access-control-list": "network ACLs cost nothing",
    "vpc-router": _CONCEPT,
    "vpc-virtual-private-cloud-vpc": "a VPC costs nothing on its own",
    "vpc-vpn-gateway": "a virtual private gateway costs nothing; the VPN connection is priced",
    "waf-labels": _FEATURE,
    "wavelength": "a location; what runs there is priced on its own elements",
    "well-architected-tool": "the Well-Architected Tool has no charge",
}

# -- reasons something is not priced
_TOKENS = "billed per input and output token by model; no fixed size to estimate"
_PER_REQUEST = "billed per request, image, page or minute processed; no volume to estimate"
_QUOTE = "priced by quote or contract; AWS publishes no on-demand rate"
_OUTPOSTS = "Outposts capacity is bought on a three-year term, priced by quote"
_PER_USER = "billed per user subscription; no user count to estimate"
_MEDIA = "billed per minute of video by resolution, codec and features; no media volume to estimate"
_SECURITY = "billed by the volume of events, resources and data analysed; no volume to estimate"

_UNPRICED: dict[str, str] = {
    "amazon-kinesis-video-streams": "billed per GB ingested, stored and consumed by each stream; no media volume to estimate",
    "kinesis-video-streams": "billed per GB ingested, stored and consumed by each stream; no media volume to estimate",
    "amplify": "Amplify Hosting is billed per build minute, GB stored and GB served; no app to size",
    "amplify-aws-amplify-studio": "Amplify Studio is free; the backends it builds are priced by the services they use",
    "app-studio": "billed per user of the published apps; no user count to estimate",
    "appconfig": "billed per configuration request and per configuration received; no request volume to estimate",
    "appfabric": "billed per connected application per user a month; no user count to estimate",
    "appflow": "billed per flow run and per GB processed; no flow volume to estimate",
    "audit-manager": "billed per resource assessment; no assessment count to estimate",
    "augmented-ai-a2i": "billed per object reviewed by human reviewers; no volume to estimate",
    "b2b-data-interchange": "billed per partnership and per transformation step; no trading volume to estimate",
    "backint-agent": "free agent; SAP HANA backups are billed as the storage they land in",
    "backup-audit-manager": "billed per control evaluation; no evaluation count to estimate",
    "backup-backup-restore": "billed per GB restored for some resource types; no restore volume to estimate",
    "backup-compliance-reporting": "billed per control evaluation; no evaluation count to estimate",
    "bedrock": _TOKENS,
    "bedrock-agentcore": "billed per second of runtime vCPU and memory and per gateway request; no workload to estimate",
    "billing-conductor": "billed per account in each billing group; no account count to estimate",
    "braket": "billed per task and per shot on quantum hardware, per minute on simulators; no workload to estimate",
    "braket-chandelier": "billed per task and per shot on quantum hardware; no workload to estimate",
    "braket-chip": "billed per task and per shot on quantum hardware; no workload to estimate",
    "braket-embedded-simulator": "billed per minute of simulation; no workload to estimate",
    "braket-managed-simulator": "billed per minute of simulation; no workload to estimate",
    "braket-noise-simulator": "billed per minute of simulation; no workload to estimate",
    "braket-qpu": "billed per task and per shot on quantum hardware; no workload to estimate",
    "braket-simulator": "billed per minute of simulation; no workload to estimate",
    "braket-simulator-1": "billed per minute of simulation; no workload to estimate",
    "braket-simulator-2": "billed per minute of simulation; no workload to estimate",
    "braket-simulator-3": "billed per minute of simulation; no workload to estimate",
    "braket-simulator-4": "billed per minute of simulation; no workload to estimate",
    "braket-state-vector": "billed per minute of simulation; no workload to estimate",
    "braket-tensor-network": "billed per minute of simulation; no workload to estimate",
    "chime": _PER_USER,
    "chime-sdk": "billed per attendee minute, message and media pipeline; no usage to estimate",
    "clean-rooms": "billed per CRPU-hour of the queries run; no query volume to estimate",
    "cloud-digital-interface": _QUOTE,
    "cloud-directory": "billed per GB stored and per read and write; no directory size to estimate",
    "cloudsearch-search-documents": "billed per batch of documents uploaded; no upload volume to estimate",
    "cloudwatch-evidently": "billed per event and per analysis unit; no experiment volume to estimate",
    "cloudwatch-metrics-insights": "billed through the metrics its alarms and queries analyse; no query volume to estimate",
    "codeartifact": "billed per GB stored and per request; no package volume to estimate",
    "codecatalyst": "billed per space by tier and per active user; no team to size",
    "codecommit": "billed per active user beyond five; closed to new customers",
    "codeguru": "billed per line of code scanned or per profiled hour; no code base to size",
    "codewhisperer": _PER_USER,
    "comprehend": _PER_REQUEST,
    "comprehend-medical": _PER_REQUEST,
    "connect": "billed per minute of voice and per chat message by channel and country; no contact volume to estimate",
    "data-exchange": "data products are priced by their providers",
    "data-exchange-for-apis": "data products are priced by their providers",
    "data-transfer-terminal": "billed per port-hour reserved at a terminal location; no booking to estimate",
    "datasync-discovery": "AWS's price list holds no rate for DataSync Discovery",
    "datazone": "billed per user and per metadata stored and requested; no user count to estimate",
    "datazone-business-data-catalog": "billed per user and per metadata stored and requested; no user count to estimate",
    "datazone-data-portal": "billed per user and per metadata stored and requested; no user count to estimate",
    "datazone-data-projects": "billed per user and per metadata stored and requested; no user count to estimate",
    "deadline-cloud": "billed per minute of worker compute and per licence used; no render workload to estimate",
    "deepracer": "billed per hour of training and evaluation; no training time to estimate",
    "detective": _SECURITY,
    "devops-agent": "billed per agent usage; no workload to estimate",
    "devops-guru": "billed per resource hour analysed and per API call; no resource count to estimate",
    "devops-guru-insights": "billed per resource hour analysed and per API call; no resource count to estimate",
    "device-farm": "billed per device minute or per device slot; no test time to estimate",
    "ec2-spot-instance": "billed at the Spot price, which moves with supply and demand; AWS sets no fixed rate",
    "eks-anywhere": "EKS Anywhere support is a one- or three-year subscription per cluster; no on-demand rate",
    "elastic-inference": "Elastic Inference is no longer offered; AWS sells no new capacity",
    "elastic-kubernetes-service-eks-on-outposts": _OUTPOSTS,
    "elastic-vmware-service": "billed per i4i.metal host plus VMware Cloud Foundation licences bought separately; no host count to estimate",
    "elemental-appliances-software": _QUOTE,
    "elemental-conductor": _QUOTE,
    "elemental-delta": _QUOTE,
    "elemental-inference": _MEDIA,
    "elemental-link": "a device bought outright, priced per unit",
    "elemental-live": _QUOTE,
    "elemental-mediaconnect": "billed per flow hour and per GB transferred; no stream to size",
    "elemental-mediaconnect-mediaconnect-gateway": "billed per gateway instance hour and per GB; no stream to size",
    "elemental-mediaconvert": _MEDIA,
    "elemental-medialive": "billed per channel hour by input and output resolution; no channel to size",
    "elemental-mediapackage": "billed per GB ingested and delivered; no stream to size",
    "elemental-mediastore": "billed per GB stored and per request; discontinued for new customers",
    "elemental-mediatailor": "billed per thousand ads inserted; no audience to estimate",
    "elemental-server": _QUOTE,
    "end-user-messaging": "SMS and voice are billed per message by destination country; no message volume to estimate",
    "entity-resolution": "billed per record processed; no record volume to estimate",
    "fault-injection-service": "billed per action-minute of experiments run; no experiment to size",
    "finops-agent": "billed per agent usage; no workload to estimate",
    "finspace": "billed per environment, user and kdb cluster hour; no environment to size",
    "firewall-manager": "billed per protection policy per region, plus the firewalls it creates; no policy count to estimate",
    "forecast": _PER_REQUEST,
    "fraud-detector": _PER_REQUEST,
    "gamelift-servers": "billed per instance hour of each fleet by instance type and location; no fleet to size",
    "gamelift-streams": "billed per stream class hour; no stream capacity to size",
    "ground-station": "billed per antenna minute reserved; no contact schedule to estimate",
    "guardduty": _SECURITY,
    "healthimaging": "billed per GB stored and per API request; no image volume to estimate",
    "healthlake": "billed per data store hour and per GB stored and queried; no data store to size",
    "healthomics": "billed per workflow run compute hour and per GB stored; no workflow to size",
    "healthscribe": "billed per second of audio processed; no audio volume to estimate",
    "inspector": _SECURITY,
    "inspector-agent": _SECURITY,
    "interactive-video-service": "billed per hour of video input and output by quality; no audience to estimate",
    "interconnect": "AWS Interconnect is priced per connection by bandwidth through its partners; no connection to size",
    "iot-core-device-advisor": "billed per test case minute; no test volume to estimate",
    "iot-core-device-location": "billed per location resolved; no device volume to estimate",
    "iot-device-defender": "billed per device audited and per metric datapoint; no fleet to size",
    "iot-device-defender-iot-device-jobs": "billed per remote action executed; no job volume to estimate",
    "iot-device-management": "billed per job execution and per fleet indexing operation; no fleet to size",
    "iot-device-management-fleet-hub": "billed per device managed by the application; no fleet to size",
    "iot-device-tester": "Device Tester is free to download; tests run against priced IoT services",
    "iot-events": "billed per message evaluated; no message volume to estimate",
    "iot-expresslink": "a hardware module bought from its makers",
    "iot-fleetwise": "billed per vehicle per month and per message; no fleet to size",
    "iot-greengrass": "billed per active core device a month; no fleet to size",
    "iot-over-air-update": "billed per remote action executed; no job volume to estimate",
    "iot-simulator": "the simulator runs on priced IoT Core and compute",
    "iot-sitewise": "billed per message, property and GB stored; no asset model to size",
    "iot-sitewise-asset": "billed per message, property and GB stored; no asset model to size",
    "iot-sitewise-asset-hierarchy": "billed per message, property and GB stored; no asset model to size",
    "iot-sitewise-asset-model": "billed per message, property and GB stored; no asset model to size",
    "iot-sitewise-asset-properties": "billed per message, property and GB stored; no asset model to size",
    "iot-sitewise-data-streams": "billed per message, property and GB stored; no asset model to size",
    "iot-twinmaker": "billed per entity, API call and query; no twin to size",
    "iq": "experts are paid at the price they quote",
    "kendra": "billed per index edition hour plus connectors and queries; no index to size",
    "lex": _PER_REQUEST,
    "lightsail": "billed per bundle plan by size and operating system; plans are not in the price table",
    "lightsail-for-research": "billed per application bundle by size; plans are not in the price table",
    "location-service": "billed per request by API; no request volume to estimate",
    "location-service-geofence": "billed per request by API; no request volume to estimate",
    "location-service-map": "billed per map tile request; no request volume to estimate",
    "location-service-place": "billed per place request; no request volume to estimate",
    "location-service-routes": "billed per route calculated; no request volume to estimate",
    "location-service-track": "billed per position update; no device volume to estimate",
    "lookout-for-equipment": "billed per GB ingested and per inference hour; no asset to size",
    "lookout-for-vision": _PER_REQUEST,
    "macie": _SECURITY,
    "mainframe-modernization": "billed per runtime environment instance hour by engine; no environment to size",
    "mainframe-modernization-analyzer": "billed by quote through partners",
    "mainframe-modernization-compiler": "billed by quote through partners",
    "mainframe-modernization-converter": "billed by quote through partners",
    "mainframe-modernization-developer": "billed by quote through partners",
    "mainframe-modernization-runtime": "billed per runtime environment instance hour by engine; no environment to size",
    "managed-blockchain": "billed per node hour by size, per GB stored and per request; no network to size",
    "managed-blockchain-blockchain": "billed per node hour by size, per GB stored and per request; no network to size",
    "managed-services": "AMS fees are a share of the AWS bill under contract",
    "monitron": "sensors and gateways are bought outright, then billed per sensor a year",
    "nova": _TOKENS,
    "oracle-database-at-aws": "bought through AWS Marketplace offers from Oracle; no on-demand AWS rate",
    "outposts-family": _OUTPOSTS,
    "outposts-rack": _OUTPOSTS,
    "outposts-servers": _OUTPOSTS,
    "panorama": "the appliance is bought outright, then billed per camera stream a month",
    "parallel-computing-service": "billed per cluster controller size hour and per managed node hour; no cluster to size",
    "partner-central": "a programme for AWS partners, not a billed resource",
    "payment-cryptography": "billed per active key a month and per API call; no key count to estimate",
    "personalize": "billed per GB ingested, training hour and recommendation; no workload to estimate",
    "pinpoint": "billed per targeted endpoint and per message by channel; no audience to estimate",
    "pinpoint-apis": "billed per message by channel and country; no message volume to estimate",
    "pinpoint-journey": "billed per targeted endpoint and per message by channel; no audience to estimate",
    "polly": "billed per million characters synthesised by voice type; no text volume to estimate",
    "professional-services": _QUOTE,
    "q": _PER_USER,
    "quick": _PER_USER,
    "red-hat-openshift-service-on-aws": "Red Hat's service fee per worker vCPU is billed apart from EC2; not in the AWS price list",
    "redshift-dense-storage-node": "DS2 nodes are retired; AWS lists no on-demand rate for new clusters",
    "rekognition": _PER_REQUEST,
    "rekognition-image": _PER_REQUEST,
    "rekognition-video": "billed per minute of video analysed; no video volume to estimate",
    "repost-private": _QUOTE,
    "resilience-hub": "billed per application assessed a month; no application count to estimate",
    "rtb-fabric": "billed per transaction routed between bidders; no traffic to estimate",
    "s3-on-outposts": _OUTPOSTS,
    "sagemaker": "billed per instance hour by instance type and per usage of each SageMaker feature; no workload to size",
    "sagemaker-ai": "billed per instance hour by instance type and per usage of each SageMaker feature; no workload to size",
    "sagemaker-ai-canvas": "billed per session hour and per model trained; no usage to estimate",
    "sagemaker-ai-geospatial-ml": "billed per data processed and per notebook hour; no workload to size",
    "sagemaker-ai-model": "billed per inference instance hour or per serverless request; no endpoint to size",
    "sagemaker-ai-notebook": "billed per notebook instance hour by instance type; no notebook to size",
    "sagemaker-ai-shadow-testing": "billed as the shadow endpoint's inference instances; no endpoint to size",
    "sagemaker-ai-train": "billed per training instance second by instance type; no training job to size",
    "sagemaker-ground-truth": "billed per object labelled; no dataset to size",
    "security-agent": "billed per agent usage; no workload to estimate",
    "security-hub": _SECURITY,
    "security-hub-finding": _SECURITY,
    "security-incident-response": "a monthly subscription priced by the account's spend",
    "security-lake": "billed per GB ingested and normalised; no log volume to estimate",
    "service-catalog": "billed per API call beyond the first thousand a month; no call volume to estimate",
    "simple-storage-service-s3-batch-operations": "billed per job and per million objects processed; no job to size",
    "simple-storage-service-s3-files": "billed per GB of file data and per read and write; no file system to size",
    "simple-storage-service-s3-multi-region-access-points": "billed per GB routed through the access point; no traffic to estimate",
    "simple-storage-service-s3-object-lambda": "billed per GB returned plus the Lambda function's invocations; no traffic to estimate",
    "simple-storage-service-s3-object-lambda-access-points": "billed per GB returned plus the Lambda function's invocations; no traffic to estimate",
    "simple-storage-service-s3-on-outposts": _OUTPOSTS,
    "simple-storage-service-s3-replication": "billed as the replica's storage and requests on the destination bucket plus data transfer; price the destination bucket",
    "simple-storage-service-s3-replication-time-control": "billed per GB replicated on top of replication; no replication volume to estimate",
    "simple-storage-service-s3-select": "billed per GB scanned and returned by queries; no query volume to estimate",
    "simple-storage-service-s3-vectors": "billed by vectors stored, written and queried; no index to size",
    "simspace-weaver": "billed per worker hour by instance type and per GB of snapshot; no simulation to size",
    "snowball": "billed per device job, its days on site and shipping; no job to estimate",
    "snowball-edge": "billed per device job, its days on site and shipping; no job to estimate",
    "snowball-snowball-import-export": "billed per device job, its days on site and shipping; no job to estimate",
    "spot-fleet": "billed at the Spot price, which moves with supply and demand; AWS sets no fixed rate",
    "supply-chain": "a monthly subscription per instance plus storage; no instance to size",
    "support": "support plans are a share of the monthly AWS bill, with a minimum",
    "systems-manager-automation": "billed per step run beyond the free steps; no runbook volume to estimate",
    "systems-manager-change-manager": "billed per change request and per API call; no change volume to estimate",
    "systems-manager-incident-manager": "billed per response plan and per incident; no plan count to estimate",
    "systems-manager-opscenter": "billed per OpsItem and per API call; no item count to estimate",
    "telco-network-builder": "billed per network operation and per GB of network data; no network to size",
    "textract": _PER_REQUEST,
    "textract-analyze-lending": _PER_REQUEST,
    "thinkbox-deadline": "usage-based licences are billed per hour of each render product; no render farm to size",
    "thinkbox-frost": "usage-based licences are billed per hour; no render workload to estimate",
    "thinkbox-krakatoa": "usage-based licences are billed per hour; no render workload to estimate",
    "thinkbox-stoke": "usage-based licences are billed per hour; no render workload to estimate",
    "thinkbox-xmesh": "usage-based licences are billed per hour; no render workload to estimate",
    "training-certification": "courses and exams are priced individually",
    "transcribe": "billed per second of audio transcribed; no audio volume to estimate",
    "transform": "billed per job or agent usage; no workload to estimate",
    "translate": "billed per million characters translated; no text volume to estimate",
    "verified-permissions": "billed per authorization request; no request volume to estimate",
    "vpc-flow-logs": "billed per GB of flow logs delivered, by destination; no traffic volume to estimate",
    "wickr": _PER_USER,
    "workdocs": _PER_USER,
    "workdocs-sdk": _PER_USER,
    "workmail": _PER_USER,
    "workspaces": "billed per WorkSpace by bundle, running mode and licence; no desktop fleet to size",
}

COVERAGE = Coverage(
    cloud="aws",
    default_region="us-east-1",
    region_of=region_of,
    pricers=_PRICERS,
    free=_FREE,
    unpriced=_UNPRICED,
)
