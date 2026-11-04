"""What a document says about itself, read from what it holds.

The libraries a diagram draws from and the kind of diagram it is are derived
from its elements, in the order they were first used, rather than asked of the
author -- who has already said it by choosing the classes.
"""

from __future__ import annotations

from collections.abc import Sequence

from ..models.topology import TopologyElement
from ..projects import ProjectKind
from .ids import NON_PROVIDER_COLLECTIONS, _registered_providers

__all__ = ["infer_kind", "infer_providers"]


#: Shared-only Azure edition diagrams use its primary installed library.
NEUTRAL_LIBRARY = "azure"


def infer_providers(root: TopologyElement) -> tuple[str, ...]:
    """Installed libraries the tree draws from, in order of first use.

    A node names its library through its component or collection; a frame
    names one through its gallery group (an AWS VPC frame means AWS). A tree
    made only of shared primitives and generic frames falls back to
    :data:`NEUTRAL_LIBRARY`.
    """
    providers = _registered_providers()
    seen: dict[str, None] = {}
    for element in root.walk():
        candidates = []
        if element.component is not None:
            candidates.append(element.component.provider)
        else:
            candidates.append(str(element.attributes.get("collection") or ""))
        candidates.append(str(element.attributes.get("editor_frame_group") or ""))
        for candidate in candidates:
            if candidate in providers and candidate not in NON_PROVIDER_COLLECTIONS:
                seen.setdefault(candidate, None)
    if not seen:
        # walk() always yields the root itself, so a tree is never empty here
        fallback = NEUTRAL_LIBRARY if NEUTRAL_LIBRARY in providers else next(iter(providers), None)
        if fallback is not None:
            seen[fallback] = None
    return tuple(seen)


def infer_kind(providers: Sequence[str]) -> ProjectKind:
    """The project kind the schema expects for this mix of libraries."""
    kinds = _registered_providers()
    cloud = [provider for provider in providers if kinds.get(provider) == "cloud"]
    other = [provider for provider in providers if kinds.get(provider) != "cloud"]
    if len(providers) == 1:
        return "single-cloud" if cloud else "platform"
    if cloud and other:
        return "hybrid"
    if cloud:
        return "multicloud"
    return "platform"
