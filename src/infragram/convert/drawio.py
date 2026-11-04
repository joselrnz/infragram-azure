"""draw.io (diagrams.net) files: every page, every shape, every line.

A file is an ``<mxfile>`` of ``<diagram>`` pages, each an ``<mxGraphModel>``
written inline or deflated, base64'd and URL-encoded; a bare
``<mxGraphModel>``; a ``.drawio.svg`` carrying the file in its ``content``
attribute; or a ``.drawio.png`` carrying it in a ``tEXt``/``zTXt``/``iTXt``
chunk named ``mxfile``. All of them read the same.

What a cell is comes from its style: a stencil (``mxgraph.aws4.lambda_function``,
``shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.rds``,
``shape=mxgraph.kubernetes.icon;prIcon=pod``), an icon file
(``img/lib/azure2/compute/Function_Apps.svg``), or a shape family (a
cylinder is a database, ``umlActor`` a person). Containers are the cells
the file nests others in, and any shape drawn wholly around others
(:mod:`.nesting`). Text cells are annotations; a text cell on a line is
its label.
"""

from __future__ import annotations

import base64
import re
import struct
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

from . import xmlsafe
from .model import Bounds, Hint, Link, Shape, Sketch, split_label, words
from .nesting import nest_by_bounds, snap

__all__ = ["DrawioError", "read_drawio", "read_drawio_text"]


class DrawioError(ValueError):
    """The file holds no draw.io diagram this reader can open."""


#: ``mxgraph.<library>`` -> the library it draws in.
_STENCIL_PROVIDERS = {
    "aws4": "aws",
    "aws3": "aws",
    "aws3d": "aws",
    "aws2": "aws",
    "aws": "aws",
    "azure": "azure",
    "azure2": "azure",
    "mscae": "azure",
    "gcp2": "gcp",
    "gcp": "gcp",
    "gcpicons": "gcp",
    "kubernetes": "kubernetes",
    "kubernetes2": "kubernetes",
    "ibm": "ibm",
    "ibm_cloud": "ibm",
    "alibaba_cloud": "alibaba",
    "openstack": "openstack",
    "oci": "oracle",
    "oracle": "oracle",
    "digitalocean": "digitalocean",
    "cloudflare": "cloudflare",
    "vmware": "vmware",
    "proxmox": "proxmox",
    "hetzner": "hetzner",
}
#: ``img/lib/<folder>/`` -> the library its icons draw in.
_IMAGE_PROVIDERS = {
    "azure2": "azure",
    "mscae": "azure",
    "azure": "azure",
    "active_directory": "azure",
    "aws4": "aws",
    "aws": "aws",
    "gcp2": "gcp",
    "gcp": "gcp",
    "ibm": "ibm",
    "kubernetes": "kubernetes",
    "oracle": "oracle",
    "openstack": "openstack",
}
#: Stencil suffixes that say what a shape is, not which product.
_DATABASE = re.compile(r"cylinder|datastore|database|\bdb\b|stored_data", re.IGNORECASE)
_ACTOR = re.compile(r"umlactor|\bactor\b|person|\buser\b|users", re.IGNORECASE)
_FILE = re.compile(r"document|\bnote\b|\bfile\b|\bcard\b", re.IGNORECASE)
_GROUP_NUMBER = re.compile(r"\d+$")


def _style(text: str | None) -> dict[str, str]:
    """``rounded=0;whiteSpace=wrap;ellipse`` -> ``{"rounded": "0", ..., "ellipse": ""}``."""
    out: dict[str, str] = {}
    for part in (text or "").split(";"):
        part = part.strip()
        if not part:
            continue
        key, sep, value = part.partition("=")
        out[key.strip()] = value.strip() if sep else ""
    return out


