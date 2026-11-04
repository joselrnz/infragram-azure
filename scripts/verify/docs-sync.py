#!/usr/bin/env python3
"""Verify that routing and browsing surfaces stay in sync with the skill.

Five drift classes:

1. The SKILL.md frontmatter description is the only text an agent sees before
   deciding to load the skill - every installed library and every export
   format must keep a lexical hook there, and every skill's description must
   fit the 1024 characters Codex allows.
2. Every concrete file named in README.md's architecture tree must exist.
3. Every relative references/*.md link in SKILL.md must resolve.
4. Every provider manifest must have one indexed, provider-specific reference.
5. README.md's command reference, between the ``[//]: # (commands:start)`` and
   ``[//]: # (commands:end)`` markers, is the table the CLI registry makes
   (``infragram.cli.commands.project.COMMANDS``): one row per user command,
   with its help line. ``--write-commands`` rewrites it from the registry.
"""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import gatelib

ROOT = gatelib.REPO_ROOT
# The command reference is read from this checkout's registry, as the other
# gates read this checkout's package.
sys.path.insert(1, str(ROOT / "src"))
SKILL = ROOT / "skills/infragram-azure/SKILL.md"
PROVIDERS = ROOT / "skills/infragram-azure/assets/catalog/providers.json"
README = ROOT / "README.md"
#: Where the repository tree lives: the README links to it, and every file it
#: names must exist.
TREE_DOC = ROOT / "CONTRIBUTING.md"
#: Vocabulary every description must carry besides the library names.
REQUIRED_TERMS = ("infrastructure", "html", "svg", "png", ".infragram.json")
#: The longest description Codex loads a skill with (the Agent Skills limit).
DESCRIPTION_LIMIT = 1024


def normalized(text: str) -> str:
    text = text.casefold()
    text = re.sub(r"\s*/\s*", "/", text)
    return re.sub(r"\s+", " ", text)


FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(?P<body>.*?)^---[ \t]*\r?$", re.MULTILINE | re.DOTALL
)


def frontmatter_description(markdown: str) -> str:
    """Read description: from a leading YAML frontmatter block only.

    A naive split("---") also matched horizontal rules later in the document;
    the anchored regex requires the block to open at the first byte and close
    on its own line.
    """
    match = FRONTMATTER_RE.match(markdown)
    if match is None:
        return ""
    description = re.search(r"^description:\s*(.+)$", match.group("body"), re.MULTILINE)
    return description.group(1).strip() if description else ""


def installed_library_names() -> list[str]:
    payload = json.loads(PROVIDERS.read_text(encoding="utf-8"))
    return [entry["display_name"] for entry in payload["providers"]]


def check_description(errors: list[str]) -> None:
    markdown = SKILL.read_text(encoding="utf-8")
    description = normalized(frontmatter_description(markdown))
    if not description:
        errors.append("SKILL.md frontmatter description is missing")
        return
    for name in installed_library_names():
        if normalized(name) not in description:
            errors.append(
                f"description lost the lexical hook for library {name!r} "
                f"(expected it in the SKILL.md frontmatter description)"
            )
    for term in REQUIRED_TERMS:
        if term not in description:
            errors.append(f"description lost the lexical hook {term!r}")
    for skill in sorted(SKILL.parent.parent.glob("*/SKILL.md")):
        length = len(frontmatter_description(skill.read_text(encoding="utf-8")))
        if length > DESCRIPTION_LIMIT:
            errors.append(
                f"{skill.relative_to(ROOT).as_posix()}: description is {length} characters; "
                f"Codex refuses a skill past {DESCRIPTION_LIMIT}"
            )


def readme_tree_tokens(markdown: str) -> list[str]:
    """The file names the "Repository layout" section names, as a tree or a list."""
    blocks = re.findall(
        r"^## Repository layout\n(.*?)(?=^## |\Z)", markdown, re.DOTALL | re.MULTILINE
    )
    tokens: list[str] = []
    for block in blocks:
        tokens.extend(
            re.findall(
                r"([A-Za-z0-9_][A-Za-z0-9_.*-]*\.(?:md|html|py|yml|yaml|json|txt|mmd|drawio|png))",
                block,
            )
        )
    return tokens


