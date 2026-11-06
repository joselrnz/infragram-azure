"""What a headless browser does for an export.

The page an author saved is the one the editor runtime draws, not the static
layout embedded in its source, so SVG and PNG both come from the runtime:
staged alone at the origin, cropped to what is actually drawn plus a margin.
Everything that opens a page -- here and in every browser suite -- goes through
:func:`prepare_page`, so one timeout and one network policy cover all of them.
"""

from __future__ import annotations

import atexit
import contextlib
import re
import sys
import threading
from functools import cache
from pathlib import Path
from typing import Any

from .errors import ExportError
from .svg import finish_standalone_svg

__all__ = [
    "EXPORT_THEMES",
    "PNG_CONTENT_MARGIN",
    "browser_missing",
    "editor_page_url",
    "playwright_png_renderer",
    "playwright_static_png_renderer",
    "playwright_svg_renderer",
    "prepare_page",
    "remote_url",
    "render_offline",
    "render_timeout_ms",
]


#: Transparent breathing room, in canvas units, kept around the drawn content
#: when a PNG is cropped out of the editor world.
PNG_CONTENT_MARGIN = 48


#: Workspace themes the exported editor can draw a diagram in. Light gives
#: white cards and dark text for documents; dark matches the editor's default
#: workspace.
EXPORT_THEMES = ("light", "dark", "darker")


#: How the editor routes the wires a picture is captured with: around the
#: cards (its default), or ``direct``, straight from port to port.
EXPORT_ROUTINGS = ("around", "direct")


def editor_page_url(
    source: Path,
    theme: str | None = None,
    display: str | None = None,
    routing: str | None = None,
) -> str:
    """The file URL that opens an exported editor for capture.

    ``motion=static`` disables animation. ``theme`` picks the workspace theme
    the diagram is drawn in, so cards and labels come out light on a light
    theme and dark on a dark one instead of whatever the browser last saved.
    ``display`` draws every component as a ``card`` or a bare ``icon`` for
    this visit, without touching what the document saved. ``routing="direct"``
    draws the wires straight rather than around the cards, as the editor's own
    routing switch does, for this visit only.
    """

    if theme is not None and theme not in EXPORT_THEMES:
        raise ExportError(f"unknown export theme {theme!r}; use light or dark")
    if display is not None and display not in ("card", "icon"):
        raise ExportError(f"unknown export display {display!r}; use card or icon")
    if routing is not None and routing not in EXPORT_ROUTINGS:
        raise ExportError(f"unknown routing {routing!r}; use {' or '.join(EXPORT_ROUTINGS)}")
    url = source.resolve().as_uri() + "?motion=static"
    url += f"&theme={theme}" if theme else ""
    url += "&routing=direct" if routing == "direct" else ""
    return url + (f"&display={display}" if display else "")


