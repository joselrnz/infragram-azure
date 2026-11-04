"""The shipped checker, loaded once, so the package and the skill judge an
export with the same code."""

from __future__ import annotations

import importlib.util
import sys
from functools import cache
from types import ModuleType

from ...paths import skill_scripts

__all__ = ["checker"]

_MODULE = "infragram_project_check"


@cache
def checker() -> ModuleType:
    """``project_check.py`` from the skill: the checkout's copy, or the one an
    installed wheel carries beside the package."""
    path = skill_scripts() / "project_check.py"
    spec = importlib.util.spec_from_file_location(_MODULE, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the checker at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE] = module
    spec.loader.exec_module(module)
    return module
