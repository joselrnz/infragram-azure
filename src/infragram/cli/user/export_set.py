"""``infragram export:set``: every diagram in a folder, one folder per diagram.

A set is a folder of diagrams that belong together -- the views of one
estate, a snapshot taken on one day: ``*.py`` diagram files, ``*.infragram.json``
documents, or both. Each diagram gets a folder of its own, beside the sources
or under ``--output-dir``::

    <output>/
      README.md                  what is here, and how to rebuild it
      <slug>/
        <slug>.py                a copy of the source, beside what it drew
        <slug>.html              the editor page
        <slug>.svg
        <slug>.png

``--formats``, ``--prices`` and the other export options are the ones
``compose`` takes, and mean the same; a diagram file's saved layout
(``<name>.layout.json``, from ``layout:save``) is put back as ``compose`` puts
it, and travels with the copy. The set draws both looks and checks every file
it writes; ``--jobs`` draws several diagrams at once.

The specs themselves are never moved or changed. Every spec is run before
anything is written, so two specs drawing the same slug, or a file that
closes no diagram, stop the set up front. Each diagram is checked in both
looks, and each page is rendered several times and compared when a browser
is available. Nothing is replaced without ``--force``.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ...paths import bundled_plugin
from ..version import package_version
from .options import (
    add_export_options,
    apply_render_settings,
    export_keywords,
    price_flags,
    with_overrides,
)

__all__ = ["build_parser", "main", "specs_in"]

#: What one diagram's folder can hold, in the order the README lists them:
#: the spec's copy, then the export's files and Terraform folders.
ARTIFACTS = (
    "py",
    "template",
    "html",
    "svg",
    "png",
    "svg_icons",
    "png_icons",
    "terraform",
    "terraform_modules",
)
_CHECKS = re.compile(r"(\d+) checks")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infragram export:set",
        description="Export every diagram spec in a folder, one folder per diagram, "
        "and write the set's README.",
    )
    parser.add_argument(
        "folder",
        type=Path,
        help="the folder holding the diagrams: *.py diagram files and *.infragram.json documents",
    )
    add_export_options(
        parser,
        libraries="drawn",
        output_dir=None,
        output_help="where the diagram folders and the README go (default: the specs' own folder)",
        display="both",
        verify=False,
        title=False,
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        metavar="N",
        help="diagrams drawn at once, each in its own browser (default 1)",
    )
    parser.add_argument(
        "--passes",
        type=int,
        default=3,
        metavar="N",
        help="renders to compare per page (default 3); 0 skips the render gate",
    )
    return parser


_DOCUMENT = ".infragram.json"


def _stem(path: Path) -> str:
    """``shop.py`` and ``shop.infragram.json`` are both ``shop``."""
    return path.name[: -len(_DOCUMENT)] if path.name.endswith(_DOCUMENT) else path.stem


def specs_in(folder: Path, output: Path) -> list[Path]:
    """The diagrams to export: the ``*.py`` diagram files and ``*.infragram.json``
    documents in the folder (names starting with ``_`` are helpers), or, when
    there are none, the copies an earlier run filed beside its pictures."""
    loose = sorted(
        path
        for path in (*folder.glob("*.py"), *folder.glob(f"*{_DOCUMENT}"))
        if not path.name.startswith("_")
    )
    if loose:
        return loose
    return sorted(
        path
        for path in (*output.glob("*/*.py"), *output.glob(f"*/*{_DOCUMENT}"))
        if _stem(path) == path.parent.name
    )


def _load(spec: Path):
    """The document a source describes, with a diagram file's saved layout put
    back as ``compose`` puts it; and that layout file, when there is one."""
    from ...projects import CloudProject
    from .compose import project_from_spec

    if spec.name.endswith(_DOCUMENT):
        return CloudProject.load(spec), None
    from ...compose.layout_file import apply_layout, layout_path

    project = project_from_spec(spec)
    sidecar = layout_path(spec)
    if not sidecar.is_file():
        return project, None
    for note in apply_layout(project, sidecar):
        print(f"NOTE     {spec.name}: {note}", file=sys.stderr)
    return project, sidecar


def _rebuild_flags(options: argparse.Namespace) -> list[str]:
    """The options a rebuild needs to draw the set the same way: every one
    that differs from its default, in the order --help lists them."""
    flags = [f"--theme {options.theme}", f"--scale {options.scale:g}"]
    defaults = [
        ("libraries", "drawn"),
        ("display", "both"),
        ("write_looks", "both"),
        ("background", "paper"),
        ("drawio_icons", "native"),
        ("size", "fit"),
        ("renderer", "editor"),
        ("routing", "around"),
    ]
    for name, default in defaults:
        value = getattr(options, name)
        if value != default:
            flags.append(f"--{name.replace('_', '-')} {value}")
    flags += price_flags(options.prices)
    if options.terraform_zip:
        flags.append("--terraform-zip")
    if not options.embed:
        flags.append("--no-embed")
    if options.infracost:
        flags.append(f"--infracost {_quoted(options.infracost.as_posix())}")
    if options.status is not None:
        flags.append(f'--status "{options.status}"')
    if options.offline:
        flags.append("--offline")
    if options.timeout is not None:
        flags.append(f"--timeout {options.timeout:g}")
    if options.passes != 3:
        flags.append(f"--passes {options.passes}")
    if options.jobs != 1:
        flags.append(f"--jobs {options.jobs}")
    return flags


def _render_gate(page: Path, passes: int, theme: str) -> tuple[bool | None, str]:
    """Render ``page`` ``passes`` times in both looks and compare the passes.
    None, with the reason, when no browser can draw here."""
    from ...exports import browser_missing
    from .render_gate import check_sources

    missing = browser_missing()
    if missing:
        return None, f"render gate not run: {missing}"
    lines: list[str] = []
    ok = check_sources([page], passes=passes, display="both", theme=theme, echo=lines.append)
    return ok, "; ".join(line.strip() for line in lines if line.strip())


def _runner() -> str:
    """How the reader runs the command again: through the skill's launcher when
    this copy runs from a plugin folder or a checkout, where the skill sits
    beside the package, else the ``infragram`` command an installed copy puts
    on the PATH. ``<skill>`` is the skill's folder, as the skill's own
    documents write it; a machine's own path never goes into the README."""
    return 'python "<skill>/scripts/infragram.py"' if bundled_plugin() is None else "infragram"


