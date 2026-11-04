"""A stroked glyph stays stroked once it becomes a <symbol>.

Every icon is inlined into an export as one ``<symbol>`` holding the artwork's
inner body. The body was all that was kept, and for most artwork that is
enough: a vendor icon paints each path, so it carries its own colour.

The neutral primitives do not. The Tabler set that draws them is
``fill="none" stroke="#909296" stroke-width="1.5"`` on the root ``<svg>`` with
bare ``<path d="...">`` inside, so dropping the root dropped the entire style
and the paths fell back to the SVG default -- ``fill: black, stroke: none``.
Every WAF, bastion, load balancer, HSM and user in every exported SVG drew as
a filled black silhouette instead of a grey outline. It was invisible on the
old dark canvas and obvious the moment the themes went light.

The presentation attributes now ride on the symbol, where they inherit to the
paths exactly as they did under the original root.
"""

from __future__ import annotations

import re

import pytest

from infragram import compose
from infragram.builders.render import render_svg
from infragram.catalog.components import primitive_icon_svg
from infragram.exports import render_project_svg
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import compute
from infragram.projects import CloudProject
from infragram.verification import (
    _ATTRIBUTE,
    PRESENTATION_ATTRIBUTES,
    root_presentation,
)


def _project():
    reset_ids()
    waf = shared.security.WAF("WAF", "edge")
    users = shared.identity.PublicUsers("Customers", "public")
    vm = compute.VirtualMachine("Web tier", "D4s v5")
    users.to(waf, label="HTTPS")
    waf.to(vm, label="clean")
    return compose.to_project(
        [users, waf, vm], slug="paint", title="Paint", description="Glyph paint.", display="icon"
    )


def test_the_helper_carries_only_presentation_attributes() -> None:
    source = (
        '<svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" '
        'fill="none" stroke="#909296" stroke-width="1.5" class="x"><path d="M0 0"/></svg>'
    )
    carried = root_presentation(source)
    assert 'fill="none"' in carried
    assert 'stroke="#909296"' in carried
    assert 'stroke-width="1.5"' in carried
    # Not layout, identity or accessibility. Compared as whole attribute
    # names, because "stroke-width" ends in the one we are excluding.
    names = {name for name, _ in _ATTRIBUTE.findall(carried)}
    assert names == {"fill", "stroke", "stroke-width"}, names


def test_artwork_that_paints_itself_carries_nothing() -> None:
    """Vendor artwork colours each path, so there is nothing to hoist."""
    assert root_presentation('<svg viewBox="0 0 24 24"><path fill="#f90" d="M0 0"/></svg>') == ""


@pytest.mark.parametrize("icon_id", ["waf", "users", "jump-host", "hsm", "printer"])
def test_a_neutral_glyph_declares_its_stroke_on_the_root(icon_id: str) -> None:
    """The precondition for the bug: the style lives only on the root."""
    source = primitive_icon_svg(icon_id).decode("utf-8")
    assert 'fill="none"' in source and "stroke=" in source
    body = source[source.index(">") + 1 :]
    assert "stroke=" not in body, (
        f"{icon_id} paints its paths; this test is checking the wrong thing"
    )


def test_the_symbol_keeps_the_stroke() -> None:
    """What actually broke: the symbol, as written into an export."""
    svg = render_project_svg(CloudProject.model_validate(_project().model_dump()))
    match = re.search(r'<symbol id="icon-infragram-waf"([^>]*)>', svg)
    assert match is not None, "the WAF glyph is not in the picture"
    attributes = match.group(1)
    assert 'fill="none"' in attributes, "a filled black silhouette again"
    assert "stroke=" in attributes, "the outline lost its colour"


def test_every_symbol_that_needs_paint_has_it() -> None:
    """No glyph in a rendered picture may fall back to the SVG default."""
    svg = render_project_svg(CloudProject.model_validate(_project().model_dump()))
    for match in re.finditer(r'<symbol id="([^"]+)"([^>]*)>(.*?)</symbol>', svg, re.S):
        name, attributes, body = match.groups()
        paints_itself = "fill=" in body or "stroke=" in body
        assert paints_itself or "fill=" in attributes or "stroke=" in attributes, (
            f"{name} would draw as a filled black shape: no paint on the symbol or its paths"
        )


def test_the_attribute_list_is_documented_where_it_is_used() -> None:
    """A silent list is how this was lost the first time."""
    assert "stroke-linecap" in PRESENTATION_ATTRIBUTES
    assert "stroke-linejoin" in PRESENTATION_ATTRIBUTES
    assert "viewBox" not in PRESENTATION_ATTRIBUTES
    assert render_svg.__module__.startswith("infragram.builders")
