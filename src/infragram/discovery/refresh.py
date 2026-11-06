"""A diagram redrawn from a new read of Azure, with the reader's work kept.

``export:azure --refresh`` draws the estate again and gives the new picture
what the reader did to the old one: every ``editor_*`` attribute an element
carried (where it was moved to, the size a frame was given, a style, a label
moved by hand) goes to the element that stands for the same resource now.
What appeared since is placed by the layout, as on a first read.

What changed between the two reads is written on the new document: an
element added or changed carries ``refresh`` (its status and, for a change,
the fields that differ), and the topology's root carries the whole account,
the resources removed included, since a removed resource has no element left
to carry it. The editor lights it as a lens, and the command prints it.

Two reads compare resource by resource: what Azure Resource Graph returned
for each, its ARM id the key. With no earlier snapshot, only the earlier
diagram is known; added and removed still show, by the Resource IDs its cards
carry, but nothing can be said to have changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models.topology import TopologyElement
from ..projects import CloudProject

__all__ = ["Refresh", "carry_layout", "compare", "mark"]

#: The fields of a resource whose difference is a change. Properties are
#: compared one key down, so a change names what moved ("properties.sku").
_FIELDS = ("name", "type", "kind", "location", "sku", "tags", "managedBy", "properties")
#: Properties Azure rewrites on its own, which are no change the reader made.
_RESTLESS = frozenset(
    {
        "provisioningstate",
        "etag",
        "resourceguid",
        "timecreated",
        "createdtime",
        "creationtime",
        "lastmodifiedtime",
        "lastmodifiedat",
        "changedtime",
        "statustimestamp",
    }
)


def _rid(element: TopologyElement) -> str | None:
    """The ARM id a card was drawn for, from its details table."""
    rows = (element.attributes.get("table") or {}).get("rows") or []
    for row in rows:
        if isinstance(row, (list, tuple)) and len(row) >= 2 and row[0] == "Resource ID":
            return str(row[1]).lower()
    return None


def _key(element: TopologyElement) -> tuple[str, str]:
    rid = _rid(element)
    return ("resource", rid) if rid else ("element", element.id)


def carry_layout(previous: CloudProject, project: CloudProject) -> int:
    """Give each element of *project* the editor attributes of its earlier
    self in *previous*, matched by resource and else by element id. Returns
    how many elements got something back."""
    earlier: dict[tuple[str, str], TopologyElement] = {}
    for element in previous.topology.walk():
        earlier.setdefault(_key(element), element)
        earlier.setdefault(("element", element.id), element)
    kept = 0
    for element in project.topology.walk():
        match = earlier.get(_key(element)) or earlier.get(("element", element.id))
        if match is None:
            continue
        carried = {
            key: value for key, value in match.attributes.items() if key.startswith("editor_")
        }
        if carried:
            element.attributes.update(carried)
            kept += 1
    return kept


def _differences(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    fields = []
    for name in _FIELDS:
        old, new = before.get(name), after.get(name)
        if name != "properties":
            if old != new:
                fields.append(name)
            continue
        old, new = old or {}, new or {}
        if not isinstance(old, dict) or not isinstance(new, dict):
            if old != new:
                fields.append(name)
            continue
        for key in sorted(set(old) | set(new)):
            if key.lower() not in _RESTLESS and old.get(key) != new.get(key):
                fields.append(f"properties.{key}")
    return fields


def _brief(resource: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(resource.get("id") or "").lower(),
        "name": str(resource.get("name") or str(resource.get("id") or "").rsplit("/", 1)[-1]),
        "type": str(resource.get("type") or "").lower(),
        "group": str(resource.get("resourceGroup") or ""),
    }


@dataclass
class Refresh:
    """What changed between two reads, as the command reports it."""

    since: str | None
    read: str | None
    added: list[dict[str, str]] = field(default_factory=list)
    removed: list[dict[str, str]] = field(default_factory=list)
    changed: list[tuple[dict[str, str], list[str]]] = field(default_factory=list)
    #: whether a change could be told at all (an earlier snapshot was given)
    compared: bool = True

    @property
    def any(self) -> bool:
        return bool(self.added or self.removed or self.changed)

    def lines(self) -> list[str]:
        when = f" since {self.since}" if self.since else ""
        if not self.any:
            return [f"no change{when}"]
        out = [
            f"{len(self.added)} added, {len(self.changed)} changed, {len(self.removed)} removed{when}"
        ]
        out += [f"ADDED    {item['name']} ({item['type']}, {item['group']})" for item in self.added]
        out += [
            f"CHANGED  {item['name']} ({item['type']}): {', '.join(fields)}"
            for item, fields in self.changed
        ]
        out += [
            f"REMOVED  {item['name']} ({item['type']}, {item['group']})" for item in self.removed
        ]
        if not self.compared:
            out.append("NOTE     no earlier snapshot (--since), so changes cannot be told")
        return out


def compare(
    snapshot: dict[str, Any],
    *,
    earlier: dict[str, Any] | None = None,
    previous: CloudProject | None = None,
) -> Refresh:
    """What changed from *earlier* (a snapshot) to *snapshot*; with no
    earlier snapshot, what the *previous* diagram's cards say."""
    now = {str(item.get("id") or "").lower(): item for item in snapshot.get("resources") or []}
    if earlier is not None:
        before = {
            str(item.get("id") or "").lower(): item for item in earlier.get("resources") or []
        }
        return Refresh(
            since=earlier.get("taken"),
            read=snapshot.get("taken"),
            added=[_brief(now[rid]) for rid in sorted(set(now) - set(before))],
            removed=[_brief(before[rid]) for rid in sorted(set(before) - set(now))],
            changed=[
                (_brief(now[rid]), fields)
                for rid in sorted(set(now) & set(before))
                if (fields := _differences(before[rid], now[rid]))
            ],
        )
    drawn: dict[str, TopologyElement] = {}
    if previous is not None:
        for element in previous.topology.walk():
            if rid := _rid(element):
                drawn[rid] = element
    return Refresh(
        since=None,
        read=snapshot.get("taken"),
        added=[_brief(now[rid]) for rid in sorted(set(now) - set(drawn))] if drawn else [],
        removed=[
            {"id": rid, "name": drawn[rid].name, "type": "", "group": ""}
            for rid in sorted(set(drawn) - set(now))
        ],
        compared=False,
    )


def mark(project: CloudProject, refresh: Refresh) -> int:
    """Write *refresh* on *project*: each added or changed element says so,
    and the root keeps the account. Returns how many elements were marked."""
    added = {item["id"] for item in refresh.added}
    changed = {item["id"]: fields for item, fields in refresh.changed}
    marked = 0
    for element in project.topology.walk():
        element.attributes.pop("refresh", None)
        rid = _rid(element)
        if rid in added:
            element.attributes["refresh"] = {"status": "added"}
            marked += 1
        elif rid in changed:
            element.attributes["refresh"] = {"status": "changed", "fields": changed[rid]}
            marked += 1
    project.topology.attributes["refresh"] = {
        "since": refresh.since,
        "read": refresh.read,
        "added": len(refresh.added),
        "changed": len(refresh.changed),
        "removed": [
            {key: item[key] for key in ("name", "type", "group") if item.get(key)}
            for item in refresh.removed
        ],
        "compared": refresh.compared,
    }
    return marked
