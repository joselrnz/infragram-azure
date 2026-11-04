#!/usr/bin/env python3
"""Write one page holding every containment frame the skill ships, drawn.

Each tile is a real render: a project containing that one frame, put through
the same renderer an export uses, with the badge resolved from its theme. The
page therefore cannot drift from the product -- when a badge changes,
regenerating shows it, and the diff of the reviewed record in
``assets/catalog/frame-badges.json`` says which frame moved and why.

    python scripts/tools/frame-gallery.py                  # docs/frames/index.html
    python scripts/tools/frame-gallery.py --out some.html  # somewhere else
"""

from __future__ import annotations

import argparse
import html
import importlib
import inspect
import re
import sys
from pathlib import Path

REPO = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
sys.path.insert(0, str(REPO / "src"))

from infragram.builders.architecture import load_style  # noqa: E402
from infragram.catalog.frame_badges import frame_badges  # noqa: E402
from infragram.exports import render_project_svg  # noqa: E402
from infragram.nodes import Frame, infragram as shared, reset_ids  # noqa: E402
from infragram.patterns import Blueprint  # noqa: E402

DEFAULT_OUT = REPO / "docs" / "frames" / "index.html"

#: Gallery -> the provider library a one-frame project is filed under. The
#: core frames belong to no vendor, so their project opens in the Azure
#: library while the frames keep the neutral ``generic`` theme.
PROVIDER = {"generic": "azure"}

#: Reading order: the cloud first, then the platform, then the neutral set.
ORDER = ["azure", "kubernetes", "generic"]


def frame_classes(group: str) -> list[type[Frame]]:
    module = importlib.import_module(f"infragram.nodes.frames.{group}")
    return [
        cls
        for name in sorted(dir(module))
        if inspect.isclass(cls := getattr(module, name))
        and issubclass(cls, Frame)
        and getattr(cls, "KIND", None)
        and getattr(cls, "FRAME_ID", None)
    ]


def tile(cls: type[Frame], provider: str) -> str:
    """The frame, alone, as an inline SVG sized for a tile."""
    reset_ids()
    plan = Blueprint.fresh("frame", cls.LABEL or cls.__name__, "One frame, drawn alone.")
    plan.kind = "single-cloud"
    plan.providers = (provider,)
    (frame,) = plan.add(cls(cls.LABEL or cls.__name__))
    frame >> shared.compute.PhysicalServer("", "")
    svg = render_project_svg(plan.to_project()).split("?>", 1)[-1].strip()
    # Let the tile size it: the viewBox carries the shape.
    svg = re.sub(r'\s(?:width|height)="[^"]*"', "", svg, count=2)
    return svg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="where to write the page (default: docs/frames/index.html)",
    )
    options = parser.parse_args()
    record = frame_badges().libraries
    sections, badged, blank = [], 0, 0

    for group in ORDER:
        provider = PROVIDER.get(group, group)
        try:
            icons = dict(load_style(provider).cluster.icons or {})
        except Exception:
            icons = {}
        cards = []
        for cls in frame_classes(group):
            reference = icons.get(cls.KIND, "")
            if reference:
                badged += 1
                note = f'<span class="ref">{html.escape(reference)}</span>'
            else:
                blank += 1
                why = record[group].blank.get(cls.KIND, "") if group in record else ""
                note = f'<span class="why" title="{html.escape(why)}">unbranded on purpose</span>'
            cards.append(
                f'<figure><div class="pic">{tile(cls, provider)}</div>'
                f"<figcaption><b>{html.escape(cls.__name__)}</b>"
                f'<span class="kind">{html.escape(cls.KIND)}</span>{note}</figcaption></figure>'
            )
        with_art = sum(1 for c in frame_classes(group) if icons.get(c.KIND))
        sections.append(
            f'<section id="{group}"><h2>{group}'
            f'<span class="count">{len(cards)} frames · {with_art} with vendor artwork</span></h2>'
            f'<div class="grid">{"".join(cards)}</div></section>'
        )

    nav = " ".join(f'<a href="#{g}">{g}</a>' for g in ORDER)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Infragram Azure · every containment frame</title>
<style>
  :root {{ --ink:#0f1b2a; --muted:#455168; --soft:#5f6b7a; --line:#e6eaef; --paper:#fff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:32px 34px 60px; background:var(--paper); color:var(--ink);
         font-family:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif; }}
  h1 {{ font-size:24px; margin:0 0 6px; letter-spacing:-.01em; }}
  p.lede {{ margin:0 0 4px; color:var(--muted); font-size:13.5px; max-width:78ch; line-height:1.55; }}
  p.meta {{ margin:10px 0 0; color:var(--soft); font-size:12px;
            font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
  nav {{ margin:20px 0 6px; padding:12px 0; border-top:1px solid var(--line);
         border-bottom:1px solid var(--line); font-size:11.5px; }}
  nav a {{ color:var(--soft); text-decoration:none; margin-right:14px;
           font-family:ui-monospace,monospace; }}
  nav a:hover {{ color:var(--ink); text-decoration:underline; }}
  nav a:focus-visible, figure:focus-visible {{ outline:2px solid #2e5aa8; outline-offset:2px; }}
  h2 {{ font-size:13px; text-transform:uppercase; letter-spacing:.08em; margin:34px 0 12px;
        padding-bottom:7px; border-bottom:1px solid var(--line); }}
  .count {{ float:right; font-size:11px; font-weight:400; text-transform:none;
            letter-spacing:0; color:var(--soft); }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(232px,1fr)); gap:16px; }}
  figure {{ margin:0; border:1px solid var(--line); border-radius:8px; overflow:hidden;
            background:var(--paper); }}
  .pic {{ padding:12px; background:#fcfdfe; border-bottom:1px solid var(--line); }}
  .pic svg {{ display:block; width:100%; height:auto; }}
  figcaption {{ padding:10px 12px 12px; font-size:12.5px; line-height:1.5; }}
  figcaption b {{ display:block; }}
  .kind, .ref, .why {{ display:block; font-size:10.5px;
                       font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
  .kind {{ color:var(--soft); }}
  .ref {{ color:#2e5aa8; margin-top:2px; }}
  .why {{ color:#94a0ad; margin-top:2px; cursor:help; }}
  @media print {{ body {{ padding:0; }} figure {{ break-inside:avoid; }} }}
</style></head><body>
  <h1>Every containment frame</h1>
  <p class="lede">Each tile is a real render: a project holding that one frame, put through the
  same renderer an export uses, with the badge resolved from its theme. A blue reference means the
  vendor ships artwork for that boundary; the rest stay unbranded on purpose, because a near-miss
  icon states something false. Hover an unbranded frame for the recorded reason.</p>
  <p class="meta">{badged + blank} frames · {badged} with vendor artwork · {blank} unbranded ·
  generated from the code, not written by hand</p>
  <nav>{nav}</nav>
  {"".join(sections)}
</body></html>"""
    target = options.out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8", newline="\n")
    print(f"{badged + blank} frames ({badged} badged, {blank} unbranded) -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
