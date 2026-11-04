"""Compact cloud pages and an optional offline 3D builder from the same Azure edition."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from infragram.editor.shell import (
    LIBRARY_ENCODING,
    library_catalog_from_html,
    page_carries_3d_renderer,
)
from infragram.exports import render_project_html
from infragram.projects import CloudProject

TEMPLATES = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "infragram-azure"
    / "assets"
    / "templates"
    / "cloud"
)


def _template(name: str) -> CloudProject:
    return CloudProject.load(TEMPLATES / f"{name}.infragram.json")


def test_the_library_payload_travels_deflated_and_reads_back() -> None:
    html = render_project_html(_template("azure-api"))
    assert f'id="infragram-library-catalog" data-encoding="{LIBRARY_ENCODING}"' in html
    library = library_catalog_from_html(html)
    assert library["selectedProviders"] == ["azure"]
    assert any(component["provider"] == "azure" for component in library["components"])
    assert "DecompressionStream" in html, "the page inflates it itself"


def test_a_cloud_page_leaves_the_optional_3d_renderer_out() -> None:
    project = _template("azure-api")
    assert page_carries_3d_renderer(project, "project") is False
    html = render_project_html(project)
    assert "/* no 3D renderer" in html and "THREE" not in html
    assert "data-iso-unavailable" in html


def test_all_libraries_embeds_the_3d_builder_and_renderer_offline() -> None:
    project = _template("azure-api")
    assert page_carries_3d_renderer(project, "all") is True
    html = render_project_html(project, libraries="all")
    assert "THREE" in html and "data-infragram-iso3d" in html
    assert "data-iso-builder" in html and 'id="infragram-iso3d-vocabulary"' in html
    assert tuple(provider["id"] for provider in library_catalog_from_html(html)["providers"]) == (
        "azure",
        "kubernetes",
        "databricks",
    )

    class Scripts(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "script":
                assert "src" not in dict(attrs), "the builder must carry its runtime offline"

    Scripts().feed(html)
    assert len(html.encode("utf-8")) < 4_650_000


def test_exported_pages_stay_small() -> None:
    """Catch an uncompressed catalog or a needless 1.6 MB renderer, while
    allowing the shared editor's costs, views, policy and export controls,
    and the right-click menu's icons, view entries and More actions (about
    17 KB)."""
    sizes = {
        name: len(render_project_html(_template(name)).encode("utf-8"))
        for name in ("azure-api", "azure-web-app-front-door")
    }
    assert sizes["azure-api"] < 2_670_000, sizes
    assert sizes["azure-web-app-front-door"] < 3_000_000, sizes
