"""What a Terraform plan does to an element, and how a picture shows it.

``import:terraform`` of a plan (``terraform show -json plan.out``) marks
every card with the action the plan takes on it -- ``element.change("create")``
in the diagram file, ``attributes["change"]`` in the document -- the way
Rover, Inkdrop and the hosted plan viewers do. A picture shows it three ways,
all through what both renderers already draw, so the editor and the static
picture agree without a line of new drawing code:

* the card's outline and fill in the action's colour (the same ``fill`` and
  ``stroke`` a card restyled in the editor carries);
* a mark and a word at the head of its detail line (``+ added``), which the
  icon look, with no card to colour, still shows;
* the plan's count in the band above the drawing, the way ``terraform plan``
  ends: ``3 to add, 1 to change, 1 to destroy``.

A resource changed outside Terraform -- ``resource_drift`` in a plan, all a
``terraform plan -refresh-only -json`` holds -- is marked ``drift``. When the
plan also acts on it, the planned action wins: it is what an apply does.

A card the author styled by hand keeps its own colours.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ACTIONS",
    "Action",
    "action_of",
    "combined",
    "detail_with_change",
    "plan_summary",
    "style_of",
]


class Action(BaseModel):
    """How one plan action reads and paints."""

    model_config = ConfigDict(frozen=True)

    mark: str
    word: str
    #: the words ``terraform plan`` counts it with
    counted: str
    stroke: str
    fill: str


#: The actions, in the order a summary lists them. Colours tuned for the
#: light ground: the stroke carries the meaning, the fill only tints.
ACTIONS: dict[str, Action] = {
    "create": Action(mark="+", word="added", counted="to add", stroke="#2e7d32", fill="#edf7ee"),
    "update": Action(
        mark="~", word="changed", counted="to change", stroke="#b26a00", fill="#fff5e5"
    ),
    "replace": Action(
        mark="±", word="replaced", counted="to replace", stroke="#7b1fa2", fill="#f6ecf8"
    ),
    "delete": Action(
        mark="−", word="destroyed", counted="to destroy", stroke="#c62828", fill="#fdeded"
    ),
    # changed outside Terraform: a refresh-only plan's resource_drift
    "drift": Action(mark="≈", word="drifted", counted="drifted", stroke="#1565c0", fill="#e9f1fb"),
}


def action_of(actions: Iterable[str]) -> str | None:
    """One resource's action from the list ``resource_changes`` gives it:
    ``[delete, create]`` or ``[create, delete]`` is a replace; ``no-op`` and
    ``read`` change nothing drawn."""
    listed = [str(action) for action in actions]
    if "create" in listed and "delete" in listed:
        return "replace"
    for action in ("create", "update", "delete"):
        if action in listed:
            return action
    return None


def combined(changes: Iterable[str | None]) -> str | None:
    """One card's action from the resources drawn as it: all added is added,
    all destroyed is destroyed, a replace anywhere is a replace, and any
    other mix is a change."""
    found = [change for change in changes if change]
    if not found:
        return None
    if len(set(found)) == 1:
        return found[0]
    return "replace" if "replace" in found else "update"


def change_of(attributes: dict[str, Any]) -> str | None:
    change = attributes.get("change")
    return str(change) if change in ACTIONS else None


def style_of(attributes: dict[str, Any]) -> dict[str, str] | None:
    """The card colours its change paints, or None. A card the author
    styled by hand (``editor_style``) keeps its own."""
    change = change_of(attributes)
    if change is None or isinstance(attributes.get("editor_style"), dict):
        return None
    return {"stroke": ACTIONS[change].stroke, "fill": ACTIONS[change].fill}


def detail_with_change(detail: str, attributes: dict[str, Any]) -> str:
    """The detail line with the change's mark and word at its head."""
    change = change_of(attributes)
    if change is None:
        return detail
    head = f"{ACTIONS[change].mark} {ACTIONS[change].word}"
    return f"{head} · {detail}" if detail else head


def plan_summary(changes: Iterable[str | None]) -> str:
    """``3 to add, 1 to change, 1 to destroy``: every action that occurs."""
    counts = {action: 0 for action in ACTIONS}
    for change in changes:
        if change in counts:
            counts[change] += 1
    return ", ".join(
        f"{count} {ACTIONS[action].counted}" for action, count in counts.items() if count
    )
