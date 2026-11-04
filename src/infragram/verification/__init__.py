"""Verification primitives: SVG safety, extraction, and validation patterns.

These operate on trusted, repo-local text with regexes; they are not a
general-purpose SVG parser. ``VIEWBOX_RE`` is the one canonical extractor:
it reads the root element only, and accepts either quote style, whitespace
around ``=``, and any attribute case, so every consumer sees the same set of
valid icons -- the catalog gate included, which asks it rather than looking
for the letters itself. Two hand-rolled copies of that regex used to
disagree on single-quoted attributes.

The standalone CI gates live in ``scripts/verify/`` and build on these.
"""

from __future__ import annotations

import html
import re

from ..utils.text import SLUG as _SLUG

#: The root element's ``viewBox``: the box artwork is drawn into.
#:
#: Scoped to the ``<svg ...>`` tag and to the whole attribute name. It used to
#: be ``\bviewBox`` over the entire document, which is looser in both
#: directions at once: ``-`` is a word boundary, so ``data-viewBox`` on a
#: child element was read as the root's box; and the catalog's own check was
#: ``"viewbox=" in`` over the file, which ``xviewBox`` satisfies. A file
#: carrying that typo therefore passed the gate and was refused by the
#: renderer, which is how one shipped.
VIEWBOX_RE = re.compile(
    r'<svg\b[^>]*?(?<![\w-])viewBox\s*=\s*(["\'])(.*?)\1',
    re.IGNORECASE | re.DOTALL,
)
SVG_BODY_RE = re.compile(r"<svg\b[^>]*>(.*)</svg>\s*$", re.DOTALL | re.IGNORECASE)

# Reject active content and external references. Fragment references
# (href="#local-id", url(#gradient)) stay allowed, since icons namespace and
# reuse their own gradient and mask ids; http(s): and protocol-relative
# targets, non-raster data: payloads and CSS @import do not. A CSS url() may
# name only a fragment or an inline raster: allowing that little, rather than
# refusing known schemes, also refuses a scheme hidden behind a CSS escape.
# Inline PNG/JPEG/GIF/WebP rasters are allowed: raster-only upstream sets
# (DigitalOcean docs artwork, mingrammer's on-prem nodes) ship as <image>
# wrappers, and a raster cannot carry script the way nested SVG or HTML can.
UNSAFE_SVG_RE = re.compile(
    r"<(?:script|foreignobject)\b"
    r"|javascript:"
    r"|\bon[a-z]+\s*="
    r"|\bhref\s*=\s*[\"']?\s*(?:https?:|//|data:(?!image/(?:png|jpe?g|gif|webp);base64,))"
    r"|\burl\(\s*(?![\s\"']*(?:#|data:image/(?:png|jpe?g|gif|webp);base64,))"
    r"|@import\b",
    re.IGNORECASE,
)

#: A quoted attribute value, the place a scheme hides in.
_ATTRIBUTE_VALUE = re.compile(r"=\s*([\"'])(.*?)\1", re.DOTALL)
#: ASCII whitespace and control characters, which a browser ignores inside
#: a URL scheme: ``java&#9;script:`` is ``javascript:`` to it.
_SCHEME_NOISE = re.compile(r"[\x00-\x20]")


def _svg_readings(text: str) -> tuple[str, ...]:
    """The text as written, then as a browser reads its attribute values.

    Inside attribute values, character references are decoded
    (``&#106;avascript:`` is ``javascript:``) and then the whitespace and
    control characters a URL parser drops are dropped too. Text content is
    left as written: a ``<desc>`` that spells ``&lt;script&gt;`` is prose, and
    decoding it would refuse harmless artwork.
    """

    def attribute(m: re.Match[str], squeeze: bool) -> str:
        value = html.unescape(m.group(2))
        return "=" + m.group(1) + (_SCHEME_NOISE.sub("", value) if squeeze else value) + m.group(1)

    decoded = _ATTRIBUTE_VALUE.sub(lambda m: attribute(m, False), text)
    squeezed = _ATTRIBUTE_VALUE.sub(lambda m: attribute(m, True), text)
    return text, decoded, squeezed


def unsafe_svg_match(text: str) -> re.Match[str] | None:
    """The first unsafe construct in *text*, read as a browser would, or None."""
    for reading in _svg_readings(text):
        found = UNSAFE_SVG_RE.search(reading)
        if found is not None:
            return found
    return None


def is_unsafe_svg(text: str) -> bool:
    """Whether artwork carries active content or an external reference."""
    return unsafe_svg_match(text) is not None


#: Six-digit hex color, the only color form provider manifests may declare.
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

