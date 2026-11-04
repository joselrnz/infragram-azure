"""Registries: the provider skin catalog and the plugin manifest registry."""

from .catalog import load_catalog
from .manifests import (
    MANIFEST_PATHS,
    SEMVER,
    PackageVersionError,
    atomic_write_text,
    bump,
    parse_version,
    read_manifest,
)

__all__ = [
    "MANIFEST_PATHS",
    "PackageVersionError",
    "SEMVER",
    "atomic_write_text",
    "bump",
    "load_catalog",
    "parse_version",
    "read_manifest",
]
