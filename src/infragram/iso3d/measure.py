"""Measure an icon's ink the way the shipped table was measured.

A 128 px raster in Chromium: on each side, 33 lines from edge to edge record
where the first ink is (the device), or that the first ink is a detail (a
dashed outline, a badge) the wire may pass, or that the line meets nothing.
The build tool measures every shipped icon into ``ink-profiles.json``; the
compose-time renderer measures each dynamic render once and caches the
result beside it. Both go through :func:`measure_in_page`.
"""

from __future__ import annotations

import base64

from ..catalog.ink import EDGE_LEVELS, EDGE_LINES, EDGE_NONE, SIDES

SIZE = 128  # raster size per icon; insets are stored as fractions of it
ALPHA = 64  # a pixel counts as ink above this alpha
MAIN = 0.35  # a piece of ink under this share of the largest is a detail

MEASURE_JS = """
async (entries) => {
  const size = %d, alpha = %d, lines = %d, main = %f;
  const canvas = document.createElement('canvas');
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  const out = {};
  for (const [key, uri] of entries) {
    const img = new Image();
    const loaded = new Promise((resolve) => { img.onload = () => resolve(true); img.onerror = () => resolve(false); });
    img.src = uri;
    if (!(await loaded) || !img.naturalWidth || !img.naturalHeight) { out[key] = null; continue; }
    // xMidYMid meet: the artwork keeps its aspect and is centred in the square.
    const scale = Math.min(size / img.naturalWidth, size / img.naturalHeight);
    const w = img.naturalWidth * scale, h = img.naturalHeight * scale;
    ctx.clearRect(0, 0, size, size);
    ctx.drawImage(img, (size - w) / 2, (size - h) / 2, w, h);
    const data = ctx.getImageData(0, 0, size, size).data;
    const opaque = (x, y) => data[(y * size + x) * 4 + 3] > alpha;
    // The separate pieces of ink (8-neighbour). A piece under `main` of the
    // largest is a detail -- a wifi arc above a router, a sparkle -- and a
    // link must neither land on one nor run through one to reach the device.
    const piece = new Int32Array(size * size).fill(-1), areas = [];
    for (let start = 0; start < size * size; start += 1) {
      if (piece[start] >= 0 || !opaque(start %% size, (start / size) | 0)) continue;
      const id = areas.length, stack = [start];
      let area = 0;
      piece[start] = id;
      while (stack.length) {
        const at = stack.pop(), x = at %% size, y = (at / size) | 0;
        area += 1;
        for (let dy = -1; dy <= 1; dy += 1) for (let dx = -1; dx <= 1; dx += 1) {
          const nx = x + dx, ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= size || ny >= size) continue;
          const next = ny * size + nx;
          if (piece[next] < 0 && opaque(nx, ny)) { piece[next] = id; stack.push(next); }
        }
      }
      areas.push(area);
    }
    const biggest = areas.reduce((most, area) => Math.max(most, area), 0);
    // How far in, in raster pixels, the first ink lies along one line across
    // a side: i when that ink is the device, -2 - i when it is a detail, -1
    // when the line meets none. Left and right lines run top to bottom; top
    // and bottom lines run left to right.
    const scan = (side, ratio) => {
      const line = Math.min(size - 1, Math.max(0, Math.round(ratio * (size - 1))));
      for (let i = 0; i < size; i += 1) {
        const [x, y] = side === 'left' ? [i, line] : side === 'right' ? [size - 1 - i, line]
          : side === 'top' ? [line, i] : [line, size - 1 - i];
        if (opaque(x, y)) return areas[piece[y * size + x]] >= main * biggest ? i : -2 - i;
      }
      return -1;
    };
    const edges = {};
    for (const side of ['left', 'right', 'top', 'bottom']) {
      const depths = Array.from({length: lines}, (_, k) => scan(side, k / (lines - 1)));
      // A dashed outline. A line that passes between two dashes of one
      // straight dashed edge -- two details within a few lines of each
      // other at the same depth -- and meets something deeper behind them
      // is held at the dashes' depth, and those dashes become the edge a
      // link seats on. Details that flank no such line, like the arcs over
      // a router or a badge on a corner, stay decorations.
      const out = depths.slice();
      const usable = new Set();
      const detailAt = k => -2 - depths[k];
      const step = 3 * size / 64;
      for (let k = 0; k < lines; k += 1) {
        if (depths[k] < 0) continue;
        let a = k - 1, b = k + 1;
        while (a >= 0 && depths[a] >= -1) a -= 1;
        while (b < lines && depths[b] >= -1) b += 1;
        if (a < 0 || b >= lines || b - a > 4) continue;
        const da = detailAt(a), db = detailAt(b);
        if (Math.abs(da - db) > step) continue;
        const outline = Math.min(da, db);
        if (depths[k] > outline) { out[k] = outline; usable.add(a); usable.add(b); }
      }
      // A dash that held a line makes its whole run of dashes the edge.
      for (const start of [...usable]) {
        for (const dir of [-1, 1]) {
          for (let k = start + dir; k >= 0 && k < lines && depths[k] <= -2; k += dir) {
            if (Math.abs(detailAt(k) - detailAt(start)) > step) break;
            usable.add(k);
          }
        }
      }
      usable.forEach(k => { out[k] = detailAt(k); });
      edges[side] = out;
    }
    // How dark the artwork is: the mean relative luminance of its opaque
    // pixels. Artwork below DARK_INK (catalog/ink.py) cannot hold 3:1
    // against a dark canvas, and both renderers draw it light there.
    let total = 0, lit = 0;
    const linear = (value) => { const c = value / 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] <= alpha) continue;
      total += 0.2126 * linear(data[i]) + 0.7152 * linear(data[i + 1]) + 0.0722 * linear(data[i + 2]);
      lit += 1;
    }
    const result = Object.values(edges).every(side => side.every(depth => depth === -1)) ? null : edges;
    if (result && lit) result.tone = Math.round((total / lit) * 1000) / 1000;
    out[key] = result;
  }
  return out;
}
"""


