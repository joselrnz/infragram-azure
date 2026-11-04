"""The Google Cloud price table, from the Cloud Billing Catalog API.

The Catalog API (``cloudbilling.googleapis.com/v1``) lists every Google
Cloud service and, for each, its SKUs: a description ("E2 Instance Core
running in Americas"), a category (resource family, group, usage type), the
regions it is sold in (``serviceRegions``) and its price as tiered rates in
units and nanos of a usage unit (``h``, ``GiBy.mo``, ``count``). It needs an
API key, read from ``INFRAGRAM_GCP_PRICING_KEY``: create one in any Google
Cloud project with the Cloud Billing API enabled. The key goes on each
request only; the build cache is keyed by the URL without it.

The builder keeps on-demand SKUs in USD, reduces each to the one rate a
pricer reads (the first tier with a price, so before any free tier), and
files it under the region it is sold in, the most specific SKU winning
where two cover the same region. Machine types (vCPUs and memory per
machine type) are not in the Catalog API: they are read from the Compute
Engine machine-family pages, which are public and need no key.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import sys
from collections.abc import Callable, Iterable
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict

from ...iso3d.cache import cache_root
from .. import PricingError
from ..fetch import fetch_url
from . import download, write_table

__all__ = ["CATALOG", "KEY_VARIABLE", "MACHINE_PAGES", "build", "machine_types"]

CATALOG = "https://cloudbilling.googleapis.com/v1"
KEY_VARIABLE = "INFRAGRAM_GCP_PRICING_KEY"
SOURCE = "Cloud Billing Catalog API (cloudbilling.googleapis.com)"
#: The Compute Engine pages whose tables give each machine type's shape.
MACHINE_PAGES = tuple(
    f"https://cloud.google.com/compute/docs/{page}"
    for page in (
        "general-purpose-machines",
        "compute-optimized-machines",
        "memory-optimized-machines",
        "accelerator-optimized-machines",
        "storage-optimized-machines",
    )
)
MACHINE_SOURCE = "Compute Engine machine family pages (cloud.google.com/compute/docs)"


# -- the Catalog API ----------------------------------------------------------


def _key() -> str:
    key = os.environ.get(KEY_VARIABLE, "").strip()
    if not key:
        raise PricingError(
            f"the Google Cloud price table is read from the Cloud Billing Catalog API, which "
            f"needs an API key: create one in a Google Cloud project with the Cloud Billing "
            f"API enabled (APIs & Services > Credentials > Create credentials > API key), "
            f"then set {KEY_VARIABLE} and run scripts/build/price-tables.py gcp again"
        )
    return key


def _get(path: str, params: dict[str, str], key: str, *, fresh: bool) -> Any:
    """One Catalog API page, kept in the build cache under its URL without the key."""
    url = f"{CATALOG}/{path}?{urlencode(sorted(params.items()))}"
    folder = cache_root() / "price-build"
    folder.mkdir(parents=True, exist_ok=True)
    cached = folder / (hashlib.sha256(url.encode("utf-8")).hexdigest()[:40] + ".json")
    if cached.is_file() and not fresh:
        return json.loads(cached.read_bytes())
    try:
        body = fetch_url(f"{url}&{urlencode({'key': key})}")
        data = json.loads(body)
    except PricingError as error:
        # the error names the URL; never with the key in it
        raise PricingError(str(error).replace(key, "<key>")) from None
    except ValueError as error:
        raise PricingError(f"{url} did not answer with JSON ({error})") from None
    partial = cached.with_name(f"{cached.name}.{os.getpid()}.part")
    partial.write_bytes(body)
    os.replace(partial, cached)
    return data


def _pages(path: str, field: str, params: dict[str, str], key: str, *, fresh: bool) -> list[Any]:
    """Every item of a paged list, following ``nextPageToken``."""
    items: list[Any] = []
    token = ""
    while True:
        page = _get(path, {**params, **({"pageToken": token} if token else {})}, key, fresh=fresh)
        items.extend(page.get(field, []))
        token = page.get("nextPageToken", "")
        if not token:
            return items


def _price(sku: dict[str, Any]) -> tuple[float, str, str] | None:
    """(rate, usage unit, effective day) of the SKU's first tier with a price."""
    infos = sku.get("pricingInfo") or []
    if not infos:
        return None
    info = infos[-1]
    expression = info.get("pricingExpression", {})
    for tier in expression.get("tieredRates", []):
        money = tier.get("unitPrice", {})
        if money.get("currencyCode", "USD") != "USD":
            return None
        rate = int(money.get("units") or 0) + int(money.get("nanos") or 0) / 1e9
        if rate > 0:
            day = str(info.get("effectiveTime", ""))[:10]
            return rate, str(expression.get("usageUnit", "")), day
    return None


# -- units --------------------------------------------------------------------

_DATA = {"By": 1, "KiBy": 2**10, "MiBy": 2**20, "GiBy": 2**30, "TiBy": 2**40, "PiBy": 2**50}
_TIME = {"ms": 0.001, "s": 1, "min": 60, "h": 3600, "d": 86400, "mo": 730 * 3600}


