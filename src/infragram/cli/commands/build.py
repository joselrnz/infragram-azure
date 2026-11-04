"""Fetching and normalising the artwork the libraries are built from, and
building the packages a release publishes (the plugin is the repository root).
"""

from __future__ import annotations

__all__ = ["COMMANDS"]

#: command -> (script path relative to scripts/, help text)
COMMANDS: dict[str, tuple[str, str]] = {
    "build:icons": ("build/icons.py", "fetch/normalize the primitive icon set"),
    "build:index": ("build/provider-index.py", "rebuild the merged icon index"),
    "build:tiles": ("build/vendor-tiles.py", "rebuild the provider tile artwork"),
    "build:packages": (
        "build/packages.py",
        "build the npm package, the wheel and the sdist into dist/packages; publish nothing",
    ),
}
