"""Policy checks: what a diagram draws that a reviewer would stop, and what
Checkov or Trivy find in a Terraform folder, when one of them is installed.

The diagram rules read the drawing, so they hold for a diagram drawn by hand
as much as for one imported from Terraform (where a security group rule that
lets the internet in is drawn as a wire from the Internet card):

- ``database-in-public-subnet``: a database inside a public subnet frame;
- ``internet-reaches-database``: a wire from the internet straight to a database;
- ``internet-reaches-private-subnet``: a wire from the internet to something in
  a private subnet that is no front door (a load balancer, gateway, firewall or
  WAF -- a networking or security component -- is there to be reached);
- ``admin-port-open-to-internet``: a wire from the internet that lets in SSH
  (22), RDP (3389) or every port.

The scanners are the user's own: Infragram never installs them, and runs one
only when it is on the PATH.

What ``check:policy`` read and found is one JSON object as well
(:func:`policy_json`, ``check:policy --json``), for a pipeline to act on.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..models.topology import TopologyElement
from ..projects import CloudProject

__all__ = [
    "RULES",
    "SCANNERS",
    "Finding",
    "SourceReport",
    "diagram_findings",
    "policy_json",
    "scan_folder",
    "scanner_on_path",
]

#: rule -> what it holds, for the report and the docs.
RULES = {
    "database-in-public-subnet": "a database inside a public subnet",
    "internet-reaches-database": "a wire from the internet straight to a database",
    "internet-reaches-private-subnet": "a wire from the internet to something in a private subnet",
    "admin-port-open-to-internet": "a wire from the internet that lets in SSH, RDP or every port",
}
#: The scanners, in the order ``auto`` tries them.
SCANNERS = ("checkov", "trivy")
#: Shared components that stand for the internet, or anyone on it.
_INTERNET = frozenset({"public-internet", "public-users", "public-user"})
#: A label that lets in SSH, RDP or every port: ``SSH :22``, ``TCP :3389``, ``all traffic``.
_ADMIN = re.compile(r"\b(ssh|rdp)\b|:(22|3389)\b|\ball (traffic|tcp)\b", re.IGNORECASE)
_RANGE = re.compile(r"\b(\d{1,5})-(\d{1,5})\b")
#: A label that lets in every port: ``all traffic``, ``all TCP``, ``0-65535``.
_EVERY_PORT = re.compile(r"\ball (traffic|tcp|udp|ports?)\b|\b0-65535\b", re.IGNORECASE)
#: How long one scanner may take over one folder.
SCAN_TIMEOUT = 600


class Finding(BaseModel):
    """One thing a rule or a scanner flagged."""

    rule: str
    #: The element, or the resource and file, it is about.
    where: str
    message: str
    severity: str = "warning"
    #: ``diagram``, or the scanner that found it.
    source: str = "diagram"
    #: A diagram rule's: the element's name (``where`` is its id).
    name: str = ""
    #: A scanner's: the resource, the file and the first line it points at,
    #: which ``where`` says in one phrase for a person.
    resource: str = ""
    file: str = ""
    line: int | None = None


class SourceReport(BaseModel):
    """What ``check:policy`` made of one source it was given."""

    path: str
    #: ``diagram`` (a document, a diagram file, a page or picture) or ``folder``.
    kind: str
    #: ``read`` (a diagram), ``scanned`` (a folder) or ``skipped`` (a folder no scanner read).
    status: str
    #: The scanner that read a folder.
    scanner: str | None = None
    findings: list[Finding] = Field(default_factory=list)
    #: Why a folder was skipped.
    note: str = ""


def _category(element: TopologyElement) -> str:
    from ..catalog.components import component_category

    return component_category(element)


def _is_database(element: TopologyElement) -> bool:
    return _category(element) == "databases"


#: What stands in front: the internet reaching one is what it is for.
_FRONT_DOORS = frozenset({"networking", "security"})


def _is_internet(element: TopologyElement) -> bool:
    component = element.component
    return (
        component is not None
        and component.provider == "infragram"
        and component.service_id in _INTERNET
    )


def _admits_admin(label: str) -> bool:
    if _ADMIN.search(label):
        return True
    return any(
        int(low) <= port <= int(high) for low, high in _RANGE.findall(label) for port in (22, 3389)
    )


def diagram_findings(project: CloudProject) -> list[Finding]:
    """What the diagram rules flag in *project*, in document order."""
    subnet: dict[str, str] = {}  # element id -> the type of the nearest subnet frame around it
    elements: dict[str, TopologyElement] = {}

    def visit(element: TopologyElement, around: str) -> None:
        elements[element.id] = element
        if around:
            subnet[element.id] = around
        inner = element.type if element.type in ("subnet-public", "subnet-private") else around
        for child in element.children:
            visit(child, inner)

    visit(project.topology, "")
    findings: list[Finding] = []
    for element in elements.values():
        if _is_database(element) and subnet.get(element.id) == "subnet-public":
            findings.append(
                Finding(
                    rule="database-in-public-subnet",
                    where=element.id,
                    name=element.name,
                    message=f"{element.name} is a database in a public subnet; a database "
                    "belongs in a private one, reached through what serves it",
                )
            )
    for source in elements.values():
        for connection in source.connections:
            target = elements.get(connection.target)
            if target is None:
                continue
            ends = [(source, target)]
            if connection.direction in ("both", "none"):  # either end may start it
                ends.append((target, source))
            for start, end in ends:
                if not _is_internet(start):
                    continue
                label = f" ({connection.label})" if connection.label else ""
                if _is_database(end):
                    findings.append(
                        Finding(
                            rule="internet-reaches-database",
                            where=end.id,
                            name=end.name,
                            message=f"{start.name} reaches the database {end.name} directly{label}",
                        )
                    )
                elif subnet.get(end.id) == "subnet-private" and _category(end) not in _FRONT_DOORS:
                    findings.append(
                        Finding(
                            rule="internet-reaches-private-subnet",
                            where=end.id,
                            name=end.name,
                            message=f"{start.name} reaches {end.name} in a private subnet "
                            f"directly{label}",
                        )
                    )
                if _admits_admin(connection.label):
                    findings.append(
                        Finding(
                            rule="admin-port-open-to-internet",
                            where=end.id,
                            name=end.name,
                            message=f"{start.name} may open {connection.label!r} to {end.name}",
                            severity="error" if _EVERY_PORT.search(connection.label) else "warning",
                        )
                    )
    return findings


def scanner_on_path(wanted: str = "auto") -> str | None:
    """The scanner to run: the one named, or the first installed for ``auto``."""
    names = SCANNERS if wanted == "auto" else (wanted,)
    return next((name for name in names if shutil.which(name)), None)


def _command(scanner: str, folder: Path) -> list[str]:
    executable = shutil.which(scanner) or scanner
    if scanner == "checkov":
        return [
            executable,
            "--directory",
            str(folder),
            "--framework",
            "terraform",
            "--output",
            "json",
            "--quiet",
            "--compact",
        ]
    return [executable, "config", "--format", "json", "--quiet", str(folder)]


def _line(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _checkov(payload: Any) -> list[Finding]:
    reports = payload if isinstance(payload, list) else [payload]
    findings: list[Finding] = []
    for report in reports:
        if not isinstance(report, dict):
            continue
        for check in (report.get("results") or {}).get("failed_checks") or []:
            lines = check.get("file_line_range") or []
            line = f":{lines[0]}" if lines else ""
            findings.append(
                Finding(
                    rule=str(check.get("check_id", "")),
                    where=f"{check.get('resource', '')} ({check.get('file_path', '')}{line})",
                    message=str(check.get("check_name", "")),
                    severity=str(check.get("severity") or "warning").lower(),
                    source="checkov",
                    resource=str(check.get("resource") or ""),
                    file=str(check.get("file_path") or ""),
                    line=_line(lines[0]) if lines else None,
                )
            )
    return findings


def _trivy(payload: Any) -> list[Finding]:
    findings: list[Finding] = []
    for result in (payload or {}).get("Results") or []:
        for item in result.get("Misconfigurations") or []:
            if item.get("Status", "FAIL") != "FAIL":
                continue
            cause = item.get("CauseMetadata") or {}
            line = f":{cause['StartLine']}" if cause.get("StartLine") else ""
            findings.append(
                Finding(
                    rule=str(item.get("AVDID") or item.get("ID") or ""),
                    where=f"{cause.get('Resource', '')} ({result.get('Target', '')}{line})",
                    message=str(item.get("Title", "")),
                    severity=str(item.get("Severity") or "warning").lower(),
                    source="trivy",
                    resource=str(cause.get("Resource") or ""),
                    file=str(result.get("Target") or ""),
                    line=_line(cause.get("StartLine")),
                )
            )
    return findings


def scan_folder(folder: Path, scanner: str) -> list[Finding]:
    """What *scanner* finds in a Terraform folder; raises RuntimeError when it cannot run."""
    try:
        done = subprocess.run(  # the user's own scanner, found on the PATH
            _command(scanner, folder),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SCAN_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"{scanner} did not run: {error}") from error
    try:
        payload = json.loads(done.stdout) if done.stdout.strip() else {}
    except ValueError as error:
        tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or [""]
        raise RuntimeError(f"{scanner} wrote no report: {tail[0]}") from error
    return _checkov(payload) if scanner == "checkov" else _trivy(payload)


def policy_json(sources: Iterable[SourceReport], *, strict: bool = False) -> dict[str, Any]:
    """What ``check:policy`` read and found, as one JSON-ready object
    (``check:policy --json``): each source in the order it was given and what
    became of it; every finding with its rule, severity and message, and the
    element (a diagram rule's) or the resource, file and line (a scanner's);
    and the verdict the text report ends with: ``ok`` when nothing is found,
    else ``warn``, or ``fail`` under ``--strict``, the one that exits 1.
    Findings are sorted, so the same sources always give the same text."""
    read = list(sources)
    found = sorted(
        ((source.path, finding) for source in read for finding in source.findings),
        key=lambda pair: (pair[0], pair[1].source, pair[1].rule, pair[1].where, pair[1].message),
    )
    severities: dict[str, int] = {}
    for _, finding in found:
        severities[finding.severity] = severities.get(finding.severity, 0) + 1
    return {
        "verdict": "ok" if not found else "fail" if strict else "warn",
        "strict": strict,
        "total": len(found),
        "by_severity": dict(sorted(severities.items())),
        "rules": dict(sorted(RULES.items())),
        "sources": [
            {
                "path": source.path,
                "kind": source.kind,
                "status": source.status,
                "scanner": source.scanner,
                "findings": len(source.findings),
                "note": source.note,
            }
            for source in read
        ],
        "findings": [
            {
                "path": path,
                "source": finding.source,
                "rule": finding.rule,
                "severity": finding.severity,
                "message": finding.message,
                "where": finding.where,
                "element_id": finding.where if finding.source == "diagram" else None,
                "element_name": finding.name if finding.source == "diagram" else None,
                "resource": finding.resource or None,
                "file": finding.file or None,
                "line": finding.line,
            }
            for path, finding in found
        ],
    }
