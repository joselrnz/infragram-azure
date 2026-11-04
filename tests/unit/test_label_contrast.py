"""A frame's title is readable, and still says which frame it is.

A frame's title used to be painted in the frame's own border colour, which is
how a vendor deck draws a group. At the size a deck draws it, that is legible.
Our titles are 10 px, and at 10 px several of those colours were not: the
generic frame's grey measured 1.9:1 against white where 4.5:1 is the floor for
text that size, and the AWS Region teal and public-subnet green sat near 3:1.

The border still carries the deck's colour exactly -- that fidelity is
documented in frames.md and tested in test_aws_group_fidelity.py. Only the
text is darkened, and only as far as the floor, so the hue that identifies the
frame survives.

One implementation serves both renderers: the static picture calls
``readable`` directly and the editor state carries its result to the runtime,
so a title cannot come out one colour in the fallback picture and another in
the export.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from infragram.builders.ink import MINIMUM_CONTRAST, contrast, luminance, readable
from infragram.exports import render_project_svg
from infragram.projects import CloudProject

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
TEMPLATES = ROOT / "skills/infragram-azure/assets/templates/cloud"
TEXT = re.compile(r'<text[^>]*font-size="([0-9.]+)"[^>]*>', re.IGNORECASE)
FILL = re.compile(r'fill="(#[0-9a-fA-F]{6})"')


def test_white_and_black_anchor_the_scale() -> None:
    assert contrast("#ffffff", "#000000") == pytest.approx(21.0, abs=0.01)
    assert contrast("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.01)
    assert luminance("#000000") == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("colour", ["#0F1B2A", "#232f3e", "#16191f", "#000000"])
def test_a_colour_that_already_reads_is_left_alone(colour: str) -> None:
    assert readable(colour) == colour


@pytest.mark.parametrize("colour", ["#bdbdbd", "#00a4a6", "#7aa116", "#7d8998", "#e7157b"])
def test_a_colour_too_pale_to_read_is_darkened_to_the_floor(colour: str) -> None:
    out = readable(colour)
    assert out != colour
    assert contrast(out, "#ffffff") >= MINIMUM_CONTRAST
    # Darkened, not replaced: it must still be recognisably the same colour.
    assert luminance(out) < luminance(colour)


def test_the_hue_survives_the_darkening() -> None:
    """A green frame keeps a green title; that is what makes it identifiable."""
    import colorsys

    def hue(colour: str) -> float:
        value = colour.lstrip("#")
        rgb = tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
        return colorsys.rgb_to_hls(*rgb)[0]

    for colour in ("#00a4a6", "#7aa116", "#8c4fff", "#e7157b"):
        assert hue(readable(colour)) == pytest.approx(hue(colour), abs=0.02)


@pytest.mark.parametrize("value", ["", "none", "currentColor", "url(#x)", None, 42])
def test_anything_that_is_not_a_hex_colour_passes_through(value) -> None:
    assert readable(value) == value


def test_every_label_in_every_template_is_readable() -> None:
    """The whole point, checked against everything we ship."""
    failures = []
    for path in sorted(TEMPLATES.glob("*.infragram.json")):
        svg = render_project_svg(CloudProject.load(path))
        for match in re.finditer(r"<text[^>]*>", svg):
            tag = match.group(0)
            size = re.search(r'font-size="([0-9.]+)"', tag)
            fill = FILL.search(tag)
            if not size or not fill:
                continue
            floor = 3.0 if float(size.group(1)) >= 14 else MINIMUM_CONTRAST
            ratio = contrast(fill.group(1), "#ffffff")
            if ratio < floor:
                failures.append(
                    f"{path.stem}: {fill.group(1)} at {size.group(1)}px is {ratio:.1f}:1"
                )
    assert failures == [], failures[:12]


def test_both_renderers_agree_on_a_title_colour() -> None:
    """The static picture and the editor state must name the same ink."""
    from infragram.builders.architecture import from_topology, load_style, load_theme
    from infragram.editor.state import _editor_state  # noqa: PLC2701 - the state is the contract

    path = next(TEMPLATES.glob("azure-hub-*.infragram.json"))
    project = CloudProject.load(path)
    svg = render_project_svg(project)
    drawn = set(FILL.findall(svg))
    theme = load_theme(project.provider)
    scene = from_topology(
        project.topology,
        theme,
        slug=project.slug,
        title=project.title,
        desc=project.description,
        style=load_style(project.provider),
    )
    state = json.loads(json.dumps(_editor_state(project, scene, {"providers": []})))
    for boundary in state.get("boundaries") or []:
        colour = boundary.get("labelColor")
        if isinstance(colour, str) and colour.startswith("#"):
            assert contrast(colour, "#ffffff") >= MINIMUM_CONTRAST, boundary.get("label")
            assert colour in drawn, (
                f"{boundary.get('label')}: {colour} is not a fill the picture draws"
            )