def _png_text(data: bytes) -> str | None:
    """The ``mxfile`` a draw.io PNG carries, if any."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos = 8
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        body = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if kind == b"tEXt":
            key, _, value = body.partition(b"\0")
            if key in (b"mxfile", b"mxGraphModel"):
                return urllib.parse.unquote(value.decode("latin-1"))
        elif kind == b"zTXt":
            key, _, rest = body.partition(b"\0")
            if key in (b"mxfile", b"mxGraphModel"):
                return urllib.parse.unquote(zlib.decompress(rest[1:]).decode("latin-1"))
        elif kind == b"iTXt":
            key, _, rest = body.partition(b"\0")
            if key in (b"mxfile", b"mxGraphModel"):
                compressed = rest[0] == 1
                rest = rest[2:]
                _lang, _, rest = rest.partition(b"\0")
                _translated, _, text = rest.partition(b"\0")
                raw = zlib.decompress(text) if compressed else text
                return urllib.parse.unquote(raw.decode("utf-8"))
        elif kind == b"IEND":
            break
    return None


def _inflate(text: str) -> ET.Element:
    """A page written compressed: deflate, base64, URL encoding."""
    text = text.strip()
    if text.startswith("<"):
        return xmlsafe.parse(text)
    try:
        raw = base64.b64decode(text)
    except ValueError as error:
        raise DrawioError(f"a page is neither XML nor compressed XML ({error})") from error
    for wbits in (-15, 15):
        try:
            inflated = zlib.decompress(raw, wbits).decode("utf-8")
            break
        except (zlib.error, UnicodeDecodeError):
            continue
    else:
        inflated = raw.decode("utf-8", errors="replace")
    return xmlsafe.parse(urllib.parse.unquote(inflated))


def _pages(text: str) -> list[tuple[str | None, ET.Element]]:
    try:
        root = xmlsafe.parse(text)
    except ET.ParseError as error:
        raise DrawioError(f"not a draw.io file: {error}") from error
    if root.tag.endswith("svg"):
        content = root.get("content")
        if not content:
            raise DrawioError(
                "an SVG without a draw.io diagram in it (export it with "
                "'Include a copy of my diagram')"
            )
        return _pages(content)
    if root.tag == "mxGraphModel":
        return [(None, root)]
    if root.tag != "mxfile":
        raise DrawioError(f"not a draw.io file: the document is <{root.tag}>")
    pages: list[tuple[str | None, ET.Element]] = []
    for diagram in root.findall("diagram"):
        model = diagram.find("mxGraphModel")
        if model is None:
            model = _inflate(diagram.text or "")
        pages.append((diagram.get("name"), model))
    if not pages:
        raise DrawioError("the file holds no pages")
    return pages


def _image_hints(image: str) -> list[Hint]:
    if not image or image.startswith("data:"):
        return []
    match = re.search(r"img/lib/([^/]+)/(?:.*/)?([^/]+?)\.(?:svg|png)", image)
    if not match:
        return []
    folder, stem = match.groups()
    stem = re.sub(r"^\d+-icon-service-", "", stem)
    stem = re.sub(r"^\d+[-_]?", "", stem)
    return [Hint(provider=_IMAGE_PROVIDERS.get(folder), phrase=words(stem), raw=image)]


def _stencil(value: str) -> tuple[str | None, str] | None:
    """``mxgraph.aws4.lambda_function`` -> ``("aws", "lambda_function")``."""
    match = re.match(r"mxgraph\.([a-z0-9_]+)\.(.+)$", value)
    if not match:
        return None
    library, name = match.groups()
    return _STENCIL_PROVIDERS.get(library), name


#: Stencil names whose words are not the product's: (library, words) -> phrase.
_STENCIL_WORDS = {
    ("aws", "instance"): "ec2 instance",
    ("aws", "instances"): "ec2 instances",
    ("aws", "instance with cloudwatch"): "ec2 instance",
    ("aws", "generic database"): "database",
    ("aws", "bucket with objects"): "bucket",
    ("aws", "internet"): "internet",
}


def _phrase(provider: str | None, name: str) -> str:
    """A stencil's name as the product's words: ``instance2`` -> ``ec2 instance``."""
    spoken = " ".join(
        w
        for w in (re.sub(r"(?<=[a-z]{4})\d$", "", w) for w in words(name).split())
        if w and w not in {"alt", "light", "dark", "bg", "icon"}
    )
    return _STENCIL_WORDS.get((provider or "", spoken), spoken)


def _kind_and_hints(style: dict[str, str]) -> tuple[str, list[Hint], bool]:
    """What a vertex is: its shape family, what it names, whether it is a frame."""
    shape = style.get("shape", "")
    hints: list[Hint] = []
    frame = False
    # an icon named inside a generic AWS/GCP/Kubernetes wrapper shape
    for key in ("resIcon", "prIcon", "grIcon"):
        if style.get(key):
            found = _stencil(style[key])
            provider, name = found if found else (None, style[key])
            if provider is None and shape:
                wrapper = _stencil(shape)
                provider = wrapper[0] if wrapper else None
            is_group = key == "grIcon"
            if is_group:
                name = _GROUP_NUMBER.sub("", re.sub(r"^group_", "", name))
            hints.append(
                Hint(
                    provider=provider,
                    phrase=_phrase(provider, name),
                    frame=is_group,
                    raw=style[key],
                )
            )
            frame = frame or is_group
    if shape.startswith("mxgraph.") and not hints:
        found = _stencil(shape)
        if found:
            provider, name = found
            if name.startswith("group") or shape.endswith(".group"):
                frame = True
            elif name not in {"icon", "icon2", "resourceIcon", "productIcon", "hexIcon"}:
                hints.append(
                    Hint(
                        provider=provider, phrase=_phrase(provider, name.split(".")[-1]), raw=shape
                    )
                )
    hints += _image_hints(style.get("image", ""))
    family = shape or next(
        (
            k
            for k in (
                "ellipse",
                "rhombus",
                "hexagon",
                "cloud",
                "text",
                "image",
                "swimlane",
                "triangle",
            )
            if k in style
        ),
        "",
    )
    if "text" in style or (
        shape == ""
        and style.get("strokeColor") == "none"
        and style.get("fillColor", "none") == "none"
        and "image" not in style
    ):
        kind = "text"
    elif _DATABASE.search(family):
        kind = "database"
    elif _ACTOR.search(family):
        kind = "actor"
    elif "cloud" in family and not hints:
        kind = "cloud"
    elif _FILE.search(family):
        kind = "file"
    elif "queue" in family:
        kind = "queue"
    elif family in ("ellipse", "doubleEllipse"):
        kind = "ellipse"
    elif family == "rhombus":
        kind = "diamond"
    elif family == "hexagon":
        kind = "hexagon"
    elif "image" in style or family == "image":
        kind = "image"
    else:
        kind = "box"
    if kind == "box" and family.startswith("mxgraph.") and not hints and not frame:
        # a generic stencil (mxgraph.networks.server) names a kind of thing
        hints.append(Hint(phrase=words(family.split(".")[-1]), raw=family))
    return kind, hints, frame


def _label(cell: ET.Element, holder: ET.Element | None) -> tuple[str, dict[str, str]]:
    """A cell's label and the data a wrapping ``<object>`` gives it."""
    if holder is None:
        return cell.get("value", ""), {}
    data = {k: v for k, v in holder.attrib.items() if k not in {"id", "label", "placeholders"}}
    label = holder.get("label", "")
    if "c4Name" in data:
        label = data["c4Name"]
    if holder.get("placeholders") == "1":
        label = re.sub(r"%([\w.-]+)%", lambda m: data.get(m.group(1), m.group(0)), label)
    return label, data


