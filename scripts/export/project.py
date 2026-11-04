#!/usr/bin/env python3
"""Export a versioned cloud-project template to deterministic artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

# In a checkout the package is imported from src/; an installed wheel carries
# this script beside the package, which is already importable.
ROOT = next(
    (path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir()), None
)
if ROOT is not None:
    sys.path.insert(0, str(ROOT / "src"))

from infragram.exports import ExportError, export_project  # noqa: E402
from infragram.projects import CloudProject  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a .infragram.json cloud project to HTML, SVG, and PNG."
    )
    parser.add_argument("source", type=Path, help="source .infragram.json template")
    parser.add_argument(
        "--formats",
        default="template,html",
        help="comma-separated template,html,svg,png (default: template,html)",
    )
    parser.add_argument("--output-dir", type=Path, default=Path.cwd() / "dist")
    parser.add_argument(
        "--scale", type=float, default=3, help="PNG scale from 1 through 4 (default 3)"
    )
    parser.add_argument(
        "--theme",
        choices=("light", "dark"),
        default="light",
        help="workspace theme SVG and PNG are drawn in (default: light)",
    )
    parser.add_argument(
        "--libraries",
        choices=("project", "all"),
        default="project",
        help="libraries embedded in the HTML: the project's own (default, a few MB) or every installed one",
    )
    parser.add_argument(
        "--background",
        default="paper",
        help=(
            "what to paint behind the diagram: paper (the theme's own ground, "
            "the default), transparent, or a hex colour"
        ),
    )
    parser.add_argument(
        "--display",
        choices=("project", "card", "icon", "both"),
        default="project",
        help="how components draw in SVG and PNG: the document's own choice (default), "
        "cards, bare icons with captions, or both (icons written as <slug>-icons.*)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="after exporting, run the shipped checker on every artifact: document structure, "
        "real components, and for SVGs the picture itself (wires, text, captions, arrowheads)",
    )
    parser.add_argument("--force", action="store_true", help="replace existing artifacts")
    return parser


def verify_outputs(result) -> bool:
    """Run skills/infragram-azure/scripts/project_check.py on what was written."""
    import importlib.util

    from infragram.paths import skill_scripts

    checker_path = skill_scripts() / "project_check.py"
    spec = importlib.util.spec_from_file_location("project_check", checker_path)
    assert spec is not None and spec.loader is not None
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    clean = True
    for label in ("template", "html", "svg", "svg_icons"):
        path = getattr(result, label)
        if path is None:
            continue
        ok, message = checker.check_path(path)
        print(message)
        clean = clean and ok
    return clean


def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)
    formats = tuple(part.strip() for part in options.formats.split(",") if part.strip())
    try:
        project = CloudProject.load(options.source)
        result = export_project(
            project,
            options.output_dir,
            formats=formats,
            scale=options.scale,
            theme=options.theme,
            libraries=options.libraries,
            overwrite=options.force,
            display=options.display,
            background=options.background,
        )
    except (ExportError, OSError, ValidationError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    for label in ("template", "html", "svg", "png", "svg_icons", "png_icons"):
        path = getattr(result, label)
        if path is not None:
            print(f"{label.upper():8} {path} ({path.stat().st_size} bytes)")
    for note in result.notes:
        print(f"NOTE     {note}", file=sys.stderr)
    if options.verify and not verify_outputs(result):
        print("ERROR: the export did not pass verification", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
