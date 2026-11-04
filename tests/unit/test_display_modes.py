"""Two ways to draw a component, and both exportable from one document.

``card`` is the titled box with the icon in a lane beside the text. ``icon``
is the bare vendor mark with its caption beneath, the way the vendors' own
reference architectures are drawn. The choice lives on the project, a node
may override it, and the exporter can write either look or both from the
same HTML without changing what the author saved.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from infragram import compose
from infragram.exports import (
    EXPORT_DISPLAYS,
    ExportError,
    editor_page_url,
    export_many,
    export_project,
    render_project_html,
)
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import compute, databases
from infragram.nodes.frames import azure as frames
from infragram.projects import CloudProject, Presentation

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
TEMPLATE = (
    ROOT / "skills/infragram-azure/assets/templates/cloud/azure-web-app-front-door.infragram.json"
)
SLUG = "azure-web-app-front-door"


@pytest.fixture(autouse=True)
def _fresh_ids():
    reset_ids()


def _estate():
    subscription = frames.Subscription("Production")
    vnet = subscription >> frames.ResourceGroup("rg-prod") >> frames.VNet("VNet")
    web = (
        vnet
        >> frames.Subnet("Private")
        >> compute.VirtualMachine("Application Gateway Ingress Controller", "long name")
    )
    db = vnet >> frames.Subnet("Data") >> databases.SQLDatabase("SQL", "zone redundant")
    users = shared.identity.PublicUsers("Users", "internet")
    users.to(web, label="HTTPS")
    web.to(db, label="SQL")
    return [users, subscription], web, db


def _state(html: str) -> dict:
    match = re.search(r'<script[^>]*id="infragram-editor-state"[^>]*>(.*?)</script>', html, re.S)
    assert match
    return json.loads(match.group(1))


def _static_groups(html: str, display: str) -> list[str]:
    """The static renderer's node groups drawn in ``display``."""
    return re.findall(rf'<g [^>]*data-node="[^"]*" data-display="{display}">(.*?)</g>', html, re.S)


# ------------------------------------------------------------- the model
def test_a_project_draws_bare_marks_unless_told_otherwise() -> None:
    """Azure's own reference architectures draw the deck's marks bare with a
    caption, not boxed, so that is what a document draws when it says
    nothing. A document that wants the boxes still asks for them, and one
    that already asked keeps what it asked for."""
    assert Presentation().display == "icon"
    assert Presentation(display="card").display == "card"
    # The shipped templates pin nothing, so they follow the house default.
    project = CloudProject.load(TEMPLATE)
    assert project.presentation.display == "icon"
    assert "display" not in TEMPLATE.read_text(encoding="utf-8")


def test_the_display_must_be_card_or_icon() -> None:
    with pytest.raises(ValidationError):
        Presentation(display="sticker")


# ---------------------------------------------------------- compose path
def test_compose_carries_the_display_into_the_document_and_the_canvas() -> None:
    elements, web, db = _estate()
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="icon")
    assert project.presentation.display == "icon"

    state = _state(render_project_html(project))
    assert state["canvas"]["displayMode"] == "icon"
    assert {node["displayMode"] for node in state["nodes"]} == {"icon"}


def test_an_icon_node_is_sized_for_its_caption_not_for_a_text_lane() -> None:
    elements, web, db = _estate()
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="icon")
    nodes = {node["name"]: node for node in _state(render_project_html(project))["nodes"]}
    assert (nodes["SQL"]["width"], nodes["SQL"]["height"]) == (144, 116)
    # The long name grows the node, the same as a card grows in fit sizing.
    assert nodes["Application Gateway Ingress Controller"]["width"] > 144
    assert nodes["Application Gateway Ingress Controller"]["height"] == 116


def test_a_nodes_own_choice_wins_over_the_project_default() -> None:
    elements, web, db = _estate()
    db.attributes["editor_display_mode"] = "card"
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="icon")
    nodes = {node["name"]: node for node in _state(render_project_html(project))["nodes"]}
    assert nodes["SQL"]["displayMode"] == "card"
    assert nodes["Users"]["displayMode"] == "icon"


