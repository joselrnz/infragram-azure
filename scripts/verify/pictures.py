#!/usr/bin/env python3
"""Golden pictures: every shipped template draws exactly what it drew last time.

Rendering is deterministic, so the picture of every template, as cards and as
icons, is locked by its SHA-256 in ``tests/golden/pictures.lock.json``. A
change anywhere in the renderer, the layout, a theme or an icon that alters
any picture fails this gate and names the template and look that moved. When
the change is intended, ``--update`` rewrites the lock and the diff of that
file is the review: it says exactly which pictures a change touched.

Every render is also read by the shipped checker, so a template cannot lock
in a wire through text or a caption on a card.

Usage::

    python -m infragram verify:pictures            # check, exit 1 on any drift
    python -m infragram verify:pictures --update   # accept the current pictures

The static render is used, which needs no browser and is the layout the
exporter falls back to; the browser-drawn pictures are proven separately by
``verify:render``. A look applies to every component, including ones an
author switched by hand, exactly as the editor's own Components switch does.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))

from infragram.exports import look_variant, render_project_svg  # noqa: E402
from infragram.projects import CloudProject  # noqa: E402

TEMPLATES = ROOT / "skills" / "infragram-azure" / "assets" / "templates" / "cloud"
LOCK = ROOT / "tests" / "golden" / "pictures.lock.json"
CHECKER = ROOT / "skills" / "infragram-azure" / "scripts" / "project_check.py"
LOOKS = ("card", "icon")


def load_checker():
    spec = importlib.util.spec_from_file_location("project_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def picture(project: CloudProject, look: str) -> str:
    """The static SVG of ``project`` drawn in ``look``."""
    return render_project_svg(look_variant(project, look))


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def current(checker=None) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Every template's picture hashes, and every picture-check finding."""
    pictures: dict[str, dict[str, str]] = {}
    findings: list[str] = []
    for path in sorted(TEMPLATES.glob("*.infragram.json")):
        project = CloudProject.load(path)
        pictures[project.slug] = {}
        for look in LOOKS:
            svg = picture(project, look)
            pictures[project.slug][look] = digest(svg)
            if checker is not None:
                errors: list[str] = []
                checker.check_svg(svg, errors, project.model_dump(mode="json"))
                findings += [f"{project.slug} [{look}]: {error}" for error in errors]
    return pictures, findings


def read_lock() -> dict[str, dict[str, str]]:
    if not LOCK.is_file():
        return {}
    data = json.loads(LOCK.read_text(encoding="utf-8"))
    return data.get("pictures", {})


def write_lock(pictures: dict[str, dict[str, str]]) -> None:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "schema": 1,
        "renderer": "static",
        "note": "sha256 of render_project_svg(look_variant(template, look)) per look. "
        "Regenerate with `python -m infragram verify:pictures --update` when a "
        "picture is meant to change; the diff of this file is the review.",
        "pictures": pictures,
    }
    # the lock keeps the line endings it has, which verify/line-endings checks
    newline = "\r\n" if LOCK.is_file() and b"\r\n" in LOCK.read_bytes() else "\n"
    LOCK.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline=newline
    )


def compare(locked: dict[str, dict[str, str]], now: dict[str, dict[str, str]]) -> list[str]:
    problems: list[str] = []
    for slug in sorted(set(locked) | set(now)):
        if slug not in locked:
            problems.append(f"{slug}: new template, not in the lock")
            continue
        if slug not in now:
            problems.append(f"{slug}: in the lock but no longer shipped")
            continue
        for look in LOOKS:
            before, after = locked[slug].get(look), now[slug].get(look)
            if before != after:
                problems.append(
                    f"{slug} [{look}]: picture changed ({(before or '?')[:12]} -> {(after or '?')[:12]})"
                )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--update", action="store_true", help="accept the current pictures as golden"
    )
    options = parser.parse_args(argv)

    checker = load_checker()
    now, findings = current(checker)
    for finding in findings:
        print(f"  - {finding}")
    if findings:
        print(
            f"FAIL: {len(findings)} picture finding(s) in the shipped templates; fix before locking"
        )
        return 1

    if options.update:
        write_lock(now)
        print(f"OK: locked {len(now)} templates x {len(LOOKS)} looks in {LOCK.relative_to(ROOT)}")
        return 0

    problems = compare(read_lock(), now)
    for problem in problems:
        print(f"  - {problem}")
    if problems:
        print(
            f"FAIL: {len(problems)} picture(s) differ from tests/golden/pictures.lock.json. "
            "If the change is intended, run `python -m infragram verify:pictures --update` "
            "and commit the lock with the change that moved them."
        )
        return 1
    print(
        f"OK: {len(now)} templates x {len(LOOKS)} looks match the golden pictures, all pass the picture checks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
