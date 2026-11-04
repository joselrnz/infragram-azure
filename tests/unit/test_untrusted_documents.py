"""A project document is untrusted input.

Anyone can be sent a `.infragram.json` and asked to render it, and the render
opens the result in a browser, so a document must not be able to run code or
read files. These are the four ways it could, each demonstrated and each
closed. They exist because a security review found all four working.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from infragram import compose
from infragram.builders.architecture import load_icon_set
from infragram.exports import render_project_html, render_project_svg
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.azure import general

BREAKOUT = "</SCRIPT><img src=x onerror=alert(1)>"


@pytest.fixture(autouse=True)
def _fresh_ids():
    reset_ids()


def _two_nodes():
    internet = shared.networking.PublicInternet("Internet", "public")
    browser = general.Browser("Browser", "client")
    internet.to(browser, label="egress")
    return [internet, browser]


def _page(**project_kwargs) -> str:
    project = compose.to_project(_two_nodes(), **project_kwargs)
    return render_project_html(project)


def test_a_title_cannot_close_the_script_block_that_carries_it() -> None:
    """HTML matches an end tag without regard to case, so a case-sensitive
    guard leaves `</SCRIPT>` alone and the document escapes into markup."""
    html = _page(slug="d", title=f"Report {BREAKOUT}", description="d.", display="card")
    # The payload never appears as written: it would end the JSON block, and
    # everything after it would be parsed as markup.
    assert BREAKOUT not in html
    # What survives is the neutralised form, still inside the block, and a
    # JSON parser decodes it straight back to the title the author wrote.
    assert "\\u003c/SCRIPT\\u003e" in html
    state = re.search(r'id="infragram-project">(.*?)</script>', html, re.S)
    assert state and json.loads(state.group(1))["title"].endswith(BREAKOUT)


def test_a_description_cannot_comment_out_the_rest_of_the_page() -> None:
    html = _page(slug="d", title="D", description="<!-- swallow the page", display="card")
    assert "<!-- swallow" not in html


def test_a_connector_colour_cannot_break_out_of_its_attribute() -> None:
    """The stroke comes from the document and lands in an SVG attribute."""
    internet, browser = _two_nodes()
    internet.attributes["editor_edge_styles"] = {
        browser.id: {"stroke": '#000" onload="alert(1)', "width": 1.4},
    }
    html = render_project_html(
        compose.to_project(
            [internet, browser], slug="d", title="D", description="d.", display="card"
        )
    )
    assert 'onload="alert(1)' not in html
    state = re.search(r'id="infragram-editor-state" data-editor-state>(.*?)</script>', html, re.S)
    assert state, "the page carries editor state"
    json.loads(state.group(1))  # still parses: the guard did not corrupt it


def test_a_document_cannot_name_an_icon_collection_outside_the_assets() -> None:
    """`icon_collection` is a name, not a path: a separator or a parent
    reference would read whatever it landed on and inline it as artwork."""
    for escape_attempt in ("../../../..", "vendors/azure", "azure/../..", "", "AZURE"):
        with pytest.raises(KeyError):
            load_icon_set(escape_attempt)
    assert load_icon_set("azure") is not None


def test_the_static_picture_escapes_what_it_draws() -> None:
    svg = render_project_svg(
        compose.to_project(
            _two_nodes(), slug="d", title=f"T {BREAKOUT}", description="d.", display="card"
        )
    )
    assert BREAKOUT not in svg
    assert "&lt;/SCRIPT&gt;" in svg or "&lt;/script&gt;" in svg.lower()


def test_every_shipped_icon_is_safe_to_inline() -> None:
    """Artwork is inlined verbatim into an export, so none of it may carry a
    script, an event handler, a foreign object or an external reference."""
    from infragram.verification import unsafe_svg_match

    root = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
    icons = sorted((root / "skills/infragram-azure/assets/icons").rglob("*.svg"))
    assert len(icons) > 700, "the shipped icon sets are present"
    unsafe = [
        (p.name, unsafe_svg_match(p.read_text(encoding="utf-8", errors="ignore"))) for p in icons
    ]
    offenders = [(name, hit.group(0)) for name, hit in unsafe if hit]
    assert offenders == [], offenders
