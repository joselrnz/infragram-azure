# Editor chrome

The exported HTML page is an editor: a sidebar of components, a header and
toolbar, the canvas, and an inspector. Everything around the canvas is the
*chrome*. It is Material 3, laid out the way a React component library is --
primitives, views composed from them, a page composed from views -- and
bundled at render time into one self-contained file. Every control in it is
covered by a browser test. This page is the map.

## The tree

```
src/infragram/editor/
├── shell.py                 render_editor_html: prepares the data, composes the views
├── bundle.py                assembles ui/ stylesheets and runtime/ modules in order
├── state.py, sidebar.py,    the editor state, the library payload, category and
│   artwork.py               frame artwork (data, not markup)
├── ui/
│   ├── styles/              tokens.css  base.css  states.css  rails.css  responsive.css
│   ├── icons.py             the glyph set: icon(name)
│   ├── html.py              attributes(attrs)
│   ├── components/          primitives, a builder beside its stylesheet
│   │   ├── button.py        + button.css         md-button
│   │   ├── icon_button.py   + icon_button.css    md-icon-button
│   │   ├── segmented.py     + segmented.css      md-segmented
│   │   ├── field.py         + field.css          md-field, md-field__input, md-color-field
│   │   ├── empty_state.py   + empty_state.css    md-empty-state
│   │   └── chip.css  list.css  nav_item.css  tile.css  tabs.css  search.css
│   │       switch.css  checkbox.css  card.css  menu.css  tooltip.css  badge.css
│   │       setting_row.css
│   └── views/               the page's regions, composed from primitives
│       ├── sidebar.py       + sidebar.css        brand, search, libraries, categories
│       ├── header.py        + header.css         document bar, theme, Download, toolbar
│       ├── canvas.py        + canvas.css, overlays.css   drawing, selection toolbar,
│       │                                                 tooltip, popup, context menu
│       ├── inspector/       inspector.css; __init__ (tabs) and one module per panel:
│       │                    diagram.py  style.py  text.py  arrange.py  layers.py
│       ├── workspace.css, workbench.css                  the two page grids
│       └── page.py          the document every view is placed into
└── runtime/                 the browser side: 35 ordered modules sharing one closure
    00-bootstrap.js  01-sidebar-rail.js  …  16-render.js  …  30-frame-review.js  31-shortcut-sheet.js  …  34-api-and-start.js
```

| React idea | Here |
|---|---|
| A component, a function of props | `ui/components/button.py`: `button(label, *, variant, attrs, glyph)` returns markup |
| Co-located styles | `button.css` beside `button.py`; `bundle.STYLE_ORDER` is the cascade |
| A composite view | `ui/views/sidebar.py` builds the sidebar from `button`, `icon` and the list styles |
| The app root | `ui/views/page.py` places sidebar, header, canvas and inspector |
| Hooks and event handlers | `runtime/` modules, bound to the markup by `data-*` hooks |
| The bundler | `bundle.py`: stylesheets in cascade order, runtime modules in number order |

## The page

```
┌──────────────┬──────────────────────────────────────────────┬──────────────┐
│ Sidebar      │ Header: title · status · theme · Download    │              │
│  brand       │ Toolbar: undo redo delete │ zoom │ fit │ grid │              │
│  search      ├──────────────────────────────────────────────┤  Inspector   │
│  libraries   │ Canvas                                       │   Diagram    │
│  categories  │   selection toolbar · tooltip · popup        │   Style      │
│   cards      │   context menu · help                        │   Text       │
│   frames     │                                              │   Arrange    │
│              │                                              │   Layers     │
└──────────────┴──────────────────────────────────────────────┴──────────────┘
```

