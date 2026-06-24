from __future__ import annotations

import json

from intent_code.agents import _BLOCK_START, resolve_agents, wire_agents


def test_resolve_agents_default_all_and_dedup():
    assert resolve_agents(None) == ["claude"]
    assert resolve_agents([]) == ["claude"]
    assert resolve_agents(["all"]) == ["claude", "copilot", "gemini"]
    assert resolve_agents(["gemini", "gemini", "copilot"]) == ["gemini", "copilot"]


def test_wire_claude(tmp_path):
    wire_agents(tmp_path, ["claude"])
    mcp = json.loads((tmp_path / ".mcp.json").read_text())
    assert mcp["mcpServers"]["code"]["command"] == "intent-code"
    claude = (tmp_path / "CLAUDE.md").read_text()
    assert _BLOCK_START in claude and "code_search" in claude


def test_wire_copilot(tmp_path):
    wire_agents(tmp_path, ["copilot"])
    mcp = json.loads((tmp_path / ".vscode" / "mcp.json").read_text())
    assert mcp["servers"]["intent-code"]["type"] == "stdio"
    instr = (tmp_path / ".github" / "copilot-instructions.md").read_text()
    assert instr.count(_BLOCK_START) == 1


def test_wire_gemini(tmp_path):
    wire_agents(tmp_path, ["gemini"])
    mcp = json.loads((tmp_path / ".gemini" / "settings.json").read_text())
    assert mcp["mcpServers"]["intent-code"]["command"] == "intent-code"
    assert _BLOCK_START in (tmp_path / "GEMINI.md").read_text()


def test_inject_block_idempotent_and_preserves_user_content(tmp_path):
    claude = tmp_path / "CLAUDE.md"
    claude.write_text("# My project\n\nKeep this line.\n", encoding="utf-8")

    wire_agents(tmp_path, ["claude"])
    text = claude.read_text()
    assert "Keep this line." in text  # user content preserved
    assert text.count(_BLOCK_START) == 1

    wire_agents(tmp_path, ["claude"])  # re-run
    text = claude.read_text()
    assert text.count(_BLOCK_START) == 1  # replaced in place, not duplicated
    assert "Keep this line." in text


def test_merge_json_preserves_other_servers(tmp_path):
    vscode = tmp_path / ".vscode"
    vscode.mkdir()
    (vscode / "mcp.json").write_text(
        json.dumps({"servers": {"other": {"command": "x"}}}), encoding="utf-8"
    )
    wire_agents(tmp_path, ["copilot"])
    data = json.loads((vscode / "mcp.json").read_text())
    assert "other" in data["servers"]  # existing entry untouched
    assert "intent-code" in data["servers"]  # new entry merged in


def test_wire_all_writes_every_target(tmp_path):
    result = wire_agents(tmp_path, ["all"])
    assert set(result) == {"claude", "copilot", "gemini"}
    assert (tmp_path / ".mcp.json").exists()
    assert (tmp_path / ".vscode" / "mcp.json").exists()
    assert (tmp_path / ".gemini" / "settings.json").exists()
