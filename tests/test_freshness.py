"""Query-time freshness: detect edits with no hook and no git, made cheap by a
stat gate so unchanged files are never read.
"""

from __future__ import annotations

from pathlib import Path

from intent_code import CodeIndex
from intent_code import manifest as _manifest

_TWO = "def foo():\n    return 1\n\n\ndef NEW():\n    return 2\n"


def test_stat_gate_skips_reading_unchanged_files(repo, monkeypatch):
    root = repo({"a.py": "def foo():\n    return 1\n"})
    ci = CodeIndex(root, embedder="hashing:dim=512", auto_refresh=False)
    try:
        ci.index()  # first pass records mtime_ns + size
        reads: list[Path] = []
        original = Path.read_bytes
        monkeypatch.setattr(
            Path, "read_bytes", lambda self: (reads.append(self), original(self))[1]
        )
        report = ci.index()  # nothing changed on disk
        assert report.files_skipped == 1
        assert report.added == 0 and report.changed == 0
        assert reads == []  # the stat gate meant we never opened the file
    finally:
        ci.close()


def test_auto_refresh_picks_up_edit_without_any_dirty_marker(repo):
    root = repo({"a.py": "def foo():\n    return 1\n"})
    ci = CodeIndex(root, embedder="hashing:dim=512", refresh_ttl=0.0)  # always due
    try:
        ci.index()
        (root / "a.py").write_text(_TWO, encoding="utf-8")  # edit on disk only
        assert ci._read_dirty() == []  # nothing marked it dirty
        hits = ci.search("NEW", k=5)
        assert any(h["qualname"] == "NEW" for h in hits)
    finally:
        ci.close()


def test_auto_refresh_disabled_stays_stale(repo):
    root = repo({"a.py": "def foo():\n    return 1\n"})
    ci = CodeIndex(root, embedder="hashing:dim=512", auto_refresh=False)
    try:
        ci.index()
        (root / "a.py").write_text(_TWO, encoding="utf-8")
        hits = ci.search("NEW", k=5)
        assert not any(h["qualname"] == "NEW" for h in hits)  # not picked up
    finally:
        ci.close()


def test_ttl_throttles_rescan(repo):
    root = repo({"a.py": "def foo():\n    return 1\n"})
    ci = CodeIndex(root, embedder="hashing:dim=512", refresh_ttl=3600.0)
    try:
        ci.index()
        ci.search("foo")  # records last_scan
        (root / "a.py").write_text(_TWO, encoding="utf-8")
        hits = ci.search("NEW", k=5)  # within the TTL window: no re-scan
        assert not any(h["qualname"] == "NEW" for h in hits)
    finally:
        ci.close()


def test_env_disables_auto_refresh(repo, monkeypatch):
    monkeypatch.setenv("INTENT_CODE_AUTO_REFRESH", "0")
    root = repo({"a.py": "def foo():\n    return 1\n"})
    ci = CodeIndex(root, embedder="hashing:dim=512", refresh_ttl=0.0)
    try:
        assert ci._auto_refresh is False  # env beats the default
        ci.index()
        (root / "a.py").write_text(_TWO, encoding="utf-8")
        assert not any(h["qualname"] == "NEW" for h in ci.search("NEW", k=5))
    finally:
        ci.close()


def test_backfill_missing_mtime_self_heals(repo):
    root = repo({"a.py": "def foo():\n    return 1\n"})
    ci = CodeIndex(root, embedder="hashing:dim=512", auto_refresh=False)
    try:
        ci.index()
        # simulate a pre-0.2.3 manifest with no stat fields
        man = _manifest.load_manifest(ci.idb)
        for entry in man["files"].values():
            entry.pop("mtime_ns", None)
            entry.pop("size", None)
        _manifest.save_manifest(ci.idb, man)

        report = ci.index()  # must not crash, must not re-embed identical content
        assert report.added == 0 and report.changed == 0
        healed = _manifest.load_manifest(ci.idb)
        assert all("mtime_ns" in e for e in healed["files"].values())
    finally:
        ci.close()