| Region | View | Runtime modules | Hooks |
|---|---|---|---|
| Brand, search, categories, library selector | `views/sidebar.py` | `01-sidebar-rail`, `18-sidebar-catalog` | `data-sidebar-logo-trigger`, `data-sidebar-search`, `data-category-id`, `data-provider-*` |
| Component cards, frame groups | markup built in `18-sidebar-catalog` | `17-editing`, `19-canvas-pointer` | `data-component-id`, `data-frame-group`, `data-frame-preset` |
| Header actions | `views/header.py` | `08-theme-and-layout`, `29-downloads` | `data-theme-menu`, `data-theme-choice`, `data-download-*` |
| Toolbar | `views/header.py` | `10-grid`, `20-zoom-and-pan` | `data-editor-action` |
| Drawing | `views/canvas.py` | `11-anchors` … `16-render`, `19-canvas-pointer` | `data-graph-node`, `data-graph-edge`, `data-graph-boundary` |
| Selection toolbar, context menu, tooltip, popup | `views/canvas.py` | `15-overlays`, `24-context-menu`, `28-tooltip` | `data-selection-action`, `data-context-action` |
| Shortcut sheet | `views/canvas.py` (`shortcuts`, `SHORTCUTS`) | `31-shortcut-sheet` | `data-shortcut-sheet`, `data-editor-action="shortcuts"` |
| Connectors: draw, select, reconnect, reverse, reset route | `views/canvas.py` (connector toolbar and menu items) | `16-render` (preview, end handles), `17-editing` (`reconnectEdge`), `19-canvas-pointer`, `22-connector-and-text-editing` (`reverseEdge`, `resetEdgeRoute`) | `data-node-port`, `data-connect-target`, `data-connection-preview`, `data-edge-end`, `data-selection-action="edge-*"` |
| Connector shape: bends, connection points | `views/inspector/text.py` (the two side selects) | `11-anchors` (`edgeControlPoints`, `nearestEdgeStretch`), `16-render` (handles), `19-canvas-pointer`, `22-connector-and-text-editing` (`setEdgePort`, `removeEdgeBend`) | `data-edge-bend`, `data-edge-bend-ghost`, `data-edge-port-control` |
| Clipboard: copy, cut, paste, duplicate | `views/canvas.py` (toolbar button, menu items) | `17-editing` (`selectionBundle`, `pasteBundle`), `24-context-menu`, `26-keyboard` | `data-selection-action="duplicate"`, `data-context-action="copy"`/`"paste"` |
| Frame call-outs: highlight, contents as icons or cards, component review | `views/canvas.py` (menu, review), `views/inspector/style.py` (Frame section) | `23-display-mode`, `30-frame-review` | `data-context-action="frame-*"`, `data-frame-review`, `data-frame-highlight-toggle`, `data-frame-display` |
| Inspector tabs and panels | `views/inspector/` | `06-inspector-sync`, `21-arrange`, `22-connector-and-text-editing`, `23-display-mode`, `25-panels` | `data-inspector-tab` and one hook per field |

A wire is shaped by its `waypoints`, which both renderers already drew: the
editor now makes them. Dragging any point on a wire adds one in the stretch it
was pulled from -- `nearestEdgeStretch` picks the stretch, so a bend joins the
route in the right order -- and each bend carries a handle, with a hollow one
in the middle of every stretch to pull the next from. A press alone adds
nothing, so a click still only selects and a double-click still opens the
label; the pointer is captured on the first movement, not on the press, or the
click would land on the canvas instead of the handle and no double-click would
ever arrive. On release, a bend back in line with its neighbours is dropped.
Each end's side is `sourcePort`/`targetPort`, offered as *Leaves from* and
*Arrives at*; a node has one connection point a side (ADR 0006), so those are
the choices, and a side set by hand counts as part of the route that *Reset
route* clears. It travels in `editor_edge_styles` beside the wire's style, so
the static renderer anchors the wire on that side too (`Link.source_side`).
Bends are canvas coordinates, so they mean something only where that canvas
stands: the static renderer draws them once it has placed the drawing on the
layout the editor saved (`Scene.saved_layout`, `builders/saved_geometry.py`),
and routes the wire itself when a document was never arranged by hand.

The clipboard is the page's own, not the system's: `selectionBundle` in
`17-editing` deep-copies what the selection implies -- the frames inside a
picked frame, the components those frames hold, and the connectors whose two
ends are both in the set -- and `pasteBundle` rebuilds it with fresh ids,
remapping each `boundaryId` and connector end to the copy when it came too and
leaving it pointing at the original when it did not. Copies are never locked,
step `PASTE_STEP` each paste, and land under the pointer when the paste came
from the context menu. Duplicate uses the same bundle without touching the
clipboard.

