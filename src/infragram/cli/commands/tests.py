"""One command per suite, each run under pytest."""

from __future__ import annotations

__all__ = ["COMMANDS"]

#: command -> (script path relative to scripts/, help text)
COMMANDS: dict[str, tuple[str, str]] = {
    "test:builder": ("tests/unit/test_architecture_builder.py", "scene renderer layout invariants"),
    "test:nodes": ("tests/unit/test_nodes.py", "node class contract: icons, nesting, theming"),
    "test:catalog": ("tests/unit/test_provider_catalog.py", "theme catalog regression tests"),
    "test:categories": ("tests/unit/test_cloud_categories.py", "shared category contract"),
    "test:exports": (
        "tests/unit/test_cloud_project_exports.py",
        "project and artifact export contracts",
    ),
    "test:package": ("tests/integration/test_plugin_package.py", "adversarial package-gate tests"),
    "test:providers": (
        "tests/integration/test_provider_suite.py",
        "icon registry contract and DigitalOcean artwork",
    ),
    "test:skill": (
        "tests/skill/test_skill_structure.py",
        "skill layout, catalogs, manifest paths, committed icon index",
    ),
    "test:skill-runtime": (
        "tests/skill/test_skill_runtime.py",
        "shipped scripts run from an installed copy and from the wheel layout",
    ),
    "test:skill-sealed": (
        "tests/skill/test_skill_is_self_contained.py",
        "skill imports stdlib only, no dev-tree refs",
    ),
}
