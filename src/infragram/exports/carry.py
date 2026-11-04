"""The document a picture was drawn from, carried inside the picture.

A PNG pasted into a wiki or an SVG attached to a ticket used to be a dead
end: to change the diagram someone had to find the ``.infragram.json`` it
came from. Every exported SVG and PNG now carries its document -- the same
JSON ``.infragram.json`` holds -- so ``infragram export:project diagram.png``
redraws it, and reading it back needs nothing but the standard library.

* SVG: one ``<metadata id="infragram-document">`` element holding the JSON,
  XML-escaped. A viewer never draws metadata.
* PNG: one ``iTXt`` chunk, keyword ``infragram``, zlib-compressed, before
  ``IEND``. Viewers ignore text chunks they do not know.
* HTML: the page the editor saved already carries it
  (``<script id="infragram-project">``).

draw.io and Excalidraw do the same for their own files; ``--no-embed``
leaves a picture bare.
"""

from __future__ import annotations

import json
import re
import struct
import zlib
from html import unescape
from pathlib import Path
from xml.sax.saxutils import escape

__all__ = ["KEYWORD", "carried_document", "embed_in_png", "embed_in_svg", "page_document"]

#: The PNG text chunk's keyword, and the SVG metadata element's id suffix.
KEYWORD = "infragram"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_SVG_METADATA = re.compile(r'<metadata\b[^>]*\bid="infragram-document"[^>]*>(.*?)</metadata>', re.S)
_HTML_PROJECT = re.compile(r'<script\b[^>]*\bid="infragram-project"[^>]*>(.*?)</script>', re.S)


def embed_in_svg(svg: str, document: str) -> str:
    """The SVG with *document* in a metadata element just inside its close;
    an earlier copy is replaced, so embedding twice leaves one."""
    svg = _SVG_METADATA.sub("", svg)
    # < > & only occur inside JSON strings, where their \u escapes mean the
    # same: no reading of the picture, unescaped or not, finds markup in it
    safe = document.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    element = (
        f'<metadata id="infragram-document" data-format="infragram-project">'
        f"{escape(safe)}</metadata>\n"
    )
    end = svg.rfind("</svg>")
    # not a closed SVG: left as it is rather than broken
    return svg if end < 0 else svg[:end] + element + svg[end:]


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def _chunks(png: bytes):
    if not png.startswith(_PNG_SIGNATURE):
        raise ValueError("not a PNG image")
    at = len(_PNG_SIGNATURE)
    while at + 8 <= len(png):
        length = struct.unpack(">I", png[at : at + 4])[0]
        kind = png[at + 4 : at + 8]
        yield at, kind, png[at + 8 : at + 8 + length], at + 12 + length
        at += 12 + length


def embed_in_png(png: bytes, document: str) -> bytes:
    """The PNG with *document* in a compressed ``iTXt`` chunk before ``IEND``;
    an earlier ``infragram`` chunk is dropped, so embedding twice leaves one."""
    if not png.startswith(_PNG_SIGNATURE) or not png.endswith(b"IEND\xaeB`\x82"):
        return png  # not a whole PNG: left as it is rather than broken
    # iTXt: keyword, NUL, compression flag 1, method 0, empty language and
    # translated keyword (each NUL-terminated), then the deflated UTF-8 text
    data = (
        KEYWORD.encode("latin-1")
        + b"\x00\x01\x00\x00\x00"
        + zlib.compress(document.encode("utf-8"), 9)
    )
    kept = bytearray(_PNG_SIGNATURE)
    for start, kind, body, end in _chunks(png):
        if kind == b"iTXt" and body.startswith(KEYWORD.encode("latin-1") + b"\x00"):
            continue
        if kind == b"IEND":
            kept += _chunk(b"iTXt", data)
        kept += png[start:end]
    return bytes(kept)


def _png_document(png: bytes) -> str | None:
    for _, kind, body, _ in _chunks(png):
        if kind != b"iTXt":
            continue
        keyword, _, rest = body.partition(b"\x00")
        if keyword.decode("latin-1") != KEYWORD or len(rest) < 2:
            continue
        compressed = rest[0] == 1
        # skip the method, then the language and translated keyword
        text = rest[2:].split(b"\x00", 2)[-1]
        return (zlib.decompress(text) if compressed else text).decode("utf-8")
    return None


def page_document(html: str) -> str | None:
    """The JSON of the document a page carries, as its script holds it, or None.

    The one place a page's document is found: :func:`carried_document`, the
    editor's ``project_from_html`` and ``verify:render`` all read it here.
    """
    # the page's script holds JSON, its < > & written as \u escapes
    match = _HTML_PROJECT.search(html)
    return match.group(1) if match else None


def carried_document(path: Path) -> dict | None:
    """The document an exported SVG, PNG or page carries, or None."""
    suffix = path.suffix.casefold()
    try:
        if suffix == ".png":
            raw = _png_document(path.read_bytes())
        else:
            text = path.read_text(encoding="utf-8")
            if suffix == ".svg":
                match = _SVG_METADATA.search(text)
                raw = unescape(match.group(1)) if match else None
            else:
                raw = page_document(text)
    except (OSError, UnicodeDecodeError, ValueError, zlib.error):
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
