"""Where compose-time renders live: the user's cache, keyed by spec hash.

``INFRAGRAM_CACHE`` names the root; otherwise the platform's cache directory
(``%LOCALAPPDATA%\\infragram\\cache`` on Windows, ``~/.cache/infragram``
elsewhere). Each render is ``iso3d/<hash>.svg`` beside ``<hash>.ink.json``,
the icon's measured ink profile and edges, so a link seats on a dynamic
render the way it seats on a shipped one.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def cache_root() -> Path:
    """The cache directory, created on first use."""
    override = os.environ.get("INFRAGRAM_CACHE")
    if override:
        root = Path(override)
    elif sys.platform == "win32":
        root = (
            Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            / "infragram"
            / "cache"
        )
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "infragram"
    root.mkdir(parents=True, exist_ok=True)
    return root


def iso_dir() -> Path:
    path = cache_root() / "iso3d"
    path.mkdir(parents=True, exist_ok=True)
    return path


def svg_path(digest: str) -> Path:
    return iso_dir() / f"{digest}.svg"


def ink_path(digest: str) -> Path:
    return iso_dir() / f"{digest}.ink.json"


def read_ink(digest: str) -> dict | None:
    path = ink_path(digest)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_ink(digest: str, entry: dict) -> None:
    ink_path(digest).write_text(json.dumps(entry, sort_keys=True), encoding="utf-8", newline="\n")
