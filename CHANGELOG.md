# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.2.3] - 2026-06-24

### Added
- Automatic query-time freshness: a search now detects edited files and re-indexes
  what changed with no git and no editor hook required. A stat gate (mtime and size
  recorded per file) means unchanged files are never read, so the check is cheap,
  and it runs at most once per `refresh_ttl` (default 2s). On by default; disable
  with `INTENT_CODE_AUTO_REFRESH=0` or tune with `INTENT_CODE_REFRESH_TTL`.

### Changed
- Incremental indexing skips reading files whose mtime and size are unchanged
  (previously every file was read and hashed on every pass), and a poll that finds
  no changes does no writes at all (no graph or repo-map rebuild, no manifest save).

## [0.2.2] - 2026-06-24

### Added
- Repo-scoped search for indexes that span several repositories. Each symbol and
  chunk is tagged with its enclosing git repository (the nearest ancestor holding
  `.git`; deepest wins for nested repos and submodules), every search result
  carries its `repo`, and a search can be scoped with `search --repo <name>` on
  the CLI or `filters={"repo": "<name>"}` over MCP. `stats` lists the
  repositories in the index with their file counts.

### Notes
- Run `index --full` once to backfill repo tags on an index built before 0.2.2;
  the tag is location-derived, so unchanged files are not otherwise re-touched.

## [0.2.1] - 2026-06-24

### Added
- `intent-code init --agent claude|copilot|gemini|all` wires the index into each
  agent's native config: an MCP server entry (`.mcp.json`, `.vscode/mcp.json`, or
  `.gemini/settings.json`) and the protocol written into the agent's instruction
  file (`CLAUDE.md`, `.github/copilot-instructions.md`, or `GEMINI.md`). The flag
  is repeatable and defaults to `claude`. Writes use an idempotent managed block
  and JSON key-merge, so re-running never clobbers existing content.
- `intent-code install-hooks` installs git hooks (post-commit, post-merge,
  post-checkout, post-rewrite) that flag the index stale, so the next query
  re-indexes incrementally. Editor-agnostic: it appends to an existing shell hook
  and leaves a non-shell hook untouched.

### Changed
- The indexer no longer indexes the agent instruction files it generates
  (`CLAUDE.md`, `GEMINI.md`, `AGENTS.md`, `.github/copilot-instructions.md`,
  `*.prompt.md`, `.mcp.json`, and the `.gemini/` directory), avoiding a re-index
  feedback loop.

## [0.2.0] - 2026-06-24

### Added
- Comprehension tools that return code, not just locations:
  - `code_read` (CLI `read`): a symbol's full source span, untruncated, resolved
    by doc_key, qualname, or name.
  - `code_context` (CLI `context`): the full bodies of a symbol and what it calls,
    in call order, packed to a token budget, so an agent can follow a flow end to
    end in a single call.
  - `code_flow` (CLI `flow`): the ordered call sequence inside a function, each
    call with its resolved target location.
- `--local` flag on the `note` subcommands, so notes use the same `.intentdb`
  knowledge dir as an index built with `--local` instead of writing to the
  committed `docs/codemap`.
- A clear warning when no embedder is configured and Ollama is unreachable, so it
  is obvious that search has fallen back to the weaker lexical hashing embedder.

### Changed
- Call edges now preserve source order (previously sorted alphabetically), so
  `flow` and `context` reflect the real execution sequence.
- Re-indexing removes stale symbols in a single batched delete (using intent-db's
  `delete_many` when present) instead of rebuilding the matrix once per key, which
  speeds up large refactors and file deletions.
- Requires `intent-vector-db>=0.2.3` for the batched delete and add paths.

## [0.1.1] - 2026-06-22

### Added
- Intent-aware code index built on intent-db: a `symbol`, `chunk`, and `note`
  layer in a single local index per repository.
- Incremental indexing: content-hash change detection re-embeds only the symbols
  that changed, and removes symbols for deleted files.
- Tree-sitter symbol extraction (functions, classes, methods) with qualnames,
  line spans, and import/call edges, across Python, JavaScript, TypeScript, Go,
  Rust, Java, C, C++, Ruby, and C#. Text and grammar-less files fall back to
  AST-aware chunking.
- Structural map: a symbol dependency graph with PageRank ranking, a
  token-budgeted repo map (`MAP.md`), and `neighbors` tracing of callers,
  callees, and importers.
- Knowledge layer: durable, human-authored gotcha and flow notes, with a catalog
  and an append-only log, and automatic stale-flagging when covered files change.
- Default code-intent pack: `debugging`, `extending`, `reviewing`, `onboarding`,
  with a feedback loop that learns per-intent ranking.
- Auto-detecting embedder (local Ollama if reachable, else a zero-dependency
  hashing embedder) with BM25 hybrid search.
- Consumption surfaces: an MCP stdio server, committed `docs/codemap/` markdown,
  and a JSON CLI.
- Claude Code plugin (MCP server, `/code-index` and `/code-note` commands, and an
  optional PostToolUse freshness hook).
- Token-spend benchmark comparing index-assisted retrieval to naive file reads.

Designed by Harsha Rahul
