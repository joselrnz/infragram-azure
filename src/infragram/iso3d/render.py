"""Render one 3D item from its spec, in headless Chromium.

``scene.js`` builds the hardware procedurally in three.js from a spec --
``{"recipe", "args", "kwargs", "colour", "glyph"}`` -- lit and shadowed from
one fixed three-quarter camera onto a transparent canvas. This module serves
the renderer over a local HTTP port (module scripts will not load from
file://), drives it with Playwright, and brings each render down to a
:data:`ICON_PX` palette PNG wrapped in an SVG, the way the imported on-prem
artwork ships. The build script installs the shipped table through it; the
compose-time renderer (``infragram.iso``) renders diagram-specific items
through it and caches them by :func:`spec_hash`.
"""

from __future__ import annotations

import base64
import functools
import hashlib
import http.server
import io
import json
import socketserver
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ICON_PX = 192
#: How a render is encoded; part of the spec hash, so changing it re-renders.
ENCODING = f"png{ICON_PX}-palette256-dithered-lanczos"


def spec_hash(spec: dict) -> str:
    """The hash that names a render: the spec, the builder itself, the encoding.

    The builder is read with its line endings normalised. CRLF or LF cannot
    change what three.js draws, so a hash that moved when they changed was
    answering the wrong question: it called 846 installed renders stale when
    nothing about the render had moved, and re-rendering them would have
    produced the same pixels. What is hashed is the source's content, not the
    bytes a particular checkout wrote it with.
    """
    scene = (HERE / "scene.js").read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(
        json.dumps(spec, sort_keys=True).encode("utf-8") + scene + ENCODING.encode("ascii")
    ).hexdigest()


def wrap(png: bytes) -> str:
    """The render as a self-contained SVG."""
    data = base64.b64encode(png).decode("ascii")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ICON_PX} {ICON_PX}" aria-hidden="true">'
        f'<image width="{ICON_PX}" height="{ICON_PX}" href="data:image/png;base64,{data}"/></svg>\n'
    )


class Renderer:
    """Headless Chromium on a local server, kept open across renders.

    ``root`` is the folder served -- this package's, with the shipped scene,
    unless a candidate scene was staged elsewhere (``iso3d.recipes``).
    """

    #: Errors the page threw while this renderer was open.
    errors: list[str]

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else HERE

    def __enter__(self):
        from playwright.sync_api import sync_playwright

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args, **kwargs):
                pass

        handler = functools.partial(Quiet, directory=str(self.root))
        self.server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch()
        self.page = self.browser.new_page(viewport={"width": 800, "height": 800})
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.goto(f"http://127.0.0.1:{self.server.server_address[1]}/render.html")
        try:
            self.page.wait_for_function("() => window.iso3dReady && window.iso3d", timeout=60000)
        except Exception as error:  # noqa: BLE001 - raised again below, with the page's words
            # a builder that does not load says why before the timeout is blamed
            raise RuntimeError(
                "scene.js did not load: " + "; ".join(self.errors or [str(error)])
            ) from None
        return self

    def __exit__(self, *_):
        self.browser.close()
        self.playwright.stop()
        self.server.shutdown()

    def render(self, spec: dict) -> bytes:
        """One item as an :data:`ICON_PX` PNG with a transparent background."""
        from PIL import Image

        uri = self.page.evaluate("spec => window.iso3d.render(spec)", spec)
        image = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGBA")
        out = io.BytesIO()
        # rendered at 768 and brought down with a proper filter: crisper than
        # rendering small, and a quarter of the bytes an export carries; then
        # 256 colours with dithering, which at icon size cannot be told from
        # the truecolour render and is a quarter of the bytes again
        small = image.resize((ICON_PX, ICON_PX), Image.Resampling.LANCZOS)
        small.quantize(
            256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG
        ).save(out, format="PNG", optimize=True)
        return out.getvalue()

    def render_svg(self, spec: dict) -> str:
        return wrap(self.render(spec))
