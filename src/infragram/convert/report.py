"""What a diagram import read and drew, as a Markdown page beside the diagram file.

Every shape the source held is in it: what it was drawn as and what the
match rested on, what it was folded into, or why it is not drawn; and
every guess (a shape drawn as a generic component because nothing it said
named a product) is listed for the person to correct.
"""

from __future__ import annotations

from ..estate.draw import Drawing
from ..estate.report import _cell, _table
from .model import Sketch

__all__ = ["sketch_comment", "write_sketch_report"]


def write_sketch_report(
    sketch: Sketch, drawing: Drawing, *, command: str, date: str, spec: str
) -> str:
    """The import's report: counts, the guesses, then every shape and where it went."""
    lines = [
        f"# {drawing.title}: what the import read",
        "",
        f"`infragram {command}` read {sketch.origin} ({sketch.format}) on {date} and wrote `{spec}`.",
        "",
        "| | |",
        "|---|---|",
        f"| Shapes read | {len(sketch.shapes)} |",
        f"| Lines read | {len(sketch.links)} |",
        f"| Drawn | {len(drawing.drawn)} |",
        f"| Folded into what holds them | {len(drawing.folded)} |",
        f"| Left out | {len(drawing.left_out)} |",
        f"| Wires | {len(drawing.wires)} |",
        "",
    ]
    if drawing.unmapped:
        lines += [
            "## Guessed from words or shape",
            "",
            "Nothing these shapes said named a product, so each is drawn as the shared "
            "component its words or its shape suggest. Change the class in the diagram file "
            "where the guess is wrong.",
            "",
            "| Shape | Drawn as |",
            "|---|---|",
            *(
                f"| {_cell(key.split(' -> ')[0])} | `infragram:{key.split(' -> ')[1]}` |"
                for key in sorted(drawing.unmapped)
            ),
            "",
        ]
    lines += _table("Drawn", "Shape", "As", sorted(drawing.drawn.items()))
    lines += _table("Folded", "Shape", "Into", sorted(drawing.folded.items()))
    lines += _table("Left out", "Shape", "Why", sorted(drawing.left_out.items()))
    notes = list(dict.fromkeys(drawing.notes))
    if notes:
        lines += ["## Notes", "", *(f"- {_cell(note)}" for note in notes), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def sketch_comment(sketch: Sketch, drawing: Drawing) -> str:
    """The import as a pull request comment: the counts, then the guesses a
    reviewer should look at, since those are where a diagram can be wrong
    without anything failing (``import:diagram --comment``)."""
    lines = [
        f"### Diagram imported: {drawing.title}",
        "",
        f"**{len(drawing.drawn)} drawn, {len(drawing.wires)} wires** from "
        f"{len(sketch.shapes)} shapes and {len(sketch.links)} lines"
        + (f"; {len(drawing.left_out)} left out" if drawing.left_out else ""),
    ]
    if drawing.unmapped:
        lines += [
            "",
            f"#### Guessed ({len(drawing.unmapped)})",
            "",
            "Nothing these shapes said named a product; check what each is drawn as.",
            "",
            "| Shape | Drawn as |",
            "|---|---|",
            *(
                f"| {_cell(key.split(' -> ')[0])} | `infragram:{key.split(' -> ')[1]}` |"
                for key in sorted(drawing.unmapped)
            ),
        ]
    if drawing.left_out:
        lines += ["", "| Left out | Why |", "|---|---|"] + [
            f"| {_cell(shape)} | {_cell(why)} |" for shape, why in sorted(drawing.left_out.items())
        ]
    lines += ["", f"<sub>Drawn by Infragram Architect from {sketch.origin}.</sub>", ""]
    return "\n".join(lines)
