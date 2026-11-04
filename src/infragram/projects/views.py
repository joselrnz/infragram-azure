"""A view: part of the one diagram, selected by rule, drawn as its own picture.

One diagram serves several readers. ``--view NAME`` draws the part a reader
asked for, laid out afresh, from the same document:

- **a level**: name a frame, by id or by caption, and the picture is that
  frame and everything in it -- one subscription, one resource group, one
  VNet, one VPC, one namespace. Nothing has to be declared for this;
- **a rule**: ``tag:env=prod``, ``category:networking``, ``name:*-prod-*``
  (the naming convention), ``id:...``, or a view the document declares with
  ``include`` and ``exclude`` lists of those.

What comes with a selection: a frame is drawn when anything in it is, a wire
when both its ends are, and nothing is bridged. An environment frame is not
drawn in a view: the names already say the environment, and the view's name
stands at the top of the picture instead.

The result is a project document like any other, so every export, the
checker and the editor read it unchanged.

``infragram views`` lists what can be named; :func:`views_json` is that list
as one JSON object (``views --json``).
"""

from __future__ import annotations

import difflib
import fnmatch
from typing import Any

from ..models.topology import TopologyElement
from ..utils.text import SLUG, slugify
from .document import CloudProject
from .parts import View, ViewSelector

__all__ = [
    "SHORTHANDS",
    "ViewError",
    "frames_of",
    "resolve",
    "select",
    "selector_text",
    "views_json",
]

#: The ``kind:value`` forms ``--view`` takes, beside a view's id and a frame.
SHORTHANDS = ("tag", "category", "name", "within", "id")
#: A frame that says which environment its contents are: never drawn in a view.
_ENVIRONMENT = "environment"


class ViewError(ValueError):
    """A view that cannot be resolved or selects nothing."""


def _category(element: TopologyElement) -> str:
    """The element's catalog category, else the category its attributes name,
    so a component no catalog lists can still be selected by category."""
    from ..catalog.components import component_category

    if element.component is None:
        return ""
    return component_category(element) or str(element.attributes.get("category") or "")


def _caption(element: TopologyElement) -> str:
    """A frame's name without the address range its caption carries."""
    return element.name.split(" · ")[0].strip()


def frames_of(project: CloudProject) -> list[tuple[int, TopologyElement]]:
    """Every frame a view can be scoped to, with its depth, in document order."""
    out: list[tuple[int, TopologyElement]] = []

    def visit(element: TopologyElement, depth: int) -> None:
        for child in element.children:
            if child.children:
                out.append((depth, child))
                visit(child, depth + 1)

    visit(project.topology, 0)
    return out


def selector_text(selector: ViewSelector) -> str:
    """A view's rule as ``--view`` spells it: ``tag:env=prod``, ``within:vpc-shop``."""
    key, value = next(item for item in selector.model_dump().items() if item[1] is not None)
    return f"{key}:{value}"


def views_json(project: CloudProject) -> dict[str, Any]:
    """What ``--view`` can draw from *project*, as one JSON-ready object
    (``views --json``): the views it declares, in the order it declares them,
    with their rules as ``--view`` spells them; every frame in document order
    with its level (0 outermost), the frame around it and how many components
    it holds, however deep; and the kinds of rule ``--view`` takes."""
    frames = frames_of(project)
    parents = {child.id: frame.id for _, frame in frames for child in frame.children}
    return {
        "title": project.title,
        "slug": project.slug,
        "views": [
            {
                "id": view.id,
                "title": view.title or view.id,
                "extends": view.extends,
                "include": [selector_text(selector) for selector in view.include],
                "exclude": [selector_text(selector) for selector in view.exclude],
            }
            for view in project.views
        ],
        "frames": [
            {
                "id": frame.id,
                "name": frame.name,
                "type": frame.type,
                "level": depth,
                "parent": parents.get(frame.id),
                "components": sum(1 for element in frame.walk() if not element.children),
            }
            for depth, frame in frames
        ],
        "rule_kinds": list(SHORTHANDS),
    }


def _matches(selector: ViewSelector, element: TopologyElement) -> bool:
    if selector.id is not None:
        return element.id == selector.id
    if selector.within is not None:
        return element.id == selector.within
    if selector.name is not None:
        return fnmatch.fnmatchcase(element.name.casefold(), selector.name.casefold())
    if selector.category is not None:
        return not element.children and _category(element) == selector.category
    if selector.tag is not None:
        key, _, value = selector.tag.partition("=")
        tags = element.attributes.get("tags")
        return isinstance(tags, dict) and key in tags and str(tags[key]) == value
    return False


def _chain(project: CloudProject, view: View) -> list[View]:
    """The view and the views it extends, outermost first; a cycle is refused."""
    declared = {item.id: item for item in project.views}
    chain, seen = [view], {view.id}
    while chain[0].extends:
        parent = declared.get(chain[0].extends)
        if parent is None:
            raise ViewError(
                f"view {chain[0].id!r} extends {chain[0].extends!r}, which is not a view"
            )
        if parent.id in seen:
            raise ViewError(f"view {view.id!r} extends itself through {parent.id!r}")
        seen.add(parent.id)
        chain.insert(0, parent)
    return chain


