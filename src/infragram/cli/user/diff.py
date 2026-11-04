"""``infragram diff <before> <after>``: what changed between two versions of
a diagram, written out and drawn (infragram/review/diff.py).

For a pipeline: ``--json`` prints the report as one JSON document and keeps
stdout for it alone, ``--exit-code`` answers "did anything change?" the way
``git diff --exit-code`` does, and ``--comment`` writes the report as
Markdown for a pull request, as ``import:terraform --comment`` does for a plan.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

from .options import add_export_options

__all__ = ["load_any", "main"]


def load_any(path: Path):
    """A document from a .infragram.json, a diagram file, or an exported page
    or picture that carries one."""
    from ...exports import ExportError
    from ...exports.carry import carried_document
    from ...projects import CloudProject
    from .compose import project_from_spec

    suffix = path.suffix.casefold()
    if suffix == ".py":
        return project_from_spec(path)
    if suffix in (".svg", ".png", ".html", ".htm"):
        payload = carried_document(path)
        if payload is None:
            raise ExportError(f"{path} carries no document")
        return CloudProject.model_validate(payload)
    return CloudProject.load(path)


def main(argv: list[str] | None = None) -> int:
    from pydantic import ValidationError

    from ...compose import ComposeError
    from ...exports import ExportError
    from ...review.diff import diff_comment, diff_json, diff_projects
    from .export_project import run_export
    from .import_estate import shown

    parser = argparse.ArgumentParser(
        prog="infragram diff",
        description="What changed between two versions of a diagram: elements and wires added, "
        "changed and removed, written out and drawn on the second with the marks a "
        "Terraform plan uses. Either side may be a .infragram.json, a diagram file, "
        "or an exported page or picture that carries its document.",
        epilog="exit status: 0 done; 1 the picture failed --verify; 2 a version could not be "
        "read or the picture could not be written (a mistyped option is 2 as well). With "
        "--exit-code: 0 the versions are the same, 1 they differ, 2 any error, a picture "
        "that fails --verify included.",
    )
    parser.add_argument("before", type=Path, help="the earlier version")
    parser.add_argument("after", type=Path, help="the later version")
    parser.add_argument(
        "--report-only", action="store_true", help="print what changed; draw nothing"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print what changed as one JSON document (elements added, changed and removed "
        "with ids and each changed field's two values, wires added and removed) and nothing "
        "else on stdout; what the export writes goes to stderr; still draws unless --report-only",
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="exit 1 when the versions differ and 0 when they are the same, as "
        "`git diff --exit-code` does; an error exits 2",
    )
    parser.add_argument(
        "--comment",
        type=Path,
        default=None,
        metavar="FILE",
        help="also write what changed as Markdown for a pull request comment",
    )
    add_export_options(parser, libraries="drawn")
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        before, after = load_any(options.before), load_any(options.after)
    except (ExportError, ComposeError, ValidationError, ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    difference = diff_projects(before, after)
    # with --json, stdout is the JSON document alone: every other line goes to stderr
    said = sys.stderr if options.json else sys.stdout
    if options.json:
        print(json.dumps(diff_json(difference), ensure_ascii=False, indent=2))
    else:
        print(difference.report())
    if options.comment is not None:
        text = diff_comment(difference, before=shown(options.before), after=shown(options.after))
        from ...exports.written import write_side_file

        try:
            write_side_file(options.comment, text, force=options.force)
        except (OSError, ValueError) as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 2
        print(f"COMMENT  {options.comment}", file=said)
    status = 0
    if not options.report_only:
        project = difference.project
        project.slug = f"{after.slug}-diff"
        with contextlib.redirect_stdout(said):
            status = run_export(project, options)
    if not options.exit_code:
        return status
    # 1 is taken by "they differ": a picture that failed --verify is an error like the rest
    if status:
        return 2
    return 0 if difference.identical else 1
