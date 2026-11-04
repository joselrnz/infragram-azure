"""The sidebar finds what people type, and a card fits what it says."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from infragram.builders.scene import Node, Style
from infragram.editor import load_sidebar_catalog
from infragram.editor.shell import library_catalog_from_html
from infragram.exports import render_project_html

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


def _components(provider: str) -> dict[str, object]:
    catalog = load_sidebar_catalog(provider)
    return {
        component.id: component
        for category in catalog.categories
        for component in category.components
    }


@pytest.mark.parametrize(
    ("provider", "service_id", "expected"),
    [
        ("azure", "virtual-networks", "vnet"),
        ("azure", "kubernetes-services", "aks"),
        ("azure", "key-vaults", "secrets"),
        ("azure", "storage-accounts", "blob"),
        ("kubernetes", "cm", "configmap"),
        ("kubernetes", "sts", "statefulset"),
        ("kubernetes", "mainframe", "z/os"),
    ],
)
def test_sidebar_components_carry_their_search_aliases(
    provider: str, service_id: str, expected: str
) -> None:
    component = _components(provider)[service_id]
    assert expected in component.aliases, f"{service_id} aliases: {component.aliases}"


def test_frames_are_findable_as_frames() -> None:
    frame = _components("azure")["custom-boundary-azure-vnet"]
    assert "frame" in frame.aliases and "boundary" in frame.aliases


def test_rendered_sidebar_search_text_includes_aliases() -> None:
    """The search string the sidebar filters on is built server-side."""
    html = render_project_html(_project())
    payload = library_catalog_from_html(html)
    search = {component["qualifiedId"]: component["search"] for component in payload["components"]}
    assert "aks" in search["azure:kubernetes-services"]
    assert "vnet" in search["azure:virtual-networks"]
    assert "blob" in search["azure:storage-accounts"]
    assert "z/os" in search["infragram:mainframe"]
    assert "frame" in search["infragram:custom-boundary-azure-vnet"]


def _project():
    from infragram.author import latest_diagram

    spec = runpy.run_path(str(ROOT / "examples/azure_tenant_to_vm.py"), run_name="__spec__")
    return spec.get("PROJECT") or latest_diagram().to_project()


def _fit_style() -> Style:
    style = Style()
    style.canvas.fit = True
    return style


def test_a_card_grows_to_fit_its_own_name() -> None:
    style = _fit_style()
    short = Node(name="EC2", detail="")
    long = Node(name="Application Load Balancer", detail="HTTPS :443")
    short.resolve(style)
    long.resolve(style)
    assert short.width == style.node.width
    assert long.width > style.node.width
    # what the card is sized for is what the renderer will fit: the runtime
    # budget is (width - 54 - 12) / (font size * 0.58) characters.
    budget = int((long.width - 66) / (style.node.title_size * 0.58))
    assert budget >= len(long.name)
    assert long.width % 4 == 0, "cards stay on the editor's 4px grid"


def test_card_growth_is_capped_and_can_be_disabled() -> None:
    style = _fit_style()
    huge = Node(name="A" * 200, detail="")
    huge.resolve(style)
    assert huge.width == style.node.max_width

    fixed = _fit_style()
    fixed.node.max_width = 0
    node = Node(name="Application Load Balancer", detail="")
    node.resolve(fixed)
    assert node.width == fixed.node.width

    explicit = Node(name="A" * 200, detail="", width=160)
    explicit.resolve(style)
    assert explicit.width == 160, "an author's width is never overridden"

    # A fixed document preset keeps its size promise: the name truncates.
    boxed = Style()
    assert boxed.canvas.fit is False
    node = Node(name="Application Load Balancer", detail="")
    node.resolve(boxed)
    assert node.width == boxed.node.width


def test_long_names_reach_the_editor_untruncated() -> None:
    # A card's width is what has to hold its name, so this asks the example
    # for the boxed look rather than for whatever the document default is.
    project = _project()
    project.presentation = project.presentation.model_copy(update={"display": "card"})
    html = render_project_html(project)
    anchor = html.index('"projectSlug"')
    state = json.JSONDecoder().raw_decode(html[html.rfind("{", 0, anchor) :])[0]
    by_name = {node["name"]: node for node in state["nodes"]}
    card = by_name["Application Gateway"]
    budget = int((card["width"] - 66) / 6.96)
    assert budget >= len(card["name"])
