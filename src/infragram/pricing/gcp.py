"""Google Cloud prices: the Cloud Billing Catalog API.

The table (``assets/prices/gcp.json``) is built from the Catalog API's SKUs
by :mod:`infragram.pricing.build.gcp`, with the machine types' vCPUs and
memory read from the Compute Engine machine-family pages. A Compute Engine
machine type is priced as Google bills it: its vCPUs at the series' core
rate plus its GiB at the series' RAM rate (a shared-core type at its share
of a vCPU), its GPUs at the GPU rate, a Windows licence per vCPU.

Every figure is the on-demand list price before any free tier, committed
use or sustained use discount. A rate held for a multi-region (``us``,
``eu``, ``asia``) or for ``global`` prices a region that has none of its own.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from ..models.topology import TopologyElement
from . import Price, PriceLine, PricingError
from .ask import Ask, Coverage, Pricer, line, priced
from .tables import Service

__all__ = ["COVERAGE", "region_of"]

#: A Google Cloud region as Google names them: us-central1, europe-west4.
REGION = re.compile(r"\b([a-z]+-[a-z]+\d+)\b")


def region_of(ancestors: tuple[TopologyElement, ...]) -> str | None:
    for frame in reversed(ancestors):
        if frame.type == "region" and (match := REGION.search(frame.name.lower())):
            return match.group(1)
    return None


# -- reading the table --------------------------------------------------------

#: The multi-region a region's rate falls back to.
_MULTI = (("us", ("us-", "northamerica-")), ("eu", ("europe-",)), ("asia", ("asia-",)))
#: A dual-region code: nam4, eur4, asia1.
_DUAL = re.compile(r"^[a-z]{3,4}\d+$")


def _places(region: str) -> list[str]:
    multi = [name for name, prefixes in _MULTI if region.startswith(prefixes)]
    return [region, *multi, "global"]


def _rate(ask: Ask, name: str, region: str, *rest: str) -> float:
    """*name*'s rate at *region*, else at its multi-region, else ``global``."""
    service = ask.table.service(name)
    refused: PricingError | None = None
    for place in _places(region):
        if place in service.rates:
            try:
                return service.rate(place, *rest)
            except PricingError as error:
                refused = refused or error
    if refused is not None:
        raise refused
    return service.rate(region, *rest)


def _choices(ask: Ask, name: str, region: str, *rest: str) -> list[str] | None:
    """The values the next key takes at *region* (or where it falls back to):
    None when the table has none, so the lookup that follows names what it does have."""
    service = ask.table.service(name)
    for place in _places(region):
        if held := service.choices(place, *rest):
            return held
    return None


def _source(ask: Ask, name: str) -> tuple[str, str]:
    service: Service = ask.table.service(name)
    return service.source, service.published


def _optional(ask: Ask, key: str) -> Any:
    """The sizing's *key* if it says it; never a default, never assumed."""
    ask.taken.add(key)
    value = ask.sizing.get(key)
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise PricingError(f"{ask.name}: {key} {value!r} is not the right kind of value")
    return value


def _number(ask: Ask, key: str) -> float | None:
    value = _optional(ask, key)
    if value is not None and not isinstance(value, (int, float)):
        raise PricingError(f"{ask.name}: {key} {value!r} is not a number")
    if value is not None and value < 0:
        raise PricingError(f"{ask.name}: {key} must be 0 or more, not {value}")
    return value


def _dollars(rate: float) -> str:
    return f"${rate:.6g}"


# -- Compute Engine -----------------------------------------------------------


class Shape(BaseModel):
    """A machine: what it is called, its series, and what it holds."""

    name: str
    series: str
    vcpus: float
    memory_gb: float
    gpus: float = 0
    gpu: str = ""
    custom: bool = False


#: custom-4-16384, n2-custom-4-16384, n2-custom-4-16384-ext: vCPUs and MB.
_CUSTOM = re.compile(r"^(?:(?P<series>[a-z][a-z0-9]*)-)?custom-(?P<cpus>\d+)-(?P<mb>\d+)(?:-ext)?$")
#: The shared-core types: a Windows licence is per instance, not per vCPU.
_SHARED = frozenset({"f1-micro", "g1-small", "e2-micro", "e2-small", "e2-medium"})


def _shape(ask: Ask, machine_type: str) -> Shape:
    """A machine type's shape: a custom type from its name, else from the
    machine-family pages' table."""
    custom = _CUSTOM.match(machine_type)
    if custom:
        return Shape(
            name=machine_type,
            series=custom.group("series") or "n1",
            vcpus=int(custom.group("cpus")),
            memory_gb=int(custom.group("mb")) / 1024,
            custom=True,
        )
    types = ask.table.service("machine_types")
    if machine_type not in types.rates:
        types.rate(machine_type, "vcpus")  # refuses, naming the nearest types
    fields = types.rates[machine_type]
    return Shape(
        name=machine_type,
        series=machine_type.split("-")[0],
        vcpus=float(fields["vcpus"]),
        memory_gb=float(fields["memory_gb"]),
        gpus=float(fields.get("gpus", 0)),
        gpu=types.info.get("gpu", {}).get(machine_type, ""),
    )


def _machine(ask: Ask, default: str, *, prefix: str = "") -> Shape:
    """The machine the sizing names: ``machine_type``, or ``vcpus`` and
    ``memory_gb`` (a custom machine of ``series``)."""
    vcpus = _number(ask, f"{prefix}vcpus")
    memory = _number(ask, f"{prefix}memory_gb")
    if vcpus is None and memory is None:
        name = str(ask.take(f"{prefix}machine_type", default, kind=str)).strip().lower()
        return _shape(ask, name)
    if f"{prefix}machine_type" in ask.sizing:
        raise PricingError(
            f"{ask.name}: give {prefix}machine_type, or {prefix}vcpus and {prefix}memory_gb, "
            f"not both"
        )
    if vcpus is None or memory is None:
        raise PricingError(
            f"{ask.name}: a custom machine needs {prefix}vcpus and {prefix}memory_gb"
        )
    series = str(ask.take(f"{prefix}series", "n2", kind=str)).strip().lower()
    return Shape(
        name=f"{series}-custom-{vcpus:g}-{memory * 1024:g}",
        series=series,
        vcpus=vcpus,
        memory_gb=memory,
        custom=True,
    )


def _instance_rate(ask: Ask, region: str, shape: Shape) -> tuple[float, str]:
    """A machine's hourly rate: vCPUs at the core rate plus GiB at the RAM rate."""
    compute = ask.table.service("compute")
    if shape.name in ("f1-micro", "g1-small") and "instance" in compute.choices(
        region, shape.series
    ):
        rate = compute.rate(region, shape.series, "instance")
        return rate, f"{shape.name} at {_dollars(rate)}/h"
    held = compute.choices(region, shape.series)
    core_key, ram_key = "core", "ram"
    if shape.custom and "custom-core" in held and "custom-ram" in held:
        core_key, ram_key = "custom-core", "custom-ram"
    core = compute.rate(region, shape.series, core_key)
    ram = compute.rate(region, shape.series, ram_key)
    words = (
        f"{shape.vcpus:g} vCPU x {_dollars(core)}/h + {shape.memory_gb:g} GiB x {_dollars(ram)}/h"
    )
    return shape.vcpus * core + shape.memory_gb * ram, words


def _gpu_rate(ask: Ask, region: str, model: str) -> tuple[float, str]:
    """The hourly rate of one *model* GPU: the table's own name for it, else
    the nearest it holds (``h100`` -> ``h100-80gb``)."""
    service = ask.table.service("gpu")
    held = service.choices(region)
    if not held:
        service.rate(region, model)  # refuses, naming the regions it has
    name = model if model in held else None
    if name is None:
        near = sorted((g for g in held if g.startswith(f"{model}-")), key=len)
        if not near:
            raise PricingError(
                f"{ask.name}: no {model} GPU rate in {region}; it has {', '.join(held[:10])}"
            )
        name = near[0]
    return service.rate(region, name), name


