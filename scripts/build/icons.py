"""Fetch and normalize the icon set for the infragram skill.

Pulls SVGs from Tabler Icons (MIT), Simple Icons (CC0), log-z/logos (MIT),
and Devicon (MIT), normalizes them to a 24x24 viewBox using `currentColor`
so they inherit ink from context, and writes
skills/infragram-azure/references/primitive-icons.md: the gallery the
renderer reads each shared primitive's glyph from. A picture of every shared
primitive is docs/inventory/icons-shared.png (`infragram inventory --images`).

Sources are cached under scripts/vendor/icons; a glyph whose source is not
cached there is fetched, so a rebuild without the network reports it missing.

Run:    python scripts/build/icons.py
Reqs:   stdlib only (urllib, re, pathlib)

Re-run any time the manifest below changes. The generated file is
committed; users of the skill never need to run this script.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

sys.path.insert(
    0,
    str(
        next(p for p in pathlib.Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
        / "src"
    ),
)
from infragram import verification as fr_verify

REPO = next(p for p in pathlib.Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())

MD_OUT = REPO / "skills" / "infragram-azure" / "references" / "primitive-icons.md"
VENDOR_DIR = REPO / "scripts" / "vendor" / "icons"


def vendor_path(slot: str, source: str, source_id: str) -> pathlib.Path:
    """Return the local cache path for a given icon."""
    if source == "tabler":
        return VENDOR_DIR / "tabler" / f"{source_id}.svg"
    if source == "simple":
        return VENDOR_DIR / "simple" / f"{source_id}.svg"
    if source == "logz":
        return VENDOR_DIR / "logz" / f"{source_id}.svg"
    if source.startswith("devicon"):
        variant = source.split(":")[1] if ":" in source else "plain"
        return VENDOR_DIR / "devicon" / f"{source_id}-{variant}.svg"
    if source == "official":
        return VENDOR_DIR / "official" / f"{source_id}.svg"
    # "url" source — key by slot name so the cache is human-readable
    safe = re.sub(r"[^\w\-]", "_", slot)
    return VENDOR_DIR / "url" / f"{safe}.svg"


TABLER_URL = "https://raw.githubusercontent.com/tabler/tabler-icons/main/icons/outline/{name}.svg"
TABLER_URL_FALLBACK = "https://raw.githubusercontent.com/tabler/tabler-icons/main/icons/{name}.svg"
SI_URL = "https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/{slug}.svg"
SI_CDN_URL = "https://cdn.jsdelivr.net/npm/simple-icons/icons/{slug}.svg"
LOGZ_URL = "https://raw.githubusercontent.com/log-z/logos/main/website-logos/{name}.svg"
DEVICON_URL = (
    "https://raw.githubusercontent.com/devicons/devicon/master/icons/{name}/{name}-{variant}.svg"
)
# For "url" source: source_id is the full URL; blurb should note license

#: Logos taken from the project's own published files, where no icon library
#: carries the mark. Each is pinned to the commit it was read at, and kept
#: unmodified in scripts/vendor/icons/official/. THIRD_PARTY_LICENSES.md says
#: what each one may be used for; a test holds every entry to that.
OFFICIAL: dict[str, dict[str, str]] = {
    "valkey": {
        "owner": "Valkey",
        "repository": "valkey-io/valkey-io.github.io",
        "path": "static/img/Valkey-logo.svg",
        "commit": "c2a4d37b33afc4cd879d29857d6c6bf3ae952f97",
        "licence": "BSD-3-Clause",
    },
    "redpanda": {
        "owner": "Redpanda Data",
        "repository": "redpanda-data/redpanda",
        "path": "docs/icon-redpanda.svg",
        "commit": "10932ba73d4c98eeda85ee55d80f2d6a8e01901c",
        "licence": "Redpanda artwork, no redistribution grant",
    },
}


# (slot_name, source, source_id, blurb)
# slot_name = what users call the icon
# source = "tabler" or "simple"
# source_id = upstream filename / slug (no extension)
ICONS: dict[str, list[tuple[str, str, str, str]]] = {
    "Compute": [
        ("laptop", "tabler", "device-laptop", "User laptop or workstation."),
        ("phone", "tabler", "device-mobile", "Mobile phone or tablet client."),
        ("desktop", "tabler", "device-desktop", "Desktop computer."),
        ("server", "tabler", "server", "Physical server or VM host."),
        ("container", "tabler", "package", "Container image or running instance."),
        ("vm", "tabler", "cube", "Virtual machine."),
    ],
    "People": [
        ("user", "tabler", "user", "End user or single actor."),
        ("users", "tabler", "users", "Group / cohort / team."),
        ("admin", "tabler", "user-shield", "Privileged user / admin."),
        ("robot", "tabler", "robot", "Bot, agent, or automated process."),
    ],
    "Network": [
        ("cloud", "tabler", "cloud", "Cloud provider or boundary."),
        ("internet", "tabler", "world", "Public internet."),
        ("cdn", "tabler", "world-www", "CDN or edge cache."),
        ("firewall", "tabler", "wall", "Firewall or perimeter control."),
        ("vpn", "tabler", "shield-lock", "VPN or encrypted tunnel."),
        ("load-balancer", "tabler", "arrows-split", "Load balancer / traffic split."),
        ("gateway", "tabler", "door-enter", "API gateway or ingress door."),
        ("dns", "tabler", "tag", "DNS / name resolution."),
    ],
    "Data": [
        ("database", "tabler", "database", "Relational or document database."),
        ("file", "tabler", "file", "Generic file."),
        ("log", "tabler", "file-text", "Log file / event stream."),
        ("queue", "tabler", "stack-2", "Message queue / FIFO."),
        ("cache", "tabler", "bolt", "Cache layer."),
        ("bucket", "tabler", "bucket", "Object storage / S3 bucket."),
        ("backup", "tabler", "device-floppy", "Backup or snapshot."),
        ("search", "tabler", "search", "Search index / query."),
    ],
    "Kubernetes": [
        ("pod", "tabler", "hexagon", "Pod (smallest deployable unit)."),
        ("node", "tabler", "topology-star", "Cluster node."),
        ("service", "tabler", "world-cog", "K8s service / virtual endpoint."),
        ("deployment", "tabler", "rocket", "Deployment rollout."),
        ("ingress", "tabler", "arrow-right-rhombus", "Ingress controller / route in."),
        ("volume", "tabler", "device-sd-card", "Persistent volume."),
    ],
    "Action": [
        ("api", "tabler", "braces", "API surface / endpoint."),
        ("request", "tabler", "arrow-right", "Outbound request."),
        ("response", "tabler", "arrow-left", "Inbound response."),
        ("sync", "tabler", "refresh", "Sync / reconcile loop."),
        ("lock", "tabler", "lock", "Locked / authenticated."),
        ("key", "tabler", "key", "Key / secret."),
        ("alert", "tabler", "alert-triangle", "Warning / paged alert."),
    ],
    "DevOps": [
        ("git-branch", "tabler", "git-branch", "Branch / fork point."),
        ("terminal", "tabler", "terminal", "Shell / CLI."),
        ("pipeline", "tabler", "git-merge", "CI/CD pipeline."),
        ("bug", "tabler", "bug", "Bug / defect."),
        ("monitoring", "tabler", "chart-line", "Metrics / observability."),
        ("test", "tabler", "test-pipe", "Test / experiment."),
        # Originals for a pipeline's parts no set draws: the machine that runs
        # its jobs, the gate a person approves, the artifact it signs.
        (
            "runner",
            "inline",
            """<rect x="4" y="3" width="16" height="18" rx="2" /> <path d="M4 8h16" /> <path d="M7.5 5.5h.01" /> <path d="M10.5 11.5v6l5 -3z" />""",
            "CI runner / build agent.",
        ),
        (
            "approval",
            "inline",
            """<path d="M9 5h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2h-2" /> <rect x="9" y="3" width="6" height="4" rx="1" /> <path d="M9 14l2 2l4 -4" />""",
            "Approval gate / protected environment.",
        ),
        (
            "signed-artifact",
            "inline",
            """<path d="M12 3l7 4v5" /> <path d="M12 3l-7 4v10l7 4" /> <path d="M5 7l7 4l7 -4" /> <path d="M12 11v10" /> <path d="M15 18l2 2l4 -4" />""",
            "Signed artifact / attested image.",
        ),
    ],
    "Identity": [
        # OpenID Connect's marks: the token a workload presents is a JSON Web
        # Token, and who issues it speaks OpenID Connect (Simple Icons, CC0).
        ("oidc-token", "simple", "jsonwebtokens", "OIDC / identity token (a JSON Web Token)."),
        ("idp", "simple", "openid", "Identity provider / OpenID Connect issuer."),
    ],
    "Brand": [
        # Stroke-style brand outlines (Tabler) where available — match the rest of the set
        ("docker", "tabler", "brand-docker", "Docker engine / image."),
        ("terraform", "tabler", "brand-terraform", "Terraform IaC."),
        ("aws", "tabler", "brand-aws", "Amazon Web Services."),
        ("azure", "tabler", "brand-azure", "Microsoft Azure."),
        ("digitalocean", "simple", "digitalocean", "DigitalOcean cloud platform."),
        ("github", "tabler", "brand-github", "GitHub."),
        ("github-actions", "simple", "githubactions", "GitHub Actions."),
        # Filled silhouettes (Simple Icons) for brands Tabler doesn't ship
        ("kubernetes", "simple", "kubernetes", "Kubernetes."),
        ("gcp", "simple", "googlecloud", "Google Cloud."),
        ("postgres", "simple", "postgresql", "PostgreSQL."),
        ("redis", "logz", "redis", "Redis."),
        ("valkey", "official", "valkey", "Valkey (the Linux Foundation's Redis fork)."),
        ("nginx", "simple", "nginx", "Nginx."),
        ("gitea", "simple", "gitea", "Gitea self-hosted git."),
        ("keycloak", "simple", "keycloak", "Keycloak identity / SSO."),
        (
            "active-directory",
            "tabler",
            "address-book",
            "Active Directory / LDAP identity directory.",
        ),
        ("minio", "simple", "minio", "MinIO S3-compatible object storage."),
        ("mysql", "logz", "mysql", "MySQL."),
        ("oracle", "simple", "oracle", "Oracle Database."),
        ("sqlserver", "simple", "microsoftsqlserver", "Microsoft SQL Server."),
        ("sqlite", "simple", "sqlite", "SQLite embedded database."),
        ("hive", "simple", "apachehive", "Apache Hive data warehouse."),
        ("starrocks", "logz", "starrocks", "StarRocks MPP analytical DB."),
        ("stripe", "tabler", "brand-stripe", "Stripe (Tabler brand outline)."),
        ("paypal", "tabler", "brand-paypal", "PayPal (Tabler brand outline)."),
        ("discord", "tabler", "brand-discord", "Discord (Tabler brand outline)."),
        ("telegram", "tabler", "brand-telegram", "Telegram (Tabler brand outline)."),
        ("twilio", "tabler", "brand-twilio", "Twilio (Tabler brand outline)."),
        ("facebook", "tabler", "brand-facebook", "Facebook (Tabler brand outline)."),
        ("x-twitter", "tabler", "brand-x", "X, formerly Twitter (Tabler brand outline)."),
    ],
    "Self-hosted platforms": [
        ("pihole", "simple", "pihole", "Pi-hole network-wide DNS sinkhole."),
        ("adguard", "simple", "adguard", "AdGuard Home DNS filtering."),
        ("wireguard", "simple", "wireguard", "WireGuard VPN."),
        ("openvpn", "simple", "openvpn", "OpenVPN."),
        ("authelia", "simple", "authelia", "Authelia SSO and 2FA portal."),
        ("authentik", "simple", "authentik", "authentik identity provider."),
        ("vaultwarden", "simple", "vaultwarden", "Vaultwarden password server."),
        ("portainer", "simple", "portainer", "Portainer container management."),
        ("rancher", "simple", "rancher", "Rancher Kubernetes management."),
        ("longhorn", "simple", "longhorn", "Longhorn distributed block storage."),
        ("forgejo", "simple", "forgejo", "Forgejo self-hosted Git forge."),
        ("salt", "simple", "saltproject", "Salt configuration management."),
        ("rundeck", "simple", "rundeck", "Rundeck runbook automation."),
        ("truenas", "simple", "truenas", "TrueNAS storage appliance."),
        ("home-assistant", "simple", "homeassistant", "Home Assistant automation hub."),
        ("mattermost", "simple", "mattermost", "Mattermost team messaging."),
        ("rocket-chat", "simple", "rocketdotchat", "Rocket.Chat team messaging."),
        ("matrix", "simple", "matrix", "Matrix decentralized messaging."),
        ("jitsi", "simple", "jitsi", "Jitsi video conferencing."),
        ("coder", "simple", "coder", "Coder / code-server remote development."),
        ("syncthing", "simple", "syncthing", "Syncthing file synchronization."),
        ("paperless", "simple", "paperlessngx", "Paperless-ngx document management."),
        ("bookstack", "simple", "bookstack", "BookStack wiki."),
        ("wiki-js", "simple", "wikidotjs", "Wiki.js knowledge base."),
        ("gitbook", "simple", "gitbook", "GitBook documentation."),
        ("elasticsearch", "simple", "elasticsearch", "Elasticsearch search and analytics engine."),
        ("kibana", "simple", "kibana", "Kibana dashboards."),
        ("logstash", "simple", "logstash", "Logstash ingest pipeline."),
        ("opensearch", "simple", "opensearch", "OpenSearch search and analytics."),
        ("icinga", "simple", "icinga", "Icinga monitoring."),
        ("checkmk", "simple", "checkmk", "Checkmk monitoring."),
        ("uptime-kuma", "simple", "uptimekuma", "Uptime Kuma status monitoring."),
        ("netdata", "simple", "netdata", "Netdata real-time monitoring."),
        ("nginx-proxy-manager", "simple", "nginxproxymanager", "Nginx Proxy Manager."),
        ("qemu", "simple", "qemu", "QEMU / KVM virtualization."),
        ("virtualbox", "simple", "virtualbox", "Oracle VirtualBox."),
        ("nutanix", "simple", "nutanix", "Nutanix hyperconverged infrastructure."),
        ("veeam", "simple", "veeam", "Veeam backup and replication."),
        ("borgbackup", "simple", "borgbackup", "BorgBackup deduplicating backup."),
        ("talend", "simple", "talend", "Talend data integration."),
        ("hadoop", "simple", "apachehadoop", "Apache Hadoop."),
        ("spark", "simple", "apachespark", "Apache Spark."),
        ("snowflake", "simple", "snowflake", "Snowflake data cloud."),
        ("cloudera", "simple", "cloudera", "Cloudera data platform."),
        ("teradata", "simple", "teradata", "Teradata analytics database."),
        ("microstrategy", "simple", "microstrategy", "MicroStrategy BI."),
        ("qlik", "simple", "qlik", "Qlik analytics."),
        ("sap", "simple", "sap", "SAP enterprise applications."),
    ],
    "Network and hardware vendors": [
        ("cisco", "simple", "cisco", "Cisco networking."),
        ("juniper", "simple", "junipernetworks", "Juniper Networks."),
        ("fortinet", "simple", "fortinet", "Fortinet security."),
        ("palo-alto", "simple", "paloaltonetworks", "Palo Alto Networks."),
        ("ubiquiti", "simple", "ubiquiti", "Ubiquiti networking."),
        ("f5", "simple", "f5", "F5 application delivery."),
        ("sonicwall", "simple", "sonicwall", "SonicWall firewalls."),
        ("netgear", "simple", "netgear", "NETGEAR networking."),
        ("tp-link", "simple", "tplink", "TP-Link networking."),
        ("huawei", "simple", "huawei", "Huawei networking."),
        ("dell", "simple", "dell", "Dell servers and storage."),
        ("supermicro", "simple", "supermicro", "Supermicro servers."),
    ],
    "Datacenter and network infrastructure": [
        ("mainframe", "tabler", "server-2", "Mainframe (IBM Z, z/OS, IBM i)."),
        ("blade-chassis", "tabler", "box-multiple", "Blade chassis / enclosure."),
        ("hpc-node", "tabler", "cpu-2", "HPC compute node."),
        ("gpu-server", "tabler", "cpu", "GPU server."),
        ("ha-cluster", "tabler", "affiliate", "High-availability cluster."),
        ("failover-pair", "tabler", "arrows-shuffle", "Active/passive failover pair."),
        ("kvm-console", "tabler", "devices", "KVM / out-of-band console."),
        ("ups", "tabler", "battery-charging", "Uninterruptible power supply."),
        ("pdu", "tabler", "plug-connected", "Power distribution unit."),
        ("san-switch", "tabler", "topology-star-ring", "SAN fabric switch (Fibre Channel)."),
        ("storage-array", "tabler", "stack-3", "Block storage array."),
        ("nas", "tabler", "archive", "NAS filer (NFS / SMB)."),
        ("tape-library", "tabler", "disc", "Tape or archive library."),
        ("wireless-access-point", "tabler", "access-point", "Wireless access point."),
        ("wlan-controller", "tabler", "antenna", "Wireless LAN controller."),
        ("wan-link", "tabler", "cloud-network", "WAN / MPLS / carrier link."),
        (
            "edge-router",
            "inline",
            """<ellipse cx="12" cy="8" rx="9" ry="3.75" /> <path d="M3 8v7.5c0 2.07 4.03 3.75 9 3.75s9 -1.68 9 -3.75v-7.5" /> <path d="M13.2 8h4" /> <path d="M15.8 6.9l1.4 1.1l-1.4 1.1" /> <path d="M10.8 8h-4" /> <path d="M8.2 6.9l-1.4 1.1l1.4 1.1" />""",
            "Edge router / SD-WAN appliance: the classic router drum, an original drawing, so a wire on any side meets the device and not an antenna.",
        ),
        ("core-switch", "tabler", "switch-2", "Core / distribution switch."),
        ("access-switch", "tabler", "network", "Access switch."),
        ("proxy", "tabler", "arrows-exchange", "Forward or reverse proxy."),
        ("patch-panel", "tabler", "grid-dots", "Patch panel / structured cabling."),
        ("dhcp-server", "tabler", "sitemap", "DHCP server."),
        ("ntp-server", "tabler", "clock", "NTP time server."),
        ("pbx", "tabler", "phone", "PBX / VoIP system."),
        ("vpn-concentrator", "tabler", "cloud-lock", "VPN concentrator."),
        ("ids-ips", "tabler", "radar", "Intrusion detection / prevention."),
        ("waf", "tabler", "shield-check", "Web application firewall."),
        ("badge-reader", "tabler", "fingerprint", "Physical access control."),
        ("security-camera", "tabler", "device-cctv", "Security camera."),
        ("domain-controller", "tabler", "id-badge", "Domain controller."),
        ("print-server", "tabler", "printer", "Print server."),
        ("iot-gateway", "tabler", "route", "IoT gateway."),
        ("sensor", "tabler", "temperature", "Environmental sensor."),
        ("monitoring-probe", "tabler", "gauge", "Monitoring probe / collector."),
        ("printer", "tabler", "printer", "Network or office printer."),
        ("ip-phone", "tabler", "device-landline-phone", "IP desk phone or VoIP handset."),
        ("satellite-terminal", "tabler", "satellite", "Satellite terminal or VSAT uplink."),
        ("disk-shelf", "tabler", "disc", "Disk shelf, JBOD or expansion enclosure."),
    ],
    "Enterprise platforms and vendors": [
        ("red-hat", "simple", "redhat", "Red Hat."),
        ("openshift", "simple", "redhatopenshift", "Red Hat OpenShift."),
        ("suse", "simple", "suse", "SUSE Linux Enterprise."),
        ("opensuse", "simple", "opensuse", "openSUSE."),
        ("rocky-linux", "simple", "rockylinux", "Rocky Linux."),
        ("almalinux", "simple", "almalinux", "AlmaLinux."),
        ("freebsd", "simple", "freebsd", "FreeBSD."),
        ("fedora", "simple", "fedora", "Fedora."),
        ("citrix", "simple", "citrix", "Citrix virtualization and VDI."),
        ("netapp", "simple", "netapp", "NetApp storage."),
        ("hitachi", "simple", "hitachi", "Hitachi Vantara storage."),
        ("veritas", "simple", "veritas", "Veritas backup and availability."),
        ("okta", "simple", "okta", "Okta identity."),
        ("auth0", "simple", "auth0", "Auth0 identity."),
        ("qualys", "simple", "qualys", "Qualys vulnerability management."),
        ("fastly", "simple", "fastly", "Fastly edge and CDN."),
        ("atlassian", "simple", "atlassian", "Atlassian."),
        ("jira", "simple", "jira", "Jira."),
        ("confluence", "simple", "confluence", "Confluence."),
        ("bitbucket", "simple", "bitbucket", "Bitbucket."),
        ("zoom", "simple", "zoom", "Zoom."),
        ("asterisk", "simple", "asterisk", "Asterisk PBX."),
        ("hashicorp", "simple", "hashicorp", "HashiCorp."),
        ("vagrant", "simple", "vagrant", "Vagrant."),
        ("packer", "simple", "packer", "Packer image builder."),
        ("chef", "simple", "chef", "Chef configuration management."),
        ("octopus-deploy", "simple", "octopusdeploy", "Octopus Deploy."),
        ("sonatype-nexus", "simple", "sonatype", "Sonatype Nexus repository."),
        ("podman", "simple", "podman", "Podman."),
        ("helm", "simple", "helm", "Helm charts."),
        ("owncloud", "simple", "owncloud", "ownCloud."),
        ("seafile", "simple", "seafile", "Seafile."),
        ("openmediavault", "simple", "openmediavault", "openmediavault NAS."),
        ("unraid", "simple", "unraid", "Unraid."),
        ("synology", "simple", "synology", "Synology NAS."),
        ("qnap", "simple", "qnap", "QNAP NAS."),
        ("timescale", "simple", "timescale", "TimescaleDB."),
        ("mqtt", "simple", "mqtt", "MQTT broker."),
        ("pagerduty", "simple", "pagerduty", "PagerDuty."),
        ("opsgenie", "simple", "opsgenie", "Opsgenie."),
        ("wireshark", "simple", "wireshark", "Wireshark."),
        ("kali-linux", "simple", "kalilinux", "Kali Linux."),
        ("snort", "simple", "snort", "Snort IDS."),
        ("cloudstack", "simple", "apachecloudstack", "Apache CloudStack."),
        ("opennebula", "simple", "opennebula", "OpenNebula."),
        ("hp", "simple", "hp", "HP."),
        ("intel", "simple", "intel", "Intel."),
        ("roundcube", "simple", "roundcube", "Roundcube webmail."),
    ],
    "Operations, security, facilities and OT concepts": [
        ("unix-server", "tabler", "server-cog", "UNIX server (AIX, Solaris, HP-UX)."),
        ("console-server", "tabler", "terminal-2", "Serial / out-of-band console server."),
        ("network-cable", "tabler", "plug", "Copper or fibre cable / structured cabling."),
        ("isp-uplink", "tabler", "world-www", "Internet service provider uplink / modem."),
        ("network-tap", "tabler", "eye", "Network TAP / SPAN / packet broker."),
        ("ipam", "tabler", "list-search", "IP address management / DCIM."),
        ("overlay-network", "tabler", "layers-intersect", "VXLAN / SDN overlay network."),
        ("nac", "tabler", "id-badge-2", "Network access control / 802.1X."),
        ("radius-server", "tabler", "user-check", "RADIUS / TACACS+ AAA server."),
        ("routing-protocol", "tabler", "route-2", "Dynamic routing adjacency (OSPF, BGP)."),
        ("honeypot", "tabler", "spider", "Honeypot / deception host."),
        ("endpoint-protection", "tabler", "virus-off", "Antivirus / EDR / XDR agent."),
        ("zero-trust-gateway", "tabler", "shield-lock", "Zero-trust access gateway / ZTNA."),
        ("pki", "tabler", "certificate", "PKI / certificate authority."),
        ("hsm", "tabler", "lock-square-rounded", "Hardware security module."),
        ("dlp", "tabler", "file-shredder", "Data loss prevention."),
        ("mail-server", "tabler", "mail-cog", "Mail server (SMTP / IMAP)."),
        ("mail-relay", "tabler", "mail-forward", "Mail relay / spam gateway."),
        ("esb", "tabler", "arrows-left-right", "Enterprise service bus / integration platform."),
        ("cdc", "tabler", "database-export", "Change data capture / replication stream."),
        ("webhook", "tabler", "webhook", "Webhook / HTTP callback."),
        ("file-transfer", "tabler", "transfer", "SFTP / managed file transfer."),
        ("bpm", "tabler", "hierarchy-2", "Business process / workflow engine."),
        ("payment-gateway", "tabler", "credit-card", "Payment gateway / PSP."),
        ("crm", "tabler", "address-book", "CRM system."),
        ("itsm", "tabler", "ticket", "ITSM / service desk."),
        ("cmdb", "tabler", "clipboard-list", "CMDB / asset inventory."),
        ("kiosk", "tabler", "device-tv", "Kiosk / digital signage."),
        ("generator", "tabler", "engine", "Backup power generator."),
        ("utility-power", "tabler", "bolt", "Utility power feed."),
        ("cooling", "tabler", "snowflake", "Cooling / HVAC / CRAC."),
        ("fire-suppression", "tabler", "flame", "Fire detection and suppression."),
        ("plc", "tabler", "circuit-pushbutton", "PLC / industrial controller."),
        ("scada", "tabler", "circuit-switch-open", "SCADA / RTU."),
        ("hmi", "tabler", "device-desktop-analytics", "HMI / operator station."),
        ("single-board-computer", "tabler", "cpu", "Single-board computer / edge device."),
        ("lpwan-radio", "tabler", "radio", "LoRaWAN / Zigbee / LPWAN radio."),
        ("rfid-reader", "tabler", "nfc", "RFID / NFC reader."),
        ("barcode-scanner", "tabler", "barcode", "Barcode scanner."),
        ("bluetooth-beacon", "tabler", "bluetooth", "Bluetooth / BLE beacon."),
        ("air-gap", "tabler", "network-off", "Air-gapped / isolated segment."),
        ("windows", "tabler", "brand-windows", "Microsoft Windows (Tabler brand outline)."),
        ("slack", "tabler", "brand-slack", "Slack (Tabler brand outline)."),
        ("teams", "tabler", "brand-teams", "Microsoft Teams (Tabler brand outline)."),
        ("microsoft-365", "tabler", "brand-office", "Microsoft 365 (Tabler brand outline)."),
        ("jump-host", "tabler", "door-enter", "Bastion or jump host: the one way in."),
    ],
    "Platform and product marks II": [
        ("1password", "simple", "1password", "1Password."),
        ("airbyte", "simple", "airbyte", "Airbyte."),
        ("alpinelinux", "simple", "alpinelinux", "Alpine Linux."),
        ("anydesk", "simple", "anydesk", "AnyDesk."),
        ("apacheguacamole", "simple", "apacheguacamole", "Apache Guacamole."),
        ("apacheparquet", "simple", "apacheparquet", "Apache Parquet."),
        ("apachepulsar", "simple", "apachepulsar", "Apache Pulsar."),
        ("redpanda", "official", "redpanda", "Redpanda (Kafka-compatible streaming)."),
        ("arangodb", "simple", "arangodb", "ArangoDB."),
        ("archlinux", "simple", "archlinux", "Arch Linux."),
        ("arduino", "simple", "arduino", "Arduino."),
        ("backstage", "simple", "backstage", "Backstage."),
        ("bigbluebutton", "simple", "bigbluebutton", "BigBlueButton."),
        ("burpsuite", "simple", "burpsuite", "Burp Suite."),
        ("camunda", "simple", "camunda", "Camunda."),
        ("dependabot", "simple", "dependabot", "Dependabot."),
        ("dovecot", "simple", "dovecot", "Dovecot."),
        ("drupal", "simple", "drupal", "Drupal."),
        ("erpnext", "simple", "erpnext", "ERPNext."),
        ("esphome", "simple", "esphome", "ESPHome."),
        ("falco", "simple", "falco", "Falco."),
        ("fluentbit", "simple", "fluentbit", "Fluent Bit."),
        ("frigate", "simple", "frigate", "Frigate."),
        ("gitpod", "simple", "gitpod", "Gitpod."),
        ("graphql", "simple", "graphql", "GraphQL."),
        ("hubspot", "simple", "hubspot", "HubSpot."),
        ("jellyfin", "simple", "jellyfin", "Jellyfin."),
        ("keepassxc", "simple", "keepassxc", "KeePassXC."),
        ("langchain", "simple", "langchain", "LangChain."),
        ("lenovo", "simple", "lenovo", "Lenovo."),
        ("meilisearch", "simple", "meilisearch", "Meilisearch."),
        ("metasploit", "simple", "metasploit", "Metasploit."),
        ("milvus", "simple", "milvus", "Milvus."),
        ("n8n", "simple", "n8n", "n8n."),
        ("nixos", "simple", "nixos", "NixOS."),
        ("nodered", "simple", "nodered", "Node-RED."),
        ("nvidia", "simple", "nvidia", "NVIDIA."),
        ("odoo", "simple", "odoo", "Odoo."),
        ("ollama", "simple", "ollama", "Ollama."),
        ("openbsd", "simple", "openbsd", "OpenBSD."),
        ("openhab", "simple", "openhab", "openHAB."),
        ("openwrt", "simple", "openwrt", "OpenWrt."),
        ("parrotsecurity", "simple", "parrotsecurity", "Parrot Security."),
        ("raspberrypi", "simple", "raspberrypi", "Raspberry Pi."),
        ("rclone", "simple", "rclone", "rclone."),
        ("renovate", "simple", "renovate", "Renovate."),
        ("rook", "simple", "rook", "Rook."),
        ("rustdesk", "simple", "rustdesk", "RustDesk."),
        ("scylladb", "simple", "scylladb", "ScyllaDB."),
        ("shopify", "simple", "shopify", "Shopify."),
        ("snyk", "simple", "snyk", "Snyk."),
        ("sonarqubeserver", "simple", "sonarqubeserver", "SonarQube Server."),
        ("strongswan", "simple", "strongswan", "strongSwan."),
        ("sumologic", "simple", "sumologic", "Sumo Logic."),
        ("tailscale", "simple", "tailscale", "Tailscale."),
        ("talos", "simple", "talos", "Talos Linux."),
        ("teamviewer", "simple", "teamviewer", "TeamViewer."),
        ("thunderbird", "simple", "thunderbird", "Thunderbird."),
        ("tidb", "simple", "tidb", "TiDB."),
        ("victoriametrics", "simple", "victoriametrics", "VictoriaMetrics."),
        ("virustotal", "simple", "virustotal", "VirusTotal."),
        ("vitess", "simple", "vitess", "Vitess."),
        ("webassembly", "simple", "webassembly", "WebAssembly."),
        ("woocommerce", "simple", "woocommerce", "WooCommerce."),
        ("yubico", "simple", "yubico", "Yubico."),
        ("zapier", "simple", "zapier", "Zapier."),
        ("zendesk", "simple", "zendesk", "Zendesk."),
        ("zerotier", "simple", "zerotier", "ZeroTier."),
        ("zigbee", "simple", "zigbee", "Zigbee."),
        ("macos", "simple", "macos", "macOS."),
    ],
    "Data stack": [
        ("nifi", "simple", "apachenifi", "Apache NiFi data flow."),
        ("airflow", "simple", "apacheairflow", "Apache Airflow scheduler / DAG runner."),
        (
            "hop",
            "tabler",
            "binary-tree",
            "Apache Hop data orchestration and ETL. Generic glyph: no licence-clean brand mark exists.",
        ),
        (
            "pentaho",
            "tabler",
            "report-analytics",
            "Pentaho data integration and BI. Generic glyph: no licence-clean brand mark exists.",
        ),
        (
            "dagster",
            "tabler",
            "topology-star-3",
            "Dagster data orchestration. Generic glyph: no licence-clean brand mark exists.",
        ),
        ("trino", "simple", "trino", "Trino distributed SQL query engine."),
        ("superset", "simple", "apachesuperset", "Apache Superset BI / dashboards."),
        ("redash", "simple", "redash", "Redash open-source BI & dashboards."),
        ("tableau", "simple", "tableau", "Tableau data visualization."),
        ("powerbi", "simple", "powerbi", "Microsoft Power BI."),
        ("jupyter", "simple", "jupyter", "Jupyter / JupyterLab notebooks."),
    ],
    "Language": [
        ("python", "simple", "python", "Python."),
        ("r", "simple", "r", "R statistical language."),
        ("sql", "tabler", "sql", "SQL / generic relational query."),
    ],
    "Statistical tools": [
        ("spss", "devicon:plain", "spss", "IBM SPSS Statistics."),
        (
            "sas",
            "tabler",
            "chart-histogram",
            "SAS statistical analytics. Generic glyph: no licence-clean brand mark exists.",
        ),
        (
            "stata",
            "tabler",
            "chart-dots",
            "Stata statistical analysis. Generic glyph: no licence-clean brand mark exists.",
        ),
        ("rstudio", "devicon:plain", "rstudio", "RStudio / Posit IDE for R and Python."),
        ("qgis", "simple", "qgis", "QGIS open-source GIS platform."),
    ],
    "File formats": [
        ("excel", "tabler", "file-type-xls", "Microsoft Excel spreadsheet."),
        ("csv", "tabler", "file-type-csv", "Comma-separated values file."),
        ("txt", "tabler", "file-type-txt", "Plain text file."),
    ],
}


FETCH_ATTEMPTS = 3
FETCH_BACKOFF_SECONDS = 1.0


def fetch(url: str) -> str | None:
    """Fetch a URL as UTF-8 text, retrying transient network failures."""
    if not url.startswith("https://"):
        raise SystemExit(f"icons are fetched over https only, not {url}")
    request = urllib.request.Request(  # noqa: S310 - https, checked above
        url, headers={"User-Agent": "infragram-build/1.0 (https://github.com)"}
    )
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - https, checked above
                return response.read().decode("utf-8")
        except urllib.error.HTTPError:
            # A definitive upstream answer (404 etc.) — callers try fallbacks.
            return None
        except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError) as error:
            if attempt == FETCH_ATTEMPTS:
                print(f"  network error for {url}: {error}", file=sys.stderr)
                return None
            time.sleep(FETCH_BACKOFF_SECONDS * attempt)
    return None


def fetch_tabler(name: str) -> str | None:
    return fetch(TABLER_URL.format(name=name)) or fetch(TABLER_URL_FALLBACK.format(name=name))


def fetch_simple(slug: str) -> str | None:
    return fetch(SI_URL.format(slug=slug)) or fetch(SI_CDN_URL.format(slug=slug))


def fetch_logz(name: str) -> str | None:
    return fetch(LOGZ_URL.format(name=name))


def fetch_devicon(name: str, variant: str = "plain") -> str | None:
    return fetch(DEVICON_URL.format(name=name, variant=variant))


def fetch_url(url: str) -> str | None:
    return fetch(url)


def normalize_tabler(raw: str) -> str:
    """Extract inner geometry from a Tabler SVG and wrap with our normalized attrs."""
    inner = re.search(r"<svg\b[^>]*>(.*?)</svg>", raw, flags=re.DOTALL | re.IGNORECASE)
    if not inner:
        raise ValueError("no <svg> in Tabler payload")
    body = inner.group(1).strip()
    # Drop tabler-icons class wrapper paths (icon-tabler placeholder path that does nothing)
    body = re.sub(r'<path\s+stroke="none"[^/]*?/>', "", body)
    body = re.sub(r"\s+", " ", body).strip()
    return (
        '<svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


def normalize_simple(raw: str) -> str:
    """Extract path from a Simple Icons SVG; force fill=currentColor."""
    inner = re.search(r"<svg\b[^>]*>(.*?)</svg>", raw, flags=re.DOTALL | re.IGNORECASE)
    if not inner:
        raise ValueError("no <svg> in Simple Icons payload")
    body = inner.group(1).strip()
    body = re.sub(r"\s+", " ", body).strip()
    return (
        '<svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" '
        f'fill="currentColor">{body}</svg>'
    )


def normalize_url(raw: str) -> str:
    """Generic normalizer for directly-fetched SVGs (icepanel, vendor CDNs, etc.).
    Extracts inner paths, rewrites fill/stroke colours to currentColor,
    and preserves the original viewBox.

    Rules applied:
    - White / near-white fills (#fff, #ffffff, white) are kept as-is — they
      act as contrast cutouts in 2-colour logos (e.g. white letter on coloured
      circle).  Every other colour becomes currentColor.
    - inline fill/stroke colours are normalized without discarding other styles.
    - Inkscape layer translate() transforms are stripped (canvas offset artefact).
    """
    viewbox = fr_verify.view_box(raw) or "0 0 128 128"
    inner = re.search(r"<svg\b[^>]*>(.*?)</svg>", raw, flags=re.DOTALL | re.IGNORECASE)
    if not inner:
        raise ValueError("no <svg> in payload")
    body = inner.group(1)
    body = re.sub(r"<style\b[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<title\b[^>]*>.*?</title>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<defs\b[^>]*>.*?</defs>", "", body, flags=re.DOTALL | re.IGNORECASE)
    # Strip Inkscape canvas-offset translate transforms from group wrappers
    body = re.sub(r'\btransform="translate\([^"]+\)"', "", body)

    def _normalized_fill(value: str) -> str:
        """Keep white; turn everything else into currentColor."""
        hex_val = value.lower().strip()
        if hex_val in ("#fff", "#ffffff", "white", "#fefefe", "#fdfdfd"):
            return "#fff"
        return "currentColor"

    def _normalize_inline_style(match: re.Match) -> str:
        quote, declarations = match.group(1), match.group(2)
        declarations = re.sub(
            r"(\bfill\s*:\s*)(#[0-9a-fA-F]{3,8}|white)\b",
            lambda fill: f"{fill.group(1)}{_normalized_fill(fill.group(2))}",
            declarations,
            flags=re.IGNORECASE,
        )
        declarations = re.sub(
            r"(\bstroke\s*:\s*)#[0-9a-fA-F]{3,8}\b",
            lambda stroke: f"{stroke.group(1)}currentColor",
            declarations,
            flags=re.IGNORECASE,
        )
        return f"style={quote}{declarations}{quote}"

    # Normalize supported inline colours while preserving unrelated declarations.
    body = re.sub(
        r'style\s*=\s*(["\'])(.*?)\1',
        _normalize_inline_style,
        body,
        flags=re.IGNORECASE,
    )
    # Rewrite standalone fill="#rrggbb" attributes.
    body = re.sub(
        r'\bfill\s*=\s*(["\'])(#[0-9a-fA-F]{3,8}|white)\1',
        lambda m: f'fill="{_normalized_fill(m.group(2))}"',
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r'\bstroke\s*=\s*(["\'])#[0-9a-fA-F]{3,8}\1',
        'stroke="currentColor"',
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        r'\bfill\s*=\s*(["\'])none\1',
        "",
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(r"\s+", " ", body).strip()
    return (
        f'<svg aria-hidden="true" width="24" height="24" viewBox="{viewbox}" '
        f'fill="currentColor">{body}</svg>'
    )


_CIRCLE = re.compile(r'cx="(?P<cx>[\d.]+)"\s+cy="(?P<cy>[\d.]+)"\s+r="(?P<r>[\d.]+)"')
_PATH_DATA = re.compile(r'(?<![\w-])d="([^"]+)"')


def _circle_path(attributes: str) -> str:
    """A ``<circle>`` as path data, so it can share one path with others."""
    found = _CIRCLE.search(attributes)
    if found is None:
        raise ValueError(f"a circle without cx, cy and r: {attributes!r}")
    cx, cy, r = (float(found.group(name)) for name in ("cx", "cy", "r"))
    return f"M{cx - r:g} {cy:g}a{r:g} {r:g} 0 1 0 {2 * r:g} 0a{r:g} {r:g} 0 1 0 {-2 * r:g} 0Z"


def normalize_official(raw: str) -> str:
    """A project's own logo, in one colour.

    As :func:`normalize_url`, and a two-colour mark whose second colour is
    white (a panda on a disc) becomes one shape with the white cut out, so
    the card shows through it in either theme instead of a white figure on
    a near-white disc in the dark one.
    """
    glyph = normalize_url(raw)
    if 'fill="#fff"' not in glyph:
        return glyph
    whole = re.match(r"(<svg\b[^>]*>)(.*)</svg>$", glyph, flags=re.DOTALL)
    if whole is None:
        raise ValueError("no <svg> in payload")
    head, body = whole.groups()
    shapes = re.findall(r"<(circle|path)\b([^>]*)/>", body)
    if not shapes or len(shapes) != len(re.findall(r"<[a-z]", body)):
        raise ValueError("a two-colour logo of anything but circles and paths")
    parts = []
    for kind, attributes in shapes:
        if kind == "circle":
            parts.append(_circle_path(attributes))
        else:
            data = _PATH_DATA.search(attributes)
            if data is None:
                raise ValueError(f"a path without data: {attributes!r}")
            parts.append(data.group(1))
    return f'{head}<path fill-rule="evenodd" d="{" ".join(parts)}"/></svg>'


def normalize_devicon(raw: str) -> str:
    """Devicon SVGs have colored fills and a 128x128 or 32x32 viewBox.
    Strip fills/classes and rewrite to 24x24 currentColor."""
    viewbox_match = re.search(r'\bviewBox\s*=\s*(["\'])(.*?)\1', raw, flags=re.IGNORECASE)
    viewbox = viewbox_match.group(2).strip() if viewbox_match else "0 0 128 128"
    inner = re.search(r"<svg\b[^>]*>(.*?)</svg>", raw, flags=re.DOTALL | re.IGNORECASE)
    if not inner:
        raise ValueError("no <svg> in Devicon payload")
    body = inner.group(1)
    body = re.sub(r"<style\b[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r"<title\b[^>]*>.*?</title>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'\bfill="#[0-9a-fA-F]{3,8}"', 'fill="currentColor"', body)
    body = re.sub(r'\bstroke="#[0-9a-fA-F]{3,8}"', 'stroke="currentColor"', body)
    # Drop class attributes instead of rewriting them to fill="currentColor":
    # an element that already carries a fill would otherwise end up with two
    # fill attributes. The wrapper <svg fill="currentColor"> inherits anyway.
    body = re.sub(r'\bclass="[^"]*"', "", body)
    body = re.sub(r"\s+", " ", body).strip()
    return (
        f'<svg aria-hidden="true" width="24" height="24" viewBox="{viewbox}" '
        f'fill="currentColor">{body}</svg>'
    )


def normalize_logz(raw: str) -> str:
    """log-z/logos SVGs are 100x100 with embedded <style> + class-based fills.
    Strip the style block and rewrite class refs so the icon inherits currentColor."""
    inner = re.search(r"<svg\b[^>]*>(.*?)</svg>", raw, flags=re.DOTALL | re.IGNORECASE)
    if not inner:
        raise ValueError("no <svg> in log-z payload")
    body = inner.group(1)
    body = re.sub(r"<style\b[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
    body = re.sub(r'\bclass="st\d+"', 'fill="currentColor"', body)
    body = re.sub(r'\bfill="#[0-9a-fA-F]{3,8}"', 'fill="currentColor"', body)
    body = re.sub(r"\s+", " ", body).strip()
    return (
        '<svg aria-hidden="true" width="24" height="24" viewBox="0 0 100 100" '
        f'fill="currentColor">{body}</svg>'
    )


def normalize_inline(body: str) -> str:
    return (
        '<svg aria-hidden="true" width="24" height="24" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
        + re.sub(r"\s+", " ", body).strip()
        + "</svg>"
    )


def resolve_source(
    source: str, source_id: str
) -> tuple[Callable[[str], str], str, Callable[[], str | None]]:
    """Return (normalizer, attribution, fetcher) for one manifest entry."""
    if source == "tabler":
        return (
            normalize_tabler,
            f"Tabler Icons / `{source_id}` (MIT)",
            lambda: fetch_tabler(source_id),
        )
    if source == "simple":
        return (
            normalize_simple,
            f"Simple Icons / `{source_id}` (CC0)",
            lambda: fetch_simple(source_id),
        )
    if source == "logz":
        return normalize_logz, f"log-z/logos / `{source_id}` (MIT)", lambda: fetch_logz(source_id)
    if source.startswith("devicon"):
        variant = source.split(":")[1] if ":" in source else "plain"
        return (
            normalize_devicon,
            f"Devicon / `{source_id}-{variant}` (MIT)",
            lambda: fetch_devicon(source_id, variant),
        )
    if source == "official":
        entry = OFFICIAL[source_id]
        url = (
            f"https://raw.githubusercontent.com/{entry['repository']}/"
            f"{entry['commit']}/{entry['path']}"
        )
        return (
            normalize_official,
            f"{entry['owner']} / `{entry['repository']}` `{entry['path']}` ({entry['licence']})",
            lambda: fetch(url),
        )
    if source == "inline":
        # An original drawing kept in this table: source_id is the SVG body,
        # in the same hairline stroke style as the Tabler set.
        return normalize_inline, "Infragram original (MIT)", lambda: source_id
    if source == "url":
        domain = urllib.parse.urlparse(source_id).netloc
        return (
            normalize_url,
            f"Direct fetch / `{domain}` — verify license before use",
            lambda: fetch_url(source_id),
        )
    raise ValueError(f"unknown source: {source}")


def load_raw_icon(
    slot: str, source: str, source_id: str, fetcher: Callable[[], str | None]
) -> tuple[str | None, pathlib.Path]:
    """Return the raw SVG payload from cache or network, caching valid fetches."""
    if source == "inline":
        return source_id, VENDOR_DIR / "inline" / f"{slot}.svg"
    vpath = vendor_path(slot, source, source_id)
    if vpath.exists():
        print(f"  local   {source}/{source_id} -> {slot}", file=sys.stderr)
        return vpath.read_text(encoding="utf-8"), vpath
    print(f"  fetching {source}/{source_id} -> {slot}", file=sys.stderr)
    raw = fetcher()
    if raw is not None and "<svg" not in raw.lower():
        # An HTML error page served with HTTP 200 would otherwise be cached
        # forever; treat any payload without an <svg> tag as a miss.
        print(f"  invalid payload (no <svg>) for {source}/{source_id}", file=sys.stderr)
        return None, vpath
    if raw is not None:
        vpath.parent.mkdir(parents=True, exist_ok=True)
        vpath.write_text(raw, encoding="utf-8", newline="\n")
    return raw, vpath


def build() -> tuple[list[str], list[str]]:
    md_chunks: list[str] = []
    misses: list[str] = []

    md_chunks.append(
        "# Shared primitive artwork\n\nThe glyphs the shared library's "
        "neutral components draw with: one monochrome 24×24 SVG per "
        "artwork slot, in `currentColor`, with its upstream source. The "
        "renderer reads them from this file. Nothing here is pasted into a "
        "diagram, and the headings are artwork slots, not component ids: "
        "to place a component, use its `infragram:` id or its class from "
        "[shared-components.md](shared-components.md).\n\nGenerated from the "
        "icon sources the repository keeps; do not edit by hand. Generic "
        "glyphs are stroked at 1.5 px; brand silhouettes are filled.\n\n"
    )

    for category, items in ICONS.items():
        md_chunks.append(f"## {category}\n\n")

        for slot, source, source_id, blurb in items:
            normalize, attribution, fetcher = resolve_source(source, source_id)
            raw, vpath = load_raw_icon(slot, source, source_id, fetcher)

            if raw is None:
                misses.append(f"{slot} <- {source}/{source_id}")
                md_chunks.append(f"### {slot}\n_NOT FOUND — please pick a fallback_\n\n")
                continue

            try:
                snippet = normalize(raw)
            except ValueError as e:
                # A cached payload that cannot be normalized is poisoned;
                # drop it so the next run re-fetches instead of failing forever.
                vpath.unlink(missing_ok=True)
                misses.append(f"{slot} <- {source}/{source_id} (parse: {e})")
                continue

            md_chunks.append(
                f"### {slot}\n{blurb}\n\n```svg\n{snippet}\n```\n\nSource: {attribution}\n\n"
            )

    md_chunks.append(
        "---\n\n## License attribution\n\n- **Tabler Icons** — MIT — "
        "https://github.com/tabler/tabler-icons\n- **Simple Icons** — CC0 — "
        "https://github.com/simple-icons/simple-icons\n- **Devicon** — MIT "
        "— https://github.com/devicons/devicon\n- **log-z/logos** — MIT — "
        "https://github.com/log-z/logos\n- **Project logos** — the Valkey "
        "(BSD-3-Clause) and Redpanda marks, from each project's own "
        "repository at a pinned commit; THIRD_PARTY_LICENSES.md says what "
        "each may be used for\n\nEvery other glyph in this gallery comes "
        "from one of those four libraries, whose licences permit "
        "redistribution, including in this repository's MIT-licensed "
        "source. Where no licence-clean brand mark exists (Apache Hop, "
        "Pentaho, Dagster, SAS, Stata), the component draws a generic "
        "glyph that says what the tool does.\n\nBrand logos retain their "
        "respective trademarks; an icon licence never grants trademark "
        "rights. This set is for documentation and illustrative use only.\n"
    )

    return md_chunks, misses


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args(argv)
    print("Building icon library…", file=sys.stderr)
    md_chunks, misses = build()

    MD_OUT.parent.mkdir(parents=True, exist_ok=True)
    MD_OUT.write_text("".join(md_chunks), encoding="utf-8", newline="\n")

    total = sum(len(items) for items in ICONS.values())
    print(f"\nDone. {total - len(misses)}/{total} fetched.", file=sys.stderr)
    print(f"  primitive-icons.md: {MD_OUT}", file=sys.stderr)
    if misses:
        print(f"\n  {len(misses)} miss(es) — review and pick fallbacks:", file=sys.stderr)
        for m in misses:
            print(f"    - {m}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