def _measure(unit: str) -> tuple[str, float] | None:
    """A usage unit as (dimension, size): ``GiBy.mo`` -> (data.time, 2**30 x month)."""
    if unit in ("count", "1") or unit.startswith("{"):
        return "count", 1.0
    data, time, size = "", "", 1.0
    for part in unit.split("."):
        if part in _DATA and not data:
            data, size = "data", size * _DATA[part]
        elif part in _TIME and not time:
            time, size = "time", size * _TIME[part]
        else:
            return None
    return f"{data}.{time}", size


def convert(rate: float, unit: str, want: str) -> float | None:
    """*rate* per *unit* as a rate per *want*; None when they measure different things."""
    have, wanted = _measure(unit), _measure(want)
    if have is None or wanted is None or have[0] != wanted[0]:
        return None
    return rate * wanted[1] / have[1]


# -- what the table keeps -----------------------------------------------------

#: Words in a SKU description that mark a rate a list price is not.
_NOT_LIST = re.compile(
    r"\b(spot|preemptible|commit\w*|reserv\w*|sole.?tenan\w*|dws|flex.?start|calendar|"
    r"confidential|premium|extended|upgrade|free)\b",
    re.IGNORECASE,
)

Key = tuple[str | None, tuple[str, ...]]


class Rule(BaseModel):
    """SKUs the table keeps: which services, which descriptions, and where they go."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    #: The table service the rate is written to.
    service: str
    #: The Catalog API services (display names) whose SKUs it reads.
    sources: tuple[str, ...]
    pattern: re.Pattern[str]
    #: The match -> (location, or None for the SKU's regions; the keys after it).
    key: Callable[[re.Match[str]], Key | None]
    #: The unit the table holds the rate in.
    unit: str
    #: Filed under a location: the SKU's regions, else ``global``.
    regional: bool = True
    exclude: re.Pattern[str] | None = None
    #: The unit for a key's last part where it differs (a core per hour, RAM per GiB-hour).
    units: dict[str, str] = {}


def _rule(
    service: str,
    sources: str | tuple[str, ...],
    pattern: str,
    key: Callable[[re.Match[str]], Key | None] | tuple[str, ...],
    unit: str,
    *,
    regional: bool = True,
    exclude: str = "",
    units: dict[str, str] | None = None,
) -> Rule:
    chosen: Callable[[re.Match[str]], Key | None]
    if isinstance(key, tuple):
        path = key
        chosen = lambda _match: (None, path)  # noqa: E731 - typed by the annotation above
    else:
        chosen = key
    return Rule(
        service=service,
        sources=(sources,) if isinstance(sources, str) else sources,
        pattern=re.compile(pattern, re.IGNORECASE),
        key=chosen,
        unit=unit,
        regional=regional,
        exclude=re.compile(exclude, re.IGNORECASE) if exclude else None,
        units=units or {},
    )


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


_SERIES_WORDS = {"custom", "predefined", "instance", "amd", "arm", "intel"}
_SERIES_NAMES = {"compute optimized": "c2", "memory-optimized": "m1", "memory optimized": "m1"}


def _compute(match: re.Match[str]) -> Key | None:
    """``N2D AMD Custom Instance Core`` -> (n2d, custom-core)."""
    words = match.group("head").split()
    custom = any(word.lower() == "custom" for word in words)
    rest = [word for word in words if word.lower() not in _SERIES_WORDS]
    named = " ".join(rest).lower()
    if not rest:
        series = "n1" if custom else ""
    elif named in _SERIES_NAMES:
        series = _SERIES_NAMES[named]
    elif re.fullmatch(r"[A-Z]\d[A-Z]?", rest[0]):
        series = rest[0].lower()
    else:
        series = ""
    if not series:
        return None
    what = match.group("what").lower()
    return None, (series, f"custom-{what}" if custom else what)


def _gpu(match: re.Match[str]) -> Key:
    return None, (gpu_slug(match.group("model")),)


def gpu_slug(name: str) -> str:
    """A GPU's name as the table keys it: ``Tesla A100 80GB`` -> ``a100-80gb``."""
    words = [
        word
        for word in name.replace("NVIDIA", "").replace("Nvidia", "").split()
        if word.lower() not in {"tesla", "gpu", "gpus", "superchip", "superchips", "attached"}
    ]
    slug = _slug(" ".join(words))
    return "a100" if slug == "a100-40gb" else slug


def _sql(match: re.Match[str]) -> Key | None:
    engine = {"mysql": "mysql", "postgresql": "postgres", "sql server": "sqlserver"}[
        match.group("engine").lower()
    ]
    item = match.group("item").lower()
    edition = "enterprise-plus" if "enterprise plus" in match.string.lower() else "enterprise"
    found = next((name for words, name in _SQL_ITEMS if re.search(words, item)), None)
    if found is None:
        return None
    return None, (engine, edition, match.group("ha").lower(), found)