# Runs inside an exported editor page. Takes the runtime's own clean SVG
# export (editor-only layers already stripped, selection state cleared),
# stages it alone at the origin with the chrome hidden, crops its viewBox to
# what is actually drawn plus a margin, and reports the crop box. Returns null
# on a page without the editor runtime so the caller can fall back to a plain
# element screenshot.
_EDITOR_PNG_CAPTURE = r"""
margin => {
    const editor = window.infragramEditor;
    if (!editor || typeof editor.exportSvg !== 'function') return null;
    const parsed = new DOMParser().parseFromString(editor.exportSvg({background: 'transparent'}), 'image/svg+xml');
    const parseError = parsed.querySelector('parsererror');
    if (parseError) {
        // Chromium wraps the parser's line in a banner of its own.
        const detail = parseError.textContent
            .replace(/^This page contains the following errors:/, '')
            .split('Below is a rendering')[0].trim();
        return {failed: `its export is not well-formed SVG (${detail.slice(0, 200)})`};
    }
    if (parsed.documentElement.tagName.toLowerCase() !== 'svg') {
        return {failed: 'its export is not an SVG document'};
    }
    const svg = document.importNode(parsed.documentElement, true);
    const viewBox = svg.viewBox && svg.viewBox.baseVal;
    const world = viewBox && viewBox.width && viewBox.height
        ? {x: viewBox.x, y: viewBox.y, width: viewBox.width, height: viewBox.height}
        : {x: 0, y: 0, width: svg.width.baseVal.value, height: svg.height.baseVal.value};
    if (!world.width || !world.height) return {failed: 'its export has no size'};

    // Take the chrome off screen and stage the copy alone at the origin,
    // unscaled, so client rectangles read in canvas units. The live diagram
    // goes away entirely, not just out of view: it defines the same marker
    // ids as the copy, url(#…) resolves to the first id in the document, and
    // a marker inside a hidden subtree never paints -- which is how every
    // PNG lost its arrowheads while the SVG kept them.
    document.querySelectorAll('svg').forEach(other => other.remove());
    Array.from(document.body.children).forEach(child => {
        child.style.setProperty('display', 'none', 'important');
    });
    const stage = document.createElement('div');
    stage.setAttribute('data-infragram-png-stage', '');
    stage.style.cssText = 'position:fixed;left:0;top:0;margin:0;padding:0;border:0;';
    svg.removeAttribute('data-infragram-diagram');
    svg.setAttribute('data-infragram-png-capture', '');
    svg.setAttribute('viewBox', `${world.x} ${world.y} ${world.width} ${world.height}`);
    svg.setAttribute('width', String(world.width));
    svg.setAttribute('height', String(world.height));
    svg.style.cssText = 'display:block;border:0;';
    stage.appendChild(svg);
    document.body.appendChild(stage);
    document.body.style.setProperty('margin', '0', 'important');
    document.body.style.setProperty('overflow', 'hidden', 'important');
    for (const element of [document.documentElement, document.body, stage, svg]) {
        element.style.setProperty('background', 'transparent', 'important');
        element.style.setProperty('background-color', 'transparent', 'important');
    }

    // Crop to what is drawn: the status line above the drawing, frames,
    // cards, wires and their labels, the provider mark in its band below
    // them, and the legend strip under that. Client rectangles include
    // captions and transforms that saved geometry omits.
    const origin = svg.getBoundingClientRect();
    let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
    svg.querySelectorAll('[data-graph-boundary],[data-graph-node],[data-graph-edge],[data-edge-label],[data-brand-mark],[data-legend-strip],[data-export-title],[data-step-list],[data-status-block]')
        .forEach(element => {
            const rect = element.getBoundingClientRect();
            if (!rect.width && !rect.height) return;
            left = Math.min(left, rect.left - origin.left + world.x);
            top = Math.min(top, rect.top - origin.top + world.y);
            right = Math.max(right, rect.right - origin.left + world.x);
            bottom = Math.max(bottom, rect.bottom - origin.top + world.y);
        });
    if (!Number.isFinite(left)) {
        // Nothing drawn yet: keep the whole world rather than guess.
        left = world.x; top = world.y;
        right = world.x + world.width; bottom = world.y + world.height;
    }
    const box = {
        x: Math.floor(left - margin),
        y: Math.floor(top - margin),
        width: Math.ceil(right - left + margin * 2),
        height: Math.ceil(bottom - top + margin * 2),
    };
    svg.setAttribute('viewBox', `${box.x} ${box.y} ${box.width} ${box.height}`);
    svg.setAttribute('width', String(box.width));
    svg.setAttribute('height', String(box.height));
    return box;
}
"""


# Anything the runtime raised in reaction to the viewport change (a toast, a
# help card) must not land on top of the staged capture.
_EDITOR_PNG_SETTLE = """
() => {
    Array.from(document.body.children).forEach(child => {
        if (!child.hasAttribute('data-infragram-png-stage')) {
            child.style.setProperty('display', 'none', 'important');
        }
    });
    return document.fonts.ready.then(() => true);
}
"""


