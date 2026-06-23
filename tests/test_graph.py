from __future__ import annotations

from intent_code import CodeIndex, graph


def _manifest():
    def sym(name, calls, line):
        return {
            "sha": name,
            "name": name,
            "qualname": name,
            "kind": "function",
            "start_line": line,
            "end_line": line + 1,
            "sig": f"def {name}():",
            "calls": calls,
        }

    return {
        "files": {
            "m.py": {
                "sha": "x",
                "lang": "python",
                "kind": "code",
                "imports": ["from pkg import util"],
                "symbols": {
                    "m.py::hub#sym": sym("hub", [], 1),
                    "m.py::a#sym": sym("a", ["hub"], 4),
                    "m.py::b#sym": sym("b", ["hub", "a"], 7),
                },
            },
            "pkg/util.py": {
                "sha": "y",
                "lang": "python",
                "kind": "code",
                "imports": [],
                "symbols": {"pkg/util.py::helper#sym": sym("helper", [], 1)},
            },
        }
    }


def test_pagerank_ranks_hub_highest():
    g = graph.build_graph(_manifest())
    ranks = graph.pagerank(g)
    assert max(ranks, key=ranks.get) == "m.py::hub#sym"


def test_neighbors_callers_and_callees():
    g = graph.build_graph(_manifest())
    callers = {c["qualname"] for c in graph.neighbors(g, "hub", direction="callers")}
    assert {"a", "b"} <= callers
    callees = {c["qualname"] for c in graph.neighbors(g, "b", direction="callees")}
    assert {"hub", "a"} <= callees


def test_neighbors_importers():
    g = graph.build_graph(_manifest())
    files = {i["file"] for i in graph.neighbors(g, "helper", direction="importers")}
    assert "m.py" in files


def test_render_map_respects_budget_and_header():
    g = graph.build_graph(_manifest())
    ranks = graph.pagerank(g)
    full = graph.render_map(_manifest(), ranks, budget_tokens=10000)
    tiny = graph.render_map(_manifest(), ranks, budget_tokens=50)
    assert "intent-code" in full
    assert "hub" in full
    assert len(tiny) <= len(full)


def test_map_and_neighbors_after_index(repo):
    root = repo(
        {
            "m.py": (
                "def hub():\n    return 1\n\n\n"
                "def a():\n    return hub()\n\n\n"
                "def b():\n    return hub() + a()\n"
            )
        }
    )
    ci = CodeIndex(root, embedder="hashing:dim=512", local_knowledge=True)
    try:
        ci.index()
        mp = ci.map()
        assert "hub" in mp and "m.py" in mp
        assert (root / ".intentdb" / "codemap" / "MAP.md").exists()
        callers = {c["qualname"] for c in ci.neighbors("hub", direction="callers")}
        assert {"a", "b"} <= callers
    finally:
        ci.close()
