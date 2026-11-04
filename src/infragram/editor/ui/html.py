"""Markup helpers shared by every component."""

from __future__ import annotations


def attributes(attrs: str) -> str:
    return f" {attrs}" if attrs else ""


__all__ = ["attributes"]
