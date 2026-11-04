"""Inspector view: six tabs, one module per panel. Styles: inspector.css."""

from __future__ import annotations

from .....builders.scene import Scene
from ...components import icon_button
from . import arrange, cost, diagram, layers, style, text
from .diagram import template_brief

#: The six panels, in the order their tabs are shown. The first is the one
#: the page opens on, and the panels render in this order too, so a tab and
#: the section it reveals cannot end up in different places.
PANELS = (
    ("diagram", "Diagram"),
    ("style", "Style"),
    ("text", "Text"),
    ("arrange", "Arrange"),
    ("layers", "Layers"),
    ("cost", "Cost"),
)


def tab(panel: str, label: str, selected: bool = False) -> str:
    return (
        f'<button type="button" class="md-tab inspector-tab" role="tab" '
        f'data-inspector-tab="{panel}" aria-selected="{"true" if selected else "false"}">'
        f"<span>{label}</span></button>"
    )


def tabs() -> str:
    return "".join(tab(panel, label, index == 0) for index, (panel, label) in enumerate(PANELS))


def inspector(scene: Scene, brief_markup: str, arrow_options: str, corner_options: str) -> str:
    """The right-hand panel: the tab row and the six panels under it."""
    return f"""        <aside class="right-inspector" data-right-inspector data-collapsed="false" aria-label="Diagram inspector">
          <header class="inspector-header">
            <div class="md-tabs inspector-tabs" role="tablist" aria-label="Inspector panels">
              {tabs()}
            </div>
            {icon_button("chevron-right", "Collapse inspector", size="sm", classes="inspector-toggle", attrs='data-inspector-toggle aria-expanded="true"')}
          </header>
          <div class="inspector-body">
{diagram.panel(scene, brief_markup)}
{style.panel()}
{text.panel(arrow_options, corner_options)}
{arrange.panel()}
{layers.panel()}
{cost.panel()}
          </div>
        </aside>"""


__all__ = ["PANELS", "inspector", "tab", "tabs", "template_brief"]
