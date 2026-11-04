"""What a diagram's components cost: an approximate month, line by line.

Every component AWS, Azure and Google Cloud draw is priced, free, or listed
as not priced and why (each cloud's :class:`~infragram.pricing.ask.Coverage`).
A priced component is priced from its cloud's on-demand list prices, by
default from the price table shipped with the skill (no network; the table
says the day it was read), or with ``--prices live`` from the cloud's
public source fetched now where a live pricer exists (EC2).

A price is the sum of its lines: each a thing billed (instance hours,
storage, requests, data out), its quantity, rate and amount, **fixed** (a
resource running all month) or **usage** (what it serves), and whether its
quantity was assumed. What the element does not say about its size is
priced as the pricer's default and marked assumed; ``attributes.sizing``
says otherwise (``Element.sizing(...)`` in a diagram file). The price is
written into the element's attributes (``attributes.price``); the page shows
it on the card and adds it up in its Cost tab, and stays offline.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Iterator
from typing import Any

from pydantic import BaseModel, Field

from ..models.topology import TopologyElement
from ..projects import CloudProject

__all__ = [
    "PRICERS",
    "SOURCES",
    "Price",
    "PriceLine",
    "PricingError",
    "PricingResult",
    "price_project",
    "walk",
]

#: Where prices come from: the shipped table (no network), or the cloud's
#: public source fetched now, where a live pricer exists.
SOURCES = ("table", "live")

#: Fetches a URL's body: the network in an export, a table in a test.
Fetch = Callable[[str], bytes]


class PricingError(RuntimeError):
    """A component that could not be priced, and why."""


class PriceLine(BaseModel):
    """One thing billed: instance hours, storage, requests, data out."""

    label: str
    quantity: float
    #: ``hours``, ``GB-month``, ``GB``, ``1M requests``, ...
    unit: str
    #: Currency per unit.
    rate: float
    #: quantity x rate, for the month.
    amount: float
    #: ``fixed``: a resource billed all month; ``usage``: what it serves.
    kind: str = "fixed"
    #: The quantity is a default, not what the element said.
    assumed: bool = False


class Price(BaseModel):
    """What one element costs, and what it was priced as."""

    #: The whole element, for the month: its lines added up.
    monthly: float
    hourly: float
    currency: str = "USD"
    #: What was priced: instance type, region, operating system, count, hours.
    sizing: dict[str, Any]
    #: The sizing keys the element did not state, and a default stood in for.
    assumed: list[str] = Field(default_factory=list)
    #: The rate priced, in words: ``EC2 on-demand, Linux, shared tenancy``.
    rate: str
    #: Where the price came from, and the date that source published it.
    source: str
    published: str = ""
    #: The day the export priced it, or the day the table it priced from was read.
    priced: str
    #: What it adds up from; empty for a price written before lines existed.
    lines: list[PriceLine] = Field(default_factory=list)
    fixed: float = 0.0
    usage: float = 0.0
    #: Who wrote it: ``table`` or ``live`` for Infragram's own pricing, which
    #: an export replaces; empty for a price written by hand or by Infracost,
    #: which it never touches.
    origin: str = ""


class PricingResult(BaseModel):
    """What an export priced, and what it could not."""

    priced: list[tuple[str, Price]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    #: The cloud components nothing prices yet: (element id, its caption, provider:service).
    unpriced: list[tuple[str, str, str]] = Field(default_factory=list)
    #: The components that cost nothing on their own: (element id, caption, why).
    free: list[tuple[str, str, str]] = Field(default_factory=list)

    @property
    def monthly(self) -> float:
        return round(sum(price.monthly for _, price in self.priced), 2)


def walk(
    element: TopologyElement, ancestors: tuple[TopologyElement, ...] = ()
) -> Iterator[tuple[TopologyElement, tuple[TopologyElement, ...]]]:
    """Every element under *element*, each with the frames around it, outermost first."""
    yield element, ancestors
    for child in element.children:
        yield from walk(child, (*ancestors, element))


def _live() -> dict[tuple[str, str], Callable[..., Price]]:
    from . import aws

    return {("aws", "ec2"): aws.price_ec2}


#: (provider, service) -> the function that prices it from the cloud's
#: source fetched now (``--prices live``).
PRICERS: dict[tuple[str, str], Callable[..., Price]] = _live()
#: Libraries with no vendor price to read: never listed as not priced.
_UNPRICED_LIBRARIES = frozenset({"infragram", "onprem"})


#: The source the EC2 pricer wrote before prices said who wrote them.
_EARLIER_LIVE = "AWS price list (aws.amazon.com/ec2/pricing)"


def _written_by_us(price: Any) -> bool:
    return isinstance(price, dict) and (
        price.get("origin") in SOURCES or price.get("source") == _EARLIER_LIVE
    )


def coverages() -> dict[str, Any]:
    """provider -> its :class:`~infragram.pricing.ask.Coverage`."""
    from . import aws, azure, gcp

    return {module.COVERAGE.cloud: module.COVERAGE for module in (aws, azure, gcp)}


def price_project(
    project: CloudProject,
    *,
    source: str = "table",
    fetch: Fetch | None = None,
    today: str | None = None,
) -> PricingResult:
    """Price every component *project* draws, writing each price into its
    element's attributes (``price``; ``unpriced``, the reason, where it
    cannot be). A price an earlier export wrote is replaced or removed; a
    price written by hand or by Infracost is kept as it is, and counted.
    *source* is ``table`` (the shipped table, no network) or ``live``."""
    from .ask import Ask
    from .fetch import cached_fetch
    from .tables import load_table

    if source not in SOURCES:
        raise PricingError(f"prices come from {' or '.join(SOURCES)}, not {source!r}")
    fetch = fetch or cached_fetch
    today = today or datetime.date.today().isoformat()
    covered = coverages()
    result = PricingResult()
    for element, ancestors in walk(project.topology):
        component = element.component
        element.attributes.pop("unpriced", None)
        written = element.attributes.get("price")
        if written is not None and not _written_by_us(written):
            # the author's own price, or Infracost's: never replaced, and
            # added up by the rollup as it stands
            continue
        if component is None:
            element.attributes.pop("price", None)
            continue
        key = (component.provider, component.service_id)
        coverage = covered.get(component.provider)
        sizing = element.attributes.get("sizing")
        if sizing is not None and not isinstance(sizing, dict):
            element.attributes.pop("price", None)
            result.notes.append(
                f"{element.name} ({element.id}): not priced: sizing must be an object of "
                f"values, not {type(sizing).__name__}"
            )
            continue
        billed_by = (sizing or {}).get("billed_by")
        if billed_by:
            # an app on an App Service plan bills through the plan, which is
            # priced on its own card: priced here too, it is counted twice
            why = f"billed through {billed_by}"
            element.attributes.pop("price", None)
            element.attributes["unpriced"] = f"free: {why}"
            result.free.append((element.id, element.name, why))
            continue
        if coverage is not None and component.service_id in coverage.free:
            why = coverage.free[component.service_id]
            element.attributes.pop("price", None)
            element.attributes["unpriced"] = f"free: {why}"
            result.free.append((element.id, element.name, why))
            continue
        live = PRICERS.get(key) if source == "live" else None
        pricer = coverage.pricers.get(component.service_id) if coverage else None
        if live is None and pricer is None:
            element.attributes.pop("price", None)
            if component.provider not in _UNPRICED_LIBRARIES:
                why = (
                    coverage.unpriced.get(component.service_id, "")
                    if coverage is not None
                    else f"Infragram prices AWS, Azure and Google Cloud, not {component.provider}"
                )
                element.attributes["unpriced"] = why or "not priced yet"
                result.unpriced.append(
                    (element.id, element.name, f"{component.provider}:{component.service_id}")
                )
            continue
        try:
            if live is not None:
                price = live(sizing or {}, ancestors, fetch=fetch, today=today)
            else:
                assert coverage is not None and pricer is not None
                ask = Ask(
                    element_id=element.id,
                    name=element.name,
                    provider=component.provider,
                    service_id=component.service_id,
                    sizing=dict(sizing or {}),
                    framed_region=coverage.region_of(ancestors),
                    default_region=coverage.default_region,
                    table=load_table(coverage.cloud),
                    today=today,
                )
                price = pricer(ask)
        except PricingError as error:
            element.attributes.pop("price", None)
            element.attributes["unpriced"] = str(error)
            result.notes.append(f"{element.name} ({element.id}): not priced: {error}")
            continue
        price.origin = source if live is not None else "table"
        unused = element.attributes.get("unused")
        if isinstance(unused, dict) and unused.get("bills") == "disks" and price.monthly:
            # A deallocated VM bills only its disks, which are cards of their
            # own: its compute costs nothing now, and what it would cost
            # started is kept for the inventory.
            unused["running_monthly"] = price.monthly
            price = price.model_copy(
                update={
                    "monthly": 0.0,
                    "hourly": 0.0,
                    "fixed": 0.0,
                    "usage": 0.0,
                    "lines": [],
                    "rate": f"Deallocated, compute not billed (started: {price.rate})",
                }
            )
        element.attributes["price"] = price.model_dump()
        result.priced.append((element.id, price))
    return result
