"""Named output sizes.

A preset is a promise about the finished artifact -- a slide is 1280x720 --
so a picture that outgrew the one it was given is refused rather than shipped
at a size the preset denies. ``fit`` makes no promise and lets the canvas take
the size its content needs. Every preset draws the same type: the editor,
which draws every export, has one set of sizes, so a slide preset that raised
them changed only the fallback picture.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..builders.architecture import load_style
from ..builders.scene import Canvas
from ..projects import CloudProject
from .errors import ExportError

__all__ = ["SIZE_PRESETS", "SizePreset"]


@dataclass(frozen=True, slots=True)
class SizePreset:
    width: int | None
    height: int | None
    margin: int = 40


SIZE_PRESETS: dict[str, SizePreset] = {
    "doc-inline": SizePreset(960, 600),
    "doc-wide": SizePreset(1280, 720),
    "slide-16x9": SizePreset(1280, 720),
    "slide-4x3": SizePreset(1024, 768),
    "social-og": SizePreset(1200, 632, margin=64),
    "social-square": SizePreset(1080, 1080),
    "print-a4-landscape": SizePreset(1120, 792),
    "print-letter-landscape": SizePreset(1056, 816),
    "fit": SizePreset(None, None),
}


def _links_of(provider: str) -> dict:
    """The link table a library's theme defines, or nothing when it has no theme."""
    try:
        return load_style(provider).links
    except (KeyError, OSError, ValueError):
        return {}


def _style_for(project: CloudProject):
    preset = SIZE_PRESETS[project.presentation.size]
    style = load_style(project.provider).model_copy(deep=True)
    # A link kind belongs to whichever of the document's libraries defines it,
    # so a hybrid diagram whose default library is Cloudflare still draws the
    # AWS theme's ``vpn``. The default library wins a kind both define.
    for provider in project.provider_ids:
        if provider != project.provider:
            for kind, link in _links_of(provider).items():
                style.links.setdefault(kind, link)
    if preset.width is None or preset.height is None:
        style.canvas.fit = True
        style.canvas.fit_margin = preset.margin
    else:
        style.canvas = Canvas(
            width=preset.width,
            height=preset.height,
            margin_x=preset.margin,
            content_top=96,
            content_bottom=preset.height - 112,
            legend_offset=84,
        )
    return style


def _check_preset(project: CloudProject, scene) -> None:
    """A fixed size preset is a promise: a picture that outgrew it is refused,
    on every export path, rather than shipped at a size the preset denies."""
    preset = SIZE_PRESETS[project.presentation.size]
    if preset.width is not None and (scene.width, scene.height) != (preset.width, preset.height):
        raise ExportError(
            f"project content exceeds {project.presentation.size} "
            f"({preset.width}x{preset.height}); rendered size would be "
            f"{scene.width}x{scene.height}. Reduce detail or choose a larger preset."
        )
