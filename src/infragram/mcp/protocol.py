"""The MCP protocol: newline-delimited JSON-RPC 2.0 over stdio, answered from
the tools, resources and prompts. stdout carries the protocol and nothing
else; anything else goes to stderr.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .resources import _CATALOG, _CATALOG_TEMPLATE, _PROMPTS, PROMPTS, _catalog, _resources
from .run import _failure, _run
from .tools import _BY_NAME, TOOLS, ArgumentError

#: The protocol versions this server speaks; it answers in the client's when it knows it.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

INSTRUCTIONS = """\
Infragram Azure draws infrastructure architecture diagrams with Azure, Kubernetes and
Databricks components, and writes and reads Azure Terraform.

- To draw: write a Python diagram file (`with Diagram(...)`, frames as `with` blocks, nodes from
  `infragram.nodes.<library>.<category>`, wires as `a >> Edge("label") >> b`; find classes with
  find_components, start from an example or a template with new_diagram), then call compose.
  Without file tools, pass the file's text to compose_source. Or export a .infragram.json
  document with export_project, or a folder of them with export_set. Pass preview: true to see
  the PNG drawn.
- check checks documents and exported pages; verify_render renders a diagram several times and
  checks the picture; check_policy says what a reviewer would stop; check_terraform shows a
  diagram's Terraform works without deploying it; costs adds up what a diagram costs; views
  lists the parts a view can draw.
- import_terraform, import_diagram (draw.io, Mermaid, PlantUML, Excalidraw, Visio) and discover
  draw what already exists (discover reads a live account or cluster, read-only, through the
  cloud's own CLI or kubectl as the user is signed in); diff draws what changed between two
  versions.
- export_azure draws Azure Resource Graph inventory in network and resource-group views,
  across selected subscriptions, and saves or replays raw snapshots without Azure access.
- layout_save keeps what the user moved in the editor beside the diagram file.
- recipes lists the 3D items drawn by spec and draw_recipe draws one; docs reads a reference.
- The references (infragram://references/...) explain the authoring form, frames, exports and
  Terraform; read compose.md before writing a diagram file.
Paths are relative to the folder the server runs in. Never pass force unless the user asked to
replace files."""


# ------------------------------------------------------------ the protocol
def _result(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _error(message_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def handle(message: Any) -> dict[str, Any] | None:
    """The answer to one JSON-RPC message, or None for a notification."""
    from ..cli.version import package_version

    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or "method" not in message:
        return _error(
            message.get("id") if isinstance(message, dict) else None, -32600, "invalid request"
        )
    method, message_id = message["method"], message.get("id")
    params = message.get("params")
    if "id" not in message:
        return None  # notifications/initialized, notifications/cancelled: nothing to answer
    if params is None:
        params = {}
    elif not isinstance(params, dict):
        return _error(message_id, -32602, "params must be an object")
    if method == "initialize":
        asked = params.get("protocolVersion")
        return _result(
            message_id,
            {
                "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"listChanged": False, "subscribe": False},
                    "prompts": {"listChanged": False},
                },
                "serverInfo": {
                    "name": "infragram",
                    "title": "Infragram Architect",
                    "version": package_version(),
                },
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _result(message_id, {})
    if method == "tools/list":
        return _result(message_id, {"tools": [tool.listing() for tool in TOOLS]})
    if method == "tools/call":
        tool = _BY_NAME.get(str(params.get("name")))
        if tool is None:
            return _error(message_id, -32602, f"unknown tool {params.get('name')!r}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(message_id, -32602, "arguments must be an object")
        try:
            answer = _run(tool, arguments)
        except Exception as error:  # noqa: BLE001 - a tool that raises answers with what it raised
            answer = _failure(tool, f"{type(error).__name__}: {error}")
        return _result(message_id, answer.result())
    if method == "resources/list":
        return _result(message_id, {"resources": [entry for entry, _ in _resources().values()]})
    if method == "resources/templates/list":
        return _result(message_id, {"resourceTemplates": [_CATALOG_TEMPLATE]})
    if method == "resources/read":
        uri = str(params.get("uri", ""))
        if uri.startswith(_CATALOG):
            text = _catalog(uri.removeprefix(_CATALOG))
            if text is None:
                return _error(message_id, -32002, f"no library {uri.removeprefix(_CATALOG)!r}")
            return _result(
                message_id, {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": text}]}
            )
        found = _resources().get(uri)
        if found is None:
            return _error(message_id, -32002, f"no resource {uri!r}")
        entry, path = found
        text = path.read_text(encoding="utf-8")
        return _result(
            message_id, {"contents": [{"uri": uri, "mimeType": entry["mimeType"], "text": text}]}
        )
    if method == "prompts/list":
        return _result(message_id, {"prompts": [prompt.listing() for prompt in PROMPTS]})
    if method == "prompts/get":
        prompt = _PROMPTS.get(str(params.get("name")))
        if prompt is None:
            return _error(message_id, -32602, f"unknown prompt {params.get('name')!r}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _error(message_id, -32602, "arguments must be an object")
        try:
            messages = prompt.messages(arguments)
        except ArgumentError as error:
            return _error(message_id, -32602, str(error))
        return _result(message_id, {"description": prompt.description, "messages": messages})
    return _error(message_id, -32601, f"method not found: {method}")


def _answer(message: Any) -> dict[str, Any] | None:
    """:func:`handle`, and an internal error in place of a dead server."""
    try:
        return handle(message)
    except Exception as error:  # noqa: BLE001 - the next request still gets its answer
        message_id = message.get("id") if isinstance(message, dict) else None
        return _error(message_id, -32603, f"{type(error).__name__}: {error}")


def serve(stdin: Any = None, stdout: Any = None) -> int:
    """Answer messages from *stdin* on *stdout*, one JSON line each, until stdin closes."""
    reader = stdin or sys.stdin.buffer
    writer = stdout or sys.stdout.buffer
    # Reading every node module takes seconds; done while the client is
    # still starting up, the first find_components answers at once.
    import threading

    from ..catalog.find import node_classes

    threading.Thread(target=node_classes, name="infragram-find-index", daemon=True).start()
    for raw in reader:
        line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            answers: Any = _error(None, -32700, "parse error")
        else:
            if message == []:
                answers = _error(None, -32600, "an empty batch")
            elif isinstance(message, list):
                answers = [
                    answer for item in message if (answer := _answer(item)) is not None
                ] or None
            else:
                answers = _answer(message)
        if answers is not None:
            writer.write((json.dumps(answers, ensure_ascii=False) + "\n").encode("utf-8"))
            writer.flush()
    return 0
