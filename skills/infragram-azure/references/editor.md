# The exported editor

The HTML export is the diagram *and* the editor for it: one file, opened from
`file://`, with no server and no account. This is what it can do, so the
person handed the file knows what is in their hands. Everything here is kept
in the document when they export it again.

## The canvas

A click shows, a double click edits. **Click** a component and its wires
animate in the direction the traffic runs while the rest of the drawing
steps back -- its flow -- and its details open if it has any; nothing is
selected. **Double-click** it to select it for editing: its handles, its
connection points and the inspector. Double-click what is already selected
to edit its name. Wires and frames work the same way: a click shows the
flow of that wire, or of everything in the frame. A click on empty canvas or
**Escape** ends a flow.

| To do this | Do that |
|---|---|
| See what flows through something | Click it (a component, a wire, a frame) |
| Follow one step of a flow | Click its row in the step list: that step's wires light and the other rows step back. Click it again, or empty canvas, to end it |
| See what depends on a component | Right-click it, **Show what depends on this**: everything that leads to it, however many wires away |
| See what the internet reaches, what costs most, or what wears a tag | Right-click empty canvas |
| Use the right-click menu | First what concerns the item: **Inspect details**, **Center on item** and what is particular to a card, a frame or a wire. Then the view: **Zoom in**, **Zoom out**, **Fit all**, **Actual size**, **Scroll moves the map** and **Tidy layout**, the same on empty canvas. The editing entries (duplicate, copy, style, display, order, group, detach, lock) are under **More actions**; **Delete** is last. Arrow keys move through it; **Right** opens More actions and **Left** closes it |
| Select it for editing | Double-click it; double-click again to edit its name |
| Add a component | Drag it from the sidebar onto the canvas, or drop it inside a frame to put it there |
| Find a component | Type in the sidebar's search. When nothing matches, the sidebar says so, and whether libraries the page carries are switched off or it carries only some (a copy exported with `--libraries all` carries every one) |
| Move something | Drag it -- it is selected as it moves. Hold **Alt** to ignore the grid and the alignment guides |
| Resize | Drag a component's right or bottom edge or its bottom-right corner; a frame by any corner or side |
| Select several | **Shift**-click, or drag a box on empty canvas. **Ctrl+A** takes everything in the frame you are in |
| Step through the drawing | **Tab** and **Shift+Tab**; **Escape** drops the selection |
| Nudge | Arrow keys, **Shift+Arrow** for a bigger step |
| Pan and zoom | Drag empty canvas or middle-drag to pan. The wheel zooms by how far it turns; with **Scroll moves the map** ticked in the right-click menu it pans instead, and **Ctrl** with the wheel (or a pinch) zooms. The browser remembers the choice. **+** / **-** (or **Ctrl+=** / **Ctrl+-**) zoom, **0** fits all, **1** (or **Ctrl+0**) is actual size |
| Put the layout back | **Tidy** in the toolbar restores the geometry the renderer laid out, keeping every name, style and connector |
| See the keyboard | **?**, or the keyboard button in the toolbar |
| Move the selection toolbar out of the way | Drag its grip, the six dots at its start. It stays there for every selection until you double-click the grip |

## Lenses

A lens lights part of the drawing and dims the rest, the way a click's flow
does. It changes nothing in the document or in a downloaded picture, its
menu entry shows a tick while it is on, and it ends on that entry, on
**Escape** or on a click on empty canvas.

- **Show what depends on this** (right-click a component): every component
  a wire leads from to this one, directly or through others. It is what
  stops working if this does. A wire with a head at both ends, or none, is
  followed both ways.
- **Show what the internet reaches** (right-click empty canvas): from the
  Internet, Public users and User components, along the wires' direction.
  An imported security group rule that lets the internet in is such a wire.
- **Show what costs most**: the priced components, each tinted by its
  share of the dearest one, with its month's amount above it.
- **Show what changed in 7 days** and **Show what has findings**, on a page
  an Azure import made with its recent changes and security findings: the
  components and frames changed in the week before the read, or with a
  Defender for Cloud or Azure Policy finding. Listed only when the page
  holds some.