def _vm_lines(
    ask: Ask,
    region: str,
    shape: Shape,
    *,
    count: int,
    hours: float,
    windows: bool = False,
    label: str = "",
    assumed: bool = False,
) -> tuple[list[PriceLine], list[str]]:
    """A machine's lines for *count* of them over *hours*: the instance, its
    GPUs, its Windows licence; and the words for what was priced."""
    rate, words = _instance_rate(ask, region, shape)
    name = label or shape.name
    lines = [line(f"{name} ({count} x {hours:g} h)", count * hours, "hours", rate, assumed=assumed)]
    notes = [words]
    if shape.gpus:
        each, model = _gpu_rate(ask, region, shape.gpu)
        lines.append(
            line(
                f"{name} GPUs ({shape.gpus:g} x {model})",
                count * hours,
                "hours",
                shape.gpus * each,
                assumed=assumed,
            )
        )
        notes.append(f"{shape.gpus:g} x {model} GPU at {_dollars(each)}/h")
    if windows:
        service = ask.table.service("windows")
        shared = shape.name in _SHARED and "shared" in (
            service.choices("global") or service.choices(region)
        )
        each = _rate(ask, "windows", region, "shared" if shared else "core")
        licence = each if shared else each * max(shape.vcpus, 1)
        lines.append(line(f"{name} Windows licence", count * hours, "hours", licence))
        notes.append(f"Windows Server licence {_dollars(licence)}/h")
    return lines, notes


def _disk_line(
    ask: Ask, region: str, *, size: float, kind: str, label: str, count: int = 1
) -> PriceLine:
    rate = _rate(ask, "disk", region, kind)
    return line(
        f"{label} ({size:g} GB {kind})",
        size * count,
        "GB-month",
        rate,
        assumed=ask.was_assumed("disk_gb", "disk_type", "size_gb", "type"),
    )


def price_compute(ask: Ask) -> Price:
    """Compute Engine VMs: the machine, its GPUs, a Windows licence, its boot disk."""
    region = ask.region()
    shape = _machine(ask, "e2-standard-2")
    count, hours = ask.count(), ask.hours()
    os_name = ask.take("os", "linux", choices=("linux", "windows"))
    gpu = _optional(ask, "gpu")
    gpu_count = _number(ask, "gpu_count")
    if gpu is not None or gpu_count:
        if shape.gpus:
            raise PricingError(f"{ask.name}: {shape.name} comes with its GPUs; gpu is not added")
        shape = shape.model_copy(update={"gpu": str(gpu or "t4").lower(), "gpus": gpu_count or 1})
    disk_gb = ask.amount("disk_gb", 10)
    if disk_gb:
        disk_type = ask.take("disk_type", "pd-balanced", choices=_choices(ask, "disk", region))
    else:
        disk_type = str(_optional(ask, "disk_type") or "none")
    lines, notes = _vm_lines(
        ask,
        region,
        shape,
        count=count,
        hours=hours,
        windows=os_name == "windows",
        assumed=ask.was_assumed("machine_type", "count", "hours"),
    )
    if disk_gb:
        lines.append(
            _disk_line(ask, region, size=disk_gb, kind=disk_type, label="Boot disk", count=count)
        )
    source, published = _source(ask, "compute")
    return priced(
        ask,
        lines,
        sizing={
            "region": region,
            "machine_type": shape.name,
            "vcpus": shape.vcpus,
            "memory_gb": shape.memory_gb,
            **({"gpu": shape.gpu, "gpus": shape.gpus} if shape.gpus else {}),
            "os": os_name,
            "count": count,
            "hours": hours,
            "disk_type": disk_type,
            "disk_gb": disk_gb,
        },
        rate=f"Compute Engine on-demand, {os_name}: " + "; ".join(notes),
        source=source,
        published=published,
    )


def price_gpu(ask: Ask) -> Price:
    """GPUs attached to a VM: the GPUs alone; the VM is its own card."""
    region = ask.region()
    model = str(ask.take("gpu", "t4", kind=str)).strip().lower()
    gpus = ask.amount("gpu_count", 1, low=0.125)
    count, hours = ask.count(), ask.hours()
    each, name = _gpu_rate(ask, region, model)
    source, published = _source(ask, "gpu")
    return priced(
        ask,
        [
            line(
                f"{gpus:g} x {name} GPU ({count} x {hours:g} h)",
                count * hours,
                "hours",
                gpus * each,
                assumed=ask.was_assumed("gpu", "gpu_count", "count", "hours"),
            )
        ],
        sizing={"region": region, "gpu": name, "gpu_count": gpus, "count": count, "hours": hours},
        rate=f"Compute Engine GPU on-demand, {name} at {_dollars(each)}/h",
        source=source,
        published=published,
    )


#: The disk a disk component is, and its size, when the sizing does not say.
_DISKS = {
    "persistent-disk": ("pd-balanced", 100),
    "hyperdisk": ("hyperdisk-balanced", 100),
    "local-ssd": ("local-ssd", 375),
}
#: What a Hyperdisk includes before provisioned performance is billed.
_BASELINE = {"hyperdisk-balanced": {"iops": 3000.0, "throughput": 140.0}}


def price_disk(ask: Ask) -> Price:
    """Persistent Disk, Hyperdisk and Local SSD: GB-months, plus Hyperdisk's
    provisioned IOPS and throughput above what it includes."""
    region = ask.region()
    kind, size = _DISKS[ask.service_id]
    disk_type = ask.take("type", kind, choices=_choices(ask, "disk", region))
    size_gb = ask.amount("size_gb", size, low=1)
    count = ask.count()
    lines = [_disk_line(ask, region, size=size_gb, kind=disk_type, label="Disk", count=count)]
    for what, key, unit in (
        ("iops", "iops", "IOPS-months"),
        ("throughput", "throughput_mbps", "MBps-months"),
    ):
        given = _number(ask, key)
        if given is None:
            continue
        if not disk_type.startswith("hyperdisk"):
            raise PricingError(f"{ask.name}: only Hyperdisk is provisioned by {what}")
        billed = max(0.0, given - _BASELINE.get(disk_type, {}).get(what, 0.0))
        if billed:
            rate = _rate(ask, "disk_performance", region, disk_type, what)
            lines.append(line(f"Provisioned {what} ({billed:g})", billed * count, unit, rate))
    source, published = _source(ask, "disk")
    return priced(
        ask,
        lines,
        sizing={"region": region, "type": disk_type, "size_gb": size_gb, "count": count},
        rate=f"{disk_type} capacity, per GB-month",
        source=source,
        published=published,
    )


def price_ip(ask: Ask) -> Price:
    """External IP addresses: in use on a VM, or reserved and unused."""
    region = ask.region()
    state = ask.take("state", "in-use", choices=("in-use", "reserved"))
    count, hours = ask.count(), ask.hours()
    rate = _rate(ask, "ip", region, state)
    source, published = _source(ask, "ip")
    return priced(
        ask,
        [
            line(
                f"{count} external IP ({state})",
                count * hours,
                "hours",
                rate,
                assumed=ask.was_assumed("count", "hours", "state"),
            )
        ],
        sizing={"region": region, "state": state, "count": count, "hours": hours},
        rate=f"External IP address, {state}, {_dollars(rate)}/h",
        source=source,
        published=published,
    )


# -- databases ----------------------------------------------------------------

_SQL_TIER = re.compile(r"^db-custom-(?P<cpus>\d+)-(?P<mb>\d+)$")
_SQL_PERF = re.compile(r"^db-perf-optimized-n-(?P<cpus>\d+)$")
_SQL_SHARED = ("db-f1-micro", "db-g1-small")


