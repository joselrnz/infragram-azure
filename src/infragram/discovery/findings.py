"""What a security review would raise about an estate, as Azure states it.

Two sources, both read from Resource Graph with the rest of a snapshot:

Defender for Cloud
    Each recommendation a resource fails (an assessment whose status is
    ``Unhealthy``), with its severity and how to fix it.

Azure Policy
    Each policy rule a resource does not comply with, named as the rule's
    definition is named, with the assignment that applies it. Policy gives no
    severity of its own.

Nothing is judged here: a finding is shown only because Azure reports it,
and a tenant without Defender, or without policy assignments, simply has
none of that kind. A resource that fails one rule through several
assignments has one finding for it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

__all__ = ["SEVERITY_ORDER", "Finding", "read_findings"]

#: Worst first; Policy's findings carry no severity and come after Low.
SEVERITY_ORDER = ("High", "Medium", "Low", "")

_ASSESSMENT = re.compile(r"/providers/microsoft\.security/assessments/[^/]+$", re.IGNORECASE)


class Finding(BaseModel):
    """One thing Azure says is wrong with one resource."""

    #: ``Defender`` or ``Policy``.
    source: str
    #: What is wrong, as Azure names it.
    title: str
    #: ``High``, ``Medium`` or ``Low`` for Defender; empty for Policy.
    severity: str = ""
    #: How to fix it (Defender), or the assignment that applies the rule (Policy).
    detail: str = ""
    #: Where Azure's portal shows it, when the row says.
    link: str = ""


def _severity(value: Any) -> str:
    text = str(value or "").strip().lower()
    return {"high": "High", "medium": "Medium", "low": "Low"}.get(text, "")


def _rank(finding: Finding) -> tuple[int, str, str]:
    return (SEVERITY_ORDER.index(finding.severity), finding.source, finding.title.lower())


def _words(name: str) -> str:
    """``storageAccountsShouldRestrictNetworkAccess`` -> a sentence."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name.replace("_", " ").replace("-", " "))
    return spaced[:1].upper() + spaced[1:].lower() if spaced else ""


def _guid(name: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", name.lower()))


def read_findings(
    defender: Iterable[dict[str, Any]] = (),
    policy: Iterable[dict[str, Any]] = (),
    names: Iterable[dict[str, Any]] = (),
) -> dict[str, list[Finding]]:
    """Every finding by the lower-cased id of the resource it is about, worst first."""
    named = {
        str(row.get("id") or "").lower(): str(row.get("name") or "")
        for row in names
        if row.get("name")
    }
    found: dict[str, dict[tuple[str, str], Finding]] = {}

    def add(resource: str, finding: Finding) -> None:
        if resource and finding.title:
            found.setdefault(resource, {}).setdefault((finding.source, finding.title), finding)

    for row in defender:
        # the assessment's own id is the resource's id with the assessment after it
        resource = str(row.get("resourceId") or "") or _ASSESSMENT.sub("", str(row.get("id") or ""))
        add(
            resource.lower(),
            Finding(
                source="Defender",
                title=str(row.get("title") or "").strip(),
                severity=_severity(row.get("severity")),
                detail=" ".join(str(row.get("remediation") or "").split()),
                link=str(row.get("link") or ""),
            ),
        )
    for row in policy:
        definition = str(row.get("definition") or "")
        reference = str(row.get("reference") or "")
        title = (
            named.get(str(row.get("definitionId") or "").lower())
            or (_words(reference) if reference and not _guid(reference) else "")
            or (definition if definition and not _guid(definition) else "")
            or f"Policy rule {definition[:8]}".strip()
        )
        assignment = named.get(str(row.get("assignmentId") or "").lower()) or str(
            row.get("assignment") or ""
        )
        add(
            str(row.get("resourceId") or "").lower(),
            Finding(
                source="Policy",
                title=title,
                detail=f"Assigned as {assignment}" if assignment else "",
            ),
        )
    return {resource: sorted(items.values(), key=_rank) for resource, items in found.items()}
