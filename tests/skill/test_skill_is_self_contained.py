"""The shipped skill must not depend on this repository's dev tooling.

``skills/infragram-azure/`` installs on its own wherever an agent reads
skills, and its scripts run before anything else is installed: the launcher
finds the package (beside the skill in a plugin, or installed) and says what
is missing, and the checker needs none. If a script there imported
``infragram`` or a third-party module, or reached outside the skill
directory, the installed skill would break.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
SKILL = ROOT / "skills" / "infragram-azure"

# Modules the shipped scripts may import: the standard library only.
FORBIDDEN_ROOTS = {"infragram", "lib"}


def imported_roots(source: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def shipped_scripts() -> list[Path]:
    scripts = sorted((SKILL / "scripts").glob("*.py"))
    assert scripts, f"no shipped scripts found under {SKILL / 'scripts'}"
    return scripts


def prose(markdown: str) -> str:
    """Markdown with its fenced blocks and inline code spans removed."""
    without_fences = re.sub(r"```.*?```", "", markdown, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", without_fences)


def agent_docs() -> list[Path]:
    """SKILL.md and every reference document, the per-library pages under
    references/providers/ included."""
    return [
        path
        for path in (SKILL / "SKILL.md", *sorted((SKILL / "references").rglob("*.md")))
        if path.is_file()
    ]


def test_shipped_scripts_import_the_standard_library_only() -> None:
    for script in shipped_scripts():
        roots = imported_roots(script.read_text(encoding="utf-8"))
        leaked = roots & FORBIDDEN_ROOTS
        assert not leaked, (
            f"{script.relative_to(ROOT)} imports dev-only module(s): {', '.join(sorted(leaked))}"
        )
        third_party = {r for r in roots if r not in sys.stdlib_module_names}
        assert not third_party, (
            f"{script.relative_to(ROOT)} imports non-stdlib module(s): {', '.join(sorted(third_party))}"
        )


def test_agent_docs_do_not_point_at_the_dev_tree() -> None:
    """Agent-facing docs may not point at the dev tree. Two exemptions:
    generated JSON records its generator (provenance, not a dependency),
    and the data-folder READMEs are contributor notes on regenerating
    artwork, addressed to someone working in this repository.

    Code is not prose. The compose workflow is Python that imports the
    shipped package (`from infragram.author import Diagram`, run through the
    skill's launcher), so inside a fenced block or an inline
    code span an import of `infragram` is the product working as designed.
    In prose it is still a pointer at the tree, and paths into the tree are
    forbidden everywhere.
    """
    for path in agent_docs():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for needle in ("src/infragram", "scripts/verify/", "scripts/build/"):
            assert needle not in text, (
                f"{path.relative_to(ROOT)} references the dev tree: {needle!r}"
            )
        for needle in ("from infragram", "import infragram"):
            assert needle not in prose(text), (
                f"{path.relative_to(ROOT)} imports the package in prose: {needle!r}; "
                "code samples may, prose points the reader at the dev tree"
            )
