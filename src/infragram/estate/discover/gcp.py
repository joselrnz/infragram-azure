"""A live Google Cloud estate, read-only through the ``gcloud`` CLI.

Every call is a ``list`` on one project. What each returns is written as the
``google`` resource it would be, with the values the drawing reads: the VPC
network and subnetwork a resource sits in, its region, its size, an
instance's network tags and service accounts, and the firewall rules.
"""

from __future__ import annotations

from typing import Any

from ..link import link_by_value
from ..model import Estate, Found
from . import CallError, DiscoveryError, Runner, cli_runner, last_segment

__all__ = ["discover_gcp"]


class _Reader:
    def __init__(self, run: Runner, project: str) -> None:
        self.run = run
        self.project = project
        self.found: list[Found] = []
        self.notes: list[str] = []
        self.seen: set[str] = set()

    def call(self, *command: str) -> list[dict[str, Any]]:
        args = [*command, "--project", self.project, "--format", "json", "--quiet"]
        try:
            answer = self.run(args)
        except CallError as error:
            self.notes.append(f"not read: gcloud {' '.join(command)}: {error.message}")
            return []
        return answer if isinstance(answer, list) else []

    def add(
        self, kind: str, name: str, values: dict[str, Any], source: str, region: str | None
    ) -> None:
        address = f"{kind}.{name}"
        n = 2
        while address in self.seen:
            address = f"{kind}.{name}_{n}"
            n += 1
        self.seen.add(address)
        self.found.append(
            Found(
                address,
                kind,
                name,
                {"project": self.project, "name": name, **values},
                source=source,
                region=region,
            )
        )

    def read(self, regions: list[str]) -> None:
        for network in self.call("compute", "networks", "list"):
            self.add(
                "google_compute_network",
                network["name"],
                {"id": network.get("id"), "self_link": network.get("selfLink")},
                "gcloud compute networks list",
                None,
            )
        found_regions: list[str] = []
        for subnet in self.call("compute", "networks", "subnets", "list"):
            region = last_segment(subnet.get("region"))
            if region and region not in found_regions:
                found_regions.append(region)
            self.add(
                "google_compute_subnetwork",
                subnet["name"],
                {
                    "id": subnet.get("id"),
                    "self_link": subnet.get("selfLink"),
                    "network": subnet.get("network"),
                    "region": region,
                    "ip_cidr_range": subnet.get("ipCidrRange"),
                },
                "gcloud compute networks subnets list",
                region,
            )
        for instance in self.call("compute", "instances", "list"):
            zone = last_segment(instance.get("zone"))
            self.add(
                "google_compute_instance",
                instance["name"],
                {
                    "self_link": instance.get("selfLink"),
                    "zone": zone,
                    "machine_type": last_segment(instance.get("machineType")),
                    "tags": (instance.get("tags") or {}).get("items") or [],
                    "service_account": [
                        {"email": a.get("email")} for a in instance.get("serviceAccounts") or []
                    ],
                    "network_interface": [
                        {
                            "network": n.get("network"),
                            "subnetwork": n.get("subnetwork"),
                            "network_ip": n.get("networkIP"),
                        }
                        for n in instance.get("networkInterfaces", [])
                    ],
                },
                "gcloud compute instances list",
                zone.rsplit("-", 1)[0] if zone else None,
            )
        for rule in self.call("compute", "firewall-rules", "list"):
            # an allowed entry without ports allows every port, as Terraform's allow block
            self.add(
                "google_compute_firewall",
                rule["name"],
                {
                    "self_link": rule.get("selfLink"),
                    "network": rule.get("network"),
                    "direction": rule.get("direction"),
                    "disabled": bool(rule.get("disabled")),
                    "source_ranges": rule.get("sourceRanges") or [],
                    "source_tags": rule.get("sourceTags") or [],
                    "source_service_accounts": rule.get("sourceServiceAccounts") or [],
                    "target_tags": rule.get("targetTags") or [],
                    "target_service_accounts": rule.get("targetServiceAccounts") or [],
                    "allow": [
                        {"protocol": a.get("IPProtocol"), "ports": a.get("ports") or []}
                        for a in rule.get("allowed") or []
                    ],
                    "deny": [
                        {"protocol": d.get("IPProtocol"), "ports": d.get("ports") or []}
                        for d in rule.get("denied") or []
                    ],
                },
                "gcloud compute firewall-rules list",
                None,
            )
        for router in self.call("compute", "routers", "list"):
            region = last_segment(router.get("region"))
            self.add(
                "google_compute_router",
                router["name"],
                {
                    "self_link": router.get("selfLink"),
                    "network": router.get("network"),
                    "region": region,
                },
                "gcloud compute routers list",
                region,
            )
            for nat in router.get("nats", []) or []:
                self.add(
                    "google_compute_router_nat",
                    nat["name"],
                    {"router": router["name"], "region": region},
                    "gcloud compute routers list",
                    region,
                )
        for address in self.call("compute", "addresses", "list"):
            if address.get("region"):
                continue
            self.add(
                "google_compute_global_address",
                address["name"],
                {"self_link": address.get("selfLink"), "address": address.get("address")},
                "gcloud compute addresses list",
                None,
            )
        for cluster in self.call("container", "clusters", "list"):
            self.add(
                "google_container_cluster",
                cluster["name"],
                {
                    "self_link": cluster.get("selfLink"),
                    "location": cluster.get("location"),
                    "network": cluster.get("network"),
                    "subnetwork": cluster.get("subnetwork"),
                },
                "gcloud container clusters list",
                cluster.get("location"),
            )
        for database in self.call("sql", "instances", "list"):
            settings = database.get("settings") or {}
            private = (settings.get("ipConfiguration") or {}).get("privateNetwork")
            self.add(
                "google_sql_database_instance",
                database["name"],
                {
                    "self_link": database.get("selfLink"),
                    "region": database.get("region"),
                    "database_version": database.get("databaseVersion"),
                    "settings": [
                        {
                            "tier": settings.get("tier"),
                            "ip_configuration": [{"private_network": private}],
                        }
                    ],
                },
                "gcloud sql instances list",
                database.get("region"),
            )
        for service in self.call("run", "services", "list"):
            metadata = service.get("metadata") or {}
            region = (metadata.get("labels") or {}).get("cloud.googleapis.com/location")
            self.add(
                "google_cloud_run_v2_service",
                metadata.get("name") or service.get("name", "service"),
                {"location": region},
                "gcloud run services list",
                region,
            )
        for function in self.call("functions", "list"):
            name = last_segment(function.get("name")) or "function"
            self.add(
                "google_cloudfunctions2_function",
                name,
                {"runtime": function.get("runtime")},
                "gcloud functions list",
                None,
            )
        for bucket in self.call("storage", "buckets", "list"):
            self.add(
                "google_storage_bucket",
                bucket.get("name", "bucket"),
                {"location": bucket.get("location")},
                "gcloud storage buckets list",
                None,
            )
        for topic in self.call("pubsub", "topics", "list"):
            name = last_segment(topic.get("name")) or "topic"
            self.add(
                "google_pubsub_topic",
                name,
                {"id": topic.get("name")},
                "gcloud pubsub topics list",
                None,
            )
        for region in regions or found_regions:
            for cache in self.call("redis", "instances", "list", "--region", region):
                name = last_segment(cache.get("name")) or "redis"
                self.add(
                    "google_redis_instance",
                    name,
                    {
                        "tier": cache.get("tier"),
                        "authorized_network": cache.get("authorizedNetwork"),
                        "region": region,
                    },
                    "gcloud redis instances list",
                    region,
                )


def discover_gcp(
    *, project: str | None = None, regions: list[str] | None = None, runner: Runner | None = None
) -> Estate:
    """What ``project`` holds, as an estate."""
    run = runner or cli_runner("gcloud")
    chosen = project
    if not chosen:
        try:
            config = run(["config", "list", "--format", "json"]) or {}
        except CallError as error:
            raise DiscoveryError(
                f"the gcloud CLI cannot say its project: {error.message}"
            ) from error
        chosen = (config.get("core") or {}).get("project")
        if not chosen:
            raise DiscoveryError("name a project with --project (gcloud has none configured)")
    reader = _Reader(run, str(chosen))
    reader.read(list(regions or []))
    estate = Estate(
        f"Google Cloud project {chosen}",
        f"the Google Cloud project {chosen}, read-only",
        reader.found,
        reader.notes,
    )
    link_by_value(estate)
    return estate
