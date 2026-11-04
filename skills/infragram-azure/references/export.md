# Export a project to HTML, SVG, PNG, its document and Terraform

Load this file before exporting: when the user invokes
`/infragram-azure:export-project <file>`, asks in natural language to
export, render, save, rasterize, or download a project as HTML, SVG, or PNG
("export this template", "give me a PNG of the VPN diagram", "render the
multicloud project"), or asks for a diagram, which is written out the same
way. An export replaces no existing file the user has not asked to replace. For Terraform, the `terraform` format below writes the
diagram's modular skeleton; [terraform.md](terraform.md) says what it holds.

## Command

```text
python "<skill>/scripts/infragram.py" export:project <project.infragram.json> [options]
```

`<skill>` is this skill's folder (inside Claude Code, `${CLAUDE_SKILL_DIR}`).
The document and the output directory resolve against the directory you are
in, so a diagram for another project is exported from that project's folder.
A copy installed with `uv tool install` (or `pip install`) runs the same
command as `infragram export:project ...`; the wheel carries the skill's
assets, so it needs no plugin folder.

| Option | Values | Default | What it does |
|---|---|---|---|
| `--formats` | any of `template`, `html`, `svg`, `png`, `drawio`, `terraform`, `terraform-modules`, comma-separated | `html,svg,png` | `svg` and `png` are drawn from the page, so they also write the HTML; the document (`template`) is written only when named, since the page carries it and downloads it; `terraform` writes the skeleton folder `<slug>-terraform/` for Azure, `terraform-modules` the same through the public registry's modules to `<slug>-terraform-modules/`; `drawio` writes `<slug>.drawio` (below); none of those three needs a browser |
| `--output-dir` | a folder | `./dist` | where the files go |
| `--libraries` | `drawn`, `project`, `all` | `project` | which component libraries the page embeds (below) |
| `--theme` | `light`, `dark`, `darker` | `light` | the workspace theme the SVG and PNG are drawn in |
| `--display` | `project`, `card`, `icon`, `both` | `project` | how components draw in the SVG and PNG (below) |
| `--write-looks` | `document`, `both` | `document` | with `--display both`, which looks reach disk |
| `--prices`, `--no-prices` | flag | tables | every export prices its Azure components from the shipped price tables (no network); `--prices` fetches live where supported, `--no-prices` writes no price (below) |
| `--background` | `paper`, `transparent`, a hex colour | `paper` | what the picture carries behind it |
| `--scale` | 1 to 4 | 3 | the PNG's multiplier |
| `--verify` | | off | run the shipped checker over every file written |
| `--drawio-icons` | `native`, `embedded` | `native` | with `drawio`: draw.io's own Azure and Kubernetes stencils where one matches, Infragram's artwork elsewhere; `embedded` draws Infragram's artwork everywhere |
| `--no-embed` | | off | leave the SVG and PNG bare; by default each carries its document, so `export:project picture.png` redraws it |
| `--size` | `fit` or a preset (below) | `fit` | the canvas the SVG and PNG are drawn on: `fit` crops them to the drawing; a preset (`slide-16x9`, `social-og` ...) centres the drawing on that canvas and scales it to fit |
| `--renderer` | `editor`, `static` | `editor` | what draws the SVG and PNG: the editor runtime in a browser (the static renderer steps in, with a note, when it cannot), or the static renderer on purpose, which needs no browser for the SVG |
| `--routing` | `around`, `direct` | `around` | how the wires run in the SVG and PNG: around the cards, or straight from port to port as the editor's routing switch draws them |
| `--terraform-zip` | | off | with `terraform` or `terraform-modules`: each skeleton as `<slug>-terraform.zip`, laid out as the page's Download menu gives it, instead of a folder |
| `--title` | text | the document's | the title the exported diagram carries |
| `--status` | text | the document's | where the drawing stands, saved as metadata (below) |
| `--offline` | | off | load nothing remote while drawing; the same as `INFRAGRAM_RENDER_OFFLINE=1` |
| `--timeout` | seconds | 120 | how long a page may take to draw; the same as `INFRAGRAM_RENDER_TIMEOUT_MS` |
| `--force` | | off | replace files the command refuses: written elsewhere, or edited since the last export; only when the user means it |

Outputs are named after the project `slug`. Report every path written and
its size.

`--formats drawio` writes a draw.io file for anyone who keeps diagrams in
draw.io, Confluence or VS Code. It holds the picture as laid out here, in the
icon look: frames as draw.io containers in their own colours, every wire with
its bends and its ends where they were seated, so it opens as exported
rather than re-laid-out. Azure and Kubernetes components use draw.io's
own stencils where the name matches exactly (944 of them), which keeps the
file small and lets draw.io restyle them and export them to Visio; the rest
carry Infragram's artwork. Every element keeps `infragram_component`, so
`import:drawio` reads the file back as the same components.

Every SVG and PNG carries the document it was drawn from (a `<metadata>`
element in the SVG, an `iTXt` chunk in the PNG), so a picture found in a
wiki or a ticket redraws: `export:project picture.png` (or `.svg`, or the
exported page) takes it as its source. `--no-embed` leaves a picture bare.

**What the page embeds.** `project` ships the document's own libraries, any
library their starter stacks place components from, and the shared
primitives and frames: two to three megabytes for a cloud project. `all`
ships every installed library, about ten times larger, so the page can add
any of them later. `drawn` (the default for `compose` and `export:set`) ships
only the components the drawing places, plus the shared set every diagram
arranges with -- the architecture frames, the basic elements, the 3D item:
1.5 to 2.4 MB over the shipped templates, and a multicloud or on-premises
page loses most of its weight (26.3 to 1.6 MB, 13.6 to 2.4 MB). The reader
of a `drawn` page can still move, restyle, connect, frame and export
everything in it, but cannot add a component it does not carry; a search
that finds nothing says so.

**Looks.** `project` follows the document's `presentation.display` (`icon`
unless the document says `card`) and keeps the look an author set on any one
component. `card` is the titled box; `icon` is the bare vendor mark with its
caption beneath, as reference architectures are drawn; either one applies to
every component, including ones switched by hand, as the inspector's
**Components** row does. `both` with `--write-looks both` writes both looks,
each laid out for itself: the cards under the plain names and the icons as
`<slug>-icons.svg` and `<slug>-icons.png`. Without it only the document's own
look is written, and the other is drawn and checked only under `--verify`
(and with `svg` among the formats), then discarded. The HTML is the same whichever
look is asked for, and the page opens in another look for one visit with
`?display=icon` in its address.

