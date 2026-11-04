"""Turning a node's artwork into a provider-qualified component id.

A node written with the generated classes carries the library it came from and
the icon it draws. Qualification turns that into the ``provider:id`` pair a
document stores, and refuses an id no installed catalog ships -- with the
nearest real ones, because a typo here draws a blank card.
"""

from __future__ import annotations

import difflib
from functools import lru_cache

from ..catalog import (
    ARCHITECTURE_BOUNDARY_SPECS,
    CUSTOM_COMPONENT_SPECS,
    SHARED_PRIMITIVE_SPECS,
    load_default_provider_registry,
    load_provider_component_catalog,
)
from ..models.topology import ComponentRef, TopologyElement
from .errors import ComposeError

__all__ = ["NON_PROVIDER_COLLECTIONS", "qualify", "shared_service_ids"]


#: Collections that are artwork packs, not installable libraries.
NON_PROVIDER_COLLECTIONS = frozenset({"logos"})


@lru_cache(maxsize=1)
def shared_service_ids() -> frozenset[str]:
    """Every id the shared ``infragram`` library answers to."""
    return frozenset(
        {spec.service_id for spec in SHARED_PRIMITIVE_SPECS}
        | {spec[0] for spec in ARCHITECTURE_BOUNDARY_SPECS}
        | {spec[0] for spec in CUSTOM_COMPONENT_SPECS}
    )


@lru_cache(maxsize=32)
def _provider_service_ids(provider: str) -> frozenset[str]:
    return frozenset(
        component.service_id for component in load_provider_component_catalog(provider).components
    )


def _known_ids(provider: str) -> frozenset[str]:
    return shared_service_ids() if provider == "infragram" else _provider_service_ids(provider)


def _registered_providers() -> dict[str, str]:
    """provider id -> library kind (cloud, platform, on-prem)."""
    registry = load_default_provider_registry()
    return {provider_id: registry[provider_id].kind for provider_id in registry.by_id}


def qualify(root: TopologyElement) -> TopologyElement:
    """Write provider-qualified components onto a tree, in place.

    An element built from a generated node class knows its collection and
    icon id but not, as a document, its ``component``. Give it one whenever
    the collection is an installed library, then check every component in
    the tree names a real service of its provider.
    """
    providers = _registered_providers()
    for element in root.walk():
        if element.component is None:
            collection = str(element.attributes.get("collection") or "")
            icon = str(element.attributes.get("icon") or "")
            if collection and icon and (collection in providers or collection == "infragram"):
                element.component = ComponentRef(provider=collection, service_id=icon)
        if element.component is None:
            continue
        provider, service_id = element.component.provider, element.component.service_id
        if provider != "infragram" and provider not in providers:
            raise ComposeError(
                f"{element.name!r} uses provider {provider!r}, which is not an installed library"
            )
        known = _known_ids(provider)
        if service_id not in known:
            near = difflib.get_close_matches(service_id, sorted(known), n=3, cutoff=0.5)
            hint = f"; did you mean {', '.join(near)}?" if near else ""
            raise ComposeError(
                f"{element.name!r} names {provider}:{service_id}, which the {provider} "
                f"library does not ship{hint}"
            )
    return root
