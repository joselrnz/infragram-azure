# Third-party licenses

The infragram code is MIT-licensed (see [`LICENSE`](LICENSE)). Required code
and artwork notices ship in [`licenses/`](licenses/), with font notices beside
the fonts and the Databricks notice beside its icons. It bundles
artwork, fonts and code from the following third-party sources, redistributed under their
respective licenses. Every provider icon pack records source, release, terms
URL, and SHA-256 per file in its `catalog.json`; read an icon's own fields
first and fall back to the collection's `source` block.

## Tabler Icons

- **License:** MIT
- **Upstream:** https://github.com/tabler/tabler-icons
- **Used in:** stroked neutral primitives in `skills/infragram-azure/references/primitive-icons.md` and `skills/infragram-azure/assets/icons.html` (compute, people, network, data, Kubernetes, action, and DevOps symbols, the datacenter and network infrastructure concepts such as mainframe, SAN fabric switch, storage array, NAS, tape library, wireless access point, WAN link, core and access switches, UPS, PDU, IDS/IPS and WAF, the operations, security, facilities and OT concepts (console server, IPAM, PKI, HSM, DLP, mail server and relay, ESB, CDC, ITSM, CMDB, PLC, SCADA, HMI, generator, cooling, fire suppression, and more), plus the stroked brand outlines for Docker, Terraform, AWS, Azure, GitHub, Windows, Slack, Microsoft Teams and Microsoft 365), and the semantic sidebar glyphs.

The MIT license is reproduced in full at https://github.com/tabler/tabler-icons/blob/main/LICENSE.

## GitHub Primer Octicons

- **License:** MIT
- **Upstream:** https://github.com/primer/octicons
- **Used in:** the Containers category glyph in the library sidebar.

The MIT license is reproduced in full at https://github.com/primer/octicons/blob/main/LICENSE.

## Simple Icons

- **License:** CC0 1.0 Universal (Public Domain Dedication)
- **Upstream:** https://github.com/simple-icons/simple-icons
- **Used in:** filled brand silhouettes in `skills/infragram-azure/references/primitive-icons.md` and `skills/infragram-azure/assets/icons.html` (DigitalOcean, Kubernetes, Google Cloud, PostgreSQL, Nginx, Gitea, Keycloak, MinIO, Apache NiFi, Apache Airflow, Trino, Apache Superset, Jupyter, Python, R, and the self-hosted platform marks listed under "Self-hosted platforms" in the same gallery: Pi-hole, AdGuard Home, WireGuard, OpenVPN, Authelia, authentik, Vaultwarden, Portainer, Rancher, Longhorn, Forgejo, Salt, Rundeck, TrueNAS, Home Assistant, Mattermost, Rocket.Chat, Matrix, Jitsi, Coder, Syncthing, Paperless-ngx, BookStack, Wiki.js, GitBook, Elasticsearch, Kibana, Logstash, OpenSearch, Icinga, Checkmk, Uptime Kuma, Netdata, Nginx Proxy Manager, QEMU, VirtualBox, Nutanix, Veeam, BorgBackup, Talend, Apache Hadoop, Apache Spark, Snowflake, Cloudera, Teradata, MicroStrategy, Qlik, SAP, and the network and hardware vendor marks Cisco, Juniper Networks, Fortinet, Palo Alto Networks, Ubiquiti, F5, SonicWall, NETGEAR, TP-Link, Huawei, Dell, Supermicro, and the enterprise platform marks Red Hat, Red Hat OpenShift, SUSE, openSUSE, Rocky Linux, AlmaLinux, FreeBSD, Fedora, Citrix, NetApp, Hitachi, Veritas, Okta, Auth0, Qualys, Fastly, Atlassian, Jira, Confluence, Bitbucket, Zoom, Asterisk, HashiCorp, Vagrant, Packer, Chef, Octopus Deploy, Sonatype, Podman, Helm, ownCloud, Seafile, openmediavault, Unraid, Synology, QNAP, Timescale, MQTT, PagerDuty, Opsgenie, Wireshark, Kali Linux, Snort, Apache CloudStack, OpenNebula, HP, Intel, Roundcube, and the second platform batch 1Password, Airbyte, Alpine Linux, AnyDesk, Apache Guacamole, Apache Parquet, Apache Pulsar, ArangoDB, Arch Linux, Arduino, Backstage, BigBlueButton, Burp Suite, Camunda, Dependabot, Dovecot, Drupal, ERPNext, ESPHome, Falco, Fluent Bit, Frigate, Gitpod, GraphQL, HubSpot, Jellyfin, KeePassXC, LangChain, Lenovo, Meilisearch, Metasploit, Milvus, n8n, NixOS, Node-RED, NVIDIA, Odoo, Ollama, OpenBSD, openHAB, OpenWrt, Parrot Security, Raspberry Pi, rclone, Renovate, Rook, RustDesk, ScyllaDB, Shopify, Snyk, SonarQube Server, strongSwan, Sumo Logic, Tailscale, Talos Linux, TeamViewer, Thunderbird, TiDB, VictoriaMetrics, VirusTotal, Vitess, WebAssembly, WooCommerce, Yubico, Zapier, Zendesk, ZeroTier, Zigbee, macOS). Each mark remains its owner's trademark; its presence is a drawing capability, not an endorsement.