**Themes and backgrounds.** `light` gives white cards and dark text and is
what the editor opens in; `dark` and `darker` are for a dark slide or page.
A dark picture is drawn from the canvas colours the editor paints with, by
the static renderer too, so an export on a machine with no browser is dark
as asked. The page also takes `?theme=light` and `?grid=1` (the grid opens hidden) in its address.
`--background paper` is the theme's own ground; `transparent` takes the
colour of whatever the picture is placed on.

## Views: one part of the diagram, on its own

`--view NAME` draws part of the diagram as its own picture, laid out afresh,
written as `<slug>-<view>.*`. One diagram file then serves every reader.

```bash
infragram views landing-zone.py                       # what can be named
infragram compose landing-zone.py --view rg-prod-app  # one resource group
infragram compose landing-zone.py --view "name:*prod*"
infragram compose landing-zone.py --view all          # every declared view
```

- **A level.** Name any frame, by id or caption: a subscription, a resource
  group, a VNet, a VPC, a namespace. The picture is that frame and what is
  in it, with nothing around it. Nothing has to be declared. Two frames with
  one caption are told apart by id, which `infragram views` lists.
- **A rule.** `tag:env=prod`, `category:networking`, `name:*-prod-*` (a
  naming convention), `id:<element>`. The frames the matching components sit
  in are drawn around them.
