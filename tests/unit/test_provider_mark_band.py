"""The provider mark has a band of its own below the drawing.

The mark used to sit at the bottom-left of the canvas while frames were laid
out without regard to it, so an outermost frame ran straight through the
Microsoft wordmark. Both renderers now seat the mark one gap below the lowest
frame or card and extend the picture to hold it, and the checker refuses a
picture where the mark touches anything.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from infragram.builders import metrics
from infragram.builders.scene import Canvas, Style
from infragram.exports import render_project_svg
from infragram.nodes import infragram as shared, reset_ids
from infragram.nodes.frames import azure, kubernetes
from infragram.patterns import Blueprint

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())
MARK = metrics.mark()
_MARK = re.compile(
    r'<svg data-brand-mark="" x="([\d.]+)" y="([\d.]+)" width="(\d+)" height="(\d+)"'
)
_FRAME = re.compile(
    r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)" rx="\d+" fill="[^"]*"/>'
)
_VIEW = re.compile(r'viewBox="0 0 (\d+) (\d+)"')


def _checker():
    spec = importlib.util.spec_from_file_location(
        "project_check", ROOT / "skills" / "infragram-azure" / "scripts" / "project_check.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _framed(provider: str, frame_cls: type):
    reset_ids()
    plan = Blueprint.fresh("mark-band", "mark band", "One outer frame.")
    plan.kind = "single-cloud"
    plan.providers = (provider,)
    (frame,) = plan.add(frame_cls(frame_cls.LABEL or frame_cls.__name__))
    frame >> shared.compute.PhysicalServer("Host", "one")
    return plan.to_project()


@pytest.mark.parametrize(
    "provider,frame_cls", [("azure", azure.Tenant), ("kubernetes", kubernetes.Cluster)]
)
def test_the_static_picture_seats_the_mark_below_the_outer_frame(
    provider: str, frame_cls: type
) -> None:
    svg = render_project_svg(_framed(provider, frame_cls))
    mark = _MARK.search(svg)
    assert mark, "no provider mark drawn"
    mark_x, mark_y, _mark_w, mark_h = (float(v) for v in mark.groups())
    frames = [tuple(int(v) for v in m.groups()) for m in _FRAME.finditer(svg)]
    assert frames, "no frame box drawn"
    lowest = max(y + h for _x, y, _w, h in frames)
    assert mark_y >= lowest + MARK["gap"], (
        f"mark at y={mark_y} rides over a frame ending at {lowest}"
    )
    view = _VIEW.search(svg)
    assert view and mark_y + mark_h <= int(view.group(2)), "the picture does not hold the mark"
    errors: list[str] = []
    _checker().check_svg(svg, errors)
    assert not [e for e in errors if "provider mark" in e], errors


def test_the_checker_refuses_a_mark_that_touches_a_frame() -> None:
    svg = render_project_svg(_framed("azure", azure.Tenant))
    frame = _FRAME.search(svg)
    assert frame
    inside_y = int(frame.group(2)) + int(frame.group(4)) - 10
    tampered = _MARK.sub(
        lambda m: m.group(0).replace(f'y="{m.group(2)}"', f'y="{inside_y}"'), svg, count=1
    )
    assert tampered != svg
    errors: list[str] = []
    _checker().check_svg(tampered, errors)
    assert any(e.startswith("provider mark overlaps frame") for e in errors), errors


def test_the_band_numbers_come_from_the_shared_metrics() -> None:
    assert Canvas().mark_gap == MARK["gap"]
    assert Style().mark_height == MARK["height"]
    from infragram.editor.bundle import runtime_script

    runtime = runtime_script()
    assert "METRICS.mark" in runtime and "[data-brand-mark]" in runtime
    capture = (ROOT / "src" / "infragram" / "exports" / "browser.py").read_text(encoding="utf-8")
    assert "[data-brand-mark]" in capture, "the export crop must keep the mark's band"
