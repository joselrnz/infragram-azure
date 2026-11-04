"""Portable cloud-project templates shared by editors and exporters.

The template stores intent, not rendered coordinates.  A provider-aware
renderer turns the topology into a scene, so browser editing, CLI rendering,
and future hosted exports all consume the same versioned document.

:mod:`.names` holds the closed vocabularies, :mod:`.parts` the pieces a
document is made of beside its topology, and :mod:`.document` the document
itself.
"""

from __future__ import annotations

from .document import CloudProject
from .names import (
    AudienceName,
    DetailName,
    DisplayName,
    LayerKind,
    ProjectKind,
    SizeName,
)
from .parts import Layer, Presentation, ProviderSelection, View, ViewSelector

__all__ = [
    "AudienceName",
    "CloudProject",
    "DetailName",
    "DisplayName",
    "Layer",
    "LayerKind",
    "Presentation",
    "ProjectKind",
    "ProviderSelection",
    "SizeName",
    "View",
    "ViewSelector",
]
