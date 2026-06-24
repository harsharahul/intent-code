"""MCP (Model Context Protocol) stdio server for intent-code.

Pure standard library, JSON-RPC 2.0 over stdin/stdout, protocol 2024-11-05 -
mirrors intent-db's server. Wraps a single CodeIndex for the repo so models can
query the code-knowledge index instead of re-reading files.

Claude Code (.mcp.json)::

    {"mcpServers": {"code": {"command": "intent-code",
                             "args": ["serve-mcp", "."]}}}
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import __version__
from .index import CodeIndex

PROTOCOL_VERSION = "2024-11-05"

_SEARCH_PROPS = {
    "query": {"type": "string", "description": "search text"},
    "intent": {
        "type": "string",
        "description": "code intent: debugging | extending | reviewing | onboarding",
    },
    "k": {"type": "integer", "default": 8},
    "layer": {
        "type": "string",
        "enum": ["symbol", "chunk", "note", "any"],
        "default": "symbol",
        "description": "which layer to search",
    },
    "filters": {
        "type": "object",
        "description": "metadata equality filters, e.g. {\"lang\":\"python\",\"kind\":\"function\"}",
    },
    "hybrid": {"type": "boolean", "default": True},
}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "code_index",
        "description": (
            "Incrementally (re)index the repository. Only changed files are "
            "re-parsed and only changed symbols re-embedded. Call once before "
            "searching, and after edits."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"full": {"type": "boolean", "default": False}},
        },
    },
    {
        "name": "code_search",
        "description": (
            "Search the code-knowledge index. Returns ranked hits with a "
            "file:line location, the symbol's signature card, and a score "
            "breakdown. The SAME query ranks differently per intent. Read only "
            "the returned spans instead of re-reading whole files."
        ),
        "inputSchema": {
            "type": "object",
            "properties": _SEARCH_PROPS,
            "required": ["query"],
        },
    },
    {
        "name": "code_map",
        "description": (
            "Return the PageRank-ranked repo map: the most important symbols "
            "with signatures and file:line, packed to a token budget. Read this "
            "at session start instead of globbing the tree."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"budget": {"type": "integer", "default": 2000}},
        },
    },
    {
        "name": "code_neighbors",
        "description": (
            "Trace a symbol's callers, callees, or importers (blast radius / "
            "flow) without reading files. Edges are name-based and approximate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "doc_key, qualname, or name"},
                "direction": {
                    "type": "string",
                    "enum": ["callers", "callees", "importers"],
                    "default": "callees",
                },
                "k": {"type": "integer", "default": 20},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "code_read",
        "description": (
            "Return a symbol's FULL source span, untruncated, resolved from the "
            "index by doc_key, qualname, or name. Read exact body logic without "
            "globbing for the file or guessing line numbers."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "doc_key, qualname, or name"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "code_context",
        "description": (
            "Assemble the full bodies of a symbol AND what it calls, in call "
            "order, packed to a token budget. One call shows how a function works "
            "end to end instead of chasing callees by hand."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "doc_key, qualname, or name"},
                "depth": {"type": "integer", "default": 2},
                "budget_tokens": {"type": "integer", "default": 4000},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "code_flow",
        "description": (
            "Return the ordered call sequence inside a function: each call in "
            "source order with its resolved target location. See control flow and "
            "ordering without reading the whole body."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "doc_key, qualname, or name"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "note_put",
        "description": (
            "Write or update a durable knowledge note (a gotcha, an invariant, "
            "a control/data-flow explanation). Persists across sessions so it is "
            "never re-derived. List the files it covers so it can be flagged "
            "stale when they change."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {"type": "string", "description": "stable slug/title"},
                "markdown": {"type": "string"},
                "covers": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["note_id", "markdown"],
        },
    },
    {
        "name": "note_get",
        "description": "Read a knowledge note by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"note_id": {"type": "string"}},
            "required": ["note_id"],
        },
    },
    {
        "name": "note_list_stale",
        "description": "List notes whose covered files have changed (need a refresh).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "code_stats",
        "description": "Index statistics: document/file counts, intents, embedder.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "code_feedback",
        "description": (
            "Report whether a search hit was actually useful. Trains per-intent "
            "ranking. Call after using (or discarding) a result."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "doc_key": {"type": "string"},
                "useful": {"type": "boolean", "default": True},
                "intent": {"type": "string"},
            },
            "required": ["query", "doc_key"],
        },
    },
]


def call_tool(ci: CodeIndex, name: str, arguments: dict[str, Any]) -> Any:
    if name == "code_index":
        return ci.index(full=bool(arguments.get("full", False))).to_dict()
    if name == "code_search":
        return ci.search(
            arguments["query"],
            intent=arguments.get("intent"),
            k=int(arguments.get("k", 8)),
            layer=arguments.get("layer", "symbol"),
            filters=arguments.get("filters"),
            hybrid=bool(arguments.get("hybrid", True)),
        )
    if name == "code_map":
        return {"map": ci.map(budget_tokens=int(arguments.get("budget", 2000)))}
    if name == "code_neighbors":
        return ci.neighbors(
            arguments["symbol"],
            direction=arguments.get("direction", "callees"),
            k=int(arguments.get("k", 20)),
        )
    if name == "code_read":
        return ci.read(arguments["symbol"]) or {"found": False}
    if name == "code_context":
        return (
            ci.context(
                arguments["symbol"],
                depth=int(arguments.get("depth", 2)),
                budget_tokens=int(arguments.get("budget_tokens", 4000)),
            )
            or {"found": False}
        )
    if name == "code_flow":
        return ci.flow(arguments["symbol"]) or {"found": False}
    if name == "note_put":
        return ci.note_put(
            arguments["note_id"],
            arguments["markdown"],
            covers=arguments.get("covers"),
        )
    if name == "note_get":
        return ci.note_get(arguments["note_id"]) or {"found": False}
    if name == "note_list_stale":
        return {"stale": ci.note_list_stale()}
    if name == "code_stats":
        return ci.stats()
    if name == "code_feedback":
        ci.feedback(
            arguments["query"],
            arguments["doc_key"],
            useful=bool(arguments.get("useful", True)),
            intent=arguments.get("intent"),
        )
        return {"recorded": True}
    raise ValueError(f"unknown tool {name!r}")


def handle_message(ci: CodeIndex, msg: dict[str, Any]) -> dict[str, Any] | None:
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "intent-code", "version": __version__},
            },
        }
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        try:
            result = call_tool(ci, params.get("name", ""), params.get("arguments") or {})
            content = [{"type": "text", "text": json.dumps(result, indent=2)}]
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": content, "isError": False},
            }
        except Exception as e:  # surface tool failures as tool results, per MCP
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"error: {e}"}],
                    "isError": True,
                },
            }
    if msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }
    return None


def serve(repo: str) -> None:
    """Run the stdio server until stdin closes."""
    ci = CodeIndex(repo)
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = handle_message(ci, msg)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
    finally:
        ci.close()
