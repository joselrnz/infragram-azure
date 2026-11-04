# icons/

Icon libraries: provenance-tracked artwork, never hand-edited. Icons exist
exactly once — themes and the index reference them, nothing copies them.
Collections are named by **artwork kind**, and each has exactly one owner
(one importer), so regeneration can never destroy curated work.

```text
icons/
├── index.json          GENERATED lookup over everything (id, family, tags, path, rights)
├── vendors/            per-vendor icon packs — drawn as nodes INSIDE diagrams
│   ├── sources.json    official pack manifest — add vendors HERE, not in code
│   ├── azure/          catalog.json + <category>/<id>.svg (Azure Public Service Icons V24)
│   └── kubernetes/     catalog.json + <category>/<id>.svg (kubernetes/community, Apache-2.0)
└── logos/              company identity artwork the editor references — 5 slugs
    ├── catalog.json    pruned to the referenced slugs, per-variant sha256 (see logos/README.md)
    ├── families.json   curated grouping overlay (never regenerated)
    └── <slug>/<variant>.svg
```

Which collection does something belong to? Three questions:
node drawn *inside* a diagram → `vendors/`; a company's identity as published
→ `logos/`; the badge a theme stamps on examples → `../themes/marks/`.

## Regeneration (one owner per collection)

- `vendors/*` — `python scripts/importers/official-icons.py [vendor ...]`,
  from checksum-verified official downloads in the separate
  `cloud-diagram-sources` vault.

A catalog's `source` block describes where the collection as a whole came
from. An individual icon that came from somewhere else overrides it with its
own `source_url`, `source_release`, and `terms_url`. Read an icon's own
fields first, then fall back to the collection block; never assume the
collection terms cover every file.
- `logos/*` — `python scripts/importers/brand-icons.py` wipes and rebuilds
  every slug folder from thesvg; afterwards prune back to the referenced
  slugs listed in `logos/README.md`. `families.json` is the one file the
  importer must never touch.
- `index.json` — `python scripts/build/provider-index.py`.

## families.json

Groups related logo slugs (microsoft-*, ...) without moving folders, so
grouping survives regeneration. `official.vendors` names the pack that
supersedes those logos in lookup (tier 1 beats tier 2); `official.url`
records where to download the official pack later.

## Reuse rule

The license covering repository code is not necessarily the license covering
the icons. Provider names, product marks, logos, and architecture artwork
often retain separate terms even when distributed under MIT or Apache
wrappers. Check `license_status` in the index before altering any artwork;
Microsoft's terms permit use in diagrams but forbid modification.
