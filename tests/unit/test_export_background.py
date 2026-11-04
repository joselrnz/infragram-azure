"""An export carries its own ground.

Exports used to be transparent, deliberately: a picture with no background
drops onto any page and takes its colour. For a light-only product that was
the wrong default. A transparent PNG in a dark viewer, a dark chat client or
a terminal shows dark text on black, which is what people actually saw, and
the diagram they opened looked broken rather than adaptable.

The default is now the theme's own paper -- white -- painted over the whole
viewBox including the margin. ``background="transparent"`` still asks for the
old behaviour, and a hex colour asks for anything else.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from infragram.exports import (
    DEFAULT_EXPORT_BACKGROUND,
    ExportError,
    export_project,
    finish_standalone_svg,
    resolve_background,
)
from infragram.projects import CloudProject

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
TEMPLATE = (
    ROOT
    / "skills/infragram-azure/assets/templates/cloud/azure-hub-spoke-landing-zone.infragram.json"
)
GROUND = re.compile(r'<rect data-export-background="[^"]*"([^>]*)>')


def test_the_default_is_the_theme_paper_not_transparency() -> None:
    assert DEFAULT_EXPORT_BACKGROUND == "paper"
    assert resolve_background(DEFAULT_EXPORT_BACKGROUND, "#ffffff") == "#ffffff"


@pytest.mark.parametrize("asked", ["transparent", "none", ""])
def test_transparency_is_still_available(asked: str) -> None:
    assert resolve_background(asked, "#ffffff") is None


@pytest.mark.parametrize("colour", ["#fff", "#f5f5f5", "#0F1B2A"])
def test_a_hex_colour_passes_through(colour: str) -> None:
    assert resolve_background(colour, "#ffffff") == colour


def test_a_colour_name_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ExportError, match="unknown export background"):
        resolve_background("chartreuse", "#ffffff")


def test_the_ground_covers_the_whole_view_box() -> None:
    """Including the margin, so no corner of the file is clear."""
    svg = (
        '<svg viewBox="-8 48 1280 2128" xmlns="http://www.w3.org/2000/svg">'
        "<title>t</title><desc>d</desc><g/></svg>"
    )
    finished = finish_standalone_svg(svg, "#ffffff")
    match = GROUND.search(finished)
    assert match is not None, "no ground was painted"
    for attribute in ('x="-8"', 'y="48"', 'width="1280"', 'height="2128"', 'fill="#ffffff"'):
        assert attribute in match.group(1), attribute


def test_the_ground_sits_behind_the_drawing() -> None:
    """After the title and defs, before anything drawn, or it hides the picture."""
    svg = (
        '<svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg">'
        '<title>t</title><desc>d</desc><defs><marker id="m"/></defs>'
        '<rect data-boundary-surface="" x="1" y="1" width="2" height="2"/></svg>'
    )
    finished = finish_standalone_svg(svg, "#ffffff")
    assert finished.index("data-export-background") > finished.index("</defs>")
    assert finished.index("data-export-background") < finished.index("data-boundary-surface")


def test_asking_for_nothing_paints_nothing() -> None:
    svg = '<svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg"><g/></svg>'
    assert "data-export-background" not in finish_standalone_svg(svg, None)


@pytest.mark.parametrize(
    "background,expected",
    [
        ("paper", "#ffffff"),
        ("#f5f5f5", "#f5f5f5"),
    ],
)
def test_a_real_export_carries_the_ground(tmp_path: Path, background: str, expected: str) -> None:
    """End to end, through the fallback that runs without a browser."""

    def no_browser(source, output, theme=None, display=None, background=None):
        raise ExportError("no browser (simulated)")

    project = CloudProject.load(TEMPLATE)
    export_project(
        project,
        tmp_path,
        formats=("svg",),
        svg_renderer=no_browser,
        overwrite=True,
        background=background,
    )
    svg = (tmp_path / f"{project.slug}.svg").read_text(encoding="utf-8")
    match = GROUND.search(svg)
    assert match is not None, "the fallback render lost the ground"
    assert f'fill="{expected}"' in match.group(1)


def test_a_transparent_export_is_still_clear(tmp_path: Path) -> None:
    def no_browser(source, output, theme=None, display=None, background=None):
        raise ExportError("no browser (simulated)")

    project = CloudProject.load(TEMPLATE)
    export_project(
        project,
        tmp_path,
        formats=("svg",),
        svg_renderer=no_browser,
        overwrite=True,
        background="transparent",
    )
    assert "data-export-background" not in (tmp_path / f"{project.slug}.svg").read_text(
        encoding="utf-8"
    )


def test_the_ground_sits_behind_the_drawing_not_inside_a_card() -> None:
    """A card carries a <title>; the ground must not be filed under it.

    Taking the last </title> in the document put the ground rectangle inside
    the last card's group, and every checker that reads a card's box from its
    first <rect> then saw that card covering the whole picture.
    """
    from infragram.exports import render_project_svg
    from infragram.paths import skill_assets
    from infragram.projects import CloudProject

    project = CloudProject.load(skill_assets() / "templates" / "cloud" / "azure-api.infragram.json")
    svg = render_project_svg(project, "#ffffff")
    ground = svg.index("data-export-background")
    assert ground < svg.index("<g "), "the ground is behind everything drawn"
    assert "data-node=" not in svg[:ground], "and outside every component's group"
