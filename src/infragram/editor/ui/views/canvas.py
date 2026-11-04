"""Canvas view: the drawing, the selection toolbar, the shortcut sheet, the
frame review, the tooltip, the popup and the right-click menu. Styles: canvas.css, overlays.css.

The floating controls are ``md-*`` components like the rest of the chrome:
icon buttons over a selection, list items in the menu. The hooks are this
edition's own, so the runtime is unchanged.
"""

from __future__ import annotations

from ..branding import mascot_uri
from ..components import button, icon_button
from ..html import attributes
from ..icons import icon


def selection_toolbar() -> str:
    """The toolbar that follows a selection: icon buttons only.

    There is no room for words here, so every button is a glyph and
    ``icon_button`` writes the name twice -- once where a pointer finds it
    and once where a screen reader does.

    Two sets of buttons that hide each other. A wire cannot be aligned,
    grouped or brought to the front, and an object has no direction to
    reverse, so ``data-edge-only`` and ``data-object-only`` say which
    selection each button belongs to and the runtime shows one set.

    The grip at its start moves it: dragged, the toolbar stays where it was
    put, over every selection after, until the grip is double-clicked.
    """
    return f"""          <div class="selection-toolbar" data-selection-toolbar hidden aria-label="Selection actions">
            {icon_button("grip", "Move toolbar (double-click puts it back)", attrs="data-selection-toolbar-grip", classes="selection-toolbar__grip")}
            <span class="md-badge selection-count-chip" data-selection-count-chip data-object-only>0</span>
            {icon_button("align-left", "Align left", attrs='data-selection-action="align-left" data-object-only')}
            {icon_button("align-top", "Align top", attrs='data-selection-action="align-top" data-object-only')}
            <span class="toolbar-divider" aria-hidden="true" data-object-only></span>
            {icon_button("copy", "Duplicate", attrs='data-selection-action="duplicate" data-object-only')}
            {icon_button("to-front", "Bring to front", attrs='data-selection-action="to-front" data-object-only')}
            {icon_button("rotate", "Rotate 90°", attrs='data-selection-action="rotate-90" data-object-only')}
            {icon_button("group", "Group selection", attrs='data-selection-action="group" data-object-only')}
            {icon_button("text", "Edit label", attrs='data-selection-action="edge-edit-label" data-edge-only hidden')}
            {icon_button("swap", "Reverse direction", attrs='data-selection-action="edge-reverse" data-edge-only hidden')}
            {icon_button("route-reset", "Reset route", attrs='data-selection-action="edge-reset-route" data-edge-only hidden')}
            {icon_button("show-icons", "Show as icons", attrs='data-selection-action="display-icon"')}
            {icon_button("show-cards", "Show as cards", attrs='data-selection-action="display-card" hidden')}
            {icon_button("detach", "Detach from frame", attrs='data-selection-action="detach" data-selection-detach hidden')}
            {icon_button("lock", "Lock selection", toggle=True, attrs='data-selection-action="lock" aria-pressed="false" data-object-only')}
            <span class="toolbar-divider" aria-hidden="true"></span>
            {icon_button("delete", "Delete selection", attrs='data-selection-action="delete"')}
          </div>"""


def menu_item(
    action: str,
    label: str,
    *,
    attrs: str = "",
    role: str = "menuitem",
    danger: bool = False,
    keys: str = "",
    glyph: str = "",
) -> str:
    """One entry of the right-click menu.

    ``role`` is ``menuitemcheckbox`` for the entries that show a tick, which
    the stylesheet draws from ``aria-checked`` -- so an entry that toggles and
    keeps the plain role is an entry whose tick never appears.

    ``keys`` is the shortcut that does the same, shown muted at the right as
    the keyboard sheet writes it. A screen reader hears it from
    ``aria-keyshortcuts``, not as part of the entry's name.

    ``glyph`` names the icon drawn at the left; an entry without one keeps
    the empty slot, so every label starts at the same edge.
    """
    kind = " md-list-item--danger context-menu-danger" if danger else ""
    hint = (
        (
            f' aria-keyshortcuts="{keys.replace("Ctrl+", "Control+")}"',
            f'<span class="md-menu__keys" aria-hidden="true">{keys}</span>',
        )
        if keys
        else ("", "")
    )
    return (
        f'<button type="button" class="md-list-item{kind}" role="{role}" '
        f'data-context-action="{action}"{attributes(attrs)}{hint[0]}>'
        f'<span class="md-menu__icon">{icon(glyph) if glyph else ""}</span>'
        f'<span class="md-list-item__label">{label}</span>{hint[1]}</button>'
    )


