"""Which library component a shape is, and which frame a container is.

A shape is matched on the strongest thing it says, in this order:

1. **Its own stencil or icon, in its library** (``mxgraph.aws4.lambda_function``,
   ``logos:aws-lambda``, ``AzureFunction(...)``): the phrase is searched in
   that library's catalog, dropping words until something draws.
2. **A phrase that could be anyone's** (a C4 technology, a ``logos:redis``
   icon, a Visio master named ``Database``) or **the label itself**: an
   exact name, id or alias, in the libraries the diagram already uses first,
   then the shared library; then a whole name or long alias the text
   contains (``Orders DB (RDS)`` holds ``RDS``), in those libraries only.
3. **What the words say it is** (``users`` is people, ``queue`` a message
   queue, ``db`` a database) and then **what the shape is** (a cylinder is a
   database, a stick figure a person, a cloud a cloud).
4. Otherwise a **generic container**, reported as a guess.

A container is a frame of the library its stencil names (a draw.io AWS VPC
group is ``frames.aws.VPC``) or its label names (``Public subnet``,
``rg-prod``, ``us-east-1``), in the library most of its contents come from,
then the generic frames; one whose label names no kind is a plain group.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from functools import cache

from pydantic import BaseModel

from ..catalog.components import load_composite_catalog
from ..compose.inference import NEUTRAL_LIBRARY
from ..estate.tables import frame_class
from .model import Shape, words

__all__ = ["FrameMatch", "Match", "match_component", "match_frame", "name_of", "providers_named"]


class Match(BaseModel):
    library: str
    service_id: str
    #: how it was found, for the popup and the report
    how: str
    #: a guess from the words or the shape, not a named product
    generic: bool = False


class FrameMatch(BaseModel):
    #: ``""`` for a plain group
    library: str
    kind: str
    how: str


#: Words that say nothing about which product a stencil means.
_FILLER = {
    "amazon",
    "aws",
    "azure",
    "microsoft",
    "google",
    "gcp",
    "cloud platform",
    "icon",
    "resource",
    "resources",
    "service",
    "services",
    "product",
    "the",
    "and",
    "of",
    "for",
    "light",
    "dark",
    "bg",
    "color",
    "grey",
    "gray",
    "group",
    "alt",
    "v2",
    "2",
}
#: One word that names no product by itself.
_WEAK = {
    "instance",
    "instances",
    "service",
    "server",
    "group",
    "cluster",
    "resource",
    "node",
    "app",
    "application",
    "data",
    "cloud",
    "network",
    "function",
    "container",
    "api",
    "user",
    "users",
    "web",
    "client",
    "system",
    "storage",
    "database",
    "db",
    "store",
    "gateway",
    "manager",
    "management",
    "security",
    "monitoring",
    "internet",
    "public",
    "private",
    "file",
    "files",
}
#: The libraries whose components any diagram may use without naming them.
_NEUTRAL = ("infragram", "onprem")
#: Words any diagram uses for a kind of thing, never one product: a label made only
#: of them is matched in the diagram's own libraries and the shared one, never
#: in a cloud the diagram does not use ("Browser" is not Azure's Browser).
_COMMON = _WEAK | {
    "browser",
    "scheduler",
    "cdn",
    "metadata",
    "catalog",
    "dashboard",
    "backup",
    "backups",
    "monitor",
    "log",
    "logs",
    "queue",
    "queues",
    "cache",
    "worker",
    "workers",
    "frontend",
    "backend",
    "portal",
    "website",
    "site",
    "email",
    "mail",
    "dns",
    "firewall",
    "router",
    "switch",
    "vpn",
    "proxy",
    "search",
    "analytics",
    "notification",
    "notifications",
    "identity",
    "auth",
    "secrets",
    "secret",
    "registry",
    "repository",
    "repo",
    "pipeline",
    "build",
    "deploy",
    "deployment",
    "load",
    "balancer",
    "sql",
    "nosql",
    "table",
    "tables",
    "bucket",
    "blob",
    "object",
    "objects",
    "event",
    "events",
    "stream",
    "streams",
    "topic",
    "topics",
    "job",
    "jobs",
    "batch",
    "cron",
    "timer",
    "gear",
    "cog",
    "settings",
    "config",
    "configuration",
    "admin",
    "mobile",
    "desktop",
    "laptop",
    "phone",
    "device",
    "devices",
    "sensor",
    "sensors",
    "camera",
    "printer",
    "disk",
    "volume",
    "share",
    "files",
    "folder",
    "document",
    "documents",
    "report",
    "reports",
    "order",
    "orders",
    "payment",
    "payments",
    "customer",
    "customers",
    "account",
    "accounts",
    "product",
    "products",
    "inventory",
    "shipping",
    "billing",
    "invoice",
    "chat",
    "message",
    "messages",
    "cluster",
    "pod",
    "pods",
    "vm",
    "vms",
    "host",
    "hosts",
    "edge",
    "core",
    "hub",
    "spoke",
    "zone",
    "region",
    "tier",
    "layer",
    "internal",
    "external",
    "legacy",
    "primary",
    "secondary",
    "replica",
    "master",
    "main",
    "prod",
    "production",
    "staging",
    "dev",
    "test",
    "the",
    "a",
    "an",
    "of",
    "for",
    "and",
    "to",
    "with",
    "via",
    "on",
    "in",
    "my",
    "our",
    "new",
    "old",
    "service",
    "system",
    "platform",
    "engine",
    "store",
    "center",
    "centre",
    "manager",
    "agent",
    "gateway",
    "endpoint",
    "endpoints",
    "interface",
    "connector",
    "adapter",
    "bridge",
    "link",
    "web",
    "app",
    "apps",
    "application",
    "applications",
    "ui",
    "spa",
    "client",
    "clients",
    "user",
    "users",
}
#: A vendor's word before its product's name.
_VENDORS = {
    "azure",
    "amazon",
    "aws",
    "google",
    "gcp",
    "ibm",
    "oracle",
    "oci",
    "alibaba",
    "microsoft",
}

#: Words -> a shared component, when nothing named a product.
_WORDS: tuple[tuple[str, str], ...] = (
    (
        r"\b(?:users?|customers?|clients?|persons?|people|visitors?|end users?|consumers?|members?)\b",
        "public-users",
    ),
    (
        r"\b(?:admins?|administrators?|operators?|engineers?|developers?|devs?|ops|sre)\b",
        "administrator",
    ),
    (
        r"\binternet\b(?!\s+(?:banking|facing|gateway|explorer|of things|system|service|app\w*|portal|site))|"
        r"\bwww\b|\bpublic network\b",
        "public-internet",
    ),
    (r"\bcdn\b|\bedge\b", "cdn-edge"),
    (r"\bdns\b", "dns-service"),
    (r"\bwaf\b|\bfirewall\b|\bfw\b", "firewall"),
    (r"\bvpn\b", "vpn-concentrator"),
    (r"\bbastion\b|\bjump ?(?:host|box|server)\b", "jump-host"),
    (
        r"\bload ?balancers?\b|\blb\b|\balb\b|\bnlb\b|\bhaproxy\b|\breverse proxy\b|\bingress\b",
        "generic-load-balancer",
    ),
    (
        r"\b(?:identity|idp|sso|oauth|oidc|saml|login|auth(?:entication|orization)?|iam)\b",
        "identity-provider",
    ),
    (r"\b(?:web|app(?:lication)?|file|game) ?servers?\b", "virtual-machine"),
    (r"\bapi\b|\brest\b|\bendpoints?\b|\bbackend\b|\bback end\b", "api-endpoint"),
    (r"\bgateway\b", "network-gateway"),
    (r"\bmobile\b|\bios\b|\bandroid\b|\bphone\b|\btablet\b", "mobile-client"),
    (
        r"\bbrowsers?\b|\bfrontend\b|\bfront end\b|\bspa\b|\bsingle page app\w*|\bwebsite\b|\bui\b|\bportal\b|"
        r"\bweb\b(?! ?(?:app\w*|servers?|services?|api|tier|layer|hooks?))",
        "browser-client",
    ),
    (r"\bdesktop\b|\blaptop\b|\bpc\b|\bworkstation\b", "desktop-client"),
    (r"\bcache\b|\bmemcached?\b", "generic-cache"),
    (
        r"\bqueues?\b|\btopics?\b|\bbus\b|\bbroker\b|\bstreams?\b|\bevents?\b|\bmessag\w*|\bpub ?sub\b",
        "message-queue",
    ),
    (
        r"\bdb\b|\bdbs\b|\bdatabases?\b|\bsql\b|\bdata ?stores?\b|\bwarehouse\b|\bdata ?lake\b|\brdbms\b",
        "generic-database",
    ),
    (
        r"\bbuckets?\b|\bblobs?\b|\bobject stor\w*|\bfiles?\b|\bshares?\b|\bnas\b|\bstorage\b|\bdisks?\b",
        "generic-file",
    ),
    (r"\bmail\b|\bemails?\b|\bsmtp\b", "mail-server"),
    (r"\bmonitor\w*|\bmetrics?\b|\bobservability\b|\balert\w*|\bdashboards?\b", "monitoring"),
    (r"\blogs?\b|\blogging\b|\baudit\b", "log-stream"),
    (
        r"\bsecrets?\b|\bvault\b|\bkeys?\b|\bkms\b|\bcertificates?\b|\bcerts?\b|\bhsm\b",
        "secret-key",
    ),
    (r"\bwebhooks?\b", "webhook"),
    (r"\bpayments?\b|\bbilling\b|\bcheckout\b", "payment-gateway"),
    (r"\bcrm\b", "crm"),
    (r"\betl\b|\bpipelines?\b|\bworkflows?\b|\borchestrat\w*", "bpm"),
    (r"\brouters?\b", "edge-router"),
    (r"\bswitch(?:es)?\b", "core-switch"),
    (r"\bmainframe\b", "mainframe"),
    (r"\bprinters?\b", "printer"),
    (
        r"\bcontainers?\b|\bpods?\b|\bdocker\b|\bmicro ?services?\b|\bservices?\b|\bworkers?\b|\bjobs?\b|"
        r"\bapps?\b|\bapplications?\b|\bfunctions?\b|\blambdas?\b",
        "generic-container",
    ),
    (
        r"\bservers?\b|\bhosts?\b|\bvms?\b|\bvirtual machines?\b|\binstances?\b|\bnodes?\b|\bmachines?\b",
        "virtual-machine",
    ),
    (r"\bcloud\b|\bsaas\b|\bthird[- ]party\b|\bexternal\b", "generic-cloud"),
)
#: What a shape's own form says it is.
_KINDS = {
    "database": "generic-database",
    "cache": "generic-cache",
    "actor": "public-user",
    "cloud": "generic-cloud",
    "queue": "message-queue",
    "file": "generic-file",
    "storage": "storage-array",
}
_DEFAULT = "generic-container"

#: Container words -> the frame kinds they may be, in order.
_FRAME_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (r"\bpublic\b.*\bsubnet|\bsubnet\b.*\bpublic\b|\bdmz subnet\b", ("subnet-public",)),
    (r"\bprivate\b.*\bsubnet|\bsubnet|\bvlan\b|\bsnet[-_]", ("subnet-private",)),
    (r"\bvpc\b", ("vpc", "network")),
    (r"\bvnet\b|\bvirtual network\b", ("network", "vpc")),
    (r"\bresource group\b|^rg[-_ ]", ("resource-group",)),
    (r"\bmanagement group\b", ("management-group",)),
    (r"\bsubscriptions?\b", ("subscription", "account")),
    (r"\btenant\b|\bentra\b|\bazure ad\b", ("organization",)),
    (r"\borgani[sz]ation\b", ("organization",)),
    (r"\baccounts?\b", ("account",)),
    (r"\bprojects?\b", ("project",)),
    (r"\bfolders?\b", ("folder",)),
    (r"\bnamespaces?\b|^ns[-_ ]", ("namespace",)),
    (r"\bnode ?pools?\b|\bnode ?groups?\b", ("node-pool",)),
    (r"\bauto ?scaling\b|\basg\b", ("auto-scaling",)),
    (r"\bsecurity groups?\b|\bnsg\b", ("security-group",)),
    (r"\bsecurity zone\b|\btrust(?:ed)? zone\b|\buntrusted\b", ("security-zone",)),
    (
        r"\bavailability zones?\b|\baz ?[a-z0-9]?\b|\bzone [a-z0-9]\b|^zone$|^[a-z]{2}-[a-z]+-\d[a-z]$",
        ("zone",),
    ),
    (
        r"\bregions?\b|^[a-z]{2}-[a-z]+-\d$|^(?:east|west|central|north|south)[a-z]*\s?\d?$",
        ("region",),
    ),
    (r"\bdmz\b|\bperimeter\b", ("dmz",)),
    (r"\bhub\b", ("hub",)),
    (r"\bspokes?\b", ("spoke",)),
    (
        r"\bon[- ]?prem\w*|\bdata ?cent(?:er|re)s?\b|\bdc\b|\bcolo\w*|\boffices?\b|\bbranch\b|\bsites?\b|"
        r"\bcampus\b|\bhomelab\b|\blab\b",
        ("site",),
    ),
    (
        r"\bclusters?\b|\baks\b|\beks\b|\bgke\b|\bk8s\b|\bk3s\b|\bkubernetes\b|\bopenshift\b",
        ("cluster",),
    ),
    (r"\bmanagement network\b|\boob\b|\bout of band\b", ("management",)),
    (r"\bnetworks?\b|\blan\b|\bwan\b", ("network",)),
    (
        r"\bprod(?:uction)?\b|\bstag(?:ing|e)\b|\bdev(?:elopment)?\b|\btest(?:ing)?\b|\bqa\b|\buat\b|"
        r"\benvironments?\b|\benvs?\b|\bsandbox\b",
        ("environment",),
    ),
    (r"\baws\b|\bamazon web services\b|\bazure\b|\bgoogle cloud\b|\bgcp\b|\bclouds?\b", ("cloud",)),
)
#: The cloud a container's own label names.
_FRAME_PROVIDERS = (
    (r"\baws\b|\bamazon\b", "aws"),
    (r"\bazure\b|\bentra\b", "azure"),
    (r"\bgoogle\b|\bgcp\b", "gcp"),
    (r"\bkubernetes\b|\bk8s\b|\bk3s\b", "kubernetes"),
)
#: A stencil's frame phrase -> kind, where the phrase is not a kind word already.
_FRAME_PHRASES = {
    "aws cloud": "cloud",
    "aws cloud alt": "cloud",
    "cloud": "cloud",
    "cloud alt": "cloud",
    "corporate data center": "site",
    "on premise": "site",
    "account": "account",
    "auto scaling group": "auto-scaling",
    "spot fleet": "auto-scaling",
    "availability zone": "zone",
}


@cache
def _drawable(library: str) -> frozenset[str]:
    """The service ids a library has node classes for."""
    try:
        from ..estate.tables import _component_classes

        return frozenset(_component_classes(library))
    except (ImportError, AttributeError):
        return frozenset()


#: Words that end in s and are no plural.
_NO_SINGULAR = frozenset({"kubernetes", "series", "species", "news", "analytics", "ops", "devops"})


def _singular(key: str) -> str:
    """The name with its last word in the singular, or "" when it has none:
    "key vaults" -> "key vault", "policies" -> "policy", "ip addresses" ->
    "ip address"; "dns" and "analysis" stay as they are."""
    head, _, last = key.rpartition(" ")
    if len(last) < 4 or last.endswith(("ss", "us", "is")) or last in _NO_SINGULAR:
        return ""
    if last.endswith("ies"):
        last = last[:-3] + "y"
    elif last.endswith(("sses", "xes", "ches", "shes")):
        last = last[:-2]
    elif last.endswith("s"):
        last = last[:-1]
    else:
        return ""
    return f"{head} {last}" if head else last


@cache
def _index() -> dict[str, list[tuple[str, str, bool]]]:
    """Every name, id and alias, spoken as words -> (library, service id, strong)."""
    out: dict[str, list[tuple[str, str, bool]]] = {}
    for component in load_composite_catalog().components:
        if component.component_kind != "node" or component.service_id not in _drawable(
            component.provider
        ):
            continue
        if component.service_id.startswith("iso-"):
            continue  # the 3D set is asked for by name, never guessed
        entry = (component.provider, component.service_id)
        strong = {words(component.name), words(component.service_id)}
        # "Azure Cosmos DB" is also "Cosmos DB", "Amazon RDS" also "RDS"
        strong |= {
            key.split(" ", 1)[1]
            for key in strong
            if " " in key and key.split(" ", 1)[0] in _VENDORS
        }
        # Azure names its icons in the plural ("Key Vaults", "Function Apps");
        # a diagram names one of them ("Key Vault")
        strong |= {_singular(key) for key in strong} - {""}
        for key in strong:
            if key:
                out.setdefault(key, []).append((*entry, True))
        spelled = " ".join(strong).replace(" ", "")
        for alias in component.aliases:
            key = words(alias)
            if key and key not in strong:
                # an alias spelled inside the name ("postgres" of PostgreSQL) is as good as the name
                out.setdefault(key, []).append(
                    (*entry, len(key) >= 4 and key.replace(" ", "") in spelled)
                )
    return out


def name_of(library: str, service_id: str) -> str:
    """A component's catalog name, for a card the source left without a label."""
    for component in load_composite_catalog().components:
        if component.provider == library and component.service_id == service_id:
            return component.name
    return service_id.replace("-", " ").capitalize()