- **A declared view** in the diagram file, with `include`, `exclude` and
  `extends`: `diagram.view("prod", "Production", include=["name:*prod*"],
  exclude=["category:analytics"])`.

A wire is drawn when both its ends are in the view; nothing is bridged. An
environment frame is not drawn in a view: the names say the environment, and
the view's name stands at the top of the picture. The page written for a
view shows that view. `export:set` draws whole diagrams and takes no
`--view`.

## Checking an export

Pass `--verify`, or run the shipped checker on what was written:

```text
python "<skill>/scripts/infragram.py" check <directory>
```

For a `.svg` the checker reads the picture: wires orthogonal, none through a
card's text, a glyph, a frame title or a card it does not join, none running
along a frame's border (within 3 px for 24 px or more), no caption on another
caption, a card or a frame's border, every caption's chip within 12 px of a
wire, everything -- wires too -- inside the viewBox. It holds the
picture to its document -- every declared connection drawn exactly once, with
the arrowheads (`forward`, `both`, `none`) and line kind (`solid`, `dashed`,
`dotted`) it asked for -- reading the `<slug>.infragram.json` beside it, or
else the document the `<slug>.html` beside it carries. Every component in a
document is checked against the shipped inventory, so a service no library
ships is refused rather than drawn.

To prove an export repeatable:

```text
python "<skill>/scripts/infragram.py" verify:render <page.html> --passes 3 --display both
```

renders the page three separate times in Chromium, for cards and for icons,
requires the passes to be byte-identical, and then runs the picture checks on
the result. It exits non-zero on any finding.

## A set of diagrams

Four views of one estate belong together, and exporting them one at a time
leaves every artifact in one flat folder. `export:set` gives each diagram a
folder:

```text
python "<skill>/scripts/infragram.py" export:set <folder> [--output-dir <directory>] [--passes 3] [export options]
```

It reads every `*.py` diagram file and `*.infragram.json` document in
`<folder>` before writing anything -- files named `_*` are helpers and are
skipped, and a folder with no loose sources rebuilds from the copies filed as
`<slug>/<slug>.py` or `<slug>/<slug>.infragram.json` -- and stops up front
when a file closes no diagram or two sources draw the same slug. A diagram
file's saved layout (`<name>.layout.json`, from `layout:save`) is put back as
`compose` puts it and travels with the copy. Each diagram then goes into
`<slug>/` under `--output-dir` (the sources' own folder by default) as a copy
of its source (never moved) beside what the export writes: `.html`, `.svg`
and `.png` unless `--formats` says otherwise. The export options are
`compose`'s and mean the same, every one of them (`--formats`, `--size`,
`--no-embed`, `--drawio-icons`, `--terraform-zip`, `--status` ...), with four
differences: the output goes beside the sources by default, `--display`
defaults to `both`, every file is always checked, so there is no `--verify`,
and there is no `--title` or `--view` (each diagram keeps its own title, and a
set draws whole diagrams; draw a view with `compose` or `export:project`).
`--jobs N` draws N diagrams at once, each in its own browser. Each page is rendered
`--passes` times in both looks with the passes required identical
(`--passes 0` skips that), and `README.md` records every diagram's status,
notes, date, check count and files with their sizes, the version that drew
them, and the command that rebuilds the set with the same options. A
diagram folder that exists is replaced whole with `--force`, or not at all.
Without Playwright and Chromium the default formats leave out the PNG with
a note, as `compose` does; a `png` asked for by name stops the set before
anything is written. Its pages embed only what they draw unless
`--libraries` says otherwise.

## Where a drawing stands

A diagram of an estate is a claim about that estate on a day. `Diagram(...,
status=, notes=, drawn=)` records it:

```python
with Diagram("Production target", "...", status="CURRENT — verified 2026-09-07",
             notes=("PRODUCTION NO-GO",), drawn="2026-09-22") as diagram:
```

Status, notes, and dates save as document metadata. They are not printed in
the editor header, SVG, or PNG, and no status attribute is attached to the
HTML or SVG root. Keep explanatory text in a companion README or notes file.

