"""Visio drawings (``.vsdx``), and Lucidchart's diagrams exported as Visio.

A ``.vsdx`` is a zip of XML: ``visio/pages/pages.xml`` lists the pages,
each page lists its shapes with their cells (``PinX``, ``Width``,
``BeginX`` ...) and text, and ``<Connects>`` says which shape each
connector's begin and end are glued to. A shape made from a stencil master
names it (``Amazon EC2``, ``Azure SQL Database``, ``Database``), which is
what the shape is; a value the shape leaves out comes from its master. A
Visio container is a frame; so is any shape drawn wholly around others.
Background pages are left out.
"""

from __future__ import annotations

import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from . import xmlsafe
from .model import Bounds, Hint, Link, Shape, Sketch, split_label, words
from .nesting import nest_by_bounds, snap

__all__ = ["VisioError", "read_visio"]

_V = "{http://schemas.microsoft.com/office/visio/2012/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class VisioError(ValueError):
    """The file is not a Visio drawing this reader can open."""


_PROVIDERS = (
    ("amazon", "aws"),
    ("aws", "aws"),
    ("azure", "azure"),
    ("microsoft", "azure"),
    ("google", "gcp"),
    ("gcp", "gcp"),
    ("kubernetes", "kubernetes"),
    ("k8s", "kubernetes"),
)
_FILLER = {"amazon", "aws", "azure", "microsoft", "google", "gcp", "icon", "shape", "stencil"}


def _rels(archive: zipfile.ZipFile, part: str) -> dict[str, str]:
    folder, name = posixpath.split(part)
    path = posixpath.join(folder, "_rels", f"{name}.rels")
    if path not in archive.namelist():
        return {}
    root = xmlsafe.parse(archive.read(path))
    return {
        rel.get("Id", ""): posixpath.normpath(posixpath.join(folder, rel.get("Target", "")))
        for rel in root.iter(f"{_PKG}Relationship")
    }


def _cells(shape: ET.Element) -> dict[str, str]:
    out = {cell.get("N", ""): cell.get("V", "") for cell in shape.findall(f"{_V}Cell")}
    for section in shape.findall(f"{_V}Section"):
        if section.get("N") == "User":
            for row in section.findall(f"{_V}Row"):
                value = row.find(f"{_V}Cell[@N='Value']")
                if value is not None:
                    out[f"User.{row.get('N')}"] = value.get("V", "")
    return out


def _text(shape: ET.Element) -> str:
    text = shape.find(f"{_V}Text")
    return "".join(text.itertext()) if text is not None else ""


class _Masters:
    def __init__(self, archive: zipfile.ZipFile) -> None:
        self.names: dict[str, str] = {}
        self.shapes: dict[str, ET.Element] = {}
        part = "visio/masters/masters.xml"
        if part not in archive.namelist():
            return
        rels = _rels(archive, part)
        for master in xmlsafe.parse(archive.read(part)).iter(f"{_V}Master"):
            key = master.get("ID", "")
            self.names[key] = master.get("NameU") or master.get("Name") or ""
            rel = master.find(f"{_V}Rel")
            target = rels.get(rel.get(f"{_R}id", "")) if rel is not None else None
            if target and target in archive.namelist():
                top = xmlsafe.parse(archive.read(target)).find(f".//{_V}Shape")
                if top is not None:
                    self.shapes[key] = top


