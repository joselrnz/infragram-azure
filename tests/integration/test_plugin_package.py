"""Regression tests for plugin versioning and marketplace package verification."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from lib import gatelib

ROOT = gatelib.REPO_ROOT
VERIFY_SCRIPT = ROOT / "scripts/verify/plugin-package.py"
BUMP_SCRIPT = ROOT / "scripts/tools/bump-plugin-version.py"
PLUGIN_NAME = "infragram-azure"


def _load_script(name: str, path: Path):
    """Load a hyphenated gate script as a module."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VERIFY = _load_script("verify_plugin_package", VERIFY_SCRIPT)
BUMP = _load_script("bump_plugin_version", BUMP_SCRIPT)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def manifest(version: str, codex: bool = False) -> dict:
    payload = {
        "name": PLUGIN_NAME,
        "description": "Draw infrastructure diagrams.",
        "version": version,
        "author": {"name": "Infragram Azure"},
    }
    if codex:
        payload["skills"] = "./skills/"
    return payload


#: The plugin's four manifests, repository-relative, and which version each follows in set_versions.
MANIFESTS = {
    ".claude-plugin/plugin.json": "claude",
    ".codex-plugin/plugin.json": "codex",
    "plugin.json": "claude",
    "package.json": "claude",
}
PYPROJECT = Path("pyproject.toml")


def write_pyproject(root: Path, version: str) -> None:
    (root / PYPROJECT).parent.mkdir(parents=True, exist_ok=True)
    (root / PYPROJECT).write_text(
        '[build-system]\nrequires = ["hatchling"]\n\n'
        f'[project]\nname = "{PLUGIN_NAME}"\nversion = "{version}"\n\n'
        "[tool.ruff]\nline-length = 100\n",
        encoding="utf-8",
    )


def write_changelog(root: Path, version: str) -> None:
    (root / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## [{version}] - 2026-01-01\n\n- Something.\n\n## [0.0.1] - 2025-01-01\n\n- First.\n",
        encoding="utf-8",
    )


def write_marketplaces(folder: Path, source: str) -> None:
    """Claude Code's and Codex's marketplaces in *folder*, naming the plugin at *source*."""
    write_json(
        folder / ".claude-plugin/marketplace.json",
        {
            "name": PLUGIN_NAME,
            "plugins": [{"name": PLUGIN_NAME, "source": source}],
        },
    )
    write_json(
        folder / ".agents/plugins/marketplace.json",
        {
            "name": PLUGIN_NAME,
            "plugins": [
                {
                    "name": PLUGIN_NAME,
                    "source": {"source": "local", "path": source},
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": "Productivity",
                }
            ],
        },
    )


def seed_package(root: Path, version: str = "1.2.3") -> None:
    """The flat Azure plugin: each marketplace names its own root."""
    for relative, follows in MANIFESTS.items():
        write_json(root / relative, manifest(version, codex=follows == "codex"))
    write_pyproject(root, version)
    write_changelog(root, version)
    write_marketplaces(root, "./")
    skill = root / "skills" / PLUGIN_NAME / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(f"---\nname: {PLUGIN_NAME}\n---\n", encoding="utf-8")


@contextmanager
def package_repo() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        seed_package(root)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.name", "Package Test"], cwd=root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "package-test@example.invalid"],
            cwd=root,
            check=True,
        )
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "base package"], cwd=root, check=True)
        yield root


def set_versions(
    root: Path, claude: str, codex: str, pyproject: str | None = None, changelog: str | None = None
) -> None:
    """Set each versioned file; pyproject and the changelog follow the Claude
    manifest unless told otherwise, since a bump moves them together."""
    for relative, follows in MANIFESTS.items():
        version = codex if follows == "codex" else claude
        payload = json.loads((root / relative).read_text(encoding="utf-8"))
        payload["version"] = version
        write_json(root / relative, payload)
    write_pyproject(root, pyproject or claude)
    write_changelog(root, changelog or claude)


def expect_failure(label: str, errors: list[str], needle: str) -> None:
    if not any(needle in error for error in errors):
        raise AssertionError(f"{label}: expected {needle!r}, got {errors}")
    print(f"OK: {label} rejected")


