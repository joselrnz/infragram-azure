"""Regenerating what is committed but derived."""

from __future__ import annotations

__all__ = ["COMMANDS"]

#: command -> (script path relative to scripts/, help text)
COMMANDS: dict[str, tuple[str, str]] = {
    "gen:nodes": ("tools/generate-nodes.py", "regenerate the node classes from the icon catalogs"),
    "gen:ink": (
        "tools/ink-profiles.py",
        "measure where each icon's ink starts, so a wire touches the mark (pass --check)",
    ),
}
