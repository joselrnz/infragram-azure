"""A coverage diagram a cloud: one of each component the Terraform table
writes, placed where the table requires, wired where a wire is a rule.

The export's own test document. ``verify:terraform`` validates its skeleton
in both styles and the tests read it back through the import, so every row
of the tables -- not only what the templates happen to draw -- is written,
accepted by Terraform, and drawn back as the component it was.
"""

from __future__ import annotations

from typing import Any

from ..projects import CloudProject
from .mapping import PROVIDERS, load_mapping

__all__ = ["coverage_project"]

#: Components that sit in a public subnet; the others that need a subnet sit in a private one.
_PUBLIC = frozenset(
    {
        "elastic-load-balancing",
        "vpc-nat-gateway",
        "application-gateways",
        "bastions",
        "firewalls",
        "virtual-network-gateways",
        "load-balancers",
    }
)


def _element(provider: str, element_id: str, service_id: str) -> dict[str, Any]:
    return {
        "id": element_id,
        "name": element_id,
        "type": "service",
        "component": {
            "provider": provider,
            "service_id": service_id,
            "icon_ref": f"{provider}:{service_id}",
        },
        "attributes": {},
        "connections": [],
        "children": [],
    }


def _frame(
    provider: str, frame_id: str, name: str, kind: str, children: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "id": frame_id,
        "name": name,
        "type": kind,
        "attributes": {"editor_frame_group": provider},
        "connections": [],
        "children": children,
    }


