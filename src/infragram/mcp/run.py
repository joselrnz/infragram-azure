"""Running one tool: its arguments held to its schema, its command run in the
folder the server started in, and what the command printed read back as data.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .tools import ArgumentError, Tool

#: How long one command may run: a PNG renders in a browser, a Terraform check plans.
COMMAND_TIMEOUT = 900
#: The widest preview a tool attaches; a wider PNG is scaled down when Pillow is there.
PREVIEW_WIDTH = 1600
#: The largest preview attached as it is, when it cannot be scaled down.
PREVIEW_BYTES = 2_000_000

#: A line an export or import prints for a file: ``SVG      path (123 bytes)``.
_WROTE = re.compile(r"^([A-Z][A-Z0-9-]{1,11})\s+(\S.*?)(?: \(([^()]*)\))?$")
#: A line the checker prints for a file: ``OK path: summary`` or ``FAIL path: problem``.
_VERDICT = re.compile(r"^(OK|FAIL|ERROR)\s+(\S.*?): (.*)$")


def _read_output(text: str, cwd: Path) -> dict[str, list[Any]]:
    """The files, verdicts, notes and errors a command printed, as data."""
    files: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    notes: list[str] = []
    errors: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.rstrip()
        if line.startswith(("ERROR:", "FAIL:")):
            errors.append(line.split(":", 1)[1].strip())
            continue
        verdict = _VERDICT.match(line)
        if verdict:
            checks.append(
                {"path": verdict[2], "ok": verdict[1] == "OK", "message": verdict[3].strip()}
            )
            continue
        wrote = _WROTE.match(line)
        if not wrote:
            continue
        kind, rest = wrote[1], wrote[2]
        if kind in ("NOTE", "WARN", "WARNING", "OVERRIDE", "READ", "PROJECT"):
            notes.append(line.split(None, 1)[1] if " " in line else line)
            continue
        path = (cwd / rest).resolve() if not Path(rest).is_absolute() else Path(rest)
        if path.is_file() and str(path) not in seen:
            seen.add(str(path))
            files.append({"kind": kind, "path": rest, "bytes": path.stat().st_size})
    return {"files": files, "checks": checks, "notes": notes, "errors": errors}


def _check_output(stdout: str) -> dict[str, list[Any]] | None:
    """What ``check --json`` printed, as the tool's data; None when it printed no report."""
    try:
        report = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(report, dict) or not isinstance(report.get("files"), list):
        return None
    checks = [
        {
            "path": str(entry.get("path", "")),
            "ok": bool(entry.get("ok")),
            "message": str(entry.get("message", "")),
            "kind": str(entry.get("kind", "")),
            "problems": [str(problem) for problem in entry.get("problems") or []],
        }
        for entry in report["files"]
        if isinstance(entry, dict)
    ]
    return {"files": [], "checks": checks, "notes": [], "errors": []}


def _check_text(checks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for check in checks:
        lines.append(check["message"] or f"{'OK' if check['ok'] else 'FAIL'} {check['path']}")
        lines += [
            f"  - {problem}" for problem in check.get("problems", []) if problem not in lines[-1]
        ]
    return "\n".join(lines)


def _preview(files: list[dict[str, Any]], cwd: Path) -> tuple[dict[str, Any] | None, str]:
    """The first PNG written as an image block, scaled to PREVIEW_WIDTH; or why there is none."""
    png = next((entry for entry in files if entry["path"].lower().endswith(".png")), None)
    if png is None:
        return None, "no PNG was written to preview; add png to formats"
    path = Path(png["path"]) if Path(png["path"]).is_absolute() else cwd / png["path"]
    data = path.read_bytes()
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            if image.width > PREVIEW_WIDTH:
                image.thumbnail((PREVIEW_WIDTH, PREVIEW_WIDTH * 4))
                out = io.BytesIO()
                image.save(out, format="PNG", optimize=True)
                data = out.getvalue()
    except ImportError:
        if len(data) > PREVIEW_BYTES:
            return None, f"{png['path']} is too large to preview without Pillow"
    block = {
        "type": "image",
        "data": base64.b64encode(data).decode("ascii"),
        "mimeType": "image/png",
    }
    return block, ""


# ------------------------------------------------------------ running a tool
class Answer(BaseModel):
    """What a tool call answers: its text, its data, any image, and whether it failed."""

    text: str
    #: The ``structuredContent``; None for a failure the tool's own schema has no room for.
    data: dict[str, Any] | None
    failed: bool = False
    image: dict[str, Any] | None = None

    def result(self) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": self.text}]
        if self.image is not None:
            content.append(self.image)
        out: dict[str, Any] = {"content": content, "isError": self.failed}
        if self.data is not None:
            out["structuredContent"] = self.data
        return out


def _arguments(tool: Tool, args: dict[str, Any]) -> dict[str, Any]:
    """The arguments as the tool's schema takes them: a single path where a
    list is asked is a list of one, and anything of another type, a name the
    schema does not know or a value outside its choices is refused."""
    unknown = sorted(set(args) - set(tool.properties))
    if unknown:
        raise ArgumentError(f"{tool.name} takes no {', '.join(unknown)}")
    clean: dict[str, Any] = {}
    for key, value in args.items():
        schema = tool.properties[key]
        kind = schema.get("type")
        if value is None:
            continue
        if kind == "array":
            items = [value] if isinstance(value, str) else value
            if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
                raise ArgumentError(f"{key} is a list of paths or names")
            value = items
        elif kind == "string":
            if not isinstance(value, str):
                raise ArgumentError(f"{key} is text")
            if "enum" in schema and value not in schema["enum"]:
                raise ArgumentError(f"{key} is one of {', '.join(schema['enum'])}, not {value!r}")
        elif kind == "boolean" and not isinstance(value, bool):
            raise ArgumentError(f"{key} is true or false")
        elif kind == "integer" and (
            isinstance(value, bool) or not isinstance(value, int) or value < schema["minimum"]
        ):
            raise ArgumentError(f"{key} is a whole number, {schema['minimum']} or more")
        elif kind == "number" and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not _in_range(schema, value)
        ):
            raise ArgumentError(f"{key} is a number {_range_text(schema)}")
        clean[key] = value
    missing = [
        key
        for key in tool.required
        if not (clean.get(key) if not isinstance(clean.get(key), str) else clean[key].strip())
    ]
    if missing:
        raise ArgumentError(f"missing argument: {', '.join(missing)}")
    return clean


