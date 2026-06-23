from __future__ import annotations

from intent_code import embedder_auto


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