def _sql_shape(ask: Ask) -> tuple[str, float, float]:
    """(tier, vCPUs, GiB): a tier name, or vcpus and memory_gb."""
    vcpus, memory = _number(ask, "vcpus"), _number(ask, "memory_gb")
    if vcpus is not None or memory is not None:
        if "tier" in ask.sizing or vcpus is None or memory is None:
            raise PricingError(f"{ask.name}: give tier, or vcpus and memory_gb")
        return f"db-custom-{vcpus:g}-{memory * 1024:g}", vcpus, memory
    tier = str(ask.take("tier", "db-custom-2-8192", kind=str)).strip().lower()
    if tier in _SQL_SHARED:
        return tier, 0.0, 0.0
    if match := _SQL_TIER.match(tier):
        return tier, int(match.group("cpus")), int(match.group("mb")) / 1024
    if match := _SQL_PERF.match(tier):
        cpus = int(match.group("cpus"))
        return tier, cpus, cpus * 8.0
    if tier.startswith("db-"):
        shape = _shape(ask, tier[3:])
        return tier, shape.vcpus, shape.memory_gb
    raise PricingError(
        f"{ask.name}: tier {tier!r} is not a Cloud SQL tier (db-custom-2-8192, db-f1-micro, "
        f"db-n1-standard-2)"
    )


def price_sql(ask: Ask) -> Price:
    """Cloud SQL: vCPUs and memory, storage, high availability, a SQL Server licence."""
    region = ask.region()
    engine = ask.take("engine", "postgres", choices=("mysql", "postgres", "sqlserver"))
    edition = ask.take("edition", "enterprise", choices=("enterprise", "enterprise-plus"))
    tier, vcpus, memory = _sql_shape(ask)
    ha = ask.take("ha", False, kind=bool)
    count, hours = ask.count(), ask.hours()
    storage_type = ask.take("storage_type", "ssd", choices=("ssd", "hdd"))
    storage_gb = ask.amount("storage_gb", 100, low=10)

    def rate(item: str) -> tuple[float, str]:
        # high availability is billed at the regional rate, twice the zonal one
        if ha:
            try:
                return _rate(ask, "cloud_sql", region, engine, edition, "regional", item), ""
            except PricingError:
                pass
        zonal = _rate(ask, "cloud_sql", region, engine, edition, "zonal", item)
        return (zonal * 2, " (zonal x 2)") if ha else (zonal, "")

    if tier in _SQL_SHARED:
        if engine == "sqlserver":
            raise PricingError(f"{ask.name}: SQL Server has no shared-core tier")
        hourly, note = rate(tier)
        words = f"{tier} at {_dollars(hourly)}/h{note}"
    else:
        core, note = rate("core")
        ram, _ = rate("ram")
        hourly = vcpus * core + memory * ram
        words = f"{vcpus:g} vCPU x {_dollars(core)}/h + {memory:g} GiB x {_dollars(ram)}/h{note}"
    lines = [
        line(
            f"{tier} {'HA' if ha else 'zonal'} ({count} x {hours:g} h)",
            count * hours,
            "hours",
            hourly,
            assumed=ask.was_assumed("tier", "ha", "count", "hours"),
        )
    ]
    storage, _ = rate(f"storage-{storage_type}")
    lines.append(
        line(
            f"Storage ({storage_gb:g} GB {storage_type})",
            storage_gb * count,
            "GB-month",
            storage,
            assumed=ask.was_assumed("storage_gb", "storage_type"),
        )
    )
    sizing: dict[str, Any] = {
        "region": region,
        "engine": engine,
        "edition": edition,
        "tier": tier,
        "vcpus": vcpus,
        "memory_gb": memory,
        "ha": ha,
        "count": count,
        "hours": hours,
        "storage_type": storage_type,
        "storage_gb": storage_gb,
    }
    if engine == "sqlserver":
        licence = ask.take(
            "license", "standard", choices=("standard", "enterprise", "web", "express")
        )
        sizing["license"] = licence
        if licence != "express":
            each = _rate(ask, "sql_license", region, licence)
            lines.append(
                line(
                    f"SQL Server {licence} licence",
                    count * hours,
                    "hours",
                    each * vcpus,
                    assumed=ask.was_assumed("license"),
                )
            )
    source, published = _source(ask, "cloud_sql")
    return priced(
        ask,
        lines,
        sizing=sizing,
        rate=f"Cloud SQL for {engine}, {edition}, {'high availability' if ha else 'zonal'}: {words}",
        source=source,
        published=published,
    )


def price_alloydb(ask: Ask) -> Price:
    """AlloyDB: the primary's vCPUs and memory (two nodes when highly
    available), and the storage it holds."""
    region = ask.region()
    vcpus = ask.amount("vcpus", 2, low=1)
    memory = ask.amount("memory_gb", 16, low=1)
    ha = ask.take("ha", True, kind=bool)
    count, hours = ask.count(), ask.hours()
    storage_gb = ask.amount("storage_gb", 100)
    nodes = 2 if ha else 1
    core = _rate(ask, "alloydb", region, "vcpu")
    ram = _rate(ask, "alloydb", region, "memory")
    lines = [
        line(
            f"Primary, {nodes} node{'s' if nodes > 1 else ''} ({count} x {hours:g} h)",
            count * hours,
            "hours",
            nodes * (vcpus * core + memory * ram),
            assumed=ask.was_assumed("vcpus", "memory_gb", "ha", "count", "hours"),
        ),
        line(
            f"Storage ({storage_gb:g} GB)",
            storage_gb * count,
            "GB-month",
            _rate(ask, "alloydb", region, "storage"),
            kind="usage",
            assumed=ask.was_assumed("storage_gb"),
        ),
    ]
    source, published = _source(ask, "alloydb")
    return priced(
        ask,
        lines,
        sizing={
            "region": region,
            "vcpus": vcpus,
            "memory_gb": memory,
            "ha": ha,
            "count": count,
            "hours": hours,
            "storage_gb": storage_gb,
        },
        rate=f"AlloyDB: {vcpus:g} vCPU x {_dollars(core)}/h + {memory:g} GiB x {_dollars(ram)}/h"
        f" per node",
        source=source,
        published=published,
    )


#: Memorystore for Redis capacity bands, by the largest GB each holds.
_BANDS = ((4, "m1"), (10, "m2"), (35, "m3"), (100, "m4"), (300, "m5"))


def price_memorystore(ask: Ask) -> Price:
    """Memorystore for Redis: capacity at its tier's and band's GB-hour rate."""
    region = ask.region()
    tier = ask.take("tier", "basic", choices=("basic", "standard"))
    capacity = ask.amount("capacity_gb", 1, low=1, high=300)
    count, hours = ask.count(), ask.hours()
    band = next(name for top, name in _BANDS if capacity <= top)
    each = _rate(ask, "memorystore", region, tier, band)
    source, published = _source(ask, "memorystore")
    return priced(
        ask,
        [
            line(
                f"Redis {tier} {capacity:g} GB ({count} x {hours:g} h)",
                count * hours,
                "hours",
                capacity * each,
                assumed=ask.was_assumed("tier", "capacity_gb", "count", "hours"),
            )
        ],
        sizing={
            "region": region,
            "tier": tier,
            "capacity_gb": capacity,
            "count": count,
            "hours": hours,
        },
        rate=f"Memorystore for Redis {tier} {band.upper()}, {_dollars(each)} per GB-hour",
        source=source,
        published=published,
    )


