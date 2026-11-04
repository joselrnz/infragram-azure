"""``infragram find``: which class to import for a component, by the words an
architect uses ("s3", "aks", "load balancer", "vpc"), best match first.

The same search answers the MCP server's ``find_components``
(:mod:`infragram.catalog.find`). Without a query it lists: ``--library aws``
every class of that library by category, ``--libraries`` the libraries
themselves. The patterns (``MultiAZ``, ``Guardrails``, ``Blueprint``...) are
found by the same words and listed after the classes, apart, so a query
answers with the classes it always did.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...catalog.find import Found

__all__ = ["main"]

#: How many classes a query lists when --limit is not given.
DEFAULT_LIMIT = 20


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="infragram find",
        description="Find the node and frame classes a diagram file imports, by words in their "
        "name, service, icon or the names architects use for them; best match first. The "
        "patterns that match (infragram.patterns: MultiAZ, Guardrails, DirectConnectUplink, "
        "Blueprint...) follow the classes. With --library and no words, list that whole "
        "library; --libraries lists the libraries.",
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="words to match, all of them (e.g. s3, aks, load balancer, multi az)",
    )
    parser.add_argument(
        "--library",
        default=None,
        metavar="NAME",
        help="only this library: aws, azure, gcp, kubernetes, onprem, frames, patterns, ...; "
        "without a query, list every class in it",
    )
    parser.add_argument(
        "--libraries",
        action="store_true",
        help="list the libraries --library takes, with their names and how many classes each holds",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help=f"the most classes to list (default {DEFAULT_LIMIT} for a query, every one for a "
        "whole library)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the matches as JSON: module, class, title, library, import line",
    )
    return parser


def _row(hit: Found) -> dict[str, Any]:
    return {
        "import": hit.import_line,
        "module": hit.module,
        "class": hit.name,
        "title": hit.title,
        "library": hit.library,
        "frame": hit.frame,
        "aliases": list(hit.aliases),
    }


def _libraries(as_json: bool) -> int:
    from ...catalog.find import libraries

    listed = libraries()
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "id": library.id,
                        "name": library.name,
                        "nodes": library.nodes,
                        "frames": library.frames,
                        "patterns": library.patterns,
                    }
                    for library in listed
                ],
                indent=1,
            )
        )
        return 0
    width = max(len(library.id) for library in listed)
    name_width = max(len(library.name) for library in listed)
    for library in listed:
        held = [
            f"{count} {noun}{'' if count == 1 else 's'}"
            for count, noun in (
                (library.nodes, "node"),
                (library.frames, "frame"),
                (library.patterns, "pattern"),
            )
            if count
        ]
        print(f"{library.id:<{width}}  {library.name:<{name_width}}  {', '.join(held)}")
    return 0


def _whole_library(library: str, limit: int | None, as_json: bool) -> int:
    from ...catalog.find import libraries, library_classes

    classes = library_classes(library)
    if not classes:
        import difflib

        known = [entry.id for entry in libraries()]
        near = difflib.get_close_matches(library.casefold(), known, n=3)
        hint = f"; did you mean {', '.join(near)}?" if near else "; --libraries lists them"
        print(f"no library {library!r}{hint}", file=sys.stderr)
        return 1
    shown = classes if limit is None else classes[: max(1, limit)]
    if as_json:
        print(json.dumps([_row(hit) | {"category": hit.category} for hit in shown], indent=1))
        return 0
    print(f"# {library}: {len(classes)} classes")
    module = ""
    for hit in shown:
        if hit.module != module:
            module = hit.module
            print(f"\n## {hit.category} ({module})")
        print(f"{hit.import_line}  # {hit.title}")
    if len(classes) > len(shown):
        print(f"\n... {len(classes) - len(shown)} more; raise --limit or leave it out")
    return 0


def main(argv: list[str] | None = None) -> int:
    from ...catalog.find import find, find_patterns

    parser = _parser()
    options = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if options.libraries:
        return _libraries(options.json)
    if not options.query:
        if options.library:
            return _whole_library(options.library, options.limit, options.json)
        parser.error("the following arguments are required: query")
    query = " ".join(options.query)
    limit = max(1, DEFAULT_LIMIT if options.limit is None else options.limit)
    hits = find(query, options.library)
    patterns = find_patterns(query, options.library)
    shown = hits[:limit]
    shown_patterns = patterns[:limit]
    if options.json:
        print(json.dumps([_row(hit) for hit in (*shown, *shown_patterns)], indent=1))
        return 0 if hits or patterns else 1
    if not hits and not patterns:
        where = f" in {options.library}" if options.library else ""
        print(f"no node or frame class matches {query!r}{where}", file=sys.stderr)
        return 1
    for hit in shown:
        print(f"{hit.import_line}  # {hit.title}")
    if len(hits) > len(shown):
        print(f"... {len(hits) - len(shown)} more; narrow the query or name a --library")
    if shown_patterns:
        if shown:
            print()
        print("# patterns (infragram.patterns; patterns.md)")
        for hit in shown_patterns:
            print(f"{hit.import_line}  # {hit.title}")
    return 0
