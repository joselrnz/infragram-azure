"""Bottom drawer: the example shelf and the 3D builder.

Styles: drawer.css.

This region exists only in this edition, so its Material 3 dress is written
here rather than ported: md-tabs across the top, cards on the shelf, fields
in the builder.
"""

from __future__ import annotations

from html import escape

from ..components import button, field, select, text_input
from ..icons import icon

#: The drawer's panels, in tab order. The first is the one it opens on.
PANELS = (
    ("examples", "Examples"),
    ("builder", "3D builder"),
    ("resources", "Resources"),
)

#: The 3D item being built, as (label, control). The recipe and its knobs sit
#: in the first column; these are the second.
ITEM_FIELDS = (
    ("Family", select("data-iso-family", "")),
    (
        "Colour",
        text_input(
            'type="text" data-iso-colour placeholder="family colour, or #rrggbb" maxlength="7"'
        ),
    ),
    ("Glyph", select("data-iso-glyph", "")),
    ("Item name", text_input('type="text" data-iso-name placeholder="the caption"')),
    ("Item detail", text_input('type="text" data-iso-detail placeholder="the line beneath"')),
)


#: The Resources table's columns, as (key, sort key, heading). Name is always
#: shown; the rest are ticked on or off in the Display menu (33-costs.js).
COLUMNS = (
    ("name", "name", "Name"),
    ("type", "type", "Type"),
    ("group", "group", "Group"),
    ("location", "location", "Location"),
    ("links", "links", "Attached"),
    ("monthly", "monthly", "A month"),
    ("unused", "unused", "Unused"),
    ("findings", "findings", "Findings"),
    ("changed", "changed", "Changed"),
    ("tags", "tags", "Tags"),
)

#: How the rows can be grouped, as (value, label); the empty value is none.
GROUP_BY = (
    ("", "No grouping"),
    ("group", "Resource group"),
    ("type", "Type"),
    ("tied", "What it is tied to"),
    ("status", "Status"),
)


def columns() -> str:
    money = ' class="resource-money"'
    return "\n                  ".join(
        f'<th scope="col" data-col="{key}"{money if key == "monthly" else ""}>'
        f'<button type="button" data-resource-sort="{sort}">{label}</button></th>'
        for key, sort, label in COLUMNS
    )


def foot() -> str:
    """The totals row under the table: a cell per column, the month's total
    filled in by the runtime (33-costs.js)."""
    cells = {"name": "Total", "monthly": ""}
    attrs = {"monthly": ' class="resource-money" data-foot-total'}
    return "\n                  ".join(
        f'<td data-col="{key}"{attrs.get(key, "")}>{cells.get(key, "")}</td>'
        for key, _, _ in COLUMNS
    )


def group_options() -> str:
    return "".join(f'<option value="{value}">{label}</option>' for value, label in GROUP_BY)


def tabs() -> str:
    return "".join(
        f'<button type="button" class="md-tab bottom-tab" role="tab" data-bottom-tab="{panel}" '
        f'aria-selected="{"true" if index == 0 else "false"}"><span>{label}</span></button>'
        for index, (panel, label) in enumerate(PANELS)
    )


def item_fields() -> str:
    return "\n                ".join(field(label, control) for label, control in ITEM_FIELDS)