- **Show what changed since the last read**, on a page drawn with
  `export:azure --refresh`: the components and frames added or changed since
  the read the earlier diagram came from. What was removed has nothing left to
  light, so the status line names it. Listed only on a refreshed page.
- A tag, listed as `Show env=prod (2)`: the components wearing it. Up to
  twelve tags are listed, the most worn first. Tags come from `.tags(env="prod")` in a diagram file,
  from a resource's tags on import, and from a Kubernetes workload's labels.

## Connectors

A connector is drawn by dragging from a component's port -- the dot that
stands just outside the middle of each side while the pointer is over the
component or it is selected -- onto another component.
The card under the pointer lights up as the drop target.

| To do this | Do that |
|---|---|
| Bend a wire | Drag the line itself -- a faint handle sits in the middle of each straight run of a selected wire. Each bend keeps a handle; drag one onto its neighbours to take that bend out |
| Move an end to another component | Drag the round handle at either end of a selected wire |
| Choose the side each end uses | Select the wire, **Text** tab, *Leaves from* and *Arrives at* |
| Put the route back | Right-click the wire, **Reset route** |
| Turn it around | Right-click, **Reverse direction** |
| Label it | Double-click the selected wire, or the **Text** tab. Drag the label to move it; **Reset label position** puts it back |
| Line, arrowhead, colour, width | **Text** tab, under *Connector* |
| Several at once | **Shift**-click each wire, then delete or restyle them together |

Wires route themselves around cards and frame titles, and around a frame that
holds neither of their ends unless the way around is a long detour. Two wires
between the same pair take a lane each instead of drawing over one another,
and a wire bent by hand keeps its corners in the exported picture as well.

## Frames

A frame holds components and moves with everything inside it. Drop a
component inside to put it in; drag it out, or **Detach**, to take it out.

| To do this | Do that |
|---|---|
| Call one out | Right-click, **More actions**, **Highlight frame** -- an accent ring, drawn in the picture too |
| Switch its contents | Right-click, **More actions**, **Show contents as icons** / **as cards**, or the **Style** tab's *Contents* |
| Review what is inside | Right-click, **Review components** -- every component in the frame, in one list, where each can be switched or selected |
| See it alone | Right-click, **Open this frame**, or **Open** in its review -- only the frame and what it holds, fitted to the screen |
| Fit it to its contents | Right-click, **More actions**, **Shrink frame to fit** |
| Group a selection | **Ctrl+G**; **Ctrl+Shift+G** detaches |

An open frame is a view, like the zoom. The breadcrumb over the canvas
(*Whole diagram > region > network*) goes back to any level above. A wire
that leaves the open frame ends at its border, with the name of the card it
reaches just outside; click the name to open the frame that holds that card.
The inventory and the costs count what the open frame holds, and the steps
its wires do not carry step back. Nothing of it is saved, and a download,
whatever is open, is the whole diagram.

## What it costs

The inspector's **Cost** tab shows what the diagram costs a month,
approximately, from on-demand list prices before tax and discounts:

- the total, split into **fixed** (resources running all month) and
  **usage** (what they serve: storage, requests, data out), with how many
  components are priced, free and assumed;
- **By frame**: each frame's subtotal, everything priced inside it however
  deep, nested as the frames are;
- **Items, most first**: each priced component with what it was priced as;
  open one for its lines, and **Show on canvas** for its flow and Details;
- **Assumed**: the values each item's price rests on that the diagram did
  not state (a region, a size, a quantity) -- `.sizing(...)` in a diagram
  file states them;
- **Not priced**: each component that is not, and why (billed per token,
  sold by contract, not in the tables), and a folded list of the ones that
  cost nothing on their own.

The tab is hidden when nothing is priced (an export with
`--no-prices`).

## Panels

A box written with compartments, several detail lines, a shape or a tone
(compose.md, Panels) is drawn so in the page as in every export: its name
and lines centred, each row of compartments under a rule, each cell on its
own tone. **Icons** leaves a panel a box, since its lines are the point of
it, and the legend lists what each tone means. The draw.io download keeps
the shape and the tone, with the compartments in the box's label.

