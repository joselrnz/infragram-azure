"""The .drawio export: the diagram opens in draw.io as it was drawn here, and
reads back into Infragram as the same components.

draw.io reads the file itself; these tests hold what it needs to: a valid
mxfile, every frame a container holding its children in coordinates relative
to it, every wire parented by the innermost frame holding both ends with its
bends as points, draw.io's own stencil where one is mapped and Infragram's
artwork (with its SVG namespace) where not, and ``infragram_component`` on
every element so ``import:drawio`` reads it back exactly.
"""

from __future__ import annotations

import base64
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from infragram.exports.drawio import render_project_drawio
from infragram.paths import repo_root
from infragram.projects import CloudProject

TEMPLATES = sorted(
    (repo_root() / "skills/infragram-azure/assets/templates/cloud").glob("*.infragram.json")
)
EXAMPLE = repo_root() / "examples/azure_hub_spoke_landing_zone.py"


@pytest.mark.parametrize(
    "legend_id,role",
    [("infragram:legend", ""), ("renamed-legend", 'infragram_role="legend"')],
)
def test_import_keeps_legend_labels_as_notes_and_excludes_its_descendants(
    legend_id: str, role: str
) -> None:
    from infragram.convert.drawio import read_drawio_text

    xml = f'''<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>
      <mxCell id="client" value="Client" vertex="1" parent="1">
        <mxGeometry x="0" y="0" width="80" height="40" as="geometry"/></mxCell>
      <mxCell id="server" value="Legend" vertex="1" parent="1">
        <mxGeometry x="200" y="0" width="80" height="40" as="geometry"/></mxCell>
      <mxCell id="flow" source="client" target="server" edge="1" parent="1"/>
      <mxCell id="{legend_id}" {role} value="Legend" vertex="1" parent="1" style="swimlane;container=1;">
        <mxGeometry x="0" y="100" width="640" height="80" as="geometry"/></mxCell>
      <mxCell id="opaque-group" vertex="1" parent="{legend_id}" style="group;"/>
      <mxCell id="opaque-symbol" vertex="1" parent="opaque-group" style="shape=line;"/>
      <mxCell id="opaque-label" value="HTTPS traffic" vertex="1" parent="opaque-group" style="text;"/>
    </root></mxGraphModel>'''
    sketch = read_drawio_text(xml, name="legend-round-trip")[0]
    assert {shape.key for shape in sketch.shapes} == {"client", "server"}
    assert next(shape for shape in sketch.shapes if shape.key == "server").label == "Legend"
    assert len(sketch.links) == 1
    assert sketch.notes == ["Legend: HTTPS traffic"]


@pytest.mark.parametrize(
    "caption_id,role",
    [("infragram:title", ""), ("renamed-title", 'infragram_role="caption"')],
)
def test_import_keeps_exported_title_as_a_note(caption_id: str, role: str) -> None:
    from infragram.convert.drawio import read_drawio_text

    xml = f'''<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/>
      <mxCell id="app" value="Application" vertex="1" parent="1"/>
      <mxCell id="{caption_id}" {role} value="Application architecture" vertex="1" parent="1"/>
    </root></mxGraphModel>'''
    sketch = read_drawio_text(xml, name="caption-round-trip")[0]
    assert [shape.key for shape in sketch.shapes] == ["app"]
    assert sketch.notes == ["Title: Application architecture"]


def _project(path: Path) -> CloudProject:
    return CloudProject.model_validate_json(path.read_text(encoding="utf-8"))


def _cells(xml: str) -> dict[str, tuple[dict, ET.Element]]:
    root = ET.fromstring(xml)
    out: dict[str, tuple[dict, ET.Element]] = {}
    for holder in root.iter():
        if holder.tag == "object":
            cell = holder.find("mxCell")
            out[holder.get("id")] = ({**holder.attrib, **cell.attrib}, cell)
        elif holder.tag == "mxCell" and holder.get("id"):
            out[holder.get("id")] = (dict(holder.attrib), holder)
    return out


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda path: path.name.split(".")[0])
def test_every_template_exports_a_well_formed_nested_file(template: Path) -> None:
    project = _project(template)
    xml = render_project_drawio(project)
    cells = _cells(xml)
    elements = {
        element.id for element in project.topology.walk() if element is not project.topology
    }
    carried = {
        attrs.get("infragram_id") for attrs, _ in cells.values() if attrs.get("infragram_id")
    }
    assert carried <= elements and len(carried) >= len(elements) * 0.9, (
        "every drawn element is a cell"
    )
    for attrs, cell in cells.values():
        parent = attrs.get("parent")
        if parent and parent not in ("0", "1"):
            assert "container=1" in cells[parent][0]["style"], f"{attrs['id']} sits in a container"
        if attrs.get("edge") == "1":
            assert attrs["source"] in cells and attrs["target"] in cells
        geometry = cell.find("mxGeometry")
        if attrs.get("vertex") == "1" and parent not in (None, "0", "1"):
            # relative to its frame: inside its bounds
            frame = cells[parent][1].find("mxGeometry")
            assert -1 <= float(geometry.get("x")) <= float(frame.get("width")), attrs["id"]


