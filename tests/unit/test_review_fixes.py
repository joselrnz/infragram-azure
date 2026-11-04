"""Six defects from the 2026-09-09 full-tree review, each pinned by the case that showed it."""

from __future__ import annotations

import importlib
import xml.etree.ElementTree as ET

import pytest

from infragram import compose, exports
from infragram.author import Diagram
from infragram.builders import metrics
from infragram.catalog.categories import UnknownCategoryError, _key
from infragram.exports import ExportError, finish_standalone_svg, render_project_svg
from infragram.nodes import reset_ids
from infragram.nodes.azure import compute
from infragram.nodes.frames import azure as az


def test_the_svg_finisher_finds_its_tags_on_the_text_itself() -> None:
    # A dotted capital I lower-cases to two code points, so a position found
    # in the lower-cased text sliced the original one character off.
    # Draw the extended-Latin text too, so the slim finisher has a reason
    # to insert a font definition after the mixed-case title.
    svg = (
        '<svg viewBox="0 0 10 10"><TITLE>İstanbul İzmir İstanbul</TITLE>'
        '<text font-family="Inter">İstanbul İzmir İstanbul</text>'
        '<rect width="1" height="1"/></svg>'
    )
    finished = finish_standalone_svg(svg, background="#ffffff")
    ET.fromstring(finished)  # well-formed
    assert "</TITLE>\n        <defs>" in finished
    assert finished.index("data-export-background") > finished.index("</defs>")
    assert "İstanbul İzmir İstanbul" in finished


def test_a_bare_badge_slug_resolves_in_the_diagrams_own_library() -> None:
    reset_ids()
    with Diagram("Badged", providers=("azure",)) as diagram:
        with az.VNet("vnet"):
            with az.Subnet("snet") as subnet:
                compute.VirtualMachine("VM")
                subnet.badge("network-security-groups")
    scene = exports.render._scene_for(diagram.to_project())
    badged = [cluster for cluster in scene.root.clusters() if cluster.badges]
    assert len(badged) == 1 and badged[0].label == "snet"


def test_the_svg_export_refuses_a_picture_that_outgrew_its_preset() -> None:
    reset_ids()
    elements = [compute.VirtualMachine(f"VM {n}") for n in range(12)]
    project = compose.to_project(
        elements, slug="wide", title="Wide", description="x.", size="doc-inline"
    )
    with pytest.raises(ExportError, match="exceeds doc-inline"):
        render_project_svg(project)


def test_the_static_straighten_is_the_shared_metric() -> None:
    render_module = importlib.import_module("infragram.builders.render")
    assert metrics.router()["straighten"] == render_module.STRAIGHTEN


def test_an_empty_category_key_is_the_error_the_callers_catch() -> None:
    with pytest.raises(UnknownCategoryError):
        _key("")
    assert issubclass(UnknownCategoryError, ValueError)


def test_a_node_built_before_the_block_keeps_its_id_beside_a_namesake_inside() -> None:
    reset_ids()
    outside = compute.VirtualMachine("Web")
    with Diagram("Two webs", providers=("azure",)) as diagram:
        inside = compute.VirtualMachine("Web")
        diagram.add(outside)
    assert outside.id == "web" and inside.id == "web-2"
    ids = [element.id for element in diagram.to_project().topology.walk()]
    assert len(ids) == len(set(ids))


def test_a_closed_diagram_frees_its_ids_for_the_next() -> None:
    reset_ids()
    with Diagram("First", providers=("azure",)) as first:
        compute.VirtualMachine("Web")
    with Diagram("Second", providers=("azure",)) as second:
        compute.VirtualMachine("Web")
    assert first.roots[0].id == "web" and second.roots[0].id == "web"
