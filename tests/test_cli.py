from __future__ import annotations

import json

from intent_code.cli import main


def test_cli_note_local_flag(repo, capsys):
    root = repo({"a.py": "def foo():\n    return 1\n"})
    main(["index", str(root), "--embedder", "hashing:dim=512", "--local"])
    capsys.readouterr()
    assert (
        main(["note", "put", str(root), "my-note", "--text", "# gotcha\nbeware", "--covers", "a.py", "--local"])
        == 0
    )
    capsys.readouterr()
    # the note lands in the LOCAL knowledge dir, not the committed docs/codemap
    assert (root / ".intentdb" / "codemap" / "notes" / "my-note.md").exists()
    assert not (root / "docs" / "codemap").exists()
    # and is retrievable with --local
    assert main(["note", "get", str(root), "my-note", "--local", "--json"]) == 0
    note = json.loads(capsys.readouterr().out)
    assert "beware" in note["markdown"]


def test_cli_index_then_search(repo, capsys):
    root = repo({"a.py": "def foo():\n    return bar()\n\n\ndef bar():\n    return 1\n"})
    assert main(["index", str(root), "--embedder", "hashing:dim=512"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["added"] >= 2

    assert main(["search", str(root), "foo", "--json", "-k", "5"]) == 0
    hits = json.loads(capsys.readouterr().out)
    assert any(h["qualname"] == "foo" for h in hits)
    assert all(h["layer"] == "symbol" for h in hits)


def test_cli_init_wires_mcp_and_protocol(repo, capsys):
    root = repo({"a.py": "def foo():\n    return 1\n"})
    assert main(["init", str(root), "--embedder", "hashing:dim=512", "--local"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["index"]["added"] >= 1
    mcp = json.loads((root / ".mcp.json").read_text())
    assert mcp["mcpServers"]["code"]["command"] == "intent-code"
    assert (root / ".intentdb" / "AGENT_PROTOCOL.md").exists()


def test_cli_stats(repo, capsys):
    root = repo({"a.py": "def foo():\n    return 1\n"})
    main(["index", str(root), "--embedder", "hashing:dim=512"])
    capsys.readouterr()
    assert main(["stats", str(root)]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["files"] == 1
    assert stats["embedder"].startswith("hashing:dim=512")