def price_spanner(ask: Ask) -> Price:
    """Spanner: compute in nodes (1,000 processing units each), and storage."""
    region = ask.region()
    units = _number(ask, "processing_units")
    if units is not None:
        if "nodes" in ask.sizing:
            raise PricingError(f"{ask.name}: give nodes or processing_units, not both")
        nodes = units / 1000
    else:
        nodes = ask.amount("nodes", 1, low=0.1)
    hours = ask.hours()
    storage_gb = ask.amount("storage_gb", 100)
    service = ask.table.service("spanner")
    held = _choices(ask, "spanner", region) or []
    if "node" in held or "processing-unit" not in held:
        node = _rate(ask, "spanner", region, "node")
    else:
        node = _rate(ask, "spanner", region, "processing-unit") * 1000
    source, published = service.source, service.published
    return priced(
        ask,
        [
            line(
                f"Compute ({nodes:g} nodes x {hours:g} h)",
                hours,
                "hours",
                nodes * node,
                assumed=ask.was_assumed("nodes", "hours"),
            ),
            line(
                f"Storage ({storage_gb:g} GB)",
                storage_gb,
                "GB-month",
                _rate(ask, "spanner", region, "storage"),
                kind="usage",
                assumed=ask.was_assumed("storage_gb"),
            ),
        ],
        sizing={"region": region, "nodes": nodes, "hours": hours, "storage_gb": storage_gb},
        rate=f"Spanner, {_dollars(node)} per node-hour",
        source=source,
        published=published,
    )


def price_bigtable(ask: Ask) -> Price:
    """Bigtable: nodes by the hour, and the data stored on SSD or HDD."""
    region = ask.region()
    nodes = ask.count("nodes")
    hours = ask.hours()
    storage_type = ask.take("storage_type", "ssd", choices=("ssd", "hdd"))
    storage_gb = ask.amount("storage_gb", 100)
    node = _rate(ask, "bigtable", region, "node")
    source, published = _source(ask, "bigtable")
    return priced(
        ask,
        [
            line(
                f"Nodes ({nodes} x {hours:g} h)",
                nodes * hours,
                "hours",
                node,
                assumed=ask.was_assumed("nodes", "hours"),
            ),
            line(
                f"Storage ({storage_gb:g} GB {storage_type})",
                storage_gb,
                "GB-month",
                _rate(ask, "bigtable", region, storage_type),
                kind="usage",
                assumed=ask.was_assumed("storage_gb", "storage_type"),
            ),
        ],
        sizing={
            "region": region,
            "nodes": nodes,
            "hours": hours,
            "storage_type": storage_type,
            "storage_gb": storage_gb,
        },
        rate=f"Bigtable, {_dollars(node)} per node-hour",
        source=source,
        published=published,
    )


# -- containers and serverless ------------------------------------------------


def price_gke(ask: Ask) -> Price:
    """GKE: the cluster management fee, and the nodes of a Standard cluster
    (priced as Compute Engine VMs) or the pods of an Autopilot one."""
    region = ask.region()
    mode = ask.take("mode", "standard", choices=("standard", "autopilot"))
    hours = ask.hours()
    fee = _rate(ask, "gke", region, "cluster")
    lines = [line(f"Cluster management fee ({hours:g} h)", hours, "hours", fee)]
    sizing: dict[str, Any] = {"region": region, "mode": mode, "hours": hours}
    notes = [f"cluster fee {_dollars(fee)}/h"]
    if mode == "standard":
        shape = _machine(ask, "e2-medium")
        nodes = ask.count("node_count", 3)
        disk_gb = ask.amount("disk_gb", 100)
        vm_lines, words = _vm_lines(
            ask,
            region,
            shape,
            count=nodes,
            hours=hours,
            label=f"Nodes, {shape.name}",
            assumed=ask.was_assumed("machine_type", "node_count", "hours"),
        )
        lines += vm_lines
        if disk_gb:
            lines.append(
                _disk_line(
                    ask,
                    region,
                    size=disk_gb,
                    kind="pd-balanced",
                    label="Node boot disks",
                    count=nodes,
                )
            )
        notes += words
        sizing.update(machine_type=shape.name, node_count=nodes, disk_gb=disk_gb)
    else:
        vcpus = ask.amount("pod_vcpus", 2, low=0.25)
        memory = ask.amount("pod_memory_gb", 8, low=0.5)
        core = _rate(ask, "gke", region, "autopilot-vcpu")
        ram = _rate(ask, "gke", region, "autopilot-memory")
        lines.append(
            line(
                f"Autopilot pods ({vcpus:g} vCPU, {memory:g} GiB)",
                hours,
                "hours",
                vcpus * core + memory * ram,
                assumed=ask.was_assumed("pod_vcpus", "pod_memory_gb", "hours"),
            )
        )
        notes.append(
            f"pods {vcpus:g} vCPU x {_dollars(core)}/h + {memory:g} GiB x {_dollars(ram)}/h"
        )
        sizing.update(pod_vcpus=vcpus, pod_memory_gb=memory)
    source, published = _source(ask, "gke")
    return priced(
        ask,
        lines,
        sizing=sizing,
        rate=f"GKE {mode}, before the free tier's monthly credit: " + "; ".join(notes),
        source=source,
        published=published,
    )


def _serverless(ask: Ask, *, vcpu: float, memory_gb: float, what: str) -> Price:
    """Cloud Run's request-based billing: vCPU-seconds, GiB-seconds, requests."""
    region = ask.region()
    millions = ask.amount("requests_millions", 1)
    duration = ask.amount("duration_ms", 200)
    cpus = ask.amount("vcpu", vcpu, low=0.08, high=8)
    memory = ask.amount("memory_gb", memory_gb, low=0.125, high=32)
    concurrency = ask.amount("concurrency", 1, low=1, high=1000)
    seconds = millions * 1e6 * duration / 1000 / concurrency
    timed = ask.was_assumed("requests_millions", "duration_ms", "concurrency")
    source, published = _source(ask, "cloud_run")
    return priced(
        ask,
        [
            line(
                "vCPU time",
                seconds * cpus,
                "vCPU-seconds",
                _rate(ask, "cloud_run", region, "cpu"),
                kind="usage",
                assumed=timed or ask.was_assumed("vcpu"),
            ),
            line(
                "Memory time",
                seconds * memory,
                "GiB-seconds",
                _rate(ask, "cloud_run", region, "memory"),
                kind="usage",
                assumed=timed or ask.was_assumed("memory_gb"),
            ),
            line(
                "Requests",
                millions,
                "1M requests",
                _rate(ask, "cloud_run", region, "requests") * 1e6,
                kind="usage",
                assumed=ask.was_assumed("requests_millions"),
            ),
        ],
        sizing={
            "region": region,
            "requests_millions": millions,
            "duration_ms": duration,
            "vcpu": cpus,
            "memory_gb": memory,
            "concurrency": concurrency,
        },
        rate=f"{what}, request-based billing, before the free tier",
        source=source,
        published=published,
    )


def price_run(ask: Ask) -> Price:
    return _serverless(ask, vcpu=1, memory_gb=0.5, what="Cloud Run")


def price_functions(ask: Ask) -> Price:
    return _serverless(
        ask, vcpu=0.167, memory_gb=0.25, what="Cloud Run functions at Cloud Run's rates"
    )


#: App Engine standard instance classes, as multiples of F1 or B1.
_CLASSES = {
    "F1": 1,
    "F2": 2,
    "F4": 4,
    "F4_1G": 6,
    "B1": 1,
    "B2": 2,
    "B4": 4,
    "B4_1G": 6,
    "B8": 8,
}


