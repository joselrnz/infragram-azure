"""A plan's changes as a pull request comment (``import:terraform --comment``).

The picture shows the plan; the comment says it in words where a reviewer
reads first: the count ``terraform plan`` ends with, then every resource the
plan touches, by action, with what the diagram draws it as. A CI job posts it
beside the uploaded picture (assets/ci/, references/terraform.md).
"""

from __future__ import annotations

from ..models.changes import ACTIONS, plan_summary
from .draw import Drawing
from .model import Estate

__all__ = ["plan_comment"]


def plan_comment(estate: Estate, drawing: Drawing, *, picture: str | None = None) -> str:
    """Markdown for the plan's changes; ``picture`` is a link or path to the drawing."""
    changed = [found for found in estate.resources if found.mode == "managed" and found.change]
    lines = [f"### Infrastructure diagram: {estate.title}", ""]
    if not changed:
        lines.append("This plan changes nothing that is drawn.")
    else:
        lines.append(f"**Plan: {plan_summary(found.change for found in changed)}**")
    if picture:
        lines += ["", f"![The plan, drawn]({picture})"]
    for action, spec in ACTIONS.items():
        rows = [found for found in changed if found.change == action]
        if not rows:
            continue
        lines += [
            "",
            f"#### {spec.mark} {spec.word.capitalize()} ({len(rows)})",
            "",
            "| Resource | Drawn as |",
            "|---|---|",
        ]
        for found in sorted(rows, key=lambda item: item.address):
            where = (
                drawing.drawn.get(found.address)
                or drawing.folded.get(found.address)
                or drawing.left_out.get(found.address)
                or "not drawn"
            )
            lines.append(f"| `{found.address}` | {where} |")
    lines += ["", f"<sub>Drawn by Infragram Architect from {estate.origin}.</sub>", ""]
    return "\n".join(lines)
