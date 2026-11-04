"""A bad setting fails at the line that wrote it, naming what was wrong.

``Diagram`` validates on assignment and ``Edge`` is frozen, so an author's
file stops at its own mistake instead of somewhere inside an export. The
catalog records load through models for the same reason: a malformed
``providers.json`` or ``categories.json`` fails with the field named.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from infragram.author import Diagram, Edge
from infragram.catalog.categories import CategoryRegistry
from infragram.catalog.providers import ProviderRegistry
from infragram.paths import skill_assets


def test_a_bad_corner_style_fails_where_it_is_set() -> None:
    with pytest.raises(ValueError, match="unknown corner style"):
        Diagram("Bends", corners="zigzag")
    diagram = Diagram("Bends")
    with pytest.raises(ValueError, match="unknown corner style"):
        diagram.corners = "zigzag"
    with pytest.raises(ValidationError, match="direction"):
        diagram.direction = "sideways"  # type: ignore[assignment]
    assert (diagram.corners, diagram.direction) == (None, None)


def test_an_edge_checks_its_head_and_then_never_changes() -> None:
    with pytest.raises(ValueError, match="unknown arrowhead"):
        Edge(arrow="harpoon")
    edge = Edge("HTTPS", dashed=True)
    assert (edge.label, edge.kind, edge.direction) == ("HTTPS", "dashed", "forward")
    with pytest.raises(ValidationError, match="frozen"):
        edge.label = "other"


def _copy_of(name: str, tmp_path: Path, mutate) -> Path:
    record = json.loads((skill_assets() / "catalog" / name).read_text(encoding="utf-8"))
    mutate(record)
    path = tmp_path / name
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_a_provider_record_with_an_insecure_url_names_the_field(tmp_path: Path) -> None:
    def downgrade(record: dict) -> None:
        record["providers"][0]["source_url"] = "http://insecure.example/icons"

    with pytest.raises(ValidationError, match="source_url"):
        ProviderRegistry.load(_copy_of("providers.json", tmp_path, downgrade))


def test_a_category_with_a_zero_order_names_the_field(tmp_path: Path) -> None:
    def zero(record: dict) -> None:
        record["categories"][0]["order"] = 0

    with pytest.raises(ValidationError, match="order"):
        CategoryRegistry.load(_copy_of("categories.json", tmp_path, zero))


def test_a_category_file_with_a_stray_key_is_refused(tmp_path: Path) -> None:
    def stray(record: dict) -> None:
        record["categories"][0]["colour"] = "red"

    with pytest.raises(ValidationError, match="colour"):
        CategoryRegistry.load(_copy_of("categories.json", tmp_path, stray))
