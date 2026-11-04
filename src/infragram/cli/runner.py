"""Running one command, and running every gate in CI's order.

Every ``test:*`` command runs its module under pytest: run as a plain script,
a module that only defines test functions exits 0 having run none of them.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from .commands import VERIFY_ALL, VERIFY_QUICK
from .scripts import (
    CALL_PREFIX,
    PYTEST_PREFIX,
    ROOT,
    SCRIPTS,
    STEP_PREFIX,
    resolve_script,
)

__all__ = ["call", "pytest_argv", "run_script", "verify_all", "verify_all_plan", "verify_quick"]


#: Where CI's export step writes; cleared before each run so a stale page
#: from an earlier run is never the one checked.
EXPORT_DIR = Path("dist") / "ci"


TEMPLATES = Path("skills") / "infragram-azure" / "assets" / "templates" / "cloud"


EXPORT_FORMATS = "template,html,svg"


def pytest_argv(targets: Sequence[str], args: Sequence[str]) -> list[str]:
    """The suite command, quiet and without a cache directory, as CI runs it."""
    return [sys.executable, "-m", "pytest", *targets, "-q", "-p", "no:cacheprovider", *args]


def call(target: str, args: Sequence[str]) -> int:
    """Run a package function, ``module:function``, with the command's arguments."""
    module_name, _, function = target.partition(":")
    return int(getattr(importlib.import_module(module_name), function)(list(args)) or 0)


def export_templates(args: Sequence[str]) -> int:
    """CI's export step: every shipped template to template, HTML and SVG
    under dist/ci, then the shipped checker over everything written."""
    if ROOT is None:
        print("ERROR: exporting every template needs a checkout", file=sys.stderr)
        return 2
    out = ROOT / EXPORT_DIR
    shutil.rmtree(out, ignore_errors=True)
    templates = sorted((ROOT / TEMPLATES).glob("*.infragram.json"))
    if not templates:
        print(f"ERROR: no templates under {TEMPLATES}", file=sys.stderr)
        return 2
    for template in templates:
        code = call(
            "infragram.cli.user.export_project:main",
            (str(template), "--formats", EXPORT_FORMATS, "--output-dir", str(out), *args),
        )
        if code != 0:
            return code
    written = [
        str(path)
        for suffix in ("*.infragram.json", "*.html", "*.svg")
        for path in sorted(out.glob(suffix))
    ]
    return call("infragram.cli.user.check:main", written)


STEPS: dict[str, Callable[[Sequence[str]], int]] = {
    "export-templates": export_templates,
}


def run_script(script: str, args: Sequence[str]) -> int:
    if script.startswith(CALL_PREFIX):
        return call(script[len(CALL_PREFIX) :], args)
    if script.startswith(PYTEST_PREFIX):
        targets = script[len(PYTEST_PREFIX) :].split()
        return subprocess.run(pytest_argv(targets, args), cwd=ROOT).returncode
    if script.startswith(STEP_PREFIX):
        return STEPS[script[len(STEP_PREFIX) :]](args)
    path = resolve_script(script)
    if path is None:
        print(f"ERROR: script not found under {SCRIPTS}: {script}", file=sys.stderr)
        return 2
    # A test module runs under pytest: run as a plain script, a module that
    # only defines test functions exits 0 having executed none of them, and
    # the gate reports a pass it never earned.
    argv = (
        pytest_argv([str(path)], args)
        if path.name.startswith("test_")
        else [sys.executable, str(path), *args]
    )
    return subprocess.run(argv, cwd=ROOT).returncode


def verify_all_plan() -> list[str]:
    """`verify:all` as CI would write it, one entry per step, so a test can
    hold it against the workflow file: ``scripts/verify/naming.py``,
    ``pytest:tests/unit ...``, ``scripts/tools/generate-nodes.py --check``,
    ``step:export-templates``."""
    plan: list[str] = []
    for script, args in VERIFY_ALL:
        if script.startswith((PYTEST_PREFIX, STEP_PREFIX, CALL_PREFIX)):
            plan.append(" ".join((script, *args)))
        else:
            plan.append(" ".join((f"scripts/{script}", *args)))
    return plan


def _run_gates(gates: Sequence[tuple[str, tuple[str, ...]]], name: str) -> int:
    for index, (script, args) in enumerate(gates, 1):
        rendered = " ".join((script, *args))
        print(f"[{index}/{len(gates)}] {rendered}", flush=True)
        code = run_script(script, args)
        if code != 0:
            print(f"FAIL: {rendered} exited {code}", file=sys.stderr)
            return code
    print(f"OK: all {len(gates)} {name} passed")
    return 0


def verify_all() -> int:
    """Every gate CI's no-browser job runs, in its order: the release check."""
    return _run_gates(VERIFY_ALL, "gates")


def verify_quick() -> int:
    """The per-change check: lint, the tree gates, the suite without its
    slow tests."""
    return _run_gates(VERIFY_QUICK, "quick gates")
