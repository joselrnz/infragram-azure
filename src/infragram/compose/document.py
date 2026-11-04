"""A topology tree in, a valid project document out.

:func:`to_project` is the one place a tree becomes a document: it qualifies
every component against the installed catalogs, infers the libraries and the
kind, and fills in everything the author did not say.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from ..exports import ExportResult, export_project
from ..models.topology import TopologyElement
from ..nodes._base import ROOT_ID
from ..projects import CloudProject, Presentation, ProjectKind, View
from .errors import ComposeError
from .ids import qualify
from .inference import infer_kind, infer_providers

__all__ = ["export", "to_project", "undrawn_root"]


def _as_elements(source: TopologyElement | Iterable[TopologyElement]) -> list[TopologyElement]:
    if isinstance(source, TopologyElement):
        return [source]
    elements = list(source)
    if not elements:
        raise ComposeError("an estate needs at least one element")
    if not all(isinstance(element, TopologyElement) for element in elements):
        raise ComposeError("every top-level item must be a TopologyElement")
    return elements


def undrawn_root(children: list[TopologyElement], title: str) -> TopologyElement:
    """The frame a document's top-level elements sit in; it is never drawn.

    Its id is :data:`~infragram.nodes.ROOT_ID` (``root``), the id every
    shipped template and the inventory builder use, so an element that
    already carries it cannot be placed under it: the topology model would
    refuse the duplicate with a message that names neither party. Auto-ids
    never mint ``root`` (an element named "Root" becomes ``root-2``), so the
    only way here is an explicit ``id="root"`` on something that is not the
    root, which is refused by name.
    """
    for element in children:
        for taken in element.walk():
            if taken.id == ROOT_ID:
                raise ComposeError(
                    f"{taken.name!r} carries id {ROOT_ID!r}, which names the undrawn root "
                    f"of the document; give it another id"
                )
    return TopologyElement(id=ROOT_ID, name=title, type="group", children=children)


def _wrap(elements: list[TopologyElement], title: str) -> TopologyElement:
    """The project root is a frame that is not drawn; its children are.

    A single plain ``Group`` with id ``root`` is already that frame. Anything
    else - a provider frame, a node, or several siblings - is placed under a
    synthetic root so it is drawn rather than swallowed.
    """
    if len(elements) == 1:
        only = elements[0]
        if (
            only.id == ROOT_ID
            and only.component is None
            and not only.attributes.get("editor_frame_group")
        ):
            return only
    return undrawn_root(elements, title)


def to_project(
    source: TopologyElement | Iterable[TopologyElement],
    *,
    slug: str,
    title: str,
    description: str,
    providers: Sequence[str] | None = None,
    kind: ProjectKind | None = None,
    default_library: str | None = None,
    size: str = "fit",
    eyebrow: str = "Architecture",
    heading: str = "",
    legend: Sequence[tuple[str, str]] = (),
    template_brief: str = "",
    display: str = "card",
    status: str = "",
    notes: Sequence[str] = (),
    drawn: str = "",
    crossings: str = "plain",
    frame_lines: str = "thin",
    tones: Iterable[tuple[str, str]] = (),
    views: Sequence[View] = (),
) -> CloudProject:
    """Build a valid project document from a topology tree.

    ``display`` is how every component draws unless a node says otherwise:
    ``card`` (a titled box) or ``icon`` (the bare mark with its caption). A
    resource-tier glyph -- a NAT gateway, an internet gateway, an endpoint --
    draws bare in either look, the way its deck places it.

    ``source`` is one element or the top-level siblings of the diagram.
    Everything not given is inferred: components from node classes,
    providers and kind from the components, the default library from the
    first provider, and ``fit`` sizing so the canvas wraps the content.

    An explicit ``providers=`` replaces the inferred set rather than joining
    it; the kind and the default library then follow from what was given, and
    a component from a library left out fails the document's own check.
    """
    root = _wrap(_as_elements(source), title)
    qualify(root)
    chosen = tuple(dict.fromkeys(providers)) if providers else infer_providers(root)
    if not chosen:
        raise ComposeError("an estate needs at least one element")
    library = default_library or chosen[0]
    presentation = Presentation(
        size=size,
        eyebrow=eyebrow,
        heading=heading,
        legend=tuple(tuple(item) for item in legend),
        tones=tuple(tuple(item) for item in tones),
        display=display,
        status=status,
        notes=tuple(notes),
        drawn=drawn,
        crossings=crossings,
        frame_lines=frame_lines,
    )
    return CloudProject(
        kind=kind or infer_kind(chosen),
        slug=slug,
        title=title,
        description=description,
        template_brief=template_brief,
        providers=[{"id": provider} for provider in chosen],
        default_library=library,
        presentation=presentation,
        views=tuple(views),
        topology=root,
    )


def export(
    source: CloudProject | TopologyElement | Iterable[TopologyElement],
    output_dir: Path,
    *,
    formats: Sequence[str] = ("html", "svg", "png"),
    theme: str = "light",
    scale: float = 3,
    libraries: str = "project",
    overwrite: bool = False,
    display: str = "project",
    write_looks: str = "both",
    background: str = "paper",
    check: Callable[[Path], tuple[bool, str]] | None = None,
    embed: bool = True,
    drawio_icons: str = "native",
    size: str = "fit",
    renderer: str = "editor",
    routing: str = "around",
    terraform_zip: bool = False,
    **project_kwargs,
) -> ExportResult:
    """Export a project, or a tree turned into one with ``project_kwargs``.

    ``display`` is the export look: ``project`` follows the document, ``card``
    or ``icon`` force one, ``both`` draws both (see
    :func:`infragram.exports.export_project` for which of them is written).
    ``check`` reads every file written; its verdicts come back on the result.

    ``project_kwargs`` (slug, title, ...) only apply to a tree. Given with a
    finished project they would be silently ignored, so they are refused.
    """
    if isinstance(source, CloudProject):
        if project_kwargs:
            raise TypeError(
                "export() takes no document options for a finished project; "
                f"got {', '.join(sorted(project_kwargs))}"
            )
        project = source
    else:
        project = to_project(source, **project_kwargs)
    return export_project(
        project,
        Path(output_dir),
        formats=tuple(formats),
        scale=scale,
        theme=theme,
        libraries=libraries,
        display=display,
        write_looks=write_looks,
        overwrite=overwrite,
        background=background,
        embed=embed,
        drawio_icons=drawio_icons,
        size=size,
        renderer=renderer,
        routing=routing,
        terraform_zip=terraform_zip,
        check=check,
    )
