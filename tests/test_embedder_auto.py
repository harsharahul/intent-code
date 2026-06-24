from __future__ import annotations

from intent_code import CodeIndex, embedder_auto


def test_fallback_to_hashing(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_available", lambda *a, **k: False)
    assert embedder_auto.auto_embedder_spec() == "hashing:dim=512"


def test_uses_ollama_when_available(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_available", lambda *a, **k: True)
    assert embedder_auto.auto_embedder_spec().startswith("ollama:model=")


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("INTENT_CODE_EMBEDDER", "hashing:dim=256")
    monkeypatch.setattr(embedder_auto, "ollama_available", lambda *a, **k: True)
    assert embedder_auto.auto_embedder_spec() == "hashing:dim=256"


def test_describe_warns_on_hashing_fallback(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_available", lambda *a, **k: False)
    spec, warning = embedder_auto.describe_auto()
    assert spec == "hashing:dim=512"
    assert warning and "Ollama" in warning


def test_describe_no_warning_with_ollama(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_available", lambda *a, **k: True)
    spec, warning = embedder_auto.describe_auto()
    assert spec.startswith("ollama:model=")
    assert warning is None


def test_describe_no_warning_with_override(monkeypatch):
    monkeypatch.setenv("INTENT_CODE_EMBEDDER", "hashing:dim=256")
    monkeypatch.setattr(embedder_auto, "ollama_available", lambda *a, **k: False)
    spec, warning = embedder_auto.describe_auto()
    assert spec == "hashing:dim=256"
    assert warning is None


def test_index_report_carries_warning(repo, monkeypatch):
    # auto-detect (embedder=None) on a fresh index with no Ollama -> warning.
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_available", lambda *a, **k: False)
    root = repo({"a.py": "def foo():\n    return 1\n"})
    ci = CodeIndex(root)
    try:
        report = ci.index()
        assert report.embedder_warning and "Ollama" in report.embedder_warning
        assert "embedder_warning" in report.to_dict()
    finally:
        ci.close()
