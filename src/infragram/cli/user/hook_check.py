"""``infragram hook:check``: the plugin's check hook.

Claude Code and Codex run it after the agent writes or edits a file
(``PostToolUse``), with the tool call as JSON on stdin: Claude Code's
``Write``/``Edit``/``MultiEdit`` name the file in ``tool_input.file_path``,
Codex's ``apply_patch`` in the patch it ran (``tool_input.command``).

- A ``.infragram.json`` document is checked by the shipped checker.
- A Python diagram file -- one that imports ``infragram`` and, at its top
  level, opens ``with Diagram(...)`` or assigns ``PROJECT`` -- is read, never
  run: a file the agent may write is not a file the hook may execute, or
  permission to write would be permission to run code unasked. What reading
  finds is a syntax error, a name used and never defined (``Edgee``), and a
  node class the module it names does not hold (``compute.RDS``, with where
  it does live). Building the diagram, and every check of its picture, is
  ``compose --verify``'s, which the user approves.
- Every other file passes at once.

What it finds goes back to the agent as a block, with the findings, so it
fixes them before moving on. A diagram that passes, and every other file,
says nothing. It never fails the tool call it follows: whatever goes wrong
inside the hook, it exits 0.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
from pathlib import Path

from ...compose.diagram_file import static_findings

__all__ = ["main", "static_findings", "written_paths"]

#: The lines of an ``apply_patch`` patch that name a file it leaves on disk.
_PATCH_FILE = re.compile(r"^\*\*\* (?:Add File|Update File|Move to): (.+?)\s*$", re.MULTILINE)


def written_paths(event: dict) -> list[Path]:
    """The files a tool call wrote, as the hook event names them, resolved
    against the session's folder."""
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    names: list[str] = []
    for key in ("file_path", "path"):
        if isinstance(tool_input.get(key), str):
            names.append(tool_input[key])
    command = tool_input.get("command")
    if isinstance(command, str) and "*** Begin Patch" in command:
        names += _PATCH_FILE.findall(command)
    base = Path(event["cwd"]) if isinstance(event.get("cwd"), str) else Path.cwd()
    return list(dict.fromkeys((base / name).resolve() for name in names))


def _check(path: Path) -> str | None:
    """The findings for one written file, or None when it passes or is no diagram."""
    if path.name.endswith(".infragram.json"):
        if not path.is_file():
            return None
        from .checker import checker

        ok, text = checker().check_path(path)
        return None if ok else text
    if path.suffix != ".py" or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    findings = static_findings(path, text)
    if not findings:
        return None
    return f"FAIL {path}: {len(findings)} problem(s), read without running it\n" + "\n".join(
        f"  - {finding}" for finding in findings[:20]
    )


def main(argv: list[str] | None = None) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        event = json.loads(sys.stdin.read() or "{}")
        if not isinstance(event, dict):
            return 0
        # stdout carries the hook's answer and nothing else
        with contextlib.redirect_stdout(sys.stderr):
            findings = [text for path in written_paths(event) if (text := _check(path)) is not None]
    except BaseException as error:  # noqa: BLE001 - the hook never fails the call it follows
        print(f"infragram hook:check did not run: {type(error).__name__}: {error}", file=sys.stderr)
        return 0
    if findings:
        reason = (
            "Infragram's checker found problems in the diagram just written; fix them "
            "before exporting it:\n" + "\n".join(findings)
        )
        print(json.dumps({"decision": "block", "reason": reason}))
    return 0