#: Lowercase kebab-case identifier used for provider, icon, and category ids;
#: the one pattern in :mod:`infragram.utils.text`, re-exported here for the
#: registries that always imported it from this module.
SLUG = _SLUG

#: Lowercase hex sha256 digest, as recorded for every reviewed icon.
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def view_box(source: str) -> str | None:
    """The trimmed viewBox value of an SVG document, or None."""
    match = VIEWBOX_RE.search(source)
    return match.group(2).strip() if match else None


XLINK_NS = "http://www.w3.org/1999/xlink"


def declare_xlink(svg: str) -> str:
    """The document with ``xmlns:xlink`` on its root, when it uses the prefix.

    An icon that says ``xlink:href`` declares the namespace on its own root,
    and inlining keeps the body and drops that root. HTML never needs the
    declaration, so the page draws; XML does, so the same markup saved as an
    ``.svg`` does not open, and the editor's own export, which is parsed as
    XML before it is captured, fails. Nothing is added to a drawing that does
    not use the prefix, so those stay byte-for-byte what they were.
    """
    if "xlink:" not in svg:
        return svg
    opening = re.search(r"<svg\b[^>]*>", svg)
    if opening is None or "xmlns:xlink" in opening.group(0):
        return svg
    tag = opening.group(0)
    declared = tag[:-1].rstrip() + f' xmlns:xlink="{XLINK_NS}">'
    return svg[: opening.start()] + declared + svg[opening.end() :]


def inner_body(source: str) -> str | None:
    """Everything between the root ``<svg ...>`` and ``</svg>``, or None."""
    match = SVG_BODY_RE.search(source)
    return match.group(1) if match else None


#: Presentation attributes that decide how artwork draws. A stroked glyph
#: carries them on its root and nowhere else -- the Tabler set that draws the
#: neutral primitives is `fill="none" stroke="..." stroke-width="1.5"` on the
#: `<svg>` with bare `<path d="...">` inside -- so dropping the root turns an
#: outline into a filled black silhouette. Vendor artwork paints each path
#: instead, which is why the loss only ever showed on the neutral glyphs.
PRESENTATION_ATTRIBUTES = (
    "fill",
    "fill-rule",
    "fill-opacity",
    "stroke",
    "stroke-width",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-dasharray",
    "stroke-opacity",
    "clip-rule",
    "opacity",
    "color",
)

_ROOT_TAG = re.compile(r"<svg\b([^>]*)>", re.IGNORECASE | re.DOTALL)
_ATTRIBUTE = re.compile(r'([a-zA-Z-]+)\s*=\s*"([^"]*)"')


def root_presentation(source: str) -> str:
    """The root ``<svg>``'s presentation attributes, ready to re-emit.

    Returned as a string beginning with a space, or empty when the artwork
    paints itself. Copying these onto the ``<symbol>`` keeps a stroked glyph
    stroked: SVG presentation attributes inherit, so the paths inside pick
    them up exactly as they did under the original root.
    """
    match = _ROOT_TAG.search(source)
    if match is None:
        return ""
    carried = [
        f'{name}="{value}"'
        for name, value in _ATTRIBUTE.findall(match.group(1))
        if name.lower() in PRESENTATION_ATTRIBUTES
    ]
    return (" " + " ".join(carried)) if carried else ""


#: Drawing-editor leftovers: an RDF metadata block, Inkscape's saved canvas
#: state, and its namespaced attributes. They draw nothing.
_EDITOR_METADATA = re.compile(
    r"<metadata\b.*?</metadata\s*>"
    r"|<sodipodi:namedview\b[^>]*/\s*>"
    r"|<sodipodi:namedview\b.*?</sodipodi:namedview\s*>",
    re.IGNORECASE | re.DOTALL,
)
_EDITOR_ATTRIBUTE = re.compile(r"\s+(?:inkscape|sodipodi):[\w.-]+\s*=\s*\"[^\"]*\"", re.IGNORECASE)


def strip_editor_metadata(body: str) -> str:
    """Artwork with the drawing editor's own bookkeeping taken out.

    Thirty-five shipped icons were saved from Inkscape and kept its
    ``<sodipodi:namedview>``, an RDF ``<metadata>`` block and ``inkscape:``
    attributes. Inlined into an export they are worse than dead weight: the
    prefixes are undeclared in the output document, so the editor's own SVG
    export stopped being well-formed XML. The PNG exporter parses that export
    to crop the picture to its content, and a parse error sent it down a
    fallback that screenshotted the page instead -- which is how a diagram
    using Kubernetes artwork exported a PNG of the inspector panel.

    ``xlink:`` is left alone: it is declared and it does work.
    """
    return _EDITOR_ATTRIBUTE.sub("", _EDITOR_METADATA.sub("", body))