def _order(libraries: Iterable[str], preferred: list[str]) -> list[str]:
    rank = {library: index for index, library in enumerate(preferred)}
    return sorted(
        set(libraries), key=lambda lib: (rank.get(lib, len(rank) + (lib not in _NEUTRAL)), lib)
    )


def _exact(
    phrase: str, libraries: list[str] | None, preferred: list[str], *, names_first: bool = False
) -> tuple[str, str, bool] | None:
    """(library, service id, by its name or id rather than an alias)."""
    candidates = _index().get(words(phrase), [])
    if libraries is not None:
        candidates = [c for c in candidates if c[0] in libraries]
    if not candidates:
        return None
    order = _order((c[0] for c in candidates), preferred)
    if names_first:
        return min(candidates, key=lambda c: (not c[2], order.index(c[0]), len(c[1])))
    return min(candidates, key=lambda c: (order.index(c[0]), not c[2], len(c[1])))


def _anywhere(phrase: str, scope: list[str], preferred: list[str]) -> tuple[str, str, bool] | None:
    """An exact name in the diagram's own or the shared libraries, then in any
    library when the phrase is specific enough to mean one product."""
    found = _exact(phrase, scope, preferred)
    if found and (found[2] or found[0] not in _NEUTRAL):
        return found
    # an alias of a shared component ("customer" of a CRM) says too little
    spoken = words(phrase)
    if len(spoken) < 2 or all(w in _COMMON for w in spoken.split()):
        return None
    candidates = _index().get(spoken, [])
    named = [c for c in candidates if c[2]]
    clouds = {c[0] for c in candidates if c[0] not in _NEUTRAL}
    if not named and len(clouds) == 1:
        # an alias only one cloud uses: "S3" is Amazon's
        named = [c for c in candidates if c[0] in clouds]
    if not named:
        return None
    order = _order((c[0] for c in named), preferred)
    return min(named, key=lambda c: (order.index(c[0]), not c[2], len(c[1])))