def test_verifier() -> None:
    with package_repo() as root:
        set_versions(root, "1.2.4", "1.2.4")
        errors, manifests = VERIFY.collect_package_state(root, "HEAD")
        if errors:
            raise AssertionError(f"valid bump failed: {errors}")
        print("OK: valid synchronized bump accepted")
        # main() reuses the loaded manifests for its summary line rather than
        # re-reading (and potentially crashing on) the manifest file.
        if manifests["Claude"].get("version") != "1.2.4":
            raise AssertionError(
                f"collect_package_state did not return loaded manifests: {manifests}"
            )
        print("OK: verification returns the loaded manifest payloads")

    with package_repo() as root:
        write_changelog(root, "1.2.4")
        expect_failure(
            "a release entry without a bump",
            VERIFY.collect_package_state(root, "HEAD")[0],
            "must increase",
        )

    with package_repo() as root:
        set_versions(root, "1.2.4", "1.2.4", changelog="1.2.3")
        expect_failure(
            "a bump without a release entry",
            VERIFY.collect_package_state(root, "HEAD")[0],
            "without a new release entry",
        )

    with package_repo() as root:
        text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        (root / "CHANGELOG.md").write_text(
            text.replace("## [1.2.3]", "## [Unreleased]\n\n- Work in progress.\n\n## [1.2.3]", 1),
            encoding="utf-8",
        )
        errors, _ = VERIFY.collect_package_state(root, "HEAD")
        if errors:
            raise AssertionError(f"work under Unreleased asked for a bump: {errors}")
        print("OK: work between releases keeps the version")

    with package_repo() as root:
        set_versions(root, "1.2.4", "1.2.5")
        expect_failure(
            "mismatched manifests",
            VERIFY.collect_package_state(root, "HEAD")[0],
            "versions must match",
        )

    with package_repo() as root:
        set_versions(root, "1.2", "1.2")
        expect_failure(
            "malformed versions",
            VERIFY.collect_package_state(root, "HEAD")[0],
            "strict MAJOR.MINOR.PATCH",
        )

    with package_repo() as root:
        set_versions(root, "1.2.4", "1.2.4", pyproject="1.2.3")
        expect_failure(
            "pyproject left behind by the bump",
            VERIFY.collect_package_state(root, "HEAD")[0],
            "pyproject.toml [project] version is '1.2.3'",
        )

    with package_repo() as root:
        set_versions(root, "1.2.4", "1.2.4", changelog="1.2.3")
        expect_failure(
            "changelog without an entry for the release",
            VERIFY.collect_package_state(root, "HEAD")[0],
            "CHANGELOG.md top '## [x.y.z]' entry is '1.2.3'",
        )

    with package_repo() as root:
        set_versions(root, "1.2.4", "1.2.4")
        (root / PYPROJECT).write_text('[project]\nname = "x"\n', encoding="utf-8")
        expect_failure(
            "pyproject with no version line",
            VERIFY.collect_package_state(root, "HEAD")[0],
            "no version",
        )

    with package_repo() as root:
        set_versions(root, "1.2.4", "1.2.4")
        marketplace_path = root / ".agents/plugins/marketplace.json"
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["source"]["path"] = "./missing"
        write_json(marketplace_path, marketplace)
        expect_failure(
            "missing marketplace target",
            VERIFY.collect_package_state(root, "HEAD")[0],
            "target does not exist",
        )

    with package_repo() as root:
        set_versions(root, "1.2.4", "1.2.4")
        write_marketplaces(root, "./elsewhere")
        expect_failure(
            "the plugin's own marketplace naming another folder",
            VERIFY.collect_package_state(root, "HEAD")[0],
            "target does not exist",
        )


def test_default_base_ref_follows_the_tree() -> None:
    """On a push to main, HEAD is origin/main and comparing against it always
    fails; the script must then compare against HEAD~1 on its own."""
    with package_repo() as root:
        if VERIFY.default_base_ref(root) is not None:
            raise AssertionError("a root commit with no origin has no base to compare against")
        print("OK: a root commit with no origin compares against nothing")
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=root, check=True
        )
        if VERIFY.default_base_ref(root) is not None:
            raise AssertionError("HEAD is origin/main and HEAD~1 does not exist: no base")
        set_versions(root, "1.2.4", "1.2.4")
        subprocess.run(["git", "commit", "-qam", "bump"], cwd=root, check=True)
        if VERIFY.default_base_ref(root) != "origin/main":
            raise AssertionError("HEAD ahead of origin/main must compare against origin/main")
        print("OK: a branch ahead of origin/main compares against origin/main")
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/main", "HEAD"], cwd=root, check=True
        )
        if VERIFY.default_base_ref(root) != "HEAD~1":
            raise AssertionError("HEAD == origin/main must compare against HEAD~1")
        print("OK: a push to main compares against HEAD~1")
        errors, _ = VERIFY.collect_package_state(root, VERIFY.default_base_ref(root))
        if errors:
            raise AssertionError(f"the pushed bump failed against HEAD~1: {errors}")
        errors, _ = VERIFY.collect_package_state(root, None)
        if errors:
            raise AssertionError(f"no base ref must still validate the current state: {errors}")
        print("OK: no base ref validates the current state only")


