"""The faces every picture carries inline.

The editor page, the static page and the standalone SVG all set their text in
Inter, with Geist Mono for monospaced text. The faces ship with the skill
(``assets/fonts``: subsetted woff2 as the Google Fonts API serves them, under
the SIL Open Font License, with the notices beside them) and are written into
each document as ``@font-face`` rules with the file inline, so a picture
opened offline, embedded as an image, or rendered on a machine without a
route out still draws in its own faces, and a render never waits on a font
request.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from functools import cache, lru_cache
from html import unescape
from pathlib import Path

from ..paths import skill_assets

#: The families a picture sets its text in, in the order the rules are written.
FAMILIES = ("Inter", "Geist Mono")


def fonts_dir() -> Path:
    return skill_assets() / "fonts"


@lru_cache(maxsize=1)
def load_font_catalog() -> dict:
    """The shipped faces with their provenance: file, weight range, subset,
    unicode range, source URL, digest and licence notice."""
    return json.loads((fonts_dir() / "catalog.json").read_text(encoding="utf-8"))


def font_face_rules() -> list[dict]:
    return list(load_font_catalog()["faces"])


@cache
def _face_rule(file: str) -> str:
    """One face's ``@font-face`` rule, its file inline as a data URI.

    Every file is checked against the digest the catalog records before it is
    written into a document, so a font that drifted from its provenance is
    refused rather than shipped.
    """
    face = next(face for face in font_face_rules() if face["file"] == file)
    data = (fonts_dir() / face["file"]).read_bytes()
    if hashlib.sha256(data).hexdigest() != face["sha256"]:
        raise RuntimeError(f"font {face['file']} does not match the digest in fonts/catalog.json")
    payload = base64.b64encode(data).decode("ascii")
    return (
        "@font-face{"
        f"font-family:'{face['family']}';"
        f"font-style:{face['style']};"
        f"font-weight:{face['weight']};"
        "font-display:swap;"
        f"src:url(data:font/woff2;base64,{payload}) format('woff2');"
        f"unicode-range:{face['unicode_range']}"
        "}"
    )


@lru_cache(maxsize=1)
def font_face_css() -> str:
    """Every shipped face, for a page that may set any text in any of them:
    the editor, where the reader types."""
    return "".join(_face_rule(face["file"]) for face in font_face_rules())


def _ranges(unicode_range: str) -> list[tuple[int, int]]:
    """``U+0000-00FF, U+0131`` as inclusive code point spans."""
    spans = []
    for part in unicode_range.split(","):
        part = part.strip().upper().removeprefix("U+")
        if not part:
            continue
        low, _, high = part.partition("-")
        if "?" in low:  # U+04?? is a span of the wildcard's width
            spans.append((int(low.replace("?", "0"), 16), int(low.replace("?", "F"), 16)))
        else:
            spans.append((int(low, 16), int(high or low, 16)))
    return spans


_TEXT_RUN = re.compile(r"<(?:text|tspan)\b[^>]*>([^<]*)", re.S)
_FAMILY_ATTR = re.compile(r"font-family\s*[=:]\s*\"?([^\";>]+)")
_FACE_BLOCK = re.compile(r"@font-face\s*\{[^}]*\}")


def used_faces(svg: str) -> list[str]:
    """The shipped face files a finished picture needs: the families its text
    names, and of each only the subsets holding a character it draws. A
    picture set in Inter alone never carried Geist Mono, and
    one written in English never needed the Latin Extended file."""
    body = _FACE_BLOCK.sub("", svg)
    named = {
        family.strip().strip("\"'").strip().casefold()
        for match in _FAMILY_ATTR.finditer(body)
        for family in match.group(1).split(",")
    }
    families = [family for family in FAMILIES if family.casefold() in named]
    points = {ord(char) for run in _TEXT_RUN.findall(body) for char in unescape(run)}
    files = []
    for family in families:
        faces = [face for face in font_face_rules() if face["family"] == family]
        needed = [
            face["file"]
            for face in faces
            if any(
                low <= point <= high
                for point in points
                for low, high in _ranges(face["unicode_range"])
            )
        ]
        # a family named with no text of its own still keeps its base subset
        files += needed or [faces[0]["file"]] if faces else []
    return files


def font_css_for(svg: str) -> str:
    """The ``@font-face`` rules one finished picture needs (see used_faces)."""
    return "".join(_face_rule(file) for file in used_faces(svg))


def font_style_element() -> str:
    """The ``<style>`` element a document carries its faces in."""
    return f'<style type="text/css">{font_face_css()}</style>'