# The static fallback: screenshot the inline SVG at its viewBox size over a
# transparent ground, with any editor-only layers hidden. Element screenshots
# composite over authored ancestor backgrounds, so only those ancestors go
# transparent; fills inside the SVG stay intact.
_PLAIN_SVG_CAPTURE = """
element => {
    const viewBox = element.viewBox && element.viewBox.baseVal;
    if (viewBox && viewBox.width && viewBox.height) {
        element.style.setProperty('width', `${viewBox.width}px`, 'important');
        element.style.setProperty('height', `${viewBox.height}px`, 'important');
    }
    element.style.setProperty('border', '0', 'important');
    element.style.setProperty('background', 'transparent', 'important');
    element.style.setProperty('background-color', 'transparent', 'important');
    element.querySelectorAll('[data-canvas-background], [data-editor-grid], [data-edge-terminal-layer], [data-edge-terminal], [data-node-port], .node-selection, .boundary-selection, [data-boundary-resize], [data-edge-hit], [data-connection-preview]').forEach(child => {
        child.style.setProperty('display', 'none', 'important');
    });
    document.querySelectorAll('.editor-toolbar, .canvas-help').forEach(control => {
        control.style.setProperty('display', 'none', 'important');
    });
    // Lift the diagram out of the page and over the chrome. This branch
    // screenshots the element where it sits, so anything painting on top
    // lands in the picture: on a page whose runtime was not ready in time --
    // a large library payload on a slow machine -- the PNG came out as the
    // inspector panel and the library tabs over a corner of the diagram.
    // Hiding the panels by name missed the ones added since, and hiding
    // every sibling collapsed the flex parent that sizes the canvas, which
    // shrank the picture to a fraction of itself. Taking the element out of
    // flow at its natural size avoids both.
    element.style.setProperty('position', 'fixed', 'important');
    element.style.setProperty('left', '0', 'important');
    element.style.setProperty('top', '0', 'important');
    element.style.setProperty('margin', '0', 'important');
    element.style.setProperty('max-width', 'none', 'important');
    element.style.setProperty('max-height', 'none', 'important');
    element.style.setProperty('transform', 'none', 'important');
    element.style.setProperty('z-index', '2147483647', 'important');
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
        parent.style.setProperty('background', 'transparent', 'important');
        parent.style.setProperty('background-color', 'transparent', 'important');
    }
    document.documentElement.style.setProperty('background', 'transparent', 'important');
    document.documentElement.style.setProperty('background-color', 'transparent', 'important');
}
"""


def _made_by_uv(prefix: Path) -> bool:
    """Whether uv made the environment at *prefix*, which then has no pip.

    uv writes ``uv = <version>`` into the ``pyvenv.cfg`` of every environment
    it makes: a project's ``uv venv``, an installed tool, the plugin's MCP
    server under uvx. Where the environment sits says nothing: a project's
    ``.venv`` made by uv is in no folder called ``uv``, and a venv made with
    pip can be.
    """
    try:
        config = (prefix / "pyvenv.cfg").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return any(
        key.strip().casefold() == "uv"
        for key, equals, _ in (line.partition("=") for line in config.splitlines())
        if equals
    )


def install_hint(chromium_only: bool = False) -> str:
    """How to give *this* Python what a PNG needs: the interpreter that is
    running, never a ``python`` that may be another one. A Python uv made (a
    project's environment, an installed tool, the plugin's MCP server under
    uvx) has no pip: it gets Playwright through uv."""
    import sys

    python = f'"{sys.executable}"'
    chromium = f"{python} -m playwright install chromium"
    if chromium_only:
        return chromium
    if _made_by_uv(Path(sys.prefix)):
        return (
            f"this Python is one uv made, without pip: uv pip install --python {python} "
            "playwright pillow; an installed tool keeps them through upgrades when installed "
            'with the png extra (uv tool install --reinstall "infragram[png]", or the plugin\'s '
            f'"<plugin>[png]"); then {chromium}'
        )
    return f"{python} -m pip install playwright pillow, then {chromium}"


def _playwright():
    """The Playwright entry points, or the ExportError every renderer raises without them."""
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError as error:
        raise ExportError(
            "Playwright isn't installed. To enable PNG export and the editor's own SVG: "
            + install_hint()
        ) from error
    return sync_playwright, PlaywrightError


