---
name: infragram-azure
description: Create, edit, import and review infrastructure diagrams for Azure, Kubernetes and Databricks. Use Python authoring, the offline HTML editor, Terraform configuration/plan/state import, read-only Azure and Kubernetes discovery, multi-subscription Azure snapshots, diagram import, visual diffs, views, policy checks, Azure cost estimates and MCP tools. Export one .infragram.json document to HTML, SVG, PNG, draw.io or an Azure Terraform skeleton. Includes provider containment frames, shared primitives, automatic routing and custom 3D components.
---

# Infragram Azure

Use this skill for Azure, Kubernetes and Databricks architecture: landing zones, AKS workloads, data platforms and hybrid estates drawn with shared primitives. It provides the main Infragram workflows with three vendor libraries, including the Azure edition's network and resource-group inventory views.

The source is a versioned `.infragram.json` project. Python authoring, the editor, imports, CLI exports and MCP tools use that same graph. New documents use schema version 3; older supported versions migrate on load.

## Quick start

Every command runs through the launcher beside this file, the same way in
bash, PowerShell and every agent. `<skill>` is the folder holding this file
(inside Claude Code, `${CLAUDE_SKILL_DIR}`); use `python3` where `python` is
not Python 3.

```text
python "<skill>/scripts/infragram.py" compose diagram.py --verify
python "<skill>/scripts/infragram.py" export:project project.infragram.json --verify
python "<skill>/scripts/infragram.py" check <file or folder>
```

It needs Python 3.11+. Without pydantic 2 it hands the command to an installed
`infragram` or to `uvx`, and says how to install pydantic when neither is
there. A PNG also needs Playwright and Chromium; without them an export with the
default formats writes the HTML and SVG and says why the PNG is missing.
Files land in `./dist` unless `--output-dir` says otherwise, and relative
paths mean the directory you are in. Exporting again replaces what the last
export wrote, if nobody has changed it since; any other existing file is
refused without `--force`. An installed copy also answers to `infragram`.

Installed as the Infragram Azure plugin, the skill comes with more. A check
hook checks every `.infragram.json` you write, reads (never runs) every
diagram file you write, and hands any problem back to you: fix it before
exporting. In Claude Code, the `diagram-reviewer` agent reviews a finished
diagram read-only; use it before the user shares one. The user's own
commands (`compose`, `export-project`, `export-azure`, `import`, `discover`,
`check`, `check-terraform`) run the same launcher. The plugin's `infragram`
MCP server offers the same work as tools (`compose`, `compose_source` for a
host without file tools, `export_project`, `export_set`, `export_azure`,
`check`, `verify_render`, `check_policy`, `check_terraform`, `diff`,
`costs`, `views`, `import_terraform`, `import_diagram`, `discover`,
`new_diagram`, `layout_save`, `draw_recipe`), plus `list_templates`,
`list_examples`, `recipes`, `docs` and `find_components`. Where there is no
shell, call those, under the same rules.

## When to use this skill

Use it when the request is about Azure, Kubernetes or Databricks
infrastructure that exists or will exist:

- an Azure estate: a landing zone, a hub and spoke network, a web app or API
  behind Front Door or Application Gateway, a data platform
- an AKS platform or workload layout (cluster, namespaces, node pools)
- a Databricks workspace and its Unity Catalog beside the Azure resources
- what is already deployed: Terraform files, a plan or a state, or a live
  subscription or cluster read through `az` or `kubectl`
- an editable diagram the user will keep changing, or one they need as HTML,
  SVG and PNG from the same source

Do not use it for flowcharts, sequence diagrams, ER models, timelines or
other editorial diagrams, for IP plans, VLAN tables or cabling, or for
deploying anything. Its prices are an estimate from on-demand list prices,
never a bill.

## Workflow

1. **Choose the starting point.** Use one of the four templates in `assets/templates/cloud/`, compose a Python diagram, import an existing diagram or Terraform, or read Azure/Kubernetes inventory.
2. **Read the relevant reference.** Load [compose.md](references/compose.md) before writing Python. Open only the provider references used by the diagram: [Azure](references/providers/azure.md), [Kubernetes](references/providers/kubernetes.md), [Databricks](references/providers/databricks.md).
3. **Model containment.** Frames describe ownership, location and networks. Azure uses tenant → management group → subscription → resource group → VNet → subnet; Kubernetes uses cluster → namespace → workload; Databricks uses account → workspace → compute, with Unity Catalog beside it. Read [frames.md](references/frames.md).
4. **Export and check.** `infragram compose diagram.py` or `infragram export:project project.infragram.json` uses the shared exporter. Select `--formats template,html,svg,png,drawio,terraform,terraform-modules` as needed. PNG and browser rendering need Playwright/Chromium; `--renderer static` provides a local SVG path. Use `--verify` and inspect visual artifacts at their intended size.
5. **Deliver the editable source and artifacts.** Report their paths and relevant validation. The HTML opens from disk with no server and supports component editing, frames, routing, layers, views and downloads.

