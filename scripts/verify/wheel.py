#!/usr/bin/env python3
"""The wheel is the whole product: build it, unpack it far from the checkout, draw a template from it.

An installed copy -- ``uv tool install``, ``pipx``, ``pip`` -- has no
repository above it. This gate builds the wheel from ``plugin/`` the way a
release does, unpacks it into a temporary directory that carries no checkout
marker, and runs a fresh interpreter against it with ``INFRAGRAM_ASSETS``
unset, so the package must find the plugin it carries (``infragram/_plugin``,
the whole plugin folder: manifests, skills, hook, agent, MCP configuration
and its own copy of the package) on its own: the catalog, the fonts,
every template, and it must draw one, write a Terraform skeleton from the
bundled tables, and import that skeleton back into a diagram file. The
shipped checker is run from the
same unpacked copy against a document naming an invented service, and must
refuse it: the checker once found no inventory beside itself in a wheel and
said OK to anything.

Usage::

    python scripts/verify/wheel.py            # exit 1 on any failure
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
#: Where the wheel carries the plugin folder, beside the package.
PLUGIN = "infragram/_plugin"

PROBE = """
import json, os, sys
assert "INFRAGRAM_ASSETS" not in os.environ
from infragram.paths import bundled_plugin, plugin_root, skill_assets
assets = skill_assets()
assert bundled_plugin() is not None and plugin_root() == bundled_plugin(), plugin_root()
assert assets == bundled_plugin() / "skills" / "infragram-azure" / "assets", assets
assert (assets / "catalog" / "inventory.json").is_file()
catalog = assets / "fonts" / "catalog.json"
assert catalog.is_file()
# a picture carries the faces its text draws with, out of those the bundle
# records: one it needs but leaves out is a label that draws in a fallback
# on a machine that has never seen the face
faces = len(json.loads(catalog.read_text(encoding="utf-8"))["faces"])
templates = sorted((assets / "templates" / "cloud").glob("*.infragram.json"))
assert len(templates) == 4, len(templates)
from infragram.exports import render_project_svg
from infragram.projects import CloudProject
svg = render_project_svg(CloudProject.load(templates[0]))
from infragram.catalog.fonts import used_faces
needed = len(used_faces(svg))
assert 1 <= needed <= faces, (needed, faces)
assert svg.count("@font-face{") == needed, (svg.count("@font-face{"), needed)
assert "<use href=\"#icon-" in svg
print(json.dumps({"assets": str(assets), "templates": len(templates), "svg_bytes": len(svg)}))
"""


def ignored_but_tracked() -> list[str]:
    """Tracked plugin files a .gitignore pattern matches. Hatch reads the
    ignore files when it builds the sdist, so such a file is left out of the
    sdist and of every wheel built from it -- the route a release takes --
    while git, and a wheel built straight from the tree, keep it."""
    done = subprocess.run(
        [git(), "ls-files", "-ci", "--exclude-standard", "--", "plugin"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return done.stdout.split()


def tracked_plugin_files() -> list[str]:
    """Every tracked file of the plugin folder, relative to it."""
    done = subprocess.run(
        [git(), "ls-files", "--", "plugin"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    # a deletion not yet committed is no longer the plugin's
    return [
        name.removeprefix("plugin/")
        for name in done.stdout.split("\n")
        if name and (ROOT / name).is_file()
    ]


def git() -> str:
    found = shutil.which("git")
    if found is None:
        raise SystemExit("FAIL wheel: git is not on the PATH")
    return found


def build_wheel(out: Path) -> Path:
    uv = shutil.which("uv")
    if uv:
        # the sdist first and the wheel from it, as a release builds them:
        # what the sdist leaves out, the published wheel lacks too
        command = [uv, "build", "--out-dir", str(out)]
    else:
        # CI has no uv; pip builds the same wheel through the same backend
        command = [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "-q", "-w", str(out)]
    subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    wheels = sorted(out.glob("infragram_azure-*.whl"))
    if not wheels:
        raise SystemExit("FAIL wheel: nothing was built")
    return wheels[-1]


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="infragram-wheel-") as scratch:
        scratch_path = Path(scratch)
        dropped = ignored_but_tracked()
        if dropped:
            print(
                "FAIL wheel: .gitignore matches tracked plugin files, so the sdist and every "
                f"wheel built from it leave them out: {', '.join(dropped[:5])}"
            )
            return 1
        wheel = build_wheel(scratch_path / "build")
        names = zipfile.ZipFile(wheel).namelist()
        carried = set(names)
        lacking = [name for name in tracked_plugin_files() if f"{PLUGIN}/{name}" not in carried]
        if lacking:
            print(
                f"FAIL wheel: {wheel.name} lacks {len(lacking)} tracked plugin files: "
                f"{', '.join(lacking[:5])}"
            )
            return 1
        stubs = sum(1 for name in names if name.startswith("infragram/") and name.endswith(".pyi"))
        if "infragram/py.typed" not in carried or not stubs:
            print(
                f"FAIL wheel: {wheel.name} carries {'no' if 'infragram/py.typed' not in carried else 'a'} "
                f"py.typed and {stubs} type stubs: an installed copy's types would be invisible "
                "to a type checker"
            )
            return 1
        assets = f"{PLUGIN}/skills/infragram-azure/assets"
        required = (
            f"{assets}/catalog/inventory.json",
            f"{assets}/fonts/catalog.json",
            f"{assets}/icons/index.json",
            "infragram/editor/runtime/00-bootstrap.js",
            "infragram/iso3d/scene.js",
            "infragram/cli/user/export_project.py",
            "infragram/cli/user/compose.py",
            "infragram/cli/user/render_gate.py",
            f"{PLUGIN}/skills/infragram-azure/scripts/project_check.py",
            "infragram/terraform/emit.py",
            "infragram/terraform/readconfig.py",
            "infragram/estate/draw.py",
            "infragram/estate/discover/aws.py",
            f"{assets}/terraform/aws.json",
            f"{assets}/terraform/ports.json",
            # the plugin around the skill, whole: an agent installs this folder
            f"{PLUGIN}/.claude-plugin/plugin.json",
            f"{PLUGIN}/.claude-plugin/marketplace.json",
            f"{PLUGIN}/.codex-plugin/plugin.json",
            f"{PLUGIN}/plugin.json",
            f"{PLUGIN}/package.json",
            f"{PLUGIN}/.mcp.json",
            f"{PLUGIN}/hooks/hooks.json",
            f"{PLUGIN}/agents/diagram-reviewer.md",
            f"{PLUGIN}/skills/compose/SKILL.md",
            f"{PLUGIN}/pyproject.toml",
            f"{PLUGIN}/src/infragram/__init__.py",
            "infragram/mcp/protocol.py",
        )
        missing = [name for name in required if name not in names]
        cached = [name for name in names if "__pycache__" in name or name.endswith(".pyc")]
        if cached:
            print(f"FAIL wheel: {wheel.name} carries compiled caches: {cached[:3]}")
            return 1
        templates = sum(
            1
            for name in names
            if name.startswith(f"{assets}/templates/cloud/") and name.endswith(".json")
        )
        if missing or templates != 4:
            print(
                f"FAIL wheel: {wheel.name} is missing {missing or 'nothing'}; {templates} templates of 4"
            )
            return 1
        site = scratch_path / "site"
        zipfile.ZipFile(wheel).extractall(site)
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("INFRAGRAM_ASSETS", "PYTHONPATH")
        }
        env["PYTHONPATH"] = str(site)
        env["PYTHONIOENCODING"] = "utf-8"
        probe = subprocess.run(
            [sys.executable, "-c", PROBE], cwd=scratch_path, env=env, capture_output=True, text=True
        )
        if probe.returncode != 0:
            print(
                f"FAIL wheel: an installed copy cannot draw from its bundled assets\n{probe.stderr[-2000:]}"
            )
            return 1
        result = json.loads(probe.stdout.strip().splitlines()[-1])
        # and the user command itself, from the installed copy, with the checker
        template = Path(result["assets"]) / "templates" / "cloud" / "azure-api.infragram.json"
        out = scratch_path / "out"
        export = subprocess.run(
            [
                sys.executable,
                "-m",
                "infragram",
                "export:project",
                str(template),
                "--formats",
                "template,svg,terraform",
                "--output-dir",
                str(out),
                "--verify",
            ],
            cwd=scratch_path,
            env=env,
            capture_output=True,
            text=True,
        )
        if (
            export.returncode != 0
            or not list(out.glob("*.svg"))
            or not list(out.glob("*-terraform/environments/prod/versions.tf"))
        ):
            print(
                f"FAIL wheel: export:project from an installed copy failed\n{export.stdout[-1200:]}\n{export.stderr[-1200:]}"
            )
            return 1
        skeleton = next(out.glob("*-terraform"))
        imported = subprocess.run(
            [
                sys.executable,
                "-m",
                "infragram",
                "import:terraform",
                str(skeleton),
                "--no-export",
                "--output-dir",
                str(out / "imported"),
            ],
            cwd=scratch_path,
            env=env,
            capture_output=True,
            text=True,
        )
        if imported.returncode != 0 or not list((out / "imported").glob("*.py")):
            print(
                f"FAIL wheel: import:terraform from an installed copy failed\n{imported.stdout[-1200:]}\n"
                f"{imported.stderr[-1200:]}"
            )
            return 1
        failure = checker_refuses_an_invented_service(site, template, scratch_path, env)
        if failure:
            print(f"FAIL wheel: {failure}")
            return 1
        size = wheel.stat().st_size / 1e6
        print(
            f"OK wheel: {wheel.name} ({size:.1f} MB) carries the whole plugin and the user commands; an "
            f"installed copy drew a template ({result['templates']} templates, {result['svg_bytes']} bytes of SVG), "
            "export:project --verify passed from it with its Terraform skeleton, import:terraform read the "
            "skeleton back, and its checker refused an invented service"
        )
        return 0


def checker_refuses_an_invented_service(
    site: Path, template: Path, scratch: Path, env: dict[str, str]
) -> str | None:
    """Run the wheel's own project_check.py on a copy of *template* with one
    component's service_id invented; the reason it must fail, or None."""
    checker = site / PLUGIN / "skills" / "infragram-azure" / "scripts" / "project_check.py"
    document = json.loads(template.read_text(encoding="utf-8"))

    def invent(element: object) -> bool:
        if not isinstance(element, dict):
            return False
        component = element.get("component")
        if isinstance(component, dict) and isinstance(component.get("service_id"), str):
            component["service_id"] = "zzz-invented"
            return True
        return any(invent(child) for child in element.get("children") or [])

    if not invent(document.get("topology")):
        return f"{template.name} has no component to invent a service on"
    invented = scratch / "invented.infragram.json"
    invented.write_text(json.dumps(document), encoding="utf-8", newline="\n")
    check = subprocess.run(
        [sys.executable, str(checker), str(invented)],
        cwd=scratch,
        env=env,
        capture_output=True,
        text=True,
    )
    if check.returncode == 0:
        return (
            f"the checker at {checker.relative_to(site)} said OK to an invented service; it is not "
            f"reading the inventory bundled beside it\n{check.stdout[-800:]}{check.stderr[-800:]}"
        )
    if "no installed library ships" not in check.stdout:
        return (
            f"the checker at {checker.relative_to(site)} failed for the wrong reason (it should name the "
            f"invented service, not a missing inventory)\n{check.stdout[-800:]}{check.stderr[-800:]}"
        )
    return None


if __name__ == "__main__":
    raise SystemExit(main())