The CC0 dedication is reproduced in full at https://github.com/simple-icons/simple-icons/blob/develop/LICENSE.md.

## log-z/logos

- **License:** MIT
- **Upstream:** https://github.com/log-z/logos/tree/main/website-logos
- **Used in:** filled brand silhouettes that aren't carried by Simple Icons or Tabler — currently MySQL, Redis, and StarRocks. Source SVGs are 100×100 with embedded `<style>` + class-based fills; the build script strips the style block and rewrites class refs to `currentColor` for monochrome consistency.

The MIT license is reproduced in full at https://github.com/log-z/logos/blob/main/LICENSE.

## Devicon

- **License:** MIT
- **Upstream:** https://github.com/devicons/devicon
- **Used in:** the RStudio and SPSS icons in `scripts/vendor/icons/devicon/`.

The MIT license is reproduced in full at https://github.com/devicons/devicon/blob/master/LICENSE.

## thesvg brand logos

- **License:** per entry; the 17 retained entries are all `permissive` (CC0-1.0 or MIT), recorded in `license` and `license_status` in `skills/infragram-azure/assets/icons/logos/catalog.json`
- **Upstream:** https://github.com/glincker/thesvg (pinned commit recorded in the catalog's `source` block)
- **Used in:** the Azure and Kubernetes theme marks and the neutral brand components every slug offers as a node class (`infragram.nodes.logos`, such as `logos.software.IBM` and the nginx example in the node-class tests). Only these 17 slugs ship: `aws`, `microsoft`, `microsoft-azure`, `kubernetes`, `cloudflare`, `cloudflare-workers`, `cloudflare-pages`, `workersai-cloudflare`, `ibm`, `nginx`, `openstack`, `ovh`, `vultr`, `akamai`, `vmware`, `proxmox`, `equinix-metal`.

## Official cloud architecture icon packages

- **Microsoft Azure:** reviewed service icons copied without geometric or color modification from Azure Public Service Icons V24. Source and permitted-use restrictions: https://learn.microsoft.com/en-us/azure/architecture/icons/
- **Kubernetes:** project artwork from the Kubernetes community repository (Apache-2.0); CNCF and Linux Foundation trademark policies apply to the marks.
- **Databricks:** architecture icons built from Databricks' official SVGs (https://brand.databricks.com/), vendored in `assets/icons/vendors/databricks/`. That set is Copyright (c) 2026 Eduardo Rabelo under the MIT License, whose full notice ships beside the icons as `assets/icons/vendors/databricks/LICENSE`; nothing is fetched from its repository. The license grants no trademark rights: Databricks, the Databricks logo and the product names are trademarks of Databricks, Inc., which does not sponsor or endorse the set. The theme mark (`assets/themes/marks/databricks.svg`) is the same logo redrawn in one colour.

These files are provider artwork, not relicensed under Infragram Azure's MIT license. They are bundled only for architecture-diagram and documentation use under the linked provider terms. Their per-file source path, release, terms URL, and SHA-256 digest are recorded in each pack's `catalog.json`. No vendor library in this edition is bundled without an established grant: `tests/unit/test_artwork_licensing.py` pins the count of `vendor-unverified` icons at zero. The one logo without a grant is Redpanda's, under Project logos below.

