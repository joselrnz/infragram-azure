# Scope

Infragram Azure is a local infrastructure diagram editor, import and export pipeline, and review toolkit for **Azure, Kubernetes and Databricks**. It carries the main Infragram workflows with three vendor libraries and the Azure edition's enhanced inventory importer.

A versioned `.infragram.json` document is the source for Python authoring, the offline editor, CLI and MCP tools, and exported artifacts. Shared primitives and core frames describe users, services, networks, sites and systems around the cloud.

## Supported workflows

- Author architecture in Python or project documents, using reusable patterns, layers, containment frames and automatic routing.
- Edit offline HTML; export HTML, SVG, PNG and draw.io; generate Azure Terraform skeletons as plain resources or Azure Verified Modules.
- Import Terraform configuration, plans and state; import draw.io, Mermaid, PlantUML, Excalidraw and Visio; report uncertain matches and omissions.
- Read Azure subscriptions through the existing Azure CLI session and Kubernetes through kubectl. Keep network and resource-group Azure views, multi-subscription reads, raw snapshot replay, external peering endpoints and network attachment badges.
- Review plan actions and drift, compare diagram versions, select filtered views, save layout, and run diagram policy checks or installed Terraform scanners.
- Estimate Azure monthly list-price costs with explicit sizing and assumptions, optional live prices, CSV breakdowns and prepared Infracost input.
- Use these workflows through the CLI, agent skill, plugin hooks and stdio MCP server; create custom 3D components through shared rendering tools.

The Azure inventory importer and the Terraform-oriented Azure discovery reader remain distinct entry points. The former favors complete inventory, network placement and snapshots; the latter interprets supported security rules into traffic relationships and produces a Terraform-oriented report.

## Libraries

| Library | Role |
|---|---|
| Azure | Tenant, management group, subscription, resource group, region/zone, VNet/subnet and AKS architecture |
| Kubernetes | Cluster, namespace, node pool and workload architecture |
| Databricks | Account, workspace, compute, Unity Catalog and data-platform services |
| Shared primitives and frames | Generic services, identities, networks and hybrid sites |

The installed inventory contains 827 vendor icons, 370 shared primitives, 40 frames and four starter templates. Counts are generated in `skills/infragram-azure/references/inventory.md`.

## Boundaries

Azure is the supported Terraform export provider. Kubernetes and Databricks artwork and architecture are in scope; adding their own Terraform providers is a separate capability. Other vendors' icon packs and service catalogs remain in the full product.

Terraform output is a reviewable skeleton, not a deployment promise. Commands may validate it and plan with mocked providers; they do not automatically apply infrastructure. Live discovery reads existing CLI sessions without writing back to the estate.

Costs are estimates based on list prices and stated or marked assumed quantities. They exclude negotiated discounts, reservations and actual billing visibility. Diagram exposure rules and configured NSG traffic relationships do not replace effective-reachability or comprehensive security assessments.

General editorial diagrams, detailed cabling/VLAN/port-engineering documents, hosted collaboration and automatic deployment are outside scope. The editor and its saved HTML work locally without a server.

The three-vendor catalog is the edition boundary.
