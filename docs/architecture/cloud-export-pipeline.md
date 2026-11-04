# Cloud project export pipeline

## Decision

Use the versioned `.infragram.json` cloud project as the editable template
and Infragram Azure's scene renderer as the single diagram authority. HTML wraps
that exact scene in a self-contained provider editor; SVG and PNG isolate the
same marked diagram node. Do not maintain separate diagram layouts per format.

```text
.infragram.json template
          │ validate provider, topology, links, output preset
          ▼
   provider-aware Scene
          │ one deterministic render
          ▼
 editor HTML + catalog sidebar + inline accessible SVG
          ├──────── runtime SVG export, cropped ► standalone .svg
          └──────── Chromium capture, cropped to content ► .png on paper
```

The browser editor reads and writes the same JSON contract. Canvas
coordinates may be stored later as optional authored layout data, but service
identity, containment, connections, provider, and presentation settings stay
portable and renderer-independent.

## Artifacts

| Artifact | Role | Generated from |
|---|---|---|
| `.infragram.json` | Reusable/editable template | Project model |
| `.html` | Self-contained editor: full provider palette, drag/drop nodes, terminal wiring, move/delete, undo/redo, zoom, recovery, and current-state downloads | Project + provider catalog + Scene + embedded graph state |
| `.svg` | Accessible vector diagram only, authored layout | The editor runtime's own SVG export, cropped like the PNG; static render as the no-browser fallback |
| `.png` | Pixel-stable diagram on the theme's paper | Chromium capture of the runtime's clean SVG export, cropped to the drawn content |
| `-icons.svg`, `-icons.png` | The same diagram with every component as a bare vendor icon and caption, written beside the cards by `--display both` | The same page opened with `?display=icon` |
| `.pdf` | Future print/page adapter | Canonical HTML print rendering |
| `.webp` | Future compact raster adapter | Verified PNG/browser raster path |

The SVG is the editor runtime's export of the rendered page, so frames, cards
and wires sit where the author left them; the static SVG embedded in the HTML
source only knows the automatic layout and is used solely when no browser is
available (the export result carries a note). Static extraction balances
nested `<svg>` elements because provider lockups can contain their own SVG
roots. Either way the standalone file keeps the title, description, ARIA
relationship, viewBox, symbols, and provider artwork, and adds the browser
font import inside the existing `<defs>` block.

PNG export waits for browser fonts, stages the runtime's clean SVG export by
itself, crops its viewBox to the drawn frames, cards, wires, and labels, the provider
mark in its band below them (`[data-brand-mark]`, `render-metrics.json` under
`mark`), plus a 48 px margin (`PNG_CONTENT_MARGIN`), and captures it over the
theme's paper.
It never screenshots the empty canvas, the sidebar, or editor
controls. A page without the runtime falls back to capturing
`svg[data-infragram-diagram]` at its viewBox.

## CLI

```powershell
$env:PYTHONPATH = "src"
python -m infragram export:project `
  skills/infragram-azure/assets/templates/cloud/azure-api.infragram.json `
  --formats template,html,svg,png `
  --output-dir dist/cloud
```

Existing files are protected by default. Add `--force` only when replacing a
known export. PNG accepts scales from 1 through 4; scale 3 is the default.

## Editor integration

The exported HTML loads the category registry and complete provider catalog
into the sidebar. It preserves the fixed 21-category order and supports search
and accessible accordions. A category that no embedded library populates is
left out; every other category stays in place with a `No components` state
when the current selection has none, so the navigation never shifts between
the Azure, Kubernetes and Databricks catalogs.

The editor chrome does not depend on the provider. It includes a two-row command header, the
collapsible provider sidebar and a collapsible inspector. The workspace opens
light, and a top-header toggle switches to dark, storing the choice in
browser-local storage. The chrome follows Material 3: `--md-sys-color-*` roles
generated from Azure blue `#0078D4` with the fidelity scheme for each theme,
and material-web's shape, type scale, elevation, state-layer, focus and motion
values. The canvas keeps its own palette (`--canvas-bg`, `--card-bg`,
`--text-canvas` and the other tokens the runtime reads to paint the drawing),
so restyling the chrome never moves a picture.

Every control is one of a small component set under
`src/infragram/editor/ui/components/`: button, icon button, segmented button, chip,
list and navigation item, tab, tile, text field, switch, checkbox, menu and
tooltip, at one desktop-dense size (controls 32 px, fields and dense rows 40 px,
tabs, search and navigation 48 px, two-line rows 56 px). The shell builds its
controls through the views in `editor/ui/views/` and the runtime builds its rows
with the same `md-*` classes. `tests/integration/test_chrome_components_browser.py`
walks an export through its panels in both themes and fails on any control that
is not a component or leaves the type, shape or height scale;
[editor-chrome.md](editor-chrome.md) maps every region and control to its
file. Provider themes
may supply the brand mark, original-color service SVGs, and diagram semantics;
they must not alter workspace layout, surface tokens, or shared interaction
colors.

Palette items are real drag sources. The canvas
reconstructs the project as editable SVG groups with visible terminals:

1. Drop a provider component to create a snapped node with embedded artwork.
2. Move any node; every incident edge recomputes from its terminal anchor.
3. Drag one terminal to another to create a square-cornered orthogonal connection.
4. Select nodes or edges for deletion; undo and redo retain graph state.
5. Zoom or fit without changing graph coordinates.
6. Download the current project, interactive HTML, or clean SVG. Browser-local
   recovery protects edits between reloads without transmitting data.

High-degree nodes grow when necessary so 10+ same-edge connections receive
distinct, fanned terminal positions.

PDF and WebP should be added only after HTML/SVG/PNG visual-parity tests are
stable. They are output adapters, not new renderers.
