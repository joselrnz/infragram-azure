"""Reading an Azure estate through the Azure CLI's own session.

Nothing here holds a credential. Every call goes through ``az``, so whatever
``az login`` established -- a user, a service principal, a managed identity,
a device-code login on a jump box -- is what the import sees, with the same
permissions. The estate is read from Azure Resource Graph over ``az rest``,
which needs no CLI extension: one paged query returns every resource with
its properties, which is all the placement and wiring rules need.

The result is a *snapshot*: a plain JSON document of subscriptions, resource
groups and resources, and -- read the same way, from Resource Graph's own
tables -- the last fourteen days of changes and the open security findings
(Defender for Cloud recommendations, Azure Policy results). Those two are
extras: a read Azure refuses is noted in the snapshot, and the picture is
drawn without it. The importer draws from a snapshot, never from Azure
directly, so a snapshot saved today redraws the same picture tomorrow, in CI,
or on a machine with no Azure access at all.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "SNAPSHOT_FORMAT",
    "AzureCliError",
    "AzureSession",
    "load_snapshot",
    "save_snapshot",
]

SNAPSHOT_FORMAT = "infragram.azure-snapshot/1"

RESOURCE_GRAPH = (
    "https://management.azure.com/providers/Microsoft.ResourceGraph/resources"
    "?api-version=2022-10-01"
)

#: Resource Graph accepts at most this many subscriptions per request.
_SUBSCRIPTIONS_PER_QUERY = 1000
_PAGE = 1000

RESOURCES_QUERY = (
    "resources"
    " | project id, name, type, kind, location, resourceGroup, subscriptionId,"
    " tenantId, sku, managedBy, tags, properties"
)

SUBSCRIPTIONS_QUERY = (
    "resourcecontainers"
    " | where type =~ 'microsoft.resources/subscriptions'"
    " | project id=subscriptionId, name, tenantId, state=tostring(properties.state)"
)

GROUPS_QUERY = (
    "resourcecontainers"
    " | where type =~ 'microsoft.resources/subscriptions/resourcegroups'"
    " | project id, name, location, subscriptionId, managedBy, tags"
)

#: Asked of one subscription alone: refused when the identity may not read it.
PROBE_QUERY = "resourcecontainers | take 1 | project id"

#: Resource Graph keeps fourteen days of changes. The newest are kept, at
#: most this many, so a busy estate's snapshot stays a size a page can carry.
CHANGES_KEPT = 5000

CHANGES_QUERY = (
    "resourcechanges"
    " | extend changeTime = todatetime(properties.changeAttributes.timestamp)"
    " | where changeTime > ago(14d)"
    " | order by changeTime desc"
    f" | take {CHANGES_KEPT}"
    " | project targetId=tostring(properties.targetResourceId),"
    " changeType=tostring(properties.changeType), changeTime,"
    " changedBy=tostring(properties.changeAttributes.changedBy),"
    " clientType=tostring(properties.changeAttributes.clientType),"
    " operation=tostring(properties.changeAttributes.operation),"
    " changes=properties.changes"
)

#: Defender for Cloud's recommendations a resource fails.
DEFENDER_QUERY = (
    "securityresources"
    " | where type =~ 'microsoft.security/assessments'"
    " | where tostring(properties.status.code) =~ 'Unhealthy'"
    " | project id, resourceId=tostring(properties.resourceDetails.Id),"
    " title=tostring(properties.displayName),"
    " severity=tostring(properties.metadata.severity),"
    " remediation=tostring(properties.metadata.remediationDescription),"
    " link=tostring(properties.links.azurePortal)"
)

#: The Azure Policy rules a resource does not comply with ...
POLICY_QUERY = (
    "policyresources"
    " | where type =~ 'microsoft.policyinsights/policystates'"
    " | where tostring(properties.complianceState) =~ 'NonCompliant'"
    " | project resourceId=tostring(properties.resourceId),"
    " assignmentId=tostring(properties.policyAssignmentId),"
    " assignment=tostring(properties.policyAssignmentName),"
    " definitionId=tostring(properties.policyDefinitionId),"
    " definition=tostring(properties.policyDefinitionName),"
    " reference=tostring(properties.policyDefinitionReferenceId),"
    " effect=tostring(properties.policyDefinitionAction)"
)

#: ... and the names people gave the assignments and definitions behind them.
POLICY_NAMES_QUERY = (
    "policyresources"
    " | where type in~ ('microsoft.authorization/policyassignments',"
    " 'microsoft.authorization/policydefinitions')"
    " | project id, name=tostring(properties.displayName)"
)

Runner = Callable[[Sequence[str]], str]


class AzureCliError(RuntimeError):
    """``az`` is missing, not signed in, or refused a call."""


def _default_runner(args: Sequence[str]) -> str:
    executable = shutil.which("az")
    if executable is None:
        raise AzureCliError(
            "the Azure CLI (az) is not on PATH; install it from "
            "https://aka.ms/installazurecli and run `az login`"
        )
    completed = subprocess.run(
        [executable, *args, "--only-show-errors", "--output", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip()
        if "az login" in message:
            message += "\n(sign in with `az login`, or `az login --tenant <id>` for another tenant)"
        elif any(code in message for code in ("AccessDenied", "Forbidden", "AuthorizationFailed")):
            message = (
                "Azure refused the read: the signed-in identity needs at least the Reader "
                "role on the subscription (`az account show` says who that is).\n" + message
            )
        what = (
            "Azure Resource Graph query"
            if args and args[0] == "rest"
            else f"az {' '.join(args[:2])}"
        )
        raise AzureCliError(f"{what} failed: {message}")
    return completed.stdout


class AzureSession:
    """The subscriptions ``az`` can see, and a Resource Graph reader over them.

    ``runner`` takes the ``az`` arguments and returns its JSON output; the
    default runs the real CLI, and tests pass a fake.
    """

    def __init__(self, runner: Runner | None = None) -> None:
        self._run = runner or _default_runner

    def _json(self, *args: str) -> Any:
        output = self._run(list(args))
        try:
            return json.loads(output) if output.strip() else None
        except json.JSONDecodeError as error:
            raise AzureCliError(
                f"az {' '.join(args[:2])} returned something that is not JSON"
            ) from error

    # -- subscriptions ----------------------------------------------------
    def current_subscription(self) -> dict[str, Any]:
        """The subscription ``az account show`` names."""
        return _subscription(self._json("account", "show"))

    def subscriptions(self) -> list[dict[str, Any]]:
        """Every subscription the signed-in identity can see, enabled or not."""
        return [_subscription(entry) for entry in self._json("account", "list", "--all") or []]

    def resolve(self, wanted: Iterable[str] = (), *, every: bool = False) -> list[dict[str, Any]]:
        """Subscriptions by id or name; the current one when none are named.

        ``every`` takes every enabled subscription instead.
        """
        wanted = [item.strip() for item in wanted if item.strip()]
        if not wanted and not every:
            return [self.current_subscription()]
        known = self.subscriptions()
        if every:
            chosen = [entry for entry in known if entry["state"].lower() == "enabled"]
            if not chosen:
                raise AzureCliError("az sees no enabled subscription; run `az login`")
            return chosen
        chosen, missing = [], []
        for item in wanted:
            match = [
                entry
                for entry in known
                if item.lower() in (entry["id"].lower(), entry["name"].lower())
            ]
            if not match:
                missing.append(item)
            elif len(match) > 1:
                raise AzureCliError(
                    f"{item!r} names {len(match)} subscriptions; pass the id instead: "
                    + ", ".join(entry["id"] for entry in match)
                )
            elif match[0] not in chosen:
                chosen.append(match[0])
        if missing:
            names = ", ".join(f"{entry['name']} ({entry['id']})" for entry in known) or "none"
            raise AzureCliError(
                f"no subscription matches {', '.join(map(repr, missing))}; az sees: {names}"
            )
        return chosen

    def under_management_groups(self, groups: Iterable[str]) -> list[dict[str, Any]]:
        """The enabled subscriptions under the named management groups, at any
        depth, as Resource Graph sees them through the signed-in identity."""
        names = list(dict.fromkeys(group.strip() for group in groups if group.strip()))
        rows = self._pages({"managementGroups": names}, SUBSCRIPTIONS_QUERY)
        chosen = [
            _subscription(row)
            for row in sorted(rows, key=lambda row: str(row.get("name", "")).lower())
            if str(row.get("state") or "Enabled").lower() == "enabled"
        ]
        if not chosen:
            raise AzureCliError(
                f"no enabled subscription under management group {', '.join(map(repr, names))}"
                " that the signed-in identity can read"
            )
        return chosen

    # -- Resource Graph ---------------------------------------------------
    def query(self, query: str, subscription_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Every row of a Resource Graph query over the given subscriptions."""
        rows: list[dict[str, Any]] = []
        ids = list(subscription_ids)
        for start in range(0, len(ids), _SUBSCRIPTIONS_PER_QUERY):
            batch = ids[start : start + _SUBSCRIPTIONS_PER_QUERY]
            rows.extend(self._pages({"subscriptions": batch}, query))
        return rows

    def _pages(self, scope: dict[str, Any], query: str) -> list[dict[str, Any]]:
        """Every page of one query over one scope (subscriptions or
        management groups)."""
        rows: list[dict[str, Any]] = []
        token: str | None = None
        while True:
            options: dict[str, Any] = {"resultFormat": "objectArray", "$top": _PAGE}
            if token:
                options["$skipToken"] = token
            page = self._post(RESOURCE_GRAPH, {**scope, "query": query, "options": options})
            rows.extend(page.get("data") or [])
            token = page.get("$skipToken")
            if not token:
                break
        return rows

    def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        # The body goes through a file: on Windows ``az`` is a batch file, and
        # cmd.exe mangles quotes in a JSON argument.
        with tempfile.TemporaryDirectory(prefix="infragram-az-") as scratch:
            path = Path(scratch) / "body.json"
            path.write_text(json.dumps(body), encoding="utf-8")
            return self._json("rest", "--method", "post", "--url", url, "--body", f"@{path}") or {}

    def snapshot(
        self,
        subscriptions: Sequence[dict[str, Any]],
        *,
        changes: bool = True,
        findings: bool = True,
    ) -> dict[str, Any]:
        """One read of everything the importer draws from.

        ``changes`` and ``findings`` read the last fourteen days of changes
        and the open security findings too. Either read refused (an identity
        without the right to it, a tenant without Defender) is written under
        ``unread`` with Azure's reason, and the rest is kept. A subscription
        the identity may not read at all is listed under ``unreadable``.
        """
        ids = [entry["id"] for entry in subscriptions]
        taken: dict[str, Any] = {
            "format": SNAPSHOT_FORMAT,
            "taken": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "subscriptions": list(subscriptions),
            "resourceGroups": self.query(GROUPS_QUERY, ids),
            "resources": self.query(RESOURCES_QUERY, ids),
        }
        # Asked about several subscriptions, Resource Graph answers for those
        # the identity may read and leaves the rest out without a word, so a
        # closed one would draw as an empty one. One that came back with no
        # resource group is asked again on its own: that says which it is.
        seen = {str(group.get("subscriptionId") or "").lower() for group in taken["resourceGroups"]}
        unreadable: dict[str, str] = {}
        for sub_id in ids:
            if sub_id.lower() in seen:
                continue
            try:
                self.query(PROBE_QUERY, [sub_id])
            except AzureCliError as error:
                unreadable[sub_id] = str(error)
        if unreadable:
            taken["unreadable"] = unreadable
        unread: dict[str, str] = {}
        if changes:
            try:
                taken["changes"] = self.query(CHANGES_QUERY, ids)
            except AzureCliError as error:
                unread["changes"] = str(error)
        if findings:
            try:
                taken["findings"] = {
                    "defender": self.query(DEFENDER_QUERY, ids),
                    "policy": self.query(POLICY_QUERY, ids),
                    "names": self.query(POLICY_NAMES_QUERY, ids),
                }
            except AzureCliError as error:
                unread["findings"] = str(error)
        if unread:
            taken["unread"] = unread
        return taken


def _subscription(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry.get("id", ""),
        "name": entry.get("name") or entry.get("id", ""),
        "state": entry.get("state", "Enabled"),
        "tenantId": entry.get("tenantId", ""),
        "tenantName": entry.get("tenantDisplayName") or "",
    }


def save_snapshot(snapshot: dict[str, Any], path: Path, *, force: bool = True) -> Path:
    """Write *snapshot* to *path*. Without *force*, a file this tool did not
    write, or one edited since, is refused (ValueError), as an export is."""
    from ..exports.written import write_side_file

    write_side_file(path, json.dumps(snapshot, indent=2, sort_keys=True) + "\n", force=force)
    return path


def load_snapshot(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != SNAPSHOT_FORMAT:
        raise ValueError(f"{path} is not an Azure snapshot ({SNAPSHOT_FORMAT})")
    return data
