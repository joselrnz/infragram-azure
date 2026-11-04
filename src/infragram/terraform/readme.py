"""The skeleton's READMEs, written the way a Terraform repository on GitHub reads.

The skeleton's README says what it is and how it is laid out, how to use an
environment, what the diagram draws and where each thing is written, what to
fill, its modules and the environment's inputs and outputs; then every wire
of the diagram and how it was written, and every element written as no
resource. Every module gets a README of its own: what it writes, how an
environment calls it, and its requirements, modules, resources, inputs and
outputs, in the tables terraform-docs lays out.

The tables are read back out of the files the skeleton holds, with the same
reader the import uses (:mod:`.hclread`), so a README cannot say an input or
an output the code does not have.
"""

from __future__ import annotations

import re
from typing import Any

from ..utils.text import markdown_cell as _cell
from .emit import Plan, Variable
from .hclread import Body, evaluate, parse
from .mapping import load_modules, registry_page

__all__ = ["layout_readmes"]

_PROVIDER_DOCS = {
    "aws": "https://registry.terraform.io/providers/hashicorp/aws/latest/docs",
    "azurerm": "https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs",
    "azuread": "https://registry.terraform.io/providers/hashicorp/azuread/latest/docs",
    "google": "https://registry.terraform.io/providers/hashicorp/google/latest/docs",
}


# ---------------------------------------------------------------- reading the files back
def _one_line(text: str) -> str:
    """An expression's text on one line, as HCL writes an object type on one:
    ``map(object({ name = string, ami = string }))``."""
    parts = [
        re.sub(r"\s+=\s+", " = ", line.strip())
        for line in text.strip().splitlines()
        if line.strip()
    ]
    out = parts[0] if parts else ""
    for before, part in zip(parts, parts[1:], strict=False):
        out += " " if before.endswith(("{", "(", "[")) or part.startswith(("}", ")", "]")) else ", "
        out += part
    return out


def _text(expr: Any) -> str:
    value = evaluate(expr) if expr is not None else None
    return value if isinstance(value, str) else ""


def _body(files: dict[str, str], folder: str) -> Body:
    """Every block of a folder's .tf files, as one body."""
    body = Body()
    prefix = f"{folder}/" if folder else ""
    for name, text in sorted(files.items()):
        if name.startswith(prefix) and name.endswith(".tf") and "/" not in name[len(prefix) :]:
            parsed = parse(text, name)
            body.blocks.extend(parsed.blocks)
    return body


def _inputs(body: Body) -> list[str]:
    rows = ["| Name | Description | Type | Default | Required |", "|---|---|---|---|:---:|"]
    for block in body.blocks_of("variable"):
        attributes = block.body.attributes
        kind = _one_line(attributes["type"].text) if "type" in attributes else "any"
        default = attributes.get("default")
        rows.append(
            f"| `{block.labels[0]}` | {_cell(_text(attributes.get('description')))} | "
            f"`{_cell(kind)}` | {'`' + _cell(_one_line(default.text)) + '`' if default else 'n/a'} | "
            f"{'no' if default else 'yes'} |"
        )
    return rows if len(rows) > 2 else ["No inputs."]


def _outputs(body: Body) -> list[str]:
    rows = ["| Name | Description |", "|---|---|"]
    rows += [
        f"| `{block.labels[0]}` | {_cell(_text(block.body.attributes.get('description')))} |"
        for block in body.blocks_of("output")
    ]
    return rows if len(rows) > 2 else ["No outputs."]


def _modules(body: Body) -> list[str]:
    rows = ["| Name | Source | Version |", "|---|---|---|"]
    for block in body.blocks_of("module"):
        source = _text(block.body.attributes.get("source"))
        version = _text(block.body.attributes.get("version"))
        shown = (
            f"[`{source}`]({source})"
            if source.startswith("./")
            else f"[`{source}`]({registry_page(source, version)})"
            if version
            else f"`{source}`"
        )
        rows.append(f"| `{block.labels[0]}` | {shown} | {version or 'n/a'} |")
    return rows if len(rows) > 2 else ["No modules."]