def _command_data(command: str, exit_code: int, errors: list[str]) -> dict[str, Any]:
    return {
        "command": command,
        "exit_code": exit_code,
        "ok": False,
        "files": [],
        "checks": [],
        "notes": [],
        "errors": errors,
    }


def _in_range(schema: dict[str, Any], value: float) -> bool:
    """Whether *value* keeps the bounds a number's schema sets, whichever it sets."""
    return (
        ("minimum" not in schema or value >= schema["minimum"])
        and ("maximum" not in schema or value <= schema["maximum"])
        and ("exclusiveMinimum" not in schema or value > schema["exclusiveMinimum"])
    )


def _range_text(schema: dict[str, Any]) -> str:
    if "minimum" in schema and "maximum" in schema:
        return f"from {schema['minimum']} through {schema['maximum']}"
    if "exclusiveMinimum" in schema:
        return f"greater than {schema['exclusiveMinimum']}"
    return f"of at least {schema.get('minimum', 0)}"


def _failure(tool: Tool, message: str) -> Answer:
    """A call refused before anything ran, or a tool that raised."""
    data = None if tool.output else _command_data("", 2, [message])
    return Answer(text=message, data=data, failed=True)


def _run(tool: Tool, args: dict[str, Any]) -> Answer:
    """Run the tool: its answer in-process, or its command."""
    try:
        args = _arguments(tool, args)
    except ArgumentError as error:
        return _failure(tool, str(error))
    if tool.answer is not None:
        try:
            text, data = tool.answer(args)
        except ArgumentError as error:
            return _failure(tool, str(error))
        return Answer(text=text, data=data)
    assert tool.argv is not None
    prepared = ""
    if tool.prepare is not None:
        try:
            prepared = tool.prepare(args)
        except ArgumentError as error:
            return _failure(tool, str(error))
    # the folder holding the infragram package: run.py sits in infragram/mcp/
    package_parent = str(Path(__file__).resolve().parents[2])
    env = dict(
        os.environ,
        PYTHONIOENCODING="utf-8",
        PYTHONPATH=os.pathsep.join(filter(None, [package_parent, os.environ.get("PYTHONPATH")])),
    )
    argv = tool.argv(args)
    # -P: the folder the command runs in is not where Python finds modules, so a
    # diagram file called logging.py does not stand in for the standard library
    command = [sys.executable, "-P", "-m", "infragram", *argv]
    shown = "infragram " + " ".join(argv)
    cwd = Path.cwd()
    try:
        done = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=COMMAND_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        message = f"infragram {argv[0]} did not finish in {COMMAND_TIMEOUT} s"
        return Answer(text=message, data=_command_data(shown, -1, [message]), failed=True)
    read: dict[str, Any] | None = _check_output(done.stdout) if tool.name == "check" else None
    if read is not None:
        text = "\n".join(
            part for part in (_check_text(read["checks"]), done.stderr.strip()) if part
        )
    elif tool.json_result:
        try:
            result = json.loads(done.stdout) if done.stdout.strip() else None
        except ValueError:
            result = None
        text = "\n".join(
            part
            for part in (
                json.dumps(result, indent=2, ensure_ascii=False) if result is not None else "",
                done.stderr.strip(),
            )
            if part
        )
        read = {**_read_output(done.stderr, cwd), "result": result}
    else:
        text = "\n".join(part.strip() for part in (done.stdout, done.stderr) if part.strip())
        read = _read_output(text, cwd)
    if prepared:
        read["notes"].insert(0, prepared)
        text = f"{prepared}\n{text}" if text else prepared
    failed = done.returncode != 0
    answer = Answer(
        text=f"$ {shown}\n{text or '(no output)'}\n(exit {done.returncode})",
        data={"command": shown, "exit_code": done.returncode, "ok": not failed, **read},
        failed=failed,
    )
    if args.get("preview") and not failed:
        image, why = _preview(read["files"], cwd)
        if image is not None:
            answer.image = image
        else:
            read["notes"].append(why)
            answer.text += f"\n{why}"
    return answer
