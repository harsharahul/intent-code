"""Repo-scoped search: tag each symbol with its enclosing git repo so a single
index over several repos can be searched per-repo and hits show provenance.
"""

from __future__ import annotations

from intent_code import CodeIndex
from intent_code.walk import iter_source_files


def _multirepo(repo):
    return repo(
        {
            "repoA/.git/HEAD": "ref: refs/heads/main\n",
            "repoA/svc.py": "def alpha():\n    return 1\n",
            "repoB/.git/HEAD": "ref: refs/heads/main\n",
            "repoB/svc.py": "def beta():\n    return 2\n",
            "loose.py": "def gamma():\n    return 3\n",  # in the parent, no repo
        }
    )


def test_walk_tags_enclosing_repo(repo):
    by_rel = {sf.relpath: sf.repo for sf in iter_source_files(_multirepo(repo))}
    assert by_rel["repoA/svc.py"] == "repoA"
    assert by_rel["repoB/svc.py"] == "repoB"
    assert by_rel["loose.py"] == "."  # the index root


def test_walk_nested_repo_deepest_wins(repo):
    root = repo(
        {
            "outer/.git/HEAD": "x\n",
            "outer/a.py": "def a():\n    return 1\n",
            "outer/vendor/lib/.git/HEAD": "x\n",
            "outer/vendor/lib/b.py": "def b():\n    return 2\n",
        }
    )
    by_rel = {sf.relpath: sf.repo for sf in iter_source_files(root)}
    assert by_rel["outer/a.py"] == "outer"
    assert by_rel["outer/vendor/lib/b.py"] == "outer/vendor/lib"  # deepest enclosing


def test_walk_git_as_file_is_repo_root(repo):
    # submodules / linked worktrees store .git as a FILE, not a directory
    root = repo(
        {
            "mod/.git": "gitdir: ../.git/modules/mod\n",
            "mod/c.py": "def c():\n    return 1\n",
        }
    )
    by_rel = {sf.relpath: sf.repo for sf in iter_source_files(root)}
    assert by_rel["mod/c.py"] == "mod"


def test_search_scopes_and_reports_provenance(repo):
    ci = CodeIndex(_multirepo(repo), embedder="hashing:dim=512")
    try:
        ci.index()
        hits = ci.search("alpha beta gamma", layer="symbol", k=10)
        by_repo = {h["qualname"]: h["repo"] for h in hits}
        assert by_repo.get("alpha") == "repoA"  # provenance on every hit
        assert by_repo.get("beta") == "repoB"
        assert by_repo.get("gamma") == "."

        scoped = ci.search(
            "alpha beta gamma", layer="symbol", k=10, filters={"repo": "repoA"}
        )
        names = {h["qualname"] for h in scoped}
        assert "alpha" in names
        assert "beta" not in names and "gamma" not in names

        repos = ci.stats()["repos"]
        assert repos.get("repoA") == 1
        assert repos.get("repoB") == 1
        assert repos.get(".") == 1
    finally:
        ci.close()
