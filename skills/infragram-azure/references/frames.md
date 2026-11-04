# Frames

Frames are Infragram-drawn containment components. They are not copied
stencil artwork, so they stay editable in exported HTML: move a frame and its
children move with it; connections recompute from world coordinates. Each
library has its own frames because ownership, location, and network are
*not* one universal hierarchy - an Azure resource group can hold resources
from several regions, and Kubernetes node pools are infrastructure, not
parents of namespaces.

In a project document a frame is an element whose `component` is
`infragram:<frame id>`; its members are its `children`
(see [project-schema.md](project-schema.md)).

## Artwork

A frame draws as an outlined region with a solid, provider-colored tab holding
a small icon and the frame's name. The icon resolves in three tiers:

1. an official vendor icon named by the library's theme (Azure ships one for
   every boundary but the availability zone);
2. the Kubernetes mark for cluster frames (the Kubernetes cluster and AKS);
3. an Infragram-owned line glyph for the frame's kind.

Colors, dashes, widths, and fills come from the theme's `boundaries` block
where one exists; otherwise from the library's frame color.

## Core frames

The generic group carries provider-neutral frames for the containment every
diagram needs regardless of vendor. Ownership: **Organization**, **Account**,
**Project**, **Environment** (production, staging, development). Location:
**Region**, **Availability zone**, **On-premises site**, **Campus /
building**, **Wiring closet** (IDF/MDF). Network: **Cloud boundary**,
**Network boundary**, **Hub network** and **Spoke network** for hub-and-spoke
topologies, **Management network** for the out-of-band plane, **Storage
fabric** for SAN zones, **Public subnet**, **Private subnet**, **DMZ**.
Workload: **Security zone**, **Cluster boundary**. Dashed outlines mark the
logical groupings (environment, management plane, DMZ, zones, clusters);
solid outlines mark physical or network containment.

They draw in the neutral `generic` theme, which belongs to no library, and
they keep that look wherever they are placed: a datacenter frame inside an
Azure landing zone is grey in the static picture and grey in the editor.
That is right for containment no library names -- a datacenter, a DMZ, a
wiring closet -- and wrong for containment a library does name. **Public
subnet** and **Private subnet** are the pair to watch: Azure has frames of
its own for both (`frames.azure.PublicSubnet` and `frames.azure.Subnet`),
and reaching past them into the core frames puts a grey bordered, grey
badged subnet between two Azure blue ones. In an Azure picture, use the
Azure subnets. The
shipped hub-and-spoke template is the worked example -- a cloud boundary
holding the subscriptions, an environment frame holding the landing zones,
and a corporate datacenter beside them, all core frames around Azure's own.

## Starter stacks

The editor offers one nested starter stack per library. Frames stay
individually selectable, movable, and detachable after insertion.

| Library | Starter stack | Modelling rule |
|---|---|---|
| Azure | Tenant → management group → subscription → resource group → VNet → subnet | Region and zone are optional location frames; a resource group may span regions, so a region is never the parent of a resource group. |
| Kubernetes | Cluster → namespace → workload | Node pools are separate infrastructure frames. |
| Databricks | Account → workspace → compute | Unity Catalog sits beside the workspaces it governs. |

## What a frame draws in its title tab

A frame's tab carries a small piece of vendor artwork, chosen by the frame's
**kind** and the theme's `boundaries.icons` map. One rule decides every entry:

> A frame's badge is the vendor's own artwork **for that boundary**. Where the
> vendor ships none, the frame takes the generic tab.

A near-miss is worse than nothing, because it states something false. Azure
ships an Availability *Sets* mark and no Availability *Zone* mark, and the two
are different things — a set spreads across fault domains inside one
datacenter, a zone is a separate datacenter — so the zone frame is
deliberately unbadged rather than borrowing it.

Azure and Databricks frames carry their own vendor artwork; the generated
[inventory.md](inventory.md) gives the current counts. Azure frames use the
deck's icon for that boundary. Its public and private subnets share the
Subnet mark; the availability zone keeps the neutral zone glyph. The
Kubernetes cluster wears the Kubernetes mark. Databricks account, workspace,
compute and Unity Catalog use their corresponding marks. Core frames use
their kind's neutral glyph.