The **Style** tab's **Box** section makes any one component a panel in the
page: **Shape** (Rectangle, Ellipse, Hexagon, Note), **Tone** (a chip per
tone, titled with what the diagram says it means), and **Compartments**, one
row a line, `||` between cells side by side, `|` before each line under a
cell's title and `[tone]` first to fill a cell:

```text
[edge] Public frontend | HTTPS 443 || [private] Gateway backends | health checks
[blocker] Direct origin access must fail
```

The box grows to what it carries and its neighbours make room; undo takes
each change back. An ellipse and a hexagon carry no compartments, and the
**Display** choice steps aside while only panels are selected, as does the
**Text** tab's **Type**: a panel's type is fixed, so every export draws it
alike.

In the **Text** tab, **Description** keeps one detail line a line:
Shift+Enter starts another (Return does on a touch keyboard, and leaving
the field applies it), Enter applies it, and a card given a second
line becomes a panel. A renamed or longer panel widens to its text and
keeps any larger size it was given. Dragged smaller, a panel stops at its
rows' height and its least width; past that its lines end in an ellipsis.

## A component's details

Some cards carry more than the drawing shows, and show it in a popup beside
the card, never over it:

- *A table*, such as a route table's routes, opens when the card is
  clicked or selected.
- *A price*, written by every export for the Azure
  components it draws, shows in **Details** and in the Cost tab: the
  month's total and the lines it adds up from (each thing billed, its
  quantity, rate and amount, marked *usage* where it rests on what the
  component serves), each value the diagram did not state marked
  *assumed*, and where the rates came from and when they were read. The
  page does not price anything itself: a card added in the page is not
  priced until the diagram is exported again.
- *Where the component is read about* -- the vendor's page for it, its
  pricing page, or a search of the vendor's documentation -- is in the
  card's right-click menu, **Inspect details**, which also shows its table
  and price. It is offered for one item at a time; on a card with nothing to
  show (a shared component names no vendor), a frame or a wire it opens the
  inspector instead.

**Escape**, a click on empty canvas, the close button or selecting another
card closes the popup; the close button leaves the card selected.

## On a phone or a tablet

The page works by touch. On a phone the drawing is the whole screen:

| To do this | Do that |
|---|---|
| See a flow | Tap a component, a wire or a frame |
| Select for editing | Double-tap it; the inspector opens as a sheet from the bottom and the drawing stays where it was above it. Double-tap again to edit its name |
| Move it | Once it is selected, drag it with one finger |
| Pan and zoom | One finger on anything not selected pans; two fingers pinch to zoom |
| Its menu | Press and hold it -- the right-click menu, beside the finger |
| Add a component | The **Components** button at the start of the toolbar opens the library; tap a component to add it where you are looking |
| Draw a wire | Select a component and drag from one of its connection points |

On a phone a component's details dock along the bottom of the screen rather
than beside the card, and step aside while the inspector's sheet is open. A
tablet keeps the desktop layout with touch-sized buttons and handles, and
its inspector opens over the drawing.

## The panels

- **Diagram** -- what the drawing holds, the grid, how connectors route, and
  whether every component draws as a card or a bare icon.
- **Style** -- the selected object's display mode, a frame's own settings, and
  the outline presets (Neutral takes an outline off again).
- **Text** -- names, descriptions, connector labels and their type: face,
  size, weight, colour, and the sides each end of a wire uses.
- **Arrange** -- exact x, y, width and height, stacking order, align and
  distribute, rotate and flip, grouping and locking.
- **Layers** -- one layer per library, plus the frame tree. Hiding a layer
  hides what is on it without deleting anything; locking it stops edits. A
  frame belongs to the library whose gallery it came from.

Below the canvas: **Examples** and the **3D builder**, which renders an
isometric item from a recipe and adds it as a component. The builder works
on a page that carries the 3D renderer -- one that draws a 3D item, embeds
every library, or embeds the on-premises library among the project's own;
any other page says so in the tab.

