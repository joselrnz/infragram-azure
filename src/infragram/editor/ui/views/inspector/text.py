"""Text panel: component text, connector style and sides, and the type a label is set in.

Styles: inspector.css. Every control is a Material component (``md-*``); the
rows that vary are the tables below.
"""

from __future__ import annotations

from ...components import button, color_input, empty_state, field, select, text_input

#: The two fields on a component itself.
CONTENT = (("name", "Name"), ("detail", "Description"))

LINE_KINDS = (("solid", "Solid"), ("dashed", "Dashed"), ("dotted", "Dotted"))
DIRECTIONS = (("forward", "One way"), ("both", "Both ways"), ("none", "None"))

#: Where a connector leaves its source and arrives at its target. A node has
#: one connection point a side; "auto" lets the router choose.
SIDES = (
    ("auto", "Automatic"),
    ("top", "Top"),
    ("right", "Right"),
    ("bottom", "Bottom"),
    ("left", "Left"),
)
ENDS = (("sourcePort", "Leaves from"), ("targetPort", "Arrives at"))

#: The two ends of a connector's label offset, as the document stores them.
OFFSETS = (("dx", "ΔX"), ("dy", "ΔY"))

#: Inter is the face every label is set in; Geist Mono stays on offer for an
#: author who wants a monospaced label.
FONTS = (("Inter", "Inter"), ("Geist Mono", "Geist Mono"))
WEIGHTS = (("400", "Regular"), ("500", "Medium"), ("600", "Bold"))
ALIGNMENTS = (("left", "Left"), ("center", "Center"), ("right", "Right"))


def options(pairs: tuple[tuple[str, str], ...]) -> str:
    return "".join(f'<option value="{value}">{label}</option>' for value, label in pairs)


def content_fields() -> str:
    """A name is one line; a description may run to several, each a line of
    the card's detail, so it is a textarea that grows with them (Enter still
    applies it, Shift+Enter starts a line, Return does on a touch keyboard:
    22-connector-and-text-editing.js)."""
    name, description = CONTENT
    return "\n                ".join(
        (
            field(
                name[1],
                text_input(
                    f'type="text" data-content-control="{name[0]}" autocomplete="off" disabled'
                ),
            ),
            field(
                description[1],
                f'<textarea class="md-field__input md-field__input--lines" data-content-control="{description[0]}" '
                'rows="1" spellcheck="false" autocomplete="off" disabled></textarea>',
            ),
            '<p class="field-help">Shift+Enter (Return on a touch keyboard) starts another line. '
            "More than one line draws the card as a box.</p>",
        )
    )


def connector_fields(arrow_options: str, corner_options: str) -> str:
    """How one wire is drawn. The arrowheads and the corner styles come from
    the same specs the static renderer reads, so the two agree."""
    return "\n                  ".join(
        (
            field("Line", select('data-edge-style-control="kind" disabled', options(LINE_KINDS))),
            field(
                "Arrows",
                select('data-edge-style-control="direction" disabled', options(DIRECTIONS)),
            ),
            field("Arrowhead", select('data-edge-style-control="arrow" disabled', arrow_options)),
            field("Corners", select('data-edge-style-control="corners" disabled', corner_options)),
            field("Line color", color_input('data-edge-style-control="stroke" disabled')),
            field(
                "Line width",
                text_input(
                    'type="number" min="0.5" max="6" step="0.1" data-edge-style-control="width" disabled'
                ),
            ),
        )
    )


def connection_points() -> str:
    """The side each end of the selected wire is pinned to."""
    return "\n                  ".join(
        field(label, select(f'data-edge-port-control="{end}" disabled', options(SIDES)))
        for end, label in ENDS
    )


def label_offsets() -> str:
    return "\n                  ".join(
        field(
            label,
            text_input(f'type="number" step="1" data-edge-label-field="{axis}" disabled'),
            prefix=True,
        )
        for axis, label in OFFSETS
    )


def type_fields() -> str:
    return "\n                  ".join(
        (
            field("Font", select('data-text-control="fontFamily"', options(FONTS))),
            field(
                "Size",
                text_input(
                    'type="number" min="8" max="40" step="1" data-text-control="fontSize" value="12"'
                ),
            ),
            field("Weight", select('data-text-control="fontWeight"', options(WEIGHTS))),
            field("Align", select('data-text-control="textAlign"', options(ALIGNMENTS))),
            field("Text color", color_input('data-text-control="textColor" value="#0F1B2A"')),
            field(
                "Opacity",
                text_input(
                    'type="number" min="10" max="100" step="5" data-text-control="opacity" value="100"'
                ),
            ),
        )
    )


def panel(arrow_options: str, corner_options: str) -> str:
    return f"""            <section class="inspector-section" data-inspector-panel="text" role="tabpanel" data-empty="true" hidden>
              <h2>Text</h2>
              {
        empty_state(
            "text",
            "Nothing selected",
            "Double-click a component or connector on the canvas to edit its text.",
        )
    }
              <p>Edit the selected item's text here, or double-click it on the canvas to type in place.</p>
              <div class="inspector-subsection" data-content-section>
                {content_fields()}
              </div>
              <div class="inspector-subsection" data-edge-label-section hidden>
                <h3>Connector</h3>
                {
        field(
            "Label",
            text_input('type="text" data-edge-label-control="label" autocomplete="off" disabled'),
        )
    }
                <div class="md-field-grid" aria-label="Connector line">
                  {connector_fields(arrow_options, corner_options)}
                </div>
                <div class="md-field-grid" aria-label="Connector connection points">
                  {connection_points()}
                </div>
                <div class="md-field-grid" aria-label="Connector label offset">
                  {label_offsets()}
                </div>
                <div class="md-button-row">
                  {button("Reset label style", variant="text", attrs="data-edge-text-reset")}
                  {
        button(
            "Automatic placement",
            variant="text",
            attrs='data-edge-label-reset title="Return the label to automatic placement" disabled',
        )
    }
                </div>
              </div>
              <div class="inspector-subsection" data-text-type-section>
                <h3>Type</h3>
                <div class="md-field-grid">
                  {type_fields()}
                </div>
              </div>
              <p class="field-help" data-text-type-note hidden>A box sets its own type, as every export draws it, so there is no font to choose.</p>
            </section>"""


__all__ = [
    "ALIGNMENTS",
    "CONTENT",
    "DIRECTIONS",
    "ENDS",
    "FONTS",
    "LINE_KINDS",
    "OFFSETS",
    "SIDES",
    "WEIGHTS",
    "connection_points",
    "connector_fields",
    "content_fields",
    "label_offsets",
    "options",
    "panel",
    "type_fields",
]
