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
        self.calls.append(("route", pattern))


def test_every_prepared_page_gets_both_budgets_and_refuses_other_machines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INFRAGRAM_RENDER_TIMEOUT_MS", "240000")
    for offline in (None, "1"):
        if offline is None:
            monkeypatch.delenv("INFRAGRAM_RENDER_OFFLINE", raising=False)
        else:
            monkeypatch.setenv("INFRAGRAM_RENDER_OFFLINE", offline)
        page = _Page()
        exports.prepare_page(page)
        assert page.calls[:2] == [("timeout", 240_000), ("navigation", 240_000)]
        assert page.calls[2] == ("route", exports.remote_url)
    # a shared document's <image href> must not reach its server
    for url in (
        "https://fonts.googleapis.com/css2?family=Geist",
        "https://attacker.example/pixel.png",
        "http://169.254.169.254/latest/meta-data/",
        "//attacker.example/x",
        "wss://attacker.example/socket",
    ):
        assert exports.remote_url(url), url
    # the page itself, what it carries, and the 3D page served on this machine
    for url in (
        "file:///tmp/page.html",
        "data:image/png;base64,AAAA",
        "blob:null/1234",
        "about:blank",
        "http://127.0.0.1:51234/render.html",
        "http://localhost:8000/x",
    ):
        assert not exports.remote_url(url), url
    assert exports.FONT_HOSTS.match("https://fonts.gstatic.com/s/geist/v1/x.woff2")
