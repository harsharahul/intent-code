"""The knowledge layer: durable, LLM-authored gotcha/flow notes (Karpathy-style).

On-disk markdown under the knowledge dir is the human-auditable source of truth;
each note is also ingested as a `layer=note` document so it shows up in intent
search. A catalog (`index.md`) and an append-only `log.md` are maintained. When a
note's covered files change, the note is flagged stale (its content is never
rewritten by the indexer - only its author rewrites it).
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from . import manifest as _manifest


def slugify(note_id: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", note_id.strip().lower()).strip("-")
    return s or "note"


def _title_of(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()
        if line:
            return line[:80]
    return fallback


class NotesStore:
    def __init__(self, idb, knowledge_dir: Path):
        self.idb = idb
        self.knowledge_dir = Path(knowledge_dir)
        self.notes_dir = self.knowledge_dir / "notes"

    def _doc_key(self, slug: str) -> str:
        return f"note::{slug}"

    def put(self, note_id: str, markdown: str, covers: list[str] | None = None) -> dict:
        slug = slugify(note_id)
        covers = covers or []
        m = _manifest.load_manifest(self.idb)
        files = m.get("files", {})
        covers_sha = {f: files[f]["sha"] for f in covers if f in files}

        self.notes_dir.mkdir(parents=True, exist_ok=True)
        path = self.notes_dir / f"{slug}.md"
        path.write_text(markdown, encoding="utf-8")

        self.idb.add(
            markdown,
            doc_key=self._doc_key(slug),
            metadata={
                "layer": "note",
                "slug": slug,
                "covers": covers,
                "covers_sha": covers_sha,
                "stale": False,
            },
        )
        self._append_log("note", slug)
        self.rewrite_index(m)
        return {"slug": slug, "path": str(path), "covers": covers}

    def get(self, note_id: str) -> dict | None:
        slug = slugify(note_id)
        rec = self.idb.get(self._doc_key(slug))
        if not rec:
            return None
        meta = rec.get("metadata") or {}
        return {
            "slug": slug,
            "markdown": rec.get("text", ""),
            "covers": meta.get("covers", []),
            "stale": bool(meta.get("stale", False)),
        }

    def remove(self, note_id: str) -> bool:
        slug = slugify(note_id)
        path = self.notes_dir / f"{slug}.md"
        if path.exists():
            path.unlink()
        return bool(self.idb.delete(self._doc_key(slug)))

    def slugs(self) -> list[str]:
        if not self.notes_dir.is_dir():
            return []
        return sorted(p.stem for p in self.notes_dir.glob("*.md"))

    def list_stale(self, manifest: dict) -> list[str]:
        current = {f: fe["sha"] for f, fe in manifest.get("files", {}).items()}
        stale: list[str] = []
        for slug in self.slugs():
            rec = self.idb.get(self._doc_key(slug))
            if not rec:
                continue
            covers_sha = (rec.get("metadata") or {}).get("covers_sha", {})
            for f, sha in covers_sha.items():
                if current.get(f) != sha:
                    stale.append(slug)
                    break
        return stale

    def flag_stale(self, slugs: list[str]) -> None:
        for slug in slugs:
            rec = self.idb.get(self._doc_key(slug))
            if not rec:
                continue
            meta = dict(rec.get("metadata") or {})
            if meta.get("stale"):
                continue
            meta["stale"] = True
            self.idb.add(rec.get("text", ""), doc_key=self._doc_key(slug), metadata=meta)

    def rewrite_index(self, manifest: dict | None = None) -> None:
        slugs = self.slugs()
        if not slugs:
            return
        lines = ["# Code knowledge notes", ""]
        for slug in slugs:
            rec = self.idb.get(self._doc_key(slug))
            meta = (rec.get("metadata") or {}) if rec else {}
            title = _title_of(rec.get("text", "") if rec else "", slug)
            covers = ", ".join(meta.get("covers", [])) or "(none)"
            flag = "  **[STALE]**" if meta.get("stale") else ""
            lines.append(f"- [{title}](notes/{slug}.md) (covers: {covers}){flag}")
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        (self.knowledge_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _append_log(self, event: str, detail: str) -> None:
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        line = f"## [{stamp}] {event} | {detail}\n"
        with (self.knowledge_dir / "log.md").open("a", encoding="utf-8") as fh:
            fh.write(line)
