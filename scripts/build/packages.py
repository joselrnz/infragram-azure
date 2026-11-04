#!/usr/bin/env python3
"""Build what a release publishes, into ``dist/packages``; publish nothing.

- the npm package: the plugin folder as ``npm pack`` makes it (the
  ``files`` list in ``plugin/package.json``), which Claude Code
  (``claude plugin install infragram-azure@npm``), Codex marketplaces and
  Pi (``pi install npm:infragram-azure``) install;
- the wheel and the sdist: the Python package, which carries the plugin
  whole (``infragram plugin:install`` registers it with an agent).

A tool that is not on the PATH is named and its package skipped: npm for the
npm package, uv for the sdist (pip builds the wheel without it).

Usage::

    python -m infragram build:packages [--out dist/packages]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
PLUGIN = ROOT


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def build(out: Path) -> tuple[list[Path], list[str]]:
    """The packages built into *out*, and a note for each one that was not."""
    out.mkdir(parents=True, exist_ok=True)
    built: list[Path] = []
    notes: list[str] = []
    npm = shutil.which("npm")
    if npm is None:
        notes.append("no npm on the PATH: the npm package was not built")
    else:
        done = _run([npm, "pack", "--pack-destination", str(out)], PLUGIN)
        if done.returncode:
            raise SystemExit(f"FAIL npm pack\n{done.stdout[-1500:]}{done.stderr[-1500:]}")
        built.append(out / done.stdout.strip().splitlines()[-1])
    uv = shutil.which("uv")
    if uv is not None:
        done = _run([uv, "build", "--out-dir", str(out)], PLUGIN)
    else:
        notes.append("no uv on the PATH: the sdist was not built (pip builds the wheel)")
        done = _run(
            [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-q", "-w", str(out)], PLUGIN
        )
    if done.returncode:
        raise SystemExit(f"FAIL the Python build\n{done.stdout[-1500:]}{done.stderr[-1500:]}")
    built += sorted(out.glob("infragram-*.whl")) + sorted(out.glob("infragram-*.tar.gz"))
    return list(dict.fromkeys(built)), notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="infragram build:packages", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "dist" / "packages",
        help="where the packages go (default: dist/packages)",
    )
    options = parser.parse_args(argv)
    built, notes = build(options.out.resolve())
    for path in built:
        print(f"BUILT    {path} ({path.stat().st_size / 1e6:.1f} MB)")
    for note in notes:
        print(f"NOTE     {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
