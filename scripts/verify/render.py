#!/usr/bin/env python3
"""Render a diagram several times and prove the picture is right and repeatable.

Three questions, each answered by evidence rather than by trust:

1. **Deterministic.** The page is rendered ``--passes`` times (three by
   default) in a fresh browser each time, and every pass must be
   byte-identical to the first. Same document, same picture, every time.
2. **Correct.** The shipped checker reads the final SVG the way an eye
   would: wires orthogonal, no wire through text, a glyph, a frame title or
   a card it does not belong to, no caption on another caption, everything
   inside the picture, and -- with the document beside it -- every
   connection drawn once with the arrowheads and line kind it asked for.
3. **Honest.** Every component the document names exists in an installed
   library. Nothing is drawn that the catalogs do not ship.

Usage::

    python -m infragram verify:render <page.html | project.infragram.json>... \\
        [--passes 3] [--display project|card|icon|both] [--theme light|dark] \\
        [--output-dir <dir>]

Exit status is 0 only when every question is answered yes for every input.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))

from infragram.catalog import load_provider_component_catalog  # noqa: E402
from infragram.catalog.specs import ARCHITECTURE_BOUNDARY_SPECS  # noqa: E402
from infragram.compose import shared_service_ids  # noqa: E402
from infragram.exports import (  # noqa: E402
    ExportError,
    export_project,
    look_variant,
    playwright_svg_renderer,
)
from infragram.projects import CloudProject  # noqa: E402

CHECKER = ROOT / "skills" / "infragram-azure" / "scripts" / "project_check.py"


def load_checker():
    """The shipped, stdlib-only checker, imported by path so the same code
    that ships in the skill judges the picture here."""
    spec = importlib.util.spec_from_file_location("project_check", CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("sources", nargs="+", type=Path, help="exported pages or project documents")
    parser.add_argument(
        "--passes", type=int, default=3, help="independent renders to compare (default 3)"
    )
    parser.add_argument(
        "--display",
        choices=("project", "card", "icon", "both"),
        default="both",
        help="which looks to render and check (default: both)",
    )
    parser.add_argument("--theme", choices=("light", "dark"), default="light")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="keep the rendered SVGs here (default: a temporary directory)",
    )
    return parser


def page_for(source: Path, workdir: Path) -> tuple[Path, CloudProject | None]:
    """An HTML page to render, exporting a project document first if needed."""
    if source.suffix.casefold() in (".html", ".htm"):
        return source, None
    project = CloudProject.load(source)
    result = export_project(project, workdir / "page", formats=("html",), overwrite=True)
    assert result.html is not None
    return result.html, project


def page_for_look(
    project: CloudProject | None, page: Path, look: str | None, workdir: Path
) -> Path:
    """The page to capture for ``look``: the given page when it already draws
    that way, else a fresh export of the document with that display, so the
    layout is made for the look rather than resized into it.

    The document's own display counts as already drawing that way. Without
    that arm a re-export replaced the page for every look, and
    ``look_variant`` drops the saved editor geometry, so the layout the
    author actually placed was never the one checked."""
    if project is None or look in (None, "project", project.presentation.display):
        return page
    variant = look_variant(project, look)
    result = export_project(variant, workdir / f"look-{look}", formats=("html",), overwrite=True)
    assert result.html is not None
    return result.html


def known_ids() -> set[str]:
    """Every ``provider:service`` the installed libraries draw."""
    from infragram.catalog import load_default_provider_registry

    known = {f"infragram:{service}" for service in shared_service_ids()}
    known |= {f"infragram:{spec[0]}" for spec in ARCHITECTURE_BOUNDARY_SPECS}
    for provider_id in load_default_provider_registry().by_id:
        for component in load_provider_component_catalog(provider_id).components:
            known.add(f"{provider_id}:{component.service_id}")
    return known


def honest(project: CloudProject, known: set[str]) -> list[str]:
    problems = []
    for element in project.topology.walk():
        if element.component is None:
            continue
        ref = f"{element.component.provider}:{element.component.service_id}"
        if ref not in known:
            problems.append(f"{element.name!r} names {ref}, which no installed library ships")
    return problems


def verify(
    source: Path, options: argparse.Namespace, workdir: Path, checker, known: set[str]
) -> list[str]:
    findings: list[str] = []
    page, project = page_for(source, workdir)
    if project is None:
        embedded = checker.EMBEDDED_PROJECT.search(page.read_text(encoding="utf-8"))
        if embedded:
            from html import unescape

            raw = embedded.group(1)
            try:
                project = CloudProject.model_validate_json(raw)
            except Exception:  # noqa: BLE001 - the checker reports malformed documents itself
                try:
                    project = CloudProject.model_validate_json(unescape(raw))
                except Exception:  # noqa: BLE001
                    project = None
    if project is not None:
        findings += [f"honesty: {problem}" for problem in honest(project, known)]

    by_display: dict[str, list[str | None]] = {
        "project": [None],
        "card": ["card"],
        "icon": ["icon"],
        "both": ["card", "icon"],
    }
    looks = by_display[options.display]
    for look in looks:
        name = f"{source.stem.replace('.infragram', '')}{'-' + look if look else ''}"
        look_page = page_for_look(project, page, look, workdir)
        digests: list[str] = []
        final: Path | None = None
        for index in range(1, options.passes + 1):
            output = workdir / f"{name}.pass{index}.svg"
            try:
                playwright_svg_renderer(look_page, output, theme=options.theme, display=look)
            except ExportError as error:
                findings.append(f"{name}: pass {index} could not render: {error}")
                break
            digests.append(hashlib.sha256(output.read_bytes()).hexdigest())
            final = output
        if final is None:
            continue
        distinct = sorted(set(digests))
        if len(distinct) != 1:
            findings.append(
                f"{name}: {options.passes} renders produced {len(distinct)} different pictures; "
                "the export is not deterministic"
            )
        errors: list[str] = []
        summary = checker.check_svg(
            final.read_text(encoding="utf-8"),
            errors,
            project.model_dump(mode="json") if project is not None else None,
        )
        findings += [f"{name}: {error}" for error in errors]
        keep = (options.output_dir / f"{name}.svg") if options.output_dir else None
        if keep is not None:
            keep.parent.mkdir(parents=True, exist_ok=True)
            keep.write_bytes(final.read_bytes())
        status = "OK  " if not errors and len(distinct) == 1 else "FAIL"
        print(
            f"{status} {source.name} [{look or 'project'}]: {options.passes} identical passes"
            if len(distinct) == 1
            else f"{status} {source.name} [{look or 'project'}]: passes differ",
            f"· {summary['nodes']} components, {summary['frames']} frames, "
            f"{summary['connectors']} connectors, {summary['labels']} captions, "
            f"{summary['checks']} checks"
            + (f", matched to {summary['project']}" if summary.get("project") else ""),
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)
    if options.passes < 1:
        print("ERROR: --passes must be at least 1", file=sys.stderr)
        return 2
    checker = load_checker()
    # One source of truth for "does this component exist": the shipped
    # inventory the checker reads. The catalog-derived set is the fallback for
    # a checkout whose inventory is missing.
    known = checker.known_components() or known_ids()
    failed = False
    with tempfile.TemporaryDirectory(prefix="infragram-verify-") as temp:
        workdir = Path(temp)
        for source in options.sources:
            if not source.is_file():
                print(f"FAIL {source}: not found")
                failed = True
                continue
            try:
                findings = verify(source, options, workdir, checker, known)
            except (ExportError, OSError, ValueError) as error:
                print(f"FAIL {source}: {error}")
                failed = True
                continue
            for finding in findings:
                print(f"  - {finding}")
            failed = failed or bool(findings)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
