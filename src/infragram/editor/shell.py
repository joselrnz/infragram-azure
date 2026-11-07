"""The editor page: the data it carries and the one call that renders it.

:func:`render_editor_html` is the public entry point. It prepares what the
page needs -- the libraries to embed, the drawing, the editor state and the
specs the runtime shares with the Python renderer -- and hands it to the
views in :mod:`.ui`, which lay out the chrome from its components. The
stylesheet and the runtime come from :mod:`.bundle`.
"""

from __future__ import annotations

import base64
import json
import re
import zlib
from dataclasses import replace
from functools import lru_cache
from textwrap import indent
from typing import cast

from ..builders import arrowheads, metrics
from ..builders.render import render_svg
from ..builders.scene import Scene
from ..catalog import (
    ARCHITECTURE_FRAME_PRESETS,
    links as component_links,
    load_default_provider_registry,
)
from ..catalog.fonts import font_style_element
from ..iso3d import vocabulary as iso3d_vocabulary
from ..iso3d.bundle import bundle_source as iso3d_bundle_source
from ..projects import CloudProject
from ..projects.comments import Comments
from .bundle import runtime_script, stylesheet
from .sidebar import (
    _library_payload,
    load_sidebar_catalog,
)
from .state import _editor_state
from .terraform_payload import terraform_script
from .ui import views
from .ui.views.sidebar import (
    shows_provider_mark as _shows_provider_mark,
    uses_multicloud_brand as _uses_multicloud_brand,
)

#: What the page carries of the libraries. "project" ships the libraries
#: the document opens, which is what a reader needs to keep building; "all"
#: ships every installed one; "drawn" ships only the components the drawing
#: places, plus the shared set every diagram arranges with -- the
#: architecture frames, the basic elements, the 3D item. Measured over the
#: shipped templates that is 1.5-2.4 MB against 1.7-26 MB: most of what is
#: left is the runtime (350 KB), the embedded faces (290 KB) and that shared
#: set (490 KB), so a page whose own library is small saves little and a
#: multicloud or on-premises page saves most of its weight. The cost is that
#: the copy cannot add a component it does not carry.
EMBEDDED_LIBRARIES = ("project", "all", "drawn")

#: How the library payload travels in the page. The catalog is the bulk of an
#: export -- every icon of every installed library as a data URI -- and the
#: text deflates three to four times; the page inflates it with the
#: browser's DecompressionStream before the editor comes up.
LIBRARY_ENCODING = "deflate-raw;base64"

_LIBRARY_SCRIPT = re.compile(
    r'<script type="application/(?:json|octet-stream)" id="infragram-library-catalog"([^>]*)>(.*?)</script>',
    re.S,
)


