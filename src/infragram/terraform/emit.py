"""A diagram into a modular Terraform skeleton.

The walk follows the diagram's containment. A frame's kind decides what it is
to Terraform (see :mod:`.mapping`): a region or subscription is a provider
configuration, a resource group a resource the things inside it name, a
network frame a child module of its own, a subnet a resource inside that
module. A component becomes the resources its provider's table lists, written
where it sits: inside the network module that holds it, else in the root.
Everything the diagram does not state is a variable, and every variable
without a default is a TODO the README lists.

The skeleton is honest about what it is: resources in the shape the diagram
asserts, not a configuration anyone has applied.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Set
from typing import Any

from pydantic import ConfigDict, Field

from ..models.topology import TopologyElement
from ..projects import CloudProject
from .hcl import BLANK, Attr, Block, Comment, Raw, identifier, literal
from .mapping import (
    PROVIDERS,
    CiStatement,
    ComponentRule,
    PrivateLink,
    ProviderMapping,
    ResourceSpec,
    load_mapping,
    load_modules,
    load_ports,
)
from .model import Record

__all__ = [
    "MISSING",
    "PLACEHOLDERS",
    "STYLES",
    "WHEN",
    "Output",
    "Plan",
    "Unit",
    "Variable",
    "Wire",
    "plan_terraform",
]

#: The export's styles: plain resources, or the public registry's modules
#: where one fits (:mod:`.registry`).
STYLES = ("resources", "modules")

_CIDR = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2})\b")
#: The subnet names Azure reserves for the one service that sits in each, as
#: Azure spells them; a caption that says one keeps it exactly.
_AZURE_SUBNETS = {
    name.lower(): name
    for name in (
        "AzureBastionSubnet",
        "AzureFirewallManagementSubnet",
        "AzureFirewallSubnet",
        "GatewaySubnet",
        "RouteServerSubnet",
    )
}
_AZURE_SUBNET = re.compile(r"\b(" + "|".join(_AZURE_SUBNETS.values()) + r")\b", re.IGNORECASE)
_AWS_REGION = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$")
_GCP_REGION = re.compile(r"^[a-z]+-[a-z]+\d+$")
#: What AWS refuses in a security group's or a rule's description.
_NOT_AWS_DESCRIPTION = re.compile(r"[^A-Za-z0-9. _\-:/()#,@\[\]+=&;{}!$*]+")
#: Every ``$`` placeholder a table may use; :mod:`.mapping` says what each is.
PLACEHOLDERS = frozenset(
    {
        "name",
        "caption",
        "caption_id",
        "tags",
        "tags_named",
        "labels",
        "var",
        "secret",
        "raw",
        "cidr",
        "network",
        "subnet",
        "subnets",
        "cluster",
        "pool",
        "self",
        "zone",
        "region",
        "location",
        "resource_group",
        "project",
        "security_groups",
        "internal",
        "tenant_id",
        "network_tags",
        "link",
        "gateway",
        "backend_pools",
        "serving_port",
        "github",
        "wired",
    }
)
#: Shared components that stand for a GitHub workflow: a wire from one into a
#: cloud identity is the workflow signing in to it through OIDC.
_GITHUB_SIDE = frozenset(
    {
        "brand-github",
        "brand-github-actions",
        "ci-runner",
        "ci-cd-pipeline",
        "oidc-token",
        "identity-provider",
    }
)
#: Who signs a GitHub workflow's OIDC token.
GITHUB_ISSUER = "https://token.actions.githubusercontent.com"
#: A repository as a caption says it: ``owner/name``.
_REPOSITORY = re.compile(
    r"(?<![\w./-])([A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100})(?![\w/])"
)
#: Where Google's load balancers and health checks reach a backend from.
GOOGLE_FRONT_ENDS = ("35.191.0.0/16", "130.211.0.0/22")
#: When a ``{"$block": ..., "$when": ...}`` block is written.
WHEN = frozenset({"internet", "link", "https"})
#: A port, or a range of them, in a wire's label: ``443``, ``8000-8080``.
_PORT = re.compile(r"(?<![\d./])(\d{2,5})(?:-(\d{2,5}))?(?![\d./])")
#: A cloud's second provider, as modules.json names it, and the settings of the
#: cloud's own configuration it takes (None: all of them).
_COMPANIONS = {"gcp": ("google-beta", None), "azure": ("azapi", ("subscription_id",))}
#: Shared-library components that stand for people and clients, not things.
_ACTORS = frozenset(
    {
        "public-user",
        "public-users",
        "administrator",
        "browser-client",
        "mobile-client",
        "public-internet",
        "developer",
        "operator",
    }
)


#: Words a detail spends on no name: "web tier" names ``web``.
_FILLER = frozenset({"tier", "tiers", "layer", "the", "a", "an", "and", "of", "for", "with"})
#: Words that join a caption's words and never name a thing: "Cache for Redis" is no ``for``.
_FUNCTION_WORDS = frozenset(
    {"the", "a", "an", "and", "of", "for", "with", "to", "in", "on", "by", "at"}
)
#: Words a label spends on the brand, never a name of its own.
_BRANDS = frozenset({"aws", "amazon", "azure", "microsoft", "google", "gcp"})
#: Words that say what a resource type is, beyond the words of the type itself:
#: a label drops them, so "Public subnets" names ``aws_subnet.public`` and
#: "Application Load Balancer" names ``aws_lb.main``.
_TYPE_SYNONYMS: dict[str, frozenset[str]] = {
    "vpc": frozenset({"vpc", "vpcs", "network", "virtual", "private", "cloud"}),
    "network": frozenset({"network", "networks", "vnet", "vnets", "vpc", "virtual"}),
    "subnet": frozenset({"subnet", "subnets", "subnetwork", "subnetworks"}),
    "subnetwork": frozenset({"subnet", "subnets", "subnetwork", "subnetworks"}),
    "instance": frozenset(
        {
            "instance",
            "instances",
            "server",
            "servers",
            "vm",
            "vms",
            "machine",
            "machines",
            "host",
            "hosts",
            "ec2",
        }
    ),
    "autoscaling": frozenset(
        {
            "auto",
            "scaling",
            "autoscaling",
            "asg",
            "server",
            "servers",
            "instance",
            "instances",
            "ec2",
            "fleet",
        }
    ),
    "lb": frozenset(
        {
            "lb",
            "alb",
            "nlb",
            "elb",
            "load",
            "balancer",
            "balancers",
            "balancing",
            "application",
            "elastic",
        }
    ),
    "db": frozenset({"db", "database", "databases", "rds"}),
    "bucket": frozenset({"bucket", "buckets", "s3"}),
    "secret": frozenset({"secret", "secrets", "manager"}),
    "log": frozenset({"log", "logs", "logging", "cloudwatch"}),
    "cluster": frozenset({"cluster", "clusters", "kubernetes", "k8s"}),
    "gateway": frozenset({"gateway", "gateways", "gw"}),
    # a Google global address is a load balancer's: "Application Load Balancer" says only that
    "global": frozenset(
        {"global", "application", "load", "balancer", "balancers", "balancing", "lb", "external"}
    ),
}
#: What an element whose label is only its type's words is called in a
#: variable or a security group's name, by its main resource type.
_NOUNS = {
    "aws_vpc": "vpc",
    "aws_subnet": "subnet",
    "aws_lb": "alb",
    "aws_instance": "server",
    "aws_autoscaling_group": "asg",
    "aws_launch_template": "asg",
    "aws_db_instance": "db",
    "aws_rds_cluster": "db",
    "aws_s3_bucket": "bucket",
    "aws_secretsmanager_secret": "secret",
    "aws_cloudwatch_log_group": "log_group",
    "aws_wafv2_web_acl": "waf",
    "aws_internet_gateway": "igw",
    "aws_nat_gateway": "nat",
    "aws_security_group": "sg",
    "azurerm_virtual_network": "vnet",
    "azurerm_subnet": "subnet",
    "azurerm_resource_group": "rg",
    "google_compute_network": "network",
    "google_compute_subnetwork": "subnet",
    "google_compute_global_address": "lb",
    "google_compute_security_policy": "armor",
    "google_compute_router_nat": "nat",
    "google_cloud_run_v2_service": "run",
    "google_iam_workload_identity_pool": "pool",
}
#: How a resource type is said in a variable or output name (``private_subnet_ids``).
_TYPE_NOUNS = {
    "aws_vpc": "vpc",
    "aws_subnet": "subnet",
    "aws_lb": "lb",
    "aws_lb_target_group": "target_group",
    "aws_security_group": "security_group",
    "aws_db_instance": "db_instance",
    "aws_s3_bucket": "bucket",
    "aws_autoscaling_group": "autoscaling_group",
    "aws_launch_template": "launch_template",
    "aws_secretsmanager_secret": "secret",
    "aws_cloudwatch_log_group": "log_group",
    "azurerm_virtual_network": "vnet",
    "azurerm_subnet": "subnet",
    "azurerm_resource_group": "resource_group",
    "google_compute_network": "network",
    "google_compute_subnetwork": "subnet",
}
#: An instance type or class a card's detail names: ``m6i.large``, ``db.r6g.large``.
_SIZE = re.compile(
    r"\b((?:db|cache)\.)?([a-z][a-z0-9-]*\d[a-z0-9-]*)\.(nano|micro|small|medium|large|\d*xlarge|metal)\b"
)


def label_words(text: str) -> list[str]:
    """A caption's own words: no address range, IP, parenthesis or
    punctuation, and no part after a middle dot that is a note about the
    thing, not its name ("VPC · 10.40.0.0/16 · no internet gateway")."""
    parts = [
        part
        for part in text.split("·")
        if not re.match(r"\s*(?:no|not|without|with)\b", part, re.IGNORECASE)
    ]
    text = " ".join(parts)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    # Azure's reserved subnet names are words run together: AzureBastionSubnet is a bastion's
    text = _AZURE_SUBNET.sub(
        lambda found: (
            " " + " ".join(re.findall(r"[A-Z][a-z]+", _AZURE_SUBNETS[found.group(1).lower()])) + " "
        ),
        text,
    )
    text = _CIDR.sub(" ", text)
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    return re.findall(r"[a-z0-9]+", text.lower())


def type_words(resource_type: str, service_id: str = "") -> frozenset[str]:
    """The words that only say what a resource is: its type's own, their
    synonyms, the component's catalog id, and the brand's."""
    tokens = resource_type.split("_")[1:]
    words: set[str] = set(tokens) | {f"{token}s" for token in tokens} | set(_BRANDS)
    for token in tokens:
        words |= _TYPE_SYNONYMS.get(token, frozenset())
    words |= set(re.findall(r"[a-z0-9]+", service_id.lower()))
    return frozenset(words)


def type_noun(resource_type: str) -> str:
    """A resource type as a variable or output name says it: ``aws_subnet`` -> ``subnet``."""
    return _TYPE_NOUNS.get(resource_type) or resource_type.split("_", 1)[-1]


#: Attributes too plain to name a value alone: ``web_autoscaling_group_name``, not ``web_name``.
_PLAIN_ATTRIBUTES = frozenset({"id", "name", "arn", "ids", "names", "arns"})


def join_words(*parts: str) -> str:
    """Names joined by underscores, a word said twice in a row said once:
    ``db`` and ``db_subnet_group`` -> ``db_subnet_group``."""
    words: list[str] = []
    for word in "_".join(part for part in parts if part).split("_"):
        if word and (not words or words[-1] != word):
            words.append(word)
    return "_".join(words)


def _stem(word: str) -> str:
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def value_name(base: str, resource_type: str, attribute: str, many: bool = False) -> str:
    """What a variable or output giving a block's attribute is called: its
    element's name, the block's kind when the attribute is too plain to say
    it (``web_autoscaling_group_name``) and the name does not already
    (``alb_arn``, ``vpc_id``), then the attribute, plural for a list."""
    attribute = f"{attribute}s" if many and not attribute.endswith("s") else attribute
    kind = (
        type_noun(resource_type) if resource_type and not resource_type.startswith("module") else ""
    )
    words = [_stem(w) for w in base.split("_")]
    said = kind and all(
        any(w == _stem(k) or w.endswith(_stem(k)) or _stem(k).endswith(w) for w in words)
        for k in kind.split("_")
    )
    parts = [base]
    if kind and attribute in _PLAIN_ATTRIBUTES and not said:
        parts.append(kind)
    return "_".join([*parts, attribute]) if attribute else "_".join(parts)


#: The module folders, in the order an environment calls them: what everything
#: sits in first, the network, then what runs on it, keeps its data and reaches it.
FOLDERS = (
    "foundation",
    "network",
    "security",
    "secrets",
    "compute",
    "containers",
    "database",
    "storage",
    "messaging",
    "analytics",
    "loadbalancer",
    "edge",
    "dns",
    "monitoring",
)


def module_folder(category: str, item: str = "") -> str:
    """The module folder of a table category and item: a secret or key its
    own ``secrets``, a load balancer its own ``loadbalancer``, the rest the
    category (observability as ``monitoring``)."""
    if category == "security" and any(
        word in item for word in ("secret", "key_vault", "kms", "keyring")
    ):
        return "secrets"
    if category == "edge" and (
        item in ("lb", "application_gateway") or item.endswith(("load_balancer", "_lb"))
    ):
        return "loadbalancer"
    if category == "observability":
        return "monitoring"
    return category


class PlacementError(Exception):
    """A placeholder the element's position cannot fill."""


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


#: A variable with no default: a TODO.
MISSING = _Missing()


class Variable(Record):
    name: str
    type: str = "string"
    default: object = MISSING
    description: str = ""
    sensitive: bool = False

    @property
    def todo(self) -> bool:
        return self.default is MISSING


class Output(Record):
    name: str
    #: the expression (Raw), or in the modules style what reads an item (a Ref)
    value: object
    description: str = ""
    #: it reads a value Terraform holds sensitive (a registry module's own output)
    sensitive: bool = False


class Unit(Record):
    """The root module, or one child module."""

    name: str
    directory: str
    provider: str | None = None
    caption: str = ""
    files: dict[str, list[object]] = Field(default_factory=dict)
    variables: dict[str, Variable] = Field(default_factory=dict)
    outputs: dict[str, Output] = Field(default_factory=dict)
    #: The root's call: module argument -> value in the root's terms.
    call: dict[str, object] = Field(default_factory=dict)
    alias: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    names: set[str] = Field(default_factory=set)

    @property
    def is_root(self) -> bool:
        return self.directory == ""

    def add(self, section: str, *items: object) -> None:
        self.files.setdefault(section, []).extend(items)

    def claim(self, kind: str, *wanted: str) -> str:
        """A block name free for its kind (a resource type, ``module``): the
        first of ``wanted`` no other block of the kind has, else the last
        numbered. The address is kind and name, so an element's database and
        its subnet group may share a name, as Terraform's own examples do."""
        for name in wanted:
            if f"{kind}.{name}" not in self.names:
                self.names.add(f"{kind}.{name}")
                return name
        base, n = wanted[-1], 2
        while f"{kind}.{base}_{n}" in self.names:
            n += 1
        self.names.add(f"{kind}.{base}_{n}")
        return f"{base}_{n}"

    def release(self, kind: str, name: str) -> None:
        self.names.discard(f"{kind}.{name}")

    def variable(self, variable: Variable) -> Raw:
        self.variables.setdefault(variable.name, variable)
        return Raw(f"var.{variable.name}")


class Resource(Record):
    type: str
    name: str
    unit: Unit
    #: written with ``count``: one reads ``[0]`` of it, or ``[*]`` of them all
    counted: bool = False

    @property
    def address(self) -> str:
        return f"{self.type}.{self.name}"

    def ref(self, attribute: str) -> Raw:
        return Raw(f"{self.address}{'[0]' if self.counted else ''}.{attribute}")

    def every(self, attribute: str) -> Raw:
        """The attribute of every instance, as a list: ``aws_subnet.private[*].id``."""
        return Raw(
            f"{self.address}[*].{attribute}" if self.counted else f"[{self.address}.{attribute}]"
        )


class ModuleResource(Resource):
    """A part written as a call of a registry module: what is read of it is
    the module output that gives it (``module.alb.dns_name``)."""

    #: attribute -> the output that gives it, or a path into one
    outputs: dict[str, str] = Field(default_factory=dict)
    #: the module's outputs Terraform holds sensitive
    sensitive: list[str] = Field(default_factory=list)
    #: attribute -> an expression that gives it without the module's outputs table
    paths: dict[str, str] = Field(default_factory=dict)
    #: attribute -> a value known without reading the module (a subnet's range)
    values: dict[str, Any] = Field(default_factory=dict)

    @property
    def address(self) -> str:
        return f"module.{self.name}"

    def ref(self, attribute: str) -> Any:
        if attribute in self.values:
            return self.values[attribute]
        if attribute in self.paths:
            return Raw(f"module.{self.name}.{self.paths[attribute]}")
        return Raw(f"module.{self.name}.{self.outputs.get(attribute, attribute)}")

    def every(self, attribute: str) -> Raw:
        return Raw(f"[{self.ref(attribute).text}]")

    def is_sensitive(self, attribute: str) -> bool:
        output = self.paths.get(attribute) or self.outputs.get(attribute, attribute)
        return re.split(r"[.\[]", output, maxsplit=1)[0] in self.sensitive


class Wire(Record):
    source: TopologyElement
    target: TopologyElement
    label: str
    written_as: str = ""


