"""``infragram templates``: the shipped reference diagrams, as documents.

Beside the example diagram files (``infragram new --list``) the skill ships
reference diagrams as ``.infragram.json`` documents: a Site-to-Site VPN, an
AKS baseline, a campus LAN, a SOC. :func:`templates` reads them where the
installed copy keeps them (:func:`infragram.paths.skill_assets`) and counts
what each draws the way the inventory does, so the listing is what ships,
not what a generated file last said. ``infragram new --template NAME``
starts a document of the user's own from one.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

__all__ = ["SUFFIX", "Template", "lookup", "main", "summary", "templates"]

#: What every template file, and every document ``new --template`` writes, ends in.
SUFFIX = ".infragram.json"


class Template(BaseModel):
    """One shipped template: the name ``new --template`` takes, and what it draws."""

    model_config = ConfigDict(frozen=True)

    name: str
    path: Path
    slug: str
    title: str
    description: str = ""
    kind: str = "single-cloud"
    providers: tuple[str, ...] = ()
    elements: int = 0
    frames: int = 0
    connections: int = 0

    def row(self) -> dict[str, Any]:
        """The template as JSON data: its file's name, then its path as a string."""
        data = self.model_dump(mode="json")
        return {"name": data.pop("name"), "file": self.path.name, **data}


def _counts(root: dict[str, Any]) -> tuple[int, int, int]:
    """Elements, frames and connections under a topology root, counted as the
    inventory counts them: the root group is a frame of convenience, not a
    drawn one, and an element is a frame when it holds others or says so."""
    elements = frames = connections = 0
    stack = [root]
    while stack:
        item = stack.pop()
        elements += 1
        children = item.get("children") or []
        if children or (item.get("attributes") or {}).get("editor_frame_group"):
            frames += 1
        connections += len(item.get("connections") or [])
        stack.extend(children)
    return elements - 1, max(frames - 1, 0), connections


def templates() -> dict[str, Template]:
    """name -> the template, for every shipped ``.infragram.json`` template,
    by name. The name is the file's, without ``.infragram.json``."""
    from ...paths import skill_assets

    out: dict[str, Template] = {}
    for path in sorted((skill_assets() / "templates" / "cloud").glob(f"*{SUFFIX}")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        name = path.name.removesuffix(SUFFIX)
        selections = data.get("providers") or [{"id": data.get("provider")}]
        elements, frames, connections = _counts(data.get("topology") or {})
        out[name] = Template(
            name=name,
            path=path,
            slug=str(data.get("slug") or name),
            title=str(data.get("title") or ""),
            description=str(data.get("description") or ""),
            # a document that names no kind is the model's default
            kind=str(data.get("kind") or "single-cloud"),
            providers=tuple(
                str(selection["id"])
                for selection in selections
                if isinstance(selection, dict) and selection.get("id")
            ),
            elements=elements,
            frames=frames,
            connections=connections,
        )
    return out


def lookup(name: str) -> Template | None:
    """The template *name* means: its name, its file name or its slug."""
    shipped = templates()
    found = shipped.get(name) or shipped.get(Path(name).name.removesuffix(SUFFIX))
    if found is None:
        found = next((template for template in shipped.values() if template.slug == name), None)
    return found


def summary(template: Template) -> str:
    """One line of what a template draws, after its name."""
    return (
        f"{template.title} ({', '.join(template.providers) or template.kind}; "
        f"{template.elements} elements, {template.connections} connections)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="infragram templates",
        description="List the shipped reference diagrams (.infragram.json documents): the name "
        "`infragram new --template NAME` takes, the title, the libraries each draws with, and "
        "how many elements and connections it holds.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print them as JSON: name, file, slug, title, description, kind, providers and counts",
    )
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)
    shipped = templates()
    if options.json:
        print(json.dumps([template.row() for template in shipped.values()], indent=1))
        return 0
    width = max(map(len, shipped), default=0)
    for name, template in shipped.items():
        print(f"{name:<{width}}  {summary(template)}")
    return 0
