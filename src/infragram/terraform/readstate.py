"""A plan or a state, read into an :class:`~infragram.estate.Estate`.

Section 3 of ``references/terraform.md``: when Terraform has said what the
configuration is, that is the truth, and the text is only what it omits.

- ``terraform show -json <plan>``: ``planned_values`` gives every instance,
  modules from a registry or git included, with the values known before
  apply; ``configuration`` gives what each argument names, followed through
  module inputs and outputs.
- ``terraform show -json`` of a state: ``values`` gives every instance with
  its real ids, and the ids give the references (:mod:`infragram.estate.link`).
- A state file itself (``terraform.tfstate``, format 4): the same, read
  from its ``resources``.

Nothing is run: the user makes the JSON (``terraform show -json plan.out >
plan.json``), or hands over the state they have.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from ..estate.azapi import as_azurerm
from ..estate.link import link_by_value
from ..estate.model import Estate, Found

__all__ = ["StateError", "read_show_json"]


class StateError(ValueError):
    """The file is not a plan, a state, or ``terraform show -json`` of one."""


_INDEXES = re.compile(r"\[[^\]]*\]")


def _module_resources(module: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield from module.get("resources", []) or []
    for child in module.get("child_modules", []) or []:
        yield from _module_resources(child)


def _found(item: dict[str, Any], source: str) -> Found:
    values = item.get("values") or {}
    return Found(
        address=str(item["address"]),
        type=str(item["type"]),
        name=str(item.get("name", "")),
        values=values if isinstance(values, dict) else {},
        source=source,
        region=_region(values if isinstance(values, dict) else {}),
        mode=str(item.get("mode", "managed")),
    )


def _region(values: dict[str, Any]) -> str | None:
    for key in ("region", "location"):
        value = values.get(key)
        if isinstance(value, str) and value:
            return value
    zone = values.get("availability_zone") or values.get("zone")
    if isinstance(zone, str) and len(zone) > 1:
        return zone[:-1] if zone[-1].isalpha() and zone[-2].isdigit() else zone.rsplit("-", 1)[0]
    arn = values.get("arn")
    if isinstance(arn, str) and arn.count(":") >= 5 and arn.split(":")[3]:
        return arn.split(":")[3]
    return None


# ------------------------------------------------------------ plan configuration
def _resource_address(reference: str) -> str | None:
    """``aws_vpc.main.id`` -> ``aws_vpc.main``; ``data.x.y.z`` -> ``data.x.y``."""
    parts = reference.split(".")
    if parts[0] in ("var", "local", "each", "count", "path", "self", "terraform", "module"):
        return None
    head = parts[:3] if parts[0] == "data" else parts[:2]
    if len(head) < (3 if parts[0] == "data" else 2):
        return None
    return ".".join(head)


class _Configuration:
    """What each argument names, from a plan's ``configuration``."""

    def __init__(self) -> None:
        #: config address (no instance keys) -> argument path -> addresses
        self.references: dict[str, dict[str, list[str]]] = {}
        #: module call address -> output -> addresses
        self.outputs: dict[str, dict[str, list[str]]] = {}

    def qualify(
        self,
        references: list[str],
        prefix: str,
        inputs: dict[str, list[str]],
        calls: dict[str, dict[str, list[str]]],
    ) -> list[str]:
        out: list[str] = []
        # Terraform lists a reference from most to least specific
        # (aws_vpc.this[0].id, aws_vpc.this[0], aws_vpc.this): the first says it
        chosen = [
            r
            for r in references
            if not any(o != r and o.startswith(r) and o[len(r)] in ".[" for o in references)
        ]
        for reference in chosen:
            parts = reference.split(".")
            if parts[0] == "var" and len(parts) > 1:
                out += inputs.get(_INDEXES.sub("", parts[1]), [])
            elif parts[0] == "module" and len(parts) > 2:
                name, bracket, index = parts[2].partition("[")
                named = calls.get(f"{prefix}module.{_INDEXES.sub('', parts[1])}", {}).get(name, [])
                if (
                    bracket
                    and len(named) == 1
                    and not named[0].endswith("]")
                    and index[:-1].isdigit()
                ):
                    # [0] of an output naming one counted resource is its [0]
                    named = [f"{named[0]}[{index[:-1]}]"]
                out += named
            else:
                address = _resource_address(reference)
                if address is not None:
                    out.append(prefix + address)
        return list(dict.fromkeys(out))

    def expressions(
        self,
        expressions: Any,
        path: str,
        into: dict[str, list[str]],
        prefix: str,
        inputs: dict[str, list[str]],
        calls: dict[str, dict[str, list[str]]],
    ) -> None:
        if isinstance(expressions, list):
            for item in expressions:
                self.expressions(item, path, into, prefix, inputs, calls)
            return
        if not isinstance(expressions, dict):
            return
        if "references" in expressions and isinstance(expressions["references"], list):
            named = self.qualify(expressions["references"], prefix, inputs, calls)
            if named:
                into.setdefault(path, [])
                into[path] += [a for a in named if a not in into[path]]
            return
        for key, value in expressions.items():
            self.expressions(value, f"{path}.{key}" if path else key, into, prefix, inputs, calls)

    def module(self, module: dict[str, Any], prefix: str, inputs: dict[str, list[str]]) -> None:
        calls: dict[str, dict[str, list[str]]] = {}
        # the calls first: a resource may name a module's output
        for name, call in (module.get("module_calls") or {}).items():
            child_inputs: dict[str, list[str]] = {}
            for argument, expression in (call.get("expressions") or {}).items():
                found: dict[str, list[str]] = {}
                self.expressions(expression, argument, found, prefix, inputs, calls)
                child_inputs[argument] = [a for named in found.values() for a in named]
            child_prefix = f"{prefix}module.{name}."
            self.module(call.get("module") or {}, child_prefix, child_inputs)
            calls[f"{prefix}module.{name}"] = self.outputs.get(child_prefix, {})
        for resource in module.get("resources") or []:
            address = prefix + str(resource.get("address", ""))
            into: dict[str, list[str]] = {}
            self.expressions(resource.get("expressions") or {}, "", into, prefix, inputs, calls)
            if resource.get("depends_on"):
                into["depends_on"] = self.qualify(
                    list(resource["depends_on"]), prefix, inputs, calls
                )
            self.references[address] = into
        outputs: dict[str, list[str]] = {}
        for name, output in (module.get("outputs") or {}).items():
            found = {}
            self.expressions(output.get("expression") or {}, "value", found, prefix, inputs, calls)
            outputs[name] = [a for named in found.values() for a in named]
        self.outputs[prefix] = outputs


