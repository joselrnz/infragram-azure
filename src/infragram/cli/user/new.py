"""``infragram new``: start a diagram file from one of the shipped examples.

A blank file means knowing the class names, the frame nesting and the
``with Diagram(...)`` form before drawing anything; the examples already show
all three for a three-tier web app, a hub-and-spoke landing zone, a
Kubernetes platform, a campus LAN and more. ``new`` copies one to a file of
the user's own with its own title and slug -- so its exported page keeps its
own saved state, apart from the example's -- and says how to draw it.

``new --template NAME`` does the same from a shipped reference diagram, a
``.infragram.json`` document (``infragram templates`` lists them): for the
reader who edits in the exported editor, or keeps the document rather than
code.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import re
import sys
from pathlib import Path

from ...utils.text import slugify

__all__ = ["examples", "main"]


def examples() -> dict[str, tuple[Path, str]]:
    """name -> (file, the first line of its docstring)."""
    from ...paths import plugin_root

    out: dict[str, tuple[Path, str]] = {}
    for path in sorted((plugin_root() / "examples").glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        except SyntaxError:
            continue
        out[path.stem] = (path, doc.strip().splitlines()[0].rstrip(".") if doc.strip() else "")
    return out


def _listing(shipped: dict[str, tuple[Path, str]]) -> None:
    """The examples as they always were, then the templates in a section of
    their own: one place names everything ``new`` starts from."""
    from .templates import summary, templates

    width = max(map(len, shipped), default=0)
    for name, (_, text) in shipped.items():
        print(f"{name:<{width}}  {text}")
    documents = templates()
    if documents:
        print()
        print("templates (new --template NAME [DEST] writes an .infragram.json document):")
        width = max(map(len, documents))
        for name, template in documents.items():
            print(f"{name:<{width}}  {summary(template)}")


def _document(path: Path) -> Path:
    """*path* as a document's file name: ``.infragram.json`` added when missing
    (``shop``, ``shop.json`` and ``shop.infragram`` all become ``shop.infragram.json``)."""
    from .templates import SUFFIX

    if path.name.endswith(SUFFIX):
        return path
    return path.with_name(path.name.removesuffix(".json").removesuffix(".infragram") + SUFFIX)


def _from_template(options: argparse.Namespace) -> int:
    """``new --template NAME [DEST]``: a copy of a template document with its
    own title and slug."""
    from .templates import SUFFIX, lookup, templates

    if options.path is not None:
        print(
            "ERROR: new --template NAME takes one destination "
            f"({options.example} or {options.path}, not both)",
            file=sys.stderr,
        )
        return 2
    template = lookup(options.template)
    if template is None:
        near = difflib.get_close_matches(options.template, list(templates()), n=3)
        if options.template.removesuffix(".py") in examples():
            hint = f"; {options.template} is an example: infragram new {options.template}"
        elif near:
            hint = f"; did you mean {', '.join(near)}?"
        else:
            hint = "; infragram templates names them"
        print(f"ERROR: no template {options.template!r}{hint}", file=sys.stderr)
        return 2
    target = _document(Path(options.example) if options.example else Path(template.name + SUFFIX))
    if target.exists() and not options.force:
        print(f"ERROR: {target} exists (pass --force to replace it)", file=sys.stderr)
        return 2

    data = json.loads(template.path.read_text(encoding="utf-8"))
    title = options.title or str(data.get("title") or template.title)
    slug = slugify(options.title or target.name.removesuffix(SUFFIX), fallback="diagram")
    root = data.get("topology")
    # the root group carries the title too; a renamed copy renames it with the document
    if isinstance(root, dict) and root.get("name") == data.get("title"):
        root["name"] = title
    data["title"] = title
    data["slug"] = slug
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"NEW      {target} (from template {template.name}, slug {slug})")
    print(f"         infragram export:project {target.as_posix()}   draws it to HTML, SVG and PNG")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="infragram new",
        description="Start a diagram file from a shipped example: a copy with its own title and "
        "slug, ready to edit and compose. With --template, start an .infragram.json document "
        "from a shipped template the same way.",
    )
    parser.add_argument(
        "example",
        nargs="?",
        help="the example to start from (--list names them); with --template, the document "
        "to write",
    )
    parser.add_argument(
        "path", nargs="?", type=Path, help="the file to write (default: <example>.py here)"
    )
    parser.add_argument(
        "--title", default=None, help="the diagram's title (default: the example's)"
    )
    parser.add_argument(
        "--template",
        default=None,
        metavar="NAME",
        help="start from this shipped template instead (infragram templates names them): "
        "writes an .infragram.json document (default: <template>.infragram.json here)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list the examples and what each draws, then the templates",
    )
    parser.add_argument("--force", action="store_true", help="replace the file if it exists")
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)

    shipped = examples()
    if options.list or not (options.example or options.template):
        _listing(shipped)
        return 0 if options.list else 2
    if options.template:
        return _from_template(options)
    found = shipped.get(options.example) or shipped.get(options.example.removesuffix(".py"))
    if found is None:
        from .templates import lookup

        near = difflib.get_close_matches(options.example, list(shipped), n=3)
        if lookup(options.example) is not None:
            hint = f"; {options.example} is a template: infragram new --template {options.example}"
        else:
            hint = f"; did you mean {', '.join(near)}?" if near else "; --list names them"
        print(f"ERROR: no example {options.example!r}{hint}", file=sys.stderr)
        return 2
    source, _ = found
    target = options.path or Path(f"{source.stem}.py")
    if target.suffix != ".py":
        target = target.with_suffix(".py")
    if target.exists() and not options.force:
        print(f"ERROR: {target} exists (pass --force to replace it)", file=sys.stderr)
        return 2

    text = source.read_text(encoding="utf-8")
    title = options.title
    if title:
        # the Diagram's first argument is its title
        text = re.sub(
            r'(with Diagram\(\s*)("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')',
            lambda m: m.group(1) + repr(title),
            text,
            count=1,
        )
    slug = slugify(title or target.stem, fallback="diagram")
    if re.search(r"\bslug\s*=\s*['\"]", text):
        text = re.sub(
            r"(\bslug\s*=\s*)(['\"])[^'\"]*\2", lambda m: f'{m.group(1)}"{slug}"', text, count=1
        )
    # the example's docstring says how to draw it from the plugin folder; the
    # copy says how to draw the copy, with the command the user has
    text = text.replace("Through the skill's launcher, from the plugin folder::", "Draw it with::")
    text = text.replace("python skills/infragram-azure/scripts/infragram.py", "infragram")
    text = text.replace(f"examples/{source.name}", target.name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8", newline="\n")
    print(f"NEW      {target} (from {source.stem}, slug {slug})")
    print(
        f"         infragram compose {target.as_posix()} --watch   draws it and redraws on every save"
    )
    return 0
