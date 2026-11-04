"""Where things live -- found, not counted.

Counting directories up from a module's own file (``parents[2]``) is fragile
in the worst way: move a file one level and it does not raise, it resolves
to the wrong directory and fails later with a confusing error about a
missing asset. This finds folders by what they hold instead, so depth does
not matter. Two folders matter:

- the **plugin** (:func:`plugin_root`): the folder holding
  ``.claude-plugin/plugin.json``, the skills and their assets. In a checkout
  it is the repository root; an agent's install is a copy of it; an installed wheel
  carries it beside the package as ``infragram/_plugin/``.
- the **checkout** (:func:`checkout_root`, :func:`repo_root`): the repository
  holding the plugin, tests and maintainer scripts. Only a
  checkout has one.

The ``INFRAGRAM_ASSETS`` override points an installed copy at any assets.
"""

from __future__ import annotations

import os
from functools import cache
from pathlib import Path

__all__ = [
    "MANIFEST",
    "MARKER",
    "bundled_plugin",
    "checkout_root",
    "plugin_root",
    "repo_root",
    "resolve_assets",
    "skill_assets",
    "skill_references",
    "skill_scripts",
]

#: The directory Claude Code's manifests live in: the plugin's own
#: ``plugin.json``, and a marketplace's ``marketplace.json``.
MARKER = ".claude-plugin"

#: The file that identifies the plugin folder.
MANIFEST = Path(MARKER) / "plugin.json"

#: The one skill every command, asset and reference belongs to.
SKILL = Path("skills") / "infragram-azure"

#: Point an installed copy at a checkout's assets.
ASSETS_ENV = "INFRAGRAM_ASSETS"


def _package_dir() -> Path:
    """The package directory (``infragram/``) -- found, not counted.

    A built wheel bundles the plugin beside the package, so this has to be
    ``infragram/`` however deep inside it this module sits. It is the
    outermost parent of this file that is still an importable package, which
    is the same answer wherever the module is moved to.
    """
    found = Path(__file__).resolve().parent
    for parent in found.parents:
        if not (parent / "__init__.py").is_file():
            break
        found = parent
    return found


def bundled_plugin(origin: Path | None = None) -> Path | None:
    """The plugin folder a built wheel carries beside the package
    (``infragram/_plugin``), or None where the package runs from a plugin
    folder (the source tree never holds a copy). *origin* is a module file
    of the package, for a test."""
    package_dir = origin.resolve().parent if origin else _package_dir()
    candidate = package_dir / "_plugin"
    return candidate if (candidate / MANIFEST).is_file() else None


@cache
def plugin_root(start: Path | None = None) -> Path:
    """The plugin folder: the one a wheel carries beside the package, else
    the folder above *start* (this file by default) holding
    ``.claude-plugin/plugin.json``."""
    bundled = bundled_plugin(start)
    if bundled is not None:
        return bundled
    origin = (start or Path(__file__)).resolve()
    for parent in (origin, *origin.parents):
        if (parent / MANIFEST).is_file():
            return parent
    raise RuntimeError(
        f"no {MANIFEST.as_posix()} found above {origin}; set {ASSETS_ENV} to the "
        "skill assets directory when running outside a plugin folder"
    )


def resolve_assets(origin: Path | None = None, override: str | None = None) -> Path:
    """Where the skill's assets are, in order: an explicit ``INFRAGRAM_ASSETS``
    override, then the plugin folder's skill (the wheel's copy, or the folder
    above the package)."""
    if override:
        return Path(override).resolve()
    return plugin_root(origin) / SKILL / "assets"


@cache
def skill_assets() -> Path:
    """The shipped skill's asset directory: icons, fonts, themes, catalog,
    templates -- from the override, the wheel, or the plugin folder."""
    return resolve_assets(None, os.environ.get(ASSETS_ENV))


@cache
def checkout_root(package: Path | None = None) -> Path | None:
    """The repository this package (or *package*) was imported from, or None
    for any other copy: an agent's install, an installed wheel.

    A checkout holds the plugin folder whose ``src/`` is this very package,
    the tests, and the maintainer scripts. A folder with a
    ``.claude-plugin/`` alone is not enough: a wheel installed anywhere under
    another plugin's folder has one above it too.
    """
    package = (package or _package_dir()).resolve()
    for parent in package.parents:
        if (parent / MANIFEST).is_file():
            inside = parent / "src" / package.name
            if not (inside.is_dir() and inside.resolve() == package):
                return None
            # Azure keeps the plugin at the root. The bundled plugin has
            # scripts/export for export:azure, but no tests or gate scripts.
            if (parent / "tests").is_dir() and (parent / "scripts" / "verify").is_dir():
                return parent
            above = parent.parent
            if (above / MARKER / "marketplace.json").is_file() and (above / "scripts").is_dir():
                return above
            return None
    return None


@cache
def repo_root() -> Path:
    """The repository around the plugin: tests, fixtures, maintainer
    scripts. Only a checkout has one."""
    root = checkout_root()
    if root is None:
        raise RuntimeError("this copy of infragram is not a checkout of the repository")
    return root


@cache
def skill_scripts() -> Path:
    """The shipped skill's scripts: the launcher and the stdlib checker."""
    return plugin_root() / SKILL / "scripts"


@cache
def skill_references() -> Path:
    """The shipped skill's references (the shared-primitive gallery is read
    from there at runtime)."""
    return plugin_root() / SKILL / "references"