def _float(cells: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(cells.get(key, default))
    except ValueError:
        return default


def _hints_and_kind(name: str) -> tuple[str, list[Hint]]:
    lowered = name.lower()
    provider = next(
        (library for word, library in _PROVIDERS if re.search(rf"\b{word}\b", lowered)), None
    )
    phrase = " ".join(w for w in words(name).split() if w not in _FILLER)
    if re.search(r"database|cylinder|\bdb\b", lowered):
        kind = "database"
    elif re.search(r"\buser|person|actor|people", lowered):
        kind = "actor"
    elif re.search(r"\bcloud\b", lowered) and not provider:
        kind = "cloud"
    elif re.search(r"document|\bfile\b", lowered):
        kind = "file"
    elif re.search(r"\btext\b|annotation|callout|title", lowered):
        kind = "text"
    elif re.search(r"ellipse|circle", lowered):
        kind = "ellipse"
    elif re.search(r"diamond|decision", lowered):
        kind = "diamond"
    else:
        kind = "box"
    generic = phrase in {"rectangle", "square", "rounded rectangle", "process", "box", "sheet", ""}
    return kind, [] if generic or kind == "text" else [
        Hint(provider=provider, phrase=phrase, raw=name)
    ]


def _page(
    archive: zipfile.ZipFile, part: str, masters: _Masters, *, title: str, origin: str, where: str
) -> Sketch:
    root = xmlsafe.parse(archive.read(part))
    sketch = Sketch(title=title, origin=origin, format="visio")
    connectors: dict[str, tuple[ET.Element, dict[str, str], str]] = {}
    shapes_node = root.find(f"{_V}Shapes")
    for element in shapes_node if shapes_node is not None else []:
        if element.tag != f"{_V}Shape":
            continue
        key = element.get("ID", "")
        master = element.get("Master", "")
        inherited = masters.shapes.get(master)
        cells = {**(_cells(inherited) if inherited is not None else {}), **_cells(element)}
        name = masters.names.get(master) or re.sub(
            r"\.\d+$", "", element.get("NameU") or element.get("Name") or ""
        )
        label = _text(element) or (_text(inherited) if inherited is not None else "")
        if element.get("Type") == "Group" and not label.strip():
            label = next(
                (t for t in (_text(s) for s in element.iter(f"{_V}Shape")) if t.strip()), ""
            )
        if "BeginX" in cells and "EndX" in cells or "connector" in name.lower():
            connectors[key] = (element, cells, label)
            continue
        kind, hints = _hints_and_kind(name)
        width, height = _float(cells, "Width"), _float(cells, "Height")
        pin_x, pin_y = _float(cells, "PinX"), _float(cells, "PinY")
        box = Bounds(
            x=pin_x - _float(cells, "LocPinX", width / 2),
            y=pin_y - _float(cells, "LocPinY", height / 2),
            width=width,
            height=height,
        )
        caption, detail = split_label(label)
        container = cells.get("User.msvStructureType", "").strip('"').lower() == "container"
        if not caption and not hints and not container and kind in ("box", "text"):
            continue  # an unlabelled rectangle or empty text: decoration
        sketch.shapes.append(
            Shape(
                key=key,
                label=caption,
                detail=detail,
                kind=kind,
                hints=hints,
                box=box,
                container=container,
                rows=[("Visio shape", name)] if name else [],
                source=f"{where}shape {key}" + (f" ({name})" if name else ""),
            )
        )
    nest_by_bounds(sketch.shapes, slack=0.02)  # Visio measures in inches
    ends: dict[str, dict[str, str]] = {}
    connects = root.find(f"{_V}Connects")
    for connect in connects if connects is not None else []:
        cell = connect.get("FromCell", "")
        if cell in ("BeginX", "EndX"):
            ends.setdefault(connect.get("FromSheet", ""), {})[cell] = connect.get("ToSheet", "")
    known = {shape.key for shape in sketch.shapes}
    for key, (_element, cells, label) in connectors.items():
        glued = ends.get(key, {})
        source, target = glued.get("BeginX"), glued.get("EndX")
        if source not in known and "BeginX" in cells:
            source = snap(
                sketch.shapes, _float(cells, "BeginX"), _float(cells, "BeginY"), slack=0.1
            )
        if target not in known and "EndX" in cells:
            target = snap(sketch.shapes, _float(cells, "EndX"), _float(cells, "EndY"), slack=0.1)
        text = " ".join(t for t in split_label(label) if t)
        if source not in known or target not in known or source == target:
            sketch.notes.append(
                f"the connector {where}shape {key}{f' ({text})' if text else ''} "
                "does not join two shapes"
            )
            continue
        start = cells.get("BeginArrow", "0") not in ("0", "")
        end = cells.get("EndArrow", "1") not in ("0", "")
        if start and not end:
            source, target = target, source
        pattern = cells.get("LinePattern", "1")
        sketch.links.append(
            Link(
                source=source,
                target=target,
                label=text,
                dashed=pattern not in ("0", "1", ""),
                direction="both" if start and end else "forward" if start or end else "none",
                origin=f"{where}shape {key}",
            )
        )
    return sketch


def read_visio(path: Path) -> list[Sketch]:
    """Every foreground page of a ``.vsdx``."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        raise VisioError(f"{path.name} is not a .vsdx (a zip of Visio XML): {error}") from error
    with archive:
        index = "visio/pages/pages.xml"
        if index not in archive.namelist():
            raise VisioError(
                f"{path.name} holds no Visio pages (an older binary .vsd? save it as .vsdx)"
            )
        masters = _Masters(archive)
        rels = _rels(archive, index)
        pages = [
            page
            for page in xmlsafe.parse(archive.read(index)).iter(f"{_V}Page")
            if page.get("Background") != "1"
        ]
        stem = re.sub(r"\.vsdx$", "", path.name, flags=re.IGNORECASE)
        sketches = []
        for page in pages:
            rel = page.find(f"{_V}Rel")
            part = rels.get(rel.get(f"{_R}id", "")) if rel is not None else None
            if not part or part not in archive.namelist():
                continue
            name = page.get("NameU") or page.get("Name") or ""
            many = len(pages) > 1
            default = re.fullmatch(r"Page-\d+", name) is not None
            title = name if many or not default else stem
            origin = f"{path.name}" + (f", page {name!r}" if many else "")
            sketches.append(
                _page(
                    archive,
                    part,
                    masters,
                    title=title or stem,
                    origin=origin,
                    where=f"page {name!r}, " if many else "",
                )
            )
    if not sketches:
        raise VisioError(f"{path.name} holds no foreground page")
    return sketches
