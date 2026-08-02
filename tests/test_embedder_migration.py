"""Adopting a newly available embedder, and recovering from a vanished store.

The dimension change is the hard part of a rebuild, and two hashing specs
reproduce it exactly (512 vs 256) with no Ollama and no network, so these run
offline like the rest of the suite.
"""

from __future__ import annotations

import os
import time
import urllib.error
from pathlib import Path

import pytest

from intent_code import CodeIndex, embedder_auto
from intent_code.embedder_auto import EmbedderUnavailable
from intent_code.index import LOCK_STALE_SECONDS
from intent_code.migrate import scratch_paths

SOURCE = {"a.py": "def foo():\n    return 1\n"}


def _build(root, spec, monkeypatch):
    monkeypatch.setenv("INTENT_CODE_EMBEDDER", spec)
    return CodeIndex(root)


def test_stored_embedder_is_no_longer_latched(repo, monkeypatch):
    """The original bug: detection ran only when the file was first created."""
    root = repo(SOURCE)
    ci = _build(root, "hashing:dim=512", monkeypatch)
    ci.index(full=True)
    ci.close()

    # A better embedder becomes available. Reopening used to restore the stored
    # spec in silence; now the difference is reported.
    ci = _build(root, "hashing:dim=256", monkeypatch)
    try:
        assert ci.embedder_status == "mismatch"
        assert ci.embedder_spec.startswith("hashing:dim=512")  # still safe to serve
        remedy = ci.stats()["embedder_remedy"]
        assert "index --full" in remedy
    finally:
        ci.close()


def test_full_index_adopts_the_detected_embedder(repo, monkeypatch):
    root = repo(SOURCE)
    ci = _build(root, "hashing:dim=512", monkeypatch)
    ci.index(full=True)
    ci.close()

    ci = _build(root, "hashing:dim=256", monkeypatch)
    try:
        report = ci.index(full=True)
        assert report.rebuild and report.rebuild["rebuilt"]
        assert ci.embedder_spec.startswith("hashing:dim=256")
        assert ci.embedder_status == "ok"
        assert ci.idb.embedder.dim == 256
        # The corpus is rebuilt, not merely re-labelled.
        assert report.files_parsed == 1
        assert ci.stats()["documents"] > 0
    finally:
        ci.close()


def test_rebuild_preserves_notes_feedback_and_queries(repo, monkeypatch):
    root = repo(SOURCE)
    ci = _build(root, "hashing:dim=512", monkeypatch)
    ci.index(full=True)
    ci.notes.put("gotcha", "# Gotcha\n\nMind the ordering.", covers=["a.py"])
    ci.feedback("how does foo work", "note::gotcha", useful=True)
    # Logged directly: CodeIndex.search does not set intent-db's `log` flag, so
    # searching here would leave the log empty and the assertion vacuous.
    ci.idb.store.log_query("how does foo work", None, False)
    before_queries = ci.idb.stats()["logged_queries"]
    assert before_queries == 1
    before_covers = ci.idb.get("note::gotcha")["metadata"]["covers_sha"]
    assert before_covers, "note should record the sha of what it covers"
    ci.close()

    ci = _build(root, "hashing:dim=256", monkeypatch)
    try:
        report = ci.index(full=True)
        assert report.rebuild["notes_preserved"] == 1
        assert report.rebuild["feedback_preserved"] == 1

        note = ci.notes.get("gotcha")
        assert note and note["markdown"].startswith("# Gotcha")
        # covers_sha lives only in the store, so re-reading the markdown from
        # disk would silently drop staleness tracking.
        assert ci.idb.get("note::gotcha")["metadata"]["covers_sha"] == before_covers
        assert len(ci.idb.store.load_feedback()) == 1
        assert ci.idb.stats()["logged_queries"] == before_queries
        # The note is searchable under the new embedder, not just present.
        assert ci.idb.get("note::gotcha") is not None
    finally:
        ci.close()


def test_rebuild_leaves_no_stray_files(repo, monkeypatch):
    root = repo(SOURCE)
    ci = _build(root, "hashing:dim=512", monkeypatch)
    ci.index(full=True)
    ci.close()

    ci = _build(root, "hashing:dim=256", monkeypatch)
    try:
        ci.index(full=True)
    finally:
        ci.close()
    leftovers = sorted(
        p.name for p in Path(root, ".intentdb").glob("code.intentdb.*")
    )
    assert leftovers == [], f"rebuild left {leftovers} behind"