def _quoted(path: str) -> str:
    """A path as a shell reads it back: quoted when it holds a space or a quote."""
    if path and not any(char in path for char in " \t\"'&|;()<>"):
        return path
    return '"' + path.replace('"', '\\"') + '"'


#: The first line of a README export:set writes, so a rebuild knows the page is its own.
README_MARK = "<!-- written by infragram export:set; rebuilt on every run -->"


def _ours(readme: Path) -> bool:
    """Whether export:set wrote *readme* (a set built before the mark carries
    its own rebuild section)."""
    try:
        text = readme.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return README_MARK in text or (
        "## Rebuilding" in text and "export:set" in text and "drawn with infragram" in text
    )


def _readme(output: Path, rows: list[dict], command: str, gate: str) -> Path:
    """The set's own page: what is here, and the one command that rebuilds it."""
    drawn = next((row["drawn"] for row in rows if row["drawn"]), "")
    status = next((row["status"] for row in rows if row["status"]), "")
    lines = [
        README_MARK,
        f"# {output.resolve().name}",
        "",
        f"**Status:** {status or 'not stated'}  ",
        f"**Date:** {drawn or 'not stated'}",
        "",
        f"{len(rows)} diagram{'s' if len(rows) != 1 else ''}, drawn with infragram "
        f"{package_version()}.",
        "Each folder holds a copy of the spec that drew the picture beside the picture itself.",
        "",
    ]
    for row in rows:
        lines += [
            f"## {row['title']}",
            "",
            f"`{row['slug']}/`",
            "",
            f"- **Status:** {row['status'] or 'not stated'}",
        ]
        if row["notes"]:
            lines.append("- **Notes:** " + " · ".join(row["notes"]))
        lines += [
            f"- **Drawn:** {row['drawn'] or 'not stated'}",
            f"- **Checks:** {row['checks']}",
            "- **Files:** "
            + ", ".join(f"`{name}` ({size // 1024} KB)" for name, size in row["files"]),
            "",
        ]
    lines += [
        "## Rebuilding",
        "",
        "```bash",
        command,
        "```",
        "",
        "Every text file is written LF, so a rebuild on any platform is byte-identical. " + gate,
        "",
    ]
    readme = output / "README.md"
    readme.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return readme


