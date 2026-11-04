# Logos collection

A small, deliberate subset of brand artwork imported from
[thesvg](https://github.com/glincker/thesvg) (`public/icons`, indexed by
`src/data/icons.json`; pinned commit in `catalog.json` → `source`). Only the
slugs the editor references ship here:

| Slug | Used for |
|---|---|
| `aws`, `microsoft`, `microsoft-azure`, `cloudflare` | theme marks and brand lockups (`logos:aws#mono`, `logos:microsoft-azure#default`, ...) |
| `openstack`, `ovh`, `vultr`, `akamai`, `vmware`, `proxmox` | theme marks for the OpenStack, OVHcloud, Vultr, Akamai Cloud, VMware vSphere, and Proxmox VE libraries |
| `equinix-metal` | the theme mark for the Equinix library: thesvg files Equinix's red "E" symbol under its retired Metal product only, so the slug keeps that name |
| `ibm` | the IBM brand component (`infragram.nodes.logos.software.IBM`); the IBM Cloud theme draws its own mark |
| `kubernetes` | the mark on the Kubernetes cluster frame and the managed-cluster frames that wear it (GKE, OKE, IBM, VKE, LKE) |
| `cloudflare-workers`, `cloudflare-pages`, `workersai-cloudflare` | the Cloudflare library's product components |
| `nginx` | the brand-logo example in the node-class contract tests |

Cloud *service* icons never come from here; they ship from the
checksum-verified official vendor packs under `../vendors/`.

## Layout

```text
logos/
├── catalog.json          # generated, then pruned to the slugs above; do not hand-edit entries
├── families.json         # curated grouping overlay (never regenerated)
└── <slug>/               # one folder per brand
    └── color.svg | default.svg | mono.svg | mono-lobe.svg | icon.svg | wordmark.svg
```

## Regenerating

`python scripts/importers/brand-icons.py --source-root scripts/cloud-diagram-sources`
rebuilds the *complete* thesvg set (thousands of slugs). After running it,
prune back to the referenced slugs so the catalog counts, `families.json`,
node classes (`infragram gen:nodes`), and the icon index
(`infragram build:index`) stay consistent. Adding a slug is a deliberate
decision recorded in `THIRD_PARTY_LICENSES.md`.

## Licensing — check `license_status` before use

Every entry records its upstream license verbatim plus a coarse
classification: `permissive` (CC0 / MIT / Apache / BSD), `attribution`
(CC-BY), `copyleft`, `no-derivatives` (never recolor or reshape),
`non-commercial`, or `restricted-review`. All 17 retained entries are
`permissive`. Brand marks remain trademarks of their respective owners;
bundled use is for documentation and illustrative diagrams only.
