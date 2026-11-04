"""``azapi_resource`` written in the ``azurerm`` terms the drawing reads.

The Azure Verified Modules, and many a configuration since, declare Azure
resources through the AzAPI provider: one resource type, ``azapi_resource``,
whose ``type`` argument names the Azure resource (``Microsoft.Network/
virtualNetworks@2024-07-01``) and whose ``body`` holds its properties. The
Azure table's ``import.azapi`` section says, per Azure type, the ``azurerm``
type it is drawn as, the values its body gives in ``azurerm`` names, and the
argument its ``parent_id`` stands for, so a virtual network and its subnets
nest as ``azurerm_virtual_network`` and ``azurerm_subnet`` do. The resource
keeps its address; ``azapi_type`` keeps the Azure type it was read with.
"""

from __future__ import annotations

from typing import Any

from .model import Estate

__all__ = ["as_azurerm"]


def _dig(values: dict[str, Any], path: str) -> Any:
    current: Any = values
    for key in path.split("."):
        if isinstance(current, list) and len(current) == 1:
            current = current[0]
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def as_azurerm(estate: Estate) -> None:
    """Every ``azapi_resource`` of an Azure type the table knows, as the
    ``azurerm`` resource it is."""
    from ..terraform.mapping import load_mapping

    rules = load_mapping("azure").imports.azapi
    for found in estate.resources:
        if found.type != "azapi_resource":
            continue
        azure_type = str(found.values.get("type") or "").split("@", 1)[0]
        rule = rules.get(azure_type)
        if rule is None:
            continue
        found.type = rule.type
        found.values["azapi_type"] = azure_type
        for name, path in rule.values.items():
            value = _dig(found.values, path)
            if value is not None:
                found.values[name] = value
        if rule.parent and found.references.get("parent_id"):
            found.references.setdefault(rule.parent, list(found.references["parent_id"]))
