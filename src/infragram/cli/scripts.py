"""Where a command's target lives, and what the entry prefixes mean.

A registry entry is one of four things: a maintainer script under
``scripts/`` (``verify/naming.py``), a package function called in-process
(``call:infragram.cli.user.compose:main``), the pytest suite over some
directories (``pytest:tests/unit tests/skill``), or a step implemented in
:mod:`.runner` (``step:export-templates``). Scripts live only in a checkout
(a plugin folder built from one carries the package, not the scripts); the
user commands are package code, so every copy runs them.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..paths import checkout_root

__all__ = [
    "CALL_PREFIX",
    "PYTEST_PREFIX",
    "ROOT",
    "SCRIPTS",
    "STEP_PREFIX",
    "resolve_script",
]


#: The checkout this package runs from, or None for an installed copy.
ROOT = checkout_root()


#: The maintainer scripts; only a checkout carries them (a plugin folder
#: built from one holds the package source but no scripts).
SCRIPTS = (ROOT / "scripts") if ROOT is not None and (ROOT / "scripts").is_dir() else None


#: An entry after this prefix is a package function, ``module:function``,
#: called in-process with the command's arguments.
CALL_PREFIX = "call:"


#: An entry naming directories after this prefix runs the suite over them,
#: as CI does, rather than naming test modules one by one.
PYTEST_PREFIX = "pytest:"


#: An entry after this prefix is a step implemented in :mod:`.runner`: CI's
#: loop over every template, exported and checked.
STEP_PREFIX = "step:"


def resolve_script(script: str) -> Path | None:
    """Locate *script* under ``scripts/`` (or, for a test module, the checkout).

    Registry entries are role-relative (``verify/naming.py``) and resolve
    directly. A bare filename is accepted as a convenience, but only when it
    matches exactly one script; ambiguity is reported rather than guessed at.
    """
    if SCRIPTS is None or ROOT is None:
        raise SystemExit(
            f"ERROR: {script} belongs to a maintainer command, which runs from a "
            "checkout of the repository; infragram --help lists what this copy runs."
        )
    for base in (SCRIPTS, ROOT):
        direct = base / script
        if direct.is_file():
            return direct
    matches = sorted(SCRIPTS.rglob(script))
    if len(matches) > 1:
        names = ", ".join(str(m.relative_to(SCRIPTS)).replace("\\", "/") for m in matches)
        print(f"ERROR: {script!r} is ambiguous; name the role folder: {names}", file=sys.stderr)
        return None
    return matches[0] if matches else None
