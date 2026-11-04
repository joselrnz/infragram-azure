"""The price tables an export prices from with no network: one per cloud.

A table is the cloud's own published on-demand list prices, read from its
public price source by ``scripts/build/price-tables.py`` and shipped in the
skill's assets (``assets/prices/<cloud>.json``). Each service's rates are
nested by the keys it names, outermost first::

    {
      "schema": 1,
      "cloud": "aws",
      "currency": "USD",
      "read": "2026-10-08",
      "services": {
        "ec2": {
          "title": "EC2 on-demand",
          "source": "AWS Price List API (pricing.us-east-1.amazonaws.com)",
          "published": "2026-10-01",
          "unit": "hour",
          "keys": ["region", "os", "instance_type"],
          "rates": {"us-east-1": {"Linux": {"t3.micro": 0.0104}}},
          "info": {"instance_type": {"t3.micro": "2 vCPU, 1 GiB"}}
        }
      }
    }

``rates`` holds numbers at the depth of ``keys``; ``info`` is optional
words about a key's values, for the card ("2 vCPU, 1 GiB"). A rate is in
the table's currency per ``unit``.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..paths import skill_assets
from . import PricingError

__all__ = ["SCHEMA", "Service", "Table", "load_table", "tables_dir"]

SCHEMA = 1


def tables_dir() -> Path:
    return skill_assets() / "prices"


class Service(BaseModel):
    """One service's rates in a table."""

    title: str
    source: str
    published: str = ""
    unit: str
    keys: list[str]
    rates: dict[str, Any]
    info: dict[str, dict[str, str]] = Field(default_factory=dict)

    def rate(self, *values: str) -> float:
        """The rate at *values*, one per key; a value the table does not
        hold is refused with the nearest choices it does."""
        if len(values) != len(self.keys):
            raise PricingError(
                f"{self.title} is priced by {', '.join(self.keys)}, not {len(values)} values"
            )
        node: Any = self.rates
        for key, value in zip(self.keys, values, strict=True):
            if not isinstance(node, dict) or value not in node:
                choices = sorted(node) if isinstance(node, dict) else []
                near = [
                    choice for choice in choices if choice.lower().startswith(value[:2].lower())
                ]
                shown = ", ".join((near or choices)[:8])
                more = " ..." if len(near or choices) > 8 else ""
                raise PricingError(
                    f"{self.title} has no {key} {value!r}"
                    + (f"; it has {shown}{more}" if shown else "")
                )
            node = node[value]
        if isinstance(node, bool) or not isinstance(node, (int, float)):
            raise PricingError(f"{self.title}: the table holds no rate at {', '.join(values)}")
        return float(node)

    def choices(self, *values: str) -> list[str]:
        """The values the next key takes after *values*."""
        node: Any = self.rates
        for value in values:
            node = node.get(value, {}) if isinstance(node, dict) else {}
        return sorted(node) if isinstance(node, dict) else []

    def describe(self, key: str, value: str) -> str:
        return self.info.get(key, {}).get(value, "")


class Table(BaseModel):
    """One cloud's price table."""

    schema_: int = Field(alias="schema")
    cloud: str
    currency: str = "USD"
    #: The day the table was read from the cloud's sources.
    read: str
    services: dict[str, Service] = Field(default_factory=dict)

    def service(self, name: str) -> Service:
        found = self.services.get(name)
        if found is None:
            raise PricingError(
                f"the {self.cloud} price table holds no {name!r}; rebuild it with "
                f"scripts/build/price-tables.py {self.cloud}"
            )
        return found


@cache
def load_table(cloud: str, folder: Path | None = None) -> Table:
    """The shipped table for *cloud* (``aws``, ``azure``, ``gcp``)."""
    path = (folder or tables_dir()) / f"{cloud}.json"
    if not path.is_file():
        raise PricingError(
            f"no {cloud} price table is shipped yet ({path.name}); build it with "
            f"scripts/build/price-tables.py {cloud}"
        )
    try:
        table = Table.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, OSError) as error:
        raise PricingError(f"the {cloud} price table cannot be read: {error}") from error
    if table.schema_ != SCHEMA or table.cloud != cloud:
        raise PricingError(f"{path.name} is not a schema-{SCHEMA} {cloud} price table")
    return table
