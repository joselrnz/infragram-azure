"""The Azure price table, from the Azure Retail Prices API.

The API (``prices.azure.com/api/retail/prices``) is public and needs no
sign-in. It answers an OData ``$filter`` a thousand meters a page, each
page naming the next. Every page is kept in the build cache, so a rebuild
reads the network once. Only pay-as-you-go meters are kept (``Consumption``,
in US dollars); Spot, Low Priority, Dev/Test and reservation meters are
left out.

Each service keeps its rates by region (``armRegionName``: ``eastus``;
``global`` for the meters Azure bills the same everywhere; ``zone1`` and so
on for the meters it bills by data-transfer zone), then by the tier or size
a sizing names, then by the meter. A meter with volume tiers keeps its
first tier under its name and each later tier as ``name@<from>``, ``from``
in the meter's own unit. ``info.unit`` keeps each meter's unit of measure
as the API states it (``1 Hour``, ``10K``, ``1 GB/Month``), so a pricer
converts from the published unit and never from a guess.

Virtual machines are their own service, by region, operating system and
size, with each size's vCPUs and memory from the Azure pricing
calculator's data (azure.microsoft.com), the only public source that lists
them without signing in. A size is kept without its ``Standard_`` prefix
(``D2s_v5``; ``Basic_A0`` keeps its own), which keeps the table small;
retired promotional sizes are left out.
"""

from __future__ import annotations

import datetime
import json
import re
import string
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field

from .. import PricingError
from . import download, write_table

__all__ = ["API", "SOURCE", "SPECS", "Spec", "build", "items", "region_key"]

API = "https://prices.azure.com/api/retail/prices"
SOURCE = "Azure Retail Prices API (prices.azure.com)"
#: The pricing calculator's virtual machine data: each size's cores and memory.
CALCULATOR = "https://azure.microsoft.com/api/v3/pricing/virtual-machines/calculator/?culture=en-us"
#: Meters for other than pay-as-you-go use.
_NOT_PAYG = re.compile(r"\b(Spot|Low Priority|DevTest|Dev/Test)\b", re.IGNORECASE)
_NO_SPOT = "contains(meterName, 'Spot') eq false and contains(meterName, 'Low Priority') eq false"
#: The free-grant twins of a priced meter ("Hot LRS Data Stored - Free").
_FREE_TWIN = re.compile(r"\s-\sFree$")
_THREADS = 4

Item = dict[str, Any]
Pick = Callable[[Item], "tuple[str, str] | None"]