def _resources(body: Body) -> list[str]:
    rows = ["| Name | Type |", "|---|---|"]
    for block in [*body.blocks_of("resource"), *body.blocks_of("data")]:
        if len(block.labels) != 2:
            continue
        kind, name = block.labels
        provider = kind.split("_", 1)[0]
        docs = _PROVIDER_DOCS.get(provider)
        address = f"{'data.' if block.type == 'data' else ''}{kind}.{name}"
        shown = (
            f"[`{address}`]({docs}/{'data-sources' if block.type == 'data' else 'resources'}/"
            f"{kind.split('_', 1)[1]})"
            if docs
            else f"`{address}`"
        )
        rows.append(f"| {shown} | {block.type} |")
    return rows if len(rows) > 2 else ["No resources of its own: its modules write them."]


def _requirements(plan: Plan, providers: list[str], versions: str) -> list[str]:
    """The Terraform the folder's ``versions.tf`` asks for, and its providers."""
    required = re.search(r'^\s*required_version\s*=\s*"([^"]+)"', versions, re.MULTILINE)
    rows = [
        "| Name | Version |",
        "|---|---|",
        f"| terraform | {required.group(1) if required else '>= 1.5'} |",
    ]
    for key in providers:
        entry = plan.providers.get(key)
        if entry is not None:
            rows.append(f"| {entry['name']} | {entry['version']} |")
    return rows


# ---------------------------------------------------------------- modules and environments
def _tree(layout: Any) -> list[str]:
    """The skeleton's folders, as ``tree`` draws them, each with what it holds."""
    from . import folder_name
    from .layout import FOLDER_TITLES

    lines = [
        f"{folder_name(layout.plan.project.slug, layout.plan.style)}/",
        "├── README.md",
        "├── modules/",
    ]
    folders = list(layout.folders.values())
    width = max((len(folder.path) for folder in folders), default=0) - len("modules/") + 2
    for n, folder in enumerate(folders):
        branch = "└──" if n == len(folders) - 1 else "├──"
        path = f"{folder.path.removeprefix('modules/')}/"
        lines.append(
            f"│   {branch} {path.ljust(width)}{FOLDER_TITLES.get(folder.concern, folder.concern)}"
        )
    lines += [
        "└── environments/",
        "    ├── dev/".ljust(width + 8) + "the same modules, with their own state and values",
        "    └── prod/",
    ]
    return lines


