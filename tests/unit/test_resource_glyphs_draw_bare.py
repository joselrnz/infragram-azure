"""A deck's bare glyph draws bare; a service keeps its card.

Vendor decks draw two kinds of artwork. A service is a coloured tile and
reads well in a titled card. The Azure deck's General folder -- browser,
mobile, globe, file -- and its actors (users, client apps) are line glyphs
Microsoft places bare beside its services, with a caption beneath. The rule
follows the artwork through one function, so the editor state, the static
fallback and the sidebar all agree, and a node's own saved choice still
wins.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from infragram import compose
from infragram.builders.architecture import display_of, icon_for
from infragram.editor.shell import library_catalog_from_html
from infragram.exports import render_project_html
from infragram.models.topology import TopologyElement
from infragram.nodes import reset_ids
from infragram.nodes.azure import compute, general, identity
from infragram.nodes.frames import azure as frames
from infragram.projects import CloudProject

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
FRONT_DOOR = (
    ROOT / "skills/infragram-azure/assets/templates/cloud/azure-web-app-front-door.infragram.json"
)


@pytest.fixture(autouse=True)
def _fresh_ids():
    reset_ids()


def _estate():
    subscription = frames.Subscription("Production")
    vnet = subscription >> frames.ResourceGroup("rg-prod") >> frames.VNet("VNet")
    public = vnet >> frames.Subnet("Public")
    browser = public >> general.Browser("Browser", "client")
    operators = vnet >> identity.Users("Operators", "on call")
    app = vnet >> frames.Subnet("Private") >> compute.VirtualMachine("App server", "web tier")
    operators.to(browser, label="support")
    app.to(browser, label="serves")
    return [subscription], browser, operators, app


def _state(html: str) -> dict:
    match = re.search(r'<script[^>]*id="infragram-editor-state"[^>]*>(.*?)</script>', html, re.S)
    assert match
    return json.loads(match.group(1))


def _library(html: str) -> dict:
    return library_catalog_from_html(html)


def _static_groups(html: str, display: str) -> list[str]:
    return re.findall(rf'<g [^>]*data-node="([^"]*)" data-display="{display}">', html)


# ------------------------------------------------------------- the rule
def test_the_rule_reads_the_deck_and_the_nodes_own_choice_wins() -> None:
    elements, browser, operators, app = _estate()
    # The rule reads the component reference, which compose writes on
    # qualification; a bare node class carries only its collection and icon.
    compose.qualify(elements[0])
    assert icon_for(browser).category == "general"
    assert icon_for(app).category == "compute"
    assert display_of(browser, "card", icon_for(browser)) == "icon"
    assert display_of(operators, "card", icon_for(operators)) == "icon"
    assert display_of(app, "card", icon_for(app)) == "card"
    assert display_of(app, "icon", icon_for(app)) == "icon"
    browser.attributes["editor_display_mode"] = "card"
    assert display_of(browser, "card", icon_for(browser)) == "card"


def test_a_plain_element_without_artwork_follows_the_project() -> None:
    plain = TopologyElement(id="x", name="X", type="server")
    assert display_of(plain, "card") == "card"
    assert display_of(plain, "icon") == "icon"


# --------------------------------------------------------- editor state
def test_bare_glyphs_land_bare_in_a_card_diagram() -> None:
    elements, *_ = _estate()
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    assert project.presentation.display == "card"
    state = _state(render_project_html(project))
    nodes = {node["name"]: node for node in state["nodes"]}
    assert state["canvas"]["displayMode"] == "card"
    assert nodes["Browser"]["displayMode"] == "icon"
    assert nodes["Operators"]["displayMode"] == "icon"
    assert nodes["App server"]["displayMode"] == "card"
    # the Azure deck files everything as a service; the glyph draws bare by rule, not by tier
    assert nodes["Browser"]["tier"] == "service"
    assert nodes["App server"]["tier"] == "service"
    # sized as an icon node, not as a card with an empty text lane
    assert nodes["Browser"]["height"] == 116


def test_a_boxed_glyph_stays_boxed_when_the_node_says_so() -> None:
    elements, browser, *_ = _estate()
    browser.attributes["editor_display_mode"] = "card"
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    nodes = {node["name"]: node for node in _state(render_project_html(project))["nodes"]}
    assert nodes["Browser"]["displayMode"] == "card"
    assert nodes["Operators"]["displayMode"] == "icon"


# -------------------------------------------------------- static fallback
def test_the_static_fallback_draws_the_same_answer() -> None:
    elements, browser, operators, app = _estate()
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    html = render_project_html(project)
    assert {browser.id, operators.id} <= set(_static_groups(html, "icon"))
    assert app.id in _static_groups(html, "card")


# --------------------------------------------------------------- sidebar
def test_the_sidebar_payload_carries_each_components_default_look() -> None:
    elements, *_ = _estate()
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    components = {c["qualifiedId"]: c for c in _library(render_project_html(project))["components"]}
    assert components["azure:browser"]["defaultDisplay"] == "icon"
    assert components["azure:users"]["defaultDisplay"] == "icon"
    assert components["azure:virtual-machine"]["defaultDisplay"] == "card"
    assert components["azure:virtual-machine"]["tier"] == "service"


# ------------------------------------------------------- shipped template
def test_the_front_door_template_shows_its_actors_bare_and_its_services_carded() -> None:
    # The template takes the house default, which is bare (ADR 0007). Asked
    # for the boxed look, its actors stay bare anyway: that is ADR 0005's
    # per-component rule outranking the document, which is what this checks.
    project = CloudProject.load(FRONT_DOOR)
    assert project.presentation.display == "icon"
    project.presentation = project.presentation.model_copy(update={"display": "card"})
    nodes = _state(render_project_html(project))["nodes"]
    by_name: dict[str, set[str]] = {}
    for node in nodes:
        by_name.setdefault(node["name"], set()).add(node["displayMode"])
    assert by_name["Users"] == {"icon"}
    assert by_name["Mobile clients"] == {"icon"}
    assert by_name["App Service"] == {"card"}