def _page(model: ET.Element, *, title: str, origin: str, page: str | None) -> Sketch:
    root = model.find("root")
    if root is None:
        raise DrawioError("a page holds no <root>")
    cells: list[tuple[ET.Element, ET.Element | None]] = []
    for item in root:
        if item.tag == "mxCell":
            cells.append((item, None))
        else:  # <object>/<UserObject> wrapping its cell
            inner = item.find("mxCell")
            if inner is not None:
                inner.set("id", item.get("id", inner.get("id", "")))
                cells.append((inner, item))
    by_id = {cell.get("id", ""): (cell, holder) for cell, holder in cells}
    # The export's editable legend is annotation, not infrastructure. Keep
    # its labels as notes, including when draw.io renames its child cells.
    # The reserved id also recognises exports made before the role marker.
    legend_roots = {
        cell.get("id", "")
        for cell, holder in cells
        if cell.get("id") == "infragram:legend"
        or cell.get("infragram_role") == "legend"
        or (holder is not None and holder.get("infragram_role") == "legend")
    }
    caption_roots = {
        cell.get("id", "")
        for cell, holder in cells
        if cell.get("id") == "infragram:title"
        or cell.get("infragram_role") == "caption"
        or (holder is not None and holder.get("infragram_role") == "caption")
    }
    annotations = legend_roots | caption_roots
    while True:
        descendants = {
            cell.get("id", "") for cell, _ in cells if cell.get("parent") in annotations
        } - annotations
        if not descendants:
            break
        annotations.update(descendants)
    top = {cell.get("id") for cell, _ in cells if not cell.get("parent")}
    layers = {cell.get("id") for cell, _ in cells if cell.get("parent") in top} - {
        cell.get("id") for cell, _ in cells if cell.get("vertex") == "1" or cell.get("edge") == "1"
    }
    where = f"page {page!r}, " if page else ""
    sketch = Sketch(title=title, origin=origin, format="drawio")
    absolute: dict[str, tuple[float, float]] = {}

    def offset(cell_id: str | None) -> tuple[float, float]:
        if not cell_id or cell_id in top or cell_id in layers or cell_id not in by_id:
            return 0.0, 0.0
        if cell_id in absolute:
            return absolute[cell_id]
        cell, _ = by_id[cell_id]
        geometry = cell.find("mxGeometry")
        px, py = offset(cell.get("parent"))
        x = float(geometry.get("x", 0)) if geometry is not None else 0.0
        y = float(geometry.get("y", 0)) if geometry is not None else 0.0
        absolute[cell_id] = (px + x, py + y)
        return absolute[cell_id]

    edge_labels: dict[str, list[str]] = {}
    edges: list[tuple[ET.Element, dict[str, str], str]] = []
    for cell, holder in cells:
        cell_id = cell.get("id", "")
        if cell_id in annotations:
            label, _ = _label(cell, holder)
            text = " ".join(part for part in split_label(label) if part)
            if text and cell_id not in legend_roots and cell.get("visible") != "0":
                prefix = "Title" if cell_id in caption_roots else "Legend"
                sketch.notes.append(f"{prefix}: {text}")
            continue
        if cell_id in top or cell_id in layers or cell.get("visible") == "0":
            continue
        style = _style(cell.get("style"))
        label, data = _label(cell, holder)
        if cell.get("edge") == "1":
            edges.append((cell, style, label))
            continue
        if cell.get("vertex") != "1":
            continue
        parent = cell.get("parent")
        if parent in by_id and by_id[parent][0].get("edge") == "1":
            lines = split_label(label)
            if lines[0]:
                edge_labels.setdefault(parent, []).append(" ".join(t for t in lines if t))
            continue
        kind, hints, frame = _kind_and_hints(style)
        caption, detail = split_label(label)
        if "c4Name" in data:
            caption = data["c4Name"]
            detail = data.get("c4Technology") or data.get("c4Type", "")
            c4type = data.get("c4Type", "").lower()
            if "person" in c4type:
                kind = "actor"
            elif "database" in c4type or "db" in c4type.split():
                kind = "database"
            if data.get("c4Technology"):
                hints.append(Hint(phrase=data["c4Technology"], raw="c4Technology"))
            frame = frame or "boundary" in c4type
        geometry = cell.find("mxGeometry")
        box = None
        if geometry is not None and geometry.get("relative") != "1":
            x, y = offset(cell_id)
            box = Bounds(
                x=x,
                y=y,
                width=float(geometry.get("width", 0)),
                height=float(geometry.get("height", 0)),
            )
        container = (
            frame or "swimlane" in style or style.get("container") == "1" or "group" in style
        )
        rows = [
            (k, v)
            for k, v in data.items()
            if v and not k.startswith(("c4", "infragram_")) and k != "tooltip"
        ]
        raw = style.get("shape") or next(iter(style), "")
        sketch.shapes.append(
            Shape(
                key=cell_id,
                label=caption,
                detail=detail,
                parent=parent if parent in by_id and parent not in top | layers else None,
                container=container,
                kind=kind,
                hints=hints,
                rows=rows,
                box=box,
                component=data.get("infragram_component") or None,
                source=f"cell {cell_id}" + (f" ({raw})" if raw else ""),
                flow="row"
                if style.get("childLayout") == "stackLayout" and style.get("horizontalStack") == "1"
                else None,
            )
        )
    nest_by_bounds(sketch.shapes)
    known = {shape.key for shape in sketch.shapes}
    for cell, style, label in edges:
        cell_id = cell.get("id", "")
        ends: list[str | None] = [cell.get("source"), cell.get("target")]
        geometry = cell.find("mxGeometry")
        for index, (joined, point_name) in enumerate(
            zip(ends, ("sourcePoint", "targetPoint"), strict=True)
        ):
            if joined in known or geometry is None:
                continue
            point = geometry.find(f"mxPoint[@as='{point_name}']")
            if point is not None:
                ox, oy = offset(cell.get("parent"))
                ends[index] = snap(
                    sketch.shapes, ox + float(point.get("x", 0)), oy + float(point.get("y", 0))
                )
        source, target = ends
        text = " ".join(t for t in split_label(label) if t)
        text = " ".join([text, *edge_labels.get(cell_id, [])]).strip()
        if source not in known or target not in known:
            sketch.notes.append(
                f"the line {where}cell {cell_id}"
                f"{f' ({text})' if text else ''} does not join two shapes"
            )
            continue
        start = style.get("startArrow", "none") not in ("none", "")
        end = style.get("endArrow", "classic") not in ("none", "")
        if start and not end:
            source, target = target, source
        sketch.links.append(
            Link(
                source=source,
                target=target,
                label=text,
                dashed=style.get("dashed") == "1",
                direction="both" if start and end else "forward" if start or end else "none",
                origin=f"{where}cell {cell_id}",
            )
        )
    return sketch


