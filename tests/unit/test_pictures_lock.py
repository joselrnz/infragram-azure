"""Every shipped template draws what the golden lock says it draws.

The lock in tests/golden/pictures.lock.json is the picture of every template
in both looks, by SHA-256. A renderer change that moves any picture has to
move the lock too, on purpose, so the diff of that file is the review of what
a change did to the drawings. This test is the gate's own logic run under
pytest, so the lock cannot drift without the suite failing.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
GATE = ROOT / "scripts/verify/pictures.py"
LOCK = ROOT / "tests/golden/pictures.lock.json"
TEMPLATES = ROOT / "skills/infragram-azure/assets/templates/cloud"


@pytest.fixture(scope="module")
def gate():
    spec = importlib.util.spec_from_file_location("pictures_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


#: Rendering every template in both looks takes a while, so the suite
#: samples: the smallest document, the landing zone with core frames inside
#: an Azure project, and the composed web application. `verify:pictures`, in
#: `verify:all` and CI, renders every template.
SAMPLE = ("azure-aks-baseline", "azure-hub-spoke-landing-zone", "azure-web-app-front-door")


@pytest.fixture(scope="module")
def rendered(gate):
    """Render the sample once per look; the tests below share it."""
    checker = gate.load_checker()
    pictures, findings = {}, []
    for slug in SAMPLE:
        project = gate.CloudProject.load(TEMPLATES / f"{slug}.infragram.json")
        pictures[slug] = {}
        for look in gate.LOOKS:
            svg = gate.picture(project, look)
            pictures[slug][look] = gate.digest(svg)
            errors: list[str] = []
            checker.check_svg(svg, errors, project.model_dump(mode="json"))
            findings += [f"{slug} [{look}]: {error}" for error in errors]
    return pictures, findings


def test_the_lock_exists_and_names_every_template_in_both_looks() -> None:
    assert LOCK.is_file(), "run `python -m infragram verify:pictures --update` to create the lock"
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    slugs = {
        json.loads(p.read_text(encoding="utf-8"))["slug"]
        for p in TEMPLATES.glob("*.infragram.json")
    }
    assert set(lock["pictures"]) == slugs
    for slug, looks in lock["pictures"].items():
        assert set(looks) == {"card", "icon"}, f"{slug}: both looks must be locked"
        assert all(len(value) == 64 for value in looks.values()), f"{slug}: not sha256 digests"


def test_every_template_still_draws_its_golden_picture(gate, rendered) -> None:
    pictures, _ = rendered
    locked = {slug: looks for slug, looks in gate.read_lock().items() if slug in pictures}
    problems = gate.compare(locked, pictures)
    assert problems == [], (
        "pictures drifted from tests/golden/pictures.lock.json; if the change is intended, "
        "run `python -m infragram verify:pictures --update` and commit the lock:\n  - "
        + "\n  - ".join(problems)
    )


def test_no_shipped_template_locks_in_a_picture_defect(rendered) -> None:
    _, findings = rendered
    assert findings == [], "\n  - " + "\n  - ".join(findings)


def _has_components(slug: str) -> bool:
    """A starter with frames only has nothing to draw as a card or an icon."""
    for path in TEMPLATES.glob("*.infragram.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("slug") != slug:
            continue
        stack = [data["topology"]]
        while stack:
            element = stack.pop()
            if element.get("component") or (
                element.get("type") not in ("group", None) and not element.get("children")
            ):
                return True
            stack.extend(element.get("children") or [])
    return False


def test_the_two_looks_of_a_template_are_different_pictures(rendered) -> None:
    """Cards and icons must not collapse into one drawing, wherever there is
    a component to draw; a frames-only starter legitimately looks the same."""
    pictures, _ = rendered
    checked = 0
    for slug, looks in pictures.items():
        if not _has_components(slug):
            continue
        checked += 1
        assert looks["card"] != looks["icon"], f"{slug}: card and icon looks render identically"
    assert checked == len(pictures), "every sampled template has components to draw"