def test_a_named_base_that_does_not_exist_fails() -> None:
    """A typo in a named base would compare against nothing and pass a
    missing bump; only the forge's all-zeros SHA means "no base"."""
    if VERIFY.main(["no-such-ref-anywhere"]) != 2:
        raise AssertionError("a named base that does not exist passed the gate")
    print("OK: a named base that does not exist fails")


def test_bumper() -> None:
    cases = (("patch", "1.2.4"), ("minor", "1.3.0"), ("major", "2.0.0"))
    for part, expected in cases:
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            seed_package(root)
            actual = BUMP.bump(root, part)
            versions = {
                json.loads((root / relative).read_text(encoding="utf-8"))["version"]
                for relative in BUMP.MANIFEST_PATHS
            }
            versions.add(VERIFY.read_pyproject_version(root))
            if actual != expected or versions != {expected}:
                raise AssertionError(
                    f"{part} bump: expected {expected}, got {actual} and {versions}"
                )
            text = (root / PYPROJECT).read_text(encoding="utf-8")
            if "[build-system]" not in text or "line-length = 100" not in text:
                raise AssertionError(f"the bump rewrote more than the version line:\n{text}")
            note = BUMP.changelog_note(root, expected)
            if note is None or f"## [{expected}]" not in note:
                raise AssertionError(f"the bump did not ask for a changelog entry: {note!r}")
            print(f"OK: {part} bump produced {expected} in the manifests and pyproject")

    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        seed_package(root)
        write_pyproject(root, "1.2.2")
        try:
            BUMP.bump(root)
        except BUMP.PackageVersionError as exc:
            if "not synchronized" not in str(exc) or "pyproject.toml" not in str(exc):
                raise AssertionError(f"unexpected pyproject mismatch error: {exc}") from exc
        else:
            raise AssertionError("version bumper accepted a pyproject behind the manifests")
        print("OK: version bumper rejects a pyproject behind the manifests")

    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        seed_package(root)
        set_versions(root, "1.2.3", "1.2.4")
        try:
            BUMP.bump(root)
        except BUMP.PackageVersionError as exc:
            if "not synchronized" not in str(exc):
                raise AssertionError(f"unexpected mismatch error: {exc}") from exc
        else:
            raise AssertionError("version bumper accepted mismatched manifests")
        print("OK: version bumper rejects mismatched manifests")


def test_bump_changes_the_version_and_nothing_else() -> None:
    """Every text file is LF: a bump changes the version and nothing else,
    byte for byte, and never writes the platform's newline."""
    files = (*MANIFESTS, PYPROJECT.as_posix())
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        seed_package(root)
        before = {}
        for relative in files:
            path = root / relative
            before[relative] = path.read_bytes().replace(b"\r\n", b"\n")
            path.write_bytes(before[relative])
        BUMP.bump(root)
        for relative in files:
            expected = before[relative].replace(b'"1.2.3"', b'"1.2.4"')
            if (root / relative).read_bytes() != expected:
                raise AssertionError(f"the bump changed more than the version in {relative}")
    print("OK: a bump changes the version and nothing else, and writes LF")


def test_package_and_bump_work_without_a_changelog() -> None:
    with package_repo() as root:
        (root / "CHANGELOG.md").unlink()
        errors, _ = VERIFY.collect_package_state(root, "HEAD")
        assert not errors, errors
        version = BUMP.bump(root)
        assert BUMP.changelog_note(root, version) is None
        errors, _ = VERIFY.collect_package_state(root, "HEAD")
        assert not errors, errors


def test_package_without_a_changelog_rejects_a_version_decrease() -> None:
    with package_repo() as root:
        set_versions(root, "1.2.2", "1.2.2")
        (root / "CHANGELOG.md").unlink()
        errors, _ = VERIFY.collect_package_state(root, "HEAD")
        assert any("must not decrease" in error for error in errors), errors


def test_an_unreleased_section_is_not_a_version() -> None:
    """Work between releases collects under ``## [Unreleased]`` at the top of
    the changelog; the gate reads the first released entry beneath it."""
    with package_repo() as root:
        set_versions(root, "1.2.4", "1.2.4")
        (root / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [Unreleased]\n\n- Work in progress.\n\n"
            "## [1.2.4] - 2026-01-01\n\n- Something.\n",
            encoding="utf-8",
        )
        if VERIFY.read_changelog_version(root) != "1.2.4":
            raise AssertionError(f"read {VERIFY.read_changelog_version(root)!r} as the release")
        errors, _ = VERIFY.collect_package_state(root, "HEAD")
        if errors:
            raise AssertionError(f"an Unreleased section failed the gate: {errors}")
    print("OK: an Unreleased section above the release is not read as a version")
