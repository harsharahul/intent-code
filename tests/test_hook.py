from __future__ import annotations

import io
import json

from intent_code import CodeIndex, hook


def test_hook_marks_edited_file_dirty(repo, monkeypatch):
    root = repo({"a.py": "def f():\n    return 1\n"})
    ci = CodeIndex(root, embedder="hashing:dim=512")
    ci.index()
    ci.close()

    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(root / "a.py")}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert hook.main() == 0
    assert (root / ".intentdb" / "dirty").read_text().strip() == "a.py"


def test_hook_malformed_input_exits_zero(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json at all"))
    assert hook.main() == 0


def test_hook_no_index_root_is_noop(repo, monkeypatch):
    root = repo({"a.py": "x = 1\n"})  # no .intentdb dir built
    payload = {"tool_input": {"file_path": str(root / "a.py")}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert hook.main() == 0
    assert not (root / ".intentdb" / "dirty").exists()


def test_lazy_reindex_on_search(repo):
    root = repo({"a.py": "def foo():\n    return 1\n"})
    ci = CodeIndex(root, embedder="hashing:dim=512")
    try:
        ci.index()
        (root / "a.py").write_text(
            "def foo():\n    return 1\n\n\ndef bar():\n    return 2\n", encoding="utf-8"
        )
        ci.mark_dirty(["a.py"])  # simulates the PostToolUse hook
        hits = ci.search("bar", layer="symbol", k=5)
        assert any(h["qualname"] == "bar" for h in hits)
        assert not (root / ".intentdb" / "dirty").exists()  # consumed
    finally:
        ci.close()