_SQL_ITEMS = (
    (r"\bvcpu\b|\bcpu\b", "core"),
    (r"\bram\b|memory", "ram"),
    (r"low cost storage|hdd", "storage-hdd"),
    (r"storage", "storage-ssd"),
    (r"micro", "db-f1-micro"),
    (r"small", "db-g1-small"),
)


def _storage(match: re.Match[str]) -> Key:
    text = match.string.lower()
    cls = match.group("cls").lower()
    if "multi-region" in text or "multi region" in text:
        place = re.search(r"\b(us|eu|asia)\b", text)
        return (place.group(1) if place else "multi-region"), (cls,)
    if "dual-region" in text or "dual region" in text:
        return "dual-region", (cls,)
    return None, (cls,)


def _storage_ops(match: re.Match[str]) -> Key:
    scope = _slug(match.group("scope") or "any")
    return None, (scope, (match.group("cls") or "standard").lower(), match.group("op").lower())


def _interconnect(match: re.Match[str]) -> Key:
    size = match.group("size").lower().replace("bps", "").replace(" ", "")
    return None, (match.group("kind").lower(), size)


GCE = ("Compute Engine",)
NET = ("Compute Engine", "Networking", "Network Services", "Cloud Armor", "Cloud CDN")

RULES: tuple[Rule, ...] = (
    _rule(
        "compute",
        GCE,
        r"^(?P<head>.+?)\s+(?P<what>Core|Ram)\s+running in\b",
        _compute,
        "h",
        units={"ram": "GiBy.h", "custom-ram": "GiBy.h"},
        exclude=r"gpu|local|licens",
    ),
    _rule("compute", GCE, r"^Micro Instance with burstable CPU", ("f1", "instance"), "h"),
    _rule("compute", GCE, r"^Small Instance with 1 VCPU", ("g1", "instance"), "h"),
    _rule(
        "gpu",
        GCE,
        r"^Nvidia (?P<model>.+?) GPU running in\b",
        _gpu,
        "h",
        exclude=r"workstation",
    ),
    _rule(
        "windows",
        GCE,
        r"^Licensing Fee for Windows Server .*\(CPU cost\)",
        ("core",),
        "h",
        regional=False,
    ),
    _rule(
        "windows",
        GCE,
        r"^Licensing Fee for Windows Server .*(f1-micro|g1-small|shared)",
        ("shared",),
        "h",
        regional=False,
    ),
    _rule("disk", GCE, r"^Storage PD Capacity", ("pd-standard",), "GiBy.mo"),
    _rule("disk", GCE, r"^Balanced PD Capacity", ("pd-balanced",), "GiBy.mo"),
    _rule("disk", GCE, r"^SSD backed PD Capacity", ("pd-ssd",), "GiBy.mo"),
    _rule("disk", GCE, r"^Extreme PD Capacity", ("pd-extreme",), "GiBy.mo"),
    _rule("disk", GCE, r"^Regional Storage PD Capacity", ("regional-pd-standard",), "GiBy.mo"),
    _rule("disk", GCE, r"^Regional Balanced PD Capacity", ("regional-pd-balanced",), "GiBy.mo"),
    _rule("disk", GCE, r"^Regional SSD backed PD Capacity", ("regional-pd-ssd",), "GiBy.mo"),
    _rule(
        "disk",
        GCE,
        r"^Hyperdisk (?P<kind>Balanced High Availability|Balanced|Throughput|Extreme|ML) "
        r"Capacity",
        lambda m: (
            None,
            ("hyperdisk-" + _slug(m.group("kind")).replace("high-availability", "ha"),),
        ),
        "GiBy.mo",
    ),
    _rule("disk", GCE, r"^SSD backed Local Storage", ("local-ssd",), "GiBy.mo"),
    _rule(
        "disk_performance",
        GCE,
        r"^Hyperdisk (?P<kind>Balanced|Extreme|Throughput|ML) (?:Provisioned )?"
        r"(?P<what>IOPS|Throughput)\b",
        lambda m: (None, ("hyperdisk-" + _slug(m.group("kind")), m.group("what").lower())),
        "mo",
        exclude=r"capacity",
    ),
    _rule("ip", NET, r"^External IP Charge on a Standard VM", ("in-use",), "h"),
    _rule("ip", NET, r"^Static Ip Charge", ("reserved",), "h"),
    _rule(
        "load_balancing",
        NET,
        r"Forwarding Rule Minimum",
        ("rule-minimum",),
        "h",
    ),
    _rule("load_balancing", NET, r"Forwarding Rule Additional", ("rule-additional",), "h"),
    _rule(
        "load_balancing",
        NET,
        r"Load Balanc\w* .*Data Processing|^Network Load Balancing: Data Processing",
        ("data",),
        "GiBy",
        exclude=r"nat|psc|private service",
    ),
    _rule(
        "cdn",
        NET,
        r"CDN.*(?:Egress|Data Transfer).* to (?P<dest>[A-Za-z ]+?)\s*$",
        lambda m: ("global", (_slug(m.group("dest")), "egress")),
        "GiBy",
        regional=False,
        exclude=r"fill|interconnect",
    ),
    _rule(
        "cdn",
        NET,
        r"CDN.*Cache Lookup",
        ("all", "lookups"),
        "count",
        regional=False,
    ),
    _rule("nat", NET, r"NAT Gateway: Uptime", ("gateway",), "h"),
    _rule("nat", NET, r"NAT Gateway: Data processing", ("data",), "GiBy"),
    _rule("vpn", NET, r"VPN Tunnel", ("tunnel",), "h"),
    _rule(
        "interconnect",
        NET,
        r"(?P<kind>Dedicated|Partner) Interconnect.*?(?P<size>\d+\s*[GM](?:bps)?)\b",
        _interconnect,
        "h",
        exclude=r"egress|data transfer",
    ),
    _rule(
        "interconnect",
        NET,
        r"Interconnect VLAN Attachment",
        ("dedicated", "vlan"),
        "h",
        exclude=r"partner|egress",
    ),
    _rule(
        "armor",
        NET,
        r"Cloud Armor.*\bPolic(?:y|ies)\b",
        ("policy",),
        "mo",
        regional=False,
        exclude=r"rule|request|enterprise|adaptive",
    ),
    _rule(
        "armor",
        NET,
        r"Cloud Armor.*\bRules?\b",
        ("rule",),
        "mo",
        regional=False,
        exclude=r"request|enterprise",
    ),
    _rule(
        "armor",
        NET,
        r"Cloud Armor.*\bRequests?\b",
        ("requests",),
        "count",
        regional=False,
        exclude=r"enterprise",
    ),
    _rule(
        "cloud_sql",
        "Cloud SQL",
        r"^Cloud SQL for (?P<engine>MySQL|PostgreSQL|SQL Server): (?P<ha>Zonal|Regional) - "
        r"(?P<item>.+?)(?: in [A-Z].*)?$",
        _sql,
        "h",
        units={"ram": "GiBy.h", "storage-ssd": "GiBy.mo", "storage-hdd": "GiBy.mo"},
        exclude=r"backup|network|ip address|read pool",
    ),
    _rule(
        "sql_license",
        "Cloud SQL",
        r"^Cloud SQL for SQL Server:.*?\b(?P<edition>Standard|Enterprise|Web|Express)\b.*licen",
        lambda m: (None, (m.group("edition").lower(),)),
        "h",
        regional=False,
    ),
    _rule(
        "gke",
        "Kubernetes Engine",
        r"Kubernetes Clusters?\b",
        ("cluster",),
        "h",
        exclude=r"enterprise|multi-cluster",
    ),
    _rule("gke", "Kubernetes Engine", r"Autopilot Pod mCPU Requests", ("autopilot-vcpu",), "h"),
    _rule(
        "gke",
        "Kubernetes Engine",
        r"Autopilot Pod Memory Requests",
        ("autopilot-memory",),
        "GiBy.h",
    ),
    _rule(
        "cloud_run",
        "Cloud Run",
        r"CPU Allocation Time|CPU \(Request-based",
        ("cpu",),
        "s",
        exclude=r"always|instance|idle|\bmin\b|jobs?\b|worker|gpu",
    ),
    _rule(
        "cloud_run",
        "Cloud Run",
        r"Memory Allocation Time|Memory \(Request-based",
        ("memory",),
        "GiBy.s",
        exclude=r"always|instance|idle|\bmin\b|jobs?\b|worker|gpu",
    ),
    _rule("cloud_run", "Cloud Run", r"^Requests\b|Request count", ("requests",), "count"),
    _rule("app_engine", "App Engine", r"^Frontend Instances", ("frontend",), "h"),
    _rule("app_engine", "App Engine", r"^Backend Instances", ("backend",), "h"),
    _rule("app_engine", "App Engine", r"^Flex Instance Core", ("flex-core",), "h"),
    _rule("app_engine", "App Engine", r"^Flex Instance RAM", ("flex-ram",), "GiBy.h"),
    _rule(
        "storage",
        "Cloud Storage",
        r"^(?P<cls>Standard|Nearline|Coldline|Archive) Storage\b",
        _storage,
        "GiBy.mo",
        exclude=r"early delet|retrieval|operation|replication|transfer|egress",
    ),
    _rule(
        "storage_ops",
        "Cloud Storage",
        r"^(?:(?P<scope>Multi-Region|Regional|Dual-Region) )?(?:(?P<cls>Standard|Nearline|"
        r"Coldline|Archive) (?:Storage )?)?Class (?P<op>A|B) Operations",
        _storage_ops,
        "count",
        regional=False,
    ),
    _rule(
        "storage_ops",
        "Cloud Storage",
        r"^(?P<cls>Nearline|Coldline|Archive) (?:Storage )?Data Retrieval",
        lambda m: (None, ("any", m.group("cls").lower(), "retrieval")),
        "GiBy",
        regional=False,
    ),
    _rule(
        "memorystore",
        ("Cloud Memorystore for Redis", "Memorystore for Redis"),
        r"Redis Capacity (?P<tier>Basic|Standard) (?P<band>M[1-5])\b",
        lambda m: (None, (m.group("tier").lower(), m.group("band").lower())),
        "GiBy.h",
    ),
    _rule(
        "pubsub",
        "Cloud Pub/Sub",
        r"Message Delivery Basic|Throughput",
        ("throughput",),
        "TiBy",
        regional=False,
        exclude=r"lite|storage",
    ),
    _rule(
        "pubsub",
        "Cloud Pub/Sub",
        r"message storage|retained.*storage|topic.*storage",
        ("storage",),
        "GiBy.mo",
        regional=False,
        exclude=r"lite|snapshot",
    ),
    _rule(
        "dataflow",
        ("Dataflow", "Cloud Dataflow"),
        r"^(?P<what>vCPU|RAM) Time (?P<mode>Batch|Streaming)",
        lambda m: (
            None,
            (
                f"{m.group('mode').lower()}-{'vcpu' if m.group('what').lower() == 'vcpu' else 'memory'}",
            ),
        ),
        "h",
        units={"batch-memory": "GiBy.h", "streaming-memory": "GiBy.h"},
        exclude=r"flex|gpu|prime",
    ),
    _rule(
        "dataflow",
        ("Dataflow", "Cloud Dataflow"),
        r"^Local Disk Time PD (?P<kind>Standard|SSD)",
        lambda m: (None, ("pd" if m.group("kind") == "Standard" else "pd-ssd",)),
        "GiBy.h",
    ),
    _rule("bigquery", "BigQuery", r"^Analysis\b", ("analysis",), "TiBy", exclude=r"edition|slot"),
    _rule(
        "bigquery",
        "BigQuery",
        r"^Active (?:Logical )?Storage",
        ("active-storage",),
        "GiBy.mo",
    ),
    _rule(
        "bigquery",
        "BigQuery",
        r"^Long[ -]Term (?:Logical )?Storage",
        ("long-term-storage",),
        "GiBy.mo",
    ),
    _rule(
        "bigtable",
        ("Cloud Bigtable", "Bigtable"),
        r"\bNodes?\b",
        ("node",),
        "h",
        exclude=r"replication|backup|data boost",
    ),
    _rule("bigtable", ("Cloud Bigtable", "Bigtable"), r"SSD Storage", ("ssd",), "GiBy.mo"),
    _rule("bigtable", ("Cloud Bigtable", "Bigtable"), r"HDD Storage", ("hdd",), "GiBy.mo"),
    _rule(
        "spanner",
        ("Cloud Spanner", "Spanner"),
        r"\bNodes?\b",
        ("node",),
        "h",
        exclude=r"backup|replication|data boost|enterprise|edition",
    ),
    _rule(
        "spanner",
        ("Cloud Spanner", "Spanner"),
        r"Processing Units?\b",
        ("processing-unit",),
        "h",
        exclude=r"backup|replication|data boost|enterprise",
    ),
    _rule(
        "spanner",
        ("Cloud Spanner", "Spanner"),
        r"\bStorage\b",
        ("storage",),
        "GiBy.mo",
        exclude=r"backup|hdd",
    ),
    _rule(
        "firestore",
        ("Cloud Firestore", "Firestore"),
        r"\bRead",
        ("reads",),
        "count",
        exclude=r"pitr|backup|restore",
    ),
    _rule(
        "firestore",
        ("Cloud Firestore", "Firestore"),
        r"\bWrite",
        ("writes",),
        "count",
        exclude=r"pitr|backup|restore",
    ),
    _rule(
        "firestore",
        ("Cloud Firestore", "Firestore"),
        r"\bDelete",
        ("deletes",),
        "count",
        exclude=r"pitr|backup|restore",
    ),
    _rule(
        "firestore",
        ("Cloud Firestore", "Firestore"),
        r"Stored Data|\bStorage\b",
        ("storage",),
        "GiBy.mo",
        exclude=r"pitr|backup|restore",
    ),
    _rule("dns", "Cloud DNS", r"Managed ?Zone", ("zone",), "mo", regional=False, exclude=r"quer"),
    _rule("dns", "Cloud DNS", r"Quer(?:y|ies)", ("queries",), "count", regional=False),
    _rule(
        "secrets",
        "Secret Manager",
        r"Secret version",
        ("versions",),
        "mo",
        regional=False,
        exclude=r"access|rotation",
    ),
    _rule(
        "secrets",
        "Secret Manager",
        r"Access operations",
        ("access",),
        "count",
        regional=False,
    ),
    _rule(
        "logging",
        ("Cloud Logging", "Stackdriver Logging"),
        r"Log Volume|Logging Storage|Log Storage|Ingest",
        ("ingestion",),
        "GiBy",
        regional=False,
        exclude=r"retention|analytics|vended",
    ),
    _rule(
        "monitoring",
        ("Cloud Monitoring", "Stackdriver Monitoring"),
        r"Metric Volume|Ingest",
        ("ingestion",),
        "MiBy",
        regional=False,
        exclude=r"api|uptime|sample",
    ),
    _rule(
        "artifact_registry",
        "Artifact Registry",
        r"\bStorage\b",
        ("storage",),
        "GiBy.mo",
        exclude=r"egress|transfer",
    ),
    _rule(
        "dataproc",
        ("Cloud Dataproc", "Dataproc"),
        r"Dataproc",
        ("vcpu",),
        "h",
        regional=False,
        exclude=r"serverless|metastore|gke|premium|storage",
    ),
    _rule(
        "composer",
        "Cloud Composer",
        r"(?P<size>Small|Medium|Large) Environment Fee",
        lambda m: (None, (f"env-{m.group('size').lower()}",)),
        "h",
    ),
    _rule(
        "composer",
        "Cloud Composer",
        r"Data Compute Unit|\bDCU\b",
        ("dcu",),
        "h",
        exclude=r"milli|storage",
    ),
    _rule("composer", "Cloud Composer", r"\bStorage\b", ("storage",), "GiBy.mo"),
    _rule(
        "filestore",
        ("Cloud Filestore", "Filestore"),
        r"Filestore Capacity (?P<tier>Basic HDD|Basic SSD|Zonal|Regional|Enterprise|High Scale)",
        lambda m: (None, (_slug(m.group("tier")),)),
        "GiBy.mo",
    ),
    _rule(
        "alloydb",
        "AlloyDB",
        r"\b(?:vCPU|CPU)\b",
        ("vcpu",),
        "h",
        exclude=r"read pool|omni",
    ),
    _rule(
        "alloydb",
        "AlloyDB",
        r"\b(?:Memory|RAM)\b",
        ("memory",),
        "GiBy.h",
        exclude=r"read pool|omni",
    ),
    _rule(
        "alloydb",
        "AlloyDB",
        r"\bStorage\b",
        ("storage",),
        "GiBy.mo",
        exclude=r"backup|omni",
    ),
    _rule("scheduler", "Cloud Scheduler", r"\bJobs?\b", ("job",), "mo", regional=False),
    _rule("tasks", "Cloud Tasks", r"Operations|Tasks?\b", ("operations",), "count"),
    _rule(
        "kms",
        ("Cloud Key Management Service (KMS)", "Cloud KMS"),
        r"key versions?",
        ("key-version",),
        "mo",
        exclude=r"hsm|external|ekm|operation",
    ),
    _rule(
        "kms",
        ("Cloud Key Management Service (KMS)", "Cloud KMS"),
        r"cryptographic operations|operations",
        ("operations",),
        "count",
        exclude=r"hsm|external|ekm",
    ),
    _rule("cloud_build", "Cloud Build", r"Build time|build minutes", ("build-minute",), "min"),
    _rule("workflows", "Workflows", r"Internal steps?", ("internal-step",), "count"),
    _rule("workflows", "Workflows", r"External steps?|HTTP", ("external-step",), "count"),
    _rule("eventarc", "Eventarc", r"\bEvents?\b", ("events",), "count", regional=False),
    _rule("api_gateway", "API Gateway", r"\bCalls?\b", ("calls",), "count", regional=False),
)

