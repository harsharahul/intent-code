"""Chunking for the `chunk` layer.

Used for text/config files and for code files with no available grammar. Leaf
splitting reuses intent-db's `chunking.chunk_text` (paragraph/sentence aware).
Approximate line spans are recovered so chunk hits still point at a location.

(AST-child packing for oversized symbols is a future refinement; symbols are the
primary unit and are extracted whole by `parsing.extract`.)
"""

from __future__ import annotations

from intentdb.chunking import chunk_text

DEFAULT_MAX_CHARS = 1500
DEFAULT_OVERLAP = 150


def chunks_with_lines(
    text: str, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP
) -> list[tuple[str, int, int]]:
    """Return [(chunk_text, start_line, end_line), ...]."""
    if not text.strip():
        return []
    pieces = chunk_text(text, max_chars=max_chars, overlap=overlap)
    out: list[tuple[str, int, int]] = []
    cursor = 0
    for piece in pieces:
        probe = piece[:60]
        idx = text.find(probe, cursor) if probe else -1
        if idx < 0:
            idx = text.find(piece, cursor)
        if idx < 0:
            idx = cursor
        start_line = text.count("\n", 0, idx) + 1
        end_line = start_line + piece.count("\n")
        out.append((piece, start_line, end_line))
        cursor = idx + max(1, len(piece) - overlap)
    return out