**What the tab itself is painted** is the theme's `boundaries.tab_fill`, and
it has two honest values. `frame` (the default) paints the tab in the frame's
own colour and reverses the glyph out in paper -- right for Kubernetes, whose
mark is a mono wheel, and for every core frame. `paper` leaves the tab white
and lets the badge paint itself -- right for Azure, whose badges are
full-colour icons. The distinction exists because Azure's frame colours were
sampled from those very icons, so a teal management-group mark on a teal tab,
an orange key on an orange tab and cyan chevrons on a blue tab all
disappeared. Both renderers read the same field, and
`tests/unit/test_badge_tabs.py` renders every badged frame to check that the
tab is the colour the theme says and that the badge's main colours stand apart
from it. Every frame seats a tab, so a badge is never drawn as a loose sticker beside
the title.

**Where the tab sits** is half the stroke width inside the frame corner, so
its outer sides lie on the border's inner edge and the border stays whole.
Drawn at the corner itself, the plate painted out the inner half of the
stroke -- a paper plate left the border broken and the badge looking as if
it sat on the line. Both renderers seat the tab the same way;
`tests/unit/test_badge_tabs.py` measures the static picture and the browser
suite measures the editor.

## What a frame is coloured

No vendor publishes a colour and line style for its boundaries the way a
group-box deck would, so without a rule every frame would fall back to the
theme's grey, and a subscription would look the same as a resource group.

Two rules replace the grey:

- **Azure** has a palette sampled from the deck's own badge icons, not chosen:
  cloud `#0078d4` (the Azure logo's blue, badged with the deck's own Azure A
  mark), tenant `#005ba1`, management group `#37c2b1`, subscription `#ffcb12`,
  resource group `#949494`, VNet and both subnets `#1490df` (the private
  subnet filled `#50e6ff`, the public one left open, which is what tells
  the two apart where they share a mark), AKS `#341a6e`, region `#ef7100`. The availability zone shares
  the region's hue and differs by dash.
- **Kubernetes** draws its frames in the vendor's own brand colour
  (`#326ce5`). That is honest — it is the colour the vendor chose for itself
  — without inventing a per-boundary palette the vendor never published.
- **The core frames** draw in the neutral grey (`#bdbdbd`) of the `generic`
  theme.

Every badge and every blank, with the reason for each blank, is recorded in
`assets/catalog/frame-badges.json`. The themes are what the renderers read;
that file is the review, and `tests/unit/test_frame_badges.py` fails when the
two disagree — so a frame cannot gain or lose a badge without somebody
deciding to, and a new frame fails the suite until its badge is decided
either way.

**Line weight** is one rule for every library: a frame border is 1.0 px
unless the theme declares a width for that kind; the house metrics keep
1.8 px for an outermost cloud boundary. No shipped theme declares a weight,
so every frame draws at the same 1.0 rather than a heavier default -- crisp
at every whole export scale, and identical in both renderers.

## The icon and the frame

Neither library files artwork as a group box. Both draw their containment
concepts as ordinary service icons, so seven icons name something a frame
also does:

| Library | Icon | Frame for containment |
|---|---|---|
| Azure | `networking.VirtualNetworks` | `frames.azure.VNet` |
| Azure | `networking.Subnet` | `frames.azure.Subnet` |
| Azure | `general.Subscriptions` | `frames.azure.Subscription` |
| Azure | `general.ManagementGroups` | `frames.azure.ManagementGroup` |
| Azure | `general.ResourceGroups` | `frames.azure.ResourceGroup` |
| Kubernetes | `resources.Ns` | `frames.kubernetes.Namespace` |
| Kubernetes | `resources.Group` | `frames.kubernetes.Workload` |

These are genuine service icons, and placing one is not a mistake: an
inventory diagram may want the drawing of a VNet rather than a box holding
things. So each class points at its frame and `check` says nothing — a
pointer, never a refusal. Group artwork, which no shipped deck files, would
be rejected; the rule and the reviewed table in
`assets/catalog/container-artwork.json` stay in place for a deck that does.

Candidates come from the counterpart test's matcher, which matches exact
words and initials of three letters or more. Recall is derived, judgement is not:
the table settles which frame an icon points at, and a test fails if new
artwork produces a candidate nobody has reviewed.

## One description of a frame

A frame is drawn by two renderers -- the Python renderer behind the golden
pictures and this gallery, and the editor runtime behind every exported HTML,
SVG and PNG -- and shown a third way as the sidebar thumbnail. One
derivation, `builders/frame_style.py`, serves all three, and everything else
reads it:

- **Colour** is the theme's `boundaries.colors[kind]`, else the theme's
  `boundaries.color` -- the vendor's own frame colour, declared by every
  shipped theme. Nothing fades with nesting depth.