def menu_separator(attrs: str = "") -> str:
    return f'<div class="md-divider" role="separator"{attributes(attrs)}></div>'


def context_menu() -> str:
    """The right-click menu, in the order the entries are offered.

    What concerns the item comes first -- its details, centring it, what is
    particular to a card, a frame or a wire -- then the view, which is the
    same on empty canvas. The editing entries wait in "More actions", a
    submenu, so the menu stays short; Delete stays at the bottom.
    """
    return f"""          <div class="md-menu canvas-context-menu" data-canvas-context-menu role="menu" aria-label="Canvas actions" hidden>
            <strong class="md-menu__header context-menu-title" data-context-menu-title data-context-canvas>Selection</strong>
            <dl class="context-menu-facts" data-context-menu-facts hidden></dl>
            {menu_item("details", "Inspect details", attrs="data-context-details", glyph="inspect")}
            {menu_item("center", "Center on item", attrs="data-context-center", glyph="center")}
            {menu_item("lens-dependents", "Show what depends on this", attrs="data-context-node-only", role="menuitemcheckbox", glyph="dependents")}
            {menu_item("toggle-parts", "Show attached on canvas", attrs="data-context-node-only data-context-parts hidden", glyph="show-cards")}
            {menu_item("frame-review", "Review components…", attrs="data-context-frame-only", glyph="table")}
            {menu_item("edge-reverse", "Reverse direction", attrs="data-context-edge-only hidden", glyph="swap")}
            {menu_item("edge-reset-route", "Reset route", attrs="data-context-edge-only hidden", glyph="route-reset")}
            {menu_item("reset-label-position", "Reset label position", attrs="hidden", glyph="text")}
            {menu_item("edit-text", "Edit text", glyph="edit")}
            {menu_item("paste", "Paste here", attrs="data-context-canvas", keys="Ctrl+V", glyph="paste")}
            {menu_separator("data-context-canvas-only hidden")}
            {menu_item("lens-internet", "Show what the internet reaches", attrs="data-context-canvas-only hidden", role="menuitemcheckbox", glyph="globe")}
            {menu_item("lens-cost", "Show what costs most", attrs="data-context-canvas-only hidden", role="menuitemcheckbox", glyph="coin")}
            {menu_item("lens-changes", "Show what changed in 7 days", attrs="data-context-canvas-only hidden", role="menuitemcheckbox", glyph="clock")}
            {menu_item("lens-findings", "Show what has findings", attrs="data-context-canvas-only hidden", role="menuitemcheckbox", glyph="shield")}
            <div class="context-menu-tags" data-context-tags data-context-canvas-only role="group" aria-label="Tags" hidden></div>
            {menu_separator("data-context-canvas")}
            {menu_item("zoom-in", "Zoom in", attrs="data-context-canvas", keys="+", glyph="magnify-plus")}
            {menu_item("zoom-out", "Zoom out", attrs="data-context-canvas", keys="-", glyph="magnify-minus")}
            {menu_item("zoom-fit", "Fit all", attrs="data-context-canvas", keys="0", glyph="fit")}
            {menu_item("zoom-reset", "Actual size", attrs="data-context-canvas", keys="1", glyph="actual-size")}
            {menu_separator("data-context-canvas")}
            {menu_item("scroll-pans", "Scroll moves the map", attrs="data-context-canvas", role="menuitemcheckbox", glyph="scroll-pan")}
            {menu_item("tidy-layout", "Tidy layout", attrs="data-context-canvas", glyph="tidy")}
            {menu_separator()}
            <div class="context-submenu" data-context-submenu>
              <button type="button" class="md-list-item" role="menuitem" aria-haspopup="menu" aria-expanded="false" data-context-submenu-toggle><span class="md-menu__icon">{icon("more")}</span><span class="md-list-item__label">More actions</span><span class="md-menu__keys context-submenu__chevron" aria-hidden="true">{icon("chevron-right")}</span></button>
              <div class="md-menu context-submenu__menu" data-context-submenu-menu role="menu" aria-label="More actions" hidden>
                {menu_item("duplicate", "Duplicate", attrs="data-context-object-only", keys="Ctrl+D", glyph="copy")}
                {menu_item("copy", "Copy", attrs="data-context-object-only", keys="Ctrl+C", glyph="copy")}
                {menu_item("open-style", "Edit style…", glyph="palette")}
                {menu_item("open-arrange", "Arrange &amp; align…", glyph="align-left")}
                {menu_separator("data-context-node-only")}
                {menu_item("display-card", "Card with text", attrs="data-context-node-only", role="menuitemcheckbox", glyph="show-cards")}
                {menu_item("display-icon", "Icon only", attrs="data-context-node-only", role="menuitemcheckbox", glyph="show-icons")}
                {menu_separator("data-context-object-only")}
                {menu_item("to-front", "Bring to front", attrs="data-context-object-only", keys="Ctrl+]", glyph="to-front")}
                {menu_item("forward", "Bring forward", attrs="data-context-object-only", keys="Ctrl+Shift+]")}
                {menu_item("backward", "Send backward", attrs="data-context-object-only", keys="Ctrl+Shift+[")}
                {menu_item("to-back", "Send to back", attrs="data-context-object-only", keys="Ctrl+[")}
                {menu_separator("data-context-object-only")}
                {menu_item("group", "Group selection", attrs="data-context-object-only", keys="Ctrl+G", glyph="group")}
                {menu_item("ungroup", "Ungroup", attrs="data-context-frame-only")}
                {menu_item("detach", "Detach from frame", attrs="data-context-object-only", keys="Ctrl+Shift+G", glyph="detach")}
                {menu_item("shrink-fit", "Shrink frame to fit", attrs="data-context-frame-only", glyph="fit")}
                {menu_separator("data-context-frame-only")}
                {menu_item("frame-highlight", "Highlight frame", attrs="data-context-frame-only", role="menuitemcheckbox")}
                {menu_item("frame-display-icon", "Show contents as icons", attrs="data-context-frame-only", glyph="show-icons")}
                {menu_item("frame-display-card", "Show contents as cards", attrs="data-context-frame-only", glyph="show-cards")}
                {menu_separator("data-context-object-only")}
                {menu_item("lock", "Lock", attrs="data-context-object-only", keys="Ctrl+Shift+L", glyph="lock")}
              </div>
            </div>
            {menu_item("delete", "Delete", danger=True, keys="Delete", glyph="delete")}
          </div>"""


