"""A document drawn without a browser.

``render_project_html`` is the canonical artifact and the only layout
operation; ``render_project_svg`` draws the same placed scene straight to SVG,
which is what the golden-pictures gate locks and what an export falls back to
when no browser is available.
"""

from __future__ import annotations

from ..builders.architecture import from_topology, load_icon_set, load_theme
from ..editor import render_editor_html
from ..projects import CloudProject
from ..projects.comments import Comments
from .errors import ExportError
from .presets import _check_preset, _style_for
from .svg import finish_standalone_svg, resolve_background

__all__ = [
    "EXPORT_LIBRARIES",
    "look_variant",
    "render_project_html",
    "render_project_svg",
]


#: Which libraries an export embeds, smallest first as the command line lists
#: them: only what the diagram draws, the project's own (default, two to three
#: MB), or every installed one (the full workspace, roughly ten times larger).
EXPORT_LIBRARIES = ("drawn", "project", "all")


def render_project_html(
    project: CloudProject, *, libraries: str = "project", comments: Comments | None = None
) -> str:
    """Render one project to the canonical, self-contained HTML artifact,
    with the comments on it when there are some (ADR 0009)."""

    if libraries not in EXPORT_LIBRARIES:
        raise ExportError(f"unknown libraries choice {libraries!r}; use project or all")
    scene = _scene_for(project)
    _check_preset(project, scene)
    return render_editor_html(project, scene, libraries=libraries, comments=comments)


def look_variant(project: CloudProject, look: str) -> CloudProject:
    """The document drawn as ``look`` everywhere.

    A node's own ``editor_display_mode`` wins over the project default when
    the document is drawn as itself. A look is a request about the whole
    drawing -- cards, or icons -- the same request the editor's Components
    switch makes, so the per-node choices are set aside for it.
    """
    if look not in ("card", "icon"):
        raise ExportError(f"unknown display look {look!r}; use card or icon")
    variant = project.model_copy(
        deep=True,
        update={
            "presentation": project.presentation.model_copy(update={"display": look}),
        },
    )
    # Saved positions and sizes describe the document's own look: a card
    # placed by hand is 64 px tall where an icon node is 96. Drawn as the
    # other look at the same coordinates, nodes overlap the row below. The
    # variant drops them and the layout places the look for itself.
    #
    # The look is then written onto every component rather than merely left
    # to the project default, because a node's own mode is the only thing
    # that outranks the bare-drawing rules.
    # Dropping the mode let those rules keep drawing resource-tier glyphs --
    # api-endpoint, generic-cache, network-gateway, secret-key -- bare in a
    # forced *card* export, which is not what a forced look means: it is the
    # request the editor's Components switch makes, and that one wins.
    for element in variant.topology.walk():
        for key in ("editor_x", "editor_y", "editor_width", "editor_height", "editor_card_size"):
            element.attributes.pop(key, None)
        if element.is_frame:
            element.attributes.pop("editor_display_mode", None)
        else:
            element.attributes["editor_display_mode"] = look
    return variant


def _scene_for(project: CloudProject, *, theme: str = "light"):
    """The placed scene of one project: what the page embeds and the static
    picture draws. One builder for both, so the two cannot drift.

    ``theme`` is the workspace theme the picture is drawn in, as the editor
    draws it (exports/palette.py); the page itself always embeds the light
    scene and paints its own canvas from the reader's chosen theme."""
    from dataclasses import replace

    from ..editor.shell import _shows_provider_mark

    style = _style_for(project)
    palette = theme
    colours = load_theme(project.provider)
    if palette != "light":
        from .palette import dark

        colours = dark(colours, palette)
    try:
        icons = load_icon_set(project.icon_collection or project.provider)
    except KeyError:
        if project.icon_collection:
            raise
        # A library with no vendored icon collection still renders: its
        # component artwork comes from the embedded library payload.
        icons = None
    scene = from_topology(
        project.topology,
        colours,
        slug=project.slug,
        title=project.title,
        desc=project.description,
        icons=icons,
        style=style,
        eyebrow=project.presentation.eyebrow,
        heading=project.presentation.heading,
        legend=list(project.presentation.legend),
        tones=list(project.presentation.tones),
        display=project.presentation.display,
        provider=project.provider,
        status=project.presentation.status,
        notes=project.presentation.notes,
        drawn_on=project.presentation.drawn,
        crossings=project.presentation.crossings,
        frame_lines=project.presentation.frame_lines,
    )
    # A cloud-plus-cloud workspace is branded as multicloud, not with the
    # first provider's mark, and one drawn from shared parts alone carries no
    # vendor's mark. The page shell makes the same call; doing it here as well
    # keeps the static picture in step with the page.
    if not _shows_provider_mark(project) and scene.theme.mark:
        scene.theme = replace(scene.theme, mark="")
    return scene


def render_project_svg(
    project: CloudProject, background: str | None = None, *, theme: str = "light"
) -> str:
    """The static picture of one project as a standalone SVG.

    This is the drawing the exporter falls back to without a browser and the
    one the golden-pictures gate locks. It is the same scene the page embeds,
    rendered straight to SVG, so it takes a fraction of a second rather than
    assembling the page and its library payload first.

    ``background`` is read the way :func:`export_project` reads it: ``paper``
    (the theme's own ground), ``transparent``, or a hex colour. None, the
    default, paints nothing, which is what the golden pictures lock.
    """
    from ..builders import render_svg

    scene = _scene_for(project, theme=theme)
    _check_preset(project, scene)
    ground = None if background is None else resolve_background(background, scene.theme.paper)
    return finish_standalone_svg(render_svg(scene), ground)
