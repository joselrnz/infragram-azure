"""Bringing reviewed vendor artwork in from its source."""

from __future__ import annotations

__all__ = ["COMMANDS"]

#: command -> (script path relative to scripts/, help text)
COMMANDS: dict[str, tuple[str, str]] = {
    "import:brand-icons": (
        "importers/brand-icons.py",
        "import reviewed brand icons from the source vault",
    ),
    "import:official-icons": (
        "importers/official-icons.py",
        "import reviewed official icons from the source vault",
    ),
}