#: What the keyboard does, in the order a reader meets it. Every row is a
#: binding the runtime actually listens for; tests/integration checks that.
SHORTCUTS = (
    (
        "Editing",
        (
            ("Undo · redo", "Ctrl+Z · Ctrl+Shift+Z or Ctrl+Y"),
            ("Copy · cut · paste", "Ctrl+C · Ctrl+X · Ctrl+V"),
            ("Duplicate", "Ctrl+D"),
            ("Delete", "Delete or Backspace"),
        ),
    ),
    (
        "Choosing",
        (
            ("Select everything in the frame", "Ctrl+A"),
            ("Add to the selection", "Shift-click"),
            ("Step through the drawing", "Tab · Shift+Tab"),
            ("Drop the selection, or the line being drawn", "Escape"),
        ),
    ),
    (
        "Moving",
        (
            ("Nudge · nudge further", "Arrows · Shift+Arrows"),
            ("Skip snapping while dragging", "Alt"),
            ("Bring to front · send to back", "Ctrl+] · Ctrl+["),
            ("Bring forward · send backward", "Ctrl+Shift+] · Ctrl+Shift+["),
            ("Group · detach", "Ctrl+G · Ctrl+Shift+G"),
            ("Lock", "Ctrl+Shift+L"),
        ),
    ),
    (
        "Looking",
        (
            ("Zoom in · out", "+ · - or Ctrl+= · Ctrl+-"),
            ("Fit all", "0"),
            ("Actual size", "1 or Ctrl+0"),
            ("Search the inventory", "/"),
            ("This sheet", "?"),
        ),
    ),
)


