"""``infragram views``: what ``--view`` can draw from a diagram.

The views the diagram declares, then every frame by level, each with the
name to pass: ``--view <id>`` draws that frame and everything in it.
``--json`` prints the same as one JSON document (:func:`infragram.projects.views.views_json`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    from pydantic import ValidationError

    from ...compose import ComposeError
    from ...exports import ExportError
    from ...projects.views import SHORTHANDS, frames_of, selector_text, views_json
    from .diff import load_any

    parser = argparse.ArgumentParser(
        prog="infragram views",
        description="List what --view can draw from a diagram: the views it declares, and "
        "every frame by level (a subscription, a resource group, a VNet, a VPC, a namespace).",
    )
    parser.add_argument(
        "source",
        type=Path,
        help="a .infragram.json document, a diagram file, or a page or picture that carries "
        "its document",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the declared views and every frame (id, name, type, level, the frame "
        "around it, components inside) as one JSON document and nothing else on stdout",
    )
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        project = load_any(options.source)
    except (ExportError, ComposeError, ValidationError, ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    if options.json:
        print(json.dumps(views_json(project), ensure_ascii=False, indent=2))
        return 0
    print(f"VIEWS    {project.title}: {len(project.views)} declared")
    for view in project.views:
        rules = [f"+{selector_text(selector)}" for selector in view.include]
        rules += [f"-{selector_text(selector)}" for selector in view.exclude]
        extends = f" extends {view.extends}" if view.extends else ""
        print(f"VIEW     {view.id}: {view.title or view.id}{extends} ({' '.join(rules) or 'all'})")
    for depth, frame in frames_of(project):
        components = sum(1 for element in frame.walk() if not element.children)
        print(f"FRAME    {'  ' * depth}{frame.id}: {frame.name} [{frame.type}] ({components})")
    print(f"RULES    {', '.join(f'{kind}:...' for kind in SHORTHANDS)}")
    return 0
