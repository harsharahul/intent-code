"""The agent protocol: how an LLM should use the code index.

Shipped as a constant so both `intent-code init` and the Claude Code plugin
write the same guidance. Mirrors intent-db's AGENT_MEMORY.md style.
"""

from __future__ import annotations

PROTOCOL_MD = """\
# Code index protocol (intent-code)

This repo has an intent-aware code-knowledge index. Query it instead of
re-reading files; read only the spans it points you to. This saves tokens and
gives you the gotchas other tools miss.

## At the start of a task
- Call `code_map` (or read `docs/codemap/MAP.md`) for a ranked overview of the
  most important symbols. Do this instead of globbing/listing the tree.

## While working — pick the intent for your current phase
- `code_search(query, intent="debugging")` — bugs, error paths, gotchas.
- `code_search(query, intent="extending")` — interfaces, signatures, call sites.
- `code_search(query, intent="reviewing")` — invariants, tests, conventions.
- `code_search(query, intent="onboarding")` — high-level flow, entry points.
Each hit has a `location` (file:line) and a signature card. Open ONLY those
spans. Use `code_neighbors(symbol, direction="callers")` to find blast radius.

## When you learn something non-obvious
- Save it with `note_put(note_id, markdown, covers=[files])`: a gotcha, an
  invariant, a control/data-flow explanation. It persists across sessions so it
  is never re-derived. Check `note_list_stale` and refresh notes whose covered
  files changed.

## After using a result
- Call `code_feedback(query, doc_key, useful=true, intent=...)` so per-intent
  ranking improves over time.

## Keeping the index fresh
- `code_index` re-embeds only changed symbols (cheap). If the optional
  PostToolUse hook is installed, edits are picked up automatically on the next
  search.
"""
