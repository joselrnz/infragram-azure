"""A whole diagram, assembled from elements and patterns, exported on demand.

A :class:`Blueprint` is the object a script builds and hands to the exporter.
It holds the top-level elements, the links between anything, and the words
the project document needs. It validates
what it is given as it is given, so a mistake surfaces at the line that made
it rather than deep inside an export, and it is deterministic: the same
construction order gives the same ids, the same document, the same picture.

::

    plan = Blueprint("private-dx-staging", "Private Direct Connect staging",
                     "SQL Server and DataStage land into AWS over a private VIF.")
    uplink = DirectConnectUplink("Corporate data center")
    plan.add(*uplink.elements)
    cloud = plan.add(aws.Cloud("AWS Cloud"))[0]
    ...
    plan.link(uplink["circuit"], tgw, kind="dashed", label="transit VIF")
    plan.export(Path("dist"), display="both")
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .. import compose
from ..exports import EXPORT_DISPLAYS, EXPORT_THEMES, ExportResult, export_many
from ..models.topology import TopologyElement
from ..nodes import reset_ids
from ..projects import CloudProject, ProjectKind
from ..utils.text import SLUG as _SLUG
from .base import PatternError

__all__ = ["Blueprint"]

_DISPLAYS = ("card", "icon")


class Blueprint:
    """Elements and links, plus the words a project needs."""

    def __init__(
        self,
        slug: str,
        title: str,
        description: str,
        *,
        display: str = "card",
        theme: str = "light",
        size: str = "fit",
        kind: ProjectKind | None = None,
        providers: Sequence[str] | None = None,
        template_brief: str = "",
    ) -> None:
        self._slug = self._title = self._description = ""
        self._display = self._theme = ""
        self.slug = slug
        self.title = title
        self.description = description
        self.display = display
        self.theme = theme
        self._size = "fit"
        self._kind: ProjectKind | None = None
        self._providers: tuple[str, ...] | None = None
        self._template_brief = ""
        self._elements: list[TopologyElement] = []
        self._project: CloudProject | None = None
        self.size = size
        self.kind = kind
        self.providers = providers
        self.template_brief = template_brief

    @classmethod
    def fresh(cls, *args: Any, **kwargs: Any) -> Blueprint:
        """A blueprint whose auto-ids start over.

        Ids are derived from names and counted per process, so a script that
        builds several diagrams starts each from zero to keep every document
        reproducible on its own.
        """
        reset_ids()
        return cls(*args, **kwargs)

    # ----------------------------------------------------------- the words
    @property
    def slug(self) -> str:
        return self._slug

    @slug.setter
    def slug(self, value: str) -> None:
        # fullmatch: a trailing newline or space is not part of a slug
        if not _SLUG.fullmatch(str(value)):
            raise PatternError(f"slug {value!r} must be lower-case words joined by single hyphens")
        self._slug = str(value)
        self._project = None

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        if not str(value).strip():
            raise PatternError("a blueprint needs a title")
        self._title = str(value).strip()
        self._project = None

    @property
    def description(self) -> str:
        return self._description

    @description.setter
    def description(self, value: str) -> None:
        if not str(value).strip():
            raise PatternError("a blueprint needs a description; the export page shows it")
        self._description = str(value).strip()
        self._project = None

    @property
    def display(self) -> str:
        """How components draw by default: ``card`` or ``icon``."""
        return self._display

    @display.setter
    def display(self, value: str) -> None:
        if value not in _DISPLAYS:
            raise PatternError(f"display must be one of {_DISPLAYS}, not {value!r}")
        self._display = value
        self._project = None

    @property
    def theme(self) -> str:
        """The workspace theme SVG and PNG are drawn in."""
        return self._theme

    @theme.setter
    def theme(self, value: str) -> None:
        if value not in EXPORT_THEMES:
            raise PatternError(f"theme must be one of {tuple(EXPORT_THEMES)}, not {value!r}")
        self._theme = value

    # Everything below lands in the project document, so each setter drops
    # the cached one; a plain attribute here left to_project() returning the
    # document built before the change.
    @property
    def size(self) -> str:
        """The size preset the document is laid out for (``fit`` by default)."""
        return self._size

    @size.setter
    def size(self, value: str) -> None:
        self._size = str(value)
        self._project = None

    @property
    def kind(self) -> ProjectKind | None:
        """The project kind, or None to infer it from the providers."""
        return self._kind

    @kind.setter
    def kind(self, value: ProjectKind | None) -> None:
        self._kind = value
        self._project = None

    @property
    def providers(self) -> tuple[str, ...] | None:
        """The libraries the document installs, or None to infer them from the elements."""
        return self._providers

    @providers.setter
    def providers(self, value: Sequence[str] | None) -> None:
        self._providers = tuple(value) if value else None
        self._project = None

    @property
    def template_brief(self) -> str:
        return self._template_brief

    @template_brief.setter
    def template_brief(self, value: str) -> None:
        self._template_brief = str(value)
        self._project = None

    # --------------------------------------------------------- the content
    @property
    def elements(self) -> tuple[TopologyElement, ...]:
        """Top-level elements in the order they were added."""
        return tuple(self._elements)

    def add(self, *elements: TopologyElement) -> tuple[TopologyElement, ...]:
        """Place elements at the top level and hand them back."""
        for element in elements:
            if not isinstance(element, TopologyElement):
                raise PatternError(
                    f"add() takes node or frame instances, not {type(element).__name__}"
                )
            if any(element is existing for existing in self._elements):
                raise PatternError(f"{element.name!r} is already at the top level")
            self._elements.append(element)
        self._project = None
        return elements

    def link(
        self, source: TopologyElement, target: TopologyElement, **connection: Any
    ) -> Blueprint:
        """``source.to(target, ...)`` that reads as part of the plan."""
        source.to(target, **connection)
        self._project = None
        return self

    # ---------------------------------------------------------- the output
    def to_project(self) -> CloudProject:
        """The project document, built once per change and cached."""
        if not self._elements:
            raise PatternError("a blueprint needs at least one element before it can export")
        if self._project is None:
            self._project = compose.to_project(
                list(self._elements),
                slug=self._slug,
                title=self._title,
                description=self._description,
                providers=self._providers,
                kind=self._kind,
                size=self._size,
                template_brief=self._template_brief,
                display=self._display,
            )
        return self._project

    def export(
        self,
        output_dir: Path,
        *,
        formats: Sequence[str] = ("template", "html", "svg", "png"),
        display: str = "project",
        write_looks: str = "both",
        scale: float = 3,
        libraries: str = "project",
        overwrite: bool = False,
        background: str = "paper",
    ) -> ExportResult:
        """Export through :func:`infragram.compose.export`.

        ``display`` is the export look: ``project`` follows :attr:`display`,
        ``card`` or ``icon`` force one, ``both`` writes cards and an
        ``-icons`` variant of the SVG and PNG.

        ``background`` is what the picture carries behind it: ``paper`` (the
        theme's own ground, the default), ``transparent``, or a hex colour.
        """
        if display not in EXPORT_DISPLAYS:
            raise PatternError(f"display must be one of {EXPORT_DISPLAYS}, not {display!r}")
        return compose.export(
            self.to_project(),
            Path(output_dir),
            formats=tuple(formats),
            theme=self._theme,
            scale=scale,
            libraries=libraries,
            overwrite=overwrite,
            display=display,
            write_looks=write_looks,
            background=background,
        )

    @staticmethod
    def export_many(
        blueprints: Iterable[Blueprint], output_dir: Path, *, concurrency: int = 2, **options: Any
    ) -> list[ExportResult]:
        """Export several blueprints at once; see :func:`infragram.exports.export_many`.

        Every blueprint's own ``theme`` is used unless ``theme=`` is passed.
        """
        plans = list(blueprints)
        themes = {plan.theme for plan in plans}
        if "theme" not in options and len(themes) > 1:
            raise PatternError(
                "export_many draws every blueprint in one theme; these differ: "
                + ", ".join(sorted(themes))
                + ". Pass theme= to choose."
            )
        options.setdefault("theme", next(iter(themes), "light"))
        options.setdefault("formats", ("template", "html", "svg", "png"))
        return export_many(
            (plan.to_project() for plan in plans),
            Path(output_dir),
            concurrency=concurrency,
            **options,
        )

    def __repr__(self) -> str:
        return f"Blueprint({self._slug!r}, {len(self._elements)} top-level elements, display={self._display!r})"
