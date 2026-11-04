"""The command registry, now that it is a group per module.

A command is a name, a script under ``scripts/`` and a line of help. The
groups exist so a reader finds ``verify:naming`` next to the other gates
rather than in a table of thirty-one entries; the merge exists so the CLI
still sees one registry. What has to hold is that the split did not lose a
command, duplicate one, or leave one pointing at a script that is not there.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from infragram.cli import COMMANDS, VERIFY_ALL
from infragram.cli.commands import GROUPS
from infragram.cli.runner import STEPS
from infragram.cli.scripts import (
    CALL_PREFIX,
    PYTEST_PREFIX,
    ROOT,
    SCRIPTS,
    STEP_PREFIX,
    resolve_script,
)


def test_every_group_holds_at_least_one_command() -> None:
    """An empty module is a group somebody meant to fill."""
    for group in GROUPS:
        assert group.COMMANDS, f"{group.__name__} registers nothing"


def test_no_command_is_registered_twice() -> None:
    """Two groups claiming a name would leave the later import in charge
    while the help listing showed the other one."""
    seen: dict[str, str] = {}
    for group in GROUPS:
        for name in group.COMMANDS:
            assert name not in seen, f"{name!r} in both {seen[name]} and {group.__name__}"
            seen[name] = group.__name__
    assert set(seen) == set(COMMANDS)


def test_the_merge_refuses_a_name_claimed_twice() -> None:
    """The guard itself, not just the state that satisfies it today."""
    from infragram.cli import commands as registry

    class Clash:
        __name__ = "clash"
        COMMANDS = {next(iter(COMMANDS)): ("somewhere/else.py", "a second claim")}

    original = registry.GROUPS
    registry.GROUPS = (*original, Clash())
    try:
        with pytest.raises(RuntimeError, match="registered twice"):
            registry._merged()
    finally:
        registry.GROUPS = original


def test_every_command_names_a_target_that_exists() -> None:
    """A registry entry pointing at nothing fails at the moment somebody
    runs it, which is the worst moment to find out."""
    assert SCRIPTS is not None, "this test runs from a checkout"
    missing = []
    for name, (script, _help) in COMMANDS.items():
        if script.startswith(CALL_PREFIX):
            module, _, function = script.removeprefix(CALL_PREFIX).partition(":")
            assert callable(getattr(importlib.import_module(module), function)), name
        elif script.startswith(STEP_PREFIX):
            assert script.removeprefix(STEP_PREFIX) in STEPS, name
        elif script.startswith(PYTEST_PREFIX):
            assert ROOT is not None
            for target in script.removeprefix(PYTEST_PREFIX).split():
                assert (ROOT / target).exists(), name
        elif resolve_script(script) is None:
            missing.append(f"{name} -> {script}")
    assert not missing, missing


def test_every_command_carries_help() -> None:
    for name, (_script, help_text) in COMMANDS.items():
        assert help_text.strip(), f"{name} has no help text"


def test_verify_all_runs_scripts_the_registry_knows_about() -> None:
    """Except the suite entry, which names pytest targets rather than a
    script, the gate list and the registry describe the same files."""
    registered = {script for script, _help in COMMANDS.values()}
    for script, _args in VERIFY_ALL:
        if script.startswith(PYTEST_PREFIX):
            for target in script[len(PYTEST_PREFIX) :].split():
                assert (ROOT / target).exists(), target
            continue
        if script.startswith(STEP_PREFIX):
            assert script.removeprefix(STEP_PREFIX) in STEPS
            continue
        assert script in registered, f"{script} runs in verify:all but has no command"


def test_azure_discovery_and_generic_commands_are_all_available() -> None:
    expected = {
        "export:azure",
        "discover:azure",
        "discover:kubernetes",
        "costs",
        "diff",
        "views",
        "import:terraform",
        "import:diagram",
        "check:policy",
        "check:terraform",
        "mcp",
        "plugin:install",
        "plugin:path",
        "layout:save",
        "export:set",
        "schema",
        "templates",
    }
    assert expected <= COMMANDS.keys()
    assert "discover:aws" not in COMMANDS and "discover:gcp" not in COMMANDS


def test_azure_export_uses_the_importer_shipped_with_this_plugin(monkeypatch) -> None:
    from infragram.cli.user import export_azure
    from infragram.paths import plugin_root

    captured = []

    def importer(path):
        captured.append(Path(path))
        return {"main": lambda args: captured.append(args) or 0}

    monkeypatch.setattr(export_azure.runpy, "run_path", importer)
    args = ["--from-snapshot", "saved.json", "--view", "both"]
    assert export_azure.main(args) == 0
    assert captured == [plugin_root() / "scripts" / "export" / "azure.py", args]


def _package() -> Path:
    """The repository root, found by its marker."""
    return next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


def test_only_the_groups_declare_commands() -> None:
    """One table per command, and all of them under ``commands/``.

    Splitting the flat module left a full copy of the old table behind in
    ``cli/scripts.py``: nothing imported it, nothing linted it, and it would
    have sat there diverging from the real one until somebody edited the
    wrong copy. A second declaration anywhere in the package is the bug, not
    the divergence that follows it.
    """
    folder = _package() / "src" / "infragram" / "cli"
    stray = []
    for module in sorted(folder.rglob("*.py")):
        if module.parent.name == "commands":
            continue
        source = module.read_text(encoding="utf-8")
        if "COMMANDS: dict[str, tuple[str, str]] = {" in source:
            stray.append(str(module.relative_to(folder)))
    assert not stray, f"command tables outside commands/: {stray}"


def test_the_groups_are_the_modules_in_the_package() -> None:
    """A module added to ``commands/`` and left out of ``GROUPS`` registers
    nothing, silently."""
    folder = _package() / "src" / "infragram" / "cli" / "commands"
    on_disk = {p.stem for p in folder.glob("*.py") if p.stem != "__init__"}
    listed = {group.__name__.rsplit(".", 1)[1] for group in GROUPS}
    assert on_disk == listed, sorted(on_disk ^ listed)
