"""A small file that claims to expand to gigabytes is refused, not read.

A ``.vsdx`` is a zip and a draw.io page is usually deflated: either can be a
decompression bomb. convert/bounded.py caps every part and the whole archive.
"""

from __future__ import annotations

import base64
import io
import zipfile
import zlib
from pathlib import Path

import pytest

from infragram.convert import bounded
from infragram.convert.drawio import DrawioError, read_drawio
from infragram.convert.visio import VisioError, read_visio


def test_inflate_stops_at_the_limit_and_passes_what_fits() -> None:
    small = zlib.compress(b"<mxGraphModel/>")
    assert bounded.inflate(small, 15, DrawioError) == b"<mxGraphModel/>"
    bomb = zlib.compress(b"\0" * (2 * 1024 * 1024))
    with pytest.raises(DrawioError, match="expands past"):
        bounded.inflate(bomb, 15, DrawioError, limit=1024 * 1024)
    with pytest.raises(zlib.error):
        bounded.inflate(b"not deflated", 15, DrawioError)


def test_a_stream_cut_short_is_refused_as_zlib_refuses_it() -> None:
    whole = zlib.compress(b"<mxGraphModel>" + b"<mxCell/>" * 200 + b"</mxGraphModel>")
    with pytest.raises(zlib.error, match="truncated"):
        bounded.inflate(whole[: len(whole) // 2], 15, DrawioError)
    raw = zlib.compressobj(9, zlib.DEFLATED, -15)
    page = raw.compress(b"<mxGraphModel/>" * 100) + raw.flush()
    assert bounded.inflate(page, -15, DrawioError) == b"<mxGraphModel/>" * 100
    with pytest.raises(zlib.error):
        bounded.inflate(page[:-4], -15, DrawioError)


def test_a_deflated_drawio_page_that_expands_too_far_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bounded, "PART_LIMIT", 1024 * 1024)
    raw = zlib.compressobj(9, zlib.DEFLATED, -15)
    page = raw.compress(b" " * (4 * 1024 * 1024)) + raw.flush()
    path = tmp_path / "bomb.drawio"
    path.write_text(
        f'<mxfile><diagram id="a" name="A">{base64.b64encode(page).decode()}</diagram></mxfile>',
        encoding="utf-8",
    )
    with pytest.raises(DrawioError, match="expands past"):
        read_drawio(path)


def test_a_vsdx_whose_members_claim_too_much_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bounded, "ARCHIVE_LIMIT", 1024 * 1024)
    path = tmp_path / "bomb.vsdx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("visio/pages/pages.xml", b"<Pages/>" + b" " * (2 * 1024 * 1024))
    with pytest.raises(VisioError, match="expands past"):
        read_visio(path)


def test_a_zip_member_is_read_no_further_than_the_limit() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("big.xml", b"x" * 4096)
    with zipfile.ZipFile(buffer) as archive:
        assert bounded.read_part(archive, "big.xml", VisioError) == b"x" * 4096
        with pytest.raises(VisioError, match="big.xml expands past"):
            bounded.read_part(archive, "big.xml", VisioError, limit=1024)