Dragging does not redraw the drawing. `dragMovedNodes` (`16-render`) writes the
dragged cards' transforms, the paths, ends and labels of the wires they carry,
and the guides, and returns false if the page is not in a state it can patch,
which sends the caller back to `renderGraph`. Routes for wires that touch
nothing being dragged are kept in the route cache across renders -- a redraw
that moves nothing keeps all of them -- and a carried wire takes the plain path
until it is dropped. What this buys is 33 ms a move where a full redraw of the
largest template costs 400 ms; what it costs is that a label may sit further
along its wire until the card lands.

Connectors are picked like everything else: `selectedEdgeIds` beside
`selectedNodeIds` and `selectedBoundaryIds`, with `selectEdge` the one way in
so a wire picked by a click, a marquee, the Tab order, the context menu or a
text edit is a wire that looks picked. Handles and the label button belong to
one wire and step aside when several are held. Wires that join the same two
components share both anchors, so each takes a lane of its own through the
middle (`parallelLane`, `router.lane`), which both renderers work out the same
way.

Connectors work the way an ETL canvas does. A card shows a handle on each
side on hover; dragging one draws a dashed line, and whichever card is under
the pointer is the target (`data-connect-target`): it lights up, the line
runs to it, and a release anywhere on it connects. The line tells the truth
about the drop -- it takes the handle under the pointer if there is one, and
otherwise the side `inferredSides` will give the finished wire -- so nothing
moves at the moment of release. A locked component is never a target. Escape
drops the line. A selected connector shows a handle on each end
(`data-edge-end`); dragging one onto another card reconnects that end, and
the old wire fades while it moves; dropped back on its own card it changes
nothing, so a hand-made route survives. The floating selection toolbar
switches to the connector's own actions, at the middle of the wire, above the
label so the label stays draggable.

Everything that must stay grabbable scales against the zoom: the wire's click
band is a 14 px `non-scaling-stroke`, the preview line likewise, and `10-grid`
sets `--port-scale`, which grows the handle dot up to 2.5× as the canvas zooms
out. The grab circle around it keeps its size, so the middle of a card and the
gaps between cards stay free for selecting and moving, and a selected card's
edge resize handles stand 12 px off it so they no longer cover the connector
handles. While a line is being drawn only that line and the lit card are
touched -- a whole re-render costs a third of a second on the largest template
-- and every way the line can end goes through `clearConnection` in
`00-bootstrap`, so no path leaves the canvas wearing the crosshair.

## The component set

Desktop-dense throughout. Every size and shape is a Material 3 token value,
and the compaction follows Angular Material's density scale (4 px per step).

| Component | Class | Builder | Height | Corners | Used for |
|---|---|---|---|---|---|
| Button | `md-button` + `--filled` / `--tonal` / `--outlined` / `--text` | `button` | 32 | full | labelled actions |
| Connected button group | `md-button-group` | `button` × n | 32 | full outside, 8 inside | the Order actions |
| Icon button | `md-icon-button` (`--sm` 40 px, `--toggle`) | `icon_button` | 32 / 40 | full | toolbar, panel and row actions |
| Segmented button | `md-segmented` | `segmented` | 32 | full | a choice of two |
| Chip | `md-chip` (`--leading`) | inline in views | 32 | 8 | library filters, outline presets |
| List item | `md-list-item` (`--dense` 40 px, `--static`) | runtime rows, menus | 56 / 40 | 12 | cards, layer and frame rows, menu items |
| Navigation item | `md-nav-item` | `views/sidebar.py` | 48 | full | categories, brand |
| Tile | `md-tile` | runtime | 96 | 12 | frame gallery, starter stacks |
| Tabs | `md-tabs`, `md-tab` | `views/inspector` | 48 | 3 px indicator | inspector panels |
| Text field | `md-field`, `md-field__input` | `field` + `text_input` / `select` | 40 | 4 | every input and drop-down |
| Colour field | `md-color-field` | `field` + `color_input` | 40 | 4, round swatch | text and line colour, with the hex read out |
| Empty state | `md-empty-state` | `empty_state` | — | 16 icon plate | Style, Text and Arrange with nothing selected |
| Search | `md-search` | `views/sidebar.py` | 48 | full | component search |
| Switch | `md-switch` | `views/inspector/diagram.py` | 32 | full | Show grid |
| Checkbox | `md-checkbox` | runtime, selector | 18 | 2 | library and layer visibility |
| Menu | `md-menu` | `views/header.py`, `views/canvas.py` | — | 16 | Download, canvas actions, libraries |
| Rich tooltip, badge, card | `md-tooltip-rich`, `md-badge`, `md-card` | views | — | 12 / full / 12 | canvas tooltip, selection count, panels |
| Snackbar | `md-snackbar` | `views/canvas.py`, shown by `setStatus` | 48 | 4 | what the last action did, for four seconds |