# Directories that can never legitimately satisfy a README tree entry: junk,
# and the build outputs (dist/ holds exported pages, build/ the wheel), which
# would let a README name a file only a previous run wrote.
SKIPPED_TREE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv"}
#: Build outputs, skipped at the repository root only: `scripts/build/` is
#: source and a README may name what is in it.
ROOT_ONLY_SKIPPED_DIRS = {"dist", "build"}


def repository_file_names(root: Path) -> set[str]:
    """Exact-case names of every file under *root*, minus junk directories.

    ``Path.rglob`` matches case-insensitively on Windows and wanders into
    .git; ``os.walk`` reports the on-disk spelling, letting the comparison
    stay case-sensitive on every platform.
    """
    names: set[str] = set()
    for directory, subdirectories, files in os.walk(root):
        skipped = SKIPPED_TREE_DIRS | (ROOT_ONLY_SKIPPED_DIRS if Path(directory) == root else set())
        subdirectories[:] = [name for name in subdirectories if name not in skipped]
        names.update(files)
    return names


def check_readme_tree(errors: list[str], root: Path = ROOT, readme: Path = TREE_DOC) -> None:
    markdown = readme.read_text(encoding="utf-8")
    tokens = readme_tree_tokens(markdown)
    if not tokens:
        errors.append(f"{readme.name}: the repository tree is not found or names no files")
        return
    on_disk = repository_file_names(root)
    for token in sorted(set(tokens)):
        if "*" in token:
            found = any(fnmatch.fnmatchcase(name, token) for name in on_disk)
        else:
            found = token in on_disk
        if not found:
            errors.append(
                f"{readme.name}: the repository tree names {token!r} but no such file exists"
            )


def skill_reference_links(markdown: str) -> list[str]:
    """Return direct relative links from SKILL.md into references/."""
    return re.findall(
        r"\]\((references/[A-Za-z0-9][A-Za-z0-9_./-]*\.md)(?:#[^)]*)?\)",
        markdown,
    )


def check_skill_reference_links(errors: list[str], markdown: str, skill_directory: Path) -> None:
    for target in sorted(set(skill_reference_links(markdown))):
        if not (skill_directory / target).is_file():
            errors.append(f"SKILL.md links to missing reference {target!r}")


def check_provider_reference_index(errors: list[str], skill_directory: Path) -> None:
    """Keep the provider router aligned with the machine-readable catalog."""
    catalog_path = skill_directory / "assets/themes/catalog.json"
    index_path = skill_directory / "references/provider-themes.md"
    if not catalog_path.is_file():
        errors.append("provider theme catalog is missing: assets/themes/catalog.json")
        return
    if not index_path.is_file():
        errors.append("provider reference index is missing: references/provider-themes.md")
        return
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        errors.append(f"provider theme catalog is invalid JSON: {error}")
        return
    entries = payload.get("providers")
    if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
        errors.append("provider theme catalog must contain a string providers array")
        return

    slugs = [Path(entry).stem for entry in entries]
    index = index_path.read_text(encoding="utf-8")
    linked = re.findall(r"\]\(providers/([a-z0-9-]+)\.md\)", index)
    for slug in slugs:
        reference = skill_directory / f"references/providers/{slug}.md"
        if linked.count(slug) != 1:
            errors.append(
                f"provider {slug!r} must appear exactly once in references/provider-themes.md"
            )
        if not reference.is_file():
            errors.append(f"provider {slug!r} reference is missing: references/providers/{slug}.md")
            continue
        manifest_link = f"../../assets/themes/{slug}.json"
        if manifest_link not in reference.read_text(encoding="utf-8"):
            errors.append(
                f"provider {slug!r} reference does not link its manifest: {manifest_link}"
            )
    for slug in sorted(set(linked) - set(slugs)):
        errors.append(f"provider index contains unregistered provider {slug!r}")


#: The markers are Markdown link definitions, which no viewer draws; an HTML
#: comment shows as text in a viewer that escapes raw HTML.
COMMANDS_START = "[//]: # (commands:start)"
COMMANDS_END = "[//]: # (commands:end)"
REGENERATE = "python scripts/verify/docs-sync.py --write-commands"
#: What follows the table inside the markers: the maintainer commands are not
#: listed one by one, since only a checkout runs them.
MAINTAINER_LINE = (
    "The maintainer commands need a checkout of the repository; `infragram --help` "
    "lists them, and [Development and scope](#development-and-scope) says which to run when."
)


