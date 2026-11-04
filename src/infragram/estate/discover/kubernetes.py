"""A live Kubernetes cluster, read through ``kubectl``: ``discover:kubernetes``.

Read-only: ``kubectl config view --minify`` for the context, then one
``kubectl get <kind> -o json`` per kind, as the kubeconfig signs in. A kind
the account may not list is a note, and the rest is still drawn.

Unlike the clouds, a cluster is drawn here rather than through Terraform's
terms: a namespace is a frame inside the cluster's, and each workload a
card. What a controller made is folded into it -- a Deployment's
ReplicaSets and their Pods, a CronJob's Jobs, a StatefulSet's claims from
its volume claim templates -- so the picture shows what was declared. The
wires are read from the objects themselves, in a fixed rank order (after
k8sviz): an Ingress to the Services its rules name, a Service to the
workloads its selector matches, a workload to the claims it mounts, and a
HorizontalPodAutoscaler to what it scales. The system namespaces are left
out unless asked for.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..draw import Box, Card, Drawing, Wire
from ..model import Estate, Found
from . import CallError, DiscoveryError, Runner, cli_runner

__all__ = ["KINDS", "SYSTEM_NAMESPACES", "discover_kubernetes", "draw_cluster"]

#: What is read, in the rank order the picture runs in: kind, as ``kubectl get`` names it.
KINDS = (
    ("ingresses", "Ingress"),
    ("services", "Service"),
    ("deployments", "Deployment"),
    ("statefulsets", "StatefulSet"),
    ("daemonsets", "DaemonSet"),
    ("cronjobs", "CronJob"),
    ("jobs", "Job"),
    ("replicasets", "ReplicaSet"),
    ("pods", "Pod"),
    ("horizontalpodautoscalers", "HorizontalPodAutoscaler"),
    ("persistentvolumeclaims", "PersistentVolumeClaim"),
)
#: kind -> the Kubernetes library's service id.
_SERVICE = {
    "Ingress": "ing",
    "Service": "svc",
    "Deployment": "deploy",
    "StatefulSet": "sts",
    "DaemonSet": "ds",
    "CronJob": "cronjob",
    "Job": "job",
    "ReplicaSet": "rs",
    "Pod": "pod",
    "HorizontalPodAutoscaler": "hpa",
    "PersistentVolumeClaim": "pvc",
}
_RANK = {kind: rank for rank, (_, kind) in enumerate(KINDS)}
#: What runs pods, and so can be selected, mount claims and be scaled.
_WORKLOADS = frozenset(
    {"Deployment", "StatefulSet", "DaemonSet", "CronJob", "Job", "ReplicaSet", "Pod"}
)
SYSTEM_NAMESPACES = frozenset({"kube-system", "kube-public", "kube-node-lease"})


def _address(kind: str, namespace: str, name: str) -> str:
    return f"{kind}/{namespace}/{name}"


def discover_kubernetes(
    *,
    context: str | None = None,
    namespaces: Iterable[str] = (),
    runner: Runner | None = None,
) -> Estate:
    """What the cluster holds, as an estate: one record per object read."""
    run = runner or cli_runner("kubectl")
    scope = ["--context", context] if context else []
    try:
        config = run(["config", "view", "--minify", "-o", "json", *scope]) or {}
    except CallError as error:
        raise DiscoveryError(f"kubectl cannot say its context: {error.message}") from error
    chosen = context or config.get("current-context")
    if not chosen:
        raise DiscoveryError("name a context with --context (the kubeconfig has none current)")
    wanted = list(namespaces)
    where = [["--namespace", name] for name in wanted] or [["--all-namespaces"]]
    found: list[Found] = []
    notes: list[str] = []
    for plural, kind in KINDS:
        for place in where:
            call = ["get", plural, "-o", "json", *place, *scope]
            try:
                answer = run(call) or {}
            except CallError as error:
                notes.append(f"{plural} not read: {error.message}")
                break
            for item in answer.get("items") or []:
                meta = item.get("metadata") or {}
                namespace, name = str(meta.get("namespace") or ""), str(meta.get("name") or "")
                if not name:
                    continue
                found.append(
                    Found(
                        address=_address(kind, namespace, name),
                        type=f"kubernetes_{kind.lower()}",
                        name=name,
                        values=item,
                        source=f"kubectl get {plural}",
                    )
                )
    scope_text = f"namespaces {', '.join(wanted)}" if wanted else "every namespace"
    return Estate(
        f"Kubernetes cluster {chosen}",
        f"the Kubernetes context {chosen} ({scope_text}), read-only",
        found,
        notes,
    )


# ------------------------------------------------------------ drawing
def _kind(found: Found) -> str:
    return found.address.split("/", 1)[0]


def _namespace(found: Found) -> str:
    return found.address.split("/")[1]


def _template(found: Found) -> dict[str, Any]:
    """The pod template a workload runs: its labels, volumes and containers."""
    kind = _kind(found)
    if kind == "Pod":
        return {"metadata": found.values.get("metadata") or {}, "spec": found.value("spec") or {}}
    if kind == "CronJob":
        template = found.value("spec", "jobTemplate", "spec", "template")
    else:
        template = found.value("spec", "template")
    return template if isinstance(template, dict) else {}


def _labels(found: Found) -> dict[str, str]:
    labels = (_template(found).get("metadata") or {}).get("labels") or {}
    return {str(key): str(value) for key, value in labels.items()}


def _images(found: Found) -> list[str]:
    containers = (_template(found).get("spec") or {}).get("containers") or []
    return [str(container.get("image", "")) for container in containers if container.get("image")]


def _short(image: str) -> str:
    """``registry.example.com/team/shop:1.4`` -> ``shop:1.4``."""
    return image.rsplit("/", 1)[-1]


def _detail(found: Found) -> str:
    kind, spec = _kind(found), found.values.get("spec") or {}
    if kind in ("Deployment", "StatefulSet", "ReplicaSet"):
        images = ", ".join(_short(image) for image in _images(found)[:2])
        return f"{spec.get('replicas', 1)} replicas" + (f" · {images}" if images else "")
    if kind in ("DaemonSet", "Pod", "Job"):
        return ", ".join(_short(image) for image in _images(found)[:2])
    if kind == "CronJob":
        return str(spec.get("schedule", ""))
    if kind == "Service":
        ports = ", ".join(f":{port.get('port')}" for port in spec.get("ports") or [])
        return f"{spec.get('type', 'ClusterIP')} {ports}".strip()
    if kind == "Ingress":
        hosts = [str(rule.get("host")) for rule in spec.get("rules") or [] if rule.get("host")]
        return ", ".join(hosts[:2])
    if kind == "HorizontalPodAutoscaler":
        return f"{spec.get('minReplicas', 1)}-{spec.get('maxReplicas', '?')} replicas"
    if kind == "PersistentVolumeClaim":
        size = ((spec.get("resources") or {}).get("requests") or {}).get("storage", "")
        return " · ".join(str(part) for part in (size, spec.get("storageClassName")) if part)
    return ""


def draw_cluster(estate: Estate, *, include_system: bool = False) -> Drawing:
    """The cluster as a drawing: namespaces in the cluster's frame, what a
    controller made folded into it, and the wires the objects name."""
    by_uid = {
        str((found.values.get("metadata") or {}).get("uid")): found
        for found in estate.resources
        if (found.values.get("metadata") or {}).get("uid")
    }
    drawn: dict[str, str] = {}
    folded: dict[str, str] = {}
    left_out: dict[str, str] = {}

    def top(found: Found) -> Found:
        """The object at the head of *found*'s owner chain, among those read."""
        seen = {found.address}
        while True:
            owners = (found.values.get("metadata") or {}).get("ownerReferences") or []
            owner = next((o for o in owners if o.get("controller")), owners[0] if owners else None)
            parent = by_uid.get(str(owner.get("uid"))) if owner else None
            if parent is None or parent.address in seen:
                return found
            seen.add(parent.address)
            found = parent

    heads: list[Found] = []
    for found in estate.resources:
        if _namespace(found) in SYSTEM_NAMESPACES and not include_system:
            left_out[found.address] = "a system namespace (--include-system draws it)"
            continue
        if found.address == "Service/default/kubernetes":
            left_out[found.address] = "the API server's own Service, in every cluster"
            continue
        head = top(found)
        if head is not found:
            folded[found.address] = head.address
            continue
        heads.append(found)

    # a StatefulSet's claims from its volume claim templates: <template>-<set>-<ordinal>
    claim_templates: dict[str, list[str]] = {}
    for found in heads:
        if _kind(found) != "StatefulSet":
            continue
        for template in found.value("spec", "volumeClaimTemplates") or []:
            name = str((template.get("metadata") or {}).get("name", ""))
            prefix = f"{name}-{found.name}-"
            claims = [
                claim.address
                for claim in heads
                if _kind(claim) == "PersistentVolumeClaim"
                and _namespace(claim) == _namespace(found)
                and claim.name.startswith(prefix)
                and claim.name[len(prefix) :].isdigit()
            ]
            for claim in claims:
                folded[claim] = found.address
            claim_templates.setdefault(found.address, []).append(f"{name} ({len(claims)})")
    heads = [found for found in heads if found.address not in folded]

    cards: dict[str, Card] = {}
    for found in heads:
        kind = _kind(found)
        rows = [("Resource", found.address), ("Kind", kind), ("Namespace", _namespace(found))]
        rows += [("Image", image) for image in _images(found)[:4]]
        if claim_templates.get(found.address):
            rows.append(("Claims", ", ".join(claim_templates[found.address])))
        cards[found.address] = Card(
            found.address,
            "kubernetes",
            _SERVICE[kind],
            found.name,
            _detail(found),
            rows=rows,
            sources=[found],
            # a workload wears its pods' labels, which are what selectors match
            tags=_labels(found)
            or {
                str(key): str(value)
                for key, value in ((found.values.get("metadata") or {}).get("labels") or {}).items()
            },
        )
        drawn[found.address] = f"{kind} {found.name}"
    for address, owner in list(folded.items()):
        folded[address] = f"folded into {owner}"

    # (source, target) -> its labels, and whether it is dashed; one wire each, labels joined
    joined: dict[tuple[str, str], tuple[list[str], bool]] = {}

    def wire(source: str, target: str, label: str = "", dashed: bool = False) -> None:
        if source in cards and target in cards and source != target:
            labels, _ = joined.setdefault((source, target), ([], dashed))
            if label and label not in labels:
                labels.append(label)

    workloads = [found for found in heads if _kind(found) in _WORKLOADS]
    for found in heads:
        kind, namespace, spec = _kind(found), _namespace(found), found.values.get("spec") or {}
        if kind == "Ingress":
            for backend, label in _ingress_backends(spec):
                wire(found.address, _address("Service", namespace, backend), label)
        elif kind == "Service":
            selector = {str(k): str(v) for k, v in (spec.get("selector") or {}).items()}
            ports = ", ".join(
                f":{port.get('targetPort', port.get('port'))}" for port in spec.get("ports") or []
            )
            for workload in workloads:
                labels = _labels(workload)
                if (
                    selector
                    and _namespace(workload) == namespace
                    and all(labels.get(key) == value for key, value in selector.items())
                ):
                    wire(found.address, workload.address, ports)
        elif kind == "HorizontalPodAutoscaler":
            scaled = spec.get("scaleTargetRef") or {}
            if scaled.get("kind") and scaled.get("name"):
                wire(
                    found.address,
                    _address(str(scaled["kind"]), namespace, str(scaled["name"])),
                    "scales",
                    dashed=True,
                )
        if kind in _WORKLOADS:
            for volume in (_template(found).get("spec") or {}).get("volumes") or []:
                mounted = (volume.get("persistentVolumeClaim") or {}).get("claimName")
                if mounted:
                    wire(found.address, _address("PersistentVolumeClaim", namespace, str(mounted)))

    wires = [
        Wire(source=source, target=target, label=", ".join(labels), dashed=dashed)
        for (source, target), (labels, dashed) in joined.items()
    ]
    # An app: a Service, the workloads it selects, what scales them and the
    # claims only they mount, in a workload frame read left to right.
    app_of: dict[str, str] = {}  # card -> the Service whose app holds it
    for (source, target), _ in joined.items():
        if source.startswith("Service/") and target.split("/")[0] in _WORKLOADS:
            app_of.setdefault(target, source)
    for source in [source for source, _ in joined]:
        if source.startswith("Service/") and source not in app_of:
            app_of[source] = source
    for (source, target), _ in joined.items():
        if source.startswith("HorizontalPodAutoscaler/") and target in app_of:
            app_of.setdefault(source, app_of[target])
        if target.startswith("PersistentVolumeClaim/") and source in app_of:
            mounted_by = {s for s, t in joined if t == target}
            if {app_of.get(s) for s in mounted_by} == {app_of[source]}:
                app_of.setdefault(target, app_of[source])
    apps: dict[str, Box] = {}
    namespaces: dict[str, Box] = {}
    for found in sorted(heads, key=lambda found: (_namespace(found), _RANK[_kind(found)])):
        namespace = _namespace(found)
        box = namespaces.get(namespace)
        if box is None:
            box = namespaces[namespace] = Box(
                f"namespace/{namespace}", "kubernetes", "namespace", namespace
            )
        service = app_of.get(found.address)
        if service is None:
            box.children.append(cards[found.address])
            continue
        app = apps.get(service)
        if app is None:
            app = apps[service] = Box(
                f"app/{service}", "kubernetes", "group", service.rsplit("/", 1)[-1], flow="row"
            )
            box.children.append(app)
        app.children.append(cards[found.address])
    context = estate.title.removeprefix("Kubernetes cluster ")
    cluster = Box("cluster", "kubernetes", "cluster", context, children=list(namespaces.values()))
    notes = list(estate.notes)
    if not include_system and any(
        reason.startswith("a system namespace") for reason in left_out.values()
    ):
        notes.append("the system namespaces are left out; --include-system draws them")
    return Drawing(
        title=estate.title,
        origin=estate.origin,
        roots=[cluster] if namespaces else [],
        wires=wires,
        drawn=drawn,
        folded=folded,
        left_out=left_out,
        notes=notes,
        thing="object",
        direction="right",
    )


def _ingress_backends(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """(service, host and path) for every backend an Ingress's rules name."""
    out: list[tuple[str, str]] = []
    default = ((spec.get("defaultBackend") or {}).get("service") or {}).get("name")
    if default:
        out.append((str(default), "default"))
    for rule in spec.get("rules") or []:
        host = str(rule.get("host") or "")
        for path in (rule.get("http") or {}).get("paths") or []:
            service = ((path.get("backend") or {}).get("service") or {}).get("name")
            if service:
                out.append((str(service), f"{host}{path.get('path') or ''}" or "/"))
    return out
