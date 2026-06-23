"""Content-hash manifest: the bookkeeping that makes re-indexing incremental.

intent-db re-embeds on every `add`, so change detection lives here. The manifest
records, per file, its content hash and the per-symbol/chunk span hashes, so a
re-index can skip unchanged files entirely and re-embed only changed spans. It
is stored as a single reserved intent-db document (`__manifest__`, excluded from
all searches).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

MANIFEST_KEY = "__manifest__"
REPOMAP_KEY = "__repomap__"
RESERVED_PREFIX = "__"


def short_hash(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=16).hexdigest()


def file_sha(data: bytes) -> str:
    return short_hash(data)


def span_sha(text: str) -> str:
    return short_hash(text.encode("utf-8", "replace"))


def empty_manifest() -> dict[str, Any]:
    return {"version": 1, "embedder": None, "files": {}}


def load_manifest(idb) -> dict[str, Any]:
    try:
        rec = idb.get(MANIFEST_KEY)
    except Exception:
        rec = None
    if not rec:
        return empty_manifest()
    text = rec.get("text") if isinstance(rec, dict) else None
    if not text:
        return empty_manifest()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return empty_manifest()
    data.setdefault("files", {})
    return data


def save_manifest(idb, manifest: dict[str, Any]) -> None:
    idb.add(
        json.dumps(manifest, separators=(",", ":")),
        doc_key=MANIFEST_KEY,
        metadata={"layer": "manifest"},
    )
