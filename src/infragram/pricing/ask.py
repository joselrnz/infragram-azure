"""What a pricer is asked, how it answers, and what a cloud covers.

A pricer takes an :class:`Ask` -- the element, its sizing, the region its
frames put it in, the cloud's price table -- and answers a
:class:`~infragram.pricing.Price` built from lines (:func:`priced`): each
line one thing billed (instance hours, storage, requests, data out), its
quantity, rate and amount, fixed or usage, and whether its quantity was
assumed. A value the element's sizing does not state is taken from the
pricer's default through :meth:`Ask.take` and listed as assumed.

Each cloud module states its :class:`Coverage`: for every component its
library draws, a pricer, or why it is free, or why it is not priced.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..models.topology import TopologyElement
from . import Price, PriceLine, PricingError
from .tables import Table

__all__ = ["HOURS", "MAX_COUNT", "MAX_HOURS", "Ask", "Coverage", "Pricer", "line", "priced"]

#: The hours in the month every price is for: 365 days x 24 / 12.
HOURS = 730
#: The most hours a month has: 31 days x 24.
MAX_HOURS = 744
#: The most copies of one element a sizing may ask for.
MAX_COUNT = 100_000

_YES_NO = {"yes": True, "true": True, "no": False, "false": False}

_MISSING = object()


class Ask(BaseModel):
    """One element to price."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    element_id: str
    name: str
    provider: str
    service_id: str
    sizing: dict[str, Any] = Field(default_factory=dict)
    #: The region the frames around the element put it in, else None.
    framed_region: str | None = None
    default_region: str
    table: Table
    today: str
    assumed: list[str] = Field(default_factory=list)
    taken: set[str] = Field(default_factory=set)

    def take(
        self,
        key: str,
        default: Any = _MISSING,
        *,
        kind: type | tuple[type, ...] = (str, int, float),
        choices: Iterable[str] | None = None,
        low: float | None = None,
        high: float | None = None,
    ) -> Any:
        """The sizing's *key*, else *default* (listed as assumed). A number
        is checked against *low* and *high*; text against *choices*,
        matched without regard to case; ``kind=bool`` takes true/false or
        the words yes/no."""
        self.taken.add(key)
        value = self.sizing.get(key)
        if value in (None, ""):
            if default is _MISSING:
                raise PricingError(f"{self.name}: sizing must say {key}")
            self.assumed.append(key)
            return default
        if kind is bool:
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.strip().lower() in _YES_NO:
                return _YES_NO[value.strip().lower()]
            raise PricingError(f"{self.name}: {key} {value!r} is not yes or no")
        if isinstance(value, bool) or not isinstance(value, kind):
            raise PricingError(f"{self.name}: {key} {value!r} is not the right kind of value")
        if isinstance(value, (int, float)) and (
            (low is not None and value < low) or (high is not None and value > high)
        ):
            raise PricingError(f"{self.name}: {key} must be {low} to {high}, not {value}")
        if choices is not None:
            options = list(choices)
            match = next((c for c in options if c.lower() == str(value).strip().lower()), None)
            if match is None:
                raise PricingError(
                    f"{self.name}: {key} {value!r} is not one of {', '.join(options[:12])}"
                    + (" ..." if len(options) > 12 else "")
                )
            return match
        return value

    # -- the sizes every cloud reads the same way

    def count(self, key: str = "count", default: int = 1) -> int:
        """How many: a whole number from 1 to :data:`MAX_COUNT` (3.0 counts as 3)."""
        value = self.take(key, default, kind=(int, float), low=1, high=MAX_COUNT)
        if not float(value).is_integer():
            raise PricingError(f"{self.name}: {key} must be a whole number, not {value}")
        return int(value)

    def hours(self) -> float:
        """The hours a month it runs: 1 to :data:`MAX_HOURS`, else :data:`HOURS`."""
        return float(self.take("hours", HOURS, kind=(int, float), low=1, high=MAX_HOURS))

    def amount(
        self, key: str, default: float, *, low: float = 0, high: float | None = None
    ) -> float:
        """A quantity (GB, requests, ...): a number from *low* (0) up to *high*."""
        return float(self.take(key, default, kind=(int, float), low=low, high=high))

    def was_assumed(self, *keys: str) -> bool:
        """Whether any of *keys* fell back to the pricer's default."""
        return any(key in self.assumed for key in keys)

    def region(self) -> str:
        """The sizing's region, else the frames', else the cloud's first;
        assumed only when neither the sizing nor a frame says."""
        self.taken.add("region")
        given = self.sizing.get("region")
        if given not in (None, ""):
            return str(given).strip()
        if self.framed_region:
            return self.framed_region
        self.assumed.append("region")
        return self.default_region

    def finish(self) -> None:
        """Refuse sizing keys the pricer does not read: a typo is never
        priced silently as a default."""
        unknown = sorted(set(self.sizing) - self.taken)
        if unknown:
            raise PricingError(
                f"{self.name}: sizing for this service takes {', '.join(sorted(self.taken))}, "
                f"not {', '.join(unknown)}"
            )


Pricer = Callable[[Ask], Price]


class Coverage(BaseModel):
    """Every component one cloud's library draws: priced, free, or not priced and why."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    cloud: str
    default_region: str
    region_of: Callable[[tuple[TopologyElement, ...]], str | None]
    #: service id -> its pricer.
    pricers: dict[str, Pricer] = Field(default_factory=dict)
    #: service id -> why it costs nothing on its own ("IAM roles are free").
    free: dict[str, str] = Field(default_factory=dict)
    #: service id -> why it is not priced ("billed per model token; no fixed size").
    unpriced: dict[str, str] = Field(default_factory=dict)


def line(
    label: str,
    quantity: float,
    unit: str,
    rate: float,
    *,
    kind: str = "fixed",
    assumed: bool = False,
) -> PriceLine:
    """One billed thing: *quantity* *unit* at *rate* each."""
    return PriceLine(
        label=label,
        quantity=quantity,
        unit=unit,
        rate=rate,
        amount=round(quantity * rate, 4),
        kind=kind,
        assumed=assumed,
    )


def priced(
    ask: Ask,
    lines: list[PriceLine],
    *,
    sizing: dict[str, Any],
    rate: str,
    source: str,
    published: str = "",
) -> Price:
    """The price *lines* add up to, with the sizing and assumptions behind it."""
    ask.finish()
    fixed = round(sum(item.amount for item in lines if item.kind == "fixed"), 2)
    usage = round(sum(item.amount for item in lines if item.kind == "usage"), 2)
    hours = sizing.get("hours", HOURS) or HOURS
    # the fixed part by the hour it runs: a resource billed by the day or the
    # month has an hourly cost too
    hourly = sum(item.amount for item in lines if item.kind == "fixed")
    return Price(
        monthly=round(fixed + usage, 2),
        hourly=round(hourly / float(hours), 6) if hourly else 0.0,
        currency=ask.table.currency,
        sizing=sizing,
        assumed=list(dict.fromkeys(ask.assumed)),
        rate=rate,
        source=source,
        published=published or ask.table.read,
        priced=ask.table.read,
        lines=lines,
        fixed=fixed,
        usage=usage,
    )
