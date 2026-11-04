"""The version this copy of infragram reports."""

from __future__ import annotations

import json

from ..paths import MANIFEST, plugin_root

__all__ = ["package_version"]


def package_version() -> str:
    """The plugin manifest's version (a checkout, an agent's install, or the
    plugin folder a wheel carries), else the installed distribution's, or
    ``unknown``."""
    try:
        manifest = json.loads((plugin_root() / MANIFEST).read_text(encoding="utf-8"))
        return str(manifest["version"])
    except (OSError, RuntimeError, ValueError, KeyError):
        pass
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - the standard library always has it
        return "unknown"
    try:
        return version("infragram-azure")
    except PackageNotFoundError:
        return "unknown"
