"""The ``infragram`` command line.

The user commands draw, export and check diagrams; they run in the current
directory, from a checkout or an installed copy. The maintainer commands run
scripts under scripts/ and need a checkout; infragram verify:quick is the
check after a change, and infragram verify:all runs CI's no-browser gates in
CI's order and stops at the first failure.
"""

from __future__ import annotations

import argparse
import difflib
import sys

from .commands import COMMANDS, FIXED_ARGS, project as user_commands
from .runner import run_script, verify_all, verify_quick
from .scripts import SCRIPTS
from .version import package_version

__all__ = ["build_parser", "main"]

_VERIFY_ALL_HELP = "run CI's no-browser gates in CI's order, stop on the first failure"
_VERIFY_QUICK_HELP = (
    "lint, the tree gates and the suite without its slow tests: the check to run after a change"
)


def _maintainer_commands() -> list[tuple[str, str]]:
    return sorted(
        [(name, entry[1]) for name, entry in COMMANDS.items() if name not in user_commands.COMMANDS]
        + [("verify:all", _VERIFY_ALL_HELP), ("verify:quick", _VERIFY_QUICK_HELP)]
    )


def _listing(entries: list[tuple[str, str]]) -> str:
    return "\n".join(f"  {name:<24} {help_text}" for name, help_text in entries)


def build_parser() -> argparse.ArgumentParser:
    # an installed copy has no scripts/ to run: it lists what it can run
    checkout = SCRIPTS is not None
    description = __doc__.split("\n\n")[1].replace("\n", " ")
    if not checkout:
        description = description.split(" The maintainer commands")[0]
    parser = argparse.ArgumentParser(
        prog="infragram",
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    user = [(name, entry[1]) for name, entry in user_commands.COMMANDS.items()]
    maintainer = _maintainer_commands()
    parser.epilog = (
        f"commands:\n{_listing(user)}\n\n"
        + (
            f"maintainer commands (need a checkout):\n{_listing(maintainer)}\n\n"
            if checkout
            else f"{len(maintainer)} maintainer commands run from a checkout of the repository.\n\n"
        )
        + "Arguments after the command go to it; `infragram <command> --help` shows its options."
    )
    parser.add_argument("--version", action="version", version=f"infragram {package_version()}")
    parser.add_argument("command", help="one of the commands listed below")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="passed to the command")
    return parser


def utf8_output() -> None:
    """Write UTF-8 to a pipe as well as to a console. A Windows pipe, which is
    how an agent reads the output, defaults to cp1252: it cannot encode a
    label in another script, and the command would stop at a traceback."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if reconfigure is not None and encoding != "utf8":
            reconfigure(encoding="utf-8", errors="backslashreplace")


def main(argv: list[str] | None = None) -> int:
    utf8_output()
    options = build_parser().parse_args(argv)
    every_gate = options.command in {"verify:all", "verify-all", "all"}
    quick = options.command == "verify:quick"
    entry = COMMANDS.get(options.command)
    if entry is None and not (every_gate or quick):
        offered = [
            *user_commands.COMMANDS,
            *([name for name, _ in _maintainer_commands()] if SCRIPTS is not None else []),
        ]
        close = difflib.get_close_matches(options.command, offered, n=1)
        print(
            f"ERROR: unknown command {options.command!r}; "
            + (f"did you mean {close[0]}? Run" if close else "run")
            + " infragram --help",
            file=sys.stderr,
        )
        return 2
    if options.command not in user_commands.COMMANDS and SCRIPTS is None:
        print(
            f"ERROR: {options.command} is a maintainer command, which runs from a checkout "
            f"of the repository; this copy runs {', '.join(user_commands.COMMANDS)}",
            file=sys.stderr,
        )
        return 2
    if every_gate:
        return verify_all()
    if quick:
        return verify_quick()
    fixed = FIXED_ARGS.get(options.command, ())
    repeated = [flag for flag in fixed if flag in options.args]
    if repeated:
        print(
            f"ERROR: {options.command} already passes {' '.join(repeated)}; drop it "
            f"(or run the script's own command to pass other flags)",
            file=sys.stderr,
        )
        return 2
    # Only the two gate runs have no entry, and both returned above.
    assert entry is not None
    return run_script(entry[0], (*fixed, *options.args))
