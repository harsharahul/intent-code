from __future__ import annotations

from intent_code.walk import detect_lang, iter_source_files


def test_gitignore_nested_and_forced_ignores(repo):
    root = repo(
        {
            ".gitignore": "ignored/\n*.log\n",
            "a.py": "x = 1\n",
            "docs/readme.md": "# hi\n",
            "ignored/secret.py": "x = 2\n",
            "node_modules/pkg/index.js": "1\n",
            ".git/config": "[core]\n",
            "sub/.gitignore": "skip.py\n",
            "sub/keep.py": "y = 1\n",
            "sub/skip.py": "z = 1\n",
        }
    )
    rels = {sf.relpath for sf in iter_source_files(root)}
    assert "a.py" in rels
    assert "docs/readme.md" in rels
    assert "sub/keep.py" in rels
    assert "ignored/secret.py" not in rels
    assert "node_modules/pkg/index.js" not in rels
    assert "sub/skip.py" not in rels  # nested .gitignore honored
    assert not any(r.startswith(".git/") for r in rels)


def test_classification_and_lang():
    assert detect_lang_path("a.py") == "python"
    assert detect_lang_path("a.ts") == "typescript"
    assert detect_lang_path("a.tsx") == "tsx"
    assert detect_lang_path("a.md") is None


def detect_lang_path(name: str):
    from pathlib import Path

    return detect_lang(Path(name))


def test_kinds(repo):
    root = repo({"a.py": "x=1\n", "b.md": "# t\n", "c.unknownext": "x"})
    by_rel = {sf.relpath: sf for sf in iter_source_files(root)}
    assert by_rel["a.py"].kind == "code" and by_rel["a.py"].lang == "python"
    assert by_rel["b.md"].kind == "text" and by_rel["b.md"].lang is None
    assert "c.unknownext" not in by_rel  # unknown extensions are skipped


def test_agent_instruction_files_excluded(repo):
    # Files written by `init` must not be indexed (re-index feedback loop).
    root = repo(
        {
            "a.py": "x = 1\n",
            "CLAUDE.md": "# protocol\n",
            "GEMINI.md": "# protocol\n",
            "AGENTS.md": "# protocol\n",
            ".github/copilot-instructions.md": "# protocol\n",
            ".github/prompts/code-index.prompt.md": "do it\n",
            ".gemini/commands/code-index.toml": "prompt = 'x'\n",
            "docs/guide.md": "# real doc\n",
        }
    )
    rels = {sf.relpath for sf in iter_source_files(root)}
    assert "a.py" in rels
    assert "docs/guide.md" in rels  # genuine docs still indexed
    for excluded in (
        "CLAUDE.md",
        "GEMINI.md",
        "AGENTS.md",
        ".github/copilot-instructions.md",
        ".github/prompts/code-index.prompt.md",
    ):
        assert excluded not in rels
    assert not any(r.startswith(".gemini/") for r in rels)
