#!/usr/bin/env python3
"""Check infrastructure project documents, exported pages and pictures.

Usage:
    infragram check <file or folder> [more...]
    python project_check.py <file or folder> [more...]

A project document (``.infragram.json``, schema version 1, 2 or 3) is checked
for structure: slugs, unique element ids, no unknown keys, connection targets
that resolve, connection kinds the document's libraries define,
provider-qualified component references, and layer references. An exported
editor page is checked for the marked diagram, the document it carries (then
checked like a document file), and the absence of remote scripts. A picture
(``.svg``) is read the way an eye would -- wires, text, captions, arrowheads --
and against its document when one sits beside it; a ``.png`` is checked to be
a PNG. A folder stands for the documents, pages and pictures in it.

Standard library only, so it runs from an installed copy of the skill. Exits
0 when every file passes and 1 otherwise; one line per finding.
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
import struct
import sys
from html import unescape
from pathlib import Path
from typing import TypedDict, cast

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NAMESPACED = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*(?::[a-z0-9]+(?:-[a-z0-9]+)*)?$")
PROJECT_KINDS = {"single-cloud", "multicloud", "platform", "hybrid"}
DIAGRAM_SVG = re.compile(r"<svg\b[^>]*\bdata-[a-z]+-diagram\b", re.IGNORECASE)
EMBEDDED_PROJECT = re.compile(
    r'<script\b[^>]*\bid="[a-z]+-project"[^>]*>(.*?)</script>', re.IGNORECASE | re.DOTALL
)
#: The page's own code and styles, set aside before its markup is checked.
PAGE_CODE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
EMBEDDED_STATE = re.compile(r'<script\b[^>]*\bid="[a-z]+-editor-state"', re.IGNORECASE)
REMOTE_SCRIPT = re.compile(r'<script\b[^>]*\bsrc\s*=\s*["\']?\s*(?:https?:)?//', re.IGNORECASE)
# Loaded resources only: src= on any element and href= on <link>. Ordinary
# <a href> links (attribution, terms of use) are allowed to point anywhere.
REMOTE_SRC = re.compile(
    r'(?:\bsrc\s*=\s*["\'](https?://[^"\']+)|<link\b[^>]*\bhref\s*=\s*["\'](https?://[^"\']+))',
    re.IGNORECASE,
)
ALLOWED_HOSTS = ("https://fonts.googleapis.com/", "https://fonts.gstatic.com/")
# Artwork is inlined into an export, so the export is only as safe as what
# was inlined. A picture that carries a script, an event handler, an embedded
# document or a link to somewhere else is not a picture any more: opening it
# runs someone else's code. SVG fetches through href on <image>, <use> and
# <feImage>, which the loaded-resource rule above does not see.
UNSAFE_MARKUP = re.compile(
    r"<(?:script|foreignobject|iframe|object|embed)\b"
    r"|javascript:"
    r"|(?<![\w-])on[a-z]+\s*="
    r"|<!ENTITY\b"
    r"|@import\b"
    r"|\burl\(\s*[\"']?\s*(?:https?:)?//",
    re.IGNORECASE,
)
#: A ``data:`` link and the element carrying it. A raster is safe anywhere;
#: an SVG only as an ``<image>``, which a browser draws without scripts or
#: fetches; anything else (``text/html``, ...) is a document that runs.
DATA_HREF = re.compile(
    r"<([a-z][\w:-]*)\b[^>]*?\bhref\s*=\s*[\"']?\s*data:([^;,\"'\s>]*)", re.IGNORECASE
)
_SAFE_DATA = frozenset({"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"})
#: A quoted attribute value, the place a scheme hides in.
_ATTRIBUTE_VALUE = re.compile(r"=\s*([\"'])(.*?)\1", re.DOTALL)
#: ASCII whitespace and control characters, which a browser ignores inside a
#: URL scheme: ``java&#9;script:`` is ``javascript:`` to it.
_SCHEME_NOISE = re.compile(r"[\x00-\x20]")
#: The keys the package's models accept; a document with any other key is
#: refused at load, so it is refused here too.
ELEMENT_KEYS = frozenset(
    {
        "attributes",
        "badges",
        "children",
        "component",
        "connections",
        "id",
        "layer_id",
        "name",
        "role",
        "type",
    }
)
#: A frame's corner badges (a subnet's NSG, its route table). Older
#: documents carry an empty list on every element; marks pinned to a frame's
#: other sides were retired because the editor never drew them. The package
#: accepts corner badges and refuses the rest, and so does this.
RETIRED_BADGES = "badges"
BADGE_KEYS = frozenset({"collection", "icon", "label", "side", "offset"})
CONNECTION_KEYS = frozenset(
    {
        "direction",
        "kind",
        "label",
        "label_placement",
        "step",
        "step_flow",
        "step_text",
        "target",
        "waypoints",
    }
)
COMPONENT_KEYS = frozenset({"icon_ref", "provider", "service_id"})
#: The files a folder stands for, and the PNG file signature.
CHECKED_SUFFIXES = (".json", ".html", ".htm", ".svg", ".png")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
REMOTE_REFERENCE_PATTERN = (
    r"<(?:image|use|feimage)\b[^>]*\b(?:xlink:)?href\s*=\s*[\"']((?:https?:)?//[^\"']+)"
)
REMOTE_REFERENCE = re.compile(
    REMOTE_REFERENCE_PATTERN,
    re.IGNORECASE,
)


def _slug(value: object, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not SLUG.fullmatch(value.strip().casefold()):
        errors.append(f"{label} must be a slug, got {value!r}")
        return None
    return value.strip().casefold()


def _text(value: object, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a non-empty string")


def check_project(payload: object, errors: list[str]) -> dict[str, object]:
    """Validate one project document; return a small summary for reporting."""
    summary: dict[str, object] = {"slug": "?", "elements": 0, "connections": 0, "providers": []}
    if not isinstance(payload, dict):
        errors.append("project must be a JSON object")
        return summary

    version = payload.get("schema_version")
    if version not in (1, 2, 3):
        errors.append(f"schema_version must be 1, 2 or 3, got {version!r}")
        return summary

    slug = _slug(payload.get("slug"), "slug", errors)
    summary["slug"] = slug or "?"
    _text(payload.get("title"), "title", errors)
    _text(payload.get("description"), "description", errors)

    providers: list[str] = []
    layer_ids: set[str] = set()
    if version == 1:
        provider = _slug(payload.get("provider"), "provider", errors)
        if provider:
            providers.append(provider)
    else:
        kind = payload.get("kind", "single-cloud")
        if kind not in PROJECT_KINDS:
            errors.append(f"kind must be one of {sorted(PROJECT_KINDS)}, got {kind!r}")
        raw_providers = payload.get("providers")
        if not isinstance(raw_providers, list) or not raw_providers:
            errors.append("providers must be a non-empty array")
            raw_providers = []
        for index, selection in enumerate(raw_providers):
            if not isinstance(selection, dict):
                errors.append(f"providers[{index}] must be an object")
                continue
            provider = _slug(selection.get("id"), f"providers[{index}].id", errors)
            if provider:
                if provider in providers:
                    errors.append(f"duplicate provider selection: {provider}")
                providers.append(provider)
        enabled = [
            selection.get("id")
            for selection in raw_providers
            if isinstance(selection, dict) and selection.get("enabled", True)
        ]
        if raw_providers and not enabled:
            errors.append("at least one provider library must be enabled")
        default_library = payload.get("default_library", "all")
        if default_library != "all" and default_library not in enabled:
            errors.append(
                f"default_library must be 'all' or an enabled provider: {default_library!r}"
            )
        if kind == "single-cloud" and len(providers) != 1:
            errors.append("single-cloud projects require exactly one provider")
        if kind == "multicloud" and len(providers) < 2:
            errors.append("multicloud projects require at least two providers")

        layers = payload.get("layers", [])
        if not isinstance(layers, list):
            errors.append("layers must be an array")
            layers = []
        for index, layer in enumerate(layers):
            if not isinstance(layer, dict):
                errors.append(f"layers[{index}] must be an object")
                continue
            layer_id = layer.get("id")
            if not isinstance(layer_id, str) or not NAMESPACED.fullmatch(
                layer_id.strip().casefold()
            ):
                errors.append(f"layers[{index}].id must be a slug or one-level qualified slug")
                continue
            layer_id = layer_id.strip().casefold()
            if layer_id in layer_ids:
                errors.append(f"duplicate layer id: {layer_id}")
            layer_ids.add(layer_id)
            _text(layer.get("name"), f"layer {layer_id} name", errors)
            layer_provider = layer.get("provider")
            if layer_provider is not None and layer_provider not in providers:
                errors.append(
                    f"layer {layer_id} provider {layer_provider!r} is not installed in this project"
                )
    summary["providers"] = providers

    topology = payload.get("topology")
    if not isinstance(topology, dict):
        errors.append("topology must be an object")
        return summary

    ids: dict[str, int] = {}
    connections: list[tuple[str, str]] = []
    known_kinds = {"solid", *link_dashes_for(payload)}

    def walk(element: object, path: str) -> None:
        if not isinstance(element, dict):
            errors.append(f"{path} must be an object")
            return
        _unknown_keys(element, ELEMENT_KEYS, path, errors)
        badges = element.get(RETIRED_BADGES)
        if badges is not None and not isinstance(badges, list):
            errors.append(f"{path}.badges must be a list")
        for number, badge in enumerate(badges if isinstance(badges, list) else []):
            where = f"{path}.badges[{number}]"
            if not isinstance(badge, dict):
                errors.append(f"{where} must be an object")
                continue
            _unknown_keys(badge, BADGE_KEYS, where, errors)
            if badge.get("side", "top") not in ("corner", "edge", "top", "bottom", "left", "right"):
                errors.append(f"{where}.side must name a frame side, corner or edge")
            if "offset" in badge and (
                isinstance(badge["offset"], bool) or not isinstance(badge["offset"], (int, float))
            ):
                errors.append(f"{where}.offset must be a number")
            _text(badge.get("icon"), f"{where}.icon", errors)
        element_id = element.get("id")
        if not isinstance(element_id, str) or not element_id.strip():
            errors.append(f"{path}.id must be a non-empty string")
            element_id = f"<{path}>"
        ids[element_id] = ids.get(element_id, 0) + 1
        _text(element.get("name"), f"{path}.name", errors)
        _text(element.get("type"), f"{path}.type", errors)

        component = element.get("component")
        if component is not None:
            if not isinstance(component, dict):
                errors.append(f"{path}.component must be an object")
            else:
                _unknown_keys(component, COMPONENT_KEYS, f"{path}.component", errors)
                provider = _slug(component.get("provider"), f"{path}.component.provider", errors)
                service_id = _slug(
                    component.get("service_id"), f"{path}.component.service_id", errors
                )
                icon_ref = component.get("icon_ref")
                if (
                    provider
                    and icon_ref is not None
                    and not str(icon_ref).startswith(f"{provider}:")
                ):
                    errors.append(f"{path}.component.icon_ref must start with {provider}:")
                if (
                    provider
                    and service_id
                    and version != 1
                    and provider not in providers
                    and provider != "infragram"
                ):
                    errors.append(
                        f"{path}.component.provider {provider!r} is not installed in this project"
                    )

        layer_id = element.get("layer_id")
        if layer_id is not None and version != 1 and layer_id not in layer_ids:
            errors.append(f"{path}.layer_id references unknown layer {layer_id!r}")

        _check_paint(element.get("attributes"), path, errors)

        for index, connection in enumerate(element.get("connections", []) or []):
            if not isinstance(connection, dict) or not isinstance(connection.get("target"), str):
                errors.append(f"{path}.connections[{index}] must be an object with a target id")
                continue
            _unknown_keys(connection, CONNECTION_KEYS, f"{path}.connections[{index}]", errors)
            kind = connection.get("kind", "solid")
            if kind not in known_kinds:
                # the renderers look the kind up in the link table of the
                # document's libraries; one they do not know is a crash there,
                # so it is an error here
                errors.append(
                    f"{path}.connections[{index}] kind {kind!r} is not in the link table "
                    f"of this document's libraries ({', '.join(sorted(known_kinds))})"
                )
            step = connection.get("step")
            if step is not None and (
                not isinstance(step, int) or isinstance(step, bool) or not 1 <= step <= 99
            ):
                errors.append(
                    f"{path}.connections[{index}].step must be a whole number from 1 to 99"
                )
            elif step is not None and not str(connection.get("label") or "").strip():
                errors.append(
                    f"{path}.connections[{index}] has a step and no label: a step numbers a caption"
                )
            flow = connection.get("step_flow")
            if flow is not None and (step is None or not isinstance(flow, str) or not flow.strip()):
                errors.append(
                    f"{path}.connections[{index}].step_flow names the flow a step belongs to: "
                    f"give the wire a step and the flow a name"
                )
            connections.append((element_id, connection["target"]))
        for index, child in enumerate(element.get("children", []) or []):
            walk(child, f"{path}.children[{index}]")

    walk(topology, "topology")
    for element_id, count in ids.items():
        if count > 1:
            errors.append(f"duplicate topology id: {element_id!r}")
    for source, target in connections:
        if target not in ids:
            errors.append(f"{source!r} connects to unknown target {target!r}")
    summary["elements"] = len(ids)
    summary["connections"] = len(connections)
    return summary


#: A colour a document may paint with (the package's verification.SAFE_COLOUR).
SAFE_COLOUR = re.compile(r"#[0-9a-fA-F]{3,8}|[A-Za-z]{3,24}|(?:rgb|rgba|hsl|hsla)\([0-9.,\s%]+\)")
#: The stored-style keys whose values are written into a colour attribute.
PAINT_KEYS = ("fill", "stroke", "label", "labelColor", "tabFill", "color")


def _check_paint(attributes: object, path: str, errors: list[str]) -> None:
    """A stored colour must be a colour: it is written into an attribute.

    The package drops one that is not, so a crafted fill such as
    ``red" onmouseover="...`` paints nothing; the checker says so rather
    than let the document pass.
    """
    if not isinstance(attributes, dict):
        return
    styles: list[tuple[str, object]] = [
        (f"{path}.attributes.{key}", attributes.get(key))
        for key in ("editor_style", "editor_boundary_style")
    ]
    edges = attributes.get("editor_edge_styles")
    if isinstance(edges, dict):
        styles += [(f"{path}.attributes.editor_edge_styles.{k}", v) for k, v in edges.items()]
    for where, style in styles:
        if not isinstance(style, dict):
            continue
        for key in PAINT_KEYS:
            value = style.get(key)
            if value is not None and not (isinstance(value, str) and SAFE_COLOUR.fullmatch(value)):
                errors.append(f"{where}.{key} is not a colour: {str(value)[:60]!r}")


def _check_markup_safety(text: str, errors: list[str]) -> None:
    """Nothing in an exported document may run or fetch anything.

    A document is shared as a file and opened by whoever receives it, so a
    script, an event handler, an embedded document or a reference to another
    server would run or call out on their machine, not the author's.
    """
    for reading in _readings(text):
        unsafe = UNSAFE_MARKUP.search(reading)
        if unsafe is None:
            unsafe = next(
                (
                    match
                    for match in DATA_HREF.finditer(reading)
                    if not _safe_data(match.group(1), match.group(2))
                ),
                None,
            )
        if unsafe is not None:
            errors.append(f"document contains executable markup: {unsafe.group(0)[:80]!r}")
            break
    for reading in _readings(text):
        remote = REMOTE_REFERENCE.search(reading)
        if remote is not None:
            errors.append(f"document fetches artwork from elsewhere: {remote.group(1)}")
            break


def _safe_data(element: str, media: str) -> bool:
    """Whether a ``data:`` link of this media type is harmless on this element."""
    media = media.casefold()
    return media in _SAFE_DATA or (
        media == "image/svg+xml" and element.casefold() in ("image", "feimage")
    )


def _readings(text: str) -> tuple[str, str, str]:
    """The text as written, then as a browser reads its attribute values.

    Inside attribute values, character references are decoded
    (``&#106;avascript:`` is ``javascript:``) and then the whitespace and
    control characters a URL parser drops are dropped too. Text content is
    left as written, so a caption that spells ``&lt;script&gt;`` stays prose.
    """

    def attribute(match: re.Match[str], squeeze: bool) -> str:
        value = unescape(match.group(2))
        if squeeze:
            value = _SCHEME_NOISE.sub("", value)
        return "=" + match.group(1) + value + match.group(1)

    decoded = _ATTRIBUTE_VALUE.sub(lambda match: attribute(match, False), text)
    squeezed = _ATTRIBUTE_VALUE.sub(lambda match: attribute(match, True), text)
    return text, decoded, squeezed


def _unknown_keys(value: dict, known: frozenset[str], path: str, errors: list[str]) -> None:
    """Refuse keys the package would refuse, naming the nearest real one."""
    for key in sorted(set(value) - known):
        close = difflib.get_close_matches(str(key), sorted(known), n=1)
        errors.append(
            f"{path} has unknown key {key!r}" + (f" (did you mean {close[0]!r}?)" if close else "")
        )


def check_html(text: str, errors: list[str]) -> dict[str, object]:
    """Validate an exported editor page and the project embedded in it."""
    summary: dict[str, object] = {"slug": "?", "elements": 0, "connections": 0, "providers": []}
    if not DIAGRAM_SVG.search(text):
        errors.append("no diagram SVG marked with a data-*-diagram attribute")
    if not EMBEDDED_STATE.search(text):
        errors.append("no embedded editor state script")
    if REMOTE_SCRIPT.search(text):
        errors.append("page loads a remote script; exports must work offline")
    # The page's own code sits in <script> and <style> elements; the rest is
    # markup drawn from the document, and must carry nothing that runs.
    _check_markup_safety(PAGE_CODE.sub("", text), errors)
    for src_url, link_url in REMOTE_SRC.findall(text):
        url = src_url or link_url
        if not url.startswith(ALLOWED_HOSTS):
            errors.append(f"page loads a remote resource: {url}")
            break
    match = EMBEDDED_PROJECT.search(text)
    if match is None:
        errors.append("no embedded project document")
        return summary
    raw = match.group(1)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # Some exporters HTML-escape the embedded document; retry once unescaped.
        try:
            payload = json.loads(unescape(raw))
        except json.JSONDecodeError as error:
            errors.append(f"embedded project is not valid JSON: {error}")
            return summary
    summary = check_project(payload, errors)
    check_components(payload, errors)
    check_nesting(payload, errors)
    return summary


# --------------------------------------------------------------------------
# Components must exist. A diagram is only as honest as its parts: a card
# naming a service the library does not ship is an invention with a real
# vendor's colours on it. The inventory the skill ships lists every component,
# primitive and frame of every library, so the check needs nothing else.

#: The env var the package honours to point an installed copy at a
#: checkout's assets; the checker reads the same one, never a second name.
ASSETS_ENV = "INFRAGRAM_ASSETS"


def _asset_candidates() -> tuple[Path, ...]:
    """Where the skill's assets may be, in the order they are tried: beside
    this script's folder in a checkout (``scripts/../assets``), beside it in
    an installed wheel (``infragram/_skill_scripts/../_assets``), then
    wherever ``INFRAGRAM_ASSETS`` points."""
    here = Path(__file__).resolve().parent
    candidates = [here.parent / "assets", here.parent / "_assets"]
    override = os.environ.get(ASSETS_ENV)
    if override:
        candidates.append(Path(override))
    return tuple(candidates)


def _find_assets() -> Path | None:
    for candidate in _asset_candidates():
        if (candidate / "catalog").is_dir():
            return candidate
    return None


#: The assets this copy of the checker reads, or None when no candidate
#: holds a catalog; the paths below then point at the first place looked, so
#: every read fails the same way and the component check says where it looked.
ASSETS = _find_assets()
_ASSETS_OR_FIRST = ASSETS or _asset_candidates()[0]
INVENTORY = _ASSETS_OR_FIRST / "catalog" / "inventory.json"


THEMES = _ASSETS_OR_FIRST / "themes"

#: Numbers both renderers agree on, read from the file they both read. The
#: fallback is what shipped alongside this script, for a copy taken without
#: its assets.
RENDER_METRICS = _ASSETS_OR_FIRST / "catalog" / "render-metrics.json"
#: Group artwork and the frame that replaces each piece of it.
CONTAINER_ARTWORK = _ASSETS_OR_FIRST / "catalog" / "container-artwork.json"

_warned_no_assets = False


def _warn_no_assets() -> None:
    """Say once, on stderr, that this copy runs without its assets."""
    global _warned_no_assets
    if _warned_no_assets or ASSETS is not None:
        return
    _warned_no_assets = True
    looked = ", ".join(str(path) for path in _asset_candidates())
    print(
        f"WARNING: no skill assets found beside {Path(__file__).name} (looked in {looked}); "
        f"set {ASSETS_ENV} to the skill's assets directory",
        file=sys.stderr,
    )


def render_metrics() -> dict:
    try:
        return json.loads(RENDER_METRICS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"link_dashes": {"dotted": "2 3", "dashed": "5 4"}}


def default_link_dashes() -> dict[str, str | None]:
    """The dash a connection kind gets before any theme has a say."""
    return dict(render_metrics().get("link_dashes") or {})


def primary_provider(project: dict) -> str | None:
    """The provider whose theme styles a document, resolved the way the model
    does: an explicit ``default_library``, else the first enabled entry of
    ``providers``, else the phase-one ``provider`` field."""
    default = project.get("default_library")
    if isinstance(default, str) and default and default != "all":
        return default
    providers = project.get("providers")
    if isinstance(providers, list):
        for entry in providers:
            if isinstance(entry, str) and entry:
                return entry
            if (
                isinstance(entry, dict)
                and entry.get("enabled", True)
                and isinstance(entry.get("id"), str)
            ):
                return entry["id"]
    provider = project.get("provider")
    return provider if isinstance(provider, str) and provider else None


def link_dashes(provider: object) -> dict[str, str | None]:
    """Connection kind -> dash pattern, as the editor draws it for a project
    of this provider.

    Mirrors how the renderer builds its link styles: the built-in kinds, then
    the provider theme's ``style.links`` on top. A kind neither knows draws
    solid, so ``local`` is solid everywhere while the AWS theme dashes ``vpn``
    and ``vif`` its own way.
    """
    dashes = default_link_dashes()
    path = THEMES / f"{provider}.json" if isinstance(provider, str) and provider else None
    if path is None or not path.is_file():
        return dashes
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dashes
    links = (manifest.get("style") or {}).get("links") if isinstance(manifest, dict) else None
    if isinstance(links, dict):
        for kind, style in links.items():
            if isinstance(style, dict):
                dashes[str(kind)] = style.get("dash") or None
    return dashes


def document_providers(project: dict) -> list[str]:
    """The libraries a document draws with: the one that styles it first,
    then every other enabled provider."""
    ordered: list[str] = []
    primary = primary_provider(project)
    if primary:
        ordered.append(primary)
    providers = project.get("providers")
    if isinstance(providers, list):
        for entry in providers:
            name = (
                entry
                if isinstance(entry, str)
                else (
                    entry.get("id")
                    if isinstance(entry, dict) and entry.get("enabled", True)
                    else None
                )
            )
            if isinstance(name, str) and name and name not in ordered:
                ordered.append(name)
    return ordered


def link_dashes_for(project: dict) -> dict[str, str | None]:
    """Connection kind -> dash pattern for a whole document, as the renderer
    builds it: the styling library's table, then any kind only another of
    the document's libraries defines (a hybrid diagram styled by Cloudflare
    still draws the AWS theme's ``vpn``)."""
    providers = document_providers(project)
    dashes = link_dashes(providers[0] if providers else None)
    for provider in providers[1:]:
        for kind, dash in link_dashes(provider).items():
            dashes.setdefault(kind, dash)
    return dashes


def known_components() -> set[str] | None:
    """Every ``provider:id`` the installed skill can draw, or None when the
    inventory is not beside this script (the script was copied out alone)."""
    try:
        data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _warn_no_assets()
        return None
    known: set[str] = set()
    for primitive in data.get("shared_primitives", []):
        known.add(f"infragram:{primitive.get('id')}")
    for frame in data.get("core_frames", []):
        known.add(f"infragram:{frame.get('id')}")
    for library in data.get("libraries", []):
        for component in library.get("components", []):
            known.add(f"{library.get('id')}:{component.get('id')}")
        for frame in library.get("frames", []):
            known.add(f"infragram:{frame.get('id')}")
    return known


def container_artwork() -> dict:
    """Artwork the vendor files as a group box, and the frame that replaces it.

    A group icon is the box drawn *around* things. It ships as a component
    like everything else, and its name collides with the frame that does the
    same job -- ``Region`` the glyph beside ``Region`` the frame -- so placing
    it as a node draws a card that contains nothing and reads as a boundary
    while modelling none. Empty when the table is not beside this script.
    """
    try:
        data = json.loads(CONTAINER_ARTWORK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def container_advice(provider: str, service: str) -> str | None:
    """What to place instead of this glyph, or None when it is not one."""
    row = (container_artwork().get("providers") or {}).get(provider, {}).get(service)
    if not isinstance(row, dict):
        return None
    frame = row.get("frame")
    if frame:
        return f"to contain, use {frame}"
    reason = str(row.get("reason") or "").replace("``", "")
    return f"no frame ships for it: {reason}" if reason else "no frame ships for it"


def check_components(payload: object, errors: list[str]) -> int:
    """Every component in the document names something the skill ships, and
    nothing draws a group box as though it were a node."""
    known = known_components()
    if known is None:
        # Passing silently here is how an installed copy once said OK to an
        # invented service: the check must fail, and say where it looked.
        looked = ", ".join(str(path / "catalog" / "inventory.json") for path in _asset_candidates())
        errors.append(
            f"no component inventory found (looked in {looked}); the checker cannot tell "
            f"a shipped service from an invented one, so set {ASSETS_ENV} to the skill's assets"
        )
        return 0
    if not isinstance(payload, dict):
        return 0
    checked = 0

    def walk(element: object, path: str) -> None:
        nonlocal checked
        if not isinstance(element, dict):
            return
        component = element.get("component")
        if isinstance(component, dict):
            provider = component.get("provider")
            service = component.get("service_id")
            if isinstance(provider, str) and isinstance(service, str):
                checked += 1
                if f"{provider}:{service}" not in known:
                    errors.append(
                        f"{path}.component names {provider}:{service}, which no installed "
                        "library ships; the diagram would draw an invented service"
                    )
                advice = container_advice(provider, service)
                if advice:
                    errors.append(
                        f"{path}.component draws {provider}:{service}, which is the box the "
                        f"vendor draws around things, not a node; placed here it contains "
                        f"nothing ({advice})"
                    )
        for index, child in enumerate(element.get("children") or []):
            walk(child, f"{path}.children[{index}]")

    walk(payload.get("topology"), "topology")
    return checked


#: Public clouds: a frame of one never holds another's frames or services.
#: Edges, interconnects and platforms that run inside a cloud (Cloudflare,
#: Equinix, Databricks, Kubernetes) are not in it.
_CLOUDS = frozenset(
    {
        "aws",
        "azure",
        "gcp",
        "oracle",
        "ibm",
        "alibaba",
        "digitalocean",
        "hetzner",
        "ovhcloud",
        "vultr",
        "akamai",
    }
)
#: Frame kinds no vendor nests inside one of the same kind: a resource group in
#: a resource group, a VPC in a VPC. Management groups, folders and
#: organizational units do nest, so they are not here.
_NO_SELF_NESTING = frozenset(
    {
        "subscription",
        "account",
        "project",
        "resource-group",
        "region",
        "vpc",
        "network",
        "zone",
        "subnet-public",
        "subnet-private",
    }
)


def _cloud_of(element: dict) -> str | None:
    """The public cloud an element belongs to: a service's provider, or the
    vendor a frame's ``custom-boundary-<vendor>-...`` id names."""
    component = element.get("component")
    if not isinstance(component, dict):
        return None
    provider = component.get("provider")
    service = str(component.get("service_id") or "")
    if provider in _CLOUDS:
        return str(provider)
    if provider == "infragram" and service.startswith("custom-boundary-"):
        vendor = service.removeprefix("custom-boundary-").split("-", 1)[0]
        return vendor if vendor in _CLOUDS else None
    return None


def check_nesting(payload: object, errors: list[str]) -> None:
    """Frames nest the way the clouds do: one cloud's frames and services never
    sit inside another cloud's frame, and a resource group, a subscription, a
    VPC or a subnet never sits inside one of its own kind."""
    if not isinstance(payload, dict):
        return

    def walk(element: object, path: str, frames: list[dict]) -> None:
        if not isinstance(element, dict):
            return
        cloud = _cloud_of(element)
        children = element.get("children") or []
        kind = str(element.get("type") or "")
        name = element.get("name")
        outer = next((frame for frame in reversed(frames) if _cloud_of(frame)), None)
        if cloud and outer is not None and _cloud_of(outer) != cloud:
            errors.append(
                f"{path} ({name!r}) is {cloud}, inside {_cloud_of(outer)}'s "
                f"{outer.get('type')} frame {outer.get('name')!r}: one cloud's resources never "
                "sit in another's; draw each cloud in its own frame and wire across"
            )
        if children and cloud and kind in _NO_SELF_NESTING:
            same = next(
                (
                    frame
                    for frame in reversed(frames)
                    if frame.get("type") == kind and _cloud_of(frame) == cloud
                ),
                None,
            )
            if same is not None:
                errors.append(
                    f"{path} is the {kind} {name!r} inside the {kind} {same.get('name')!r}: "
                    f"{cloud} does not nest a {kind} in a {kind}; draw them side by side"
                )
        inner = [*frames, element] if children else frames
        for index, child in enumerate(children):
            walk(child, f"{path}.children[{index}]", inner)

    walk(payload.get("topology"), "topology", [])


# --------------------------------------------------------------------------
# The picture. An exported SVG is read by eye, so the checks below ask what an
# eye would: are the wires orthogonal, does any wire run through text or
# through a card it does not belong to, do captions sit on top of each other,
# and do the arrowheads say what the document says. Text width is estimated
# the way the editor estimates it, so what is clear here is clear there.

_NUM = r"(-?\d+(?:\.\d+)?)"
_NODE_GROUP = re.compile(
    r'<g data-graph-node([^>]*?)data-node-id="([^"]*)"[^>]*?data-display-mode="([^"]*)"[^>]*?transform="translate\('
    + _NUM
    + r"\s+"
    + _NUM
    + r'\)"[^>]*>(.*?)</g>',
    re.S,
)
_STATIC_NODE_GROUP = re.compile(
    r'<g(?: data-ink="([^"]*)")?(?: data-ink-edge="([^"]*)")? data-node="([^"]*)" data-display="([^"]*)"(?: data-panel="")?>(.*?)</g>',
    re.S,
)
#: Where a node's icon keeps air inside its square, written by both renderers
#: as left,right,top,bottom fractions so a glyph box can be drawn in to the ink.
_INK = re.compile(r'data-ink="([^"]*)"')
#: Where a bare glyph's ink begins along every line of each side, in the
#: encoding of the renderers' ink table: 33 characters a side, the depth in
#: 64ths of the glyph square ('A' is 0, '/' is 63, '.' no ink), sides joined
#: by '|' as left, right, top, bottom. A link on that glyph is seated there.
_INK_EDGE = re.compile(r'data-ink-edge="([^"]*)"')
_EDGE_LEVELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_EDGE_SIDES = ("left", "right", "top", "bottom")


def _edge_depth(code: str, side: str, along: float) -> float | None:
    """How deep into the glyph square, as a fraction of it, the ink begins
    on ``side`` at ``along`` of the way from the side's start to its end.

    The checker's own copy of ``infragram.catalog.ink.edge_depth`` (it may
    not import the package): measured lines are interpolated unless they are
    a step apart, a line with no ink borrows the shallower of its nearest
    measured neighbours within three lines, and nothing is seated deeper
    than the square's middle.
    """
    parts = code.split("|")
    if side not in _EDGE_SIDES or len(parts) != len(_EDGE_SIDES):
        return None
    line = parts[_EDGE_SIDES.index(side)]
    count = len(line)
    if count < 2:
        return None

    def level(index: int) -> float | None:
        # Ink that begins past the middle of the square is no seat either.
        if index < 0 or index >= count or line[index] == ".":
            return None
        found = _EDGE_LEVELS.find(line[index])
        return None if found < 0 or found / 64 > 0.5 else found / 64

    position = min(1.0, max(0.0, along)) * (count - 1)
    low = int(position)
    high = min(low + 1, count - 1)
    a, b = level(low), level(high)
    depth: float | None
    if a is not None and b is not None:
        # Lines more than a step apart are an edge of the mark, not a slope.
        if abs(a - b) > 3 / 64:
            depth = a if position - low < 0.5 else b
        else:
            depth = a + (b - a) * (position - low)
    elif a is not None:
        depth = a
    elif b is not None:
        depth = b
    else:
        depth = None
        for step in range(1, 4):
            near = [value for value in (level(low - step), level(high + step)) if value is not None]
            if near:
                depth = min(near)
                break
        if depth is None:
            return None
    return min(depth, 0.5)


def _ink_of(group: str) -> list[float]:
    found = _INK.search(group)
    if not found or not found.group(1).strip():
        return [0.0, 0.0, 0.0, 0.0]
    parts = [_num(part, 0.0) for part in found.group(1).split(",")]
    return (parts + [0.0, 0.0, 0.0, 0.0])[:4]


#: The ink is measured on a raster, and a renderer rounds the anchor it puts
#: on that edge, so the box is read half a pixel forgiving: a wire that leaves
#: from the edge must not be read as one that crosses it.
INK_TOLERANCE = 0.5


def _inked(glyph: Box, insets: list[float]) -> Box:
    """The glyph box drawn in to where the artwork's ink starts."""
    width, height = glyph.right - glyph.left, glyph.bottom - glyph.top
    box = Box(
        glyph.left + insets[0] * width + INK_TOLERANCE,
        glyph.top + insets[2] * height + INK_TOLERANCE,
        glyph.right - insets[1] * width - INK_TOLERANCE,
        glyph.bottom - insets[3] * height - INK_TOLERANCE,
        glyph.label,
    )
    return box if box.right - box.left > 2 and box.bottom - box.top > 2 else glyph


_BOUNDARY_GROUP = re.compile(
    r'<g data-graph-boundary[^>]*?data-boundary-id="([^"]*)"[^>]*>(.*?)</g>', re.S
)
_EDGE_PATH = re.compile(r"<path data-graph-edge[^>]*>")
_STATIC_LINK_LAYER = re.compile(r'<g data-static-link-layer="true">(.*?)</g>', re.S)
_STATIC_CLUSTER_LAYER = re.compile(r'<g data-static-cluster-layer="true">(.*?)</g>', re.S)
_LABEL_GROUP = re.compile(
    r'<g data-edge-label="([^"]*)"[^>]*?transform="translate\('
    + _NUM
    + r"\s+"
    + _NUM
    + r'\)"[^>]*>(.*?)</g>',
    re.S,
)
_RECT = re.compile(r"<rect\b([^>]*)>")
_TEXT = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)
_IMAGE = re.compile(r"<image\b([^>]*)>")
_USE = re.compile(r"<use\b([^>]*)>")
_ATTR = re.compile(r'([a-zA-Z:-]+)="([^"]*)"')
#: The provider mark, seated by both renderers in a band below the drawing.
_MARK_SVG = re.compile(r"<svg\b([^>]*\bdata-brand-mark\b[^>]*)>")
_STATUS_BLOCK = re.compile(r'<g data-status-block="[^"]*">(.*?)</g>', re.S)
_TEXT_HEAD = re.compile(r"<text\s([^>]*)>")
_VIEWBOX = re.compile(r'viewBox="' + _NUM + r"\s+" + _NUM + r"\s+" + _NUM + r"\s+" + _NUM + '"')
_TAG = re.compile(r"<[^>]+>")


def _attrs(raw: str) -> dict[str, str]:
    return dict(_ATTR.findall(raw))


def _num(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


class Box:
    """An axis-aligned box: what every check compares."""

    __slots__ = ("left", "top", "right", "bottom", "label")

    def __init__(
        self, left: float, top: float, right: float, bottom: float, label: str = ""
    ) -> None:
        self.left, self.top, self.right, self.bottom, self.label = left, top, right, bottom, label

    def overlaps(self, other: Box, slack: float = 0.0) -> bool:
        return (
            self.left + slack < other.right
            and self.right - slack > other.left
            and self.top + slack < other.bottom
            and self.bottom - slack > other.top
        )

    def contains_point(self, x: float, y: float, slack: float = 0.0) -> bool:
        return (
            self.left - slack <= x <= self.right + slack
            and self.top - slack <= y <= self.bottom + slack
        )

    def crossed_by(self, ax: float, ay: float, bx: float, by: float) -> bool:
        """Does the axis-aligned segment enter the box? Strict, so a wire may
        run along an edge (which is how it leaves and arrives)."""
        lo_x, hi_x = min(ax, bx), max(ax, bx)
        lo_y, hi_y = min(ay, by), max(ay, by)
        return lo_x < self.right and hi_x > self.left and lo_y < self.bottom and hi_y > self.top

    def inside(self, outer: Box, slack: float = 0.5) -> bool:
        return (
            self.left >= outer.left - slack
            and self.top >= outer.top - slack
            and self.right <= outer.right + slack
            and self.bottom <= outer.bottom + slack
        )


def _text_box(attrs: dict[str, str], text: str, dx: float = 0.0, dy: float = 0.0) -> Box | None:
    # measured as drawn: "&amp;" is one character on the page, not five
    content = unescape(_TAG.sub("", text)).strip()
    if not content:
        return None
    size = _num(attrs.get("font-size"), 12)
    # One advance for every face the editor uses; the sans and the mono both
    # measure close to 0.58 em per character at caption sizes.
    width = len(content) * size * 0.58
    x = _num(attrs.get("x")) + dx
    y = _num(attrs.get("y")) + dy
    anchor = attrs.get("text-anchor", "start")
    left = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
    return Box(left, y - size * 0.8, left + width, y + size * 0.25, content)


def _rect_box(attrs: dict[str, str], dx: float = 0.0, dy: float = 0.0) -> Box:
    x, y = _num(attrs.get("x")) + dx, _num(attrs.get("y")) + dy
    return Box(x, y, x + _num(attrs.get("width")), y + _num(attrs.get("height")))


def _polyline(d: str) -> list[tuple[float, float]]:
    """The corners a path visits. Q control points are the true corners the
    rounded joins bend around, so including them keeps every segment axis-
    aligned and lets the wire be checked as the polyline it really is."""
    points: list[tuple[float, float]] = []
    for command, body in re.findall(r"([MLQHVAmlhv])([^MLQHVAZmlhvz]*)", d):
        numbers = [float(n) for n in re.findall(_NUM, body)]
        last = points[-1] if points else (0.0, 0.0)
        if command in "ML" and len(numbers) >= 2:
            points.append((numbers[0], numbers[1]))
        elif command in "ml" and len(numbers) >= 2:
            points.append((last[0] + numbers[0], last[1] + numbers[1]))
        elif command == "Q" and len(numbers) >= 4:
            points.append((numbers[0], numbers[1]))
            points.append((numbers[2], numbers[3]))
        elif command == "A" and len(numbers) == 7:
            # Crossing hops have level endpoints; checking the underlying
            # straight run preserves orthogonal routing and endpoint checks.
            # Other arcs still produce a diagonal when their endpoints differ.
            points.append((numbers[5], numbers[6]))
        elif command == "H" and numbers:
            points.append((numbers[0], last[1]))
        elif command == "h" and numbers:
            points.append((last[0] + numbers[0], last[1]))
        elif command == "V" and numbers:
            points.append((last[0], numbers[0]))
        elif command == "v" and numbers:
            points.append((last[0], last[1] + numbers[0]))
    return points


def _crossing_boxes(d: str) -> tuple[list[Box], bool]:
    """Small semicircular hops retain their ink bounds and obstacle checks."""
    boxes: list[Box] = []
    invalid = False
    limit = float(render_metrics()["router"]["crossing_radius"])
    for match in re.finditer(r"A([^MLQHVAZ]*)", d):
        values = [float(number) for number in re.findall(_NUM, match[1])]
        before = _polyline(d[: match.start()])
        if len(values) != 7 or not before:
            invalid = True
            continue
        rx, ry, rotation, large, sweep, x, y = values
        ax, ay = before[-1]
        if not (
            0 < rx <= limit
            and abs(rx - ry) < 0.01
            and rotation == 0
            and large == 0
            and sweep in (0, 1)
            and abs(ay - y) < 0.01
            and abs(abs(x - ax) - 2 * rx) < 0.01
        ):
            invalid = True
            continue
        upper = (x > ax) == (sweep == 1)
        boxes.append(Box(min(ax, x), y - ry if upper else y, max(ax, x), y if upper else y + ry))
    return boxes, invalid


class Edge(TypedDict):
    """One drawn wire: the corners it visits, where its two ends point, and
    whether each end carries a head and the line a dash."""

    id: str
    points: list[tuple[float, float]]
    path: str
    start: tuple[float, float]
    end: tuple[float, float]
    marker_end: bool
    marker_start: bool
    dash: str


class Picture:
    """What the checker sees in an SVG, in absolute coordinates."""

    def __init__(self) -> None:
        self.view: Box | None = None
        self.nodes: dict[str, Box] = {}  # the card box, or the icon's hit box
        self.node_text: dict[str, list[Box]] = {}  # captions and glyphs a wire must not cross
        self.node_display: dict[str, str] = {}
        self.glyph_squares: dict[str, Box] = {}  # a bare glyph's whole artwork square
        self.ink_edges: dict[str, str] = {}  # where its ink begins along each side
        self.frame_titles: dict[str, Box] = {}
        #: a frame's corner badges (a subnet's NSG): each icon and each name
        self.frame_badges: list[Box] = []
        self.frames: dict[str, Box] = {}  # each frame's box
        self.mark: Box | None = None  # the provider mark, if drawn
        self.status: list[Box] = []  # the status lines above the drawing
        self.edges: list[Edge] = []
        self.labels: dict[str, Box] = {}
        self.static = False


def _read_badges(markup: str, picture: Picture) -> None:
    """A frame's corner badges in either renderer's markup: the icon (a
    ``use`` in the static picture, an ``image`` in the editor's) and its name."""
    for raw in [*_USE.findall(markup), *_IMAGE.findall(markup)]:
        if "data-frame-badge" in raw:
            box = _rect_box(_attrs(raw))
            box.label = "badge icon"
            picture.frame_badges.append(box)
    for raw, text in _TEXT.findall(markup):
        if "data-frame-badge-label" in raw:
            name = _text_box(_attrs(raw), text)
            if name:
                picture.frame_badges.append(name)


def read_picture(svg: str) -> Picture:
    picture = Picture()
    view = _VIEWBOX.search(svg)
    if view:
        x, y, w, h = (float(view.group(i)) for i in range(1, 5))
        picture.view = Box(x, y, x + w, y + h, "viewBox")
    mark = _MARK_SVG.search(svg)
    if mark:
        picture.mark = _rect_box(_attrs(mark.group(1)))
        picture.mark.label = "provider mark"
    # The status block's lines, as tall as their glyphs: a crop that starts
    # at the baseline's neighbourhood cuts the tops of the letters off.
    status = _STATUS_BLOCK.search(svg)
    for raw in _TEXT_HEAD.findall(status.group(1) if status else ""):
        attrs = _attrs(raw)
        size, x, base = _num(attrs.get("font-size"), 10), _num(attrs.get("x")), _num(attrs.get("y"))
        picture.status.append(Box(x, base - 0.8 * size, x + 1, base + 0.25 * size, "status line"))

    for head, node_id, display, dx, dy, body in _NODE_GROUP.findall(svg):
        dx, dy = float(dx), float(dy)
        boxes: list[Box] = []
        surface: Box | None = None
        for raw in _RECT.findall(body):
            attrs = _attrs(raw)
            if "data-node-surface" in raw:
                surface = _rect_box(attrs, dx, dy)
        insets = _ink_of(head)
        square: Box | None = None
        for raw in _IMAGE.findall(body):
            glyph = _rect_box(_attrs(raw), dx, dy)
            glyph.label = "glyph"
            square = square or Box(glyph.left, glyph.top, glyph.right, glyph.bottom, "glyph")
            boxes.append(_inked(glyph, insets))
        for raw, text in _TEXT.findall(body):
            box = _text_box(_attrs(raw), text, dx, dy)
            if box:
                boxes.append(box)
        if surface is None:
            continue
        picture.nodes[node_id] = surface
        picture.node_text[node_id] = boxes
        picture.node_display[node_id] = display
        edge_code = _INK_EDGE.search(head)
        if square is not None and edge_code and edge_code.group(1):
            picture.glyph_squares[node_id] = square
            picture.ink_edges[node_id] = edge_code.group(1)

    if not picture.nodes:
        # The static render the exporter falls back to without a browser.
        picture.static = True
        for insets_text, edge_text, node_id, display, body in _STATIC_NODE_GROUP.findall(svg):
            rects = [_rect_box(_attrs(raw)) for raw in _RECT.findall(body)]
            texts = [
                b for b in (_text_box(_attrs(raw), text) for raw, text in _TEXT.findall(body)) if b
            ]
            # The static picture draws artwork as <use>; it is a glyph box the
            # same way the editor's <image> is, for the wire rules below.
            insets = _ink_of(f'data-ink="{insets_text}"')
            for raw in _USE.findall(body):
                glyph = _rect_box(_attrs(raw))
                glyph.label = "glyph"
                if edge_text and node_id not in picture.glyph_squares:
                    picture.glyph_squares[node_id] = Box(
                        glyph.left, glyph.top, glyph.right, glyph.bottom, "glyph"
                    )
                    picture.ink_edges[node_id] = edge_text
                texts.append(_inked(glyph, insets))
            if rects:
                picture.nodes[node_id] = rects[0]
            elif texts:
                picture.nodes[node_id] = Box(
                    min(b.left for b in texts),
                    min(b.top for b in texts) - 52,
                    max(b.right for b in texts),
                    max(b.bottom for b in texts),
                )
            else:
                continue
            picture.node_text[node_id] = texts
            picture.node_display[node_id] = display
        cluster = _STATIC_CLUSTER_LAYER.search(svg)
        if cluster:
            titles = [
                (raw, text)
                for raw, text in _TEXT.findall(cluster.group(1))
                if "data-frame-badge-label" not in raw
            ]
            for index, (raw, text) in enumerate(titles):
                box = _text_box(_attrs(raw), text)
                if box:
                    picture.frame_titles[f"frame-{index}"] = box
            _read_badges(cluster.group(1), picture)
            # A frame's box is the rounded rect it fills; the 20 px tab rects
            # have no corner radius.
            frame_rects = [raw for raw in _RECT.findall(cluster.group(1)) if "rx=" in raw]
            for index, raw in enumerate(frame_rects):
                picture.frames[f"frame-{index}"] = _rect_box(_attrs(raw))
        link_layer = _STATIC_LINK_LAYER.search(svg)
        if link_layer:
            for raw in re.findall(r"<path\b[^>]*>", link_layer.group(1)):
                attrs = _attrs(raw)
                d = attrs.get("d", "")
                points = _polyline(d)
                if len(points) >= 2:
                    start, end = _tips(
                        points,
                        "marker-start" in attrs,
                        "marker-end" in attrs,
                        arrowhead_tip_clear(),
                    )
                    picture.edges.append(
                        {
                            "id": f"edge-{len(picture.edges) + 1}",
                            "path": d,
                            "points": points,
                            "start": start,
                            "end": end,
                            "marker_end": "marker-end" in attrs,
                            "marker_start": "marker-start" in attrs,
                            "dash": attrs.get("stroke-dasharray", ""),
                        }
                    )
            # a caption is the chip drawn behind its text, where there is one:
            # a numbered caption's text starts past its step circle, so the
            # text alone stands away from the wire the chip sits beside
            chips = [_rect_box(_attrs(raw)) for raw in _RECT.findall(link_layer.group(1))]
            for index, (raw, text) in enumerate(_TEXT.findall(link_layer.group(1))):
                # a step's number sits in its caption's chip: the caption, not a second one
                if "data-edge-step-number" in raw:
                    continue
                box = _text_box(_attrs(raw), text)
                if box:
                    middle_x, middle_y = (box.left + box.right) / 2, (box.top + box.bottom) / 2
                    chip = next(
                        (chip for chip in chips if chip.contains_point(middle_x, middle_y)), None
                    )
                    picture.labels[f"label-{index}"] = chip or box
        return picture

    for boundary_id, body in _BOUNDARY_GROUP.findall(svg):
        title: Box | None = None
        _read_badges(body, picture)
        for raw, text in _TEXT.findall(body):
            if "data-frame-badge-label" in raw:
                continue
            title = _text_box(_attrs(raw), text)
            if title:
                break
        for raw in _RECT.findall(body):
            attrs = _attrs(raw)
            if "data-boundary-surface" in raw:
                picture.frames[boundary_id] = _rect_box(attrs)
                continue
            if _num(attrs.get("width")) != 20:
                continue
            tab = _rect_box(attrs)
            title = (
                Box(
                    min(tab.left, title.left),
                    min(tab.top, title.top),
                    max(tab.right, title.right),
                    max(tab.bottom, title.bottom),
                    title.label,
                )
                if title
                else tab
            )
        if title:
            picture.frame_titles[boundary_id] = title

    for raw in _EDGE_PATH.findall(svg):
        attrs = _attrs(raw)
        points = _polyline(attrs.get("d", ""))
        if len(points) < 2:
            continue
        # The editor records the anchors; without them the tips are carried
        # on from the path's ends the way the static picture's are.
        tip_start, tip_end = _tips(
            points, "marker-start" in attrs, "marker-end" in attrs, arrowhead_tip_clear()
        )
        picture.edges.append(
            {
                "id": attrs.get("data-edge-id", f"edge-{len(picture.edges) + 1}"),
                "path": attrs.get("d", ""),
                "points": points,
                "start": (
                    _num(attrs.get("data-source-x"), tip_start[0]),
                    _num(attrs.get("data-source-y"), tip_start[1]),
                ),
                "end": (
                    _num(attrs.get("data-target-x"), tip_end[0]),
                    _num(attrs.get("data-target-y"), tip_end[1]),
                ),
                "marker_end": "marker-end" in attrs,
                "marker_start": "marker-start" in attrs,
                "dash": attrs.get("stroke-dasharray", ""),
            }
        )

    for edge_id, dx, dy, body in _LABEL_GROUP.findall(svg):
        dx, dy = float(dx), float(dy)
        for raw in _RECT.findall(body):
            if "edge-label-mask" in raw:
                picture.labels[edge_id] = _rect_box(_attrs(raw), dx, dy)
                break
    return picture


ANCHOR_TOLERANCE = 2.0
#: A wire this close to a frame's border, for this long, reads as part of
#: the border: the reader cannot tell which line is the frame.
FRAME_HUG = 3.0
FRAME_HUG_RUN = 24.0
#: A caption's chip farther than this from every wire names none of them.
CAPTION_REACH = 12.0
#: How far a frame's border must run through a caption's chip to cut it.
CAPTION_CUT = 2.0


def _hug_run(frame: Box, ax: float, ay: float, bx: float, by: float) -> float:
    """How far the segment runs along one of the frame's borders, within
    ``FRAME_HUG`` of it; 0 when it only crosses or keeps clear."""
    run = 0.0
    if abs(ay - by) < 0.5:
        along = min(max(ax, bx), frame.right) - max(min(ax, bx), frame.left)
        if any(abs(ay - edge) <= FRAME_HUG for edge in (frame.top, frame.bottom)):
            run = max(run, along)
    elif abs(ax - bx) < 0.5:
        along = min(max(ay, by), frame.bottom) - max(min(ay, by), frame.top)
        if any(abs(ax - edge) <= FRAME_HUG for edge in (frame.left, frame.right)):
            run = max(run, along)
    return run


def _cut_by_border(box: Box, frame: Box) -> bool:
    """Does one of the frame's borders run through the chip?"""
    level = box.right > frame.left and box.left < frame.right
    upright = box.bottom > frame.top and box.top < frame.bottom
    return (
        level
        and any(
            box.top + CAPTION_CUT < edge < box.bottom - CAPTION_CUT
            for edge in (frame.top, frame.bottom)
        )
    ) or (
        upright
        and any(
            box.left + CAPTION_CUT < edge < box.right - CAPTION_CUT
            for edge in (frame.left, frame.right)
        )
    )


def _reach(box: Box, ax: float, ay: float, bx: float, by: float) -> float:
    """How far the chip is from an axis-aligned segment; 0 when they touch."""
    dx = max(box.left - max(ax, bx), 0.0, min(ax, bx) - box.right)
    dy = max(box.top - max(ay, by), 0.0, min(ay, by) - box.bottom)
    return math.hypot(dx, dy)


#: The house arrowheads, shared with both renderers. A head's length is how
#: much straight wire must run under it; its frame is what every marker in a
#: picture must match.
ARROWHEADS = _ASSETS_OR_FIRST / "catalog" / "arrowheads.json"
_MARKER = re.compile(r"<marker\b([^>]*)>")


def arrowhead_spec() -> dict | None:
    """The shared spec, or None when it is not beside this script."""
    try:
        data = json.loads(ARROWHEADS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("heads"), dict) else None


def arrowhead_length(name: str = "triangle") -> float:
    spec = arrowhead_spec()
    if spec is None:
        return 7.0
    entry = spec["heads"].get(name) or spec["heads"].get(spec.get("default", "triangle")) or {}
    return float(entry.get("length", 7.0))


def arrowhead_tip_clear() -> float:
    """How far short of the tip a headed wire stops; the tip is that far on."""
    spec = arrowhead_spec()
    return float(spec.get("tip_clear", 2.0)) if spec is not None else 2.0


def _tips(
    points: list[tuple[float, float]], marker_start: bool, marker_end: bool, clear: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Where a wire's heads actually point: the path's ends, carried on by
    the tip clearance along the end segments when a head is there."""

    def carried(end: tuple[float, float], back: tuple[float, float] | None) -> tuple[float, float]:
        if back is None or clear <= 0:
            return end
        dx, dy = end[0] - back[0], end[1] - back[1]
        span = abs(dx) + abs(dy)
        if span < 0.01:
            return end
        return (end[0] + dx / span * clear, end[1] + dy / span * clear)

    start = carried(points[0], _next_point(points, True)) if marker_start else points[0]
    end = carried(points[-1], _next_point(points, False)) if marker_end else points[-1]
    return start, end


def _head_name(marker_id: str) -> str:
    """Which head a marker id names: the editor's suffixes, else the default."""
    for name in ("open", "circle", "diamond"):
        if f"-{name}" in marker_id:
            return name
    return "triangle"


def _marker_problem(attrs: dict[str, str], spec: dict) -> str | None:
    """Why a marker is not the house head, or None when it is: fixed size,
    the spec's frame, tip exactly at the wire's end."""
    head = (
        spec["heads"].get(_head_name(attrs.get("id", "")))
        or spec["heads"][spec.get("default", "triangle")]
    )
    length, width = float(head["length"]), float(head["width"])
    found = {
        "markerUnits": attrs.get("markerUnits", "strokeWidth"),
        "markerWidth": _num(attrs.get("markerWidth"), 0.0),
        "markerHeight": _num(attrs.get("markerHeight"), 0.0),
        "refX": _num(attrs.get("refX"), 0.0),
        "refY": _num(attrs.get("refY"), 0.0),
    }
    wanted = {
        "markerUnits": "userSpaceOnUse",
        "markerWidth": length,
        "markerHeight": width,
        "refX": length - float(spec.get("tip_clear", 0)),
        "refY": width / 2,
    }
    if all(found[key] == wanted[key] for key in wanted):
        return None
    diff = ", ".join(
        f"{key} {found[key]!r} (spec {wanted[key]!r})"
        for key in wanted
        if found[key] != wanted[key]
    )
    return diff


def _on_edge(value: float, edge: float) -> bool:
    return abs(value - edge) <= ANCHOR_TOLERANCE


def _within(value: float, low: float, high: float) -> bool:
    return low - ANCHOR_TOLERANCE <= value <= high + ANCHOR_TOLERANCE


def _sides_met(picture: Picture, node_id: str, x: float, y: float) -> tuple[list[str], str]:
    """The drawn sides of ``node_id`` a wire end at (x, y) touches, with the
    complaint to make when it touches none. Cards: the box edge. Bare glyphs:
    the glyph's left, right or top edge, or the node's underside beneath the
    caption."""
    box = picture.nodes[node_id]
    if picture.node_display.get(node_id) == "icon":
        glyph = next((b for b in picture.node_text.get(node_id, []) if b.label == "glyph"), None)
        if glyph is None:
            return ["any"], ""  # artwork missing: nothing drawn to hold the wire to
        edges = {"left": glyph.left, "right": glyph.right, "top": glyph.top, "bottom": box.bottom}
        # A glyph that carries its edge lines is met where its ink begins on
        # the line through the end: a link is seated on the drawing, which
        # on a round or uneven mark lies inside the box.
        for side, along in (("left", y), ("right", y), ("top", x)):
            seated = _seat_line(picture, node_id, side, along)
            if seated is not None:
                edges[side] = seated
        span_y, span_x = (glyph.top, glyph.bottom), (glyph.left, glyph.right)
        complaint = (
            f"in empty air at ({x:g}, {y:g}); a bare glyph is met on its drawing "
            f"({glyph.left:g}-{glyph.right:g} x {glyph.top:g}-{glyph.bottom:g}) or beneath its caption (y {box.bottom:g})"
        )
    else:
        edges = {"left": box.left, "right": box.right, "top": box.top, "bottom": box.bottom}
        span_y, span_x = (box.top, box.bottom), (box.left, box.right)
        complaint = f"at ({x:g}, {y:g}), not at the card's edge ({box.left:g}-{box.right:g} x {box.top:g}-{box.bottom:g})"
    sides = [side for side in ("left", "right") if _on_edge(x, edges[side]) and _within(y, *span_y)]
    sides += [
        side for side in ("top", "bottom") if _on_edge(y, edges[side]) and _within(x, *span_x)
    ]
    return sides, complaint


def _seat_line(picture: Picture, node_id: str, side: str, along: float) -> float | None:
    """Where a bare glyph's ink begins on ``side`` on the line through
    ``along`` (a y for left and right, an x for top), in picture
    coordinates; None when the node carries no edge lines there."""
    code = picture.ink_edges.get(node_id)
    square = picture.glyph_squares.get(node_id)
    if not code or square is None:
        return None
    size = square.right - square.left
    if size <= 0:
        return None
    if side in ("left", "right"):
        depth = _edge_depth(code, side, (along - square.top) / size)
        if depth is None:
            return None
        return square.left + depth * size if side == "left" else square.right - depth * size
    depth = _edge_depth(code, "top", (along - square.left) / size)
    return None if depth is None else square.top + depth * size


def _without_lead_ins(
    picture: Picture, points: list[tuple[float, float]], source: str | None, target: str | None
) -> list[tuple[float, float]]:
    """The wire as judged for crossings. A link is seated on its own glyph's
    drawing, which can lie inside the glyph's box; the stretch from the box's
    edge in to that seat runs along the link's own line through air (rule 1),
    so it is not a crossing of the glyph. An end inside its own glyph box is
    moved back to where the wire enters the box."""
    if len(points) < 2:
        return points
    trimmed = list(points)
    for index, neighbour, node_id in ((0, 1, source), (-1, -2, target)):
        if node_id is None or picture.node_display.get(node_id) != "icon":
            continue
        glyph = next((b for b in picture.node_text.get(node_id, []) if b.label == "glyph"), None)
        if glyph is None:
            continue
        (x, y), (nx, ny) = trimmed[index], trimmed[neighbour]
        if not (glyph.left < x < glyph.right and glyph.top < y < glyph.bottom):
            continue
        if abs(ny - y) <= 0.5:
            x = glyph.right if nx > x else glyph.left
        else:
            y = glyph.bottom if ny > y else glyph.top
        trimmed[index] = (x, y)
    return trimmed


def _straight_out(side: str, x: float, y: float, nx: float, ny: float) -> bool:
    """Does the segment from a wire end (x, y) to the wire's next point
    (nx, ny) run straight out of ``side``: perpendicular to it, heading away?"""
    if side == "any":
        return True
    if side in ("left", "right"):
        return abs(ny - y) <= ANCHOR_TOLERANCE and (nx < x if side == "left" else nx > x)
    return abs(nx - x) <= ANCHOR_TOLERANCE and (ny < y if side == "top" else ny > y)


def _next_point(points: list[tuple[float, float]], from_start: bool) -> tuple[float, float] | None:
    """The wire's first point away from the end being judged."""
    end = points[0] if from_start else points[-1]
    ordered = points[1:] if from_start else points[-2::-1]
    return next(
        (p for p in ordered if abs(p[0] - end[0]) > 0.01 or abs(p[1] - end[1]) > 0.01), None
    )


def _anchor_problem(
    picture: Picture, node_id: str, x: float, y: float, neighbour: tuple[float, float] | None = None
) -> str | None:
    """Why a wire end at (x, y) does not meet the drawn shape of ``node_id``
    squarely, or None when it does. It must touch a drawn side (rule 1) and,
    given the wire's next point, run straight out of that side (rule 8)."""
    sides, complaint = _sides_met(picture, node_id, x, y)
    if not sides:
        return complaint
    if neighbour is None or any(_straight_out(side, x, y, *neighbour) for side in sides):
        return None
    return (
        f"at ({x:g}, {y:g}) sideways: the wire runs along the {'/'.join(sides)} edge toward "
        f"({neighbour[0]:g}, {neighbour[1]:g}) instead of straight out of it"
    )


def _endpoints_of(picture: Picture, edge: Edge) -> tuple[str | None, str | None]:
    """The nodes a wire leaves and arrives at, found from where it touches."""

    def owner(point: tuple[float, float]) -> str | None:
        for node_id, box in picture.nodes.items():
            if box.contains_point(point[0], point[1], slack=2.5):
                return node_id
        return None

    return owner(edge["start"]), owner(edge["end"])


#: Size presets that make no promise about the finished box, so a card is
#: free to grow to its own text. Every other preset fixes the picture's size
#: and truncates instead; see exports/presets.py.
_FITTING_SIZES = frozenset({"fit"})


def _grows_to_fit(project: dict | None) -> bool:
    """Was this picture drawn at a size that lets a card grow to its text?

    Unknown documents are treated as fitting: a picture checked on its own,
    with no document beside it, should still have its text read.
    """
    if not isinstance(project, dict):
        return True
    presentation = project.get("presentation")
    if not isinstance(presentation, dict):
        return True
    return str(presentation.get("size", "fit")) in _FITTING_SIZES


def _growth_ceilings() -> dict[str, float]:
    """How wide each kind of component may grow before it truncates by design."""
    metrics = render_metrics()
    out: dict[str, float] = {}
    for display, key in (("card", "card"), ("icon", "icon_node")):
        try:
            out[display] = float((metrics.get(key) or {}).get("max_width") or 0)
        except (TypeError, ValueError):
            out[display] = 0.0
    return out


def check_svg(svg: str, errors: list[str], project: dict | None = None) -> dict[str, object]:
    """Read the picture and report what an eye would object to."""
    # A picture is data, not a program. The editor page is allowed its own
    # scripts because it is one; a picture carrying a script, a handler or a
    # link to another server would run or call out on the machine of whoever
    # was sent it.
    _check_markup_safety(svg, errors)
    picture = read_picture(svg)
    summary: dict[str, object] = {
        "nodes": len(picture.nodes),
        "frames": len(picture.frame_titles),
        "connectors": len(picture.edges),
        "labels": len(picture.labels),
        "checks": 0,
    }
    if not picture.nodes:
        errors.append("no components found in the SVG; is this an infragram export?")
        return summary
    checks = 0

    # 1. Wires are orthogonal: every segment runs along one axis.
    for edge in picture.edges:
        points = edge["points"]
        for (ax, ay), (bx, by) in zip(points, points[1:], strict=False):
            checks += 1
            if abs(ax - bx) > 0.5 and abs(ay - by) > 0.5:
                errors.append(
                    f"connector {edge['id']} has a diagonal segment ({ax:g},{ay:g})-({bx:g},{by:g})"
                )
                break

    # Hops are intentional curves, but their ink must still clear obstacles.
    for edge in picture.edges:
        bridges, invalid = _crossing_boxes(edge.get("path", ""))
        if invalid:
            errors.append(f"connector {edge['id']} has an unsupported crossing arc")
        for bridge in bridges:
            obstacles = [box for boxes in picture.node_text.values() for box in boxes]
            obstacles += [
                box
                for node, box in picture.nodes.items()
                if picture.node_display.get(node) != "icon"
            ]
            obstacles += list(picture.frame_titles.values()) + picture.frame_badges
            obstacles += list(picture.labels.values())
            checks += len(obstacles) + 1
            if any(bridge.overlaps(box) for box in obstacles):
                errors.append(
                    f"connector {edge['id']} has a crossing bridge overlapping an obstacle"
                )
            if picture.view and (
                bridge.left < picture.view.left
                or bridge.right > picture.view.right
                or bridge.top < picture.view.top
                or bridge.bottom > picture.view.bottom
            ):
                errors.append(f"connector {edge['id']} has a crossing bridge outside the picture")

    # 2. A wire never runs through text, a glyph, a frame title, or a card
    #    it does not belong to.
    for edge in picture.edges:
        source, target = _endpoints_of(picture, edge)
        points = _without_lead_ins(picture, edge["points"], source, target)
        seen: set[str] = set()
        for (ax, ay), (bx, by) in zip(points, points[1:], strict=False):
            for node_id, boxes in picture.node_text.items():
                for box in boxes:
                    checks += 1
                    if box.crossed_by(ax, ay, bx, by):
                        what = "glyph" if box.label == "glyph" else f"text ({box.label!r})"
                        message = f"connector {edge['id']} runs through the {what} of {node_id!r}"
                        if message not in seen:
                            seen.add(message)
                            errors.append(message)
            for frame_id, title in picture.frame_titles.items():
                checks += 1
                if title.crossed_by(ax, ay, bx, by):
                    message = f"connector {edge['id']} runs through the title of frame {frame_id!r} ({title.label!r})"
                    if message not in seen:
                        seen.add(message)
                        errors.append(message)
            for badge in picture.frame_badges:
                checks += 1
                if badge.crossed_by(ax, ay, bx, by):
                    message = f"connector {edge['id']} runs through a frame's corner badge ({badge.label!r})"
                    if message not in seen:
                        seen.add(message)
                        errors.append(message)
            for node_id, box in picture.nodes.items():
                if node_id in (source, target) or picture.node_display.get(node_id) == "icon":
                    continue
                checks += 1
                if box.crossed_by(ax, ay, bx, by):
                    message = f"connector {edge['id']} cuts through the card {node_id!r}"
                    if message not in seen:
                        seen.add(message)
                        errors.append(message)

    # 2b. A wire touches what is drawn (ADR 0006). Each end of a connector
    #     meets its node at the card's edge, or -- for a bare glyph -- at the
    #     glyph's own left, right or top edge, or at the node's underside
    #     beneath the caption. Never the empty air of the invisible layout box.
    #     And it meets that side squarely: the segment at either end runs
    #     straight out of the side, never along it (rule 8).
    for edge in picture.edges:
        source, target = _endpoints_of(picture, edge)
        points = edge["points"]
        for end_id, point, neighbour, verb in (
            (source, edge["start"], _next_point(points, True), "leaves"),
            (target, edge["end"], _next_point(points, False), "arrives at"),
        ):
            if end_id is None:
                continue
            x, y = point
            checks += 1
            problem = _anchor_problem(picture, end_id, x, y, neighbour)
            if problem:
                errors.append(f"connector {edge['id']} {verb} {end_id!r} {problem}")

    # 2c. A head sits on a straight shaft (rule 9). The last segment of a
    #     headed wire -- the first, for a head at the start -- is at least an
    #     arrowhead long, so a bend never runs into the head.
    for edge in picture.edges:
        points = edge["points"]
        source, target = _endpoints_of(picture, edge)
        for headed, from_start, end_id, verb in (
            (edge["marker_end"], False, target, "arrives at"),
            (edge["marker_start"], True, source, "leaves"),
        ):
            if not headed:
                continue
            end = points[0] if from_start else points[-1]
            neighbour = _next_point(points, from_start)
            if neighbour is None:
                continue
            checks += 1
            run = abs(neighbour[0] - end[0]) + abs(neighbour[1] - end[1])
            if run + ANCHOR_TOLERANCE < arrowhead_length():
                errors.append(
                    f"connector {edge['id']} {verb} {end_id or 'its end'!r} with its arrowhead on a bend: "
                    f"{run:g} px of straight wire under a {arrowhead_length():g} px head"
                )

    # 2d. Every arrowhead is the house head (rule 9): the marker's frame is
    #     the spec's, it is a fixed size whatever the stroke, and its tip sits
    #     exactly at the wire's end. A picture drawn with any other head fails.
    spec = arrowhead_spec()
    if spec is not None:
        for raw in _MARKER.findall(svg):
            attrs = _attrs(raw)
            marker_id = attrs.get("id", "")
            if not (
                marker_id.startswith("infragram-editor-arrow") or marker_id.startswith("arrow-")
            ):
                continue
            checks += 1
            problem = _marker_problem(attrs, spec)
            if problem:
                errors.append(f"arrowhead marker {marker_id!r} is not the house head: {problem}")

    # 3. Captions sit clear of each other, of cards and glyphs, and of titles.
    labels = list(picture.labels.items())
    for index, (edge_id, box) in enumerate(labels):
        for other_id, other in labels[index + 1 :]:
            checks += 1
            if box.overlaps(other, slack=1.0):
                errors.append(f"captions of connectors {edge_id} and {other_id} overlap")
        for node_id, boxes in picture.node_text.items():
            for text in boxes:
                checks += 1
                if box.overlaps(text, slack=1.0):
                    errors.append(
                        f"caption of connector {edge_id} covers {node_id!r} ({text.label!r})"
                    )
                    break
        for frame_id, title in picture.frame_titles.items():
            checks += 1
            if box.overlaps(title, slack=1.0):
                errors.append(
                    f"caption of connector {edge_id} covers the title of frame {frame_id!r}"
                )
        for badge in picture.frame_badges:
            checks += 1
            if box.overlaps(badge, slack=1.0):
                errors.append(
                    f"caption of connector {edge_id} covers a frame's corner badge ({badge.label!r})"
                )

    # 3b. A caption is read as part of a wire, never of a frame: no border
    #     runs through its chip, and its chip sits beside a wire. The picture
    #     does not say which wire a caption names, so the nearest one stands
    #     in for it; a caption far from every wire names none.
    segments = [
        segment
        for edge in picture.edges
        for segment in zip(edge["points"], edge["points"][1:], strict=False)
    ]
    for edge_id, box in labels:
        for frame_id, frame in picture.frames.items():
            checks += 1
            if _cut_by_border(box, frame):
                errors.append(
                    f"caption of connector {edge_id} sits on the border of frame {frame_id!r}"
                )
                break
        if segments:
            checks += 1
            reach = min(_reach(box, ax, ay, bx, by) for (ax, ay), (bx, by) in segments)
            if reach > CAPTION_REACH:
                errors.append(
                    f"caption of connector {edge_id} stands {reach:.0f} px from the nearest wire"
                )

    # 3c. A wire keeps off the frames' borders: one running along a border
    #     reads as the border, and the frame's outline as a wire.
    for edge in picture.edges:
        points = edge["points"]
        for frame_id, frame in picture.frames.items():
            checks += 1
            run = max(
                (
                    _hug_run(frame, ax, ay, bx, by)
                    for (ax, ay), (bx, by) in zip(points, points[1:], strict=False)
                ),
                default=0.0,
            )
            if run >= FRAME_HUG_RUN:
                errors.append(
                    f"connector {edge['id']} runs {run:.0f} px along the border of frame {frame_id!r}"
                )

    # 4. Components do not sit on each other.
    nodes = list(picture.nodes.items())
    for index, (node_id, box) in enumerate(nodes):
        for other_id, other in nodes[index + 1 :]:
            checks += 1
            if box.overlaps(other, slack=2.0):
                errors.append(f"components {node_id!r} and {other_id!r} overlap")

    # 5. Everything is inside the picture.
    if picture.view:
        for node_id, box in picture.nodes.items():
            checks += 1
            if not box.inside(picture.view):
                errors.append(f"component {node_id!r} lies outside the viewBox")
        for edge_id, box in picture.labels.items():
            checks += 1
            if not box.inside(picture.view):
                errors.append(f"caption of connector {edge_id} lies outside the viewBox")
        for box in picture.status:
            checks += 1
            if not box.inside(picture.view):
                errors.append("the status line above the drawing is cut off by the viewBox")
        for edge in picture.edges:
            checks += 1
            if any(not picture.view.contains_point(x, y, slack=0.5) for x, y in edge["points"]):
                errors.append(f"connector {edge['id']} runs outside the viewBox")

    # 6. With the document beside it: every connection is drawn once, with the
    #    arrowheads and line the document asked for.
    if project and not picture.static:
        elements = _index(project.get("topology"))
        wanted: dict[tuple[str, str], list[dict]] = {}
        for element_id, element in elements.items():
            for connection in element.get("connections") or []:
                if isinstance(connection, dict) and isinstance(connection.get("target"), str):
                    wanted.setdefault((element_id, connection["target"]), []).append(connection)
        # A wire aimed at a frame is drawn to a card inside it (the one nearest
        # the other end, compose.md), so an end the document aims at a frame
        # may sit on any card drawn within it. A connection between two cards
        # is matched first, so it is never mistaken for a frame's.
        # Keyed by the ends a drawn wire is found to have, and an end that
        # touches no card has none: such a pair is looked up and never found.
        seated: dict[tuple[str | None, str | None], tuple[str, str]] = {
            pair: pair for pair in wanted
        }
        for a, b in wanted:
            for s in _drawn_within(elements.get(a), picture.nodes) or [a]:
                for t in _drawn_within(elements.get(b), picture.nodes) or [b]:
                    seated.setdefault((s, t), (a, b))
        summary["project"] = project.get("slug", "document")
        dashes = link_dashes_for(project)
        connection_count = sum(len(connections) for connections in wanted.values())
        remaining = {pair: list(connections) for pair, connections in wanted.items()}
        checks += 1
        if len(picture.edges) != connection_count:
            errors.append(
                f"the document declares {connection_count} connections but the picture draws {len(picture.edges)}"
            )
        for edge in picture.edges:
            source, target = _endpoints_of(picture, edge)
            pair = seated.get((source, target))
            reversed_ = pair is None
            if reversed_:
                pair = seated.get((target, source))
            candidates = remaining.get(pair, []) if pair is not None else []
            has_end, has_start = bool(edge["marker_end"]), bool(edge["marker_start"])
            if reversed_:
                has_end, has_start = has_start, has_end

            # Parallel data and DNS flows share endpoints, but each declaration
            # is matched once. SVG path order need not be document order.
            def matches(
                connection: dict,
                drawn_heads: tuple[bool, bool] = (has_end, has_start),
                drawn_dash: bool = bool(edge["dash"]),
            ) -> bool:
                heads = {"forward": (True, False), "both": (True, True), "none": (False, False)}
                return (
                    heads.get(connection.get("direction", "forward"), (True, False))
                    == (drawn_heads)
                    and bool(dashes.get(connection.get("kind", "solid"))) == drawn_dash
                )

            match = next((index for index, item in enumerate(candidates) if matches(item)), 0)
            connection = candidates.pop(match) if candidates else None
            checks += 1
            if connection is None:
                errors.append(
                    f"connector {edge['id']} joins {source!r} and {target!r}, which the document does not connect"
                )
                continue
            direction = connection.get("direction", "forward")
            expected = {"forward": (True, False), "both": (True, True), "none": (False, False)}.get(
                direction, (True, False)
            )
            checks += 1
            if (bool(has_end), bool(has_start)) != expected:
                errors.append(
                    f"connector {edge['id']} ({source} -> {target}) has arrowheads for {direction!r} wrong"
                )
            # A connector is dashed exactly when its kind has a dash in the
            # provider's link table (built-in dotted/dashed, then the theme).
            kind = connection.get("kind", "solid")
            dashed = bool(edge["dash"])
            checks += 1
            if bool(dashes.get(kind)) != dashed:
                errors.append(
                    f"connector {edge['id']} ({source} -> {target}) is drawn {'dashed' if dashed else 'solid'} but the document says {kind!r}"
                )

    # 7. The provider mark stands in its own band: no frame, card, caption or
    #    wire touches it, and it is inside the picture.
    if picture.mark is not None:
        mark = picture.mark
        for frame_id, box in picture.frames.items():
            checks += 1
            if mark.overlaps(box):
                errors.append(f"provider mark overlaps frame {frame_id!r}")
        for node_id, box in picture.nodes.items():
            checks += 1
            if mark.overlaps(box):
                errors.append(f"provider mark overlaps component {node_id!r}")
        for label_id, box in picture.labels.items():
            checks += 1
            if mark.overlaps(box):
                errors.append(f"provider mark overlaps the caption of connector {label_id}")
        for edge in picture.edges:
            points = edge["points"]
            for (ax, ay), (bx, by) in zip(points, points[1:], strict=False):
                checks += 1
                if mark.crossed_by(ax, ay, bx, by):
                    errors.append(f"connector {edge['id']} runs through the provider mark")
                    break
        checks += 1
        if picture.view is not None and not mark.inside(picture.view):
            errors.append("provider mark lies outside the viewBox")

    # 8. No text is cut. A card is sized for its own name and detail line, so
    #    an ellipsis in a finished picture means the layout and the renderer
    #    disagreed about how much room that text needed. Nobody reviewing a
    #    diagram notices one missing character; the reader who needs the name
    #    does. Three roundings used to disagree here, each losing a fraction
    #    of a pixel the same way (builders/scene.py, builders/render.py).
    #
    #    Only where the card was free to grow. A fixed size preset is a
    #    promise that the picture fits a given box (exports/presets.py), and
    #    there a long name truncates by contract rather than by mistake --
    #    flagging that would be reporting the preset the author chose.
    if _grows_to_fit(project):
        caps = _growth_ceilings()
        for node_id, boxes in picture.node_text.items():
            card = picture.nodes.get(node_id)
            cap = caps.get(str(picture.node_display.get(node_id) or "card"))
            # At the ceiling the cut is deliberate: a box grows only so far
            # before one long name would sprawl across the whole picture.
            if card is not None and cap and (card.right - card.left) >= cap - 0.5:
                continue
            for text in boxes:
                if text.label == "glyph":
                    continue
                checks += 1
                if "…" in str(text.label):
                    errors.append(
                        f"component {node_id!r} is drawn with its text cut: {str(text.label)!r}"
                    )
        for frame_id, title in picture.frame_titles.items():
            checks += 1
            if "…" in str(title.label):
                errors.append(
                    f"frame {frame_id!r} is drawn with its title cut: {str(title.label)!r}"
                )

    summary["checks"] = checks
    return summary


def _drawn_within(element: object, drawn: dict[str, Box]) -> list[str]:
    """The ids drawn for ``element`` or inside it: one for a card, the cards
    a wire aimed at a frame may sit on for a frame."""
    found: list[str] = []

    def walk(item: object) -> None:
        if not isinstance(item, dict):
            return
        if isinstance(item.get("id"), str) and item["id"] in drawn:
            found.append(item["id"])
        for child in item.get("children") or []:
            walk(child)

    walk(element)
    return found


def _index(topology: object) -> dict[str, dict]:
    found: dict[str, dict] = {}

    def walk(element: object) -> None:
        if not isinstance(element, dict):
            return
        if isinstance(element.get("id"), str):
            found[element["id"]] = element
        for child in element.get("children") or []:
            walk(child)

    walk(topology)
    return found


def _embedded_project(page: Path) -> dict | None:
    """The project document an exported page carries, or None."""
    try:
        match = EMBEDDED_PROJECT.search(page.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    if match is None:
        return None
    for raw in (match.group(1), unescape(match.group(1))):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        return payload if isinstance(payload, dict) else None
    return None


def _sibling_project(svg_path: Path) -> dict | None:
    """The document a picture was drawn from: the ``<slug>.infragram.json``
    written beside it, else the project its ``<slug>.html`` page embeds.

    An export writes the page by default and the document only when asked,
    so without the page the picture would be checked without its document:
    no comparison of connections, arrowheads or line kinds.
    """
    stems = [svg_path.stem]
    if svg_path.stem.endswith("-icons"):
        stems.append(svg_path.stem[: -len("-icons")])
    for stem in stems:
        candidate = svg_path.with_name(f"{stem}.infragram.json")
        if candidate.is_file():
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                return payload
    for stem in stems:
        page = svg_path.with_name(f"{stem}.html")
        if page.is_file():
            payload = _embedded_project(page)
            if payload is not None:
                return payload
    return None


def _check_png(path: Path) -> tuple[bool, str]:
    """A PNG is checked to be one, and its size reported."""
    try:
        with path.open("rb") as handle:
            head = handle.read(24)
    except OSError as error:
        return False, f"FAIL {path}: cannot read file ({error})"
    if len(head) < 24 or not head.startswith(PNG_SIGNATURE) or head[12:16] != b"IHDR":
        return False, f"FAIL {path}: not a PNG image"
    width, height = struct.unpack(">II", head[16:24])
    return True, f"OK {path}: PNG image, {width} x {height} px"


def check_path(path: Path) -> tuple[bool, str]:
    report = inspect_path(path)
    return bool(report["ok"]), str(report["message"])


def inspect_path(path: Path) -> dict[str, object]:
    """Check one file and say so as data: ``ok``, ``kind`` (``project``,
    ``page``, ``picture``, ``png`` or ``other``), every ``problem``, the
    ``summary`` counts, and the one-line ``message`` the report prints."""
    suffix = path.suffix.casefold()
    kind = (
        "png"
        if suffix == ".png"
        else "page"
        if suffix in (".html", ".htm")
        else "picture"
        if suffix == ".svg"
        else "project"
        if suffix == ".json"
        else "other"
    )
    report: dict[str, object] = {
        "path": str(path),
        "kind": kind,
        "ok": False,
        "problems": [],
        "summary": {},
        "message": "",
    }

    def failed(message: str, problems: list[str]) -> dict[str, object]:
        report.update(message=message, problems=problems)
        return report

    if suffix == ".png":
        ok, message = _check_png(path)
        report.update(ok=ok, message=message, problems=[] if ok else [message.split(": ", 1)[-1]])
        return report
    if suffix == ".py":
        # the package reads a diagram file without running it; this script
        # stands alone, so it says what to check instead
        return failed(
            f"FAIL {path}: a Python diagram file, not a document; `compose` it "
            "with --verify, or check the files compose wrote",
            ["a Python diagram file, not a document"],
        )
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return failed(f"FAIL {path}: cannot read file ({error})", [f"cannot read file ({error})"])

    if kind == "page":
        summary = check_html(text, errors)
    elif kind == "picture":
        project = _sibling_project(path)
        summary = check_svg(text, errors, project)
    else:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            return failed(f"FAIL {path}: not valid JSON ({error})", [f"not valid JSON ({error})"])
        summary = check_project(payload, errors)
        check_components(payload, errors)
        check_nesting(payload, errors)
    report["summary"] = summary

    if errors:
        details = "\n".join(f"  - {error}" for error in errors[:20])
        more = f"\n  ... {len(errors) - 20} more" if len(errors) > 20 else ""
        return failed(f"FAIL {path}: {len(errors)} problem(s)\n{details}{more}", list(errors))
    report["ok"] = True
    if "connectors" in summary:
        report["message"] = (
            f"OK {path}: picture - {summary['nodes']} components, {summary['frames']} frames, "
            f"{summary['connectors']} connectors, {summary['labels']} captions, "
            f"{summary['checks']} checks, no collisions"
            + (f", matches {summary['project']}" if summary.get("project") else "")
        )
        return report
    # check_project fills this with the slugs it read; the summary's values
    # are mixed, so the checker is told which one this is
    providers = ", ".join(cast("list[str]", summary["providers"])) or "none"
    report["message"] = (
        f"OK {path}: project {summary['slug']} - {summary['elements']} elements, "
        f"{summary['connections']} connections, providers {providers}"
    )
    return report


def utf8_output() -> None:
    """Write UTF-8 to a pipe as well as to a console. A Windows pipe, which is
    how an agent reads the report, defaults to cp1252: it cannot encode a
    label in another script, and the report would stop at a traceback."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if reconfigure is not None and encoding != "utf8":
            reconfigure(encoding="utf-8", errors="backslashreplace")


def main(argv: list[str] | None = None) -> int:
    utf8_output()
    parser = argparse.ArgumentParser(
        prog="infragram check",
        description="Check project documents, exported pages and pictures.",
        epilog="Exit status is 0 when every file passes and 1 otherwise.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=Path,
        help="documents (.infragram.json), pages (.html), pictures (.svg, .png), "
        "or folders of them",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print one JSON document instead of the report: every file's path, kind, "
        "ok, problems and summary counts",
    )
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)
    failed = False
    files: list[Path] = []
    reports: list[dict[str, object]] = []
    for path in options.paths:
        if not path.is_dir():
            files.append(path)
            continue
        found = sorted(
            entry
            for entry in path.iterdir()
            if entry.is_file() and entry.suffix.casefold() in CHECKED_SUFFIXES
        )
        if not found:
            message = f"FAIL {path}: no documents, pages or pictures in this folder"
            reports.append(
                {
                    "path": str(path),
                    "kind": "folder",
                    "ok": False,
                    "message": message,
                    "problems": ["no documents, pages or pictures in this folder"],
                    "summary": {},
                }
            )
            if not options.json:
                print(message)
            failed = True
        files.extend(found)
    for path in files:
        report = inspect_path(path)
        reports.append(report)
        if not options.json:
            print(report["message"])
        failed = failed or not report["ok"]
    if options.json:
        print(json.dumps({"ok": not failed, "files": reports}, indent=1, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
