"""Two versions of a diagram, drawn as one picture of what changed.

``infragram diff before after`` matches the two documents' elements by id --
the id a diagram file derives from a name, an import from an address --
and draws the second with the change marks a plan uses (changes.py), so the
picture says what the difference is the way Hava's revision compare or a
plan viewer does, from files alone:

* an element only in the second is ``added``; one only in the first is drawn
  back in where it stood, ``destroyed``; one whose name, detail, component,
  type or frame changed is ``changed``, with what changed in the report;
* a wire only in the second is drawn in the added colour, one only in the
  first drawn back in the destroyed colour (between elements the picture
  still has);
* a frame, which draws no card to colour, carries the mark on its title.

Either side may be a ``.infragram.json``, a diagram file (``.py``), or an
exported page or picture that carries its document (exports/carry.py): two
discovery runs, two commits of a document, a design and what was imported.

The same difference reads three ways: the text report a person reads, one
JSON object a pipeline reads (:func:`diff_json`, ``diff --json``), and
Markdown for a pull request comment (:func:`diff_comment`, ``diff --comment``).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ..models.changes import ACTIONS
from ..models.topology import TopologyElement
from ..projects import CloudProject
from ..utils.text import markdown_cell

__all__ = [
    "Difference",
    "ElementChange",
    "FieldChange",
    "WireChange",
    "diff_comment",
    "diff_json",
    "diff_projects",
]


class FieldChange(BaseModel):
    """One thing about an element that differs: what the two versions say,
    empty where a version says nothing (no detail, no component)."""

    field: str
    before: str
    after: str


class ElementChange(BaseModel):
    """One element added, changed or removed, with the ids a pipeline joins on."""

    id: str
    name: str
    #: ``create``, ``update`` or ``delete``: the plan's word for it, and the
    #: mark the picture draws (changes.ACTIONS).
    change: str
    #: A frame draws no card to colour, so the picture marks its title instead.
    is_frame: bool = False
    #: The frame it stands in, in the version it is drawn from; empty at the top.
    parent: str = ""
    parent_name: str = ""
    #: What differs, for an element both versions have.
    fields: list[FieldChange] = Field(default_factory=list)


class WireChange(BaseModel):
    """One wire only one version has."""

    source: str
    source_name: str
    target: str
    target_name: str
    label: str = ""
    #: ``create`` when only the second has it, ``delete`` when only the first.
    change: str


class Difference(BaseModel):
    """What changed between two documents, and the picture that shows it."""

    project: CloudProject
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[tuple[str, list[str]]] = Field(default_factory=list)
    wires_added: list[str] = Field(default_factory=list)
    wires_removed: list[str] = Field(default_factory=list)
    #: The two versions' titles, as they were before the picture retitled the second.
    before_title: str = ""
    after_title: str = ""
    #: The same changes with ids and each field's two values, for --json and --comment.
    elements: list[ElementChange] = Field(default_factory=list)
    wires: list[WireChange] = Field(default_factory=list)

    @property
    def identical(self) -> bool:
        """Nothing added, changed or removed, wires included."""
        return not (
            self.added or self.changed or self.removed or self.wires_added or self.wires_removed
        )

    @property
    def summary(self) -> str:
        parts = [
            f"{len(self.added)} added",
            f"{len(self.changed)} changed",
            f"{len(self.removed)} removed",
        ]
        wires = [f"{len(self.wires_added)} added", f"{len(self.wires_removed)} removed"]
        return ", ".join(parts) + "; wires " + ", ".join(wires)

    def report(self) -> str:
        lines = [f"Diff: {self.summary}"]
        lines += [f"  + {name}" for name in self.added]
        lines += [f"  ~ {name}: {', '.join(what)}" for name, what in self.changed]
        lines += [f"  − {name}" for name in self.removed]
        lines += [f"  + wire {text}" for text in self.wires_added]
        lines += [f"  − wire {text}" for text in self.wires_removed]
        return "\n".join(lines)


def _parents(root: TopologyElement) -> dict[str, str]:
    out: dict[str, str] = {}

    def visit(element: TopologyElement) -> None:
        for child in element.children:
            out[child.id] = element.id
            visit(child)

    visit(root)
    return out


def _signature(element: TopologyElement, parent: str | None) -> dict[str, Any]:
    component = element.component
    return {
        "name": element.name,
        "type": element.type,
        "component": f"{component.provider}:{component.service_id}" if component else "",
        "detail": str(element.attributes.get("detail") or ""),
        "frame": parent or "",
    }


def _mark(element: TopologyElement, change: str) -> None:
    if element.is_frame:
        element.name = f"{ACTIONS[change].mark} {element.name}"
    else:
        element.attributes["change"] = change


def _wires(root: TopologyElement) -> dict[tuple[str, str, str], tuple[TopologyElement, Any]]:
    return {
        (element.id, connection.target, connection.label): (element, connection)
        for element in root.walk()
        for connection in element.connections
    }


def diff_projects(before: CloudProject, after: CloudProject) -> Difference:
    """The second document, marked with how it differs from the first."""
    result = after.model_copy(deep=True)
    root = result.topology
    old_index, new_index = before.topology.index(), root.index()
    old_parents, new_parents = _parents(before.topology), _parents(root)
    difference = Difference(project=result, before_title=before.title, after_title=after.title)
    # names as the documents give them: the picture puts a frame's mark in its name
    names = {element.id: element.name for element in before.topology.walk()}
    names.update((element.id, element.name) for element in after.topology.walk())

    def record(
        element: TopologyElement,
        change: str,
        parent: str | None,
        fields: list[FieldChange] | None = None,
    ) -> None:
        inside = "" if parent in (None, before.topology.id, root.id) else str(parent)
        difference.elements.append(
            ElementChange(
                id=element.id,
                name=element.name,
                change=change,
                is_frame=element.is_frame,
                parent=inside,
                parent_name=names.get(inside, inside),
                fields=fields or [],
            )
        )

    for element_id, element in new_index.items():
        if element is root:
            continue
        old = old_index.get(element_id)
        if old is None:
            difference.added.append(element.name)
            record(element, "create", new_parents.get(element_id))
            _mark(element, "create")
            continue
        was = _signature(old, old_parents.get(element_id))
        now = _signature(element, new_parents.get(element_id))
        fields = [
            FieldChange(field=key, before=str(was[key]), after=str(now[key]))
            for key in was
            if was[key] != now[key]
        ]
        if fields:
            what = [f"{item.field} {item.before or '-'} → {item.after or '-'}" for item in fields]
            difference.changed.append((element.name, what))
            record(element, "update", new_parents.get(element_id), fields)
            _mark(element, "update")

    # what the first had and the second has not, drawn back in where it stood
    def restore(old: TopologyElement, into: TopologyElement) -> None:
        copy = old.model_copy(deep=True)
        copy.children = []
        copy.connections = []
        _mark(copy, "delete")
        into.children.append(copy)
        difference.removed.append(old.name)
        record(old, "delete", old_parents.get(old.id))
        for child in old.children:
            if child.id not in new_index:
                restore(child, copy)

    for element_id, old in old_index.items():
        if old is before.topology or element_id in new_index:
            continue
        parent_id = old_parents.get(element_id)
        if parent_id is not None and parent_id not in new_index:
            continue  # its frame is restored too, and brings it along
        into = root.index().get(parent_id) if parent_id else root
        restore(old, into or root)

    old_wires, new_wires = _wires(before.topology), _wires(root)
    present = root.index()

    def wire(key: tuple[str, str, str], change: str) -> WireChange:
        source, target, label = key
        return WireChange(
            source=source,
            source_name=names.get(source, source),
            target=target,
            target_name=names.get(target, target),
            label=label,
            change=change,
        )

    for key, (element, connection) in new_wires.items():
        if key not in old_wires:
            _paint(element, connection.target, "create")
            difference.wires_added.append(_wire_text(key, present))
            difference.wires.append(wire(key, "create"))
    for key, (_element, connection) in old_wires.items():
        if key in new_wires or key[0] not in present or key[1] not in present:
            continue
        source = present[key[0]]
        source.connections.append(connection.model_copy(deep=True))
        _paint(source, connection.target, "delete")
        difference.wires_removed.append(_wire_text(key, present))
        difference.wires.append(wire(key, "delete"))

    result.presentation.notes = (f"Diff: {difference.summary}", *result.presentation.notes)
    result.title = (
        f"{after.title} (compared with {before.title})"
        if after.title != before.title
        else f"{after.title}: what changed"
    )
    return difference


def _paint(source: TopologyElement, target: str, change: str) -> None:
    styles = source.attributes.setdefault("editor_edge_styles", {})
    styles.setdefault(target, {})["stroke"] = ACTIONS[change].stroke


def _wire_text(key: tuple[str, str, str], index: dict[str, TopologyElement]) -> str:
    source, target, label = key
    name = lambda element_id: index[element_id].name if element_id in index else element_id  # noqa: E731
    return f"{name(source)} → {name(target)}" + (f" ({label})" if label else "")


def diff_json(difference: Difference) -> dict[str, Any]:
    """The change report as one JSON-ready object (``diff --json``): the counts
    the text report starts with, then every element added, changed and
    removed and every wire added and removed, with ids beside names and each
    changed field's two values. Lists are sorted by id, so the same two
    versions always give the same text, whatever order their files list things."""

    def elements(change: str) -> list[dict[str, Any]]:
        rows = sorted(
            (item for item in difference.elements if item.change == change),
            key=lambda item: item.id,
        )
        return [row.model_dump(exclude={"change"}) for row in rows]

    def wires(change: str) -> list[dict[str, Any]]:
        rows = sorted(
            (item for item in difference.wires if item.change == change),
            key=lambda item: (item.source, item.target, item.label),
        )
        return [row.model_dump(exclude={"change"}) for row in rows]

    return {
        "before_title": difference.before_title,
        "after_title": difference.after_title,
        "identical": difference.identical,
        "summary": difference.summary,
        "counts": {
            "added": len(difference.added),
            "changed": len(difference.changed),
            "removed": len(difference.removed),
            "wires_added": len(difference.wires_added),
            "wires_removed": len(difference.wires_removed),
        },
        "added": elements("create"),
        "changed": elements("update"),
        "removed": elements("delete"),
        "wires_added": wires("create"),
        "wires_removed": wires("delete"),
    }


def _cell(text: str) -> str:
    return markdown_cell(text, squeeze=True)


def _code(text: str) -> str:
    if not text:
        return "none"
    if "`" in text:
        return f"`` {_cell(text)} ``"
    return f"`{_cell(text)}`"


def diff_comment(
    difference: Difference,
    *,
    before: str | None = None,
    after: str | None = None,
    picture: str | None = None,
) -> str:
    """Markdown for a pull request comment on what changed (``diff --comment``),
    laid out as a plan's comment is (estate/comment.py): the count first, then
    a table for each kind of change in the order the report lists them, then
    the wires. ``before`` and ``after`` name the two versions (file names, or
    commits); ``picture`` is a link or path to the drawing."""
    title = difference.after_title or difference.project.title
    lines = [f"### Diagram changes: {_cell(title)}", ""]
    if difference.identical:
        lines.append("The two versions draw the same thing.")
    else:
        lines.append(f"**Diff: {difference.summary}**")
    if difference.before_title and difference.before_title != difference.after_title:
        lines += ["", f"Compared with *{_cell(difference.before_title)}*."]
    if picture:
        lines += ["", f"![What changed, drawn]({picture})"]
    for change, heading in (("create", "Added"), ("update", "Changed"), ("delete", "Removed")):
        rows = [item for item in difference.elements if item.change == change]
        if not rows:
            continue
        lines += ["", f"#### {ACTIONS[change].mark} {heading} ({len(rows)})", ""]
        if change == "update":
            lines += ["| Element | What changed |", "|---|---|"]
            for row in rows:
                what = "; ".join(
                    f"{item.field} {_code(item.before)} → {_code(item.after)}"
                    for item in row.fields
                )
                lines.append(f"| {_element_cell(row)} | {what} |")
        else:
            lines += ["| Element | In |", "|---|---|"]
            for row in rows:
                lines.append(f"| {_element_cell(row)} | {_cell(row.parent_name) or 'top level'} |")
    if difference.wires:
        lines += ["", f"#### Wires ({len(difference.wires)})", ""]
        lines += ["| | From | To | Label |", "|---|---|---|---|"]
        for wire in difference.wires:
            lines.append(
                f"| {ACTIONS[wire.change].mark} | {_cell(wire.source_name)} | "
                f"{_cell(wire.target_name)} | {_cell(wire.label)} |"
            )
    compared = f": {_code(before)} → {_code(after)}" if before and after else ""
    lines += ["", f"<sub>Compared by Infragram Architect{compared}.</sub>", ""]
    return "\n".join(lines)


def _element_cell(row: ElementChange) -> str:
    return f"{_cell(row.name)} ({_code(row.id)}{', frame' if row.is_frame else ''})"