def summarise(edges: dict[str, list[int]]) -> tuple[list[float], str]:
    """One icon's measurement as the table stores it: the bounding-box insets
    (the outermost ink on each side, details included, so other wires keep
    clear of them) and the edge lines in the table's encoding, where a line
    whose first ink is a detail is marked like one that meets none."""
    box, parts = [], []
    for side in SIDES:
        depths = edges[side]
        hits = [depth if depth >= 0 else -2 - depth for depth in depths if depth != -1]
        box.append(round(min(hits) / SIZE, 3) if hits else 0.0)
        parts.append(
            "".join(
                EDGE_NONE
                if depth < 0
                else EDGE_LEVELS[min(len(EDGE_LEVELS) - 1, round(depth * 64 / SIZE))]
                for depth in depths
            )
        )
    return box, "|".join(parts)


def entries_for(edges: dict[str, list[int]]) -> tuple[list[float] | None, str | None]:
    """What the table records for one icon: a profile when its ink box keeps
    air worth crossing, edge lines when any line starts inside the square."""
    box, code = summarise(edges)
    profile = box if max(box) > 0.02 else None
    return profile, (code if set(code) - {"A", "|"} else None)


def measurable(data: bytes) -> bytes:
    """The artwork as a data URI can parse it. Inline primitives are written
    for an SVG document that already declares the namespace; on their own
    they need it, or the image silently fails to load."""
    head = data[:400].decode("utf-8", "replace")
    if "xmlns" in head or not head.lstrip().startswith("<svg"):
        return data
    return data.replace(b"<svg", b'<svg xmlns="http://www.w3.org/2000/svg"', 1)


def measure_in_page(page, items: dict[str, bytes]) -> dict[str, dict | None]:
    """Measure ``items`` (key -> SVG bytes) in an open Playwright page."""
    script = MEASURE_JS % (SIZE, ALPHA, EDGE_LINES, MAIN)
    results: dict[str, dict | None] = {}
    entries = [
        (key, "data:image/svg+xml;base64," + base64.b64encode(measurable(data)).decode("ascii"))
        for key, data in items.items()
    ]
    for start in range(0, len(entries), 200):
        results.update(page.evaluate(script, entries[start : start + 200]))
    return results


def measure(items: dict[str, bytes]) -> dict[str, dict | None]:
    """Measure ``items`` in a browser of their own."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.set_content("<html><body></body></html>")
        try:
            return measure_in_page(page, items)
        finally:
            browser.close()
