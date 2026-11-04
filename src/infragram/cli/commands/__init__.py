"""Every command, one module per group.

A command here is a name, a target and a line of help. The target is a user
command in :mod:`infragram.cli.user` or a maintainer script under
``scripts/``; the bodies live there, so a group module is a table and the
groups are split by namespace rather than one file per command.

The merge refuses a name claimed twice. Two groups quietly registering the
same command would leave whichever imported last in charge, and the help
listing would show one of them while the other ran.
"""

from __future__ import annotations

from . import build, gen, importers, inventory, project, recipes, tests, tools, verify
from .verify import FIXED_ARGS, VERIFY_ALL, VERIFY_QUICK

__all__ = ["COMMANDS", "FIXED_ARGS", "GROUPS", "VERIFY_ALL", "VERIFY_QUICK"]

#: The groups, in the order a reader meets them: what an installed copy can
#: do, then the repository's own build, gates and chores.
GROUPS = (project, build, gen, importers, inventory, recipes, verify, tests, tools)


def _merged() -> dict[str, tuple[str, str]]:
    merged: dict[str, tuple[str, str]] = {}
    for group in GROUPS:
        for name, entry in group.COMMANDS.items():
            if name in merged:
                raise RuntimeError(
                    f"command {name!r} is registered twice: {merged[name][0]} and {entry[0]}"
                )
            merged[name] = entry
    return merged


#: command -> (target, help text)
COMMANDS: dict[str, tuple[str, str]] = _merged()
