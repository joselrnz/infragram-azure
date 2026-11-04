"""The MCP server's tools: each one's schema, the command line it runs or the
answer it gives in-process, and what it answers with.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..cli.user.options import DISPLAYS, LIBRARIES, RENDERERS, ROUTINGS, SIZES, THEMES


class Tool(BaseModel):
    """One tool: its schema for the client, and the command line it runs."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    name: str
    title: str
    description: str
    properties: dict[str, dict[str, Any]]
    required: tuple[str, ...] = ()
    read_only: bool = False
    open_world: bool = False
    #: The ``infragram`` command line for the arguments, or None for a tool answered in-process.
    argv: Callable[[dict[str, Any]], list[str]] | None = None
    #: An in-process answer, for a tool that runs no command: its text and its data.
    answer: Callable[[dict[str, Any]], tuple[str, dict[str, Any]]] | None = None
    #: What a tool does before its command runs (compose_source writes the file); says what it did.
    prepare: Callable[[dict[str, Any]], str] | None = None
    #: The schema of the tool's ``structuredContent``.
    output: dict[str, Any] = Field(default_factory=dict)
    #: The command is run with ``--json``: what it prints on stdout comes back
    #: as the data's ``result``, and its other lines (files written, notes)
    #: are read from stderr as usual.
    json_result: bool = False

    def listing(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.properties,
                "required": list(self.required),
                "additionalProperties": False,
            },
            "outputSchema": self.output or _COMMAND_OUTPUT,
            "annotations": {
                "title": self.title,
                "readOnlyHint": self.read_only,
                "destructiveHint": False,
                "openWorldHint": self.open_world,
            },
        }


# ------------------------------------------------------------ arguments
def _string(description: str, **extra: Any) -> dict[str, Any]:
    return {"type": "string", "description": description, **extra}


def _strings(description: str) -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}, "description": description}


def _flag(description: str, default: bool = False) -> dict[str, Any]:
    return {"type": "boolean", "description": description, "default": default}


def _price_flags(value: Any) -> list[str]:
    """``prices`` as flags; ``true`` from a client of the old flag means live."""
    from ..cli.user.options import price_flags

    if value is True:
        value = "live"
    return price_flags(value if isinstance(value, str) else "table")


def _count(description: str) -> dict[str, Any]:
    return {"type": "integer", "minimum": 1, "description": description}


