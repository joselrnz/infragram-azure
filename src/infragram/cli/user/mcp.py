"""``infragram mcp``: Infragram's commands served to an MCP client over stdio.

The client starts it (the plugin's ``.mcp.json`` does, through ``uvx``); it
answers on stdout until the client closes stdin (:mod:`infragram.mcp`).
"""

from __future__ import annotations

import argparse

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        prog="infragram mcp",
        description="Serve Infragram's commands to an MCP client over stdio (JSON-RPC, one "
        "message a line). The client starts it; run from a terminal it waits for input.",
    ).parse_args(argv)
    from ...mcp import serve

    return serve()
