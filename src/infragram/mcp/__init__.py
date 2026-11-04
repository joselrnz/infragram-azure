"""Infragram as an MCP server: ``infragram mcp``.

A Model Context Protocol server over stdio (newline-delimited JSON-RPC 2.0),
written on the standard library so it needs nothing the package does not.
Its tools are the user commands -- compose, export, check, render
verification, the Terraform check, diff, import and discovery -- each run as
``python -m infragram <command>`` in the folder the client started the server
in, so a path means what it means to the user. A tool answers with what the
command printed, and with the same as data (``structuredContent``: the files
written with their sizes, each check's verdict, notes and errors); asked for a
preview, it attaches the PNG it wrote. It fails when the command did. The
read-only tools answer in-process: the shipped templates and examples, and
the node classes a diagram file imports, by name.

The references, the templates, the examples and the document's JSON Schema are
resources, and a few prompts start the usual jobs.

stdout carries the protocol and nothing else; anything else goes to stderr.

The package follows the server's seams: :mod:`.tools` (what each tool takes
and runs), :mod:`.run` (running one and reading what it printed),
:mod:`.resources` (resources and prompts) and :mod:`.protocol` (the JSON-RPC
loop).
"""

from __future__ import annotations

from .protocol import handle, serve
from .resources import PROMPTS
from .tools import TOOLS, Tool

__all__ = ["PROMPTS", "TOOLS", "Tool", "handle", "serve"]
