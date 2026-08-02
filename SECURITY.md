# Security Policy

## Reporting a vulnerability

Please report security issues privately through GitHub's "Report a vulnerability"
feature on this repository's Security tab, rather than opening a public issue.
You will receive an acknowledgement, and a fix or mitigation will be coordinated
before any public disclosure.

## Supported versions

The latest released version receives security fixes.

## Supply-chain practices

- Few runtime dependencies, all from the official tree-sitter organization for
  the grammars.
- Dependency versions are bounded in `pyproject.toml`, and CI installs from those
  bounds. The `uv.lock` used for local development is not published, because it
  resolves the intent-db library from a working copy rather than from PyPI.
- CI audits dependencies with `pip-audit` on every push and pull request.
- GitHub Actions are pinned to commit SHAs, and workflows run with least-
  privilege permissions.
- Releases publish to PyPI via trusted publishing (OIDC), with no long-lived API
  tokens stored in the repository.
- Dependabot proposes grouped dependency and action updates weekly.

## Data handling

intent-code is local-first. Indexing, embeddings, and the knowledge layer stay on
your machine; no source code is sent to any external service. If the optional
Ollama embedder is enabled, embeddings are computed by your local Ollama server.
