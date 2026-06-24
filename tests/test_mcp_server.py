from __future__ import annotations

import json

from intent_code import mcp_server
from intent_code.index import CodeIndex


def _call(ci, name, arguments, msg_id=1):
    return mcp_server.handle_message(
        ci,
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


def test_mcp_protocol_and_tools(repo):
    root = repo(
        {"a.py": "def foo():\n    return 1\n\n\nclass C:\n    def m(self):\n        return 2\n"}
    )
    ci = CodeIndex(root, embedder="hashing:dim=512")
    try:
        init = mcp_server.handle_message(
            ci, {"jsonrpc": "2.0", "id": 0, "method": "initialize"}
        )
        assert init["result"]["serverInfo"]["name"] == "intent-code"

        listed = mcp_server.handle_message(
            ci, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        names = {t["name"] for t in listed["result"]["tools"]}
        assert {"code_index", "code_search", "code_stats", "code_feedback"} <= names

        idx = _call(ci, "code_index", {}, 2)
        assert idx["result"]["isError"] is False
        report = json.loads(idx["result"]["content"][0]["text"])
        assert report["added"] >= 2

        res = _call(ci, "code_search", {"query": "foo", "k": 5}, 3)
        hits = json.loads(res["result"]["content"][0]["text"])
        assert any(h["qualname"] == "foo" for h in hits)

        # filters -> server-side where translation
        res = _call(ci, "code_search", {"query": "m", "filters": {"kind": "method"}}, 4)
        hits = json.loads(res["result"]["content"][0]["text"])
        assert hits and all(h["kind"] == "method" for h in hits)

        bad = _call(ci, "nope", {}, 5)
        assert bad["result"]["isError"] is True
    finally:
        ci.close()


def test_mcp_comprehension_tools(repo):
    root = repo(
        {
            "p.py": (
                "def validate(x):\n    return x\n\n\n"
                "def run(x):\n    validate(x)\n    return x\n"
            )
        }
    )
    ci = CodeIndex(root, embedder="hashing:dim=512")
    try:
        _call(ci, "code_index", {}, 1)
        listed = mcp_server.handle_message(
            ci, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        names = {t["name"] for t in listed["result"]["tools"]}
        assert {"code_read", "code_context", "code_flow"} <= names

        res = _call(ci, "code_read", {"symbol": "run"}, 3)
        data = json.loads(res["result"]["content"][0]["text"])
        assert "validate(x)" in data["code"]

        res = _call(ci, "code_flow", {"symbol": "run"}, 4)
        data = json.loads(res["result"]["content"][0]["text"])
        assert data["steps"][0]["call"] == "validate"

        res = _call(ci, "code_context", {"symbol": "run"}, 5)
        data = json.loads(res["result"]["content"][0]["text"])
        assert "def validate" in data["text"]

        # unknown symbol surfaces as a non-error result with found=false
        res = _call(ci, "code_read", {"symbol": "missing"}, 6)
        assert res["result"]["isError"] is False
        assert json.loads(res["result"]["content"][0]["text"]) == {"found": False}
    finally:
        ci.close()