def test_a_saved_card_size_does_not_leak_into_icon_display() -> None:
    """A width a card was stretched to describes a card. Drawn as an icon,
    the same node takes the caption size, not a 288 px invisible box."""
    elements, web, db = _estate()
    db.attributes["editor_card_size"] = {"width": 288, "height": 72}
    project = compose.to_project(elements, slug="d", title="D", description="d.", display="icon")
    nodes = {node["name"]: node for node in _state(render_project_html(project))["nodes"]}
    assert (nodes["SQL"]["width"], nodes["SQL"]["height"]) == (144, 116)


# ------------------------------------------------------- static renderer
def test_the_static_render_draws_icons_without_a_box() -> None:
    elements, web, db = _estate()
    html = render_project_html(
        compose.to_project(elements, slug="d", title="D", description="d.", display="icon")
    )
    groups = _static_groups(html, "icon")
    assert groups, "no icon-display node groups in the static render"
    for body in groups:
        visible = [
            r
            for r in re.findall(r"<rect[^>]*>", body)
            if 'fill="none"' not in r or 'stroke="none"' not in r
        ]
        assert visible == [], "an icon node must not draw a visible card box"
        assert 'text-anchor="middle"' in body, "the caption is centred under the glyph"


def test_the_static_render_keeps_the_box_for_cards() -> None:
    elements, web, db = _estate()
    html = render_project_html(
        compose.to_project(elements, slug="d", title="D", description="d.", display="card")
    )
    groups = _static_groups(html, "card")
    assert groups and all("<rect" in body for body in groups)


# -------------------------------------------------------------- exports
def test_the_capture_url_carries_the_display(tmp_path: Path) -> None:
    page = tmp_path / "d.html"
    page.write_text("<html></html>", encoding="utf-8")
    assert editor_page_url(page, "light", "icon").endswith(
        "?motion=static&theme=light&display=icon"
    )
    assert "display=" not in editor_page_url(page, "light")
    with pytest.raises(ExportError, match="card or icon"):
        editor_page_url(page, display="sticker")


def _renderers(calls: list[tuple[str, str | None]]):
    def svg(source: Path, output: Path, display: str | None = None) -> None:
        calls.append((output.name, display))
        output.write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")

    def png(source: Path, output: Path, scale: float, display: str | None = None) -> None:
        calls.append((output.name, display))
        output.write_bytes(b"PNG")

    return svg, png


def test_export_both_writes_cards_and_an_icons_variant(tmp_path: Path) -> None:
    calls: list[tuple[str, str | None]] = []
    svg, png = _renderers(calls)
    project = CloudProject.load(TEMPLATE)
    result = export_project(
        project,
        tmp_path,
        formats=("svg", "png"),
        svg_renderer=svg,
        png_renderer=png,
        display="both",
    )
    assert result.svg == tmp_path / f"{SLUG}.svg"
    assert result.svg_icons == tmp_path / f"{SLUG}-icons.svg"
    assert result.png == tmp_path / f"{SLUG}.png"
    assert result.png_icons == tmp_path / f"{SLUG}-icons.png"
    assert all(
        path.is_file() for path in (result.svg, result.svg_icons, result.png, result.png_icons)
    )
    assert sorted(calls) == [
        (f"{SLUG}-icons.png", "icon"),
        (f"{SLUG}-icons.svg", "icon"),
        (f"{SLUG}.png", "card"),
        (f"{SLUG}.svg", "card"),
    ]


def test_both_can_write_only_the_document_look_when_explicit(tmp_path: Path) -> None:
    calls: list[tuple[str, str | None]] = []
    svg, png = _renderers(calls)
    project = CloudProject.load(TEMPLATE)
    result = export_project(
        project,
        tmp_path,
        formats=("svg", "png"),
        svg_renderer=svg,
        png_renderer=png,
        display="both",
        write_looks="document",
    )
    assert result.svg == tmp_path / f"{SLUG}.svg" and result.svg.is_file()
    assert result.png == tmp_path / f"{SLUG}.png" and result.png.is_file()
    assert result.svg_icons is None and result.png_icons is None
    assert sorted(calls) == [(f"{SLUG}.png", None), (f"{SLUG}.svg", None)]
    assert project.presentation.display == "icon"


