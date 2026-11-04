"""Reading a Python diagram file without running it, and saying why one
that ran failed.

A diagram file imports ``infragram`` and, at its top level, opens
``with Diagram(...)`` or assigns ``PROJECT``. :func:`static_findings` reads
one -- syntax, a name used and never defined, a node class the module it
names does not hold -- and never runs it, which is what lets the check hook
and ``infragram check`` look at a file nobody has approved running.
:func:`explain_failure` is for ``compose``, which does run it: the error the
file raised, from the file's own lines, with the nearest real name.
"""

from __future__ import annotations

import ast
import builtins
import difflib
import importlib
import re
import traceback
from pathlib import Path

__all__ = ["explain_failure", "is_diagram", "static_findings"]

_NODES = "infragram.nodes"


def is_diagram(tree: ast.Module) -> bool:
    """Whether a module is a diagram file: it imports infragram, and its top
    level opens ``with Diagram(...)`` or assigns ``PROJECT``."""
    imports = any(
        isinstance(node, ast.Import)
        and any(alias.name.split(".")[0] == "infragram" for alias in node.names)
        or isinstance(node, ast.ImportFrom)
        and (node.module or "").split(".")[0] == "infragram"
        for node in tree.body
    )
    if not imports:
        return False
    for node in tree.body:
        if isinstance(node, ast.With) and any(
            isinstance(item.context_expr, ast.Call)
            and (
                getattr(item.context_expr.func, "id", None) == "Diagram"
                or getattr(item.context_expr.func, "attr", None) == "Diagram"
            )
            for item in node.items
        ):
            return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "PROJECT" for target in targets):
                return True
    return False


def _bound(tree: ast.Module) -> tuple[set[str], bool]:
    """Every name the module binds anywhere, and whether it star-imports."""
    names: set[str] = set()
    star = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "*":
                    star = True
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            names.update(node.names)
        elif isinstance(node, ast.MatchAs) and node.name:
            names.add(node.name)
    return names, star


def _ours(name: str) -> bool:
    """The infragram package itself: a module merely named ``infragram_x`` is
    the user's, and reading a diagram file never runs the user's code."""
    return name == "infragram" or name.startswith("infragram.")


def _module(name: str):
    if not _ours(name):
        return None
    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001 - a module that does not import is named, not a crash
        return None


def _elsewhere(library: str, name: str) -> list[str]:
    """Where in a node library a class called *name* lives."""
    import pkgutil

    package = _module(library)
    found = []
    for info in pkgutil.iter_modules(getattr(package, "__path__", []) or [], prefix=f"{library}."):
        module = _module(info.name)
        if module is not None and isinstance(getattr(module, name, None), type):
            found.append(f"{info.name}.{name}")
    return found


def _submodules(package_name: str) -> list[str]:
    """The modules in a package, imported or not (``dir`` sees only the first)."""
    import pkgutil

    package = _module(package_name)
    return [info.name for info in pkgutil.iter_modules(getattr(package, "__path__", []) or [])]


def _missing(module_name: str, attribute: str) -> str | None:
    """Why *attribute* is not in *module_name*, with where it is, or None when it is."""
    module = _module(module_name)
    if module is None:
        return f"{module_name} is not a module infragram has"
    if hasattr(module, attribute):
        return None
    names = {n for n in dir(module) if not n.startswith("_")} | set(_submodules(module_name))
    close = difflib.get_close_matches(attribute, sorted(names), n=3)
    library = ".".join(module_name.split(".")[:3]) if module_name.startswith(f"{_NODES}.") else ""
    where = _elsewhere(library, attribute) if library and library != module_name else []
    hint = (
        f"; it is {' or '.join(where)}"
        if where
        else f"; did you mean {', '.join(close)}"
        if close
        else ""
    )
    return f"{module_name} has no {attribute}{hint}"


