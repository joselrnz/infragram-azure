"""The shipped picture checker judges dashes by the table the editor draws from.

A connector is dashed exactly when its kind has a dash in the provider's link
table: the built-in dotted and dashed, then whatever the provider theme adds
under ``style.links``. The checker reads that table for the provider whose
theme styles the document, resolved the way the model resolves it.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from infragram.builders.architecture import load_style
from infragram.paths import skill_assets

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


def _checker():
    spec = importlib.util.spec_from_file_location(
        "project_check", ROOT / "skills/infragram-azure/scripts/project_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_the_checker_reads_the_same_dash_table_the_renderer_draws_from() -> None:
    checker = _checker()
    for provider in ("azure", "kubernetes"):
        style = load_style(provider)
        drawn = {kind: link.dash for kind, link in style.links.items() if link.dash}
        judged = {kind: dash for kind, dash in checker.link_dashes(provider).items() if dash}
        assert judged == drawn, provider


def test_the_built_in_kinds_dash_as_the_metrics_say_and_solid_stays_solid() -> None:
    dashes = _checker().link_dashes("azure")
    assert dashes["dotted"] and dashes["dashed"]
    assert dashes.get("solid") is None


def test_an_unknown_provider_falls_back_to_the_built_in_kinds() -> None:
    checker = _checker()
    assert checker.link_dashes("no-such-provider") == checker.default_link_dashes()
    assert checker.link_dashes(None) == checker.default_link_dashes()


@pytest.mark.parametrize(
    "document, expected",
    [
        ({"providers": [{"id": "azure", "enabled": True}]}, "azure"),
        (
            {
                "providers": [
                    {"id": "azure", "enabled": False},
                    {"id": "kubernetes", "enabled": True},
                ]
            },
            "kubernetes",
        ),
        ({"providers": ["kubernetes", "azure"]}, "kubernetes"),
        ({"default_library": "azure", "providers": [{"id": "kubernetes"}]}, "azure"),
        ({"default_library": "all", "providers": [{"id": "azure"}]}, "azure"),
        ({"provider": "kubernetes"}, "kubernetes"),
        ({}, None),
    ],
)
def test_the_primary_provider_resolves_like_the_model(document: dict, expected: str | None) -> None:
    assert _checker().primary_provider(document) == expected


def test_every_shipped_template_resolves_to_a_provider_with_a_theme() -> None:
    checker = _checker()
    themes = skill_assets() / "themes"
    for path in sorted((skill_assets() / "templates").rglob("*.infragram.json")):
        provider = checker.primary_provider(json.loads(path.read_text(encoding="utf-8")))
        assert provider, path.name
        assert (themes / f"{provider}.json").is_file(), f"{path.name}: {provider} has no theme"
