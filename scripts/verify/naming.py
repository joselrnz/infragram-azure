#!/usr/bin/env python3
"""Fail if the tree carries anything that must not ship in this product.

Three classes of leak, checked over tracked files plus untracked, non-ignored
files so a local run catches a stray mention before it is committed:

1. The name of the editorial diagram skill this repository was carved out of.
2. The name of the client project whose production diagrams were removed -
   infragram ships the base (shell, libraries, frames), never a customer's
   estate.
3. Machine-specific paths (a user's home directory on Windows, macOS, or
   Linux), which only appear when private working files leak into shipped
   content.
4. The name of a person with no part in this project, which arrived in a
   licence header from whatever template the repository was started from and
   was still claiming copyright over the whole of it.

The forbidden words are assembled at runtime so this gate cannot trip on its
own source. File names are checked as well as contents.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())

# Assembled from pieces so no forbidden sequence appears literally in this file.
_SEGMENT = r"[^\\/\s\"'<>]+"
_SLASHES = r"[\\/]+"
_HOME_DIRECTORIES = (
    r"\b[A-Za-z]:" + _SLASHES + "Users" + _SLASHES + _SEGMENT,  # Windows profile
    r"(?<![\w.-])" + "/" + "Users" + "/" + _SEGMENT,  # macOS home
    r"(?<![\w.-])" + "/" + "home" + "/" + _SEGMENT,  # Linux home
)
#: A name that arrived with a template this repository was started from and
#: belonged to nobody here. Both words are required, so the gate cannot trip
#: on the letters appearing by chance inside a base64 image payload.
_STRAY_HOLDER = "Cath" + "ryn" + r"\s+" + "Lav" + "ery"
FORBIDDEN = (
    ("the previous product name", re.compile("figure" + r"[-_ ]?" + "room", re.IGNORECASE)),
    ("a client project name", re.compile("hire" + r"[-_ ]?" + "reset", re.IGNORECASE)),
    ("a machine-specific path", re.compile("(?:" + "|".join(_HOME_DIRECTORIES) + ")")),
    ("a person who has no part in this project", re.compile(_STRAY_HOLDER, re.IGNORECASE)),
)


def tracked_and_untracked() -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    return sorted({rel for rel in listing.split("\0") if rel})


def main() -> int:
    hits: list[str] = []
    files = tracked_and_untracked()
    for rel in files:
        for label, pattern in FORBIDDEN:
            if pattern.search(rel):
                hits.append(f"{rel} (file name carries {label})")
        path = ROOT / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8000]:
            continue
        for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            for label, pattern in FORBIDDEN:
                if pattern.search(line):
                    hits.append(f"{rel}:{number}: {label}: {line.strip()[:100]}")
    if hits:
        print(f"FAIL naming: {len(hits)} leak(s) that must not ship")
        for hit in hits[:50]:
            print(f"  - {hit}")
        if len(hits) > 50:
            print(f"  ... {len(hits) - 50} more")
        return 1
    print(
        f"OK naming: {len(files)} files, no previous product name, "
        "no client project names, no machine-specific paths, "
        "no unrelated copyright holder"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
