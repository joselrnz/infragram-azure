#!/usr/bin/env python3
"""The plugin installs the way users install it, and each agent loads all of it.

Every agent runs with a throwaway home (``CLAUDE_CONFIG_DIR``, ``CODEX_HOME``,
``UV_TOOL_DIR``), so a user's own agents are never touched, and nothing is
published or downloaded (uv runs ``--offline``, from its cache):

- the packages are built as a release builds them (``build:packages``);
- Claude Code installs the repository as a marketplace, the unpacked npm
  package as one, and the plugin the wheel carries through
  ``infragram plugin:install claude`` after ``uv tool install``; each time
  ``claude plugin details`` must list the seven skills, the reviewer agent,
  the check hook and the MCP server;
- Codex installs the repository as a marketplace, enabled, with its MCP
  server;
- from Claude Code's install, the check hook passes a good document and
  blocks a broken one, and the MCP server (started as ``.mcp.json`` starts it,
  through ``uvx``) lists its tools and checks the broken document.

An agent or tool not on the PATH is named and its part skipped; with
``--strict`` (before a release) each such part fails instead, and a run that
installed nothing at all fails either way. It needs the agents' CLIs, which
CI does not have, so ``verify:all`` does not run it: run it after a change to
the plugin's manifests, hooks, MCP server or packaging, and with
``--strict`` before a release.

Usage::

    python -m infragram verify:install [--strict] [--keep DIR]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
PLUGIN = "infragram-azure"
ID = f"{PLUGIN}@{PLUGIN}"
SKILLS = {
    "infragram-azure",
    "compose",
    "export-project",
    "import",
    "discover",
    "check",
    "check-terraform",
}
TEMPLATE = (
    ROOT
    / "skills"
    / PLUGIN
    / "assets"
    / "templates"
    / "cloud"
    / "gcp-three-tier-web.infragram.json"
)


def _run(
    command: list[str],
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    stdin: str | None = None,
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        env=env,
        cwd=cwd,
        input=stdin,
        capture_output=True,
        timeout=timeout,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _tail(done: subprocess.CompletedProcess[str]) -> str:
    return "\n".join((done.stdout + done.stderr).strip().splitlines()[-12:])


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_packages", ROOT / "scripts" / "build" / "packages.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------ Claude Code
def claude_install(
    claude: str, home: Path, source: Path | None, then: list[list[str]] | None = None
) -> str | None:
    """Install the plugin into a throwaway Claude Code home (from *source* as
    a marketplace, or by the *then* commands), and check what it loaded; the
    failure, or None."""
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(home))
    steps = then or [
        [claude, "plugin", "marketplace", "add", str(source)],
        [claude, "plugin", "install", ID],
    ]
    for step in steps:
        done = _run(step, env=env)
        if done.returncode:
            return f"{' '.join(step[:4])} failed\n{_tail(done)}"
    details = _run([claude, "plugin", "details", PLUGIN], env=env)
    text = details.stdout
    skills = re.search(r"Skills \((\d+)\)\s+(.+)", text)
    found = {name.strip() for name in skills.group(2).split(",")} if skills else set()
    wanted = [
        ("skills", found == SKILLS),
        ("the reviewer agent", "diagram-reviewer" in text),
        ("the check hook", re.search(r"Hooks \(1\)\s+PostToolUse", text) is not None),
        ("the MCP server", re.search(r"MCP servers \(1\)\s+infragram", text) is not None),
    ]
    missing = [name for name, ok in wanted if not ok]
    if missing:
        return f"claude plugin details lacks {', '.join(missing)} (skills: {sorted(found)})\n{text[-1500:]}"
    return None


def installed_copy(home: Path, fallback: Path) -> Path:
    """Where Claude Code keeps the plugin it installed: its cache, else the folder it loads in place."""
    copies = sorted(home.glob(f"plugins/cache/{PLUGIN}/{PLUGIN}/*"))
    return copies[-1] if copies else fallback


def hook_and_server(copy: Path, scratch: Path) -> list[str]:
    """Run the installed plugin's check hook and MCP server on a good and a broken document."""
    failures: list[str] = []
    work = scratch / "project"
    work.mkdir()
    shutil.copy(TEMPLATE, work / "good.infragram.json")
    broken = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    broken["slug"] = "Not A Slug!"
    (work / "bad.infragram.json").write_text(json.dumps(broken), encoding="utf-8")
    sh = shutil.which("sh")
    if sh is None:
        failures.append("SKIP the hook: no sh on the PATH")
    else:
        for name, blocks in (("good", False), ("bad", True)):
            event = {
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "cwd": str(work),
                "tool_input": {"file_path": f"{name}.infragram.json"},
            }
            done = _run(
                [sh, str(copy / "hooks" / "run"), "hook:check"], cwd=work, stdin=json.dumps(event)
            )
            said = done.stdout.strip()
            if (
                done.returncode
                or bool(said) != blocks
                or (blocks and '"decision": "block"' not in said)
            ):
                failures.append(
                    f"the hook on the {name} document said {said[:300] or 'nothing'} "
                    f"(exit {done.returncode})\n{done.stderr[-800:]}"
                )
    uvx = shutil.which("uvx")
    if uvx is None:
        failures.append("SKIP the MCP server: no uvx on the PATH")
        return failures
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "verify", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "check", "arguments": {"paths": ["bad.infragram.json"]}},
        },
    ]
    done = _run(
        [uvx, "--offline", "--from", str(copy), "infragram", "mcp"],
        cwd=work,
        stdin="".join(json.dumps(message) + "\n" for message in messages),
    )
    answers = {}
    for line in done.stdout.splitlines():
        try:
            answer = json.loads(line)
        except ValueError:
            failures.append(
                f"the MCP server wrote something other than JSON on stdout: {line[:200]}"
            )
            break
        answers[answer.get("id")] = answer
    tools = {tool["name"] for tool in answers.get(2, {}).get("result", {}).get("tools", [])}
    # the installed copy offers what this checkout's server declares: no fixed count to drift
    sys.path.insert(0, str(ROOT / "src"))
    from infragram.mcp import TOOLS

    expected = {tool.name for tool in TOOLS}
    call = answers.get(3, {}).get("result", {})
    if (
        1 not in answers
        or tools != expected
        or not call.get("isError")
        or "slug" not in json.dumps(call)
    ):
        failures.append(
            f"the MCP server did not answer as it should (tools: {sorted(tools)})\n{_tail(done)}"
        )
    return failures


