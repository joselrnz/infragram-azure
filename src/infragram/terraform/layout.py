"""A plan laid out the way a Terraform repository is: modules and environments.

::

    <slug>-terraform/
    ├── README.md
    ├── .gitignore
    ├── modules/                 one module a concern: network, security, compute...
    │   └── <concern>/           main.tf  variables.tf  outputs.tf  versions.tf  README.md
    └── environments/            one composition an environment, each its own state
        ├── dev/                 main.tf  variables.tf  outputs.tf  locals.tf  providers.tf
        └── prod/                versions.tf  backend.tf  terraform.tfvars.example

The walk (:mod:`.emit`) writes every block into one namespace, each filed
under its concern. This module cuts that namespace into modules, as
HashiCorp's standard module structure and its style guide lay them out:

- **A module a concern** (``modules/network``, ``modules/compute``), holding
  that concern's blocks; a diagram on several clouds has a folder a cloud
  (``modules/aws/network``). A module configures no provider: it declares
  the ones it needs, and the aliases it is handed.
- **What one module reads of another** is an output of the one and a
  variable of the other, and the environment passes it across:
  ``vpc_id = module.network.vpc_id``. A variable of the configuration is a
  variable of each module that reads it; the name and tags every resource
  carries are the ``name`` and ``tags`` inputs.
- **Each environment** is the same composition of the modules, with its own
  state and its own values: ``dev`` and ``prod``.

Variables and outputs are in alphabetical order, a variable's arguments type
first, as the style guide asks.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import Field

from .emit import FOLDERS, MISSING, Plan, Variable, _words, join_words, value_name
from .hcl import BLANK, Attr, Bare, Block, Comment, Raw, quote, render
from .mapping import load_modules, required_terraform
from .model import Record

__all__ = ["ENVIRONMENTS", "configuration_root", "environment_folders", "render_layout"]

#: The environments every skeleton composes: the same modules, their own state.
ENVIRONMENTS = ("dev", "prod")
#: Where each provider's state is usually kept.
_BACKENDS = {"aws": "s3", "azure": "azurerm", "gcp": "gcs"}
_CLOUDS = {"aws": "AWS", "azure": "Azure", "gcp": "Google Cloud"}
_PROVIDER_ORDER = ("aws", "azure", "gcp")
#: What each module folder holds, as its README and the environment say.
FOLDER_TITLES = {
    "foundation": "the resource groups and project APIs everything else sits in or needs",
    "network": "the networks, their subnets, gateways and routes",
    "security": "security groups and their rules, firewalls and guards",
    "secrets": "secrets and keys",
    "compute": "servers, scale sets, functions and app services",
    "containers": "Kubernetes clusters, container services and registries",
    "database": "managed databases and caches",
    "storage": "buckets, file systems, vaults and backups",
    "messaging": "queues, topics, streams and hubs",
    "analytics": "query engines, stream jobs and data explorers",
    "loadbalancer": "load balancers, their target groups and listeners",
    "edge": "CDNs, API gateways, certificates and the other ways in",
    "dns": "hosted zones and resolvers",
    "monitoring": "logs, metrics, traces and audit trails",
}
#: A network module's lists of subnets, as the plain style names them.
_SIDES = {
    "private_subnets": "private_subnet_ids",
    "public_subnets": "public_subnet_ids",
    "database_subnets": "database_subnet_ids",
}


def concern_title(concern: str) -> str:
    """A module folder as a heading says it: ``Load balancer``, ``DNS``."""
    return {"loadbalancer": "Load balancer", "dns": "DNS"}.get(concern, concern.title())


#: What a module output that is a list is called, among the registry modules'.
_LIST_OUTPUTS = frozenset(
    {
        "private_subnets",
        "public_subnets",
        "database_subnets",
        "azs",
        "natgw_ids",
        "private_subnets_cidr_blocks",
        "public_subnets_cidr_blocks",
        "subnet_ids",
        "ids",
    }
)
#: What a resource attribute that is a list is called, among those one module reads of another.
_LIST_ATTRIBUTES = frozenset(
    {"address_prefixes", "address_space", "ip_addresses", "private_ip_addresses"}
)
_NAME = r"[A-Za-z_][A-Za-z0-9_-]*"
_REST = r"((?:\[[^\[\]]*\]|\.[A-Za-z_][A-Za-z0-9_-]*)*)"
_VAR = re.compile(rf"(?<![\w.])var\.({_NAME})")
_LOCAL = re.compile(rf"(?<![\w.])local\.({_NAME})")
#: A template's interpolation, not a ``$${`` written as text.
_INTERPOLATION = re.compile(r"(?<!\$)\$\{([^{}]*)\}")
#: The locals every configuration has, and what a module takes them as.
_BASE_LOCALS = {
    "name": (
        "string",
        "The name every resource's name starts with: the project and the environment.",
    ),
    "tags": ("map(string)", "The tags every resource carries."),
    "labels": ("map(string)", "The labels every resource carries."),
}


class Folder(Record):
    """One module: the blocks of one concern on one cloud."""

    key: str
    provider: str
    concern: str
    path: str = ""
    call: str = ""
    items: list[object] = Field(default_factory=list)
    #: variable name -> (type, description, sensitive, the value the environment passes)
    inputs: dict[str, tuple[str, str, bool, object]] = Field(default_factory=dict)
    #: output name -> (value, description, sensitive)
    outputs: dict[str, tuple[object, str, bool]] = Field(default_factory=dict)
    #: the data sources it reads, copied in
    data: list[object] = Field(default_factory=list)
    #: the provider configurations it is handed: (provider name, alias or None)
    configurations: set[tuple[str, str | None]] = Field(default_factory=set)
    #: the other modules it waits for
    waits: list[str] = Field(default_factory=list)
    #: the registry modules its blocks call, keys of modules.json
    registry: list[str] = Field(default_factory=list)


class _Layout:
    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.variables = dict(plan.root.variables)
        providers = sorted(
            {key.split("/")[0] for key in plan.root.files if not key.startswith("_")},
            key=lambda p: _PROVIDER_ORDER.index(p) if p in _PROVIDER_ORDER else 9,
        )
        self.several = len(providers) > 1
        self.folders: dict[str, Folder] = {}
        for key in sorted(
            (k for k in plan.root.files if not k.startswith("_") and plan.root.files[k]),
            key=self.order,
        ):
            provider, concern = key.split("/", 1)
            path = f"modules/{provider}/{concern}" if self.several else f"modules/{concern}"
            call = f"{provider}_{concern}" if self.several else concern
            self.folders[key] = Folder(
                key=key,
                provider=provider,
                concern=concern,
                path=path,
                call=call,
                items=list(plan.root.files[key]),
            )
        #: address -> the folder that writes it
        self.owner: dict[str, str] = {}
        #: data source address -> its block
        self.data: dict[str, Block] = {}
        self.table = load_modules().modules
        #: module address -> the registry module it calls
        self.called: dict[str, str] = {}
        for key, folder in self.folders.items():
            for item in folder.items:
                address = self.address(item)
                if address is not None:
                    self.owner[address] = key
                if isinstance(item, Block) and item.type == "module":
                    source = self.source(item)
                    found = next((k for k, m in self.table.items() if m.source == source), None)
                    if found is not None:
                        self.called[f"module.{item.labels[0]}"] = found
                        if found not in folder.registry:
                            folder.registry.append(found)
        for item in plan.root.files.get("_data", []):
            address = self.address(item)
            if address is not None and isinstance(item, Block):
                self.data[address] = item
        # the Google APIs are turned on first: every other Google module waits for them
        foundation = self.folders.get("gcp/foundation")
        if foundation is not None and any(
            isinstance(item, Block) and item.labels[:1] == ("google_project_service",)
            for item in foundation.items
        ):
            for folder in self.folders.values():
                if folder.provider == "gcp" and folder is not foundation:
                    folder.waits.append(foundation.call)
        known = sorted([*self.owner, *self.data], key=len, reverse=True)
        self.reference = (
            re.compile(
                rf"(?<![\w.])({'|'.join(re.escape(a) for a in known)})(?![A-Za-z0-9_-]){_REST}"
            )
            if known
            else None
        )
        #: (owner folder, expression) -> the output that gives it
        self.exports: dict[tuple[str, str], str] = {}
        #: the data sources the environment reads (its locals')
        self.environment_data: list[str] = []

    # ------------------------------------------------------------ reading blocks
    @staticmethod
    def order(key: str) -> tuple[int, int]:
        provider, concern = key.split("/", 1)
        return (
            FOLDERS.index(concern) if concern in FOLDERS else len(FOLDERS),
            _PROVIDER_ORDER.index(provider) if provider in _PROVIDER_ORDER else 9,
        )

    @staticmethod
    def address(item: object) -> str | None:
        if not isinstance(item, Block):
            return None
        if item.type == "resource" and len(item.labels) == 2:
            return f"{item.labels[0]}.{item.labels[1]}"
        if item.type == "data" and len(item.labels) == 2:
            return f"data.{item.labels[0]}.{item.labels[1]}"
        if item.type == "module" and item.labels:
            return f"module.{item.labels[0]}"
        return None

    @staticmethod
    def source(block: Block) -> str:
        for item in block.body:
            if isinstance(item, Attr) and item.name == "source" and isinstance(item.value, str):
                return item.value
        return ""

    # ------------------------------------------------------------ names
    def export_name(self, owner: str, address: str, rest: str) -> str:
        """What an output giving ``address`` + ``rest`` is called: ``vpc_id``,
        ``private_subnet_ids``, ``web_security_group_id``."""
        attributes = re.findall(rf"\.({_NAME})", rest)
        splat = "[*]" in rest
        if address.startswith("module."):
            label = address[len("module.") :]
            output = "_".join(attributes) or "outputs"
            if len(attributes) == 1 and not rest.endswith("]") and attributes[0] in _SIDES:
                # a network module's list of one side's subnets
                name = _SIDES[attributes[0]]
            else:
                if label.endswith("_sg"):
                    label = f"{label[:-3]}_security_group"
                    output = output.removeprefix("security_group_")
                name = join_words(label, output)
        else:
            kind, own = address.split(".", 1)
            base = self.plan.nouns.get(address) or (
                own if own != "main" else kind.split("_", 1)[-1]
            )
            name = value_name(base, kind, attributes[-1] if attributes else "", many=splat)
        taken = {out for (folder, _expr), out in self.exports.items() if folder == owner}
        wanted, n = name, 2
        while name in taken:
            name, n = f"{wanted}_{n}", n + 1
        return name

    def seed(self) -> None:
        """The environment's outputs name the module outputs that give them:
        ``alb_dns_name = module.loadbalancer.alb_dns_name``."""
        if self.reference is None:
            return
        for name, output in self.plan.root.outputs.items():
            if not isinstance(output.value, Raw):
                continue
            match = self.reference.fullmatch(output.value.text)
            if match is None or match.group(1) not in self.owner:
                continue
            owner, expression = self.owner[match.group(1)], output.value.text
            taken = {out for (folder, _expr), out in self.exports.items() if folder == owner}
            if (owner, expression) not in self.exports and name not in taken:
                self.exports[(owner, expression)] = name
                value = Raw(self.rewrite_text(expression, self.folders[owner]))
                self.folders[owner].outputs[name] = (
                    value,
                    output.description,
                    self.sensitive(match.group(1), match.group(2)),
                )

    def export_type(self, address: str, rest: str) -> str:
        if not rest:
            return "any"
        if "[*]" in rest:
            return "list(string)"
        last = re.findall(rf"\.({_NAME})", rest)[-1:]
        if (
            last
            and not rest.endswith("]")
            and (
                last[0] in _LIST_ATTRIBUTES
                or (address.startswith("module.") and last[0] in _LIST_OUTPUTS)
            )
        ):
            return "list(string)"
        return "string"

    def describe(self, address: str, rest: str) -> str:
        """An output's description: what it gives, of which element."""
        attributes = re.findall(rf"\.({_NAME})", rest)
        if len(attributes) == 1 and attributes[0] in _SIDES and not rest.endswith("]"):
            side = attributes[0].split("_")[0]
            return f"The ids of the {side} subnets, one an availability zone."
        label = self.plan.labels.get(address) or address
        what = _words(attributes[-1]) if attributes else "whole"
        if "[*]" in rest:
            what = f"{what}s" if not what.endswith("s") else what
        return f"The {what} of {label}."

    def sensitive(self, address: str, rest: str) -> bool:
        key = self.called.get(address)
        if key is None:
            return False
        first = re.findall(rf"\.({_NAME})", rest)[:1]
        return bool(first) and first[0] in self.table[key].sensitive

    def export(self, owner: str, address: str, rest: str) -> str:
        """The output of ``owner`` that gives ``address`` + ``rest``, made once."""
        expression = f"{address}{rest}"
        key = (owner, expression)
        if key not in self.exports:
            name = self.export_name(owner, address, rest)
            self.exports[key] = name
            # the output reads it in its own module's terms: a variable, not a local
            value = Raw(self.rewrite_text(expression, self.folders[owner]))
            self.folders[owner].outputs[name] = (
                value,
                self.describe(address, rest),
                self.sensitive(address, rest),
            )
        return self.exports[key]

    # ------------------------------------------------------------ rewriting
    def rewrite_text(self, text: str, folder: Folder | None) -> str:
        """An expression as the module (``folder``) or the environment (None) reads it."""
        if self.reference is not None:
            text = self.reference.sub(lambda match: self.reference_in(match, folder), text)
        if folder is not None:
            text = _VAR.sub(lambda match: self.variable_in(match.group(1), folder), text)
            text = _LOCAL.sub(lambda match: self.local_in(match.group(1), folder), text)
        return text

    def reference_in(self, match: re.Match[str], folder: Folder | None) -> str:
        address, rest = match.group(1), match.group(2)
        if address in self.data:
            if folder is None:
                if address not in self.environment_data:
                    self.environment_data.append(address)
            elif self.data[address] not in folder.data:
                folder.data.append(self.data[address])
                for item in self.data[address].body:
                    if isinstance(item, Attr):
                        self.configuration(self.data[address], item, folder)
            return match.group(0)
        owner = self.owner[address]
        if folder is not None and owner == folder.key:
            return match.group(0)
        # an instance picked by the reader's own count or key: the whole of them crosses
        crosses, kept = (address, rest) if not re.search(r"count\.|each\.", rest) else (address, "")
        if kept != rest:
            output = self.export(owner, crosses, "")
            tail = rest
        else:
            output = self.export(owner, crosses, rest)
            tail = ""
        value = Raw(f"module.{self.folders[owner].call}.{output}")
        if folder is None:
            return f"{value.text}{tail}"
        name = output
        description = self.folders[owner].outputs[output][1]
        kind = self.export_type(crosses, "" if tail else rest)
        existing = folder.inputs.get(name)
        if existing is not None and existing[3] != value:
            name = f"{self.folders[owner].concern}_{output}"
        folder.inputs.setdefault(
            name, (kind, description, self.folders[owner].outputs[output][2], value)
        )
        return f"var.{name}{tail}"

    def variable_in(self, name: str, folder: Folder) -> str:
        variable = self.variables.get(name)
        if variable is not None:
            folder.inputs.setdefault(
                name,
                (
                    variable.type,
                    variable.description or f"The {_words(name)}.",
                    variable.sensitive,
                    Raw(f"var.{name}"),
                ),
            )
        return f"var.{name}"

    def local_in(self, name: str, folder: Folder) -> str:
        kind, description = _BASE_LOCALS.get(
            name, ("any", f"The {_words(name)} the environment works out.")
        )
        if name == "azs" or name.endswith("_azs"):
            kind, description = (
                "list(string)",
                "The availability zones a tier spreads across, one subnet each.",
            )
        elif name.endswith("_subnet_names"):
            kind, description = "map(string)", "The name of each subnet of the network, by its key."
        folder.inputs.setdefault(name, (kind, description, False, Raw(f"local.{name}")))
        return f"var.{name}"

    def rewrite(self, value: object, folder: Folder | None) -> object:
        if isinstance(value, Raw):
            return Raw(self.rewrite_text(value.text, folder))
        if isinstance(value, str):
            return _INTERPOLATION.sub(
                lambda m: "${" + self.rewrite_text(m.group(1), folder) + "}", value
            )
        if isinstance(value, list):
            return [self.rewrite(item, folder) for item in value]
        if isinstance(value, dict):
            return type(value)({key: self.rewrite(item, folder) for key, item in value.items()})
        if isinstance(value, Attr):
            return Attr(value.name, self.rewrite(value.value, folder))
        if isinstance(value, Block):
            body: list[object] = []
            for item in value.body:
                if (
                    isinstance(item, Attr)
                    and item.name == "depends_on"
                    and isinstance(item.value, list)
                    and folder is not None
                ):
                    kept = [dep for dep in item.value if not self.elsewhere(dep, folder)]
                    if kept:
                        body.append(Attr("depends_on", kept))
                    elif body and body[-1] is BLANK:
                        body.pop()
                    continue
                if isinstance(item, Attr) and folder is not None:
                    self.configuration(value, item, folder)
                body.append(self.rewrite(item, folder))
            return Block(value.type, value.labels, body)
        return value

    def elsewhere(self, dependency: object, folder: Folder) -> bool:
        """A ``depends_on`` entry on another module's block: the module waits
        for that module instead."""
        text = dependency.text if isinstance(dependency, Raw) else str(dependency)
        owner = self.owner.get(text)
        if owner is None or owner == folder.key:
            return False
        if self.folders[owner].call not in folder.waits:
            folder.waits.append(self.folders[owner].call)
        return True

    def configuration(self, block: Block, attr: Attr, folder: Folder) -> None:
        """The provider configurations a block names: the module is handed them."""
        if (
            block.type in ("resource", "data")
            and attr.name == "provider"
            and isinstance(attr.value, Raw)
        ):
            name, _, alias = attr.value.text.partition(".")
            folder.configurations.add((name, alias or None))
        if block.type == "module" and attr.name == "providers" and isinstance(attr.value, dict):
            for value in attr.value.values():
                if isinstance(value, Raw):
                    name, _, alias = value.text.partition(".")
                    folder.configurations.add((name, alias or None))

    # ------------------------------------------------------------ the modules
    def modules(self) -> dict[str, str]:
        self.seed()
        rewritten: dict[str, list[object]] = {}
        for key, folder in self.folders.items():
            rewritten[key] = [self.rewrite(item, folder) for item in folder.items]
        # the environment's outputs are read last: every export they need is made
        self.outputs = {
            name: (self.rewrite(output.value, None), output.description, output.sensitive)
            for name, output in self.plan.root.outputs.items()
        }
        for value, _description, sensitive in self.outputs.values():
            if sensitive and isinstance(value, Raw):
                found = re.fullmatch(rf"module\.({_NAME})\.({_NAME})", value.text)
                if found is None:
                    continue
                owner = next((f for f in self.folders.values() if f.call == found.group(1)), None)
                if owner is not None and found.group(2) in owner.outputs:
                    out = owner.outputs[found.group(2)]
                    owner.outputs[found.group(2)] = (out[0], out[1], True)
        files: dict[str, str] = {}
        for key, folder in self.folders.items():
            files.update(self.module_files(folder, rewritten[key]))
        return files

    def entries_for(self, folder: Folder) -> list[dict[str, Any]]:
        """The providers a module needs: its cloud's, and its registry modules' companions."""
        entries = []
        own = self.plan.providers.get(folder.provider)
        if own is not None:
            entries.append(own)
        called = {name for key in folder.registry for name in self.table[key].providers}
        for entry in self.plan.providers.values():
            if (
                entry.get("companion_of") == folder.provider
                and entry["name"] in called | {"google-beta", "azapi"}
                and folder.registry
                and entry not in entries
            ):
                entries.append(entry)
        for name, _alias in folder.configurations:
            configured = next((e for e in self.plan.providers.values() if e["name"] == name), None)
            if configured is not None and configured not in entries:
                entries.append(configured)
        # a companion the folder's own resources name (azuread_application)
        written = {
            item.labels[0]
            for item in folder.items
            if isinstance(item, Block) and item.type in ("resource", "data") and item.labels
        }
        for entry in self.plan.providers.values():
            prefix = entry.get("prefix")
            if prefix and entry not in entries and any(kind.startswith(prefix) for kind in written):
                entries.append(entry)
        return entries

    def module_files(self, folder: Folder, items: list[object]) -> dict[str, str]:
        base = folder.path
        requirements: list[object] = []
        for entry in self.entries_for(folder):
            aliases = sorted(
                alias for name, alias in folder.configurations if name == entry["name"] and alias
            )
            value: dict[str, object] = {"source": entry["source"], "version": entry["version"]}
            if aliases:
                value["configuration_aliases"] = [
                    Raw(f"{entry['name']}.{alias}") for alias in aliases
                ]
            requirements.append(Attr(entry["name"], value))
        versions = [
            Attr("required_version", required_terraform(folder.registry)),
            BLANK,
            Block("required_providers", (), requirements),
        ]
        files = {f"{base}/versions.tf": render([Block("terraform", (), versions)])}
        main: list[object] = [*folder.data, *items] if folder.data else list(items)
        files[f"{base}/main.tf"] = render(main)
        files[f"{base}/variables.tf"] = render(
            [
                _variable(name, kind, description, MISSING, sensitive)
                for name, (kind, description, sensitive, _value) in sorted(folder.inputs.items())
            ]
        )
        if folder.outputs:
            files[f"{base}/outputs.tf"] = render(
                [
                    _output(name, value, description, sensitive)
                    for name, (value, description, sensitive) in sorted(folder.outputs.items())
                ]
            )
        return files

    # ------------------------------------------------------------ the environments
    def call_block(self, folder: Folder) -> Block:
        body: list[object] = [Attr("source", f"../../{folder.path}")]
        if any(alias for _name, alias in folder.configurations):
            # a call that names its providers hands over the defaults too: the
            # module inherits none once any is named
            named = set(folder.configurations) | {
                (entry["name"], None) for entry in self.entries_for(folder)
            }
            handed = {
                Bare(name if alias is None else f"{name}.{alias}"): Raw(
                    name if alias is None else f"{name}.{alias}"
                )
                for name, alias in sorted(named, key=lambda c: (c[0], c[1] or ""))
            }
            body.append(Attr("providers", handed))
        body.append(BLANK)
        first = [name for name in ("name", "tags", "labels") if name in folder.inputs]
        rest = sorted(name for name in folder.inputs if name not in first)
        body += [Attr(name, folder.inputs[name][3]) for name in [*first, *rest]]
        if folder.waits:
            body += [BLANK, Attr("depends_on", [Raw(f"module.{call}") for call in folder.waits])]
        return Block("module", (folder.call,), body)

    def environment(self, name: str, used: set[str]) -> dict[str, str]:
        plan = self.plan
        base = f"environments/{name}"
        providers = [p for p in plan.providers]
        files: dict[str, str] = {}
        registry = [key for folder in self.folders.values() for key in folder.registry]
        files[f"{base}/versions.tf"] = render(
            [
                Block(
                    "terraform",
                    (),
                    [
                        Attr("required_version", required_terraform(registry)),
                        BLANK,
                        Block(
                            "required_providers",
                            (),
                            [
                                Attr(
                                    entry["name"],
                                    {"source": entry["source"], "version": entry["version"]},
                                )
                                for entry in plan.providers.values()
                            ],
                        ),
                    ],
                )
            ]
        )
        files[f"{base}/backend.tf"] = _backend(plan, name, [p for p in providers if p in _BACKENDS])
        files[f"{base}/providers.tf"] = render(_provider_blocks(plan))
        values: list[object] = [Attr("name", "${var.project}-${var.environment}")]
        if {"aws", "azure"} & set(providers):
            values.append(
                Attr(
                    "tags",
                    {
                        "Project": Raw("var.project"),
                        "Environment": Raw("var.environment"),
                        "ManagedBy": "terraform",
                    },
                )
            )
        if "gcp" in providers:
            values.append(
                Attr(
                    "labels",
                    {
                        "project": Raw("lower(var.project)"),
                        "environment": Raw("lower(var.environment)"),
                        "managed-by": "terraform",
                    },
                )
            )
        for local, value in plan.locals.items():
            values.append(Attr(local, self.rewrite(value, None)))
        files[f"{base}/locals.tf"] = render([Block("locals", (), values)])
        main: list[object] = [self.data[address] for address in self.environment_data]
        for folder in self.folders.values():
            main.append(
                Comment(
                    f"{concern_title(folder.concern)}: {FOLDER_TITLES.get(folder.concern, folder.concern)}"
                    + (
                        f" on {_CLOUDS.get(folder.provider, folder.provider)}."
                        if self.several
                        else "."
                    )
                )
            )
            main.append(self.call_block(folder))
        files[f"{base}/main.tf"] = render(main)
        variables = {
            "project": Variable(
                "project",
                "string",
                plan.project.slug,
                "The name every resource's name starts with.",
            ),
            "environment": Variable(
                "environment", "string", name, "The environment: dev, test, prod, ..."
            ),
        }
        for variable_name in sorted(used):
            variable = self.variables.get(variable_name)
            if variable is not None:
                variables[variable_name] = variable
        files[f"{base}/variables.tf"] = render(
            [
                _variable(v.name, v.type, v.description, v.default, v.sensitive)
                for v in sorted(variables.values(), key=lambda v: v.name)
            ]
        )
        if self.outputs:
            files[f"{base}/outputs.tf"] = render(
                [
                    _output(output, value, description, sensitive)
                    for output, (value, description, sensitive) in sorted(self.outputs.items())
                ]
            )
        todos = [v for v in variables.values() if v.todo]
        files[f"{base}/terraform.tfvars.example"] = _tfvars(todos, name)
        return files

    def used_variables(self, files: dict[str, str]) -> set[str]:
        """The configuration's variables the environment reads: its modules'
        inputs, its providers' and its locals' settings."""
        used = {
            name
            for folder in self.folders.values()
            for name, (*_rest, value) in folder.inputs.items()
            if isinstance(value, Raw) and value.text == f"var.{name}"
        }
        for text in (
            files.get("environments/dev/providers.tf", ""),
            files.get("environments/dev/locals.tf", ""),
        ):
            used |= set(_VAR.findall(text))
        return used - {"project", "environment"}


