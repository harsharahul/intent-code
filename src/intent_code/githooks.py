"""Install git hooks that keep the index fresh after history changes.

Any non-empty ``.intentdb/dirty`` triggers an incremental re-index on the next
query (see ``CodeIndex._lazy_reindex``), so each hook only needs to append a
line. Hooks are written with a managed marker and appended after any existing
shell hook, so re-running is safe and a user's own hooks are preserved. A
non-shell hook is left untouched (reported as skipped) rather than corrupted.

This is an optional accelerant for git repositories. Freshness does not depend
on it: agents are told to call ``code_index`` after edits, and Claude Code's
PostToolUse hook marks files dirty without git.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# History-changing events. Each marks the index stale; the next query re-indexes.
_HOOK_NAMES = ("post-commit", "post-merge", "post-checkout", "post-rewrite")
_MARKER = "# >>> intent-code freshness (managed) >>>"
_MARKER_END = "# <<< intent-code freshness (managed) <<<"

_BLOCK = (
    f"{_MARKER}\n"
    'root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0\n'
    'if [ -d "$root/.intentdb" ]; then echo "git-hook" >> "$root/.intentdb/dirty"; fi\n'
    f"{_MARKER_END}\n"
)


def _git(repo: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True
        )
    except (OSError, FileNotFoundError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _hooks_dir(repo: Path) -> Path | None:
    """Resolve the active hooks directory (honors core.hooksPath and worktrees)."""
    configured = _git(repo, "config", "--get", "core.hooksPath")
    if configured:
        p = Path(configured)
        return p if p.is_absolute() else repo / p
    rel = _git(repo, "rev-parse", "--git-path", "hooks")
    if rel is None:
        return None
    p = Path(rel)
    return p if p.is_absolute() else repo / p


def install_git_hooks(repo: str | Path) -> dict:
    """Install (idempotently) the freshness hooks. Returns a status dict."""
    repo = Path(repo).resolve()
    hooks = _hooks_dir(repo)
    if hooks is None:
        return {
            "ok": False,
            "reason": "not a git repository; freshness relies on code_index calls",
        }
    hooks.mkdir(parents=True, exist_ok=True)
    statuses: dict[str, str] = {}
    for name in _HOOK_NAMES:
        path = hooks / name
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            if _MARKER in text:
                statuses[name] = "already installed"
                continue
            first = text.splitlines()[0] if text.strip() else "#!/bin/sh"
            if not (first.startswith("#!") and "sh" in first):
                statuses[name] = "skipped (existing non-shell hook; add the block manually)"
                continue
            path.write_text(text.rstrip("\n") + "\n\n" + _BLOCK, encoding="utf-8")
            statuses[name] = "appended to existing hook"
        else:
            path.write_text("#!/bin/sh\n" + _BLOCK, encoding="utf-8")
            statuses[name] = "created"
        path.chmod(0o755)
    return {"ok": True, "hooks_dir": str(hooks), "hooks": statuses}
