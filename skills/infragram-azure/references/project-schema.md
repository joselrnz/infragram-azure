# Project document (`.infragram.json`, schema version 3)

A project stores *intent*: which libraries are installed, what the elements
are, how they contain each other, what connects to what, and how the result
should be presented. It does not store rendered coordinates unless they were
authored. The same document feeds the editor HTML, the SVG, and the PNG.

Unknown keys are rejected everywhere (`extra: forbid`), so a typo fails
loudly instead of being ignored.

The same rules ship as a JSON Schema,
[`../assets/schema/infragram-project.schema.json`](../assets/schema/infragram-project.schema.json)
(`infragram schema` prints it, `infragram schema --path` says where it is),
generated from the model the package validates with. An editor pointed at it
completes keys and flags a typo as the document is written: in VS Code, a
`"$schema"` key naming the file, or the `json.schemas` setting. A document may
carry `$schema`; it is accepted and not kept. Version 1 and 2 documents
validate as older versions.

## Top level

| Field | Type | Rules |
|---|---|---|
| `schema_version` | `3` | Version 1 and 2 documents are migrated on load (below); saving writes version 3. |
| `kind` | `single-cloud` \| `multicloud` \| `platform` \| `hybrid` | `single-cloud` needs exactly one provider; `multicloud` needs at least two. Default `single-cloud`. |
| `slug` | slug | Lowercase letters, digits, hyphens. Names the exported files. |
| `title`, `description` | non-empty text | Diagram title and accessible description. |
| `template_brief` | text | Optional note for people starting from this template. |
| `starter_preset` | slug | Optional starter stack the editor offers to insert (see frames.md). |
| `providers` | `[{ "id": slug, "enabled": bool }]` | Libraries installed in the document, not those visible on the canvas. Ids must be registered libraries; at least one enabled; no duplicates. |
| `default_library` | `"all"` or an enabled provider id | The library filter the editor opens with. |
| `layers` | `[Layer]` | Visibility and z-order groups, independent from containment. |
| `icon_collection` | collection name | Optional. The icon collection the static picture draws the primary library's artwork from; the primary library's own by default. |
| `presentation` | object | Size, look, detail, audience, headings, legend, and where the drawing stands. |
| `topology` | element | The root element; everything else is nested under it. |

### Layer

```json
{ "id": "provider:azure", "name": "Azure", "kind": "provider", "provider": "azure",
  "visible": true, "locked": false, "order": 10 }
```

`kind` is `provider`, `platform`, `on-prem`, or `logical`; `id` is a slug or
a one-level qualified slug (`provider:azure`, `phase:migration-2`); `provider`,
when set, must be installed in the document. A layer hides or locks its
members without touching the graph; order controls z-order groups only.

### Presentation

| Field | Values |
|---|---|
| `size` | `doc-inline` (default), `doc-wide`, `slide-16x9`, `slide-4x3`, `social-og`, `social-square`, `print-a4-landscape`, `print-letter-landscape`, `fit` |
| `detail` | `faithful`, `balanced` (default), `simplified` |
| `audience` | `engineer`, `mixed` (default), `executive` |
| `display` | `icon` (default: bare marks with captions) or `card` (titled boxes); a node's own `attributes.editor_display_mode` wins |
| `crossings` | `plain` (default) or `bridge`: a small semicircular hop at safe crossings between separate wires; saved and used by HTML, SVG, and PNG |
| `frame_lines` | `thin` (default: each frame kind's own border width), `medium` (1.75 times it) or `thick` (2.5 times it); every frame alike, in HTML, SVG, PNG and draw.io |
| `eyebrow`, `heading` | short text above and as the diagram title (`eyebrow` defaults to "Architecture") |
| `legend` | list of `[label, connection kind]` pairs |
| `status`, `notes`, `drawn` | optional document metadata describing the drawing's status, warnings, and date; never printed in the editor header or diagrams; put explanations in companion documentation |

## Elements

Every node, frame, and site is one element. Containment is the `children`
list; connections are the other axis.

```json
{
  "id": "api-management",
  "name": "API Management",
  "type": "gateway",
  "role": "entry",
  "component": { "provider": "azure", "service_id": "api-management-services" },
  "layer_id": "provider:azure",
  "attributes": { "detail": "Standard v2 · East US" },
  "children": [],
  "connections": [
    { "target": "orders-fn", "kind": "solid", "label": "invoke" }
  ]
}
```

| Field | Rules |
|---|---|
| `id` | Unique across the whole document. Connection targets refer to it. |
| `name` | Display name. |
| `type` | What the thing *is* - `service`, `gateway`, `database`, `client`, `group`, `site`, `pod`, `node-pool`, and so on. Free text; keep it descriptive. |
| `role` | What part it plays in a pattern (`hub`, `spoke`, `entry`); optional. |
| `component` | Provider-qualified identity: `provider` and `service_id` are slugs; `icon_ref` defaults to `provider:service_id` and, if given, must start with `provider:`. The provider must be installed in the document, except the shared library `infragram`. Both pictures draw the component's artwork -- the vendor pack, or the same library catalog the editor reads for a component the pack lacks; an `attributes.icon` names a different mark and wins. Omit `component` for an element with no artwork. |
| `layer_id` | Must name a declared layer. An element belongs to at most one layer. |
| `attributes` | Free dictionary. `detail` is the secondary text line the renderer draws. `table` (`{"columns": [...], "rows": [[...]]}`) opens in the card's popup; `sizing` (`size`, `tier`, `region`, `os`, `count`, `hours`, ...) is what an export prices an element as, and `price` is what it wrote ([export.md](export.md), Prices and links). None of them is drawn. |
| `children` | Contained elements. A frame's members live here. |
| `connections` | The wires that leave this element; see below. |
| `badges` | A frame's corner badges (a subnet's NSG, its route table): each `{"icon", "collection", "label", "side": "corner"}`, drawn on the frame's top-right corner by every renderer. Written only when there are some; older documents' `"badges": []` still loads. A mark on any other side, or with no side, is refused: the editor never drew those. |

