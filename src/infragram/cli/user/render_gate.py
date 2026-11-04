"""``infragram verify:render``: render a diagram several times and prove the
picture is right and repeatable.

Three questions, each answered by evidence rather than by trust:

1. **Deterministic.** The page is rendered ``--passes`` times (three by
   default) in a fresh browser each time, and every pass must be
   byte-identical to the first. Same document, same picture, every time.
2. **Correct.** The shipped checker reads the final SVG the way an eye
   would: wires orthogonal, no wire through text, a glyph, a frame title or
   a card it does not belong to, no caption on another caption, everything
   inside the picture, and -- with the document known -- every connection
   drawn once with the arrowheads and line kind it asked for.
3. **Honest.** Every component the document names exists in an installed
   library. Nothing is drawn that the catalogs do not ship.

The exit status is 0 only when every question is answered yes for every input.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
from collections.abc import Callable
from html import unescape
from pathlib import Path

from .options import DISPLAYS, THEMES

__all__ = ["build_parser", "check_sources", "known_ids", "main", "page_for", "page_for_look"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infragram verify:render",
        description="Render a diagram several times, prove the passes identical, "
        "and check the picture.",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        type=Path,
        metavar="SOURCE",
        help="exported pages or .infragram.json documents",
    )
    parser.add_argument(
        "--passes",
        type=int,
        default=3,
        metavar="N",
        help="independent renders to compare (default 3)",
    )
    parser.add_argument(
        "--display",
        choices=DISPLAYS,
        default="both",
        help="which looks to render and check (default: both)",
    )
    parser.add_argument(
        "--theme",
        choices=THEMES,
        default="light",
        help="theme the passes are drawn in (default: light)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="keep the rendered SVGs here (default: a temporary directory)",
    )
    return parser


def page_for(source: Path, workdir: Path):
    """An HTML page to render, exporting a project document first if needed."""
    from ...exports import export_project
    from ...projects import CloudProject

    if source.suffix.casefold() in (".html", ".htm"):
        return source, None
    project = CloudProject.load(source)
    result = export_project(project, workdir / "page", formats=("html",), overwrite=True)
    assert result.html is not None
    return result.html, project


def page_for_look(project, page: Path, look: str | None, workdir: Path) -> Path:
    """The page to capture for ``look``: the given page when it already draws
    that way, else a fresh export of the document with that display, so the
    layout is made for the look rather than resized into it.

    The document's own display counts as already drawing that way: the
    saved editor geometry lives on that page, and ``look_variant`` would drop
    it, so re-exporting it would check a layout the author never placed."""
    from ...exports import export_project, look_variant

    if project is None or look in (None, "project", project.presentation.display):
        return page
    variant = look_variant(project, look)
    result = export_project(variant, workdir / f"look-{look}", formats=("html",), overwrite=True)
    assert result.html is not None
    return result.html


def known_ids() -> set[str]:
    """Every ``provider:service`` the installed libraries draw."""
    from ...catalog import load_default_provider_registry, load_provider_component_catalog
    from ...catalog.specs import ARCHITECTURE_BOUNDARY_SPECS
    from ...compose import shared_service_ids

    known = {f"infragram:{service}" for service in shared_service_ids()}
    known |= {f"infragram:{spec[0]}" for spec in ARCHITECTURE_BOUNDARY_SPECS}
    for provider_id in load_default_provider_registry().by_id:
        for component in load_provider_component_catalog(provider_id).components:
            known.add(f"{provider_id}:{component.service_id}")
    return known


def _honest(project, known: set[str]) -> list[str]:
    problems = []
    for element in project.topology.walk():
        if element.component is None:
            continue
        ref = f"{element.component.provider}:{element.component.service_id}"
        if ref not in known:
            problems.append(f"{element.name!r} names {ref}, which no installed library ships")
    return problems


def _embedded_project(page: Path):
    """The document an exported page carries, or None."""
    from ...exports.carry import page_document
    from ...projects import CloudProject

    embedded = page_document(page.read_text(encoding="utf-8"))
    if not embedded:
        return None
    for raw in (embedded, unescape(embedded)):
        try:
            return CloudProject.model_validate_json(raw)
        except Exception:  # noqa: BLE001, S112 - the checker reports malformed documents itself
            continue
    return None


def _verify(
    source: Path,
    *,
    passes: int,
    display: str,
    theme: str,
    output_dir: Path | None,
    workdir: Path,
    checker,
    known: set[str],
    echo: Callable[[str], None],
) -> list[str]:
    from ...exports import ExportError, playwright_svg_renderer

    findings: list[str] = []
    page, project = page_for(source, workdir)
    if project is None:
        project = _embedded_project(page)
    if project is not None:
        findings += [f"honesty: {problem}" for problem in _honest(project, known)]

    # None is the look the document itself asks for
    looks_by_display: dict[str, list[str | None]] = {
        "project": [None],
        "card": ["card"],
        "icon": ["icon"],
        "both": ["card", "icon"],
    }
    looks = looks_by_display[display]
    for look in looks:
        name = f"{source.stem.replace('.infragram', '')}{'-' + look if look else ''}"
        look_page = page_for_look(project, page, look, workdir)
        digests: list[str] = []
        final: Path | None = None
        for index in range(1, passes + 1):
            output = workdir / f"{name}.pass{index}.svg"
            try:
                playwright_svg_renderer(look_page, output, theme=theme, display=look)
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
                f"{name}: {passes} renders produced {len(distinct)} different "
                "pictures; the export is not deterministic"
            )
        errors: list[str] = []
        summary = checker.check_svg(
            final.read_text(encoding="utf-8"),
            errors,
            project.model_dump(mode="json") if project is not None else None,
        )
        findings += [f"{name}: {error}" for error in errors]
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / f"{name}.svg").write_bytes(final.read_bytes())
        status = "OK  " if not errors and len(distinct) == 1 else "FAIL"
        passes_text = f"{passes} identical passes" if len(distinct) == 1 else "passes differ"
        echo(
            f"{status} {source.name} [{look or 'project'}]: {passes_text} "
            f"| {summary['nodes']} components, {summary['frames']} frames, "
            f"{summary['connectors']} connectors, {summary['labels']} captions, "
            f"{summary['checks']} checks"
            + (f", matched to {summary['project']}" if summary.get("project") else "")
        )
    return findings


def check_sources(
    sources: list[Path],
    *,
    passes: int = 3,
    display: str = "both",
    theme: str = "light",
    output_dir: Path | None = None,
    echo: Callable[[str], None] = print,
) -> bool:
    """Render and check every source; ``echo`` receives one line per look and
    one per finding. True when every source held still and checked clean."""
    from ...exports import ExportError
    from .checker import checker as load_checker

    checker = load_checker()
    # One source of truth for "does this component exist": the shipped
    # inventory the checker reads, with the catalogs as the fallback for a
    # checkout whose inventory is missing.
    known = checker.known_components() or known_ids()
    clean = True
    with tempfile.TemporaryDirectory(prefix="infragram-verify-") as temp:
        workdir = Path(temp)
        for source in sources:
            if not source.is_file():
                echo(f"FAIL {source}: not found")
                clean = False
                continue
            try:
                findings = _verify(
                    source,
                    passes=passes,
                    display=display,
                    theme=theme,
                    output_dir=output_dir,
                    workdir=workdir,
                    checker=checker,
                    known=known,
                    echo=echo,
                )
            except (ExportError, OSError, ValueError) as error:
                echo(f"FAIL {source}: {error}")
                clean = False
                continue
            for finding in findings:
                echo(f"  - {finding}")
            clean = clean and not findings
    return clean


def main(argv: list[str] | None = None) -> int:
    options = build_parser().parse_args(argv)
    if options.passes < 1:
        print("ERROR: --passes must be at least 1", file=sys.stderr)
        return 2
    clean = check_sources(
        options.sources,
        passes=options.passes,
        display=options.display,
        theme=options.theme,
        output_dir=options.output_dir,
    )
    return 0 if clean else 1