class Spec(BaseModel):
    """One service in the table: what to ask the API for, and how each meter is kept."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    title: str
    #: The OData filter, without the pay-as-you-go clause.
    filter: str
    #: A meter -> (tier or size, meter name kept), or None to leave it out.
    pick: Pick
    #: Filters that split one large query into parallel ones; their union is the whole.
    split: list[str] = Field(default_factory=list)


def _url(odata: str) -> str:
    return f"{API}?currencyCode=%27USD%27&$filter=" + quote(odata, safe="")


def _page(url: str, fresh: bool) -> Any:
    """One page; a busy API (HTTP 429) is asked again after a pause."""
    for attempt in range(8):
        try:
            return json.loads(download(url, fresh=fresh))
        except PricingError as error:
            if "HTTP 429" not in str(error) and "HTTP 503" not in str(error):
                raise
            time.sleep(min(60, 4 * 2**attempt))
    raise PricingError(f"the Azure Retail Prices API stayed busy for {url}")


def items(odata: str, *, fresh: bool = False) -> list[Item]:
    """Every pay-as-you-go meter the filter matches, page by page."""
    url: str | None = _url(f"{odata} and priceType eq 'Consumption'")
    found: list[Item] = []
    while url:
        page = _page(url, fresh)
        if not isinstance(page, dict) or not isinstance(page.get("Items"), list):
            raise PricingError(f"{url} did not answer with the API's page shape")
        found.extend(page["Items"])
        url = page.get("NextPageLink") or None
    return found


def region_key(name: str) -> str | None:
    """The table's region key for an ``armRegionName``; None for US Government
    and other non-public clouds."""
    lowered = name.strip().lower()
    if lowered in ("", "global"):
        return "global"
    if "gov" in lowered or "dod" in lowered or lowered.startswith(("china", "germany")):
        return None
    return re.sub(r"[^a-z0-9]", "", lowered)


def _tier(value: Any) -> str:
    number = float(value or 0)
    return str(int(number)) if number.is_integer() else repr(number)


def _reduce(spec: Spec, found: list[Item]) -> dict[str, Any]:
    """The service's rates, units and newest effective date."""
    kept: list[tuple[str, str, str, Item]] = []
    seen_units: dict[str, Counter[str]] = {}
    for item in found:
        if item.get("type") != "Consumption" or item.get("currencyCode", "USD") != "USD":
            continue
        meter_name = str(item.get("meterName", ""))
        if _NOT_PAYG.search(f"{item.get('skuName', '')} {meter_name}"):
            continue
        if _FREE_TWIN.search(meter_name):
            continue
        region = region_key(str(item.get("armRegionName", "")))
        if region is None:
            continue
        picked = spec.pick(item)
        if picked is None:
            continue
        sku, meter = picked
        kept.append((region, sku, meter, item))
        seen_units.setdefault(f"{sku}|{meter}", Counter())[str(item.get("unitOfMeasure", ""))] += 1
    # a meter a few regions publish in another unit keeps the unit most use
    units = {key: counts.most_common(1)[0][0] for key, counts in seen_units.items()}
    rates: dict[str, dict[str, dict[str, float]]] = {}
    dates: dict[tuple[str, str, str], str] = {}
    newest = ""
    for region, sku, meter, item in kept:
        if str(item.get("unitOfMeasure", "")) != units[f"{sku}|{meter}"]:
            continue
        tier = _tier(item.get("tierMinimumUnits"))
        key = meter if tier == "0" else f"{meter}@{tier}"
        price = float(item["retailPrice"])
        start = str(item.get("effectiveStartDate", ""))[:10]
        node = rates.setdefault(region, {}).setdefault(sku, {})
        seen = dates.get((region, sku, key))
        # two meters for one key: the one that took effect last is the price
        if seen is None or start > seen or (start == seen and price > node[key]):
            node[key] = price
            dates[(region, sku, key)] = start
        newest = max(newest, start)
    if not rates:
        raise PricingError(f"{spec.name}: the API answered no meters for {spec.filter}")
    return {
        "title": spec.title,
        "source": SOURCE,
        "published": newest,
        "unit": "each meter's unit of measure, in info.unit",
        "keys": ["region", "sku", "meter"],
        "rates": rates,
        "info": {"unit": dict(sorted(units.items()))},
    }


def _query(spec: Spec, fresh: bool) -> list[Item]:
    if not spec.split:
        return items(spec.filter, fresh=fresh)
    found: list[Item] = []
    for part in spec.split:
        found.extend(items(f"{spec.filter} and {part}", fresh=fresh))
    return found


# -- the meters each service keeps ---------------------------------------------------------


