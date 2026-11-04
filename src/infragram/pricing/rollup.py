"""What a diagram costs, added up: every priced element, each frame's total, the diagram's.

It reads the prices already in the document (``attributes.price``: written
by ``--prices``, by ``--infracost``, or by hand), so it prices nothing
itself. A frame's total is every priced element inside it, however deep;
amounts in different currencies are kept apart, never converted.

It reads three ways: the text report, CSV (``costs --csv``) and one JSON
object (:func:`rollup_json`, ``costs --json``).
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

from ..projects import CloudProject
from . import walk

__all__ = ["CostLine", "FrameCost", "Rollup", "rollup", "rollup_json"]


class CostLine(BaseModel):
    """One priced element."""

    element_id: str
    name: str
    #: ``provider:service``, or empty for an element drawn without a component.
    component: str = ""
    #: The frames around it, outermost first, by caption.
    frames: tuple[str, ...] = ()
    monthly: float
    hourly: float = 0.0
    currency: str = "USD"
    source: str = ""
    assumed: tuple[str, ...] = ()
    #: What was priced, in words, and the part of the month's price that is
    #: resources running (fixed) and what they serve (usage).
    rate: str = ""
    fixed: float = 0.0
    usage: float = 0.0
    #: The billed lines it adds up from (``Price.lines``).
    parts: list[dict[str, Any]] = Field(default_factory=list)


class FrameCost(BaseModel):
    """What everything priced inside one frame costs."""

    frame_id: str
    #: The frame and the frames around it, outermost first, by caption.
    path: tuple[str, ...]
    #: currency -> a month.
    monthly: dict[str, float] = Field(default_factory=dict)
    count: int = 0


class Rollup(BaseModel):
    """Every priced element, each frame's total and the diagram's."""

    title: str
    lines: list[CostLine] = Field(default_factory=list)
    frames: list[FrameCost] = Field(default_factory=list)
    #: currency -> the diagram's total a month.
    totals: dict[str, float] = Field(default_factory=dict)
    #: What a breakdown priced that the diagram does not draw: (address, a month, currency).
    undrawn: list[tuple[str, float, str]] = Field(default_factory=list)
    #: currency -> the part of the total that is fixed, and usage.
    fixed: dict[str, float] = Field(default_factory=dict)
    usage: dict[str, float] = Field(default_factory=dict)
    #: The components that cost nothing on their own: (element id, caption, why).
    free: list[tuple[str, str, str]] = Field(default_factory=list)
    #: The cloud components not priced: (element id, caption, why).
    unpriced: list[tuple[str, str, str]] = Field(default_factory=list)

    def report(self) -> str:
        """The rollup as the ``costs`` command prints it."""
        if not self.lines:
            return "\n".join(
                [
                    f"COSTS    {self.title}: nothing is priced. Its AWS, Azure and Google Cloud "
                    "components are priced from the shipped tables unless --no-prices; "
                    "--infracost FILE prices what an Infracost breakdown of its Terraform covers"
                ]
                + self._others()
            )
        undrawn = (
            f", {_count(len(self.undrawn), 'resource')} priced but not drawn"
            if self.undrawn
            else ""
        )
        split = (
            f" ({_amounts(self.fixed)} fixed, {_amounts(self.usage)} usage)"
            if any(self.usage.values())
            else ""
        )
        others = "".join(
            f", {len(group)} {label}"
            for group, label in ((self.free, "free"), (self.unpriced, "not priced"))
            if group
        )
        out = [
            f"COSTS    {self.title}: about {_amounts(self.totals)} a month{split}, "
            f"{_count(len(self.lines), 'component')} priced{undrawn}{others}"
        ]
        for frame in self.frames:
            indent = "  " * (len(frame.path) - 1)
            out.append(
                f"FRAME    {indent}{frame.path[-1]}: {_amounts(frame.monthly)} ({frame.count})"
            )
        for line in sorted(self.lines, key=lambda line: -line.monthly):
            where = " > ".join(line.frames) or "(outside every frame)"
            assumed = f"; assumed {', '.join(line.assumed)}" if line.assumed else ""
            what = f"{line.rate}; " if line.rate else ""
            out.append(
                f"ITEM     {line.name}: {_money(line.monthly, line.currency)} "
                f"[{line.component or 'no component'}] in {where} ({what}{line.source}{assumed})"
            )
        for address, monthly, currency in self.undrawn:
            out.append(f"UNDRAWN  {address}: {_money(monthly, currency)} (priced, not drawn)")
        return "\n".join(out + self._others())

    def _others(self) -> list[str]:
        return [f"FREE     {name}: {why}" for _, name, why in self.free] + [
            f"UNPRICED {name}: {why}" for _, name, why in self.unpriced
        ]

    def csv(self) -> str:
        """One row per priced element, per frame and for the diagram."""
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            [
                "kind",
                "id",
                "name",
                "component",
                "frames",
                "monthly",
                "hourly",
                "currency",
                "source",
                "assumed",
            ]
        )
        for line in self.lines:
            writer.writerow(
                [
                    "component",
                    line.element_id,
                    line.name,
                    line.component,
                    " > ".join(line.frames),
                    f"{line.monthly:.2f}",
                    f"{line.hourly:.4f}",
                    line.currency,
                    line.source,
                    "; ".join(line.assumed),
                ]
            )
        for frame in self.frames:
            for currency, monthly in frame.monthly.items():
                writer.writerow(
                    [
                        "frame",
                        frame.frame_id,
                        frame.path[-1],
                        "",
                        " > ".join(frame.path[:-1]),
                        f"{monthly:.2f}",
                        "",
                        currency,
                        "",
                        "",
                    ]
                )
        for address, monthly, currency in self.undrawn:
            writer.writerow(
                ["undrawn", address, address, "", "", f"{monthly:.2f}", "", currency, "", ""]
            )
        for currency, monthly in self.totals.items():
            writer.writerow(
                ["diagram", "", self.title, "", "", f"{monthly:.2f}", "", currency, "", ""]
            )
        return buffer.getvalue()


def _count(number: int, thing: str) -> str:
    return f"{number} {thing}{'' if number == 1 else 's'}"


def _money(amount: float, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def _amounts(totals: dict[str, float]) -> str:
    return " + ".join(_money(amount, currency) for currency, amount in totals.items()) or "0"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def rollup(project: CloudProject, undrawn: Iterable[tuple[str, float, str]] = ()) -> Rollup:
    """Add up the prices *project* carries."""
    result = Rollup(title=project.title or project.slug, undrawn=list(undrawn))
    frames: dict[str, FrameCost] = {}
    for element, ancestors in walk(project.topology):
        if element is project.topology:
            continue
        around = [frame for frame in ancestors if frame is not project.topology]
        if element.children and element.id not in frames:
            frames[element.id] = FrameCost(
                frame_id=element.id, path=(*(frame.name for frame in around), element.name)
            )
        price = element.attributes.get("price")
        monthly = _number(price.get("monthly")) if isinstance(price, dict) else None
        if not isinstance(price, dict) or monthly is None:
            why = element.attributes.get("unpriced")
            if isinstance(why, str) and why:
                if why.startswith("free: "):
                    result.free.append((element.id, element.name, why.removeprefix("free: ")))
                else:
                    result.unpriced.append((element.id, element.name, why))
            continue
        currency = str(price.get("currency") or "USD")
        component = element.component
        result.lines.append(
            CostLine(
                element_id=element.id,
                name=element.name,
                component=f"{component.provider}:{component.service_id}" if component else "",
                frames=tuple(frame.name for frame in around),
                monthly=round(monthly, 2),
                hourly=_number(price.get("hourly")) or 0.0,
                currency=currency,
                source=str(price.get("source") or ""),
                assumed=tuple(str(key) for key in price.get("assumed") or ()),
                rate=str(price.get("rate") or ""),
                fixed=_number(price.get("fixed")) or 0.0,
                usage=_number(price.get("usage")) or 0.0,
                parts=[part for part in price.get("lines") or () if isinstance(part, dict)],
            )
        )
        result.totals[currency] = round(result.totals.get(currency, 0.0) + monthly, 2)
        # a price written before lines existed is all fixed
        usage = _number(price.get("usage")) or 0.0
        result.usage[currency] = round(result.usage.get(currency, 0.0) + usage, 2)
        result.fixed[currency] = round(result.fixed.get(currency, 0.0) + monthly - usage, 2)
        for frame in around:
            cost = frames[frame.id]
            cost.monthly[currency] = round(cost.monthly.get(currency, 0.0) + monthly, 2)
            cost.count += 1
    for _, monthly, currency in result.undrawn:
        result.totals[currency] = round(result.totals.get(currency, 0.0) + monthly, 2)
    result.frames = [frame for frame in frames.values() if frame.count]
    return result


def rollup_json(result: Rollup, notes: Iterable[str] = ()) -> dict[str, Any]:
    """The rollup as one JSON-ready object (``costs --json``): the diagram's
    total a month and each frame's, keyed by currency because currencies are
    never converted; every priced component with where its price came from and
    what it assumed; what a breakdown priced that the diagram does not draw;
    the fixed and usage parts of the total; what is free and what is not
    priced, each with why; and *notes*, what could not be priced. Frames keep document order, which
    is the tree ``level`` and ``path`` describe; components come most
    expensive first, as the text report lists them, ties by id."""
    return {
        "title": result.title,
        "priced": len(result.lines),
        "totals": dict(sorted(result.totals.items())),
        "fixed": dict(sorted(result.fixed.items())),
        "usage": dict(sorted(result.usage.items())),
        "frames": [
            {
                "frame_id": frame.frame_id,
                "name": frame.path[-1],
                "path": list(frame.path),
                "level": len(frame.path) - 1,
                "monthly": dict(sorted(frame.monthly.items())),
                "count": frame.count,
            }
            for frame in result.frames
        ],
        "items": [
            {**line.model_dump(mode="json"), "assumed": sorted(line.assumed)}
            for line in sorted(result.lines, key=lambda line: (-line.monthly, line.element_id))
        ],
        "undrawn": [
            {"address": address, "monthly": monthly, "currency": currency}
            for address, monthly, currency in sorted(result.undrawn)
        ],
        "free": [
            {"element_id": element_id, "name": name, "why": why}
            for element_id, name, why in result.free
        ],
        "unpriced": [
            {"element_id": element_id, "name": name, "why": why}
            for element_id, name, why in result.unpriced
        ],
        "notes": list(notes),
    }
