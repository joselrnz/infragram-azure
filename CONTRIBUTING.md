# Contributing to Infragram Azure

This document covers setup, the validation gates, and the
conventions that keep the editor, its libraries, and its exports consistent.

## What this project is

An offline infrastructure diagram editor and export pipeline,
the Azure, Kubernetes and Databricks edition of Infragram Architect, shipped as an agent
skill (`skills/infragram-azure/`) with a Python package and CLI
(`src/infragram/`) that renders one versioned `.infragram.json` project into
editor HTML, SVG, and PNG. Read [`docs/architecture/scope.md`](docs/architecture/scope.md)
before proposing a feature: the Azure and Kubernetes libraries and the shared
primitives are in scope; other vendors' libraries belong to the full product,
and editorial diagrams and L2/L3 network engineering to neither.

## Repository layout

```text
README.md
pyproject.toml
src/infragram/
  __main__.py
  cli/
  discovery/
  editor/
  exports/
skills/infragram-azure/
  SKILL.md
  references/
  assets/
skills/<command>/      the user's commands: compose, export-project,
                       export-azure, import, discover, check, check-terraform
scripts/
tests/
```

Azure, Kubernetes and Databricks remain this edition's libraries. The shared
editor, Terraform import/export, costs, diagram review and MCP workflows are
also in scope; see the current scope document for their limits.

## Setup

```bash
git clone <this repository> infragram-azure
cd infragram-azure
pip install -e ".[test]"
playwright install chromium
```

Python 3.11 or newer. Windows contributors: `core.autocrlf` is `false` on
purpose, and the tree carries mixed line endings; write each file with the
ending its committed copy has. Icon catalogs pin SHA-256 digests per file,
and `.gitattributes` keeps SVG and PNG byte-exact for that reason.

## Validation gates

Run everything CI runs:

```bash
infragram verify:all
python -m pytest tests/unit tests/skill tests/integration
infragram verify:browser
for f in skills/infragram-azure/assets/templates/cloud/*.infragram.json; do infragram verify:render "$f" --passes 3 --display both; done
```

`verify:all` is the browser-free gate list CI runs, in CI's order. The
browser suite renders the exported editor in Chromium and exercises drag,
connect, frames, layers, zoom, the display toggle, tooltips, captions and the
downloads. `verify:render` renders every template three separate times in
both looks, requires the passes to be byte-identical, and runs the picture
checks; `.forgejo/workflows/ci.yml` runs all of it on every push, and on
GitHub `.github/workflows/ci.yml` runs the quick gates and the inventory check.

| Gate | Command | Guards |
|---|---|---|
| naming | `infragram verify:naming` | no trace of the previous product name or of client projects, and no machine-specific paths, in content or file names |
| docs sync | `infragram verify:docs` | SKILL.md description names every library and format; README tree, reference links, provider routing |
| package | `infragram verify:package <base-ref>` | synchronized manifest versions, marketplace shape |
| skill | `infragram test:skill`, `test:skill-sealed`, `test:skill-runtime` | layout, stdlib-only shipped scripts, scripts run from an installed copy |
| exports | `infragram test:exports`, `test:categories` | project schema, migration, export contracts, category registry |
| libraries | `infragram test:providers`, `test:catalog` | icon provenance, hashes, SVG safety, theme manifests, and the licence basis of every icon (nothing `vendor-unverified` ships) |
| renderer | `infragram test:builder`, `test:nodes`, `gen:nodes --check` | placement invariants, generated node classes match catalogs |
| ink profiles | `infragram gen:ink --check` | every shipped icon has a current measurement of where its ink starts, so anchors land on the mark |
| pictures | `infragram verify:pictures` | every shipped template still draws its golden picture in both looks (`tests/golden/pictures.lock.json`) and passes the picture checks; `--update` accepts an intended change, and the lock's diff is the review of what moved |
| picture checks | `infragram check <slug>.svg`, `--verify` on exports | wires orthogonal, none through text, glyphs, titles or unrelated cards; captions clear; everything in the viewBox; connections drawn once with declared arrowheads and line kind; every component real |
| render | `infragram verify:render <page> --passes 3 --display both` | three Chromium passes byte-identical for cards and icons, then the picture checks |
| browser | `infragram verify:browser` | the Chromium editor suite |

If a gate fails, fix the cause; never weaken the gate to make a change pass
without an ADR explaining why the rule changed. A picture that changed on
purpose is accepted with `infragram verify:pictures --update`, committed
together with the change that moved it, so the reviewer sees which pictures
it touched.

## Adding a library

Another vendor's library belongs to the full Infragram Architect product,
not to this edition. The steps are recorded here because they are what keep
the Azure edition's three libraries honest when their artwork is refreshed.

1. Import reviewed artwork with a script under `scripts/importers/`; every
   file gets source, release, terms URL, and SHA-256 in the pack's `catalog.json`.
   Record the license in `THIRD_PARTY_LICENSES.md`.
2. Register the provider in `skills/infragram-azure/assets/catalog/providers.json`
   (kind, coverage, terms, attribution) and its category mapping in
   `provider-category-map.json`.
3. Add the theme manifest under `assets/themes/`, list it in
   `themes/catalog.json`, and give it a mark (theme-owned `marks/<slug>.svg`
   or a library reference such as `logos:<slug>#mono`).
4. Add its frames and starter stack, and a reference under
   `skills/infragram-azure/references/providers/<slug>.md` linked from
   `provider-themes.md`.
5. Regenerate node classes, the icon index, and the ink profiles that tell
   a wire where each new icon's artwork begins: `infragram gen:nodes`,
   `infragram build:index`, `infragram gen:ink`.

## Conventions

- One project document and one graph state are the authority for every
  export. Never add a format-specific layout.
- Provider identity is stored per component, never inferred from the active
  library filter.
- The shell is provider-neutral: library-specific knowledge belongs in data
  (catalogs, themes, frame specs), not in the `editor/` package or the runtime.
- Commit messages: imperative subject under 72 characters, a body that says
  why. Bump the plugin version with `infragram bump [major|minor|patch]` in
  the same change that ships user-visible behavior.
- Settled decisions are short ADRs in [`docs/adr/`](docs/adr/). Read them
  before relitigating one; add one when you settle a new policy.
