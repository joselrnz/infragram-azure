"""How an icon id becomes a Python class name.

One rule, used by both the icon registry and the node-class generator, so
``icons.VirtualMachine`` and ``nodes.azure.compute.VirtualMachine`` can never
drift apart.

Plain title casing mangles the acronyms that fill cloud catalogs -- ``rds``
becomes ``Rds``, ``db`` becomes ``Db``. :data:`UPPER_WORDS` is the list of
tokens that stay uppercase instead, the same idea as the generator config in
mingrammer/diagrams.
"""

from __future__ import annotations

import re

__all__ = ["UPPER_WORDS", "TITLE_WORDS", "class_name"]

SPLIT = re.compile(r"[-_\s.]+")

#: Whole tokens that are acronyms, not words. Matched case-insensitively.
UPPER_WORDS = frozenset(
    {
        # general computing
        "ai",
        "api",
        "apis",
        "bi",
        "cdn",
        "cli",
        "cpu",
        "css",
        "csv",
        "db",
        "dns",
        "dr",
        "ftp",
        "gpu",
        "html",
        "http",
        "https",
        "hpc",
        "iam",
        "id",
        "ide",
        "io",
        "iot",
        "ip",
        "ipv4",
        "ipv6",
        "json",
        "jwt",
        "ldap",
        "llm",
        "lts",
        "ml",
        "mq",
        "nat",
        "nfs",
        "nlp",
        "os",
        "pdf",
        "php",
        "png",
        "pop3",
        "qos",
        "ram",
        "rdp",
        "rest",
        "rpc",
        "sdk",
        "sla",
        "smb",
        "smtp",
        "sql",
        "ssd",
        "ssh",
        "ssl",
        "sso",
        "svg",
        "tcp",
        "tls",
        "tpu",
        "ttl",
        "udp",
        "ui",
        "uri",
        "url",
        "uuid",
        "ux",
        "vm",
        "vms",
        "vpc",
        "vpn",
        "waf",
        "wan",
        "xml",
        "yaml",
        # vendors and platforms
        "aws",
        "gcp",
        "ibm",
        "sap",
        "oci",
        "k8s",
        "acr",
        "aks",
        "eks",
        "gke",
        "ec2",
        "ecs",
        "efs",
        "rds",
        "s3",
        "sns",
        "sqs",
        # data and ops
        "etl",
        "elt",
        "olap",
        "oltp",
        "crm",
        "erp",
        "kpi",
        "cicd",
        "ci",
        "cd",
        "nosql",
        "rdbms",
        "saas",
        "paas",
        "iaas",
        "faas",
        "dbms",
        # networking
        "bgp",
        "lan",
        "vlan",
        "mpls",
        "lb",
        "nic",
        "tor",
        "fqdn",
        "dhcp",
        "ntp",
        "wlan",
        "nac",
        "isp",
        "ipam",
        "vxlan",
        "dmz",
        "oob",
        "dx",
        "ids",
        "ips",
        # datacenter, storage, security and operations
        "san",
        "nas",
        "ups",
        "pdu",
        "kvm",
        "hsm",
        "pki",
        "dlp",
        "mfa",
        "vdi",
        "ztna",
        "siem",
        "edr",
        "cctv",
        "pbx",
        "cdc",
        "esb",
        "bpm",
        "itsm",
        "cmdb",
        "mft",
        "psp",
        "ibx",
        "acl",
        # OT and IoT
        "plc",
        "scada",
        "hmi",
        "rfid",
        "nfc",
        "ble",
        "lpwan",
        "qr",
    }
)

#: Tokens with a fixed mixed-case spelling.
TITLE_WORDS = {
    "iot": "IoT",
    "ios": "iOS",
    "macos": "macOS",
    "graphql": "GraphQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongodb": "MongoDB",
    "openai": "OpenAI",
    "openshift": "OpenShift",
    "sdwan": "SDWAN",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "nodejs": "NodeJS",
    "devops": "DevOps",
    "mlops": "MLOps",
    "vnet": "VNet",
    "vnets": "VNets",
    "dotnet": "DotNet",
    "digitalocean": "DigitalOcean",
    "onprem": "OnPrem",
    "elasticsearch": "ElasticSearch",
}


def _token(word: str) -> str:
    lowered = word.lower()
    if lowered in TITLE_WORDS:
        return TITLE_WORDS[lowered]
    if lowered in UPPER_WORDS:
        return lowered.upper()
    return word[:1].upper() + word[1:] if word else word


def class_name(slug: str) -> str:
    """``virtual-machine`` -> ``VirtualMachine``, ``azure-cosmos-db`` -> ``AzureCosmosDB``.

    Returns "" when the slug cannot express a Python identifier, which the
    caller is expected to treat as "skip this icon".
    """
    parts = [part for part in SPLIT.split(slug) if part]
    name = "".join(_token("".join(ch for ch in part if ch.isalnum())) for part in parts)
    if not name or not name.isascii():
        return ""
    if name[0].isdigit():
        name = "N" + name
    return name if name.isidentifier() else ""
