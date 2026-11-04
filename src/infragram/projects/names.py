"""The closed vocabularies a project document is written in.

Each one is a ``Literal``, so an unknown value is refused when the document is
validated rather than found later by a renderer that has no rule for it.
"""

from __future__ import annotations

import re
from typing import Literal

__all__ = [
    "AudienceName",
    "DetailName",
    "DisplayName",
    "LayerKind",
    "ProjectKind",
    "SizeName",
]


SizeName = Literal[
    "doc-inline",
    "doc-wide",
    "slide-16x9",
    "slide-4x3",
    "social-og",
    "social-square",
    "print-a4-landscape",
    "print-letter-landscape",
    "fit",
]


DetailName = Literal["faithful", "balanced", "simplified"]


AudienceName = Literal["engineer", "mixed", "executive"]


#: How a component draws. ``card`` is a titled box with the icon in a lane
#: beside the text; ``icon`` is the bare vendor mark with its caption beneath,
#: the way the vendors' own reference architectures are drawn.
DisplayName = Literal["card", "icon"]


_NAMESPACED_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?::[a-z0-9]+(?:-[a-z0-9]+)*)?$")


ProjectKind = Literal["single-cloud", "multicloud", "platform", "hybrid"]


LayerKind = Literal["provider", "platform", "on-prem", "logical"]
