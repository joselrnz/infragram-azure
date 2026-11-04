"""The MCP server's resources (the references, templates, examples, catalogs
and the document's schema) and its prompts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from .tools import ArgumentError


# ------------------------------------------------------------ resources
def _resources() -> dict[str, tuple[dict[str, Any], Path]]:
    """uri -> (the listing, the file): the references, templates, examples and schema."""
    from ..cli.user.new import examples
    from ..paths import skill_assets, skill_references
    from ..projects.schema import schema_path

    out: dict[str, tuple[dict[str, Any], Path]] = {}

    def add(uri: str, path: Path, title: str, mime: str, description: str) -> None:
        out[uri] = (
            {
                "uri": uri,
                "name": path.name,
                "title": title,
                "mimeType": mime,
                "description": description,
            },
            path,
        )

    references = skill_references()
    for path in sorted(references.rglob("*.md")):
        relative = path.relative_to(references).as_posix()
        add(
            f"infragram://references/{relative}",
            path,
            f"Reference: {relative.removesuffix('.md')}",
            "text/markdown",
            _first_heading(path) or "an Infragram reference",
        )
    for path in sorted((skill_assets() / "templates" / "cloud").glob("*.infragram.json")):
        add(
            f"infragram://templates/{path.name}",
            path,
            f"Template: {path.name.removesuffix('.infragram.json')}",
            "application/json",
            "a shipped reference diagram, as a .infragram.json document",
        )
    for name, (path, summary) in examples().items():
        add(
            f"infragram://examples/{name}.py",
            path,
            f"Example: {name}",
            "text/x-python",
            summary or "a shipped example diagram file",
        )
    add(
        "infragram://schema/project",
        schema_path(),
        "The .infragram.json schema",
        "application/schema+json",
        "the JSON Schema of an Infragram document",
    )
    return out


_CATALOG = "infragram://catalog/"
_CATALOG_TEMPLATE = {
    "uriTemplate": _CATALOG + "{library}",
    "name": "catalog",
    "title": "A library's node classes",
    "mimeType": "text/markdown",
    "description": "every node and frame class of one library (aws, azure, gcp, kubernetes, "
    "onprem, frames...) as the import line a diagram file writes, by module",
}


def _catalog(library: str) -> str | None:
    """One library's classes as import lines, by module; None for no such library."""
    from ..catalog.find import node_classes

    classes = [found for found in node_classes() if found.library == library.casefold()]
    if not classes:
        return None
    lines = [f"# {library}: {len(classes)} classes"]
    module = ""
    for found in sorted(classes, key=lambda found: (found.module, found.name)):
        if found.module != module:
            module = found.module
            lines += ["", f"## {module}", ""]
        lines.append(f"- `{found.name}`: {found.title}")
    return "\n".join(lines) + "\n"


def _first_heading(path: Path) -> str:
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("#"):
                    return line.lstrip("#").strip()
    except OSError:
        pass
    return ""


# ------------------------------------------------------------ prompts
class Prompt(BaseModel):
    """A prompt a client offers its user: its arguments, and the message it starts with."""

    model_config = ConfigDict(frozen=True)

    name: str
    title: str
    description: str
    arguments: tuple[tuple[str, str, bool], ...]
    template: str

    def listing(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "arguments": [
                {"name": name, "description": description, "required": required}
                for name, description, required in self.arguments
            ],
        }

    def messages(self, arguments: dict[str, Any]) -> list[dict[str, Any]]:
        missing = [
            name for name, _, required in self.arguments if required and not arguments.get(name)
        ]
        if missing:
            raise ArgumentError(f"missing argument: {', '.join(missing)}")
        values = {name: str(arguments.get(name) or "") for name, _, _ in self.arguments}
        return [
            {"role": "user", "content": {"type": "text", "text": self.template.format(**values)}}
        ]


PROMPTS: tuple[Prompt, ...] = (
    Prompt(
        name="draw_architecture",
        title="Draw an architecture",
        description="Draw an architecture described in words as an Infragram diagram.",
        arguments=(
            ("description", "what to draw: the system, its parts and how they connect", True),
        ),
        template="Draw this architecture with Infragram:\n\n{description}\n\n"
        "Read infragram://references/compose.md first. Find the node classes with "
        "find_components, write the diagram file (frames as with-blocks, every wire labelled "
        "where it says something), compose it with preview: true, look at the picture, and "
        "fix what reads badly before calling it done.",
    ),
    Prompt(
        name="diagram_from_terraform",
        title="Draw existing Terraform",
        description="Draw what a Terraform configuration, plan or state declares, and tidy it.",
        arguments=(("source", "a configuration folder, a plan JSON or a state file", True),),
        template="Draw the Terraform at {source} with import_terraform (preview: true). Read the "
        "report it writes; where a resource is drawn wrong or a wire is missing, keep the "
        "correction in <diagram>.overrides.toml so the next import keeps it, and import again.",
    ),
    Prompt(
        name="review_diagram",
        title="Review a diagram",
        description="Check a diagram and its pictures, and say what to fix.",
        arguments=(
            ("path", "a diagram file, a .infragram.json document or an exported page", True),
        ),
        template="Review the Infragram diagram at {path}: run check on it (and on its exported "
        "HTML and SVG), and verify_render on the document. Report every problem the checks "
        "find, then what an architect would question: missing frames, unlabelled wires, "
        "components drawn in the wrong place.",
    ),
)
_PROMPTS = {prompt.name: prompt for prompt in PROMPTS}
