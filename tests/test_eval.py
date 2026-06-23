from __future__ import annotations

from intent_code.eval.harness import Question, run


def test_index_beats_naive_read(repo):
    root = repo(
        {
            "big1.py": "# pad line\n" * 200 + "def unrelated():\n    return 0\n",
            "big2.py": "# pad line\n" * 200,
            "z_target.py": "def target_symbol():\n    return compute_total()\n",
        }
    )
    questions = [
        Question("q1", "target compute total symbol", "z_target.py", "target_symbol")
    ]
    result = run(root, questions, embedder="hashing:dim=512", k=8)

    assert result["recall_at_k"] == 1.0
    # whole-file reads cost far more than the returned signature card
    assert result["index_tokens_total"] < result["baseline_tokens_total"]
    assert result["savings_ratio"] > 0
