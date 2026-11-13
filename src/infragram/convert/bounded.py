"""Compressed parts of a file somebody else wrote, expanded within a limit.

A ``.vsdx`` is a zip and a draw.io page is usually deflated, so a file of a
few kilobytes can claim to expand to gigabytes. No real diagram comes near
the limits here; a part that would pass one is refused before it is read
whole, rather than left to exhaust the memory of whoever opened it.
"""

from __future__ import annotations

import zipfile
import zlib

__all__ = ["ARCHIVE_LIMIT", "PART_LIMIT", "check_archive", "inflate", "read_part"]

#: The most one part (a page, a zip member) may expand to.
PART_LIMIT = 64 * 1024 * 1024
#: The most a whole archive's members may add up to.
ARCHIVE_LIMIT = 256 * 1024 * 1024


def inflate(data: bytes, wbits: int, error: type[Exception], limit: int | None = None) -> bytes:
    """*data* decompressed, or *error* when it expands past *limit*.

    Raises :class:`zlib.error` for data that is not deflated, as
    :func:`zlib.decompress` does, so a caller trying several formats can.
    """
    limit = PART_LIMIT if limit is None else limit
    stream = zlib.decompressobj(wbits)
    out = stream.decompress(data, limit)
    if stream.unconsumed_tail:
        raise error(f"a compressed part expands past {limit // (1024 * 1024)} MB")
    out += stream.flush()
    if len(out) > limit:
        raise error(f"a compressed part expands past {limit // (1024 * 1024)} MB")
    if not stream.eof:
        # what zlib.decompress says of a stream cut short, rather than
        # handing back half a page to fail later as broken XML
        raise zlib.error("Error -5 while decompressing data: incomplete or truncated stream")
    return out


def check_archive(archive: zipfile.ZipFile, error: type[Exception]) -> None:
    """Refuse an archive whose members claim more than :data:`ARCHIVE_LIMIT`."""
    total = sum(info.file_size for info in archive.infolist())
    if total > ARCHIVE_LIMIT:
        raise error(f"the archive expands past {ARCHIVE_LIMIT // (1024 * 1024)} MB")


def read_part(
    archive: zipfile.ZipFile, name: str, error: type[Exception], limit: int | None = None
) -> bytes:
    """One member of *archive*, read no further than *limit* bytes.

    The size a zip records can lie, so the read itself stops at the limit too.
    """
    limit = PART_LIMIT if limit is None else limit
    info = archive.getinfo(name)
    if info.file_size > limit:
        raise error(f"{name} expands past {limit // (1024 * 1024)} MB")
    with archive.open(info) as part:
        data = part.read(limit + 1)
    if len(data) > limit:
        raise error(f"{name} expands past {limit // (1024 * 1024)} MB")
    return data
