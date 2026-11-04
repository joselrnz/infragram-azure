"""Every icon the skill ships can actually be drawn.

The renderer refuses artwork it cannot read -- ``unusable icon svg`` -- and a
component whose icon is refused does not fall back to a blank mark: it raises,
and takes the whole diagram with it. So a single bad file in an icon pack is
not a cosmetic fault in one sidebar row, it is every document that reaches for
that component failing to render at all.

One did ship: ``azure/ai-machine-learning/foundry-control-plane.svg`` carried
``xviewBox`` where it meant ``viewBox``, so ``FoundryControlPlane`` raised for
as long as it has existed. Nothing caught it, because the shipped templates
happen not to use that component and nothing else asked all 3,535 files
whether they could be drawn.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from infragram.builders.render import inner_body, view_box

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
ICONS = ROOT / "skills" / "infragram-azure" / "assets" / "icons"

#: The renderer reads the root element for the box it draws into. An
#: ``xviewBox`` is a typo an eye slides over and a parser does not.
SVG_TAG = re.compile(r"<svg\b[^>]*>", re.S)


def icons() -> list[Path]:
    found = sorted(ICONS.rglob("*.svg"))
    assert len(found) > 700, f"only {len(found)} icons found; is the assets path right?"
    return found


@pytest.mark.parametrize("path", icons(), ids=lambda p: p.relative_to(ICONS).as_posix())
def test_every_shipped_icon_has_a_box_and_a_body(path: Path) -> None:
    """What the renderer needs from a file before it will draw it: somewhere
    to draw into, and something to draw."""
    source = path.read_text(encoding="utf-8")
    relative = path.relative_to(ICONS).as_posix()

    tag = SVG_TAG.search(source)
    assert tag, f"{relative}: no <svg> root element"
    assert re.search(r"\bviewBox\s*=", tag.group(0)), f"{relative}: the root has no viewBox" + (
        " -- it has xviewBox" if "xviewBox" in tag.group(0) else ""
    )

    assert view_box(source) is not None, f"{relative}: the renderer cannot read its box"
    assert inner_body(source) is not None, f"{relative}: the renderer finds nothing to draw"


# The gate that should have stopped it. `"viewbox=" not in lowered` was a
# substring test over the whole file, and `xviewBox="0 0 18 18"` contains the
# letters `viewbox=`, so the one check standing between a third-party pack and
# the renderer waved through the exact file the renderer refuses.
VIEW_BOX_CASES = (
    ('<svg width="18" height="18" viewBox="0 0 18 18"><path d="M0 0h1v1H0z"/></svg>', True),
    ('<svg xviewBox="0 0 18 18"><path d="M0 0h1v1H0z"/></svg>', False),
    ('<svg\n  width="1"\n  viewBox="0 0 1 1">\n<path d="M0 0h1v1H0z"/></svg>', True),
    ('<svg id="a"><g data-viewBox="0 0 1 1"/></svg>', False),
    ('<svg data-viewBox="nope" viewBox="0 0 2 2"><path d="M0 0h1v1H0z"/></svg>', True),
    ('<svg VIEWBOX="0 0 2 2"><path d="M0 0h1v1H0z"/></svg>', True),
)


@pytest.mark.parametrize(("source", "usable"), VIEW_BOX_CASES)
def test_a_view_box_is_read_off_the_root_and_nowhere_else(source: str, usable: bool) -> None:
    """A decoy attribute must not pass, and a real one must not be refused --
    including one on a second line, spelled in capitals, or sitting after an
    attribute whose name merely ends in the same word. The catalog asks this
    same extractor, so the gate and the renderer cannot disagree."""
    assert (view_box(source) is not None) is usable
