"""Default question set for dogfooding on the intent-db repository."""

from __future__ import annotations

from .harness import Question

INTENTDB_QUESTIONS: list[Question] = [
    Question(
        "lens-fit",
        "how is the intent lens fitted from exemplars",
        "src/intentdb/intent.py",
        "IntentLens.fit",
        intent="extending",
    ),
    Question(
        "score-pass",
        "where are the base, lensed and affinity scores computed",
        "src/intentdb/db.py",
        "IntentDB._score_pass",
        intent="debugging",
    ),
    Question(
        "bm25",
        "how is BM25 lexical scoring implemented",
        "src/intentdb/lexical.py",
        "BM25Index",
        intent="onboarding",
    ),
    Question(
        "upsert",
        "how are documents stored and upserted in sqlite",
        "src/intentdb/store.py",
        "upsert_document",
        intent="extending",
    ),
    Question(
        "rerank",
        "how does the cross-encoder reranker score candidates",
        "src/intentdb/rerank.py",
        "FlashRankReranker",
        intent="debugging",
    ),
]
