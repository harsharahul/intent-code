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


def test_cli_read_flow_context(repo, capsys):
    root = repo(
        {
            "p.py": (
                "def validate(x):\n    return x is not None\n\n\n"
                "def run(x):\n    validate(x)\n    return x\n"
            )
        }
    )
    main(["index", str(root), "--embedder", "hashing:dim=512"])
    capsys.readouterr()

    assert main(["read", str(root), "run", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "validate(x)" in out["code"]

    assert main(["flow", str(root), "run", "--json"]) == 0
    flow = json.loads(capsys.readouterr().out)
    assert [s["call"] for s in flow["steps"]] == ["validate"]

    assert main(["context", str(root), "run", "--json"]) == 0
    ctx = json.loads(capsys.readouterr().out)
    assert "def validate" in ctx["text"]

    # missing symbol -> non-zero exit
    assert main(["read", str(root), "nope"]) == 1


def test_cli_search_repo_scope(repo, capsys):
    root = repo(
        {
            "repoA/.git/HEAD": "x\n",
            "repoA/svc.py": "def alpha():\n    return 1\n",
            "repoB/.git/HEAD": "x\n",
            "repoB/svc.py": "def beta():\n    return 2\n",
        }
    )
    main(["index", str(root), "--embedder", "hashing:dim=512"])
    capsys.readouterr()
    # --repo must not collide with the positional repo path (regression guard)
    assert main(["search", str(root), "alpha beta", "--repo", "repoA", "--json", "-k", "10"]) == 0
    hits = json.loads(capsys.readouterr().out)
    names = {h["qualname"] for h in hits}
    assert "alpha" in names and "beta" not in names
    assert all(h["repo"] == "repoA" for h in hits)


def test_cli_init_agent_all(repo, capsys):
    root = repo({"a.py": "def foo():\n    return 1\n"})
    assert (
        main(["init", str(root), "--agent", "all", "--embedder", "hashing:dim=512", "--local"])
        == 0
    )
    out = json.loads(capsys.readouterr().out)
    assert set(out["agents"]) == {"claude", "copilot", "gemini"}
    assert (root / ".mcp.json").exists()
    assert (root / ".vscode" / "mcp.json").exists()
    assert (root / ".gemini" / "settings.json").exists()
    assert (root / "GEMINI.md").exists()
    assert (root / ".github" / "copilot-instructions.md").exists()
    # the instruction files written into the tree are not re-indexed
    capsys.readouterr()
    main(["index", str(root), "--local"])
    report = json.loads(capsys.readouterr().out)
    assert report["added"] == 0 and report["changed"] == 0


def test_cli_stats(repo, capsys):
    root = repo({"a.py": "def foo():\n    return 1\n"})
    main(["index", str(root), "--embedder", "hashing:dim=512"])
    capsys.readouterr()
    assert main(["stats", str(root)]) == 0
    stats = json.loads(capsys.readouterr().out)
    assert stats["files"] == 1
    assert stats["embedder"].startswith("hashing:dim=512")
