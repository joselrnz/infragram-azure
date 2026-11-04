# infragram

The developer-side library and CLI. The *product* it builds and verifies is
the agent skill under [`skills/infragram-azure/`](../../skills/infragram-azure/);
the wire format keeps the short name (`.infragram.json`, the `infragram`
package, the `infragram:` shared library id).

| Module | Owns |
|---|---|
| `author/` | how a diagram is written: `edge` (the wire: label, line, sides), `diagram` (the `with` block and what it exports) |
| `compose/` | a topology tree into a project document: `errors`, `ids` (qualification against the installed catalogs), `inference` (the libraries and kind a document reads from what it holds), `document` (the assembly) |
| `exports/` | the exporter, split along its seams: `errors` (the one error), `presets` (named sizes and the style each asks for), `svg` (finishing one document: namespace, viewBox, fonts, ground), `render` (drawing without a browser), `browser` (the Playwright renderers and the content crop), `project` (writing the artifacts asked for). Every public name is re-exported from the package, so the import path never changed |
| `projects/` | the project document: `names` (the closed vocabularies), `parts` (provider selection, layer, presentation), `document` (`CloudProject` and its migrations) |
| `models/` | domain models: the topology tree (`TopologyElement`, `Connection`), providers and icons |
| `nodes/` | generated node and frame classes per library; `_base.py` (Element, Group, Frame), `_scope.py` (open `with` scopes) |
| `patterns/` | `Pattern` and `Blueprint`: repetition and the low-level assembly layer for generators |
| `builders/` | the Python renderer and its rules: `scene`, `render`, `routing`, `frame_style`, `metrics`, `arrowheads`, `ink` |
| `editor/` | the exported page: `shell` (data in, page out), `bundle` (assembles styles and runtime), `ui/` (components and views), `runtime/` (the browser side, in ordered modules), editor state, sidebar, artwork |
| `catalog/` | catalog contracts: component specs, aliases, tiers and container artwork, the frame badge record |
| `registries/` | the provider skin catalog, icon collections, class naming, plugin manifests ([README](registries/README.md)) |
| `themes/` | `Theme` and recolouring |
| `verification/` | SVG safety screen, viewBox and body extraction, presentation attributes |
| `utils/` | small cross-cutting helpers |
| `paths/` | where the skill's assets live -- found by a marker, never by counting directories |
| `cli/` | the `infragram` command: `commands/` (one module per group -- project, build, gen, importers, inventory, verify, tests, tools -- merged by its `__init__`, which refuses a name claimed twice), `scripts` (finding the file a command names, in a checkout or an installed wheel), `runner` (running one, or every gate in CI's order), `cli` (parsing and dispatch). `main` is re-exported from the package because `pyproject.toml` declares the console script as `infragram.cli:main`; the entry module is `cli` and not `main` so that importing it cannot shadow that function |

## Layering

```
author ──► compose ──► projects ──► exports ──► editor + builders
nodes  ──► models                             builders ──► catalog, registries, themes, verification
```

Dependencies point one way. `models/`, `themes/` and `verification/` import
nothing above them; `nodes/` builds on `models/`; `builders/` reads the
catalogs and themes and draws; `editor/` writes the page from a placed scene;
`exports/` runs the browser. The numbers both renderers share live in
`skills/infragram-azure/assets/catalog/render-metrics.json` and are read
through `builders/metrics.py`; every JSON asset loads through a pydantic model.

## Using it

```python
from infragram.author import Diagram, Edge
from infragram.nodes.frames import azure as az
from infragram.nodes.azure import compute

with Diagram("Azure: subscription to VM") as diagram:
    with az.Subscription("Production"), az.ResourceGroup("rg-prod"):
        with az.VNet("vnet-prod").row(), az.Subnet("snet-web"):
            web = compute.VirtualMachine("Web tier", "VM scale set")
diagram.export("dist", formats=("html", "svg", "png"))
```

```bash
PYTHONPATH=src python -m infragram compose spec.py --formats html,svg,png --output-dir dist
PYTHONPATH=src python -m infragram verify:all
```
