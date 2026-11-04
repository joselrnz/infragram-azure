"""Render an item by spec at compose time, cached by its hash.

A diagram that needs a 3U server with twelve bays in the storage colour and
a database badge does not look for it in the table -- it says so::

    from infragram.nodes.iso import Iso
    db = Iso("DB-01", "PostgreSQL", recipe="server", family="storage", glyph="database", units=3, drivesN=12)

:func:`build_spec` turns that into the spec ``scene.js`` builds from, checked
against the recipes and knobs the builder actually offers
(:func:`infragram.iso3d.vocabulary.recipes`). :func:`render_cached` renders it
once in headless Chromium, measures its ink the way the shipped table was
measured, keeps both in the user's cache under the spec hash, and registers
the measurement so the wires seat on the render. The element carries the
spec, the SVG and the measurement in its attributes, so the saved document
draws the same everywhere without the cache.
"""

from __future__ import annotations

import atexit
import json
import queue
import threading
from collections.abc import Callable
from concurrent.futures import Future

from ..catalog import ink
from ..verification import HEX_COLOR
from . import cache
from .measure import entries_for, measure_in_page
from .render import Renderer, spec_hash
from .vocabulary import FAMILY_COLOURS, FAMILY_GLYPH, GLYPHS, glyph_paths, recipes


class SpecError(ValueError):
    """The spec names a recipe, knob, family, colour or glyph the builder does not have."""


def build_spec(
    recipe: str,
    *,
    family: str = "compute",
    colour: str | None = None,
    glyph: str | None = None,
    badge: bool = True,
    **knobs: object,
) -> dict:
    """The spec ``scene.js`` builds from, validated against its recipes.

    ``knobs`` are the recipe's own parameters by name (``units=3``,
    ``kind="nuclear"``); unset ones take the builder's defaults. ``glyph`` is
    a name from the vocabulary or the path data of your own 24-unit mark;
    ``badge=False`` draws none. ``colour`` overrides the family colour.
    """
    table = recipes()
    if recipe not in table:
        raise SpecError(f"unknown recipe {recipe!r}; one of {', '.join(sorted(table))}")
    known = table[recipe]
    names = [name for name, _ in known]
    unknown = sorted(set(knobs) - set(names))
    if unknown:
        raise SpecError(
            f"recipe {recipe!r} has no knob {', '.join(unknown)}; it takes {', '.join(names) or 'none'}"
        )
    args: list[object] = [knobs.get(name, default) for name, default in known]
    while args and args[-1] == known[len(args) - 1][1]:
        args.pop()
    if family not in FAMILY_COLOURS:
        raise SpecError(f"unknown family {family!r}; one of {', '.join(FAMILY_COLOURS)}")
    paint = (colour or FAMILY_COLOURS[family]).strip()
    if not HEX_COLOR.fullmatch(paint):
        raise SpecError(f"colour must be #rrggbb, not {paint!r}")
    if not badge:
        paths: list[str] = []
    elif glyph is None:
        paths = glyph_paths(FAMILY_GLYPH[family])
    elif glyph in GLYPHS:
        paths = glyph_paths(glyph)
    elif glyph.strip()[:1] in ("M", "m"):
        paths = [glyph.strip()]
    else:
        raise SpecError(
            f"unknown glyph {glyph!r}; a name from the vocabulary or path data starting with M"
        )
    return {
        "id": f"{recipe}:{json.dumps(args, separators=(',', ':'))}",
        "recipe": recipe,
        "args": args,
        "kwargs": {},
        "colour": paint.lower(),
        "glyph": "|".join(paths),
    }


