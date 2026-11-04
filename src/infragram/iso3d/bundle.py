"""The 3D builder as one classic script, for the editor page.

``scene.js`` and its vendored three.js are ES modules, and a module script
cannot be loaded from a page opened as a file. The editor export is such a
page, so it carries the builder inline as a classic script: the three.js
module as a function whose result is the ``THREE`` namespace, the room
environment as a function of it, and the scene as a function of both, each
in its own scope so their top-level names never meet. ``window.iso3d`` comes
out the same as the render page's.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
LIB = HERE / "lib"

_EXPORT_LIST = re.compile(r"^export \{([^}]*)\};?[ \t]*$", re.MULTILINE)
_IMPORT = re.compile(r"^import\s[^;]*?from\s+'[^']+';[ \t]*$", re.MULTILINE | re.DOTALL)
_EXPORT_NAMES = re.compile(r"^export \{\s*([\w, ]+)\s*\};?[ \t]*$", re.MULTILINE)
NL = "\n"


def _namespace(members: str) -> str:
    """``a, b as c`` -> ``a, c: b`` for an object literal."""
    parts = []
    for member in members.split(","):
        member = member.strip()
        if not member:
            continue
        if " as " in member:
            name, alias = (piece.strip() for piece in member.split(" as ", 1))
            parts.append(f"{alias}: {name}")
        else:
            parts.append(member)
    return ", ".join(parts)


def three_as_namespace(source: str) -> str:
    """three.module.js as a function whose result is the ``THREE`` namespace."""
    matches = list(_EXPORT_LIST.finditer(source))
    if len(matches) != 1:
        raise ValueError(f"expected one export list in three.module.js, found {len(matches)}")
    match = matches[0]
    body = (
        source[: match.start()]
        + "return { "
        + _namespace(match.group(1))
        + " };"
        + source[match.end() :]
    )
    return "const THREE = (function () {" + NL + body + NL + "})();"


def room_environment_from_namespace(source: str) -> str:
    """RoomEnvironment.js as a function of ``THREE`` whose result is the class."""
    imports = list(_IMPORT.finditer(source))
    if len(imports) != 1:
        raise ValueError(f"expected one import in RoomEnvironment.js, found {len(imports)}")
    names = re.findall(r"\w+", imports[0].group(0).split("from")[0].replace("import", ""))
    body = (
        source[: imports[0].start()]
        + "const { "
        + ", ".join(names)
        + " } = THREE;"
        + source[imports[0].end() :]
    )
    body, count = _EXPORT_NAMES.subn("return RoomEnvironment;", body)
    if count != 1:
        raise ValueError("expected RoomEnvironment.js to export once")
    return "const RoomEnvironment = (function (THREE) {" + NL + body + NL + "})(THREE);"


def scene_without_imports(source: str) -> str:
    """scene.js as a function of ``THREE`` and ``RoomEnvironment``; it sets ``window.iso3d``."""
    body, count = _IMPORT.subn("", source)
    if count != 2:
        raise ValueError(f"expected scene.js to import twice, found {count}")
    return "(function (THREE, RoomEnvironment) {" + NL + body + NL + "})(THREE, RoomEnvironment);"


@lru_cache(maxsize=1)
def bundle_source() -> str:
    """The builder as one classic script; read once per process."""
    three = three_as_namespace((LIB / "three.module.js").read_text(encoding="utf-8"))
    room = room_environment_from_namespace((LIB / "RoomEnvironment.js").read_text(encoding="utf-8"))
    scene = scene_without_imports((HERE / "scene.js").read_text(encoding="utf-8"))
    return (
        "(function () {"
        + NL
        + "'use strict';"
        + NL
        + three
        + NL
        + room
        + NL
        + scene
        + NL
        + "})();"
        + NL
    )
