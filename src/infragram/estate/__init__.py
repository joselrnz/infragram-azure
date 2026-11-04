"""An existing estate into a diagram: what Terraform or a cloud says is there.

Three readers fill one :class:`Estate`, in Terraform's own terms:

- a configuration's files (:func:`infragram.terraform.readconfig.read_configuration`);
- a plan or a state (:func:`infragram.terraform.readstate.read_show_json`);
- a live estate, read-only, through the provider's CLI (:mod:`.discover`).

:func:`draw` places what it holds into frames with the wires between them,
and :func:`write_spec` writes that as a diagram file ``infragram compose``
draws, and a person edits. ``references/terraform.md`` section 3 is the
method.
"""

from __future__ import annotations

from .draw import Box, Card, Drawing, Wire, draw
from .model import Estate, Found
from .spec import SpecError, write_spec

__all__ = ["Box", "Card", "Drawing", "Estate", "Found", "SpecError", "Wire", "draw", "write_spec"]
