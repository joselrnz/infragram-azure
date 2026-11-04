#!/usr/bin/env python3
"""Fail when ruff finds a problem anywhere in the tree, a Python file is not
laid out as ruff formats it, or Node finds a syntax error in the JavaScript a
page carries.

The rules are the ones ``pyproject.toml`` selects (``[tool.ruff.lint]``):
pyflakes, import order, pyupgrade, bugbear, simplify, blind excepts, unused
noqa comments and bandit's security rules. The layout is ``ruff format``'s (``[tool.ruff.format]``); run
``ruff format --no-cache .`` to apply it. Ruff comes with the ``test`` extra
(``pip install -e "./plugin[test]"``).

The editor runtime and the 3D renderer are JavaScript that only a browser
runs, so a syntax error in either would pass every gate but the browser
suite. ``node --check`` reads each as the page carries it -- the runtime
joined from its modules, the renderer as one script -- and runs nothing.
Without Node on the PATH that part is named as not checked; CI's image has
Node.

    python scripts/verify/lint.py
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


def page_scripts() -> dict[str, str]:
    """The JavaScript an exported page carries, by name."""
    sys.path.insert(0, str(ROOT / "src"))
    from infragram.editor.bundle import runtime_script
    from infragram.iso3d.bundle import bundle_source

    return {"the editor runtime": runtime_script(), "the 3D renderer": bundle_source()}


def syntax_errors(scripts: dict[str, str], node: str) -> list[str]:
    """What ``node --check`` says about each script, for those it refuses."""
    errors = []
    with tempfile.TemporaryDirectory(prefix="infragram-lint-") as scratch:
        for index, (name, text) in enumerate(scripts.items()):
            path = Path(scratch) / f"script-{index}.js"
            path.write_text(text, encoding="utf-8")
            done = subprocess.run(
                [node, "--check", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if done.returncode:
                errors.append(f"{name}: {(done.stderr or done.stdout).strip()}")
    return errors


def main(argv: list[str] | None = None) -> int:
    if importlib.util.find_spec("ruff") is None:
        print(
            'FAIL lint: ruff is not installed; python -m pip install -e ".[test]"', file=sys.stderr
        )
        return 2
    # Ruff's binary cache includes absolute working paths; keep it out of shared checkouts.
    done = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", ".", *(argv or [])], cwd=ROOT
    )
    if done.returncode:
        return done.returncode
    done = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--no-cache", "--check", "."], cwd=ROOT
    )
    if done.returncode:
        print(
            "FAIL lint: files differ from Ruff's layout; run `ruff format --no-cache .`",
            file=sys.stderr,
        )
        return done.returncode
    node = shutil.which("node")
    if node is None:
        print(
            "OK lint: ruff finds nothing and formats nothing; NOT CHECKED: the page's JavaScript"
            " (no node on the PATH)"
        )
        return 0
    scripts = page_scripts()
    errors = syntax_errors(scripts, node)
    for error in errors:
        print(f"FAIL lint: {error}", file=sys.stderr)
    if errors:
        return 1
    print(
        "OK lint: ruff finds nothing and formats nothing; node --check passes"
        f" {' and '.join(scripts)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
