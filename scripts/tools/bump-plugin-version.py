#!/usr/bin/env python3
"""Increment the synchronized plugin manifest and package versions.

The manifest list, semver rule, and bump logic live in
``infragram.registries.manifests`` (shared with ``plugin-package.py``);
this file is the CLI plus the re-exports the test harness imports. The bump
writes the plugin manifests and ``pyproject.toml``. If a changelog is present,
the script notes when its current entry needs updating.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir()) / "src"
    ),
)
from infragram.registries.manifests import (
    CHANGELOG,
    MANIFEST_PATHS as _MANIFEST_LABELS,
    PYPROJECT,
    PackageVersionError,
    bump,
    read_changelog_version,
)

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
#: Historical tuple form kept for existing consumers and tests.
MANIFEST_PATHS = tuple(_MANIFEST_LABELS.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Increment both plugin manifests and pyproject.toml (patch by default)."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--major", action="store_true", help="increment the major version")
    group.add_argument("--minor", action="store_true", help="increment the minor version")
    return parser.parse_args()


def changelog_note(root: Path, version: str) -> str | None:
    """What the changelog still needs, or None when its top entry is *version*."""
    if not (root / CHANGELOG).exists():
        return None
    try:
        top = read_changelog_version(root)
    except PackageVersionError as exc:
        return f"{exc}; add a '## [{version}]' entry before the version gate runs"
    if top != version:
        return (
            f"{CHANGELOG} top entry is [{top}]; add a '## [{version}]' entry above it "
            "before the version gate runs"
        )
    return None


def main() -> int:
    args = parse_args()
    part = "major" if args.major else "minor" if args.minor else "patch"
    try:
        version = bump(ROOT, part)
    except PackageVersionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Updated Claude and Codex plugin manifests and {PYPROJECT} to {version}")
    note = changelog_note(ROOT, version)
    if note:
        print(f"note: {note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
