"""Recognising a Mermaid file takes time in proportion to the file.

A file of %% comment lines with no diagram keyword after them made the old
header pattern backtrack exponentially (CodeQL py/redos): forty lines would
have taken longer than anyone waits. An imported file is untrusted.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from infragram.convert import DiagramError, detect_format


def test_a_file_of_comment_lines_is_refused_at_once(tmp_path: Path) -> None:
    crafted = tmp_path / "notes.txt"
    crafted.write_text("%%\n" * 5000 + "not a diagram", encoding="utf-8")
    start = time.perf_counter()
    with pytest.raises(DiagramError, match="cannot tell what notes.txt is"):
        detect_format(crafted)
    assert time.perf_counter() - start < 1


def test_mermaid_is_still_recognised_after_comments_and_front_matter(tmp_path: Path) -> None:
    for name, text in {
        "plain.txt": "flowchart TD\n  a --> b\n",
        "noted.txt": "%% a note\n%% another\ngraph LR\n  a --> b\n",
        "fronted.txt": "---\ntitle: shop\n---\nflowchart LR\n  a --> b\n",
    }.items():
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        assert detect_format(path) == "mermaid", name