def layout_readmes(
    plan: Plan, layout: Any, files: dict[str, str], todos: list[Variable]
) -> dict[str, str]:
    """The skeleton's README, and one a module."""
    from ..cli.version import package_version
    from .layout import ENVIRONMENTS, FOLDER_TITLES, concern_title

    project = plan.project
    style = (
        "each module calling the public registry's maintained modules where one fits, and writing "
        "plain resources where none does"
        if plan.style == "modules"
        else "plain resources in every module"
    )
    out: dict[str, str] = {}
    lines = [f"# {project.title}", ""]
    if getattr(project, "description", "").strip():
        lines += [project.description.strip(), ""]
    lines += [
        f"Terraform for the `{project.slug}` diagram, written by Infragram Architect {package_version()}: "
        f"a module a concern, {style}, composed once an environment. It is a skeleton to review: the "
        "resources the diagram asserts, placed the way its frames contain them, with a variable wherever the "
        "diagram does not say. Nobody has applied it.",
        "",
        "## Layout",
        "",
        "```text",
        *_tree(layout),
        "```",
        "",
        "Each module under `modules/` holds one concern and configures no provider; what one module reads of "
        "another is an output of the one and a variable of the other, which the environment passes across. "
        "Each folder under `environments/` calls every module once and keeps its own state, so `dev` and "
        "`prod` are the same code with their own values.",
        "",
        "## Usage",
        "",
        "```sh",
        "cd environments/dev",
        "cp terraform.tfvars.example terraform.tfvars   # fill every value it lists",
        "terraform init",
        "terraform plan",
        "```",
        "",
        "Before you share an environment, give it a remote state in its `backend.tf`.",
        "",
        "## Architecture",
        "",
    ]
    if plan.rows:
        where = {folder.key: folder.path for folder in layout.folders.values()}
        lines += ["| Category | Item | Written as | Module |", "|---|---|---|---|"]
        for category, item, written, key in plan.rows:
            path = where.get(key, "")
            shown = f"[`{path}`]({path})" if path else "-"
            lines.append(f"| {_cell(category)} | {_cell(item)} | {written} | {shown} |")
    else:
        lines.append("Nothing is written but the provider configurations.")
    lines += ["", f"## Values to fill ({len(todos)})", ""]
    if todos:
        lines += [
            "Each environment's `terraform.tfvars.example` lists them.",
            "",
            "| Variable | What |",
            "|---|---|",
        ]
        lines += [
            f"| `{v.name}` | {_cell(v.description)} |" for v in sorted(todos, key=lambda v: v.name)
        ]
    else:
        lines.append("None: the diagram answers every value.")
    lines += ["", "## Modules", "", "| Module | Holds |", "|---|---|"]
    lines += [
        f"| [`{folder.path}`]({folder.path}) | {_cell(FOLDER_TITLES.get(folder.concern, folder.concern))} |"
        for folder in layout.folders.values()
    ]
    if plan.registry:
        table = load_modules().modules
        lines += [
            "",
            "The public registry's modules they call, at the versions checked against:",
            "",
            "| Module | Version |",
            "|---|---|",
        ]
        lines += [
            f"| [`{table[key].source}`]({table[key].page}) | {table[key].version} |"
            for key in plan.registry
        ]
        if any(key.startswith("azure-") for key in plan.registry):
            lines += [
                "",
                "The Azure Verified Modules report usage to Microsoft unless `enable_telemetry` is "
                "false; the skeleton sets it false.",
            ]
    env = _body(files, f"environments/{ENVIRONMENTS[-1]}")
    lines += [
        "",
        "## Environment inputs",
        "",
        *_inputs(env),
        "",
        "## Environment outputs",
        "",
        *_outputs(env),
        "",
        "## Wires",
        "",
    ]
    if plan.wires:
        lines += ["| From | To | Label | Written as |", "|---|---|---|---|"]
        lines += [
            f"| {_cell(plan.label(w.source))} | {_cell(plan.label(w.target))} | "
            f"{_cell(w.label or '-')} | {_cell(w.written_as)} |"
            for w in plan.wires
        ]
    else:
        lines.append("The diagram draws no wires.")
    lines += ["", "## Not written as resources", ""]
    if plan.not_written:
        lines += ["| Element | Why |", "|---|---|"]
        lines += [f"| {_cell(name)} | {_cell(why)} |" for name, why in plan.not_written]
    else:
        lines.append("Every element is written.")
    if plan.notes:
        lines += ["", "## Notes", ""]
        lines += [f"- {note}" for note in dict.fromkeys(plan.notes)]
    out["README.md"] = "\n".join(lines) + "\n"
    call_text = files.get(f"environments/{ENVIRONMENTS[-1]}/main.tf", "")
    for folder in layout.folders.values():
        items = sorted(
            {
                label
                for address, label in plan.labels.items()
                if layout.owner.get(address) == folder.key
            }
        )
        body = _body(files, folder.path)
        versions = files.get(f"{folder.path}/versions.tf", "")
        required = [
            key
            for key, entry in plan.providers.items()
            if re.search(rf"^\s+{re.escape(entry['name'])}\s*=", versions, re.MULTILINE)
        ]
        usage = re.search(rf'(?ms)^module "{re.escape(folder.call)}" {{\n.*?^}}\n', call_text)
        cloud = {"aws": "AWS", "azure": "Azure", "gcp": "Google Cloud"}.get(
            folder.provider, folder.provider
        )
        title = FOLDER_TITLES.get(folder.concern, folder.concern)
        text = [
            f"# {concern_title(folder.concern)} module",
            "",
            f"{title[:1].upper()}{title[1:]}, as the `{project.slug}` diagram draws them on {cloud}.",
            "",
        ]
        if items:
            text += ["It writes: " + ", ".join(items) + ".", ""]
        if usage:
            text += ["## Usage", "", "```hcl", usage.group(0).rstrip("\n"), "```", ""]
        text += [
            "## Requirements",
            "",
            *_requirements(plan, required, versions),
            "",
            "## Modules",
            "",
            *_modules(body),
            "",
            "## Resources",
            "",
            *_resources(body),
            "",
            "## Inputs",
            "",
            *_inputs(body),
            "",
            "## Outputs",
            "",
            *_outputs(body),
        ]
        out[f"{folder.path}/README.md"] = "\n".join(text) + "\n"
    return out
