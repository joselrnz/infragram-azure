# Kubernetes library (platform)

Load only for Kubernetes content. The theme is
[`kubernetes.json`](../../assets/themes/kubernetes.json)
(`theme="kubernetes"`); the component catalog is the Kubernetes community
artwork, 34 icons in `assets/icons/vendors/kubernetes/`. Coverage:
**reviewed**. Kubernetes is a *platform* library: it never stands in for a
cloud account, and selecting it never removes the cloud resources underneath.

## Frames

Starter stack: **Cluster → namespace → workload**. Node pools are separate
infrastructure frames, not parents of namespaces or workloads.

| Frame id | Kind |
|---|---|
| `custom-boundary-kubernetes-cluster` | cluster (Kubernetes mark on the tab) |
| `custom-boundary-kubernetes-namespace` | namespace |
| `custom-boundary-kubernetes-node-pool` | node-pool |
| `custom-boundary-kubernetes-workload` | group |

Managed clusters belong to their cloud library's frame instead: AKS, GKE,
DOKS, OKE, and IBM Kubernetes each have a cluster frame there, and all carry
the Kubernetes mark on the tab.

## Artwork

Use the registered Kubernetes resource icons (`kubernetes:deploy`,
`kubernetes:svc`, `kubernetes:ing`, `kubernetes:pvc`, ...) for objects inside
a cluster; use the shared neutral primitives (`infragram:kubernetes-pod`,
`infragram:kubernetes-node`) when a diagram needs a generic pod or node
without a specific resource kind.

## Modelling rules

- Control plane and worker nodes are infrastructure: draw them in node-pool
  or cloud frames, with workloads in namespaces alongside.
- Ingress and LoadBalancer services are where cloud load balancers attach;
  connect them with `solid` links from the cloud component.
- Kubernetes project artwork (Apache-2.0). CNCF and Linux Foundation
  trademark policies apply to the marks.
