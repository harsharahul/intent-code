"""Run the token-spend benchmark.

    python -m intent_code.eval.run /path/to/repo            # intent-db question set
    python -m intent_code.eval.run . --embedder hashing:dim=512 --json
"""

from __future__ import annotations

import argparse
import json

from .harness import run
from .questions import INTENTDB_QUESTIONS


def _render(r: dict) -> str:
    lines = [
        f"questions: {r['n']}   recall@k: {r['recall_at_k']:.0%}",
        f"baseline tokens: {r['baseline_tokens_total']:,}   "
        f"index tokens: {r['index_tokens_total']:,}",
        f"token savings: {r['savings_ratio']:.0%}",
        "",
        f"{'id':22} {'intent':11} {'baseline':>9} {'index':>7} {'rank':>5}",
    ]
    for row in r["rows"]:
        lines.append(
            f"{row['id']:22} {str(row['intent']):11} "
            f"{row['baseline_tokens']:>9,} {row['index_tokens']:>7,} "
            f"{str(row['index_rank']):>5}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="intent-code-eval")
    ap.add_argument("repo")
    ap.add_argument("--embedder", default="hashing:dim=512")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = run(args.repo, INTENTDB_QUESTIONS, embedder=args.embedder, k=args.k)
    print(json.dumps(result, indent=2) if args.json else _render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