def _search(phrase: str, library: str) -> tuple[str, str] | None:
    """The best component of one library for a stencil phrase, dropping words until one draws."""
    tokens = words(phrase).split()
    kept = [t for t in tokens if t not in _FILLER] or tokens
    attempts: list[list[str]] = [tokens, kept]
    attempts += [kept[:n] for n in range(len(kept) - 1, 0, -1)]
    attempts += [kept[n:] for n in range(1, len(kept))]
    catalog = load_composite_catalog()
    drawable = _drawable(library)
    for attempt in (tokens, kept):
        # a name or alias as the stencil spells it, before any looser search
        exact = _exact(" ".join(attempt), [library], [library])
        if exact:
            return exact[0], exact[1]
    for attempt in attempts:
        if not attempt or (len(attempt) == 1 and attempt[0] in _WEAK and attempt != tokens):
            continue
        text = " ".join(attempt)
        exact = _exact(text, [library], [library])
        if exact:
            return exact[0], exact[1]
        for component in catalog.search(text):
            if component.provider == library and component.service_id in drawable:
                return library, component.service_id
    return None


def _contained(
    text: str, libraries: list[str], preferred: list[str], *, least: int = 1
) -> tuple[str, str] | None:
    """A whole name or long alias the text holds, longest first, in the given
    libraries; a name of at least ``least`` words."""
    tokens = words(text).split()
    index = _index()
    for size in range(min(len(tokens), 5), least - 1, -1):
        hits = []
        for start in range(len(tokens) - size + 1):
            gram = " ".join(tokens[start : start + size])
            if size == 1 and (gram in _WEAK or gram in _VENDORS):
                continue
            hits += [
                c
                for c in index.get(gram, [])
                if c[0] in libraries
                and (
                    len(gram) >= (3 if c[0] not in _NEUTRAL else 4)
                    if c[2]
                    else len(gram) >= 5 and c[0] not in _NEUTRAL
                )
            ]
        if hits:
            # the diagram's own libraries before the shared one, at the same length
            order = _order((c[0] for c in hits), preferred)
            best = min(hits, key=lambda c: (order.index(c[0]), not c[2], len(c[1])))
            return best[0], best[1]
    return None


