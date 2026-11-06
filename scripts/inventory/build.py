#!/usr/bin/env python3
"""Build, or check, the component inventory: everything Infragram ships.

The inventory is the answer to "do we have all the components?": every
library with its kind and coverage, every component it offers (id, name,
category), every frame and starter stack, every shared primitive, and every
shipped template. It is generated from the same registries and library
payload the editor sidebar is built from, so it cannot drift from the product
by accident - only the committed copies can drift, and ``--check`` catches
that.

    PYTHONPATH=src python -m infragram inventory           # rewrite the text files
    PYTHONPATH=src python -m infragram inventory --images  # also redraw the picture sheets
    PYTHONPATH=src python -m infragram inventory --check   # gate: current, pictures present, icons decode

Outputs:
    skills/infragram-azure/assets/catalog/inventory.json   machine-readable, complete (shipped)
    skills/infragram-azure/references/inventory.md         human summary with counts (shipped)
    skills/infragram-azure/references/shared-components.md every shared component: id, class, name (shipped)
    docs/inventory/README.md                         the same summary with pictures
    docs/inventory/icons-<library>.png               every component of a library, by category
    docs/inventory/frames-<library>.png              every frame of a library as the editor draws it
    docs/inventory/frames-tabs.png                   every frame tab icon on one sheet

Picture generation needs Playwright with Chromium and Pillow (``pip install
-e ".[png]"``); the text files and the check need neither.
"""

from __future__ import annotations

import argparse
import html as H
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = next(path for path in Path(__file__).resolve().parents if (path / ".claude-plugin").is_dir())
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from lib import gatelib  # noqa: E402

from infragram.catalog import load_default_provider_registry  # noqa: E402
from infragram.editor import load_sidebar_catalog  # noqa: E402
from infragram.editor.artwork import artwork_bytes  # noqa: E402
from infragram.editor.sidebar import _library_payload  # noqa: E402
from infragram.utils.generated import write_generated_text  # noqa: E402

SKILL = ROOT / "skills" / "infragram-azure"
JSON_PATH = SKILL / "assets" / "catalog" / "inventory.json"
MARKDOWN_PATH = SKILL / "references" / "inventory.md"
SHARED_PATH = SKILL / "references" / "shared-components.md"
TEMPLATES = SKILL / "assets" / "templates" / "cloud"
DOCS = ROOT / "docs" / "inventory"
DOCS_MARKDOWN_PATH = DOCS / "README.md"
SCHEMA = 1
CORE_GROUP = "generic"


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------


def load_payload():
    """The provider registry and the full library payload the editor embeds."""

    registry = load_default_provider_registry()
    providers = list(
        registry.providers.values() if isinstance(registry.providers, dict) else registry.providers
    )
    catalogs = tuple(load_sidebar_catalog(provider.id) for provider in providers)
    payload = _library_payload(catalogs, tuple(provider.id for provider in providers))
    return providers, payload


def _walk(element: dict) -> tuple[int, int, int]:
    """Count elements, frames and connections in a template topology."""

    elements = frames = connections = 0
    stack = [element]
    while stack:
        item = stack.pop()
        elements += 1
        children = item.get("children") or []
        attributes = item.get("attributes") or {}
        if children or attributes.get("editor_frame_group"):
            frames += 1
        connections += len(item.get("connections") or [])
        stack.extend(children)
    # the root group is a frame of convenience, not a drawn one
    return elements - 1, max(frames - 1, 0), connections