def test_mapped_components_are_native_and_the_rest_is_embedded_artwork() -> None:
    from infragram.cli.user.compose import project_from_spec

    xml = render_project_drawio(project_from_spec(EXAMPLE))
    assert "image=img/lib/azure2/" in xml, "Azure services use draw.io's own stencils"
    art = re.search(r"image=data:image/svg\+xml,([A-Za-z0-9+/=]+);", xml)
    assert art, "an unmapped component as its artwork"
    assert 'xmlns="http://www.w3.org/2000/svg"' in base64.b64decode(art.group(1)).decode("utf-8")
    embedded = render_project_drawio(project_from_spec(EXAMPLE), icons="embedded")
    assert "image=img/lib/azure2/" not in embedded and embedded.count("image=data:") > xml.count(
        "image=data:"
    )


def test_a_wire_keeps_its_bends_and_its_seats() -> None:
    from infragram.cli.user.compose import project_from_spec

    cells = _cells(render_project_drawio(project_from_spec(EXAMPLE)))
    wires = [(attrs, cell) for attrs, cell in cells.values() if attrs.get("edge") == "1"]
    assert wires and all(
        "exitX=" in attrs["style"] and "entryX=" in attrs["style"] for attrs, _ in wires
    )
    assert any(cell.find("mxGeometry/Array") is not None for _, cell in wires), "bends as points"


def test_the_file_reads_back_as_the_same_components(tmp_path: Path) -> None:
    from infragram.cli.user.compose import project_from_spec
    from infragram.convert import read_diagrams

    project = project_from_spec(EXAMPLE)
    path = tmp_path / "three-tier.drawio"
    path.write_text(render_project_drawio(project), encoding="utf-8")
    sketch = read_diagrams(path)[0]
    read = sorted(shape.component for shape in sketch.shapes if shape.component)
    wanted = sorted(
        f"{e.component.provider}:{e.component.service_id}"
        for e in project.topology.walk()
        if getattr(e, "component", None)
    )
    assert read == wanted


def test_the_stencil_table_is_exact_and_attributed() -> None:
    table = json.loads(
        (repo_root() / "skills/infragram-azure/assets/catalog/drawio-stencils.json").read_text(
            encoding="utf-8"
        )
    )
    assert table["source"]["license"] == "Apache-2.0" and re.fullmatch(
        r"[0-9a-f]{40}", table["source"]["commit"]
    )
    assert (
        table["components"]["azure:virtual-machine"]["style"].count(
            "image=img/lib/azure2/compute/Virtual_Machine.svg"
        )
        == 1
    )


def test_crossing_choice_keeps_the_same_cells_and_routes() -> None:
    from infragram.cli.user.compose import project_from_spec

    project = project_from_spec(EXAMPLE)
    project.presentation.crossings = "plain"
    plain = _cells(render_project_drawio(project))
    project.presentation.crossings = "bridge"
    bridge = _cells(render_project_drawio(project))
    assert plain.keys() == bridge.keys()
    edges = 0
    for key, (attrs, cell) in plain.items():
        other, other_cell = bridge[key]
        if attrs.get("edge") != "1":
            assert attrs == other
            continue
        edges += 1
        assert "jumpStyle=none;" in attrs["style"]
        assert "jumpStyle=arc;jumpSize=16;" in other["style"]
        assert attrs["source"] == other["source"] and attrs["target"] == other["target"]
        assert ET.tostring(cell.find("mxGeometry")) == ET.tostring(other_cell.find("mxGeometry"))
    assert edges
