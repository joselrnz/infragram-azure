"""Five more review defects, each pinned by the case that showed it."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from infragram import exports
from infragram.author import Diagram, Edge
from infragram.builders import metrics
from infragram.builders.scene import GLYPH_TOP, NodeStyle
from infragram.editor.bundle import runtime_script
from infragram.exports import render_project_svg
from infragram.nodes import reset_ids
from infragram.nodes.azure import compute
from infragram.nodes.frames import azure as az

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


def _checker():
    spec = importlib.util.spec_from_file_location(
        "project_check", ROOT / "skills/infragram-azure/scripts/project_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_an_unknown_connection_kind_is_refused_by_name_everywhere() -> None:
    reset_ids()
    with Diagram("Kinds", providers=("azure",)) as diagram:
        web = compute.VirtualMachine("Web")
        db = compute.VirtualMachine("DB")
        web.to(db, kind="teleport")
    project = diagram.to_project()
    with pytest.raises(ValueError, match="unknown kind 'teleport'.*solid"):
        render_project_svg(project)
    errors: list[str] = []
    _checker().check_project(json.loads(project.model_dump_json(exclude_none=True)), errors)
    assert any("kind 'teleport' is not in the link table" in error for error in errors)
    # a kind the library knows passes both
    reset_ids()
    with Diagram("Kinds", providers=("azure",)) as diagram:
        web = compute.VirtualMachine("Web")
        db = compute.VirtualMachine("DB")
        web >> Edge("x", dashed=True) >> db
    project = diagram.to_project()
    render_project_svg(project)
    errors = []
    _checker().check_project(json.loads(project.model_dump_json(exclude_none=True)), errors)
    assert not [error for error in errors if "kind" in error]


def test_a_node_hoisted_after_its_frame_closed_has_one_parent() -> None:
    reset_ids()
    with Diagram("Hoist", providers=("azure",)) as diagram:
        with az.VNet("vnet"):
            with az.Subnet("first"):
                vm = compute.VirtualMachine("Host")
            second = az.Subnet("second")
        second.add(vm)
    parents = [
        element
        for element in diagram.topology().walk()
        if any(child is vm for child in element.children)
    ]
    assert [parent.name for parent in parents] == ["second"]
    ids = [element.id for element in diagram.to_project().topology.walk()]
    assert len(ids) == len(set(ids))


def test_cards_are_the_same_height_in_both_renderers() -> None:
    assert NodeStyle().height == metrics.card()["height"] == 64
    source = runtime_script()
    assert "ICON_NODE.height : CARD_HEIGHT" in source and "ICON_NODE.height : 72" not in source


def test_the_static_picture_draws_a_wires_own_colour_and_width() -> None:
    reset_ids()
    with Diagram("Styled", providers=("azure",)) as diagram:
        web = compute.VirtualMachine("Web")
        db = compute.VirtualMachine("DB")
        web >> db
    web.attributes["editor_edge_styles"] = {db.id: {"stroke": "#ff0000", "width": 3}}
    svg = render_project_svg(diagram.to_project())
    assert 'stroke="#ff0000" stroke-width="3"' in svg


def test_a_wire_to_an_empty_frame_or_to_its_own_first_node_is_refused() -> None:
    reset_ids()
    with Diagram("Empty", providers=("azure",)) as diagram:
        web = compute.VirtualMachine("Web")
        empty = az.Subnet("empty")
        web.to(empty)
    with pytest.raises(ValueError, match="nothing drawn"):
        exports.render._scene_for(diagram.to_project())
    reset_ids()
    with Diagram("Self", providers=("azure",)) as diagram:
        with az.Subnet("snet") as subnet:
            host = compute.VirtualMachine("Host")
        subnet.to(host)
    with pytest.raises(ValueError, match="same"):
        exports.render._scene_for(diagram.to_project())


def test_the_glyph_top_is_one_number_read_by_both_renderers() -> None:
    assert metrics.icon_node()["glyph_top"] == GLYPH_TOP
    source = runtime_script()
    assert source.count("captioned ? ICON_NODE.glyphTop") == 2 and "captioned ? 6" not in source
