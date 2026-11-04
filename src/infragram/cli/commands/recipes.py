"""The 3D recipe bench: adding one, and trying one."""

from __future__ import annotations

__all__ = ["COMMANDS"]

#: command -> (script path relative to scripts/, help text)
COMMANDS: dict[str, tuple[str, str]] = {
    "recipe:add": (
        "tools/recipe-add.py",
        "add a tried 3D recipe to scene.js and the table, then install, nodes, inventory, ink and the gates",
    ),
    "recipe:try": (
        "tools/recipe-try.py",
        "render a candidate 3D recipe, measure it and check where links would seat; the picture and report land in --out",
    ),
}
