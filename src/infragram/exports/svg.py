"""One SVG document, finished: namespace, viewBox, fonts, ground.

Everything here works on SVG markup as text, wherever it came from -- the
static renderer, a page's embedded drawing, or the editor runtime's own export
-- so a file written by any path carries the same faces and the same ground.
"""

from __future__ import annotations

import re

from ..catalog.fonts import font_css_for, font_style_element
from ..verification import declare_xlink
from .errors import ExportError

__all__ = [
    "DEFAULT_EXPORT_BACKGROUND",
    "extract_svg",
    "finish_standalone_svg",
    "make_standalone_svg",
    "resolve_background",
]


_SVG_TAG = re.compile(r"<\s*(/?)svg\b[^>]*>", re.IGNORECASE)


_OPEN_SVG = re.compile(r"<svg\b([^>]*)>", re.IGNORECASE)


_FACE = re.compile(r"@font-face\s*\{[^}]*\}")
_DEFS = re.compile(r"<defs\b[^>]*>", re.IGNORECASE)


#: One element of the root preamble: the parts that draw nothing and that a
#: reader is announced before the picture, or a comment, with the whitespace
#: before it. Matched one at a time from the opening tag onwards.
_PREAMBLE_PART = re.compile(
    r"\s*(?:<!--.*?-->"
    r"|<(title|desc|defs|style|metadata)\b[^>]*>.*?</\1\s*>"
    r"|<(?:title|desc|defs|style|metadata)\b[^>]*/>)",
    re.IGNORECASE | re.DOTALL,
)


def extract_svg(html: str) -> str:
    """Return the marked diagram SVG, falling back to the first complete SVG."""

    tags = list(_SVG_TAG.finditer(html))
    opening_index = next(
        (
            index
            for index, match in enumerate(tags)
            if not match.group(1) and "data-infragram-diagram" in match.group(0)
        ),
        next(
            (index for index, match in enumerate(tags) if not match.group(1)),
            None,
        ),
    )
    if opening_index is None:
        raise ExportError("source HTML does not contain an SVG diagram")

    start = tags[opening_index].start()
    depth = 0
    for match in tags[opening_index:]:
        closing = bool(match.group(1))
        depth += -1 if closing else 1
        if depth == 0:
            return html[start : match.end()]
    raise ExportError("source HTML does not contain an SVG diagram")


def make_standalone_svg(html: str) -> str:
    """Finish the static SVG embedded in an HTML page.

    Kept for Azure callers; editor-authored coordinates use the browser
    renderer, while this helper extracts the page's static drawing.
    """
    picture = finish_standalone_svg(extract_svg(html))
    # This historical Azure helper carries the complete font set. Current
    # exporters call finish_standalone_svg directly for the smaller used set.
    picture = re.sub(
        r"(<style[^>]*>)([^<]*)(</style>)",
        lambda match: match.group(1) + _FACE.sub("", match.group(2)) + match.group(3),
        picture,
    )
    picture = re.sub(r"<style[^>]*>\s*</style>", "", picture)
    defs = _DEFS.search(picture)
    if defs is None:
        insertion = _end_of_preamble(picture)
        picture = (
            picture[:insertion] + "<defs>" + font_style_element() + "</defs>" + picture[insertion:]
        )
    else:
        picture = picture[: defs.end()] + font_style_element() + picture[defs.end() :]
    return picture


#: What an export paints behind the diagram when the caller does not say.
#: A transparent picture takes the colour of whatever it lands on, and in a
#: dark viewer, chat client or terminal that is dark text on black, so a
#: light-only product paints its own paper. ``background="transparent"`` is
#: for a picture that really is going onto a coloured ground.
DEFAULT_EXPORT_BACKGROUND = "paper"


def resolve_background(background: str, paper: str) -> str | None:
    """The colour to paint behind a diagram, or None to leave it clear."""
    if background in ("transparent", "none", ""):
        return None
    if background == DEFAULT_EXPORT_BACKGROUND:
        return paper or "#ffffff"
    if not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", background):
        raise ExportError(
            f"unknown export background {background!r}; use paper, transparent, or a hex colour"
        )
    return background