def build_inventory(loaded=None) -> tuple[dict, list[str]]:
    """Return the inventory and a list of artwork problems (empty when clean)."""

    providers, payload = loaded or load_payload()

    problems: list[str] = []
    components_by_provider: dict[str, list[dict]] = defaultdict(list)
    frames_by_group: dict[str, list[dict]] = defaultdict(list)
    for component in payload["components"]:
        uri = str(component.get("iconUri") or "")
        artwork = artwork_bytes(uri)
        if artwork is None:
            problems.append(f"{component['qualifiedId']}: artwork is not an inline SVG data URI")
        elif b"<svg" not in artwork:
            problems.append(f"{component['qualifiedId']}: artwork does not decode to an SVG")
        entry = {
            "id": component["serviceId"],
            "name": component["name"],
            "category": component["categoryId"],
        }
        if component.get("mappingStatus", "mapped") != "mapped":
            entry["mapping"] = component["mappingStatus"]
        if component.get("componentKind") == "boundary":
            # A boundary belonging to no vendor library is a core frame: the
            # generic Section is one. Dropping those recorded fewer components
            # than the product ships, and the shipped checker reads this file,
            # so it rejected documents the schema and compose both accept.
            frames_by_group[component.get("frameGroup") or CORE_GROUP].append(
                {
                    **entry,
                    "kind": component.get("boundaryKind", ""),
                    "level": int(component.get("hierarchyLevel") or 0),
                }
            )
        else:
            components_by_provider[component["provider"]].append(entry)

    presets = {preset["group"]: preset for preset in payload.get("framePresets", [])}
    libraries = []
    for provider in providers:
        components = sorted(
            components_by_provider.get(provider.id, []), key=lambda c: (c["category"], c["id"])
        )
        frames = sorted(frames_by_group.get(provider.id, []), key=lambda f: (f["level"], f["id"]))
        preset = presets.get(provider.id)
        libraries.append(
            {
                "id": provider.id,
                "display_name": provider.display_name,
                "kind": provider.kind,
                "coverage": provider.coverage,
                "mark_only": False,
                "icons": len(components),
                # components the category map could not place in a canonical
                # category; they land in "custom" and are worth mapping
                "unmapped": sum(
                    1 for c in components if c.get("mapping") or c["category"] == "custom"
                ),
                "categories": dict(sorted(Counter(c["category"] for c in components).items())),
                "components": components,
                "frames": frames,
                "starter_stack": (
                    {
                        "id": preset["id"],
                        "label": preset.get("label", preset["id"]),
                        "frames": list(preset.get("componentIds") or []),
                    }
                    if preset
                    else None
                ),
            }
        )
    core_frames = sorted(frames_by_group.get(CORE_GROUP, []), key=lambda f: (f["level"], f["id"]))
    shared = sorted(
        components_by_provider.get("infragram", []), key=lambda c: (c["category"], c["id"])
    )

    templates = []
    for path in sorted(TEMPLATES.glob("*.infragram.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        selections = data.get("providers") or [{"id": data.get("provider")}]
        element_count, frame_count, connection_count = _walk(data["topology"])
        templates.append(
            {
                "file": path.name,
                "slug": data.get("slug", path.stem.replace(".infragram", "")),
                "title": data.get("title", ""),
                "kind": data.get("kind", "single-cloud"),
                "libraries": [selection["id"] for selection in selections],
                "elements": element_count,
                "frames": frame_count,
                "connections": connection_count,
            }
        )

    inventory = {
        "schema": SCHEMA,
        "totals": {
            "libraries": len(libraries),
            "vendor_icons": sum(library["icons"] for library in libraries),
            "unmapped": sum(library["unmapped"] for library in libraries),
            "shared_primitives": len(shared),
            "frames": len(core_frames) + sum(len(library["frames"]) for library in libraries),
            "frame_groups": 1 + sum(1 for library in libraries if library["frames"]),
            "starter_stacks": sum(1 for library in libraries if library["starter_stack"]),
            "templates": len(templates),
        },
        "categories": [category["id"] for category in payload.get("categories", [])],
        "libraries": libraries,
        "core_frames": core_frames,
        "shared_primitives": shared,
        "templates": templates,
    }
    return inventory, problems


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------


def _totals_line(inventory: dict) -> str:
    totals = inventory["totals"]
    return (
        f"**{totals['libraries']} libraries · {totals['vendor_icons']} vendor icons "
        f"({totals['unmapped']} still in the generic `custom` category) · "
        f"{totals['shared_primitives']} shared primitives · {totals['frames']} frames in "
        f"{totals['frame_groups']} groups · {totals['starter_stacks']} starter stacks · "
        f"{totals['templates']} templates.**"
    )


def _library_table(inventory: dict) -> list[str]:
    lines = [
        "| Library | Kind | Coverage | Icons | Unmapped | Frames | Starter stack |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for library in inventory["libraries"]:
        icons, unmapped = str(library["icons"]), str(library["unmapped"])
        stack = library["starter_stack"]["label"] if library["starter_stack"] else "-"
        lines.append(
            f"| {library['display_name']} | {library['kind']} | {library['coverage']} | "
            f"{icons} | {unmapped} | {len(library['frames'])} | {stack} |"
        )
    return lines


TABLE_NOTE = [
    "*Unmapped* counts components the category map could not place in a",
    "canonical category, so they sit under `custom` in the sidebar; mapping them",
    "is catalog work, not missing artwork.",
]


def _templates_table(inventory: dict) -> list[str]:
    lines = [
        "| File | Title | Libraries | Elements | Frames | Wires |",
        "|---|---|---|---:|---:|---:|",
    ]
    for template in inventory["templates"]:
        lines.append(
            f"| `{template['file']}` | {template['title']} | {', '.join(template['libraries'])} | "
            f"{template['elements']} | {template['frames']} | {template['connections']} |"
        )
    return lines


def render_markdown(inventory: dict) -> str:
    """The shipped summary: counts only, no pictures."""

    totals = inventory["totals"]
    lines = [
        "# Component inventory",
        "",
        "Generated by `python -m infragram inventory`; `infragram verify:all` fails when",
        "this file or `assets/catalog/inventory.json` no longer matches what the",
        "libraries actually ship, or when any component's artwork fails to decode.",
        "Do not edit by hand. The same inventory with a picture of every icon and",
        "frame is kept in the repository's `docs/inventory/` folder.",
        "",
        _totals_line(inventory),
        "",
        "## Libraries",
        "",
        *_library_table(inventory),
        "",
        *TABLE_NOTE,
        "",
        "## Components by category",
        "",
    ]
    for library in inventory["libraries"]:
        breakdown = ", ".join(
            f"{category} {count}" for category, count in library["categories"].items()
        )
        lines.append(f"- **{library['display_name']}** ({library['icons']}): {breakdown}")
    shared_counts = Counter(component["category"] for component in inventory["shared_primitives"])
    lines.append(
        f"- **Shared primitives** ({totals['shared_primitives']}, every library): "
        + ", ".join(f"{category} {count}" for category, count in sorted(shared_counts.items()))
    )
    lines += ["", "## Frames", ""]
    lines.append(
        "- **Core (shared)**: "
        + ", ".join(f"{frame['name']} ({frame['kind']})" for frame in inventory["core_frames"])
    )
    for library in inventory["libraries"]:
        if not library["frames"]:
            continue
        lines.append(
            f"- **{library['display_name']}**: "
            + ", ".join(f"{frame['name']} ({frame['kind']})" for frame in library["frames"])
        )
    lines += ["", "## Templates", "", *_templates_table(inventory)]
    lines += [
        "",
        "The complete component list, one entry per icon with its category, is in",
        "`assets/catalog/inventory.json`.",
        "",
    ]
    return "\n".join(lines)


def _shared_classes() -> dict[str, str]:
    """Shared component id -> the class compose code draws it with, as
    ``shared.<module>.<Class>`` after ``from infragram.nodes import infragram as shared``."""

    import importlib
    import pkgutil

    from infragram.nodes import infragram as shared

    classes: dict[str, str] = {}
    for info in pkgutil.iter_modules(shared.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{shared.__name__}.{info.name}")
        for name, value in vars(module).items():
            icon = getattr(value, "ICON", None)
            if (
                isinstance(value, type)
                and icon
                and not name.startswith("_")
                and value.__module__ == module.__name__
            ):
                classes[icon] = f"shared.{info.name}.{name}"
    return classes


def render_shared_components(inventory: dict) -> str:
    """The shipped table of shared components an agent picks from: every
    ``infragram:`` id with the class that draws it and its name, by category."""

    from infragram.catalog import load_default_category_registry

    classes = _shared_classes()
    labels = {
        category.id: category.label for category in load_default_category_registry().categories
    }
    by_category: dict[str, list[dict]] = defaultdict(list)
    for component in inventory["shared_primitives"]:
        by_category[component["category"]].append(component)
    example = classes.get("public-users", "shared.identity.PublicUsers")
    lines = [
        "# Shared components",
        "",
        "Generated by `python -m infragram inventory`; do not edit by hand.",
        "",
        f"The {len(inventory['shared_primitives'])} neutral components every library offers: clients and",
        "people, generic servers and databases, network and security appliances,",
        "common open-source and commercial products. A document names one as",
        "`infragram:<id>`; compose code draws it with its class, after",
        "`from infragram.nodes import infragram as shared`:",
        "",
        "```python",
        f'users = {example}("Users")',
        "```",
        "",
        "The Custom rows are the editor's own elements (a label, an annotation, a",
        "shape, a custom resource, a 3D render) and have no class. The glyph each",
        "component draws with is in [primitive-icons.md](primitive-icons.md).",
        "",
    ]
    for category_id in inventory["categories"]:
        components = by_category.get(category_id)
        if not components:
            continue
        lines += [
            f"## {labels.get(category_id, category_id)} ({len(components)})",
            "",
            "| id | class | name |",
            "|---|---|---|",
        ]
        for component in components:
            drawn_by = f"`{classes[component['id']]}`" if component["id"] in classes else "-"
            lines.append(f"| `{component['id']}` | {drawn_by} | {component['name']} |")
        lines.append("")
    return "\n".join(lines)


def render_docs_markdown(inventory: dict) -> str:
    """The docs page: the same inventory with a picture of every icon and frame."""

    lines = [
        "# Component inventory, with pictures",
        "",
        "Every icon and every frame Infragram ships, drawn from the same library",
        "payload the editor sidebar uses. Generated by",
        "`python -m infragram inventory --images`; `infragram verify:all` fails when",
        "this page is out of date or a picture is missing. Do not edit by hand.",
        "",
        _totals_line(inventory),
        "",
        "## Libraries at a glance",
        "",
        *_library_table(inventory),
        "",
        *TABLE_NOTE,
        "",
        "## Every frame tab",
        "",
        f"All {inventory['totals']['frames']} frame tab icons as the editor draws them, grouped by library.",
        "",
        f"![All {inventory['totals']['frames']} frame tabs](frames-tabs.png)",
        "",
        "## Shared primitives",
        "",
        f"{inventory['totals']['shared_primitives']} neutral components available in every library:"
        " clients, users, generic servers and databases, networking, security, storage, brand marks"
        " and annotation shapes.",
        "",
        "![Shared primitives](icons-shared.png)",
        "",
        "## Core frames",
        "",
        "Provider-neutral frames for generic pictures: "
        + ", ".join(f"{frame['name']} ({frame['kind']})" for frame in inventory["core_frames"])
        + ".",
        "",
        f"![Core frames](frames-{CORE_GROUP}.png)",
        "",
    ]
    for library in inventory["libraries"]:
        name = library["display_name"]
        stack = library["starter_stack"]["label"] if library["starter_stack"] else "none"
        icons = f"{library['icons']} components"
        lines += [
            f"## {name}",
            "",
            f"{library['kind']} · {library['coverage']} · {icons} · {len(library['frames'])} frames · starter stack: {stack}",
            "",
        ]
        breakdown = ", ".join(
            f"{category} {count}" for category, count in library["categories"].items()
        )
        lines += [
            f"Components by category: {breakdown}.",
            "",
            f"![{name} components](icons-{library['id']}.png)",
            "",
        ]
        if library["frames"]:
            lines += [
                "Frames: "
                + ", ".join(f"{frame['name']} ({frame['kind']})" for frame in library["frames"])
                + ".",
                "",
                f"![{name} frames](frames-{library['id']}.png)",
                "",
            ]
    lines += ["## Templates", "", *_templates_table(inventory), ""]
    return "\n".join(lines)


def serialize(inventory: dict) -> str:
    return json.dumps(inventory, indent=1, ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------
# Pictures
# --------------------------------------------------------------------------

SHEET_CSS = """
body{margin:0;background:#fff;font-family:'Segoe UI',system-ui,sans-serif;color:#161a20}
h1{font-size:28px;margin:24px 28px 4px}
p.sub{margin:0 28px 18px;color:#5f6875;font-size:15px}
h2{font-size:15px;letter-spacing:.06em;text-transform:uppercase;color:#5f6875;margin:22px 28px 8px;border-bottom:1px solid #e3e6ea;padding-bottom:6px}
.grid{display:grid;grid-template-columns:repeat(12,1fr);gap:10px 8px;padding:0 28px}
.tile{display:flex;flex-direction:column;align-items:center;text-align:center;padding:8px 4px;border:1px solid #eceff3;border-radius:6px;background:#fbfbfc}
.tile img{width:52px;height:52px;object-fit:contain;margin-bottom:6px}
.name{font-size:11.5px;line-height:1.25;font-weight:600;max-width:100%;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.id{font-family:Consolas,monospace;font-size:9.5px;color:#7a8390;margin-top:2px;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
"""


def _icon_sheet_html(title: str, components: list[dict], category_order: list[str]) -> str:
    by_category: dict[str, list[dict]] = defaultdict(list)
    for component in components:
        by_category[component["categoryId"]].append(component)
    sections = []
    for category in sorted(
        by_category, key=lambda k: category_order.index(k) if k in category_order else 99
    ):
        tiles = "".join(
            f'<div class="tile"><img src="{c["iconUri"]}" alt=""><div class="name">{H.escape(c["name"])}</div>'
            f'<div class="id">{H.escape(c["serviceId"])}</div></div>'
            for c in sorted(by_category[category], key=lambda c: c["name"].lower())
        )
        sections.append(
            f"<h2>{H.escape(category)} · {len(by_category[category])}</h2><div class='grid'>{tiles}</div>"
        )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><style>{SHEET_CSS}</style></head><body>"
        f"<h1>{H.escape(title)} · {len(components)} components</h1>"
        f"<p class='sub'>Every component of the {H.escape(title)} library as it appears in the editor sidebar, grouped by category.</p>"
        f"{''.join(sections)}<div style='height:24px'></div></body></html>"
    )


def _frames_project(group: str, provider: str, title: str, frames: list[dict]) -> dict:
    """A frames-only project in the editor's own export shape, three per row."""

    columns, origin, gap = 3, 100, 40
    children, x, y, row_height = [], origin, origin, 0
    for index, component in enumerate(frames):
        width, height = component["defaultSize"]["width"], component["defaultSize"]["height"]
        if index and index % columns == 0:
            x, y, row_height = origin, y + row_height + gap, 0
        children.append(
            {
                "id": component["serviceId"],
                "name": component["name"],
                "type": component["boundaryKind"],
                "attributes": {
                    "editor_x": x,
                    "editor_y": y,
                    "editor_width": width,
                    "editor_height": height,
                    "editor_frame_group": group,
                    "editor_boundary_style": component["boundaryStyle"],
                },
            }
        )
        x += 560
        row_height = max(row_height, height)
    return {
        "schema_version": 2,
        "kind": "single-cloud",
        "slug": f"frames-{group}",
        "title": title,
        "description": f"Every {title} frame at its default size.",
        "providers": [{"id": provider, "enabled": True}],
        "default_library": provider,
        "presentation": {"size": "fit"},
        "topology": {"id": "root", "name": title, "type": "group", "children": children},
    }


def generate_images(inventory: dict, providers, payload) -> list[Path]:
    """Draw the icon sheets, the frame sheets and the tab sheet into docs/inventory."""

    from PIL import Image, ImageDraw, ImageFont
    from playwright.sync_api import sync_playwright

    from infragram.exports import PNG_CONTENT_MARGIN, export_project
    from infragram.projects import CloudProject

    DOCS.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    category_order = list(inventory["categories"])
    components_by_provider: dict[str, list[dict]] = defaultdict(list)
    frames_by_group: dict[str, list[dict]] = defaultdict(list)
    for component in payload["components"]:
        if component.get("componentKind") == "boundary":
            frames_by_group[component.get("frameGroup") or CORE_GROUP].append(component)
        else:
            components_by_provider[component["provider"]].append(component)
    display = {provider.id: provider.display_name for provider in providers}
    display["infragram"] = "Shared primitives"
    display[CORE_GROUP] = "Core"

    with tempfile.TemporaryDirectory() as scratch:
        scratch_dir = Path(scratch)

        # Icon sheets first, in one browser session. The session must be closed
        # before the frame exports below, which open their own; the sync
        # Playwright API refuses to nest.
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()

            def screenshot_sheet(name: str, title: str, components: list[dict]) -> Path:
                html_path = scratch_dir / f"{name}.html"
                html_path.write_text(
                    _icon_sheet_html(title, components, category_order),
                    encoding="utf-8",
                    newline="\n",
                )
                page = browser.new_page(
                    viewport={"width": 1800, "height": 1000}, device_scale_factor=1.5
                )
                page.goto(html_path.resolve().as_uri())
                page.wait_for_load_state("networkidle")
                page.evaluate(
                    "Promise.all([...document.images].map(i => i.decode().catch(() => null)))"
                )
                output = DOCS / f"{name}.png"
                page.screenshot(path=str(output), full_page=True)
                page.close()
                image = Image.open(output).convert("RGB")
                image.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(
                    output, optimize=True
                )
                return output

            for provider in providers:
                if not components_by_provider.get(provider.id):
                    continue
                written.append(
                    screenshot_sheet(
                        f"icons-{provider.id}",
                        provider.display_name,
                        components_by_provider[provider.id],
                    )
                )
                print(
                    f"  icons-{provider.id}.png ({len(components_by_provider[provider.id])} components)"
                )
            written.append(
                screenshot_sheet(
                    "icons-shared", "Shared primitives", components_by_provider["infragram"]
                )
            )
            print(f"  icons-shared.png ({len(components_by_provider['infragram'])} components)")
            browser.close()

        # frame sheets, exported through the real export path at 4x, then the
        # tab of every frame cropped from those renders onto one sheet
        tiles: list[tuple[str, dict, Image.Image]] = []
        registered = {provider.id for provider in providers}
        groups = [CORE_GROUP] + [
            provider.id for provider in providers if frames_by_group.get(provider.id)
        ]
        for group in groups:
            frames = sorted(
                frames_by_group[group], key=lambda c: (c.get("hierarchyLevel", 0), c["name"])
            )
            # the shared frames are drawn under the on-premises library where it
            # is installed, else under the first library this edition has
            fallback = "onprem" if "onprem" in registered else min(registered)
            provider_id = group if group in registered else fallback
            project = CloudProject.model_validate(
                _frames_project(group, provider_id, display[group], frames)
            )
            result = export_project(
                project, scratch_dir / group, formats=("png",), scale=4, overwrite=True
            )
            # formats=("png",) asked for the PNG, so the export wrote one
            assert result.png is not None
            sheet = Image.open(result.png).convert("RGBA")
            # the crop origin is the first frame's corner minus the export margin
            columns, origin, gap = 3, 100, 40
            x, y, row_height = origin, origin, 0
            for index, component in enumerate(frames):
                height = component["defaultSize"]["height"]
                if index and index % columns == 0:
                    x, y, row_height = origin, y + row_height + gap, 0
                px = int((x - origin + PNG_CONTENT_MARGIN - 3) * 4)
                py = int((y - origin + PNG_CONTENT_MARGIN - 3) * 4)
                tiles.append(
                    (display[group], component, sheet.crop((px, py, px + 27 * 4, py + 27 * 4)))
                )
                x += 560
                row_height = max(row_height, height)
            output = DOCS / f"frames-{group}.png"
            sheet.resize((sheet.width // 2, sheet.height // 2), Image.Resampling.LANCZOS).save(
                output, optimize=True
            )
            written.append(output)
            print(f"  frames-{group}.png ({len(frames)} frames)")

        font = ImageFont.load_default(size=22)
        small = ImageFont.load_default(size=18)
        head = ImageFont.load_default(size=34)
        tile, cell_w, cell_h, per_row = 108, 300, 176, 8
        rows = -(-len(tiles) // per_row)
        out = Image.new("RGB", (per_row * cell_w + 40, 90 + rows * cell_h), (255, 255, 255))
        draw = ImageDraw.Draw(out)
        draw.text(
            (20, 22),
            f"All {len(tiles)} frame tab icons as exported, grouped by library",
            fill=(0, 0, 0),
            font=head,
        )
        for index, (group_name, component, crop) in enumerate(tiles):
            cx = 20 + (index % per_row) * cell_w
            cy = 90 + (index // per_row) * cell_h
            out.paste(Image.new("RGB", (tile, tile), (245, 245, 245)), (cx, cy))
            out.paste(crop, (cx, cy), crop)
            draw.rectangle((cx, cy, cx + tile - 1, cy + tile - 1), outline=(215, 215, 215))
            name = (
                component["name"] if len(component["name"]) <= 24 else component["name"][:23] + "…"
            )
            draw.text((cx, cy + tile + 6), name, fill=(0, 0, 0), font=font)
            draw.text(
                (cx, cy + tile + 34),
                f"{group_name} · {component['boundaryKind']}",
                fill=(90, 90, 90),
                font=small,
            )
        tabs = DOCS / "frames-tabs.png"
        out.save(tabs, optimize=True)
        written.append(tabs)
        print(f"  frames-tabs.png ({len(tiles)} tabs)")
    return written


# --------------------------------------------------------------------------
# Check
# --------------------------------------------------------------------------


def _display(path: Path) -> str:
    """Repo-relative when possible; a temporary path in tests is shown as is."""

    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def referenced_images(markdown: str) -> list[str]:
    return re.findall(r"!\[[^\]]*\]\(([^)]+\.png)\)", markdown)


def check(
    inventory: dict,
    json_path: Path = JSON_PATH,
    markdown_path: Path = MARKDOWN_PATH,
    docs_path: Path = DOCS_MARKDOWN_PATH,
    shared_path: Path = SHARED_PATH,
) -> list[str]:
    """Differences between the committed inventory and the one just built."""

    errors: list[str] = []
    if not json_path.exists():
        errors.append(f"{_display(json_path)} is missing")
    else:
        committed = json.loads(json_path.read_text(encoding="utf-8"))
        if committed != inventory:
            errors.append(f"{_display(json_path)} is out of date")
            old = {library["id"]: library for library in committed.get("libraries", [])}
            for library in inventory["libraries"]:
                before = old.get(library["id"])
                if before is None:
                    errors.append(
                        f"  new library {library['id']} ({library['icons']} icons, {len(library['frames'])} frames)"
                    )
                    continue
                if before.get("icons") != library["icons"] or len(before.get("frames", [])) != len(
                    library["frames"]
                ):
                    errors.append(
                        f"  {library['id']}: icons {before.get('icons')} -> {library['icons']}, "
                        f"frames {len(before.get('frames', []))} -> {len(library['frames'])}"
                    )
            for library_id in set(old) - {library["id"] for library in inventory["libraries"]}:
                errors.append(f"  library {library_id} disappeared")
            if committed.get("totals") != inventory["totals"]:
                errors.append(f"  totals {committed.get('totals')} -> {inventory['totals']}")
    if not markdown_path.exists():
        errors.append(f"{_display(markdown_path)} is missing")
    elif markdown_path.read_text(encoding="utf-8") != render_markdown(inventory):
        errors.append(f"{_display(markdown_path)} is out of date")
    if not shared_path.exists():
        errors.append(f"{_display(shared_path)} is missing")
    elif shared_path.read_text(encoding="utf-8") != render_shared_components(inventory):
        errors.append(f"{_display(shared_path)} is out of date")
    if not docs_path.exists():
        errors.append(f"{_display(docs_path)} is missing")
    else:
        expected = render_docs_markdown(inventory)
        if docs_path.read_text(encoding="utf-8") != expected:
            errors.append(f"{_display(docs_path)} is out of date")
        for image in referenced_images(expected):
            if not (docs_path.parent / image).exists():
                errors.append(
                    f"{_display(docs_path.parent / image)} is missing; run `python -m infragram inventory --images`"
                )
    return errors


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or check the component inventory.")
    parser.add_argument(
        "--check", action="store_true", help="verify the committed inventory is current"
    )
    parser.add_argument(
        "--images",
        action="store_true",
        help="also redraw the icon and frame sheets in docs/inventory",
    )
    options = parser.parse_args(argv)

    loaded = load_payload()
    inventory, problems = build_inventory(loaded)
    totals = inventory["totals"]
    summary = (
        f"{totals['libraries']} libraries, {totals['vendor_icons']} vendor icons, "
        f"{totals['shared_primitives']} shared primitives, {totals['frames']} frames, "
        f"{totals['starter_stacks']} starter stacks, {totals['templates']} templates"
    )
    if problems:
        for problem in problems[:20]:
            print(f"  {problem}", file=sys.stderr)
        gatelib.fail(f"{len(problems)} component(s) have unusable artwork")

    if options.check:
        errors = check(inventory)
        if errors:
            for error in errors:
                print(f"  {error}", file=sys.stderr)
            gatelib.fail(
                "inventory is stale; run `python -m infragram inventory` and commit the result"
            )
        gatelib.ok(f"inventory is current, pictures present, every icon decodes: {summary}")
        return 0

    write_generated_text(JSON_PATH, serialize(inventory))
    write_generated_text(MARKDOWN_PATH, render_markdown(inventory))
    write_generated_text(SHARED_PATH, render_shared_components(inventory))
    DOCS.mkdir(parents=True, exist_ok=True)
    write_generated_text(DOCS_MARKDOWN_PATH, render_docs_markdown(inventory))
    print(
        f"wrote {_display(JSON_PATH)}, {_display(MARKDOWN_PATH)}, {_display(SHARED_PATH)} and "
        f"{_display(DOCS_MARKDOWN_PATH)}: {summary}"
    )
    if options.images:
        providers, payload = loaded
        written = generate_images(inventory, providers, payload)
        print(f"drew {len(written)} sheets into {_display(DOCS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