def _from_plan(document: dict[str, Any], source: str) -> tuple[list[Found], list[str]]:
    notes: list[str] = []
    root = (document.get("planned_values") or {}).get("root_module") or {}
    resources = [_found(item, source) for item in _module_resources(root)]
    prior = ((document.get("prior_state") or {}).get("values") or {}).get("root_module") or {}
    known = {found.address for found in resources}
    for item in _module_resources(prior):
        # data sources and resources the plan leaves untouched live only here
        if item.get("address") not in known:
            resources.append(_found(item, source))
    # What the plan does to each resource (changes.py): a resource it
    # destroys lives in prior_state alone, read above, and is marked here.
    from ..models.changes import action_of

    actions = {
        str(item.get("address")): action_of((item.get("change") or {}).get("actions") or ())
        for item in document.get("resource_changes") or []
        if isinstance(item, dict)
    }
    drifted = {
        str(item.get("address"))
        for item in document.get("resource_drift") or []
        if isinstance(item, dict)
        and (item.get("change") or {}).get("actions") not in (None, ["no-op"])
    }
    for found in resources:
        found.change = actions.get(found.address) or ("drift" if found.address in drifted else None)
    configuration = _Configuration()
    configuration.module((document.get("configuration") or {}).get("root_module") or {}, "", {})
    for found in resources:
        named = configuration.references.get(_INDEXES.sub("", found.address))
        if named:
            found.references = {path: list(addresses) for path, addresses in named.items()}
    # The provider's own region, when the plan's configuration states it, is
    # where a resource that names none lives.
    providers = (document.get("configuration") or {}).get("provider_config") or {}
    for key, provider in providers.items():
        region = (((provider or {}).get("expressions") or {}).get("region") or {}).get(
            "constant_value"
        )
        if isinstance(region, str) and "." not in key:
            for found in resources:
                if found.region is None and found.type.startswith(f"{provider.get('name', key)}_"):
                    found.region = region
    return resources, notes


# ------------------------------------------------------------ states
def _from_values(document: dict[str, Any], source: str) -> list[Found]:
    root = (document.get("values") or {}).get("root_module") or {}
    return [_found(item, source) for item in _module_resources(root)]


def _from_state_file(document: dict[str, Any], source: str) -> list[Found]:
    out: list[Found] = []
    for resource in document.get("resources") or []:
        module = resource.get("module")
        mode = resource.get("mode", "managed")
        base = (
            (f"{module}." if module else "")
            + ("data." if mode == "data" else "")
            + f"{resource.get('type')}.{resource.get('name')}"
        )
        for instance in resource.get("instances") or []:
            key = instance.get("index_key")
            suffix = "" if key is None else (f"[{key}]" if isinstance(key, int) else f'["{key}"]')
            values = instance.get("attributes") or {}
            out.append(
                Found(
                    address=base + suffix,
                    type=str(resource.get("type")),
                    name=str(resource.get("name")),
                    values=values,
                    source=source,
                    region=_region(values),
                    mode=mode,
                )
            )
    return out


#: File names Terraform and its users give every plan and state, which say
#: nothing about the estate: a diagram titled "plan" or "terraform" is named
#: after its folder instead.
_GENERIC = frozenset(
    {"plan", "tfplan", "terraform", "state", "tfstate", "show", "default", "main", "out"}
)


def _title(path: Path) -> str:
    stem = path.name.split(".")[0]
    folder = path.resolve().parent.name
    return folder if stem.casefold() in _GENERIC and folder else path.stem


def read_show_json(path: Path, *, title: str | None = None) -> Estate:
    """A plan or a state, as ``terraform show -json`` writes it, or a state file."""
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise StateError(f"{path}: {error}") from error
    if not isinstance(document, dict):
        raise StateError(f"{path}: not a Terraform plan or state")
    source = path.name
    notes: list[str] = []
    if "planned_values" in document:
        resources, notes = _from_plan(document, source)
        origin = f"the Terraform plan {path.name}"
    elif "values" in document:
        resources = _from_values(document, source)
        origin = f"the Terraform state {path.name}"
    elif document.get("version") == 4 and "resources" in document:
        resources = _from_state_file(document, source)
        origin = f"the Terraform state file {path.name}"
    else:
        raise StateError(
            f"{path}: not a plan or a state; make one with "
            "`terraform show -json plan.out > plan.json`, or pass terraform.tfstate"
        )
    estate = Estate(title or _title(path), origin, resources, notes)
    as_azurerm(estate)
    link_by_value(estate)
    return estate
