"""A resource glyph says which service it belongs to.

A vendor may ship two kinds of artwork: a service icon that stands for the
service, and a resource glyph placed inside that service's group box. Their
classes sit side by side in the same module and read alike, and picking the
wrong one produces a diagram that looks plausible and is wrong. So every
resource glyph whose service also ships must name that service in its
docstring and say to use it instead.

Neither library this edition ships files artwork in tiers -- the Azure deck
and the Kubernetes set are services throughout -- so the rule is held here
as a floor: no confusable pair exists today, and the generator's docstring
rule still runs over every class, ready for a deck that does.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from pathlib import Path

from infragram.catalog import tiers

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
VENDORS = ROOT / "skills/infragram-azure/assets/icons/vendors"
LIBRARIES = ("azure", "kubernetes")


def _resource_pairs(icons: list[dict]) -> dict[str, str]:
    """Resource id -> service id, for every pair a caller could confuse."""
    services = tiers.service_names(icons)
    pairs = {}
    for entry in icons:
        service = tiers.parent_service(entry, services)
        if service is not None:
            pairs[str(entry.get("id") or "")] = str(service.get("id") or "")
    return pairs


def _pairs() -> list[tuple[str, str, str]]:
    """(provider, resource id, service id) for every confusable pair, asked of
    the one module that owns the rule."""
    found = []
    for catalog in sorted(VENDORS.glob("*/catalog.json")):
        icons = json.loads(catalog.read_text(encoding="utf-8")).get("icons") or []
        for resource, service in _resource_pairs(icons).items():
            found.append((catalog.parent.name, resource, service))
    return found


def test_no_shipped_library_files_artwork_in_tiers() -> None:
    """If this changes, artwork was imported that ships resource glyphs, and
    the docstring rule below starts doing real work."""
    assert _pairs() == []
    for library in LIBRARIES:
        icons = json.loads((VENDORS / library / "catalog.json").read_text(encoding="utf-8"))[
            "icons"
        ]
        assert {icon.get("tier", "service") for icon in icons} == {"service"}, library


def test_every_generated_resource_class_names_its_service() -> None:
    """The docstring is where a caller meets the choice, so it carries it."""
    known = {p[1] for p in _pairs()}
    missing = []
    for library in LIBRARIES:
        package = importlib.import_module(f"infragram.nodes.{library}")
        for module_info in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"infragram.nodes.{library}.{module_info.name}")
            for name in dir(module):
                cls = getattr(module, name)
                icon = getattr(cls, "ICON", None)
                if not isinstance(icon, str) or icon not in known:
                    continue
                doc = cls.__doc__ or ""
                if "Resource glyph" not in doc or "For the service use" not in doc:
                    missing.append(f"{library}.{module_info.name}.{name}")
    assert missing == [], missing[:10]
