"""Enumerate the source files of a repository.

Honors `.gitignore` (root and nested) via `pathspec`, always skips heavy/VCS
directories, and skips binary or oversized files. Classifies each file as
`code` (a tree-sitter grammar exists) or `text` (indexed as chunks).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pathspec

# Extension -> tree-sitter language name (must match parsing._LOADERS keys).
LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".rb": "ruby",
    ".cs": "c_sharp",
}

# Non-code files still worth indexing as chunks.
TEXT_EXTS: set[str] = {
    ".md",
    ".markdown",
    ".rst",
    ".txt",
    ".toml",
    ".cfg",
    ".ini",
    ".yaml",
    ".yml",
    ".json",
}

# Directories we never descend into (independent of .gitignore).
ALWAYS_IGNORE_DIRS: set[str] = {
    ".git",
    ".intentdb",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "dist",
    "build",
    ".idea",
    ".vscode",
    ".eggs",
}

MAX_BYTES = 1_500_000  # skip files larger than ~1.5 MB


@dataclass(frozen=True)
class SourceFile:
    path: Path
    relpath: str  # posix, relative to repo root
    lang: str | None  # tree-sitter language name, or None for text files
    kind: str  # "code" or "text"


def detect_lang(path: Path) -> str | None:
    return LANG_BY_EXT.get(path.suffix.lower())


def _classify(path: Path) -> tuple[str | None, str] | None:
    lang = detect_lang(path)
    if lang is not None:
        return lang, "code"
    if path.suffix.lower() in TEXT_EXTS:
        return None, "text"
    return None


def _ignored(relpath_posix: str, specs: list[tuple[str, pathspec.PathSpec]]) -> bool:
    """True if any applicable .gitignore spec matches the path.

    Each spec is anchored at the directory of its source .gitignore (``base``);
    a spec only applies to paths at or below its base, and matching is done on
    the path made relative to that base (correct nested-gitignore semantics).
    """
    for base, spec in specs:
        if base in ("", "."):
            sub = relpath_posix
        elif relpath_posix == base or relpath_posix.startswith(base + "/"):
            sub = relpath_posix[len(base) + 1 :]
        else:
            continue
        if sub and spec.match_file(sub):
            return True
    return False


def _read_gitignore(path: Path) -> pathspec.PathSpec | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return pathspec.GitIgnoreSpec.from_lines(lines)


def is_probably_binary(data: bytes) -> bool:
    return b"\x00" in data[:8000]


def iter_source_files(
    root: str | Path, exclude_dirs: set[Path] | None = None
) -> Iterator[SourceFile]:
    """Yield indexable source files under ``root`` in a deterministic order.

    ``exclude_dirs`` lists absolute directories to skip entirely (e.g. the
    index's own generated knowledge dir, to avoid re-indexing its output).
    """
    root = Path(root).resolve()
    excluded = {Path(p).resolve() for p in (exclude_dirs or set())}
    specs: list[tuple[str, pathspec.PathSpec]] = []

    for dirpath, dirnames, filenames in os.walk(root):
        if Path(dirpath).resolve() in excluded:
            dirnames[:] = []
            continue
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir

        gi = Path(dirpath) / ".gitignore"
        if gi.is_file():
            spec = _read_gitignore(gi)
            if spec is not None:
                specs.append((rel_dir, spec))

        # Prune directories in place (so os.walk does not descend).
        kept = []
        for d in sorted(dirnames):
            if d in ALWAYS_IGNORE_DIRS:
                continue
            rel = f"{rel_dir}/{d}" if rel_dir else d
            if _ignored(rel + "/", specs):
                continue
            kept.append(d)
        dirnames[:] = kept

        for fname in sorted(filenames):
            rel = f"{rel_dir}/{fname}" if rel_dir else fname
            if _ignored(rel, specs):
                continue
            fpath = Path(dirpath) / fname
            classified = _classify(fpath)
            if classified is None:
                continue
            try:
                if fpath.stat().st_size > MAX_BYTES:
                    continue
            except OSError:
                continue
            lang, kind = classified
            yield SourceFile(path=fpath, relpath=rel, lang=lang, kind=kind)
