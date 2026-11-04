"""Draw the service tiles for the libraries whose vendors publish no icon pack we may redistribute.

Cloudflare, OVHcloud, Vultr, Akamai Cloud (Linode), VMware vSphere, Proxmox VE and Equinix
offer no service-icon pack with a redistribution grant, so this script draws a
set for each -- a Tabler glyph (MIT, cached under scripts/vendor/icons/tabler)
in white on a rounded tile of the vendor's colour -- and writes it as a vendor
collection under
skills/infragram-azure/assets/icons/vendors/<library>/ with a catalog.json in
the same shape as the imported packs. The tiles are this project's own artwork
(license basis ``original-artwork``); they are not the vendor's icons, and the
vendor's name and colour are used only to say which product a card stands for.

Four generic ids (entry-service, app-service, object-store-service,
database-service) are tiles in every set but Cloudflare's, so a document that
names them opens and draws in any of these libraries.

usage: vendor-tiles.py            # draw every set
       vendor-tiles.py --check    # verify the shipped sets match this table
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
TABLER = REPO / "scripts" / "vendor" / "icons" / "tabler"
VENDORS = REPO / "skills" / "infragram-azure" / "assets" / "icons" / "vendors"
LF = "\n"


@dataclass(frozen=True)
class Tile:
    id: str
    name: str
    category: str
    glyph: str
    aliases: tuple[str, ...] = ()


def tile(id: str, name: str, category: str, glyph: str, *aliases: str) -> Tile:
    return Tile(id, name, category, glyph, tuple(aliases))


#: library -> (tile colour, source url, the tiles)
SETS: dict[str, tuple[str, str, tuple[Tile, ...]]] = {
    "cloudflare": (
        "#f38020",
        "https://developers.cloudflare.com/",
        (
            tile("dns", "Cloudflare DNS", "networking", "world", "authoritative dns", "dns"),
            tile("cdn", "Cloudflare CDN", "networking", "cloud-network", "cache", "edge cache"),
            tile(
                "waf",
                "Web Application Firewall",
                "security",
                "shield-check",
                "waf",
                "managed rules",
            ),
            tile(
                "ddos-protection", "DDoS Protection", "security", "shield-lock", "ddos", "anti-ddos"
            ),
            tile(
                "load-balancing",
                "Load Balancing",
                "networking",
                "arrows-split",
                "load balancer",
                "steering",
            ),
            tile(
                "tunnel", "Cloudflare Tunnel", "networking", "route", "cloudflared", "argo tunnel"
            ),
            tile(
                "zero-trust-access", "Zero Trust Access", "security", "id-badge", "ztna", "access"
            ),
            tile(
                "zero-trust-gateway",
                "Zero Trust Gateway",
                "security",
                "cloud-lock",
                "secure web gateway",
                "swg",
            ),
            tile(
                "warp-client", "WARP Client", "security", "device-laptop", "warp", "device client"
            ),
            tile("r2", "Cloudflare R2", "storage", "bucket", "object storage", "s3-compatible"),
            tile("d1", "Cloudflare D1", "databases", "database", "serverless sql", "sqlite"),
            tile("kv", "Workers KV", "databases", "key", "key-value", "kv"),
            tile(
                "durable-objects",
                "Durable Objects",
                "databases",
                "cube",
                "stateful",
                "coordination",
            ),
            tile(
                "hyperdrive",
                "Hyperdrive",
                "databases",
                "database-export",
                "connection pool",
                "postgres accelerator",
            ),
            tile(
                "vectorize",
                "Vectorize",
                "ai-machine-learning",
                "grid-dots",
                "vector database",
                "embeddings",
            ),
            tile(
                "ai-gateway",
                "AI Gateway",
                "ai-machine-learning",
                "hierarchy-2",
                "llm gateway",
                "ai proxy",
            ),
            tile("queues", "Cloudflare Queues", "integration", "stack-2", "queue", "message queue"),
            tile(
                "email-routing",
                "Email Routing",
                "integration",
                "mail-forward",
                "email",
                "mail routing",
            ),
            tile("stream", "Cloudflare Stream", "web", "device-tv", "video", "streaming"),
            tile("images", "Cloudflare Images", "web", "file", "image resizing", "image hosting"),
            tile("registrar", "Cloudflare Registrar", "networking", "tag", "domain", "registrar"),
            tile("spectrum", "Spectrum", "networking", "arrows-exchange", "tcp proxy", "udp proxy"),
            tile("magic-wan", "Magic WAN", "networking", "topology-star", "wan", "sd-wan"),
            tile("magic-transit", "Magic Transit", "networking", "network", "bgp", "network ddos"),
            tile(
                "argo-smart-routing",
                "Argo Smart Routing",
                "networking",
                "route-2",
                "smart routing",
                "argo",
            ),
            tile("rate-limiting", "Rate Limiting", "security", "gauge", "rate limit", "throttling"),
            tile(
                "api-shield",
                "API Shield",
                "security",
                "braces",
                "api security",
                "schema validation",
            ),
            tile(
                "bot-management", "Bot Management", "security", "spider", "bots", "bot fight mode"
            ),
            tile("turnstile", "Turnstile", "security", "robot", "captcha", "challenge"),
            tile("logpush", "Logpush", "analytics", "file-text", "logs", "log export"),
            tile("web-analytics", "Web Analytics", "analytics", "chart-line", "analytics", "rum"),
            tile("workers-cron", "Cron Triggers", "compute", "clock", "scheduled worker", "cron"),
            tile(
                "browser-rendering",
                "Browser Rendering",
                "compute",
                "world-www",
                "headless browser",
                "puppeteer",
            ),
        ),
    ),
    "ovhcloud": (
        "#000e9c",
        "https://www.ovhcloud.com/",
        (
            tile(
                "entry-service",
                "OVHcloud Load Balancer",
                "networking",
                "arrows-split",
                "load balancer",
                "octavia",
            ),
            tile(
                "app-service",
                "Public Cloud Instance",
                "compute",
                "server",
                "instance",
                "public cloud",
            ),
            tile(
                "object-store-service",
                "Object Storage",
                "storage",
                "bucket",
                "s3-compatible",
                "swift",
            ),
            tile(
                "database-service",
                "Managed Database",
                "databases",
                "database",
                "postgresql",
                "mysql",
                "mongodb",
            ),
            tile(
                "bare-metal",
                "Bare Metal Server",
                "compute",
                "server-2",
                "dedicated server",
                "bare metal",
            ),
            tile("vps", "VPS", "compute", "cube", "virtual private server"),
            tile("gpu-instance", "GPU Instance", "compute", "cpu", "gpu", "cloud gpu"),
            tile(
                "hosted-private-cloud",
                "Hosted Private Cloud",
                "compute",
                "stack-3",
                "vmware",
                "private cloud",
            ),
            tile(
                "managed-kubernetes",
                "Managed Kubernetes Service",
                "containers",
                "hexagon",
                "kubernetes",
                "mks",
            ),
            tile(
                "managed-registry",
                "Managed Private Registry",
                "containers",
                "package",
                "harbor",
                "container registry",
            ),
            tile("block-storage", "Block Storage", "storage", "device-floppy", "volume", "cinder"),
            tile("cold-archive", "Cold Archive", "storage", "archive", "archive", "tape"),
            tile("backup", "Backup and Snapshot", "storage", "refresh", "snapshot", "backup"),
            tile("nas-ha", "NAS-HA", "storage", "file", "nfs", "network attached storage"),
            tile("vrack", "vRack", "networking", "topology-star", "private network", "vlan"),
            tile(
                "public-network",
                "Public Network",
                "networking",
                "world",
                "floating ip",
                "additional ip",
            ),
            tile("domains-dns", "Domains and DNS", "networking", "world-www", "dns", "domain"),
            tile("anti-ddos", "Anti-DDoS", "security", "shield-lock", "ddos", "vac"),
            tile(
                "network-firewall",
                "Network Firewall",
                "security",
                "wall",
                "firewall",
                "edge firewall",
            ),
            tile(
                "iam", "Identity and Access Management", "identity", "user-shield", "iam", "users"
            ),
            tile("kms", "Key Management Service", "security", "key", "kms", "secrets"),
            tile("web-hosting", "Web Hosting", "web", "world-www", "shared hosting", "cms"),
            tile(
                "data-processing",
                "Data Processing",
                "analytics",
                "chart-line",
                "spark",
                "analytics",
            ),
            tile(
                "logs-data-platform",
                "Logs Data Platform",
                "analytics",
                "list-search",
                "logs",
                "opensearch",
            ),
            tile(
                "ai-notebooks",
                "AI Notebooks and Training",
                "ai-machine-learning",
                "robot",
                "notebooks",
                "training",
            ),
            tile(
                "ai-deploy",
                "AI Deploy",
                "ai-machine-learning",
                "rocket",
                "inference",
                "model serving",
            ),
        ),
    ),
    "vultr": (
        "#007bfc",
        "https://www.vultr.com/",
        (
            tile(
                "entry-service",
                "Vultr Load Balancer",
                "networking",
                "arrows-split",
                "load balancer",
            ),
            tile(
                "app-service",
                "Cloud Compute Instance",
                "compute",
                "server",
                "instance",
                "vc2",
                "cloud compute",
            ),
            tile(
                "object-store-service",
                "Vultr Object Storage",
                "storage",
                "bucket",
                "s3-compatible",
                "object storage",
            ),
            tile(
                "database-service",
                "Managed Database",
                "databases",
                "database",
                "postgresql",
                "mysql",
                "redis",
            ),
            tile("bare-metal", "Bare Metal", "compute", "server-2", "dedicated", "bare metal"),
            tile("cloud-gpu", "Cloud GPU", "compute", "cpu", "gpu", "accelerated"),
            tile(
                "optimized-cloud-compute",
                "Optimized Cloud Compute",
                "compute",
                "cpu-2",
                "dedicated cpu",
                "high frequency",
            ),
            tile(
                "kubernetes-engine",
                "Vultr Kubernetes Engine",
                "containers",
                "hexagon",
                "vke",
                "kubernetes",
            ),
            tile(
                "container-registry",
                "Container Registry",
                "containers",
                "package",
                "registry",
                "images",
            ),
            tile("block-storage", "Block Storage", "storage", "device-floppy", "volume", "nvme"),
            tile("file-system", "Vultr File System", "storage", "file", "nfs", "shared storage"),
            tile("snapshots", "Snapshots", "storage", "refresh", "snapshot", "image"),
            tile("backups", "Automatic Backups", "storage", "archive", "backup"),
            tile("vpc", "VPC", "networking", "topology-star", "private network", "vpc 2.0"),
            tile("reserved-ip", "Reserved IP", "networking", "tag", "floating ip", "elastic ip"),
            tile("dns", "Vultr DNS", "networking", "world-www", "dns", "domain"),
            tile(
                "direct-connect",
                "Direct Connect",
                "networking",
                "plug-connected",
                "private link",
                "cross connect",
            ),
            tile("firewall", "Vultr Firewall", "security", "wall", "firewall group", "firewall"),
            tile("ddos-protection", "DDoS Protection", "security", "shield-lock", "ddos"),
            tile(
                "serverless-inference",
                "Serverless Inference",
                "ai-machine-learning",
                "robot",
                "inference",
                "llm",
            ),
            tile(
                "marketplace-app",
                "Marketplace App",
                "web",
                "rocket",
                "one-click app",
                "marketplace",
            ),
        ),
    ),
    "akamai": (
        "#0096d6",
        "https://www.linode.com/",
        (
            tile(
                "entry-service",
                "NodeBalancer",
                "networking",
                "arrows-split",
                "load balancer",
                "nodebalancer",
            ),
            tile(
                "app-service",
                "Linode Compute Instance",
                "compute",
                "server",
                "linode",
                "instance",
                "shared cpu",
            ),
            tile(
                "object-store-service",
                "Object Storage",
                "storage",
                "bucket",
                "s3-compatible",
                "object storage",
            ),
            tile(
                "database-service",
                "Managed Database",
                "databases",
                "database",
                "postgresql",
                "mysql",
            ),
            tile("dedicated-cpu", "Dedicated CPU Instance", "compute", "cpu-2", "dedicated cpu"),
            tile("gpu-instance", "GPU Instance", "compute", "cpu", "gpu", "rtx"),
            tile("bare-metal", "Bare Metal", "compute", "server-2", "dedicated server"),
            tile("lke", "Linode Kubernetes Engine", "containers", "hexagon", "lke", "kubernetes"),
            tile("block-storage", "Block Storage", "storage", "device-floppy", "volume"),
            tile("images", "Images", "storage", "disc", "custom image", "golden image"),
            tile("backups", "Backups", "storage", "archive", "backup", "snapshot"),
            tile("vpc", "VPC", "networking", "topology-star", "private network", "vlan"),
            tile("cloud-firewall", "Cloud Firewall", "security", "wall", "firewall"),
            tile("dns-manager", "DNS Manager", "networking", "world-www", "dns", "domain"),
            tile(
                "edge-dns",
                "Akamai Edge DNS",
                "networking",
                "world",
                "authoritative dns",
                "edge dns",
            ),
            tile("cdn", "Akamai CDN", "networking", "cloud-network", "ion", "content delivery"),
            tile(
                "app-api-protector",
                "App and API Protector",
                "security",
                "shield-check",
                "waf",
                "api protection",
            ),
            tile("bot-manager", "Bot Manager", "security", "spider", "bots"),
            tile(
                "prolexic",
                "Prolexic DDoS Protection",
                "security",
                "shield-lock",
                "ddos",
                "prolexic",
            ),
            tile(
                "guardicore",
                "Guardicore Segmentation",
                "security",
                "layers-intersect",
                "microsegmentation",
                "zero trust",
            ),
            tile(
                "enterprise-application-access",
                "Enterprise Application Access",
                "security",
                "id-badge",
                "ztna",
                "eaa",
            ),
            tile("edgeworkers", "EdgeWorkers", "compute", "bolt", "edge compute", "edge functions"),
            tile("edgekv", "EdgeKV", "databases", "key", "key-value", "edge kv"),
            tile("datastream", "DataStream", "analytics", "file-text", "logs", "log streaming"),
        ),
    ),
    "vmware": (
        "#0091da",
        "https://www.vmware.com/products/vsphere.html",
        (
            tile(
                "entry-service",
                "NSX Load Balancer",
                "networking",
                "arrows-split",
                "load balancer",
                "nsx alb",
                "avi",
            ),
            tile(
                "app-service",
                "vSphere Virtual Machine",
                "compute",
                "cube",
                "vm",
                "virtual machine",
                "guest",
            ),
            tile(
                "object-store-service",
                "vSAN Datastore",
                "storage",
                "stack-2",
                "vsan",
                "hyperconverged",
            ),
            tile(
                "database-service",
                "Database Virtual Machine",
                "databases",
                "database",
                "database vm",
                "sql vm",
            ),
            tile("esxi-host", "ESXi Host", "compute", "server", "esxi", "hypervisor", "host"),
            tile(
                "vcenter", "vCenter Server", "devops", "server-cog", "vcenter", "vcsa", "management"
            ),
            tile(
                "vsphere-cluster", "vSphere Cluster", "compute", "stack-3", "cluster", "ha cluster"
            ),
            tile(
                "resource-pool", "Resource Pool", "compute", "box-multiple", "resource pool", "vapp"
            ),
            tile("vm-template", "VM Template", "compute", "file", "template", "content library"),
            tile("vmotion", "vMotion", "compute", "arrows-exchange", "live migration", "vmotion"),
            tile(
                "ha-drs",
                "HA and DRS",
                "compute",
                "refresh",
                "high availability",
                "drs",
                "scheduler",
            ),
            tile(
                "datastore",
                "VMFS Datastore",
                "storage",
                "device-floppy",
                "datastore",
                "vmfs",
                "nfs datastore",
            ),
            tile("storage-policy", "Storage Policy", "storage", "clipboard-list", "spbm", "policy"),
            tile(
                "nsx-manager", "NSX Manager", "networking", "topology-star", "nsx", "sdn", "overlay"
            ),
            tile(
                "nsx-edge", "NSX Edge Gateway", "networking", "router", "tier-0", "tier-1", "edge"
            ),
            tile(
                "distributed-switch",
                "vSphere Distributed Switch",
                "networking",
                "switch-2",
                "vds",
                "port group",
            ),
            tile(
                "distributed-firewall",
                "NSX Distributed Firewall",
                "security",
                "wall",
                "dfw",
                "microsegmentation",
            ),
            tile(
                "tanzu",
                "Tanzu Kubernetes Grid",
                "containers",
                "hexagon",
                "tkg",
                "kubernetes",
                "supervisor",
            ),
            tile("horizon", "Horizon Desktop", "compute", "device-desktop", "vdi", "horizon"),
            tile(
                "aria-operations",
                "Aria Operations",
                "analytics",
                "chart-line",
                "vrealize operations",
                "vrops",
            ),
            tile(
                "aria-automation",
                "Aria Automation",
                "devops",
                "robot",
                "vrealize automation",
                "vra",
            ),
            tile(
                "site-recovery",
                "Site Recovery Manager",
                "storage",
                "archive",
                "srm",
                "disaster recovery",
            ),
            tile(
                "cloud-foundation", "Cloud Foundation", "compute", "layers-intersect", "vcf", "sddc"
            ),
        ),
    ),
    "proxmox": (
        "#e57000",
        "https://www.proxmox.com/en/products/proxmox-virtual-environment/overview",
        (
            tile(
                "entry-service",
                "Reverse Proxy VM",
                "networking",
                "arrows-split",
                "haproxy",
                "reverse proxy",
                "ingress",
            ),
            tile("app-service", "QEMU Virtual Machine", "compute", "cube", "vm", "kvm", "qemu"),
            tile(
                "object-store-service",
                "Ceph Storage",
                "storage",
                "stack-2",
                "ceph",
                "rbd",
                "cephfs",
            ),
            tile(
                "database-service",
                "Database Container",
                "databases",
                "database",
                "lxc database",
                "postgresql",
            ),
            tile("pve-node", "PVE Node", "compute", "server", "node", "host", "pve"),
            tile("pve-cluster", "PVE Cluster", "compute", "stack-3", "cluster", "corosync"),
            tile("datacenter", "Datacenter", "compute", "sitemap", "datacenter", "pve datacenter"),
            tile(
                "lxc-container", "LXC Container", "containers", "package", "lxc", "ct", "container"
            ),
            tile("vm-template", "VM and CT Template", "compute", "file", "template", "clone"),
            tile("ha-group", "HA Group", "compute", "refresh", "high availability", "ha"),
            tile(
                "quorum-device",
                "Corosync Quorum Device",
                "compute",
                "hierarchy-2",
                "qdevice",
                "quorum",
            ),
            tile("zfs-pool", "ZFS Pool", "storage", "device-floppy", "zfs", "zpool"),
            tile(
                "local-storage",
                "Local and LVM Storage",
                "storage",
                "disc",
                "local-lvm",
                "directory storage",
            ),
            tile("nfs-storage", "NFS and SMB Storage", "storage", "file", "nfs", "cifs", "smb"),
            tile(
                "iso-images",
                "ISO Images and Templates",
                "storage",
                "device-sd-card",
                "iso",
                "templates",
            ),
            tile("backup-server", "Proxmox Backup Server", "storage", "archive", "pbs", "backup"),
            tile(
                "mail-gateway",
                "Proxmox Mail Gateway",
                "security",
                "mail-cog",
                "pmg",
                "mail gateway",
            ),
            tile("linux-bridge", "Linux Bridge", "networking", "switch-2", "vmbr", "bridge"),
            tile("sdn-zone", "SDN Zone", "networking", "topology-star", "sdn", "vnet", "vxlan"),
            tile("bond", "Network Bond", "networking", "arrows-left-right", "bond", "lacp"),
            tile("firewall", "PVE Firewall", "security", "wall", "firewall", "security group"),
            tile(
                "two-factor",
                "Two-Factor Authentication",
                "identity",
                "fingerprint",
                "totp",
                "2fa",
                "realm",
            ),
            tile("api-token", "API Token", "identity", "key", "api", "token"),
        ),
    ),
    "equinix": (
        "#ed2224",
        "https://docs.equinix.com/",
        (
            tile(
                "entry-service",
                "Network Edge Load Balancer",
                "networking",
                "arrows-split",
                "load balancer",
                "adc",
                "vnf load balancer",
            ),
            tile(
                "app-service",
                "Colocated Server",
                "compute",
                "server",
                "server",
                "colo server",
                "customer equipment",
            ),
            tile(
                "object-store-service",
                "Colocated Storage Array",
                "storage",
                "device-floppy",
                "storage array",
                "san",
                "nas",
            ),
            tile(
                "database-service",
                "Colocated Database Server",
                "databases",
                "database",
                "database server",
                "database",
            ),
            tile(
                "fabric-port",
                "Fabric Port",
                "networking",
                "plug",
                "port",
                "fabric port",
                "physical port",
            ),
            tile(
                "fabric-virtual-connection",
                "Fabric Virtual Connection",
                "networking",
                "route",
                "virtual connection",
                "evpl",
                "layer 2 connection",
            ),
            tile(
                "fabric-cloud-router",
                "Fabric Cloud Router",
                "networking",
                "cloud-network",
                "fcr",
                "cloud router",
                "layer 3 routing",
            ),
            tile(
                "fabric-cloud-connection",
                "Fabric Cloud Connection",
                "networking",
                "cloud",
                "cloud onramp",
                "direct connect",
                "expressroute",
                "partner interconnect",
            ),
            tile(
                "service-profile",
                "Fabric Service Profile",
                "networking",
                "id-badge",
                "service profile",
                "provider profile",
                "marketplace",
            ),
            tile(
                "service-token",
                "Fabric Service Token",
                "security",
                "key",
                "service token",
                "a-side token",
                "z-side token",
            ),
            tile(
                "metro-connect",
                "Metro Connect",
                "networking",
                "route-2",
                "metro connect",
                "dark fiber",
                "wavelength",
            ),
            tile(
                "internet-exchange",
                "Equinix Internet Exchange",
                "networking",
                "arrows-exchange",
                "ix",
                "ixp",
                "peering",
            ),
            tile(
                "internet-access",
                "Equinix Internet Access",
                "networking",
                "world",
                "eia",
                "ip transit",
                "internet",
            ),
            tile(
                "precision-time",
                "Equinix Precision Time",
                "networking",
                "clock",
                "ntp",
                "ptp",
                "time sync",
            ),
            tile(
                "network-edge-device",
                "Network Edge Virtual Device",
                "networking",
                "server-cog",
                "network edge",
                "vnf",
                "virtual device",
            ),
            tile(
                "network-edge-router",
                "Network Edge Router",
                "networking",
                "router",
                "virtual router",
                "vrouter",
            ),
            tile(
                "network-edge-firewall",
                "Network Edge Firewall",
                "security",
                "wall",
                "virtual firewall",
                "ngfw",
            ),
            tile(
                "network-edge-sdwan",
                "Network Edge SD-WAN",
                "networking",
                "topology-star-ring",
                "sd-wan",
                "sdwan edge",
            ),
            tile(
                "device-link-group",
                "Device Link Group",
                "networking",
                "topology-star",
                "device link",
                "dlg",
            ),
            tile(
                "acl-template",
                "ACL Template",
                "security",
                "shield-check",
                "acl",
                "access control list",
            ),
            tile(
                "iam",
                "Identity and Access Management",
                "identity",
                "user-shield",
                "iam",
                "portal users",
                "roles",
            ),
            tile(
                "ibx-data-center",
                "IBX Data Center",
                "colocation",
                "grid-dots",
                "ibx",
                "international business exchange",
                "data center",
            ),
            tile(
                "cage",
                "Cage",
                "colocation",
                "lock-square-rounded",
                "colocation cage",
                "private cage",
                "suite",
            ),
            tile("cabinet", "Cabinet", "colocation", "stack-3", "rack", "colocation cabinet"),
            tile(
                "cross-connect",
                "Cross Connect",
                "colocation",
                "plug-connected",
                "cross connect",
                "patch",
                "fiber",
            ),
            tile("power-circuit", "Power Circuit", "colocation", "bolt", "power", "pdu", "circuit"),
            tile(
                "smart-hands",
                "Smart Hands",
                "colocation",
                "user-check",
                "remote hands",
                "smart hands",
                "on-site support",
            ),
        ),
    ),
}

PLACEHOLDER_IDS = ("entry-service", "app-service", "object-store-service", "database-service")


def glyph_paths(name: str) -> str:
    """The drawing elements of a cached Tabler outline icon, without its wrapper."""
    source = TABLER / f"{name}.svg"
    if not source.is_file():
        raise SystemExit(f"no cached Tabler glyph named {name!r} ({source})")
    body = re.sub(r"<!--.*?-->", "", source.read_text(encoding="utf-8"), flags=re.S)
    elements = re.findall(r"<(?:path|circle|rect|line|polyline|polygon|ellipse)\b[^>]*/>", body)
    if not elements:
        raise SystemExit(f"Tabler glyph {name!r} has no drawing elements")
    return "".join(re.sub(r"\s+", " ", element).replace(" />", "/>") for element in elements)


def tile_svg(colour: str, glyph: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" aria-hidden="true">'
        f'<rect x="3" y="3" width="58" height="58" rx="13" fill="{colour}"/>'
        '<g transform="translate(11 11) scale(1.75)" fill="none" stroke="#ffffff" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{glyph_paths(glyph)}</g></svg>\n'
    )


def catalog_for(library: str) -> tuple[dict, dict[str, str]]:
    """The catalog document and every tile's SVG text, keyed by relative file."""
    colour, source_url, tiles = SETS[library]
    ids = [t.id for t in tiles]
    if len(ids) != len(set(ids)):
        raise SystemExit(f"{library}: duplicate tile ids")
    if library != "cloudflare" and any(p not in ids for p in PLACEHOLDER_IDS):
        raise SystemExit(f"{library}: the four placeholder ids must stay")
    files: dict[str, str] = {}
    icons = []
    for t in tiles:
        rel = f"{t.category}/{t.id}.svg"
        svg = tile_svg(colour, t.glyph)
        files[rel] = svg
        icons.append(
            {
                "id": t.id,
                "name": t.name,
                "aliases": list(t.aliases),
                "category": t.category,
                "file": rel,
                "source_path": f"drawn: Tabler glyph {t.glyph} on {colour}",
                "sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
            }
        )
    catalog = {
        "schema_version": 1,
        "collection": f"vendors/{library}",
        "generated_by": "scripts/build/vendor-tiles.py (this project's own tiles: a Tabler glyph on the vendor's colour)",
        "source": {
            "url": source_url,
            "release": "drawn for Infragram; not the vendor's artwork. Glyphs: Tabler Icons (MIT).",
            "terms": "https://github.com/tabler/tabler-icons/blob/main/LICENSE",
        },
        "counts": {"icons": len(icons)},
        "icons": icons,
    }
    return catalog, files


