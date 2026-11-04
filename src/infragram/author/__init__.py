"""Write a diagram the way you would describe it.

Nesting is containment and an arrow is a wire: the conventions of the
``diagrams`` library and of every text form in the field. A frame is a ``with``
block; whatever is written inside it belongs to it. Between two nodes ``>>``
draws a wire, ``<<`` one the other way, ``-`` one without arrowheads, and an
:class:`Edge` between them carries the label and the line kind.

:mod:`.edge` holds the wire, :mod:`.diagram` the block it is written in. Every
public name is re-exported here, so ``from infragram.author import Diagram``
reads and resolves as it always did.
"""

from __future__ import annotations

from .diagram import Diagram, Direction, latest_diagram, slugify
from .edge import Edge

__all__ = ["Diagram", "Direction", "Edge", "latest_diagram", "slugify"]
