"""Repository chores that are neither a build nor a gate."""

from __future__ import annotations

__all__ = ["COMMANDS"]

#: command -> (script path relative to scripts/, help text)
COMMANDS: dict[str, tuple[str, str]] = {
    "bump": (
        "tools/bump-plugin-version.py",
        "bump the synchronized plugin manifest and pyproject versions",
    ),
}
