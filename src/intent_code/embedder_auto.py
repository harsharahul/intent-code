"""Pick an embedder automatically.

Prefer a local Ollama embedding model (better code semantics) when the server is
reachable; otherwise fall back to intent-db's zero-dependency hashing embedder.
The probe is deliberately cheap and short-timeout so we never hang when Ollama
is absent. Override with the INTENT_CODE_EMBEDDER environment variable.
"""

from __future__ import annotations

import os
import urllib.request

HASHING_SPEC = "hashing:dim=512"
DEFAULT_OLLAMA_MODEL = "nomic-embed-text"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"


def ollama_available(host: str = DEFAULT_OLLAMA_HOST, timeout: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as resp:
            return getattr(resp, "status", 200) == 200
    except Exception:
        return False


def auto_embedder_spec(
    model: str = DEFAULT_OLLAMA_MODEL, host: str = DEFAULT_OLLAMA_HOST
) -> str:
    override = os.environ.get("INTENT_CODE_EMBEDDER")
    if override:
        return override
    if ollama_available(host):
        return f"ollama:model={model}"
    return HASHING_SPEC