def providers_named(shapes: Iterable[Shape]) -> list[str]:
    """The libraries a diagram's stencils name, most used first."""
    counts: Counter[str] = Counter()
    for shape in shapes:
        for hint in shape.hints:
            if hint.provider and hint.provider not in _NEUTRAL:
                counts[hint.provider] += 1
    return [library for library, _ in counts.most_common()]


def _shared(service_id: str, how: str) -> Match:
    return Match(library="infragram", service_id=service_id, how=how, generic=True)


def match_component(shape: Shape, preferred: list[str]) -> Match:
    """The component a shape is drawn as; always one, a guess at worst."""
    if shape.component and ":" in shape.component:
        # an Infragram export names it outright; kept when the catalog has it
        library, _, service = shape.component.partition(":")
        if any(
            component.provider == library and component.service_id == service
            for component in load_composite_catalog().components
        ):
            return Match(
                library=library, service_id=service, how="the infragram_component it carries"
            )
    named = [hint for hint in shape.hints if not hint.frame]
    for hint in named:
        if hint.provider:
            found = _search(hint.phrase, hint.provider)
            if found:
                return Match(
                    library=found[0],
                    service_id=found[1],
                    how=f"its stencil {hint.raw or hint.phrase}",
                )
    text = " ".join(t for t in (shape.label, shape.detail) if t)
    # a cloud the label names goes first: "Amazon S3" is AWS's
    named_clouds = [lib for pattern, lib in _FRAME_PROVIDERS if re.search(pattern, words(text))]
    preferred = list(dict.fromkeys([*named_clouds, *preferred]))
    scope = [*preferred, *_NEUTRAL]
    for hint in named:
        if hint.provider:
            continue
        hit = _anywhere(hint.phrase, scope, preferred) or _contained(hint.phrase, scope, preferred)
        if hit:
            return Match(
                library=hit[0], service_id=hit[1], how=f"its icon or type {hint.raw or hint.phrase}"
            )
    head, colon, _ = shape.label.partition(":")
    if colon and head.strip():
        # "Private Endpoint: pe-sql" names its type before the colon, the way
        # Azure's resource visualizer labels a resource; the name after it
        # ("web", "sql") must not decide what the shape is
        hit = _anywhere(head, list(dict.fromkeys([*scope, NEUTRAL_LIBRARY])), preferred)
        if hit:
            return Match(library=hit[0], service_id=hit[1], how="the type its label names")
    if shape.label:
        hit = _anywhere(shape.label, scope, preferred)
        if hit:
            return Match(library=hit[0], service_id=hit[1], how="its label")
    for cloud in named_clouds:
        found = _search(text, cloud)
        if found:
            return Match(library=found[0], service_id=found[1], how=f"its label, in {cloud}")
    if text:
        found = _contained(text, scope, preferred)
        if found:
            return Match(library=found[0], service_id=found[1], how="a name in its label")
    for hint in named:
        if hint.provider:
            # a stencil its library has no component for: its words, as a label's
            found = _contained(hint.phrase, [hint.provider, *_NEUTRAL], preferred)
            if found:
                return Match(library=found[0], service_id=found[1], how=f"its stencil {hint.raw}")
    if NEUTRAL_LIBRARY not in scope and text:
        # A source that names no cloud (Mermaid, PlantUML, bare boxes) is read
        # in this edition's own library last, and only for a name of two words
        # or more: "Key Vault: kv-shop" is Azure's, while "Users" and "Queue"
        # stay the shared components below.
        edition = [NEUTRAL_LIBRARY]
        if shape.label and len(words(shape.label).split()) >= 2:
            hit = _exact(shape.label, edition, edition)
            if hit:
                return Match(library=hit[0], service_id=hit[1], how=f"its label, in {hit[0]}")
        found = _contained(text, edition, edition, least=2)
        if found:
            return Match(
                library=found[0], service_id=found[1], how=f"a name in its label, in {found[0]}"
            )
    spoken = words(" ".join([text, *(hint.phrase for hint in named)]))
    if shape.kind in ("database", "cache", "queue") and shape.kind in _KINDS:
        # the form beats the words: a cylinder labelled "Orders service" is its database
        for pattern, service in _WORDS:
            fits = service == _KINDS[shape.kind] or (
                shape.kind == "database" and service == "generic-cache"
            )
            if fits and re.search(pattern, spoken):
                return _shared(service, "words in its label")
        return _shared(_KINDS[shape.kind], f"its shape ({shape.kind})")
    for pattern, service in _WORDS:
        if re.search(pattern, spoken):
            return _shared(service, "words in its label")
    if shape.kind in _KINDS:
        return _shared(_KINDS[shape.kind], f"its shape ({shape.kind})")
    return _shared(_DEFAULT, "nothing it says names a product: a generic container")


