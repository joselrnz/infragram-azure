"""Reading Azure again keeps the reader's work and says what changed.

export:azure --refresh redraws an earlier diagram from a newer read: a card
the reader moved stays where it was left, a new resource is laid out, and
what was added, changed or removed is written on the document and printed.
The exit status says whether anything changed, for a scheduled job.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_discovery_azure import resource, snapshot  # noqa: E402

from infragram.discovery import save_snapshot  # noqa: E402
from infragram.discovery.refresh import compare  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export" / "azure.py"


def _command():
    spec = importlib.util.spec_from_file_location("_export_azure_refresh", SCRIPT)
    assert spec is not None and spec.loader is not None
    command = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(command)
    return command


def _card(document: dict, name: str) -> dict:
    def walk(element: dict):
        yield element
        for child in element.get("children", []) or []:
            yield from walk(child)

    found = [element for element in walk(document["topology"]) if element.get("name") == name]
    assert found, f"no element named {name!r}"
    return found[0]


def _later() -> dict:
    """The estate a day on: a vault added, the workspace gone, storage resized."""
    later = copy.deepcopy(snapshot())
    later["taken"] = "2026-09-30T12:00:00+00:00"
    later["resources"] = [r for r in later["resources"] if r["name"] != "log-prod"]
    for item in later["resources"]:
        if item["name"] == "stprod":
            item["sku"] = {"name": "Premium_ZRS"}
            item["properties"] = dict(item.get("properties") or {}, provisioningState="Updating")
    later["resources"].append(resource("rg-app", "Microsoft.KeyVault", "vaults", "kv-prod"))
    return later


def test_compare_names_added_removed_and_changed_and_ignores_restless_fields() -> None:
    refresh = compare(_later(), earlier=snapshot())
    assert [item["name"] for item in refresh.added] == ["kv-prod"]
    assert [item["name"] for item in refresh.removed] == ["log-prod"]
    # the sku moved; provisioningState is Azure's own bookkeeping, not a change
    assert [(item["name"], fields) for item, fields in refresh.changed] == [("stprod", ["sku"])]
    assert refresh.any
    assert compare(snapshot(), earlier=snapshot()).lines() == [
        "no change since 2026-09-29T12:00:00+00:00"
    ]


def test_refresh_keeps_a_moved_card_and_marks_the_changes(tmp_path: Path, capsys) -> None:
    command = _command()
    first = save_snapshot(snapshot(), tmp_path / "estate.json")
    out = tmp_path / "first"
    assert (
        command.main(
            ["--from-snapshot", str(first), "--formats", "template", "--output-dir", str(out)]
        )
        == 0
    )
    (written,) = out.glob("*.infragram.json")
    document = json.loads(written.read_text(encoding="utf-8"))
    # the reader drags the storage account somewhere of their own, and colours it
    storage = _card(document, "stprod")
    storage["attributes"].update(editor_x=1234, editor_y=567, editor_style={"fill": "#fff7e6"})
    edited = tmp_path / "edited.infragram.json"
    edited.write_text(json.dumps(document), encoding="utf-8")

    second = save_snapshot(_later(), tmp_path / "estate-2.json")
    capsys.readouterr()
    code = command.main(
        [
            "--refresh",
            str(edited),
            "--since",
            str(first),
            "--from-snapshot",
            str(second),
            "--formats",
            "template",
            "--output-dir",
            str(tmp_path / "second"),
        ]
    )
    printed = capsys.readouterr().out
    assert code == 4, printed
    assert "1 added, 1 changed, 1 removed since 2026-09-29T12:00:00+00:00" in printed
    assert "CHANGED  stprod (microsoft.storage/storageaccounts): sku" in printed

    (refreshed,) = (tmp_path / "second").glob("*.infragram.json")
    assert refreshed.name == written.name, "the refresh keeps the earlier diagram's name"
    after = json.loads(refreshed.read_text(encoding="utf-8"))
    kept = _card(after, "stprod")["attributes"]
    assert (kept["editor_x"], kept["editor_y"]) == (1234, 567)
    assert kept["editor_style"] == {"fill": "#fff7e6"}
    assert kept["refresh"] == {"status": "changed", "fields": ["sku"]}
    assert _card(after, "kv-prod")["attributes"]["refresh"] == {"status": "added"}
    account = after["topology"]["attributes"]["refresh"]
    assert account["removed"] == [
        {"name": "log-prod", "type": "microsoft.operationalinsights/workspaces", "group": "rg-app"}
    ]
    assert (account["added"], account["changed"]) == (1, 1)


def test_nothing_changed_exits_zero_and_one_view_is_required(tmp_path: Path, capsys) -> None:
    command = _command()
    first = save_snapshot(snapshot(), tmp_path / "estate.json")
    out = tmp_path / "first"
    command.main(["--from-snapshot", str(first), "--formats", "template", "--output-dir", str(out)])
    (written,) = out.glob("*.infragram.json")
    again = ["--refresh", str(written), "--since", str(first), "--from-snapshot", str(first)]
    capsys.readouterr()
    assert (
        command.main([*again, "--formats", "template", "--output-dir", str(tmp_path / "again")])
        == 0
    )
    assert "no change since" in capsys.readouterr().out
    assert command.main([*again, "--view", "both", "--output-dir", str(tmp_path / "x")]) == 2
    assert "give its --view" in capsys.readouterr().err


def test_without_the_earlier_snapshot_only_added_and_removed_are_told(tmp_path: Path) -> None:
    command = _command()
    first = save_snapshot(snapshot(), tmp_path / "estate.json")
    out = tmp_path / "first"
    command.main(["--from-snapshot", str(first), "--formats", "template", "--output-dir", str(out)])
    (written,) = out.glob("*.infragram.json")
    from infragram.cli.user.diff import load_any

    refresh = compare(_later(), previous=load_any(written))
    assert not refresh.compared and not refresh.changed
    assert "kv-prod" in [item["name"] for item in refresh.added]
    assert "NOTE     no earlier snapshot (--since), so changes cannot be told" in refresh.lines()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))


def test_refresh_reads_an_earlier_diagram_and_never_runs_one(tmp_path: Path, capsys) -> None:
    """A .py diagram file is a program: --refresh refuses it rather than run
    whatever a colleague sent as "the earlier diagram"."""
    command = _command()
    planted = tmp_path / "prod-network.py"
    marker = tmp_path / "ran"
    planted.write_text(f"open({str(marker)!r}, 'w').close()\n", encoding="utf-8")
    first = save_snapshot(snapshot(), tmp_path / "estate.json")
    code = command.main(
        [
            "--refresh",
            str(planted),
            "--from-snapshot",
            str(first),
            "--output-dir",
            str(tmp_path / "o"),
        ]
    )
    assert code == 2
    assert "not a diagram file that would run" in capsys.readouterr().err
    assert not marker.exists()


def test_a_name_cannot_drive_the_terminal() -> None:
    later = _later()
    for item in later["resources"]:
        if item["name"] == "kv-prod":
            item["name"] = "kv\x1b[2J\x1b[31mprod"
    printed = "\n".join(compare(later, earlier=snapshot()).lines())
    assert "\x1b" not in printed
    assert r"kv\x1b[2J\x1b[31mprod" in printed