def write_all() -> int:
    total = 0
    for library in SETS:
        catalog, files = catalog_for(library)
        root = VENDORS / library
        for rel, svg in files.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(svg, encoding="utf-8", newline=LF)
        stale = {p.relative_to(root).as_posix() for p in root.rglob("*.svg")} - set(files)
        for rel in sorted(stale):
            (root / rel).unlink()
        (root / "catalog.json").write_text(
            json.dumps(catalog, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline=LF
        )
        total += len(files)
        print(f"{library}: {len(files)} tiles" + (f", {len(stale)} stale removed" if stale else ""))
    print(f"OK: {total} tiles across {len(SETS)} libraries")
    return 0


def check() -> int:
    problems = []
    for library in SETS:
        catalog, files = catalog_for(library)
        root = VENDORS / library
        shipped = root / "catalog.json"
        if not shipped.is_file():
            problems.append(f"{library}: no catalog.json")
            continue
        if json.loads(shipped.read_text(encoding="utf-8")) != catalog:
            problems.append(f"{library}: catalog.json differs from the table")
        for rel, svg in files.items():
            path = root / rel
            if not path.is_file() or path.read_text(encoding="utf-8") != svg:
                problems.append(f"{library}: {rel} differs")
    if problems:
        print("FAIL vendor tiles:\n  " + "\n  ".join(problems[:20]))
        return 1
    print(
        f"OK vendor tiles: {sum(len(s[2]) for s in SETS.values())} tiles across {len(SETS)} libraries match the table"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="verify the shipped sets match this table"
    )
    options = parser.parse_args(argv)
    return check() if options.check else write_all()


if __name__ == "__main__":
    sys.exit(main())
