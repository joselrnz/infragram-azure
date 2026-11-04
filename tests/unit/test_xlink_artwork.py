"""A drawing that uses an icon written with ``xlink:href`` is still XML.

Three shipped icons -- ExternalID, ExternalIDModified and PublicIPPrefixes --
say ``xlink:href``. Each declares ``xmlns:xlink`` on its own root, and inlining
keeps the body and drops that root. HTML never needs the declaration, so the
page drew; XML does, so every ``.svg`` holding one of them failed to open
outside a browser tab, and the editor's own export -- parsed as XML before it
is captured -- failed too. The full edition found it (Azure's every-service
map came out as a PNG that was 98% black); this edition shipped the same three
icons without the declaration until it was ported.

None of the shipped templates uses these icons, which is why no picture ever
showed it: the failure waited for somebody to drag one onto a canvas.
"""

from __future__ import annotations

import importlib
import inspect
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from infragram.author import Diagram
from infragram.exports import render_project_svg
from infragram.exports.svg import finish_standalone_svg
from infragram.nodes._base import Element
from infragram.verification import XLINK_NS, declare_xlink

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
ICONS = ROOT / "skills" / "infragram-azure" / "assets" / "icons" / "vendors"


def xlink_components() -> list[tuple[str, type]]:
    """Every component whose shipped artwork says xlink, found by reading
    the artwork rather than listed by hand, so a sixth one is covered the
    day it is imported."""
    found: list[tuple[str, type]] = []
    for path in sorted(ICONS.rglob("*.svg")):
        if "xlink:" not in path.read_text(encoding="utf-8", errors="replace"):
            continue
        library = path.relative_to(ICONS).parts[0]
        package = importlib.import_module(f"infragram.nodes.{library}")
        for category in package.CATEGORIES:
            module = importlib.import_module(f"infragram.nodes.{library}.{category}")
            match = next(
                (
                    value
                    for name, value in vars(module).items()
                    if inspect.isclass(value)
                    and not name.startswith("_")
                    and issubclass(value, Element)
                    and value.__module__ == module.__name__
                    and path.stem == value.ICON
                ),
                None,
            )
            if match is not None:
                found.append((library, match))
                break
    return found


XLINKED = xlink_components()


def test_the_artwork_that_needs_this_is_still_shipped() -> None:
    """If none are left, the screens below prove nothing and should say so."""
    assert XLINKED, "no shipped icon uses xlink any more; retire this file"


@pytest.mark.parametrize(
    ("library", "component"), XLINKED, ids=[f"{library}-{cls.__name__}" for library, cls in XLINKED]
)
def test_a_drawing_holding_it_is_well_formed_xml(library: str, component: type) -> None:
    with Diagram("x", "y", slug=f"xlink-{component.ICON}", providers=(library,)) as diagram:
        component("It", "uses xlink")
    svg = render_project_svg(diagram.to_project())
    assert "xlink:" in svg, "the fixture no longer exercises the prefix"
    ET.fromstring(svg.encode("utf-8"))  # raises on an unbound prefix


def test_the_declaration_goes_on_once_and_only_where_it_is_needed() -> None:
    uses = '<svg viewBox="0 0 1 1"><use xlink:href="#a"/></svg>'
    declared = declare_xlink(uses)
    assert declared.count(f'xmlns:xlink="{XLINK_NS}"') == 1
    assert declare_xlink(declared) == declared, "declaring twice is not XML either"
    ET.fromstring(declared)

    # A drawing that never says xlink is left byte-for-byte alone -- which is
    # why none of the golden pictures moved.
    plain = '<svg viewBox="0 0 1 1"><use href="#a"/></svg>'
    assert declare_xlink(plain) == plain


def test_every_standalone_file_carries_it_whatever_produced_it() -> None:
    """The editor's export, the static render and a hand-written SVG all go
    through the one finisher before they become a file."""
    raw = '<svg viewBox="0 0 10 10"><defs><linearGradient id="a" xlink:href="#b"/></defs></svg>'
    ET.fromstring(finish_standalone_svg(raw).encode("utf-8"))