Type is Material 3's. The controls are set in Roboto, the typeface
material-web names for both `md-ref-typeface-brand` (titles) and
`md-ref-typeface-plain` (body and labels), and so is every label of the
drawing: card titles and details, frame labels, connector labels and the
legend, in both renderers. It ships in `assets/fonts` and is embedded in the
editor page and every SVG. Geist and Geist Mono remain for an author who
picks them in the Text panel; a monospaced connector label is tracked and
measured wider. Every rule that sets a role
(`font:var(--md-sys-typescale-body-medium)`) sets that role's tracking beside
it (`letter-spacing:var(--md-sys-typescale-body-medium-tracking)`), and no rule
sets a size, family or tracking by hand; `tests/unit/test_chrome_typescale.py`
holds every stylesheet to that.

Menus, the canvas tooltip and the popup enter with a 200 ms fade on the M3
emphasized-decelerate curve; menus also drop 4 px. Nothing scales, because a
scale changes the size a script measures while the element opens, and
`prefers-reduced-motion` turns every animation off.

Colour roles are the `--md-sys-color-*` tokens generated from Azure blue
`#0078D4` with the fidelity scheme, dark on `:root` and light on the light
`body`. The palette button offers a third theme, Darker: the same roles on
neutral near-black surfaces (page `#171717`, panels `#212121`, raised
`#2F2F2F`). It keeps `data-workspace-theme="dark"` so every dark rule and
canvas behaviour holds, and `data-workspace-palette="darker"` overrides the
values, the drawing's included, in a block of its own after the light one. The first token block in `ui/styles/tokens.css` is the canvas palette
the runtime paints the drawing with; the chrome never reads it, and it must
not change, or every golden picture moves.

## Adding or changing a control

1. **Use a primitive.** Build it with a builder from `ui/components`, or the
   primitive's classes when it has none; never a raw style.
2. **Place it in a view.** The region's module in `ui/views` composes it; a new
   region gets its own view module and, if it needs styles, a `.css` beside
   it listed in `bundle.STYLE_ORDER` where it belongs in the cascade.
3. **Give it a `data-*` hook** and wire its behaviour in the runtime module for
   that region, by the hook, never by class name. A new concern gets a new
   numbered module after the ones it uses.
4. **Test what it does** in `tests/integration/test_editor_controls_browser.py`:
   operate it and read the effect back from `window.infragramEditor.getState()`.
5. **Run the gates:** `tests/unit/test_editor_bundle.py` (every stylesheet has
   a place, every module is numbered and named),
   `tests/integration/test_chrome_components_browser.py` (every control is a
   component on the type, shape and height scale, both themes),
   `python -m infragram verify:browser`, and `verify:pictures` when anything
   near the canvas changed.

## Sources

The values come from Google's own implementations; the links pin the commit
that was read.

- Typeface and type scale: [material-web typescale](https://github.com/material-components/material-web/blob/56a486b147b8b7e95e6e8035fa02aed7e0009a85/tokens/versions/latest/sass/_md-sys-typescale.scss) and [ref typeface](https://github.com/material-components/material-web/blob/56a486b147b8b7e95e6e8035fa02aed7e0009a85/tokens/versions/latest/sass/_md-ref-typeface.scss)
- Shape, state, focus and component tokens: [material-web](https://github.com/material-components/material-web/tree/56a486b147b8b7e95e6e8035fa02aed7e0009a85/tokens/versions/latest/sass)
- Elevation shadows: [material-web elevation](https://github.com/material-components/material-web/blob/56a486b147b8b7e95e6e8035fa02aed7e0009a85/elevation/internal/_elevation.scss)
- Colour scheme: [material-color-utilities SchemeFidelity](https://github.com/material-foundation/material-color-utilities/blob/main/typescript/scheme/scheme_fidelity.ts)
- Density: [Angular Material theming guide](https://github.com/angular/components/blob/main/guides/theming.md)
