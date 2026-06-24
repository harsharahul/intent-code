from __future__ import annotations

import os
import subprocess
from pathlib import Path

from intent_code.githooks import _MARKER, install_git_hooks


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def test_non_git_repo_reports_not_ok(tmp_path):
    result = install_git_hooks(tmp_path)
    assert result["ok"] is False
    assert "not a git repository" in result["reason"]


def test_creates_executable_hooks_and_is_idempotent(tmp_path):
    _git_init(tmp_path)
    result = install_git_hooks(tmp_path)
    assert result["ok"] is True

    post_commit = Path(result["hooks_dir"]) / "post-commit"
    assert post_commit.exists()
    assert _MARKER in post_commit.read_text()
    assert os.access(post_commit, os.X_OK)

    again = install_git_hooks(tmp_path)
    assert again["hooks"]["post-commit"] == "already installed"
    assert post_commit.read_text().count(_MARKER) == 1  # not duplicated


def test_appends_to_existing_shell_hook(tmp_path):
    _git_init(tmp_path)
    post_commit = tmp_path / ".git" / "hooks" / "post-commit"
    post_commit.write_text("#!/bin/sh\necho existing-hook\n", encoding="utf-8")

    result = install_git_hooks(tmp_path)
    assert result["hooks"]["post-commit"] == "appended to existing hook"
    text = post_commit.read_text()
    assert "echo existing-hook" in text  # user's hook preserved
    assert _MARKER in text


def test_skips_non_shell_hook(tmp_path):
    _git_init(tmp_path)
    post_merge = tmp_path / ".git" / "hooks" / "post-merge"
    post_merge.write_text("#!/usr/bin/env python\nprint('hi')\n", encoding="utf-8")

    result = install_git_hooks(tmp_path)
    assert "skipped" in result["hooks"]["post-merge"]
    assert "intent-code" not in post_merge.read_text()  # left untouched