def test_cli_preserves_both_written_looks_by_default() -> None:
    from infragram.cli.user.compose import build_parser

    options = build_parser().parse_args(["diagram.py", "--display", "both"])
    assert options.write_looks == "both"
    explicit = build_parser().parse_args(
        [
            "diagram.py",
            "--display",
            "both",
            "--write-looks",
            "document",
        ]
    )
    assert explicit.write_looks == "document"


def test_export_follows_the_document_unless_a_display_is_forced(tmp_path: Path) -> None:
    calls: list[tuple[str, str | None]] = []
    svg, png = _renderers(calls)
    project = CloudProject.load(TEMPLATE)
    result = export_project(project, tmp_path, formats=("png",), png_renderer=png)
    assert result.png_icons is None
    assert calls == [(f"{SLUG}.png", None)]

    calls.clear()
    export_project(
        project, tmp_path, formats=("png",), png_renderer=png, display="icon", overwrite=True
    )
    assert calls == [(f"{SLUG}.png", "icon")]


def test_export_refuses_a_renderer_that_cannot_draw_the_requested_display(tmp_path: Path) -> None:
    """An injected fake with the old three-argument shape cannot be asked for
    icons; dropping the request would be a silent wrong picture."""

    def legacy(source: Path, output: Path, scale: float) -> None:
        output.write_bytes(b"PNG")

    project = CloudProject.load(TEMPLATE)
    with pytest.raises(ExportError, match="takes no display argument"):
        export_project(project, tmp_path, formats=("png",), png_renderer=legacy, display="icon")
    # ...but the plain export still works with it.
    export_project(project, tmp_path, formats=("png",), png_renderer=legacy, overwrite=True)


def test_export_rejects_an_unknown_display(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="display choice"):
        export_project(CloudProject.load(TEMPLATE), tmp_path, formats=("html",), display="poster")
    assert EXPORT_DISPLAYS == ("project", "card", "icon", "both")


# ----------------------------------------------------------- batch export
def test_export_many_exports_every_project_in_the_order_given(tmp_path: Path) -> None:
    calls: list[tuple[str, str | None]] = []
    svg, png = _renderers(calls)
    base = CloudProject.load(TEMPLATE)
    projects = [base.model_copy(update={"slug": f"estate-{n}"}) for n in range(3)]
    results = export_many(
        projects, tmp_path, concurrency=3, formats=("html", "png"), png_renderer=png
    )
    assert [result.png.name for result in results] == [
        "estate-0.png",
        "estate-1.png",
        "estate-2.png",
    ]
    assert all(result.png.is_file() and result.html.is_file() for result in results)


def test_export_many_refuses_projects_that_would_write_over_each_other(tmp_path: Path) -> None:
    base = CloudProject.load(TEMPLATE)
    with pytest.raises(ExportError, match="distinct slugs"):
        export_many([base, base], tmp_path, formats=("html",))
    with pytest.raises(ExportError, match="at least 1"):
        export_many([base], tmp_path, concurrency=0, formats=("html",))


# -------------------------------------------------------------- runtime
def test_the_editor_can_switch_the_whole_diagram_and_the_exporters_can_ask_it_to() -> None:
    html = render_project_html(CloudProject.load(TEMPLATE))
    assert "const applyProjectDisplayMode = " in html
    assert "data-inspector-display" in html and 'data-project-display="icon"' in html
    assert "workspaceParams.get('display')" in html
    assert "setDisplayMode: mode => applyProjectDisplayMode(mode, {persist: false})" in html
    # the template the page downloads remembers the choice
    assert "project.presentation = {...(project.presentation || {}), display:" in html
    # and an icon node is sized to its caption, as the Python layout sizes it
    assert "const iconNodeWidth = node =>" in html
