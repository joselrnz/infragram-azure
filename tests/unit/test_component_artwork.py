"""A card that names its service only through its component draws that component's artwork.

Twenty-four shipped templates are written that way -- the document form --
and the static picture drew every one of their cards without an icon while
the editor page drew them from its payload. Both now resolve the same way.
"""

from __future__ import annotations

import json
from pathlib import Path

from infragram.builders.architecture import icon_for
from infragram.exports import render_project_svg
from infragram.exports.render import _scene_for
from infragram.models.topology import ComponentRef, TopologyElement
from infragram.projects import CloudProject

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
TEMPLATES = ROOT / "skills" / "infragram-azure" / "assets" / "templates" / "cloud"


def _element(provider: str, service_id: str, **attributes) -> TopologyElement:
    return TopologyElement(
        id="x",
        name="X",
        type="service",
        attributes=attributes,
        component=ComponentRef(
            provider=provider, service_id=service_id, icon_ref=f"{provider}:{service_id}"
        ),
    )


def test_a_vendor_component_resolves_from_its_pack() -> None:
    icon = icon_for(_element("azure", "load-balancers"))
    assert icon is not None and icon.slug == "load-balancers"


def test_a_shared_primitive_component_resolves_from_the_gallery() -> None:
    icon = icon_for(_element("infragram", "public-users"))
    assert icon is not None and icon.markup and icon.slug == "infragram-public-users"


def test_a_component_the_pack_lacks_resolves_from_the_sidebar_catalog() -> None:
    # the platform card: the Kubernetes mark stands for the cluster itself
    # and is not an entry in the vendor icon pack
    icon = icon_for(_element("kubernetes", "kubernetes"))
    assert icon is not None and icon.markup and icon.markup.lstrip().startswith("<svg")


def test_an_explicit_icon_the_pack_cannot_find_still_falls_back_to_the_component() -> None:
    icon = icon_for(
        _element("kubernetes", "kubernetes", icon="kubernetes", collection="kubernetes")
    )
    assert icon is not None and icon.markup and icon.markup.lstrip().startswith("<svg")


def test_a_frame_keeps_its_own_rule() -> None:
    frame = TopologyElement(
        id="f",
        name="F",
        type="network",
        children=[],
        component=ComponentRef(provider="infragram", service_id="custom-boundary-azure-vnet"),
    )
    assert icon_for(frame, None, explicit_only=True) is None


def test_every_shipped_template_draws_an_icon_on_every_card() -> None:
    # Five templates once carried a bare "Client" element with no component:
    # a card with text only, and in the icon look a label with no glyph.
    bare: list[str] = []
    for path in sorted(TEMPLATES.glob("*.infragram.json")):
        project = CloudProject.model_validate(json.loads(path.read_text(encoding="utf-8")))
        scene = _scene_for(project)
        bare += [f"{project.slug}: {node.name}" for node in scene.root.walk() if node.icon is None]
    assert bare == []


def test_the_front_door_template_draws_an_icon_on_every_card() -> None:
    project = CloudProject.model_validate(
        json.loads(
            (TEMPLATES / "azure-web-app-front-door.infragram.json").read_text(encoding="utf-8")
        )
    )
    scene = _scene_for(project)
    assert all(node.icon is not None for node in scene.root.walk())
    svg = render_project_svg(project)
    assert svg.count('<use href="#icon-') >= 6