#: Each table service: its title, its keys, and its unit in words.
SERVICES: dict[str, tuple[str, list[str], str]] = {
    "compute": (
        "Compute Engine on-demand",
        ["region", "series", "resource"],
        "vCPU-hour (core), GiB-hour (ram), instance-hour (f1, g1)",
    ),
    "gpu": ("Compute Engine GPUs", ["region", "gpu"], "GPU-hour"),
    "windows": ("Windows Server licence", ["region", "resource"], "vCPU-hour"),
    "disk": ("Persistent Disk and Hyperdisk", ["region", "type"], "GiB-month"),
    "disk_performance": (
        "Hyperdisk provisioned performance",
        ["region", "type", "what"],
        "IOPS-month, MiBps-month",
    ),
    "ip": ("External IP addresses", ["region", "state"], "hour"),
    "load_balancing": ("Cloud Load Balancing", ["region", "item"], "hour, GiB"),
    "cdn": ("Cloud CDN", ["region", "destination", "item"], "GiB, request"),
    "nat": ("Cloud NAT", ["region", "item"], "VM-hour, GiB"),
    "vpn": ("Cloud VPN", ["region", "item"], "tunnel-hour"),
    "interconnect": ("Cloud Interconnect", ["region", "kind", "capacity"], "hour"),
    "armor": ("Cloud Armor", ["region", "item"], "month, request"),
    "cloud_sql": (
        "Cloud SQL",
        ["region", "engine", "edition", "availability", "item"],
        "vCPU-hour, GiB-hour, GiB-month",
    ),
    "sql_license": ("Cloud SQL for SQL Server licence", ["region", "edition"], "vCPU-hour"),
    "gke": ("Google Kubernetes Engine", ["region", "item"], "hour, vCPU-hour, GiB-hour"),
    "cloud_run": ("Cloud Run", ["region", "item"], "vCPU-second, GiB-second, request"),
    "app_engine": ("App Engine", ["region", "item"], "instance-hour, vCPU-hour, GiB-hour"),
    "storage": ("Cloud Storage", ["region", "class"], "GiB-month"),
    "storage_ops": ("Cloud Storage operations", ["region", "scope", "class", "item"], "op, GiB"),
    "memorystore": ("Memorystore for Redis", ["region", "tier", "band"], "GiB-hour"),
    "pubsub": ("Pub/Sub", ["region", "item"], "TiB, GiB-month"),
    "dataflow": ("Dataflow", ["region", "item"], "vCPU-hour, GiB-hour"),
    "bigquery": ("BigQuery", ["region", "item"], "TiB scanned, GiB-month"),
    "bigtable": ("Bigtable", ["region", "item"], "node-hour, GiB-month"),
    "spanner": ("Spanner", ["region", "item"], "node-hour, GiB-month"),
    "firestore": ("Firestore", ["region", "item"], "operation, GiB-month"),
    "dns": ("Cloud DNS", ["region", "item"], "zone-month, query"),
    "secrets": ("Secret Manager", ["region", "item"], "version-month, operation"),
    "logging": ("Cloud Logging", ["region", "item"], "GiB"),
    "monitoring": ("Cloud Monitoring", ["region", "item"], "MiB"),
    "artifact_registry": ("Artifact Registry", ["region", "item"], "GiB-month"),
    "dataproc": ("Dataproc", ["region", "item"], "vCPU-hour"),
    "composer": ("Cloud Composer", ["region", "item"], "hour, DCU-hour, GiB-month"),
    "filestore": ("Filestore", ["region", "tier"], "GiB-month"),
    "alloydb": ("AlloyDB", ["region", "item"], "vCPU-hour, GiB-hour, GiB-month"),
    "scheduler": ("Cloud Scheduler", ["region", "item"], "job-month"),
    "tasks": ("Cloud Tasks", ["region", "item"], "operation"),
    "kms": ("Cloud KMS", ["region", "item"], "key-version-month, operation"),
    "cloud_build": ("Cloud Build", ["region", "item"], "build-minute"),
    "workflows": ("Workflows", ["region", "item"], "step"),
    "eventarc": ("Eventarc", ["region", "item"], "event"),
    "api_gateway": ("API Gateway", ["region", "item"], "call"),
}


