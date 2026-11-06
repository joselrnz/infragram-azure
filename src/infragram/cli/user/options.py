"""The options the export commands share, declared once so they cannot drift."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

from ...exports.browser import EXPORT_ROUTINGS, EXPORT_THEMES
from ...exports.framing import SIZES
from ...exports.project import EXPORT_DISPLAYS, EXPORT_FORMATS, EXPORT_RENDERERS
from ...exports.render import EXPORT_LIBRARIES

__all__ = [
    "DEFAULT_FORMATS",
    "DISPLAYS",
    "FORMATS",
    "LIBRARIES",
    "RENDERERS",
    "ROUTINGS",
    "SIZES",
    "THEMES",
    "add_export_options",
    "add_price_options",
    "apply_render_settings",
    "chosen_formats",
    "export_keywords",
    "price_flags",
    "with_overrides",
]


def add_price_options(parser: argparse.ArgumentParser) -> None:
    """``--prices`` and ``--no-prices``: where the approximate monthly cost comes from."""
    parser.set_defaults(prices="table")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--prices",
        action="store_const",
        const="live",
        dest="prices",
        help="price from current public prices where supported, else from the shipped "
        "tables; without it, Azure components are priced from the shipped tables offline",
    )
    group.add_argument(
        "--no-prices",
        action="store_const",
        const="off",
        dest="prices",
        help="leave prices out: no price is written, and the page shows no cost",
    )


def price_flags(prices: str) -> list[str]:
    """The flags that ask for *prices* again, for a command passed on."""
    return {"live": ["--prices"], "off": ["--no-prices"]}.get(prices, [])


# The choices each option offers are the exporter's own lists, so the parser
# cannot accept a value the export then refuses, or leave out one it takes.

#: Every format an export can write (exports/project.py).
FORMATS = EXPORT_FORMATS
#: What an export writes when ``--formats`` is not given. The page carries the
#: document and can download it, so the template is written only when asked.
DEFAULT_FORMATS = ("html", "svg", "png")
#: The workspace themes a picture can be drawn in; light is the default.
THEMES = EXPORT_THEMES
#: What the HTML embeds: only the drawn components, the project's libraries,
#: or every installed library.
LIBRARIES = EXPORT_LIBRARIES
#: How components draw in the pictures, as ``--display`` names it.
DISPLAYS = EXPORT_DISPLAYS
#: What draws the SVG and PNG (exports/project.py).
RENDERERS = EXPORT_RENDERERS
#: How the wires in the SVG and PNG are routed (exports/browser.py).
ROUTINGS = EXPORT_ROUTINGS
# SIZES, the canvases a picture can be framed on -- fit (cropped to the
# drawing) and the document's size presets -- is exports/framing.py's own.


def add_export_options(
    parser: argparse.ArgumentParser,
    *,
    libraries: str,
    output_dir: Path | None = Path("dist"),
    output_help: str = "where the files go (default: ./dist)",
    display: str = "project",
    verify: bool = True,
    title: bool = True,
) -> None:
    """Add ``--formats`` through ``--force``. ``libraries`` is the command's
    default for what the HTML embeds; a command that writes elsewhere by
    default, draws both looks by default, or always verifies (``export:set``)
    says so with the others. ``title=False`` leaves ``--title`` to a command
    that names the drawing itself (the imports)."""
    parser.add_argument(
        "--formats",
        default=None,
        metavar="LIST",
        help=f"comma-separated {','.join(FORMATS)} (default: {','.join(DEFAULT_FORMATS)}; "
        "without a browser for the PNG, html,svg and a note saying why)",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=output_dir, metavar="DIR", help=output_help
    )
    parser.add_argument(
        "--scale", type=float, default=3, metavar="N", help="PNG scale from 1 through 4 (default 3)"
    )
    parser.add_argument(
        "--theme",
        choices=THEMES,
        default="light",
        help="theme the SVG and PNG are drawn in (default: light)",
    )
    parser.add_argument(
        "--libraries",
        choices=LIBRARIES,
        default=libraries,
        help=f"component libraries the HTML embeds (default: {libraries}): only what the "
        "diagram draws (smallest; nothing else can be added in that copy), the "
        "project's own libraries, or every installed one",
    )
    parser.add_argument(
        "--background",
        default="paper",
        metavar="COLOUR",
        help="behind the diagram: paper (the theme's own ground, the default), "
        "transparent, or a hex colour",
    )
    parser.add_argument(
        "--display",
        choices=DISPLAYS,
        default=display,
        help=f"how components draw in SVG and PNG (default: {display}): the document's own "
        "choice, cards, bare icons with captions, or both (both are checked; "
        "--write-looks says which reach disk)",
    )
    parser.add_argument(
        "--write-looks",
        choices=("document", "both"),
        default="both",
        dest="write_looks",
        help="with --display both: write both looks (default), the cards under the plain "
        "names and the icons as <slug>-icons.*; document writes only the document's own look",
    )
    if verify:
        parser.add_argument(
            "--verify",
            action="store_true",
            help="check every file written with the shipped checker: documents, pages, and "
            "for SVGs the picture itself",
        )
    add_price_options(parser)
    parser.add_argument(
        "--view",
        default=None,
        metavar="NAME",
        help="draw one part of the diagram on its own, laid out afresh, as <slug>-<view>.*: a "
        "frame by id or caption (a subscription, a resource group, a VNet, a VPC, a namespace), "
        "a view the diagram declares, or a rule: tag:env=prod, category:networking, "
        "name:*-prod-*; `all` draws every declared view (`infragram views` lists them)",
    )
    parser.add_argument(
        "--infracost",
        type=Path,
        default=None,
        metavar="FILE",
        help="price each component from an `infracost breakdown --format json` file, joined "
        "by the Terraform address it was drawn from (import:terraform writes it); Infracost "
        "needs its own key or a self-hosted pricing endpoint, and is never required",
    )
    parser.add_argument(
        "--drawio-icons",
        choices=("native", "embedded"),
        default="native",
        dest="drawio_icons",
        help="with --formats drawio: draw.io's own AWS, Azure and Kubernetes stencils where one "
        "matches, our artwork elsewhere (native, the default), or our artwork everywhere",
    )
    parser.add_argument(
        "--no-embed",
        action="store_false",
        dest="embed",
        help="leave the SVG and PNG bare: by default each carries its document, so "
        "`export:project picture.png` redraws it",
    )
    parser.add_argument(
        "--size",
        choices=SIZES,
        default="fit",
        help="the canvas the SVG and PNG are drawn on: fit (cropped to the drawing, the "
        "default) or a preset -- doc-inline 960x600, doc-wide 1280x720, slide-16x9 1280x720, "
        "slide-4x3 1024x768, social-og 1200x632, social-square 1080x1080, print-a4-landscape "
        "1120x792, print-letter-landscape 1056x816 -- the drawing centred and scaled to fit",
    )
    parser.add_argument(
        "--renderer",
        choices=RENDERERS,
        default="editor",
        help="what draws the SVG and PNG: the editor runtime in a browser (the default; the "
        "static renderer steps in, with a note, when it cannot) or the static renderer on "
        "purpose, which needs no browser for the SVG",
    )
    parser.add_argument(
        "--routing",
        choices=ROUTINGS,
        default="around",
        help="how the wires run in the SVG and PNG: around the cards (the default) or direct, "
        "straight from port to port, as the editor's routing switch draws them",
    )
    parser.add_argument(
        "--terraform-zip",
        action="store_true",
        dest="terraform_zip",
        help="with --formats terraform or terraform-modules: write each skeleton as "
        "<slug>-terraform.zip, laid out as the page's Download menu gives it, instead of a folder",
    )
    if title:
        parser.add_argument(
            "--title",
            default=None,
            metavar="TEXT",
            help="the title the exported diagram carries, in place of the document's own",
        )
    parser.add_argument(
        "--status",
        default=None,
        metavar="TEXT",
        help="where the drawing stands, saved as document metadata: "
        '"CURRENT -- verified 2026-09-30", "TARGET", "PROPOSED" (default: the document\'s own)',
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="kept for older scripts: a render never loads anything from another machine "
        "(INFRAGRAM_RENDER_OFFLINE=1 is accepted too)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="how long a page may take to draw before the export gives up (default 120); the "
        "same as INFRAGRAM_RENDER_TIMEOUT_MS",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace files written elsewhere or edited since the last export",
    )


def chosen_formats(value: str | None) -> tuple[tuple[str, ...], bool]:
    """The formats asked for, and whether they were asked for explicitly."""
    if value is None:
        return DEFAULT_FORMATS, False
    return tuple(part.strip() for part in value.split(",") if part.strip()), True


def export_keywords(options: argparse.Namespace) -> dict[str, Any]:
    """What the shared options ask of an export, as :func:`infragram.compose.export`'s
    keywords (formats, output folder, overwrite and check aside). Every command
    that exports builds its call from this, so an option cannot be accepted by
    the parser and then left out of the export."""
    return {
        "scale": options.scale,
        "theme": options.theme,
        "libraries": options.libraries,
        "display": options.display,
        "write_looks": options.write_looks,
        "background": options.background,
        "embed": getattr(options, "embed", True),
        "drawio_icons": getattr(options, "drawio_icons", "native"),
        "size": getattr(options, "size", "fit"),
        "renderer": getattr(options, "renderer", "editor"),
        "routing": getattr(options, "routing", "around"),
        "terraform_zip": getattr(options, "terraform_zip", False),
    }


def apply_render_settings(options: argparse.Namespace) -> None:
    """``--offline`` and ``--timeout``, set for this run the way the
    environment sets them: the browser code reads them when it draws."""
    if getattr(options, "offline", False):
        os.environ["INFRAGRAM_RENDER_OFFLINE"] = "1"
    seconds = getattr(options, "timeout", None)
    if seconds is not None:
        if seconds <= 0:
            raise ValueError(f"--timeout must be more than 0 seconds, not {seconds:g}")
        os.environ["INFRAGRAM_RENDER_TIMEOUT_MS"] = str(round(seconds * 1000))


def with_overrides(project, options: argparse.Namespace):
    """``project`` with the title and status ``--title`` and ``--status`` give,
    or ``project`` itself when neither was given. Applied to what is drawn --
    after a view is selected -- so a view keeps the name it adds."""
    title = getattr(options, "title", None)
    status = getattr(options, "status", None)
    if title is None and status is None:
        return project
    update: dict[str, Any] = {}
    if title is not None:
        update["title"] = title
    if status is not None:
        update["presentation"] = project.presentation.model_copy(update={"status": status})
    return project.model_copy(update=update)
