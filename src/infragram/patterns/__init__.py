"""Patterns: reusable pieces of infrastructure, and the Blueprint that
assembles them into a diagram.

Composing as code (:mod:`infragram.compose`) removes coordinates. Patterns
remove repetition: two Availability Zones built from one recipe, a row of
guardrails, a site's edge and the circuit it lands on, each a class with a
name, the elements it made and the parts a caller wires up. A
:class:`Blueprint` holds elements, patterns and links, validates as it goes,
and exports deterministically, alone or many at once.

::

    from infragram.patterns import Blueprint, Pattern

Azure, Kubernetes and Databricks diagrams use these shared authoring classes.
Provider-specific patterns from other editions require their own libraries.

Everything here builds on the generated node classes; nothing names an SVG.
"""

from __future__ import annotations

from .base import Pattern, PatternError
from .blueprint import Blueprint

__all__ = ["Blueprint", "Pattern", "PatternError"]