def read_drawio_text(text: str, *, name: str) -> list[Sketch]:
    """Every page of a draw.io document given as text."""
    pages = _pages(text)
    sketches = []
    for number, (page, model) in enumerate(pages, start=1):
        default = page is None or re.fullmatch(r"Page-\d+", page or "") is not None
        title = name if default and len(pages) == 1 else (page or f"{name} page {number}")
        origin = f"{name}" + (f", page {page!r}" if page and len(pages) > 1 else "")
        sketches.append(
            _page(model, title=title, origin=origin, page=page if len(pages) > 1 else None)
        )
    return sketches


def read_drawio(path: Path) -> list[Sketch]:
    """Every page of a ``.drawio``, ``.xml``, ``.drawio.svg`` or ``.drawio.png`` file."""
    data = path.read_bytes()
    if data.startswith(b"\x89PNG"):
        text = _png_text(data)
        if text is None:
            raise DrawioError(
                f"{path.name} is a PNG without a draw.io diagram in it (export it "
                "with 'Include a copy of my diagram')"
            )
    else:
        text = data.decode("utf-8-sig")
    name = path.name
    for suffix in (
        ".drawio.png",
        ".drawio.svg",
        ".drawio.xml",
        ".drawio",
        ".xml",
        ".svg",
        ".png",
        ".dio",
    ):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    return read_drawio_text(text, name=name)