# ---------------------------------------------------------------- blocks
def _text(description: str) -> str:
    """A description as HCL text: the diagram's ``${`` and ``%{`` stay text,
    once escaped however often this is called."""
    return re.sub(r"(?<![$%])([$%])\{", r"\1\1{", description)


def _variable(name: str, kind: str, description: str, default: object, sensitive: bool) -> Block:
    body: list[object] = [Attr("type", Raw(kind)), Attr("description", _text(description))]
    if default is not MISSING:
        body.append(Attr("default", default))
    if sensitive:
        body.append(Attr("sensitive", True))
    return Block("variable", (name,), body)


def _output(name: str, value: object, description: str, sensitive: bool) -> Block:
    body: list[object] = [Attr("description", _text(description)), Attr("value", value)]
    if sensitive:
        body.append(Attr("sensitive", True))
    return Block("output", (name,), body)


def _provider_blocks(plan: Plan) -> list[object]:
    blocks: list[object] = []
    for entry in plan.providers.values():
        for config in entry["configs"]:
            body: list[object] = []
            if config["alias"]:
                body.append(Attr("alias", config["alias"]))
            nested: list[object] = []
            for key, value in config["settings"].items():
                if isinstance(value, dict) and set(value) == {"$block"}:
                    nested.append(Block(key, (), [Attr(k, v) for k, v in value["$block"].items()]))
                else:
                    body.append(Attr(key, value))
            for block in nested:
                if body:
                    body.append(BLANK)
                body.append(block)
            blocks.append(Block("provider", (entry["name"],), body))
    return blocks


