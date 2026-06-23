"""Claude Code PostToolUse hook: a fast dirty-marker (never a synchronous embed).

Reads the hook JSON from stdin, finds the edited file, and appends its repo path
to ``.intentdb/dirty``. The next `code_search`/`code_index` lazily re-indexes the
dirty files. Always exits 0 so it can never block the agent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _find_index_root(path: Path) -> Path | None:
    for parent in [path] + list(path.parents):
        if (parent / ".intentdb").is_dir():
            return parent
    return None


def _append_dirty(root: Path, relpath: str) -> None:
    dirty = root / ".intentdb" / "dirty"
    try:
        with dirty.open("a", encoding="utf-8") as fh:
            fh.write(relpath + "\n")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    tool_input = payload.get("tool_input") or {}
    fp = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not fp:
        return 0
    try:
        path = Path(fp).resolve()
    except Exception:
        return 0
    root = _find_index_root(path)
    if root is None:
        return 0
    try:
        rel = path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return 0
    _append_dirty(root, rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
