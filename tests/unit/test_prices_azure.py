"""Azure prices, from the table the Azure Retail Prices API is read into.

Held here, with a small table built in the test (no network):

- a virtual machine is priced by size, operating system, count and hours;
  what the sizing does not say is a default, listed as assumed;
- a region the frames name is used, and a meter Azure bills the same in
  every region is priced from the table's ``global`` rates;
- usage is priced tier by tier in the meter's published unit (Blob storage
  past 50 TB, the Functions free grant), and kept apart from fixed lines;
- a size, a region, a choice or a sizing key the table or the pricer does
  not know is refused, never priced as a default;
- the shipped table prices every Azure pricer's defaults, and a
  Standard_D2s_v5 Linux VM in East US at the rate the API publishes.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from infragram.pricing import Price, PricingError, tables as price_tables
from infragram.pricing.ask import HOURS, Ask
from infragram.pricing.azure import COVERAGE, measure, tiered
from infragram.pricing.build import write_table
from infragram.pricing.tables import load_table


def _service(rates: dict[str, Any], units: dict[str, str], title: str) -> dict[str, Any]:
    return {
        "title": title,
        "source": "Azure Retail Prices API (prices.azure.com)",
        "published": "2026-10-01",
        "unit": "each meter's unit of measure, in info.unit",
        "keys": ["region", "sku", "meter"],
        "rates": rates,
        "info": {"unit": units},
    }


SERVICES: dict[str, dict[str, Any]] = {
    "vm": {
        "title": "Virtual machines, pay as you go",
        "source": "Azure Retail Prices API (prices.azure.com)",
        "published": "2026-10-01",
        "unit": "hour",
        "keys": ["region", "os", "size"],
        "rates": {
            "eastus": {"Linux": {"D2s_v5": 0.096}, "Windows": {"D2s_v5": 0.188}},
            "westeurope": {"Linux": {"D2s_v5": 0.1}, "Windows": {"D2s_v5": 0.2}},
        },
        "info": {"size": {"D2s_v5": "2 vCPU, 8 GiB"}},
    },
    "storage": _service(
        {
            "eastus": {
                "Blob Hot LRS": {
                    "stored": 0.0208,
                    "stored@51200": 0.019968,
                    "write": 0.05,
                    "read": 0.004,
                },
                # East US 2's rates: the price list gives RA-GZRS no write meter
                "Blob Hot GZRS": {"stored": 0.0414, "write": 0.1125, "read": 0.0044},
                "Blob Hot RA-GZRS": {"stored": 0.05175, "read": 0.0044},
            }
        },
        {
            "Blob Hot LRS|stored": "1 GB/Month",
            "Blob Hot LRS|write": "10K",
            "Blob Hot LRS|read": "10K",
            "Blob Hot GZRS|stored": "1 GB/Month",
            "Blob Hot GZRS|write": "10K",
            "Blob Hot GZRS|read": "10K",
            "Blob Hot RA-GZRS|stored": "1 GB/Month",
            "Blob Hot RA-GZRS|read": "10K",
        },
        "Storage accounts",
    ),
    "site-recovery": _service(
        {"eastus": {"Azure": {"VM Replicated to Azure": 25.0}}},
        {"Azure|VM Replicated to Azure": "1/Month"},
        "Azure Site Recovery",
    ),
    "servicebus": _service(
        {
            "eastus": {
                "Standard": {"Standard Base Unit": 0.0135, "Standard Messaging Operations": 0.0},
                "Premium": {"Premium Messaging Unit": 0.928},
            }
        },
        {
            "Standard|Standard Base Unit": "1/Hour",
            "Standard|Standard Messaging Operations": "1M",
            "Premium|Premium Messaging Unit": "1/Hour",
        },
        "Service Bus",
    ),
    "firewall": _service(
        {"global": {"Standard": {"Standard Deployment": 1.25, "Standard Data Processed": 0.016}}},
        {"Standard|Standard Deployment": "1 Hour", "Standard|Standard Data Processed": "1 GB"},
        "Azure Firewall",
    ),
    "functions": _service(
        {
            "eastus": {
                "Standard": {
                    "Standard Execution Time": 0.0,
                    "Standard Execution Time@400000": 1.6e-05,
                    "Standard Total Executions": 0.0,
                    "Standard Total Executions@100000": 2e-06,
                }
            }
        },
        {
            "Standard|Standard Execution Time": "1 GB Second",
            "Standard|Standard Total Executions": "10",
        },
        "Azure Functions",
    ),
    "aks": _service(
        {"eastus": {"Standard": {"Standard Uptime SLA": 0.1}}},
        {"Standard|Standard Uptime SLA": "1 Hour"},
        "Azure Kubernetes Service",
    ),
    "sql": _service(
        {
            "eastus": {
                "DB General Purpose Gen5": {"vcore": 0.152217},
                "DB General Purpose Storage": {"gb": 0.115},
            },
            "global": {"DB General Purpose License": {"vcore": 0.099966}},
        },
        {
            "DB General Purpose Gen5|vcore": "1 Hour",
            "DB General Purpose License|vcore": "1 Hour",
            "DB General Purpose Storage|gb": "1 GB/Month",
        },
        "Azure SQL Database",
    ),
    "acr": _service(
        {"eastus": {"Standard": {"Standard Registry Unit": 0.6666, "Data Stored": 0.1}}},
        {"Standard|Standard Registry Unit": "1/Day", "Standard|Data Stored": "1 GB/Month"},
        "Azure Container Registry",
    ),
}


@pytest.fixture
def table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    write_table("azure", SERVICES, read="2026-10-08", folder=tmp_path)
    monkeypatch.setattr(price_tables, "tables_dir", lambda: tmp_path)
    load_table.cache_clear()
    yield
    load_table.cache_clear()


def _price(
    service_id: str, sizing: dict[str, Any] | None = None, framed: str | None = "eastus"
) -> Price:
    ask = Ask(
        element_id="e1",
        name=service_id,
        provider="azure",
        service_id=service_id,
        sizing=dict(sizing or {}),
        framed_region=framed,
        default_region=COVERAGE.default_region,
        table=load_table("azure"),
        today="2026-10-08",
    )
    return COVERAGE.pricers[service_id](ask)


def test_units_and_tiers_read_as_the_api_states_them() -> None:
    assert measure("10K") == (10_000, "count")
    assert measure("1 GB/Month") == (1, "GB-month")
    assert measure("1/Day") == (1, "day")
    assert measure("100 Hours") == (100, "hour")
    assert measure("1M/Month") == (1_000_000, "count")
    with pytest.raises(PricingError):
        measure("1 Furlong")
    bands = [(0.0, 0.0), (100.0, 2.0), (200.0, 1.0)]
    assert tiered(bands, 50) == 0
    assert tiered(bands, 250) == pytest.approx(100 * 2.0 + 50 * 1.0)


@pytest.mark.usefixtures("table")
def test_a_vm_is_priced_by_size_os_count_and_hours() -> None:
    price = _price(
        "virtual-machine", {"size": "Standard_D2s_v5", "os": "Windows", "count": 2, "hours": 100}
    )
    assert price.monthly == pytest.approx(0.188 * 200)
    assert price.assumed == []
    (item,) = price.lines
    assert (item.kind, item.unit, item.quantity, item.rate) == ("fixed", "hours", 200, 0.188)
    assert "2 vCPU, 8 GiB" in price.rate
    assert price.hourly == pytest.approx(0.188 * 2)


@pytest.mark.usefixtures("table")
def test_what_the_sizing_does_not_say_is_a_default_listed_as_assumed() -> None:
    price = _price("virtual-machine", framed=None)
    assert price.monthly == pytest.approx(0.096 * HOURS)
    assert set(price.assumed) == {"size", "os", "count", "hours", "region"}
    assert price.sizing["region"] == "eastus"
    assert price.lines[0].assumed


@pytest.mark.usefixtures("table")
def test_the_framed_region_prices_and_a_global_meter_stands_in() -> None:
    assert _price("virtual-machine", {"size": "D2s_v5"}, framed="westeurope").monthly == (
        pytest.approx(0.1 * HOURS)
    )
    price = _price("firewalls", {"tier": "Standard"}, framed="westeurope")
    fixed, usage = price.lines
    assert (fixed.kind, fixed.amount) == ("fixed", pytest.approx(1.25 * HOURS))
    assert (usage.kind, usage.quantity, usage.assumed) == ("usage", 100, True)
    assert price.fixed == pytest.approx(912.5)
    assert price.usage == pytest.approx(1.6)
    assert price.monthly == pytest.approx(914.1)


@pytest.mark.usefixtures("table")
def test_storage_is_priced_tier_by_tier_in_the_published_unit() -> None:
    price = _price(
        "storage-accounts",
        {"storage_gb": 60_000, "write_operations_millions": 2, "read_operations_millions": 0},
    )
    stored, writes = price.lines
    assert stored.amount == pytest.approx(51_200 * 0.0208 + 8_800 * 0.019968)
    # 0.05 per 10K writes is 5.00 per million
    assert (writes.unit, writes.rate, writes.amount) == ("1M operations", 5.0, 10.0)
    assert {line.kind for line in price.lines} == {"usage"}
    assert price.assumed == ["tier", "redundancy"]


@pytest.mark.usefixtures("table")
def test_read_access_writes_bill_on_the_meter_of_the_redundancy_they_read_from() -> None:
    price = _price(
        "storage-accounts",
        {
            "redundancy": "RA-GZRS",
            "storage_gb": 100,
            "write_operations_millions": 1,
            "read_operations_millions": 1,
        },
    )
    stored, writes, reads = price.lines
    assert stored.amount == pytest.approx(100 * 0.05175)
    # no RA-GZRS write meter: GZRS's 0.1125 per 10K, 11.25 per million
    assert writes.rate == pytest.approx(11.25)
    # its own read meter where it has one
    assert reads.rate == pytest.approx(0.44)


@pytest.mark.usefixtures("table")
def test_a_vault_that_replicates_vms_is_priced_as_site_recovery() -> None:
    price = _price("recovery-services-vaults", {"protects": "Site Recovery", "instances": 6})
    (replicated,) = price.lines
    assert replicated.amount == pytest.approx(6 * 25.0)
    assert price.sizing["protects"] == "Site Recovery"
    assert "Site Recovery" in price.rate


@pytest.mark.usefixtures("table")
def test_the_functions_free_grant_is_the_meters_first_tier() -> None:
    price = _price(
        "function-apps", {"executions_millions": 3, "memory_mb": 1024, "duration_ms": 1000}
    )
    executions, seconds = price.lines
    assert executions.amount == pytest.approx((300_000 - 100_000) * 2e-06)
    assert seconds.quantity == pytest.approx(3_000_000)
    assert seconds.amount == pytest.approx((3_000_000 - 400_000) * 1.6e-05)
    assert price.fixed == 0


@pytest.mark.usefixtures("table")
def test_aks_adds_the_tier_fee_to_its_nodes() -> None:
    price = _price("kubernetes-services", {"tier": "Standard", "nodes": 2, "node_size": "D2s_v5"})
    fee, nodes = price.lines
    assert fee.amount == pytest.approx(0.1 * HOURS)
    assert nodes.quantity == 2 * HOURS
    assert price.monthly == pytest.approx(0.1 * HOURS + 2 * HOURS * 0.096)
    assert "node_os" in price.assumed


@pytest.mark.usefixtures("table")
def test_sql_database_bills_compute_the_global_license_and_storage() -> None:
    price = _price("sql-database", {"vcores": 2, "storage_gb": 100})
    compute, license_, storage = price.lines
    assert compute.amount == pytest.approx(2 * HOURS * 0.152217)
    assert license_.amount == pytest.approx(2 * HOURS * 0.099966)
    assert storage.amount == pytest.approx(100 * 0.115)
    without = _price("sql-database", {"vcores": 2, "storage_gb": 100, "license": "ahb"})
    assert len(without.lines) == 2


@pytest.mark.usefixtures("table")
def test_a_daily_fee_runs_for_the_month_and_storage_past_the_included() -> None:
    price = _price("container-registries", {"tier": "Standard", "storage_gb": 150})
    unit, extra = price.lines
    assert (unit.unit, unit.quantity) == ("days", pytest.approx(HOURS / 24))
    assert unit.amount == pytest.approx(0.6666 * HOURS / 24, abs=1e-3)
    assert (extra.quantity, extra.amount) == (50, pytest.approx(5.0))


@pytest.mark.usefixtures("table")
@pytest.mark.parametrize(
    ("service_id", "sizing", "says"),
    [
        ("virtual-machine", {"size": "D2s_v99"}, "has no size 'D2s_v99'"),
        ("virtual-machine", {"region": "marsnorth"}, "has no region 'marsnorth'"),
        ("virtual-machine", {"sizee": "D2s_v5"}, "not sizee"),
        ("virtual-machine", {"count": 0}, "must be 1"),
        ("virtual-machine", {"os": "Plan 9"}, "is not one of Linux, Windows"),
        ("storage-accounts", {"tier": "Warm"}, "is not one of Hot, Cool, Cold, Archive"),
        ("storage-accounts", {"storage_gb": -1}, "must be 0"),
        ("firewalls", {"tier": "Premium"}, "Azure Firewall Premium is not sold in eastus"),
    ],
)
def test_what_the_table_or_pricer_does_not_know_is_refused(
    service_id: str, sizing: dict[str, Any], says: str
) -> None:
    with pytest.raises(PricingError, match=says.replace("(", r"\(")):
        _price(service_id, sizing)


def test_the_shipped_table_prices_every_pricer_and_the_real_d2s_v5() -> None:
    load_table.cache_clear()
    try:
        for service_id in COVERAGE.pricers:
            price = _price(service_id, framed=None)
            assert price.monthly >= 0 and price.source.startswith("Azure Retail Prices API")
        price = _price("virtual-machine", {"size": "Standard_D2s_v5", "os": "Linux"})
        # the API's pay-as-you-go rate on 2026-10-08 (meter "D2s v5", East US);
        # a rebuild that moves it is checked against prices.azure.com and noted here
        assert price.lines[0].rate == 0.096
        assert price.monthly == pytest.approx(0.096 * HOURS)
    finally:
        load_table.cache_clear()


@pytest.mark.usefixtures("table")
def test_only_standard_service_bus_says_operations_are_free() -> None:
    """Premium bills messaging units, not operations: Standard's free
    allowance is not Premium's to claim."""
    premium = _price("azure-service-bus", {"tier": "Premium", "units": 1})
    assert premium.fixed == pytest.approx(0.928 * 730)
    assert "13M" not in premium.rate
    assert "13M" in _price("azure-service-bus", {"tier": "Standard"}).rate