def _launch(playwright, playwright_error: type[BaseException]):
    """Chromium, or the ExportError that says how to install it.

    Playwright installed without its browser fails at launch, not at import;
    unconverted, that error would escape every fallback as a traceback.
    """
    try:
        return playwright.chromium.launch()
    except playwright_error as error:
        raise ExportError(
            "Chromium isn't installed for Playwright. To enable PNG export and "
            f"the editor's own SVG, run: {install_hint(chromium_only=True)}"
        ) from error


def browser_missing() -> str | None:
    """Why this machine cannot draw a PNG, or None when it can.

    PNG needs Playwright and its Chromium. Asking before anything is written
    lets an export without them fail, or leave the PNG out, cleanly instead
    of stopping halfway with some of its files already on disk.
    """
    try:
        sync_playwright, _ = _playwright()
    except ExportError:
        return f"Playwright isn't installed ({install_hint()})"
    return _probe(sync_playwright)


@cache
def _probe(sync_playwright) -> str | None:
    """Ask Playwright where its Chromium is, once per Playwright: keyed by the
    entry point, so a stand-in's answer is never taken for the real one's.

    A session that answers yes is parked for the render that follows rather
    than closed: starting and stopping Playwright's driver costs seconds on
    Windows, and the probe is always followed by a render.
    """
    manager = sync_playwright()
    try:
        playwright = manager.__enter__()
        executable = getattr(playwright.chromium, "executable_path", None)
    except Exception as error:  # noqa: BLE001 - failing to start the driver is the answer
        with contextlib.suppress(Exception):
            manager.__exit__(None, None, None)
        return f"Playwright could not start: {error}"
    if executable is not None and (not executable or not Path(executable).exists()):
        manager.__exit__(None, None, None)
        return "Chromium isn't installed for Playwright (run: playwright install chromium)"
    # None is a stand-in that cannot say: the launch itself will tell
    _park(sync_playwright, manager, playwright)
    return None


#: Sessions the probe opened, waiting for a render, by thread and entry point:
#: Playwright's sync API belongs to the thread that started it.
_PARKED: dict[tuple[int, int], tuple[Any, Any]] = {}


def _parked_key(sync_playwright) -> tuple[int, int]:
    return threading.get_ident(), id(sync_playwright)


def _park(sync_playwright, manager, playwright) -> None:
    previous = _PARKED.pop(_parked_key(sync_playwright), None)
    if previous is not None:
        with contextlib.suppress(Exception):
            previous[0].__exit__(None, None, None)
    _PARKED[_parked_key(sync_playwright)] = (manager, playwright)


@atexit.register
def _close_parked() -> None:
    """A probe whose export never rendered leaves no driver running."""
    while _PARKED:
        manager, _ = _PARKED.popitem()[1]
        with contextlib.suppress(Exception):
            manager.__exit__(None, None, None)


@contextlib.contextmanager
def _session(sync_playwright):
    """A Playwright session for one render: the probe's, when it parked one in
    this thread, or a new one. Either way it is closed when the render ends."""
    parked = _PARKED.pop(_parked_key(sync_playwright), None)
    if parked is not None:
        manager, playwright = parked
    else:
        manager = sync_playwright()
        playwright = manager.__enter__()
    try:
        yield playwright
    except BaseException:
        if not manager.__exit__(*sys.exc_info()):
            raise
    else:
        manager.__exit__(None, None, None)


def _open_page(
    page, source: Path, theme: str | None, display: str | None, routing: str | None = None
) -> None:
    """Load a page for capture: budget, offline policy, fonts settled."""
    prepare_page(page)
    page.goto(editor_page_url(source, theme, display, routing))
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready")


#: The element every exported editor page carries: the runtime's own script.
#: A page without it never had a runtime and is a static page by design.
_RUNTIME_MARKER = "script[data-infragram-editor]"


