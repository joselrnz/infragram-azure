"""The shipped scripts run correctly from an installed copy of the skill.

Copies only ``skills/infragram-azure/`` into a scratch directory - the way an
install lands on a user's machine - and exercises each entry point there, so
a hidden dependency on this repository shows up as a failure. A second copy
is shaped like the wheel (``_skill_scripts/`` beside ``_assets/``), where the
checker once found no inventory and said OK to an invented service.

The launcher, ``scripts/infragram.py``, is how every agent runs a command: it
takes the package beside the skill in a plugin, an importable one, or the
``infragram`` command an install put on the PATH, and says what to install
when there is none. ``-I -S`` runs it with no site-packages, so what this
machine happens to have installed cannot answer for it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
SKILL = ROOT / "skills" / "infragram-azure"
CHECKER = SKILL / "scripts" / "project_check.py"
LAUNCHER = SKILL / "scripts" / "infragram.py"
MANIFEST = ROOT / ".claude-plugin" / "plugin.json"
INVENTORY = SKILL / "assets" / "catalog" / "inventory.json"

#: The checker must find the assets beside itself, never through the override.
_ENV = {key: value for key, value in os.environ.items() if key != "INFRAGRAM_ASSETS"}


def run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env=_ENV,
    )


@contextmanager
def installed_skill() -> Iterator[tuple[Path, Path]]:
    """(scratch, installed skill copy) with only the skill folder copied in."""
    with tempfile.TemporaryDirectory(prefix="skill-runtime-") as temp_dir:
        installed = Path(temp_dir) / SKILL.name
        shutil.copytree(SKILL, installed)
        yield Path(temp_dir), installed


def shipped_templates(installed: Path) -> list[Path]:
    templates = sorted((installed / "assets" / "templates").rglob("*.json"))
    assert templates, "no shipped project templates found in the installed copy"
    return templates


def azure_api(installed: Path) -> Path:
    return next(t for t in shipped_templates(installed) if t.name.startswith("azure-api"))


def with_an_invented_service(template: Path, out: Path) -> Path:
    """A copy of *template* whose first component names a service nothing ships."""
    document = json.loads(template.read_text(encoding="utf-8"))

    def invent(element: object) -> bool:
        if not isinstance(element, dict):
            return False
        component = element.get("component")
        if isinstance(component, dict) and isinstance(component.get("service_id"), str):
            component["service_id"] = "zzz-invented"
            return True
        return any(invent(child) for child in element.get("children") or [])

    assert invent(document.get("topology")), (
        f"{template.name} has no component to invent a service on"
    )
    out.write_text(json.dumps(document), encoding="utf-8")
    return out


# ------------------------------------------------------- the installed skill
@pytest.mark.slow
def test_checker_accepts_every_shipped_template_from_an_installed_copy() -> None:
    with installed_skill() as (_scratch, installed):
        templates = shipped_templates(installed)
        result = run(installed / "scripts" / "project_check.py", *map(str, templates))
        assert result.returncode == 0 and result.stdout.count("OK ") == len(templates), (
            f"project_check.py rejected a shipped template:\n{result.stdout}{result.stderr}"
        )


def test_checker_accepts_an_exported_editor_page_from_an_installed_copy() -> None:
    # The dev tree renders the fixture page; the installed copy must check it
    # without ever importing the dev tree.
    from infragram.exports import render_project_html
    from infragram.projects import CloudProject

    with installed_skill() as (scratch, installed):
        exported = scratch / "azure-api.html"
        exported.write_text(
            render_project_html(CloudProject.load(azure_api(installed))), encoding="utf-8"
        )
        result = run(installed / "scripts" / "project_check.py", str(exported))
        assert result.returncode == 0 and "OK " in result.stdout, (
            f"project_check.py rejected an exported editor page:\n{result.stdout}{result.stderr}"
        )


def test_checker_rejects_a_dangling_connection_from_an_installed_copy() -> None:
    with installed_skill() as (scratch, installed):
        broken = json.loads(azure_api(installed).read_text(encoding="utf-8"))
        broken["topology"]["connections"] = [{"target": "no-such-element"}]
        broken_path = scratch / "broken.json"
        broken_path.write_text(json.dumps(broken), encoding="utf-8")
        result = run(installed / "scripts" / "project_check.py", str(broken_path))
        assert result.returncode != 0 and "unknown target" in result.stdout, (
            f"project_check.py accepted a dangling connection:\n{result.stdout}{result.stderr}"
        )


# ------------------------------------------------ the checker inside a wheel
def test_checker_in_the_wheel_layout_refuses_an_invented_service() -> None:
    """The wheel installs the script at ``infragram/_skill_scripts/`` with the
    assets at ``infragram/_assets/``; the checker must find the inventory
    there, not look for ``../assets`` and pass everything."""
    with tempfile.TemporaryDirectory(prefix="skill-wheel-layout-") as temp_dir:
        package = Path(temp_dir) / "infragram"
        (package / "_skill_scripts").mkdir(parents=True)
        (package / "_assets" / "catalog").mkdir(parents=True)
        shutil.copy(CHECKER, package / "_skill_scripts" / "project_check.py")
        shutil.copy(INVENTORY, package / "_assets" / "catalog" / "inventory.json")
        template = SKILL / "assets" / "templates" / "cloud" / "azure-api.infragram.json"
        invented = with_an_invented_service(template, Path(temp_dir) / "invented.infragram.json")
        result = run(package / "_skill_scripts" / "project_check.py", str(invented))
        assert result.returncode != 0, (
            f"the checker in the wheel layout said OK to an invented service:\n{result.stdout}{result.stderr}"
        )
        assert "no installed library ships" in result.stdout, (
            f"the checker failed for the wrong reason (it should name the invented service):\n"
            f"{result.stdout}{result.stderr}"
        )


def test_checker_without_its_assets_fails_and_says_where_it_looked() -> None:
    """A copy taken out alone cannot tell a shipped service from an invented
    one; it must say so and fail the run, not pass in silence."""
    with tempfile.TemporaryDirectory(prefix="skill-bare-checker-") as temp_dir:
        script = Path(temp_dir) / "x" / "_skill_scripts" / "project_check.py"
        script.parent.mkdir(parents=True)
        shutil.copy(CHECKER, script)
        template = SKILL / "assets" / "templates" / "cloud" / "azure-api.infragram.json"
        result = run(script, str(template))
        assert result.returncode != 0, f"a checker with no inventory passed:\n{result.stdout}"
        assert "no component inventory found" in result.stdout and "looked in" in result.stdout, (
            result.stdout
        )
        assert "WARNING: no skill assets found" in result.stderr, result.stderr


# ------------------------------------------------------------- the launcher
def launch(
    launcher: Path,
    *args: str,
    cwd: Path,
    flags: tuple[str, ...] = (),
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *flags, str(launcher), *args],
        cwd=cwd,
        env=env or _ENV,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def skill_alone(scratch: Path) -> Path:
    """The launcher in a skill folder with no plugin around it."""
    launcher = scratch / "skills" / SKILL.name / "scripts" / LAUNCHER.name
    launcher.parent.mkdir(parents=True)
    shutil.copy(LAUNCHER, launcher)
    return launcher


def installed_command(folder: Path, says: str, name: str = "infragram") -> None:
    """A *name* command (``infragram`` by default) that prints *says* and its
    arguments, and exits 3."""
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        (folder / f"{name}.cmd").write_text(f"@echo {says} %*\r\n@exit /b 3\r\n", encoding="ascii")
        return
    command = folder / name
    command.write_text(f'#!/bin/sh\necho "{says} $*"\nexit 3\n', encoding="ascii")
    command.chmod(0o755)


def test_launcher_runs_the_plugin_package_from_any_folder() -> None:
    """From a folder holding a diagram file called infragram.py, which must
    not stand in for the package."""
    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    with tempfile.TemporaryDirectory(prefix="launcher-") as temp_dir:
        work = Path(temp_dir)
        (work / "infragram.py").write_text('raise SystemExit("the decoy ran")\n', encoding="utf-8")
        result = launch(LAUNCHER, "--version", cwd=work)
        assert result.returncode == 0 and result.stdout.strip() == f"infragram {version}", (
            f"the launcher did not run the plugin's package:\n{result.stdout}{result.stderr}"
        )


def test_launcher_keeps_the_exit_status_and_writes_utf8_to_a_pipe() -> None:
    """A Windows pipe, which is how an agent reads the report, defaults to
    cp1252; the report must still arrive whole, with the command's status."""
    with tempfile.TemporaryDirectory(prefix="launcher-") as temp_dir:
        work = Path(temp_dir)
        broken = json.loads(azure_api(SKILL).read_text(encoding="utf-8"))
        broken["topology"]["connections"] = [{"target": "東京-missing"}]
        (work / "broken.json").write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        result = launch(
            LAUNCHER, "check", "broken.json", cwd=work, env={**_ENV, "PYTHONIOENCODING": "cp1252"}
        )
        assert result.returncode == 1 and "unknown target '東京-missing'" in result.stdout, (
            f"the check did not report through a cp1252 pipe:\n{result.stdout}{result.stderr}"
        )


