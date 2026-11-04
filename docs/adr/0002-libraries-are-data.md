# ADR 0002 - Libraries are data; the shell is provider-neutral

**Status:** accepted (0.1.0)

## Context

The plan that produced the multicloud editor requires that adding a provider
needs no editor-shell changes. At the time of the carve-out the shell still
special-cases a few libraries in code: Cloudflare and the on-premises extras
are Python tuples behind `if provider.id == ...` branches, frame specs and
starter stacks live in a Python module, and small presentation rules (a
display name, quick-filter membership, default-open state) are hard-coded in
the shell and runtime. Every one of those is a place where a new library
means editing the editor.

## Decision

Everything a library contributes is data: its component catalog, its theme
(colors, mark, frame styling and official frame artwork), its frames and
starter stacks, and its presentation hints. The shell reads a registry and
manifests; it never names a provider. A gate (`shell-neutrality`) will fail
the build if a provider id appears in shell or runtime code once the
remaining branches are moved into manifests.

## Consequences

- Adding a library is an importer run plus JSON, not a code change.
- The frame specs and starter stacks move out of Python into per-library
  frame manifests during the restructure phase; the loader becomes one code
  path.
- Presentation hints (`display_short`, `quick_filter`, `default_open`,
  `id_infixes`) become fields of the provider descriptor.
