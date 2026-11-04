"""The user commands: what an installed copy runs as well as a checkout.

They are package code in :mod:`infragram.cli.user`, called in-process in
the user's own directory, so relative paths mean what the user meant.
"""

from __future__ import annotations

from ..scripts import CALL_PREFIX

__all__ = ["COMMANDS"]

_USER = CALL_PREFIX + "infragram.cli.user."

#: command -> (target, help text), in the order the help lists them.
COMMANDS: dict[str, tuple[str, str]] = {
    "new": (
        _USER + "new:main",
        "start a diagram file from a shipped example (or a document from a template with "
        "--template): its own title and slug, ready to compose",
    ),
    "templates": (
        _USER + "templates:main",
        "list the shipped template documents: name, title, libraries, elements and "
        "connections; new --template starts from one",
    ),
    "compose": (
        _USER + "compose:main",
        "run a Python diagram file and export it to HTML, SVG and PNG",
    ),
    "export:project": (
        _USER + "export_project:main",
        "render a .infragram.json document to HTML, SVG and PNG",
    ),
    "export:azure": (
        _USER + "export_azure:main",
        "draw live Azure subscriptions or a saved snapshot, with network or resource-group views",
    ),
    "export:set": (
        _USER + "export_set:main",
        "export a folder of diagram files, one folder per diagram, checked, with the set's README",
    ),
    "find": (
        _USER + "find:main",
        "which class to import for a component: aks, load balancer, vnet; best match first, "
        "then the patterns; --library lists a whole library, --libraries the libraries",
    ),
    "recipes": (
        _USER + "recipes:main",
        "the 3D items drawn by spec: every recipe with its knobs, the families, colours and "
        "glyphs; one in detail, or drawn to an SVG with --svg",
    ),
    "diff": (
        _USER + "diff:main",
        "what changed between two versions of a diagram, written out and drawn",
    ),
    "check:policy": (
        _USER + "check_policy:main",
        "what a reviewer would stop in a diagram (a database in a public subnet, the internet "
        "reaching a database), and Checkov or Trivy on a Terraform folder when installed",
    ),
    "views": (
        _USER + "views:main",
        "list what --view can draw from a diagram: the views it declares, and every frame by level",
    ),
    "costs": (
        _USER + "costs:main",
        "what a diagram costs a month, approximately, added up by frame: Azure "
        "priced from the shipped tables, --prices live, or an Infracost breakdown; --csv "
        "writes it out",
    ),
    "layout:save": (
        _USER + "layout:main",
        "keep what was moved in the editor beside a diagram file, so compose draws "
        "it where it was left",
    ),
    "schema": (
        _USER + "schema:main",
        "the JSON Schema of an .infragram.json document, for an editor's completion",
    ),
    "docs": (
        _USER + "docs:main",
        "list the reference documents the skill ships (compose, frames, providers/azure...), "
        "print one, or --path to say where it is",
    ),
    "check": (
        _USER + "check:main",
        "check documents and exported pages: structure, real components, the "
        "picture itself, nothing remote",
    ),
    "check:terraform": (
        _USER + "check_terraform:main",
        "check that a diagram's Terraform works without deploying it: fmt, init and "
        "validate offline, then a plan against mocked providers",
    ),
    "verify:render": (
        _USER + "render_gate:main",
        "render a diagram several times, prove the passes identical, and "
        "check the picture in both looks",
    ),
    "import:terraform": (
        _USER + "import_estate:import_terraform",
        "draw what a Terraform configuration, plan or state declares: an "
        "editable diagram file, a report, and the diagram exported",
    ),
    "import:diagram": (
        _USER + "import_diagram:import_diagram",
        "draw a draw.io, Mermaid, PlantUML, Excalidraw or Visio diagram (or a Markdown "
        "page's blocks) as an editable diagram file, a report, and the diagram exported",
    ),
    "import:drawio": (
        _USER + "import_diagram:import_drawio",
        "import:diagram for a draw.io file: .drawio, .drawio.png, .drawio.svg, every page",
    ),
    "import:mermaid": (
        _USER + "import_diagram:import_mermaid",
        "import:diagram for Mermaid: a .mmd file, or a Markdown page's mermaid blocks",
    ),
    "discover:azure": (
        _USER + "import_estate:discover_azure",
        "draw a live Azure estate, read-only through the az CLI",
    ),
    "discover:kubernetes": (
        _USER + "import_estate:discover_kubernetes",
        "draw a live Kubernetes cluster, read-only through kubectl",
    ),
    "mcp": (
        _USER + "mcp:main",
        "serve these commands to an MCP client over stdio (the plugin's MCP server)",
    ),
    "hook:check": (
        _USER + "hook_check:main",
        "the plugin's check hook: check a diagram an agent just wrote (event JSON on stdin)",
    ),
    "plugin:install": (
        _USER + "plugin_install:install_main",
        "register the plugin this copy carries with Claude Code, Codex or Pi",
    ),
    "plugin:path": (
        _USER + "plugin_install:path_main",
        "print the plugin folder this copy carries",
    ),
}
