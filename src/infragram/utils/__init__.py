"""Small cross-cutting helpers.

Kept separate from the domain packages so nothing in models/, themes/, or
registries/ has to import a sibling just for a formatting utility.
"""

from .text import SLUG, slugify

__all__ = ["SLUG", "slugify"]