_EXPORT = {
    "formats": _string(
        "comma-separated: template, html, svg, png, drawio, terraform, terraform-modules "
        "(default html,svg,png; without a browser for the PNG, html,svg)"
    ),
    "output_dir": _string("where the files go (default ./dist)"),
    "display": _string("how components draw in the SVG and PNG", enum=list(DISPLAYS)),
    "write_looks": _string(
        "with display both: write both card and icon files, or the document's own look",
        enum=["both", "document"],
    ),
    "theme": _string("the theme the SVG and PNG are drawn in", enum=list(THEMES)),
    "scale": {
        "type": "number",
        "minimum": 1,
        "maximum": 4,
        "description": "PNG scale from 1 through 4 (default 3)",
    },
    "background": _string("behind the diagram: paper (default), transparent, or a hex colour"),
    "libraries": _string(
        "the component libraries the HTML embeds: only what is drawn (smallest), the "
        "project's own, or every installed one",
        enum=list(LIBRARIES),
    ),
    "drawio_icons": _string(
        "with formats drawio: draw.io's own stencils where one matches (native) or "
        "Infragram's artwork everywhere (embedded)",
        enum=["native", "embedded"],
    ),
    "no_embed": _flag(
        "leave the SVG and PNG bare; by default each carries its document, so exporting "
        "the picture redraws it"
    ),
    "verify": _flag("check every file written with the shipped checker", True),
    "prices": _string(
        "where each Azure component's approximate monthly price comes "
        "from: the price tables shipped with Infragram (table, the default; no network), the "
        "cloud's public prices fetched now where Infragram can (live), or none (off); the "
        "page adds it up in its Cost tab",
        enum=["table", "live", "off"],
    ),
    "view": _string(
        "draw one part of the diagram on its own: a frame by id or caption (a subscription, a "
        "resource group, a VNet), a view the diagram declares, a rule (tag:env=prod, "
        "category:networking, name:*-prod-*), or all"
    ),
    "infracost": _string(
        "price each component from an `infracost breakdown --format json` file, joined by "
        "the Terraform address it was drawn from"
    ),
    "size": _string(
        "the canvas the SVG and PNG are drawn on: fit (cropped to the drawing, the default) or "
        "a preset, the drawing centred and scaled to fit",
        enum=list(SIZES),
    ),
    "renderer": _string(
        "what draws the SVG and PNG: the editor runtime (default) or the static renderer",
        enum=list(RENDERERS),
    ),
    "routing": _string(
        "how the wires run in the SVG and PNG: around the cards (default) or direct",
        enum=list(ROUTINGS),
    ),
    "terraform_zip": _flag(
        "with formats terraform or terraform-modules: each skeleton as a .zip, as the page's "
        "Download menu gives it, instead of a folder"
    ),
    "title": _string("the title the exported diagram carries, in place of the document's own"),
    "status": _string(
        'where the drawing stands, drawn on the picture: "CURRENT -- verified <date>", "TARGET", '
        '"PROPOSED"'
    ),
    "offline": _flag("load nothing remote while drawing (INFRAGRAM_RENDER_OFFLINE=1)"),
    "timeout": {
        "type": "number",
        "exclusiveMinimum": 0,
        "description": "seconds a page may take to draw before the export gives up (default 120)",
    },
    "preview": _flag("attach the PNG written, to see the diagram (formats must include png)"),
    "force": _flag("replace files that already exist; only when the user asked to"),
}


def _export_options(args: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key, flag in (
        ("formats", "--formats"),
        ("output_dir", "--output-dir"),
        ("display", "--display"),
        ("write_looks", "--write-looks"),
        ("theme", "--theme"),
        ("scale", "--scale"),
        ("background", "--background"),
        ("libraries", "--libraries"),
        ("drawio_icons", "--drawio-icons"),
        ("infracost", "--infracost"),
        ("view", "--view"),
        ("size", "--size"),
        ("renderer", "--renderer"),
        ("routing", "--routing"),
        ("title", "--title"),
        ("status", "--status"),
        ("timeout", "--timeout"),
    ):
        if args.get(key):
            out += [flag, str(args[key])]
    for key, flag in (
        ("no_embed", "--no-embed"),
        ("terraform_zip", "--terraform-zip"),
        ("offline", "--offline"),
    ):
        if args.get(key):
            out.append(flag)
    if args.get("verify", True):
        out.append("--verify")
    out += _price_flags(args.get("prices"))
    if args.get("force"):
        out.append("--force")
    return out


_IMPORT = {
    "title": _string("the diagram's title (default: what was read)"),
    "spec": _string("where the diagram file goes (default <output_dir>/<slug>.py)"),
    "no_export": _flag("write the diagram file and report only"),
}


def _import_options(args: dict[str, Any]) -> list[str]:
    # the import's --title is the export's own flag, which _export_options passes
    return [
        *_optional("--spec", args.get("spec")),
        *(["--no-export"] if args.get("no_export") else []),
        *_export_options(args),
    ]


def _repeat(flag: str, values: Any) -> list[str]:
    return [part for value in (values or []) for part in (flag, str(value))]


def _optional(flag: str, value: Any) -> list[str]:
    return [flag, str(value)] if value not in (None, "") else []


# ------------------------------------------------------------ what a tool answers with
_FILE = {
    "type": "object",
    "properties": {
        "kind": {"type": "string"},
        "path": {"type": "string"},
        "bytes": {"type": "integer"},
    },
    "required": ["kind", "path", "bytes"],
}
_CHECK = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "ok": {"type": "boolean"},
        "message": {"type": "string"},
    },
    "required": ["path", "ok", "message"],
}
_COMMAND_OUTPUT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "the infragram command line run"},
        "exit_code": {"type": "integer"},
        "ok": {"type": "boolean"},
        "files": {"type": "array", "items": _FILE, "description": "every file written"},
        "checks": {"type": "array", "items": _CHECK, "description": "each file checked"},
        "notes": {"type": "array", "items": {"type": "string"}},
        "errors": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["command", "exit_code", "ok", "files", "checks", "notes", "errors"],
}
#: A command that prints JSON (``--json``): the usual record, and what it printed.
_JSON_OUTPUT: dict[str, Any] = {
    **_COMMAND_OUTPUT,
    "properties": {
        **_COMMAND_OUTPUT["properties"],
        "result": {
            "type": ["object", "array", "null"],
            "description": "what the command printed as JSON (its --json output)",
        },
    },
}