## Prices and links

Right-click a card and choose **Inspect details** to open its component information
and official-site links from `assets/catalog/links.json`. Shared components
without a vendor have no provider links. Links open only when clicked.

Every export prices what it draws, before it draws it, approximately:

```text
PRICED   app-vm: approximate monthly price for the stated Azure size and region
PRICED   storage: fixed and usage lines, with unspecified quantities marked assumed
PRICED   summary: priced resources, free resources and resources without a fixed estimate
```

- **Where prices come from.** Azure's shipped table
  (`assets/prices/azure.json`) comes from the Azure Retail Prices API and
  records its publication date. Table pricing needs no network. `--prices`
  requests a live source where supported and otherwise uses the table;
  `--no-prices` writes no price.
- **What is priced.** Azure components are priced, marked free, or left
  unpriced with a reason (token usage, contracts or no fixed size). Other
  installed diagram libraries do not gain an Azure price by assumption.
- **What it is priced as.** An element's `attributes.sizing`
  (`.sizing(size="Standard_B2s", region="eastus2", count=3)` in a diagram file): a size
  or class, a `region` (else the region frame around it), a `count`,
  `hours` a month (730), and for what is billed by use the quantities
  (storage, requests, data out). What it does not say is priced as the
  service's default and marked **assumed**; a key the service does not read
  is refused, never ignored.
- **Lines.** A price is the sum of its lines: each a thing billed, its
  quantity, rate and amount, **fixed** (a resource running all month) or
  **usage** (what it serves), the quantity marked assumed where it is a
  default.
- **Where it goes.** The price is written into the element
  (`attributes.price`: the month's total, the lines, fixed and usage, the
  sizing, what was assumed, the rate in words, the source and the dates);
  where it cannot price, the reason (`attributes.unpriced`). The page's
  header shows the total and its Cost tab the detail; nothing is drawn on
  the canvas, the SVG or the PNG. A price written by hand or by Infracost
  is never replaced.
- **What it cannot price** is a `NOTE` and no price -- a size the cloud does
  not list in that region, a sizing value that is not one -- never a guess.

A price is an estimate from on-demand list prices: no tax, discounts,
savings plans, reserved, committed-use or spot rates, and usage only as
the quantities shown.

**Infracost.** `--infracost FILE` reads what `infracost breakdown --path
<folder> --format json` wrote (Infracost needs the user's own key or a
self-hosted pricing endpoint; Infragram never runs it, and never needs it)
and prices matching resources covered by that breakdown. A resource is joined to
the element drawn from it by its Terraform address: the table's `Resource`
rows `import:terraform` writes. An element drawn from several resources is
priced at their sum, and Infracost's price wins where `--prices` priced
the same element. The popup names the breakdown as the source.

**Adding it up.** `infragram costs <document|diagram.py|page>` prices the
diagram as an export does and adds it up -- the total, each frame's (everything priced
inside it, however deep) and each component's -- and `--csv FILE` writes
the same as one row each (`kind` is component, frame, undrawn or diagram).
It takes `--prices`, `--no-prices` (add up only what the document carries)
and `--infracost` too, and `--json` prints the same as
one JSON document (the totals, each frame's, each priced component with what
its price assumed) for a script or a CI job. What a breakdown prices and the
diagram does not draw is listed `UNDRAWN` and counted in the total, so the
total stays the configuration's; currencies are added up apart, never
converted.

```text
COSTS    plan-changes: about USD 181.88 a month, 2 components priced, 1 resource priced but not drawn
FRAME    Production: USD 180.38 (2)
FRAME      eastus2: USD 180.38 (2)
ITEM     database: USD 150.01 [azure:sql-database] in Production > eastus2 (Infracost breakdown ...)
UNDRAWN  azurerm_log_analytics_workspace.app: USD 1.50 (priced, not drawn)
```

## What each artifact contains

