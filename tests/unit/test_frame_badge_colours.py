"""A frame tab shows the vendor's badge in the vendor's colours where it can.

Two tab treatments, and the badge follows the tab:

- a tab painted the frame's own colour carries a single-ink glyph, because a
  full-colour mark would not read against it (Kubernetes);
- a paper tab is white, so the vendor's badge paints itself and keeps every
  colour it ships with (Azure).

The editor used to flatten both, which drew Azure's cyan resource-group cube
as a grey one and disagreed with the static renderer, whose picture of the
same document kept the cyan.
"""

from __future__ import annotations

import base64
import re

import pytest

from infragram.builders.architecture import load_icon_set, load_style, load_theme
from infragram.builders.frame_style import frame_paint
from infragram.editor.artwork import frame_visual

#: The paper-tab library, and a frame whose badge is vendor artwork carrying a
#: colour of its own. Azure is the one the flattening hit; Kubernetes paints
#: its tab the frame's colour and wants a single ink.
PAPER_TAB = {"azure": "resource-group"}
COLOURED_TAB = {"kubernetes": "cluster"}


def _badge_fills(provider: str, kind: str) -> set[str]:
    style, theme = load_style(provider).cluster, load_theme(provider)
    uri = str(frame_visual(style, theme, kind).get("iconUri") or "")
    assert uri.startswith("data:image/svg+xml;base64,"), f"{provider}:{kind} has no badge"
    art = base64.b64decode(uri.split(",", 1)[1]).decode("utf-8", "replace")
    return set(re.findall(r'(?:fill|stroke)="(#[0-9a-fA-F]{3,8})"', art))


def _source_fills(reference: str) -> set[str]:
    collection, _, slug = reference.partition(":")
    icon = load_icon_set(collection).find(slug)
    return set(
        re.findall(
            r'(?:fill|stop-color)="(#[0-9a-fA-F]{6})"', icon.path.read_text(encoding="utf-8")
        )
    )


def _saturated(colours: set[str]) -> set[str]:
    out = set()
    for value in colours:
        if len(value) != 7:
            continue
        r, g, b = (int(value[i : i + 2], 16) for i in (1, 3, 5))
        if max(r, g, b) - min(r, g, b) > 40:
            out.add(value.casefold())
    return out


@pytest.mark.parametrize(("provider", "kind"), sorted(PAPER_TAB.items()))
def test_a_paper_tab_keeps_the_vendors_own_badge_colours(provider: str, kind: str) -> None:
    style, theme = load_style(provider).cluster, load_theme(provider)
    paint = frame_paint(style, theme, kind)
    assert paint.paper_tab, f"{provider}:{kind} is no longer a paper tab; pick another kind"

    wanted = _saturated(_source_fills(paint.badge))
    assert wanted, f"{paint.badge} has no brand colour to preserve"
    drawn = {value.casefold() for value in _badge_fills(provider, kind)}
    missing = sorted(wanted - drawn)
    assert not missing, f"{provider}:{kind} badge lost the vendor's colours {missing}"


@pytest.mark.parametrize(("provider", "kind"), sorted(COLOURED_TAB.items()))
def test_a_coloured_tab_carries_a_single_ink_glyph(provider: str, kind: str) -> None:
    style, theme = load_style(provider).cluster, load_theme(provider)
    paint = frame_paint(style, theme, kind)
    assert not paint.paper_tab, f"{provider}:{kind} is now a paper tab; pick another kind"

    drawn = {value.casefold() for value in _badge_fills(provider, kind)}
    assert drawn <= {paint.glyph_ink.casefold()}, (
        f"{provider}:{kind} glyph must be one ink on its coloured tab, got {sorted(drawn)}"
    )


def test_no_badge_falls_back_to_svgs_default_black() -> None:
    """An icon that declares no paint inherits SVG's default fill, which is
    black. The Kubernetes mark is one, and it drew as a black wheel on Google
    Cloud's blue tab while every other badge there was white."""
    import importlib
    import inspect

    from infragram.builders.frame_style import frame_paint
    from infragram.nodes import frames as frames_package

    unpainted = []
    for group in sorted(frames_package.GROUPS):
        style, theme = load_style(group).cluster, load_theme(group)
        module = importlib.import_module(f"infragram.nodes.frames.{group}")
        kinds = sorted(
            {
                cls.KIND
                for name in dir(module)
                if inspect.isclass(cls := getattr(module, name))
                and getattr(cls, "KIND", None)
                and getattr(cls, "FRAME_ID", None)
            }
        )
        for kind in kinds:
            if frame_paint(style, theme, kind).paper_tab:
                continue
            uri = str(frame_visual(style, theme, kind).get("iconUri") or "")
            if not uri.startswith("data:image/svg+xml;base64,"):
                continue
            art = base64.b64decode(uri.split(",", 1)[1]).decode("utf-8", "replace")
            if not re.search(r"(?i)\bfill=", art):
                unpainted.append(f"{group}:{kind}")
    assert not unpainted, f"these badges would draw black on their tab: {unpainted}"


def test_the_azure_resource_group_cube_is_cyan_not_grey() -> None:
    """The report that started this: the cube drew grey in the exported page."""
    drawn = {value.casefold() for value in _badge_fills("azure", "resource-group")}
    assert "#32bedd" in drawn or "#50e6ff" in drawn, sorted(drawn)
    # The brackets are grey in Microsoft's own artwork, so grey may be present;
    # what must not happen is grey being the only colour left.
    assert _saturated(drawn), f"the badge is entirely neutral: {sorted(drawn)}"
