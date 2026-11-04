"""References read from values: an argument that holds another resource's id names it.

A state, a plan against existing resources and a live estate all carry ids
rather than expressions: a subnet's ``vpc_id`` is ``vpc-0a1b``, an Azure
NIC's subnet is a full resource id, a Google subnet's network a self link.
:func:`link_by_value` turns every such value into the reference a
configuration would have written, so one drawing step reads them all.
"""

from __future__ import annotations

from .model import Estate, walk_values

__all__ = ["link_by_value"]

#: The attributes that identify a resource: another resource holding one of
#: these values names it (a DNS alias holds a load balancer's ``dns_name``).
_IDENTITY = ("id", "arn", "self_link", "dns_name", "domain_name")
#: Arguments that name a resource by its plain name, and the types they name.
_BY_NAME = {
    "resource_group_name": ("azurerm_resource_group",),
    "virtual_network_name": ("azurerm_virtual_network",),
    "network_security_group_name": ("azurerm_network_security_group",),
    "network": ("google_compute_network",),
    "subnetwork": ("google_compute_subnetwork",),
    "cluster": ("google_container_cluster", "aws_ecs_cluster"),
    "cluster_name": ("aws_eks_cluster",),
    "function_name": ("aws_lambda_function",),
    "bucket": ("aws_s3_bucket",),
    "db_subnet_group_name": ("aws_db_subnet_group",),
    "subnet_group_name": ("aws_elasticache_subnet_group",),
    "router": ("google_compute_router",),
}


def _naming(path: str) -> bool:
    """A value that names or describes the resource itself: an IAM role's id
    is its name, and another resource called the same is not a reference."""
    return path in ("name", "identifier", "description", "display_name") or path.split(".", 1)[
        0
    ] in ("tags", "tags_all", "labels")


def _key(value: str) -> str:
    # Azure resource ids differ in case between APIs (resourceGroups,
    # resourcegroups), and a Google self link is its id behind the API root.
    if value.startswith("/subscriptions/"):
        return value.lower()
    if value.startswith("https://www.googleapis.com/compute/") and "/projects/" in value:
        return "projects/" + value.split("/projects/", 1)[1]
    return value


def link_by_value(estate: Estate) -> None:
    """Add to every resource the references its values hold."""
    index: dict[str, str] = {}
    for found in estate.resources:
        for attribute in _IDENTITY:
            value = found.values.get(attribute)
            if isinstance(value, str) and len(value) > 3:
                index.setdefault(_key(value), found.address)
    names: dict[tuple[str, str], str] = {}
    for argument, types in _BY_NAME.items():
        for found in estate.of_type(*types):
            name = found.values.get("name")
            if isinstance(name, str) and name:
                names.setdefault((argument, name.lower()), found.address)
    for found in estate.resources:
        for path, value in walk_values(found.values):
            if not isinstance(value, str) or path in _IDENTITY or _naming(path):
                continue
            leaf = path.rsplit(".", 1)[-1]
            target = index.get(_key(value)) or names.get((leaf, value.lower()))
            if target is None and "/" in value and leaf in ("network", "subnetwork"):
                # a Google network named by a partial path: its last segment
                target = names.get((leaf, value.rsplit("/", 1)[-1].lower()))
            if target is None or target == found.address:
                continue
            known = found.references.setdefault(path, [])
            if target not in known:
                known.append(target)
