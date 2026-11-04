#!/usr/bin/env python3
r"""Fail when a file's line endings changed, or when one file mixes both.

This repository keeps mixed line endings on purpose. ``core.autocrlf`` is
off, so what is committed is what is checked out: a file written CRLF stays
CRLF while its neighbour stays LF. Nothing enforced that, and the way it
breaks is quiet. An edit script that ends with ``text.replace("\n", "\r\n")``
without asking what the file already used rewrites every line of it. The
content is identical, the diff is the whole file, and a reviewer reads a
thousand changed lines looking for the two that matter.

Two checks, over the files a commit range touched:

1. **The style did not flip.** A file that was CRLF is still CRLF; one that
   was LF is still LF. A new file may be either -- the repository has both --
   but an existing one may not change, because nothing about a real edit
   requires it.
2. **No file mixes the two.** A partial rewrite leaves CRLF in the part it
   touched and LF everywhere else, which no editor shows and every later
   diff carries.

Run with a base ref to check a range, or with no arguments to compare the
working tree against the index -- which is the check to run before
committing, and the one that would have caught this file being written.

    python scripts/verify/line-endings.py            # worktree vs index
    python scripts/verify/line-endings.py HEAD~1     # a commit range
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())

CRLF = b"\r\n"
LF = b"\n"


def git(*args: str) -> str:
    """Run git in the repository and return its stdout."""
    done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout


def style(data: bytes) -> str:
    """``crlf``, ``lf``, ``mixed``, or ``none`` for a file with no newline."""
    crlf = data.count(CRLF)
    lf = data.count(LF) - crlf
    if crlf and lf:
        return "mixed"
    if crlf:
        return "crlf"
    if lf:
        return "lf"
    return "none"


def is_text(data: bytes) -> bool:
    """A NUL byte in the first 8 kB means binary, the rule git uses."""
    return b"\0" not in data[:8000]


def blob(ref: str, path: str) -> bytes | None:
    """One file's bytes at *ref*, or None when it is not there.

    ``:0`` is the index, so the same call compares against a commit or
    against what is staged.
    """
    done = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True)
    return done.stdout if done.returncode == 0 else None


def listing(base: str | None) -> list[str]:
    """The paths to check: a range's changed files, or every tracked file."""
    out = git("diff", "--name-only", "--diff-filter=d", base, "HEAD") if base else git("ls-files")
    return [line for line in out.splitlines() if line]


def current(path: str, base: str | None) -> bytes | None:
    """The file as it is now: at HEAD for a range, else on disk."""
    if base:
        return blob("HEAD", path)
    whole = ROOT / path
    return whole.read_bytes() if whole.is_file() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "base",
        nargs="?",
        default=None,
        help="a ref to compare HEAD against; omitted compares the working tree against the index",
    )
    options = parser.parse_args(argv)

    flipped: list[str] = []
    mixed: list[str] = []
    checked = 0
    for path in listing(options.base):
        after = current(path, options.base)
        if after is None or not is_text(after):
            continue
        checked += 1
        now = style(after)
        if now == "mixed":
            mixed.append(path)
            continue
        before = blob(options.base or ":0", path)
        # A file that is new in this range has nothing to have flipped from.
        if before is None or not is_text(before):
            continue
        was = style(before)
        if was in ("crlf", "lf") and now in ("crlf", "lf") and was != now:
            flipped.append(f"{path}: {was} -> {now}")

    if flipped or mixed:
        print(f"FAIL line endings: {len(flipped)} flipped, {len(mixed)} mixed")
        for item in flipped[:30]:
            print(f"  - flipped  {item}")
        for item in mixed[:30]:
            print(f"  - mixed    {item}")
        extra = max(0, len(flipped) - 30) + max(0, len(mixed) - 30)
        if extra:
            print(f"  ... {extra} more")
        print()
        print("This repository keeps both styles on purpose. Read a file's bytes,")
        print("keep the endings it already has, and write it back the same way.")
        return 1

    where = f"{options.base}..HEAD" if options.base else "worktree vs index"
    print(f"OK line endings: {checked} text files ({where}), none flipped, none mixed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
