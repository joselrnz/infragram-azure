"""infragram - shared models and helpers for the infragram tooling.

This package is the developer-side library and CLI. The product it builds and
verifies is the agent skill under ``skills/infragram-architect/``.

Layout (``src/infragram/``):

- :mod:`infragram.models` - frozen domain models (Provider, ProviderIcon, Service)
- :mod:`infragram.themes` - Theme, heading treatment, theme files, hex colours
- :mod:`infragram.registries` - provider skin catalog + plugin manifests
- :mod:`infragram.verification` - SVG safety, extraction, validation patterns
- :mod:`infragram.utils` - small cross-cutting helpers
- :mod:`infragram.cli` - the ``infragram`` command line entry point

Each subpackage carries a README.md describing what it owns and why.

The standalone gate scripts under ``scripts/`` share ``scripts/lib/gatelib.py``
for their own reporting and subprocess helpers; nothing there is part of
this package.
"""

from .catalog import (
    EXPECTED_CATEGORY_LABELS,
    CatalogComponent,
    Category,
    CategoryCoverage,
    CategoryRegistry,
    ProviderCategoryMappings,
    ProviderDescriptor,
    ProviderRegistry,
    UnknownCategoryError,
    load_composite_catalog,
    load_default_category_registry,
    load_default_provider_mappings,
    load_default_provider_registry,
)
from .models import SERVICE_ROLES, Provider, ProviderIcon, Service

# ComponentRef belongs to the topology model; it was reachable through
# projects only because that module imported it.
from .models.topology import ComponentRef
from .projects import CloudProject, Layer, Presentation, ProviderSelection
from .registries import load_catalog
from .themes import THEME_ROLES, Theme
from .utils import slugify
from .verification import HEX_COLOR, SHA256, SLUG, inner_body, view_box

__all__ = [
    "EXPECTED_CATEGORY_LABELS",
    "Category",
    "CategoryCoverage",
    "CategoryRegistry",
    "CatalogComponent",
    "CloudProject",
    "ComponentRef",
    "HEX_COLOR",
    "Layer",
    "Provider",
    "ProviderCategoryMappings",
    "ProviderDescriptor",
    "ProviderIcon",
    "ProviderRegistry",
    "ProviderSelection",
    "Presentation",
    "SERVICE_ROLES",
    "SHA256",
    "SLUG",
    "Service",
    "THEME_ROLES",
    "Theme",
    "UnknownCategoryError",
    "inner_body",
    "load_catalog",
    "load_composite_catalog",
    "load_default_category_registry",
    "load_default_provider_mappings",
    "load_default_provider_registry",
    "slugify",
    "view_box",
]
