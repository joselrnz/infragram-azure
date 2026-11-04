"""Which components draw bare is written once and read everywhere (ADR 0005).

The rules file names, per library, the glyphs the deck places bare: general
icons, actors and endpoints, shared line art. Service tiles, logos and
Kubernetes objects keep the card. The resolver is the only reader; the
scene, the sidebar payload and the editor state all agree with it, and a
node's own choice still wins.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from infragram import compose
from infragram.catalog.display import (
    DISPLAYS,
    default_display,
    load_display_defaults,
)
from infragram.editor.shell import library_catalog_from_html
from infragram.exports import render_project_html
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import compute, databases, general
from infragram.nodes.frames import azure as frames
from infragram.paths import skill_assets

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
INVENTORY = json.loads((skill_assets() / "catalog/inventory.json").read_text(encoding="utf-8"))
LIBRARIES = {lib["id"]: {c["id"]: c for c in lib["components"]} for lib in INVENTORY["libraries"]}
LIBRARIES["infragram"] = {c["id"]: c for c in INVENTORY["shared_primitives"]}


@pytest.fixture(autouse=True)
def _fresh_ids():
    reset_ids()


def _state(html: str) -> dict:
    match = re.search(r'<script[^>]*id="infragram-editor-state"[^>]*>(.*?)</script>', html, re.S)
    assert match
    return json.loads(match.group(1))


def _library(html: str) -> dict:
    return library_catalog_from_html(html)


# ------------------------------------------------------------- the file
def test_the_rules_file_is_well_formed_and_every_id_it_names_exists() -> None:
    data = load_display_defaults()
    assert data.default == "card"
    for rule in data.rules:
        assert rule.display in DISPLAYS
        assert rule.why, rule
        if rule.provider == "*":
            continue
        assert rule.provider in LIBRARIES, rule.provider
        for component_id in [*rule.match.get("ids", []), *rule.match.get("not_ids", [])]:
            assert component_id in LIBRARIES[rule.provider], (
                f"{rule.provider}:{component_id} is not a shipped component"
            )
        for prefix in rule.match.get("prefixes", []):
            assert any(c.startswith(prefix) for c in LIBRARIES[rule.provider]), (
                f"{rule.provider}: nothing starts with {prefix!r}"
            )


def test_a_malformed_rules_file_is_refused(tmp_path: Path) -> None:
    load_display_defaults.cache_clear()
    bad = tmp_path / "display-defaults.json"
    bad.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "default": "card",
                "rules": [{"provider": "azure", "match": {"colour": "red"}, "display": "icon"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_display_defaults(bad)
    load_display_defaults.cache_clear()


# --------------------------------------------------------- the resolver
@pytest.mark.parametrize(
    "provider, component_id, tier, category, expected",
    [
        ("azure", "globe-success", None, "general", "icon"),
        ("azure", "users", None, "identity", "icon"),
        ("azure", "client-apps", None, "intune", "icon"),
        ("azure", "virtual-machine", None, "compute", "card"),
        ("kubernetes", "user", None, "containers", "icon"),
        ("kubernetes", "pod", None, "containers", "card"),
        ("infragram", "public-users", None, "identity", "icon"),
        ("infragram", "core-switch", None, "networking", "icon"),
        ("infragram", "brand-ibm", None, "integration", "card"),
        ("infragram", "data-tableau", None, "analytics", "card"),
        ("infragram", "language-python", None, "devops", "card"),
        ("infragram", "kubernetes-pod", None, "containers", "card"),
        ("infragram", "slack", None, "integration", "card"),
        (None, None, None, None, "card"),
    ],
)
def test_the_resolver_draws_the_decks_bare_glyphs_bare_and_the_tiles_as_cards(
    provider: str | None,
    component_id: str | None,
    tier: str | None,
    category: str | None,
    expected: str,
) -> None:
    assert default_display(provider, component_id, tier=tier, category=category) == expected


def test_a_resource_tier_glyph_is_bare_in_any_library() -> None:
    for provider in ("azure", "kubernetes", "some-future-deck"):
        assert default_display(provider, "anything", tier="resource") == "icon"
    # A deck with no rules of its own still gets the one wildcard rule.
    future_rules = [
        rule.match
        for rule in load_display_defaults().rules
        if rule.provider in ("*", "some-future-deck")
    ]
    assert future_rules == [{"tier": "resource"}]


# --------------------------------------------------- the sidebar payload
def test_the_sidebar_payload_carries_the_same_answer_for_every_component() -> None:
    elements = [frames.Subscription("Production") >> compute.VirtualMachine("App", "web")]
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    components = _library(render_project_html(project))["components"]
    assert components, "the payload lists components"
    # The payload carries the canonical category; the rule reads the deck's
    # own folder, which the sidebar catalog still knows.
    from infragram.editor import load_sidebar_catalog

    native = {
        (item.provider_id, item.id): item.native_category
        for category in load_sidebar_catalog("azure").categories
        for item in category.components
    }
    for component in components:
        expected = default_display(
            component["provider"],
            component["serviceId"],
            tier=component.get("tier"),
            category=native.get((component["provider"], component["serviceId"]))
            or component.get("categoryId"),
        )
        assert component["defaultDisplay"] in DISPLAYS
        if component["provider"] in ("azure", "infragram"):
            assert component["defaultDisplay"] == expected, component["qualifiedId"]
    by_id = {c["qualifiedId"]: c["defaultDisplay"] for c in components}
    assert by_id["azure:globe-success"] == "icon"
    assert by_id["azure:users"] == "icon"
    assert by_id["azure:virtual-machine"] == "card"
    assert by_id["infragram:public-users"] == "icon"
    assert by_id["infragram:brand-ibm"] == "card"


# ------------------------------------------------------ the editor state
def test_a_card_diagram_draws_actors_and_hardware_bare_and_tiles_and_logos_carded() -> None:
    subscription = frames.Subscription("Production")
    vnet = subscription >> frames.ResourceGroup("rg-prod") >> frames.VNet("VNet")
    app = vnet >> frames.Subnet("Private") >> compute.VirtualMachine("App server", "web tier")
    vnet >> frames.Subnet("Public") >> general.Browser("Browser", "client")
    users = shared.identity.PublicUsers("Users", "customers")
    switch = shared.networking.CoreSwitch("Core switch", "campus")
    logo = shared.integration.BrandIBM("DataStage", "ETL")
    sql = databases.SQLServer("SQL Server", "OLTP")
    users.to(app, label="HTTPS")
    project = compose.to_project(
        [users, switch, logo, sql, subscription],
        slug="d",
        title="D",
        description="d.",
        display="card",
    )
    state = _state(render_project_html(project))
    modes = {node["name"]: node["displayMode"] for node in state["nodes"]}
    defaults = {node["name"]: node["defaultDisplay"] for node in state["nodes"]}
    assert modes["Users"] == "icon" and defaults["Users"] == "icon"
    assert modes["Core switch"] == "icon"
    assert modes["Browser"] == "icon"
    assert modes["App server"] == "card" and defaults["App server"] == "card"
    assert modes["DataStage"] == "card"
    assert modes["SQL Server"] == "card"


def test_a_nodes_own_choice_still_wins_over_the_rules() -> None:
    users = shared.identity.PublicUsers("Users", "customers")
    users.attributes["editor_display_mode"] = "card"
    project = compose.to_project([users], slug="d", title="D", description="d.", display="card")
    modes = {
        node["name"]: node["displayMode"] for node in _state(render_project_html(project))["nodes"]
    }
    assert modes["Users"] == "card"
