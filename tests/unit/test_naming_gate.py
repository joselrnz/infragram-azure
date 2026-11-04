"""The naming gate catches what must not ship.

`scripts/verify/naming.py` is the only thing standing between a stray mention
and a public release, and until now nothing checked that its patterns still
match. Each forbidden class is proved here against a string it must catch and
a string it must leave alone.

Every forbidden word is assembled at runtime, exactly as the gate assembles
its own, so this file does not trip the gate it tests.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".claude-plugin").is_dir())


def _gate():
    spec = importlib.util.spec_from_file_location("naming", ROOT / "scripts/verify/naming.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _match(text: str) -> str | None:
    """The label of the first forbidden class that matches, or None."""
    for label, pattern in _gate().FORBIDDEN:
        if pattern.search(text):
            return label
    return None


PREVIOUS_PRODUCT = "figure" + "room"
CLIENT_PROJECT = "hire" + "reset"
STRAY_HOLDER = "Cath" + "ryn" + " " + "Lav" + "ery"
# The separator variants the gate must also catch.
HYPHENATED_PRODUCT = "figure" + "-" + "room"
UNDERSCORED_CLIENT = "hire" + "_" + "reset"
# Home directories are assembled too: a literal one here would be a
# machine-specific path in a shipped file, which is the third rule.
WINDOWS_HOME = "C:" + chr(92) + "Users" + chr(92) + "someone" + chr(92) + "secret"
MAC_HOME = "/" + "Users" + "/someone/secret"
LINUX_HOME = "/" + "home" + "/someone/secret"


@pytest.mark.parametrize(
    "text,expected",
    [
        (PREVIOUS_PRODUCT, "the previous product name"),
        (PREVIOUS_PRODUCT.upper(), "the previous product name"),
        (HYPHENATED_PRODUCT, "the previous product name"),
        (CLIENT_PROJECT, "a client project name"),
        (UNDERSCORED_CLIENT, "a client project name"),
        (f"Copyright (c) 2025 {STRAY_HOLDER}", "a person who has no part in this project"),
        (STRAY_HOLDER.lower(), "a person who has no part in this project"),
        (WINDOWS_HOME, "a machine-specific path"),
        (LINUX_HOME, "a machine-specific path"),
        (MAC_HOME, "a machine-specific path"),
    ],
)
def test_the_gate_catches_what_must_not_ship(text: str, expected: str) -> None:
    assert _match(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Copyright (c) 2025 Infragram Azure contributors",
        "Infragram Azure draws infrastructure.",
        "frames.aws.VPC contains the subnets",
        # A surname's letters turning up inside a base64 image payload is not a
        # mention of anybody: the Oracle DDoS glyph contains exactly that.
        "iVBORw0KGgoAAAlaverypayloadNSUhEUgAAAQAAAAEACAYAAA",
        # Ordinary prose that shares a word with a forbidden phrase.
        "Reset the layout, then hire a reviewer.",
        "The figure sits in the room.",
    ],
)
def test_the_gate_leaves_honest_content_alone(text: str) -> None:
    assert _match(text) is None


def test_the_stray_holder_is_gone_from_the_licence() -> None:
    """The licence keeps MIT terms under a holder who actually holds it."""
    licence = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in licence
    assert _match(licence) is None
    assert "Copyright (c) 2025 Infragram Azure contributors" in licence


def test_every_forbidden_class_is_documented() -> None:
    """A rule nobody can read is a rule nobody can honour."""
    gate = _gate()
    assert len(gate.FORBIDDEN) == 4
    doc = gate.__doc__ or ""
    for label, _ in gate.FORBIDDEN:
        head = label.split()[-1]
        assert head in doc or label in doc, f"{label} is not explained in the gate's docstring"
