"""Record the README's tour of the editor on Azure architectures.

Each architecture is an example a reader can open, walked in the real editor
in Chromium: its numbered steps in order, its frames, captions, lenses and
themes. The recordings become one MP4 and a GIF per architecture.

Run with Python, Playwright Chromium and FFmpeg installed::

    python scripts/docs/regenerate-media.py
"""

from __future__ import annotations

import runpy
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from playwright.sync_api import Page, sync_playwright  # noqa: E402

from infragram.exports import render_project_html  # noqa: E402

IMAGES = ROOT / "docs" / "images"
MEDIA = ROOT / "docs" / "media"
LIT = "document.querySelectorAll('[data-graph-edge][data-focus-edge=true]').length"


def _collect(errors: list[str], error: object) -> None:
    errors.append(str(error))


def encode(*args: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Install FFmpeg and add it to PATH before regenerating media")
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def open_editor(page: Page, source: Path) -> None:
    page.goto(source.as_uri())
    page.wait_for_function("window.infragramEditor && window.infragramEditor.getState")
    page.locator(".app-mascot").wait_for()
    page.evaluate("() => window.infragramEditor.whenSettled()")


def fold(page: Page) -> None:
    # with both panels folded the fit zoom nearly doubles, so the captions
    # stay readable and the flow's dashes keep marching in the GIF
    for toggle in ("[data-sidebar-logo-trigger]", "[data-inspector-toggle]"):
        if page.locator(toggle).get_attribute("aria-expanded") == "true":
            page.locator(toggle).click()
    page.wait_for_timeout(400)
    page.locator('[data-editor-action="zoom-fit"]').click()


def card(page: Page, node_id: str):
    return page.locator(f'[data-graph-node][data-node-id="{node_id}"]')


def park(page: Page) -> None:
    # the pointer rests on the header, where no hover card opens over the drawing
    page.mouse.move(1100, 20)


def shown(page: Page, wires: int | None, hold: int = 1900) -> None:
    """Hold the flow on screen once it animates ``wires`` wires (any, for None)."""
    park(page)
    page.wait_for_function(f"{LIT} === {wires}" if wires is not None else f"{LIT} > 0")
    page.wait_for_timeout(hold)


def flow_of(page: Page, node_id: str, hold: int = 1900) -> None:
    """A click on a card: every wire it joins animates, the rest steps back."""
    wires = page.evaluate(
        "id => window.infragramEditor.getState().edges"
        ".filter(e => e.source === id || e.target === id).length",
        node_id,
    )
    card(page, node_id).click()
    shown(page, wires, hold)


def frame_label(page: Page, frame_id: str) -> tuple[float, float]:
    box = page.locator(f'[data-graph-boundary][data-boundary-id="{frame_id}"]').bounding_box()
    assert box is not None, frame_id
    return box["x"] + 90, box["y"] + 9


def empty_point(page: Page) -> tuple[float, float]:
    point = page.evaluate("""() => {
      const v = document.querySelector('.canvas-viewport').getBoundingClientRect();
      for (let y = v.bottom - 60; y > v.top + 20; y -= 12)
        for (let x = v.right - 60; x > v.left + 20; x -= 12) {
          const el = document.elementFromPoint(x, y);
          if (el && el.closest('[data-infragram-diagram]') && !el.closest(
            '[data-graph-node],[data-graph-boundary],[data-edge-group],[data-edge-label]'))
            return [x, y];
        }
      return null; }""")
    assert point, "no empty canvas"
    return point[0], point[1]


def context_action(page: Page, at: tuple[float, float], action: str) -> None:
    page.mouse.click(*at, button="right")
    page.locator(f'[data-context-action="{action}"]').click()
    park(page)


def wheel_zoom(page: Page, at: tuple[float, float], steps: int) -> None:
    # the wheel zooms about the pointer, as a reader would close in on a part
    page.mouse.move(*at)
    for _ in range(steps):
        page.mouse.wheel(0, -100)
        page.wait_for_timeout(180)
    park(page)


def move_to(page: Page, selector: str, top: bool = False) -> None:
    """Scroll the canvas so ``selector`` sits in the middle, or mid-width with
    its top edge near the top of the view. A jump, not a glide: a glide
    repaints every frame of the GIF."""
    page.evaluate(
        """([selector, top]) => {
          const view = document.querySelector('.canvas-viewport');
          const box = document.querySelector(selector).getBoundingClientRect();
          const frame = view.getBoundingClientRect();
          view.scrollBy(
            box.left + box.width / 2 - (frame.left + frame.width / 2),
            top ? box.top - frame.top - 32
                : box.top + box.height / 2 - (frame.top + frame.height / 2),
          );
        }""",
        [selector, top],
    )
    page.wait_for_timeout(500)


def clear(page: Page) -> None:
    """A click on empty canvas ends the flow without a keyboard focus ring."""
    page.mouse.click(*empty_point(page))
    park(page)


def set_theme(page: Page, choice: str) -> None:
    page.locator("[data-theme-menu] > summary").click()
    page.locator(f'[data-theme-choice="{choice}"]').click()


def tour_front_door(page: Page) -> None:
    """The whole picture; then, close enough to read, a request's numbered
    steps in order from the users through Front Door and App Service to the
    data, and the Steps panel that tells them; then, fitted again, the
    Failover flow."""
    page.wait_for_timeout(1400)
    view = page.locator(".canvas-viewport").bounding_box()
    assert view is not None
    wheel_zoom(page, (view["x"] + view["width"] / 2, view["y"] + view["height"] / 2), 5)
    for node_id in (
        "users",
        "azure-front-door-premium",
        "app-service",
        "private-endpoints",
        "cache-for-redis",
        "azure-sql-database",
        "storage-account",
    ):
        move_to(page, f'[data-graph-node][data-node-id="{node_id}"]')
        flow_of(page, node_id, hold=1300)
    clear(page)
    move_to(page, "[data-step-list]", top=True)
    park(page)
    page.wait_for_timeout(3000)
    page.locator('[data-editor-action="zoom-fit"]').click()
    park(page)
    page.wait_for_timeout(800)
    for node_id in ("azure-sql-geo-secondary", "app-service-warm-standby"):
        flow_of(page, node_id, hold=1500)
    clear(page)
    page.wait_for_timeout(800)


def tour_aks(page: Page) -> None:
    """In the dark theme: what the internet reaches, then closer in, ingress to
    the pods, their private endpoints and their egress."""
    set_theme(page, "dark")
    page.wait_for_timeout(1500)
    context_action(page, empty_point(page), "lens-internet")
    shown(page, None, hold=3400)
    page.keyboard.press("Escape")
    box = card(page, "user-node-pool").bounding_box()
    assert box is not None
    wheel_zoom(page, (box["x"] + box["width"] / 2, box["y"] + box["height"]), 3)
    page.wait_for_timeout(900)
    for node_id in (
        "application-gateway",
        "internal-load-balancer",
        "user-node-pool",
        "private-endpoints",
        "azure-firewall",
    ):
        flow_of(page, node_id)
    page.mouse.click(*frame_label(page, "supply-chain-and-secrets"))
    shown(page, None)
    page.keyboard.press("Escape")
    set_theme(page, "light")


#: Each architecture: its example, the name its GIF goes by, and the walk.
TOUR: tuple[tuple[str, str, Callable[[Page], None]], ...] = (
    ("azure_web_app_front_door", "azure-front-door", tour_front_door),
    ("azure_aks_baseline", "azure-aks", tour_aks),
)


def record_tour(scratch: Path) -> list[tuple[Path, float]]:
    """Each architecture is its own recording, cut in once it is open and
    folded, so no page load shows."""
    takes = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for name, _label, walk in TOUR:
            diagram = runpy.run_path(str(ROOT / "examples" / f"{name}.py"), run_name="tour")
            source = scratch / f"{name}.html"
            source.write_text(
                render_project_html(diagram["diagram"].to_project()),
                encoding="utf-8",
                newline="\n",
            )
            context = browser.new_context(
                viewport={"width": 1600, "height": 1000},
                record_video_dir=str(scratch / name),
                record_video_size={"width": 1600, "height": 1000},
            )
            page = context.new_page()
            errors: list[str] = []
            page.on("pageerror", partial(_collect, errors))
            started = time.monotonic()
            open_editor(page, source)
            fold(page)
            page.wait_for_timeout(600)
            lead_in = time.monotonic() - started
            page.wait_for_timeout(1700)
            walk(page)
            assert not errors, (name, errors)
            video = page.video
            assert video is not None
            context.close()
            takes.append((Path(video.path()), lead_in))
        browser.close()
    return takes


def to_mp4(recording: Path, lead_in: float, target: Path) -> None:
    encode(
        "-ss", str(lead_in), "-i", str(recording), "-an", "-r", "20",
        "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(target),
    )  # fmt: skip


def to_gif(movie: Path, target: Path, width: int = 860, fps: int = 8) -> None:
    encode(
        "-i",
        str(movie),
        "-filter_complex",
        # Eight frames a second keep the flow's dashes marching; 32 colours,
        # no dither and rectangle diffs keep each GIF a few megabytes.
        f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];"
        "[a]palettegen=stats_mode=diff:max_colors=32[p];"
        "[b][p]paletteuse=dither=none:diff_mode=rectangle",
        "-loop",
        "0",
        str(target),
    )


def main() -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    MEDIA.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="infragram-tour-") as folder:
        scratch = Path(folder)
        parts = []
        for index, (recording, lead_in) in enumerate(record_tour(scratch)):
            parts.append(scratch / f"part-{index}.mp4")
            to_mp4(recording, lead_in, parts[-1])
        listing = scratch / "parts.txt"
        listing.write_text("".join(f"file '{part.as_posix()}'\n" for part in parts))
        target = MEDIA / "infragram-tour.mp4"
        encode("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(target))
        for part, (_name, label, _walk) in zip(parts, TOUR, strict=True):
            to_gif(part, IMAGES / f"infragram-tour-{label}.gif")
    print(f"Wrote {target.relative_to(ROOT)} and a GIF per architecture in docs/images")


if __name__ == "__main__":
    main()