- **Fill** is `none` unless the theme declares `boundaries.fills[kind]`.
- **Dash**: `boundaries.dashes[kind]` if declared; else groupings a diagram
  invents (organization, folder, project, region, zone, cluster, namespace,
  node pool, security zone, group, environment, DMZ, ...) draw `5,4` and real
  perimeters draw solid.
- **Line weight**: `boundaries.widths[kind]`, else 1.8 px for a cloud, else
  1.0 px.
- **Corners** are square unless `boundaries.radii[kind]` rounds them.
- **The tab**: every frame seats one, half the stroke inside the corner. It
  holds the theme's badge for the kind (`boundaries.icons[kind]`), else the
  generic glyph for the kind from `assets/catalog/frame-glyphs.json`, the
  same file the editor draws from. `boundaries.tab_fill` decides whether the
  tab is the frame's colour with a paper glyph (`frame`, Kubernetes and the
  core frames) or paper with the glyph in the frame's colour (`paper`, Azure).
- **The caption** is set in the sans face, authored case, weight 500, no
  tracking, in a readable darkening of the frame's colour; a theme may still
  choose mono uppercase.
- **The numbers** both renderers share -- tab 20, glyph 16 with a 2 px inset,
  5 px to the caption, baseline at tab / 2 + size / 2.8 -- live in
  `assets/catalog/render-metrics.json` under `frame`.
- **The gallery** a frame came from (`editor_frame_group`) decides which
  theme's block the derivation reads: a frame of the project's own library
  draws with the project's style, and a frame from another gallery keeps
  that gallery's look in both renderers.

A saved document's `editor_boundary_style` is a cache of that look, not an
override: on load the theme's values win for every key the derivation
carries, so a diagram saved under an older rule cannot drag stale paint into
a new picture. `tests/unit/test_frame_parity.py` renders every one of the 34
frames through both renderers and compares colour, weight, dash, corners,
fill, tab paint and seat, badge or glyph, and every caption property; it also
holds the sidebar's frame table to the theme colour and checks the runtime
reads the shared numbers rather than its own literals.

## Building a framed diagram

Four templates ship as worked examples; `references/inventory.md`
lists them with their libraries and counts. `azure-hub-spoke-landing-zone`
shows the core frames in use around Azure's own: a cloud boundary holding a
connectivity subscription, an environment frame holding two landing-zone
subscriptions, a management subscription, and a corporate datacenter drawn
from the shared primitives beside them. `azure-aks-baseline` nests the AKS
cluster frame in its subnet; `azure-web-app-front-door` spreads a
zone-redundant application over two regions; `azure-api` is the smallest
document, a client, an API and its storage. Export any of them to see the
finished picture:

```text
PYTHONPATH=src python -m infragram export:project skills/infragram-azure/assets/templates/cloud/azure-hub-spoke-landing-zone.infragram.json --formats html,svg,png --output-dir dist
PYTHONPATH=src python -m infragram export:project skills/infragram-azure/assets/templates/cloud/azure-aks-baseline.infragram.json --formats html,svg,png --output-dir dist
```

### In the exported HTML editor

1. Open the HTML. Add `?fresh=1` to the address to start from the file rather
   than a saved browser workspace.
2. Insert frames from the library's **Frames** gallery: a starter stack drops
   the whole nested hierarchy at once; single frames nest into whatever frame
   you drop them on. Resize with the corner handle; children move with their
   frame.
3. Drag a component from the library into a frame. The drop point decides the
   parent: a card dropped inside a subnet belongs to that subnet, and the
   exported project records it as that frame's child.
4. Drag a card's terminal onto another card to wire them, then click the wire
   label to name it (`HTTPS`, `SQL`).
5. **Template** downloads the `.infragram.json`, **HTML** the editor with the
   current state, **SVG** the clean diagram. PNG comes from the CLI export.

Scripts can do the same through `window.infragramEditor`: `addBoundary` and
`addNode` take the payload a sidebar drag carries (`id` is the service id,
plus `qualifiedId`, `provider`, `name`, `detail`, `iconUri`), `connect` wires
two ids, `setEdgeLabel` names a wire, and `exportProject()` returns the
document the Template button downloads.

### In the project document

A frame is an element whose `type` is its kind, whose `attributes` carry the
saved geometry and the frame group, and whose `children` are its members. A
component is a leaf with a `component` reference. Coordinates are editor
canvas units on a 4 px grid; sizes are the frame's own, so nest with room for
the 24 px padding.

