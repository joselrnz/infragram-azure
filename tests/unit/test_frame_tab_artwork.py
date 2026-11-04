"""A frame's corner tab must carry the group's glyph, not its gallery preview.

Every frame component ships two pieces of artwork. One is a small square
glyph -- the AWS logo, a padlock for a private subnet, a flag for a Region --
meant to be reversed out of the 16 px tab in the frame's corner. The other is
a 120x72 *preview*: a little picture of a framed box with a tab and a label,
drawn for the component gallery in the sidebar.

They are easy to confuse because both hang off the same component. Feeding the
preview to the tab squeezes a 120x72 drawing into 16 px, which renders as an
unreadable dark smudge, and it did so on every frame of every diagram until
this was caught by eye rather than by a test.

The give-away is the aspect ratio, so that is what these assert.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest

from infragram.exports import render_project_html
from infragram.projects import CloudProject

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
TEMPLATES = ROOT / "skills/infragram-azure/assets/templates/cloud"

#: Frames whose tab is drawn from a data URI, across Azure badges, the
#: Kubernetes mark and the core frames' generic glyphs.
TEMPLATE_SLUGS = (
    "azure-hub-spoke-landing-zone",
    "azure-aks-baseline",
    "azure-web-app-front-door",
)


def _boundaries(slug: str) -> list[dict]:
    project = CloudProject.model_validate(
        json.loads((TEMPLATES / f"{slug}.infragram.json").read_text(encoding="utf-8"))
    )
    html = render_project_html(project)
    match = re.search(r'<script[^>]*id="infragram-editor-state"[^>]*>(.*?)</script>', html, re.S)
    assert match, f"{slug}: no editor state in the page"
    boundaries = json.loads(match.group(1)).get("boundaries")
    assert boundaries, f"{slug}: editor state carries no boundaries"
    return boundaries


def _view_box(icon_uri: str) -> tuple[float, float] | None:
    """The width and height an icon declares, or None if it declares neither."""
    prefix = "data:image/svg+xml;base64,"
    if not icon_uri.startswith(prefix):
        return None
    svg = base64.b64decode(icon_uri[len(prefix) :]).decode("utf-8", "replace")
    box = re.search(r'viewBox="\s*[\d.-]+\s+[\d.-]+\s+([\d.]+)\s+([\d.]+)', svg)
    if box:
        return float(box.group(1)), float(box.group(2))
    return None


@pytest.mark.parametrize("slug", TEMPLATE_SLUGS)
def test_frame_tabs_are_glyphs_not_gallery_previews(slug: str) -> None:
    checked = 0
    for boundary in _boundaries(slug):
        icon_uri = str(boundary.get("iconUri") or "")
        if not icon_uri:
            continue
        size = _view_box(icon_uri)
        if size is None:
            continue
        width, height = size
        checked += 1
        assert height, f"{slug}: {boundary.get('name')!r} tab icon has no height"
        ratio = width / height
        assert ratio < 1.5, (
            f"{slug}: {boundary.get('name')!r} tab icon is {width:g}x{height:g}"
            f" (ratio {ratio:.2f}). That is the shape of the 120x72 gallery"
            " preview, not a tab glyph."
        )
    assert checked, f"{slug}: no frame tab artwork to check"


@pytest.mark.parametrize("slug", TEMPLATE_SLUGS)
def test_a_tabbed_frame_actually_has_artwork(slug: str) -> None:
    """`tabbed` fills the corner with a solid block of the border colour and
    reverses the glyph out of it. Claiming a tab with nothing to put in it
    leaves a coloured square sitting where the label should start."""
    for boundary in _boundaries(slug):
        if boundary.get("tabbed"):
            assert boundary.get("iconUri"), (
                f"{slug}: {boundary.get('name')!r} claims a tab but ships no glyph"
            )
