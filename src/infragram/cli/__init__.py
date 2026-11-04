"""The command line, in four pieces.

:mod:`.commands` holds one module per group of commands and a merge that
refuses a name claimed twice; :mod:`.scripts` says where a command's target
lives; :mod:`.runner` runs one, or every gate in CI's order; and :mod:`.cli`
parses the arguments and dispatches. The user commands themselves are
package code in :mod:`.user`.

``main`` is re-exported here because ``pyproject.toml`` declares the console
script as ``infragram.cli:main``; the entry module is ``cli`` rather than
``main`` for that reason, since a submodule of that name would be set as this
package's ``main`` attribute the moment anything imported it, shadowing the
function the console script resolves.
"""

from __future__ import annotations

from .cli import build_parser, main
from .commands import COMMANDS, FIXED_ARGS, VERIFY_ALL, VERIFY_QUICK
from .runner import call, pytest_argv, run_script, verify_all, verify_all_plan, verify_quick
from .scripts import (
    CALL_PREFIX,
    PYTEST_PREFIX,
    ROOT,
    SCRIPTS,
    STEP_PREFIX,
    resolve_script,
)

__all__ = [
    "CALL_PREFIX",
    "COMMANDS",
    "FIXED_ARGS",
    "PYTEST_PREFIX",
    "ROOT",
    "SCRIPTS",
    "STEP_PREFIX",
    "VERIFY_ALL",
    "VERIFY_QUICK",
    "build_parser",
    "call",
    "main",
    "pytest_argv",
    "resolve_script",
    "run_script",
    "verify_all",
    "verify_all_plan",
    "verify_quick",
]