def static_findings(path: Path, text: str) -> list[str] | None:
    """What reading a diagram file finds, or None when it is no diagram file."""
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as error:
        # a file that does not parse is a diagram file when it says so
        if re.search(r"^\s*(?:from|import)\s+infragram\b", text, re.MULTILINE):
            return [f"line {error.lineno}: {error.msg}"]
        return None
    if not is_diagram(tree):
        return None
    findings: list[str] = []
    modules: dict[str, str] = {}  # a name bound to an infragram module -> the module
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _ours(alias.name):
                    if alias.asname:
                        modules[alias.asname] = alias.name
                    elif _module(alias.name) is None:
                        findings.append(
                            f"line {node.lineno}: {alias.name} is not a module infragram has"
                        )
        elif isinstance(node, ast.ImportFrom) and _ours(node.module or "") and not node.level:
            for alias in node.names:
                if alias.name == "*":
                    continue
                submodule = f"{node.module}.{alias.name}"
                if _module(submodule) is not None and submodule.startswith(_NODES):
                    modules[alias.asname or alias.name] = submodule
                    continue
                reason = _missing(node.module or "", alias.name)
                if reason:
                    findings.append(f"line {node.lineno}: {reason}")
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in modules
            and isinstance(node.ctx, ast.Load)
        ):
            reason = _missing(modules[node.value.id], node.attr)
            if reason:
                findings.append(f"line {node.lineno}: {node.value.id}.{node.attr}: {reason}")
    bound, star = _bound(tree)
    if not star:
        known = bound | set(dir(builtins)) | {"__file__", "__name__", "__doc__"}
        undefined: dict[str, int] = {}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Load)
                and node.id not in known
            ):
                undefined.setdefault(node.id, node.lineno)
        for name, line in sorted(undefined.items(), key=lambda item: item[1]):
            close = difflib.get_close_matches(name, sorted(bound), n=1)
            findings.append(
                f"line {line}: {name} is used and never defined"
                + (f"; did you mean {close[0]}" if close else "")
            )
    return list(dict.fromkeys(findings))


def _hint(error: BaseException) -> str | None:
    """Where the name a diagram file asked for is, or the nearest one there is."""
    if (
        isinstance(error, ModuleNotFoundError)
        and error.name
        and error.name.startswith("infragram.")
    ):
        parent, _, leaf = error.name.rpartition(".")
        while parent and _module(parent) is None:
            parent, _, leaf = parent.rpartition(".")
        close = difflib.get_close_matches(leaf, _submodules(parent), n=3)
        return f"{parent} has no module {leaf}" + (
            f"; did you mean {' or '.join(f'{parent}.{name}' for name in close)}" if close else ""
        )
    if isinstance(error, ImportError):
        match = re.search(r"cannot import name '(\w+)' from '(infragram[\w.]*)'", str(error))
        return _missing(match.group(2), match.group(1)) if match else None
    if isinstance(error, AttributeError):
        owner = getattr(error, "obj", None)
        name = getattr(owner, "__name__", "")
        if isinstance(name, str) and name.startswith(f"{_NODES}.") and error.name:
            return _missing(name, error.name)
    return None


def explain_failure(error: BaseException, path: Path) -> str:
    """What a diagram file raised, told from its own lines: the line that
    failed, the error, and the nearest real name -- not the traceback through
    the runner, which is none of the reader's business."""
    line = text = None
    for frame in traceback.extract_tb(error.__traceback__):
        if Path(frame.filename).resolve() == path.resolve():
            line, text = frame.lineno, frame.line
    if line is None and isinstance(error, SyntaxError) and error.lineno:
        line, text = error.lineno, error.text
    message = str(error)
    if isinstance(error, ImportError):
        # the path of the package it looked in says nothing the name does not
        message = re.sub(r" \([^()]*\)$", "", message)
    told = f"{type(error).__name__}: {message}"
    if line is not None:
        told = f"{path.name}, line {line}: {(text or '').strip()}\n  {told}"
    hint = _hint(error)
    return told + (f"\n  {hint}" if hint and hint not in message else "")
