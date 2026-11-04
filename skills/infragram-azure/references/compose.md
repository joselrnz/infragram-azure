# Compose a diagram as code

Write the diagram the way you would describe it. Nesting is containment and
an arrow is a wire; nothing in the file says how anything is drawn.

```python
from infragram.author import Diagram, Edge
from infragram.nodes.frames import azure as az
from infragram.nodes.azure import compute, databases, networking

with Diagram("Azure hierarchy: tenant to virtual machine"):

    with az.Tenant("Contoso - Microsoft Entra tenant"):
        with az.ManagementGroup("Platform management group"):
            with az.Subscription("Production subscription"):
                with az.ResourceGroup("rg-prod-web"):
                    with az.VNet("vnet-prod - 10.10.0.0/16"):
                        with az.Subnet("snet-web - 10.10.1.0/24"):
                            appgw = networking.ApplicationGateways("Application Gateway", "WAF v2")
                            web = compute.VirtualMachine("Web tier", "VM scale set")
                        with az.Subnet("snet-data - 10.10.3.0/24"):
                            sql = databases.SQLDatabase("Azure SQL", "private endpoint")

    appgw >> Edge("HTTPS") >> web
    web >> Edge("TDS 1433", dashed=True) >> sql
```

Run it through the skill's launcher (`<skill>` is this skill's folder), from
the directory the file is in:

```text
python "<skill>/scripts/infragram.py" compose azure.py --formats template,html,svg,png --output-dir dist
```

`compose` finds the diagram the file wrote, builds the document, places it,
exports it and prints the paths. Then check the pictures as
[export.md](export.md) describes: `verify:render` for three identical passes
and `check` for the picture rules.

## The three rules

To mark unconnected wire crossings in every export, use
`Diagram("Network", crossings="bridge")`. The default is `crossings="plain"`.
The equivalent project setting is `presentation.crossings`: `"bridge"` or
`"plain"`. This presentation choice never changes the graph's connections.