### Connections

```json
{ "target": "orders-fn", "kind": "solid", "label": "invoke", "direction": "forward",
  "waypoints": [{ "x": 480, "y": 220 }],
  "label_placement": { "mode": "auto", "dx": 0, "dy": 0 } }
```

| Key | Rules |
|---|---|
| `target` | The id of the element the wire arrives at. Every target must exist. |
| `kind` | `solid` (default), `dashed` or `dotted` in every library; `vpn`, `vif` and `local` where a theme defines them (the shipped templates use them). The theme's link styles decide how a kind is drawn. |
| `label` | Text on the wire. |
| `direction` | `forward` (default: an arrowhead at the target), `both` (heads at both ends) or `none` (a plain association line). |
| `waypoints` | The corners a wire runs through, in editor canvas units like `editor_x`. Both renderers turn at right angles through them when the document carries the layout they were pinned on -- a document the editor saved; when it was never arranged by hand, or its saved layout no longer describes the looks being drawn, the wire is routed around whatever is in the way. |
| `label_placement` | `auto` (default) places the label; `manual` offsets it by `dx`, `dy`. |
| `step` | Where the wire comes in a flow told in order, 1 to 99: a numbered circle at the start of its caption, and a line of the step list beside the drawing. Needs a `label`. |
| `step_text` | What the step list says of the step; its `label` when absent. |
| `step_flow` | The second flow a step belongs to, by name: marked the theme's second way (`step_second`) and listed under the name. Absent is the main flow; one named flow a drawing. |

A wire's colour, width, arrowhead, sides and label type live on its source
element, in `attributes.editor_edge_styles[<target id>]`:

```json
{ "stroke": "#c7254e", "width": 1.8, "arrow": "triangle",
  "source_port": "right", "target_port": "left",
  "textStyle": { "fontFamily": "Inter", "fontSize": 9, "fontWeight": 400, "textColor": "#16191f", "opacity": 100 } }
```

`arrow` is `triangle`, `open`, `circle` or `diamond`. `source_port` and
`target_port` (`top`, `right`, `bottom`, `left`) pin the side a wire leaves
and arrives at, as the inspector Text tab's *Leaves from* and *Arrives at*
do; left out, both renderers anchor the wire where the two components stand.
The Text tab edits all of it when a connector is selected.

## Rendered 3D items

An element rendered by spec (`infragram.nodes.iso.Iso`) has `component`
`infragram:custom-3d` and carries its artwork in `attributes`:

| Attribute | Content |
|---|---|
| `iso` | The spec the renderer built from: `recipe`, `args`, `kwargs`, `colour`, `glyph`, `id`. |
| `iso_hash` | The spec hash the render is cached under. |
| `iso_artwork` | The rendered SVG (a 192 px PNG inside an SVG wrapper). |
| `iso_ink` | Its ink measurement -- `profile` (bounding-box insets) and `edges` (the 33-line edge code per side) -- so links seat on the render. |