def price_app_engine(ask: Ask) -> Price:
    """App Engine: standard instance hours by class, or flexible vCPU and memory."""
    region = ask.region()
    environment = ask.take("environment", "standard", choices=("standard", "flexible"))
    instances = ask.count("instances")
    hours = ask.hours()
    sizing: dict[str, Any] = {"region": region, "environment": environment, "instances": instances}
    if environment == "standard":
        cls = ask.take("instance_class", "F1", choices=tuple(_CLASSES))
        base = _rate(ask, "app_engine", region, "frontend" if cls.startswith("F") else "backend")
        hourly, words = base * _CLASSES[cls], f"{cls} at {_dollars(base * _CLASSES[cls])}/h"
        sizing["instance_class"] = cls
    else:
        vcpus = ask.amount("vcpus", 1, low=1)
        memory = ask.amount("memory_gb", 1, low=0.9)
        core = _rate(ask, "app_engine", region, "flex-core")
        ram = _rate(ask, "app_engine", region, "flex-ram")
        hourly = vcpus * core + memory * ram
        words = f"{vcpus:g} vCPU x {_dollars(core)}/h + {memory:g} GiB x {_dollars(ram)}/h"
        sizing.update(vcpus=vcpus, memory_gb=memory)
    sizing["hours"] = hours
    source, published = _source(ask, "app_engine")
    return priced(
        ask,
        [
            line(
                f"Instances ({instances} x {hours:g} h)",
                instances * hours,
                "hours",
                hourly,
                assumed=ask.was_assumed(
                    "instances", "instance_class", "hours", "vcpus", "memory_gb"
                ),
            )
        ],
        sizing=sizing,
        rate=f"App Engine {environment}: {words}",
        source=source,
        published=published,
    )


# -- storage and analytics ----------------------------------------------------


def _storage_ops_rate(ask: Ask, scope: str, cls: str, item: str) -> float:
    service = ask.table.service("storage_ops")
    node = service.rates.get("global", {})
    for held in (scope, "any"):
        if item in node.get(held, {}).get(cls, {}):
            return service.rate("global", held, cls, item)
    return service.rate("global", scope, cls, item)


def price_storage(ask: Ask) -> Price:
    """Cloud Storage: GB stored by class and location, class A and B
    operations, and retrieval from the colder classes."""
    location = ask.region()
    cls = ask.take(
        "storage_class", "standard", choices=("standard", "nearline", "coldline", "archive")
    )
    stored = ask.amount("storage_gb", 100)
    class_a = ask.amount("class_a_millions", 1)
    class_b = ask.amount("class_b_millions", 1)
    retrieval = _number(ask, "retrieval_gb")
    multi = location in ("us", "eu", "asia")
    dual = not multi and bool(_DUAL.match(location))
    scope = "multi-region" if multi else "dual-region" if dual else "regional"
    service = ask.table.service("storage")
    place = location if location in service.rates or not dual else "dual-region"
    lines = [
        line(
            f"Storage ({stored:g} GB {cls})",
            stored,
            "GB-month",
            service.rate(place, cls),
            kind="usage",
            assumed=ask.was_assumed("storage_gb"),
        ),
        line(
            "Class A operations",
            class_a,
            "1M operations",
            _storage_ops_rate(ask, scope, cls, "a") * 1e6,
            kind="usage",
            assumed=ask.was_assumed("class_a_millions"),
        ),
        line(
            "Class B operations",
            class_b,
            "1M operations",
            _storage_ops_rate(ask, scope, cls, "b") * 1e6,
            kind="usage",
            assumed=ask.was_assumed("class_b_millions"),
        ),
    ]
    if retrieval and cls != "standard":
        lines.append(
            line(
                f"Retrieval ({retrieval:g} GB)",
                retrieval,
                "GB",
                _storage_ops_rate(ask, "any", cls, "retrieval"),
                kind="usage",
            )
        )
    return priced(
        ask,
        lines,
        sizing={
            "region": location,
            "storage_class": cls,
            "storage_gb": stored,
            "class_a_millions": class_a,
            "class_b_millions": class_b,
            **({"retrieval_gb": retrieval} if retrieval else {}),
        },
        rate=f"Cloud Storage {cls}, {scope} ({location})",
        source=service.source,
        published=service.published,
    )


def price_filestore(ask: Ask) -> Price:
    """Filestore: provisioned capacity by tier."""
    region = ask.region()
    tier = ask.take("tier", "basic-hdd", choices=_choices(ask, "filestore", region))
    capacity = ask.amount("capacity_gb", 1024, low=1)
    count = ask.count()
    rate = _rate(ask, "filestore", region, tier)
    source, published = _source(ask, "filestore")
    return priced(
        ask,
        [
            line(
                f"Capacity ({capacity:g} GB {tier})",
                capacity * count,
                "GB-month",
                rate,
                assumed=ask.was_assumed("tier", "capacity_gb", "count"),
            )
        ],
        sizing={"region": region, "tier": tier, "capacity_gb": capacity, "count": count},
        rate=f"Filestore {tier}, {_dollars(rate)} per GB-month",
        source=source,
        published=published,
    )


def price_dataflow(ask: Ask) -> Price:
    """Dataflow: workers' vCPU, memory and disk hours, batch or streaming."""
    region = ask.region()
    mode = ask.take("mode", "batch", choices=("batch", "streaming"))
    streaming = mode == "streaming"
    workers = ask.count("workers")
    vcpus = ask.amount("vcpus", 2 if streaming else 1, low=1)
    memory = ask.amount("memory_gb", 7.5 if streaming else 3.75, low=1)
    disk_gb = ask.amount("disk_gb", 400 if streaming else 250)
    hours = ask.hours()
    run = ask.was_assumed("workers", "hours")
    source, published = _source(ask, "dataflow")
    return priced(
        ask,
        [
            line(
                f"vCPU ({workers} x {vcpus:g})",
                workers * vcpus * hours,
                "vCPU-hours",
                _rate(ask, "dataflow", region, f"{mode}-vcpu"),
                kind="usage",
                assumed=run or ask.was_assumed("vcpus"),
            ),
            line(
                f"Memory ({workers} x {memory:g} GiB)",
                workers * memory * hours,
                "GiB-hours",
                _rate(ask, "dataflow", region, f"{mode}-memory"),
                kind="usage",
                assumed=run or ask.was_assumed("memory_gb"),
            ),
            line(
                f"Worker disk ({workers} x {disk_gb:g} GB)",
                workers * disk_gb * hours,
                "GB-hours",
                _rate(ask, "dataflow", region, "pd"),
                kind="usage",
                assumed=run or ask.was_assumed("disk_gb"),
            ),
        ],
        sizing={
            "region": region,
            "mode": mode,
            "workers": workers,
            "vcpus": vcpus,
            "memory_gb": memory,
            "disk_gb": disk_gb,
            "hours": hours,
        },
        rate=f"Dataflow {mode} workers",
        source=source,
        published=published,
    )


def price_dataproc(ask: Ask) -> Price:
    """Dataproc: the master and workers as Compute Engine VMs, plus the
    Dataproc fee on every vCPU they hold."""
    region = ask.region()
    master = _machine(ask, "n2-standard-4", prefix="master_")
    worker = _machine(ask, "n2-standard-4", prefix="worker_")
    workers = ask.count("workers", 2)
    hours = ask.hours()
    lines, notes = _vm_lines(
        ask,
        region,
        master,
        count=1,
        hours=hours,
        label=f"Master, {master.name}",
        assumed=ask.was_assumed("master_machine_type", "hours"),
    )
    more, words = _vm_lines(
        ask,
        region,
        worker,
        count=workers,
        hours=hours,
        label=f"Workers, {worker.name}",
        assumed=ask.was_assumed("worker_machine_type", "workers", "hours"),
    )
    vcpus = master.vcpus + workers * worker.vcpus
    fee = _rate(ask, "dataproc", region, "vcpu")
    lines += more
    lines.append(line(f"Dataproc fee ({vcpus:g} vCPU)", hours, "hours", vcpus * fee))
    source, published = _source(ask, "dataproc")
    return priced(
        ask,
        lines,
        sizing={
            "region": region,
            "master_machine_type": master.name,
            "worker_machine_type": worker.name,
            "workers": workers,
            "hours": hours,
        },
        rate=f"Dataproc, {_dollars(fee)} per vCPU-hour on Compute Engine: "
        + "; ".join(notes + words),
        source=source,
        published=published,
    )


