"""``infragram plugin:install`` and ``infragram plugin:path``: the plugin this
copy carries, registered with an agent.

Every copy of Infragram carries its plugin folder whole: a checkout's
root, an agent's install of it, and an installed wheel's
``infragram/_plugin`` (so ``uv tool install``, ``pipx`` and ``pip`` install
the plugin as well as the command). That folder is its own marketplace, so
registering it is the agent's own two steps:

- Claude Code: ``claude plugin marketplace add <folder>``, then
  ``claude plugin install infragram-azure@infragram-azure``;
- Codex: ``codex plugin marketplace add <folder>``, then
  ``codex plugin add infragram-azure@infragram-azure``;
- Pi: ``pi install <folder>``.

``--dry-run`` prints the commands without running them.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

__all__ = ["install_commands", "install_main", "path_main"]

PLUGIN = "infragram-azure"
AGENTS = ("claude", "codex", "pi")


def install_commands(agent: str, folder: Path, scope: str | None = None) -> list[list[str]]:
    """The commands that register *folder* with *agent*."""
    where = str(folder)
    if agent == "claude":
        scoped = ["--scope", scope] if scope else []
        return [
            ["claude", "plugin", "marketplace", "add", where, *scoped],
            ["claude", "plugin", "install", f"{PLUGIN}@{PLUGIN}", *scoped],
        ]
    if agent == "codex":
        return [
            ["codex", "plugin", "marketplace", "add", where],
            ["codex", "plugin", "add", f"{PLUGIN}@{PLUGIN}"],
        ]
    if agent == "pi":
        return [["pi", "install", where, *(["-l"] if scope == "project" else [])]]
    raise ValueError(f"unknown agent {agent!r}; one of {', '.join(AGENTS)}")


def _folder() -> Path:
    from ...paths import plugin_root

    return plugin_root()


def path_main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        prog="infragram plugin:path",
        description="Print the plugin folder this copy carries (its own marketplace).",
    ).parse_args(argv)
    print(_folder())
    return 0


def install_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="infragram plugin:install",
        description="Register the plugin this copy carries with an agent: Claude Code, Codex or Pi.",
    )
    parser.add_argument("agent", choices=AGENTS, help="the agent to install the plugin into")
    parser.add_argument(
        "--scope",
        choices=("user", "project", "local"),
        default=None,
        help="Claude Code's installation scope (default: user); for Pi, project "
        "installs into this project's .pi/settings.json",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")
    options = parser.parse_args(argv)
    folder = _folder()
    commands = install_commands(options.agent, folder, options.scope)
    if options.dry_run:
        for command in commands:
            print(subprocess.list2cmdline(command))
        return 0
    executable = shutil.which(commands[0][0])
    if executable is None:
        print(
            f"ERROR: the {commands[0][0]} command is not on PATH; install {options.agent} first",
            file=sys.stderr,
        )
        return 2
    for command in commands:
        print(f"RUN      {subprocess.list2cmdline(command)}", flush=True)
        done = subprocess.run([executable, *command[1:]], check=False)
        if done.returncode:
            print(f"ERROR: {command[0]} exited {done.returncode}", file=sys.stderr)
            return done.returncode
    print(
        f"OK       {PLUGIN} is installed in {options.agent} from {folder}; start a new session to load it"
    )
    return 0
