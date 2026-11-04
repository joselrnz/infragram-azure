"""Shared test configuration.

Every suite here runs standalone (``python tests/unit/test_x.py``) because
that is how CI invokes them; this file only makes the same imports work when
the suites are collected by pytest from the repository root.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

for candidate in (ROOT / "src", ROOT / "scripts"):
    entry = str(candidate)
    if entry not in sys.path:
        sys.path.insert(0, entry)


# Every page a browser suite opens gets the render budget. CI runs on a small
# self-hosted runner where a single-file editor page loads slowly; Playwright's
# own default is 30 s and, on the release CI pins, navigation waits (goto, load
# states) do not inherit a default timeout. INFRAGRAM_RENDER_TIMEOUT_MS and
# INFRAGRAM_RENDER_OFFLINE are the knobs, the same ones the exporter reads.
@pytest.fixture(autouse=True, scope="session")
def _browser_pages_get_the_render_budget():
    try:
        from playwright.sync_api import Browser, BrowserContext
    except ImportError:
        yield
        return
    from infragram.exports import prepare_page

    def with_budget(original):
        def new_page(self, *args, **kwargs):
            page = original(self, *args, **kwargs)
            prepare_page(page)
            return page

        return new_page

    originals = (Browser.new_page, BrowserContext.new_page)
    Browser.new_page = with_budget(originals[0])
    BrowserContext.new_page = with_budget(originals[1])
    try:
        yield
    finally:
        Browser.new_page, BrowserContext.new_page = originals
