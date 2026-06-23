from __future__ import annotations

from intent_code import CodeIndex


def test_note_put_get_search_and_staleness(repo):
    root = repo({"svc.py": "def charge():\n    return gateway()\n"})
    ci = CodeIndex(root, embedder="hashing:dim=512", local_knowledge=True)
    try:
        ci.index()
        res = ci.note_put(
            "Charge gotcha",
            "# Charge gotcha\n\nThe gateway queue is bounded; overflow drops silently.\n",
            covers=["svc.py"],
        )
        slug = res["slug"]
        assert slug == "charge-gotcha"

        note = ci.note_get("charge-gotcha")
        assert "gateway queue is bounded" in note["markdown"]
        assert note["stale"] is False

        # searchable in the note layer, not the symbol layer
        hits = ci.search("gateway overflow drops silently", layer="note", k=3)
        assert any(h["doc_key"] == "note::charge-gotcha" for h in hits)
        sym_hits = ci.search("gateway", layer="symbol", k=5)
        assert all(h["layer"] == "symbol" for h in sym_hits)

        # on-disk artifacts (Karpathy layer)
        kd = root / ".intentdb" / "codemap"
        assert (kd / "notes" / "charge-gotcha.md").exists()
        assert (kd / "index.md").exists()
        assert (kd / "log.md").exists()

        # changing a covered file flags the note stale on the next index
        (root / "svc.py").write_text("def charge():\n    return gateway2()\n", encoding="utf-8")
        report = ci.index()
        assert "charge-gotcha" in report.stale_notes
        assert ci.note_get("charge-gotcha")["stale"] is True
        assert "charge-gotcha" in ci.note_list_stale()
    finally:
        ci.close()