```json
{
  "id": "snet-web", "name": "snet-web · 10.10.1.0/24", "type": "subnet-private",
  "attributes": {"editor_x": 456, "editor_y": 288, "editor_width": 432, "editor_height": 160,
                 "editor_frame_group": "azure"},
  "children": [
    {
      "id": "appgw", "name": "Application Gateway", "type": "service",
      "component": {"provider": "azure", "service_id": "application-gateways",
                    "icon_ref": "azure:application-gateways"},
      "attributes": {"editor_x": 528, "editor_y": 332, "detail": "WAF v2",
                     "editor_card_size": {"width": 288, "height": 72}},
      "connections": [{"target": "web-a", "kind": "solid", "label": "HTTP"}]
    }
  ]
}
```

An empty frame (no `children`) stays a frame because of `editor_frame_group`;
the tab icon, colour and dash come from the library's theme for that kind.

## Calling out a frame

A frame can be highlighted to call a region out: an accent ring six units
outside its border with a light tint, drawn the same way by the editor and
the static renderer and carried into the SVG, PNG and HTML exports. It is
saved on the frame as `"editor_highlight": true`; a frame that is not called
out carries no such attribute. In the editor, right-click a frame (or select
it and open the Style panel's Frame section):

- **Highlight frame** toggles the call-out.
- **Show contents as icons / cards** switches every component inside the
  frame, however deeply nested, and nothing outside it. Components keep
  their centres; stacked neighbours move apart to keep their gaps, and the
  frame and the frames around it grow to hold them, so icons never land on
  each other's captions.
- **Review components** opens a list of every component inside, grouped by
  the frame that holds it, with how each is drawn. Choosing a row selects the
  component and scrolls to it; the list also offers the highlight and the
  icons/cards switch for the whole frame.

## Frame ids

Kinds in parentheses drive the glyph and default styling. Use a library's own
frames when the provider is known; the core frames are for generic or
provider-neutral pictures and for the estate around the cloud.

### Core (shared)

| Id | Name |
|---|---|
| `custom-boundary-cloud` | Cloud boundary (cloud) |
| `custom-boundary-organization` | Organization (organization) |
| `custom-boundary-account` | Account (account) |
| `custom-boundary-project` | Project (project) |
| `custom-boundary-region-generic` | Region (region) |
| `custom-boundary-zone-generic` | Availability zone (zone) |
| `custom-boundary-network` | Network boundary (network) |
| `custom-boundary-public-subnet-generic` | Public subnet (subnet-public) |
| `custom-boundary-private-subnet-generic` | Private subnet (subnet-private) |
| `custom-boundary-security-zone` | Security zone (security-zone) |
| `custom-boundary-cluster` | Cluster boundary (cluster) |
| `custom-boundary-on-premises` | On-premises site (site) |
| `custom-boundary-environment` | Environment (environment) |
| `custom-boundary-dmz` | DMZ (dmz) |
| `custom-boundary-hub-network` | Hub network (hub) |
| `custom-boundary-spoke-network` | Spoke network (spoke) |
| `custom-boundary-management-network` | Management network (management) |
| `custom-boundary-storage-fabric` | Storage fabric (storage-fabric) |
| `custom-boundary-campus` | Campus / building (campus) |
| `custom-boundary-wiring-closet` | Wiring closet (closet) |
| `custom-section` | Section (group) |

### Azure

| Id | Name |
|---|---|
| `custom-boundary-azure-cloud` | Microsoft Azure (cloud) |
| `custom-boundary-azure-tenant` | Microsoft Entra tenant (organization) |
| `custom-boundary-azure-management-group` | Azure management group (management-group) |
| `custom-boundary-azure-subscription` | Azure subscription (subscription) |
| `custom-boundary-azure-resource-group` | Azure resource group (resource-group) |
| `custom-boundary-azure-region` | Azure region (region) |
| `custom-boundary-azure-zone` | Azure availability zone (zone) |
| `custom-boundary-azure-vnet` | Azure virtual network (network) |
| `custom-boundary-azure-subnet` | Azure subnet (subnet-private) |
| `custom-boundary-azure-public-subnet` | Azure public subnet (subnet-public) |
| `custom-boundary-azure-aks` | Azure Kubernetes Service cluster (cluster) |

### Kubernetes

| Id | Name |
|---|---|
| `custom-boundary-kubernetes-cluster` | Kubernetes cluster (cluster) |
| `custom-boundary-kubernetes-namespace` | Kubernetes namespace (namespace) |
| `custom-boundary-kubernetes-node-pool` | Kubernetes node pool (node-pool) |
| `custom-boundary-kubernetes-workload` | Kubernetes workload (group) |
