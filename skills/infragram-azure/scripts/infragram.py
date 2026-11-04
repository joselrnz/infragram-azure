#!/usr/bin/env python3
"""Run Infragram from the skill, the same way in every agent and every shell.

    python <this skill's folder>/scripts/infragram.py <command> [arguments]

It runs the package the plugin ships (the ``src`` folder beside ``skills/``)
when there is one; else an ``infragram`` this Python can import; else the
``infragram`` command an install put on the PATH (``uv tool install``,
``pipx``). It checks for Python 3.11 and pydantic first: a Python without
pydantic hands the command to an installed ``infragram``, else to ``uvx``
(the plugin's own package, in an environment uv makes), else says how to
install what is missing. It runs the command in the current directory.
``--help`` lists the commands. Standard library only, so it runs before
anything is installed.
"""

from __future__ import annotations

import importlib.util
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

MINIMUM = (3, 11)
HERE = Path(__file__).resolve().parent
INSTALL = (
    "Install it from the folder holding Infragram's pyproject.toml: "
    "uv tool install <folder>, or python -m pip install <folder>."
)


def _plugin_source() -> Path | None:
    """The ``src`` folder of the plugin this skill ships in, or None. The
    plugin holds this file at ``skills/<skill>/scripts/``."""
    parents = HERE.parents
    if len(parents) > 2 and (parents[2] / "src" / "infragram" / "__init__.py").is_file():
        return parents[2] / "src"
    return None


def _installed_command() -> Path | None:
    """The ``infragram`` command an install put on the PATH, never one in the
    current folder, where a diagram file may well be called infragram.py."""
    names = (
        ("infragram.exe", "infragram.cmd", "infragram.bat") if os.name == "nt" else ("infragram",)
    )
    here = Path.cwd().resolve()
    for folder in filter(None, os.environ.get("PATH", "").split(os.pathsep)):
        try:
            if Path(folder).resolve() == here:
                continue
        except OSError:
            continue
        for name in names:
            candidate = Path(folder) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
    return None


def main() -> int:
    if sys.version_info < MINIMUM:
        print(
            f"Infragram needs Python {MINIMUM[0]}.{MINIMUM[1]} or newer; this is "
            f"{sys.version.split()[0]}. Run it with a newer python (python3.11 or later).",
            file=sys.stderr,
        )
        return 2
    # Python put this script's own folder first on the path, where this file
    # would answer to `import infragram` in place of the package.
    sys.path[:] = [entry for entry in sys.path if Path(entry or ".").resolve() != HERE]
    source = _plugin_source()
    if source is not None:
        sys.path.insert(0, str(source))
    elif importlib.util.find_spec("infragram") is None:
        command = _installed_command()
        if command is not None:
            return subprocess.run([str(command), *sys.argv[1:]], check=False).returncode
        print(
            f"Infragram's package is neither beside this skill nor installed. {INSTALL}",
            file=sys.stderr,
        )
        return 2
    if importlib.util.find_spec("pydantic") is None:
        # This Python lacks the one dependency: an installed command has it,
        # and uv can run the plugin's own package in an environment that does.
        command = _installed_command()
        if command is not None:
            return subprocess.run([str(command), *sys.argv[1:]], check=False).returncode
        uvx = shutil.which("uvx")
        if source is not None and uvx is not None:
            print(
                "infragram: this Python has no pydantic; running the plugin's package through uvx",
                file=sys.stderr,
            )
            return subprocess.run(
                [uvx, "--from", str(source.parent), "infragram", *sys.argv[1:]], check=False
            ).returncode
        print(
            'Infragram needs pydantic 2. Install it with: python -m pip install "pydantic>=2,<3" '
            "(or install uv, and the launcher runs it through uvx)",
            file=sys.stderr,
        )
        return 2
    sys.argv = ["infragram", *sys.argv[1:]]
    runpy.run_module("infragram", run_name="__main__", alter_sys=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