def _short(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _vm_os(item: Item) -> str | None:
    product = str(item.get("productName", ""))
    if re.search(r"Cloud ?Services|Dedicated ?Host", product, re.IGNORECASE):
        return None
    if str(item.get("unitOfMeasure")) != "1 Hour":
        return None
    return "Windows" if "Windows" in product else "Linux"


_DISK_TIER = re.compile(r"^([PES]\d+) (LRS|ZRS) Disk$")
_DISK_PART = {
    "Provisioned Capacity": "capacity",
    "Provisioned IOPS": "iops",
    "Provisioned Throughput (MBps)": "throughput",
}


def _disks(item: Item) -> tuple[str, str] | None:
    product, sku, meter = item["productName"], item["skuName"], item["meterName"]
    if match := _DISK_TIER.match(meter):
        return f"{match.group(1)} {match.group(2)}", "disk"
    if product in ("Azure Premium SSD v2", "Ultra Disks") and "Confidential" not in sku:
        kind = "PremiumV2" if product == "Azure Premium SSD v2" else "Ultra"
        redundancy = sku.split()[-1]
        for words, part in _DISK_PART.items():
            if meter.endswith(words):
                return f"{kind} {redundancy}", part
    return None


#: The blob, file and queue meters a pricer reads, by the words they end with.
_STORAGE_PART = (
    ("Data Stored", "stored"),
    ("Write Operations", "write"),
    ("Read Operations", "read"),
    ("All Other Operations", "other"),
    ("Other Operations", "other"),
    ("Protocol Operations", "other"),
    ("List and Create Container Operations", "list"),
    ("List Operations", "list"),
    ("Data Retrieval", "retrieval"),
    ("Data Write", "data-write"),
    ("Metadata", "metadata"),
    ("Class 1 Operations", "write"),
    ("Class 2 Operations", "read"),
    ("Provisioned", "provisioned"),
)


def _storage(item: Item) -> tuple[str, str] | None:
    product, sku, meter = item["productName"], item["skuName"], item["meterName"]
    if re.search(r"Priority|Index Tags|Early Delete|Inventory|Additional IO|Free|Batch", meter):
        return None
    kind = {
        "General Block Blob v2": "Blob",
        "Files v2": "Files",
        "Premium Files": "Files",
        "Queues v2": "Queue",
        "Tables": "Table",
    }.get(product)
    if kind is None:
        return None
    for words, part in _STORAGE_PART:
        if meter.endswith(words):
            return f"{kind} {sku}", part
    return None


def _sku_meter(item: Item) -> tuple[str, str]:
    """The API's own sku and meter names, spaces tidied."""
    return _short(item["skuName"]), _short(item["meterName"])


def _named(products: dict[str, str]) -> Pick:
    """Meters of the named products, each sku prefixed with the product's short name."""

    def pick(item: Item) -> tuple[str, str] | None:
        short = products.get(item["productName"])
        if short is None:
            return None
        sku, meter = _sku_meter(item)
        return (f"{short} {sku}" if short else sku), meter

    return pick


_APP_PLAN = re.compile(r"^Azure App Service (.+?) Plan( - Linux)?$")


def _app_service(item: Item) -> tuple[str, str] | None:
    product, sku, meter = item["productName"], item["skuName"], item["meterName"]
    if product == "Static Web Apps":
        return f"StaticWebApps {_short(sku)}", _short(meter)
    if product.startswith(("Azure App Service SSL", "Azure App Service Domain")):
        return "Extras", _short(meter)
    match = _APP_PLAN.match(product)
    if match is None or str(item.get("unitOfMeasure")) != "1 Hour":
        return None
    if re.search(r"Stamp|Front End|ASIP|IDH", sku):
        return None
    os_name = "Linux" if match.group(2) else "Windows"
    return f"{os_name} {sku.replace(' ', '')}", "instance"


_SQL_HW = re.compile(
    r"^SQL (?:Database|Managed Instance)(?: Single/Elastic Pool| SingleDB/Elastic Pool)?"
    r" (General Purpose|Business Critical|Hyperscale) - "
    r"(?:Compute (Gen5|FSv2 Series|DC-Series|M Series)|(Premium Series(?: Memory Optimized)?) Compute)$"
)


_SQL_TIERS = ("General Purpose", "Business Critical", "Hyperscale")


def _sql(item: Item) -> tuple[str, str] | None:
    """SQL Database and SQL Managed Instance: compute per vCore by tier and
    hardware, zone redundancy per vCore, the SQL license per vCore, storage,
    and the DTU sizes per day."""
    product, sku, meter = item["productName"], item["skuName"], item["meterName"]
    unit = str(item.get("unitOfMeasure"))
    kind = "MI" if product.startswith("SQL Managed Instance") else "DB"
    if match := _SQL_HW.match(product):
        tier = match.group(1)
        hardware = match.group(2) or match.group(3)
        if meter == "vCore" and sku == "vCore":
            return f"{kind} {tier} {hardware}", "vcore"
        if meter == "Zone Redundancy vCore" and sku.startswith("vCore"):
            return f"{kind} {tier} {hardware}", "zone-redundancy"
        return None
    if product.endswith("- SQL License") and meter == "vCore":
        tier = next(
            t for t in ("General Purpose", "Business Critical", "Hyperscale") if t in product
        )
        return f"{kind} {tier} License", "vcore"
    if product == "SQL Database General Purpose - Serverless - Compute Gen5":
        if sku == "1 vCore" and meter == "vCore":
            return "DB Serverless General Purpose Gen5", "vcore"
        return None
    storage = {
        "SQL Database Single/Elastic Pool General Purpose - Storage": "General Purpose",
        "SQL Database Single/Elastic Pool Business Critical - Storage": "Business Critical",
        "SQL Database SingleDB Hyperscale - Storage": "Hyperscale",
        "SQL Managed Instance General Purpose - Storage": "General Purpose",
        "SQL Managed Instance Business Critical - Storage": "Business Critical",
    }.get(product)
    if storage and meter in (f"{storage} Data Stored", f"{storage} Zone Redundancy Data Stored"):
        zone = " Zone Redundancy" if "Zone Redundancy" in meter else ""
        return f"{kind} {storage} Storage{zone}", "gb"
    if match := re.match(r"^SQL Database Single (Basic|Standard|Premium)$", product):
        if "Secondary" in sku or unit != "1/Day" or not re.fullmatch(r"B|S\d+|P\d+", sku):
            return None
        return "DTU", "Basic" if sku == "B" else sku
    return None


def _flexible(item: Item) -> tuple[str, str] | None:
    """PostgreSQL and MySQL Flexible Server: compute per vCore by series (or
    per burstable size), and storage."""
    product, sku, meter = item["productName"], item["skuName"], item["meterName"]
    engine = "PostgreSQL" if "PostgreSQL" in product else "MySQL"
    if "Cosmos DB" in product or "HorizonDB" in product:
        return None
    if match := re.search(
        r"Flexible Server (?:General Purpose|Memory Optimized|Confidential Compute)?\s*"
        r"(\w+?) Series(?: Compute)?$",
        product,
    ):
        series = match.group(1)
        if sku == "vCore" and meter == "vCore":
            return f"{engine} {series.lower()}", "vcore"
        return None
    if "Burstable BS Series Compute" in product:
        size = re.sub(r"^Standard_", "", sku).lower().rstrip("2")
        if size in ("basic",):
            return None
        return f"{engine} burstable", size
    if product.endswith(("Flex Server Storage", "Flexible Server Storage")) and (
        meter == "Storage Data Stored"
    ):
        return f"{engine} storage", "gb"
    return None


def _cosmos(item: Item) -> tuple[str, str] | None:
    product, sku, meter = item["productName"], item["skuName"], item["meterName"]
    if product == "Azure Cosmos DB":
        if sku == "RUs" and meter in ("100 RU/s", "Data Stored"):
            return "Provisioned", "ru" if meter == "100 RU/s" else "gb"
        if sku == "mRUs" and meter == "100 Multi-master RU/s":
            return "Provisioned", "ru-multi-write"
        return None
    if product == "Azure Cosmos DB serverless" and meter == "1M RUs":
        return "Serverless", "ru-million"
    return None


def _redis(item: Item) -> tuple[str, str] | None:
    product, sku, meter = item["productName"], item["skuName"], item["meterName"]
    if match := re.match(r"^Azure Redis Cache (Basic|Standard|Premium)$", product):
        if meter == f"{sku} Cache":
            return match.group(1), sku
        return None
    if match := re.match(r"^Azure Redis Cache (Enterprise(?: Flash)?)$", product):
        if meter == f"{sku} Cache":
            return match.group(1), sku
        return None
    match = re.match(r"^Azure Managed Redis - (.+)$", product)
    if match and meter == f"{sku} Cache Instance":
        return f"Managed {match.group(1)}", sku
    return None


def _keep(test: Callable[[Item], bool]) -> Pick:
    """The meters *test* keeps, by the API's own sku and meter names."""

    def pick(item: Item) -> tuple[str, str] | None:
        return _sku_meter(item) if test(item) else None

    return pick


def _keep_named(products: dict[str, str], test: Callable[[Item], bool]) -> Pick:
    """The meters of the named products that *test* keeps."""
    named = _named(products)

    def pick(item: Item) -> tuple[str, str] | None:
        return named(item) if test(item) else None

    return pick


_NETAPP_TIERS = ("Standard", "Premium", "Ultra", "Flexible Service Level")


def _by_product(product: str, short: str = "") -> Pick:
    return _named({product: short})


def _all(item: Item) -> tuple[str, str]:
    return _sku_meter(item)


SPECS: list[Spec] = [
    Spec(
        name="disks",
        title="Managed disks",
        filter="serviceName eq 'Storage' and (productName eq 'Premium SSD Managed Disks' or "
        "productName eq 'Standard SSD Managed Disks' or productName eq "
        "'Standard HDD Managed Disks' or productName eq 'Azure Premium SSD v2' or "
        "productName eq 'Ultra Disks')",
        pick=_disks,
    ),
    Spec(
        name="storage",
        title="Storage accounts (Blob, Files, Queues, Tables)",
        filter="serviceName eq 'Storage' and (productName eq 'General Block Blob v2' or "
        "productName eq 'Files v2' or productName eq 'Premium Files' or "
        "productName eq 'Queues v2' or productName eq 'Tables')",
        pick=_storage,
    ),
    Spec(
        name="network",
        title="Virtual network: public IPs, Private Link, peering",
        filter="serviceName eq 'Virtual Network'",
        pick=_named(
            {
                "IP Addresses": "IP",
                "Public IP Prefix": "Prefix",
                "Virtual Network Private Link": "PrivateLink",
                "Virtual Network Peering": "Peering",
                "Global Virtual Network Peering": "GlobalPeering",
            }
        ),
    ),
    Spec(
        name="sql",
        title="Azure SQL Database and SQL Managed Instance",
        filter="(serviceName eq 'SQL Database' or serviceName eq 'SQL Managed Instance')",
        pick=_sql,
    ),
    Spec(
        name="flexible",
        title="Azure Database for PostgreSQL and MySQL, flexible server",
        filter="(serviceName eq 'Azure Database for PostgreSQL' or "
        "serviceName eq 'Azure Database for MySQL')",
        pick=_flexible,
    ),
    Spec(
        name="cosmos",
        title="Azure Cosmos DB",
        filter="serviceName eq 'Azure Cosmos DB'",
        pick=_cosmos,
    ),
    Spec(
        name="redis",
        title="Azure Cache for Redis",
        filter="serviceName eq 'Redis Cache'",
        pick=_redis,
    ),
    Spec(
        name="appservice",
        title="App Service",
        filter="serviceName eq 'Azure App Service'",
        pick=_app_service,
    ),
    Spec(name="functions", title="Azure Functions", filter="serviceName eq 'Functions'", pick=_all),
    Spec(
        name="aks",
        title="Azure Kubernetes Service",
        filter="serviceName eq 'Azure Kubernetes Service'",
        pick=_keep(lambda item: item["skuName"] in ("Standard", "Automatic")),
    ),
    Spec(
        name="containerapps",
        title="Azure Container Apps",
        filter="serviceName eq 'Azure Container Apps'",
        pick=_keep(lambda item: item["skuName"] in ("Standard", "Dedicated")),
    ),
    Spec(
        name="aci",
        title="Azure Container Instances",
        filter="serviceName eq 'Container Instances'",
        pick=_by_product("Container Instances"),
    ),
    Spec(
        name="acr",
        title="Azure Container Registry",
        filter="serviceName eq 'Container Registry'",
        pick=_all,
    ),
    Spec(
        name="appgateway",
        title="Application Gateway",
        filter="serviceName eq 'Application Gateway'",
        pick=_named(
            {
                "Application Gateway Basic v2": "Basic_v2",
                "Application Gateway Standard v2": "Standard_v2",
                "Application Gateway WAF v2": "WAF_v2",
                "Application Gateway for Containers": "AGC",
                "Application Gateway for Containers WAF": "AGC_WAF",
            }
        ),
    ),
    Spec(
        name="loadbalancer",
        title="Load Balancer",
        filter="serviceName eq 'Load Balancer'",
        pick=_all,
    ),
    Spec(
        name="firewall",
        title="Azure Firewall",
        filter="serviceName eq 'Azure Firewall'",
        pick=_keep(lambda item: item["skuName"] in ("Basic", "Standard", "Premium")),
    ),
    Spec(
        name="frontdoor",
        title="Azure Front Door",
        filter="serviceName eq 'Azure Front Door Service'",
        pick=_by_product("Azure Front Door"),
    ),
    Spec(
        name="cdn",
        title="Azure CDN from Microsoft (classic)",
        filter="serviceName eq 'Content Delivery Network'",
        pick=_by_product("Azure CDN from Microsoft"),
    ),
    Spec(
        name="vpn",
        title="VPN Gateway",
        filter="serviceName eq 'VPN Gateway'",
        pick=_keep(
            lambda item: (
                item["productName"] == "VPN Gateway" and item["meterName"] != "P2S Connection"
            )
        ),
    ),
    Spec(
        name="expressroute",
        title="ExpressRoute",
        filter="serviceName eq 'ExpressRoute'",
        pick=_named(
            {
                "ExpressRoute": "Circuit",
                "ExpressRoute Gateway": "Gateway",
                "ExpressRoute Standard Gateway": "Gateway",
                "ExpressRoute High Performance Gateway": "Gateway",
                "ExpressRoute Ultra High Performance Gateway": "Gateway",
            }
        ),
    ),
    Spec(name="nat", title="NAT Gateway", filter="serviceName eq 'NAT Gateway'", pick=_all),
    Spec(name="bastion", title="Azure Bastion", filter="serviceName eq 'Azure Bastion'", pick=_all),
    Spec(name="dns", title="Azure DNS", filter="serviceName eq 'Azure DNS'", pick=_all),
    Spec(
        name="trafficmanager",
        title="Traffic Manager",
        filter="serviceName eq 'Traffic Manager'",
        pick=_all,
    ),
    Spec(
        name="ddos",
        title="Azure DDoS Protection",
        filter="serviceName eq 'Azure DDOS Protection'",
        pick=_all,
    ),
    Spec(
        name="virtualwan",
        title="Virtual WAN",
        filter="serviceName eq 'Virtual WAN'",
        pick=_keep(lambda item: item["skuName"] == "Standard Hub"),
    ),
    Spec(
        name="routeserver",
        title="Azure Route Server",
        filter="serviceName eq 'Azure Route Server'",
        pick=_keep(lambda item: item["skuName"] == "Basic"),
    ),
    Spec(
        name="keyvault",
        title="Key Vault",
        filter="serviceName eq 'Key Vault'",
        pick=_keep_named(
            {"Key Vault": "", "Azure Dedicated HSM": "Dedicated HSM"},
            lambda item: (
                item["meterName"]
                in ("Operations", "Premium HSM-protected RSA 2048-bit key", "Standard Instance")
            ),
        ),
    ),
    Spec(name="eventhubs", title="Event Hubs", filter="serviceName eq 'Event Hubs'", pick=_all),
    Spec(
        name="servicebus",
        title="Service Bus and Relay",
        filter="serviceName eq 'Service Bus'",
        pick=_keep(
            lambda item: (
                item["skuName"] in ("Basic", "Standard", "Premium", "Hybrid Connections")
                and not (
                    item["meterName"] == "Standard Base Unit" and item["unitOfMeasure"] != "1/Hour"
                )
            )
        ),
    ),
    Spec(name="eventgrid", title="Event Grid", filter="serviceName eq 'Event Grid'", pick=_all),
    Spec(name="apim", title="API Management", filter="serviceName eq 'API Management'", pick=_all),
    Spec(
        name="loganalytics",
        title="Log Analytics",
        filter="serviceName eq 'Log Analytics'",
        pick=_all,
    ),
    Spec(
        name="sentinel",
        title="Microsoft Sentinel",
        filter="serviceName eq 'Sentinel'",
        pick=_keep(lambda item: item["skuName"] == "Pay-as-you-go"),
    ),
    Spec(
        name="synapse",
        title="Azure Synapse Analytics",
        filter="serviceName eq 'Azure Synapse Analytics'",
        pick=_named(
            {
                "Azure Synapse Analytics Dedicated SQL Pool": "Dedicated",
                "Azure Synapse Analytics SQL Storage": "SQL Storage",
                "Azure Synapse Analytics Serverless SQL Pool": "Serverless",
                "Azure Synapse Analytics Serverless Apache Spark Pool - Memory Optimized": "Spark",
            }
        ),
    ),
    Spec(
        name="datafactory",
        title="Azure Data Factory",
        filter="serviceName eq 'Azure Data Factory v2'",
        pick=_keep_named(
            {
                "Azure Data Factory v2": "",
                "Azure Data Factory v2 Data Flow - General Purpose": "Data Flow General Purpose",
            },
            lambda item: item["skuName"] in ("Cloud", "vCore"),
        ),
    ),
    Spec(
        name="databricks",
        title="Azure Databricks",
        filter="serviceName eq 'Azure Databricks'",
        pick=_keep(
            lambda item: (
                item["productName"] == "Azure Databricks" and "Free Trial" not in item["skuName"]
            )
        ),
    ),
    Spec(
        name="logicapps",
        title="Logic Apps",
        filter="serviceName eq 'Logic Apps'",
        pick=_keep_named(
            {"Logic Apps": "", "Logic Apps Integration Account": "Integration Account"},
            lambda item: item["skuName"] in ("Consumption", "Standard", "Basic", "Premium"),
        ),
    ),
    Spec(
        name="signalr", title="Azure SignalR Service", filter="serviceName eq 'SignalR'", pick=_all
    ),
    Spec(
        name="webpubsub", title="Azure Web PubSub", filter="serviceName eq 'Web PubSub'", pick=_all
    ),
    Spec(
        name="backup",
        title="Azure Backup",
        filter="serviceName eq 'Backup'",
        pick=_keep(
            lambda item: (
                item["productName"] == "Backup"
                and (
                    item["skuName"] == "Standard"
                    or item["meterName"].endswith("Protected Instance")
                )
            )
        ),
    ),
    Spec(
        name="site-recovery",
        title="Azure Site Recovery",
        filter="serviceName eq 'Azure Site Recovery'",
        pick=_keep(lambda item: item["productName"] == "Azure Site Recovery"),
    ),
    Spec(
        name="search",
        title="Azure AI Search",
        filter="serviceName eq 'Azure Cognitive Search'",
        pick=_keep(
            lambda item: (
                item["productName"] == "Azure AI Search" and item["meterName"].endswith(" Unit")
            )
        ),
    ),
    Spec(
        name="notificationhubs",
        title="Notification Hubs",
        filter="serviceName eq 'Notification Hubs'",
        pick=_all,
    ),
    Spec(
        name="iothub",
        title="IoT Hub",
        filter="serviceName eq 'IoT Hub'",
        pick=_named(
            {"IoT Hub": "", "IoT Hub Device Provisioning": "DPS", "Device Update for IoT Hub": "DU"}
        ),
    ),
    Spec(
        name="streamanalytics",
        title="Stream Analytics",
        filter="serviceName eq 'Stream Analytics'",
        pick=_by_product("Stream Analytics"),
    ),
    Spec(
        name="appconfig",
        title="App Configuration",
        filter="serviceName eq 'App Configuration'",
        pick=_keep(lambda item: item["meterName"].endswith("Instance")),
    ),
    Spec(
        name="netapp",
        title="Azure NetApp Files",
        filter="serviceName eq 'Azure NetApp Files'",
        pick=_keep(
            lambda item: (
                item["meterName"].endswith(" Capacity") and item["skuName"] in _NETAPP_TIERS
            )
        ),
    ),
    Spec(
        name="powerbi",
        title="Power BI Embedded",
        filter="serviceName eq 'Power BI Embedded'",
        pick=_all,
    ),
    Spec(
        name="analysisservices",
        title="Azure Analysis Services",
        filter="serviceName eq 'Azure Analysis Services'",
        pick=_all,
    ),
    Spec(
        name="grafana",
        title="Azure Managed Grafana",
        filter="serviceName eq 'Azure Grafana Service'",
        pick=_all,
    ),
    Spec(
        name="entrads",
        title="Microsoft Entra Domain Services",
        filter="serviceName eq 'Microsoft Entra Domain Services'",
        pick=_all,
    ),
    Spec(
        name="confidentialledger",
        title="Azure confidential ledger",
        filter="serviceName eq 'Azure confidential ledger'",
        pick=_all,
    ),
    Spec(
        name="digitaltwins",
        title="Azure Digital Twins",
        filter="serviceName eq 'Digital Twins'",
        pick=_all,
    ),
    Spec(name="iotcentral", title="IoT Central", filter="serviceName eq 'IoT Central'", pick=_all),
    Spec(
        name="dataexplorer",
        title="Azure Data Explorer",
        filter="serviceName eq 'Azure Data Explorer'",
        pick=_by_product("Azure Data Explorer"),
    ),
    Spec(
        name="apptesting",
        title="Azure Load Testing",
        filter="serviceName eq 'Azure App Testing'",
        pick=_all,
    ),
    Spec(
        name="botservice",
        title="Azure Bot Service",
        filter="serviceName eq 'Azure Bot Service'",
        pick=_by_product("Azure Bot Service"),
    ),
]


# -- virtual machines ------------------------------------------------------------------------


def _calculator_sizes(fresh: bool) -> dict[str, str]:
    """Each VM size's cores and memory, by its name without separators
    (``d2sv5``), from the pricing calculator's data; empty if it cannot be read."""
    try:
        data = json.loads(download(CALCULATOR, fresh=fresh))
        offers = data["offers"]
    except (PricingError, ValueError, KeyError, TypeError):
        return {}
    sizes: dict[str, str] = {}
    for key, offer in offers.items() if isinstance(offers, dict) else ():
        match = re.match(r"^(?:linux|windows)-(.+)-(standard|basic)$", str(key))
        if not match or not isinstance(offer, dict):
            continue
        cores, ram = offer.get("cores"), offer.get("ram")
        if isinstance(cores, (int, float)) and isinstance(ram, (int, float)) and cores:
            name = re.sub(r"[-_]", "", match.group(1)) + (
                "|basic" if match.group(2) == "basic" else ""
            )
            memory = f"{ram:g}"
            sizes.setdefault(name, f"{cores:g} vCPU, {memory} GiB")
    return sizes


def _size_key(size: str) -> str:
    """A table size (``D2s_v5``, ``Basic_A0``) as the calculator names it."""
    basic = size.startswith("Basic_")
    rest = size.partition("_")[2] if basic else size
    return re.sub(r"[-_]", "", rest.lower()) + ("|basic" if basic else "")


def _vms(fresh: bool) -> dict[str, Any]:
    base = f"serviceName eq 'Virtual Machines' and {_NO_SPOT}"
    parts = [f"startswith(armSkuName, 'Standard_{letter}')" for letter in string.ascii_uppercase]
    parts.append("startswith(armSkuName, 'Basic_')")
    with ThreadPoolExecutor(_THREADS) as pool:
        pages = list(pool.map(lambda part: items(f"{base} and {part}", fresh=fresh), parts))
    rates: dict[str, dict[str, dict[str, float]]] = {}
    dates: dict[tuple[str, str, str], str] = {}
    newest = ""
    for item in (each for page in pages for each in page):
        if item.get("type") != "Consumption" or _NOT_PAYG.search(
            f"{item.get('skuName', '')} {item.get('meterName', '')}"
        ):
            continue
        os_name = _vm_os(item)
        region = region_key(str(item.get("armRegionName", "")))
        size = str(item.get("armSkuName", "")).removeprefix("Standard_")
        if os_name is None or region is None or region == "global" or not size:
            continue
        if size.endswith("_Promo"):
            continue
        price = float(item["retailPrice"])
        start = str(item.get("effectiveStartDate", ""))[:10]
        node = rates.setdefault(region, {}).setdefault(os_name, {})
        seen = dates.get((region, os_name, size))
        if seen is None or start > seen or (start == seen and price > node[size]):
            node[size] = price
            dates[(region, os_name, size)] = start
        newest = max(newest, start)
    if not rates:
        raise PricingError("the API answered no virtual machine meters")
    sizes = _calculator_sizes(fresh)
    every = {size for region in rates.values() for table in region.values() for size in table}
    info = {size: sizes[_size_key(size)] for size in sorted(every) if _size_key(size) in sizes}
    return {
        "title": "Virtual machines, pay as you go",
        "source": SOURCE,
        "published": newest,
        "unit": "hour",
        "keys": ["region", "os", "size"],
        "rates": rates,
        "info": {"size": info},
    }


def build(fresh: bool = False) -> Path:
    """Read the Azure Retail Prices API and write ``assets/prices/azure.json``."""
    services: dict[str, dict[str, Any]] = {"vm": _vms(fresh)}
    with ThreadPoolExecutor(_THREADS) as pool:
        found = list(pool.map(lambda spec: _query(spec, fresh), SPECS))
    for spec, meters in zip(SPECS, found, strict=True):
        services[spec.name] = _reduce(spec, meters)
    return write_table("azure", services, read=datetime.date.today().isoformat())
