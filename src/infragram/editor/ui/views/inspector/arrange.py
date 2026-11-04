"""Arrange panel: exact geometry, order, alignment, transform, frames and locking.

Styles: inspector.css. Every control is a Material component (``md-*``); the
rows that vary are the tables below.
"""

from __future__ import annotations

from ...components import button, empty_state, field, icon_button, text_input

#: The four numbers that place and size one object: (field, label, limits).
#: Width and height carry a floor, because an object smaller than the snap
#: lattice cannot be picked up again once it is dropped.
GEOMETRY = (
    ("x", "X", 'step="1"'),
    ("y", "Y", 'step="1"'),
    ("width", "W", 'min="32" step="4"'),
    ("height", "H", 'min="32" step="4"'),
)

#: Stacking order, front to back: (action, label, what it does). Words
#: rather than glyphs -- the icon set has one mark for depth, and four
#: buttons wearing it would be four buttons a reader cannot tell apart.
ORDER = (
    ("to-front", "To front", "Bring to front"),
    ("forward", "Forward", "Bring forward"),
    ("backward", "Backward", "Send backward"),
    ("to-back", "To back", "Send to back"),
)

#: Align and distribute; each action is also the name of its glyph.
ALIGNMENT = (
    ("align-left", "Align left"),
    ("align-center", "Align horizontal centers"),
    ("align-right", "Align right"),
    ("align-top", "Align top"),
    ("align-middle", "Align vertical middles"),
    ("align-bottom", "Align bottom"),
    ("distribute-horizontal", "Distribute horizontally"),
    ("distribute-vertical", "Distribute vertically"),
)

#: Turning an object: (action, glyph, label).
TRANSFORM = (
    ("rotate-90", "rotate", "Rotate 90°"),
    ("flip-horizontal", "flip-horizontal", "Flip horizontal"),
    ("flip-vertical", "flip-vertical", "Flip vertical"),
)

#: What an object belongs to, and whether it may move.
CONTAINMENT = (
    ("group", "Group"),
    ("ungroup", "Ungroup"),
    ("detach", "Detach"),
    ("shrink-fit", "Shrink to fit"),
    ("lock", "Lock"),
)


def align(glyph: str, label: str) -> str:
    return icon_button(glyph, label, attrs=f'data-arrange-action="{glyph}" disabled')


def geometry() -> str:
    return "\n                ".join(
        field(
            label,
            text_input(f'type="number" {limits} data-exact-field="{name}" disabled'),
            prefix=True,
        )
        for name, label, limits in GEOMETRY
    )


def panel() -> str:
    order = "".join(
        button(label, variant="tonal", attrs=f'data-arrange-action="{action}" title="{title}"')
        for action, label, title in ORDER
    )
    alignment = "".join(align(glyph, label) for glyph, label in ALIGNMENT)
    transform = "".join(
        icon_button(glyph, label, attrs=f'data-arrange-action="{action}"')
        for action, glyph, label in TRANSFORM
    )
    containment = "".join(
        button(label, attrs=f'data-arrange-action="{action}"') for action, label in CONTAINMENT
    )
    return f"""            <section class="inspector-section" data-inspector-panel="arrange" role="tabpanel" data-empty="true" hidden>
              <h2>Arrange</h2>
              {
        empty_state(
            "select",
            "Nothing selected",
            "Select components or frames to position, align and lock them. Shift‑click adds to the selection.",
        )
    }
              <p><span data-arrange-selection-kind>Nothing selected</span>. Shift-click to select more; hold Alt while dragging to skip snapping.</p>
              <div class="md-field-grid" aria-label="Exact geometry">
                {geometry()}
              </div>
              <div class="inspector-subsection">
                <h3>Order</h3>
                <div class="md-button-group" role="group" aria-label="Order">
                  {order}
                </div>
              </div>
              <div class="inspector-subsection">
                <h3>Align and distribute</h3>
                <div class="md-icon-row" aria-label="Align and distribute the selection">
                  {alignment}
                </div>
              </div>
              <div class="inspector-subsection">
                <h3>Transform</h3>
                <div class="md-icon-row">
                  {transform}
                </div>
              </div>
              <div class="inspector-subsection">
                <h3>Frames and locking</h3>
                <div class="md-button-row">
                  {containment}
                </div>
              </div>
            </section>"""


__all__ = [
    "ALIGNMENT",
    "CONTAINMENT",
    "GEOMETRY",
    "ORDER",
    "TRANSFORM",
    "align",
    "geometry",
    "panel",
]