class _Worker(threading.Thread):
    """The browser on a thread of its own, warm across renders.

    Playwright's sync API owns an event loop per thread and refuses a second
    session on the same thread; the exporters open their own sessions on the
    main thread, so the renderer lives here and takes jobs through a queue.
    """

    def __init__(self) -> None:
        super().__init__(name="iso3d-renderer", daemon=True)
        self.jobs: queue.Queue[tuple[Callable[[Renderer], object], Future] | None] = queue.Queue()
        self.ready = threading.Event()
        self.failure: BaseException | None = None

    def run(self) -> None:
        try:
            with Renderer() as renderer:
                self.ready.set()
                while True:
                    job = self.jobs.get()
                    if job is None:
                        return
                    fn, future = job
                    try:
                        future.set_result(fn(renderer))
                    except BaseException as error:  # noqa: BLE001  handed back to the caller
                        future.set_exception(error)
        except BaseException as error:  # noqa: BLE001
            self.failure = error
            self.ready.set()

    def submit(self, fn, timeout: float | None = None):
        """Run ``fn(renderer)`` on the worker and hand back its result.

        Bounded: a render that does not come back within ``timeout`` seconds
        (the exporter's budget by default) raises rather than holding the
        caller for good, and the worker is discarded so the next call starts
        a fresh browser instead of queueing behind the stuck job.
        """
        future: Future = Future()
        self.jobs.put((fn, future))
        try:
            return future.result(timeout=render_timeout_seconds() if timeout is None else timeout)
        except TimeoutError:
            _discard(self)
            raise RuntimeError(
                "the 3D renderer did not answer within the render budget "
                "(INFRAGRAM_RENDER_TIMEOUT_MS); the worker was discarded and the next "
                "render starts a new one"
            ) from None


_worker: _Worker | None = None
_lock = threading.Lock()


def render_timeout_seconds() -> float:
    """The exporter's render budget, in seconds; one reading of the variable."""
    from ..exports import render_timeout_ms

    return render_timeout_ms() / 1000


def _discard(worker: _Worker) -> None:
    """Forget a worker that stopped answering; its thread is a daemon and is
    told to stop if it ever reads its queue again."""
    global _worker
    with _lock:
        if _worker is worker:
            _worker = None
    worker.jobs.put(None)


def _renderer_thread(timeout: float | None = None) -> _Worker:
    """The warm worker, started on first use.

    A worker whose browser never came up within ``timeout`` seconds (the
    exporter's budget by default), or that failed to start, is never cached:
    caching it left every later render waiting on a future nothing would
    ever complete. The error names the cause when there is one.
    """
    global _worker
    with _lock:
        if _worker is None:
            worker = _Worker()
            worker.start()
            became_ready = worker.ready.wait(
                timeout=render_timeout_seconds() if timeout is None else timeout
            )
            if worker.failure is not None:
                raise RuntimeError(
                    f"the 3D renderer did not start: {worker.failure}"
                ) from worker.failure
            if not became_ready:
                worker.jobs.put(None)
                raise RuntimeError(
                    "the 3D renderer did not start within the render budget "
                    "(INFRAGRAM_RENDER_TIMEOUT_MS); nothing was cached, the next render retries"
                )
            _worker = worker
            atexit.register(lambda: worker.jobs.put(None))
        return _worker


def render_cached(spec: dict, *, timeout: float | None = None) -> tuple[str, dict, str]:
    """The SVG for a spec, its ink measurement and its hash; rendered once.

    ``timeout`` bounds both the browser start and the render, in seconds;
    the exporter's budget when not given.
    """
    digest = spec_hash(spec)
    path = cache.svg_path(digest)
    entry = cache.read_ink(digest)
    if path.is_file() and entry is not None:
        svg = path.read_text(encoding="utf-8")
    else:

        def job(renderer: Renderer) -> tuple[str, dict]:
            svg = renderer.render_svg(spec)
            measured = measure_in_page(renderer.page, {digest: svg.encode("utf-8")}).get(digest)
            profile, edges = entries_for(measured) if measured else (None, None)
            return svg, {"profile": profile, "edges": edges}

        svg, entry = _renderer_thread(timeout).submit(job, timeout)
        path.write_text(svg, encoding="utf-8", newline="\n")
        cache.write_ink(digest, entry)
    register(svg, entry)
    return svg, entry, digest


def register(svg: str, entry: dict | None) -> None:
    """Make a render's measurement known to the seating rules of this process."""
    entry = entry or {}
    ink.register(ink.artwork_key(svg.encode("utf-8")), entry.get("profile"), entry.get("edges"))