def drawer(title: str) -> str:
    """The library drawer, collapsed to its tab row until it is opened."""
    return f"""      <section class="bottom-drawer" data-bottom-drawer data-expanded="false" aria-label="Diagram library">
        <div class="dock-divider dock-divider--bottom" data-dock-divider="bottom" role="separator" aria-orientation="horizontal" aria-label="Resize the inventory" tabindex="0" hidden></div>
        <header class="bottom-drawer-header">
          <div class="md-tabs bottom-tabs" role="tablist" aria-label="Diagram library panels">
            {tabs()}
          </div>
          <button type="button" class="md-icon-button md-icon-button--sm bottom-toggle" data-bottom-toggle aria-expanded="false" title="Expand diagram library" aria-label="Expand diagram library">{icon("expand")}</button>
        </header>
        <div class="bottom-drawer-body">
          <section data-bottom-panel="examples" role="tabpanel">
            <article class="md-card md-card--outlined example-card">
              <strong>{escape(title)}</strong><small>The diagram open now</small>
            </article>
          </section>
          <section data-bottom-panel="builder" role="tabpanel" hidden>
            <div class="md-empty-state iso-builder-note" data-iso-unavailable hidden>
              <strong class="md-empty-state__headline">No 3D renderer in this page</strong>
              <span class="md-empty-state__supporting">To build 3D items here, export the project with every library embedded, or with the on-premises library installed and its libraries embedded.</span>
            </div>
            <form class="iso-builder" data-iso-builder autocomplete="off">
              <div class="iso-builder-column">
                {field("Recipe", select("data-iso-recipe", ""))}
                <div class="iso-builder-knobs" data-iso-knobs></div>
              </div>
              <div class="iso-builder-column">
                {item_fields()}
              </div>
              <div class="iso-builder-column iso-builder-actions">
                <img class="iso-builder-preview" data-iso-preview-image alt="" hidden>
                {button("Render preview", variant="tonal", attrs="data-iso-preview")}
                {button("Add to diagram", attrs="data-iso-add disabled")}
                <p class="iso-builder-status" data-iso-status>Pick a recipe and turn its knobs; the item renders here, in the page.</p>
              </div>
            </form>
          </section>
          <section class="resource-panel" data-bottom-panel="resources" role="tabpanel" hidden>
            <div class="resource-bar">
              <div class="resource-views" role="tablist" aria-label="Inventory view">
                <button type="button" class="md-tab" role="tab" data-resource-view="resources" aria-selected="true"><span>Resources</span></button>
                <button type="button" class="md-tab" role="tab" data-resource-view="savings" aria-selected="false"><span>Savings<b class="resource-views-total" data-savings-tab-total hidden></b></span></button>
                <button type="button" class="md-tab" role="tab" data-resource-view="changes" aria-selected="false" hidden><span>Changes</span></button>
              </div>
              <div class="resource-toolbar">
                <label class="resource-search"><span class="sr-only">Search resources</span>
                  <input type="search" data-resource-search placeholder="Search name, type, group, tag" autocomplete="off" aria-keyshortcuts="/">
                  <button type="button" class="md-icon-button resource-search-clear" data-resource-search-clear aria-label="Clear the search" title="Clear the search" hidden>{icon("close")}</button></label>
                <div class="resource-filters-menu" data-resource-filters-menu>
                  <button type="button" class="md-button md-button--outlined resource-filters-toggle" data-resource-filters-toggle aria-haspopup="dialog" aria-expanded="false">Filters<span class="resource-filters-count" data-resource-filters-count hidden></span></button>
                  <div class="md-menu resource-filters-panel" data-resource-filters-panel role="dialog" aria-label="Filters" hidden>
                    <div class="resource-filter-section">
                      <span class="md-menu__header">Show only</span>
                      <div class="filter-choices resource-filters" role="group" aria-label="Show only">
                        <button type="button" class="md-list-item filter-choice" data-resource-only="unused" aria-pressed="false"><span class="filter-check" aria-hidden="true"></span><span class="md-list-item__label">Unused</span><span class="filter-count" data-only-count="unused"></span></button>
                        <button type="button" class="md-list-item filter-choice" data-resource-only="untagged" aria-pressed="false"><span class="filter-check" aria-hidden="true"></span><span class="md-list-item__label">Untagged</span><span class="filter-count" data-only-count="untagged"></span></button>
                        <button type="button" class="md-list-item filter-choice" data-resource-only="priced" aria-pressed="false"><span class="filter-check" aria-hidden="true"></span><span class="md-list-item__label">Priced</span><span class="filter-count" data-only-count="priced"></span></button>
                        <button type="button" class="md-list-item filter-choice" data-resource-only="findings" aria-pressed="false" hidden><span class="filter-check" aria-hidden="true"></span><span class="md-list-item__label">With findings</span><span class="filter-count" data-only-count="findings"></span></button>
                        <button type="button" class="md-list-item filter-choice" data-resource-only="changed" aria-pressed="false" hidden><span class="filter-check" aria-hidden="true"></span><span class="md-list-item__label">Changed in 7 days</span><span class="filter-count" data-only-count="changed"></span></button>
                      </div>
                    </div>
                    <div class="resource-filter-section">
                      <span class="md-menu__header">Type</span>
                      <label hidden><span>Type</span><select data-resource-type><option value="">Type</option></select></label>
                      <div class="filter-choices" data-filter-choices role="group" aria-label="Type"></div>
                    </div>
                    <div class="resource-filter-section">
                      <span class="md-menu__header">Resource group</span>
                      <label hidden><span>Resource group</span><select data-resource-group><option value="">Group</option></select></label>
                      <div class="filter-choices" data-filter-choices role="group" aria-label="Resource group"></div>
                    </div>
                    <button type="button" class="md-button md-button--text resource-filters-clear" data-resource-filters-clear>Clear filters</button>
                  </div>
                </div>
                <div class="resource-filters-menu" data-resource-display-menu>
                  <button type="button" class="md-button md-button--outlined resource-filters-toggle" data-resource-display-toggle aria-haspopup="dialog" aria-expanded="false">Display</button>
                  <div class="md-menu resource-filters-panel" data-resource-display-panel role="dialog" aria-label="Display" hidden>
                    <div class="resource-filter-section">
                      <span class="md-menu__header">Group rows by</span>
                      <label hidden><span>Group rows by</span><select data-resource-groupby>{group_options()}</select></label>
                      <div class="filter-choices" data-groupby-choices role="group" aria-label="Group rows by"></div>
                    </div>
                    <div class="resource-filter-section">
                      <span class="md-menu__header">Sort by</span>
                      <div class="filter-choices" data-sort-choices role="group" aria-label="Sort by"></div>
                    </div>
                    <div class="resource-filter-section">
                      <span class="md-menu__header">Columns</span>
                      <div class="filter-choices" data-column-choices role="group" aria-label="Columns"></div>
                    </div>
                    <button type="button" class="md-button md-button--text resource-filters-clear" data-columns-reset>Default columns</button>
                  </div>
                </div>
                <p class="resource-summary" data-resource-summary></p>
                <button type="button" class="md-icon-button" data-resource-csv title="Download CSV" aria-label="Download CSV">{icon("download")}</button>
              </div>
              <div class="resource-dock-controls">
                <div class="md-segmented" role="group" aria-label="Inventory layout">
                  <button type="button" class="resource-dock-side" data-dock-side="right" aria-pressed="false" title="Beside the map" aria-label="Beside the map">{icon("dock-right")}</button>
                  <button type="button" data-dock-side="bottom" aria-pressed="false" title="Under the map" aria-label="Under the map">{icon("dock-bottom")}</button>
                  <button type="button" data-dock-mode="table" aria-pressed="false" title="The table only" aria-label="The table only">{icon("table")}</button>
                </div>
                <button type="button" class="md-icon-button" data-dock-close aria-label="Close the inventory" title="Close the inventory">{icon("close")}</button>
              </div>
            </div>
            <div class="resource-table-wrap" tabindex="0" aria-label="Resources: arrow keys move through the rows, Enter opens details" data-resource-wrap>
              <table class="resource-table" data-resource-table>
                <thead><tr>
                  {columns()}
                </tr></thead>
                <tbody data-resource-rows></tbody>
                <tfoot data-resource-foot><tr>
                  {foot()}
                </tr></tfoot>
              </table>
              <div class="resource-empty" data-resource-empty hidden><strong>Nothing matches</strong><span>No resource fits the search and filters.</span><button type="button" class="md-button md-button--outlined" data-resource-clear>Clear search and filters</button></div>
            </div>
            <div class="resource-selected" data-resource-selected hidden></div>
            <div class="resource-savings" data-resource-savings hidden></div>
            <div class="resource-savings resource-changes" data-resource-changes hidden></div>
          </section>
        </div>
      </section>"""


__all__ = [
    "COLUMNS",
    "GROUP_BY",
    "ITEM_FIELDS",
    "PANELS",
    "columns",
    "drawer",
    "foot",
    "group_options",
    "item_fields",
    "tabs",
]
