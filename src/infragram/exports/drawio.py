"""A diagram as a draw.io file (``.drawio``): open it in draw.io, Confluence,
VS Code or anywhere diagrams.net runs, and keep editing there.

The file is drawn from the laid-out scene the static picture draws, in the
icon look draw.io diagrams read in: every position, every frame and every
wire's bends are Infragram's, so the drawing opens as it was exported rather
than re-laid-out by draw.io.

* A frame is a draw.io container (``container=1``) in the frame's own colour,
  dash and tint, holding what it holds; a child's geometry is relative to it.
* A component is draw.io's own stencil where one is known to match
  (``assets/catalog/drawio-stencils.json``, built by
  ``scripts/build/drawio-stencils.py``: AWS, Azure, Kubernetes), which keeps
  the file small, restyles in draw.io and survives its Visio export; anything
  else is Infragram's artwork, embedded. ``icons="embedded"`` embeds all of
  them, for the exact look.
* A wire's parent is the innermost frame holding both ends; its bends are
  written as its points and its ends pinned where Infragram seated them, so
  draw.io does not route it again.
* Every element is an ``<object>`` carrying ``infragram_id`` and
  ``infragram_component``, so the file reads back into Infragram exactly
  (``import:drawio``).
"""

from __future__ import annotations

import base64
import json
import re
from functools import cache
from html import escape as html_escape
from pathlib import Path
from xml.sax.saxutils import quoteattr

from ..builders import metrics
from ..paths import skill_assets
from ..projects import CloudProject
from ..themes.colour import hex_rgb

__all__ = ["ICONS", "render_project_drawio"]

#: How components draw: draw.io's stencil where one matches, else the artwork.
ICONS = ("native", "embedded")


@cache
def _stencils() -> dict[str, dict]:
    path = skill_assets() / "catalog" / "drawio-stencils.json"
    return json.loads(path.read_text(encoding="utf-8"))["components"]


def _polyline(d: str) -> list[tuple[float, float]]:
    """The corners an SVG path of M/L/H/V/Q commands visits, Q's control
    points included (they are the corners a rounded join bends around)."""
    points: list[tuple[float, float]] = []
    x = y = 0.0
    for match in re.finditer(r"([MLHVQ])([^MLHVQ]*)", d):
        command, numbers = (
            match.group(1),
            [float(n) for n in re.findall(r"-?[\d.]+", match.group(2))],
        )
        if command == "H":
            x = numbers[-1]
        elif command == "V":
            y = numbers[-1]
        elif command == "Q":
            for i in range(0, len(numbers) - 1, 2):
                points.append((numbers[i], numbers[i + 1]))
            x, y = numbers[-2], numbers[-1]
        else:
            x, y = numbers[0], numbers[1]
        if not points or points[-1] != (x, y):
            points.append((x, y))
    # drop points on a straight run: draw.io needs only the turns
    out: list[tuple[float, float]] = []
    for point in points:
        if len(out) >= 2 and (
            (out[-2][0] == out[-1][0] == point[0]) or (out[-2][1] == out[-1][1] == point[1])
        ):
            out[-1] = point
        else:
            out.append(point)
    return out


def _tint(hex_colour: str, alpha: float) -> str:
    """The colour laid over white at *alpha*: draw.io fills are opaque."""
    rgb = hex_rgb(hex_colour)
    if rgb is None:
        # the picture's own renderer refuses the same fill (builders/ink.py rgba)
        raise ValueError(f"a frame fill is a hex colour, #rgb or #rrggbb; got {hex_colour!r}")
    return "#" + "".join(f"{round(255 - (255 - c) * alpha):02x}" for c in rgb)


def _artwork(icon) -> str | None:
    if icon is None:
        return None
    markup = (
        icon.markup
        if getattr(icon, "markup", None) is not None
        else Path(icon.path).read_text(encoding="utf-8")
    )
    # An SVG inside a page needs no namespace; one loaded as an image does,
    # or draw.io shows a broken picture.
    opening = re.search(r"<svg\b[^>]*>", markup)
    if opening and "xmlns=" not in opening.group(0):
        markup = (
            markup[: opening.start()]
            + '<svg xmlns="http://www.w3.org/2000/svg"'
            + markup[opening.start() + 4 :]
        )
    return base64.b64encode(markup.encode("utf-8")).decode("ascii")


def _component_key(element) -> str:
    """``aws:ec2``: the library and service an element is drawn as."""
    component = getattr(element, "component", None)
    if component is None:
        return ""
    return f"{component.provider}:{component.service_id}"


#: A panel's shape, as draw.io names it (builders/panels.py).
_PANEL_SHAPES = {
    "rect": "rounded=1;arcSize=4;",
    "ellipse": "ellipse;",
    "hexagon": "shape=hexagon;perimeter=hexagonPerimeter2;size=0.1;",
    "note": "shape=note;size=10;",
}


def _label(name: str, detail: str) -> str:
    """The component's name and detail, as draw.io's HTML label."""
    text = f"<b>{html_escape(name)}</b>"
    return text + (
        f'<br><font style="font-size:10px" color="#5f6b7a">{html_escape(detail)}</font>'
        if detail
        else ""
    )


