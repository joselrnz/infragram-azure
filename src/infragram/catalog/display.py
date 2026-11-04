"""Which components draw bare by default, answered from one rules file.

A component is drawn one of two ways: a **card** (a titled box with the
glyph in a lane beside the text) or an **icon** (the bare glyph with its
caption beneath, the way the vendor decks place it). The project picks a
look and a node may override it, but between the two sits a default that
follows the artwork: a NAT gateway is a line glyph the deck places bare, a
service is a coloured tile that reads well in a card.

That default lives in ``assets/catalog/display-defaults.json`` and nowhere
else. The editor state, the exports, the static fallback and the sidebar
all call :func:`default_display`, so a component looks the same however it
reaches the canvas.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..paths import skill_assets

Display = Literal["card", "icon"]
DISPLAYS = ("card", "icon")
MATCH_KEYS = frozenset(
    {
        "tier",
        "category",
        "ids",
        "prefixes",
        "not_prefixes",
        "not_ids",
        "not_categories",
    }
)


def display_defaults_path() -> Path:
    return skill_assets() / "catalog" / "display-defaults.json"


class DisplayRule(BaseModel):
    """One rule: a provider (or ``*``), what to match, and how to draw it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(min_length=1)
    match: dict[str, Any] = Field(min_length=1)
    display: Display
    why: str = ""

    @field_validator("match")
    @classmethod
    def _known_keys(cls, match: dict[str, Any]) -> dict[str, Any]:
        unknown = set(match) - MATCH_KEYS
        if unknown:
            raise ValueError(f"unknown match keys {sorted(unknown)}")
        return match


class DisplayDefaults(BaseModel):
    """The rules document: the default look and the first-match-wins rules."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1]
    about: str = ""
    default: Display
    rules: tuple[DisplayRule, ...] = ()


@lru_cache(maxsize=4)
def load_display_defaults(path: Path | None = None) -> DisplayDefaults:
    """The rules document, validated once: schema, displays, match keys."""
    path = path or display_defaults_path()
    return DisplayDefaults.model_validate_json(path.read_text(encoding="utf-8"))


def _matches(match: dict, component_id: str, tier: str | None, category: str | None) -> bool:
    if "tier" in match and tier != match["tier"]:
        return False
    if "category" in match and category != match["category"]:
        return False
    if "ids" in match and component_id not in match["ids"]:
        return False
    if "prefixes" in match and not component_id.startswith(tuple(match["prefixes"])):
        return False
    if "not_prefixes" in match and component_id.startswith(tuple(match["not_prefixes"])):
        return False
    if "not_ids" in match and component_id in match["not_ids"]:
        return False
    return not ("not_categories" in match and category in match["not_categories"])


def default_display(
    provider: str | None,
    component_id: str | None,
    *,
    tier: str | None = None,
    category: str | None = None,
) -> str:
    """How a component draws unless a node says otherwise: ``card`` or ``icon``.

    ``provider`` and ``component_id`` name the component (``aws``,
    ``vpc-nat-gateway``); ``tier`` and ``category`` are the icon's own, as
    the vendor deck files it. The first matching rule wins; a component no
    rule matches draws as the document's default. An element with neither an
    id nor artwork -- nothing to match on -- draws as the default.
    """
    data = load_display_defaults()
    if not component_id and tier is None and category is None:
        return data.default
    # An element that carries artwork but no library component yet -- a
    # compose node before to_project() qualifies it -- still has the icon's
    # tier and category to match on; id-based matches simply fail.
    component_id = component_id or ""
    for rule in data.rules:
        if rule.provider not in ("*", provider):
            continue
        if _matches(rule.match, component_id, tier, category):
            return rule.display
    return data.default