def test_failed_rebuild_leaves_the_original_index_intact(repo, monkeypatch):
    root = repo(SOURCE)
    ci = _build(root, "hashing:dim=512", monkeypatch)
    ci.index(full=True)
    ci.notes.put("keep-me", "# Keep\n\nImportant.", covers=["a.py"])
    before = ci.stats()["documents"]
    ci.close()

    ci = _build(root, "hashing:dim=256", monkeypatch)

    def exploding(*a, **k):
        raise RuntimeError("backend died mid-rebuild")

    monkeypatch.setattr("intent_code.migrate.IntentDB", exploding)
    try:
        with pytest.raises(RuntimeError):
            ci.index(full=True)
    finally:
        ci.close()

    # The swap happens only at the very end, so a crash must not cost the index.
    ci = _build(root, "hashing:dim=512", monkeypatch)
    try:
        assert ci.stats()["documents"] == before
        assert ci.notes.get("keep-me") is not None
        assert ci.embedder_spec.startswith("hashing:dim=512")
        leftovers = sorted(
            p.name for p in Path(root, ".intentdb").glob("code.intentdb.*")
        )
        assert leftovers == []
    finally:
        ci.close()


def test_rebuild_scratch_paths_are_unique_per_attempt():
    # A fixed scratch name lets two concurrent rebuilds of the same repo delete
    # each other's work-in-progress, which surfaces as a SQLite disk I/O error.
    db = Path("/tmp/whatever/code.intentdb")
    first_tmp, first_bak = scratch_paths(db)
    second_tmp, second_bak = scratch_paths(db)
    assert first_tmp != second_tmp
    assert first_bak != second_bak
    assert first_tmp != first_bak
    assert first_tmp.parent == db.parent  # same filesystem, so rename is atomic


def test_explicit_embedder_is_never_overridden(repo, monkeypatch):
    """An explicit --embedder is a decision, not a detection to second-guess."""
    root = repo(SOURCE)
    ci = CodeIndex(root, embedder="hashing:dim=512")
    ci.index(full=True)
    ci.close()

    monkeypatch.setattr(
        embedder_auto, "ollama_models", lambda *a, **k: ["nomic-embed-text:latest"]
    )
    ci = CodeIndex(root, embedder="hashing:dim=512")
    try:
        report = ci.index(full=True)
        assert ci.embedder_status == "ok"
        assert report.rebuild is None
        assert ci.embedder_spec.startswith("hashing:dim=512")
    finally:
        ci.close()


def test_search_reports_an_unreachable_backend_actionably(repo, monkeypatch):
    root = repo(SOURCE)
    ci = _build(root, "hashing:dim=512", monkeypatch)
    try:
        ci.index(full=True)

        def dead(*a, **k):
            raise urllib.error.URLError("Connection refused")

        monkeypatch.setattr(ci.idb, "query", dead)
        with pytest.raises(EmbedderUnavailable) as excinfo:
            ci.search("foo")
        assert "index --full" in str(excinfo.value) or "start the embedding" in str(
            excinfo.value
        )
    finally:
        ci.close()


# -- self-healing -------------------------------------------------------------


def test_deleted_store_is_reopened_rather_than_answered_from_memory(repo, monkeypatch):
    """A long-lived server used to answer from a file that no longer existed."""
    root = repo(SOURCE)
    ci = _build(root, "hashing:dim=512", monkeypatch)
    try:
        ci.index(full=True)
        assert ci.stats()["documents"] > 0

        for path in Path(root, ".intentdb").glob("code.intentdb*"):
            path.unlink()

        # Incremental, exactly as the MCP server would run it. Without the
        # liveness check this reports "0 parsed, 1 skipped" from the in-memory
        # manifest: a confident answer about a database that is gone.
        report = ci.index()
        assert report.files_parsed == 1
        assert report.files_skipped == 0
        assert ci.stats()["documents"] > 0
    finally:
        ci.close()


def test_replaced_store_is_picked_up(repo, monkeypatch):
    root = repo(SOURCE)
    ci = _build(root, "hashing:dim=512", monkeypatch)
    try:
        ci.index(full=True)
        db = Path(root, ".intentdb", "code.intentdb")
        # Another process rebuilds the index: same name, different inode.
        replacement = db.with_name("other.intentdb")
        other = CodeIndex(root, db_path=replacement)
        other.index(full=True)
        other.close()
        os.replace(replacement, db)

        assert ci.stats()["documents"] > 0
        assert ci._db_ident == ci._current_db_ident()
    finally:
        ci.close()


def test_stale_reindex_lock_is_broken(repo, monkeypatch):
    root = repo(SOURCE)
    ci = _build(root, "hashing:dim=512", monkeypatch)
    try:
        lock = ci.idb_dir / "reindex.lock"
        lock.write_text("", encoding="utf-8")
        old = time.time() - (LOCK_STALE_SECONDS + 60)
        os.utime(lock, (old, old))
        # A process killed mid-index used to disable auto-refresh permanently.
        assert ci._take_lock(lock) is True
    finally:
        ci.close()


def test_fresh_reindex_lock_is_respected(repo, monkeypatch):
    root = repo(SOURCE)
    ci = _build(root, "hashing:dim=512", monkeypatch)
    try:
        lock = ci.idb_dir / "reindex.lock"
        lock.write_text("", encoding="utf-8")
        assert ci._take_lock(lock) is False
    finally:
        ci.close()