def _backend(plan: Plan, environment: str, providers: list[str]) -> str:
    """Where the environment keeps its state: commented out, since only the
    reader knows the bucket; the key is the environment's own."""
    key = f"{plan.project.slug}/{environment}/terraform.tfstate"
    lines = [
        "# Where this environment keeps its state. Terraform keeps it in this folder",
        "# until you uncomment a backend below, fill it in and run terraform init again.",
        "# Each environment has a key of its own, so dev and prod never share state.",
        "#",
    ]
    examples = {
        "aws": [
            "# terraform {",
            '#   backend "s3" {',
            '#     bucket       = "TODO"',
            f'#     key          = "{key}"',
            '#     region       = "TODO"',
            "#     use_lockfile = true",
            "#   }",
            "# }",
        ],
        "azure": [
            "# terraform {",
            '#   backend "azurerm" {',
            '#     resource_group_name  = "TODO"',
            '#     storage_account_name = "TODO"',
            '#     container_name       = "tfstate"',
            f'#     key                  = "{key}"',
            "#   }",
            "# }",
        ],
        "gcp": [
            "# terraform {",
            '#   backend "gcs" {',
            '#     bucket = "TODO"',
            f'#     prefix = "{plan.project.slug}/{environment}"',
            "#   }",
            "# }",
        ],
    }
    for n, provider in enumerate(providers[:1] or ["aws"]):
        if n:
            lines.append("#")
        lines += examples[provider]
    return "\n".join(lines) + "\n"