def _file(
    rates: dict[str, Any], path: tuple[str, ...], rate: float, rank: int, ranks: dict[Any, int]
) -> None:
    """Write *rate* at *path*; a SKU sold in fewer regions wins over a broader one."""
    if ranks.get(path, sys.maxsize) <= rank:
        return
    node = rates
    for part in path[:-1]:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            return
        node = child
    if isinstance(node.get(path[-1]), dict):
        return
    node[path[-1]] = rate
    ranks[path] = rank


def reduce(skus: Iterable[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """The SKUs as each table service's rates, and each service's latest effective day."""
    rates: dict[str, dict[str, Any]] = {}
    days: dict[str, str] = {}
    ranks: dict[Any, int] = {}
    for sku in skus:
        category = sku.get("category", {})
        if category.get("usageType", "OnDemand") != "OnDemand":
            continue
        description = str(sku.get("description", ""))
        if _NOT_LIST.search(description):
            continue
        priced = _price(sku)
        if priced is None:
            continue
        value, unit, day = priced
        source = category.get("serviceDisplayName", "")
        for rule in RULES:
            if source not in rule.sources:
                continue
            match = rule.pattern.search(description)
            if match is None or (rule.exclude is not None and rule.exclude.search(description)):
                continue
            key = rule.key(match)
            if key is None:
                continue
            where, path = key
            rate = convert(value, unit, rule.units.get(path[-1], rule.unit))
            if rate is None:
                continue
            regions = [str(region) for region in sku.get("serviceRegions") or []]
            places = [where] if where else (regions if rule.regional and regions else ["global"])
            rank = 0 if where else len(regions)
            for place in places:
                _file(rates, (rule.service, place, *path), rate, rank, ranks)
            days[rule.service] = max(days.get(rule.service, ""), day)
            break
    return rates, days


# -- machine types ------------------------------------------------------------


class _Tables(HTMLParser):
    """Every table's rows as text cells, footnote markers left out."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._sup = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
        elif tag == "sup":
            self._sup += 1
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None and self.tables:
            self.tables[-1].append(self._row)
            self._row = None
        elif tag == "sup" and self._sup:
            self._sup -= 1

    def handle_data(self, data: str) -> None:
        if self._cell is not None and not self._sup:
            self._cell.append(data)


_MACHINE = re.compile(r"[a-z][a-z0-9]*-[a-z0-9-]+")


def _number(text: str) -> float | None:
    cleaned = text.replace(",", "").strip()
    if share := re.fullmatch(r"(\d+)/(\d+)", cleaned):
        # a share of one GPU: g4-standard-6 has 1/8
        return int(share.group(1)) / int(share.group(2))
    return float(cleaned) if re.fullmatch(r"\d+(?:\.\d+)?", cleaned) else None


def machine_types(pages: Iterable[str]) -> dict[str, dict[str, float | str]]:
    """machine type -> vcpus, memory_gb, and gpus and gpu (the model) where it has GPUs,
    read from the machine-family pages' tables."""
    found: dict[str, dict[str, float | str]] = {}
    for page in pages:
        parser = _Tables()
        parser.feed(page)
        for table in parser.tables:
            columns: dict[str, int] | None = None
            model = ""
            for row in table:
                lowered = [cell.lower() for cell in row]
                attached = next((cell for cell in row if cell.startswith("Attached NVIDIA")), "")
                if attached:
                    model = gpu_slug(re.sub(r"Grace|Blackwell|Ultra", "", attached))
                    continue
                if lowered and lowered[0].startswith("machine type"):
                    vcpu = [i for i, c in enumerate(lowered) if c.startswith("vcpu")]
                    share = [i for i, c in enumerate(lowered) if c.startswith("fractional")]
                    memory = [
                        i
                        for i, c in enumerate(lowered)
                        if "memory" in c and "range" not in c and "custom" not in c
                    ]
                    gpus = [
                        i
                        for i, c in enumerate(lowered)
                        if c.startswith(("gpu count", "number of gpu"))
                    ]
                    columns = (
                        {
                            "vcpus": (share or vcpu)[0],
                            "memory_gb": memory[0],
                            **({"gpus": gpus[0]} if gpus else {}),
                        }
                        if vcpu and memory
                        else None
                    )
                    continue
                if columns is None or not row or not _MACHINE.fullmatch(row[0]):
                    continue
                values = {
                    name: _number(row[index]) if index < len(row) else None
                    for name, index in columns.items()
                }
                if values["vcpus"] is None or values["memory_gb"] is None:
                    continue
                shape: dict[str, float | str] = {
                    "vcpus": float(values["vcpus"]),
                    "memory_gb": float(values["memory_gb"]),
                }
                count = values.get("gpus")
                named = re.search(r"-(\d+)g$", row[0])
                if count is None and named and model:
                    count = float(named.group(1))
                if model and count:
                    shape["gpus"], shape["gpu"] = float(count), model
                found.setdefault(row[0], shape)
    return found


def _machine_service(shapes: dict[str, dict[str, float | str]], read: str) -> dict[str, Any]:
    rates = {
        name: {key: value for key, value in shape.items() if not isinstance(value, str)}
        for name, shape in shapes.items()
    }
    words: dict[str, str] = {}
    gpus: dict[str, str] = {}
    for name, shape in shapes.items():
        vcpus = float(shape["vcpus"])
        text = f"{vcpus:g} vCPU, {float(shape['memory_gb']):g} GB"
        if "gpu" in shape:
            text += f", {float(shape['gpus']):g} x {shape['gpu']} GPU"
            gpus[name] = str(shape["gpu"])
        words[name] = text
    return {
        "title": "Compute Engine machine types",
        "source": MACHINE_SOURCE,
        "published": read,
        "unit": "vCPUs, GB of memory, GPUs",
        "keys": ["machine_type", "field"],
        "rates": rates,
        "info": {"machine_type": words, "gpu": gpus},
    }


# -- the build ----------------------------------------------------------------


def _services(key: str, *, fresh: bool) -> dict[str, str]:
    """Catalog API display name -> service id."""
    return {
        service["displayName"]: service["serviceId"]
        for service in _pages("services", "services", {"pageSize": "5000"}, key, fresh=fresh)
    }


def build(fresh: bool = False, *, folder: Path | None = None, today: str | None = None) -> Path:
    """Read the Catalog API and the machine-family pages; write ``gcp.json``."""
    key = _key()
    read = today or datetime.date.today().isoformat()
    catalog = _services(key, fresh=fresh)
    wanted = sorted({name for rule in RULES for name in rule.sources})
    missing = [name for name in wanted if name not in catalog]
    skus: list[dict[str, Any]] = []
    for name in wanted:
        if name in catalog:
            skus.extend(
                _pages(
                    f"services/{catalog[name]}/skus",
                    "skus",
                    {"currencyCode": "USD", "pageSize": "5000"},
                    key,
                    fresh=fresh,
                )
            )
    rates, days = reduce(skus)
    if not rates.get("compute"):
        raise PricingError(
            "the Catalog API answered, but no Compute Engine core or RAM rate was found in it; "
            "the SKU descriptions may have changed (see RULES in pricing/build/gcp.py)"
        )
    services: dict[str, dict[str, Any]] = {}
    for name, (title, keys, unit) in SERVICES.items():
        found = rates.get(name)
        if not found:
            print(f"NOTE gcp: no {name} rates in the Catalog API answer", file=sys.stderr)
            continue
        services[name] = {
            "title": title,
            "source": SOURCE,
            "published": days.get(name, "") or read,
            "unit": unit,
            "keys": keys,
            "rates": found,
        }
    if missing:
        print(f"NOTE gcp: the Catalog API lists none of {', '.join(missing)}", file=sys.stderr)
    shapes = machine_types(
        download(url, fresh=fresh).decode("utf-8", "replace") for url in MACHINE_PAGES
    )
    if not shapes:
        raise PricingError(f"no machine types were read from {', '.join(MACHINE_PAGES)}")
    services["machine_types"] = _machine_service(shapes, read)
    return write_table("gcp", services, read=read, folder=folder)
