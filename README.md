# intent-code

[![PyPI](https://img.shields.io/pypi/v/intent-code)](https://pypi.org/project/intent-code/)
[![CI](https://github.com/harsharahul/intent-code/actions/workflows/ci.yml/badge.svg)](https://github.com/harsharahul/intent-code/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/intent-code/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An intent-aware code-knowledge index for LLM agents, built on
[intent-db](https://github.com/harsharahul/intent-db).

Index a repository once, then query it **by intent** so an agent reads only what
it needs instead of re-reading the whole repo every session. The same search
returns different results for the agent's current phase: `debugging`,
`extending`, `reviewing`, or `onboarding`.

## Why

LLM coding agents re-read files every session because they have no durable,
queryable understanding of a codebase. intent-code builds that understanding
once and keeps it fresh incrementally, so the expensive "read and synthesize"
happens once per change and is reused across sessions.

It combines three established ideas:

- A durable, LLM-maintained **knowledge layer** of gotcha and flow notes, in the
  spirit of Karpathy's LLM Wiki.
- A tree-sitter **symbol and dependency map** ranked by PageRank, in the spirit
  of Aider's repo map.
- **Incremental indexing**: only changed code is re-embedded, in the spirit of
  Cursor's Merkle indexing.

The retrieval engine is intent-db: documents are embedded once and a per-intent
lens re-ranks results at query time, with a feedback loop that learns per-intent
ranking from what the agent actually used.

## How an agent uses it

One index, three ways to consume it (the same data, regenerated on every index):

1. **MCP (primary)** for Claude Code and any tool-capable agent: `code_map`,
   `code_search`, `code_read`, `code_context`, `code_flow`, `code_neighbors`,
   `note_put` / `note_get` / `note_list_stale`, `code_feedback`, `code_index`.
   `code_search` finds *where* something is; `code_read` / `code_context` /
   `code_flow` answer *how it works* by returning full bodies and the call
   sequence, so the agent stops re-reading whole files.
2. **Committed markdown** under `docs/codemap/` (`MAP.md`, `index.md`,
   `notes/`): readable by any LLM or human, even without MCP, straight from a
   `git clone`.
3. **CLI `--json`** for any agent that can run a shell command.

## Install

```bash
uv tool install intent-code          # or: pipx install intent-code
```

## Quickstart

```bash
cd your-repo
intent-code init .                   # builds the index, writes .mcp.json + protocol
# restart Claude Code -> the "code" MCP tools are available
```

Or use it directly:

```bash
intent-code index .
intent-code search "where is the retry handled" --intent debugging
intent-code map
intent-code neighbors your.module.Class.method --direction callers

# understand how code works, not just where it is
intent-code read your.module.handle_request           # full body, untruncated
intent-code context your.module.handle_request        # it + its callees, in call order
intent-code flow your.module.handle_request           # the ordered call sequence
```

### Claude Code plugin

```
/plugin marketplace add harsharahul/intent-code
/plugin install intent-code
```

The plugin wires the MCP server, the `/code-index` and `/code-note` commands,
and an optional PostToolUse freshness hook.

### Use with GitHub Copilot or Gemini CLI

The same MCP server works with any agent that speaks MCP. `init` writes each
agent's native config and the protocol into its instruction file:

```bash
intent-code init . --agent copilot   # .vscode/mcp.json + .github/copilot-instructions.md
intent-code init . --agent gemini    # .gemini/settings.json + GEMINI.md
intent-code init . --agent all        # claude + copilot + gemini at once
```

Writes are idempotent: instruction files get a marked managed block and JSON
configs are key-merged, so re-running never clobbers your own content. The files
`init` generates are excluded from the index, so the protocol is never indexed
back into itself.

### Keeping the index fresh

Freshness does not require git. Re-indexing is incremental (only changed files
re-parse), and it stays current several ways:

- Automatic (any agent, no git, no hook): a search polls the tree at query time
  and re-indexes what changed. A stat gate skips unchanged files, so the check is
  cheap, and it runs at most once per interval (default 2s). On by default;
  `INTENT_CODE_AUTO_REFRESH=0` disables it and `INTENT_CODE_REFRESH_TTL` tunes the
  interval (raise it for very large monorepos).
- Claude Code: the plugin's PostToolUse hook marks edited files dirty for an
  immediate pickup.
- Git repos: `intent-code install-hooks .` adds commit/merge/checkout hooks that
  flag the index stale.
- Any agent: the protocol also tells it to call `code_index` after edits.

### Indexing multiple repositories

One index lives at the path you point `init`/`serve-mcp` at, and the walk skips
every nested `.git/` at any depth. Point at a single repo for that repo's index,
or at a parent folder of several repos for one combined, cross-repo index.

In a combined index every result is tagged with its repository, and you can
scope a search to one:

```bash
intent-code stats .                          # lists the repos and file counts
intent-code search "retry logic" --repo api  # only hits from the 'api' repo
```

Over MCP, pass `filters={"repo": "api"}` to `code_search`. The tag is the path of
the nearest enclosing `.git` (deepest wins for nested repos and submodules), and
`.` is the index root. Run `index --full` once to backfill tags on an index built
before 0.2.2. Git hooks are per-repository, so the combined-parent case relies on
the `code_index` path for freshness rather than hooks.

## How it works

The index is a single intent-db SQLite file under `.intentdb/` (add it to your
`.gitignore`). Documents are tagged by layer:

- `symbol`: a signature card per function/class/method (tree-sitter), with line
  span, content hash, and import/call edges.
- `chunk`: AST-aware chunks for text or grammar-less files.
- `note`: durable, human-authored gotcha and flow articles.

A dependency graph and PageRank ranking are derived from the symbol edges to
produce the repo map and `neighbors` tracing. Re-indexing hashes each file and
re-embeds only the symbols whose content changed.

The default embedder auto-detects: a local Ollama model (`nomic-embed-text`) if
reachable, otherwise the zero-dependency hashing embedder, with BM25 hybrid
search always on for exact symbol matches.

## Benchmark

A token-spend benchmark ships in `intent_code.eval`. On the intent-db codebase,
answering a five-question set used about 97% fewer input tokens than reading
whole files to reach the answer (roughly 7.8k versus 227k), with the
zero-dependency hashing embedder. A local embedding model improves which
questions land in the top results.

```bash
python -m intent_code.eval.run /path/to/repo
```

## Security and supply chain

Minimal runtime dependencies, official tree-sitter grammars, version bounds plus
a hash-pinned lockfile, dependency auditing in CI, SHA-pinned GitHub Actions, and
PyPI trusted publishing. See [SECURITY.md](SECURITY.md).

## License

MIT