def _placeholder(variable: Variable) -> str:
    if variable.type == "number":
        return "0"
    if variable.type == "bool":
        return "false"
    if variable.type.startswith("map("):
        return "{}"
    if variable.type.startswith("list("):
        return '["TODO", "TODO"]' if "cidr" in variable.name else "[]"
    return quote("TODO")


def _tfvars(todos: list[Variable], environment: str) -> str:
    lines = [
        f"# The {environment} environment's values the diagram does not answer. Copy this",
        "# file to terraform.tfvars and fill it in before you plan.",
        "",
    ]
    for variable in sorted(todos, key=lambda v: v.name):
        lines += [f"# {variable.description}", f"{variable.name} = {_placeholder(variable)}", ""]
    if not todos:
        lines.append("# The diagram answers every value; nothing to fill.")
    return "\n".join(lines).rstrip("\n") + "\n"


def _holds_terraform(folder: Path) -> bool:
    return any(folder.glob("*.tf")) or any(folder.glob("*.tf.json"))


def environment_folders(folder: Path) -> list[Path]:
    """The configurations a skeleton laid out by environment holds:
    ``environments/dev``, ``environments/prod``; none for any other folder."""
    environments = Path(folder) / "environments"
    if not environments.is_dir():
        return []
    return [
        child
        for child in sorted(environments.iterdir())
        if child.is_dir() and _holds_terraform(child)
    ]