class Plan(Record):
    """Everything the writer turns into files, and what the README reports."""

    project: CloudProject
    root: Unit
    modules: list[Unit]
    providers: dict[str, dict[str, Any]]
    not_written: list[tuple[str, str]]
    notes: list[str]
    wires: list[Wire]
    #: Captions more than one element shares: shown with their ids.
    repeated: frozenset[str] = frozenset()
    #: ``resources`` or ``modules``, and the registry modules a modules skeleton calls
    style: str = "resources"
    registry: tuple[str, ...] = ()
    #: what each element became, for the README: (category, element, written as, where)
    rows: list[tuple[str, str, str, str]] = Field(default_factory=list)
    #: the configuration's locals beyond its name, tags and labels: name -> value
    locals: dict[str, object] = Field(default_factory=dict)
    #: block address -> the caption of the element it was written for
    labels: dict[str, str] = Field(default_factory=dict)
    #: block address -> the name its values start with (``web``, ``public_subnet``)
    nouns: dict[str, str] = Field(default_factory=dict)
    #: element id -> what the skeleton calls it (``web``, ``vpc``)
    element_nouns: dict[str, str] = Field(default_factory=dict)

    def label(self, element: TopologyElement) -> str:
        return _labelled(element, self.repeated)


def _labelled(element: TopologyElement, repeated: Set[str]) -> str:
    """The element's caption, with its id when another element shares it."""
    return f"{element.name} ({element.id})" if element.name in repeated else element.name


class Place(Record):
    """Where the walk is: the unit resources go in, and the frames around them."""

    model_config = ConfigDict(frozen=True)

    unit: Unit
    provider: str | None = None
    alias: str | None = None
    region: object = None
    location: object = None
    resource_group: object = None
    resource_group_id: object = None
    project: object = None
    network: Resource | None = None
    network_element: TopologyElement | None = None
    subnet: Resource | None = None
    subnet_kind: str | None = None
    zone: object = None
    security_groups: tuple[object, ...] = ()
    cluster: Resource | None = None
    outside: bool = False


def _moved(place: Place, **changes: object) -> Place:
    """The place with some of its frames changed: a copy, the walk's places
    being values."""
    return place.model_copy(update=changes)


