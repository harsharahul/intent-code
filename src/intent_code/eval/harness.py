"""Measure tokens-to-answer: a naive read baseline vs the intent index.

Baseline models an agent with no index: it reads whole files (alphabetical
order) until it reaches the file holding the answer. Index arm: it calls
``code_search`` and reads only the returned signature cards until the gold
symbol appears. Token counts use the standard ~4-chars-per-token heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import CodeIndex
from ..walk import iter_source_files


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class Question:
    id: str
    text: str
    gold_file: str  # repo-relative posix path
    gold_symbol: str  # qualname (or its trailing component)
    intent: str | None = None


def baseline_cost(repo_root, q: Question) -> dict:
    files = sorted(iter_source_files(repo_root), key=lambda sf: sf.relpath)
    tokens = reads = 0
    found = False
    for sf in files:
        try:
            text = sf.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        tokens += est_tokens(text)
        reads += 1
        if sf.relpath == q.gold_file:
            found = True
            break
    return {"tokens": tokens, "reads": reads, "found": found}


def _matches(hit: dict, gold: str) -> bool:
    qn = hit.get("qualname") or ""
    return qn == gold or qn.endswith("." + gold) or hit.get("doc_key") == gold


def index_cost(ci: CodeIndex, q: Question, k: int = 8) -> dict:
    hits = ci.search(q.text, intent=q.intent, k=k)
    tokens = 0
    for rank, hit in enumerate(hits, 1):
        tokens += est_tokens(hit.get("snippet") or "")
        if _matches(hit, q.gold_symbol):
            return {"tokens": tokens, "found": True, "rank": rank}
    return {"tokens": tokens, "found": False, "rank": None}


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    bt = sum(r["baseline_tokens"] for r in rows)
    it = sum(r["index_tokens"] for r in rows)
    recall = (sum(1 for r in rows if r["index_found"]) / n) if n else 0.0
    return {
        "rows": rows,
        "n": n,
        "baseline_tokens_total": bt,
        "index_tokens_total": it,
        "savings_ratio": (1 - it / bt) if bt else 0.0,
        "recall_at_k": recall,
    }


def run(repo_root, questions: list[Question], embedder: str = "hashing:dim=512", k: int = 8) -> dict:
    ci = CodeIndex(repo_root, embedder=embedder, local_knowledge=True)
    try:
        ci.index()
        rows = []
        for q in questions:
            base = baseline_cost(repo_root, q)
            idx = index_cost(ci, q, k=k)
            rows.append(
                {
                    "id": q.id,
                    "intent": q.intent,
                    "baseline_tokens": base["tokens"],
                    "baseline_reads": base["reads"],
                    "index_tokens": idx["tokens"],
                    "index_found": idx["found"],
                    "index_rank": idx["rank"],
                }
            )
    finally:
        ci.close()
    return aggregate(rows)
