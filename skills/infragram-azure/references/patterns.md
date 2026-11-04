# Patterns and blueprints

[compose.md](compose.md) is how a diagram is written: frames as `with`
blocks, arrows for wires, no coordinates. Patterns remove repetition inside
that form, and a blueprint is the low-level assembly for generators and
batch exports. Both live in `infragram.patterns` and build on the same
generated classes, so nothing here names an SVG or a provider id by hand.

A pattern is used inside a `with` block by attaching it to the open frame.
Its elements nest once, under that frame, and its parts are wired like any
node:

```python
from infragram.author import Diagram, Edge
from infragram.nodes.azure import compute, databases
from infragram.nodes.frames import azure as az
from infragram.patterns import Pattern


class Tier(Pattern):
    """One subnet holding a web tier and its database."""

    def __init__(self, name: str, cidr: str) -> None:
        super().__init__(name)
        self.cidr = cidr

    def build(self):
        subnet = az.Subnet(f"{self.name} · {self.cidr}")
        self.part("web", subnet >> compute.VirtualMachine("Web servers", "scale set"))
        self.part("db", subnet >> databases.SQLDatabase("Azure SQL", "zone redundant"))
        return subnet


with Diagram("Two tiers"):
    with az.Subscription("Production"), az.ResourceGroup("rg-prod"):
        with az.VNet("vnet-prod · 10.10.0.0/16").row() as vnet:
            blue = Tier("snet-blue", "10.10.1.0/24").attach(vnet)
            green = Tier("snet-green", "10.10.2.0/24").attach(vnet)
    blue["web"] >> Edge("SQL") >> blue["db"]
    green["web"] >> Edge("SQL") >> green["db"]
```

Inside a pattern's `build()` the older `parent >> child` form still nests, as
the recipe above shows: explicit placement always wins over the `with`
block's adoption, so nothing is drawn twice.

## What a pattern is

A `Pattern` is a named piece of infrastructure that builds once, on first
use, and afterwards answers two questions:

- **Which elements did you make?** `pattern.elements` is the tuple of
  top-level frames or nodes. `pattern.attach(parent)` nests them all under a
  parent.
- **Where is the thing I need to wire?** `pattern.parts` is a read-only
  mapping of stable keys to elements, and `pattern["key"]` reads one. A
  missing key raises with the keys that exist. Keys are the pattern's
  contract; the structure inside is not.

Settings are properties with setters that validate, and they are fixed once
the pattern has built, because changing them afterwards would do nothing.
`repr(pattern)` says whether it has built and how many parts it has.

This edition ships the base classes only: an Azure or Kubernetes pattern
is written against the generated node classes, as the `Tier` above.

## Blueprint

A `Blueprint` is the assembly layer beneath `Diagram`: generators and batch
exports use it, an ordinary diagram does not need it. It holds the top-level
elements, the links, and the words the
project document needs, and it validates as it is given things, so a mistake
surfaces at the line that made it:

- `Blueprint(slug, title, description, display="card", theme="light", size="fit")`.
  `slug` must be lower-case words joined by hyphens; `title` and
  `description` must not be empty; `display` is `card` or `icon`; `theme`
  is `light`, `dark` or `darker`. All are properties with setters.
- `Blueprint.fresh(...)` resets the auto-id counters first. Ids are derived
  from names and counted per process, so a script that builds several
  diagrams starts each from zero.
- `plan.add(*elements)` places elements at the top level and returns them;
  a pattern's elements arrive the same way (`plan.add(*pattern.elements)`)
  or nest with `pattern.attach(frame)`.
  `plan.link(source, target, kind=..., label=..., direction=...)` is
  `source.to(target, ...)` that reads as part of the plan.
- `plan.to_project()` is the `CloudProject`, built once and rebuilt only
  after a change. `plan.export(dir, formats=..., display=...)` exports it
  through `compose.export`; `Blueprint.export_many([plans], dir, concurrency=2)`
  exports several at once and requires one theme across them. A file may expose
  `PROJECT = plan` or `PROJECTS = [plan_a, plan_b]` for `infragram compose`.

## Display: cards or icons

Every component draws one of two ways. `card` is the titled box with the icon
in a lane beside the text. `icon` is the bare vendor mark with its caption
beneath and no box, which is how the vendors' own reference architectures
look. The choice is `presentation.display` on the project (`display=` on
`compose.to_project` and on `Blueprint`), a node may override it with its
`editor_display_mode` attribute, and the editor's inspector has a
**Components** row that switches the whole diagram either way. The template
the page downloads remembers the choice.

Exports can draw either look from one document: `--display card|icon` forces
one, `--display both --write-looks both` writes the cards under the plain names and the icons
as `<slug>-icons.svg` and `<slug>-icons.png`. The page accepts
`?display=icon` in its address to open that way for one visit, which is what
the exporters use. `--write-looks document` keeps only the document's own
look on disk while still checking both. New project documents use schema 3.

## Tooltips

Hovering a component in the exported page shows its name, detail, component
id, frame and layer; a wire shows what it joins and its line kind; a frame
shows its kind, its parent and how many components it holds. Every node also
carries an SVG `<title>`, so the exported `.svg` explains itself in any
viewer with no script running.

## Writing a pattern

Subclass `Pattern`, implement `build()`, register parts, and keep settings as
validated properties guarded with `self._guard_unbuilt(name)`:

```python
from infragram.models.topology import TopologyElement
from infragram.nodes.azure import databases
from infragram.nodes.frames import azure as az
from infragram.patterns import Pattern, PatternError

class ReplicaSet(Pattern):
    def __init__(self, name="Database", replicas=1):
        super().__init__(name)
        self.replicas = replicas

    @property
    def replicas(self): return self._replicas
    @replicas.setter
    def replicas(self, value):
        self._guard_unbuilt("replicas")
        if not 0 <= int(value) <= 5:
            raise PatternError("0 to 5 replicas")
        self._replicas = int(value)

    def build(self) -> TopologyElement:
        group = az.Subnet(self.name, flow="row")
        primary = self.part("primary", group >> databases.SQLDatabase("Primary", "writer"))
        for n in range(self._replicas):
            replica = self.part(f"replica:{n + 1}", group >> databases.SQLDatabase(f"Replica {n + 1}", "reader"))
            primary.to(replica, kind="dashed", label="replication")
        return group
```

Determinism rules: build from names, not from randomness or the clock; do
not read the environment; register every element a caller might connect.
Two runs of the same script then produce byte-identical documents, which is
what lets a team review a diagram change as a diff.