def match_frame(shape: Shape, inside: Counter[str], preferred: list[str]) -> FrameMatch:
    """The frame a container is drawn as: a library's, the generic set's, or a plain group."""
    label = words(shape.label)
    raw_label = shape.label.strip().lower()
    frame_hints = [hint for hint in shape.hints if hint.frame]
    hinted = [hint.provider for hint in frame_hints if hint.provider]
    named = [library for pattern, library in _FRAME_PROVIDERS if re.search(pattern, label)]
    libraries = list(
        dict.fromkeys(
            [
                *hinted,
                *named,
                *(lib for lib, _ in inside.most_common() if lib not in ("infragram",)),
                *preferred,
                NEUTRAL_LIBRARY,
                "generic",
            ]
        )
    )
    kinds: list[str] = []
    for hint in frame_hints:
        phrase = words(hint.phrase)
        if phrase in _FRAME_PHRASES:
            kinds.append(_FRAME_PHRASES[phrase])
        elif phrase == "security group" and "subnet" in label:
            kinds.append("subnet-public" if "public" in label else "subnet-private")
        else:
            kinds += [
                kind
                for pattern, options in _FRAME_WORDS
                if re.search(pattern, phrase)
                for kind in options
            ]
    how = "its stencil" if kinds else "its label"
    for pattern, options in _FRAME_WORDS:
        if re.search(pattern, label) or re.search(pattern, raw_label):
            kinds += list(options)
            break
    for kind in dict.fromkeys(kinds):
        order = ["kubernetes", *libraries] if kind in ("namespace", "node-pool") else libraries
        for library in order:
            if frame_class(library, kind) is not None:
                return FrameMatch(library=library, kind=kind, how=how)
    return FrameMatch(library="", kind="group", how="its label names no frame: a plain group")