| Artifact | Contains | Excludes |
|---|---|---|
| `<slug>.infragram.json` | the project document, schema version 3 | rendered coordinates that were never authored |
| `<slug>.html` | header, library sidebar (the embedded libraries), search, inspector, drawer (examples, 3D builder), interactive SVG canvas, embedded document and editor state, runtime, the four faces inline | nothing remote - this is the editor |
| `<slug>.svg` | the editor's own diagram export with its title, description, ARIA relationship, provider artwork, frames, wires, labels, and the faces as inline `@font-face` rules in `<defs>`, cropped to the drawn content plus a 48 px margin | sidebar, inspector, header, grid, guides, handles, selection |
| `<slug>.png` | the same SVG captured in Chromium at the requested scale, cropped like the SVG, on the `--background` | everything the SVG excludes, and the empty canvas around the content |
| `<slug>-terraform/` | the diagram's Terraform as a module a concern (`modules/network`, `modules/compute`, ...) of plain resources, and `environments/dev` and `environments/prod` calling each once; a variable for every value the diagram does not state, listed in each environment's `terraform.tfvars.example` ([terraform.md](terraform.md)) |
| `<slug>-terraform-modules/` | the same layout, each module calling the public registry's maintained module where one fits, pinned ([terraform.md](terraform.md)) |

Every picture sets its text in Inter and carries its faces -- Inter and Geist
Mono, about 230 KB of `@font-face` rules -- so the
page, the SVG and the PNG draw the same text anywhere: offline, embedded as
an image, or on a machine with no route out. The SVG and the PNG come from
the page's editor runtime, so they show the drawing as the author left it;
without Playwright the SVG is the static renderer's, which draws the same
picture from the same saved positions, and the export says so in its notes.

The exported HTML works from `file://`: components drag from the library,
terminals create orthogonal connections, frames contain and move their
children, layers hide and lock, and the page downloads its current document,
HTML or SVG without a server. Browser-local recovery keeps edits between
reloads; `?fresh=1` opens a separate workspace that ignores saved state.
Hovering a component shows its name, detail, component id, frame and layer;
a wire shows what it joins; every node also carries an SVG `<title>`, so the
`.svg` explains itself in any viewer.

## Connectors

A connector carries its own look: line kind (solid, dashed, dotted), colour
and width, one of four arrowheads (`triangle`, which the inspector calls
Solid; `open`; `circle`; `diamond`), a direction, and a label with its own
font, size, weight, colour and opacity. The inspector's Text tab holds all
of it when a connector is selected.

Connectors route around cards rather than through them: the renderer
searches for the shortest orthogonal path that keeps clear of every card
that is not one of the wire's own endpoints, charging for each corner so it
does not stair-step across open space. Pin a wire by hand with `waypoints`
on the connection, turn routing off for one visit with `?routing=simple`, or
for the project with the Connectors control on the inspector's Diagram tab.

## Size presets

`--size` puts the SVG and PNG on one of these canvases: the drawing is the
one the editor drew, centred and scaled to fit inside the preset's margin,
with the ground carried out to the edges, so a slide gets a 1280 x 720
picture whatever the diagram's proportions. `fit`, the default, crops the
picture to the drawing. A document's own `presentation.size` bounds the
static renderer's layout (the picture the page carries for a reader without
scripts, and `--renderer static`), and every preset draws the same type.

| Preset | Canvas |
|---|---|
| `doc-inline` | 960 × 600 |
| `doc-wide` | 1280 × 720 |
| `slide-16x9` | 1280 × 720 |
| `slide-4x3` | 1024 × 768 |
| `social-og` | 1200 × 632, 64 px margin |
| `social-square` | 1080 × 1080 |
| `print-a4-landscape` | 1120 × 792 |
| `print-letter-landscape` | 1056 × 816 |
| `fit` | content bounds |

Without `--size`, the PNG's pixel size is the content bounds plus a 48 px
margin on every side, times the scale; with it, the preset's canvas times the
scale (`--size slide-16x9 --scale 3` is 3840 x 2160). Never scale below 1 to
hit a small target (pick a smaller preset instead) and never above 4.

