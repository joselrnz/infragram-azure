"""Writing a project's artifacts, all derived from one HTML render.

Template, HTML, SVG and PNG come from a single canonical render, which is what
keeps geometry, typography and accessibility from drifting between them. A
*look* -- cards or icons -- is a laid-out document rather than a switch on a
finished page, so each look that differs from the document's own is rendered
from a copy whose presentation says so. The Terraform skeleton is read from
the document, not the picture (:mod:`infragram.terraform`).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from ..builders.architecture import load_theme
from ..projects import CloudProject
from . import written
from .browser import (
    EXPORT_ROUTINGS,
    EXPORT_THEMES,
    browser_missing,
    playwright_png_renderer,
    playwright_static_png_renderer,
    playwright_svg_renderer,
    playwright_svg_to_png,
)
from .errors import ExportError
from .framing import frame_size, frame_svg
from .palette import dark as dark_theme
from .render import (
    EXPORT_LIBRARIES,
    look_variant,
    render_project_html,
    render_project_svg,
)
from .svg import (
    DEFAULT_EXPORT_BACKGROUND,
    extract_svg,
    finish_standalone_svg,
    resolve_background,
)

__all__ = [
    "EXPORT_DISPLAYS",
    "EXPORT_FORMATS",
    "EXPORT_RENDERERS",
    "ExportResult",
    "PngRenderer",
    "SvgRenderer",
    "export_many",
    "export_project",
    "export_project_async",
]


#: Every format an export can write, in the order the command line lists them;
#: ``terraform`` is the modular skeleton the diagram describes, in
#: ``<slug>-terraform/``, and ``terraform-modules`` the same through the public
#: registry's modules, in ``<slug>-terraform-modules/``; ``drawio`` is a draw.io
#: file (exports/drawio.py).
EXPORT_FORMATS = ("template", "html", "svg", "png", "drawio", "terraform", "terraform-modules")
_SUPPORTED_FORMATS = frozenset(EXPORT_FORMATS)
#: What draws the SVG and PNG: the editor runtime in a browser (falling back
#: to the static renderer, with a note, when it cannot), or the static
#: renderer on purpose.
EXPORT_RENDERERS = ("editor", "static")
#: The formats drawn from the HTML render.
_DRAWN = frozenset({"html", "svg", "png", "svg_icons", "png_icons"})


@dataclass(frozen=True, slots=True)
class ExportResult:
    template: Path | None = None
    html: Path | None = None
    svg: Path | None = None
    png: Path | None = None
    #: The draw.io file, ``<slug>.drawio`` (exports/drawio.py).
    drawio: Path | None = None
    #: The icon-display variants ``display="both"`` writes beside the cards,
    #: named ``<slug>-icons.svg`` and ``<slug>-icons.png``.
    svg_icons: Path | None = None
    png_icons: Path | None = None
    #: The Terraform skeleton's folder, ``<slug>-terraform/``.
    terraform: Path | None = None
    #: The skeleton through the registry's modules, ``<slug>-terraform-modules/``.
    terraform_modules: Path | None = None
    #: Anything the caller should relay, such as an SVG that fell back to the
    #: static layout because no browser was available.
    notes: tuple[str, ...] = ()
    #: What ``check`` said about each file it read: ``(name, passed, message)``.
    #: The look ``display="both"`` draws only to check is listed too, though
    #: it is not written.
    checks: tuple[tuple[str, bool, str], ...] = ()


PngRenderer = Callable[..., None]


SvgRenderer = Callable[..., None]


#: How the components draw in SVG and PNG. ``project`` follows the document's
#: own ``presentation.display``; ``card`` and ``icon`` force one look;
#: ``both`` writes the cards under the plain names and the icons beside them.
EXPORT_DISPLAYS = ("project", "card", "icon", "both")


def _accepts_display(renderer: Callable[..., None]) -> bool:
    import inspect

    parameters = inspect.signature(renderer).parameters
    return "display" in parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
    )


def _check_renderer(renderer: Callable[..., None], display: str | None) -> None:
    """Refuse, before anything is written, a renderer that cannot draw ``display``.

    The Playwright renderers take it. A caller's injected fake usually has
    the old three-argument shape, and asking it for icons it cannot draw
    would be a silent wrong picture, so that is a caller error raised up
    front rather than something the fallback path papers over.
    """
    if display not in (None, "project") and not _accepts_display(renderer):
        raise ExportError(
            f"the injected renderer {getattr(renderer, '__name__', renderer)!r} cannot "
            f"draw display={display!r}; it takes no display argument"
        )


def _call_renderer(renderer: Callable[..., None], *args, display: str | None) -> None:
    """Call a renderer, passing ``display`` only when there is one to pass."""
    if display in (None, "project"):
        renderer(*args)
    else:
        renderer(*args, display=display)


def export_project(
    project: CloudProject,
    output_dir: Path,
    *,
    formats: Iterable[str] = ("html", "svg", "png"),
    scale: float = 3,
    png_renderer: PngRenderer | None = None,
    svg_renderer: SvgRenderer | None = None,
    theme: str = "light",
    libraries: str = "project",
    overwrite: bool = False,
    display: str = "project",
    write_looks: str = "both",
    background: str = DEFAULT_EXPORT_BACKGROUND,
    check: Callable[[Path], tuple[bool, str]] | None = None,
    embed: bool = True,
    drawio_icons: str = "native",
    size: str = "fit",
    renderer: str = "editor",
    routing: str = "around",
    terraform_zip: bool = False,
) -> ExportResult:
    """Write requested artifacts, all derived from one canonical HTML render.

    ``display`` picks how components draw in SVG and PNG: ``project`` (the
    document's own choice), ``card``, ``icon``, or ``both``. With ``both``,
    The default ``write_looks="both"`` writes the cards under the plain names
    and the icon variants as ``<slug>-icons.*``; ``"document"`` writes the
    document's own look only, and draws the other one just to ``check`` it.

    ``embed`` writes the document into every SVG and PNG (exports/carry.py),
    so ``export:project picture.png`` redraws it; False leaves them bare.

    ``check`` is called on every document, page and SVG written (the shipped
    checker's ``check_path`` fits), and its verdicts come back in
    :attr:`ExportResult.checks`. Files are drawn into a staging folder and
    moved into place only when all of them rendered, so a failure leaves the
    output folder as it was.

    ``terraform`` writes the modular skeleton the document describes to
    ``<slug>-terraform/`` (:mod:`infragram.terraform`), and
    ``terraform-modules`` the same through the public registry's modules
    where one fits, to ``<slug>-terraform-modules/``; a document that draws
    nothing on AWS, Azure or Google Cloud is refused before anything is
    written.

    SVG and PNG come from the editor runtime so both show the authored layout,
    drawn in ``theme`` (light by default: white cards and dark text). The HTML
    embeds the project's libraries by default; ``libraries="all"`` embeds every
    installed library so the provider menu can add any of them later. When no
    browser is available the SVG falls back to the static render and the
    result carries a note saying so.

    ``size`` places the SVG and PNG on the canvas a size preset names
    (``slide-16x9``, ``social-og`` ...), the drawing centred and scaled to fit
    (:mod:`.framing`); ``fit``, the default, crops them to the drawing.
    ``renderer="static"`` draws them with the static renderer on purpose,
    with no browser for the SVG and no note, where ``editor`` (the default)
    falls back to it only when the runtime cannot. ``routing="direct"`` draws
    the wires straight from port to port, as the editor's routing switch
    does, instead of around the cards. ``terraform_zip`` writes each
    Terraform skeleton as ``<slug>-terraform.zip``, laid out as the page's
    Download menu gives it, instead of a folder.
    """

    canvas = frame_size(size)
    if renderer not in EXPORT_RENDERERS:
        raise ExportError(f"unknown renderer {renderer!r}; use {', '.join(EXPORT_RENDERERS)}")
    if routing not in EXPORT_ROUTINGS:
        raise ExportError(f"unknown routing {routing!r}; use {', '.join(EXPORT_ROUTINGS)}")
    if theme not in EXPORT_THEMES:
        raise ExportError(f"unknown export theme {theme!r}; use {', '.join(EXPORT_THEMES)}")
    # The ground is the theme's own paper, which on a dark theme is the dark
    # canvas: a picture asked for in dark and painted on white is not dark.
    paper = load_theme(project.provider)
    if theme != "light":
        paper = dark_theme(paper, theme)
    ground = resolve_background(background, paper.paper)
    if libraries not in EXPORT_LIBRARIES:
        raise ExportError(
            f"unknown libraries choice {libraries!r}; use {', '.join(EXPORT_LIBRARIES)}"
        )
    requested = tuple(dict.fromkeys(value.casefold() for value in formats))
    unknown = set(requested) - _SUPPORTED_FORMATS
    if unknown:
        raise ExportError(
            f"unsupported export format: {', '.join(sorted(unknown))}; use "
            + ", ".join(sorted(_SUPPORTED_FORMATS))
        )
    if not requested:
        raise ExportError("at least one export format is required")
    if display not in EXPORT_DISPLAYS:
        raise ExportError(f"unknown display choice {display!r}; use {', '.join(EXPORT_DISPLAYS)}")
    if "png" in requested and not 1 <= scale <= 4:
        raise ExportError("PNG scale must be between 1 and 4")
    if write_looks not in ("document", "both"):
        raise ExportError(f"unknown write_looks {write_looks!r}; use document or both")
    # A PNG needs Playwright and Chromium. Asked before anything is written,
    # so a machine without them gets one clear error instead of half an
    # export that the retry then refuses to overwrite.
    if "png" in requested and (png_renderer is None or canvas is not None):
        missing = browser_missing()
        if missing:
            raise ExportError(f"cannot write the PNG: {missing}")
    # The skeleton is planned up front too: a document with nothing to write
    # is refused before any file is.
    skeletons = {}
    for name, style in (("terraform", "resources"), ("terraform-modules", "modules")):
        if name in requested:
            from ..terraform import terraform_files

            skeletons[name] = terraform_files(project, style)

    output_dir.mkdir(parents=True, exist_ok=True)
    final = {
        "template": output_dir / f"{project.slug}.infragram.json",
        "html": output_dir / f"{project.slug}.html",
        "svg": output_dir / f"{project.slug}.svg",
        "png": output_dir / f"{project.slug}.png",
        "drawio": output_dir / f"{project.slug}.drawio",
        "svg_icons": output_dir / f"{project.slug}-icons.svg",
        "png_icons": output_dir / f"{project.slug}-icons.png",
        "terraform": output_dir / f"{project.slug}-terraform{'.zip' * terraform_zip}",
        "terraform-modules": output_dir
        / f"{project.slug}-terraform-modules{'.zip' * terraform_zip}",
    }
    # ``both`` with ``write_looks="both"`` writes the cards under the plain
    # names and the icons beside them. With ``write_looks="document"`` only
    # the document's own look is written; the other look is drawn as well
    # when there is a ``check`` to read it, so both looks are proved, and is
    # never written.
    write_second = display == "both" and write_looks == "both"
    if display == "project" or (display == "both" and not write_second):
        primary_display: str | None = None
    elif display == "both":
        primary_display = "card"
    else:
        primary_display = display
    variants = {"svg_icons", "png_icons"} if write_second else set()
    other_look = "card" if project.presentation.display == "icon" else "icon"
    check_other = (
        display == "both" and not write_second and check is not None and "svg" in requested
    )
    # The SVG and PNG are drawn from the page, so the HTML is always staged
    # for them; it reaches the output folder only when it was asked for
    # (``--formats png`` writes a PNG, not a page beside it).
    materialized = set(requested)
    if materialized & {"svg", "png"}:
        materialized.add("html")
    materialized |= {f"{name}_icons" for name in ("svg", "png") if name in requested} & variants
    delivered = materialized - ({"html"} - set(requested))
    # What this tool wrote and nobody has touched since is replaced; a file
    # written elsewhere, or edited after it was written, needs --force.
    existing = written.blocking(final[name] for name in delivered)
    if existing and not overwrite:
        raise ExportError(
            "refusing to overwrite files changed since they were exported, or not "
            "exported here (pass --force to replace them): "
            + ", ".join(str(path) for path in existing)
        )

    html = render_project_html(project, libraries=libraries) if materialized & _DRAWN else ""
    notes: list[str] = []
    # What every page capture is drawn with. The routing is passed only when
    # the page is to draw straight wires, so a renderer that knows nothing of
    # it -- one a caller passes in, or one standing in for the browser -- is
    # never handed a keyword it does not take.
    capture: dict[str, Any] = {"theme": theme, "background": ground}
    if routing == "direct":
        capture["routing"] = "direct"
    render_svg = svg_renderer or partial(playwright_svg_renderer, **capture)
    render_png = png_renderer or partial(playwright_png_renderer, **capture)
    svg_jobs = [
        (name, look)
        for name, look in (("svg", primary_display), ("svg_icons", "icon"))
        if name in materialized
    ]
    png_jobs = [
        (name, look)
        for name, look in (("png", primary_display), ("png_icons", "icon"))
        if name in materialized
    ]
    for _, look in svg_jobs:
        _check_renderer(render_svg, look)
    if check_other:
        _check_renderer(render_svg, other_look)
    for _, look in png_jobs:
        _check_renderer(render_png, look)
    other_checks: list[tuple[str, bool, str]] = []
    # Everything is drawn into a staging folder beside the output and moved
    # into place only when every file rendered, so a failure never leaves half
    # an export behind for the next run to refuse to overwrite.
    staging = Path(tempfile.mkdtemp(prefix=".infragram-", dir=output_dir))
    try:
        paths = {name: staging / target.name for name, target in final.items()}
        if "template" in materialized:
            project.save(paths["template"])
        if "html" in materialized:
            paths["html"].write_text(html, encoding="utf-8", newline="\n")
        if "drawio" in materialized:
            from .drawio import render_project_drawio

            paths["drawio"].write_text(
                render_project_drawio(project, icons=drawio_icons), encoding="utf-8", newline="\n"
            )
        for name, (plan, files) in skeletons.items():
            from ..terraform import summary, write_files, write_zip

            if terraform_zip:
                write_zip(files, paths[name], folder=final[name].stem)
            else:
                write_files(files, paths[name])
            notes.append(f"{final[name].name}: {summary(plan)}")
        # A look is a laid-out document. Flipping the card page in place would
        # leave 96 px icon nodes on a 96 px pitch, so each look that differs
        # from the document's own is rendered from a copy whose presentation
        # says so and the layout sizes and spaces the nodes for it first.
        with tempfile.TemporaryDirectory(prefix="infragram-looks-") as looks_dir:
            pages: dict[str, tuple[Path, str]] = {}

            def project_for(look: str | None) -> CloudProject:
                if look in (None, "project", project.presentation.display):
                    return project
                return look_variant(project, look)

            def page_for(look: str | None) -> tuple[Path, str]:
                if look in (None, "project", project.presentation.display):
                    return paths["html"], html
                if look not in pages:
                    variant = look_variant(project, look)
                    page = Path(looks_dir) / f"{project.slug}-{look}.html"
                    markup = render_project_html(variant, libraries=libraries)
                    page.write_text(markup, encoding="utf-8", newline="\n")
                    pages[look] = (page, markup)
                return pages[look]

            def static_svg(look: str | None, output: Path) -> None:
                # The page embeds the light scene, so a picture asked for in
                # another theme is rendered again in that theme rather than
                # handed back light (exports/palette.py).
                _, markup = page_for(look)
                output.write_text(
                    finish_standalone_svg(extract_svg(markup), ground)
                    if theme == "light"
                    else render_project_svg(project_for(look), background=background, theme=theme),
                    encoding="utf-8",
                    newline="\n",
                )

            def draw_svg(look: str | None, output: Path) -> None:
                if renderer == "static":
                    static_svg(look, output)
                else:
                    page, _ = page_for(look)
                    try:
                        _call_renderer(render_svg, page, output, display=look)
                    except ExportError as error:
                        # No browser, or the page had no runtime: the static
                        # render is the honest fallback, and the note says
                        # which layout it shows.
                        static_svg(look, output)
                        notes.append(
                            f"{output.name} was drawn by the static renderer, not the editor "
                            f"runtime: {error}"
                        )
                if canvas is not None:
                    output.write_text(
                        frame_svg(output.read_text(encoding="utf-8"), size),
                        encoding="utf-8",
                        newline="\n",
                    )

            for name, look in svg_jobs:
                draw_svg(look, paths[name])
            if check_other:
                assert check is not None
                # Named after its page, so the checker finds the document the
                # page embeds and compares the picture with it.
                other = Path(looks_dir) / f"{project.slug}-{other_look}.svg"
                draw_svg(other_look, other)
                ok, message = check(other)
                other_checks.append(
                    (f"{other_look} look (drawn to check, not written)", ok, message)
                )
            for name, look in png_jobs:
                page, _ = page_for(look)
                if canvas is not None:
                    # the framed picture, drawn as a PNG: its canvas is the
                    # preset's, which a capture of the page cannot give
                    framed = Path(looks_dir) / f"{project.slug}-{name}-framed.svg"
                    draw_svg(look, framed)
                    playwright_svg_to_png(framed, paths[name], scale, transparent=ground is None)
                    continue
                if renderer == "static":
                    static_png = partial(playwright_static_png_renderer, **capture)
                    _call_renderer(static_png, page, paths[name], scale, display=look)
                    continue
                try:
                    _call_renderer(render_png, page, paths[name], scale, display=look)
                except ExportError as error:
                    # The same verdict the SVG gets: the page had no runtime in
                    # time, so the static picture is screenshotted instead and
                    # the note says which renderer drew the file. That capture
                    # still needs a browser; without one there is no PNG at all
                    # and the fallback's own error is the one raised.
                    static_png = partial(playwright_static_png_renderer, **capture)
                    _call_renderer(static_png, page, paths[name], scale, display=look)
                    notes.append(
                        f"{paths[name].name} was drawn by the static renderer, not the "
                        f"editor runtime: {error}"
                    )
        if embed:
            from .carry import embed_in_png, embed_in_svg

            document = project.model_dump_json(exclude_none=True)
            for name in ("svg", "svg_icons"):
                if name in materialized:
                    paths[name].write_text(
                        embed_in_svg(paths[name].read_text(encoding="utf-8"), document),
                        encoding="utf-8",
                        newline="\n",
                    )
            for name in ("png", "png_icons"):
                if name in materialized:
                    paths[name].write_bytes(embed_in_png(paths[name].read_bytes(), document))
        for name in sorted(delivered):
            if final[name].is_dir():
                # A folder cannot be replaced in one move: the old one goes
                # into the staging folder, which is removed below.
                os.replace(final[name], staging / f".replaced-{final[name].name}")
            os.replace(paths[name], final[name])
        written.remember(final[name] for name in delivered)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    checks: list[tuple[str, bool, str]] = []
    if check is not None:
        checked = ["template", "html", "svg", "svg_icons"]
        if not delivered & {"html", "svg"}:
            checked.append("png")  # a PNG alone is still checked: its carried document
        for name in checked:
            if name in delivered:
                ok, message = check(final[name])
                checks.append((final[name].name, ok, message))
        checks += other_checks

    return ExportResult(
        template=final["template"] if "template" in delivered else None,
        html=final["html"] if "html" in delivered else None,
        svg=final["svg"] if "svg" in delivered else None,
        png=final["png"] if "png" in delivered else None,
        drawio=final["drawio"] if "drawio" in delivered else None,
        svg_icons=final["svg_icons"] if "svg_icons" in delivered else None,
        png_icons=final["png_icons"] if "png_icons" in delivered else None,
        terraform=final["terraform"] if "terraform" in delivered else None,
        terraform_modules=final["terraform-modules"] if "terraform-modules" in delivered else None,
        notes=tuple(notes),
        checks=tuple(checks),
    )


async def export_project_async(project: CloudProject, output_dir: Path, **options) -> ExportResult:
    """:func:`export_project` off the event loop.

    Rendering is bound by a headless browser, not by Python, so one project
    exports in a worker thread while the loop stays free to schedule the
    next. ``options`` are :func:`export_project`'s keywords.
    """
    import asyncio

    return await asyncio.to_thread(export_project, project, output_dir, **options)


def export_many(
    projects: Iterable[CloudProject],
    output_dir: Path,
    *,
    concurrency: int = 2,
    **options,
) -> list[ExportResult]:
    """Export several projects at once, ``concurrency`` browsers at a time.

    Results come back in the order the projects were given. Each project
    still writes its own files under its own slug, so two projects sharing a
    slug would race; that is the caller's mistake and is refused up front.
    ``options`` are :func:`export_project`'s keywords.
    """
    import asyncio

    items = list(projects)
    slugs = [project.slug for project in items]
    duplicates = sorted({slug for slug in slugs if slugs.count(slug) > 1})
    if duplicates:
        raise ExportError("export_many needs distinct slugs; repeated: " + ", ".join(duplicates))
    if concurrency < 1:
        raise ExportError("concurrency must be at least 1")

    async def run() -> list[ExportResult]:
        gate = asyncio.Semaphore(concurrency)

        async def one(project: CloudProject) -> ExportResult:
            async with gate:
                return await export_project_async(project, output_dir, **options)

        return list(await asyncio.gather(*(one(project) for project in items)))

    return asyncio.run(run())
