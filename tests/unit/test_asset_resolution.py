"""Where a copy finds the plugin and its assets: the override, the plugin folder
a wheel carries, then the plugin folder above the package; and which copy is a
checkout of the repository."""

from __future__ import annotations

from pathlib import Path

import pytest

import infragram
from infragram.paths import (
    MANIFEST,
    bundled_plugin,
    checkout_root,
    plugin_root,
    repo_root,
    resolve_assets,
    skill_assets,
    skill_scripts,
)


def _plugin(folder: Path) -> Path:
    (folder / MANIFEST).parent.mkdir(parents=True)
    (folder / MANIFEST).write_text('{"name": "infragram-azure"}', encoding="utf-8")
    return folder


def test_a_checkout_reads_the_plugin_folder() -> None:
    assets = skill_assets()
    assert assets.name == "assets" and assets.parent.name == "infragram-azure"
    assert plugin_root() == repo_root() and (plugin_root() / MANIFEST).is_file()
    assert bundled_plugin() is None, "the source tree never holds a bundled copy"


def test_an_override_wins(tmp_path: Path) -> None:
    assert resolve_assets(None, str(tmp_path)) == tmp_path.resolve()


def test_a_wheel_finds_the_plugin_beside_the_package(tmp_path: Path) -> None:
    site = tmp_path / "site-packages" / "infragram"
    _plugin(site / "_plugin")
    origin = site / "paths.py"
    origin.write_text("", encoding="utf-8")
    assert bundled_plugin(origin) == site / "_plugin"
    assert (
        resolve_assets(origin, None) == site / "_plugin" / "skills" / "infragram-azure" / "assets"
    )


def test_an_agents_copy_of_the_plugin_reads_its_own_folder(tmp_path: Path) -> None:
    copy = _plugin(tmp_path / "cache" / "infragram-azure" / "0.5.0")
    origin = copy / "src" / "infragram" / "paths" / "__init__.py"
    origin.parent.mkdir(parents=True)
    origin.write_text("", encoding="utf-8")
    assert resolve_assets(origin, None) == copy / "skills" / "infragram-azure" / "assets"


def test_without_a_plugin_folder_the_error_names_the_override(tmp_path: Path) -> None:
    origin = tmp_path / "elsewhere" / "infragram" / "paths.py"
    origin.parent.mkdir(parents=True)
    origin.write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="INFRAGRAM_ASSETS"):
        resolve_assets(origin, None)


def test_a_checkout_runs_its_own_checker() -> None:
    assert (skill_scripts() / "project_check.py").is_file()
    assert (skill_scripts() / "infragram.py").is_file(), (
        "the hook and agent need the skill launcher"
    )
    assert skill_scripts().parent.name == "infragram-azure"


def test_a_checkout_is_the_repository_around_this_very_package() -> None:
    root = checkout_root()
    assert root is not None and root == repo_root()
    assert (root / ".claude-plugin" / "marketplace.json").is_file() and (root / "scripts").is_dir()
    assert (root / "src" / "infragram").resolve() == Path(infragram.__file__).resolve().parent


def test_an_agents_copy_is_not_a_checkout(tmp_path: Path) -> None:
    copy = _plugin(tmp_path / "cache" / "infragram-azure" / "0.5.0")
    package = copy / "src" / "infragram"
    package.mkdir(parents=True)
    assert checkout_root(package) is None


def test_a_wheel_installed_under_another_plugin_is_not_a_checkout(tmp_path: Path) -> None:
    """The manifest alone would claim it: a venv inside someone else's plugin
    folder has a ``.claude-plugin/`` above the package too."""
    host = _plugin(tmp_path / "another-plugin")
    package = host / ".venv" / "Lib" / "site-packages" / "infragram"
    package.mkdir(parents=True)
    assert checkout_root(package) is None


def test_a_bundled_azure_launcher_does_not_make_an_installed_plugin_a_checkout(
    tmp_path: Path,
) -> None:
    copy = _plugin(tmp_path / "site-packages" / "infragram" / "_plugin")
    package = copy / "src" / "infragram"
    package.mkdir(parents=True)
    (copy / "scripts" / "export").mkdir(parents=True)
    (copy / "scripts" / "export" / "azure.py").write_text("", encoding="utf-8")
    assert checkout_root(package) is None


def test_a_flat_checkout_resolves_its_own_maintainer_scripts(tmp_path: Path) -> None:
    copy = _plugin(tmp_path / "azure-checkout")
    package = copy / "src" / "infragram"
    package.mkdir(parents=True)
    (copy / "tests").mkdir()
    (copy / "scripts" / "verify").mkdir(parents=True)
    assert checkout_root(package) == copy
