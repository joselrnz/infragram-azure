"""Header view: the document bar (title, theme, downloads) and the toolbar.

Styles: header.css.

Every control here is one of the ``md-*`` components. The hooks are this
edition's own -- ``data-theme-choice``, ``data-download-*``,
``data-editor-action`` -- so the runtime that drove the old chrome drives
this one unchanged.
"""

from __future__ import annotations

from html import escape

from ..branding import mascot_uri
from ..components import icon_button, segmented
from ..icons import icon

#: The Terraform items of the download menu, one a style the page carries,
#: in the order they are offered: style, label, and what the folder holds.
TERRAFORM_ITEMS = (
    ("resources", "Terraform", "The diagram's Terraform skeleton, as plain resources"),
    (
        "modules",
        "Terraform, registry modules",
        "The diagram's Terraform skeleton, calling the public registry's modules where one fits",
    ),
)

#: The workspace palettes, in the order they are offered. Darker is the dark
#: theme on neutral near-black surfaces rather than blue-tinted ones.
THEMES = (("light", "Light"), ("dark", "Dark"), ("darker", "Darker"))


def theme_menu() -> str:
    """The palette: a menu of the workspace themes, the page's own checked.

    A toggle can only name the other one. Three themes need a list, so each
    row carries a swatch of the surface and accent it would bring.
    """

    items = "".join(
        f'<button type="button" class="md-list-item theme-choice" role="menuitemradio" data-theme-choice="{value}" '
        f'aria-checked="{str(value == "light").lower()}">'
        f'<span class="theme-swatch theme-swatch--{value}" aria-hidden="true"></span>'
        f'<span class="md-list-item__text"><span class="md-list-item__headline">{label}</span></span></button>'
        for value, label in THEMES
    )
    return f"""<details class="md-menu-anchor theme-menu" data-theme-menu>
              <summary class="md-icon-button md-icon-button--sm" data-theme-toggle aria-label="Theme: Light" title="Theme: Light">{icon("palette")}</summary>
              <div class="md-menu" role="menu" aria-label="Theme">
                <span class="md-menu__header">Theme</span>
                {items}
              </div>
            </details>"""


def download_menu(terraform: tuple[str, ...] = ()) -> str:
    """Download is one tonal menu button, not three loose ones in the header.

    ``terraform`` names the Terraform styles the page carries
    (editor/terraform_payload.py, for a diagram the Terraform export writes
    for): each is an item below a divider, with Terraform's mark, that
    downloads its folder as a .zip. A page that carries none offers none.
    """

    def item(attrs: str, label: str, detail: str, leading: str, description: str) -> str:
        return (
            f'<button type="button" class="md-list-item download-format" data-download-action {attrs}>'
            f'<span class="md-list-item__leading">{leading}</span>'
            f'<span class="md-list-item__text"><span class="md-list-item__headline">{label}</span>'
            f'<span class="md-list-item__supporting">{description}</span></span>'
            f'<span class="md-list-item__trailing">{detail}</span></button>'
        )

    terraform_items = "".join(
        item(
            f'data-download-terraform="{style}" title="{escape(what, quote=True)}"',
            escape(label),
            ".zip",
            icon("terraform"),
            "Infrastructure code",
        )
        for style, label, what in TERRAFORM_ITEMS
        if style in terraform
    )
    if terraform_items:
        terraform_items = (
            '<div role="group" aria-label="Infrastructure" data-download-infrastructure>'
            '<span class="md-menu__header">Infrastructure</span>' + terraform_items + "</div>"
        )
    resolution = segmented(
        "download-png-quality",
        tuple(
            (
                f"{scale}×",
                f'data-png-scale-choice="{scale}" aria-label="{scale}× {label}"',
                label,
                scale == 2,
            )
            for scale, label in ((1, "Standard"), (2, "Sharp"), (3, "High"), (4, "Maximum"))
        ),
    )
    return f"""<details class="md-menu-anchor download-menu" data-download-menu>
              <summary class="md-button md-button--outlined" aria-label="Download" aria-haspopup="dialog">{icon("download")}<span class="download-menu__label">Download</span>{icon("expand", extra_class="md-expand-icon")}</summary>
              <div class="md-menu download-panel" role="dialog" aria-label="Download diagram">
                <div class="download-panel__heading"><strong>Export diagram</strong><span>Fitted to your drawing</span></div>
                <div class="download-options">
                  <div class="download-resolution"><div class="download-resolution__label"><span id="download-png-quality">PNG quality</span><span data-png-quality-label>Sharp</span></div>{resolution}</div>
                  <label class="download-legend"><input type="checkbox" class="md-checkbox" data-legend-setting="exportLegend" aria-label="Include legend in PNG, SVG &amp; draw.io"><span>Include legend<small>PNG, SVG &amp; draw.io</small></span></label>
                </div>
                {item("data-download-png", "Image", ".png", icon("image"), "Ready to share")}
                {item("data-download-svg", "Diagram", ".svg", icon("vector"), "Scalable vector")}
                {item("data-download-drawio", "Editable diagram", ".drawio", icon("diagram"), "Continue in draw.io")}
                <div class="md-divider" role="separator"></div>
                {item("data-download-template", "Template", ".infragram.json", icon("file-code"), "Reuse this project")}
                {item("data-download-html", "Editor page", ".html", icon("browser"), "Open and edit offline")}
                {terraform_items}
              </div>
            </details>"""


