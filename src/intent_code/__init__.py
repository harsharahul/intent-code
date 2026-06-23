"""intent-code: an intent-aware code-knowledge index for LLM agents.

Built on intent-db. Index a repository once, then query it by intent
(debugging / extending / reviewing / onboarding) to get distilled answers and
precise file:line pointers, so an agent reads only what it needs instead of
re-reading the whole repo every session.

Public API is populated as the package is built; see `intent_code.index`.
"""

from __future__ import annotations

from .index import CodeIndex, IndexReport

__version__ = "0.1.0"

__all__ = ["__version__", "CodeIndex", "IndexReport"]
