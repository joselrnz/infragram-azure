"""The PNG path treats a page whose editor runtime never came up the way the SVG path does.

The SVG renderer raises when ``window.infragramEditor`` never appears and the
exporter falls back to the static picture with a note. The PNG renderer used
to fall through to a plain screenshot of the page silently, so one export
carried a note for the SVG and nothing for a PNG drawn from the same page.

Three pages are told apart, all without a browser:

- a page that never carried the runtime (no ``script[data-infragram-editor]``)
  is a static page by design and is captured at its viewBox;
- a page that carries the runtime but whose runtime did not publish in time
  raises, and the exporter falls back with a note;
- a page whose runtime crashed at startup publishes ``{failed: message}``,
  a truthy object, and the message is what the export reports.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from infragram import exports
from infragram.exports import (
    ExportError,
    export_project,
    playwright_png_renderer,
    playwright_svg_renderer,
)
from infragram.projects import CloudProject

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
TEMPLATE = ROOT / "skills/infragram-azure/assets/templates/cloud/azure-api.infragram.json"


class _FakeError(Exception):
    """Stands in for playwright.sync_api.Error."""


class _Locator:
    """The one inline SVG of a static page, and what is done to it."""

    def __init__(self, page: _Page) -> None:
        self.page = page
        self.first = self

    def count(self) -> int:
        return 1

    def evaluate(self, script: str, *args) -> None:
        self.page.events.append("static-capture")

    def screenshot(self, *, path: str, omit_background: bool) -> None:
        self.page.events.append("static-screenshot")
        Path(path).write_bytes(b"PNG")


class _Page:
    """A loaded page: with or without the runtime's script, published or not."""

    def __init__(self, *, carries_runtime: bool = True, failed: str | None = None) -> None:
        self.carries_runtime = carries_runtime
        self.failed = failed
        self.events: list[str] = []

    def set_default_timeout(self, value: float) -> None:
        pass

    def set_default_navigation_timeout(self, value: float) -> None:
        pass

    def route(self, pattern, handler) -> None:
        pass

    def goto(self, url: str) -> None:
        self.url = url

    def wait_for_load_state(self, state: str) -> None:
        pass

    def evaluate(self, script: str, *args):
        if "data-infragram-editor" in script:
            return self.carries_runtime
        if "Boolean(window.infragramEditor)" in script:
            # a crashed runtime still publishes an object, which is truthy
            return self.failed is not None
        if "window.infragramEditor.failed" in script:
            return self.failed
        if "infragramEditor" in script:
            self.events.append("editor-capture")
        # document.fonts.ready, and the capture script on a page with no runtime
        return None

    def wait_for_function(self, script: str, timeout: float | None = None) -> None:
        self.events.append("waited")
        raise _FakeError("Timeout waiting for window.infragramEditor")

    def set_viewport_size(self, size: dict) -> None:
        raise AssertionError("nothing may be staged from a page without a working runtime")

    def locator(self, selector: str) -> _Locator:
        self.events.append(f"locator {selector}")
        return _Locator(self)


class _Browser:
    def __init__(self, page: _Page) -> None:
        self.page = page

    def new_page(self, **options) -> _Page:
        return self.page

    def close(self) -> None:
        pass


class _Playwright:
    def __init__(self, page: _Page) -> None:
        self.chromium = types.SimpleNamespace(launch=lambda: _Browser(page))

    def __enter__(self) -> _Playwright:
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _install(monkeypatch: pytest.MonkeyPatch, page: _Page) -> _Page:
    api = types.ModuleType("playwright.sync_api")
    api.Error = _FakeError
    api.sync_playwright = lambda: _Playwright(page)
    package = types.ModuleType("playwright")
    package.sync_api = api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)
    monkeypatch.setattr(exports.browser, "EDITOR_READY_TIMEOUT_MS", 10)
    return page


@pytest.fixture
def stuck_page(monkeypatch: pytest.MonkeyPatch) -> _Page:
    return _install(monkeypatch, _Page())


@pytest.fixture
def static_page(monkeypatch: pytest.MonkeyPatch) -> _Page:
    return _install(monkeypatch, _Page(carries_runtime=False))


@pytest.fixture
def crashed_page(monkeypatch: pytest.MonkeyPatch) -> _Page:
    return _install(monkeypatch, _Page(failed="TypeError: cannot read properties of undefined"))


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "page.html"
    source.write_text("<html><body><svg></svg></body></html>", encoding="utf-8")
    return source


def test_the_png_renderer_raises_when_the_runtime_never_publishes(
    tmp_path: Path, stuck_page: _Page
) -> None:
    with pytest.raises(ExportError, match="did not publish within .* no PNG"):
        playwright_png_renderer(_source(tmp_path), tmp_path / "page.png", 1)
    assert "waited" in stuck_page.events, "the runtime was given its chance"
    assert not any(event.startswith("static") for event in stuck_page.events), (
        "no plain screenshot was taken on the quiet"
    )
    assert not (tmp_path / "page.png").exists()


def test_a_page_that_never_carried_a_runtime_is_captured_by_design(
    tmp_path: Path, static_page: _Page
) -> None:
    playwright_png_renderer(_source(tmp_path), tmp_path / "page.png", 1)
    assert (tmp_path / "page.png").read_bytes() == b"PNG"
    assert "waited" not in static_page.events, "a static page is not waited on"
    assert "editor-capture" not in static_page.events
    assert static_page.events[-2:] == ["static-capture", "static-screenshot"]


