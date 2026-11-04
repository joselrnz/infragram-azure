"""The one error composing a document raises."""

from __future__ import annotations

__all__ = ["ComposeError"]


class ComposeError(ValueError):
    """A tree cannot become a project: an unknown service, an empty estate."""
