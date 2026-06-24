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

## To LOCATE code: pick the intent for your current phase
- `code_search(query, intent="debugging")`: bugs, error paths, gotchas.
- `code_search(query, intent="extending")`: interfaces, signatures, call sites.
- `code_search(query, intent="reviewing")`: invariants, tests, conventions.
- `code_search(query, intent="onboarding")`: high-level flow, entry points.
Each hit has a `location` (file:line) and a signature card.

## To UNDERSTAND how code works (do NOT re-read whole files)
- `code_read(symbol)`: the symbol's FULL body, untruncated, by name/qualname.
- `code_context(symbol)`: the symbol AND what it calls, full bodies in call
  order, packed to a budget. Use this for "how does X work end to end" instead
  of opening each callee yourself.
- `code_flow(symbol)`: just the ordered call sequence (control flow / ordering)
  with each target's location, without reading the body.
- `code_neighbors(symbol, direction="callers")`: blast radius before a change.
`symbol` accepts a doc_key, a qualname (`module.Class.method`), or a bare name.

## Notes are a cache: check them first, write them after
- For a how/why question, FIRST `code_search(query, layer="note")` and read any
  hit: a prior session may have already worked it out, saving you the dive.
- After you understand a non-obvious subsystem (a flow, an invariant, a gotcha,
  why something is ordered the way it is), `note_put(note_id, markdown,
  covers=[files])` so the next session reads the note instead of re-deriving it.
- Check `note_list_stale` and refresh notes whose covered files changed.

## After using a result
- Call `code_feedback(query, doc_key, useful=true, intent=...)` so per-intent
  ranking improves over time.

## Keeping the index fresh
- `code_index` re-embeds only changed symbols (cheap). If the optional
  PostToolUse hook is installed, edits are picked up automatically on the next
  search.
"""
