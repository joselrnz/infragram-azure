"""XML from a file somebody else wrote, parsed without entity declarations.

draw.io and Visio files are XML a reader hands the importer. Neither format
declares an entity, so an ENTITY in one is a mistake or an attack: entities
that expand until memory runs out, or that reach outside the file. They live
in a document type's internal subset, the ``[...]`` part of a DOCTYPE, so
that is refused as well. A DOCTYPE that only names a public DTD stays: draw.io
writes one at the top of every SVG it exports, and the standard library never
fetches it. The standard library resolves no external entity and Python's
expat bounds expansion; refusing the declarations outright leaves nothing for
either to handle.

The text search reads bytes as UTF-8, so a document in UTF-16, UTF-32 or
another encoding expat accepts would slip past it. A first pass through
expat itself, which reads the encoding the same way the real parse does,
stops at the first declaration whatever the bytes are.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from xml.parsers import expat

__all__ = ["parse"]

#: An entity declaration anywhere, or a document type with an internal subset.
_DECLARATION = re.compile(r"<!\s*ENTITY|<!\s*DOCTYPE[^>\[]*\[", re.IGNORECASE)


_REFUSAL = (
    "an ENTITY declaration or a DOCTYPE with an internal subset, "
    "which a draw.io or Visio file never carries"
)


class _Declared(Exception):
    """Raised from an expat handler at the first declaration it reports."""


def _refuse(*_args: object) -> None:
    raise _Declared


def _refuse_subset(
    _name: str, _system: str | None, _public: str | None, has_internal_subset: int
) -> None:
    if has_internal_subset:
        raise _Declared


def _declares(data: str | bytes) -> bool:
    """True when expat, reading the document's own encoding, meets a declaration."""
    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = _refuse_subset
    parser.EntityDeclHandler = _refuse
    parser.UnparsedEntityDeclHandler = _refuse
    try:
        parser.Parse(data, True)
    except _Declared:
        return True
    except (expat.ExpatError, ValueError, LookupError):
        return False  # bad XML: the real parse reports it as ET.ParseError
    return False


def parse(data: str | bytes) -> ET.Element:
    """The document's root element; ``ET.ParseError`` for a declaration, as for bad XML."""
    text = data if isinstance(data, str) else data.decode("utf-8", errors="replace")
    if _DECLARATION.search(text) or _declares(data):
        raise ET.ParseError(_REFUSAL)
    return ET.fromstring(data)  # noqa: S314 - declarations refused above
