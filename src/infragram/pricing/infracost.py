"""Prices from an Infracost breakdown, joined to the diagram by Terraform address.

``infracost breakdown --path <folder> --format json`` prices every resource
of a Terraform configuration (it needs the user's Infracost key, or their own
self-hosted pricing endpoint; Infragram never calls it). ``--infracost
FILE`` reads that JSON and writes each resource's price into the element
drawn from it: an element names the resources it was drawn from in its
table's ``Resource`` rows, which ``import:terraform`` writes, and one drawn
from several is priced at their sum. What the breakdown prices and the
diagram does not draw is kept, so the total stays the configuration's.
"""

from __future__ import annotations

import datetime
import json
import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..models.topology import TopologyElement
from ..projects import CloudProject
from . import Price, walk

__all__ = ["Breakdown", "InfracostResult", "addresses_of", "apply_breakdown", "read_breakdown"]


class Breakdown(BaseModel):
    """What one Infracost breakdown prices: address -> (a month, an hour, resource type)."""

    source: str
    currency: str = "USD"
    resources: dict[str, tuple[float, float, str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class InfracostResult(BaseModel):
    """What the join priced, and what it could not place."""

    priced: list[tuple[str, Price]] = Field(default_factory=list)
    #: Priced in the breakdown, drawn nowhere: (address, a month, currency).
    undrawn: list[tuple[str, float, str]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _amount(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0  # usage-based, and no usage given: Infracost writes null
    return number if math.isfinite(number) else 0.0


def read_breakdown(path: Path) -> Breakdown:
    """The resources an ``infracost breakdown --format json`` file prices."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"{path}: not an Infracost breakdown ({error})") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("projects"), list):
        raise ValueError(f"{path}: not an Infracost breakdown (no projects)")
    breakdown = Breakdown(source=path.name, currency=str(payload.get("currency") or "USD"))
    for project in payload["projects"]:
        resources = ((project or {}).get("breakdown") or {}).get("resources") or []
        for resource in resources:
            if not isinstance(resource, dict) or not resource.get("name"):
                continue
            address = str(resource["name"])
            if address in breakdown.resources:
                breakdown.notes.append(f"{address} is priced in two projects; the first is kept")
                continue
            breakdown.resources[address] = (
                _amount(resource.get("monthlyCost")),
                _amount(resource.get("hourlyCost")),
                str(resource.get("resourceType") or ""),
            )
    return breakdown


def addresses_of(element: TopologyElement) -> list[str]:
    """The Terraform addresses an element was drawn from: its table's ``Resource`` rows."""
    table = element.attributes.get("table")
    if not isinstance(table, dict):
        return []
    rows = table.get("rows") or []
    return [
        str(row[1])
        for row in rows
        if isinstance(row, (list, tuple)) and len(row) >= 2 and row[0] == "Resource"
    ]


def apply_breakdown(
    project: CloudProject, breakdown: Breakdown, *, today: str | None = None
) -> InfracostResult:
    """Write the breakdown's prices into the elements drawn from its resources."""
    today = today or datetime.date.today().isoformat()
    result = InfracostResult(notes=list(breakdown.notes))
    placed: set[str] = set()
    for element, _ in walk(project.topology):
        matched = [address for address in addresses_of(element) if address in breakdown.resources]
        if not matched:
            continue
        placed.update(matched)
        monthly = sum(breakdown.resources[address][0] for address in matched)
        hourly = sum(breakdown.resources[address][1] for address in matched)
        types = sorted({breakdown.resources[address][2] for address in matched} - {""})
        price = Price(
            monthly=round(monthly, 2),
            hourly=round(hourly, 4),
            currency=breakdown.currency,
            sizing={"resources": ", ".join(matched)},
            rate=f"Infracost, {', '.join(types)}" if types else "Infracost",
            source=f"Infracost breakdown {breakdown.source}",
            priced=today,
        )
        element.attributes["price"] = price.model_dump()
        result.priced.append((element.id, price))
    for address, (monthly, _, _) in sorted(breakdown.resources.items()):
        if address not in placed and monthly:
            result.undrawn.append((address, round(monthly, 2), breakdown.currency))
    if breakdown.resources and not placed:
        result.notes.append(
            "no element names a resource the breakdown prices: an element is joined by the "
            "Resource rows import:terraform writes in its table"
        )
    return result
