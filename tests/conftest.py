"""Shared test fixtures.

Force the hashing embedder via env so auto-detect never reaches a real Ollama
server that may be running on the dev machine (keeps tests fast and offline).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("INTENT_CODE_EMBEDDER", "hashing:dim=512")


@pytest.fixture
def repo(tmp_path):
    def make(files: dict[str, str]):
        for rel, content in files.items():
            p = tmp_path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        return tmp_path

    return make
