from __future__ import annotations

from intent_code import CodeIndex
from intent_code.intents import CODE_INTENT_NAMES


def test_incremental_reembeds_only_changed(repo):
    root = repo(
        {
            "pkg/a.py": "def alpha():\n    return 1\n\n\ndef beta():\n    return 2\n",
            "pkg/b.py": "def gamma():\n    return 3\n",
        }
    )
    ci = CodeIndex(root, embedder="hashing:dim=512")
    try:
        r1 = ci.index()
        assert r1.added >= 3  # alpha, beta, gamma
        assert r1.changed == 0 and r1.removed == 0

        # Intents registered after first index.
        names = {i["name"] for i in ci.idb.list_intents()}
        assert set(CODE_INTENT_NAMES) <= names

        # Change ONLY beta in a.py; b.py untouched.
        (root / "pkg/a.py").write_text(
            "def alpha():\n    return 1\n\n\ndef beta():\n    return 22\n",
            encoding="utf-8",
        )
        r2 = ci.index()
        assert r2.changed == 1
        assert r2.added == 0
        assert r2.removed == 0
        assert r2.files_skipped == 1  # b.py skipped entirely (no parse/embed)
        assert r2.files_parsed == 1  # only a.py

        # Delete b.py -> its symbol is removed.
        (root / "pkg/b.py").unlink()
        r3 = ci.index()
        assert r3.removed == 1
    finally:
        ci.close()


def test_search_finds_relevant_symbol(repo):
    root = repo(
        {
            "svc.py": (
                "def handle_error(exc):\n"
                "    # log and recover from the failure\n"
                "    return recover(exc)\n\n\n"
                "def register_plugin(name):\n"
                "    # add a new plugin to the registry\n"
                "    return REGISTRY.append(name)\n"
            )
        }
    )
    ci = CodeIndex(root, embedder="hashing:dim=512")
    try:
        ci.index()
        hits = ci.search("handle error failure recover", layer="symbol", k=5)
        assert hits, "expected at least one hit"
        quals = {h["qualname"] for h in hits}
        assert "handle_error" in quals
        # every hit carries a precise location
        assert all(h["location"] and ":" in h["location"] for h in hits)
        # reserved manifest doc never leaks into results
        assert all(h["layer"] == "symbol" for h in hits)
    finally:
        ci.close()


def test_chunk_layer_for_text_files(repo):
    root = repo({"GUIDE.md": "# Title\n\n" + ("some prose paragraph. " * 80) + "\n"})
    ci = CodeIndex(root, embedder="hashing:dim=512")
    try:
        rep = ci.index()
        assert rep.added >= 1
        hits = ci.search("prose paragraph", layer="chunk", k=3)
        assert hits and hits[0]["layer"] == "chunk"
    finally:
        ci.close()
