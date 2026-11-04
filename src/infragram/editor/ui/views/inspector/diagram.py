"""Diagram panel: canvas facts, grid, connector routing, component display, template notes.

Styles: inspector.css.
"""

from __future__ import annotations

from html import escape
from textwrap import shorten

from .....builders.scene import Scene
from .....catalog import ARCHITECTURE_FRAME_PRESETS
from .....projects import CloudProject
from ...components import button, segmented
from ...icons import icon


def setting(label: str, control: str, label_id: str = "") -> str:
    """One row: what it is on the left, what it is set to on the right."""
    identity = f' id="{label_id}"' if label_id else ""
    return f'<div class="setting-row"><span{identity}>{escape(label)}</span>{control}</div>'


def reading(value: str, attrs: str = "") -> str:
    """A setting the page reports but does not let anyone change here."""
    return f'<span class="setting-value"{" " + attrs if attrs else ""}>{value}</span>'


def _starter_label(preset_id: str) -> str:
    """What the starter stack calls itself, from the preset that defines it."""
    for preset in ARCHITECTURE_FRAME_PRESETS:
        definition = dict(preset)
        if definition.get("id") == preset_id:
            return str(definition.get("label") or preset_id)
    return preset_id


def template_brief(project: CloudProject, architecture_label: str) -> str:
    """The node reference a starter template ships with, and its one button.

    Only a template carrying a brief shows this, and only one naming a
    starter preset shows the button, so an ordinary document renders nothing
    here rather than an empty disclosure.
    """
    if not project.template_brief:
        return ""
    starter_markup = ""
    if project.starter_preset:
        starter_markup = button(
            f"Add {_starter_label(project.starter_preset)}",
            variant="tonal",
            classes="template-starter",
            attrs=f'data-template-starter="{escape(project.starter_preset)}"',
        )
    return (
        '<details class="md-card md-card--outlined template-brief" data-template-brief>'
        f'<summary class="md-list-item md-list-item--dense md-subheader"><span>{escape(architecture_label)} node reference</span>{icon("expand", extra_class="md-expand-icon")}</summary>'
        f'{starter_markup}<details class="reference-section" open>'
        f'<summary class="md-list-item md-list-item--dense"><span>Overview</span>{icon("expand", extra_class="md-expand-icon")}</summary>'
        f"<p>{escape(shorten(project.description or project.template_brief, width=280, placeholder='…'))}</p></details>"
        '<details class="reference-section">'
        f'<summary class="md-list-item md-list-item--dense"><span>Full reference</span>{icon("expand", extra_class="md-expand-icon")}</summary>'
        f"<pre>{escape(project.template_brief)}</pre></details>"
        "</details>"
    )


#: What the drawing holds, counted by the runtime as it changes.
STATS = (("nodes", "Components"), ("edges", "Connectors"), ("boundaries", "Frames"))


def stats() -> str:
    return "".join(
        f'<div class="diagram-stat">'
        f'<strong data-diagram-stat="{key}">0</strong><span>{label}</span></div>'
        for key, label in STATS
    )


def panel(scene: Scene, brief_markup: str) -> str:
    # The grid is a switch: it says what it *is*. The other two are choices
    # of two, so each shows both and marks the one in force -- a button
    # carrying one word cannot say what the other option would be.
    grid_switch = (
        '<button type="button" class="md-switch" role="switch" aria-checked="false" '
        'aria-labelledby="inspector-grid-label" data-inspector-grid-toggle></button>'
    )
    routing = segmented(
        "inspector-routing-label",
        (
            ("Around", 'data-routing="around"', "Route connectors around components", True),
            ("Direct", 'data-routing="direct"', "Draw connectors on the direct path", False),
        ),
        attrs="data-inspector-routing",
    )
    crossings = segmented(
        "inspector-crossings-label",
        (
            (
                "Bridge",
                'data-crossings="bridge"',
                "Mark separate crossing wires with a small bridge",
                scene.crossings == "bridge",
            ),
            (
                "Plain",
                'data-crossings="plain"',
                "Draw crossing wires without a bridge",
                scene.crossings != "bridge",
            ),
        ),
        attrs="data-inspector-crossings",
    )
    frame_lines = segmented(
        "inspector-frame-lines-label",
        tuple(
            (
                label,
                f'data-frame-lines="{key}"',
                f"Draw every frame's border {words}",
                scene.frame_lines == key,
            )
            for key, label, words in (
                ("thin", "Thin", "at its own width"),
                ("medium", "Medium", "heavier"),
                ("thick", "Thick", "heavier still"),
            )
        ),
        attrs="data-inspector-frame-lines",
    )
    # three choices, shown side by side like the rows above it
    title_placement = segmented(
        "inspector-title-label",
        (
            ("Header", 'data-title-placement="header"', "Show the title in the page header", True),
            ("Below", 'data-title-placement="caption"', "Show the title below the diagram", False),
            ("Hidden", 'data-title-placement="hidden"', "Show no title", False),
        ),
        attrs="data-inspector-title",
    )
    display = segmented(
        "inspector-display-label",
        (
            ("Cards", 'data-project-display="card"', "Show every component as a card", False),
            (
                "Icons",
                'data-project-display="icon"',
                "Show every component as a bare icon with its caption",
                True,
            ),
        ),
        attrs="data-inspector-display",
    )
    return f"""            <section class="inspector-section" data-inspector-panel="diagram" role="tabpanel">
              <h2>Diagram</h2>
              <div class="diagram-stats" aria-label="Diagram contents">{stats()}</div>
              {setting("Canvas", reading(f"{scene.width} × {scene.height}", "data-inspector-canvas"))}
              {setting("Snap to grid", reading("4 px"))}
              {setting("Show grid", grid_switch, "inspector-grid-label")}
              {setting("Connectors", routing, "inspector-routing-label")}
              {setting("Crossings", crossings, "inspector-crossings-label")}
              {setting("Components", display, "inspector-display-label")}
              {setting("Frame lines", frame_lines, "inspector-frame-lines-label")}
              {setting("Diagram title", title_placement, "inspector-title-label")}
              {setting("Show legend", '<button type="button" class="md-switch" role="switch" aria-checked="false" aria-labelledby="inspector-legend-label" data-legend-setting="showLegend"></button>', "inspector-legend-label")}
              {setting("Legend in exports", '<button type="button" class="md-switch" role="switch" aria-checked="false" aria-labelledby="inspector-export-legend-label" data-legend-setting="exportLegend"></button>', "inspector-export-legend-label")}
              {brief_markup}
            </section>"""


__all__ = ["STATS", "panel", "reading", "setting", "stats", "template_brief"]
