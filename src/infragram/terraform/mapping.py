"""The tables that turn a diagram's frames and components into Terraform.

One JSON file per provider under ``assets/terraform/``: which resources a
frame kind stands for, which resources a component stands for, the step file
each belongs to, and the arguments each is written with. Values are literal
JSON, or a ``$`` placeholder the emitter fills from where the element sits:

``$name``, ``$name:lower``, ``$name:alnum24``, ``$name:max32``, ``$name:lower+final``
    the resource's name, ``<name_prefix>-<element>``, made to fit; ``+<word>``
    puts a word after it (``<name_prefix>-<element>-final``)
``$caption``
    the element's own caption, when it names the thing (a subnet Azure
    reserves the name of)
``$caption_id``
    the caption when the provider accepts it as a name as it is (a resource
    group, a virtual network), else ``$name``
``$tags``, ``$tags_named``, ``$labels``
    the tag map, with a ``Name`` tag for AWS, or GCP's labels
``$cidr``
    the frame's address range: from its caption, else a variable to fill
``$network.<attr>``, ``$subnet.<attr>``, ``$subnets.<attr>``, ``$cluster.<attr>``
    the enclosing network, subnet, the sibling subnets of the same kind, or
    the enclosing cluster; ``$network.private_services`` is the Google Cloud
    network read through its private services connection, which it writes
``$serving_port``
    the port the wires into the element reach it on, else 80 (a managed
    instance group's named port, which a load balancer's backend names)
``$gateway.<attr>``, ``$backend_pools``
    an Azure Application Gateway as its wires and card say: ``tier``
    (``WAF_v2`` when the card says WAF), ``waf_policy`` (its own OWASP policy
    then), ``listener``, ``listener_port``, ``listener_protocol`` and
    ``certificate`` (HTTPS on 443 when a wire into it says so), and
    ``backend_port``/``backend_protocol`` (the port of the wires out of it);
    ``$backend_pools`` is the backend pool of each gateway wired to a server
``$github.<attr>``
    a GitHub workflow's OIDC sign-in, the repository, environment and branch
    read from the diagram (the GitHub card's ``owner/repo``, the approval
    gate's environment, the Git branch's name): ``subject`` (the token's
    ``sub`` it must present), ``condition`` (Google's attribute condition),
    ``principal_set`` (Google's member for the pool), ``pool_id``, and
    ``trust_policy`` (AWS: the role's trust in GitHub's OIDC issuer)
``$link.id``, ``$link.subresources``, ``$link.zones``
    what a private endpoint connects, from the wire to it: the service's id,
    its subresource, and the private DNS zone it resolves in (written once);
    with no wire, the first two are variables to fill
``$zone``, ``$region``, ``$location``, ``$resource_group``, ``$project``
    where the element sits; ``$zone:b`` is the zone frame's zone, else zone
    ``b`` of the region; ``$resource_group.id`` is the group's id (an
    Azure Verified Module's ``parent_id``)
``$network_tags``
    the element's Google Cloud network tag, which its firewall rules name
``$security_groups``
    the element's own security group and the security-group frames around it
``$internal``
    whether the element sits anywhere but a public subnet
``$pool``
    the node pool's name, from its caption
``$tenant_id``
    the Azure tenant the provider signs in to
``$self.<key>.<attr>``
    another resource the same element writes
``$var:<name>``, ``$var:<name>=<default>``, ``$var:<name>:<type>[=<default>]``,
``$secret:<name>``
    an input: a variable named after the element, with a default when the
    table knows a sensible one, else a TODO the README lists
``$raw:<expression>``
    an expression written as is

``{"$block": {...}}`` (or a list of them) is a nested block; with
``"$when": "internet"`` it is written only for an element a person or client
wires to, with ``"$when": "link"`` only for a private endpoint wired to a
service it connects, with ``"$when": "https"`` only for an element a wire
reaches on 443.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..paths import skill_assets

__all__ = [
    "PROVIDERS",
    "AzapiRule",
    "ComponentRule",
    "EdgeRule",
    "FrameRule",
    "ImportRules",
    "ModuleTable",
    "ProviderMapping",
    "RegistryModule",
    "ResourceSpec",
    "load_mapping",
    "load_modules",
    "load_ports",
    "registry_page",
    "required_terraform",
]

#: The libraries the export writes Terraform for.
PROVIDERS = ("azure",)

Step = Literal["network", "security", "data", "compute", "edge", "observability"]

#: The modules style's categories: one module folder each -- the resource
#: groups and APIs everything else sits in or needs first, the network, then
#: what runs on it and what reaches it.
Category = Literal[
    "foundation",
    "network",
    "security",
    "compute",
    "containers",
    "database",
    "storage",
    "messaging",
    "analytics",
    "edge",
    "dns",
    "observability",
]

#: What a frame kind is to Terraform.
FrameRole = Literal[
    "none",  # a drawing frame only (the provider cloud, a generic group)
    "account",  # an account or organization: the provider's credentials pick it
    "subscription",  # an Azure subscription: a provider configuration of its own
    "project",  # a GCP project: the project id the provider works in
    "region",  # where things are: a provider region or a location
    "resource_group",  # an Azure resource group: a resource everything inside names
    "network",  # a VPC, VNet or VPC network: a child module of its own
    "subnet",  # a subnet inside the network
    "zone",  # an availability zone: where the subnets inside it are placed
    "security_group",  # a security group frame: its members wear it
    "cluster",  # a managed Kubernetes cluster: node pools inside it
    "outside",  # the other side of a link (a data centre, a partner site)
]


class ResourceSpec(BaseModel):
    """One resource an element writes."""

    model_config = ConfigDict(extra="forbid")

    #: ``main`` takes the element's own name; any other key is appended.
    key: str = "main"
    type: str
    args: dict[str, Any] = Field(default_factory=dict)
    comment: str | None = None
    #: In the modules style, the registry module (a key of modules.json)
    #: written instead of the resource, with these arguments (else ``args``).
    module: str | None = None
    module_args: dict[str, Any] | None = None
    #: False for a resource the modules style leaves to another part's
    #: registry module, which writes it (the RDS module's subnet group).
    in_modules: bool = True


class FrameRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: FrameRole
    resources: list[ResourceSpec] = Field(default_factory=list)
    note: str | None = None


class CiStatement(BaseModel):
    """One statement of what a pipeline may do on a component (AWS IAM)."""

    model_config = ConfigDict(extra="forbid")

    actions: list[str]
    #: What the actions are allowed on: ``*``, or an attribute of the
    #: component's main resource (``arn``, ``id``), with a path after it
    #: (``arn/*``: every object in a bucket).
    resources: list[str]


class CiAccess(BaseModel):
    """What a pipeline signed in through OIDC needs on a component it
    deploys to, granted by a wire from the identity to it."""

    model_config = ConfigDict(extra="forbid")

    #: AWS: the statements of the role's policy.
    statements: list[CiStatement] = Field(default_factory=list)
    #: Azure: the roles assigned on the component; Google Cloud: the project
    #: roles granted to the pool's service account (Cloud Run's deployer also
    #: acts as its runtime account).
    roles: list[str] = Field(default_factory=list)


class PrivateLink(BaseModel):
    """How a private endpoint connects to a service (Azure)."""

    model_config = ConfigDict(extra="forbid")

    #: The service's resource the endpoint connects to: its key in the entry.
    resource: str = "main"
    #: The subresource (group id) the connection names: ``sqlServer``, ``blob``.
    subresource: str
    #: The private DNS zone its private address resolves in.
    zone: str


class ComponentRule(BaseModel):
    """What a component draws as in Terraform."""

    model_config = ConfigDict(extra="forbid")

    step: Step
    #: The modules style's category: the module folder its items are written in.
    category: Category
    #: One item's name, singular snake case: its block in the category module,
    #: and (plural) the map of them the module takes and gives
    #: (``ec2_instance`` -> ``ec2_instances``).
    item: str
    resources: list[ResourceSpec] = Field(default_factory=list)
    #: What is written in place of ``resources`` when the card counts several
    #: of it or says it scales (a Google managed instance group).
    scaled: list[ResourceSpec] | None = None
    #: Said in the README (and as a comment) when nothing, or not everything,
    #: can be written for the component.
    note: str | None = None
    #: Where the element must sit for its resources to be written.
    requires: Literal["none", "network", "subnet"] = "none"
    #: The component wears a boundary of its own and the wires to it become
    #: its inbound rules: an AWS security group, the Azure network and
    #: application security groups its resources list, a Google Cloud tag.
    security_group: bool = False
    #: The port a wire *to* this component uses when its label names none.
    port: int | None = None
    #: The main resource's attribute that is the component's endpoint, or
    #: ``<key>.<attribute>`` for another of its resources.
    output: str | None = None
    #: The provider holds that attribute sensitive, so the root's output says
    #: so too, or Terraform refuses the plan (Application Insights' connection string).
    output_sensitive: bool = False
    #: A special role the emitter handles beyond the arguments.
    plumbing: (
        Literal[
            "internet_gateway",
            "nat_gateway",
            "node_pool",
            "load_balancer",
            "private_endpoint",
            "application_gateway",
            "github_oidc",
            "service_principal",
        ]
        | None
    ) = None
    #: GCP: the API a resource of this component needs enabled first.
    api: str | None = None
    #: Azure: the name the subnet it sits in must have (``AzureBastionSubnet``);
    #: that subnet is written so, whatever its caption says.
    subnet_name: str | None = None
    #: Azure: a private endpoint wired to the component connects to it so.
    private_link: PrivateLink | None = None
    #: What is written in place of ``resources`` when a GitHub workflow signs
    #: in to it through OIDC: a wire into it from GitHub Actions, its runner,
    #: its token or the token's issuer (an AWS role's trust, an Azure managed
    #: identity's federated credential, a Google Workload Identity pool).
    federated: list[ResourceSpec] | None = None
    #: What a pipeline needs on the component to deploy to it, granted by a
    #: wire from its cloud identity.
    ci_access: CiAccess | None = None
    #: Azure: the main resource's attribute a role assignment names as the
    #: principal when the component is the pipeline's identity (a managed
    #: identity's ``principal_id``, a service principal's ``object_id``);
    #: empty for one that holds no roles itself (an app registration: its
    #: service principal does).
    principal: str = "principal_id"


class TerraformProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    source: str
    version: str


class EdgeRule(BaseModel):
    """A resource that is only a wire: from what one argument names to what
    the others name (a DNS record from its zone to its alias target)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source: str = Field(alias="from")
    targets: list[str] = Field(alias="to")
    #: The wire's label, or the value whose text it takes (``type``, ``protocol``).
    label: str = ""
    label_from: str | None = None


