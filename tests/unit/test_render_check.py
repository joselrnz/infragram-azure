"""The picture is checked the way an eye would check it, and the export is
the same picture every time.

`project_check.py` ships inside the skill and imports only the standard
library, so it is loaded here by path: the code that judges a diagram for a
user is the code under test.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from infragram.exports import make_standalone_svg, render_project_html
from infragram.projects import CloudProject

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
CHECKER = ROOT / "skills/infragram-azure/scripts/project_check.py"
TEMPLATES = ROOT / "skills/infragram-azure/assets/templates/cloud"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("project_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def node(node_id: str, x: int, y: int, name: str, display: str = "card") -> str:
    w, h = (144, 116) if display == "icon" else (208, 64)
    text = (
        f'<text x="60" y="70" font-family="Geist" font-size="12" text-anchor="middle">{name}</text>'
        if display == "icon"
        else f'<text x="54" y="30" font-family="Geist" font-size="12">{name}</text>'
    )
    return (
        f'<g data-graph-node="" data-node-id="{node_id}" data-display-mode="{display}" '
        f'transform="translate({x} {y})"><title>{name}</title>'
        f'<rect data-node-surface="" width="{w}" height="{h}"/>{text}</g>'
    )


def edge(
    edge_id: str,
    d: str,
    sx: float,
    sy: float,
    tx: float,
    ty: float,
    end: bool = True,
    start: bool = False,
    dash: str = "",
) -> str:
    markers = (' marker-end="url(#a)"' if end else "") + (
        ' marker-start="url(#a)"' if start else ""
    )
    dasharray = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<path data-graph-edge="" data-edge-id="{edge_id}" data-source-x="{sx}" data-source-y="{sy}" '
        f'data-target-x="{tx}" data-target-y="{ty}" d="{d}" fill="none"{dasharray}{markers}/>'
    )


def label(edge_id: str, x: int, y: int, text: str) -> str:
    w = max(24, len(text) * 9 * 0.62 + 10)
    return (
        f'<g data-edge-label="{edge_id}" transform="translate({x} {y})">'
        f'<rect class="edge-label-mask" x="-4" y="-11" width="{w:g}" height="14"/>'
        f'<text x="0" y="0" font-family="Geist Mono" font-size="9">{text}</text></g>'
    )


def frame(frame_id: str, x: int, y: int, w: int, h: int, title: str) -> str:
    return (
        f'<g data-graph-boundary="" data-boundary-id="{frame_id}">'
        f'<rect data-boundary-surface="" x="{x}" y="{y}" width="{w}" height="{h}" fill="none"/>'
        f'<rect x="{x}" y="{y}" width="20" height="20"/>'
        f'<text x="{x + 25}" y="{y + 13}" font-family="Geist" font-size="10">{title}</text></g>'
    )


def svg(*parts: str, view: str = "0 0 1000 600") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}">{"".join(parts)}</svg>'


# --------------------------------------------------------------- reading
def test_a_clean_picture_passes_and_is_summarised(checker) -> None:
    picture = svg(
        node("a", 40, 100, "Web"),
        node("b", 400, 100, "Database"),
        edge("e1", "M248,132 L400,132", 248, 132, 400, 132),
        label("e1", 300, 124, "SQL"),
        frame("vpc", 20, 60, 700, 200, "VPC"),
    )
    errors: list[str] = []
    summary = checker.check_svg(picture, errors)
    assert errors == []
    assert (summary["nodes"], summary["frames"], summary["connectors"], summary["labels"]) == (
        2,
        1,
        1,
        1,
    )
    assert summary["checks"] > 10


def test_an_empty_or_foreign_svg_is_refused(checker) -> None:
    errors: list[str] = []
    checker.check_svg('<svg xmlns="http://www.w3.org/2000/svg"><circle r="4"/></svg>', errors)
    assert errors == ["no components found in the SVG; is this an infragram export?"]


# --------------------------------------------------------------- wires
def test_a_diagonal_segment_is_reported(checker) -> None:
    errors: list[str] = []
    checker.check_svg(
        svg(
            node("a", 40, 100, "Web"),
            node("b", 400, 300, "Database"),
            edge("e1", "M248,132 L400,332", 248, 132, 400, 332),
        ),
        errors,
    )
    assert any("diagonal segment" in e for e in errors)


def test_a_wire_through_a_cards_text_is_reported(checker) -> None:
    # e1 leaves a, and on its way to b runs straight through c's title.
    errors: list[str] = []
    checker.check_svg(
        svg(
            node("a", 40, 100, "Web"),
            node("b", 700, 100, "Database"),
            node("c", 380, 100, "Cache"),
            edge("e1", "M248,130 L700,130", 248, 130, 700, 130),
        ),
        errors,
    )
    assert any("runs through the text ('Cache') of 'c'" in e for e in errors)
    assert any("cuts through the card 'c'" in e for e in errors)


def test_a_wire_through_a_frame_title_is_reported(checker) -> None:
    errors: list[str] = []
    checker.check_svg(
        svg(
            node("a", 40, 300, "Web"),
            node("b", 600, 40, "Database"),
            frame("vpc", 300, 60, 400, 400, "Production VPC"),
            # up the left edge of the frame and across its title band
            edge("e1", "M248,332 L320,332 L320,72 L600,72", 248, 332, 600, 72),
        ),
        errors,
    )
    assert any("runs through the title of frame 'vpc'" in e for e in errors)


def test_a_wire_may_pass_through_an_icon_nodes_invisible_box_but_not_its_caption(checker) -> None:
    errors: list[str] = []
    # the wire crosses c's transparent 120x96 box above the glyph area only
    checker.check_svg(
        svg(
            node("a", 40, 100, "Web"),
            node("b", 700, 100, "Database"),
            node("c", 380, 96, "Cache", display="icon"),
            edge("e1", "M248,100 L700,100", 248, 100, 700, 100),
        ),
        errors,
    )
    assert not any("cuts through the card" in e for e in errors)
    errors.clear()
    checker.check_svg(
        svg(
            node("a", 40, 140, "Web"),
            node("b", 700, 140, "Database"),
            node("c", 380, 96, "Cache", display="icon"),
            edge("e1", "M248,166 L700,166", 248, 166, 700, 166),  # y=166 is the caption line
        ),
        errors,
    )
    assert any("runs through the text ('Cache') of 'c'" in e for e in errors)


# --------------------------------------------------------------- captions
def test_overlapping_captions_are_reported(checker) -> None:
    errors: list[str] = []
    checker.check_svg(
        svg(
            node("a", 40, 100, "Web"),
            node("b", 600, 100, "Database"),
            edge("e1", "M248,120 L600,120", 248, 120, 600, 120),
            edge("e2", "M248,140 L600,140", 248, 140, 600, 140),
            label("e1", 300, 128, "SQL"),
            label("e2", 306, 130, "replication"),
        ),
        errors,
    )
    assert any("captions of connectors e1 and e2 overlap" in e for e in errors)


def test_a_caption_covering_a_card_is_reported(checker) -> None:
    errors: list[str] = []
    checker.check_svg(
        svg(
            node("a", 40, 100, "Web"),
            node("b", 600, 100, "Database"),
            edge("e1", "M248,132 L600,132", 248, 132, 600, 132),
            label("e1", 60, 132, "sits on Web"),
        ),
        errors,
    )
    assert any("caption of connector e1 covers 'a'" in e for e in errors)


def test_overlapping_components_and_a_component_outside_the_picture_are_reported(checker) -> None:
    errors: list[str] = []
    checker.check_svg(
        svg(
            node("a", 40, 100, "Web"), node("b", 100, 120, "Database"), node("c", 950, 100, "Edge")
        ),
        errors,
    )
    assert any("components 'a' and 'b' overlap" in e for e in errors)
    assert any("component 'c' lies outside the viewBox" in e for e in errors)


# --------------------------------------------------------------- document
def _document(direction: str = "forward", kind: str = "solid") -> dict:
    return {
        "slug": "two",
        "topology": {
            "id": "root",
            "type": "group",
            "children": [
                {
                    "id": "a",
                    "name": "Web",
                    "type": "service",
                    "connections": [{"target": "b", "direction": direction, "kind": kind}],
                },
                {"id": "b", "name": "Database", "type": "service"},
            ],
        },
    }


def test_arrowheads_and_line_kind_are_checked_against_the_document(checker) -> None:
    picture = svg(
        node("a", 40, 100, "Web"),
        node("b", 400, 100, "Database"),
        edge("e1", "M248,132 L400,132", 248, 132, 400, 132, end=True, start=False),
    )
    errors: list[str] = []
    summary = checker.check_svg(picture, errors, _document())
    assert errors == [] and summary["project"] == "two"

    errors.clear()
    checker.check_svg(picture, errors, _document(direction="both"))
    assert any("arrowheads for 'both' wrong" in e for e in errors)

    errors.clear()
    checker.check_svg(picture, errors, _document(kind="dashed"))
    assert any("drawn solid but the document says 'dashed'" in e for e in errors)

    errors.clear()
    checker.check_svg(
        svg(node("a", 40, 100, "Web"), node("b", 400, 100, "Database")), errors, _document()
    )
    assert any("declares 1 connections but the picture draws 0" in e for e in errors)


def test_a_reversed_wire_is_matched_and_its_arrows_read_the_right_way(checker) -> None:
    # drawn from b to a with the arrow at the start: still a → b forward
    picture = svg(
        node("a", 40, 100, "Web"),
        node("b", 400, 100, "Database"),
        edge("e1", "M400,132 L248,132", 400, 132, 248, 132, end=False, start=True),
    )
    errors: list[str] = []
    checker.check_svg(picture, errors, _document())
    assert errors == []


# ------------------------------------------------------------ components
def test_an_invented_service_is_refused(checker) -> None:
    payload = json.loads((TEMPLATES / "azure-api.infragram.json").read_text(encoding="utf-8"))
    payload["topology"]["children"][0]["component"] = {
        "provider": "azure",
        "service_id": "quantum-database-9000",
        "icon_ref": "azure:quantum-database-9000",
    }
    errors: list[str] = []
    checked = checker.check_components(payload, errors)
    assert checked > 0
    assert any("azure:quantum-database-9000" in e and "invented" in e for e in errors)


@pytest.mark.parametrize("template", sorted(p.name for p in TEMPLATES.glob("*.infragram.json")))
def test_every_shipped_template_names_only_real_components(checker, template: str) -> None:
    payload = json.loads((TEMPLATES / template).read_text(encoding="utf-8"))
    errors: list[str] = []
    checker.check_components(payload, errors)
    assert errors == []


# ---------------------------------------------- the real static render
@pytest.mark.parametrize(
    "template", ["azure-hub-spoke-landing-zone", "azure-aks-baseline", "azure-web-app-front-door"]
)
def test_the_static_render_of_a_template_passes_the_picture_checks(checker, template: str) -> None:
    project = CloudProject.load(TEMPLATES / f"{template}.infragram.json")
    picture = make_standalone_svg(render_project_html(project))
    errors: list[str] = []
    summary = checker.check_svg(picture, errors)
    assert summary["nodes"] > 0 and summary["connectors"] > 0
    assert errors == []


# ------------------------------------------------------------ determinism
def test_the_same_document_renders_the_same_page_and_picture_three_times() -> None:
    project = CloudProject.load(TEMPLATES / "azure-web-app-front-door.infragram.json")
    pages = {render_project_html(project) for _ in range(3)}
    assert len(pages) == 1, "the page changed between renders of one document"
    pictures = {make_standalone_svg(next(iter(pages))) for _ in range(3)}
    assert len(pictures) == 1


def test_the_checker_runs_from_the_command_line_on_a_picture(checker, tmp_path: Path) -> None:
    project = CloudProject.load(TEMPLATES / "azure-api.infragram.json")
    picture = tmp_path / "azure-api.svg"
    picture.write_text(make_standalone_svg(render_project_html(project)), encoding="utf-8")
    ok, message = checker.check_path(picture)
    assert ok, message
    assert re.match(r"OK .*: picture - \d+ components, \d+ frames, \d+ connectors", message)