def price_composer(ask: Ask) -> Price:
    """Cloud Composer: the environment fee by size, its data compute units, and storage."""
    region = ask.region()
    size = ask.take("environment_size", "small", choices=("small", "medium", "large"))
    dcus = ask.amount("dcus", 3)
    storage_gb = ask.amount("storage_gb", 10)
    hours = ask.hours()
    fee = _rate(ask, "composer", region, f"env-{size}")
    dcu = _rate(ask, "composer", region, "dcu")
    source, published = _source(ask, "composer")
    return priced(
        ask,
        [
            line(
                f"Environment fee ({size})",
                hours,
                "hours",
                fee,
                assumed=ask.was_assumed("environment_size", "hours"),
            ),
            line(
                f"Data compute units ({dcus:g})",
                hours,
                "hours",
                dcus * dcu,
                assumed=ask.was_assumed("dcus", "hours"),
            ),
            line(
                f"Storage ({storage_gb:g} GB)",
                storage_gb,
                "GB-month",
                _rate(ask, "composer", region, "storage"),
                kind="usage",
                assumed=ask.was_assumed("storage_gb"),
            ),
        ],
        sizing={
            "region": region,
            "environment_size": size,
            "dcus": dcus,
            "storage_gb": storage_gb,
            "hours": hours,
        },
        rate=f"Cloud Composer {size} environment, {_dollars(dcu)} per DCU-hour",
        source=source,
        published=published,
    )


# -- networking ---------------------------------------------------------------


def price_load_balancing(ask: Ask) -> Price:
    """Cloud Load Balancing: forwarding rules by the hour (the first five
    under one charge) and the data processed."""
    region = ask.region()
    rules = ask.count("rules")
    data_gb = ask.amount("data_gb", 100)
    hours = ask.hours()
    lines = [
        line(
            f"Forwarding rules, first {min(rules, 5)}",
            hours,
            "hours",
            _rate(ask, "load_balancing", region, "rule-minimum"),
            assumed=ask.was_assumed("rules", "hours"),
        )
    ]
    if rules > 5:
        lines.append(
            line(
                f"Forwarding rules, {rules - 5} more",
                (rules - 5) * hours,
                "hours",
                _rate(ask, "load_balancing", region, "rule-additional"),
            )
        )
    lines.append(
        line(
            "Data processed",
            data_gb,
            "GB",
            _rate(ask, "load_balancing", region, "data"),
            kind="usage",
            assumed=ask.was_assumed("data_gb"),
        )
    )
    source, published = _source(ask, "load_balancing")
    return priced(
        ask,
        lines,
        sizing={"region": region, "rules": rules, "data_gb": data_gb, "hours": hours},
        rate="Cloud Load Balancing, forwarding rules and data processed",
        source=source,
        published=published,
    )


def price_cdn(ask: Ask) -> Price:
    """Cloud CDN: cache egress to where viewers are, and cache lookups."""
    ask.taken.add("region")
    destination = ask.take("destination", "north-america", choices=_choices(ask, "cdn", "global"))
    egress = ask.amount("egress_gb", 100)
    millions = ask.amount("requests_millions", 1)
    source, published = _source(ask, "cdn")
    return priced(
        ask,
        [
            line(
                f"Cache egress to {destination}",
                egress,
                "GB",
                _rate(ask, "cdn", "global", destination, "egress"),
                kind="usage",
                assumed=ask.was_assumed("egress_gb", "destination"),
            ),
            line(
                "Cache lookups",
                millions,
                "1M requests",
                _rate(ask, "cdn", "global", "all", "lookups") * 1e6,
                kind="usage",
                assumed=ask.was_assumed("requests_millions"),
            ),
        ],
        sizing={"destination": destination, "egress_gb": egress, "requests_millions": millions},
        rate=f"Cloud CDN, cache egress to {destination}",
        source=source,
        published=published,
    )


def price_nat(ask: Ask) -> Price:
    """Cloud NAT: the gateway by the hour for each VM it serves (to 32), and data processed."""
    region = ask.region()
    vms = ask.count("vms")
    data_gb = ask.amount("data_gb", 100)
    hours = ask.hours()
    billed = min(vms, 32)
    source, published = _source(ask, "nat")
    return priced(
        ask,
        [
            line(
                f"Gateway ({billed} VM{'s' if billed > 1 else ''})",
                hours,
                "hours",
                billed * _rate(ask, "nat", region, "gateway"),
                assumed=ask.was_assumed("vms", "hours"),
            ),
            line(
                "Data processed",
                data_gb,
                "GB",
                _rate(ask, "nat", region, "data"),
                kind="usage",
                assumed=ask.was_assumed("data_gb"),
            ),
        ],
        sizing={"region": region, "vms": vms, "data_gb": data_gb, "hours": hours},
        rate="Cloud NAT, per VM-hour (32 VMs at most) and per GB processed",
        source=source,
        published=published,
    )


def price_vpn(ask: Ask) -> Price:
    """Cloud VPN: tunnels by the hour (HA VPN has two)."""
    region = ask.region()
    tunnels = ask.count("tunnels", 2)
    hours = ask.hours()
    rate = _rate(ask, "vpn", region, "tunnel")
    source, published = _source(ask, "vpn")
    return priced(
        ask,
        [
            line(
                f"Tunnels ({tunnels} x {hours:g} h)",
                tunnels * hours,
                "hours",
                rate,
                assumed=ask.was_assumed("tunnels", "hours"),
            )
        ],
        sizing={"region": region, "tunnels": tunnels, "hours": hours},
        rate=f"Cloud VPN, {_dollars(rate)} per tunnel-hour, before data out",
        source=source,
        published=published,
    )


def price_interconnect(ask: Ask) -> Price:
    """Cloud Interconnect: Dedicated connections or Partner attachments by capacity."""
    region = ask.region()
    kind = "partner" if ask.service_id == "partner-interconnect" else "dedicated"
    capacity = ask.take(
        "capacity",
        "1g" if kind == "partner" else "10g",
        choices=_choices(ask, "interconnect", region, kind),
    )
    connections = ask.count("connections")
    hours = ask.hours()
    lines = [
        line(
            f"{kind.title()} {capacity} ({connections} x {hours:g} h)",
            connections * hours,
            "hours",
            _rate(ask, "interconnect", region, kind, capacity),
            assumed=ask.was_assumed("capacity", "connections", "hours"),
        )
    ]
    sizing: dict[str, Any] = {
        "region": region,
        "capacity": capacity,
        "connections": connections,
        "hours": hours,
    }
    if kind == "dedicated":
        attachments = ask.count("attachments")
        lines.append(
            line(
                f"VLAN attachments ({attachments})",
                attachments * hours,
                "hours",
                _rate(ask, "interconnect", region, kind, "vlan"),
                assumed=ask.was_assumed("attachments", "hours"),
            )
        )
        sizing["attachments"] = attachments
    source, published = _source(ask, "interconnect")
    return priced(
        ask,
        lines,
        sizing=sizing,
        rate=f"Cloud Interconnect {kind}, before data out",
        source=source,
        published=published,
    )


