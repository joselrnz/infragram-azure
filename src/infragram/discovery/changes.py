"""What changed in an estate lately, as Resource Graph keeps it.

Resource Graph keeps fourteen days of changes to every resource
(``resourcechanges``): when, what kind -- created, updated, deleted -- which
properties went from what to what, and, where Azure Resource Manager knows
it, who made the change and through what client. Read with the rest of a
snapshot, each change goes on the card of the resource it changed (the
importer decides which card: a subnet's change on its network, a NIC's on
its VM, a deleted resource's on its resource group).

Only what the rows state is kept, and trimmed for a page to carry: a value
is cut to one line, a change names its first few properties and how many
more there were, and the bookkeeping Azure changes on its own (an etag, a
provisioning state) is left out, so an update that touched nothing else is
not called a change.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["Change", "PropertyChange", "read_changes"]

#: Properties shown for one change; the rest are counted.
PROPERTIES_SHOWN = 5
#: A value longer than this is cut, with an ellipsis.
VALUE_LENGTH = 120
#: What Azure changes on its own; never the reason a change is shown.
_BOOKKEEPING = ("etag", "properties.provisioningstate", "properties.resourceguid")


class PropertyChange(BaseModel):
    """One property a change moved."""

    path: str
    before: str = ""
    after: str = ""


class Change(BaseModel):
    """One change to one resource."""

    #: The resource changed, by lower-cased ARM id.
    target: str
    #: Its name: the id's last segment, so a deleted resource still has one.
    name: str
    #: When, as ISO 8601 in UTC.
    when: str
    #: ``Create``, ``Update`` or ``Delete``.
    kind: str
    #: Who, as Azure Resource Manager recorded it: a sign-in name, an
    #: application id, or empty.
    by: str = ""
    #: Through what: ``Azure Portal``, ``Azure CLI``, ``ARM template`` ...
    client: str = ""
    properties: list[PropertyChange] = Field(default_factory=list)
    #: How many more properties it moved than are listed.
    more: int = 0


def _line(value: Any) -> str:
    if value is None:
        return ""
    text = " ".join(str(value).split())
    # an ARM id is kept whole: the page says the name at its end
    if len(text) <= VALUE_LENGTH or text.lower().startswith("/subscriptions/"):
        return text
    return text[: VALUE_LENGTH - 1] + "…"


def _when(value: Any) -> str:
    text = str(value or "")
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _kind(value: Any) -> str:
    text = str(value or "").lower()
    return {"create": "Create", "update": "Update", "delete": "Delete"}.get(text, "Update")


def _moved(changes: Any) -> list[PropertyChange]:
    """The properties a row says moved, the user's first, bookkeeping out."""
    if not isinstance(changes, dict):
        return []
    found: list[tuple[int, str, PropertyChange]] = []
    for path, detail in changes.items():
        if str(path).lower().startswith(_BOOKKEEPING):
            continue
        detail = detail if isinstance(detail, dict) else {}
        system = str(detail.get("changeCategory") or "").lower() == "system"
        found.append(
            (
                int(system),
                str(path),
                PropertyChange(
                    path=str(path),
                    before=_line(detail.get("previousValue")),
                    after=_line(detail.get("newValue")),
                ),
            )
        )
    found.sort(key=lambda item: (item[0], item[1].lower()))
    return [change for _, _, change in found]


def read_changes(rows: Iterable[dict[str, Any]]) -> list[Change]:
    """Every change the rows of a ``resourcechanges`` read describe, newest first."""
    changes: list[Change] = []
    for row in rows:
        named = str(row.get("targetId") or "").rstrip("/")
        target = named.lower()
        if not target:
            continue
        kind = _kind(row.get("changeType"))
        moved = _moved(row.get("changes"))
        if kind == "Update" and not moved and isinstance(row.get("changes"), dict):
            # it named only what Azure keeps for itself
            continue
        changes.append(
            Change(
                target=target,
                name=named.rsplit("/", 1)[-1],
                when=_when(row.get("changeTime")),
                kind=kind,
                by=str(row.get("changedBy") or ""),
                client=str(row.get("clientType") or ""),
                properties=moved[:PROPERTIES_SHOWN],
                more=max(0, len(moved) - PROPERTIES_SHOWN),
            )
        )
    changes.sort(key=lambda change: change.when, reverse=True)
    return changes