def _page_carries_runtime(page) -> bool:
    return bool(page.evaluate(f"Boolean(document.querySelector('{_RUNTIME_MARKER}'))"))


def _await_runtime(page, playwright_error: type[BaseException]) -> None:
    """Give a page's runtime :data:`EDITOR_READY_TIMEOUT_MS` to announce itself.

    A runtime that crashed at startup publishes ``{failed: message}`` (and
    draws a banner); that object is truthy, so the wait alone would go on
    to a capture that returns null and a note blaming the timeout. The
    message is raised instead, so the export says what actually happened.
    """
    if page.evaluate("Boolean(window.infragramEditor)") is False:
        with contextlib.suppress(playwright_error):
            page.wait_for_function("window.infragramEditor", timeout=EDITOR_READY_TIMEOUT_MS)
    failed = page.evaluate("window.infragramEditor && window.infragramEditor.failed")
    if isinstance(failed, str) and failed:
        raise ExportError(f"the editor runtime failed to start: {failed}")


def _stage_editor_capture(page) -> dict:
    """Stage the runtime's own export in the page and return its crop box.

    Raises :class:`ExportError` when the runtime did not publish in time (or
    its export did not parse), the same way the SVG renderer does, so the
    exporter treats both artifacts alike instead of quietly screenshotting
    whatever the page shows for one of them.
    """
    box = page.evaluate(_EDITOR_PNG_CAPTURE, PNG_CONTENT_MARGIN)
    refused = _capture_refused(box, "PNG")
    if refused:
        raise ExportError(refused)
    return box


def _capture_refused(box: object, artifact: str) -> str | None:
    """Why the editor capture staged nothing, or None when it staged a box.

    Three things stop it and they are not the same failure: a runtime that
    never published, an export that does not parse, an export with no size.
    Reporting all three as a timeout sent a reader looking at the clock when
    the drawing itself was the problem.
    """
    if isinstance(box, dict) and "failed" not in box:
        return None
    if isinstance(box, dict):
        return (
            f"the editor runtime published, but no {artifact} can be exported "
            f"from the saved layout: {box['failed']}"
        )
    return _runtime_silent(artifact)


def _runtime_silent(artifact: str) -> str:
    """The page carries the runtime but it never published: say so, with the
    budget, rather than claiming the page has no runtime at all."""
    return (
        f"the editor runtime did not publish within {EDITOR_READY_TIMEOUT_MS} ms, "
        f"so no {artifact} can be exported from the saved layout"
    )


def _capture_static_png(page, output: Path, background: str | None) -> None:
    """Screenshot the inline SVG at its viewBox; see :data:`_PLAIN_SVG_CAPTURE`."""
    diagram = page.locator("svg[data-infragram-diagram]").first
    if diagram.count() == 0:
        diagram = page.locator("svg").first
    if diagram.count() != 1:
        raise ExportError("rendered HTML does not contain an SVG diagram")
    diagram.evaluate(_PLAIN_SVG_CAPTURE)
    if background:
        diagram.evaluate(
            "(element, colour) => element.style.setProperty('background', colour, 'important')",
            background,
        )
    diagram.screenshot(path=str(output), omit_background=not background)


def _capture_editor_png(page, output: Path, background: str | None) -> None:
    """Screenshot the staged export at its crop box; see :func:`_stage_editor_capture`."""
    box = _stage_editor_capture(page)
    page.set_viewport_size(
        {
            "width": max(1, int(box["width"])),
            "height": max(1, int(box["height"])),
        }
    )
    page.evaluate(_EDITOR_PNG_SETTLE)
    if background:
        page.evaluate(
            "colour => { const s = document.querySelector('svg[data-infragram-png-capture]');"
            " if (s) s.style.setProperty('background', colour, 'important'); }",
            background,
        )
    page.locator("svg[data-infragram-png-capture]").screenshot(
        path=str(output), omit_background=not background
    )


