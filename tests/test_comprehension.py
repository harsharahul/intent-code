"""The comprehension layer: read / flow / context.

These read full bodies straight from the index (no truncation) and follow the
call graph in source order, so an agent can understand how code works without
re-globbing files.
"""

from __future__ import annotations

from intent_code import CodeIndex

PIPELINE = (
    "def validate(x):\n"
    "    return x is not None\n\n\n"
    "def normalize(x):\n"
    "    return x.strip()\n\n\n"
    "def persist(x):\n"
    "    return STORE.append(x)\n\n\n"
    "def run(x):\n"
    "    validate(x)\n"
    "    normalize(x)\n"
    "    persist(x)\n"
    "    return True\n"
)


def _index(repo):
    root = repo({"pipeline.py": PIPELINE})
    ci = CodeIndex(root, embedder="hashing:dim=512")
    ci.index()
    return ci


def test_read_returns_full_untruncated_body(repo):
    ci = _index(repo)
    try:
        result = ci.read("run")
        assert result is not None
        assert result["qualname"] == "run"
        assert result["file"] == "pipeline.py"
        # full body present, nothing truncated
        assert "validate(x)" in result["code"]
        assert "persist(x)" in result["code"]
        assert "return True" in result["code"]
        assert result["start_line"] < result["end_line"]
    finally:
        ci.close()


def test_read_missing_symbol_returns_none(repo):
    ci = _index(repo)
    try:
        assert ci.read("does_not_exist") is None
    finally:
        ci.close()


def test_flow_preserves_source_call_order(repo):
    ci = _index(repo)
    try:
        result = ci.flow("run")
        assert result is not None
        calls = [step["call"] for step in result["steps"]]
        # source order, NOT alphabetical (would be normalize, persist, validate)
        assert calls == ["validate", "normalize", "persist"]
        # each in-repo call resolves to a location
        by_call = {s["call"]: s for s in result["steps"]}
        assert by_call["validate"]["location"].startswith("pipeline.py:")
    finally:
        ci.close()


def test_context_includes_callees_in_order(repo):
    ci = _index(repo)
    try:
        result = ci.context("run", depth=2)
        assert result is not None
        text = result["text"]
        # root + all three callees present with their bodies
        assert "run (function)" in text
        assert "x.strip()" in text  # normalize body
        assert "STORE.append(x)" in text  # persist body
        # root comes before its callees
        assert text.index("def run") < text.index("def normalize")
    finally:
        ci.close()


def test_context_respects_budget(repo):
    # Bodies big enough that the whole graph cannot fit the budget floor.
    pad = "    # " + ("padding " * 50) + "\n"
    big = (
        "def leaf_a(x):\n" + pad + "    return x\n\n\n"
        "def leaf_b(x):\n" + pad + "    return x\n\n\n"
        "def root(x):\n    leaf_a(x)\n    leaf_b(x)\n    return x\n"
    )
    root = repo({"big.py": big})
    ci = CodeIndex(root, embedder="hashing:dim=512")
    ci.index()
    try:
        result = ci.context("root", depth=2, budget_tokens=1)
        assert result is not None
        # root is always included; at least one callee is dropped under budget
        assert result["root"] in result["symbols"]
        assert "omitted" in result["text"]
    finally:
        ci.close()
