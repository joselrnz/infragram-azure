"""Topology as code: a node-class tree in, a valid project out, no coordinates.

The editor document (:class:`~infragram.projects.CloudProject`) is what every
export renders. Authoring one by hand means spelling provider-qualified
component ids and placing every card. This package closes that gap for
scripts: build the estate with the generated node classes and frames, and
:func:`to_project` supplies everything else from the catalogs.

:mod:`.errors` holds the one error, :mod:`.ids` the qualification against the
installed catalogs, :mod:`.inference` what a document says about itself, and
:mod:`.document` the assembly. :mod:`infragram.author` is the friendlier way
to write the same tree.
"""

from __future__ import annotations

from .document import export, to_project, undrawn_root
from .errors import ComposeError
from .ids import qualify, shared_service_ids
from .inference import infer_kind, infer_providers

__all__ = [
    "ComposeError",
    "export",
    "infer_kind",
    "infer_providers",
    "qualify",
    "shared_service_ids",
    "to_project",
    "undrawn_root",
]
