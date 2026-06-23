---
description: Save a durable code gotcha or flow note
argument-hint: <note-id> - <what to capture>
---

Capture durable knowledge about this codebase so it never has to be re-derived.
Use the `note_put` MCP tool (from the `code` server): choose a stable
kebab-case note id, write a concise markdown explanation of the gotcha,
invariant, or control/data flow, and set `covers` to the files it concerns.

Request: $ARGUMENTS