@pytest.mark.parametrize("renderer", [playwright_png_renderer, playwright_svg_renderer])
def test_a_runtime_that_crashed_at_startup_is_reported_by_its_message(
    tmp_path: Path,
    crashed_page: _Page,
    renderer,
) -> None:
    arguments = (1,) if renderer is playwright_png_renderer else ()
    with pytest.raises(
        ExportError, match="the editor runtime failed to start: TypeError: cannot read"
    ):
        renderer(_source(tmp_path), tmp_path / "page.out", *arguments)
    assert "waited" not in crashed_page.events, "a published object, even a failure, ends the wait"
    assert "editor-capture" not in crashed_page.events, "nothing is captured from a crashed runtime"


def test_the_svg_renderer_still_raises_for_a_page_without_a_runtime(
    tmp_path: Path, static_page: _Page
) -> None:
    """The SVG has a static fallback of its own in the exporter; the renderer just says so."""
    with pytest.raises(ExportError, match="no editor runtime to export an SVG from"):
        playwright_svg_renderer(_source(tmp_path), tmp_path / "page.svg")
    assert "waited" not in static_page.events


def test_the_exporter_notes_the_png_fallback_like_the_svg_one(
    tmp_path: Path,
    stuck_page: _Page,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static_calls: list[tuple[Path, Path, float]] = []

    def fake_static(
        source: Path, output: Path, scale: float, theme=None, display=None, background=None
    ) -> None:
        static_calls.append((source, output, scale))
        output.write_bytes(b"PNG")

    monkeypatch.setattr(exports.project, "playwright_static_png_renderer", fake_static)
    project = CloudProject.load(TEMPLATE)
    result = export_project(project, tmp_path, formats=("png",), scale=2, overwrite=True)
    assert result.png is not None and result.png.read_bytes() == b"PNG"
    # Drawn in the staging folder beside the output, then moved into place.
    assert [(source.name, output.name, scale) for source, output, scale in static_calls] == [
        (f"{project.slug}.html", f"{project.slug}.png", 2)
    ]
    assert len(result.notes) == 1
    assert result.notes[0].startswith(f"{project.slug}.png was drawn by the static renderer")
    assert "did not publish within" in result.notes[0] and "no PNG" in result.notes[0]


def test_the_crash_message_reaches_the_export_note(
    tmp_path: Path,
    crashed_page: _Page,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_static(
        source: Path, output: Path, scale: float, theme=None, display=None, background=None
    ) -> None:
        output.write_bytes(b"PNG")

    monkeypatch.setattr(exports.project, "playwright_static_png_renderer", fake_static)
    result = export_project(CloudProject.load(TEMPLATE), tmp_path, formats=("png",), overwrite=True)
    assert result.notes and "the editor runtime failed to start: TypeError" in result.notes[0]


def test_an_injected_png_renderer_that_refuses_gets_the_same_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refusing(source: Path, output: Path, scale: float) -> None:
        raise ExportError("no runtime (simulated)")

    def fake_static(
        source: Path, output: Path, scale: float, theme=None, display=None, background=None
    ) -> None:
        output.write_bytes(b"PNG")

    monkeypatch.setattr(exports.project, "playwright_static_png_renderer", fake_static)
    project = CloudProject.load(TEMPLATE)
    result = export_project(
        project, tmp_path, formats=("png",), png_renderer=refusing, overwrite=True
    )
    assert result.png is not None and result.png.read_bytes() == b"PNG"
    assert result.notes and "no runtime (simulated)" in result.notes[0]


def test_without_a_browser_there_is_no_png_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback needs Playwright too; its own error is the one raised."""

    def refusing(source: Path, output: Path, scale: float) -> None:
        raise ExportError("no runtime (simulated)")

    def no_browser(
        source: Path, output: Path, scale: float, theme=None, display=None, background=None
    ) -> None:
        raise ExportError("Playwright isn't installed.")

    monkeypatch.setattr(exports.project, "playwright_static_png_renderer", no_browser)
    with pytest.raises(ExportError, match="Playwright isn't installed"):
        export_project(
            CloudProject.load(TEMPLATE),
            tmp_path,
            formats=("png",),
            png_renderer=refusing,
            overwrite=True,
        )


def test_the_probe_hands_its_session_to_the_render(
    tmp_path: Path, static_page: _Page, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asking whether Chromium is there and drawing the PNG share one
    Playwright session: starting its driver twice cost seconds an export."""
    api = sys.modules["playwright.sync_api"]
    started: list[_Playwright] = []
    make = api.sync_playwright

    def counting() -> _Playwright:
        started.append(make())
        return started[-1]

    monkeypatch.setattr(api, "sync_playwright", counting)
    assert exports.browser._probe(counting) is None
    playwright_png_renderer(_source(tmp_path), tmp_path / "page.png", 1)
    assert len(started) == 1, "the render took the probe's session"
    assert not exports.browser._PARKED, "nothing is left parked once the render is done"
    playwright_png_renderer(_source(tmp_path), tmp_path / "page.png", 1)
    assert len(started) == 2, "a render with no parked session starts its own"
