#!/usr/bin/env python3
"""Fail when mypy finds a type error in the Python the repository holds.

Two passes, with the repository's settings (``[tool.mypy]`` in
pyproject.toml, pydantic's own plugin so a model's fields are the types they
declare):

- the package under src/infragram, the shipped examples and the
  maintainer scripts, the files the settings name. The examples are diagram
  files as a user writes them, so their pass is the proof that the authoring
  form type-checks: ``compute.EC2("web")``, a frame as a ``with`` block, a
  pattern's parts;
- the skill's own scripts, on their own: its launcher is ``infragram.py``,
  the package's name, and one run cannot hold two modules of one name.

The tests are left out: a wrong test fails when it runs. mypy comes with the
``test`` extra.

    python scripts/verify/typecheck.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())

#: What each pass reads, by name: no paths means the files pyproject.toml names.
PASSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("the package, the examples and the maintainer scripts", ()),
    ("the skill's scripts", ("skills/infragram-azure/scripts",)),
)


def main(argv: list[str] | None = None) -> int:
    if importlib.util.find_spec("mypy") is None:
        print(
            'FAIL types: mypy is not installed; python -m pip install -e "./plugin[test]"',
            file=sys.stderr,
        )
        return 2
    summaries = []
    for name, paths in PASSES:
        done = subprocess.run(
            [sys.executable, "-m", "mypy", *paths, *(argv or [])],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        report = (done.stdout + done.stderr).strip()
        if done.returncode:
            print(report, file=sys.stderr)
            print(f"FAIL types: mypy reports the errors above in {name}", file=sys.stderr)
            return done.returncode
        # mypy's own last line: "Success: no issues found in N source files"
        summaries.append(report.splitlines()[-1] if report else "mypy finds nothing")
    print(f"OK types: {'; '.join(summaries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