def test_launcher_without_pydantic_says_how_to_install_it() -> None:
    with tempfile.TemporaryDirectory(prefix="launcher-") as temp_dir:
        empty = Path(temp_dir) / "bin"
        empty.mkdir()
        result = launch(
            LAUNCHER,
            "--version",
            cwd=Path(temp_dir),
            flags=("-I", "-S"),
            env={**_ENV, "PATH": str(empty)},
        )
        assert result.returncode == 2 and 'pip install "pydantic>=2,<3"' in result.stderr, (
            f"the launcher did not say how to install pydantic:\n{result.stdout}{result.stderr}"
        )


def test_launcher_without_pydantic_runs_the_plugin_through_uvx() -> None:
    """A Python without pydantic hands the command to uv, which runs the
    plugin's own package in an environment that has it."""
    with tempfile.TemporaryDirectory(prefix="launcher-") as temp_dir:
        scratch = Path(temp_dir)
        installed_command(scratch / "bin", "uvx", name="uvx")
        result = launch(
            LAUNCHER,
            "check",
            "diagram.json",
            cwd=scratch,
            flags=("-I", "-S"),
            env={**_ENV, "PATH": str(scratch / "bin")},
        )
        expected = f"uvx --from {ROOT} infragram check diagram.json"
        assert result.returncode == 3 and expected in result.stdout, (
            f"the launcher did not run the plugin through uvx:\n{result.stdout}{result.stderr}"
        )


