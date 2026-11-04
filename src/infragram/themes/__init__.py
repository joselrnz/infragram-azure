"""Theme models: canvas palettes, heading treatment, and the theme files."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..paths import skill_assets

#: Canvas color roles every provider theme must define, in cascade order
#: from background to foreground accent.
THEME_ROLES = ("paper", "paper_2", "ink", "muted", "soft", "accent", "link")


@dataclass(frozen=True)
class TypeStyle:
    """A skin's heading treatment.

    Typography is mostly house style and lives on ``Style``, but the heading
    is where a skin gets to sound like its vendor: the Microsoft drawings
    set titles in a semibold UI face, not the editorial serif the shipped
    look uses. Empty ``font`` means "keep the Style's serif".
    """

    font: str = ""
    weight: int = 400


class StepMark(BaseModel):
    """How a flow's numbered steps are marked: a filled ``circle`` or
    ``square`` in ``color`` carrying its number, or its letter (1 is A), in
    white. The clouds' own drawings mark a second flow apart: Azure's
    outbound flow in blue squares, Google's second flow in green letters."""

    color: str
    shape: Literal["circle", "square"] = "circle"
    marks: Literal["numbers", "letters"] = "numbers"

    model_config = {"extra": "forbid", "frozen": True}

    def mark(self, number: int) -> str:
        """What the badge says for step ``number``."""
        return chr(64 + number) if self.marks == "letters" and number <= 26 else str(number)


@dataclass(frozen=True)
class Theme(Mapping):
    """A provider's canvas palette plus its heading treatment.

    Implements the read-only Mapping protocol over its color roles, so
    ``theme["accent"]``, iteration, ``len``, and ``.values()`` behave exactly
    like the plain dict this replaced. Only the color roles participate in
    the mapping; the heading treatment is reached via ``theme.type``.
    """

    paper: str
    paper_2: str
    ink: str
    muted: str
    soft: str
    accent: str
    link: str
    type: TypeStyle = field(default_factory=TypeStyle)
    #: The faint dot field behind a diagram. Vendor drawings are usually
    #: laid on plain paper, so a skin can switch it off.
    dots: bool = True
    #: This palette paints a dark ground, so artwork drawn in a dark ink is
    #: drawn light over it (builders/render.py, exports/palette.py). Set by
    #: the dark palettes, never by a library's own theme.
    dark: bool = False
    #: Absolute path to the skin's brand lockup, drawn bottom-left. Empty
    #: means no mark.
    mark: str = ""
    #: The colour a numbered step's circle is filled with (``step_color`` in
    #: the theme file); empty takes the link colour, dark enough on any paper.
    step: str = ""
    #: How a second flow's steps are marked (``step_second`` in the theme
    #: file); None marks them with squares in the step colour.
    step_second: StepMark | None = None

    @property
    def step_color(self) -> str:
        return self.step or self.link

    def step_mark(self, second: bool = False) -> StepMark:
        """The main flow's mark (a circle, numbered), or the second flow's."""
        if not second:
            return StepMark(color=self.step_color)
        return self.step_second or StepMark(color=self.step_color, shape="square")

    @classmethod
    def from_colors(
        cls,
        colors: Mapping[str, str],
        type: TypeStyle | None = None,
        dots: bool = True,
        mark: str = "",
        step: str = "",
        step_second: StepMark | None = None,
    ) -> Theme:
        """Build a Theme from a role->color mapping, requiring every role."""
        missing = [role for role in THEME_ROLES if role not in colors]
        if missing:
            raise ValueError(f"theme is missing color roles: {', '.join(missing)}")
        # The roles are spelled out rather than splatted from THEME_ROLES so
        # the checker sees each one land on its own str field.
        return cls(
            paper=colors["paper"],
            paper_2=colors["paper_2"],
            ink=colors["ink"],
            muted=colors["muted"],
            soft=colors["soft"],
            accent=colors["accent"],
            link=colors["link"],
            type=type or TypeStyle(),
            dots=dots,
            mark=mark,
            step=step,
            step_second=step_second,
        )

    def __getitem__(self, role: str) -> str:
        if role not in THEME_ROLES:
            raise KeyError(role)
        return getattr(self, role)

    def __iter__(self) -> Iterator[str]:
        return iter(THEME_ROLES)

    def __len__(self) -> int:
        return len(THEME_ROLES)


def theme_manifest(name: str, assets: Path | None = None) -> dict:
    """One library's theme file, ``themes/<name>.json``, as written: from
    ``assets`` when given, else the skill assets this process resolves now.

    The palette, the boundary style and the sidebar's mark all start here;
    three readers of the same file used to keep a copy each of these lines.
    """
    root = assets or skill_assets()
    return json.loads((root / "themes" / f"{name}.json").read_text(encoding="utf-8"))