def user_commands() -> dict[str, tuple[str, str]]:
    """The registry the command line lists: command -> (target, help line)."""
    from infragram.cli.commands import project

    return project.COMMANDS


def _cell(text: str) -> str:
    """Text for a Markdown table cell: a pipe would end the cell."""
    return text.replace("|", r"\|")


def commands_table(commands: dict[str, tuple[str, str]] | None = None) -> str:
    """The command reference README.md carries, made from the registry, in its order."""
    entries = user_commands() if commands is None else commands
    rows = [f"| `{name}` | {_cell(help_text)} |" for name, (_target, help_text) in entries.items()]
    return "\n".join(["| Command | What it does |", "|---|---|", *rows, "", MAINTAINER_LINE])


def commands_span(markdown: str) -> tuple[int, int] | str:
    """Where the command reference sits between its markers, or what is wrong."""
    starts, ends = markdown.count(COMMANDS_START), markdown.count(COMMANDS_END)
    if starts != 1 or ends != 1:
        return (
            f"README must carry {COMMANDS_START} and {COMMANDS_END} once each "
            f"(found {starts} and {ends})"
        )
    start = markdown.index(COMMANDS_START) + len(COMMANDS_START)
    end = markdown.index(COMMANDS_END)
    if end < start:
        return f"README's {COMMANDS_END} comes before its {COMMANDS_START}"
    return start, end


def with_commands_table(markdown: str, table: str) -> str:
    """*markdown* with the text between the markers replaced by *table*.

    Blank lines keep each marker apart: a definition right under a paragraph
    would join that paragraph and show.
    """
    span = commands_span(markdown)
    if isinstance(span, str):
        raise ValueError(span)
    return markdown[: span[0]] + "\n\n" + table + "\n\n" + markdown[span[1] :]


def check_commands_table(
    errors: list[str],
    readme: Path = README,
    commands: dict[str, tuple[str, str]] | None = None,
) -> None:
    markdown = readme.read_text(encoding="utf-8")
    span = commands_span(markdown)
    if isinstance(span, str):
        errors.append(f"{span}; add them around the command reference, then run {REGENERATE}")
        return
    found = markdown[span[0] : span[1]].strip("\n").splitlines()
    expected = commands_table(commands).splitlines()
    if found != expected:
        diff = difflib.unified_diff(
            found, expected, "README.md", "the CLI registry", lineterm="", n=0
        )
        errors.append(
            "README's command reference is not the CLI registry's "
            "(src/infragram/cli/commands/project.py); regenerate it with "
            f"{REGENERATE}:\n" + "\n".join(f"      {line}" for line in diff)
        )


def write_commands_table(
    readme: Path = README, commands: dict[str, tuple[str, str]] | None = None
) -> bool:
    """Rewrite the command reference from the registry; True when the file changed."""
    markdown = readme.read_text(encoding="utf-8")
    updated = with_commands_table(markdown, commands_table(commands))
    if updated == markdown:
        return False
    readme.write_text(updated, encoding="utf-8", newline="\n")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--write-commands",
        action="store_true",
        help="rewrite README.md's command reference from the CLI registry, then check",
    )
    options = parser.parse_args(argv)
    if options.write_commands:
        try:
            changed = write_commands_table()
        except ValueError as refused:
            print(f"FAIL docs sync\n  - {refused}")
            return 1
        print(
            "WROTE README.md command reference"
            if changed
            else "README.md command reference already matches the registry"
        )
    errors: list[str] = []
    check_description(errors)
    check_readme_tree(errors)
    check_skill_reference_links(
        errors,
        SKILL.read_text(encoding="utf-8"),
        SKILL.parent,
    )
    check_provider_reference_index(errors, SKILL.parent)
    check_commands_table(errors)
    if errors:
        print("FAIL docs sync")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "OK docs sync: description hooks, repository tree, reference links, provider routing, "
        "command reference"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