def pack_library_payload(payload: dict) -> str:
    """The library payload as the page carries it: deflated, base64."""
    return _deflated(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


# The same page drawn again -- a test suite, one export after another --
# packs the same payload, and deflating every library at level 9 takes a
# second and a half. Two entries: each holds the text and its packing.
@lru_cache(maxsize=2)
def _deflated(text: bytes) -> str:
    packer = zlib.compressobj(9, zlib.DEFLATED, -15)
    return base64.b64encode(packer.compress(text) + packer.flush()).decode("ascii")


def library_catalog_from_html(html: str) -> dict:
    """The library payload read back out of a rendered page, whichever way it
    travels -- the test suites and any tool reading an export use this."""
    match = _LIBRARY_SCRIPT.search(html)
    if match is None:
        raise ValueError("the page carries no library catalog")
    attributes, body = match.group(1), match.group(2)
    if 'data-encoding="' not in attributes:
        return json.loads(body)
    found = re.search(r'data-encoding="([^"]*)"', attributes)
    encoding = found.group(1) if found else None
    if encoding != LIBRARY_ENCODING:
        raise ValueError(f"unknown library encoding {encoding!r}")
    return json.loads(zlib.decompress(base64.b64decode(body.strip()), -15).decode("utf-8"))


def project_from_html(html: str) -> CloudProject:
    """The document a rendered page is drawn from, read back out of it (as
    the page was exported; what is changed in the page since is the page's
    own until it is saved as a document)."""
    # imported here: the exports package imports this one as it loads
    from ..exports.carry import page_document

    raw = page_document(html)
    if raw is None:
        raise ValueError("the page carries no Infragram document")
    return CloudProject.model_validate_json(raw)


def _drawn_payload(project: CloudProject, payload: dict[str, object]) -> dict[str, object]:
    """The payload cut down to what this drawing places.

    Kept: every component the document draws, and everything the shared
    library offers -- the architecture frames, the basic elements, the 3D
    item -- because a diagram is still arranged after it is handed over, and
    a frame or a label is what an arrangement needs. Dropped: the rest of
    the vendor catalogs, which is the weight.
    """
    drawn = {
        str(element.component.icon_ref)
        for element in project.topology.walk()
        if element.component is not None and element.component.icon_ref
    }
    drawn |= {
        f"{element.component.provider}:{element.component.service_id}"
        for element in project.topology.walk()
        if element.component is not None
    }
    components = [
        component
        for component in cast("list[dict[str, object]]", payload["components"])
        if component["provider"] == "infragram" or component["qualifiedId"] in drawn
    ]
    return {**payload, "components": components, "drawnOnly": True}


def page_carries_3d_renderer(project: CloudProject, libraries: str) -> bool:
    """Whether the page ships the 3D renderer (three.js and the scene, 1.6 MB).

    A project that installs the on-premises library, or already draws a 3D
    item, gets the builder; ``libraries="all"`` always does. Any other page
    leaves the renderer out and the builder tab says so."""
    if libraries == "all" or (libraries != "drawn" and "onprem" in set(project.provider_ids)):
        return True
    for element in project.topology.walk():
        component = element.component
        if (
            component is not None
            and component.provider == "infragram"
            and component.service_id == "custom-3d"
        ):
            return True
        if element.attributes.get("iso_artwork"):
            return True
    return False


#: A project's title and description are free text, and the JSON blocks the
#: page carries sit inside <script> elements. HTML looks for an end tag or a
#: comment opener inside those blocks without regard to case, so a title
#: holding "</SCRIPT>" or "<!--" would end the block and everything after it
#: would be parsed as markup. Escaping the three characters that can start
#: such a sequence is lossless: a JSON parser decodes them straight back.
_SCRIPT_BREAKOUT = {"<": "\\u003c", ">": "\\u003e", "&": "\\u0026"}


def script_safe(payload: str) -> str:
    """JSON that cannot escape the <script> element that carries it.

    The one escaping every embedded payload goes through: the project, the
    editor state, the 3D vocabulary, the link styles, and (through their
    ``runtime_json``) the arrowhead and metrics specs. ``</script`` and
    ``<!--`` both lose their ``<``, so neither can end the block.
    """
    for character, escaped in _SCRIPT_BREAKOUT.items():
        payload = payload.replace(character, escaped)
    return payload


def render_editor_html(
    project: CloudProject,
    scene: Scene,
    *,
    libraries: str = "project",
    comments: Comments | None = None,
) -> str:
    """Render the distributable HTML workspace with sidebar and live canvas.

    ``comments`` ride along in their own script (ADR 0009); the page that
    pictures are drawn from is rendered without them.
    """

    if libraries not in EMBEDDED_LIBRARIES:
        raise ValueError(f"libraries must be one of {EMBEDDED_LIBRARIES}, not {libraries!r}")
    catalog = load_sidebar_catalog(project.provider)
    provider_registry = load_default_provider_registry()
    selected = tuple(provider.id for provider in project.providers if provider.enabled)
    required = set(selected)
    if libraries != "all":
        # A starter stack may place components from another library (the
        # DigitalOcean DOKS stack uses Kubernetes workloads), so ship those
        # libraries too or the stack would come up with holes in it.
        for preset in ARCHITECTURE_FRAME_PRESETS:
            definition = dict(preset)
            if definition.get("group") not in selected:
                continue
            for node in cast("list[dict[str, object]]", definition.get("nodes") or []):
                provider_id = str(node.get("qualifiedId", "")).partition(":")[0]
                if provider_id and provider_id != "infragram":
                    required.add(provider_id)
    embedded = tuple(
        provider.id
        for provider in provider_registry.providers
        if libraries == "all" or provider.id in required
    )
    catalogs = tuple(load_sidebar_catalog(provider_id) for provider_id in embedded)
    library_payload = _library_payload(catalogs, selected)
    if libraries == "drawn":
        library_payload = _drawn_payload(project, library_payload)
    multicloud = _uses_multicloud_brand(project)
    if not _shows_provider_mark(project) and scene.theme.mark:
        scene.theme = replace(scene.theme, mark="")
    diagram = re.sub(
        r"<svg\b",
        '<svg data-infragram-diagram="true" data-testid="diagram-canvas" tabindex="0"',
        render_svg(scene),
        count=1,
    )
    diagram_head, diagram_close, diagram_tail = diagram.rpartition("</svg>")
    diagram = diagram_head + '  <g data-graph-layer="true"></g>\n' + diagram_close + diagram_tail
    project_json = script_safe(project.model_dump_json(indent=2, exclude_none=True))
    editor_json = script_safe(
        json.dumps(_editor_state(project, scene, library_payload), separators=(",", ":"))
    )
    library_blob = pack_library_payload(library_payload)
    carries_3d = page_carries_3d_renderer(project, libraries)
    # The 3D builder rides along: its vocabulary (families, glyphs, the
    # measurer) as JSON, and the renderer as one classic script -- a module
    # script would not load from a page opened as a file. A closing tag
    # inside the script's own strings is escaped so it cannot end the block.
    iso3d_json = script_safe(json.dumps(iso3d_vocabulary.runtime_payload(), separators=(",", ":")))
    iso3d_bundle = (
        iso3d_bundle_source().replace("</", "<\\/")
        if carries_3d
        else "/* no 3D renderer: this project installs no on-premises library and draws no 3D item */"
    )
    # The arrowhead spec rides along so the runtime draws the same head the
    # static renderer and the checker read from assets/catalog/arrowheads.json.
    arrowheads_json = arrowheads.runtime_json()
    # The numbers both renderers must agree on ride along too, so the
    # editor cannot drift from the static picture (builders/metrics.py).
    metrics_json = metrics.runtime_json()
    # A theme names its own link kinds -- AWS calls a private circuit "vif"
    # and a tunnel "vpn", and gives each a colour, width and dash. The static
    # renderer read that table and the runtime did not, so the same document
    # drew a red tunnel in one picture and a grey one in the other. The table
    # rides along now, the way the arrowheads and the metrics do.
    link_styles_json = script_safe(
        json.dumps(
            {
                kind: {
                    "color": style.color or "",
                    "width": style.width,
                    "dash": style.dash or "",
                    "role": style.role,
                }
                for kind, style in (scene.style.links or {}).items()
            },
            separators=(",", ":"),
        )
    )
    # Where each component is read about: the card popup resolves a card's
    # links from this table (catalog/links.py), so a card added in the page
    # has them too, and a saved document carries none.
    component_links_json = script_safe(component_links.runtime_json(embedded))
    arrow_options = arrowheads.select_options()
    corner_options = "".join(
        f'<option value="{name}">{name.title()}</option>' for name in metrics.corner_styles()
    )
    architecture_label = "Multicloud" if multicloud else catalog.provider_name
    # The diagram's Terraform rides along for the download menu (terraform_payload.py).
    terraform_styles, terraform_block = terraform_script(project)
    data_scripts = f"""  <script type="application/octet-stream" id="infragram-library-catalog" data-encoding="{LIBRARY_ENCODING}">{library_blob}</script>
  <script type="application/json" id="infragram-project">{project_json}</script>
  <script type="application/json" id="infragram-editor-state" data-editor-state>{editor_json}</script>
  <script type="application/json" id="infragram-arrowheads">{arrowheads_json}</script>
  <script type="application/json" id="infragram-render-metrics">{metrics_json}</script>
  <script type="application/json" id="infragram-link-styles">{link_styles_json}</script>
  <script type="application/json" id="infragram-component-links">{component_links_json}</script>
  <script type="application/json" id="infragram-iso3d-vocabulary">{iso3d_json}</script>"""
    if comments is not None:
        data_scripts += (
            '\n  <script type="application/json" id="infragram-comments">'
            f"{script_safe(comments.page_json())}</script>"
        )
    if terraform_block:
        data_scripts += f"\n  {terraform_block}"
    return views.page(
        title=project.title,
        font_faces=font_style_element(),
        stylesheet=indent(stylesheet(scene.width, scene.height), "    "),
        sidebar=views.sidebar(project, catalog, library_payload),
        header=views.header(
            project.title,
            architecture_label,
            catalog.component_count,
            terraform=terraform_styles,
        ),
        canvas=views.canvas(diagram),
        inspector=views.inspector(
            scene, views.template_brief(project, architecture_label), arrow_options, corner_options
        ),
        drawer=views.drawer(project.title),
        data_scripts=data_scripts,
        iso3d_bundle=iso3d_bundle,
        runtime=runtime_script(),
    )


__all__ = [
    "EMBEDDED_LIBRARIES",
    "LIBRARY_ENCODING",
    "library_catalog_from_html",
    "pack_library_payload",
    "page_carries_3d_renderer",
    "project_from_html",
    "render_editor_html",
    "script_safe",
]
