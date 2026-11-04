"""The gate that keeps this repository's mixed line endings the way they are.

``core.autocrlf`` is off here, so what is committed is what is checked out:
a file written CRLF stays CRLF while its neighbour stays LF. Nothing enforced
that until an edit script ended with ``text.replace("\\n", "\\r\\n")`` without
asking what the file already used, rewrote every line of a LF module, and
produced a diff of the whole file around a two-line change.

These check the gate itself, because a gate nobody tests is a gate that
reports a pass it never earned.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
GATE = ROOT / "scripts" / "verify" / "line-endings.py"


def _gate():
    """The gate module, loaded from its hyphenated path."""
    spec = importlib.util.spec_from_file_location("line_endings_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"a\r\nb\r\n", "crlf"),
        (b"a\nb\n", "lf"),
        (b"a\r\nb\n", "mixed"),
        (b"a\nb\r\n", "mixed"),
        (b"no newline at all", "none"),
        (b"", "none"),
    ],
)
def test_style_names_what_a_file_uses(data: bytes, expected: str) -> None:
    assert _gate().style(data) == expected


def test_a_lone_carriage_return_is_not_counted_as_a_line_ending() -> None:
    """An old-Mac CR, or a CR inside a string, is not a CRLF."""
    assert _gate().style(b"a\rb\n") == "lf"


def test_binary_is_left_alone() -> None:
    """A PNG is full of both bytes and means neither."""
    gate = _gate()
    assert not gate.is_text(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    assert gate.is_text(b"def main():\n    return 0\n")


def test_the_gate_fails_on_a_flip_and_passes_once_it_is_undone(tmp_path: Path) -> None:
    """The whole point, exercised end to end in a throwaway repository."""
    repo = tmp_path / "repo"
    (repo / ".claude-plugin").mkdir(parents=True)
    (repo / ".claude-plugin" / "plugin.json").write_bytes(b"{}\n")
    (repo / "scripts" / "verify").mkdir(parents=True)
    (repo / "scripts" / "verify" / "line-endings.py").write_bytes(GATE.read_bytes())
    lf_file = repo / "module.py"
    lf_file.write_bytes(b"one\ntwo\nthree\n")

    def run_git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    run_git("init", "-q")
    run_git("config", "core.autocrlf", "false")
    run_git("config", "user.email", "gate@example.invalid")
    run_git("config", "user.name", "Gate")
    run_git("add", "-A")
    run_git("commit", "-qm", "first")

    def gate() -> subprocess.CompletedProcess:
        return subprocess.run(
            ["python", str(repo / "scripts" / "verify" / "line-endings.py")],
            cwd=repo,
            capture_output=True,
            text=True,
        )

    assert gate().returncode == 0, "a clean tree must pass"

    lf_file.write_bytes(b"one\r\ntwo\r\nthree\r\n")
    flipped = gate()
    assert flipped.returncode == 1
    assert "module.py: lf -> crlf" in flipped.stdout

    lf_file.write_bytes(b"one\ntwo\nthree\n")
    assert gate().returncode == 0, "undoing the flip must clear it"

    lf_file.write_bytes(b"one\r\ntwo\nthree\n")
    both = gate()
    assert both.returncode == 1
    assert "mixed    module.py" in both.stdout


def test_the_gate_is_registered_so_it_actually_runs() -> None:
    """A gate that no command and no CI step calls protects nothing."""
    from infragram.cli import COMMANDS, VERIFY_ALL
    from infragram.cli.commands.verify import VERIFY_QUICK

    assert COMMANDS["verify:line-endings"][0] == "verify/line-endings.py"
    assert ("verify/line-endings.py", ()) in VERIFY_ALL
    assert ("verify/line-endings.py", ()) in VERIFY_QUICK
    # Both workflows, because this repository has two and only one of them
    # runs. `.forgejo/` is the live one -- its own header says so -- and
    # `.github/` is the mirror. Checking the mirror alone is how this gate sat
    # out of the CI that runs for three releases while this test passed.
    workflows = sorted(ROOT.glob(".*/workflows/ci.yml"))
    assert len(workflows) >= 2, [str(w) for w in workflows]
    for workflow in workflows:
        text = workflow.read_text(encoding="utf-8")
        # verify:quick runs the gate too (asserted above)
        assert "scripts/verify/line-endings.py" in text or "infragram verify:quick" in text, (
            f"{workflow.relative_to(ROOT)} does not run the gate"
        )
