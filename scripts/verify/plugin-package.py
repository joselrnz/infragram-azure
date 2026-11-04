#!/usr/bin/env python3
"""Verify synchronized version bumps and native marketplace packaging.

Usage::

    python scripts/verify/plugin-package.py [<base-ref>]

If a changelog is present, its release entries govern version bumps. Without
one, versions may stay unchanged or increase relative to *base-ref*. The
plugin's four manifests (Claude Code's, Codex's, the Agent Plugins
``plugin.json`` and npm's ``package.json``) and ``plugin/pyproject.toml`` must
name the same version, as must an optional changelog. Both marketplaces are checked twice:
the repository's, which install the ``plugin/`` folder, and the plugin's own,
which make an unpacked copy (the npm package, the folder a wheel carries) a
marketplace of itself.

Without a base the script picks it: ``origin/main`` when HEAD is not that
commit (a branch or a pull request), else ``HEAD~1`` (a push to main, where
origin/main is HEAD), else no base at all on a root commit, where only the
current state is validated and the script says so. A base named on the
command line must exist.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(
    0,
    str(
        next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir()) / "src"
    ),
)
from lib import gatelib

from infragram.registries.manifests import (
    CHANGELOG,
    MANIFEST_PATHS,
    PLUGIN,
    PYPROJECT,
    SEMVER,
    PackageVersionError,
    changelog_release,
    read_changelog_version,
    read_pyproject_version,
)

ROOT = gatelib.REPO_ROOT


# The plugin's name is whatever the manifest under the root being verified
# declares. Reading it rather than pinning it means a rename needs no edit
# here, and the gate can check a fixture as readily as the repository.
def plugin_name(manifests: dict[str, dict[str, Any]]) -> str:
    for label, payload in manifests.items():
        if "claude" in label.lower():
            return str(payload.get("name") or "")
    return str(next(iter(manifests.values()), {}).get("name") or "")


CLAUDE_MARKETPLACE = Path(".claude-plugin/marketplace.json")
CODEX_MARKETPLACE = Path(".agents/plugins/marketplace.json")
#: Where a manifest lived before everything that ships moved into plugin/:
#: a base from before the move is read there.
BEFORE_PLUGIN_FOLDER = {
    "Claude": Path(".claude-plugin/plugin.json"),
    "Codex": Path(".codex-plugin/plugin.json"),
}


def load_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"could not read {path}: {exc}")
        return None
    except json.JSONDecodeError as exc:
        errors.append(f"{path} is not valid JSON: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{path} must contain a JSON object")
        return None
    return payload


def load_base_json(
    root: Path, base_ref: str, relative: Path, errors: list[str]
) -> dict[str, Any] | None:
    result = gatelib.run(
        ["git", "show", f"{base_ref}:{relative.as_posix()}"],
        cwd=root,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "file not found"
        errors.append(f"could not read {relative} from {base_ref}: {detail}")
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        errors.append(f"{relative} at {base_ref} is not valid JSON: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{relative} at {base_ref} must contain a JSON object")
        return None
    return payload


def parse_semver(value: object, label: str, errors: list[str]) -> tuple[int, int, int] | None:
    if not isinstance(value, str) or (match := SEMVER.fullmatch(value)) is None:
        errors.append(f"{label} version must be strict MAJOR.MINOR.PATCH semver; got {value!r}")
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def resolve_local_path(root: Path, raw_path: object, label: str, errors: list[str]) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        errors.append(f"{label} must be a non-empty local path string")
        return None
    if raw_path not in {".", "./"} and not raw_path.startswith("./"):
        errors.append(f"{label} must be '.' or start with './'; got {raw_path!r}")
        return None

    relative = raw_path[2:] if raw_path.startswith("./") else ""
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        errors.append(f"{label} must stay inside the marketplace root; got {raw_path!r}")
        return None

    resolved_root = root.resolve()
    resolved = (root / relative_path).resolve()
    if not resolved.is_relative_to(resolved_root):
        errors.append(f"{label} resolves outside the marketplace root: {raw_path!r}")
        return None
    if not resolved.is_dir():
        errors.append(f"{label} target does not exist or is not a directory: {raw_path!r}")
        return None
    return resolved


def find_plugin_entry(
    marketplace: dict[str, Any], label: str, errors: list[str], expected: str
) -> dict[str, Any] | None:
    if marketplace.get("name") != expected:
        errors.append(
            f"{label} marketplace name must match the manifest {expected!r}; "
            f"got {marketplace.get('name')!r}"
        )
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        errors.append(f"{label} marketplace plugins must be an array")
        return None
    matches = [
        entry for entry in plugins if isinstance(entry, dict) and entry.get("name") == expected
    ]
    if len(matches) != 1:
        errors.append(
            f"{label} marketplace must contain exactly one {expected!r} entry; found {len(matches)}"
        )
        return None
    return matches[0]


def verify_versions(
    root: Path,
    base_ref: str,
    manifests: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    current_versions = {label: payload.get("version") for label, payload in manifests.items()}
    version_values = list(current_versions.values())
    if any(version != version_values[0] for version in version_values[1:]):
        rendered = ", ".join(f"{label}={value!r}" for label, value in current_versions.items())
        errors.append(f"the plugin manifests' versions must match: {rendered}")

    has_changelog = (root / CHANGELOG).is_file()
    release_added = release_entry_added(root, base_ref) if has_changelog else False
    for label, relative in MANIFEST_PATHS.items():
        current = parse_semver(current_versions.get(label), f"current {label}", errors)
        base_manifest = load_base_json(root, base_ref, relative, [])
        if base_manifest is None and label in BEFORE_PLUGIN_FOLDER:
            base_manifest = load_base_json(root, base_ref, BEFORE_PLUGIN_FOLDER[label], errors)
        if base_manifest is None:
            # a manifest the base does not have yet has no version to compare
            continue
        base = parse_semver(base_manifest.get("version"), f"{label} at {base_ref}", errors)
        if current is None or base is None:
            continue
        change = f"{base_manifest.get('version')} -> {current_versions.get(label)}"
        if not has_changelog:
            if current < base:
                errors.append(
                    f"{label} manifest version must not decrease relative to {base_ref}: {change}"
                )
        elif release_added and current <= base:
            errors.append(
                f"{label} manifest version must increase relative to {base_ref} with the new "
                f"release entry in CHANGELOG.md: {change}"
            )
        elif not release_added and current != base:
            errors.append(
                f"{label} manifest version changed relative to {base_ref} without a new release "
                f"entry in CHANGELOG.md ({change}); a release adds its entry and bumps together"
            )


def release_entry_added(root: Path, base_ref: str) -> bool:
    """Whether CHANGELOG.md's top release entry differs from the one at
    *base_ref*. A base with no readable changelog counts as a new release, so
    the version is still held to an increase there."""
    try:
        now = read_changelog_version(root)
    except PackageVersionError:
        return True
    result = gatelib.run(["git", "show", f"{base_ref}:{CHANGELOG.as_posix()}"], cwd=root)
    then = changelog_release(result.stdout) if result.returncode == 0 else None
    return then is None or then != now


def verify_manifest_identity(manifests: dict[str, dict[str, Any]], errors: list[str]) -> None:
    expected = plugin_name(manifests)
    for label, payload in manifests.items():
        if payload.get("name") != expected:
            errors.append(
                f"every manifest must declare the same name {expected!r}; {label} says {payload.get('name')!r}"
            )


def verify_marketplaces(root: Path, errors: list[str], expected: str) -> None:
    claude_marketplace = load_json(root / CLAUDE_MARKETPLACE, errors)
    codex_marketplace = load_json(root / CODEX_MARKETPLACE, errors)
    if claude_marketplace is None or codex_marketplace is None:
        return

    claude_entry = find_plugin_entry(claude_marketplace, "Claude", errors, expected)
    codex_entry = find_plugin_entry(codex_marketplace, "Codex", errors, expected)
    if claude_entry is None or codex_entry is None:
        return

    claude_root = resolve_local_path(
        root, claude_entry.get("source"), "Claude plugin source", errors
    )

    codex_source = codex_entry.get("source")
    if not isinstance(codex_source, dict) or codex_source.get("source") != "local":
        errors.append("Codex plugin source must be an object with source='local'")
        codex_root = None
    else:
        codex_root = resolve_local_path(
            root, codex_source.get("path"), "Codex plugin source.path", errors
        )

    policy = codex_entry.get("policy")
    if not isinstance(policy, dict):
        errors.append("Codex marketplace entry must include a policy object")
    else:
        if policy.get("installation") != "AVAILABLE":
            errors.append("Codex policy.installation must be 'AVAILABLE'")
        if policy.get("authentication") != "ON_INSTALL":
            errors.append("Codex policy.authentication must be 'ON_INSTALL'")
    if not isinstance(codex_entry.get("category"), str) or not codex_entry.get("category"):
        errors.append("Codex marketplace entry must include a category")

    if (
        claude_root is not None
        and not (claude_root / MANIFEST_PATHS["Claude"].relative_to(PLUGIN)).is_file()
    ):
        errors.append("Claude marketplace target does not contain .claude-plugin/plugin.json")
    if (
        codex_root is not None
        and not (codex_root / MANIFEST_PATHS["Codex"].relative_to(PLUGIN)).is_file()
    ):
        errors.append("Codex marketplace target does not contain .codex-plugin/plugin.json")
    if claude_root is not None and codex_root is not None and claude_root != codex_root:
        errors.append("Claude and Codex marketplaces must package the same plugin root")

    plugin_root = codex_root or claude_root
    if plugin_root is None:
        return
    skill = plugin_root / "skills" / expected / "SKILL.md"
    if not skill.is_file():
        errors.append(f"packaged skill is missing: {skill.relative_to(root)}")


def verify_codex_skill_path(
    root: Path, codex_manifest: dict[str, Any], errors: list[str], expected: str
) -> None:
    skills_root = resolve_local_path(
        root, codex_manifest.get("skills"), "Codex manifest skills", errors
    )
    if skills_root is None:
        return
    skill = skills_root / expected / "SKILL.md"
    if not skill.is_file():
        errors.append(f"Codex skills path does not contain {expected}/SKILL.md")


def verify_package_version(
    root: Path, manifests: dict[str, dict[str, Any]], errors: list[str]
) -> None:
    """pyproject.toml and an optional changelog name the manifests' version.

    The bump writes pyproject; the changelog entry is written by hand. Either
    drifting means the wheel or the release notes ship under the wrong number.
    """
    expected = next(iter(manifests.values())).get("version")
    for label, reader in ((PYPROJECT, read_pyproject_version), (CHANGELOG, read_changelog_version)):
        if label == CHANGELOG and not (root / CHANGELOG).exists():
            continue
        try:
            found = reader(root)
        except PackageVersionError as exc:
            errors.append(str(exc))
            continue
        if found != expected:
            what = "[project] version" if label == PYPROJECT else "top '## [x.y.z]' entry"
            errors.append(
                f"{label} {what} is {found!r}; the plugin manifests say {expected!r}"
                + (
                    " (run `infragram bump`)"
                    if label == PYPROJECT
                    else " (add a changelog entry for it)"
                )
            )


def ref_exists(root: Path, ref: str) -> bool:
    """Does ``ref`` name a commit in this repository?"""
    result = gatelib.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=root)
    return result.returncode == 0


def rev(root: Path, ref: str) -> str | None:
    result = gatelib.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=root)
    return result.stdout.strip() or None if result.returncode == 0 else None


def default_base_ref(root: Path) -> str | None:
    """The commit the version must have increased from, chosen by the tree:
    origin/main unless HEAD *is* origin/main, then HEAD~1; None on a root
    commit with no origin."""
    head, origin = rev(root, "HEAD"), rev(root, "origin/main")
    if origin is not None and origin != head:
        return "origin/main"
    if rev(root, "HEAD~1") is not None:
        return "HEAD~1"
    return None


def collect_package_state(
    root: Path, base_ref: str | None
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    """Run every package gate; return (errors, loaded manifests).

    *base_ref* None means no commit to compare against (a root commit with
    no origin): the current state is validated and the note says so.
    """
    errors: list[str] = []
    manifests: dict[str, dict[str, Any]] = {}
    for label, relative in MANIFEST_PATHS.items():
        payload = load_json(root / relative, errors)
        if payload is not None:
            manifests[label] = payload

    expected = plugin_name(manifests)
    if len(manifests) == len(MANIFEST_PATHS):
        # GitHub sends the all-zeros SHA as `event.before` on the first push
        # to a branch (and after history rewrites), and HEAD~1 does not exist
        # on a root commit; either way there is no base to compare against,
        # so validate only the current state.
        if base_ref is None or set(base_ref) == {"0"} or not ref_exists(root, base_ref):
            print(
                f"note: base ref {base_ref or '(none)'} does not exist; skipping version-bump comparison"
            )
            for label in manifests:
                parse_semver(manifests[label].get("version"), label, errors)
            versions = {m.get("version") for m in manifests.values()}
            if len(versions) > 1:
                # A manifest with no version (None) or a number for one sits
                # in this set beside the strings, and those do not order
                # against each other: sorted by their text, the mismatch is
                # reported instead of the gate stopping on a TypeError.
                errors.append(f"manifest versions must match; got {sorted(versions, key=str)}")
        else:
            verify_versions(root, base_ref, manifests, errors)
        verify_manifest_identity(manifests, errors)
        verify_codex_skill_path(root / PLUGIN, manifests["Codex"], errors, expected)
        verify_package_version(root, manifests, errors)
    # the repository's marketplaces, then the plugin's own
    verify_marketplaces(root, errors, expected)
    verify_marketplaces(root / PLUGIN, errors, expected)
    return errors, manifests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "base_ref",
        nargs="?",
        default=None,
        help="the commit to compare against (default: picked from the tree)",
    )
    named: str | None = parser.parse_args(argv).base_ref
    if named is not None:
        base_ref: str | None = named
        # A base someone named is one they meant: comparing against nothing
        # because of a typo would pass a missing bump. The all-zeros SHA a
        # forge sends for a new branch is the one deliberate "no base".
        if set(named) != {"0"} and not ref_exists(ROOT, named):
            print(f"FAIL plugin package: base ref {named!r} does not exist", file=sys.stderr)
            return 2
    else:
        base_ref = default_base_ref(ROOT)
        print(
            f"note: comparing versions against {base_ref or 'no base (root commit, no origin/main)'}"
        )
    errors, manifests = collect_package_state(ROOT, base_ref)
    if errors:
        print("FAIL plugin package")
        for error in errors:
            print(f"  - {error}")
        return 1
    # No errors means every manifest loaded with matching semver versions.
    version = manifests["Claude"].get("version")
    print(
        f"OK plugin package: {', '.join(MANIFEST_PATHS)} manifests {version}, pyproject and "
        f"optional changelog agree, marketplace paths (the repository's and the plugin's own), and packaged skill"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
