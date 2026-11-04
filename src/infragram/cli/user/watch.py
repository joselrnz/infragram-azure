"""``infragram compose <file.py> --watch``: draw the diagram again every time
its file is saved, and show it in a browser page that reloads by itself.

D2, LikeC4 and Structurizr all have this loop; without it, every change to a
diagram file was an export and a reload by hand. The watcher

* composes the file once, then polls it (and the other ``.py`` files beside
  it, which a diagram may import) twice a second -- no dependency;
* composes each change in a fresh ``python -m infragram compose`` process,
  so a module the diagram imports is read again and a crash cannot take the
  watcher down;
* serves one page from ``127.0.0.1`` (never another interface): the
  exported editor in a frame, reloaded when a compose succeeds, and the
  error, with the file and line it names, laid over the last good picture
  when one fails. Server-sent events carry the news; nothing is fetched from
  outside, so it works offline.

The HTML goes where ``--output-dir`` says, as a plain compose would write it.
Ctrl+C stops it.
"""

from __future__ import annotations

import html
import http.server
import json
import os
import queue
import socketserver
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

__all__ = ["Watcher", "watch"]

_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{title} (watching)</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
html,body{{margin:0;height:100%;background:#fafafa;font:13px/1.4 system-ui,sans-serif;color:#1f2328}}
iframe{{border:0;width:100%;height:100%;display:block}}
#bar{{position:fixed;left:12px;bottom:12px;padding:4px 10px;border-radius:12px;background:#ffffffe6;
box-shadow:0 1px 3px #0003;font-size:12px}}
#error{{position:fixed;inset:auto 12px 44px 12px;max-height:45%;overflow:auto;padding:12px 14px;
border-radius:8px;background:#fdeded;border:1px solid #c62828;color:#6b1111;white-space:pre-wrap;
font:12px/1.5 ui-monospace,monospace;display:none}}
</style></head><body>
<iframe id="page" src="{page}?fresh=watch-{version}" title="{title}"></iframe>
<div id="bar">watching {source} &middot; <span id="state">drawn</span></div>
<pre id="error"></pre>
<script>
const frame = document.getElementById('page'), state = document.getElementById('state'),
      error = document.getElementById('error');
const events = new EventSource('/events');
events.addEventListener('drawing', () => {{ state.textContent = 'drawing…'; }});
events.addEventListener('drawn', event => {{
  const data = JSON.parse(event.data);
  error.style.display = 'none';
  state.textContent = 'drawn ' + data.at;
  // a fresh workspace each time: the page draws what the file now says,
  // not what an earlier version left in the browser's storage
  frame.src = data.page + '?fresh=watch-' + data.version;
}});
events.addEventListener('failed', event => {{
  const data = JSON.parse(event.data);
  state.textContent = 'not drawn: the last good picture stays';
  error.textContent = data.message;
  error.style.display = 'block';
}});
</script></body></html>
"""


class Watcher:
    """One watched diagram file: composes it and tells the page."""

    def __init__(
        self,
        spec: Path,
        output_dir: Path,
        arguments: list[str],
        *,
        compose: Callable[[list[str]], tuple[bool, str]] | None = None,
    ) -> None:
        self.spec = spec.resolve()
        self.output_dir = output_dir.resolve()
        self.arguments = arguments
        self.compose = compose or _compose_in_a_process
        self.version = 0
        self.page = ""
        self.title = self.spec.stem
        self.listeners: list[queue.Queue] = []
        self.lock = threading.Lock()

    def stamps(self) -> dict[Path, float]:
        """The modification times the watcher compares: the file and the
        Python beside it that it may import."""
        out: dict[Path, float] = {}
        for path in [self.spec, *self.spec.parent.glob("*.py")]:
            try:
                out[path] = path.stat().st_mtime
            except OSError:
                continue
        return out

    def publish(self, event: str, data: dict) -> None:
        with self.lock:
            for listener in list(self.listeners):
                listener.put((event, data))

    def draw(self) -> bool:
        """Compose once; True when it drew."""
        self.publish("drawing", {})
        ok, output = self.compose(
            [
                str(self.spec),
                "--formats",
                "html",
                "--output-dir",
                str(self.output_dir),
                *self.arguments,
            ]
        )
        if not ok:
            self.publish("failed", {"message": output.strip() or "the compose failed"})
            return False
        pages = sorted(
            self.output_dir.glob("*.html"), key=lambda path: path.stat().st_mtime, reverse=True
        )
        if pages:
            self.page = pages[0].name
        self.version += 1
        self.publish(
            "drawn", {"page": self.page, "version": self.version, "at": time.strftime("%H:%M:%S")}
        )
        return True

    def run(self, stop: threading.Event, interval: float = 0.5) -> None:
        """Poll until *stop* is set, composing after each change settles."""
        seen = self.stamps()
        while not stop.wait(interval):
            now = self.stamps()
            if now != seen:
                # an editor writes in steps; draw once it has finished
                time.sleep(0.15)
                seen = self.stamps()
                self.draw()


def _compose_in_a_process(arguments: list[str]) -> tuple[bool, str]:
    # the same package the watcher runs from, whatever else is installed
    import infragram

    package_root = str(Path(infragram.__file__).resolve().parent.parent)
    path = os.pathsep.join(filter(None, [package_root, os.environ.get("PYTHONPATH", "")]))
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": path}
    result = subprocess.run(
        [sys.executable, "-P", "-m", "infragram", "compose", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    return result.returncode == 0, (result.stderr or "") + (
        result.stdout if result.returncode else ""
    )


def _handler(watcher: Watcher) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, directory=str(watcher.output_dir), **kwargs)

        def log_message(self, *_args) -> None:  # the terminal is for the watcher's own lines
            return

        def do_GET(self) -> None:  # the http.server name
            if self.path in ("/", "/index.html"):
                body = _PAGE.format(
                    title=html.escape(watcher.title),
                    page=html.escape(watcher.page),
                    version=watcher.version,
                    source=html.escape(watcher.spec.name),
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                listener: queue.Queue = queue.Queue()
                with watcher.lock:
                    watcher.listeners.append(listener)
                try:
                    while True:
                        try:
                            event, data = listener.get(timeout=15)
                            self.wfile.write(
                                f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()
                            )
                        except queue.Empty:
                            self.wfile.write(b": still watching\n\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                finally:
                    with watcher.lock:
                        watcher.listeners.remove(listener)
                return
            super().do_GET()

    return Handler


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(watcher: Watcher, port: int = 0) -> _Server:
    """The page's server on 127.0.0.1, started on a thread; ``port`` 0 picks one."""
    server = _Server(("127.0.0.1", port), _handler(watcher))
    threading.Thread(target=server.serve_forever, name="infragram-watch", daemon=True).start()
    return server


def watch(spec: Path, output_dir: Path, arguments: list[str], port: int = 0) -> int:
    """Compose, serve, and redraw on every save until Ctrl+C."""
    watcher = Watcher(spec, output_dir, arguments)
    if not watcher.draw():
        print("NOTE     the first compose failed; fix the file and save it", file=sys.stderr)
    server = serve(watcher, port)
    # a socket bound to an IPv4 address names it as (host text, port)
    host, bound = cast(tuple[str, int], server.server_address[:2])
    print(f"WATCH    {watcher.spec.name} -> http://{host}:{bound}/  (Ctrl+C stops)")
    stop = threading.Event()
    try:
        watcher.run(stop)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.shutdown()
    return 0
