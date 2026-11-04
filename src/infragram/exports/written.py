"""Which files this tool wrote, and nobody has touched since.

Every export and import refused to replace an existing file without
``--force``, so the everyday loop -- edit the diagram file, export again --
needed the flag every time, and a flag passed every time protects nothing.
The refusal is kept for what it is for: a file someone else wrote, or one of
ours that was edited after it was written (a page saved from the editor, a
diagram file changed by hand). Everything else is replaced quietly.

The record lives in the user's cache (``INFRAGRAM_CACHE``, see
iso3d/cache.py), never beside the diagram, so an export folder that is
committed carries nothing but the diagram. One small JSON file per output
folder maps each file's name to the SHA-256 of what was written; a folder
(the Terraform skeletons) is hashed over its files' relative paths and
contents, so a file added, changed or removed inside it counts as an edit.
A folder copied to another machine has no record there, and is refused as
before: the safe side.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from pathlib import Path


def digest(path: Path) -> str:
    """SHA-256 of a file's bytes, or of a folder's files and their paths."""
    sha = hashlib.sha256()
    if path.is_dir():
        for item in sorted(p for p in path.rglob("*") if p.is_file()):
            sha.update(item.relative_to(path).as_posix().encode("utf-8") + b"\0")
            sha.update(hashlib.sha256(item.read_bytes()).digest())
        return "dir:" + sha.hexdigest()
    sha.update(path.read_bytes())
    return sha.hexdigest()


def _record(folder: Path) -> Path:
    from ..iso3d.cache import cache_root

    key = os.path.normcase(str(folder.resolve()))
    root = cache_root() / "written"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()[:32]}.json"


def _load(folder: Path) -> dict[str, str]:
    try:
        data = json.loads(_record(folder).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    files = data.get("files") if isinstance(data, dict) else None
    return {str(k): str(v) for k, v in files.items()} if isinstance(files, dict) else {}


def untouched(path: Path) -> bool:
    """Whether *path* is exactly what this tool last wrote there."""
    recorded = _load(path.parent).get(path.name)
    if not recorded or not path.exists():
        return False
    try:
        return digest(path) == recorded
    except OSError:
        return False


def blocking(paths: Iterable[Path]) -> list[Path]:
    """The existing paths among *paths* that replacing would lose work in."""
    return sorted(path for path in paths if path.exists() and not untouched(path))


def remember(paths: Iterable[Path]) -> None:
    """Record what was just written, folder by folder. Best effort: a cache
    that cannot be written only means the next export asks for --force."""
    by_folder: dict[Path, list[Path]] = {}
    for path in paths:
        if path.exists():
            by_folder.setdefault(path.parent, []).append(path)
    for folder, written in by_folder.items():
        try:
            # Lookup and hashing can fail just as writing the cache can:
            # the export is already committed, so none may turn it into a failure.
            files = _load(folder)
            files.update({path.name: digest(path) for path in written})
            # Drop names whose file is gone, keeping the record scoped to this folder.
            files = {
                name: value for name, value in sorted(files.items()) if (folder / name).exists()
            }
            record = _record(folder)
            text = json.dumps(
                {"version": 1, "folder": str(folder.resolve()), "files": files}, indent=1
            )
            staging = record.with_suffix(f".{os.getpid()}.tmp")
            staging.write_text(text + "\n", encoding="utf-8", newline="\n")
            os.replace(staging, record)
        except OSError:
            pass


def write_side_file(path: Path, text: str, *, force: bool) -> None:
    """Write a file a command writes beside its export -- a CSV, a pull request
    comment -- under the same rule: a folder is refused, and so is a file this
    tool did not write or that was edited since, unless *force*. Raises
    ValueError with what to do."""
    if path.is_dir():
        raise ValueError(f"{path} is a folder; name the file to write")
    if not force and blocking([path]):
        raise ValueError(
            f"refusing to overwrite {path}: this tool did not write it, or it was edited since "
            "(pass --force to replace it)"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    remember([path])