def price_armor(ask: Ask) -> Price:
    """Cloud Armor Standard: policies and rules by the month, and requests."""
    ask.taken.add("region")
    policies = ask.count("policies")
    rules = ask.amount("rules", 5)
    millions = ask.amount("requests_millions", 1)
    source, published = _source(ask, "armor")
    return priced(
        ask,
        [
            line(
                "Policies",
                policies,
                "months",
                _rate(ask, "armor", "global", "policy"),
                assumed=ask.was_assumed("policies"),
            ),
            line(
                "Rules",
                rules,
                "months",
                _rate(ask, "armor", "global", "rule"),
                assumed=ask.was_assumed("rules"),
            ),
            line(
                "Requests",
                millions,
                "1M requests",
                _rate(ask, "armor", "global", "requests") * 1e6,
                kind="usage",
                assumed=ask.was_assumed("requests_millions"),
            ),
        ],
        sizing={"policies": policies, "rules": rules, "requests_millions": millions},
        rate="Cloud Armor Standard",
        source=source,
        published=published,
    )


# -- metered services ---------------------------------------------------------


class Meter(BaseModel):
    """One thing a metered service bills: the sizing key that says how much."""

    label: str
    key: str
    default: float
    #: The table's item, and how many of the table's units one of the line's is.
    item: str
    unit: str
    per: float = 1.0
    kind: str = "usage"


def _metered(name: str, words: str, *meters: Meter, regional: bool = True) -> Pricer:
    """A pricer for a service billed by what it serves, each meter a line."""

    def price(ask: Ask) -> Price:
        if regional:
            region = ask.region()
        else:
            ask.taken.add("region")
            region = "global"
        lines: list[PriceLine] = []
        sizing: dict[str, Any] = {"region": region} if regional else {}
        for meter in meters:
            quantity = ask.amount(meter.key, meter.default)
            sizing[meter.key] = quantity
            lines.append(
                line(
                    meter.label,
                    quantity,
                    meter.unit,
                    _rate(ask, name, region, meter.item) * meter.per,
                    kind=meter.kind,
                    assumed=ask.was_assumed(meter.key),
                )
            )
        source, published = _source(ask, name)
        return priced(ask, lines, sizing=sizing, rate=words, source=source, published=published)

    price.__doc__ = words
    return price


def _m(
    label: str, key: str, default: float, item: str, unit: str, per: float = 1, kind: str = "usage"
) -> Meter:
    return Meter(label=label, key=key, default=default, item=item, unit=unit, per=per, kind=kind)


M = 1e6

price_bigquery = _metered(
    "bigquery",
    "BigQuery on-demand analysis and logical storage",
    _m("Data scanned", "scanned_tib", 1, "analysis", "TiB"),
    _m("Active storage", "storage_gb", 100, "active-storage", "GB-month"),
)
price_pubsub = _metered(
    "pubsub",
    "Pub/Sub message throughput",
    _m("Throughput", "throughput_tib", 0.1, "throughput", "TiB"),
    regional=False,
)
price_firestore = _metered(
    "firestore",
    "Firestore operations and stored data",
    _m("Document reads", "reads_millions", 1, "reads", "1M reads", M),
    _m("Document writes", "writes_millions", 1, "writes", "1M writes", M),
    _m("Stored data", "storage_gb", 10, "storage", "GB-month"),
)
price_dns = _metered(
    "dns",
    "Cloud DNS managed zones and queries",
    _m("Managed zones", "zones", 1, "zone", "zone-months", kind="fixed"),
    _m("Queries", "queries_millions", 1, "queries", "1M queries", M),
    regional=False,
)
price_secrets = _metered(
    "secrets",
    "Secret Manager active versions and access operations",
    _m("Active secret versions", "versions", 1, "versions", "version-months", kind="fixed"),
    _m("Access operations", "accesses", 10_000, "access", "operations"),
    regional=False,
)
price_logging = _metered(
    "logging",
    "Cloud Logging ingestion, before the monthly free allotment",
    _m("Logs ingested", "ingestion_gb", 10, "ingestion", "GB"),
    regional=False,
)
price_monitoring = _metered(
    "monitoring",
    "Cloud Monitoring metric ingestion, before the monthly free allotment",
    _m("Metrics ingested", "ingestion_mib", 100, "ingestion", "MiB"),
    regional=False,
)
price_artifact_registry = _metered(
    "artifact_registry",
    "Artifact Registry storage",
    _m("Stored images and packages", "storage_gb", 10, "storage", "GB-month"),
)
price_scheduler = _metered(
    "scheduler",
    "Cloud Scheduler jobs",
    _m("Jobs", "jobs", 1, "job", "job-months", kind="fixed"),
    regional=False,
)
price_tasks = _metered(
    "tasks",
    "Cloud Tasks operations",
    _m("Operations", "operations_millions", 1, "operations", "1M operations", M),
)
price_kms = _metered(
    "kms",
    "Cloud KMS software keys and operations",
    _m("Active key versions", "key_versions", 1, "key-version", "version-months", kind="fixed"),
    _m("Cryptographic operations", "operations", 10_000, "operations", "operations"),
)
price_cloud_build = _metered(
    "cloud_build",
    "Cloud Build build minutes on the default machine",
    _m("Build minutes", "build_minutes", 120, "build-minute", "minutes"),
)
price_workflows = _metered(
    "workflows",
    "Workflows steps",
    _m("Internal steps", "steps_thousands", 10, "internal-step", "1K steps", 1000),
)
price_eventarc = _metered(
    "eventarc",
    "Eventarc events",
    _m("Events", "events_millions", 1, "events", "1M events", M),
    regional=False,
)
price_api_gateway = _metered(
    "api_gateway",
    "API Gateway calls",
    _m("Calls", "calls_millions", 1, "calls", "1M calls", M),
    regional=False,
)


# -- coverage -----------------------------------------------------------------


def _same(pricer: Pricer, *ids: str) -> dict[str, Pricer]:
    return dict.fromkeys(ids, pricer)


PRICERS: dict[str, Pricer] = {
    **_same(price_compute, "compute-engine", "compute-engine-legacy"),
    "cloud-gpu": price_gpu,
    **_same(price_disk, "persistent-disk", "hyperdisk", "local-ssd"),
    "cloud-external-ip-addresses": price_ip,
    **_same(price_sql, "cloud-sql", "cloud-sql-legacy"),
    "alloydb": price_alloydb,
    "memorystore": price_memorystore,
    **_same(price_spanner, "cloud-spanner", "cloud-spanner-legacy"),
    "bigtable": price_bigtable,
    **_same(price_firestore, "firestore", "datastore"),
    **_same(price_gke, "gke", "google-kubernetes-engine"),
    **_same(price_run, "cloud-run", "cloud-run-legacy"),
    "cloud-functions": price_functions,
    "app-engine": price_app_engine,
    **_same(price_storage, "cloud-storage", "cloud-storage-legacy"),
    "filestore": price_filestore,
    **_same(price_bigquery, "bigquery", "bigquery-legacy"),
    "pubsub": price_pubsub,
    "dataflow": price_dataflow,
    "dataproc": price_dataproc,
    "cloud-composer": price_composer,
    "cloud-load-balancing": price_load_balancing,
    "cloud-cdn": price_cdn,
    "cloud-nat": price_nat,
    "cloud-vpn": price_vpn,
    **_same(price_interconnect, "cloud-interconnect", "partner-interconnect"),
    "cloud-armor": price_armor,
    "cloud-dns": price_dns,
    "secret-manager": price_secrets,
    "cloud-logging": price_logging,
    "cloud-monitoring": price_monitoring,
    **_same(price_artifact_registry, "artifact-registry", "container-registry"),
    "cloud-scheduler": price_scheduler,
    "cloud-tasks": price_tasks,
    "key-management-service": price_kms,
    "cloud-build": price_cloud_build,
    "workflows": price_workflows,
    "eventarc": price_eventarc,
    "cloud-api-gateway": price_api_gateway,
}