class _Emitter:
    def __init__(self, project: CloudProject, style: str = "resources") -> None:
        if style not in STYLES:
            raise ValueError(f"no Terraform style {style!r}; the styles are {', '.join(STYLES)}")
        self.style = style
        #: network element id -> the registry module call it is written as
        #: (the modules style's; the plain walk writes none)
        self.module_networks: dict[str, Any] = {}
        #: the registry modules called, in the order first called
        self.registry: list[str] = []
        self.project = project
        self.root = Unit("root", "")
        self.modules: list[Unit] = []
        self.providers: dict[str, dict[str, Any]] = {}
        #: Every resource type written, so a companion provider (azuread) is
        #: declared where one of its resources is.
        self.types_written: set[str] = set()
        self.not_written: list[tuple[str, str]] = []
        self.notes: list[str] = []
        self.wires: list[Wire] = []
        self.apis: dict[str, str] = {}
        #: element id -> the resources it wrote (key -> Resource)
        self.written: dict[str, dict[str, Resource]] = {}
        #: element id -> its own AWS security group
        self.security_group_of: dict[str, Resource] = {}
        #: element id -> where it sat and its rule, for the wire pass
        self.placed: dict[str, tuple[Place, ComponentRule | None]] = {}
        #: network element id -> its subnets: (resource, kind, zone)
        self.subnets: dict[str, list[tuple[Resource, str, object]]] = {}
        self.regions: dict[tuple[str, str], tuple[str | None, Raw]] = {}
        self.subscriptions: dict[str, str | None] = {}
        self.route_table_of: dict[str, str] = {}
        self.nat_tables: list[tuple[Place, str, object]] = []
        self.pool_name_of: dict[str, str] = {}
        self.security_items: dict[str, list[object]] = {}
        self.parent: dict[str, TopologyElement] = {}
        self.by_id: dict[str, TopologyElement] = {}
        #: the frame whose address range ``$cidr`` names, and the unit it is in
        self.cidr_frame: tuple[Unit, TopologyElement] | None = None
        self.components: list[tuple[TopologyElement, Place]] = []
        #: every network written: where its resources sit, and its frame
        self.networks: list[tuple[Place, TopologyElement]] = []
        #: element id -> its Google Cloud network tag
        self.network_tag_of: dict[str, str] = {}
        #: the elements a person or client wires to: the internet reaches them
        self.internet_reaches: set[str] = set()
        #: network security group address -> the last priority a rule took
        self.priorities: dict[str, int] = {}
        #: element id -> what it is called in variables and names (``web``, ``vpc``)
        self.nouns: dict[str, str] = {}
        #: network element id -> its private services connection (Google Cloud)
        self.private_connections: dict[str, Resource] = {}
        #: what the private endpoint being written connects: the service, its
        #: resource, and how (Azure)
        self.link: tuple[TopologyElement, Resource, PrivateLink] | None = None
        #: private DNS zone name -> its zone; (zone, network id) pairs linked
        self.dns_zones: dict[str, Resource] = {}
        self.dns_links: set[tuple[str, str]] = set()
        #: element id -> the wires into it: (source, label)
        self.incoming: dict[str, list[tuple[TopologyElement, str]]] = {}
        #: gateway element id -> its own WAF policy (Azure)
        self.waf_policies: dict[str, Resource] = {}
        #: (gateway, server) element ids: the server sits in the gateway's backend pool
        self.pool_members: set[tuple[str, str]] = set()
        #: Google load balancer element id -> its backends (element, port), and
        #: the Cloud Armor policies and Cloud CDN wired to it
        self.lb_backends: dict[str, list[tuple[TopologyElement, int]]] = {}
        self.lb_armor: dict[str, TopologyElement] = {}
        self.lb_cdn: set[str] = set()
        #: element ids a GitHub workflow is wired into: they trust it through OIDC
        self.github_signed_in: set[str] = set()
        #: the diagram's GitHub repository, environment and branch, once read
        self.github: tuple[str | None, str | None, str] | None = None
        #: GitHub's OIDC provider in the AWS account, once written
        self.github_provider: Resource | None = None
        #: AWS role element id -> what the wires from it grant, a target at a time
        self.ci_statements: dict[str, list[tuple[TopologyElement, list[CiStatement]]]] = {}
        #: (identity element id, role) pairs granted on Google Cloud
        self.ci_roles: set[tuple[str, str]] = set()
        self._fallbacks: dict[str, int] | None = None
        #: element id -> the section (module folder) its resources are in
        self.section_of: dict[str, str] = {}
        #: the configuration's locals beyond its name and tags: name -> value
        self.locals: dict[str, object] = {}
        #: network element id -> how many tiers of it were carved a range
        self.tiers: dict[str, int] = {}
        #: security group address -> the network element it is in
        self.group_network: dict[str, str | None] = {}
        names = [element.name for element in project.topology.walk()]
        self.repeated = {name for name in names if names.count(name) > 1}
        clouds = [p for p in project.provider_ids if p in PROVIDERS]
        self.document_provider = clouds[0] if len(clouds) == 1 else None

    # ------------------------------------------------------------ providers
    @staticmethod
    def mapping(provider: str) -> ProviderMapping:
        return load_mapping(provider)

    def use_provider(self, provider: str) -> None:
        if provider in self.providers:
            return
        table = self.mapping(provider).terraform
        self.providers[provider] = {
            "name": table.name,
            "source": table.source,
            "version": table.version,
            "configs": [],
        }

    def provider_config(
        self, provider: str, alias: str | None, settings: dict[str, object]
    ) -> None:
        self.use_provider(provider)
        configs = self.providers[provider]["configs"]
        if not any(config["alias"] == alias for config in configs):
            configs.append({"alias": alias, "settings": settings})

    def default_configs(self) -> None:
        """Every provider in use has a default configuration."""

        for provider, entry in self.providers.items():
            if any(config["alias"] is None for config in entry["configs"]):
                continue
            if provider == "aws":
                region = self.root.variable(
                    Variable("aws_region", "string", MISSING, "The AWS region.")
                )
                self.provider_config(
                    "aws",
                    None,
                    {"region": region, "default_tags": {"$block": {"tags": Raw("local.tags")}}},
                )
            elif provider == "azure":
                subscription = self.root.variable(
                    Variable(
                        "azure_subscription_id", "string", MISSING, "The Azure subscription id."
                    )
                )
                self.provider_config(
                    "azure", None, {"subscription_id": subscription, "features": {"$block": {}}}
                )
            elif provider == "gcp":
                self.provider_config(
                    "gcp",
                    None,
                    {
                        "project": self.root.variable(
                            Variable(
                                "gcp_project_id", "string", MISSING, "The Google Cloud project id."
                            )
                        ),
                        "region": self.root.variable(
                            Variable("gcp_region", "string", MISSING, "The Google Cloud region.")
                        ),
                    },
                )
            entry["configs"].sort(key=lambda config: config["alias"] is not None)

    def frame_provider(self, element: TopologyElement, inherited: str | None) -> str | None:
        group = str(element.attributes.get("editor_frame_group") or "")
        if group in PROVIDERS:
            return group
        component = element.component
        if component is not None and component.provider == "infragram":
            from ..catalog import architecture_boundary_group

            owner = architecture_boundary_group(component.service_id)
            if owner in PROVIDERS:
                return owner
        if inherited:
            return inherited
        below = {
            c.component.provider
            for c in element.walk()
            if c.component is not None and c.component.provider in PROVIDERS
        }
        if len(below) == 1:
            return below.pop()
        return self.document_provider

    # ------------------------------------------------------------ naming
    def main_type(self, element: TopologyElement) -> tuple[str, str]:
        """The element's main resource type, and its component's catalog id
        (a frame's kind), the words of which a name leaves out."""
        component = element.component
        specs: list[ResourceSpec] = []
        if element.is_frame:
            provider = self.frame_provider(element, None)
            rule = self.mapping(provider).frame(element.type) if provider in PROVIDERS else None
            specs, service = (rule.resources if rule is not None else []), ""
        elif component is not None and component.provider in PROVIDERS:
            found = self.mapping(component.provider).component(component.service_id)
            specs, service = (found.resources if found is not None else []), component.service_id
        else:
            service = component.service_id if component is not None else ""
        main = next(
            (spec.type for spec in specs if spec.key == "main"), specs[0].type if specs else ""
        )
        return main, service

    def own_words(self, element: TopologyElement, resource_type: str = "") -> list[str]:
        """The caption's words that name this one, not what it is: "Public
        subnets" -> ``public``; "Application Load Balancer" -> none."""
        main, service = self.main_type(element)
        drop = (
            type_words(resource_type or main, service) | type_words(main, service) | _FUNCTION_WORDS
        )
        return [word for word in label_words(element.name) if word not in drop]

    def noun(self, element: TopologyElement) -> str:
        """What the element is called in a variable, a security group, a rule
        and a name in the cloud: its own words, else its kind's (``alb``,
        ``vpc``), once in the diagram."""
        known = self.nouns.get(element.id)
        if known is not None:
            return known
        words = self.own_words(element)
        main, service = self.main_type(element)
        fallback = _NOUNS.get(main) or (type_noun(main) if main else "") or identifier(element.id)
        if not words and self.shared_fallbacks().get(fallback, 0) > 1:
            # several captioned only by what they are ("Amazon EC2"): each by its
            # detail ("web tier" -> web), when that says it in a word or two
            detail = [
                word
                for word in label_words(str(element.attributes.get("detail") or ""))
                if word not in type_words(main, service) and word not in _FILLER
            ]
            if 0 < len(detail) <= 2:
                words = detail
        noun = identifier("_".join(words)) if words else fallback
        taken = set(self.nouns.values())
        if noun in taken:
            # the element's id when it reads as a name (web-b), else the name numbered
            by_id = identifier(element.id)
            wanted = noun if re.search(r"\d+_\d+_\d+", by_id) else by_id
            noun, n = wanted, 2
            while noun in taken:
                noun, n = f"{wanted}_{n}", n + 1
        self.nouns[element.id] = noun
        return noun

    def shared_fallbacks(self) -> dict[str, int]:
        """How many elements are captioned only by what they are, by the name
        they would fall back to (two "Amazon EC2" cards: ``server`` twice)."""
        if self._fallbacks is None:
            counts: dict[str, int] = {}
            for element in self.project.topology.walk():
                if self.own_words(element):
                    continue
                main, _service = self.main_type(element)
                if main:
                    fallback = _NOUNS.get(main) or type_noun(main)
                    counts[fallback] = counts.get(fallback, 0) + 1
            self._fallbacks = counts
        return self._fallbacks

    def resource_name(
        self,
        unit: Unit,
        resource_type: str,
        element: TopologyElement,
        key: str = "main",
        shared: bool = False,
    ) -> str:
        """A block's name: the caption's own words, ``main`` when they say only
        what it is, its noun when that is taken; ``shared`` when another
        block of the element has the same type, with its key after."""
        words = self.own_words(element, resource_type)
        own = identifier("_".join(words)) if words else "main"
        noun = self.noun(element)
        if shared and key != "main":
            return unit.claim(resource_type, f"{noun}_{key}")
        return unit.claim(resource_type, own, noun, identifier(element.id))

    def section(self, provider: str | None, category: str, item: str = "") -> str:
        """The module folder a block is written in: ``aws/network``."""
        return f"{provider or 'none'}/{module_folder(category, item)}"

    def slug(self, element: TopologyElement) -> str:
        return self.noun(element)

    def name_expr(self, place: Place, element: TopologyElement, transform: str = "") -> object:
        prefix = "local.name"
        part = self.noun(element).replace("_", "-") or "unnamed"
        # "+final": a word after the name (a database's final snapshot)
        match = re.fullmatch(r"(lower|alnum|max)?(\d+)?(?:\+([a-z][a-z0-9-]*))?", transform or "")
        if match is None:
            raise PlacementError(f"unknown name transform {transform!r}")
        style, limit, suffix = match.group(1), match.group(2), match.group(3)
        base = f"${{{prefix}}}-{part}" + (f"-{suffix}" if suffix else "")
        if style is None and limit is None:
            return base
        text = f'"{base}"'
        if style in ("lower", "alnum"):
            text = f"lower({text})"
        if style == "alnum":
            text = f'replace({text}, "/[^a-z0-9]/", "")'
        if limit:
            text = f"substr({text}, 0, {int(limit)})"
            if style != "alnum":
                text = f'trim({text}, "-")'
        return Raw(text)

    def tags(self, place: Place, element: TopologyElement, provider: str, named: bool) -> object:
        if provider == "aws":
            return {"Name": self.name_expr(place, element)} if named else None
        if provider == "gcp":
            return Raw("local.labels")
        return Raw("local.tags")

    # ------------------------------------------------------------ variables
    def element_variable(
        self, place: Place, element: TopologyElement, spec: str, sensitive: bool = False
    ) -> Raw:
        name_part, _, default_text = spec.partition("=")
        name_part, _, type_name = name_part.partition(":")
        type_name = type_name or "string"
        # what the element says it is sized as (``.sizing(instance_type=...)``,
        # the same value ``--prices`` prices, or the card's own detail: "Multi-AZ
        # · db.r6g.large", "3 x m6i.large") is the default it is written with
        stated = self.stated(element, name_part, type_name)
        if stated is not None:
            default_text = str(stated).lower() if isinstance(stated, bool) else str(stated)
        name = f"{self.noun(element)}_{identifier(name_part)}"
        described = _DESCRIPTIONS.get(name_part, "The {what} of {label}.").format(
            what=_words(name_part), label=self.label(element)
        )
        if default_text:
            default: object = default_text
            if type_name == "number":
                default = float(default_text) if "." in default_text else int(default_text)
            elif type_name == "bool":
                default = default_text == "true"
            return place.unit.variable(Variable(name, type_name, default, described, sensitive))
        return self.required_variable(
            place, Variable(name, type_name, MISSING, described, sensitive)
        )

    @staticmethod
    def stated(element: TopologyElement, field: str, type_name: str) -> object:
        """What the element states for one of its variables: its sizing, else
        its caption and detail -- an instance type or class, Multi-AZ, a count
        -- else None."""
        sizing = element.attributes.get("sizing")
        sizing = sizing if isinstance(sizing, dict) else {}
        text = f"{element.name} {element.attributes.get('detail') or ''}".lower()
        value: object = sizing.get(field)
        if value is None and field in ("desired_capacity", "min_size", "max_size", "target_size"):
            count = sizing.get("count")
            if count is None:
                found = re.search(r"\b(\d{1,3})\s*[x×]\s*[a-z]", text)
                count = int(found.group(1)) if found else None
            if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                value = count * 2 if field == "max_size" else count
        if value is None and field in ("instance_type", "instance_class"):
            for prefix, family, size in _SIZE.findall(text):
                if bool(prefix) == (field == "instance_class"):
                    value = f"{prefix}{family}.{size}"
                    break
        if value is None and field == "multi_az" and re.search(r"\bmulti[- ]?az\b", text):
            value = True
        # Cloud SQL: "HA" on the card is a standby in a second zone of the region
        if (
            value is None
            and field == "availability_type"
            and re.search(r"\b(?:ha|high[- ]availability|regional)\b", text)
        ):
            value = "REGIONAL"
        if type_name == "string":
            return value.strip() if isinstance(value, str) and value.strip() else None
        if type_name == "number":
            return (
                value if isinstance(value, (int, float)) and not isinstance(value, bool) else None
            )
        if type_name == "bool":
            return value if isinstance(value, bool) else None
        return None

    def label(self, element: TopologyElement) -> str:
        """The element's caption, with its id when another element shares it."""

        return _labelled(element, self.repeated)

    def required_variable(self, place: Place, variable: Variable) -> Raw:
        """A variable with no default: a root variable, passed into the module
        that needs it, so every TODO is filled in one place."""

        ref = place.unit.variable(variable)
        if not place.unit.is_root:
            self.root.variable(
                Variable(
                    variable.name, variable.type, MISSING, variable.description, variable.sensitive
                )
            )
            place.unit.call[variable.name] = Raw(f"var.{variable.name}")
        return ref

    def root_input(
        self, unit: Unit, name: str, value: object, description: str = "", type_name: str = "string"
    ) -> object:
        """A value the root knows (a region, a resource group), as the unit sees it."""

        if unit.is_root:
            return value
        unit.variable(Variable(name, type_name, MISSING, description))
        unit.call[name] = value
        return Raw(f"var.{name}")

    # ------------------------------------------------------------ placeholders
    def resolve(
        self,
        value: object,
        place: Place,
        element: TopologyElement,
        written: dict[str, Resource],
        provider: str,
    ) -> object:
        if isinstance(value, dict):
            # an optional value the place cannot fill leaves its key out, at any depth
            resolved_items = {
                key: self.resolve(item, place, element, written, provider)
                for key, item in value.items()
            }
            return {key: item for key, item in resolved_items.items() if item is not MISSING}
        if isinstance(value, list):
            out: list[object] = []
            for item in value:
                resolved = self.resolve(item, place, element, written, provider)
                if resolved is MISSING:
                    continue
                out.extend(resolved if isinstance(resolved, list) else [resolved])
            return out
        if not isinstance(value, str) or not value.startswith("$"):
            return value
        optional = value.endswith("?")
        token = value[1:-1] if optional else value[1:]
        try:
            return self.placeholder(token, place, element, written, provider)
        except PlacementError:
            if optional:
                return MISSING
            raise

    def placeholder(
        self,
        token: str,
        place: Place,
        element: TopologyElement,
        written: dict[str, Resource],
        provider: str,
    ) -> object:
        head, _, rest = token.partition(":")
        base, _, attribute = head.partition(".")
        if base not in PLACEHOLDERS:
            # A table error, not a place the element cannot fill: loud.
            raise ValueError(f"the {provider} Terraform table uses an unknown placeholder ${token}")
        if base == "name":
            if self.link is not None and "+" not in rest:
                # one endpoint a service: each named after what it connects
                rest = f"{rest}+{self.noun(self.link[0]).replace('_', '-')}"
            return self.name_expr(place, element, rest)
        if base == "gateway":
            return self.gateway(place, element, attribute)
        if base == "github":
            return self.github_value(place, element, attribute, written)
        if base == "wired":
            return self.wired(element, attribute)
        if base == "serving_port":
            return self.serving_port(element)
        if base == "backend_pools":
            return self.backend_pools(element)
        if base == "link":
            if attribute == "id":
                return (
                    self.link[1].ref("id")
                    if self.link is not None
                    else self.element_variable(place, element, "target_resource_id")
                )
            if attribute == "subresources":
                return (
                    [self.link[2].subresource]
                    if self.link is not None
                    else self.element_variable(place, element, "subresource_names:list(string)")
                )
            if attribute == "zones":
                if self.link is None:
                    raise PlacementError("it is wired to no service a private DNS zone answers for")
                return [self.private_dns_zone(place, element, self.link[2].zone).ref("id")]
            raise ValueError(f"the {provider} Terraform table uses an unknown placeholder ${token}")
        if base == "caption":
            return literal(element.name)
        if base == "caption_id":
            # a subnet holding a service Azure pins to one is named as Azure asks
            for child in element.children:
                rule = (
                    self.mapping(child.component.provider).components.get(
                        child.component.service_id
                    )
                    if child.component is not None and child.component.provider in PROVIDERS
                    else None
                )
                if rule is not None and rule.subnet_name:
                    return rule.subnet_name
            caption = element.name.strip()
            # a caption that says a reserved name keeps it, range or not: "AzureBastionSubnet 10.0.4.0/26"
            if _CIDR.sub(" ", caption).strip().lower() in _AZURE_SUBNETS:
                return _AZURE_SUBNETS[_CIDR.sub(" ", caption).strip().lower()]
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]{0,78}[A-Za-z0-9_]", caption):
                return caption
            return self.name_expr(place, element, rest)
        if base in ("tags", "tags_named", "labels"):
            return self.tags(place, element, provider, named=base == "tags_named")
        if base == "var":
            return self.element_variable(place, element, token[len("var:") :])
        if base == "secret":
            return self.element_variable(place, element, token[len("secret:") :], sensitive=True)
        if base == "raw":
            return Raw(token[len("raw:") :])
        if base == "cidr":
            if self.cidr_frame is None:
                raise PlacementError("an address range outside a network or subnet frame")
            # declared when a resource reads it: a Google Cloud network has no range
            return self.cidr_input(*self.cidr_frame)
        if base == "network":
            if place.network is None:
                raise PlacementError("it sits in no network frame")
            if attribute == "private_services":
                # the network, read through its private services connection
                return self.private_services(place).ref("network")
            return place.network.ref(attribute or "id")
        if base == "subnet":
            return (place.subnet or self.fallback_subnet(place)).ref(attribute or "id")
        if base == "subnets":
            subnets = self.sibling_subnets(place)
            attr = attribute or "id"
            if not any(getattr(subnet, "counted", False) for subnet in subnets):
                return [subnet.ref(attr) for subnet in subnets]
            # a tier written across the zones is a list already: the siblings join
            parts = [subnet.every(attr).text for subnet in subnets]
            return Raw(parts[0] if len(parts) == 1 else f"concat({', '.join(parts)})")
        if base == "cluster":
            if place.cluster is None:
                raise PlacementError("it sits in no cluster frame")
            return place.cluster.ref(attribute or "id")
        if base == "pool":
            return self.pool_name_of.get(element.id, "system")
        if base == "self":
            key, _, attr = attribute.partition(".")
            if key not in written:
                raise PlacementError(f"no resource {key!r} written for it yet")
            return written[key].ref(attr or "id")
        if base == "zone":
            if place.zone is not None:
                return place.zone
            if rest:
                # a zone the diagram draws no frame for: that letter of the region
                region = self.region_of(place, provider)
                text = f"${{{region.text}}}" if isinstance(region, Raw) else str(region)
                return f"{text}-{rest}" if provider == "gcp" else f"{text}{rest}"
            raise PlacementError("it sits in no availability zone frame")
        if base == "region":
            return self.region_of(place, provider)
        if base == "location":
            return self.location_of(place)
        if base == "resource_group" and attribute == "id":
            # an Azure Verified Module built on azapi names its group by id: parent_id
            if place.resource_group_id is not None:
                return place.resource_group_id
            ref = self.root.variable(
                Variable(
                    "resource_group_id",
                    "string",
                    MISSING,
                    "The id of the resource group for what the diagram draws outside every resource group.",
                )
            )
            return self.root_input(place.unit, "resource_group_id", ref, "The resource group's id.")
        if base == "resource_group":
            if place.resource_group is not None:
                return place.resource_group
            ref = self.root.variable(
                Variable(
                    "resource_group_name",
                    "string",
                    MISSING,
                    "The resource group for what the diagram draws outside every resource group.",
                )
            )
            return self.root_input(place.unit, "resource_group_name", ref, "The resource group.")
        if base == "project":
            return self.project_of(place)
        if base == "security_groups":
            own = self.security_group_of.get(element.id)
            groups = ([own.ref("id")] if own is not None else []) + list(place.security_groups)
            if not groups:
                raise PlacementError("it has no security group")
            return groups
        if base == "internal":
            return place.subnet_kind != "subnet-public"
        if base == "network_tags":
            return [self.network_tag(element)]
        if base == "tenant_id":
            data = Raw("data.azurerm_client_config.current.tenant_id")
            if "_data" not in self.root.files:
                self.root.add("_data", Block("data", ("azurerm_client_config", "current"), []))
            return self.root_input(place.unit, "tenant_id", data, "The Azure tenant id.")
        raise AssertionError(f"PLACEHOLDERS names ${base}, which placeholder() does not fill")

    def wired(self, element: TopologyElement, attribute: str) -> object:
        """``$wired.<component>.<key>.<attribute>``: a resource written for a
        component wired to or from this one -- a service principal names its
        app registration's client id."""
        service_id, _, rest = attribute.partition(".")
        key, _, attr = rest.partition(".")
        neighbours = [source for source, _label in self.incoming.get(element.id, [])]
        neighbours += [self.by_id[c.target] for c in element.connections if c.target in self.by_id]
        for other in neighbours:
            if (
                other.component is not None
                and other.component.service_id == service_id
                and key in self.written.get(other.id, {})
            ):
                return self.written[other.id][key].ref(attr or "id")
        raise PlacementError(f"it is wired to no {service_id} written before it")

    def fallback_subnet(self, place: Place) -> Resource:
        if place.network_element is None:
            raise PlacementError("it sits in no subnet frame")
        subnets = self.subnets.get(place.network_element.id) or []
        if not subnets:
            raise PlacementError("its network has no subnet frame")
        private = [s for s in subnets if s[1] != "subnet-public"]
        return (private or subnets)[0][0]

    def sibling_subnets(self, place: Place) -> list[Resource]:
        if place.network_element is None:
            raise PlacementError("it sits in no network frame")
        subnets = self.subnets.get(place.network_element.id) or []
        if not subnets:
            raise PlacementError("its network has no subnet frame")
        kind = place.subnet_kind or (
            "subnet-private" if any(s[1] != "subnet-public" for s in subnets) else None
        )
        same = [s[0] for s in subnets if kind is None or s[1] == kind]
        return same or [s[0] for s in subnets]

    def region_of(self, place: Place, provider: str) -> object:
        if place.region is not None:
            return place.region
        name = {"aws": "aws_region", "gcp": "gcp_region"}.get(provider, "region")
        ref = self.root.variable(
            Variable(name, "string", MISSING, f"The {provider.upper()} region.")
        )
        return self.root_input(place.unit, "region", ref, "The region.")

    def location_of(self, place: Place) -> object:
        if place.location is not None:
            return place.location
        ref = self.root.variable(Variable("location", "string", MISSING, "The Azure location."))
        return self.root_input(place.unit, "location", ref, "The Azure location.")

    def project_of(self, place: Place) -> object:
        if place.project is not None:
            return place.project
        ref = self.root.variable(
            Variable("gcp_project_id", "string", MISSING, "The Google Cloud project id.")
        )
        return self.root_input(place.unit, "project_id", ref, "The project id.")

    # ------------------------------------------------------------ writing resources
    def write_resources(
        self,
        place: Place,
        element: TopologyElement,
        specs: list[ResourceSpec],
        provider: str,
        section: str,
        wanted: str | None = None,
    ) -> dict[str, Resource]:
        """Every resource of a table entry, in order, or none: a placeholder the
        position cannot fill leaves the element a README line instead.
        ``wanted`` names the blocks when an element writes its entry more
        than once (a private endpoint, once a service it connects)."""

        self.use_provider(provider)
        written: dict[str, Resource] = {}
        reserved: list[tuple[str, str]] = []
        blocks: list[tuple[Block, ResourceSpec]] = []
        types = [spec.type for spec in specs]
        registry = load_modules().modules
        provider_name = self.mapping(provider).terraform.name
        try:
            for spec in specs:
                if self.style == "modules" and not spec.in_modules and any(s.module for s in specs):
                    continue  # the registry module of another part writes it
                if self.style == "modules" and spec.module:
                    module = registry[spec.module]
                    # modules share one namespace: the endpoint to a service is the service's own
                    base = f"{wanted}_{self.noun(element)}" if wanted else self.noun(element)
                    name = place.unit.claim(
                        "module",
                        base if spec.key == "main" else f"{base}_{spec.key}",
                        f"{identifier(element.id)}_{spec.key}",
                    )
                    reserved.append(("module", name))
                    part = ModuleResource(
                        spec.type,
                        name,
                        place.unit,
                        outputs=module.outputs,
                        sensitive=list(module.sensitive),
                    )
                    written[spec.key] = part
                    body: list[object] = [
                        Attr("source", module.source),
                        Attr("version", module.version),
                    ]
                    if place.alias:
                        body.append(
                            Attr(
                                "providers", {provider_name: Raw(f"{provider_name}.{place.alias}")}
                            )
                        )
                    args = spec.module_args if spec.module_args is not None else spec.args
                    body += [BLANK, *self.arguments(args, place, element, written, provider)]
                    body += self.module_extras(spec.module, place, element, written)
                    self.use_module(spec.module)
                    blocks.append((Block("module", (name,), body), spec))
                    continue
                name = (
                    place.unit.claim(
                        spec.type, wanted if spec.key == "main" else f"{wanted}_{spec.key}"
                    )
                    if wanted
                    else self.resource_name(
                        place.unit, spec.type, element, spec.key, types.count(spec.type) > 1
                    )
                )
                reserved.append((spec.type, name))
                written[spec.key] = Resource(spec.type, name, place.unit)
                body = self.arguments(spec.args, place, element, written, provider)
                if place.alias:
                    body.insert(0, Attr("provider", Raw(f"{provider_name}.{place.alias}")))
                blocks.append((Block("resource", (spec.type, name), body), spec))
        except PlacementError:
            for kind, name in reserved:
                place.unit.release(kind, name)
            raise
        items: list[object] = [
            Comment(
                f"{element.name}{self.detail(element)}"
                + (f", to {self.link[0].name}" if self.link is not None else "")
            )
        ]
        for block, spec in blocks:
            if spec.comment:
                items.append(Comment(spec.comment))
            items.append(block)
        place.unit.add(section, *items)
        self.section_of[element.id] = section
        self.written[element.id] = written
        return written

    def use_module(self, key: str) -> None:
        if key not in self.registry:
            self.registry.append(key)

    def module_extras(
        self, key: str, place: Place, element: TopologyElement, written: dict[str, Resource]
    ) -> list[object]:
        """Arguments a registry module takes beyond its table's, from what the
        walk knows: none here; the wires add a load balancer's."""
        return []

    @staticmethod
    def detail(element: TopologyElement) -> str:
        detail = str(element.attributes.get("detail") or "").strip()
        return f" ({detail})" if detail else ""

    def arguments(
        self,
        args: dict[str, Any],
        place: Place,
        element: TopologyElement,
        written: dict[str, Resource],
        provider: str,
    ) -> list[object]:
        body: list[object] = []
        nested: list[object] = []
        for key, value in args.items():
            blocks = self.as_blocks(key, value, place, element, written, provider)
            if blocks is not None:
                nested.extend(blocks)
                continue
            resolved = self.resolve(value, place, element, written, provider)
            # a placeholder with nothing to say leaves the argument out; a table's
            # own null is written, to turn a module's default off
            if resolved is MISSING or (resolved is None and value is not None):
                continue
            body.append(Attr(key, resolved))
        tags = [item for item in body if isinstance(item, Attr) and item.name in ("tags", "labels")]
        plain = [
            item
            for item in body
            if not (isinstance(item, Attr) and item.name in ("tags", "labels"))
        ]
        out: list[object] = list(plain)
        for block in nested:
            if out:
                out.append(BLANK)
            out.append(block)
        if tags:
            if out:
                out.append(BLANK)
            out.extend(tags)
        return out

    def as_blocks(
        self,
        key: str,
        value: object,
        place: Place,
        element: TopologyElement,
        written: dict[str, Resource],
        provider: str,
    ) -> list[object] | None:
        values: list[Any] = value if isinstance(value, list) else [value]
        if not values or not all(
            isinstance(v, dict) and "$block" in v and set(v) <= {"$block", "$when"} for v in values
        ):
            return None
        return [
            Block(key, (), self.arguments(v["$block"], place, element, written, provider))
            for v in values
            if self.when(v.get("$when"), element)
        ]

    def when(self, condition: object, element: TopologyElement) -> bool:
        """Whether a ``$when`` block is written for the element."""
        if condition is None:
            return True
        if condition not in WHEN:
            # a table error, as an unknown placeholder is
            raise ValueError(
                f"a Terraform table writes a block $when {condition!r}, which is no condition"
            )
        if condition == "link":
            return self.link is not None
        if condition == "https":
            return self.serves_https(element)
        return element.id in self.internet_reaches

    # ------------------------------------------------------------ the walk
    def run(self) -> Plan:
        topology = self.project.topology
        for element in topology.walk():
            self.by_id[element.id] = element
            for child in element.children:
                self.parent[child.id] = element
        for child in topology.children:
            self.walk(child, Place(unit=self.root))
        for source in topology.walk():
            for connection in source.connections:
                target = self.by_id.get(connection.target)
                if self.is_actor(source):
                    self.internet_reaches.add(connection.target)
                if target is not None and self.is_actor(target) and connection.direction == "both":
                    self.internet_reaches.add(source.id)
                self.incoming.setdefault(connection.target, []).append(
                    (source, connection.label or "")
                )
                if self.is_github_side(source):
                    self.github_signed_in.add(connection.target)
        # a gateway before the servers that join its pool; a private endpoint
        # after the services it connects, so each can name the other
        order = {"application_gateway": 0, "private_endpoint": 2, "service_principal": 3}
        for element, place in sorted(
            self.components, key=lambda item: order.get(self.plumbing(item[0]) or "", 1)
        ):
            self.component(element, place)
        self.implied_internet_gateways()
        self.associate_nat_tables()
        self.write_wires()
        self.finish_module_networks()
        self.finish_module_rules()
        self.default_configs()
        self.finish_units()
        return Plan(
            self.project,
            self.root,
            self.modules,
            self.companions(self.providers),
            self.not_written,
            self.notes,
            self.wires,
            frozenset(self.repeated),
            self.style,
            tuple(self.registry),
            rows=self.architecture(),
            locals=dict(self.locals),
            labels=self.block_labels(),
            nouns=self.block_nouns(),
            element_nouns=dict(self.nouns),
        )

    def block_labels(self) -> dict[str, str]:
        """Each block's address, and the caption of the element it was written for."""
        labels: dict[str, str] = {}
        # a module several elements write into (a network and its subnets) is the first's
        for element_id, written in self.written.items():
            for resource in written.values():
                labels.setdefault(resource.address, self.label(self.by_id[element_id]))
        for element_id, group in self.security_group_of.items():
            labels.setdefault(
                group.address, f"the security group of {self.label(self.by_id[element_id])}"
            )
        return labels

    def block_nouns(self) -> dict[str, str]:
        """Each block's address, and the name its values start with: its
        element's (``web``), a frame's with its kind (``public_subnet``), a
        security group's (``web_security_group``), another block of an element
        with its own kind (``postgresql_db_subnet_group``)."""
        nouns: dict[str, str] = {}
        for element_id, written in self.written.items():
            element = self.by_id[element_id]
            main = written.get("main")
            for key, resource in written.items():
                if element.is_frame:
                    base = self.frame_name(element, "").rstrip("_")
                elif resource is main or key == "main":
                    base = self.noun(element)
                else:
                    base = join_words(self.noun(element), type_noun(resource.type))
                nouns.setdefault(resource.address, base)
        for element_id, group in self.security_group_of.items():
            nouns.setdefault(group.address, f"{self.noun(self.by_id[element_id])}_security_group")
        return nouns

    def companions(self, providers: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """The providers a cloud's registry modules call beside its own
        (google-beta, azapi), each configured as the cloud's provider is, so
        no module plans with an empty one."""
        table = load_modules()
        called = {name for key in self.registry for name in table.modules[key].providers}
        out = dict(providers)
        for library, (name, keep) in _COMPANIONS.items():
            entry = providers.get(library)
            if entry is None or name not in called or name in out:
                continue
            source = table.providers[name]
            out[name] = {
                "name": source.name,
                "source": source.source,
                "version": source.version,
                "companion_of": library,
                "configs": [
                    {
                        "alias": config["alias"],
                        "settings": {
                            key: value
                            for key, value in config["settings"].items()
                            if keep is None or key in keep
                        },
                    }
                    for config in entry["configs"]
                ],
            }
        # a table's own companions (azuread for Entra ID objects), where a
        # resource of theirs is written: signed in as the Azure CLI or the
        # pipeline is, so no setting of the cloud's carries over
        for library in providers:
            for companion in self.mapping(library).companions if library in PROVIDERS else []:
                if companion.name in out or not any(
                    t.startswith(companion.prefix) for t in self.types_written
                ):
                    continue
                out[companion.name] = {
                    "name": companion.name,
                    "source": companion.source,
                    "version": companion.version,
                    "companion_of": library,
                    "prefix": companion.prefix,
                    "configs": [{"alias": None, "settings": {}}],
                }
        return out

    def architecture(self) -> list[tuple[str, str, str, str]]:
        """What each element became: its category, its blocks and the module folder they are in."""
        rows: list[tuple[str, str, str, str]] = []
        for element_id, written in self.written.items():
            element = self.by_id[element_id]
            resources = list(dict.fromkeys(resource.address for resource in written.values()))
            if not resources:
                continue
            addresses = ", ".join(f"`{address}`" for address in resources)
            rows.append(
                (
                    self.category_of(element),
                    self.label(element),
                    addresses,
                    self.section_of.get(element_id, ""),
                )
            )
        return rows

    def category_of(self, element: TopologyElement) -> str:
        """The element's category, as the modules style files it."""
        component = element.component
        provider = component.provider if component is not None else None
        if provider in PROVIDERS and not element.is_frame:
            rule = self.mapping(provider).component(component.service_id)  # type: ignore[union-attr]
            if rule is not None:
                return rule.category.title()
        if element.type == "resource-group":
            return "Foundation"
        if element.type == "cluster":
            return "Containers"
        if element.type == "security-group":
            return "Security"
        return "Network"

    def walk(self, element: TopologyElement, place: Place) -> None:
        """The frames, in document order; each component is written after
        every frame is, so a resource that spans subnets sees all of them."""

        if element.is_frame:
            inner = self.frame(element, place)
            for child in element.children:
                self.walk(child, inner)
            return
        self.components.append((element, place))
        for child in element.children:
            self.walk(child, place)

    # ------------------------------------------------------------ frames
    def frame(self, element: TopologyElement, place: Place) -> Place:
        provider = self.frame_provider(element, place.provider)
        if provider is None:
            return _moved(place, provider=None)
        place = _moved(place, provider=provider)
        rule = self.mapping(provider).frame(element.type)
        if rule is None:
            return place
        if rule.note:
            self.notes.append(f"{element.name}: {rule.note}")
        role = rule.role
        if role == "outside":
            return _moved(place, outside=True)
        if role == "region":
            return self.region_frame(element, place, provider)
        if role == "subscription":
            return self.subscription_frame(element, place)
        if role == "project":
            return self.project_frame(element, place)
        if role == "resource_group":
            return self.resource_group_frame(element, place, rule.resources)
        if role == "network":
            return self.network_frame(element, place, provider, rule.resources)
        if role == "subnet":
            return self.subnet_frame(element, place, provider, rule.resources)
        if role == "zone":
            return self.zone_frame(element, place)
        if role == "security_group":
            if place.network is None:
                self.not_written.append(
                    (element.name, "a security group frame outside any network frame")
                )
                return place
            group = self.write_resources(
                place, element, rule.resources, provider, self.section(provider, "security")
            )["main"]
            self.group_network[group.address] = (
                place.network_element.id if place.network_element else None
            )
            self.egress_rule(place.unit, group)
            return _moved(place, security_groups=(*place.security_groups, group.ref("id")))
        if role == "cluster":
            return self.cluster_frame(element, place, provider, rule.resources)
        return place

    def region_frame(self, element: TopologyElement, place: Place, provider: str) -> Place:
        caption = element.name.strip()
        if provider == "aws":
            value = caption if _AWS_REGION.match(caption) else None
            key = ("aws", value or element.id)
            if key not in self.regions:
                first = not any(k[0] == "aws" for k in self.regions)
                alias = None if first else identifier(value or element.id)
                name = "aws_region" if first else f"{alias}_region"
                ref = self.root.variable(
                    Variable(name, "string", value or MISSING, "The AWS region.")
                )
                self.regions[key] = (alias, ref)
                self.provider_config(
                    "aws",
                    alias,
                    {"region": ref, "default_tags": {"$block": {"tags": Raw("local.tags")}}},
                )
            alias, ref = self.regions[key]
            return _moved(place, alias=alias, region=ref)
        if provider == "azure":
            location = re.sub(r"[^a-z0-9]", "", caption.lower())
            key = ("azure", location or element.id)
            if key not in self.regions:
                taken = [k for k in self.regions if k[0] == "azure"]
                name = "location" if not taken else f"location_{identifier(location or element.id)}"
                ref = self.root.variable(
                    Variable(name, "string", location or MISSING, "The Azure location.")
                )
                self.regions[key] = (None, ref)
            return _moved(place, location=self.regions[key][1])
        if provider == "gcp":
            value = caption if _GCP_REGION.match(caption) else None
            ref = self.root.variable(
                Variable(
                    "gcp_region",
                    "string",
                    value or MISSING,
                    "The Google Cloud region." if value else "The Google Cloud region.",
                )
            )
            return _moved(place, region=ref)
        return place

    def subscription_frame(self, element: TopologyElement, place: Place) -> Place:
        if element.id not in self.subscriptions:
            first = not self.subscriptions
            alias = None if first else identifier(element.id)
            name = "azure_subscription_id" if first else f"{alias}_subscription_id"
            ref = self.root.variable(
                Variable(name, "string", MISSING, f"The id of the {element.name} subscription.")
            )
            self.subscriptions[element.id] = alias
            self.provider_config(
                "azure", alias, {"subscription_id": ref, "features": {"$block": {}}}
            )
        return _moved(place, alias=self.subscriptions[element.id])

    def project_frame(self, element: TopologyElement, place: Place) -> Place:
        caption = element.name.split("·")[-1].strip()
        value = caption if re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", caption) else None
        ref = self.root.variable(
            Variable(
                "gcp_project_id",
                "string",
                value or MISSING,
                "The Google Cloud project id." if value else "The Google Cloud project id.",
            )
        )
        return _moved(place, project=ref)

    def resource_group_frame(
        self, element: TopologyElement, place: Place, specs: list[ResourceSpec]
    ) -> Place:
        root_place = _moved(place, unit=self.root)
        try:
            group = self.write_resources(
                root_place, element, specs, "azure", self.section("azure", "foundation")
            )["main"]
        except PlacementError as error:
            self.not_written.append((element.name, str(error)))
            return place
        return _moved(
            place,
            resource_group=group.ref("name"),
            resource_group_id=group.ref("id"),
            location=group.ref("location"),
        )

    def network_frame(
        self, element: TopologyElement, place: Place, provider: str, specs: list[ResourceSpec]
    ) -> Place:
        if provider == "azure" and place.resource_group is None:
            self.not_written.append(
                (element.name, "a virtual network outside any resource group frame")
            )
            return place
        inner = _moved(place, unit=self.root, provider=provider)
        if provider == "aws":
            inner = _moved(inner, region=self.region_of(place, "aws"))
        if provider == "azure":
            inner = _moved(inner, location=self.location_of(place))
        if provider == "gcp":
            inner = _moved(
                inner, project=self.project_of(place), region=self.region_of(place, "gcp")
            )
            self.need_api("compute.googleapis.com", self.root)
        self.cidr_frame = (self.root, element)
        try:
            network = self.network_resources(inner, element, provider, specs)
        except PlacementError as error:
            self.not_written.append((element.name, str(error)))
            return place
        finally:
            self.cidr_frame = None
        self.subnets[element.id] = []
        name = self.frame_name(element, "id")
        self.root.outputs[name] = Output(name, network.ref("id"), f"The id of {element.name}.")
        inner = _moved(inner, network=network, network_element=element)
        self.networks.append((inner, element))
        return inner

    def network_resources(
        self, place: Place, element: TopologyElement, provider: str, specs: list[ResourceSpec]
    ) -> Resource:
        """The network frame's own resources; the registry style's hook."""
        return self.write_resources(
            place, element, specs, provider, self.section(provider, "network")
        )["main"]

    def frame_name(self, element: TopologyElement, attribute: str, many: bool = False) -> str:
        """A network or subnet frame's variable or output: ``vpc_cidr``,
        ``hub_vpc_id``, ``public_subnet_ids``."""
        main, _service = self.main_type(element)
        kind = type_noun(main) if main else "network"
        noun = self.noun(element)
        base = noun if noun == kind or noun.endswith(f"_{kind}") else f"{noun}_{kind}"
        return f"{base}_{attribute}{'s' if many else ''}"

    def cidr_input(self, unit: Unit, element: TopologyElement) -> Raw:
        """A frame's address range: a variable, from its caption when the
        caption gives one."""

        match = _CIDR.search(element.name)
        name = self.frame_name(element, "cidr")
        described = f"The address range of {self.label(element)}."
        return self.root.variable(
            Variable(name, "string", match.group(1) if match else MISSING, described)
        )

    def zones_local(self, alias: str | None) -> Raw:
        """The two zones a tier spreads across, as a local the configuration
        reads from the region: ``local.azs``."""
        label = "available" if alias is None else f"available_{identifier(alias)}"
        local = "azs" if alias is None else f"{identifier(alias)}_azs"
        if local not in self.locals:
            self.root.add(
                "_data",
                Block(
                    "data",
                    ("aws_availability_zones", label),
                    [
                        *([Attr("provider", Raw(f"aws.{alias}")), BLANK] if alias else []),
                        Attr("state", "available"),
                    ],
                ),
            )
            self.locals[local] = Raw(f"slice(data.aws_availability_zones.{label}.names, 0, 2)")
        return Raw(f"local.{local}")

    def tier_cidrs(self, network: TopologyElement, element: TopologyElement) -> Raw:
        """A tier's two address ranges, one a zone: the caption's range halved,
        else the network's carved in order (``10.0.0.0/24``, ``10.0.1.0/24``
        for the first tier), else a variable to fill."""
        import ipaddress

        name = self.frame_name(element, "cidr", many=True)
        described = f"The address ranges of {self.label(element)}, one an availability zone."
        default: object = MISSING
        own = _CIDR.search(element.name)
        whole = _CIDR.search(network.name)
        try:
            if own is not None:
                default = [
                    str(net) for net in ipaddress.ip_network(own.group(1), strict=False).subnets(1)
                ]
            elif whole is not None:
                net = ipaddress.ip_network(whole.group(1), strict=False)
                index = self.tiers.get(network.id, 0)
                carved = net.subnets(new_prefix=min(net.prefixlen + 8, 28))
                default = [str(sub) for _n, sub in zip(range(index * 2 + 2), carved, strict=False)][
                    index * 2 :
                ]
                if len(default) != 2:
                    default = MISSING
        except ValueError:
            default = MISSING
        self.tiers[network.id] = self.tiers.get(network.id, 0) + 1
        return self.root.variable(Variable(name, "list(string)", default, described))

    def subnet_frame(
        self, element: TopologyElement, place: Place, provider: str, specs: list[ResourceSpec]
    ) -> Place:
        if place.network is None or place.network_element is None:
            self.not_written.append((element.name, "a subnet frame outside any network frame"))
            return place
        if provider == "aws" and place.zone is None:
            # a tier drawn in no zone frame spreads across two zones, as a load
            # balancer and a database subnet group need
            subnet = self.subnet_tier(place, element)
            self.subnets[place.network_element.id].append((subnet, element.type, None))
            name = self.frame_name(element, "id", many=True)
            self.root.outputs[name] = Output(
                name, subnet.every("id"), f"The ids of {element.name}, one a zone."
            )
            return _moved(place, subnet=subnet, subnet_kind=element.type)
        self.cidr_frame = (place.unit, element)
        try:
            subnet = self.write_resources(
                place, element, specs, provider, self.section(provider, "network")
            )["main"]
        except PlacementError as error:
            self.not_written.append((element.name, str(error)))
            return place
        finally:
            self.cidr_frame = None
        self.subnets[place.network_element.id].append((subnet, element.type, place.zone))
        name = self.frame_name(element, "id")
        place.unit.outputs[name] = Output(name, subnet.ref("id"), f"The id of {element.name}.")
        return _moved(place, subnet=subnet, subnet_kind=element.type)

    def subnet_tier(self, place: Place, element: TopologyElement) -> Resource:
        """An AWS subnet frame drawn in no zone: one subnet a zone, counted."""
        assert place.network is not None and place.network_element is not None
        self.use_provider("aws")
        name = self.resource_name(self.root, "aws_subnet", element)
        subnet = Resource("aws_subnet", name, self.root, counted=True)
        azs = self.zones_local(place.alias).text
        cidrs = self.tier_cidrs(place.network_element, element).text
        body: list[object] = [
            *([Attr("provider", Raw(f"aws.{place.alias}"))] if place.alias else []),
            Attr("count", Raw(f"length({azs})")),
            BLANK,
            Attr("availability_zone", Raw(f"{azs}[count.index]")),
            Attr("cidr_block", Raw(f"{cidrs}[count.index]")),
        ]
        if element.type == "subnet-public":
            body.append(Attr("map_public_ip_on_launch", True))
        noun = self.noun(element).replace("_", "-")
        body += [
            Attr("vpc_id", place.network.ref("id")),
            BLANK,
            Attr("tags", {"Name": f"${{local.name}}-{noun}-${{{azs}[count.index]}}"}),
        ]
        section = self.section("aws", "network")
        self.root.add(
            section,
            Comment(f"{element.name}{self.detail(element)}, one subnet an availability zone"),
            Block("resource", ("aws_subnet", name), body),
        )
        self.section_of[element.id] = section
        self.written[element.id] = {"main": subnet}
        return subnet

    def zone_frame(self, element: TopologyElement, place: Place) -> Place:
        caption = element.name.strip()
        if place.provider == "gcp" and re.fullmatch(r"[a-z]+-[a-z]+\d+-[a-z]", caption):
            return _moved(place, zone=caption)
        match = re.search(r"(?:zone|az)\s*([a-f])\s*$", caption, re.IGNORECASE) or re.search(
            r"\b([a-f])$", caption, re.IGNORECASE
        )
        parent = self.parent.get(element.id)
        siblings = (
            [c for c in parent.children if c.is_frame and c.type == element.type]
            if parent
            else [element]
        )
        letter = match.group(1).lower() if match else "abcdef"[min(siblings.index(element), 5)]
        region = self.region_of(place, place.provider or "aws")
        text = region.text if isinstance(region, Raw) else str(region)
        # AWS spells a zone us-east-1a, Google Cloud us-central1-a
        return _moved(place, zone=f"${{{text}}}{'-' if place.provider == 'gcp' else ''}{letter}")

    def cluster_frame(
        self, element: TopologyElement, place: Place, provider: str, specs: list[ResourceSpec]
    ) -> Place:
        table = self.mapping(provider)
        pools = []
        for child in element.children:
            component = child.component
            if component is None or component.provider != provider:
                continue
            rule = table.component(component.service_id)
            if rule is not None and rule.plumbing == "node_pool":
                pools.append(child)
        taken: set[str] = set()
        for pool in pools:
            name = self.pool_name(pool)
            wanted, n = name, 2
            while name in taken:
                name = f"{wanted[: 11 - len(str(n))]}{n}"
                n += 1
            taken.add(name)
            self.pool_name_of[pool.id] = name
        first = pools[0] if pools else None
        if first is not None:
            self.pool_name_of[element.id] = self.pool_name_of[first.id]
        try:
            cluster = self.write_resources(
                place, element, specs, provider, self.section(provider, "containers")
            )["main"]
        except PlacementError as error:
            self.not_written.append((element.name, str(error)))
            return place
        if first is not None:
            self.written[first.id] = {"main": cluster}
            self.placed[first.id] = (place, None)
            self.notes.append(f"{first.name}: written as the default node pool of {element.name}")
        return _moved(place, cluster=cluster)

    @staticmethod
    def pool_name(element: TopologyElement) -> str:
        """An AKS node pool name: lower-case letters and digits, at most
        twelve, from the first word of the caption."""

        words = re.findall(r"[a-z0-9]+", element.name.lower())
        name = (words[0] if words else "pool")[:12]
        return name if name[0].isalpha() else f"p{name}"[:12]

    # ------------------------------------------------------------ components
    def component(self, element: TopologyElement, place: Place) -> None:
        component = element.component
        if component is None:
            self.not_written.append((element.name, "no component: a label or a shape"))
            return
        if element.id in self.written:
            return
        provider = component.provider
        if provider not in PROVIDERS:
            if provider == "infragram" and component.service_id in _ACTORS:
                why = "a person or a client, not infrastructure"
            elif place.outside or provider not in ("infragram",):
                why = "outside the clouds the export writes (AWS, Azure, Google Cloud)"
            else:
                why = "a shared component with no cloud resource of its own"
            self.not_written.append((element.name, why))
            self.placed[element.id] = (place, None)
            return
        table = self.mapping(provider)
        rule = table.component(component.service_id)
        if rule is None:
            self.not_written.append(
                (element.name, f"no Terraform mapping for {provider}:{component.service_id} yet")
            )
            self.placed[element.id] = (place, None)
            return
        if provider == "aws" and component.service_id == "ec2" and self.scaled(element):
            # several of one server, or a group the diagram says scales: an
            # Auto Scaling group from a launch template, not one instance
            rule = table.component("ec2-auto-scaling") or rule
        specs = rule.scaled if rule.scaled and self.scaled(element) else rule.resources
        if rule.federated and element.id in self.github_signed_in:
            # a GitHub workflow signs in to it: the trust, not a secret
            specs = rule.federated
            if provider == "gcp":
                for api in ("iamcredentials.googleapis.com", "sts.googleapis.com"):
                    self.need_api(api, place.unit)
        if rule.plumbing == "node_pool" and place.cluster is None:
            cluster = table.frame("cluster")
            if cluster is not None:
                specs = cluster.resources
        if rule.note:
            self.notes.append(f"{element.name}: {rule.note}")
        if not specs:
            self.not_written.append((element.name, rule.note or "nothing to declare"))
            self.placed[element.id] = (place, rule)
            return
        record = (
            self.module_networks.get(place.network_element.id)
            if place.network_element is not None
            else None
        )
        if (
            record is not None
            and provider == "aws"
            and rule.plumbing in ("internet_gateway", "nat_gateway")
        ):
            self.module_gateway(record, element, place, rule)
            return
        if rule.api and provider == "gcp":
            self.need_api(rule.api, place.unit)
        if rule.requires == "network" and place.network is None:
            self.not_written.append((element.name, "it needs a network frame around it"))
            self.placed[element.id] = (place, rule)
            return
        if rule.requires == "subnet" and place.subnet is None:
            try:
                self.fallback_subnet(place)
            except PlacementError as error:
                self.not_written.append(
                    (element.name, f"it needs a subnet frame around it ({error})")
                )
                self.placed[element.id] = (place, rule)
                return
            self.notes.append(
                f"{element.name}: drawn in the network but in no subnet, "
                "so written into the network's first private subnet"
            )
        if rule.security_group and provider == "aws" and place.network is not None:
            self.security_group(place, element)
        links: list[tuple[TopologyElement, Resource, PrivateLink] | None] = [None]
        if rule.plumbing == "private_endpoint":
            links = list(self.link_targets(element)) or [None]
            if links == [None]:
                self.notes.append(
                    f"{element.name}: a wire from it to the service it reaches names what it "
                    "connects; with none, that is a variable to fill"
                )
        try:
            every: list[dict[str, Resource]] = []
            for link in links:
                self.link = link
                every.append(
                    self.write_resources(
                        place,
                        element,
                        specs,
                        provider,
                        self.section(provider, rule.category, rule.item),
                        wanted=self.noun(link[0]) if link is not None else None,
                    )
                )
        except PlacementError as error:
            if self.security_group_of.pop(element.id, None) is not None:
                self.unwrite_security_group(place, element)
            self.not_written.append((element.name, str(error)))
            self.placed[element.id] = (place, rule)
            return
        finally:
            self.link = None
        written = every[0]
        self.written[element.id] = written
        self.types_written.update(resource.type for resource in written.values())
        self.placed[element.id] = (place, rule)
        if rule.output:
            key, _, attribute = rule.output.rpartition(".")
            main_part = written.get(key or "main") or written["main"]
            name = value_name(self.noun(element), main_part.type, attribute)
            # a part the modules style leaves to the main part's registry
            # module is asked of that module: server.fully_qualified_domain_name
            part, asked = (
                (written[key or "main"], attribute)
                if (key or "main") in written
                else (written["main"], rule.output)
            )
            sensitive = rule.output_sensitive or (
                isinstance(part, ModuleResource) and part.is_sensitive(asked)
            )
            place.unit.outputs[name] = Output(
                name,
                part.ref(asked),
                f"The {_words(attribute)} of {self.label(element)}.",
                sensitive=sensitive,
            )
        if (
            rule.plumbing == "github_oidc"
            and provider == "azure"
            and element.id in self.github_signed_in
        ):
            self.azure_tenant_output()
        if rule.plumbing == "internet_gateway":
            self.internet_gateway(place, element, written["main"])
        if rule.plumbing == "nat_gateway":
            self.nat_gateway(place, element, written["main"])

    def azure_tenant_output(self) -> None:
        """The tenant's id as an output, once: azure/login asks for it beside
        the identity's client id and the subscription id."""
        if "azure_tenant_id" in self.root.outputs:
            return
        if "_data" not in self.root.files:
            self.root.add("_data", Block("data", ("azurerm_client_config", "current"), []))
        self.root.outputs["azure_tenant_id"] = Output(
            "azure_tenant_id",
            Raw("data.azurerm_client_config.current.tenant_id"),
            "The Microsoft Entra tenant's id: azure/login's tenant-id, beside the client id.",
        )

    def scaled(self, element: TopologyElement) -> bool:
        """Whether a server is a group of them: its sizing counts more than
        one, its caption or detail says so ("3 x m6i.large", "Auto Scaling"),
        or it sits in an Auto Scaling group frame."""
        sizing = element.attributes.get("sizing")
        count = sizing.get("count") if isinstance(sizing, dict) else None
        if isinstance(count, int) and not isinstance(count, bool) and count > 1:
            return True
        text = f"{element.name} {element.attributes.get('detail') or ''}".lower()
        if re.search(r"\bauto[- ]?scal", text) or re.search(
            r"\b([2-9]|\d{2,})\s*[x\u00d7]\s*[a-z]", text
        ):
            return True
        parent = self.parent.get(element.id)
        while parent is not None:
            if parent.type == "auto-scaling":
                return True
            parent = self.parent.get(parent.id)
        return False

    def security_group(self, place: Place, element: TopologyElement) -> None:
        assert place.network is not None
        group = Resource(
            "aws_security_group",
            place.unit.claim("aws_security_group", self.noun(element)),
            place.unit,
        )
        name = self.name_expr(place, element)
        section = self.section("aws", "security")
        before = len(place.unit.files.get(section, []))
        place.unit.add(
            section,
            Comment(
                f"{element.name}: its own security group; the wires to it are its ingress rules."
            ),
            Block(
                "resource",
                (group.type, group.name),
                [
                    Attr("name", name),
                    Attr("description", _aws_description(f"{element.name}{self.detail(element)}")),
                    Attr("vpc_id", place.network.ref("id")),
                    BLANK,
                    Attr("tags", {"Name": name}),
                ],
            ),
        )
        self.security_group_of[element.id] = group
        self.group_network[group.address] = (
            place.network_element.id if place.network_element else None
        )
        self.egress_rule(place.unit, group)
        self.security_items[element.id] = place.unit.files[section][before:]

    def unwrite_security_group(self, place: Place, element: TopologyElement) -> None:
        """Take back the security group written for a component whose own
        resources then could not be."""
        added = {id(item) for item in self.security_items.pop(element.id, [])}
        section = self.section("aws", "security")
        place.unit.files[section] = [
            item for item in place.unit.files[section] if id(item) not in added
        ]
        place.unit.release("aws_security_group", self.noun(element))

    def egress_rule(self, unit: Unit, group: Resource) -> None:
        name = unit.claim("aws_vpc_security_group_egress_rule", group.name)
        unit.add(
            self.section("aws", "security"),
            Block(
                "resource",
                ("aws_vpc_security_group_egress_rule", name),
                [
                    Attr("security_group_id", group.ref("id")),
                    Attr("description", "All outbound traffic"),
                    Attr("ip_protocol", "-1"),
                    Attr("cidr_ipv4", "0.0.0.0/0"),
                ],
            ),
        )

    @staticmethod
    def is_actor(element: TopologyElement) -> bool:
        """A person or a client: what a wire from stands for the internet."""
        component = element.component
        return (
            component is not None
            and component.provider == "infragram"
            and component.service_id in _ACTORS
        )

    def network_tag(self, element: TopologyElement) -> str:
        """The element's Google Cloud network tag, which its firewall rules
        name: its id as a tag is spelt (lower case, digits and hyphens, a
        letter first, 63 at most), once in the document."""
        tag = self.network_tag_of.get(element.id)
        if tag is not None:
            return tag
        wanted = re.sub(r"[^a-z0-9]+", "-", element.id.lower()).strip("-") or "element"
        if not wanted[0].isalpha():
            wanted = f"x-{wanted}"
        wanted = wanted[:63].rstrip("-")
        tag, n = wanted, 2
        while tag in self.network_tag_of.values():
            tag = f"{wanted[:60].rstrip('-')}-{n}"
            n += 1
        self.network_tag_of[element.id] = tag
        return tag

    def private_services(self, place: Place) -> Resource:
        """The network's private services connection, written once: the range
        Google's managed services (Cloud SQL) take their private addresses
        from, and the peering to them. A service on a private IP reads its
        network through the connection, so Terraform peers before it creates."""
        assert place.network is not None and place.network_element is not None
        network = place.network_element
        if network.id in self.private_connections:
            return self.private_connections[network.id]
        unit = place.unit
        noun = self.noun(network)
        address = Resource(
            "google_compute_global_address",
            unit.claim(
                "google_compute_global_address", "private_services", f"{noun}_private_services"
            ),
            unit,
        )
        connection = Resource(
            "google_service_networking_connection",
            unit.claim(
                "google_service_networking_connection",
                "private_services",
                f"{noun}_private_services",
            ),
            unit,
        )
        self.need_api("servicenetworking.googleapis.com", unit)
        part = noun.replace("_", "-")
        unit.add(
            self.section("gcp", "network"),
            Comment(
                f"The range in {self.label(network)} Google's managed services take their private "
                "addresses from, and the peering to them."
            ),
            Block(
                "resource",
                (address.type, address.name),
                [
                    Attr(
                        "name",
                        Raw(
                            f'trim(substr(lower("${{local.name}}-{part}-private-services"), 0, 63), "-")'
                        ),
                    ),
                    Attr("project", self.project_of(place)),
                    Attr("purpose", "VPC_PEERING"),
                    Attr("address_type", "INTERNAL"),
                    Attr("prefix_length", 16),
                    Attr("network", place.network.ref("id")),
                ],
            ),
            Block(
                "resource",
                (connection.type, connection.name),
                [
                    Attr("network", place.network.ref("id")),
                    Attr("service", "servicenetworking.googleapis.com"),
                    Attr("reserved_peering_ranges", [address.ref("name")]),
                ],
            ),
        )
        self.private_connections[network.id] = connection
        return connection

    def plumbing(self, element: TopologyElement) -> str | None:
        """The special role the element's rule plays, if any."""
        component = element.component
        if component is None or component.provider not in PROVIDERS:
            return None
        rule = self.mapping(component.provider).component(component.service_id)
        return rule.plumbing if rule is not None else None

    def is_endpoint(self, element: TopologyElement) -> bool:
        """Whether the element is a private endpoint (Azure)."""
        return self.plumbing(element) == "private_endpoint"

    @staticmethod
    def says_waf(element: TopologyElement) -> bool:
        """Whether the card says the gateway inspects as a web application firewall."""
        return (
            re.search(
                r"\bwaf\b", f"{element.name} {element.attributes.get('detail') or ''}".lower()
            )
            is not None
        )

    def serves_https(self, element: TopologyElement) -> bool:
        """Whether a wire reaches the element on 443."""
        return any(
            self.port(label, element) == 443 for _source, label in self.incoming.get(element.id, [])
        )

    def serving_port(self, element: TopologyElement) -> int:
        """The port the wires into the element reach it on, else 80."""
        for _source, label in self.incoming.get(element.id, []):
            port = self.port(label, element)
            if port is not None:
                return port
        return 80

    def backend_port(self, element: TopologyElement) -> int:
        """The port the element's wires out reach their targets on, else 80."""
        for connection in element.connections:
            target = self.by_id.get(connection.target)
            port = self.port(connection.label or "", target) if target is not None else None
            if port is not None:
                return port
        return 80

    def gateway(self, place: Place, element: TopologyElement, attribute: str) -> object:
        """An Azure Application Gateway's settings, from its card and wires."""
        https = self.serves_https(element)
        if attribute == "tier":
            return "WAF_v2" if self.says_waf(element) else "Standard_v2"
        if attribute == "waf_policy":
            if not self.says_waf(element):
                raise PlacementError("its card says no WAF")
            return self.waf_policy(place, element).ref("id")
        if attribute == "listener":
            return "https" if https else "http"
        if attribute == "listener_port":
            return 443 if https else 80
        if attribute == "listener_protocol":
            return "Https" if https else "Http"
        if attribute == "certificate":
            if not https:
                raise PlacementError("no wire reaches it on 443")
            return "tls"
        if attribute == "backend_port":
            return self.backend_port(element)
        if attribute == "backend_protocol":
            return "Https" if self.backend_port(element) == 443 else "Http"
        raise ValueError(
            f"the azure Terraform table uses an unknown placeholder $gateway.{attribute}"
        )

    def waf_policy(self, place: Place, element: TopologyElement) -> Resource:
        """The gateway's own web application firewall policy, written once:
        OWASP 3.2's managed rules, preventing."""
        found = self.waf_policies.get(element.id)
        if found is not None:
            return found
        unit = place.unit
        noun = self.noun(element)
        found = Resource(
            "azurerm_web_application_firewall_policy",
            unit.claim("azurerm_web_application_firewall_policy", noun, f"{noun}_waf"),
            unit,
        )
        unit.add(
            self.section("azure", "edge", "application_gateway"),
            Comment(f"{element.name}: its web application firewall policy, OWASP's managed rules."),
            Block(
                "resource",
                (found.type, found.name),
                [
                    Attr("name", self.name_expr(place, element, "+waf")),
                    Attr("location", self.location_of(place)),
                    Attr(
                        "resource_group_name",
                        self.placeholder("resource_group", place, element, {}, "azure"),
                    ),
                    BLANK,
                    Block(
                        "policy_settings", (), [Attr("enabled", True), Attr("mode", "Prevention")]
                    ),
                    BLANK,
                    Block(
                        "managed_rules",
                        (),
                        [
                            Block(
                                "managed_rule_set",
                                (),
                                [Attr("type", "OWASP"), Attr("version", "3.2")],
                            )
                        ],
                    ),
                    BLANK,
                    Attr("tags", Raw("local.tags")),
                ],
            ),
        )
        self.waf_policies[element.id] = found
        return found

    def backend_pools(self, element: TopologyElement) -> list[object]:
        """The backend pool of each Application Gateway wired to the element."""
        pools: list[object] = []
        for source, _label in self.incoming.get(element.id, []):
            gateway = self.written.get(source.id, {}).get("main")
            if self.plumbing(source) == "application_gateway" and gateway is not None:
                pools.append(Raw(f'"${{{gateway.ref("id").text}}}/backendAddressPools/backend"'))
                self.pool_members.add((source.id, element.id))
        if not pools:
            raise PlacementError("no Application Gateway is wired to it")
        return pools

    def link_targets(
        self, element: TopologyElement
    ) -> Iterable[tuple[TopologyElement, Resource, PrivateLink]]:
        """The services a private endpoint is wired to that take one, each
        with the resource it connects to and how, once each."""
        seen: set[str] = set()
        for connection in element.connections:
            target = self.by_id.get(connection.target)
            if target is None or target.id in seen or target.component is None:
                continue
            if target.component.provider not in PROVIDERS or target.id not in self.written:
                continue
            rule = self.mapping(target.component.provider).component(target.component.service_id)
            if rule is None or rule.private_link is None:
                continue
            written = self.written[target.id]
            seen.add(target.id)
            yield (
                target,
                written.get(rule.private_link.resource) or written["main"],
                rule.private_link,
            )

    def private_dns_zone(self, place: Place, element: TopologyElement, zone: str) -> Resource:
        """The private DNS zone a service's private address resolves in,
        written once, and linked once to each network an endpoint in it
        sits in, so a machine there finds the private address by name."""
        unit = place.unit
        found = self.dns_zones.get(zone)
        section = self.section("azure", "network")
        noun = identifier(zone.split(".")[1] if zone.count(".") > 1 else zone)
        if found is None:
            found = Resource(
                "azurerm_private_dns_zone",
                unit.claim("azurerm_private_dns_zone", noun, f"{noun}_zone"),
                unit,
            )
            unit.add(
                section,
                Comment(
                    f"The private DNS zone {zone}: what a private endpoint connects "
                    "resolves to its private address in it."
                ),
                Block(
                    "resource",
                    (found.type, found.name),
                    [
                        Attr("name", zone),
                        Attr(
                            "resource_group_name",
                            self.placeholder("resource_group", place, element, {}, "azure"),
                        ),
                        BLANK,
                        Attr("tags", Raw("local.tags")),
                    ],
                ),
            )
            self.dns_zones[zone] = found
        network = place.network_element
        if (
            place.network is not None
            and network is not None
            and (zone, network.id) not in self.dns_links
        ):
            self.dns_links.add((zone, network.id))
            link = unit.claim(
                "azurerm_private_dns_zone_virtual_network_link",
                found.name,
                f"{found.name}_{self.noun(network)}",
            )
            unit.add(
                section,
                Block(
                    "resource",
                    ("azurerm_private_dns_zone_virtual_network_link", link),
                    [
                        Attr(
                            "name",
                            Raw(
                                f'"${{local.name}}-{found.name.replace("_", "-")}-{self.noun(network).replace("_", "-")}"'
                            ),
                        ),
                        Attr("resource_group_name", found.ref("resource_group_name")),
                        Attr("private_dns_zone_name", found.ref("name")),
                        Attr("virtual_network_id", place.network.ref("id")),
                        BLANK,
                        Attr("tags", Raw("local.tags")),
                    ],
                ),
            )
        return found

    def need_api(self, api: str, unit: Unit) -> None:
        name = identifier(api.split(".")[0])
        self.apis[api] = name
        address = f"google_project_service.{name}"
        if not unit.is_root and address not in unit.depends_on:
            unit.depends_on.append(address)

    # ------------------------------------------------------------ plumbing
    def internet_gateway(
        self, place: Place, element: TopologyElement, gateway: Resource, through: str | None = None
    ) -> None:
        assert place.network is not None and place.network_element is not None
        network = self.noun(place.network_element)
        table = place.unit.claim("aws_route_table", "public", f"{network}_public")
        place.unit.add(
            self.section("aws", "network"),
            Comment(f"Public subnets reach the internet through {through or element.name}."),
            Block(
                "resource",
                ("aws_route_table", table),
                [
                    Attr("vpc_id", place.network.ref("id")),
                    BLANK,
                    Block(
                        "route",
                        (),
                        [Attr("cidr_block", "0.0.0.0/0"), Attr("gateway_id", gateway.ref("id"))],
                    ),
                    BLANK,
                    Attr("tags", {"Name": f"{self.name_expr(place, element)}-public"}),
                ],
            ),
        )
        for subnet, kind, _zone in self.subnets.get(place.network_element.id, []):
            if kind == "subnet-public":
                self.associate(place.unit, subnet, f"aws_route_table.{table}")

    def implied_internet_gateways(self) -> None:
        """A subnet is public because its route table reaches an internet
        gateway: an AWS network with public subnets and no gateway drawn in it
        is written with one."""

        for place, element in self.networks:
            if (
                place.provider != "aws"
                or place.network is None
                or element.id in self.module_networks
            ):
                continue
            public = [s for s in self.subnets.get(element.id, []) if s[1] == "subnet-public"]
            if not public or all(s[0].address in self.route_table_of for s in public):
                continue
            gateway = Resource(
                "aws_internet_gateway",
                place.unit.claim("aws_internet_gateway", "main", self.noun(element)),
                place.unit,
            )
            place.unit.add(
                self.section("aws", "network"),
                Comment(
                    f"{element.name} has public subnets, so it has an internet gateway; "
                    "the diagram draws none."
                ),
                Block(
                    "resource",
                    (gateway.type, gateway.name),
                    [
                        Attr("vpc_id", place.network.ref("id")),
                        BLANK,
                        Attr("tags", {"Name": f"{self.name_expr(place, element)}-igw"}),
                    ],
                ),
            )
            self.internet_gateway(place, element, gateway, "the internet gateway")
            self.notes.append(
                f"{element.name}: its public subnets need an internet gateway and the "
                "diagram draws none, so one is written"
            )

    def nat_gateway(self, place: Place, element: TopologyElement, gateway: Resource) -> None:
        assert place.network is not None
        network = (
            self.noun(place.network_element) if place.network_element is not None else gateway.name
        )
        table = place.unit.claim(
            "aws_route_table", "private", f"{network}_private", f"{gateway.name}_private"
        )
        place.unit.add(
            self.section("aws", "network"),
            Comment(f"Private subnets reach out through {element.name}."),
            Block(
                "resource",
                ("aws_route_table", table),
                [
                    Attr("vpc_id", place.network.ref("id")),
                    BLANK,
                    Block(
                        "route",
                        (),
                        [
                            Attr("cidr_block", "0.0.0.0/0"),
                            Attr("nat_gateway_id", gateway.ref("id")),
                        ],
                    ),
                    BLANK,
                    Attr("tags", {"Name": f"{self.name_expr(place, element)}-private"}),
                ],
            ),
        )
        self.nat_tables.append((place, table, place.zone))

    def associate(self, unit: Unit, subnet: Resource, table: str) -> None:
        if subnet.address in self.route_table_of:
            return
        self.route_table_of[subnet.address] = table
        name = unit.claim("aws_route_table_association", subnet.name)
        if subnet.counted:
            body: list[object] = [
                Attr("count", Raw(f"length({subnet.address})")),
                BLANK,
                Attr("route_table_id", Raw(f"{table}.id")),
                Attr("subnet_id", Raw(f"{subnet.address}[count.index].id")),
            ]
        else:
            body = [Attr("route_table_id", Raw(f"{table}.id")), Attr("subnet_id", subnet.ref("id"))]
        unit.add(
            self.section("aws", "network"),
            Block("resource", ("aws_route_table_association", name), body),
        )

    def associate_nat_tables(self) -> None:
        for place, table, zone in self.nat_tables:
            assert place.network_element is not None
            private = [
                s for s in self.subnets.get(place.network_element.id, []) if s[1] != "subnet-public"
            ]
            same_zone = [s for s in private if zone is not None and s[2] == zone]
            for subnet, _kind, _zone in same_zone or private:
                self.associate(place.unit, subnet, f"aws_route_table.{table}")

    # ------------------------------------------------------------ wires
    def write_wires(self) -> None:
        listeners: dict[str, list[int]] = {}
        targets: dict[tuple[str, int], list[TopologyElement]] = {}
        for source in self.project.topology.walk():
            for connection in source.connections:
                target = self.by_id.get(connection.target)
                if target is None:
                    continue
                wire = Wire(source, target, connection.label or "")
                self.wires.append(wire)
                wire.written_as = self.write_wire(source, target, wire.label, listeners, targets)
                if connection.direction == "both":
                    reverse = self.write_wire(target, source, wire.label, listeners, targets)
                    wire.written_as += f"; and back: {reverse}"
        self.write_load_balancers(listeners, targets)
        self.write_google_load_balancers()
        self.write_ci_policies()

    def write_wire(
        self,
        source: TopologyElement,
        target: TopologyElement,
        label: str,
        listeners: dict[str, list[int]],
        targets: dict[tuple[str, int], list[TopologyElement]],
    ) -> str:
        if (
            self.is_endpoint(source)
            and source.id in self.written
            and any(linked.id == target.id for linked, _part, _how in self.link_targets(source))
        ):
            return "the private endpoint's connection to it, resolved in its private DNS zone"
        if self.is_aws(source, "waf") and source.id in self.written:
            return self.web_acl_association(source, target)
        if (
            self.plumbing(source) in ("github_oidc", "service_principal")
            and source.id in self.written
        ):
            granted = self.ci_grant(source, target)
            if granted is not None:
                return granted
        if self.plumbing(target) == "service_principal" and target.id in self.written:
            if source.component is not None and source.component.service_id == "app-registrations":
                return "its service principal in the tenant, which holds the roles"
            # a person granting it roles, Entra ID issuing its token: the story, not a resource
            return "not written: the service principal's roles are its own wires to what it deploys"
        if (
            self.is_github_side(source)
            and self.plumbing(target) == "github_oidc"
            and target.id in self.written
        ):
            repository, environment, branch = self.github_context()
            where = f"in the {environment} environment" if environment else f"on {branch}"
            return f"the OIDC trust: workflows of {repository or 'the repository'} {where} sign in, no secret"
        if (
            self.is_google(source, "cloud-armor")
            and self.is_google(target, "cloud-load-balancing")
            and source.id in self.written
            and target.id in self.written
        ):
            self.lb_armor.setdefault(target.id, source)
            return "the security policy of the load balancer's backend services"
        if (
            self.is_google(source, "cloud-cdn")
            and self.is_google(target, "cloud-load-balancing")
            and target.id in self.written
        ):
            self.lb_cdn.add(target.id)
            return "Cloud CDN switched on in the load balancer's backend services"
        if self.is_google(source, "cloud-load-balancing") and source.id in self.written:
            return self.google_backend(source, target, label)
        if (
            self.is_google(target, "cloud-load-balancing")
            and target.id in self.written
            and any(
                self.written.get(c.target, {}).get("main") is not None
                and self.written[c.target]["main"].type in _GOOGLE_BACKENDS
                for c in target.connections
            )
        ):
            https = self.serves_https(target)
            return f"the load balancer's {'HTTPS' if https else 'HTTP'} forwarding rule, on {443 if https else 80}"
        if self.plumbing(target) == "application_gateway" and target.id in self.written:
            https = self.serves_https(target)
            return (
                f"the gateway's {'HTTPS' if https else 'HTTP'} listener on {443 if https else 80}"
            )
        written = self.write_wire_rule(source, target, label, listeners, targets)
        if (source.id, target.id) in self.pool_members:
            written = (
                "" if written.startswith("not written") else f"{written}; "
            ) + f"a member of its backend pool, on {self.backend_port(source)}"
        return written

    @staticmethod
    def is_github_side(element: TopologyElement) -> bool:
        """Whether the element stands for a GitHub workflow (its repository,
        Actions, its runner, its token or the token's issuer)."""
        component = element.component
        return (
            component is not None
            and component.provider == "infragram"
            and component.service_id in _GITHUB_SIDE
        )

    def github_context(self) -> tuple[str | None, str | None, str]:
        """The diagram's GitHub repository (the GitHub or Actions card's
        ``owner/repo``), environment (an approval gate's, ``production`` when it
        names none) and branch (a Git branch card's name, else ``main``)."""
        if self.github is None:
            repository: str | None = None
            environment: str | None = None
            branch: str | None = None
            for element in self.project.topology.walk():
                component = element.component
                if component is None or component.provider != "infragram":
                    continue
                text = f"{element.name} {element.attributes.get('detail') or ''}"
                if (
                    component.service_id in ("brand-github", "brand-github-actions")
                    and repository is None
                ):
                    found = _REPOSITORY.search(text)
                    repository = found.group(1) if found else None
                elif component.service_id == "approval-gate" and environment is None:
                    found = re.search(
                        r"\benvironment\s*[:=]?\s*([A-Za-z0-9._-]+)", text, re.IGNORECASE
                    )
                    environment = found.group(1) if found else "production"
                elif component.service_id == "git-branch" and branch is None:
                    found = re.search(r"[A-Za-z0-9._/-]+", element.name)
                    branch = found.group(0) if found else None
            self.github = (repository, environment, branch or "main")
        return self.github

    def github_subject(self) -> str:
        """The ``sub`` a workflow's token must carry, as the configuration
        writes it, its parts variables with the diagram's values."""
        repository, environment, branch = self.github_context()
        self.root.variable(
            Variable(
                "github_repository",
                "string",
                repository or MISSING,
                "The GitHub repository (owner/name) whose workflows may sign in.",
            )
        )
        if environment:
            self.root.variable(
                Variable(
                    "github_environment",
                    "string",
                    environment,
                    "The GitHub environment a workflow must deploy from to sign in.",
                )
            )
            return "repo:${var.github_repository}:environment:${var.github_environment}"
        self.root.variable(
            Variable(
                "github_branch", "string", branch, "The branch a workflow must run on to sign in."
            )
        )
        return "repo:${var.github_repository}:ref:refs/heads/${var.github_branch}"

    def github_value(
        self, place: Place, element: TopologyElement, attribute: str, written: dict[str, Resource]
    ) -> object:
        subject = self.github_subject()
        if attribute == "subject":
            return Raw(f'"{subject}"')
        if attribute == "condition":
            _repository, environment, _branch = self.github_context()
            narrower = (
                "assertion.environment == '${var.github_environment}'"
                if environment
                else "assertion.ref == 'refs/heads/${var.github_branch}'"
            )
            return Raw(f"\"assertion.repository == '${{var.github_repository}}' && {narrower}\"")
        if attribute == "principal_set":
            pool = written["main"]
            return Raw(
                f'"principalSet://iam.googleapis.com/${{{pool.ref("name").text}}}'
                '/attribute.repository/${var.github_repository}"'
            )
        if attribute == "pool_id":
            # 4 to 32 letters, digits and hyphens; Google keeps the gcp- prefix for itself
            return Raw(
                'trim(substr(replace(lower("${local.name}-github"), "/^gcp-/", "ci-"), 0, 32), "-")'
            )
        if attribute == "trust_policy":
            return self.aws_github_trust(place, element, subject)
        raise ValueError(f"the Terraform table uses an unknown placeholder $github.{attribute}")

    def aws_github_trust(self, place: Place, element: TopologyElement, subject: str) -> Raw:
        """A role's trust in GitHub's OIDC issuer: the account's provider for
        it (written once), and a policy document that lets a workflow of the
        repository, in its environment or on its branch, assume the role."""
        unit = place.unit
        section = self.section("aws", "security")
        if self.github_provider is None:
            self.github_provider = Resource(
                "aws_iam_openid_connect_provider",
                unit.claim("aws_iam_openid_connect_provider", "github"),
                unit,
            )
            unit.add(
                section,
                Comment(
                    "GitHub's OIDC issuer, once an account: the tokens it signs are what "
                    "a workflow signs in with."
                ),
                Block(
                    "resource",
                    (self.github_provider.type, self.github_provider.name),
                    [
                        Attr("url", GITHUB_ISSUER),
                        Attr("client_id_list", ["sts.amazonaws.com"]),
                        BLANK,
                        Attr("tags", {"Name": Raw('"${local.name}-github"')}),
                    ],
                ),
            )
        name = unit.claim("aws_iam_policy_document", f"{self.noun(element)}_trust")
        unit.add(
            section,
            Comment(
                f"Who may assume {self.label(element)}: a GitHub workflow of the repository, "
                "with a token for AWS."
            ),
            Block(
                "data",
                ("aws_iam_policy_document", name),
                [
                    Block(
                        "statement",
                        (),
                        [
                            Attr("actions", ["sts:AssumeRoleWithWebIdentity"]),
                            BLANK,
                            Block(
                                "principals",
                                (),
                                [
                                    Attr("type", "Federated"),
                                    Attr("identifiers", [self.github_provider.ref("arn")]),
                                ],
                            ),
                            BLANK,
                            Block(
                                "condition",
                                (),
                                [
                                    Attr("test", "StringEquals"),
                                    Attr("variable", "token.actions.githubusercontent.com:aud"),
                                    Attr("values", ["sts.amazonaws.com"]),
                                ],
                            ),
                            BLANK,
                            Block(
                                "condition",
                                (),
                                [
                                    Attr("test", "StringLike"),
                                    Attr("variable", "token.actions.githubusercontent.com:sub"),
                                    Attr("values", [Raw(f'"{subject}"')]),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )
        return Raw(f"data.aws_iam_policy_document.{name}.json")

    def ci_grant(self, source: TopologyElement, target: TopologyElement) -> str | None:
        """A wire from a pipeline's cloud identity to what it deploys to:
        what the target's ``ci_access`` says it needs, granted to the identity."""
        component = target.component
        if (
            component is None
            or component.provider not in PROVIDERS
            or target.id not in self.written
        ):
            return None
        rule = self.mapping(component.provider).component(component.service_id)
        if rule is None or rule.ci_access is None:
            return None
        provider = source.component.provider if source.component is not None else ""
        if component.provider != provider:
            return "not written: a pipeline's identity reaches its own cloud's resources"
        identity = self.written[source.id]
        main = self.written[target.id]["main"]
        place = self.placed[source.id][0]
        unit = place.unit
        access = rule.ci_access
        source_rule = (
            self.mapping(provider).component(source.component.service_id)
            if source.component is not None and provider in PROVIDERS
            else None
        )
        principal = source_rule.principal if source_rule is not None else "principal_id"
        if provider == "azure" and access.roles and not principal:
            return (
                "not written: an app registration holds no roles; its service principal does "
                "(an Enterprise application wired from it)"
            )
        if provider == "aws":
            self.ci_statements.setdefault(source.id, []).append((target, access.statements))
            actions = sorted(
                {action for statement in access.statements for action in statement.actions}
            )
            return f"the role's policy: {', '.join(actions)}"
        if provider == "azure" and access.roles:
            for role_name in access.roles:
                wanted = f"{self.noun(source)}_{self.noun(target)}"
                name = unit.claim(
                    "azurerm_role_assignment", wanted, f"{wanted}_{identifier(role_name)}"
                )
                unit.add(
                    self.section("azure", "security"),
                    Block(
                        "resource",
                        ("azurerm_role_assignment", name),
                        [
                            Attr("scope", main.ref("id")),
                            Attr("role_definition_name", role_name),
                            Attr("principal_id", identity["main"].ref(principal)),
                            Attr("principal_type", "ServicePrincipal"),
                        ],
                    ),
                )
            return f"role assignment: {', '.join(access.roles)} on it"
        if provider == "gcp" and access.roles:
            account = identity.get("account")
            if account is None:
                return (
                    "not written: a Workload Identity pool grants through its service account, "
                    "which a GitHub workflow wired to it brings"
                )
            granted = []
            for role_name in access.roles:
                if (source.id, role_name) in self.ci_roles:
                    continue
                self.ci_roles.add((source.id, role_name))
                granted.append(role_name)
                name = unit.claim(
                    "google_project_iam_member",
                    f"{self.noun(source)}_{identifier(role_name.rpartition('/')[2])}",
                )
                unit.add(
                    self.section("gcp", "security"),
                    Block(
                        "resource",
                        ("google_project_iam_member", name),
                        [
                            Attr("project", self.project_of(place)),
                            Attr("role", role_name),
                            Attr(
                                "member", Raw(f'"serviceAccount:${{{account.ref("email").text}}}"')
                            ),
                        ],
                    ),
                )
            return (
                f"project roles: {', '.join(granted)}, to its service account"
                if granted
                else f"project roles: {', '.join(access.roles)}, granted already"
            )
        return None

    def write_ci_policies(self) -> None:
        """Each AWS role's policy: one statement a grant its wires made, on the
        resources they point at."""
        for role_id, grants in self.ci_statements.items():
            role = self.written[role_id]["main"]
            element = self.by_id[role_id]
            unit = role.unit
            noun = self.noun(element)
            statements: list[object] = []
            seen: set[str] = set()
            for target, target_statements in grants:
                main = self.written[target.id]["main"]
                for statement in target_statements:
                    resources: list[object] = []
                    for wanted in statement.resources:
                        attribute, _, path = wanted.partition("/")
                        if wanted == "*":
                            resources.append("*")
                        elif path:
                            resources.append(Raw(f'"${{{main.ref(attribute).text}}}/{path}"'))
                        else:
                            resources.append(main.ref(attribute))
                    key = repr((statement.actions, [getattr(r, "text", r) for r in resources]))
                    if key in seen:
                        continue
                    seen.add(key)
                    if statements:
                        statements.append(BLANK)
                    statements.append(
                        Block(
                            "statement",
                            (),
                            [
                                Attr("actions", list(statement.actions)),
                                Attr("resources", resources),
                            ],
                        )
                    )
            document = unit.claim("aws_iam_policy_document", f"{noun}_access")
            policy = unit.claim("aws_iam_role_policy", noun)
            unit.add(
                self.section("aws", "security"),
                Comment(f"What {self.label(element)} may do: what its wires reach, and no more."),
                Block("data", ("aws_iam_policy_document", document), statements),
                Block(
                    "resource",
                    ("aws_iam_role_policy", policy),
                    [
                        Attr("name", Raw('"${local.name}-' + noun.replace("_", "-") + '"')),
                        Attr("role", role.ref("id")),
                        Attr("policy", Raw(f"data.aws_iam_policy_document.{document}.json")),
                    ],
                ),
            )

    @staticmethod
    def is_aws(element: TopologyElement, service_id: str) -> bool:
        component = element.component
        return (
            component is not None
            and component.provider == "aws"
            and component.service_id == service_id
        )

    def web_acl_association(self, source: TopologyElement, target: TopologyElement) -> str:
        """A wire from AWS WAF: its web ACL associated with the load balancer or
        API stage the wire points at."""
        main = self.written.get(target.id, {}).get("main")
        if main is None:
            return "not written: its target is no resource"
        if self.is_aws(target, "cloudfront"):
            return "not written: a CloudFront distribution names its web ACL itself, of scope CLOUDFRONT"
        if main.type not in _WEB_ACL_TARGETS:
            return "not written: a web ACL protects a load balancer or an API stage"
        acl = self.written[source.id]["main"]
        unit = acl.unit
        name = unit.claim("aws_wafv2_web_acl_association", self.noun(target))
        unit.add(
            self.section_of[source.id],
            Block(
                "resource",
                ("aws_wafv2_web_acl_association", name),
                [
                    Attr("resource_arn", main.ref("arn")),
                    Attr("web_acl_arn", acl.ref("arn")),
                ],
            ),
        )
        return "the web ACL's association with it"

    @staticmethod
    def is_google(element: TopologyElement, service_id: str) -> bool:
        component = element.component
        return (
            component is not None
            and component.provider == "gcp"
            and component.service_id == service_id
        )

    def google_backend(self, balancer: TopologyElement, target: TopologyElement, label: str) -> str:
        """A wire out of a Google load balancer: its target is a backend (a
        managed instance group, an instance, a Cloud Run service), reached
        through a firewall rule from Google's front ends when it wears a tag."""
        main = self.written.get(target.id, {}).get("main")
        if main is None:
            return "not written: its target is no resource"
        if main.type not in _GOOGLE_BACKENDS:
            return "not written: a load balancer's backend here is a managed instance group, an instance or Cloud Run"
        port = self.port(label, target) or 80
        self.lb_backends.setdefault(balancer.id, []).append((target, port))
        written = f"a backend of the load balancer, on {port}"
        rule = self.placed.get(target.id, (None, None))[1]
        if rule is not None and rule.security_group:
            written = f"{self.firewall_rule(balancer, target, label or str(port))}; {written}"
        return written

    def write_google_load_balancers(self) -> None:
        """Each Google load balancer the wires gave backends: a health check
        and backend service a backend, a URL map to the first, a proxy (HTTPS
        with a Google-managed certificate when a wire reaches it on 443) and
        the forwarding rule on its reserved address."""
        for balancer_id, backends in self.lb_backends.items():
            balancer = self.by_id[balancer_id]
            address = self.written[balancer_id]["main"]
            place = self.placed[balancer_id][0]
            unit = address.unit
            section = self.section_of[balancer_id]
            noun = self.noun(balancer)
            project = self.project_of(place)
            armor = self.lb_armor.get(balancer_id)
            services: list[Resource] = []
            for target, port in backends:
                main = self.written[target.id]["main"]
                target_place = self.placed[target.id][0]
                wanted = self.noun(target)
                items: list[object] = [Comment(f"{balancer.name} to {target.name}, on {port}.")]
                body: list[object] = [
                    Attr("name", self.name_expr(place, target, "lower63")),
                    Attr("project", project),
                    Attr("load_balancing_scheme", "EXTERNAL_MANAGED"),
                    Attr("protocol", "HTTPS" if port == 443 else "HTTP"),
                ]
                if (
                    main.type == "google_cloud_run_v2_service"
                    or main.type == "google_cloud_run_service"
                ):
                    group = Resource(
                        "google_compute_region_network_endpoint_group",
                        unit.claim(
                            "google_compute_region_network_endpoint_group",
                            wanted,
                            f"{noun}_{wanted}",
                        ),
                        unit,
                    )
                    items.append(
                        Block(
                            "resource",
                            (group.type, group.name),
                            [
                                Attr("name", self.name_expr(place, target, "lower63")),
                                Attr("project", project),
                                Attr("region", self.region_of(target_place, "gcp")),
                                Attr("network_endpoint_type", "SERVERLESS"),
                                BLANK,
                                Block("cloud_run", (), [Attr("service", main.ref("name"))]),
                            ],
                        )
                    )
                    backend = group.ref("id")
                else:
                    check = Resource(
                        "google_compute_health_check",
                        unit.claim("google_compute_health_check", wanted, f"{noun}_{wanted}"),
                        unit,
                    )
                    items.append(
                        Block(
                            "resource",
                            (check.type, check.name),
                            [
                                Attr("name", self.name_expr(place, target, "lower63")),
                                Attr("project", project),
                                BLANK,
                                Block(
                                    "https_health_check" if port == 443 else "http_health_check",
                                    (),
                                    [Attr("port", port)],
                                ),
                            ],
                        )
                    )
                    if main.type == "google_compute_instance":
                        # one instance: an unmanaged group holding it is the backend
                        group = Resource(
                            "google_compute_instance_group",
                            unit.claim("google_compute_instance_group", wanted, f"{noun}_{wanted}"),
                            unit,
                        )
                        items.append(
                            Block(
                                "resource",
                                (group.type, group.name),
                                [
                                    Attr("name", self.name_expr(place, target, "lower63")),
                                    Attr("project", project),
                                    Attr("zone", main.ref("zone")),
                                    Attr("instances", [main.ref("self_link")]),
                                    BLANK,
                                    Block(
                                        "named_port", (), [Attr("name", "http"), Attr("port", port)]
                                    ),
                                ],
                            )
                        )
                        backend = group.ref("self_link")
                    else:
                        backend = main.ref("instance_group")
                    body += [Attr("port_name", "http"), Attr("health_checks", [check.ref("id")])]
                if armor is not None:
                    body.append(Attr("security_policy", self.written[armor.id]["main"].ref("id")))
                if balancer_id in self.lb_cdn:
                    body.append(Attr("enable_cdn", True))
                body += [BLANK, Block("backend", (), [Attr("group", backend)])]
                service = Resource(
                    "google_compute_backend_service",
                    unit.claim("google_compute_backend_service", wanted, f"{noun}_{wanted}"),
                    unit,
                )
                items.append(Block("resource", (service.type, service.name), body))
                services.append(service)
                unit.add(section, *items)
            https = self.serves_https(balancer)
            url_map = Resource(
                "google_compute_url_map", unit.claim("google_compute_url_map", "main", noun), unit
            )
            items = [
                Comment(f"{balancer.name}: its URL map, proxy and forwarding rule."),
                Block(
                    "resource",
                    (url_map.type, url_map.name),
                    [
                        Attr("name", self.name_expr(place, balancer, "lower63")),
                        Attr("project", project),
                        Attr("default_service", services[0].ref("id")),
                    ],
                ),
            ]
            proxy_body: list[object] = [
                Attr("name", self.name_expr(place, balancer, "lower63")),
                Attr("project", project),
                Attr("url_map", url_map.ref("id")),
            ]
            if https:
                certificate = Resource(
                    "google_compute_managed_ssl_certificate",
                    unit.claim("google_compute_managed_ssl_certificate", "main", noun),
                    unit,
                )
                domains = self.required_variable(
                    place,
                    Variable(
                        f"{noun}_domains",
                        "list(string)",
                        MISSING,
                        f"The domains the certificate of {self.label(balancer)} covers; each must point at its address.",
                    ),
                )
                items.append(
                    Block(
                        "resource",
                        (certificate.type, certificate.name),
                        [
                            Attr("name", self.name_expr(place, balancer, "lower63")),
                            Attr("project", project),
                            BLANK,
                            Block("managed", (), [Attr("domains", domains)]),
                        ],
                    )
                )
                proxy_body.append(Attr("ssl_certificates", [certificate.ref("id")]))
            proxy_type = (
                "google_compute_target_https_proxy" if https else "google_compute_target_http_proxy"
            )
            proxy = Resource(proxy_type, unit.claim(proxy_type, "main", noun), unit)
            items.append(Block("resource", (proxy.type, proxy.name), proxy_body))
            rule_name = unit.claim(
                "google_compute_global_forwarding_rule",
                "https" if https else "http",
                f"{noun}_{'https' if https else 'http'}",
            )
            items.append(
                Block(
                    "resource",
                    ("google_compute_global_forwarding_rule", rule_name),
                    [
                        Attr("name", self.name_expr(place, balancer, "lower63")),
                        Attr("project", project),
                        Attr("load_balancing_scheme", "EXTERNAL_MANAGED"),
                        Attr("ip_address", address.ref("address")),
                        Attr("port_range", "443" if https else "80"),
                        Attr("target", proxy.ref("id")),
                    ],
                )
            )
            unit.add(section, *items)

    def write_wire_rule(
        self,
        source: TopologyElement,
        target: TopologyElement,
        label: str,
        listeners: dict[str, list[int]],
        targets: dict[tuple[str, int], list[TopologyElement]],
    ) -> str:
        target_group = self.security_group_of.get(target.id)
        if target_group is None:
            component = target.component
            if target.id not in self.written:
                return "not written: its target is no resource"
            rule = self.placed.get(target.id, (None, None))[1]
            if component is not None and component.provider == "gcp":
                if rule is not None and rule.security_group:
                    return self.firewall_rule(source, target, label)
                return "not written: on Google Cloud a wire is a firewall rule to a Compute Engine instance only"
            if component is not None and component.provider == "azure":
                if rule is not None and rule.security_group and "nsg" in self.written[target.id]:
                    return self.nsg_rule(source, target, label)
                return "not written: on Azure a wire is a network security group rule to a virtual machine or scale set only"
            if component is None or component.provider != "aws":
                return (
                    "not written: a wire is written as a rule on AWS, Azure and Google Cloud only"
                )
            return "not written: its target has no security group"
        place, target_rule = self.placed[target.id]
        source_group = self.security_group_of.get(source.id)
        component = source.component
        public = (
            component is not None
            and component.provider == "infragram"
            and component.service_id in _ACTORS
        )
        unit = target_group.unit
        if source_group is not None and self.apart(source_group, target_group):
            return "not written: its two ends sit in different networks"
        if source_group is None and not public:
            return "not written: its source has no security group"
        if public and place.subnet_kind != "subnet-public":
            return "not written: the internet cannot reach a private subnet"
        port = self.port(label, target)
        rule_name = unit.claim(
            "aws_vpc_security_group_ingress_rule",
            f"{self.noun(target)}_from_{'internet' if public else self.noun(source)}",
        )
        port_value: object = (
            port
            if port is not None
            else self.required_variable(
                place,
                Variable(
                    f"{rule_name}_port",
                    "number",
                    MISSING,
                    f"The port {self.label(source)} reaches {self.label(target)} on.",
                ),
            )
        )
        body: list[object] = [
            Attr("security_group_id", target_group.ref("id")),
            Attr("description", _aws_description(label or f"From {source.name}")),
            Attr("ip_protocol", "tcp"),
            Attr("from_port", port_value),
            Attr("to_port", port_value),
        ]
        if public:
            body.append(Attr("cidr_ipv4", "0.0.0.0/0"))
        else:
            assert source_group is not None
            body.append(Attr("referenced_security_group_id", source_group.ref("id")))
        self.ingress_rule(unit, target_group, rule_name, body)
        written = (
            f"security group rule, tcp {port}"
            if port is not None
            else "security group rule, its port a variable to fill"
        )
        if public:
            written += ", from the internet"
        if target_rule is not None and target_rule.plumbing == "load_balancer" and port is not None:
            listeners.setdefault(target.id, []).append(port)
        source_rule = self.placed.get(source.id, (None, None))[1]
        instance = self.written.get(target.id, {}).get("main")
        if (
            source_rule is not None
            and source_rule.plumbing == "load_balancer"
            and instance is not None
            and instance.type in ("aws_instance", "aws_autoscaling_group")
        ):
            targets.setdefault((source.id, port or 80), []).append(target)
            written += "; a load balancer target"
        return written

    def apart(self, one: Resource, other: Resource) -> bool:
        """Whether two security groups sit in different networks."""
        return self.group_network.get(one.address) != self.group_network.get(other.address)

    def ingress_rule(self, unit: Unit, group: Resource, name: str, body: list[object]) -> None:
        """A wire to a component that wears a security group: an ingress rule
        on it, ``body`` its attributes."""
        unit.add(
            self.section("aws", "security"),
            Block("resource", ("aws_vpc_security_group_ingress_rule", name), body),
        )

    def firewall_rule(self, source: TopologyElement, target: TopologyElement, label: str) -> str:
        """A wire to a Google Cloud instance: a firewall rule to its network
        tag, from the internet, from the source instance's tag, or from the
        range of the subnet the source sits in."""
        place = self.placed[target.id][0]
        assert place.network is not None
        unit = place.unit
        tag = self.network_tag(target)
        kind, _, where = self.origin(source, place)
        if self.is_google(source, "cloud-load-balancing"):
            kind = "front ends"
        if kind.startswith("no: "):
            return f"not written: {kind[4:]}"
        if kind == "internet":
            origin: list[object] = [Attr("source_ranges", ["0.0.0.0/0"])]
            written = "from the internet"
            origin_name = "internet"
        elif kind == "front ends":
            origin = [Attr("source_ranges", list(GOOGLE_FRONT_ENDS))]
            written = "from Google's load balancers and health checks"
            origin_name = self.noun(source).replace("_", "-")
        elif (
            kind == "element"
            and source.component is not None
            and source.component.provider == "gcp"
        ):
            origin_name = self.network_tag(source)
            origin = [Attr("source_tags", [origin_name])]
            written = f"from the {origin_name} tag"
        elif where is not None and where.subnet is not None:
            origin_name = re.sub(r"[^a-z0-9]+", "-", source.id.lower()).strip("-") or "source"
            origin = [Attr("source_ranges", [where.subnet.ref("ip_cidr_range")])]
            written = "from its subnet's range"
        else:
            return "not written: its source sits in no subnet of the target's network"
        name = unit.claim(
            "google_compute_firewall",
            f"{self.noun(target)}_from_{'internet' if kind == 'internet' else self.noun(source)}",
        )
        ports: list[object] = list(self.ports(label, target))
        if not ports:
            ports = [
                self.required_variable(
                    place,
                    Variable(
                        f"{name}_port",
                        "number",
                        MISSING,
                        f"The port {self.label(source)} reaches {self.label(target)} on.",
                    ),
                )
            ]
        prefix = "local.name"
        record = (
            self.module_networks.get(place.network_element.id)
            if place.network_element is not None
            else None
        )
        if record is not None:
            record.rules.append(
                {
                    "name": Raw(
                        f'trim(substr(lower("${{{prefix}}}-{tag}-from-{origin_name}"), 0, 63), "-")'
                    ),
                    "description": literal(label or f"From {source.name}"),
                    **{attr.name: attr.value for attr in origin if isinstance(attr, Attr)},
                    "target_tags": [tag],
                    "allow": [{"protocol": "tcp", "ports": ports}],
                }
            )
            numbers = ", ".join(str(port) for port in ports if isinstance(port, str))
            return (
                f"firewall rule, tcp {numbers}, {written}"
                if numbers
                else f"firewall rule, its port a variable to fill, {written}"
            )
        unit.add(
            self.section("gcp", "security"),
            Block(
                "resource",
                ("google_compute_firewall", name),
                [
                    Attr(
                        "name",
                        Raw(
                            f'trim(substr(lower("${{{prefix}}}-{tag}-from-{origin_name}"), 0, 63), "-")'
                        ),
                    ),
                    Attr("project", self.project_of(place)),
                    Attr("network", place.network.ref("id")),
                    Attr("description", literal(label or f"From {source.name}")),
                    Attr("direction", "INGRESS"),
                    *origin,
                    Attr("target_tags", [tag]),
                    BLANK,
                    Block("allow", (), [Attr("protocol", "tcp"), Attr("ports", ports)]),
                ],
            ),
        )
        numbers = ", ".join(str(port) for port in ports if isinstance(port, str))
        return (
            f"firewall rule, tcp {numbers}, {written}"
            if numbers
            else f"firewall rule, its port a variable to fill, {written}"
        )

    def ports(self, label: str, target: TopologyElement) -> list[str]:
        """Every port or range a label names, in order (``443``,
        ``8000-8080``); else the port its words or the target's rule name;
        else none."""
        found: list[str] = []
        for low, high in _PORT.findall(label):
            if 1 <= int(low) <= 65535 and (not high or int(low) <= int(high) <= 65535):
                found.append(f"{int(low)}-{int(high)}" if high else str(int(low)))
        if found:
            return list(dict.fromkeys(found))
        port = self.port(label, target)
        return [str(port)] if port is not None else []

    def origin(
        self, source: TopologyElement, target: Place
    ) -> tuple[str, TopologyElement | None, Place | None]:
        """Where a wire comes from, as a rule can say it: ``internet``, the
        source ``element`` itself (it wears a boundary of its own), its
        ``subnet``, or ``no: <why>``."""
        if self.is_actor(source):
            return "internet", None, None
        source_place, source_rule = self.placed.get(source.id, (None, None))
        if source.id not in self.written or source_place is None:
            return "no: its source is no resource", None, None
        if self.elsewhere(source_place, target):
            return "no: its two ends sit in different networks", None, None
        if source_rule is not None and source_rule.security_group:
            return "element", source, source_place
        if source_place.subnet is not None:
            return "subnet", source, source_place
        return "no: its source sits in no subnet of the target's network", None, None

    def rule_map(self, group: Resource) -> dict[str, object] | None:
        """The map a network security group's rules are written into, when
        they are collected; ``None`` when each is a resource of its own."""
        return None

    @staticmethod
    def elsewhere(source: Place, target: Place) -> bool:
        """Whether a wire's source sits in another network than its target."""

        def network(place: Place) -> str | None:
            return place.network_element.id if place.network_element is not None else None

        return network(source) != network(target)

    def nsg_rule(self, source: TopologyElement, target: TopologyElement, label: str) -> str:
        """A wire to an Azure virtual machine: an inbound rule on the network
        security group of its interface, from the internet, from the source
        machine's application security group, or from the address range of
        the subnet the source sits in."""
        place = self.placed[target.id][0]
        unit = place.unit
        group = self.written[target.id]["nsg"]
        kind, _, where = self.origin(source, place)
        if kind.startswith("no: "):
            return f"not written: {kind[4:]}"
        if kind == "internet":
            origin: list[object] = [Attr("source_address_prefix", "Internet")]
            written = "from the internet"
        elif kind == "element" and "asg" in self.written[source.id]:
            origin = [
                Attr(
                    "source_application_security_group_ids",
                    [self.written[source.id]["asg"].ref("id")],
                )
            ]
            written = f"from the application security group of {self.label(source)}"
        elif where is not None and where.subnet is not None:
            prefixes = where.subnet.ref("address_prefixes")
            origin = [Attr("source_address_prefixes", prefixes)]
            written = "from its subnet's range" + (
                ", a value to fill" if self.unfilled(prefixes) else ""
            )
        else:
            return "not written: its source sits in no subnet of the target's network"
        priority = self.priorities.get(group.address, 90) + 10
        if priority > 4096:
            return "not written: its network security group has no priority left"
        self.priorities[group.address] = priority
        name = unit.claim(
            "azurerm_network_security_rule",
            f"{self.noun(target)}_from_{'internet' if kind == 'internet' else self.noun(source)}",
        )
        ports: list[object] = list(self.ports(label, target))
        if not ports:
            ports = [
                self.required_variable(
                    place,
                    Variable(
                        f"{name}_port",
                        "number",
                        MISSING,
                        f"The port {self.label(source)} reaches {self.label(target)} on.",
                    ),
                )
            ]
        destination = (
            Attr("destination_port_range", ports[0])
            if len(ports) == 1
            else Attr("destination_port_ranges", ports)
        )
        rule_name = (
            re.sub(r"[^a-z0-9]+", "-", f"{target.id}-from-{source.id}".lower())
            .strip("-")[:80]
            .strip("-")
        )
        rules = self.rule_map(group)
        if rules is not None:
            rules[rule_name or "rule"] = {
                "name": rule_name or "rule",
                "description": literal((label or f"From {source.name}")[:140]),
                "priority": priority,
                "direction": "Inbound",
                "access": "Allow",
                "protocol": "Tcp",
                "source_port_range": "*",
                destination.name: destination.value,
                **{attr.name: attr.value for attr in origin if isinstance(attr, Attr)},
                "destination_address_prefix": "*",
            }
            numbers = ", ".join(port for port in ports if isinstance(port, str))
            return (
                f"network security group rule, tcp {numbers}, {written}"
                if numbers
                else f"network security group rule, its port a variable to fill, {written}"
            )
        unit.add(
            self.section("azure", "security"),
            Block(
                "resource",
                ("azurerm_network_security_rule", name),
                [
                    Attr("name", rule_name or "rule"),
                    Attr("description", literal((label or f"From {source.name}")[:140])),
                    Attr("priority", priority),
                    Attr("direction", "Inbound"),
                    Attr("access", "Allow"),
                    Attr("protocol", "Tcp"),
                    Attr("source_port_range", "*"),
                    destination,
                    *origin,
                    Attr("destination_address_prefix", "*"),
                    # a group the registry's module writes gives no resource group: the machine's is it
                    Attr(
                        "resource_group_name",
                        place.resource_group
                        if isinstance(group, ModuleResource)
                        else group.ref("resource_group_name"),
                    ),
                    Attr("network_security_group_name", group.ref("name")),
                ],
            ),
        )
        numbers = ", ".join(port for port in ports if isinstance(port, str))
        return (
            f"network security group rule, tcp {numbers}, {written}"
            if numbers
            else f"network security group rule, its port a variable to fill, {written}"
        )

    def unfilled(self, value: object) -> bool:
        """Whether a value reads a root variable the diagram gives no value."""
        texts = [
            item.text
            for item in (value if isinstance(value, list) else [value])
            if isinstance(item, Raw)
        ]
        return any(
            variable is not None and variable.todo
            for text in texts
            for name in re.findall(r"\bvar\.(\w+)", text)
            for variable in [self.root.variables.get(name)]
        )

    def port(self, label: str, target: TopologyElement) -> int | None:
        for number in re.findall(r"(?<![\d./])(\d{2,5})(?![\d./])", label):
            value = int(number)
            if 1 <= value <= 65535:
                return value
        words = load_ports().words
        for word in re.findall(r"[a-z0-9]+", label.lower()):
            if word in words:
                return words[word]
        rule = self.placed.get(target.id, (None, None))[1]
        return rule.port if rule is not None else None

    def write_load_balancers(
        self, listeners: dict[str, list[int]], targets: dict[tuple[str, int], list[TopologyElement]]
    ) -> None:
        for balancer_id in dict.fromkeys(key[0] for key in targets):
            balancer = self.written[balancer_id]["main"]
            place = self.placed[balancer_id][0]
            unit = balancer.unit
            element = self.by_id[balancer_id]
            section = self.section_of[balancer_id]
            noun = self.noun(element)
            assert place.network is not None
            first: Resource | None = None
            for (owner, port), members in targets.items():
                if owner != balancer_id:
                    continue
                wanted = self.noun(members[0]) if len(members) == 1 else f"{noun}_{port}"
                group = Resource(
                    "aws_lb_target_group",
                    unit.claim("aws_lb_target_group", wanted, f"{noun}_{port}"),
                    unit,
                )
                first = first or group
                unit.add(
                    section,
                    Comment(f"{element.name} forwards to its targets on port {port}."),
                    Block(
                        "resource",
                        (group.type, group.name),
                        [
                            # cut to 32, never ending on the hyphen the cut can leave
                            Attr(
                                "name",
                                Raw(
                                    f'trim(substr("{self.name_expr(place, members[0])}-{port}", 0, 32), "-")'
                                ),
                            ),
                            Attr("port", port),
                            Attr("protocol", "HTTPS" if port == 443 else "HTTP"),
                            Attr("vpc_id", place.network.ref("id")),
                        ],
                    ),
                )
                for member in members:
                    target = self.written[member.id]["main"]
                    if target.type == "aws_autoscaling_group":
                        attach = unit.claim("aws_autoscaling_attachment", self.noun(member))
                        unit.add(
                            section,
                            Block(
                                "resource",
                                ("aws_autoscaling_attachment", attach),
                                [
                                    Attr("autoscaling_group_name", target.ref("name")),
                                    Attr("lb_target_group_arn", group.ref("arn")),
                                ],
                            ),
                        )
                        continue
                    attach = unit.claim("aws_lb_target_group_attachment", self.noun(member))
                    unit.add(
                        section,
                        Block(
                            "resource",
                            ("aws_lb_target_group_attachment", attach),
                            [
                                Attr("target_group_arn", group.ref("arn")),
                                Attr("target_id", target.ref("id")),
                                Attr("port", port),
                            ],
                        ),
                    )
            assert first is not None
            for port in sorted(set(listeners.get(balancer_id, [])) or {80}):
                body: list[object] = [
                    Attr("load_balancer_arn", balancer.ref("arn")),
                    Attr("port", port),
                    Attr("protocol", "HTTPS" if port == 443 else "HTTP"),
                ]
                if port == 443:
                    body.append(
                        Attr(
                            "certificate_arn",
                            self.required_variable(
                                place,
                                Variable(
                                    f"{noun}_certificate_arn",
                                    "string",
                                    MISSING,
                                    f"The ARN of the certificate {self.label(element)} serves HTTPS with.",
                                ),
                            ),
                        )
                    )
                body += [
                    BLANK,
                    Block(
                        "default_action",
                        (),
                        [
                            Attr("type", "forward"),
                            Attr("target_group_arn", first.ref("arn")),
                        ],
                    ),
                ]
                protocol = "https" if port == 443 else "http"
                listener = unit.claim(
                    "aws_lb_listener",
                    protocol if port in (80, 443) else f"{protocol}_{port}",
                    f"{noun}_{protocol}_{port}",
                )
                unit.add(section, Block("resource", ("aws_lb_listener", listener), body))

    # ------------------------------------------------------------ hooks the modules style fills
    def network_subnets(
        self, network: TopologyElement
    ) -> list[tuple[TopologyElement, TopologyElement | None]]:
        """The network's subnet frames, each with the zone frame it sits in."""
        out: list[tuple[TopologyElement, TopologyElement | None]] = []

        def visit(element: TopologyElement, zone: TopologyElement | None) -> None:
            for child in element.children:
                if not child.is_frame:
                    continue
                if child.type in ("subnet-public", "subnet-private"):
                    out.append((child, zone))
                visit(child, child if child.type == "zone" else zone)

        visit(network, None)
        return out

    def module_gateway(
        self, record: Any, element: TopologyElement, place: Place, rule: ComponentRule
    ) -> None:
        """An internet or NAT gateway a network's registry module writes itself."""
        raise NotImplementedError("the plain walk writes no network as a registry module")

    def finish_module_networks(self) -> None:
        """Each network written as a registry module, now its subnets and wires are known."""

    def finish_module_rules(self) -> None:
        """The rules the wires collected, where they are written as one map."""

    # ------------------------------------------------------------ units
    def finish_units(self) -> None:
        """The Google APIs the resources need, first in the foundation."""
        if not self.apis:
            return
        self.use_provider("gcp")
        section = self.section("gcp", "foundation")
        apis: list[object] = [Comment("The Google APIs the resources need, turned on first.")]
        for api, name in sorted(self.apis.items()):
            apis.append(
                Block(
                    "resource",
                    ("google_project_service", name),
                    [
                        Attr("service", api),
                        Attr("disable_on_destroy", False),
                    ],
                )
            )
        self.root.files[section] = apis + self.root.files.get(section, [])


#: What an AWS WAF web ACL is associated with (CloudFront names its own).
_WEB_ACL_TARGETS = frozenset(
    {
        "aws_lb",
        "aws_api_gateway_stage",
        "aws_apigatewayv2_stage",
        "aws_appsync_graphql_api",
        "aws_cognito_user_pool",
    }
)
#: The resource types a Google load balancer's backend can be.
_GOOGLE_BACKENDS = frozenset(
    {
        "google_compute_region_instance_group_manager",
        "google_compute_instance_group_manager",
        "google_compute_instance",
        "google_cloud_run_v2_service",
        "google_cloud_run_service",
    }
)
#: What a variable of a table's field is, said of its element.
_DESCRIPTIONS = {
    "ami": "The AMI {label} boot from.",
    "instance_type": "The instance type of {label}.",
    "instance_class": "The instance class of {label}.",
    "desired_capacity": "How many of {label} run.",
    "min_size": "The fewest of {label} that run.",
    "max_size": "The most of {label} that run.",
    "multi_az": "Whether {label} keeps a standby in a second availability zone.",
    "target_size": "How many of {label} run.",
    "certificate_secret_id": "The Key Vault secret id of the certificate {label} serves HTTPS with.",
    "identity_id": "The id of the user-assigned identity {label} reads its certificate from Key Vault with.",
    "availability_type": "Whether {label} keeps a standby in a second zone: REGIONAL, or ZONAL for none.",
    "allocated_storage": "The storage of {label}, in GiB.",
    "retention_in_days": "How many days {label} keeps its logs.",
    "username": "The administrator's user name on {label}.",
    "engine": "The database engine of {label}.",
}
#: Words a variable name spells in capitals.
_ACRONYMS = {
    "ami": "AMI",
    "arn": "ARN",
    "asn": "ASN",
    "az": "AZ",
    "bgp": "BGP",
    "cidr": "CIDR",
    "dns": "DNS",
    "id": "ID",
    "ip": "IP",
    "sku": "SKU",
    "vm": "VM",
    "vpc": "VPC",
    "url": "URL",
}


def _words(name: str) -> str:
    return " ".join(_ACRONYMS.get(word, word) for word in name.split("_"))


def _aws_description(text: str) -> str:
    """Diagram text as AWS takes it in a description: ASCII letters, digits
    and a few marks, at most 255 characters."""

    text = unicodedata.normalize("NFKD", text.replace("\u00b7", "/"))
    text = _NOT_AWS_DESCRIPTION.sub(" ", text.encode("ascii", "ignore").decode("ascii"))
    return literal(" ".join(text.split())[:255])


def plan_terraform(project: CloudProject, style: str = "resources") -> Plan:
    """What :func:`infragram.terraform.write_terraform` writes for a document:
    in plain resources, or (``style="modules"``) through the public
    registry's modules where one fits (:mod:`.registry`)."""

    if style not in STYLES:
        raise ValueError(f"no Terraform style {style!r}; the styles are {', '.join(STYLES)}")
    if style == "modules":
        from .registry import plan_registry

        return plan_registry(project)
    return _Emitter(project, style).run()
