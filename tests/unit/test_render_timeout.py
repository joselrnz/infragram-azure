"""Render waits are sized for a slow machine and overridable."""

from __future__ import annotations

import pytest

from infragram import exports


def test_the_default_render_timeout_is_generous(monkeypatch: pytest.MonkeyPatch) -> None:
    # CI sets the variable for its slow runner; the default is what an unset environment gives.
    monkeypatch.delenv("INFRAGRAM_RENDER_TIMEOUT_MS", raising=False)
    assert exports.render_timeout_ms() == 120_000
    assert exports.EDITOR_READY_TIMEOUT_MS >= 10_000


def test_the_render_timeout_reads_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFRAGRAM_RENDER_TIMEOUT_MS", "240000")
    assert exports.render_timeout_ms() == 240_000
    monkeypatch.setenv("INFRAGRAM_RENDER_TIMEOUT_MS", "not a number")
    assert exports.render_timeout_ms() == 120_000
    monkeypatch.setenv("INFRAGRAM_RENDER_TIMEOUT_MS", "5")
    assert exports.render_timeout_ms() == 1_000, "never below a second"


def test_offline_rendering_is_off_unless_the_environment_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INFRAGRAM_RENDER_OFFLINE", raising=False)
    assert exports.render_offline() is False
    monkeypatch.setenv("INFRAGRAM_RENDER_OFFLINE", "1")
    assert exports.render_offline() is True
    monkeypatch.setenv("INFRAGRAM_RENDER_OFFLINE", "yes")
    assert exports.render_offline() is False, "only the literal 1"


class _Page:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def set_default_timeout(self, value: float) -> None:
        self.calls.append(("timeout", value))

    def set_default_navigation_timeout(self, value: float) -> None:
        self.calls.append(("navigation", value))

    def route(self, pattern, handler) -> None:
        self.calls.append(("route", pattern.pattern))


def test_a_prepared_page_gets_both_budgets_and_the_font_hosts_blocked_only_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFRAGRAM_RENDER_TIMEOUT_MS", "240000")
    monkeypatch.delenv("INFRAGRAM_RENDER_OFFLINE", raising=False)
    page = _Page()
    exports.prepare_page(page)
    assert page.calls == [("timeout", 240_000), ("navigation", 240_000)]
    monkeypatch.setenv("INFRAGRAM_RENDER_OFFLINE", "1")
    page = _Page()
    exports.prepare_page(page)
    assert page.calls[:2] == [("timeout", 240_000), ("navigation", 240_000)]
    assert page.calls[2][0] == "route"
    assert exports.FONT_HOSTS.match("https://fonts.googleapis.com/css2?family=Geist")
    assert exports.FONT_HOSTS.match("https://fonts.gstatic.com/s/geist/v1/x.woff2")
    assert not exports.FONT_HOSTS.match("file:///tmp/page.html")