_CONSOLE = "a console page or section, not a billed resource"
FREE: dict[str, str] = {
    "virtual-private-cloud": "VPC networks and subnets are free; traffic is billed where it leaves",
    "cloud-network": "VPC networks are free; traffic is billed where it leaves",
    "cloud-firewall-rules": "VPC firewall rules are free",
    "cloud-routes": "routes are free",
    "cloud-router": "Cloud Router is free; the VPN or Interconnect it serves is billed",
    "identity-and-access-management": "IAM is free",
    "permissions": "IAM permissions are free",
    "workload-identity-pool": "Workload Identity Federation is free",
    "access-context-manager": "Access Context Manager is free",
    "project": "projects are free",
    "billing": "Cloud Billing is free",
    "quotas": "quotas are free",
    "batch": "Batch has no charge of its own; the VMs it runs are billed as Compute Engine",
    "cloud-shell": "Cloud Shell is free",
    "cloud-code": "Cloud Code is a free IDE plugin",
    "tools-for-powershell": "Cloud Tools for PowerShell are free",
    "cloud-deployment-manager": "Deployment Manager is free; the resources it makes are billed",
    "container-optimized-os": "Container-Optimized OS is a free image",
    "cloud-audit-logs": "Admin Activity audit logs are free; Data Access logs bill as Cloud Logging",
    "cloud-asset-inventory": "Cloud Asset Inventory is free",
    "asset-inventory": "Cloud Asset Inventory is free",
    "policy-analyzer": "Policy Analyzer is free within its daily quota",
    "network-topology": "Network Topology is free",
    "runtime-config": "Runtime Configurator is free",
    "os-inventory-management": "VM Manager's inventory is free",
    "free-trial": "the free trial costs nothing",
    "binary-authorization": "Binary Authorization is free for GKE and Cloud Run",
    "certificate-manager": "Certificate Manager's first certificates are free; it bills per certificate past them",
    "data-studio": "Looker Studio is free (Pro is per user)",
    "cloud-healthcare-marketplace": _CONSOLE,
    "financial-services-marketplace": _CONSOLE,
    "google-cloud-marketplace": "Marketplace itself is free; each product bills on its own terms",
    "administration": _CONSOLE,
    "home": _CONSOLE,
    "my-cloud": _CONSOLE,
    "launcher": _CONSOLE,
    "catalog": _CONSOLE,
    "onboarding": _CONSOLE,
    "release-notes": _CONSOLE,
    "user-preferences": _CONSOLE,
    "early-access-center": _CONSOLE,
    "partner-portal": _CONSOLE,
    "producer-portal": _CONSOLE,
    "developer-portal": _CONSOLE,
    "cloud-apis": "the API surface itself is free; each API bills on its own",
    "api": "the API surface itself is free; each API bills on its own",
    "premium-network-tier": "a network tier is a choice of egress rate, priced on the traffic",
    "standard-network-tier": "a network tier is a choice of egress rate, priced on the traffic",
    "network-tiers": "a network tier is a choice of egress rate, priced on the traffic",
}

_PER_USE = "billed per request, page, minute or character used; no size to price from"
_CONTRACT = "sold by contract or subscription, not a published list price"
_AI = "billed per model token, prediction, node-hour or training hour; no fixed size to price"
UNPRICED: dict[str, str] = {
    **dict.fromkeys(
        (
            "vertex-ai",
            "vertexai",
            "ai-platform",
            "ai-platform-unified",
            "automl",
            "automl-natural-language",
            "automl-tables",
            "automl-translation",
            "automl-video-intelligence",
            "automl-vision",
            "advanced-agent-modeling",
            "tensorflow-enterprise",
            "cloud-inference-api",
            "data-labeling",
            "recommendations-ai",
            "retail-api",
            "visual-inspection",
            "ai-hub",
        ),
        _AI,
    ),
    **dict.fromkeys(
        (
            "agent-assist",
            "contact-center-ai",
            "dialogflow",
            "dialogflow-cx",
            "dialogflow-insights",
            "document-ai",
            "healthcare-nlp-api",
            "media-translation-api",
            "speech-to-text",
            "text-to-speech",
            "cloud-natural-language-api",
            "cloud-translation-api",
            "cloud-vision-api",
            "video-intelligence-api",
            "cloud-jobs-api",
            "cloud-optimization-ai",
            "cloud-optimization-ai-fleet-routing-api",
            "data-loss-prevention-api",
            "web-risk",
            "phishing-protection",
            "google-maps-platform",
            "fleet-engine",
            "cloud-test-lab",
            "cloud-healthcare-api",
            "genomics",
            "transfer",
            "data-transfer",
            "database-migration-service",
            "datastream",
            "cloud-data-fusion",
            "dataprep",
            "dataplex",
            "data-catalog",
            "dataproc-metastore",
            "connectors",
            "identity-platform",
            "identity-aware-proxy",
            "cloud-ids",
            "cloud-security-scanner",
            "web-security-scanner",
            "certificate-authority-service",
            "cloud-hsm",
            "cloud-ekm",
            "private-service-connect",
            "service-discovery",
            "traffic-director",
            "connectivity-test",
            "network-connectivity-center",
            "network-intelligence-center",
            "cloud-domains",
            "cloud-deploy",
            "os-configuration-management",
            "os-patch-management",
            "configuration-management",
            "gce-systems-management",
            "trace",
            "profiler",
            "error-reporting",
            "debugger",
            "analytics-hub",
            "iot-core",
            "cloud-media-edge",
        ),
        _PER_USE,
    ),
    **dict.fromkeys(
        (
            "looker",
            "looker-legacy",
            "apigee",
            "apigee-api-platform",
            "apigee-sense",
            "api-analytics",
            "api-monetization",
            "mandiant",
            "security-operations",
            "threat-intelligence",
            "security-command-center",
            "security-command-center-legacy",
            "assured-workloads",
            "support",
            "anthos",
            "anthos-legacy",
            "anthos-config-management",
            "anthos-service-mesh",
            "gke-on-prem",
            "distributed-cloud",
            "cloud-run-for-anthos",
            "kuberun",
            "migrate-for-anthos",
            "bare-metal-solutions",
            "vmware-engine",
            "transfer-appliance",
            "managed-service-for-microsoft-active-directory",
            "beyondcorp",
            "key-access-justifications",
            "advanced-solutions-lab",
            "cloud-for-marketing",
            "real-world-insights",
            "game-servers",
            "quantum-engine",
            "iot-edge",
        ),
        _CONTRACT,
    ),
    "cloud-tpu": "TPUs are billed per chip-hour by version and topology; no table holds them yet",
    "ai-hypercomputer": "a system of TPUs, GPUs and storage; price its parts",
    "migrate-for-compute-engine": "free to use; the VMs it moves are billed as Compute Engine",
    "cloud-endpoints": "billed per million calls past a free allotment; price the backend it fronts",
    "stackdriver": "the operations suite; price its Cloud Logging and Cloud Monitoring cards",
    "cloud-ops": "the operations suite; price its Cloud Logging and Cloud Monitoring cards",
    "performance-dashboard": "part of Network Intelligence Center, not billed on its own",
    "data-layers": "an illustration of data layers, not a single service",
    "data-qna": "a retired preview with no list price",
    "datalab": "retired; its notebooks ran on Compute Engine VMs",
    "datapol": "an illustration, not a billed service",
    "datashare": "sold through Marketplace by contract",
    "stream-suite": "an illustration of streaming services, not a single service",
    "security": "a category of services; price each security service",
    "network-security": "a category of services; price each security service",
    "security-health-advisor": "part of Security Command Center, sold by subscription",
    "security-key-enforcement": "Titan keys are hardware bought once, not a cloud rate",
    "risk-manager": "sold by contract with insurers",
    "private-connectivity": "a category of connectivity options; price its VPN or Interconnect",
    "cloud-generic": "a generic cloud, not a single service",
}


COVERAGE = Coverage(
    cloud="gcp",
    default_region="us-central1",
    region_of=region_of,
    pricers=PRICERS,
    free=FREE,
    unpriced=UNPRICED,
)