def render_project_drawio(project: CloudProject, *, icons: str = "native") -> str:
    """The project as an uncompressed ``.drawio`` file (mxfile XML)."""
    import importlib

    R = importlib.import_module("infragram.builders.render")
    from ..builders.scene import Cluster, glyph_square
    from .render import _scene_for, look_variant

    if icons not in ICONS:
        raise ValueError(f"icons is one of {', '.join(ICONS)}, not {icons!r}")
    project = look_variant(project, "icon")
    scene = _scene_for(project)
    # the same preparation the static picture's render makes, so each wire
    # is drawn from the route and seat the picture draws
    R._ROUTE_CACHE.clear()
    R._CAPTION_CACHE.clear()
    R._hold_captions(scene)
    index = project.topology.index()
    stencils = _stencils() if icons == "native" else {}
    style = scene.style
    cells: list[str] = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    origin: dict[str, tuple[float, float]] = {"1": (0.0, 0.0)}
    parent_of: dict[int, str] = {}  # scene node or cluster -> its draw.io parent id
    chain: dict[str, list[str]] = {"1": ["1"]}  # container id -> its ancestors, itself last
    boxes: dict[int, tuple[float, float, float, float]] = {}  # node -> glyph box, absolute
    ids: dict[int, str] = {}
    used: set[str] = set()

    def cell_id(ref: str, fallback: str) -> str:
        base = re.sub(r"[^A-Za-z0-9_.-]", "-", ref or fallback) or fallback
        candidate, n = base, 2
        while candidate in used or candidate in ("0", "1"):
            candidate, n = f"{base}-{n}", n + 1
        used.add(candidate)
        return candidate

    def visit(cluster: Cluster, parent: str) -> None:
        for child in cluster.children:
            if isinstance(child, Cluster):
                frame(child, parent)
            else:
                node(child, parent)

    def frame(cluster: Cluster, parent: str) -> None:
        own = cell_id(cluster.ref, "frame")
        ids[id(cluster)] = own
        cs = cluster.look_style or style.cluster
        colour = cs.color_for(cluster.kind) or "#5f6b7a"
        if not colour.startswith("#"):
            colour = (cluster.look_theme or scene.theme).get(colour, "#5f6b7a")
        fill = cs.fill_for(cluster.kind)
        fill = _tint(fill, cs.fill_tint) if fill.startswith("#") else "none"
        dash = cs.dash_for(cluster.kind) if hasattr(cs, "dash_for") else None
        px, py = origin[parent]
        frame_style = (
            "rounded=0;whiteSpace=wrap;html=1;container=1;collapsible=0;recursiveResize=0;"
            f"pointerEvents=0;strokeColor={colour};fillColor={fill};fontColor={colour};"
            f"strokeWidth={round(cs.width_for(cluster.kind) * scene.frame_line_scale, 2):g};"
            "verticalAlign=top;align=left;spacingLeft=8;"
            "spacingTop=2;fontSize=11;"
            + (f"dashed=1;dashPattern={dash.replace(',', ' ')};" if dash else "")
        )
        element = index.get(cluster.ref)
        attrs = _attributes(cluster.ref, element)
        cells.append(
            f'<object label={quoteattr(html_escape(cluster.label))} id="{own}"{attrs}>'
            f'<mxCell style="{frame_style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{cluster.x - px:g}" y="{cluster.y - py:g}" width="{cluster.width}" '
            f'height="{cluster.height}" as="geometry"/></mxCell></object>'
        )
        origin[own] = (float(cluster.x), float(cluster.y))
        chain[own] = [*chain[parent], own]
        parent_of[id(cluster)] = parent
        visit(cluster, own)

    def panel(item, parent: str) -> None:
        """A panel as one draw.io box: its shape, its tone, and its name,
        detail lines and compartments in the label (builders/panels.py)."""
        own = cell_id(item.ref, "node")
        ids[id(item)] = own
        boxes[id(item)] = (item.x, item.y, item.width, item.height)
        px, py = origin[parent]
        element = index.get(item.ref)
        tones = metrics.tones()
        tone = tones.get(item.panel.tone)
        fill = item.fill or (tone.fill if tone else "#ffffff")
        stroke = item.stroke or (tone.stroke if tone else "#8a9099")
        rows = []
        for row in item.panel.sections:
            parts = []
            for cell in row:
                words = "<br>".join(
                    ([f"<b>{html_escape(cell.title)}</b>"] if cell.title else [])
                    + [html_escape(line) for line in cell.lines]
                )
                paint = tones.get(cell.tone)
                parts.append(
                    f'<span style="background-color:{paint.fill}">{words}</span>'
                    if paint
                    else words
                )
            rows.append("<hr>" + " &#124; ".join(parts))
        label = f"<b>{html_escape(item.name)}</b>" + "".join(
            f"<br>{html_escape(line)}" for line in item.panel.detail_lines
        )
        node_style = (
            "html=1;whiteSpace=wrap;verticalAlign=top;spacingTop=6;fontSize=11;"
            + _PANEL_SHAPES[item.panel.shape]
            + f"fillColor={fill};strokeColor={stroke};"
        )
        cells.append(
            f'<object label={quoteattr(label + "".join(rows))} id="{own}"{_attributes(item.ref, element)}>'
            f'<mxCell style="{node_style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{item.x - px:g}" y="{item.y - py:g}" width="{item.width:g}" '
            f'height="{item.height:g}" as="geometry"/></mxCell></object>'
        )
        parent_of[id(item)] = parent

    def node(item, parent: str) -> None:
        if item.panel is not None:
            panel(item, parent)
            return
        own = cell_id(item.ref, "node")
        ids[id(item)] = own
        left, top, size = glyph_square(item, style)
        boxes[id(item)] = (left, top, size, size)
        px, py = origin[parent]
        element = index.get(item.ref)
        native = stencils.get(_component_key(element))
        label_style = (
            "verticalLabelPosition=bottom;verticalAlign=top;labelBackgroundColor=none;"
            f"whiteSpace=wrap;fontSize=11;labelWidth={item.width};"
        )
        if native is not None:
            node_style = native["style"].rstrip(";") + ";" + label_style
        else:
            art = _artwork(item.icon)
            node_style = (
                "shape=image;aspect=fixed;html=1;imageAspect=1;"
                + label_style
                + (f"image=data:image/svg+xml,{art};" if art else "shape=rect;")
            )
        attrs = _attributes(item.ref, element)
        cells.append(
            f'<object label={quoteattr(_label(item.name, item.detail))} id="{own}"{attrs}>'
            f'<mxCell style="{node_style}" vertex="1" parent="{parent}">'
            f'<mxGeometry x="{left - px:g}" y="{top - py:g}" width="{size:g}" height="{size:g}" '
            f'as="geometry"/></mxCell></object>'
        )
        parent_of[id(item)] = parent

    def _attributes(ref: str, element) -> str:
        out = f" infragram_id={quoteattr(ref)}" if ref else ""
        component = _component_key(element)
        if component:
            out += f" infragram_component={quoteattr(component)}"
        return out

    visit(scene.root, "1")

    for number, link in enumerate(scene.links):
        points = _polyline(R._path_for(link, scene))
        if len(points) < 2 or id(link.source) not in ids or id(link.target) not in ids:
            continue
        a, b = chain[parent_of[id(link.source)]], chain[parent_of[id(link.target)]]
        common = "1"
        for x, y in zip(a, b, strict=False):
            if x != y:
                break
            common = x
        ox, oy = origin[common]

        def pin(
            box: tuple[float, float, float, float], point: tuple[float, float]
        ) -> tuple[float, float]:
            x, y, w, h = box
            return (
                round(min(1, max(0, (point[0] - x) / w)), 4),
                round(min(1, max(0, (point[1] - y) / h)), 4),
            )

        ex, ey = pin(boxes[id(link.source)], points[0])
        nx, ny = pin(boxes[id(link.target)], points[-1])
        ls = style.link(link.kind)
        paint = link.stroke or ls.color or scene.theme[ls.role]
        start_head, end_head = R._heads(link, scene)
        edge_style = (
            "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;jettySize=auto;orthogonalLoop=1;"
            + (
                f"jumpStyle=arc;jumpSize={metrics.load().router.crossing_radius * 2:g};"
                if project.presentation.crossings == "bridge"
                else "jumpStyle=none;"
            )
            + f"strokeColor={paint};strokeWidth={(link.width or ls.width):g};fontSize=11;"
            f"exitX={ex:g};exitY={ey:g};exitDx=0;exitDy=0;entryX={nx:g};entryY={ny:g};entryDx=0;entryDy=0;"
            + (f"dashed=1;dashPattern={ls.dash.replace(',', ' ')};" if ls.dash else "")
            + ("endArrow=block;endFill=1;" if end_head else "endArrow=none;")
            + ("startArrow=block;startFill=1;" if start_head else "startArrow=none;")
        )
        inner = "".join(f'<mxPoint x="{x - ox:g}" y="{y - oy:g}"/>' for x, y in points[1:-1])
        geometry = (
            f'<mxGeometry relative="1" as="geometry"><Array as="points">{inner}</Array></mxGeometry>'
            if inner
            else '<mxGeometry relative="1" as="geometry"/>'
        )
        cells.append(
            f'<mxCell id="wire-{number + 1}" value={quoteattr(html_escape(link.label or ""))} '
            f'style="{edge_style}" edge="1" parent="{common}" source="{ids[id(link.source)]}" '
            f'target="{ids[id(link.target)]}">{geometry}</mxCell>'
        )

    body = "\n    ".join(cells)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<mxfile host="infragram" agent="Infragram Azure">\n'
        f'  <diagram id="{html_escape(project.slug)}" name={quoteattr(project.title)}>\n'
        f'   <mxGraphModel dx="{scene.width}" dy="{scene.height}" grid="1" gridSize="8" guides="1" '
        'tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" math="0" shadow="0">\n'
        f"    <root>\n    {body}\n    </root>\n"
        "   </mxGraphModel>\n  </diagram>\n</mxfile>\n"
    )