def playwright_png_renderer(
    source: Path,
    output: Path,
    scale: float,
    theme: str | None = "light",
    display: str | None = None,
    background: str | None = None,
    routing: str | None = None,
) -> None:
    """Screenshot the diagram alone, cropped to its content, over transparency.

    An exported editor page is a large canvas wrapped in chrome; the PNG is
    the runtime's clean SVG export cropped to the drawn content plus
    :data:`PNG_CONTENT_MARGIN`. A page that never carried the runtime (a
    plain SVG page) is captured at its viewBox, by design. A page that
    carries it but whose runtime did not publish in time, or failed to
    start, raises :class:`ExportError` exactly as
    :func:`playwright_svg_renderer` does; :func:`export_project` then falls
    back to :func:`playwright_static_png_renderer` and says so in a note.
    """

    sync_playwright, playwright_error = _playwright()
    with _session(sync_playwright) as playwright:
        browser = _launch(playwright, playwright_error)
        try:
            page = browser.new_page(device_scale_factor=scale)
            _open_page(page, source, theme, display, routing)
            if not _page_carries_runtime(page):
                _capture_static_png(page, output, background)
                return
            _await_runtime(page, playwright_error)
            _capture_editor_png(page, output, background)
        finally:
            browser.close()


def playwright_static_png_renderer(
    source: Path,
    output: Path,
    scale: float,
    theme: str | None = "light",
    display: str | None = None,
    background: str | None = None,
    routing: str | None = None,
) -> None:
    """Screenshot the static picture embedded in the page, at its viewBox.

    The fallback for a page whose runtime never announced itself: the static
    renderer's picture of the document, which is why :func:`export_project`
    pairs it with a note. The runtime is not waited for again; the first
    renderer already gave it its chance.
    """

    sync_playwright, playwright_error = _playwright()
    with _session(sync_playwright) as playwright:
        browser = _launch(playwright, playwright_error)
        try:
            page = browser.new_page(device_scale_factor=scale)
            _open_page(page, source, theme, display, routing)
            _capture_static_png(page, output, background)
        finally:
            browser.close()


# Serialises the staged, content-cropped copy that _EDITOR_PNG_CAPTURE left in
# the page, as a plain diagram document.
_EDITOR_SVG_SERIALIZE = """
() => {
    const staged = document.querySelector('svg[data-infragram-png-capture]');
    if (!staged) return null;
    const copy = staged.cloneNode(true);
    copy.removeAttribute('data-infragram-png-capture');
    copy.removeAttribute('style');
    copy.setAttribute('data-infragram-diagram', 'true');
    return copy.outerHTML;
}
"""


def render_timeout_ms() -> int:
    """How long a render may wait for a page load or a script, in ms.

    Playwright's 30 s default is sized for a laptop; a single-file editor page
    carries the whole library and a Raspberry Pi under a full test run needs
    longer. 120 s by default, ``INFRAGRAM_RENDER_TIMEOUT_MS`` to override.
    """
    import os

    raw = os.environ.get("INFRAGRAM_RENDER_TIMEOUT_MS", "").strip()
    try:
        value = int(raw) if raw else 120_000
    except ValueError:
        value = 120_000
    return max(1_000, value)


def render_offline() -> bool:
    """Whether a render must not touch the network.

    A page this version exports loads nothing remote: its faces are inline.
    A page exported before they were imports them from Google Fonts, and a
    machine without a reliable route there -- the CI runner -- can sit on
    that request until the page never reaches ``networkidle``, so two passes
    of one render could differ by whether the fonts arrived.
    Every render now refuses those hosts and every other machine
    (:func:`prepare_page`), so ``INFRAGRAM_RENDER_OFFLINE=1`` and ``--offline``
    change nothing; they are read so older scripts keep working.
    """
    import os

    return os.environ.get("INFRAGRAM_RENDER_OFFLINE", "").strip() == "1"


#: The hosts pages from older versions loaded their fonts from.
FONT_HOSTS = re.compile(r"^https?://fonts\.(googleapis|gstatic)\.com/")


#: What a render may load: the page and its inline parts, and this machine
#: (the 3D items are drawn from a page served on 127.0.0.1).
_LOCAL_URL = re.compile(
    r"^(?:file|data|blob|about):|^https?://(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?/", re.I
)