# ------------------------------------------------------------ Codex
def codex_install(codex: str, home: Path) -> str | None:
    home.mkdir(parents=True, exist_ok=True)  # Codex refuses a home that does not exist
    env = dict(os.environ, CODEX_HOME=str(home))
    for step in ([codex, "plugin", "marketplace", "add", str(ROOT)], [codex, "plugin", "add", ID]):
        done = _run(step, env=env)
        if done.returncode:
            return f"{' '.join(step[:4])} failed\n{_tail(done)}"
    listed = _run([codex, "plugin", "list", "--json"], env=env)
    servers = _run([codex, "mcp", "list", "--json"], env=env)
    try:
        installed = json.loads(listed.stdout[listed.stdout.index("{") :])["installed"]
        names = [
            server["name"] for server in json.loads(servers.stdout[servers.stdout.index("[") :])
        ]
    except (ValueError, KeyError) as error:
        return f"codex answered what this gate cannot read ({error})\n{_tail(listed)}\n{_tail(servers)}"
    entry = next((item for item in installed if item.get("pluginId") == ID), None)
    if entry is None or not entry.get("enabled"):
        return f"codex plugin list does not show {ID} installed and enabled"
    if "infragram" not in names:
        return f"codex mcp list does not show the infragram server ({names})"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="infragram verify:install", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--keep",
        type=Path,
        default=None,
        help="keep the packages and the throwaway agent homes here",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail every part a missing tool left unchecked (before a release)",
    )
    options = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="infragram-install-") as scratch_dir:
        scratch = (options.keep or Path(scratch_dir)).resolve()
        scratch.mkdir(parents=True, exist_ok=True)
        failures: list[str] = []
        passed: list[str] = []
        built, notes = _builder().build(scratch / "packages")
        claude, codex = shutil.which("claude"), shutil.which("codex")
        if claude is None:
            notes.append("no claude on the PATH: Claude Code's installs were not checked")
        else:
            home = scratch / "claude-repository"
            failure = claude_install(claude, home, ROOT)
            (
                failures.append(f"Claude Code from the repository: {failure}")
                if failure
                else passed.append("Claude Code from the repository")
            )
            if failure is None:
                with tempfile.TemporaryDirectory(prefix="infragram-hook-", dir=scratch) as run_dir:
                    found = hook_and_server(installed_copy(home, ROOT), Path(run_dir))
                failures += [line for line in found if not line.startswith("SKIP")]
                notes += [line[5:] for line in found if line.startswith("SKIP")]
                if not [line for line in found if not line.startswith("SKIP")]:
                    passed.append("its check hook and MCP server")
            tarball = next((path for path in built if path.suffix == ".tgz"), None)
            if tarball is not None:
                unpacked = scratch / "npm"
                with tarfile.open(tarball) as archive:
                    archive.extractall(unpacked, filter="data")
                failure = claude_install(claude, scratch / "claude-npm", unpacked / "package")
                (
                    failures.append(f"Claude Code from the npm package: {failure}")
                    if failure
                    else passed.append("Claude Code from the npm package")
                )
            wheel = next((path for path in built if path.suffix == ".whl"), None)
            uv = shutil.which("uv")
            if wheel is not None and uv is not None:
                tools = dict(
                    os.environ,
                    UV_TOOL_DIR=str(scratch / "uv-tools"),
                    UV_TOOL_BIN_DIR=str(scratch / "uv-bin"),
                )
                done = _run([uv, "tool", "install", "--offline", str(wheel)], env=tools)
                command = next(iter(sorted((scratch / "uv-bin").glob("infragram*"))), None)
                if done.returncode or command is None:
                    failures.append(f"uv tool install of the wheel failed\n{_tail(done)}")
                else:
                    failure = claude_install(
                        claude,
                        scratch / "claude-wheel",
                        None,
                        then=[[str(command), "plugin:install", "claude"]],
                    )
                    (
                        failures.append(f"Claude Code from the wheel (plugin:install): {failure}")
                        if failure
                        else passed.append(
                            "Claude Code from the wheel through infragram plugin:install"
                        )
                    )
            elif uv is None:
                notes.append("no uv on the PATH: the wheel's plugin:install was not checked")
        if codex is None:
            notes.append("no codex on the PATH: Codex's install was not checked")
        else:
            failure = codex_install(codex, scratch / "codex-repository")
            (
                failures.append(f"Codex from the repository: {failure}")
                if failure
                else passed.append("Codex from the repository")
            )
    return report(built, passed, failures, notes, strict=options.strict)


def report(
    built: list[Path],
    passed: list[str],
    failures: list[str],
    notes: list[str],
    *,
    strict: bool = False,
) -> int:
    """Print what was checked, and the exit status: a part a missing tool left
    unchecked is a note, or with ``strict`` a failure; installing nothing at
    all is a failure either way, never an OK."""
    if strict:
        failures = [*failures, *(f"not checked (--strict): {note}" for note in notes)]
        notes = []
    if not passed and not failures:
        failures = ["nothing was installed: no agent CLI on the PATH (claude, codex)"]
    for note in notes:
        print(f"NOTE {note}")
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    if failures:
        return 1
    print(f"OK install: {len(built)} packages built; {', '.join(passed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