## Import and discovery

- **Azure inventory:** `infragram export:azure -s Production -s Connectivity --view both --snapshot-out estate.json`. Reuse the read with `--from-snapshot estate.json`. Network placement follows ARM IDs; unknown resource types remain generic cards. Plumbing, managed groups and property-reference wires are configurable. The same read takes the last 14 days of changes and the Defender for Cloud and Azure Policy findings onto the cards (`--no-changes`, `--no-findings` skip them). See [azure-import.md](references/azure-import.md).
- **Terraform-oriented discovery:** `infragram discover:azure --source resource-graph` writes the editable Python diagram and report, including supported NSG traffic-rule relationships.
- **Kubernetes:** `infragram discover:kubernetes --context production` reads through the current kubectl session.
- **Terraform:** `infragram import:terraform <folder-or-plan-or-state>` reads declarations and plan actions, including drift. See [terraform.md](references/terraform.md).
- **Other diagrams:** `infragram import:diagram <file>` supports draw.io, Mermaid, PlantUML, Excalidraw and Visio. Review the import report's matches and guesses.

Discovery reads through the user's existing CLI session and never changes the deployed estate. A saved snapshot supports offline replay.

## Review, cost and infrastructure code

Use `diff` for two diagram versions, `views` for filtered parts, and `layout:save` to keep editor placement beside a Python diagram. `check:policy` reviews diagram exposure and can use installed Checkov or Trivy on Terraform folders. These checks do not prove effective network reachability or comprehensive compliance.

Azure exports include approximate monthly list-price costs from shipped tables. `costs --csv` writes the breakdown; `--prices` can refresh supported prices and `--infracost FILE` reads a prepared breakdown. Report assumptions and unpriced resources. List prices exclude negotiated discounts and actual billed usage.

The `terraform` and `terraform-modules` formats write Azure skeletons with variables and omissions to review. `check:terraform` validates and plans against mocked providers. Never automatically apply or deploy infrastructure. Azure is the supported Terraform provider; Kubernetes and Databricks remain diagram libraries.

`infragram mcp` exposes authoring, imports, reviews, pricing and exports over stdio. Its `export_azure` tool retains multi-subscription selection, both inventory views and snapshot replay.

## Fixed rules

- Keep provider identity on each component. A sidebar filter never changes existing nodes.
- Model containment with frames and children; layer membership is separate.
- Preserve vendor artwork and provenance. This edition's vendor packs are Azure, Kubernetes and Databricks.
- Produce every artifact from the same project. Exported pictures show the diagram, without editor controls.
- Keep offline artifacts self-contained. Network access is needed only for explicitly requested live reads or optional live services.
- Respect existing user authorization when replacing artifacts; use `--force` only within the requested work.
- Check connection targets, installed components, frame hierarchy and label clearance before delivery.

General flowcharts, sequences, ER models and editorial diagrams belong to another skill. Other cloud-vendor libraries belong to the full Infragram product. Architecture-level networking is supported; detailed cabling, VLAN and port-engineering documents are outside scope.

## Before you deliver

- `check` passes on every file you produced (or `--verify` did as it wrote them).
- Frames follow Azure's real hierarchy ([frames.md](references/frames.md)):
  services sit in the subnet, VNet or resource group they belong to, never
  directly in a region, and a network is a frame, not a card beside it.
- Labels are clear of nodes, frames, wires and each other at the exported
  size. A wire still crossing a card means its two ends have no clear lane;
  move a card rather than accept it.
- Every wire that matters names its protocol or port.
- The `PRICED` line's assumptions are reported, and nothing unpriced is
  passed off as free.
- The exported HTML opens offline, and the SVG and PNG show the same state.
- You reported every produced path and size.

## References

| Need | Read |
|---|---|
| Python diagrams and automatic layout | [compose.md](references/compose.md) |
| Boxes with compartments, several lines, shapes and tones (panels) | [compose.md](references/compose.md), Panels |
| Reusable patterns and batch generation | [patterns.md](references/patterns.md) |
| Project documents, layers and schema | [project-schema.md](references/project-schema.md) |
| Frames and starter stacks | [frames.md](references/frames.md) |
| Azure inventory and saved snapshots | [azure-import.md](references/azure-import.md) |
| Terraform import, export and checks | [terraform.md](references/terraform.md) |
| Export formats, costs and Infracost | [export.md](references/export.md) |
| Editor behavior | [editor.md](references/editor.md) |
| Provider styling and categories | [provider-themes.md](references/provider-themes.md), [provider-categories.md](references/provider-categories.md) |
| Shared primitives and exact catalog counts | [primitive-icons.md](references/primitive-icons.md), [inventory.md](references/inventory.md) |
