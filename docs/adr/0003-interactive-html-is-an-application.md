# ADR 0003 - The exported HTML is an application; its runtime is reviewed as code

**Status:** accepted (0.1.0)

## Context

The editorial skill this project was carved from ships static, script-free
HTML by policy, with one pinned motion controller verified by hash. That
posture is right for a diagram someone embeds in a post. It is wrong for an
editor: the exported page carries a several-thousand-line runtime that owns
drag, connect, frames, layers, arrange, zoom, undo, and downloads. Pretending
that is "a diagram with a controller" would either block the product or
hollow out the rule.

## Decision

The exported HTML is an application. Its runtime lives in the repository as
source (`src/infragram/editor/runtime/`, ordered modules concatenated by
`editor/bundle.py`), is reviewed and tested like any other code (browser
suite in Chromium, export parity checks), and is embedded verbatim at render
time. The constraints that remain
are about the artifact's *behavior*: it works offline from `file://`, loads no
remote scripts, keeps state only in the page and browser-local storage, and
the only remote resource it may load is a web font. The shipped
`project_check.py` verifies those properties on any exported page.

## Consequences

- No hash-pinned controller; a runtime change is a code change with tests.
- Static, diagram-only artifacts are the SVG and PNG, not the HTML.
- Third-party libraries in the runtime would need their own review and an
  ADR; today there are none.
