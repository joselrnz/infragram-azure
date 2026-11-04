"""The component inventory: rebuilding it, and checking the
committed copy is current.
"""

from __future__ import annotations

__all__ = ["COMMANDS"]

#: command -> (script path relative to scripts/, help text)
COMMANDS: dict[str, tuple[str, str]] = {
    "inventory": (
        "inventory/build.py",
        "regenerate the component inventory (assets/catalog/inventory.json + references/inventory.md)",
    ),
    "verify:inventory": (
        "inventory/build.py",
        "check the committed inventory is current and every icon decodes (passes --check itself)",
    ),
}
