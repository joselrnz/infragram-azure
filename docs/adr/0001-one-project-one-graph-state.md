# ADR 0001 - One project document and one graph state are the authority for every export

**Status:** accepted (0.1.0)

## Context

The editor produces four artifacts - a re-saved template, interactive HTML,
SVG, and PNG. Tools that keep a layout per format drift: the slide export
shows a node the SVG dropped, or the PNG rounds coordinates the HTML did not.
The parent project already held this invariant for its export pipeline and it
is the most valuable thing the carve-out inherits.

## Decision

The versioned `.infragram.json` document plus the editor's graph state are the
only source of truth. The exporter renders once into the editor HTML; the SVG
is extracted from that page's marked diagram element and the PNG is a
Chromium capture of that same SVG. No format may implement its own layout,
and future adapters (PDF, WebP) are output adapters over the same render.

## Consequences

- A rendering bug is fixed in the project or the renderer, never in an
  artifact.
- SVG and PNG are diagram-only by construction: they cannot contain the
  sidebar, grid, guides, or handles because those are not part of the marked
  element.
- Authored canvas coordinates, when stored, live in the project document so
  every format sees the same geometry.