To draw every frame's border heavier, use `Diagram("Network",
frame_lines="medium")` or `"thick"` (1.75 and 2.5 times each frame's own
width); the default is `"thin"`. The project setting is
`presentation.frame_lines`.

**A frame is a `with` block.** Whatever is written inside it belongs to it:
nodes and other frames alike. Two frames in one `with` nest in order
(`with az.Subnet("snet-app"), az.AKS("aks-prod"):`). A frame's badge, colour,
dash, line weight and tab come from the theme; see [frames.md](frames.md).

**An arrow is a wire.** Between two nodes `a >> b` draws a wire, `a << b`
one the other way, `a - b` one without arrowheads. An `Edge` between them
carries the label and the line: `a >> Edge("HTTPS") >> b`,
`a >> Edge("sync", dashed=True) >> b`, `a >> Edge("peering", both=True) >> b`,
and `a >> Edge("fan out") >> [b, c]` for one to many. Kinds are `solid`,
`dashed`, `dotted`, plus any link kind the installed provider theme declares
through `Edge(kind=...)`; the kind decides the dash and the picture
checker judges the export from the same table. The head shape is
`Edge(..., arrow="diamond")` (`triangle`, `open`, `circle`, `diamond`, from
`arrowheads.json`) and the bend `Edge(..., corners="rounded")` (`sharp`, the
square elbow every wire gets by default, `rounded`, `curved`, from
`render-metrics.json` under `router.corners`);
`Diagram(..., corners="rounded")` sets the bend for every wire that does
not choose its own. Legs stay horizontal and vertical in every style, so
the picture rules hold, and both renderers draw the same head and bend. For
dense diagrams `a.to(b, label="HTTPS", kind="dashed")` says the same thing
without operators.

Which side of a card a wire uses is
`Edge(..., leaves="bottom", arrives="top")` (`top`, `right`, `bottom`,
`left`); a node has one connection point a side (ADR 0006), so those are the
choices, and left out both renderers anchor the wire where the two cards
stand. It is the same choice as the editor's *Leaves from* and *Arrives at*,
written to the document as `source_port` and `target_port`
([project-schema.md](project-schema.md)). Say it when the reading needs it --
a wire that should leave downwards in a top-down chain -- not to tidy a
picture the router already draws well.

A flow told in order -- a CI/CD pipeline, a request's path, a sign-in --
numbers its wires: `a >> Edge("push", step=1, says="A push to main starts the
workflow") >> b`. Each numbered wire wears a bold circle with its number at
the start of its caption, marked the way the cloud's own drawings mark steps
(`step_color` in the theme file: Azure green, Databricks lava; else its link colour), and the picture gains a Steps panel
beside the drawing, one line a step, in order: `says`, else the caption. A
step needs a caption and is 1 to 99; two wires may share a number (the first
one's line is listed).

A second flow -- what happens at runtime beside a deploy, an outbound path
beside an inbound one -- names itself: `Edge("pulls", step=1, flow="At
runtime")`. Its steps are marked the theme's second way (`step_second`: Azure blue squares; a square in the step colour elsewhere) and listed under the name after the
main flow. A drawing tells two flows apart, its main one and one named
second; a third name is refused. The document keeps `step`, `step_text` and
`step_flow` on the connection, and the editor saves them back;
`examples/*_github_actions_oidc.py` number the steps of a keyless deploy
and tell a second flow: the image pull at runtime, or (Entra ID) the
one-time setup of the trust.

**Do not lay it out.** The top-level frames sit side by side;
`Diagram(..., direction="down")` stacks them instead, one tier under the
next, the way a grid or a power chain reads. Below that the layout alternates
row and column on its own, and a frame left to it wraps into rows once it
holds six or more children and its one axis runs long (a column more than
five times as tall as it is wide, a row more than eight times as wide), with
as many columns as bring it nearest 16:10, so twenty servers in a subnet
make a block, not a tower. A frame's `.row()` or `.column()` keeps it on one
axis, `.grid()` wraps it however few it holds, and `.keep_order()` keeps its
children exactly as written instead of moving them towards their
connections. The top level wraps only a very long line: a left-to-right
chain is often the point. Wires route themselves around cards, cards
grow to fit their names, and every arrowhead sits on a straight shaft.

New documents use schema 3. The installed vendor libraries are Azure,
Kubernetes and Databricks; shared components and generic frames are also available.

## What the classes give you

**Nodes.** One class per shipped icon, generated from the catalogs under
`infragram.nodes.<library>.<category>`: `azure.compute.VirtualMachine`,
`azure.networking.VirtualNetworks`, `azure.databases.SQLDatabase`,
`kubernetes.resources.Deploy`, and the classes under `infragram.nodes.databricks`. Attribute
access on the library package also finds a class in any category
(`azure.KubernetesServices`), and a typo raises with the nearest real names.
The class carries the icon, the category and the collection; the call site
adds the name and an optional detail line.

**Shared primitives.** `infragram.nodes.infragram` holds the neutral library
every diagram may draw from: `identity.PublicUsers`, `web.BrowserClient`,
`compute.Mainframe`, `storage.SANSwitch`, `networking.CoreSwitch`,
`security.Firewall`, `compute.UPS`, and the brand marks such as
`storage.BrandVeeam` and `identity.BrandKeycloak`. Every shared component,
id and class side by side, is in [shared-components.md](shared-components.md).

**Frames.** `infragram.nodes.frames.<group>` holds every containment frame of
every gallery, by the frame's own name with the group prefix dropped:
`frames.azure.ResourceGroup`, `frames.azure.VNet`, `frames.azure.Subnet`,
`frames.databricks.Workspace`, `frames.kubernetes.Namespace`,
`frames.generic.OnPremises` (a datacenter or office),
`frames.generic.DMZ`, `frames.generic.Environment`,
`frames.generic.StorageFabric`. A frame with
children draws around them; an empty one keeps its default size. The frame's
hierarchy rules are in [frames.md](frames.md); the class only fixes its
identity, not its parent.

**Plain groups.** `infragram.nodes.Group("Payments", "group")` is a zone the
theme styles by kind, for containment the galleries have no frame for. It is
a `with` block like any frame.

## What `Diagram` infers

| Field | Rule |
|---|---|
| `slug` | From the title (`azure-hierarchy-tenant-to-virtual-machine`); `slug=` overrides. |
| `description` | The title, unless given as the second argument. |
| `component` | From the node class: its collection is the provider, its icon the service id. Every id is checked against the installed catalog; an unknown one fails with the nearest real ids. |
| `providers` | Every library the elements use, in order of first use. `providers=[...]` adds or reorders. |
| `kind` | One cloud library gives `single-cloud`; one platform or on-prem library `platform`; clouds with a datacenter `hybrid`; several clouds `multicloud`. `kind=` overrides. |
| `display` | `icon` (bare marks with captions) unless `display="card"` (titled boxes); a node's own `editor_display_mode` still wins. See [export.md](export.md). |
| Ids | Derived from names and kept unique within the diagram (`web-servers`, `web-servers-2`); pass `id=` on a node to fix one. |
| Placement | None is written. The renderer lays the tree out each time it draws; a document carries positions only once someone moves things in the exported editor and saves it. |

`Diagram.to_project()` returns the document and `Diagram.export(directory,
formats=...)` writes it, the same as the command line.

## Finer control, when you mean it

- `with az.Subnet("snet-web").badge(networking.NetworkSecurityGroups, label="nsg-web"):`
  puts what applies to a frame on its top-right corner, the way Azure's
  reference diagrams seat an NSG on its subnet: the first badge's icon on the
  corner point, the rest on the top border leftwards from it, each name just
  under the line to the left of its icon. A label written `Type · name`
  (`"Route table · rt-spoke"`) sets the type in the frame's quiet tone. The
  editor, the HTML, the SVG and the PNG draw it alike; the frame widens so
  its title and badges never meet, and wires and captions keep out of the
  badges as they keep out of the title. `badge()` returns the frame, so it
  chains before `.row()` or `.column()`.
- `rt.table(("Prefix", "Next hop type", "Next hop"), routes)` attaches a
  table to any element. Nothing is drawn: selecting the card in the editor
  opens the table in a popup beside it, and any number of rows is the same
  call. Use it for a route table's routes, a security group's rules or a
  load balancer's back-end pools.
- `web.change("create")` (or `update`, `replace`, `delete`) says what a
  Terraform plan does to an element: the card in the action's colour and a
  mark on its detail line (`+ added`). `import:terraform` of a plan writes it
  ([terraform.md](terraform.md)); a card styled by hand keeps its own colours.
- `diagram.view("prod", "Production", include=["name:*prod*"])` names a
  part of the diagram that `--view prod` draws on its own; a rule is
  `tag:key=value`, `category:...`, `name:...`, `id:...` or a frame of the
  diagram. One frame alone needs no view: `--view` takes a frame's id or
  caption ([export.md](export.md), Views).
- `web.tags(env="prod", team="shop")` (or a mapping, for keys like
  `app.kubernetes.io/name`) says what tags an element wears. Nothing is
  drawn; in the page a right-click on the canvas lights the components
  wearing one.
- `web.sizing(instance_type="m6i.large", count=3)` says what an element is
  priced as when the export runs with `--prices` (EC2: `instance_type`,
  `region`, `os`, `count`, `hours`); what it does not say is assumed and
  marked so. Nothing is drawn: the price shows in the card's popup
  ([export.md](export.md), Prices and links).
- One wire's colour and width: `Edge("exfiltration", color="#d13438",
  width=2.5)` (a hex colour, 0.5 to 8 px), beside `arrow=` and `corners=`.
  They are the wire's look, not what it is: `kind` and `direction` say that,
  so reach for a colour only when the kind's own line is not the point. Two
  wires between one pair share one colour, width, arrowhead and corner
  style (the document keys them by target), and a second that asks for
  another is refused at its line. A misspelt keyword (`Edge("x", dashd=True)`)
  says which one was meant.
- Wires route themselves around cards, and around a frame that holds neither
  of their ends when the way around is not much longer: a wire crosses an
  unrelated group only when going around would cost a long detour. Pass
  `waypoints=[{"x": ..., "y": ...}]` on a connection only to overrule that.
- Cards grow to fit their own names in `fit` sizing, up to `max_width` on the
  node style, and the picture checker reports any text that was cut while the
  card could still have grown. A fixed size (`compose --size slide-16x9`, or
  `size=` on `infragram.compose.to_project`) keeps its size promise instead, so a long name
  truncates there and the checker leaves it alone.
- A wire may be aimed at a frame -- `node >> Edge("x") >> vpc` -- but only
  something drawn can carry an end of one, so the frame resolves to a card
  inside it: the one nearest the other end, once everything is placed. The
  exported page and the exported picture seat it on the same card. Aim at a
  card yourself when it matters which.
- `Diagram(..., status=, notes=, drawn=)` records where the drawing stands:
  `status="CURRENT — verified 2026-09-07"`, `notes=("PRODUCTION NO-GO",)`,
  `drawn="2026-09-22"`. These fields stay in the saved document as metadata;
  they are not printed in the editor header or diagrams. Put explanations
  and review notes in companion documentation; a picture that must carry its
  verdict itself (a NO-GO and why) draws it as a panel with the `blocker`
  tone (Panels, below), never as a card dressed as a service.
- A wire touches what is drawn: it meets a card at its edge and a bare glyph
  at the mark's own edge or beneath its caption, leaves straight out and
  arrives straight in, and every arrowhead sits on a straight shaft. The
  picture checker enforces this on every export. The rule is drawn in
  [connector-anchors.svg](connector-anchors.svg) and its cases in
  [connector-anchors-cases.svg](connector-anchors-cases.svg).

## Panels: boxes that say more

Some pictures need a box to carry its own facts: a load balancer's public
front end beside its back ends with what must never happen under both, a
worker with its pods inside it, a contract or a decision written down.
Any element becomes a *panel* when it carries one of these:

```python
from infragram.nodes import Box

lb = (
    Box("3 · Public regional HTTP load balancer", "one Gateway-owned resource")
    .tone("edge")
    .section("Public frontend", "HTTPS 443 · Full (strict)", tone="edge")
    .section("Gateway backends", "health-checked targets", tone="private", beside=True)
    .section("Direct origin access must fail", tone="blocker")
)
customer = Box("1 · Customer", "HTTPS 443\nStripe only when enabled").shape("ellipse")
control = Box("Managed control plane", "OIDC · API firewall").shape("hexagon").tone("managed")
contract = Box("Network contract", "default deny").shape("note")
```

- `.section(title, *lines, tone=, beside=False)` adds a compartment under
  the name; `beside=True` stands it beside the one before, in the same row.
  Each cell takes a share of the row by what its own words need.
- A detail with line breaks (`"one\ntwo"`) draws one line each.
- `.shape("ellipse" | "hexagon" | "note")` draws the box in that shape; only
  the rectangle and the note carry compartments.
- `.tone(name)` fills the box (or, as `tone=`, one cell) with a colour that
  means something: `edge`, `private`, `internal`, `correction`, `blocker`,
  `managed`, `neutral`. Say what each means once, and the legend lists it:
  `Diagram(..., tones={"edge": "public edge / ingress", "blocker": "launch blocker"})`.
- `Box` is a plain box with no vendor artwork (the library's Custom
  Resource), and a panel even with only a name and one line; a vendor class
  takes the same calls and keeps its icon in the corner, inside the outline
  of an ellipse or a hexagon too.

Any one of these makes a card a panel, a tone alone included; a card with
none of them is drawn as ever. Each tone's outline is its own hue (orange
edge, green private, blue internal, yellow correction, red blocker, violet
managed, grey neutral), in the light and the dark canvas alike. `import:diagram` writes the same calls from
a Mermaid flowchart's shapes, fills and line breaks (import-diagrams.md).
A panel grows to what it carries in any canvas, and stays a box when the
diagram is drawn as icons. The page, the HTML, SVG, PNG and draw.io draw it
alike, from the numbers in `render-metrics.json` (`panel`, `tones`).

## The low-level forms

Everything above compiles to the same document the low-level forms build,
and generators and patterns use them directly:

- `parent >> child` on a frame or group nests and returns the child;
  `parent.add(a, b)` fans out. Inside a `with` block this is never needed.
- `source.to(target, kind=, label=, direction=)` declares a wire and returns
  the source, so `.to()` chains.
- `compose.to_project(elements, slug=, title=, description=)` builds a
  document from a tree, and `compose.export(...)` writes it. `infragram
  compose file.py` exports the file's `Diagram`; a generator that assembles a
  `CloudProject` or a `Blueprint` itself may expose it as `PROJECT` instead,
  and a file that draws several pictures lists them as `PROJECTS` (each its
  own slug; every one is exported). `infragram compose -` reads the file from
  standard input.
- Repetition is a `Pattern` and a whole hand-assembled document a
  `Blueprint` (`infragram.patterns`); [patterns.md](patterns.md) is the
  guide.

## Items rendered by spec

When no shipped icon is the thing, describe it and it renders:

```python
from infragram.nodes.iso import Iso

db = Iso("DB-01", "PostgreSQL 16", recipe="server", family="storage", glyph="database", units=3, drivesN=12)
smr = Iso("Unit 2", "SMR", recipe="reactor", family="energy", glyph="power", kind="smr")
core = Iso("Core", "48 ports", recipe="switch", colour="#0f766e", glyph="arrows", count=48)
plain = Iso("Node 7", recipe="server", colour="#5b21b6", badge=False, units=1, drivesN=0)
```

`recipe` names one of the builders behind the shipped 3D set; the knobs are
the builder's own parameters. `infragram recipes` lists every recipe with its
knobs, their choices and defaults, the families and the glyphs; `infragram
recipes server` shows one with a ready-made `Iso(...)` line, and `infragram
recipes server --svg db.svg --set units=3 --family storage` draws it to look
at before placing it. `family` picks the colour,
`colour` overrides it, `glyph` is a vocabulary name or the path data of your
own 24-unit mark, `badge=False` draws none. The item renders once in
headless Chromium when the node is made (about a second the first time, a
cache hit after: `INFRAGRAM_CACHE`, else the platform cache directory), is
measured like a shipped icon so links seat on it, and travels in the
document -- spec, SVG and measurement in the element's attributes -- so the
static picture, the editor and every export draw the same. A spec the
builder cannot build is refused with the recipes or knobs it does have.
Place these shared custom items beside Azure, Kubernetes or Databricks
components. A shape no recipe makes is a new builder in the package, which is maintainer
work in a checkout: draw the nearest recipe and say what it lacks.

## Watching a file while you write it

`compose <file.py> --watch` draws the file, serves the editor on
`http://127.0.0.1:<port>/` (`--port N` picks it) and draws it again every
time the file, or a Python file beside it, is saved: the page reloads by
itself, and a file that fails to compose shows its error, with the line and
the nearest real name, over the last good picture. Each version opens as a
fresh workspace, so the page shows what the file says rather than what an
earlier version left in the browser. Only the HTML is written; export the
SVG and PNG with a plain `compose` when the drawing is right. It is for a
person at a keyboard: an agent composes once and checks with `--verify`.

## Keeping what was moved in the editor

A diagram file is drawn afresh on every compose, so what a reader drags or
resizes in the exported page would be lost the next time. Download the
document from the page (or keep the saved page, or a picture it exported),
then

```bash
python "<skill>/scripts/infragram.py" layout:save saved.infragram.json --for diagram.py
```

writes `diagram.layout.json` beside the file: each placed element's position
(and a frame's size, a card's look), by element id. `compose diagram.py`
reads it and draws everything where it was left; what the file adds later is
placed by the layout, and anything the layout file places that the diagram no
longer draws is reported. The diagram file is never touched. Renaming an
element changes its id, so it loses its saved place (reported).

## Checking the result

Pass `--verify`, which checks every file written, then prove the drawing
repeatable with
`python "<skill>/scripts/infragram.py" verify:render <page.html> --passes 3 --display both`,
as [export.md](export.md) describes. Open the HTML: every card should show its
artwork and every frame its tab. A card without artwork means a class from a
library the project does not install; `Diagram` reports that before export.

Every shipped example under `examples/` is written in this form and shows a
full estate. Azure: a hierarchy from tenant to virtual machine, an AKS
baseline, a hub-and-spoke landing zone, a web application behind Front Door.
A Databricks lakehouse example places its data services on Azure.
`connector_anchoring_cases.py` shows the same form in
functions: each returns a `Diagram`, so one file draws five small pictures
and, through `compose`, one combined picture.
