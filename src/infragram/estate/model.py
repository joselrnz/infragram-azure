"""What an import found: resources, where each came from, what each names.

Every reader fills the same record, in Terraform's own terms, so one drawing
step serves them all: a configuration's files (``infragram.terraform``), a
plan or a state (``terraform show -json``), or a live estate read through the
provider's CLI (``infragram.estate.discover``). A resource is its Terraform
type and address, the attribute values the reader could know, and, per
argument, the addresses that argument names.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Estate", "Found", "base_address", "walk_values"]

_INDEX = re.compile(r"\[[^\]]*\]$")


def base_address(address: str) -> str:
    """``module.net.aws_subnet.private[1]`` -> ``module.net.aws_subnet.private``."""
    return _INDEX.sub("", address)


@dataclass
class Found:
    """One resource instance."""

    #: Where Terraform keeps it: ``module.net.aws_subnet.private[1]``.
    address: str
    #: Its type: ``aws_subnet``.
    type: str
    #: Its name in the configuration (``private``), or the cloud's own id.
    name: str
    #: The attribute values the reader knows; nested blocks are lists of dicts,
    #: as ``terraform show -json`` writes them.
    values: dict[str, Any] = field(default_factory=dict)
    #: Argument path (``vpc_config.subnet_ids``) -> the addresses it names.
    references: dict[str, list[str]] = field(default_factory=dict)
    #: Where it was read: ``network.tf:12``, ``terraform.tfstate``, a CLI call.
    source: str = ""
    #: The region or location it lives in, when known.
    region: str | None = None
    #: ``managed`` for a resource, ``data`` for a data source.
    mode: str = "managed"
    #: What a plan does to it (``create``, ``update``, ``replace``,
    #: ``delete``), or None for a state or a resource the plan leaves be.
    change: str | None = None

    @property
    def base(self) -> str:
        return base_address(self.address)

    @property
    def provider(self) -> str:
        """The provider the type belongs to: ``aws``, ``azurerm``, ``google``."""
        return self.type.split("_", 1)[0]

    def value(self, *path: str) -> Any:
        """A nested value, looking through one-item block lists: ``value("vpc_config", "subnet_ids")``."""
        current: Any = self.values
        for key in path:
            if isinstance(current, list) and len(current) == 1:
                current = current[0]
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def names(self, *arguments: str) -> list[str]:
        """The addresses the given arguments name, anywhere in the resource
        (``subnet_id`` matches ``subnet_id`` and ``vpc_config.subnet_id``)."""
        wanted = set(arguments)
        out: list[str] = []
        for path, addresses in self.references.items():
            if path.rsplit(".", 1)[-1] in wanted:
                out += [a for a in addresses if a not in out]
        return out


@dataclass
class Estate:
    """Everything one import read."""

    title: str
    #: Where it was read from, in a sentence: the folder and variable files,
    #: the plan, the account and regions.
    origin: str
    resources: list[Found] = field(default_factory=list)
    #: What the reader could not follow, for the report.
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._index: dict[str, list[Found]] = {}
        self._indexed = -1

    def _addresses(self) -> dict[str, list[Found]]:
        # rebuilt when a reader has added resources since the last lookup
        if self._indexed != len(self.resources):
            index: dict[str, list[Found]] = {}
            for found in self.resources:
                index.setdefault(found.address, []).append(found)
                if found.base != found.address:
                    index.setdefault(found.base, []).append(found)
            self._index, self._indexed = index, len(self.resources)
        return self._index

    def resolve(self, address: str) -> list[Found]:
        """The resources an address names: one instance, or every instance of
        an address given without its index. An instance of a resource drawn
        once, its count known only to a plan, is that one; ``[i]`` of a
        resource repeated over a map is its ``i``-th instance in key order, as
        a list an output makes of them holds it."""
        index = self._addresses()
        found = index.get(address)
        if found is None and address != base_address(address):
            instances = index.get(base_address(address), [])
            found = [f for f in instances if f.address == f.base]
            number = re.fullmatch(r".*\[(\d+)\]", address)
            keyed = sorted(
                (f for f in instances if f.address.endswith('"]')), key=lambda f: f.address
            )
            if not found and number and int(number.group(1)) < len(keyed):
                found = [keyed[int(number.group(1))]]
        return list(found or [])

    def targets(self, found: Found, *arguments: str) -> list[Found]:
        """The resources the given arguments of ``found`` name, in order."""
        out: list[Found] = []
        for address in found.names(*arguments):
            for target in self.resolve(address):
                if target is not found and target not in out:
                    out.append(target)
        return out

    def of_type(self, *types: str) -> list[Found]:
        return [found for found in self.resources if found.type in types]


def walk_values(value: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """Every scalar in a values tree with its argument path; list positions
    are not part of the path (``ingress.cidr_blocks``)."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from walk_values(item, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for item in value:
            yield from walk_values(item, path)
    else:
        yield path, value
