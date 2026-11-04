"""A gate that cannot fail is worse than no gate: it reports a pass nobody earned.

Four ways that happened here, each with a test so it cannot come back quietly:

- a ``test:*`` command ran a module as a plain script, and a module that only
  defines test functions exits 0 having run none of them;
- ``verify:all`` named test modules one at a time, so most of the suite never
  ran locally and two of the named ones ran nothing;
- ``verify:render`` re-exported the document for every look, discarding the
  saved layout it was asked to check;
- the inventory dropped a component the product ships, and the shipped
  checker reads the inventory, so it rejected honest documents.
"""

from __future__ import annotations

import importlib.util
import json
import sys

import pytest

from infragram import cli
from infragram.catalog import load_provider_component_catalog
from infragram.catalog.specs import CUSTOM_COMPONENT_SPECS
from infragram.editor.sidebar import load_sidebar_catalog
from infragram.paths import repo_root
from infragram.projects import CloudProject

ROOT = repo_root()
INVENTORY = ROOT / "skills" / "infragram-azure" / "assets" / "catalog" / "inventory.json"
TEMPLATES = ROOT / "skills" / "infragram-azure" / "assets" / "templates" / "cloud"


# ------------------------------------------------------- the CLI's own gates
def test_every_test_command_runs_its_module_under_pytest(monkeypatch) -> None:
    """Run as a plain script, a pytest-only module exits 0 having run nothing."""
    captured: list[list[str]] = []

    class Completed:
        returncode = 0

    monkeypatch.setattr(
        cli.runner.subprocess,
        "run",
        lambda argv, **kwargs: (captured.append(list(argv)), Completed())[1],
    )
    commands = {name: entry for name, entry in cli.COMMANDS.items() if name.startswith("test:")}
    assert commands, "no test:* commands found; the table moved"
    for name, (script, _help) in commands.items():
        captured.clear()
        assert cli.run_script(script, ()) == 0
        argv = captured[0]
        assert "pytest" in argv, f"{name} runs {script} as a plain script: {argv}"


def test_verify_all_runs_the_suite_rather_than_naming_modules() -> None:
    suite = [script for script, _ in cli.VERIFY_ALL if script.startswith(cli.PYTEST_PREFIX)]
    assert len(suite) == 1, f"expected one suite entry, got {suite}"
    targets = suite[0][len(cli.PYTEST_PREFIX) :].split()
    assert "tests/unit" in targets and "tests/skill" in targets, targets

    named = [script for script, _ in cli.VERIFY_ALL if script.startswith("tests/")]
    assert named == [], f"verify:all names test modules one by one again: {named}"


# --------------------------------------------------- what verify:render checks
def _render_gate():
    path = ROOT / "scripts" / "verify" / "render.py"
    spec = importlib.util.spec_from_file_location("infragram_verify_render", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_verify_render_checks_the_page_it_was_given_for_the_documents_own_look(tmp_path) -> None:
    """A re-export drops the saved editor geometry, so the placed layout would
    never be the one rendered."""
    module = _render_gate()
    project = CloudProject.load(sorted(TEMPLATES.glob("*.infragram.json"))[0])
    page = tmp_path / "page.html"
    page.write_text("<html></html>", encoding="utf-8")

    for look in (None, "project", project.presentation.display):
        assert module.page_for_look(project, page, look, tmp_path) is page, look


# ------------------------------------- the inventory the shipped checker reads
def _inventory_component_ids() -> set[str]:
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    known = {f"infragram:{item['id']}" for item in data["shared_primitives"]}
    known |= {f"infragram:{item['id']}" for item in data["core_frames"]}
    for library in data["libraries"]:
        known |= {f"{library['id']}:{item['id']}" for item in library["components"]}
        known |= {f"infragram:{item['id']}" for item in library["frames"]}
    return known


@pytest.mark.parametrize("spec", CUSTOM_COMPONENT_SPECS, ids=lambda spec: spec[0])
def test_every_shipped_custom_component_reaches_the_inventory(spec) -> None:
    """A boundary belonging to no library is still a component the product
    ships; dropping it made `infragram check` reject honest documents."""
    assert f"infragram:{spec[0]}" in _inventory_component_ids()


def test_the_catalog_offers_the_platform_card_the_sidebar_offers() -> None:
    """The two disagreed: the sidebar showed the Kubernetes platform card and a
    shipped template placed it, while compose refused to qualify it."""
    catalog = {
        component.service_id
        for component in load_provider_component_catalog("kubernetes").components
    }
    # The sidebar also lists the shared primitives and the generic frames,
    # which belong to no library; only its own cards are the catalog's to hold.
    sidebar = {
        component.id
        for category in load_sidebar_catalog("kubernetes").categories
        for component in category.components
        if component.provider_id == "kubernetes"
    }
    assert "kubernetes" in catalog, "the platform card is missing from the catalog"
    assert sidebar - catalog == set(), (
        f"the sidebar offers what compose refuses: {sidebar - catalog}"
    )


def test_every_shipped_template_qualifies() -> None:
    """`infragram compose` must accept every document the product ships."""
    from infragram import compose

    failures = []
    for path in sorted(TEMPLATES.glob("*.infragram.json")):
        try:
            compose.qualify(CloudProject.load(path).topology)
        except Exception as error:  # noqa: BLE001 - the message is the report
            failures.append(f"{path.name}: {error}")
    assert failures == [], failures


#: Browser suites the Chromium gate deliberately does not run, and why. The
#: engine checks drive Firefox and WebKit, which are not installed with
#: Chromium and skip until ``python -m playwright install firefox webkit``.
NOT_ON_THE_CHROMIUM_GATE = {"test_engines_browser.py"}


def test_every_browser_suite_is_one_the_browser_gate_runs() -> None:
    """A browser test nobody runs is a feature nobody checks.

    `scripts/verify/browser.py` names its suites one by one rather than
    globbing, so a new file guarded by INFRAGRAM_RUN_BROWSER_TESTS is skipped
    everywhere at once: the ordinary suite skips it for want of the flag, and
    the gate skips it for want of a line. Both look green. The full edition
    found one of its own suites in exactly that state.
    """
    import re

    gate = (ROOT / "scripts" / "verify" / "browser.py").read_text(encoding="utf-8")
    listed = set(re.findall(r'"(test_[a-z0-9_]+\.py)"', gate))
    guarded = {
        path.name
        for path in sorted((ROOT / "tests" / "integration").glob("test_*.py"))
        if "INFRAGRAM_RUN_BROWSER_TESTS" in path.read_text(encoding="utf-8")
    }
    unrun = guarded - listed - NOT_ON_THE_CHROMIUM_GATE
    assert unrun == set(), f"browser suites the gate never runs: {sorted(unrun)}"
    missing = {name for name in listed if not (ROOT / "tests" / "integration" / name).is_file()}
    assert missing == set(), f"the gate names suites that do not exist: {sorted(missing)}"
    stale = {
        name
        for name in NOT_ON_THE_CHROMIUM_GATE
        if not (ROOT / "tests" / "integration" / name).is_file() or name in listed
    }
    assert stale == set(), f"exemptions that no longer apply: {sorted(stale)}"
