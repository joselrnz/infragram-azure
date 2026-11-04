"""``infragram check``: validate documents and exported pages with the checker
the skill ships, the same code an agent runs without the package.

A Python diagram file is not a document: the checker proper would read it as
JSON. The package reads one without running it -- syntax, names never
defined, node classes the module it names does not hold -- and says that the
picture is ``compose --verify``'s to check.
"""

from __future__ import annotations

import sys
from pathlib import Path

__all__ = ["main"]


def _diagram_file(path: Path) -> tuple[bool, str]:
    from ...compose.diagram_file import static_findings

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return False, f"FAIL {path}: cannot read file ({error})"
    findings = static_findings(path, text)
    if findings is None:
        return False, (
            f"FAIL {path}: not a diagram file (it opens no `with Diagram(...)` and "
            "assigns no PROJECT); check reads documents, pages and pictures"
        )
    if findings:
        return False, (
            f"FAIL {path}: {len(findings)} problem(s), read without running it\n"
            + "\n".join(f"  - {finding}" for finding in findings[:20])
        )
    return True, (
        f"OK {path}: diagram file, read without running it (syntax, names, node classes); "
        "`compose` it with --verify to check what it draws"
    )


def _json(diagrams: list[Path], others: list[str]) -> int:
    """One JSON document for everything checked: the checker's own for
    documents, pages and pictures, with the diagram files read beside it."""
    import contextlib
    import io
    import json

    from .checker import checker

    reports: list[dict[str, object]] = []
    for path in diagrams:
        ok, message = _diagram_file(path)
        problems = [
            line.strip()[2:] for line in message.splitlines()[1:] if line.strip().startswith("- ")
        ]
        if not ok and not problems:
            problems = [message.split(": ", 1)[-1]]
        reports.append(
            {
                "path": str(path),
                "kind": "diagram",
                "ok": ok,
                "problems": problems,
                "summary": {},
                "message": message,
            }
        )
    failed = not all(report["ok"] for report in reports)
    if others or not diagrams:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            code = checker().main([*others, "--json"])
        reports += json.loads(captured.getvalue())["files"]
        failed = failed or bool(code)
    checker().utf8_output()
    print(json.dumps({"ok": not failed, "files": reports}, indent=1, default=str))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    from .checker import checker

    arguments = list(sys.argv[1:] if argv is None else argv)
    if any(argument in ("-h", "--help") for argument in arguments):
        return checker().main(arguments)
    diagrams = [
        Path(argument)
        for argument in arguments
        if argument.endswith(".py") and Path(argument).is_file()
    ]
    others = [
        argument
        for argument in arguments
        if not (argument.endswith(".py") and Path(argument).is_file())
    ]
    if "--json" in others:
        return _json(diagrams, [argument for argument in others if argument != "--json"])
    failed = False
    if diagrams:
        checker().utf8_output()
        for path in diagrams:
            ok, message = _diagram_file(path)
            print(message)
            failed = failed or not ok
    if others or not diagrams:
        failed = bool(checker().main(others)) or failed
    return 1 if failed else 0
