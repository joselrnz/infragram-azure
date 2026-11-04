"""Corrections to an import, kept apart from what the import writes.

An imported diagram file is the import's; editing it by hand means the next
import either refuses (the file was edited) or, with ``--force``, loses the
edit. Terravision answers this with an annotations file; this is the same
idea: ``<diagram>.overrides.toml`` beside the diagram file, applied to the
drawing every time it is imported, so the estate can be read again and the
corrections stay.

    [[remove]]                      # leave out what the picture does not need
    address = "aws_cloudwatch_log_group.*"

    [[relabel]]                     # say it the way the team says it
    address = "aws_instance.web[0]"
    caption = "Web tier"
    detail = "3 x m6i.large"

    [[connect]]                     # what the configuration does not show
    from = "aws_instance.web[0]"
    to = "aws_db_instance.main"
    label = "SQL"
    dashed = false

    [[disconnect]]                  # a wire read from a reference, not a flow
    from = "aws_lambda_function.*"
    to = "aws_iam_role.*"

``address``, ``from`` and ``to`` are what the import keys a card or frame by
-- the Terraform address for a resource -- with shell wildcards (``*``,
``?``, ``[...]``). A rule that matches nothing is reported, never silently
dropped: the estate changed under it. Standard library only (``tomllib``).
"""

from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path
from typing import Any

from .draw import Box, Card, Drawing, Wire

__all__ = ["apply_overrides", "overrides_path"]


def overrides_path(spec: Path) -> Path:
    """``shop.py`` -> ``shop.overrides.toml``."""
    return spec.with_name(f"{spec.stem}.overrides.toml")


def _matches(key: str, pattern: str) -> bool:
    # the brackets of a count index are literal in an address, a class in a pattern
    return key == pattern or fnmatch.fnmatchcase(key, pattern)


def _held(item: Box | Card) -> list[str]:
    """The key of *item* and of everything inside it."""
    out = [item.key]
    if isinstance(item, Box):
        for child in item.children:
            out += _held(child)
    return out


def apply_overrides(drawing: Drawing, path: Path) -> tuple[int, list[str]]:
    """Apply the file's rules to *drawing*; return how many applied and notes
    on the rules that matched nothing or could not be read."""
    try:
        rules = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        return 0, [f"{path.name}: not read ({error}); nothing overridden"]
    notes: list[str] = []
    applied = 0
    items = {item.key: item for item in drawing.walk()}

    def find(pattern: str) -> list[str]:
        return [key for key in items if _matches(key, pattern)]

    def rule_list(name: str) -> list[dict[str, Any]]:
        value = rules.get(name, [])
        return [rule for rule in value if isinstance(rule, dict)] if isinstance(value, list) else []

    for rule in rule_list("remove"):
        keys = find(str(rule.get("address", "")))
        if not keys:
            notes.append(f"{path.name}: remove {rule.get('address')!r} matches nothing drawn")
            continue
        # a frame goes with everything inside it, and so do the wires to them
        gone = {inner for key in keys for inner in _held(items[key])}
        drawing.roots = [root for root in drawing.roots if root.key not in gone]
        for item in drawing.walk():
            if isinstance(item, Box):
                item.children = [child for child in item.children if child.key not in gone]
        drawing.wires = [
            wire for wire in drawing.wires if wire.source not in gone and wire.target not in gone
        ]
        for key in [*keys, *sorted(gone - set(keys))]:
            drawing.left_out[key] = f"removed by {path.name}"
            items.pop(key, None)
        applied += 1

    for rule in rule_list("relabel"):
        keys = find(str(rule.get("address", "")))
        if not keys:
            notes.append(f"{path.name}: relabel {rule.get('address')!r} matches nothing drawn")
            continue
        for key in keys:
            item = items[key]
            if "caption" in rule:
                item.caption = str(rule["caption"])
            if "detail" in rule and isinstance(item, Card):
                item.detail = str(rule["detail"])
        applied += 1

    for rule in rule_list("disconnect"):
        before = len(drawing.wires)
        source, target = str(rule.get("from", "")), str(rule.get("to", ""))
        drawing.wires = [
            wire
            for wire in drawing.wires
            if not (_matches(wire.source, source) and _matches(wire.target, target))
        ]
        if len(drawing.wires) == before:
            notes.append(f"{path.name}: disconnect {source!r} -> {target!r} matches no wire")
            continue
        applied += 1

    for rule in rule_list("connect"):
        sources, targets = find(str(rule.get("from", ""))), find(str(rule.get("to", "")))
        if not sources or not targets:
            notes.append(
                f"{path.name}: connect {rule.get('from')!r} -> {rule.get('to')!r}: "
                f"{'from' if not sources else 'to'} matches nothing drawn"
            )
            continue
        for source in sources:
            for target in targets:
                if source != target:
                    drawing.wires.append(
                        Wire(
                            source=source,
                            target=target,
                            label=str(rule.get("label", "")),
                            dashed=bool(rule.get("dashed", False)),
                        )
                    )
        applied += 1
    return applied, notes