def test_a_skill_alone_without_the_package_says_how_to_install_it() -> None:
    with tempfile.TemporaryDirectory(prefix="launcher-") as temp_dir:
        scratch = Path(temp_dir)
        launcher = skill_alone(scratch)
        (scratch / "bin").mkdir()
        result = launch(
            launcher,
            "--version",
            cwd=scratch,
            flags=("-I", "-S"),
            env={**_ENV, "PATH": str(scratch / "bin")},
        )
        assert result.returncode == 2 and "uv tool install" in result.stderr, (
            f"the launcher did not say how to install the package:\n{result.stdout}{result.stderr}"
        )


def test_a_skill_alone_runs_the_installed_command() -> None:
    """uv tool install and pipx put an ``infragram`` command on the PATH, in
    a Python of its own; the launcher hands it the command line and returns
    its status. One in the working folder is never taken for it."""
    with tempfile.TemporaryDirectory(prefix="launcher-") as temp_dir:
        scratch = Path(temp_dir)
        launcher = skill_alone(scratch)
        installed_command(scratch / "bin", "installed")
        installed_command(scratch / "work", "decoy")
        result = launch(
            launcher,
            "check",
            "diagram.json",
            cwd=scratch / "work",
            flags=("-I", "-S"),
            env={**_ENV, "PATH": os.pathsep.join((".", str(scratch / "bin")))},
        )
        assert result.returncode == 3 and "installed check diagram.json" in result.stdout, (
            f"the launcher did not run the installed command:\n{result.stdout}{result.stderr}"
        )
