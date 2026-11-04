"""Style panel: what one selected object looks like -- its display mode, a
frame's own settings, and its outline.

Styles: inspector.css. Every control is a Material component (``md-*``); the
rows that vary are the tables below.
"""

from __future__ import annotations

from .....builders import metrics
from ...components import button, empty_state, field, segmented

#: Card or icon, per component. The third value is the name a reader gets,
#: which says what the mode *is* where the label only has room to say which
#: one it is.
DISPLAY_MODES = (
    ("Card", "card", "Card with text"),
    ("Icon", "icon", "Icon only"),
)

#: The outlines offered for a selected object, in the order they are shown.
#: Each sets the stroke only; Neutral takes the outline off again. None of
#: them names a provider: the accent is the editor's own.
STYLE_PRESETS = (
    ("neutral", "Neutral"),
    ("accent-outline", "Accent"),
    ("muted-outline", "Muted"),
    ("danger-outline", "Critical"),
)

#: The shapes a component may take (builders/panels.py); Rectangle is the
#: card's own. Only Rectangle and Note carry compartments.
BOX_SHAPES = (
    ("Rectangle", "rect", "The card's own rectangle"),
    ("Ellipse", "ellipse", "An ellipse, for a person or a customer"),
    ("Hexagon", "hexagon", "A hexagon, for a managed control plane"),
    ("Note", "note", "A note with a folded corner, for a contract or a caveat"),
)

#: What a selected frame does to everything inside it, one row each.
FRAME_CONTENTS = (
    ("Cards", "card", "Show every component in this frame as a card"),
    ("Icons", "icon", "Show every component in this frame as an icon"),
)


def display_modes() -> str:
    """The two modes, each named for a reader who cannot see which is which.

    The word on the button has room for "Icon"; the name it answers to is
    "Icon only", which is what the mode actually does.
    """
    buttons = "".join(
        f'<button type="button" class="display-mode-button" data-display-mode="{mode}" '
        f'aria-label="{title}" aria-pressed="false" disabled>{label}</button>'
        for label, mode, title in DISPLAY_MODES
    )
    return (
        f'<div class="md-segmented md-segmented--block" role="group" '
        f'aria-label="Component display mode">{buttons}</div>'
    )


def frame_settings() -> str:
    """A frame's own rows: whether it is highlighted, how its contents are
    drawn, and the review that lists every component inside it."""
    switch = (
        '<button type="button" class="md-switch" role="switch" aria-checked="false" '
        'aria-labelledby="frame-highlight-label" data-frame-highlight-toggle></button>'
    )
    contents = segmented(
        "frame-display-label",
        tuple(
            (label, f'data-frame-display="{mode}"', title, False)
            for label, mode, title in FRAME_CONTENTS
        ),
        attrs="data-frame-display-group",
    )
    return "\n                ".join(
        (
            f'<div class="setting-row"><span id="frame-highlight-label">Highlight</span>{switch}</div>',
            f'<div class="setting-row"><span id="frame-display-label">Contents</span>{contents}</div>',
            button("Review components", variant="outlined", attrs="data-frame-review-open"),
        )
    )


def box_settings() -> str:
    """A component's shape, its tone and its compartments (compose.md,
    Panels). Each tone is a chip with its swatch; the page names a tone by
    what the diagram says it means, where it says."""
    shapes = segmented(
        "box-shape-label",
        tuple(
            (label, f'data-node-shape="{shape}"', title, shape == "rect")
            for label, shape, title in BOX_SHAPES
        ),
        attrs="data-node-shape-group",
    )
    tones = "".join(
        f'<button type="button" class="md-chip md-chip--leading tone-chip" data-node-tone="{name}" '
        f'aria-pressed="false" disabled><span class="tone-swatch" '
        f'style="--tone-fill:{tone.fill};--tone-line:{tone.stroke}"></span>{name.capitalize()}</button>'
        for name, tone in metrics.tones().items()
    )
    none = (
        '<button type="button" class="md-chip tone-chip" data-node-tone="" aria-pressed="true" '
        "disabled>None</button>"
    )
    sections = field(
        "Compartments",
        '<textarea class="md-field__input md-field__input--area" data-node-sections rows="3" '
        'spellcheck="false" autocomplete="off" disabled></textarea>',
    )
    return "\n                ".join(
        (
            # its words over the four, as the tones' are: beside them, four
            # shapes were wider than the inspector
            f'<div class="box-shapes"><span id="box-shape-label">Shape</span>{shapes}</div>',
            '<div class="box-tones"><span id="box-tone-label">Tone</span>'
            f'<div class="md-chip-set" role="group" aria-labelledby="box-tone-label">{none}{tones}</div></div>',
            sections,
            '<p class="field-help" data-node-sections-help>One row a line. <code>||</code> stands '
            "cells side by side, <code>|</code> starts each line under a cell's title, "
            "<code>[tone]</code> first fills the cell.</p>",
            '<p class="field-help" data-node-sections-shape hidden>An ellipse or a hexagon carries '
            "no compartments; a rectangle or a note does.</p>",
        )
    )


def style_presets() -> str:
    """Each outline is a chip; its swatch is the only thing telling two apart."""
    return "".join(
        f'<button type="button" class="md-chip md-chip--leading style-preset" data-style-preset="{name}" disabled>'
        f'<span class="preset-swatch"></span>{label}</button>'
        for name, label in STYLE_PRESETS
    )


def panel() -> str:
    return f"""            <section class="inspector-section" data-inspector-panel="style" role="tabpanel" data-empty="true" hidden>
              <h2>Style</h2>
              {
        empty_state(
            "select",
            "Nothing selected",
            "Select a component, frame or connector on the canvas to change how it looks.",
        )
    }
              <p>Selected: <strong data-inspector-selection>Nothing</strong></p>
              <div class="selection-context">
                <span>Library <strong data-inspector-provider>—</strong></span>
                <span>Component <strong data-inspector-component>—</strong></span>
                <span>Layer <strong data-inspector-layer>—</strong></span>
              </div>
              <div class="inspector-subsection" data-node-display-section>
                <h3>Display</h3>
                {display_modes()}
              </div>
              <div class="inspector-subsection" data-frame-style-section hidden>
                <h3>Frame</h3>
                {frame_settings()}
              </div>
              <div class="inspector-subsection" data-node-box-section hidden>
                <h3>Box</h3>
                {box_settings()}
              </div>
              <div class="inspector-subsection">
                <h3>Outline</h3>
                <div class="md-chip-set" aria-label="Style presets">{style_presets()}</div>
              </div>
            </section>"""


__all__ = [
    "BOX_SHAPES",
    "DISPLAY_MODES",
    "FRAME_CONTENTS",
    "STYLE_PRESETS",
    "box_settings",
    "display_modes",
    "frame_settings",
    "panel",
    "style_presets",
]
