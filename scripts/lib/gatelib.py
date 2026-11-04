"""Shared helpers for the infragram CI gate scripts.

Each gate stays a standalone file invoked as ``python scripts/<name>.py``.
Because the gate filenames are hyphenated, the scripts import this module by
putting the scripts directory first on ``sys.path``:

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from lib import gatelib

Standard library only; Python 3.11+; Windows/macOS/Ubuntu. Every filesystem
read and subprocess decode pins UTF-8 explicitly so local runs behave like CI
(which sets PYTHONUTF8=1) even when the environment does not.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------
# Gate reporting
# --------------------------------------------------------------------------


def fail(message: str) -> None:
    """Report a gate failure on stderr and stop the script with exit code 1."""
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def ok(message: str) -> None:
    """Report a passed gate step on stdout."""
    print(f"OK: {message}")


# --------------------------------------------------------------------------
# Subprocess and environment helpers
# --------------------------------------------------------------------------


def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """``subprocess.run`` with captured output decoded as UTF-8.

    Bare ``text=True`` decodes with the locale encoding, which breaks on
    Windows consoles (cp1252) whenever a tool emits non-ASCII output. Callers
    may override any option (``errors="strict"``, ``capture_output=False``,
    ``env=...``, ``cwd=...``).
    """
    options: dict[str, Any] = {
        "capture_output": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    options.update(kwargs)
    return subprocess.run(argv, **options)  # callers check returncode
