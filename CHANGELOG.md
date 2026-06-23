# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.2] - Unreleased

### Added
- `--local` flag on the `note` subcommands, so notes use the same `.intentdb`
  knowledge dir as an index built with `--local` instead of writing to the
  committed `docs/codemap`.

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
