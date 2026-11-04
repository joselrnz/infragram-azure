"""The one error every export path raises."""

from __future__ import annotations

__all__ = ["ExportError"]


class ExportError(ValueError):
    """A project or requested artifact cannot be exported safely."""
