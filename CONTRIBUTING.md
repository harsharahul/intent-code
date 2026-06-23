# Contributing

Thanks for your interest in improving intent-code.

## Development setup

intent-code depends on [intent-db](https://github.com/harsharahul/intent-db).
For local development, install intent-db from a sibling checkout, then this
package with its extras:

```bash
git clone https://github.com/harsharahul/intent-db
git clone https://github.com/harsharahul/intent-code
cd intent-code
uv pip install -e ../intent-db
uv pip install -e ".[treesitter,dev]"
```

Or, with uv's project workflow (uses the path source in `pyproject.toml`):

```bash
uv sync --extra treesitter --extra dev
```

## Tests

```bash
uv run pytest -q
```

The test suite uses the zero-dependency hashing embedder, so it runs fully
offline with no Ollama or model downloads. New behaviour should land with tests.

## Style

- Python 3.10+. Use type hints and keep modules focused.
- Prefer reusing intent-db primitives over re-implementing them.
- Keep dependencies minimal; heavy or optional functionality goes behind an
  extra.
- Run `uv run pip-audit` before opening a pull request.

## Pull requests

Open a pull request against `main`. CI runs the test suite across Python
3.10 to 3.13 and audits dependencies; please make sure it is green.
