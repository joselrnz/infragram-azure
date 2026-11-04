# ADR 0005: Bare glyphs follow the deck

**Status**: accepted, 2026-09-05

## Context

A component draws one of two ways. A **card** is a titled box with the glyph
in a lane beside the name and subtitle. An **icon** is the bare glyph with
its caption beneath, the way the vendors' own reference architectures are
drawn. The project picks a look (`presentation.display`) and a node may
override it (`editor_display_mode`).

Between those two sat a single default -- everything was a card unless told
otherwise -- and it was wrong for a whole class of artwork. The AWS deck
draws a NAT gateway, an internet gateway or a VPC endpoint as a line glyph
and places it bare inside its subnet; boxed in a card it reads as a service
it is not. The same is true of the neutral vocabulary around a system --
users, clients, devices, the internet, sites, generic servers -- in every
library: the AWS general icons, Azure's General folder, IBM's actors, OCI's
customer sites, the Kubernetes user, the on-premises hardware and the shared
line-art primitives. A coloured service tile, a brand logo or a Kubernetes
object, by contrast, reads well in a card, which carries the name and the
subtitle legibly.

Saying it per node does not scale and drifts: a template author forgets,
the sidebar drops a card, an export disagrees with the editor.

## Decision

The default follows the artwork, and it is written down once.

- `skills/infragram-azure/assets/catalog/display-defaults.json` holds ordered
  rules, each naming a provider (or `*`) and a match on the component's id
  or on the icon's own tier and category as the vendor deck files it. The
  first matching rule wins; anything unmatched draws as the document's
  default, which was `card` when this was decided and is `icon` since
  ADR 0007.
- `infragram.catalog.display.default_display(provider, id, tier=, category=)`
  is the only reader of that file.
- Every place a node's look is decided goes through it: `display_of()` for
  the scene (so the editor state, every export and the static fallback
  agree), the sidebar payload (`defaultDisplay` per component) so a
  component dropped from the sidebar lands the way the document would draw
  it, and the runtime's "show as cards" switch, which leaves bare-by-default
  glyphs bare.
- A node's own `editor_display_mode` still wins over all of it, and the
  editor's per-node Card / Icon control still boxes or unboxes any one node.

### What draws bare

| Library | Bare by default | Keeps the card |
|---|---|---|
| every library | resource-tier glyphs (`tier: resource`) | service tiles |
| AWS | 419 service resources + 47 general icons | 305 services |
| Azure | the General folder (96), Users, Client Apps | every service |
| Google Cloud | the generic cloud glyph | every product |
| IBM | user, browser, device, internet | every service |
| Oracle Cloud | customer datacenter, customer premises | every service |
| Kubernetes | user | every object |
| on-premises | `generic-*`, `client-*`, the house primitives | vendor logos |
| shared primitives | line art: servers, switches, users, devices, sensors, files | `brand-*`, `data-*`, `language-*`, `statistics-*`, `kubernetes-*`, `custom-*`, Teams, Slack, Microsoft 365 |

The criteria behind the table: a glyph draws bare when it is line art meant
to sit inside a container, or when it stands for an actor or endpoint around
the system. It keeps the card when it is a coloured tile or a logo, because
a logo alone beside a caption reads as clutter and the card carries the name.

## Consequences

- Templates re-render with the new defaults; the golden pictures are
  relocked and every template passes the picture checks in both looks.
- Adding a library means deciding its rules in the same file, reviewed
  against the vendor's own drawings, rather than per template.
- A saved page pins each node's resolved mode, so documents drawn before
  this decision keep the look they were saved with until an author changes
  a node.