def finish_standalone_svg(svg: str, background: str | None = None) -> str:
    """Complete one SVG document: namespace, viewBox check, font import.

    ``background`` paints a ground rectangle over the whole viewBox, behind
    everything, so the file carries its own colour instead of borrowing the
    viewer's.
    """

    opening = _OPEN_SVG.search(svg)
    if opening is None:
        raise ExportError("source HTML does not contain an SVG diagram")
    attributes = opening.group(1)
    if not re.search(r"\bviewBox\s*=", attributes):
        raise ExportError("diagram SVG is missing a viewBox; refusing to guess its size")
    if not re.search(r"\bxmlns\s*=", attributes):
        replacement = opening.group(0)[:-1] + ' xmlns="http://www.w3.org/2000/svg">'
        svg = svg[: opening.start()] + replacement + svg[opening.end() :]
    # Whatever produced it, a file that uses the xlink prefix declares it.
    svg = declare_xlink(svg)

    # A picture carries only the faces it draws with. The editor's export
    # carries every face its page loads; those rules come out here and the
    # ones this picture needs go back in (catalog/fonts.py used_faces).
    if "@font-face" in svg:
        svg = re.sub(
            r"(<style[^>]*>)([^<]*)(</style>)",
            lambda m: m.group(1) + _FACE.sub("", m.group(2)) + m.group(3),
            svg,
        )
        svg = re.sub(r"<style[^>]*>\s*</style>", "", svg)
    faces = font_css_for(svg)
    if faces and "fonts.googleapis.com" not in svg:
        # the faces travel with the picture: an SVG embedded as an image
        # never fetches a stylesheet, and a viewer offline has no network
        font_style = f'<style type="text/css">{faces}</style>'
        defs = _DEFS.search(svg)
        if defs is not None:
            svg = svg[: defs.end()] + "\n          " + font_style + svg[defs.end() :]
        else:
            insertion = None
            for closing_tag in ("</desc>", "</title>"):
                # matched on the text itself, case aside: lower-casing the
                # document can change its length (a dotted capital I lowers
                # to two code points) and a position found there slices the
                # original in the wrong place
                found = re.search(re.escape(closing_tag), svg, re.IGNORECASE)
                if found is not None:
                    insertion = found.end()
                    break
            if insertion is None:
                insertion = _OPEN_SVG.search(svg).end()  # type: ignore[union-attr]
            svg = svg[:insertion] + f"\n        <defs>{font_style}</defs>" + svg[insertion:]

    if background:
        # Behind everything, covering the whole viewBox including the margin.
        # Placed after the root <title>/<desc>/<defs> so it never precedes
        # the parts a reader is announced first, and before any drawn element.
        box = re.search(r'\bviewBox\s*=\s*"([^"]+)"', svg)
        numbers = box.group(1).replace(",", " ").split() if box else []
        if len(numbers) == 4:
            x, y, width, height = numbers
            ground = (
                f'<rect data-export-background="" x="{x}" y="{y}" '
                f'width="{width}" height="{height}" fill="{background}"/>'
            )
            after = _end_of_preamble(svg)
            svg = svg[:after] + "\n        " + ground + svg[after:]
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + svg.strip() + "\n"


def _end_of_preamble(svg: str) -> int:
    """Where the first drawn element of the document starts.

    Past the opening tag and every root-level ``<title>``, ``<desc>``,
    ``<defs>``, ``<style>``, ``<metadata>`` and comment that follows it, and
    not one character further. Every node group carries a ``<title>`` of its
    own, so looking for the last closing tag in the document (as this once
    did) landed the ground inside the last group, translated with it and
    painted over everything drawn before.
    """
    position = _OPEN_SVG.search(svg).end()  # type: ignore[union-attr]
    while True:
        part = _PREAMBLE_PART.match(svg, position)
        if part is None:
            return position
        position = part.end()
