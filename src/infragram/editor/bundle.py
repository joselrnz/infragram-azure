"""The bundler: the page's runtime, assembled from its numbered modules.

The runtime is one closure. It used to be one file of five thousand lines,
which meant every change to the tooltip and every change to the router landed
in the same diff, and finding where a thing lived meant searching rather than
looking.

It is a folder of numbered modules now, concatenated at render time in numeric
order. The number is not decoration: the modules share one scope, so the order
they are joined in *is* the order the statements evaluate, and ``00-bootstrap``
opening the closure and ``34-api-and-start`` closing it are the two ends of
that. Each number is used once, and each module names itself on its first line
so a reader landing in the middle of the bundle knows which file to open.

The split was made by cutting the original file at statement boundaries and
never by moving anything: ``tests/unit/test_editor_bundle.py`` holds the
contract, and the modules are contiguous slices, so what the page runs is what
the single file ran.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

EDITOR = Path(__file__).resolve().parent
RUNTIME = EDITOR / "runtime"
UI = EDITOR / "ui"

#: Every runtime module begins with this, naming itself and what it holds.
MODULE_HEADER = re.compile(r"^// @module (?P<stem>[\w-]+): .+$")

#: The page's stylesheets in cascade order, relative to ``ui/``.
#:
#: The order is the behaviour: a rule that moves above the one that overrode
#: it is a different page. Tokens first, because everything below reads them;
#: the media queries last, because they override what they narrow. The files
#: in between are runs of the block they were cut from, in the order they ran
#: in it -- which is why the header sits after the sidebar rather than where a
#: reader might file it.
STYLE_ORDER = (
    "styles/tokens.css",
    "styles/base.css",
    "styles/states.css",
    "components/button.css",
    "components/icon_button.css",
    "components/segmented.css",
    "components/chip.css",
    "components/list.css",
    "components/nav_item.css",
    "components/tile.css",
    "components/tabs.css",
    "components/field.css",
    "components/search.css",
    "components/switch.css",
    "components/checkbox.css",
    "components/card.css",
    "components/menu.css",
    "components/tooltip.css",
    "components/snackbar.css",
    "components/badge.css",
    "components/empty_state.css",
    "components/setting_row.css",
    "views/workspace.css",
    "views/sidebar.css",
    "views/header.css",
    "views/workbench.css",
    "views/inspector/inspector.css",
    "views/canvas.css",
    "views/overlays.css",
    "views/drawer.css",
    "styles/rails.css",
    "styles/responsive.css",
)

__all__ = ["RUNTIME", "STYLE_ORDER", "UI", "runtime_modules", "runtime_script", "stylesheet"]


#: The two values in the stylesheet that are not the same for every diagram:
#: the stage is sized to the scene it holds. They were an f-string
#: interpolation while the stylesheet lived inside ``shell.py``, which is why
#: it could not simply become a file -- moved as it was, every page shipped
#: the literal text ``{scene.width}px``. They are placeholders now, filled
#: where the rule already sits, so its cascade position is the one it had.
STAGE_WIDTH = "__STAGE_WIDTH__"
STAGE_HEIGHT = "__STAGE_HEIGHT__"


@cache
def _stylesheet_template() -> str:
    """Every stylesheet joined in cascade order, placeholders unfilled."""
    rows: list[str] = []
    for name in STYLE_ORDER:
        text = (UI / name).read_text(encoding="utf-8").replace("\r\n", "\n")
        piece = text.split("\n")
        if piece and piece[-1] == "":
            piece = piece[:-1]
        rows += piece
    return "\n".join(rows)


def stylesheet(stage_width: int, stage_height: int) -> str:
    """The page's whole stylesheet, sized for one diagram."""
    return (
        _stylesheet_template()
        .replace(STAGE_WIDTH, str(int(stage_width)))
        .replace(STAGE_HEIGHT, str(int(stage_height)))
    )


def runtime_modules() -> list[Path]:
    """The runtime's modules in the order they are joined, which is the order
    they evaluate. Sorted by file name, so the number leads."""
    return sorted(RUNTIME.glob("*.js"))


@cache
def runtime_script() -> str:
    """The whole runtime as one script, module headers stripped.

    The headers are for the repository, not for the page: a reader opening an
    exported diagram should not find thirty-five comments about a folder
    layout they cannot see.
    """
    # Joined as lines rather than as text. Each module is written with a
    # closing newline of its own so that reading it back yields exactly the
    # lines that were cut; concatenating the raw bodies would therefore add
    # one newline per module, and trimming each body would delete the blank
    # line that separated two statements. Neither is the file that was cut.
    joined: list[str] = []
    for module in runtime_modules():
        text = module.read_text(encoding="utf-8").replace("\r\n", "\n")
        rows = text.split("\n")
        if not MODULE_HEADER.match(rows[0]):
            raise ValueError(
                f"{module.name} must start with its '// @module {module.stem}: ...' line"
            )
        joined += rows[1:-1]
    return "\n".join(joined)
