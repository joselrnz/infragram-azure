"""An exported picture carries the document it was drawn from.

A PNG pasted into a wiki was a dead end: changing the diagram meant finding
its ``.infragram.json``. Every SVG and PNG an export writes now holds the
document (``exports/carry.py``), ``export:project picture.png`` redraws it,
and ``--no-embed`` leaves the picture bare.
"""

from __future__ import annotations

import json
import struct
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

from infragram.exports.carry import carried_document, embed_in_png, embed_in_svg

DOCUMENT = json.dumps({"schema_version": 1, "title": 'A <b> & "c" é', "nested": {"x": [1, 2]}})


def _png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    pixels = zlib.compress(b"\x00\xff\xff\xff")
    return (
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", pixels) + chunk(b"IEND", b"")
    )


def test_an_svg_carries_its_document_and_stays_well_formed(tmp_path: Path) -> None:
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><rect width="1" height="1"/></svg>'
    once = embed_in_svg(svg, DOCUMENT)
    ET.fromstring(once)
    assert "<b>" not in once and "&amp; " not in once.split("<metadata")[1], (
        "no markup, even unescaped"
    )
    twice = embed_in_svg(once, DOCUMENT)
    assert twice.count("<metadata") == 1, "embedding again replaces the copy"
    path = tmp_path / "picture.svg"
    path.write_text(twice, encoding="utf-8")
    assert carried_document(path) == json.loads(DOCUMENT)


def test_a_png_carries_its_document_in_a_text_chunk(tmp_path: Path) -> None:
    png = embed_in_png(embed_in_png(_png(), DOCUMENT), DOCUMENT)
    assert png.count(b"iTXtinfragram") == 1
    assert png.endswith(b"IEND\xaeB`\x82"), "IEND stays last"
    path = tmp_path / "picture.png"
    path.write_bytes(png)
    assert carried_document(path) == json.loads(DOCUMENT)


def test_a_bare_picture_carries_nothing(tmp_path: Path) -> None:
    (tmp_path / "bare.png").write_bytes(_png())
    (tmp_path / "bare.svg").write_text("<svg/>", encoding="utf-8")
    assert carried_document(tmp_path / "bare.png") is None
    assert carried_document(tmp_path / "bare.svg") is None


def test_export_project_redraws_from_a_picture(tmp_path: Path, capsys) -> None:
    from infragram.cli.user.export_project import main
    from infragram.paths import repo_root

    template = (
        repo_root() / "skills/infragram-azure/assets/templates/cloud/azure-api.infragram.json"
    )
    first = tmp_path / "first"
    assert main([str(template), "--formats", "svg", "--output-dir", str(first)]) == 0
    picture = next(first.glob("*.svg"))
    carried = carried_document(picture)
    assert (
        carried is not None and carried["slug"] == json.loads(template.read_text("utf-8"))["slug"]
    )
    second = tmp_path / "second"
    assert main([str(picture), "--formats", "svg", "--output-dir", str(second)]) == 0
    assert carried_document(next(second.glob("*.svg"))) == carried
    bare = tmp_path / "bare"
    assert main([str(template), "--formats", "svg", "--no-embed", "--output-dir", str(bare)]) == 0
    assert carried_document(next(bare.glob("*.svg"))) is None
    capsys.readouterr()
    assert main([str(next(bare.glob("*.svg"))), "--output-dir", str(tmp_path / "x")]) == 2
    assert "carries no document" in capsys.readouterr().err
