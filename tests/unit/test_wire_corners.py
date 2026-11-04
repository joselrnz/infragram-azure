"""A wire's bend and head are choices, drawn the same by both renderers.

``sharp``, a hard square elbow, is the house default, ``rounded`` an 8 px
bend, ``curved`` the widest bend the legs allow; the table is data in
``render-metrics.json``. The static
renderer used to draw every head as the default triangle while the editor
honoured the per-wire choice; both now read the wire's editor style.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from infragram.author import Diagram, Edge
from infragram.builders import metrics
from infragram.builders.architecture import from_topology, load_style, load_theme
from infragram.editor.state import _editor_state
from infragram.exports import render_project_svg
from infragram.nodes import Group, _scope, reset_ids
from infragram.nodes.azure import compute, databases

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
_LINK = re.compile(
    r'<path d="([^"]+)" fill="none" stroke="[^"]+" stroke-width="[\d.]+"[^>]*marker-end="url\(#([^)]+)\)"'
)


@pytest.fixture(autouse=True)
def _clean():
    _scope.reset()
    reset_ids()
    yield
    _scope.reset()


def _bent_wire(**edge) -> tuple:
    """A wire that has to turn: from a node above to the last node of a wide row beneath.

    Four spacers keep the target well to the right of the source, so the
    wire's legs are long enough to take any bend radius the style asks for
    (a leg shorter than twice the radius shrinks the bend, in both renderers)."""
    with Diagram("Bend", providers=("azure",)) as diagram:
        with Group("Zone", "group").column():
            with Group("Top", "group").row():
                a = compute.VirtualMachine("A", "source")
            with Group("Bottom", "group").row().keep_order():
                for n in range(4):
                    compute.VirtualMachine(f"B{n}", "spacer")
                c = databases.SQLDatabase("C", "target")
        a >> Edge("wire", **edge) >> c
    return diagram, a, c


def _widest_bend(d: str) -> float:
    """The largest bend radius in a path: the run from the point before a Q to its control point."""
    best, last = 0.0, None
    for token in re.findall(r"[MLQHV][^MLQHV]*", d):
        values = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", token[1:])]
        if token[0] == "Q" and last is not None and len(values) >= 4:
            best = max(best, abs(values[0] - last[0]) + abs(values[1] - last[1]))
            last = (values[2], values[3])
        elif token[0] == "H" and last is not None and values:
            last = (values[0], last[1])
        elif token[0] == "V" and last is not None and values:
            last = (last[0], values[0])
        elif values:
            last = (values[-2], values[-1])
    return best


def test_the_bend_table_is_data_and_sharp_is_the_house_default() -> None:
    router = metrics.load().router
    assert router.corners.default == "sharp"
    assert metrics.corner_radius(None) == metrics.corner_radius("sharp") == 0
    assert router.corners.rounded == router.radius
    assert metrics.corner_radius("curved") > metrics.corner_radius("rounded")
    assert metrics.corner_styles() == ("rounded", "sharp", "curved")


@pytest.mark.parametrize("style", ["rounded", "sharp", "curved"])
def test_the_static_picture_bends_the_wire_by_its_style(style: str) -> None:
    diagram, _a, _c = _bent_wire(corners=style)
    svg = render_project_svg(diagram.to_project())
    match = _LINK.search(svg)
    assert match, "no wire in the static picture"
    d = match.group(1)
    if style == "sharp":
        assert "Q" not in d, d
    else:
        assert "Q" in d, d
        bend = _widest_bend(d)
        if style == "rounded":
            assert bend == metrics.corner_radius("rounded"), d
        else:
            assert bend > metrics.corner_radius("rounded"), d


def test_a_wire_with_no_style_is_a_square_elbow() -> None:
    diagram, _a, _c = _bent_wire()
    match = _LINK.search(render_project_svg(diagram.to_project()))
    assert match and "Q" not in match.group(1), match and match.group(1)


def test_the_editor_state_carries_the_bend_and_the_head() -> None:
    diagram, _a, _c = _bent_wire(corners="curved", arrow="diamond")
    project = diagram.to_project()
    scene = from_topology(
        project.topology,
        load_theme("azure"),
        slug=project.slug,
        title=project.title,
        desc=project.description,
        style=load_style("azure"),
    )
    (edge,) = _editor_state(project, scene, {"providers": []})["edges"]
    assert edge["style"]["corners"] == "curved" and edge["style"]["arrow"] == "diamond"


def test_the_diagram_default_bends_every_plain_wire() -> None:
    with Diagram("Default bend", providers=("azure",), corners="sharp") as diagram:
        with Group("Zone", "group"):
            a = compute.VirtualMachine("A")
            b = compute.VirtualMachine("B")
            c = compute.VirtualMachine("C")
        a >> b
        a >> Edge("own", corners="curved") >> c
    styles = a.attributes["editor_edge_styles"]
    project = diagram.to_project()
    assert (
        project.topology.first(id="a").attributes["editor_edge_styles"]["b"]["corners"] == "sharp"
    )
    assert styles["c"]["corners"] == "curved", "a wire's own choice wins over the diagram's"


def test_the_static_renderer_draws_the_chosen_head_and_the_checker_reads_it() -> None:
    diagram, _a, _c = _bent_wire(arrow="diamond")
    project = diagram.to_project()
    svg = render_project_svg(project)
    match = _LINK.search(svg)
    assert match and match.group(2).endswith("-diamond"), match and match.group(2)
    assert f'<marker id="{match.group(2)}"' in svg
    spec = importlib.util.spec_from_file_location(
        "project_check", ROOT / "skills" / "infragram-azure" / "scripts" / "project_check.py"
    )
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    errors: list[str] = []
    checker.check_svg(svg, errors, project.model_dump(mode="json"))
    assert not errors, errors


def test_unknown_styles_are_refused_at_the_call_site() -> None:
    with pytest.raises(ValueError, match="corner style"):
        Edge("x", corners="wavy")
    with pytest.raises(ValueError, match="arrowhead"):
        Edge("x", arrow="harpoon")
    with pytest.raises(ValueError, match="corner style"):
        Diagram("x", corners="loopy")
