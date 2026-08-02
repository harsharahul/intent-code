from __future__ import annotations

import urllib.error

import pytest

from intent_code import CodeIndex, embedder_auto
from intent_code.embedder_auto import EmbedderUnavailable, embedder_guard


def _unreachable(*a, **k):
    """No Ollama server answering."""
    return None


def _serving(*models):
    """A reachable Ollama holding exactly `models`."""

    def probe(*a, **k):
        return list(models)

    return probe


#: what a server reports for a model pulled as plain `nomic-embed-text`
TAGGED = "nomic-embed-text:latest"


def test_fallback_to_hashing(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_models", _unreachable)
    assert embedder_auto.auto_embedder_spec() == "hashing:dim=512"


def test_uses_ollama_when_available(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_models", _serving(TAGGED))
    assert embedder_auto.auto_embedder_spec().startswith("ollama:model=")


def test_env_override_wins(monkeypatch):
    monkeypatch.setenv("INTENT_CODE_EMBEDDER", "hashing:dim=256")
    monkeypatch.setattr(embedder_auto, "ollama_models", _serving(TAGGED))
    assert embedder_auto.auto_embedder_spec() == "hashing:dim=256"


def test_describe_warns_on_hashing_fallback(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_models", _unreachable)
    spec, warning = embedder_auto.describe_auto()
    assert spec == "hashing:dim=512"
    assert warning and "Ollama" in warning


def test_describe_no_warning_with_ollama(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_models", _serving(TAGGED))
    spec, warning = embedder_auto.describe_auto()
    assert spec.startswith("ollama:model=")
    assert warning is None


def test_describe_no_warning_with_override(monkeypatch):
    monkeypatch.setenv("INTENT_CODE_EMBEDDER", "hashing:dim=256")
    monkeypatch.setattr(embedder_auto, "ollama_models", _unreachable)
    spec, warning = embedder_auto.describe_auto()
    assert spec == "hashing:dim=256"
    assert warning is None


# -- model presence -----------------------------------------------------------


def test_tagged_model_counts_as_present():
    # Ollama reports `nomic-embed-text:latest` for what you pulled as
    # `nomic-embed-text`; an exact string match would miss it.
    assert embedder_auto.has_model([TAGGED], "nomic-embed-text")
    assert embedder_auto.has_model(["nomic-embed-text"], "nomic-embed-text")
    assert not embedder_auto.has_model(["llama3.1:latest"], "nomic-embed-text")


def test_running_server_without_the_model_falls_back(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.delenv("INTENT_CODE_AUTO_PULL", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_models", _serving("llama3.1:latest"))
    spec, warning = embedder_auto.describe_auto()
    # Committing to Ollama here would fail later inside the dimension probe.
    assert spec == "hashing:dim=512"
    assert warning and "not pulled" in warning


def test_missing_model_is_pulled_when_allowed(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.delenv("INTENT_CODE_AUTO_PULL", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_models", _serving("llama3.1:latest"))
    calls = []
    monkeypatch.setattr(
        embedder_auto, "pull_model", lambda *a, **k: calls.append(a) or True
    )
    spec, warning = embedder_auto.describe_auto(allow_pull=True)
    assert spec.startswith("ollama:model=")
    assert warning is None
    assert len(calls) == 1


def test_pull_is_not_attempted_by_default(monkeypatch):
    # A search must never trigger a several-hundred-MB download.
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.delenv("INTENT_CODE_AUTO_PULL", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_models", _serving("llama3.1:latest"))
    calls = []
    monkeypatch.setattr(
        embedder_auto, "pull_model", lambda *a, **k: calls.append(a) or True
    )
    spec, _ = embedder_auto.describe_auto()
    assert spec == "hashing:dim=512"
    assert calls == []


def test_auto_pull_env_overrides_both_ways(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_models", _serving("llama3.1:latest"))
    calls = []
    monkeypatch.setattr(
        embedder_auto, "pull_model", lambda *a, **k: calls.append(a) or True
    )

    monkeypatch.setenv("INTENT_CODE_AUTO_PULL", "0")
    embedder_auto.describe_auto(allow_pull=True)
    assert calls == []

    monkeypatch.setenv("INTENT_CODE_AUTO_PULL", "1")
    embedder_auto.describe_auto(allow_pull=False)
    assert len(calls) == 1


def test_failed_pull_falls_back_with_manual_instructions(monkeypatch):
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.delenv("INTENT_CODE_AUTO_PULL", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_models", _serving())
    monkeypatch.setattr(embedder_auto, "pull_model", lambda *a, **k: False)
    spec, warning = embedder_auto.describe_auto(allow_pull=True)
    assert spec == "hashing:dim=512"
    assert warning and "ollama pull" in warning


# -- spec identity ------------------------------------------------------------


def test_identity_survives_expansion_by_the_store():
    # intent-db persists the expanded spec while detection returns the short
    # form; comparing raw strings would report a mismatch every time.
    assert embedder_auto.embedder_identity(
        "hashing:dim=512"
    ) == embedder_auto.embedder_identity("hashing:dim=512,char_ngrams=1")
    assert embedder_auto.embedder_identity(
        "ollama:model=nomic-embed-text"
    ) == embedder_auto.embedder_identity(
        "ollama:model=nomic-embed-text,host=http://localhost:11434,"
        "dim=768,prefix_mode=nomic"
    )


def test_identity_separates_real_differences():
    ident = embedder_auto.embedder_identity
    assert ident("hashing:dim=512") != ident("hashing:dim=256")
    assert ident("hashing:dim=512") != ident("ollama:model=nomic-embed-text")
    assert ident("ollama:model=a") != ident("ollama:model=b")


# -- unreachable backend ------------------------------------------------------


def test_guard_turns_transport_failure_into_a_remedy():
    # An index built against Ollama keeps using Ollama, so stopping the server
    # makes every query fail. A bare URLError from inside urllib says nothing
    # about the fact that one command fixes it.
    with pytest.raises(EmbedderUnavailable) as excinfo:
        with embedder_guard("ollama:model=nomic-embed-text", "hashing:dim=512"):
            raise urllib.error.URLError("Connection refused")
    message = str(excinfo.value)
    assert "index --full" in message
    assert "hashing:dim=512" in message


def test_guard_suggests_starting_the_server_when_nothing_better_exists():
    with pytest.raises(EmbedderUnavailable) as excinfo:
        with embedder_guard(
            "ollama:model=nomic-embed-text", "ollama:model=nomic-embed-text"
        ):
            raise urllib.error.URLError("Connection refused")
    assert "start the embedding server" in str(excinfo.value)


def test_guard_lets_unrelated_errors_through():
    with pytest.raises(ValueError):
        with embedder_guard("hashing:dim=512"):
            raise ValueError("not a transport problem")


# -- reporting through CodeIndex ----------------------------------------------


def test_index_report_carries_warning(repo, monkeypatch):
    # auto-detect (embedder=None) on a fresh index with no Ollama -> warning.
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_models", _unreachable)
    root = repo({"a.py": "def foo():\n    return 1\n"})
    ci = CodeIndex(root)
    try:
        report = ci.index()
        assert report.embedder_warning and "Ollama" in report.embedder_warning
        assert report.embedder_status == "hashing_fallback"
        assert "embedder_warning" in report.to_dict()
        assert report.to_dict()["embedder_status"] == "hashing_fallback"
    finally:
        ci.close()


def test_status_is_always_reported_even_when_the_prose_is_not(repo, monkeypatch):
    # The warning used to be emitted once and then suppressed forever, which is
    # how a degraded embedder stayed invisible. The status must not be.
    monkeypatch.delenv("INTENT_CODE_EMBEDDER", raising=False)
    monkeypatch.setattr(embedder_auto, "ollama_models", _unreachable)
    root = repo({"a.py": "def foo():\n    return 1\n"})
    ci = CodeIndex(root)
    try:
        first = ci.index()
        second = ci.index()
        assert first.embedder_warning is not None
        assert second.embedder_warning is None  # unchanged status, no repeat
        assert second.embedder_status == "hashing_fallback"
        assert second.embedder_remedy
        assert ci.stats()["embedder_status"] == "hashing_fallback"
    finally:
        ci.close()