## Project logos

Two brand marks no icon library carries are taken from the project's own
repository, pinned to a commit, and kept unmodified in
`scripts/vendor/icons/official/` (the table is `OFFICIAL` in
`scripts/build/icons.py`). The gallery draws each in one colour; Redpanda's
white panda becomes a cut-out of its disc.

- **Valkey** — `static/img/Valkey-logo.svg` from
  https://github.com/valkey-io/valkey-io.github.io at commit
  `c2a4d37b33afc4cd879d29857d6c6bf3ae952f97`. BSD-3-Clause (Copyright 2024
  Linux Foundation or its affiliates); the notice ships as
  [`licenses/valkey.txt`](licenses/valkey.txt). Valkey is a trademark of the
  Linux Foundation; the licence grants no trademark rights.
- **Redpanda** — `docs/icon-redpanda.svg` from
  https://github.com/redpanda-data/redpanda at commit
  `10932ba73d4c98eeda85ee55d80f2d6a8e01901c`.
  - **Rights status:** Redpanda publishes the mark in its repository and in
    its press media kit, with no explicit redistribution terms. It is bundled
    at the maintainer's direction for architecture-diagram and documentation
    use only; it is **not** relicensed under Infragram Azure's MIT
    license, and Redpanda Data's trademark terms apply. If Redpanda objects
    or clarifies terms that exclude this use, remove it.

## One-off sourced icons

None besides the two project logos above. Five glyphs were once fetched straight from vendor pages -- Apache Hop,
Pentaho, Dagster, SAS and Stata -- and carried no established redistribution
grant. No licence-clean brand mark exists for any of the five, so each now
carries a generic Tabler glyph describing what the tool does rather than a
logo this repository had no right to ship. The components keep their names,
and the source files were deleted. `tests/unit/test_artwork_licensing.py`
fails if a glyph is sourced that way again.

## three.js

- **License:** MIT (Copyright 2010-2024 three.js authors); the notice ships as [`licenses/three.js.txt`](licenses/three.js.txt), and `RoomEnvironment.js`, adapted from Google's model-viewer, is also under the Apache License 2.0 ([`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt))
- **Upstream:** https://github.com/mrdoob/three.js (r161)
- **Used in:** `src/infragram/iso3d/lib/three.module.js` (its MIT notice kept at the top) and `src/infragram/iso3d/lib/RoomEnvironment.js` (the three.js example environment, which three.js adapted from Google's model-viewer, Apache-2.0), which render neutral infrastructure recipes in the optional offline 3D builder.

## draw.io stencil names

- **License:** Apache License 2.0 (Copyright JGraph Ltd); the text ships as [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt)
- **Upstream:** https://github.com/jgraph/drawio-mcp, `shape-search/search-index.json` at the commit `skills/infragram-azure/assets/catalog/drawio-stencils.json` records
- **Used in:** the `.drawio` export. `scripts/build/drawio-stencils.py` matches Infragram's AWS, Azure and Kubernetes components to the draw.io style strings that index lists, by exact name, and keeps the matching style strings in `drawio-stencils.json`; the export writes them so draw.io draws its own stencils. No draw.io artwork is copied: draw.io draws the stencils it names.

## Fonts

- **License:** SIL Open Font License 1.1
- **Upstream:** google/fonts, fetched as subsetted woff2 through the Google Fonts CSS API; each face's source URL and sha256 are recorded in `skills/infragram-azure/assets/fonts/catalog.json`
- **Used in:** every editor page, static page and standalone SVG, which carry the faces inline: Inter (the editor itself and every label in a diagram) and Geist Mono (the monospaced face the Text panel offers, and monospaced frame titles). The notices are the `OFL-*.txt` files beside the fonts in `skills/infragram-azure/assets/fonts/`.

## Trademarks

Brand logos remain the trademarks of their respective owners. Their inclusion in this icon set is for documentation and illustrative use only. The presence of a brand mark in this repository does not imply endorsement, sponsorship, or affiliation.
