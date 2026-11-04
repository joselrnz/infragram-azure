"""Write generated UTF-8 text without changing an existing file's line endings."""

from __future__ import annotations

from pathlib import Path


def write_generated_text(path: Path, contents: str) -> None:
    """Keep an existing LF or CRLF convention; new files use LF everywhere."""
    try:
        previous = path.read_bytes()
    except FileNotFoundError:
        previous = b""
    first_lf = previous.find(b"\n")
    newline = "\r\n" if first_lf > 0 and previous[first_lf - 1] == 13 else "\n"
    path.write_text(contents.replace("\r\n", "\n"), encoding="utf-8", newline=newline)
