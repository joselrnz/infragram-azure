"""Outlined text field with its label, for text, number, colour and select inputs. Styles: field.css."""

from __future__ import annotations

from html import escape


def field(label: str, control: str, *, prefix: bool = False) -> str:
    """An outlined M3 text field with its label; ``control`` is the input or select."""
    kind = " md-field--prefix" if prefix else ""
    return f'<label class="md-field{kind}">{escape(label)}{control}</label>'


def text_input(attrs: str) -> str:
    return f'<input class="md-field__input" {attrs}>'


def select(attrs: str, options: str) -> str:
    return f'<select class="md-field__input" {attrs}>{options}</select>'


def color_input(attrs: str) -> str:
    """A colour input that reads out its hex value beside a round swatch."""
    return (
        f'<span class="md-color-field"><input class="md-field__input" type="color" {attrs}>'
        '<output class="md-color-field__value" aria-hidden="true"></output></span>'
    )


__all__ = ["color_input", "field", "select", "text_input"]