## SVG and PNG prerequisites

Both browser-backed formats need Playwright and Chromium. Without them the
default formats leave the PNG out with a note, an explicit `png` fails before
anything is written, and the SVG is still written, from the static renderer,
with a note saying so. Before asking for either, check:

```text
python -c "import playwright"
```

If that fails, surface this instruction and stop - do not auto-install:

> Playwright isn't installed. To enable PNG export, install it into the
> Python that runs Infragram, then its browser:
> ```
> python -m pip install playwright pillow
> python -m playwright install chromium
> ```
> A copy installed with `uv tool` takes the `png` extra instead:
> `uv tool install "<plugin folder>[png]" --force`.
> Then ask me to export again.

Pillow draws the 3D items a document renders by spec. The capture waits for
fonts, stages the runtime's clean SVG export by itself (no grid, guides,
handles, or selection), crops it to the drawn content plus a 48 px margin,
and never screenshots the sidebar, inspector, or controls. An empty diagram
keeps the whole canvas rather than guessing a crop.

Two settings shape a browser render, as flags or as environment variables.
`--timeout SECONDS` (`INFRAGRAM_RENDER_TIMEOUT_MS`) is how long a page load
or a script may take (120 s by default; a slow machine needs more).
`--offline` (`INFRAGRAM_RENDER_OFFLINE=1`) keeps a render off the network
altogether; nothing a page needs is out there, so it is a guard for a machine
without a reliable route out.

## The provider mark

Every export carries the installed provider's lockup at the bottom-left
of the picture. The mark
has a band of its own: it sits one `mark.gap` (16 px) below the lowest frame or
card, left-aligned with the content, and the picture extends to hold it.
Nothing is ever drawn over it. Both renderers read the band's numbers from
`assets/catalog/render-metrics.json` under `mark`; the export crop keeps the
band, and the checker refuses a picture where the mark touches a frame, a
card, a caption or a wire, or falls outside the viewBox.

## The 3D builder

A page carries the shared 3D renderer when it embeds a custom 3D item or
embeds every library; any other
page says in its drawer that it has none. The **3D builder** tab in the
drawer lists the builders; pick one, turn the knobs its signature declares,
choose a family colour or your own `#rrggbb`, a glyph or none, name the
item, and render a preview -- in the page, no server. *Add to diagram*
measures the render the way the shipped table was measured, so links seat
on it, and adds an `infragram:custom-3d` node that carries the spec, the
artwork and the measurement in its attributes. That is the same form
`Iso(...)` writes from code, so the saved document draws the item in the
static picture and every later export without needing the page. From a
script, `window.infragramEditor.build3d(spec, {name, detail})` adds one the
same way; `window.iso3d.recipes` and `window.iso3d.knobs(recipe)` list what
can be built. The renderer opens its WebGL context only when first used.

## Edge cases

- **Output exists**: files the last export wrote, unchanged since, are
  replaced without asking (their SHA-256 is recorded in the user's cache).
  A file written elsewhere, or edited since, is refused and named: ask
  before `--force`, which loses that edit.
- **`terraform` on a diagram with nothing on Azure**:
  refused before anything is written, the error naming the diagram. Export
  the other formats without it.
- **Unknown provider or component**: the document fails validation with the
  offending id. Fix the document; never guess a substitute library.
- **Unresolved connection target or layer**: same - the error names the
  element. The checker reports the same problems without pydantic.
- **Version 1 or 2 documents** open and export unchanged; a saved document
  is written as version 3.
- **The user wants the whole editor page as an image**: that is a browser
  screenshot, not an export. SVG and PNG are diagram-only by contract.

## What export never does

- Modify the source document in place (a document is written to the output
  directory).
- Load or add anything remote: scripts, stylesheets and fonts all travel in
  the page.
- Keep a second layout for SVG or PNG. If the picture is wrong, fix the
  project or the renderer - never the artifact.
