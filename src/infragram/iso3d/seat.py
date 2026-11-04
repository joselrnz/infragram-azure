"""Where a link would land on an icon, and whether it lands on the device.

The renderers place one connection point per side of an icon-look node:
at the usable middle of the side's edge lines, slid along to ink, and in
by the edge's depth. This module re-does that
placement for one measured icon and looks at the pixels there in Chromium:
the point must be on ink (``ok``), not in air more than a few pixels past
it (``floats``), and the line running inward from it must not meet air
after ink (``cuts`` -- a thin protrusion at the edge with nothing solid
behind it, where a wire would seem to pierce the thing). The build tools
and ``infragram recipe:try`` run it on every render.
"""

from __future__ import annotations

import base64

from ..catalog import ink
from .measure import SIZE, measurable

SIDES = ("left", "right", "top")
GAP = 9  # raster pixels of air past which a point floats

SEAT_JS = """
async (entries) => {
  const S = %d, GAP = %d, OUT = {left: [-1, 0], right: [1, 0], top: [0, -1]};
  const canvas = Object.assign(document.createElement('canvas'), {width: S, height: S});
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  const out = {};
  for (const e of entries) {
    const img = await new Promise(ok => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => ok(null); i.src = e.uri; });
    if (!img) { out[e.id] = {left: 'unreadable', right: 'unreadable', top: 'unreadable'}; continue; }
    ctx.clearRect(0, 0, S, S); ctx.drawImage(img, 0, 0, S, S);
    const px = ctx.getImageData(0, 0, S, S).data;
    const at = (x, y) => { x = Math.round(x); y = Math.round(y); return x >= 0 && y >= 0 && x < S && y < S && px[(y * S + x) * 4 + 3] > 64; };
    const res = {};
    for (const side of ['left', 'right', 'top']) {
      const [x, y] = e.points[side], [ox, oy] = OUT[side];
      let gap = 99;
      for (let s = -1; s < 60; s += 1) if (at(x - ox * s, y - oy * s)) { gap = Math.max(0, s); break; }
      let cuts = false, air = 0;
      for (let s = 1; s < S; s += 1) { const qx = x + ox * s, qy = y + oy * s; if (qx < 0 || qy < 0 || qx >= S || qy >= S) break;
        if (!at(qx, qy)) { air += 1; continue; } if (air >= 2) { cuts = true; break; } }
      res[side] = cuts ? 'cuts' : gap > GAP ? 'floats' : 'ok';
    }
    out[e.id] = res;
  }
  return out;
}
"""


def points_for(profile: list[float] | None, code: str | None) -> dict[str, list[float]]:
    """The connection point per side, in raster pixels, placed the way the
    renderers place it."""
    box = profile or [0.0, 0.0, 0.0, 0.0]
    size = SIZE
    x0, x1, y0, y1 = box[0] * size, size - box[1] * size, box[2] * size, size - box[3] * size
    points: dict[str, list[float]] = {}
    for side in SIDES:
        x = x0 if side == "left" else x1 if side == "right" else (x0 + x1) / 2
        y = y0 if side == "top" else (y0 + y1) / 2
        middle = ink.usable_middle(code, side)
        along = middle if middle is not None else (y if side != "top" else x) / size
        slid = ink.inked_along(code, side, along)
        if side == "top":
            x = slid * size
        else:
            y = slid * size
        depth = ink.edge_depth(code, side, slid)
        if depth is not None:
            if side == "left":
                x = max(x, depth * size)
            elif side == "right":
                x = min(x, size - depth * size)
            else:
                y = max(y, depth * size)
        points[side] = [round(x, 2), round(y, 2)]
    return points


def seat_in_page(
    page, items: dict[str, tuple[bytes, list[float] | None, str | None]]
) -> dict[str, dict[str, str]]:
    """``items`` maps a key to (SVG bytes, profile, edge code) as measured;
    the result maps it to a status per side."""
    entries = [
        {
            "id": key,
            "uri": "data:image/svg+xml;base64,"
            + base64.b64encode(measurable(data)).decode("ascii"),
            "points": points_for(profile, code),
        }
        for key, (data, profile, code) in items.items()
    ]
    results: dict[str, dict[str, str]] = {}
    for start in range(0, len(entries), 100):
        results.update(page.evaluate(SEAT_JS % (SIZE, GAP), entries[start : start + 100]))
    return results
