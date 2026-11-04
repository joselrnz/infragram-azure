"""The gates. `verify:all` runs the ones that need no browser, in
CI's order, stopping at the first failure; `verify:quick` runs the part of
them a change is checked with.
"""

from __future__ import annotations

from ..scripts import PYTEST_PREFIX, STEP_PREFIX

__all__ = ["COMMANDS", "FIXED_ARGS", "VERIFY_ALL", "VERIFY_QUICK"]

#: command -> (script path relative to scripts/, help text)
COMMANDS: dict[str, tuple[str, str]] = {
    "verify:pictures": (
        "verify/pictures.py",
        "every shipped template still draws its golden picture, cards and icons, and passes the picture checks (pass --update to accept a change)",
    ),
    "verify:browser": (
        "verify/browser.py",
        "run the Chromium editor suite that pytest otherwise skips",
    ),
    "verify:docs": ("verify/docs-sync.py", "docs and routing sync gate"),
    "verify:lint": (
        "verify/lint.py",
        "ruff over the whole tree, with the rules pyproject.toml selects and its layout",
    ),
    "verify:types": (
        "verify/typecheck.py",
        "mypy over the package, the examples and the maintainer scripts, then the skill's scripts",
    ),
    "verify:audit": (
        "verify/audit.py",
        "every package uv.lock pins, checked against the published vulnerability advisories (needs the network)",
    ),
    "verify:line-endings": (
        "verify/line-endings.py",
        "every tracked text file is LF (SVG artwork is kept byte for byte)",
    ),
    "verify:naming": (
        "verify/naming.py",
        "no previous product name, client project names, or machine paths in the tree",
    ),
    "verify:package": (
        "verify/plugin-package.py",
        "check synchronized package versions and marketplace paths; versions may stay unchanged or increase",
    ),
    "verify:wheel": (
        "verify/wheel.py",
        "build the wheel and draw a template from an installed copy, far from the checkout",
    ),
    "verify:install": (
        "verify/install.py",
        "install the plugin as users do (repository, npm package, wheel) into throwaway Claude Code, Codex and uv homes, and check what each loads",
    ),
    "verify:ink": (
        "tools/ink-profiles.py",
        "check the ink profiles cover the shipped artwork, in Chromium (passes --check itself)",
    ),
    "verify:terraform": (
        "verify/terraform.py",
        "every shipped template's Terraform skeleton passes terraform fmt and, offline with the providers in TF_PLUGIN_CACHE_DIR, terraform validate (needs the Terraform CLI)",
    ),
}


#: Arguments a command always passes to its script. `verify:inventory` once
#: mapped to the same script as `inventory` with nothing added, so it
#: regenerated the inventory and exited 0 instead of checking it. A user
#: passing one of these again is refused rather than doubled.
FIXED_ARGS: dict[str, tuple[str, ...]] = {
    "verify:inventory": ("--check",),
    "verify:ink": ("--check",),
}


#: `verify:all` runs these in order with the arguments CI uses: the `gates`
#: job of .forgejo/workflows/ci.yml, step for step (tests/unit/test_gates.py
#: holds the two to the same list). The suite entry
#: mirrors CI's `python -m pytest tests/unit tests/skill tests/integration`;
#: the browser tests inside it skip themselves unless
#: INFRAGRAM_RUN_BROWSER_TESTS is set, exactly as they do in CI.
VERIFY_ALL: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("verify/plugin-package.py", ()),
    ("verify/lint.py", ()),
    ("verify/typecheck.py", ()),
    ("verify/line-endings.py", ()),
    ("verify/naming.py", ()),
    (f"{PYTEST_PREFIX}tests/unit tests/skill tests/integration", ()),
    ("tools/generate-nodes.py", ("--check",)),
    ("build/vendor-tiles.py", ("--check",)),
    ("verify/wheel.py", ()),
    (f"{STEP_PREFIX}export-templates", ()),
    ("verify/pictures.py", ()),
    ("verify/docs-sync.py", ()),
    ("inventory/build.py", ("--check",)),
    ("verify/audit.py", ()),
)


#: `verify:quick` runs these after a change: lint, types, the tree gates, and
#: the unit and skill suites without the tests marked ``slow`` (the ones that
#: sweep every shipped template, example or icon). `verify:all` is the full
#: check a release runs; it adds the dependency audit, which needs the network.
VERIFY_QUICK: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("verify/lint.py", ()),
    ("verify/typecheck.py", ()),
    ("verify/line-endings.py", ()),
    ("verify/naming.py", ()),
    ("verify/docs-sync.py", ()),
    ("verify/plugin-package.py", ()),
    (f"{PYTEST_PREFIX}tests/unit tests/skill", ("-m", "not slow")),
)
