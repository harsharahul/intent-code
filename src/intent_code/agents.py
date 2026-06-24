"""Wire the code index into coding agents (MCP config + protocol instructions).

One shared protocol (``protocol.PROTOCOL_MD``) is written into each agent's
native instruction file inside an idempotent *managed block*, and an MCP server
entry is merged into each agent's config. Re-running ``intent-code init`` is
safe: the managed block is replaced in place and JSON entries are key-merged,
never clobbering surrounding user content.

Supported agents and where each looks:

- ``claude``  : ``.mcp.json`` (``mcpServers``) + ``CLAUDE.md``
- ``copilot`` : ``.vscode/mcp.json`` (``servers``) + ``.github/copilot-instructions.md``
- ``gemini``  : ``.gemini/settings.json`` (``mcpServers``) + ``GEMINI.md``

The server command is ``intent-code serve-mcp .`` (on PATH after
``uv tool install intent-code``); ``uvx`` users can swap in
``uvx --from intent-code[treesitter] intent-code``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .protocol import PROTOCOL_MD

_SERVER = {"command": "intent-code", "args": ["serve-mcp", "."]}

_BLOCK_START = "<!-- intent-code:start (managed block; edits here are overwritten) -->"
_BLOCK_END = "<!-- intent-code:end -->"

AGENT_KEYS = ("claude", "copilot", "gemini")


def _inject_block(path: Path, body: str) -> str:
    """Write a managed markdown block idempotently, preserving other content."""
    core = f"{_BLOCK_START}\n{body.rstrip()}\n{_BLOCK_END}"
    if path.exists():
        text = path.read_text(encoding="utf-8")
        start, end = text.find(_BLOCK_START), text.find(_BLOCK_END)
        if start != -1 and end != -1 and end > start:
            new = text[:start] + core + text[end + len(_BLOCK_END) :]
            path.write_text(new, encoding="utf-8")
            return f"updated managed block in {path.name}"
        path.write_text(text.rstrip("\n") + "\n\n" + core + "\n", encoding="utf-8")
        return f"appended managed block to {path.name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(core + "\n", encoding="utf-8")
    return f"created {path.name}"


def _merge_json(path: Path, top_key: str, name: str, entry: dict) -> str:
    """Merge an MCP server entry into a JSON config, preserving other keys."""
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return f"left {path.name} unchanged (could not parse existing file)"
        if not isinstance(data, dict):
            return f"left {path.name} unchanged (unexpected JSON shape)"
        servers = data.setdefault(top_key, {})
        existed = name in servers
        servers[name] = entry
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return f"{'refreshed' if existed else 'merged'} entry in {path.name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({top_key: {name: entry}}, indent=2) + "\n", encoding="utf-8")
    return f"created {path.name}"


def _wire_claude(repo: Path) -> dict[str, str]:
    return {
        ".mcp.json": _merge_json(repo / ".mcp.json", "mcpServers", "code", _SERVER),
        "CLAUDE.md": _inject_block(repo / "CLAUDE.md", PROTOCOL_MD),
    }


def _wire_copilot(repo: Path) -> dict[str, str]:
    return {
        ".vscode/mcp.json": _merge_json(
            repo / ".vscode" / "mcp.json",
            "servers",
            "intent-code",
            {"type": "stdio", **_SERVER},
        ),
        ".github/copilot-instructions.md": _inject_block(
            repo / ".github" / "copilot-instructions.md", PROTOCOL_MD
        ),
    }


def _wire_gemini(repo: Path) -> dict[str, str]:
    return {
        ".gemini/settings.json": _merge_json(
            repo / ".gemini" / "settings.json", "mcpServers", "intent-code", _SERVER
        ),
        "GEMINI.md": _inject_block(repo / "GEMINI.md", PROTOCOL_MD),
    }


_WIRERS = {"claude": _wire_claude, "copilot": _wire_copilot, "gemini": _wire_gemini}


def resolve_agents(selected: list[str]) -> list[str]:
    """Expand ``["all"]`` and de-duplicate while preserving order."""
    if not selected:
        return ["claude"]
    if "all" in selected:
        return list(AGENT_KEYS)
    seen, out = set(), []
    for key in selected:
        if key in _WIRERS and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def wire_agents(repo: str | Path, agents: list[str]) -> dict[str, dict[str, str]]:
    """Wire each agent into ``repo``. Returns {agent: {artifact: status}}."""
    repo = Path(repo)
    return {key: _WIRERS[key](repo) for key in resolve_agents(agents)}
