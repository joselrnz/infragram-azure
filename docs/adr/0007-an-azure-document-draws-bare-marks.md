# ADR 0007: An Azure document draws bare marks

**Status**: accepted, 2026-09-18

## Context

ADR 0005 decided which *components* draw bare regardless of the document:
resource-tier glyphs, the decks' general folders, actors and endpoints, the
shared line art. Everything it did not name fell through to the document's
own default, and that default was the card -- a titled box with the glyph in
a lane beside the name and subtitle.

So an Azure picture drawn with no instruction came out as a grid of boxes
with small icons in them. Microsoft does not draw Azure that way. Every
reference architecture Microsoft publishes places the deck's mark at full
size with the name beneath it, inside the boundary it belongs to, and the
mark is what a reader recognises from across a room. Put beside the two
tools an author would otherwise reach for -- `diagrams`, which is Graphviz
plus the Azure deck, and a Mermaid flowchart, which has no vendor artwork at
all -- the one thing our picture had that neither could match was the
artwork, and the card was the thing making it small.

The card is still right for plenty of documents: an inventory, a dense
estate, anything where the subtitle carries as much as the name. It is a
choice, not a fallback.

## Decision

A document that says nothing about how its components draw draws them as
bare marks with a caption. `Presentation.display` defaults to `icon`, and so
do `Diagram(...)` and `compose.to_project(...)`, which are the two ways a
document is written by hand.

- Nothing else in the chain moves. A node's `editor_display_mode` still
  wins, `display-defaults.json` still decides per component (ADR 0005), and
  `--display card|icon|both` still overrides a whole export.
- A document that wants boxes writes `display="card"` and keeps them.
- The four shipped Azure templates take the default rather than pinning a
  look, so they are drawn the way the house draws Azure.

## Consequences

- An Azure picture is taller and narrower than it was: the same diagram runs
  about a quarter taller, because a caption sits under the mark instead of
  beside it. It is still far more compact than the alternatives -- the
  bake-off diagram is 1458x780 against `diagrams`' 1625x2230.
- Documents saved before this decision keep the look they were saved with.
  A saved page pins each node's resolved mode, and a template that pins
  `display` keeps that pin.
- Tests that were written about card geometry now say `display="card"`
  rather than relying on the default, which is what they meant all along.
