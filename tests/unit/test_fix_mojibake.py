#!/usr/bin/env python3
"""Regression tests for the mojibake repair utility."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
SCRIPT = ROOT / "scripts" / "tools" / "fix-mojibake.py"


def run(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *map(str, paths)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    """A scratch directory for the fixture files these tests write.

    main() below supplies one when the file runs as a script. Under pytest
    nothing did, so all three tests reported as errors -- quiet enough that
    they stopped running without anyone noticing.
    """
    return tmp_path


def test_arrows(directory: Path) -> None:
    # These are the strings produced when UTF-8 arrow bytes are decoded as
    # Windows-1252. Bytes 0x90/0x9D are undefined in CP1252, hence the
    # explicit escapes (the third characters are invisible C1 controls).
    source = "right \u00e2\u2020\u2019, left \u00e2\u2020\u0090, up \u00e2\u2020\u2018, down \u00e2\u2020\u201c\n"
    expected = "right \u2192, left \u2190, up \u2191, down \u2193\n"
    path = directory / "arrows.md"
    path.write_text(source, encoding="utf-8")
    result = run(path)
    if result.returncode != 0:
        raise AssertionError(f"repair failed: {result.stdout}{result.stderr}")
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def test_dropped_9d_fallback(directory: Path) -> None:
    # cp1252 round-trips can drop the undefined 0x9D byte, leaving only the
    # two-character remnant of a right double quote. The fallback pair must
    # repair the remnant WITHOUT eating longer sequences that share the same
    # prefix (here: a full left-double-quote sequence in the same file).
    source = "said \u00e2\u20ac\u0153hi\u00e2\u20ac and left\n"
    expected = "said \u201chi\u201d and left\n"
    path = directory / "fallback.md"
    path.write_text(source, encoding="utf-8")
    result = run(path)
    if result.returncode != 0:
        raise AssertionError(f"fallback repair failed: {result.stdout}{result.stderr}")
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def test_failure_reporting(directory: Path) -> None:
    # A file that is not valid UTF-8 must be reported and reflected in the
    # exit code, while other files on the same invocation are still repaired.
    broken = directory / "broken.md"
    broken.write_bytes(b"\xff\xfe invalid utf-8 \xff")
    fixable = directory / "fixable.md"
    fixable.write_text("dash \u00e2\u20ac\u201d here\n", encoding="utf-8")
    result = run(broken, fixable)
    if result.returncode != 1:
        raise AssertionError(f"expected exit 1, got {result.returncode}: {result.stderr}")
    if "FAILED" not in result.stderr:
        raise AssertionError(f"failure was not reported on stderr: {result.stderr!r}")
    if fixable.read_text(encoding="utf-8") != "dash \u2014 here\n":
        raise AssertionError("valid sibling file was not repaired on a partial failure")
    if broken.read_bytes() != b"\xff\xfe invalid utf-8 \xff":
        raise AssertionError("undecodable file must be left untouched")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="infragram-mojibake-") as directory:
        root = Path(directory)
        test_arrows(root)
        test_dropped_9d_fallback(root)
        test_failure_reporting(root)
    print("PASS: mojibake sequences repair, remnants fall back, failures exit non-zero")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