def _refuse(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    from pydantic import ValidationError

    from ...compose import ComposeError, export
    from ...exports import ExportError
    from .checker import checker
    from .export_project import planned_formats, price_for_export

    options = build_parser().parse_args(argv)
    if getattr(options, "view", None):
        print(
            "ERROR: export:set draws whole diagrams; draw a view with compose or "
            "export:project --view",
            file=sys.stderr,
        )
        return 2
    folder: Path = options.folder
    if not folder.is_dir():
        return _refuse(f"not a folder: {folder}")
    if options.passes < 0:
        return _refuse("--passes cannot be negative")
    if options.jobs < 1:
        return _refuse("--jobs is at least 1")
    try:
        apply_render_settings(options)
    except ValueError as error:
        return _refuse(str(error))
    output: Path = options.output_dir or folder
    specs = specs_in(folder, output)
    if not specs:
        return _refuse(f"no diagrams (*.py or *{_DOCUMENT}) in {folder}")

    # Every source is read before anything is written: a set that cannot
    # finish stops here, with the whole folder as it was.
    loaded = []
    for spec in specs:
        try:
            project, sidecar = _load(spec)
        except (ExportError, ComposeError, ValidationError, ValueError, OSError) as error:
            return _refuse(f"{spec.name}: {error}")
        loaded.append((spec, spec.read_bytes(), with_overrides(project, options), sidecar))
    by_slug: dict[str, list[str]] = defaultdict(list)
    for spec, _, project, _ in loaded:
        by_slug[project.slug].append(spec.name)
    clashes = {slug: names for slug, names in by_slug.items() if len(names) > 1}
    if clashes:
        return _refuse(
            "two specs draw the same diagram, and each diagram needs a folder of "
            "its own; give them different titles or slugs: "
            + "; ".join(f"{slug} <- {', '.join(names)}" for slug, names in sorted(clashes.items()))
        )
    taken = sorted(
        str(output / project.slug)
        for _, _, project, _ in loaded
        if (output / project.slug).exists()
    )
    if taken and not options.force:
        return _refuse(f"refusing to replace {', '.join(taken)}; pass --force")
    # the folder's own README (the specs' folder is the default output) is
    # the user's until a set wrote it
    readme = output / "README.md"
    if readme.exists() and not options.force and not _ours(readme):
        return _refuse(
            f"refusing to replace {readme}, which export:set did not write; "
            "pass --force, or --output-dir another folder"
        )

    formats, notes = planned_formats(options)
    for note in notes:
        print(f"NOTE     {note}", file=sys.stderr)
    output.mkdir(parents=True, exist_ok=True)
    check = checker().check_path
    rows: list[dict] = []
    clean = True
    gate_ran = False
    keywords = export_keywords(options)

    def draw(item):
        """One diagram into its own folder: the source's copy (and its saved
        layout) beside the export. What went wrong comes back, not raised, so
        every diagram drawn at once is accounted for."""
        spec, source, project, sidecar = item
        target = output / project.slug
        previous = target.with_name(f".{project.slug}.previous")
        if target.exists():
            if previous.exists():
                shutil.rmtree(previous)
            target.rename(previous)
        try:
            priced = price_for_export(project, options)
            target.mkdir(parents=True)
            suffix = _DOCUMENT if spec.name.endswith(_DOCUMENT) else ".py"
            carried = target / f"{project.slug}{suffix}"
            carried.write_bytes(source)
            if sidecar is not None:
                from ...compose.layout_file import layout_path

                shutil.copyfile(sidecar, layout_path(carried))
            result = export(
                project, target, formats=formats, overwrite=True, check=check, **keywords
            )
        except (ExportError, ComposeError, OSError, ValueError) as error:
            shutil.rmtree(target, ignore_errors=True)
            if previous.exists():
                previous.rename(target)
            return spec, project, None, [], None, f"{spec.name}: {error}"
        shutil.rmtree(previous, ignore_errors=True)
        return spec, project, carried, priced, result, None

    if options.jobs > 1 and len(loaded) > 1:
        with ThreadPoolExecutor(max_workers=options.jobs) as pool:
            drawn = list(pool.map(draw, loaded))
    else:
        drawn = []
        for item in loaded:
            drawn.append(draw(item))
            if drawn[-1][-1] is not None:
                break  # one at a time, the set stops at its first failure
    failed = [message for *_, message in drawn if message is not None]
    if failed:
        for message in failed[1:]:
            print(f"ERROR: {message}", file=sys.stderr)
        return _refuse(failed[0])

    for _spec, project, carried, priced, result, _ in drawn:
        assert carried is not None and result is not None

        checks = 0
        for name, ok, message in result.checks:
            print(message if name in message else f"{message} [{name}]")
            clean = clean and ok
            found = _CHECKS.search(message)
            if found:
                checks = max(checks, int(found.group(1)))
        for note in (*priced, *result.notes):
            print(f"NOTE     {note}", file=sys.stderr)
        if options.passes and result.html is not None:
            passed, message = _render_gate(result.html, options.passes, options.theme)
            if passed is None:
                print(f"NOTE     {result.html.name}: {message}", file=sys.stderr)
            else:
                gate_ran = True
                print(
                    ("OK   " if passed else "FAIL ")
                    + f"{result.html.name} rendered {options.passes}x: {message}"
                )
                clean = clean and passed

        files = [(carried.name, carried.stat().st_size)]
        for kind in ARTIFACTS[1:]:
            path = getattr(result, kind)
            if path is None or not path.exists() or path == carried:
                continue
            if path.is_dir():
                files.append(
                    (
                        f"{path.name}/",
                        sum(item.stat().st_size for item in path.rglob("*") if item.is_file()),
                    )
                )
            else:
                files.append((path.name, path.stat().st_size))
        rows.append(
            {
                "slug": project.slug,
                "title": project.title,
                "status": project.presentation.status,
                "notes": list(project.presentation.notes),
                "drawn": project.presentation.drawn,
                "checks": checks,
                "files": files,
            }
        )

    command = " ".join(
        [_runner(), "export:set", _quoted(folder.as_posix())]
        + ([f"--output-dir {_quoted(options.output_dir.as_posix())}"] if options.output_dir else [])
        + ([f"--formats {options.formats}"] if options.formats else [])
        + _rebuild_flags(options)
        + ["--force"]
    )
    gate = (
        f"Each page was rendered {options.passes} times in both looks and the passes compared."
        if gate_ran
        else "The render gate did not run for this build."
    )
    readme = _readme(output, rows, command, gate)
    total = sum(size for row in rows for _, size in row["files"]) + readme.stat().st_size
    file_count = sum(len(row["files"]) for row in rows) + 1
    print(
        f"SET      {output} | {len(rows)} diagram{'s' if len(rows) != 1 else ''} | "
        f"{file_count} files | {total // 1024} KB"
    )
    print(f"README   {readme}")
    if not clean:
        print("ERROR: the set did not pass verification", file=sys.stderr)
        return 1
    return 0
