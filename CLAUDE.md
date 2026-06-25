# intent-code: guide for AI coding agents

intent-code is an intent-aware code index for LLM agents, built on the intent-db
library (PyPI `intent-vector-db`, import `intentdb`). It indexes a repository so an
agent can query distilled answers plus precise `file:line` pointers instead of
re-reading files. See `README.md` for usage and `docs/` for the design.

## Living context doc (read it, and keep it current)

Maintainers keep `HANDOFF.md` (gitignored, local) as the full engineering
context: the architecture deep-dive, module map, release runbook, environment
notes, and lessons learned. Treat it as a living document:

- If `HANDOFF.md` is present, read it before starting substantive work.
- After you ship a change, update it: refresh the CURRENT STATE section, and
  revise the architecture, module map, version history, or gotchas sections
  whenever they change. The goal is that the next session starts fully informed.

## Conventions

- Do not use em-dashes or en-dashes in code, comments, docs, or commit messages.
  Use `:`, `;`, `,`, `.`, or parentheses. Scrub before committing:
  `git grep -nP "[\x{2013}\x{2014}]" -- '*.py' '*.md'`.
- Conventional commit subjects: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`.
- Branch off `main` and open a pull request; `main` is protected and requires
  passing CI.
- Anything generated into the working tree (agent configs, `docs/codemap/`,
  `.intentdb/`) must be excluded from indexing. See `walk.py`
  `ALWAYS_IGNORE_DIRS` / `ALWAYS_IGNORE_FILES`.

## Build and test

- Tests run offline with the hashing embedder: `uv run --no-sync pytest -q`.
- Run the CLI against this repo: `uv run --no-sync intent-code <command> .`.
- Releases publish to PyPI from a GitHub Release via trusted publishing; the git
  tag must equal `v` plus the version in `pyproject.toml`.
