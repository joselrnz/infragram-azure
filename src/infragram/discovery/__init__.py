"""Drawing an estate that already exists, read live from where it runs.

``azcli`` reads a snapshot through the Azure CLI's own signed-in session;
``azure`` turns a snapshot into a :class:`~infragram.patterns.Blueprint`;
``arm_types`` says which node class draws each Azure resource type.
"""

from __future__ import annotations

from .azcli import SNAPSHOT_FORMAT, AzureCliError, AzureSession, load_snapshot, save_snapshot
from .azure import VIEWS, ImportOptions, ImportSummary, blueprint

__all__ = [
    "SNAPSHOT_FORMAT",
    "VIEWS",
    "AzureCliError",
    "AzureSession",
    "ImportOptions",
    "ImportSummary",
    "blueprint",
    "load_snapshot",
    "save_snapshot",
]
