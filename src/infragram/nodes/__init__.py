"""Service nodes as classes, categorised the way each vendor categorises them.

A build script names a service; it never names an SVG::

    from infragram.nodes import Group
    from infragram.nodes.azure import compute, networking

    vnet = Group("Hub VNet", "vnet", role="hub")
    vnet >> networking.Firewalls("Azure Firewall", "egress")
    vnet >> compute.VirtualMachine("Jump box", "operator access")

Each class carries its own artwork through the inheritance chain -- vendor
package, category module, leaf class -- so one diagram can mix Azure service
icons with brand logos and each still resolves against its own catalog.

Everything under a vendor package is generated from ``catalog.json`` by
``scripts/tools/generate-nodes.py`` and committed; only :mod:`._base` is
hand-written. A new icon becomes a new class by rerunning the generator.

``>>`` nests and returns the child, so chains and branches both read as the
shape they build, to whatever depth::

    region >> zone >> subnet >> host
"""

from __future__ import annotations

from ._base import Box, Element, Frame, Group, reset_ids

__all__ = ["Box", "Element", "Frame", "Group", "reset_ids"]