class AzapiRule(BaseModel):
    """An Azure type declared through ``azapi_resource``, as the ``azurerm``
    resource the drawing reads."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    type: str = Field(alias="as")
    #: azurerm argument -> the path in the resource's values that gives it
    values: dict[str, str] = Field(default_factory=dict)
    #: the azurerm argument ``parent_id`` stands for: a resource group, a network
    parent: str | None = None


class ImportRules(BaseModel):
    """What the import draws each resource type as, beyond the frames and
    components above read the other way (each table's ``about`` says more)."""

    model_config = ConfigDict(extra="forbid")

    about: str = ""
    #: type -> the component it draws as, or None for a type never drawn
    components: dict[str, str | None] = Field(default_factory=dict)
    #: type -> the argument(s) naming the drawn resource it is folded into
    owners: dict[str, str | list[str]] = Field(default_factory=dict)
    edges: dict[str, EdgeRule] = Field(default_factory=dict)
    #: type -> the component every one of them in a place is drawn as, once
    collapse: dict[str, str] = Field(default_factory=dict)
    #: types that are not architecture; one ending in ``_`` names every type it begins
    ignore: list[str] = Field(default_factory=list)
    #: types a table writes that the import still leaves out as not
    #: architecture (an IAM role: every service keeps some; the diagram draws
    #: the one a pipeline signs in to, the import does not guess which)
    not_drawn: list[str] = Field(default_factory=list)
    #: type -> the argument values that make one of it no architecture, though
    #: the type draws as a component otherwise (a global address reserved
    #: for peering is the network's plumbing, not a load balancer's address);
    #: a value ending in ``*`` matches every value it begins
    ignore_when: dict[str, dict[str, str]] = Field(default_factory=dict)
    #: the component a type with no mapping draws as, captioned with its type
    fallback: str | None = None
    #: Azure type (``Microsoft.Network/virtualNetworks``) -> the azurerm resource it is
    azapi: dict[str, AzapiRule] = Field(default_factory=dict)


class CompanionProvider(TerraformProvider):
    """A provider a table's resources name beside the cloud's own: Entra ID
    objects through ``azuread``. Declared wherever a resource of it is written."""

    #: The resource types it writes start so: ``azuread_``.
    prefix: str


class ProviderMapping(BaseModel):
    """A provider's table: every frame kind and component the export writes,
    and what the import draws each resource type as."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal[1]
    provider: str
    about: str = ""
    terraform: TerraformProvider
    companions: list[CompanionProvider] = Field(default_factory=list)
    frames: dict[str, FrameRule]
    components: dict[str, ComponentRule]
    imports: ImportRules = Field(default_factory=ImportRules, alias="import")

    def component(self, service_id: str) -> ComponentRule | None:
        return self.components.get(service_id)

    def frame(self, kind: str) -> FrameRule | None:
        return self.frames.get(kind)


class PortTable(BaseModel):
    """The ports a wire's label names: ``HTTPS`` is 443, ``SQL`` the database's."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    about: str = ""
    words: dict[str, int]


class RegistryModule(BaseModel):
    """A registry module the export's modules style calls, at the version pinned."""

    model_config = ConfigDict(extra="forbid")

    source: str
    version: str
    #: the providers it needs, by their key in the table's ``providers``
    providers: list[str] = Field(default_factory=list)
    #: an attribute a caller asks of it (``id``) -> the output that gives it,
    #: or a path into one (``fqdn["blob"]``, ``resource.hostname``)
    outputs: dict[str, str] = Field(default_factory=dict)
    #: its outputs Terraform holds sensitive: what reads them is sensitive too
    sensitive: list[str] = Field(default_factory=list)
    #: the Terraform it, and every module it calls, needs (``>= 1.11.1``)
    terraform: str = ">= 1.5"

    @property
    def package(self) -> str:
        """The registry package it is in: its source without a submodule's
        ``//modules/<name>``, the folder the module cache keeps it under."""
        return self.source.partition("//")[0]

    @property
    def page(self) -> str:
        """Its page on the public registry, at the version pinned."""
        return registry_page(self.source, self.version)


def required_terraform(keys: Iterable[str]) -> str:
    """The Terraform a skeleton that calls these registry modules needs: the
    strictest of theirs, ``>= 1.5`` at the least."""
    table = load_modules().modules

    def version(text: str) -> tuple[int, ...]:
        return tuple(int(part) for part in text.removeprefix(">=").strip().split("."))

    return max([">= 1.5", *(table[key].terraform for key in keys)], key=version)


def registry_page(source: str, version: str) -> str:
    """A registry module's page at a version; a submodule's
    (``terraform-aws-modules/ecs/aws//modules/cluster``) is its own page under it."""
    address, _, subdir = source.partition("//")
    page = f"https://registry.terraform.io/modules/{address}/{version}"
    return f"{page}/submodules/{subdir.rstrip('/').rsplit('/', 1)[-1]}" if subdir else page


class ModuleTable(BaseModel):
    """``assets/terraform/modules.json``: the registry modules, pinned."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    about: str = ""
    modules: dict[str, RegistryModule]
    providers: dict[str, TerraformProvider]


def _mapping_path(provider: str):
    return skill_assets() / "terraform" / f"{provider}.json"


@cache
def load_mapping(provider: str) -> ProviderMapping:
    """The table for one of :data:`PROVIDERS`."""

    if provider not in PROVIDERS:
        raise KeyError(
            f"no Terraform mapping for {provider!r}; the export covers {', '.join(PROVIDERS)}"
        )
    return ProviderMapping.model_validate_json(_mapping_path(provider).read_text(encoding="utf-8"))


@cache
def load_modules() -> ModuleTable:
    return ModuleTable.model_validate_json(
        (skill_assets() / "terraform" / "modules.json").read_text(encoding="utf-8")
    )


@cache
def load_ports() -> PortTable:
    return PortTable.model_validate_json(
        (skill_assets() / "terraform" / "ports.json").read_text(encoding="utf-8")
    )
