# Cloud provider theme index

Use this lightweight router for provider-branded architecture diagrams.

## Load one provider only

Identify the provider, then read exactly one linked provider reference. Open
the second file only when the diagram genuinely contains both libraries -- an
AKS platform inside an Azure landing zone, for instance.

| Provider | Theme slug | Provider-specific reference |
|---|---|---|
| Azure | `azure` | [Azure](providers/azure.md) |
| Kubernetes | `kubernetes` | [Kubernetes](providers/kubernetes.md) |
| Databricks | `databricks` | [Databricks](providers/databricks.md) |

The machine-readable provider index is
[`../assets/themes/catalog.json`](../assets/themes/catalog.json); the
library registry with kind, coverage, and terms is
[`../assets/catalog/providers.json`](../assets/catalog/providers.json).
A third theme, `generic`, belongs to no library: it is the neutral look the
core frames draw in, inside whichever project they are placed. Exported HTML,
SVG, and PNG are output, never configuration.

## Shared rules

- Apply the selected skin to the diagram itself: page, SVG paper, nodes,
  connectors, masks, legend, and text—not just surrounding application chrome.
- Preserve bundled service symbols in their reviewed product colors. Their
  palette identifies services; it does not become a generic border palette.
- Place the provider mark once, keep its proportions, make it decorative, and
  do not imply provider endorsement.
- Preserve Infragram Azure typography, restrained surfaces, orthogonal routing,
  accessibility, and the no-shadow rule.

To add or update a provider, follow
[`../assets/themes/README.md`](../assets/themes/README.md). Provider-specific
guidance belongs in its one file under `references/providers/`.

## Connection kinds

A theme may extend the connection kinds under `style.links`. Every provider
starts from the same three -- `solid`, `dotted` and `dashed`, with the dashes
every renderer reads from `render-metrics.json` -- and a theme adds or
overrides entries with `color`, `width`, `dash` and `role`:

```json
"style": {
  "links": {
    "replication": { "color": "#c7254e", "width": 1.4, "dash": "8,3,2,3" },
    "local":       { "role": "soft", "width": 1.1 }
  }
}
```

Neither shipped theme adds a kind today, so `solid`, `dashed` and `dotted`
are the kinds a document may name. The editor, the static renderer and the
shipped picture checker all read this table: a connector is dashed exactly
when its kind has a `dash` here, and the checker reports any export where the
picture disagrees with the document.

## Frame style: the `boundaries` block

Every field a theme may set for its frames. Both renderers read them through
one derivation (`builders/frame_style.py`); see *One description of a frame*
in `frames.md` for how the picture follows.

| Field | Meaning | Default |
| --- | --- | --- |
| `color` | Frame colour for every kind `colors` does not name: a theme role or hex. Every shipped theme declares it. | `""` (falls to `border_role`, faded by depth) |
| `colors` | Frame colour per kind, e.g. Azure `subscription: #ffcb12`. | `{}` |
| `fills` | Fill per kind: a role, a hex (tinted by `fill_tint`), or `none`. | `{}` (no fill) |
| `fill_tint` | Alpha applied to a declared fill. | `0.10` |
| `dashes` | Dash per kind; `null` means solid. Unlisted kinds: invented groupings `5,4`, perimeters solid. | `{}` |
| `dash` | Dash for a kind in neither table; `null` is solid. | `null` |
| `widths` | Line weight per kind. | `{}` (cloud 1.8, else 1.0) |
| `radii` | Corner radius per kind. | `{}` (square) |
| `icons` | Badge per kind, `collection:slug`. Recorded in `frame-badges.json`; a kind without one gets the generic glyph. | `{}` |
| `tab_fill` | `frame`: tab in the frame colour, paper glyph. `paper`: paper tab, glyph in the frame colour. | `frame` |
| `label_font`, `label_case`, `label_weight`, `label_tracking`, `label_size` | Caption face and setting. | `sans`, `preserve`, `500`, `0`, `10` |
| `pad` | Frame edge to its children. | `24` |
| `tab`, `label_icon`, `label_icon_gap` | Tab geometry; taken from `render-metrics.json` `frame`, not meant to be set per theme. | `20`, `16`, `5` |