def shortcuts() -> str:
    """The shortcut sheet: what the keyboard does, in one place."""
    groups = "".join(
        f"""
              <section class="shortcut-sheet__group">
                <h3>{title}</h3>
                <dl class="shortcut-sheet__rows">"""
        + "".join(f"<dt>{what}</dt><dd><kbd>{keys}</kbd></dd>" for what, keys in rows)
        + """</dl>
              </section>"""
        for title, rows in SHORTCUTS
    )
    return f"""          <section class="shortcut-sheet" data-shortcut-sheet role="dialog" aria-labelledby="shortcut-sheet-title" hidden>
            <header class="shortcut-sheet__header">
              <strong id="shortcut-sheet-title">Keyboard</strong>
              {icon_button("close", "Close the shortcut sheet", attrs="data-shortcut-sheet-close")}
            </header>
            <div class="shortcut-sheet__body">{groups}
            </div>
          </section>"""


def frame_review() -> str:
    """Every component inside one frame, with its display, to review a region
    in one place. The runtime fills the list when a frame is reviewed."""
    return f"""          <section class="frame-review" data-frame-review role="dialog" aria-labelledby="frame-review-title" hidden>
            <header class="frame-review__header">
              <div class="frame-review__heading">
                <strong id="frame-review-title" data-frame-review-title>Frame</strong>
                <span data-frame-review-summary></span>
              </div>
              {icon_button("close", "Close review", attrs="data-frame-review-close")}
            </header>
            <div class="frame-review__actions">
              <button type="button" class="md-chip" data-frame-review-highlight aria-pressed="false">Highlighted</button>
              {button("Icons", variant="tonal", attrs='data-frame-review-display="icon" title="Show every component in this frame as an icon"')}
              {button("Cards", variant="outlined", attrs='data-frame-review-display="card" title="Show every component in this frame as a card"')}
            </div>
            <div class="md-list frame-review__list" data-frame-review-list></div>
          </section>"""


def canvas(diagram: str) -> str:
    """The canvas viewport and everything that floats over it."""
    return f"""        <div class="canvas-pane">
        <section class="canvas-viewport" aria-label="Diagram canvas">
{selection_toolbar()}
{shortcuts()}
{frame_review()}
          <div class="diagram-stage">
{diagram}
          </div>
          <div class="md-tooltip-rich canvas-tooltip" data-canvas-tooltip role="tooltip" hidden></div>
          <div class="md-card canvas-popup" data-canvas-popup role="dialog" aria-label="Element details" hidden></div>
          <div class="md-snackbar" data-snackbar aria-hidden="true" hidden></div>
          <div class="save-notice" data-save-notice role="alert" hidden>
            <span>Changes cannot be saved in this browser. Download the editor page to keep your edits.</span>
            <button type="button" class="md-button md-button--tonal" data-save-download>Download editor</button>
          </div>
          <p class="canvas-help" data-editor-help>Click to see the flow · double-click to edit · pinch or wheel to zoom · drag empty canvas or middle-drag to pan</p>
{context_menu()}
        </section>
        <section class="canvas-welcome" data-canvas-welcome aria-labelledby="welcome-title" hidden>
          <img src="{mascot_uri()}" width="160" height="160" alt="Infragram's friendly pangolin architect">
          <h2 id="welcome-title">Create a diagram</h2>
          <p>Start with an example or add components.</p>
          {button("Browse examples", variant="filled", attrs="data-welcome-examples")}
        </section>
        <footer class="diagram-caption" data-diagram-caption hidden></footer>
        <section class="diagram-legend" data-diagram-legend aria-label="Legend" hidden></section>
        </div>"""


__all__ = [
    "canvas",
    "context_menu",
    "frame_review",
    "menu_item",
    "menu_separator",
    "selection_toolbar",
    "shortcuts",
]
