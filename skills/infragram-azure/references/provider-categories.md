# Cloud provider categories

Use this reference when building the provider palette, search, project
template, or cloud export flow. Provider-native icon categories are source
metadata; they never define the user-facing sidebar directly.

## Canonical order

The machine-readable source of truth is
[`../assets/catalog/categories.json`](../assets/catalog/categories.json).
Every provider uses these IDs and this order:

1. Custom
2. AI & Machine Learning
3. Analytics
4. Compute
5. Containers
6. Databases
7. DevOps
8. Hybrid & MultiCloud
9. Identity
10. Integration
11. Internet of Things
12. Energy & Power
13. Industrial & OT
14. Facilities & Sites
15. Governance
16. Mobile
17. Networking
18. Power Platform
19. Security
20. Storage
21. Web

`Custom` is always visible. Other rows are visible when populated; a catalog
browser may expose `showEmptyCategories` to render all twenty-one rows.

Energy & Power, Industrial & OT and Facilities & Sites are filled mainly by
the on-premises 3D set: power generation, transmission and storage; factory,
process and test equipment; buildings, rooms, HVAC, fire, physical plant,
vehicles and workplace gear. A cloud library rarely populates them, and a
row that is empty stays hidden.

## Normalization contract

Provider mappings live in
[`../assets/catalog/provider-category-map.json`](../assets/catalog/provider-category-map.json).
Apply a service override before its provider-native category mapping. A null
mapping means that the native category is too broad and requires a reviewed
service-level override. Unknown values are errors, never silent `Custom`
fallbacks.

The same normalized category ID must be written to editor state, reusable
templates, final HTML metadata, and downstream SVG/PNG exports. Do not
reclassify categories inside a renderer.

Every shipped vendor icon resolves to a category. Where a pack's native
folders are too broad to map (Azure `other` and `general`), the map carries a reviewed `service_overrides`
entry per icon. Generic drawing glyphs that a pack ships alongside its
services (arrows, folders, globes, power symbols) are deliberately mapped to
`custom`; the inventory counts what sits there (30, all Azure), so a new icon that arrives without a mapping changes that count and
fails the `verify:inventory` gate until someone maps it or records it.

## Search aliases

Vendor packs use their publishers' names ("Virtual Networks", "cm",
"Azure Cosmos DB"); architects type "vnet", "configmap", "cosmos".
[`../assets/catalog/aliases.json`](../assets/catalog/aliases.json) layers
curated aliases over the imported catalogs per provider and service id. The
loader merges them into each component's `aliases`, so the sidebar search,
`CompositeCatalog.search`, and the generated node-class docs all see them.
Curated entries cover the well-known Azure services, every Kubernetes
resource abbreviation, and the
acronyms of multi-word service names. Re-importing a vendor pack never
touches the overlay; an alias that names a service the pack no longer ships
fails the unit tests.

## Provider palette behavior

- Provider identity changes the header mark, title, theme, and available
  services—not the category contract.
- Search matches service names, aliases, native category names, canonical
  labels, and documentation metadata.
- Empty conditional categories stay hidden by default.
- Category glyphs are provider-neutral interface artwork. Provider service
  icons remain unmodified and retain their provenance metadata.
