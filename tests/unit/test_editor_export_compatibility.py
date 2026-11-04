"""Public Azure helpers and saved badge documents survive the editor port."""

from __future__ import annotations

from xml.etree import ElementTree

import pytest
from pydantic import ValidationError

from infragram.builders.ink import luminance
from infragram.exports import export_project, make_standalone_svg
from infragram.models.topology import Badge, TopologyElement
from infragram.projects import CloudProject
from infragram.projects.schema import project_schema, schema_path, schema_text


def test_the_azure_svg_helper_still_extracts_the_diagram() -> None:
    html = '<html><body><svg viewBox="0 0 1 1"></svg><svg data-infragram-diagram="true" viewBox="0 0 80 40"><text x="1" y="12">Azure</text></svg></body></html>'
    picture = ElementTree.fromstring(make_standalone_svg(html))
    assert picture.attrib["viewBox"] == "0 0 80 40"
    assert "Azure" in "".join(picture.itertext())


def test_the_old_luminance_import_keeps_wcag_values() -> None:
    assert luminance("#000") == 0
    assert luminance("#fff") == pytest.approx(1)
    assert luminance("#808080") == pytest.approx(0.2158605001)
    with pytest.raises(ValueError, match="hex colour"):
        luminance("red")


def test_azure_badge_sides_and_offsets_round_trip() -> None:
    frame = TopologyElement(
        id="subnet",
        name="snet-web",
        type="subnet-public",
        badges=[
            Badge(icon="network-security-groups", side="corner", label="nsg-web"),
            Badge(icon="nat", side="edge", label="nat-web"),
            Badge(icon="route-tables", side="top", offset=0.75),
        ],
    )
    restored = TopologyElement.model_validate_json(frame.model_dump_json())
    assert [(badge.side, badge.offset) for badge in restored.badges] == [
        ("corner", 0.5),
        ("edge", 0.5),
        ("top", 0.75),
    ]
    with pytest.raises(ValidationError):
        Badge(icon="nat", side="unknown")


def test_the_shipped_azure_schema_matches_the_extended_model() -> None:
    assert project_schema()["title"] == "Infragram Azure project"
    assert schema_path().read_text(encoding="utf-8") == schema_text()
    badge_schema = project_schema()["$defs"]["Badge"]["properties"]
    assert {"corner", "edge", "top"} <= set(badge_schema["side"]["enum"])
    assert "offset" in badge_schema


def test_a_read_only_cache_does_not_turn_a_written_export_into_failure(
    tmp_path, monkeypatch
) -> None:
    from infragram.iso3d import cache

    def denied():
        raise PermissionError("the cache cannot be accessed")

    template = schema_path().parent.parent / "templates/cloud/azure-api.infragram.json"
    project = CloudProject.load(template)
    monkeypatch.setattr(cache, "cache_root", denied)
    result = export_project(project, tmp_path, formats=("template",))
    assert result.template is not None and result.template.is_file()
    restored = CloudProject.load(result.template)
    assert restored.title == project.title
    assert restored.model_dump() == project.model_dump()