class ArgumentError(ValueError):
    """Arguments a tool's schema does not take."""


# ------------------------------------------------------------ read-only tools
def _templates(_args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    from ..paths import skill_assets

    inventory = json.loads(
        (skill_assets() / "catalog" / "inventory.json").read_text(encoding="utf-8")
    )
    folder = skill_assets() / "templates" / "cloud"
    lines = [f"{len(inventory['templates'])} templates in {folder}:"]
    templates = []
    for template in inventory["templates"]:
        lines.append(
            f"- {template['file']}: {template['title']} ({template['kind']}; "
            f"{', '.join(template['libraries'])}; {template['elements']} elements)"
        )
        templates.append(
            {
                key: template[key]
                for key in ("file", "title", "kind", "libraries", "elements")
                if key in template
            }
            | {
                "name": template["file"].removesuffix(".infragram.json"),
                "uri": f"infragram://templates/{template['file']}",
            }
        )
    return "\n".join(lines), {"folder": str(folder), "templates": templates}


def _find(args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """``infragram find``: the classes and patterns a query names, every class
    of one library when there is no query, or the libraries themselves."""
    from ..catalog.find import find, find_patterns, libraries, library_classes

    if args.get("libraries"):
        known = libraries()
        rows = [item.model_dump() for item in known]
        text = "\n".join(f"{item.id:<12} {item.name}" for item in known)
        return text, {"matches": [], "more": 0, "libraries": rows}
    library = str(args.get("library") or "").casefold() or None
    query = str(args.get("query") or "").strip()
    if not query and library is None:
        raise ArgumentError("name a query, a library, or ask for the libraries")
    whole = not query
    limit = int(args.get("limit") or (0 if whole else 20))
    hits = library_classes(library) if whole and library else find(query, library)
    patterns = [] if whole else find_patterns(query, library)
    shown = hits if limit == 0 else hits[:limit]
    matches = [{"import": hit.import_line, "title": hit.title} for hit in [*shown, *patterns]]
    if not hits and not patterns:
        if library and library not in {item.id for item in libraries()} | {"frames", "patterns"}:
            raise ArgumentError(f"no library {library!r}; libraries: true lists them")
        text = f"no node or frame class matches {query!r}" + (f" in {library}" if library else "")
        return text, {"matches": [], "more": 0}
    lines = [f"{hit.import_line}  # {hit.title}" for hit in [*shown, *patterns]]
    more = max(0, len(hits) - len(shown))
    if more:
        lines.append(f"... {more} more; narrow the query or name a library")
    return "\n".join(lines), {"matches": matches, "more": more}


def _examples(_args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    from ..cli.user.new import examples

    shipped = examples()
    width = max(map(len, shipped), default=0)
    lines = [f"{name:<{width}}  {summary}" for name, (_, summary) in shipped.items()]
    data = [
        {"name": name, "summary": summary, "uri": f"infragram://examples/{name}.py"}
        for name, (_, summary) in shipped.items()
    ]
    return "\n".join(lines), {"examples": data}


def _write_source(args: dict[str, Any]) -> str:
    """compose_source: the diagram file's text, written where compose reads it."""
    target = Path(args.get("spec") or "diagram.py")
    if target.suffix != ".py":
        raise ArgumentError("spec is a .py file name")
    here = Path.cwd().resolve()
    resolved = (here / target).resolve()
    if not resolved.is_relative_to(here):
        raise ArgumentError("spec stays inside the folder the server runs in")
    text = str(args["source"])
    if resolved.is_file():
        if resolved.read_text(encoding="utf-8", errors="replace") == text:
            return f"{target} unchanged"
        if not args.get("force"):
            raise ArgumentError(f"{target} exists; pass force only if the user asked to replace it")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(text, encoding="utf-8", newline="\n")
    return f"wrote {target} ({len(text.encode('utf-8'))} bytes)"


def _object(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


TOOLS: tuple[Tool, ...] = (
    Tool(
        name="compose",
        title="Compose a diagram file",
        description="Run a Python diagram file (with Diagram(...), frames as with-blocks) and export "
        "the diagram it builds: an editable HTML editor, an SVG and a PNG, and on request "
        "a draw.io file and its Terraform skeleton.",
        properties={"spec": _string("the diagram file (.py)"), **_EXPORT},
        required=("spec",),
        argv=lambda a: ["compose", a["spec"], *_export_options(a)],
    ),
    Tool(
        name="compose_source",
        title="Compose diagram code",
        description="Write a Python diagram file from its text and compose it, for a host without "
        "file tools: the same as writing the file and calling compose. An existing file is "
        "replaced only with force.",
        properties={
            "source": _string("the diagram file's Python text"),
            "spec": _string("the file to write (default diagram.py)"),
            **_EXPORT,
        },
        required=("source",),
        prepare=_write_source,
        argv=lambda a: ["compose", a.get("spec") or "diagram.py", *_export_options(a)],
    ),
    Tool(
        name="export_project",
        title="Export a document",
        description="Export a .infragram.json document, or an exported SVG or PNG that carries its "
        "document, to HTML, SVG and PNG, and on request draw.io and its Terraform skeleton.",
        properties={
            "document": _string("the .infragram.json document, or a picture carrying one"),
            **_EXPORT,
        },
        required=("document",),
        argv=lambda a: ["export:project", a["document"], *_export_options(a)],
    ),
    Tool(
        name="check",
        title="Check documents and pages",
        description="Check .infragram.json documents and exported pages (HTML, SVG, PNG): structure, "
        "real components, and for an SVG the picture itself.",
        properties={"paths": _strings("the files to check")},
        required=("paths",),
        read_only=True,
        argv=lambda a: ["check", *map(str, a["paths"]), "--json"],
    ),
    Tool(
        name="verify_render",
        title="Verify a render",
        description="Render a diagram several times, prove the passes identical, and check the "
        "picture in both looks (cards and bare icons).",
        properties={
            "sources": _strings("exported pages or .infragram.json documents"),
            "passes": _count("renders to compare (default 3)"),
            "display": _string("looks to check", enum=["project", "card", "icon", "both"]),
            "output_dir": _string("keep the rendered SVGs here"),
        },
        required=("sources",),
        read_only=True,
        argv=lambda a: [
            "verify:render",
            *map(str, a["sources"]),
            *_optional("--passes", a.get("passes")),
            *_optional("--display", a.get("display")),
            *_optional("--output-dir", a.get("output_dir")),
        ],
    ),
    Tool(
        name="check_policy",
        title="Check a diagram's policy",
        description="Check a diagram against the policy rules (a database in a public subnet, the "
        "internet reaching a database or a private subnet, SSH, RDP or every port open to the "
        "internet), and a Terraform folder with Checkov or Trivy when one is installed.",
        properties={
            "sources": _strings("documents, diagram files, pages, or Terraform folders"),
            "scanner": _string(
                "for a folder: the scanner (default auto)",
                enum=["auto", "checkov", "trivy", "none"],
            ),
            "strict": _flag("fail when anything is found"),
        },
        required=("sources",),
        read_only=True,
        json_result=True,
        output=_JSON_OUTPUT,
        argv=lambda a: [
            "check:policy",
            *map(str, a["sources"]),
            "--json",
            *_optional("--scanner", a.get("scanner")),
            *(["--strict"] if a.get("strict") else []),
        ],
    ),
    Tool(
        name="check_terraform",
        title="Check a diagram's Terraform",
        description="Show that a diagram's Terraform works without deploying it: terraform fmt, init "
        "and validate offline, then a plan against mocked providers. Nothing is created "
        "and no cloud is called. Takes documents, diagram files, exported pages or "
        "Terraform folders. Needs the Terraform CLI.",
        properties={
            "sources": _strings("documents, diagram files, pages or Terraform folders"),
            "style": _string(
                "for a diagram: which skeleton", enum=["both", "resources", "modules"]
            ),
            "output_dir": _string("where each plan goes as <folder>.plan.txt (default ./dist)"),
            "var_files": _strings(".tfvars files with the user's values"),
            "variables": _strings("NAME=VALUE pairs, as terraform plan -var takes them"),
            "keep": _string("keep the checked copies in this new or empty folder"),
        },
        required=("sources",),
        argv=lambda a: [
            "check:terraform",
            *map(str, a["sources"]),
            *_optional("--style", a.get("style")),
            *_optional("--output-dir", a.get("output_dir")),
            *_repeat("--var-file", a.get("var_files")),
            *_repeat("--var", a.get("variables")),
            *_optional("--keep", a.get("keep")),
        ],
    ),
    Tool(
        name="diff",
        title="Draw what changed",
        description="What changed between two versions of a diagram: elements and wires added, "
        "changed and removed, reported and drawn on the second with the marks a Terraform "
        "plan uses. Either side may be a document, a diagram file, or a page or picture "
        "that carries its document.",
        properties={
            "before": _string("the earlier version"),
            "after": _string("the later version"),
            "report_only": _flag("report what changed; draw nothing"),
            "comment": _string("also write the change report as Markdown for a pull request"),
            **_EXPORT,
        },
        required=("before", "after"),
        json_result=True,
        output=_JSON_OUTPUT,
        argv=lambda a: [
            "diff",
            a["before"],
            a["after"],
            "--json",
            *(["--report-only"] if a.get("report_only") else []),
            *_optional("--comment", a.get("comment")),
            *_export_options(a),
        ],
    ),
    Tool(
        name="views",
        title="List a diagram's views",
        description="What view can draw from a diagram: the views it declares, with their rules, "
        "and every frame by level (a subscription, a resource group, a VPC, a namespace), "
        "each with the components it holds.",
        properties={"source": _string("a document, a diagram file, or a page or picture")},
        required=("source",),
        read_only=True,
        json_result=True,
        output=_JSON_OUTPUT,
        argv=lambda a: ["views", a["source"], "--json"],
    ),
    Tool(
        name="export_set",
        title="Export a set of diagrams",
        description="Export every diagram in a folder (*.py diagram files and *.infragram.json "
        "documents), one folder per diagram with a copy of its source, every file checked, "
        "and the set's README with the command that rebuilds it.",
        properties={
            "folder": _string("the folder holding the diagrams"),
            "passes": {
                "type": "integer",
                "minimum": 0,
                "description": "renders compared per page (default 3; 0 skips the render gate)",
            },
            "jobs": _count("diagrams drawn at once (default 1)"),
            **{
                key: value
                for key, value in _EXPORT.items()
                if key not in ("view", "title", "verify", "preview")
            },
        },
        required=("folder",),
        argv=lambda a: [
            "export:set",
            a["folder"],
            *_optional("--passes", a.get("passes")),
            *_optional("--jobs", a.get("jobs")),
            # a set checks every file itself, and has no --title or --view
            *_export_options({**a, "verify": False, "title": None, "view": None}),
        ],
    ),
    Tool(
        name="costs",
        title="Add up what a diagram costs",
        description="What a diagram costs, added up: the total, each frame's and each priced "
        "component's, from the prices it carries, the cloud's published prices (prices) or an "
        "Infracost breakdown joined by Terraform address (infracost).",
        properties={
            "source": _string("a document, a diagram file, or a page or picture carrying one"),
            "prices": _EXPORT["prices"],
            "infracost": _EXPORT["infracost"],
            "csv": _string("also write the rollup as CSV to this file"),
            "force": _flag("with csv: replace a file this tool did not write; only when asked to"),
        },
        required=("source",),
        json_result=True,
        output=_JSON_OUTPUT,
        argv=lambda a: [
            "costs",
            a["source"],
            "--json",
            *_price_flags(a.get("prices")),
            *_optional("--infracost", a.get("infracost")),
            *_optional("--csv", a.get("csv")),
            *(["--force"] if a.get("force") else []),
        ],
    ),
    Tool(
        name="import_terraform",
        title="Draw existing Terraform",
        description="Draw what a Terraform configuration folder, a plan (terraform show -json) or a "
        "state declares: an editable diagram file, a report of every resource, and the "
        "diagram exported. A plan's changes are marked on the cards; corrections kept in "
        "<diagram>.overrides.toml apply on every import.",
        properties={
            "source": _string("a configuration folder, a plan or state JSON, or terraform.tfstate"),
            "var_files": _strings(".tfvars files, as terraform plan -var-file takes them"),
            "variables": _strings("NAME=VALUE pairs, as terraform plan -var takes them"),
            "comment": _string("also write the plan's changes as Markdown to this file"),
            **_IMPORT,
            **_EXPORT,
        },
        required=("source",),
        argv=lambda a: [
            "import:terraform",
            a["source"],
            *_repeat("--var-file", a.get("var_files")),
            *_repeat("--var", a.get("variables")),
            *_optional("--comment", a.get("comment")),
            *_import_options(a),
        ],
    ),
    Tool(
        name="import_diagram",
        title="Draw another tool's diagram",
        description="Draw a draw.io, Mermaid, PlantUML, Excalidraw or Visio file, or a Markdown "
        "page's diagram blocks, as an Infragram diagram: an editable diagram file per "
        "diagram, a report of what each shape was drawn as, and the diagram exported.",
        properties={
            "source": _string("the file to read"),
            "format": _string(
                "what the file is (default: told by its name, then its contents)",
                enum=["drawio", "mermaid", "plantuml", "excalidraw", "visio", "markdown"],
            ),
            "pages": _strings("only these diagrams of the file, by title or 1-based number"),
            "list_only": _flag("list the diagrams the file holds and stop"),
            **_IMPORT,
            **_EXPORT,
        },
        required=("source",),
        argv=lambda a: [
            "import:diagram",
            a["source"],
            *_optional("--format", a.get("format")),
            *_repeat("--page", a.get("pages")),
            *(["--list"] if a.get("list_only") else []),
            *_import_options(a),
        ],
    ),
    Tool(
        name="discover",
        title="Draw a live cloud account",
        description="Draw a live Azure estate or a Kubernetes cluster, "
        "read-only through the cloud's own CLI or kubectl as the user is signed in (list, "
        "describe and get calls only): an editable diagram file, a report, and the diagram "
        "exported.",
        properties={
            "cloud": _string("the cloud to read", enum=["azure", "kubernetes"]),
            "subscription": _string("the Azure subscription"),
            "resource_groups": _strings("Azure resource groups to read"),
            "source": _string(
                "Azure only: how to read it, cli (one az list call per kind, the default) or "
                "resource-graph (one Azure Resource Graph query)",
                enum=["cli", "resource-graph"],
            ),
            "context": _string("the kubeconfig context (Kubernetes)"),
            "namespaces": _strings("Kubernetes namespaces to read (default: every one)"),
            "include_system": _flag("Kubernetes: also draw kube-system and the other system ones"),
            **_IMPORT,
            **_EXPORT,
        },
        required=("cloud",),
        open_world=True,
        argv=lambda a: [
            f"discover:{a['cloud']}",
            *_optional("--subscription", a.get("subscription")),
            *_repeat("--resource-group", a.get("resource_groups")),
            *_optional("--source", a.get("source")),
            *_optional("--context", a.get("context")),
            *_repeat("--namespace", a.get("namespaces")),
            *(["--include-system"] if a.get("include_system") else []),
            *_import_options(a),
        ],
    ),
    Tool(
        name="export_azure",
        title="Draw Azure inventory or a saved snapshot",
        description="Read Azure Resource Graph through the signed-in az session, across selected "
        "subscriptions, and draw network or resource-group views. Save a raw snapshot to replay "
        "offline; unknown resource types keep a generic icon and are reported.",
        properties={
            "subscriptions": _strings("Azure subscription names or ids; default the current one"),
            "all_subscriptions": _flag("read every enabled subscription the az session can see"),
            "management_groups": _strings(
                "management group names; read every enabled subscription under them"
            ),
            "resource_groups": _strings("resource-group name patterns, with * and ? wildcards"),
            "exclude_types": _strings("ARM resource-type patterns to leave out"),
            "from_snapshot": _string("read this saved Azure snapshot instead of calling Azure"),
            "snapshot_out": _string("also save the raw snapshot to this JSON file"),
            "view": _string("how inventory is grouped", enum=["network", "groups", "both"]),
            "everything": _flag("include plumbing and resource groups managed by services"),
            "references": _flag("also wire resources to resources their properties reference"),
            "slug": _string("the output file name, without an extension"),
            **{
                key: _EXPORT[key]
                for key in (
                    "formats",
                    "output_dir",
                    "display",
                    "theme",
                    "scale",
                    "background",
                    "title",
                    "verify",
                    "force",
                    "preview",
                )
            },
        },
        open_world=True,
        argv=lambda a: [
            "export:azure",
            *_repeat("--subscription", a.get("subscriptions")),
            *(["--all-subscriptions"] if a.get("all_subscriptions") else []),
            *_repeat("--management-group", a.get("management_groups")),
            *_repeat("--resource-group", a.get("resource_groups")),
            *_repeat("--exclude-type", a.get("exclude_types")),
            *_optional("--from-snapshot", a.get("from_snapshot")),
            *_optional("--snapshot-out", a.get("snapshot_out")),
            *_optional("--view", a.get("view")),
            *(["--all"] if a.get("everything") else []),
            *(["--references"] if a.get("references") else []),
            *_optional("--slug", a.get("slug")),
            *[
                part
                for key, flag in (
                    ("formats", "--formats"),
                    ("output_dir", "--output-dir"),
                    ("display", "--display"),
                    ("theme", "--theme"),
                    ("scale", "--scale"),
                    ("background", "--background"),
                    ("title", "--title"),
                )
                for part in _optional(flag, a.get(key))
            ],
            *(["--verify"] if a.get("verify", True) else []),
            *(["--force"] if a.get("force") else []),
        ],
    ),
    Tool(
        name="new_diagram",
        title="Start a diagram file",
        description="Start a diagram from a shipped example (list_examples names them), a Python "
        "file to edit and compose, or from a shipped template (list_templates), an "
        ".infragram.json document to export: a copy with its own title and slug.",
        properties={
            "example": _string("the example to start from"),
            "template": _string("or the template to start from, in place of an example"),
            "path": _string(
                "the file to write (default <example>.py, or <template>.infragram.json)"
            ),
            "title": _string("the diagram's title (default: the example's or template's)"),
            "force": _EXPORT["force"],
        },
        argv=lambda a: [
            "new",
            *(["--template", a["template"]] if a.get("template") else [a.get("example") or ""]),
            *([a["path"]] if a.get("path") else []),
            *_optional("--title", a.get("title")),
            *(["--force"] if a.get("force") else []),
        ],
    ),
    Tool(
        name="layout_save",
        title="Keep the editor's layout",
        description="Keep what the user moved or resized in the editor beside a Python diagram "
        "file: read what the editor saved and write <diagram>.layout.json, which compose "
        "then draws from. The diagram file itself is never touched.",
        properties={
            "saved": _string(
                "what the editor saved: a downloaded .infragram.json, the saved page, or an "
                "exported SVG or PNG that carries its document"
            ),
            "spec": _string("the diagram file the layout belongs to"),
        },
        required=("saved", "spec"),
        argv=lambda a: ["layout:save", a["saved"], "--for", a["spec"]],
    ),
    Tool(
        name="list_templates",
        title="List the templates",
        description="List the shipped reference diagrams (.infragram.json templates): file, title, "
        "kind, libraries and size; each is also a resource to read.",
        properties={},
        read_only=True,
        answer=_templates,
        output=_object(
            {
                "folder": {"type": "string"},
                "templates": {"type": "array", "items": {"type": "object"}},
            },
            ["folder", "templates"],
        ),
    ),
    Tool(
        name="list_examples",
        title="List the examples",
        description="List the shipped example diagram files new_diagram starts from, with what each "
        "draws; each is also a resource to read.",
        properties={},
        read_only=True,
        answer=_examples,
        output=_object({"examples": {"type": "array", "items": {"type": "object"}}}, ["examples"]),
    ),
    Tool(
        name="find_components",
        title="Find node classes",
        description="Find the node and frame classes a diagram file imports, by words in their name, "
        "service, icon or the names architects use (e.g. 's3', 'aks', 'load balancer', 'vpc'); "
        "answers with import lines, best match first.",
        properties={
            "query": _string("words to match, all of them; leave it out to list a whole library"),
            "library": _string(
                "only this library: azure, kubernetes, databricks, frames, patterns..."
            ),
            "libraries": _flag("list the libraries, with their names and how many classes each"),
            "limit": _count("the most to list (default 20 for a query, every one for a library)"),
        },
        read_only=True,
        answer=_find,
        output=_object(
            {
                "matches": {
                    "type": "array",
                    "items": _object(
                        {"import": {"type": "string"}, "title": {"type": "string"}},
                        ["import", "title"],
                    ),
                },
                "more": {"type": "integer"},
                "libraries": {"type": "array", "items": {"type": "object"}},
            },
            ["matches", "more"],
        ),
    ),
    Tool(
        name="recipes",
        title="List the 3D recipes",
        description="The 3D items drawn by spec (Iso(..., recipe=...)): every recipe with its "
        "knobs, types, choices and defaults, the families and their colours, and the badge "
        "glyphs; with a name, that recipe and a ready-made Iso(...) line.",
        properties={"name": _string("one recipe to describe (default: all of them)")},
        read_only=True,
        json_result=True,
        output=_JSON_OUTPUT,
        argv=lambda a: ["recipes", *([a["name"]] if a.get("name") else []), "--json"],
    ),
    Tool(
        name="draw_recipe",
        title="Draw one 3D item",
        description="Render one 3D recipe to an SVG with its knobs, family, colour and badge, to "
        "see it before placing it in a diagram (needs Playwright and Chromium).",
        properties={
            "name": _string("the recipe"),
            "svg": _string("the SVG to write"),
            "set": _strings("knob values as knob=value, e.g. units=3"),
            "family": _string("the family, which picks the colour"),
            "colour": _string("a colour in place of the family's"),
            "glyph": _string("the badge: a glyph name, or path data"),
            "no_badge": _flag("draw no badge"),
            "force": _EXPORT["force"],
        },
        required=("name", "svg"),
        argv=lambda a: [
            "recipes",
            a["name"],
            "--svg",
            a["svg"],
            *[part for value in a.get("set") or [] for part in ("--set", str(value))],
            *_optional("--family", a.get("family")),
            *_optional("--colour", a.get("colour")),
            *_optional("--glyph", a.get("glyph")),
            *(["--no-badge"] if a.get("no_badge") else []),
            *(["--force"] if a.get("force") else []),
        ],
    ),
    Tool(
        name="docs",
        title="Read a reference document",
        description="The reference documents the skill ships (compose, frames, export, "
        "providers/azure ...): the list with a line on each, or one of them in full.",
        properties={"name": _string("the document: compose, export, providers/azure ...")},
        read_only=True,
        argv=lambda a: ["docs", *([a["name"]] if a.get("name") else [])],
    ),
)
_BY_NAME = {tool.name: tool for tool in TOOLS}