The renderers draw `iso_artwork` and register `iso_ink` when they meet the
element; nothing needs the cache to open the document. The editor keeps a
node's own render instead of the palette's placeholder for `custom-3d`.

## Frames

A frame is an element whose `component` points at the shared library:

```json
{ "id": "prod-vnet", "name": "Production VNet", "type": "group",
  "component": { "provider": "infragram", "service_id": "custom-boundary-azure-vnet" },
  "children": [ ... ] }
```

The available frame ids and each library's containment rules are in
[frames.md](frames.md). Use Azure's own frames (`custom-boundary-azure-vnet`,
`custom-boundary-azure-subnet`, `custom-boundary-azure-resource-group`)
rather than the generic ones when the frame is Azure's.

## Shared library

`infragram` is always available and never needs to appear in `providers`:

- **Frames** - `custom-boundary-*` (see frames.md).
- **Custom elements** - `custom-annotation`, `custom-label`,
  `custom-resource`, `custom-shape`, `custom-3d` (a rendered 3D item, above),
  and `custom-section`, a plain frame.
- **Neutral primitives** - clients and people (`browser-client`,
  `mobile-client`, `public-user`, `public-users`, `administrator`), generic
  infrastructure (`physical-server`, `virtual-machine`, `generic-container`,
  `generic-database`, `generic-cache`, `object-storage`, `message-queue`,
  `generic-load-balancer`, `network-gateway`, `firewall`, `vpn-tunnel`,
  `dns-service`, `public-internet`, `cdn-edge`), Kubernetes primitives
  (`kubernetes-pod`, `kubernetes-node`, `kubernetes-service`,
  `kubernetes-deployment`, `kubernetes-ingress`, `persistent-volume`), and
  common products (`brand-docker`, `brand-terraform`, `brand-postgres`,
  `brand-redis`, `brand-nginx`, `brand-github`, `brand-keycloak`, ...). Every
  id, with the class that draws it, is in
  [shared-components.md](shared-components.md).

## Validation

Loading a document checks, in this order: provider ids registered and not
duplicated; at least one enabled; `default_library` valid; `kind` versus
provider count; layer ids unique and layer providers installed; every
`layer_id` declared; every component provider installed (or `infragram`);
every connection target present; every element id unique. The launcher's
`check` command (the skill's `scripts/project_check.py`) performs the same
checks without pydantic, and also inspects exported pages and pictures.

## Migration from versions 1 and 2

A version-2 document is a version-3 document that does not say where the
drawing stands: only the number changes. A version-1 document carries one
top-level `provider`; on load it becomes a `single-cloud` document
(`platform` when the provider is a platform library -- Kubernetes or
Databricks) with that provider installed and one layer for
it, and every element whose legacy `attributes.icon` names a service gains a
`component` of that provider and joins the layer. The file on disk is never
modified; saving writes version 3.

## A complete minimal example

```json
{
  "schema_version": 3,
  "kind": "single-cloud",
  "slug": "orders-api",
  "title": "Orders API",
  "description": "API Management in front of a function app that stores orders in a storage account.",
  "providers": [{ "id": "azure", "enabled": true }],
  "default_library": "azure",
  "layers": [{ "id": "provider:azure", "name": "Azure", "kind": "provider", "provider": "azure", "order": 0 }],
  "presentation": { "size": "doc-inline", "eyebrow": "Architecture", "heading": "Orders API" },
  "topology": {
    "id": "estate", "name": "Orders", "type": "estate",
    "children": [
      { "id": "customers", "name": "Customers", "type": "client",
        "component": { "provider": "infragram", "service_id": "public-users" },
        "connections": [{ "target": "api", "kind": "solid", "label": "HTTPS" }] },
      { "id": "region", "name": "East US", "type": "group",
        "component": { "provider": "infragram", "service_id": "custom-boundary-azure-region" },
        "layer_id": "provider:azure",
        "children": [
          { "id": "api", "name": "API Management", "type": "gateway",
            "component": { "provider": "azure", "service_id": "api-management-services" }, "layer_id": "provider:azure",
            "connections": [{ "target": "orders-fn", "kind": "solid", "label": "invoke" }] },
          { "id": "orders-fn", "name": "Orders function", "type": "service",
            "component": { "provider": "azure", "service_id": "function-apps" }, "layer_id": "provider:azure",
            "connections": [{ "target": "orders-storage", "kind": "dashed", "label": "put blob" }] },
          { "id": "orders-storage", "name": "Orders storage", "type": "storage",
            "component": { "provider": "azure", "service_id": "storage-accounts" }, "layer_id": "provider:azure" }
        ] }
    ]
  }
}
```
