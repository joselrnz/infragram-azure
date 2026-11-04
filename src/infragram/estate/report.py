"""What an import read, drew, folded and left out, as a Markdown page.

It sits beside the diagram file, so the person editing the diagram can see
every resource the estate holds and where each went: which element it is,
what it was folded into, or why it is not drawn.
"""

from __future__ import annotations

from collections import Counter

from ..utils.text import markdown_cell as _cell
from .draw import Drawing
from .model import Estate

__all__ = ["write_report"]


def _table(heading: str, first: str, second: str, rows: list[tuple[str, str]]) -> list[str]:
    if not rows:
        return []
    return [
        f"## {heading} ({len(rows)})",
        "",
        f"| {first} | {second} |",
        "|---|---|",
        *(f"| `{_cell(a)}` | {_cell(b)} |" for a, b in rows),
        "",
    ]


def write_report(estate: Estate, drawing: Drawing, *, command: str, date: str, spec: str) -> str:
    """The import's report: counts, then every resource and where it went."""
    left_out = Counter(reason for reason in drawing.left_out.values())
    lines = [
        f"# {drawing.title}: what the import read",
        "",
        f"`infragram {command}` read {estate.origin} on {date} and wrote `{spec}`.",
        "",
        "| | |",
        "|---|---|",
        f"| Resources read | {len(estate.resources)} |",
        f"| Drawn | {len(drawing.drawn)} |",
        f"| Folded into what they belong to, or drawn as wires | {len(drawing.folded)} |",
        f"| Left out | {len(drawing.left_out)} |",
        f"| Wires | {len(drawing.wires)} |",
        "",
    ]
    if drawing.unmapped:
        lines += [
            "## Drawn as a generic component",
            "",
            "These types have no entry in the import's table yet, so each is drawn as its "
            "provider's generic component, captioned with the type.",
            "",
            "| Type | How many |",
            "|---|---|",
            *(f"| `{t}` | {n} |" for t, n in sorted(drawing.unmapped.items())),
            "",
        ]
    if left_out:
        lines += [
            "## Why resources are left out",
            "",
            "| Reason | How many |",
            "|---|---|",
            *(f"| {_cell(reason)} | {n} |" for reason, n in left_out.most_common()),
            "",
        ]
    lines += _table("Drawn", "Resource", "As", sorted(drawing.drawn.items()))
    lines += _table("Folded", "Resource", "Into", sorted(drawing.folded.items()))
    lines += _table("Left out", "Resource", "Why", sorted(drawing.left_out.items()))
    notes = list(dict.fromkeys(drawing.notes))
    if notes:
        lines += ["## Notes", "", *(f"- {note}" for note in notes), ""]
    return "\n".join(lines).rstrip("\n") + "\n"