def coverage_project(provider: str) -> CloudProject:
    """One of each component ``provider``'s table writes, where it requires."""
    if provider not in PROVIDERS:
        raise KeyError(f"no Terraform table for {provider!r}")
    table = load_mapping(provider)
    placed: dict[str, list[str]] = {"public": [], "private": [], "network": [], "region": []}
    for service_id, rule in table.components.items():
        if rule.plumbing == "node_pool":
            continue
        if rule.requires == "subnet":
            placed["public" if service_id in _PUBLIC else "private"].append(service_id)
        else:
            placed["network" if rule.requires == "network" else "region"].append(service_id)
    elements: dict[str, dict[str, Any]] = {}

    def made(service_id: str, suffix: str = "") -> dict[str, Any]:
        element = _element(provider, f"{service_id}{suffix}", service_id)
        elements[element["id"]] = element
        return element

    def frame(
        frame_id: str, name: str, kind: str, children: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return _frame(provider, frame_id, name, kind, children)

    if provider == "aws":
        top = frame(
            "aws-cloud",
            "AWS Cloud",
            "cloud",
            [
                frame(
                    "region",
                    "us-east-1",
                    "region",
                    [
                        *(made(s) for s in placed["region"]),
                        frame(
                            "vpc",
                            "VPC · 10.0.0.0/16",
                            "vpc",
                            [
                                frame(
                                    "az-a",
                                    "Availability Zone A",
                                    "zone",
                                    [
                                        frame(
                                            "public-a",
                                            "Public subnet · 10.0.0.0/24",
                                            "subnet-public",
                                            [made(s, "-a") for s in placed["public"]],
                                        ),
                                        frame(
                                            "private-a",
                                            "Private subnet · 10.0.1.0/24",
                                            "subnet-private",
                                            [made(s, "-a") for s in placed["private"]],
                                        ),
                                    ],
                                ),
                                frame(
                                    "az-b",
                                    "Availability Zone B",
                                    "zone",
                                    [
                                        frame(
                                            "public-b",
                                            "Public subnet · 10.0.2.0/24",
                                            "subnet-public",
                                            [],
                                        ),
                                        frame(
                                            "private-b",
                                            "Private subnet · 10.0.3.0/24",
                                            "subnet-private",
                                            [
                                                frame(
                                                    "sg-app",
                                                    "Security group · app",
                                                    "security-group",
                                                    [made("ec2", "-b")],
                                                )
                                            ],
                                        ),
                                    ],
                                ),
                                *(made(s) for s in placed["network"]),
                            ],
                        ),
                    ],
                )
            ],
        )
        wires = [
            ("users", "elastic-load-balancing-a", "HTTPS"),
            ("elastic-load-balancing-a", "ec2-a", "HTTP"),
            ("elastic-load-balancing-a", "ec2-b", "HTTP"),
            ("ec2-a", "rds-a", "SQL"),
            ("ec2-b", "aurora-a", "SQL"),
            ("ec2-a", "elasticache-a", "Redis"),
            ("ec2-a", "efs-a", "NFS"),
            ("fargate-a", "managed-streaming-for-apache-kafka-a", "Kafka"),
            ("ec2-a", "elastic-kubernetes-service-a", "HTTPS 443"),
        ]
    elif provider == "azure":
        top = frame(
            "subscription",
            "Subscription",
            "subscription",
            [
                frame(
                    "region",
                    "West Europe",
                    "region",
                    [
                        frame(
                            "rg",
                            "rg-coverage",
                            "resource-group",
                            [
                                *(made(s) for s in placed["region"]),
                                frame(
                                    "vnet",
                                    "VNet · 10.1.0.0/16",
                                    "network",
                                    [
                                        frame(
                                            "snet-public",
                                            "snet-public · 10.1.0.0/24",
                                            "subnet-public",
                                            [made(s) for s in placed["public"]],
                                        ),
                                        frame(
                                            "snet-app",
                                            "snet-app · 10.1.1.0/24",
                                            "subnet-private",
                                            [
                                                *(made(s) for s in placed["private"]),
                                                made("virtual-machine", "-2"),
                                                frame(
                                                    "aks",
                                                    "AKS cluster",
                                                    "cluster",
                                                    [made("kubernetes-services", "-pool")],
                                                ),
                                            ],
                                        ),
                                        *(made(s) for s in placed["network"]),
                                    ],
                                ),
                            ],
                        )
                    ],
                )
            ],
        )
        wires = [
            ("users", "virtual-machine", "HTTPS"),
            ("virtual-machine-2", "virtual-machine", "SSH 22"),
        ]
    else:
        top = frame(
            "project",
            "Project · coverage-project",
            "project",
            [
                frame(
                    "region",
                    "us-central1",
                    "region",
                    [
                        *(made(s) for s in placed["region"]),
                        frame(
                            "vpc",
                            "VPC network",
                            "vpc",
                            [
                                frame(
                                    "snet-app",
                                    "app · 10.20.1.0/24",
                                    "subnet-private",
                                    [
                                        *(made(s) for s in placed["private"]),
                                        made("compute-engine", "-2"),
                                    ],
                                ),
                                *(made(s) for s in placed["network"]),
                            ],
                        ),
                    ],
                )
            ],
        )
        wires = [
            ("users", "compute-engine", "HTTPS"),
            ("compute-engine-2", "compute-engine", "8080"),
        ]
    users: dict[str, Any] = {
        "id": "users",
        "name": "Users",
        "type": "service",
        "component": {
            "provider": "infragram",
            "service_id": "public-users",
            "icon_ref": "infragram:public-users",
        },
        "attributes": {},
        "connections": [],
        "children": [],
    }
    for source, target, label in wires:
        (users if source == "users" else elements[source])["connections"].append(
            {"target": target, "kind": "solid", "label": label}
        )
    return CloudProject.model_validate(
        {
            "schema_version": 2,
            "kind": "single-cloud",
            "slug": f"coverage-{provider}",
            "title": f"Every {provider} component the Terraform export writes",
            "description": "The export's test document: one of each component of the table, where it requires.",
            "providers": [{"id": provider, "enabled": True}],
            "default_library": provider,
            "topology": {
                "id": "root",
                "name": "coverage",
                "type": "group",
                "children": [users, top],
            },
        }
    )
