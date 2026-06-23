#!/usr/bin/env python3
"""Zero-dependency PostToolUse hook: mark an edited file dirty for lazy re-index.

Bundled in the plugin so it runs with only the standard library (no install of
the intent-code package needed). Reads the hook JSON from stdin, finds the
nearest ancestor containing a `.intentdb/` directory, and appends the edited
file's repo-relative path to `.intentdb/dirty`. Always exits 0 so it can never
block the agent. Mirrors `intent_code.hook`.
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


def main() -> int:
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
    try:
        with (root / ".intentdb" / "dirty").open("a", encoding="utf-8") as fh:
            fh.write(rel + "\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
