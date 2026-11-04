#!/usr/bin/env python3
"""Fail when a package the lock pins has a published vulnerability.

``uv.lock`` pins every package the plugin can install, for every extra and
every platform: pydantic for everyone, Playwright and Pillow for pictures,
the test tools for development. pip-audit reads each pinned version against
the advisories published for it (the Python Packaging Advisory Database,
through PyPI) and fails on any it finds. It resolves nothing itself: the
versions are the lock's, so what it checks is what `uv sync` installs.
tests/unit/test_lockfile.py holds the lock to plugin/pyproject.toml, so the
versions checked are the ones the package asks for.

It needs the network, so ``verify:quick`` leaves it out; ``verify:all`` and
CI run it. pip-audit comes with the ``test`` extra.

    python scripts/verify/audit.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
LOCK = ROOT / "uv.lock"


def pinned(lock: Path = LOCK) -> list[str]:
    """A requirement line for every package the lock takes from an index:
    ``name==version`` with the hash of each file the lock accepts for it. The
    project itself is a folder in the tree, not a release anyone publishes."""
    lines = []
    for package in tomllib.loads(lock.read_text(encoding="utf-8")).get("package", []):
        if "registry" not in package.get("source", {}):
            continue
        files = [package.get("sdist", {}), *package.get("wheels", [])]
        hashes = sorted({file["hash"] for file in files if "hash" in file})
        lines.append(
            " ".join(
                [
                    f"{package['name']}=={package['version']}",
                    *(f"--hash={digest}" for digest in hashes),
                ]
            )
        )
    return sorted(lines)


def main(argv: list[str] | None = None) -> int:
    if importlib.util.find_spec("pip_audit") is None:
        print(
            'FAIL audit: pip-audit is not installed; python -m pip install -e "./plugin[test]"',
            file=sys.stderr,
        )
        return 2
    requirements = pinned()
    if not requirements:
        print(f"FAIL audit: {LOCK.name} pins no package from an index", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="infragram-audit-") as scratch:
        listing = Path(scratch) / "requirements.txt"
        listing.write_text("\n".join(requirements) + "\n", encoding="utf-8")
        # --disable-pip with every file hashed: the lock already names every
        # package, so pip-audit checks the list as given instead of resolving
        # it again. --strict: a package it could not look up is a failure,
        # not a pass nobody earned. Its cache is the run's own, so a stale
        # entry from another run is never read.
        done = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "--requirement",
                str(listing),
                "--disable-pip",
                "--strict",
                "--progress-spinner",
                "off",
                "--cache-dir",
                str(Path(scratch) / "cache"),
                *(argv or []),
            ],
            check=False,
        )
    if done.returncode:
        print(
            f"FAIL audit: pip-audit reports the packages above ({len(requirements)} pinned)",
            file=sys.stderr,
        )
        return done.returncode
    print(f"OK audit: no known vulnerability in the {len(requirements)} packages {LOCK.name} pins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
