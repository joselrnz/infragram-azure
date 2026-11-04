"""Keep the Azure edition's discovery workflow available in every installation."""

from __future__ import annotations

import runpy

from ...paths import plugin_root

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Run the shipped Azure importer without changing the user's directory."""
    namespace = runpy.run_path(str(plugin_root() / "scripts" / "export" / "azure.py"))
    return int(namespace["main"](argv) or 0)