def remote_url(url: str) -> bool:
    """Whether loading *url* would reach another machine.

    A page draws from what it carries. A request anywhere else came from
    the document (an ``<image href>`` in a shared file, say), and would tell
    that server who drew it and when, so every render refuses it.
    """
    return not _LOCAL_URL.match(url)


def prepare_page(page) -> None:
    """Give a freshly opened page the render budget, and cut it off from
    every other machine. The exporter and every browser
    suite open their pages through this, so one policy covers all of them.
    Navigation waits (``goto``, load states) have their own budget and, on
    older Playwright releases, do not inherit the default one."""
    page.set_default_timeout(render_timeout_ms())
    page.set_default_navigation_timeout(render_timeout_ms())
    page.route(remote_url, lambda route: route.abort())


#: How long a page gets to announce its editor runtime before the exporter
#: treats it as a static page. Generous, because a slow machine parses the
#: runtime slowly and a wrong "static" verdict would export the wrong picture.
EDITOR_READY_TIMEOUT_MS = 10_000


def playwright_svg_renderer(
    source: Path,
    output: Path,
    theme: str | None = "light",
    display: str | None = None,
    background: str | None = None,
    routing: str | None = None,
) -> None:
    """Write the editor's own SVG export, cropped like the PNG, as a standalone file.

    The static SVG embedded in the HTML source is the static renderer's picture
    of the document as it was exported. This asks the editor runtime for its
    own export, the picture both renderers are held to, so ``.svg`` and
    ``.png`` show the same picture. Raises
    :class:`ExportError` when Playwright is missing or the page has no editor
    runtime, so callers can fall back to the static render.
    """

    sync_playwright, playwright_error = _playwright()
    with _session(sync_playwright) as playwright:
        browser = _launch(playwright, playwright_error)
        try:
            page = browser.new_page()
            _open_page(page, source, theme, display, routing)
            carries = _page_carries_runtime(page)
            if carries:
                _await_runtime(page, playwright_error)
            box = page.evaluate(_EDITOR_PNG_CAPTURE, PNG_CONTENT_MARGIN)
            refused = _capture_refused(box, "SVG")
            markup = page.evaluate(_EDITOR_SVG_SERIALIZE) if refused is None else None
        finally:
            browser.close()
    if not markup:
        raise ExportError(
            (refused or _runtime_silent("SVG"))
            if carries
            else "rendered HTML has no editor runtime to export an SVG from"
        )
    output.write_text(finish_standalone_svg(markup, background), encoding="utf-8", newline="\n")


def playwright_svg_to_png(source: Path, output: Path, scale: float, transparent: bool) -> None:
    """Draw a finished SVG file as a PNG at ``scale``, the size its root's
    width and height give: the picture a size preset framed
    (:func:`~infragram.exports.framing.frame_svg`) keeps its canvas in the
    PNG too. ``transparent`` keeps what the SVG leaves unpainted clear."""

    opening = re.search(r"<svg\b[^>]*>", source.read_text(encoding="utf-8"))
    tag = opening.group(0) if opening else ""
    found = [re.search(rf'\s{name}="([\d.]+)"', tag) for name in ("width", "height")]
    if found[0] is None or found[1] is None:
        raise ExportError(f"{source.name} gives no width and height to draw a PNG at")
    width, height = float(found[0].group(1)), float(found[1].group(1))
    sync_playwright, playwright_error = _playwright()
    with _session(sync_playwright) as playwright:
        browser = _launch(playwright, playwright_error)
        try:
            page = browser.new_page(
                device_scale_factor=scale,
                viewport={"width": max(1, round(width)), "height": max(1, round(height))},
            )
            prepare_page(page)
            page.goto(source.resolve().as_uri())
            page.wait_for_load_state("networkidle")
            page.evaluate("document.fonts.ready")
            page.locator("svg").first.screenshot(path=str(output), omit_background=transparent)
        finally:
            browser.close()