## Comments

Anyone reading the page can comment on a card, a frame or a wire: right-click
it and choose **Add comment**, or open **Comments** in the header. The panel
lists a thread per element, newest last, each with its author and time; the
element's name opens it on the map, and a numbered marker on the map opens the
thread. Your name is asked once and remembered in this browser.

Comments stay in this browser, under the page's workspace (`?fresh=` gives a
separate one), until **Download comments** saves `<slug>.comments.json`. Send
that file back, or commit it beside the `.infragram.json`: the next
`export:project` or `compose` carries it into the page it writes, and those
comments show for everyone who opens it. A view's page saves the file under
the document's slug, so it goes beside the document all the same. Only
comments written here can be deleted here; the ones the page carries belong
to the file. A comment on a wire also keeps the two cards the wire joins, so
it stays on its wire when wires are added or a view leaves some out.

A comment follows its element by id, so a rename in the editor keeps it. A
Python diagram derives ids from names, so pass `id=` on an element that
carries a discussion: a comment whose element is gone is listed under
**Detached**, with the name it was on, never dropped. Nothing is sent
anywhere, and no SVG, PNG or draw.io download ever carries a comment.

## Themes and exporting

Three themes -- Light, Dark and Darker -- from the palette button in the
header. On the dark themes, artwork drawn in a dark ink is drawn light
instead, so an icon meant for paper still reads. The theme a reader picks is
remembered in their browser and is not part of the document.

**Download** gives the document (`.infragram.json`), the page itself
(`.html`), the drawing as `.svg` or `.png`, or an editable `.drawio` file.
PNG and SVG downloads crop to the drawn content, captions, provider mark and
optional legend, with a 32 px margin; empty canvas and the editor's zoom do
not size the picture. **PNG quality** runs from 1x to 4x (2x by default), and
a very large PNG scales down to stay within 8,192 pixels a side and 16
megapixels, never clipped; SVG keeps full resolution. The Diagram panel puts
the title in the header, below the diagram or nowhere: a title below is part
of the PNG, SVG and draw.io downloads, the others are not. **Show legend**
draws a key below the drawing in the page, and **Legend in exports** (also in
the Download menu) puts it in the downloads; the key keeps a template's own
meanings, else describes the wire patterns, arrows and frames in use.
A diagram on Azure
also offers its Terraform skeleton, as plain resources or through the
Azure Verified Modules, each a `.zip` of the folder the export writes
([terraform.md](terraform.md)); it is the diagram as exported, and once you
edit the diagram the download says so -- download the template and export
it again to include the edits. A URL can ask for one visit's
look without touching what is saved: `?theme=dark`, `?display=icon`,
`?routing=direct`, `?grid=1` (the grid opens hidden), and `?fresh=<name>` for a
workspace of its own.

Edits are kept in the browser's local storage under the project slug and
optional `?fresh=<name>` workspace. Documents sharing that key share a draft.
**Download** makes the current edits a file. If browser storage is blocked or
full, a persistent warning offers **Download editor** so the edits can be
kept in an HTML file.

In **Diagram**, use **Crossings** and choose **Bridge** to mark separate wires with a
small semicircular hop, or **Plain** for their original appearance. This is
independent of **Connectors** → **Around** / **Direct**: Around finds a path past
components; Bridge marks a safe crossing between unrelated wires. Shared
endpoints, crowded crossings, and crossings too close to a label or corner
remain plain. A bridge never adds a network connection.

The choice survives undo, reopening, and Download as a template or HTML.
SVG and PNG exports, including transparent images and browserless SVG,
use the same crossing style. Draw.io exports carry the choice as native line
jumps; draw.io determines their placement when it opens the file. Existing
documents default to Plain.

**Frame lines** in **Diagram** draws every frame's border at its own width
(**Thin**), 1.75 times it (**Medium**) or 2.5 times it (**Thick**), so frames
still read on a zoomed-out drawing. It is saved with the document, undoes
like any edit, and every export draws the same weight.