def configuration_root(folder: Path) -> Path:
    """The root module a folder stands for: the folder, when it holds
    Terraform; else its ``prod`` environment (or its first), when it is a
    skeleton laid out by environment."""
    folder = Path(folder)
    if _holds_terraform(folder):
        return folder
    found = environment_folders(folder)
    for wanted in ("prod", "production"):
        for child in found:
            if child.name == wanted:
                return child
    return found[0] if found else folder


def render_layout(plan: Plan) -> dict[str, str]:
    """Every file of the skeleton, relative path -> text."""
    layout = _Layout(plan)
    files = layout.modules()
    for environment in ENVIRONMENTS:
        # the environment reads what its modules take, so it is written after them
        files.update(layout.environment(environment, set()))
    used = layout.used_variables(files)
    for environment in ENVIRONMENTS:
        files.update(layout.environment(environment, used))
    todos = [v for name, v in layout.variables.items() if name in used and v.todo]
    files[".gitignore"] = (
        ".terraform/\n*.tfstate\n*.tfstate.*\n*.tfvars\n!*.tfvars.example\ncrash.log\n"
    )
    from .readme import layout_readmes

    files.update(layout_readmes(plan, layout, files, todos))
    return dict(sorted(files.items(), key=lambda pair: (pair[0].count("/") > 0, pair[0])))
