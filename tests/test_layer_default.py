"""The default search layer adapts to what the index can actually answer.

Without tree-sitter grammars every file falls back to text chunks, so a search
filtered to the symbol layer matched nothing and returned `[]` while every
status signal reported the index as healthy. Grammars are a core dependency now,
but files no grammar can parse (markdown, config, unsupported languages) still
land in the chunk layer, so the resolution stays.
"""

from __future__ import annotations

from intent_code import CodeIndex
from intent_code.index import manifest_has_symbols

CODE = {"auth.py": "def verify_token(token):\n    return {'sub': 'user'}\n"}
PROSE = {"NOTES.md": "# Notes\n\nAuthentication uses short-lived tokens.\n"}


def test_manifest_has_symbols_distinguishes_layers():
    # Both layers are bookkept under "symbols", so the doc-key suffix is what
    # separates a parsed symbol from a text chunk.
    assert manifest_has_symbols({"a.py": {"symbols": {"a.py::f#sym": {}}}})
    assert not manifest_has_symbols({"a.md": {"symbols": {"a.md#chunk0": {}}}})
    assert not manifest_has_symbols({})
    assert manifest_has_symbols(
        {"a.md": {"symbols": {"a.md#chunk0": {}}}, "a.py": {"symbols": {"x#sym": {}}}}
    )


def test_prose_only_index_answers_a_default_search(repo):
    """The regression: an index with no symbols returned [] for everything."""
    ci = CodeIndex(repo(PROSE))
    try:
        ci.index(full=True)
        assert ci.index_has_symbols() is False
        assert ci.effective_layer(None) == "any"
        assert ci.search("authentication tokens"), "default search found nothing"
    finally:
        ci.close()


def test_explicit_symbol_layer_is_still_honoured(repo):
    # Asking for symbols in an index that has none is a real, honest empty
    # result. Only the unspecified default adapts.
    ci = CodeIndex(repo(PROSE))
    try:
        ci.index(full=True)
        assert ci.search("authentication tokens", layer="symbol") == []
    finally:
        ci.close()


def test_code_index_keeps_the_precise_symbol_default(repo):
    ci = CodeIndex(repo(CODE))
    try:
        ci.index(full=True)
        assert ci.index_has_symbols() is True
        assert ci.effective_layer(None) == "symbol"
        hits = ci.search("verify_token")
        assert hits and all(h["doc_key"].endswith("#sym") for h in hits)
    finally:
        ci.close()


def test_stats_exposes_the_resolved_default(repo):
    ci = CodeIndex(repo(PROSE))
    try:
        ci.index(full=True)
        stats = ci.stats()
        assert stats["has_symbols"] is False
        assert stats["default_layer"] == "any"
    finally:
        ci.close()


def test_symbol_presence_is_recomputed_for_older_indexes(repo, monkeypatch):
    """An index written before `has_symbols` was recorded still resolves."""
    root = repo(CODE)
    ci = CodeIndex(root)
    ci.index(full=True)
    ci.close()

    ci = CodeIndex(root)
    try:
        from intent_code import manifest as _manifest

        real = _manifest.load_manifest

        def without_flag(idb):
            m = dict(real(idb))
            m.pop("has_symbols", None)
            return m

        monkeypatch.setattr(_manifest, "load_manifest", without_flag)
        ci._symbols_present = None
        assert ci.index_has_symbols() is True
    finally:
        ci.close()


def test_default_flips_when_symbols_appear(repo):
    """Adding parseable code to a prose-only repo re-resolves the default."""
    root = repo(PROSE)
    ci = CodeIndex(root)
    try:
        ci.index(full=True)
        assert ci.effective_layer(None) == "any"
        (root / "auth.py").write_text(CODE["auth.py"], encoding="utf-8")
        ci.index(full=True)
        assert ci.effective_layer(None) == "symbol"
    finally:
        ci.close()
