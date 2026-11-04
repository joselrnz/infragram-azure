"""Plugin manifest registry: paths, semver rules, and the synchronized bump.

Single source of truth shared by ``bump-plugin-version.py`` (which writes new
versions) and ``plugin-package.py`` (which gates them in CI). Adding a
manifest here updates both sides at once, so the bumper can never write a
version the verifier does not check.

The version lives in five places. The plugin's four manifests (Claude Code's,
Codex's, the Agent Plugins ``plugin.json`` newer clients read, and npm's
``package.json``) and ``plugin/pyproject.toml`` (the wheel's version) are
written by the bump. An optional changelog can also name the current version
and is checked against the manifests when present.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

#: The folder that is the plugin, in the repository.
PLUGIN = Path(".")

#: Label -> repo-relative manifest path. Order is the display order.
MANIFEST_PATHS: dict[str, Path] = {
    "Claude": PLUGIN / ".claude-plugin" / "plugin.json",
    "Codex": PLUGIN / ".codex-plugin" / "plugin.json",
    "Agent Plugins": PLUGIN / "plugin.json",
    "npm": PLUGIN / "package.json",
}

#: The package's own version, under ``[project]``; the wheel carries it.
PYPROJECT = PLUGIN / "pyproject.toml"
#: The release notes; the top entry names the version being shipped.
CHANGELOG = Path("CHANGELOG.md")

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

#: ``version = "x.y.z"`` inside the ``[project]`` table, and nowhere else:
#: ``[tool.*]`` tables carry their own version keys.
_PROJECT_TABLE = re.compile(r"(?ms)^\[project\][ \t]*\r?\n(?P<body>.*?)(?=^\[|\Z)")
_VERSION_LINE = re.compile(r'(?m)^(?P<lead>version[ \t]*=[ \t]*")(?P<version>[^"\r\n]*)(?P<tail>")')
#: The first released ``## [x.y.z]`` heading. A Keep-a-Changelog file lists
#: newest first, under an ``## [Unreleased]`` section that collects the work
#: not yet given a version; that section is skipped.
_CHANGELOG_ENTRY = re.compile(r"(?m)^## \[(?!(?i:unreleased)\])(?P<version>[^\]\r\n]+)\]")


class PackageVersionError(ValueError):
    """Raised when the package versions cannot be read or bumped safely."""


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageVersionError(f"could not read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PackageVersionError(f"{path} must contain a JSON object")
    return payload


def parse_version(value: object, label: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or (match := SEMVER.fullmatch(value)) is None:
        raise PackageVersionError(
            f"{label} version must be strict MAJOR.MINOR.PATCH semver; got {value!r}"
        )
    major, minor, patch = map(int, match.groups())
    return major, minor, patch


def _pyproject_version_match(text: str) -> re.Match[str] | None:
    table = _PROJECT_TABLE.search(text)
    if table is None:
        return None
    body = _VERSION_LINE.search(table.group("body"))
    if body is None:
        return None
    # Re-run on the whole text at the table's offset so span() indexes it.
    return _VERSION_LINE.search(text, table.start("body"), table.end("body"))


def read_pyproject_version(root: Path) -> str:
    """The ``[project] version`` string in pyproject.toml."""
    path = root / PYPROJECT
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PackageVersionError(f"could not read {path}: {exc}") from exc
    match = _pyproject_version_match(text)
    if match is None:
        raise PackageVersionError(f'{path} has no version = "..." line under [project]')
    return match.group("version")


def write_pyproject_version(root: Path, version: str) -> None:
    """Rewrite the ``[project] version`` line and nothing else."""
    path = root / PYPROJECT
    text = path.read_text(encoding="utf-8")
    match = _pyproject_version_match(text)
    if match is None:
        raise PackageVersionError(f'{path} has no version = "..." line under [project]')
    updated = text[: match.start("version")] + version + text[match.end("version") :]
    atomic_write_text(path, updated)


def changelog_release(text: str) -> str | None:
    """The version the top released ``## [x.y.z]`` entry of a changelog's
    text names, below any ``## [Unreleased]`` section, or None."""
    match = _CHANGELOG_ENTRY.search(text)
    return match.group("version") if match else None


def read_changelog_version(root: Path) -> str:
    """The version the top released ``## [x.y.z]`` entry of CHANGELOG.md
    names, below any ``## [Unreleased]`` section."""
    path = root / CHANGELOG
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PackageVersionError(f"could not read {path}: {exc}") from exc
    version = changelog_release(text)
    if version is None:
        raise PackageVersionError(f"{path} has no '## [x.y.z]' entry")
    return version


def atomic_write_text(path: Path, contents: str) -> None:
    """Write via a sibling temp file + os.replace so readers never see a torn
    file, LF on every platform.

    Every text file in the repository is LF (``.gitattributes``); a write
    that took the platform's newline turned every line of a manifest CRLF on
    Windows, and a bump must change the version and nothing else.
    """
    contents = contents.replace("\r\n", "\n")
    temp_path = path.with_name(path.name + ".tmp")
    try:
        # newline="" writes the text exactly as prepared above
        temp_path.write_text(contents, encoding="utf-8", newline="")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def bump(root: Path, part: str = "patch") -> str:
    """Bump every manifest in MANIFEST_PATHS and pyproject.toml to the same
    next version. The changelog is not written: its top entry is authored by
    hand, and ``plugin-package.py`` requires it to name this version."""
    manifests = [(relative, read_manifest(root / relative)) for relative in MANIFEST_PATHS.values()]
    raw_versions = [payload.get("version") for _, payload in manifests]
    pyproject_version = read_pyproject_version(root)
    if (
        any(version != raw_versions[0] for version in raw_versions[1:])
        or pyproject_version != raw_versions[0]
    ):
        rendered = ", ".join(
            f"{relative}={version!r}"
            for (relative, _), version in zip(manifests, raw_versions, strict=True)
        )
        raise PackageVersionError(
            f"manifest versions are not synchronized: {rendered}, {PYPROJECT}={pyproject_version!r}"
        )

    major, minor, patch = parse_version(raw_versions[0], str(next(iter(MANIFEST_PATHS.values()))))
    if part == "major":
        next_version = (major + 1, 0, 0)
    elif part == "minor":
        next_version = (major, minor + 1, 0)
    elif part == "patch":
        next_version = (major, minor, patch + 1)
    else:
        raise PackageVersionError(f"unsupported version part: {part}")

    version = ".".join(str(value) for value in next_version)
    rendered_manifests: list[tuple[Path, str]] = []
    for relative, payload in manifests:
        payload["version"] = version
        rendered_manifests.append(
            (root / relative, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        )
    for path, contents in rendered_manifests:
        atomic_write_text(path, contents)
    write_pyproject_version(root, version)
    return version