def toolbar() -> str:
    """The diagram controls: edit, zoom, grid."""
    return f"""        <div class="editor-toolbar" role="toolbar" aria-label="Diagram controls">
          <div class="toolbar-group" role="group" aria-label="Edit graph">
            {icon_button("library", "Components", attrs='data-editor-action="library" title="Components: tap one to add it"')}
            {icon_button("help", "Keyboard shortcuts", attrs='data-editor-action="shortcuts" title="Keyboard shortcuts (?)"')}
            {icon_button("undo", "Undo", attrs='data-editor-action="undo"')}
            {icon_button("redo", "Redo", attrs='data-editor-action="redo"')}
            {icon_button("delete", "Delete selection", attrs='data-editor-action="delete"')}
          </div>
          <div class="toolbar-group" role="group" aria-label="Zoom canvas">
            {icon_button("zoom-out", "Zoom out", attrs='data-editor-action="zoom-out"')}
            <button type="button" class="md-button md-button--text zoom-value" data-editor-action="zoom-reset" data-zoom-value title="Reset zoom to 100%" aria-label="Reset zoom to 100%">100%</button>
            {icon_button("zoom-in", "Zoom in", attrs='data-editor-action="zoom-in"')}
            {icon_button("fit", "Fit diagram to window", attrs='data-editor-action="zoom-fit"')}
          </div>
          <div class="toolbar-group" role="group" aria-label="Layout">
            {icon_button("tidy", "Tidy layout", attrs='data-editor-action="tidy-layout" title="Tidy layout: put every component, frame and pinned wire back where the layout placed it"')}
          </div>
          {icon_button("grid", "Grid", toggle=True, attrs='data-editor-action="toggle-grid" aria-pressed="false"')}
        </div>"""


def header(
    title: str,
    architecture_label: str,
    component_count: int,
    *,
    terraform: tuple[str, ...] = (),
) -> str:
    """The document bar and the diagram toolbar.

    Notes belong in companion documentation, outside the drawing. ``terraform`` is what
    :func:`download_menu` offers of the diagram's Terraform.
    """
    return f"""      <header class="editor-header" data-editor-header>
        <div class="document-bar">
          <div class="document-copy">
            <strong data-document-title title="{escape(title, quote=True)}">{escape(title)}</strong>
            <small>{escape(architecture_label)} architecture</small>
          </div>
          <div class="document-actions">
            <span class="sr-only" data-search-status aria-live="polite">{component_count} components</span>
            <span class="local-state" data-local-state aria-live="polite"></span>
            {download_menu(terraform)}
            {theme_menu()}
            <img class="app-mascot" src="{mascot_uri(64)}" width="40" height="40" alt="Infragram Azure pangolin mascot" title="Infragram Azure">
          </div>
          <div class="document-views" role="group" aria-label="View">
            <button type="button" class="md-button md-button--outlined view-toggle" data-comments-toggle aria-pressed="false" aria-haspopup="dialog" title="Comments on this diagram: read them, add yours, download them">{icon("comment")}<span class="document-action-label">Comments</span><span class="comments-count" data-comments-count></span></button>
            <button type="button" class="md-button md-button--outlined view-toggle" data-inventory-toggle aria-pressed="false" title="The inventory: every resource as a table, beside or under the map">{icon("table")}<span class="document-action-label">Inventory</span></button>
            <button type="button" class="md-button md-button--outlined view-toggle" data-edit-mode aria-pressed="true" title="Editing tools: the component library and the inspector">{icon("edit")}<span class="document-action-label">Edit</span></button>
          </div>
        </div>
{toolbar()}
      </header>"""


__all__ = ["TERRAFORM_ITEMS", "download_menu", "header", "theme_menu", "toolbar"]
