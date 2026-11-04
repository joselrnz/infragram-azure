"""Text helpers shared across builders and registries.

One slug algorithm for the whole package. Element ids, project slugs, pattern
part names and catalog ids all used to have their own copy, and the copies
had drifted: one kept non-ASCII letters, one lower-cased instead of
case-folding, one matched the pattern with ``match`` instead of
``fullmatch``. Every id a document carries is compared across renders and
across machines, so they all go through here now.
"""

from __future__ import annotations

import re

#: Lowercase kebab-case identifier: provider, icon, category and element ids,
#: project slugs. The one pattern every validator checks against.
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(value: str, *, fallback: str = "") -> str:
    """Lowercase kebab-case form of *value*, matching :data:`SLUG`.

    Case-folded, then every run of anything outside ``a-z0-9`` becomes one
    hyphen. Letters outside ASCII are dropped rather than kept, so a name
    with an accent slugs the same everywhere and the result always satisfies
    :data:`SLUG`. ``fallback`` is what a value with nothing usable in it
    becomes (``"node"`` for an element id, ``"diagram"`` for a slug).
    """
    slug = _NON_SLUG.sub("-", value.strip().casefold()).strip("-")
    return slug or fallback


def markdown_cell(text: str, *, squeeze: bool = False) -> str:
    """*text* as a Markdown table cell holds it: a pipe would end the cell and
    a newline the row, so the pipe is escaped and the newline becomes a space.

    ``squeeze`` folds every run of whitespace, tabs and carriage returns
    included, into one space and trims the ends: a change report quotes
    names a person typed, where stray whitespace is noise.
    """
    if squeeze:
        return " ".join(text.split()).replace("|", "\\|")
    return text.replace("|", "\\|").replace("\n", " ")


__all__ = ["SLUG", "markdown_cell", "slugify"]