def _kept(project: CloudProject, view: View, inside: set[str] | None) -> set[str]:
    """The ids of the components one view's rules keep, of those in *inside*."""
    kept: set[str] = set()

    def visit(element: TopologyElement, included: bool, excluded: bool) -> None:
        included = included or any(_matches(selector, element) for selector in view.include)
        excluded = excluded or any(_matches(selector, element) for selector in view.exclude)
        mine = included and not excluded and (inside is None or element.id in inside)
        if not element.children and mine:
            kept.add(element.id)
        for child in element.children:
            visit(child, included, excluded)

    for child in project.topology.children:
        visit(child, not view.include, False)
    return kept


def resolve(project: CloudProject, name: str) -> View:
    """The view *name* means: one the document declares, a ``kind:value``
    rule, or the frame of that id or caption."""
    wanted = name.strip()
    for view in project.views:
        if view.id == wanted:
            return view
    kind, colon, value = wanted.partition(":")
    if colon and kind in SHORTHANDS and value.strip():
        slug = slugify(f"{kind}-{value}")
        return View(
            id=slug if slug != kind else f"{kind}-view",
            # what stands at the top of the picture: the value, without the pattern's stars
            title=value.strip().strip("*-_ ") or value.strip(),
            include=(ViewSelector(**{kind: value.strip()}),),
        )
    frames = [frame for _, frame in frames_of(project)]
    hits = [frame for frame in frames if frame.id == wanted] or [
        frame
        for frame in frames
        if wanted.casefold() in (frame.name.casefold(), _caption(frame).casefold())
    ]
    if len(hits) == 1:
        frame = hits[0]
        return View(id=frame.id, title=frame.name, include=(ViewSelector(within=frame.id),))
    if len(hits) > 1:
        raise ViewError(
            f"{len(hits)} frames are called {wanted!r}; name one by id: "
            + ", ".join(frame.id for frame in hits)
        )
    known = [view.id for view in project.views] + [frame.id for frame in frames]
    near = difflib.get_close_matches(wanted, known, n=4, cutoff=0.5)
    hint = f"; did you mean {', '.join(near)}?" if near else ""
    raise ViewError(
        f"no view or frame {wanted!r}{hint} (`infragram views <diagram>` lists them; a rule is "
        f"{', '.join(f'{kind}:...' for kind in SHORTHANDS[:3])})"
    )


def select(project: CloudProject, view: View) -> tuple[CloudProject, list[str]]:
    """The part of *project* the view selects, as a project of its own, and
    notes on what the view names that the drawing no longer has."""
    notes: list[str] = []
    known = project.topology.index()
    chain = _chain(project, view)
    for item in chain:
        for selector in (*item.include, *item.exclude):
            target = selector.within or selector.id
            if target is not None and target not in known:
                notes.append(f"view {item.id!r} names {target!r}, which the drawing does not hold")
    kept: set[str] | None = None
    for item in chain:
        kept = _kept(project, item, kept)
    assert kept is not None
    if not kept:
        raise ViewError(f"view {view.id!r} selects nothing in {project.title!r}")

    def prune(element: TopologyElement) -> list[TopologyElement]:
        """The element as the view draws it: itself, the children an
        environment frame gives up, or nothing."""
        if not element.children:
            if element.id not in kept:
                return []
            return [element]
        children = [drawn for child in element.children for drawn in prune(child)]
        if not children:
            return []
        if element.type == _ENVIRONMENT:
            return children
        return [element.model_copy(update={"children": children})]

    def wired(element: TopologyElement, drawn: set[str]) -> TopologyElement:
        """The element with only the wires whose other end is drawn too."""
        return element.model_copy(
            update={
                "children": [wired(child, drawn) for child in element.children],
                "connections": [c for c in element.connections if c.target in drawn],
            }
        )

    # a view of levels alone stands on those frames: what is around them is not drawn
    scopes = [
        selector.within
        for selector in view.include
        if selector.within is not None and selector.within in known
    ]
    if scopes and len(scopes) == len(view.include) and not view.extends:
        roots = [drawn for scope in scopes for drawn in prune(known[scope])]
    else:
        roots = [drawn for child in project.topology.children for drawn in prune(child)]
    drawn = {item.id for root in roots for item in root.walk()}
    roots = [wired(root, drawn) for root in roots]
    title = view.title or view.id
    slug = f"{project.slug}-{view.id}"
    if not SLUG.fullmatch(slug):
        # an id is a file name, not a caption: a view of name:wéb* is name-w-b
        slug = f"{project.slug}-{slugify(view.id, fallback='view')}"
    presentation = project.presentation.model_copy(
        update={"notes": (title, *project.presentation.notes)}
    )
    selected = project.model_copy(
        update={
            "slug": slug,
            "title": f"{project.title}: {title}",
            "views": (),
            "presentation": presentation,
            "topology": project.topology.model_copy(update={"children": roots}),
        }
    )
    # the same checks a loaded document passes: ids, wires, layers
    return CloudProject.model_validate(selected.model_dump()), notes
