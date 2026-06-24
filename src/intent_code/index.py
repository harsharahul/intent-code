"""CodeIndex: the orchestrator that turns a repo into an intent-db index.

Incremental by content hash (intent-db itself re-embeds on every add): unchanged
files are skipped entirely, and only changed symbol/chunk spans are re-embedded.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from intentdb import IntentDB

from . import cast_chunk
from . import manifest as _manifest
from . import parsing
from . import walk as _walk
from .embedder_auto import auto_embedder_spec, describe_auto
from .intents import register_code_intents

_RESERVED_LAYERS = {"manifest", "repomap"}


@dataclass
class IndexReport:
    added: int = 0
    changed: int = 0
    removed: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    stale_notes: list[str] = field(default_factory=list)
    embedder_spec: str = ""
    embedder_warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "added": self.added,
            "changed": self.changed,
            "removed": self.removed,
            "files_parsed": self.files_parsed,
            "files_skipped": self.files_skipped,
            "stale_notes": self.stale_notes,
            "embedder_spec": self.embedder_spec,
        }
        if self.embedder_warning:
            d["embedder_warning"] = self.embedder_warning
        return d


class CodeIndex:
    """Index and query one repository's code-knowledge store."""

    def __init__(
        self,
        repo_root: str | Path,
        embedder: str | None = None,
        db_path: str | Path | None = None,
        local_knowledge: bool = False,
        auto_refresh: bool = True,
        refresh_ttl: float = 2.0,
    ):
        self.root = Path(repo_root).resolve()
        self.idb_dir = self.root / ".intentdb"
        self.idb_dir.mkdir(parents=True, exist_ok=True)
        # Query-time freshness: poll the tree (stat only) at most once per TTL and
        # re-index what changed, so edits are picked up without a hook or git.
        env = os.environ.get("INTENT_CODE_AUTO_REFRESH")
        if env is not None:
            auto_refresh = env.strip().lower() not in ("0", "false", "no", "off")
        self._auto_refresh = auto_refresh
        self._refresh_ttl = refresh_ttl
        ttl_env = os.environ.get("INTENT_CODE_REFRESH_TTL")
        if ttl_env:
            try:
                self._refresh_ttl = float(ttl_env)
            except ValueError:
                pass
        self.db_path = Path(db_path) if db_path else self.idb_dir / "code.intentdb"
        # The committed, human-readable knowledge layer (MAP.md, notes, index.md).
        # Default: docs/codemap (travels with the repo); local: under .intentdb.
        self.local_knowledge = local_knowledge
        self.knowledge_dir = (
            self.idb_dir / "codemap" if local_knowledge else self.root / "docs" / "codemap"
        )
        first = not self.db_path.exists()
        self._embedder_warning: str | None = None
        if embedder:
            spec = embedder
        elif first:
            spec, self._embedder_warning = describe_auto()
        else:
            spec = None
        self.idb = IntentDB(str(self.db_path), embedder=spec)
        from .notes import NotesStore

        self.notes = NotesStore(self.idb, self.knowledge_dir)

    def _write_knowledge_file(self, name: str, content: str) -> None:
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        (self.knowledge_dir / name).write_text(content, encoding="utf-8")

    # -- lifecycle ------------------------------------------------------------

    @property
    def embedder_spec(self) -> str:
        return self.idb.embedder.spec

    def close(self) -> None:
        self.idb.close()

    def __enter__(self) -> "CodeIndex":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- indexing -------------------------------------------------------------

    def index(self, full: bool = False) -> IndexReport:
        old = _manifest.empty_manifest() if full else _manifest.load_manifest(self.idb)
        old_files: dict[str, Any] = old.get("files", {})
        new_files: dict[str, Any] = {}
        add_items: list[tuple[str, str, dict]] = []
        added = changed = parsed = skipped = 0
        to_remove: list[str] = []
        seen: set[str] = set()

        manifest_changed = full
        exclude = {self.idb_dir, self.knowledge_dir}
        for sf in _walk.iter_source_files(self.root, exclude_dirs=exclude):
            seen.add(sf.relpath)
            try:
                st = sf.path.stat()
            except OSError:
                continue
            prev = old_files.get(sf.relpath)
            # Stat gate: unchanged mtime+size means skip reading the file at all.
            if (
                prev is not None
                and not full
                and prev.get("mtime_ns") == st.st_mtime_ns
                and prev.get("size") == st.st_size
            ):
                new_files[sf.relpath] = prev
                skipped += 1
                continue
            try:
                data = sf.path.read_bytes()
            except OSError:
                continue
            if _walk.is_probably_binary(data):
                continue
            fsha = _manifest.file_sha(data)
            if prev and not full and prev.get("sha") == fsha:
                # Touched but content identical: carry forward, refresh the stat.
                new_files[sf.relpath] = {
                    **prev,
                    "mtime_ns": st.st_mtime_ns,
                    "size": st.st_size,
                }
                skipped += 1
                manifest_changed = True
                continue

            parsed += 1
            entry, items, a, c = self._index_file(sf, data, prev)
            entry["mtime_ns"] = st.st_mtime_ns
            entry["size"] = st.st_size
            new_files[sf.relpath] = entry
            add_items.extend(items)
            added += a
            changed += c
            manifest_changed = True
            if prev:
                to_remove.extend(
                    set(prev.get("symbols", {})) - set(entry.get("symbols", {}))
                )

        # Files that disappeared entirely.
        for relpath, prev in old_files.items():
            if relpath not in seen:
                to_remove.extend(prev.get("symbols", {}))
                manifest_changed = True

        removed = self._delete_keys(to_remove)
        if add_items:
            self.idb.add_many(add_items)

        # Register the intent pack once the corpus exists (lens fits real stats),
        # or on an explicit full rebuild.
        if full or not self.idb.list_intents():
            register_code_intents(self.idb)

        manifest = {
            "version": 1,
            "embedder": self.embedder_spec,
            "files": new_files,
        }
        # A clean poll (only stat checks, nothing changed) does no writes: skip the
        # graph/repo-map rebuild and the manifest save entirely.
        symbols_changed = bool(added or changed or removed)
        stale = self._post_index(manifest, old_files) if (full or symbols_changed) else []
        if manifest_changed or symbols_changed:
            _manifest.save_manifest(self.idb, manifest)

        # Surface the embedder fallback warning only once: a long-running MCP
        # server reuses one CodeIndex, so clear it after the first report.
        warning, self._embedder_warning = self._embedder_warning, None
        return IndexReport(
            added=added,
            changed=changed,
            removed=removed,
            files_parsed=parsed,
            files_skipped=skipped,
            stale_notes=stale,
            embedder_spec=self.embedder_spec,
            embedder_warning=warning,
        )

    def _index_file(self, sf, data: bytes, prev):
        text = data.decode("utf-8", "replace")
        prev_syms: dict[str, Any] = (prev or {}).get("symbols", {})
        items: list[tuple[str, str, dict]] = []
        new_syms: dict[str, Any] = {}
        added = changed = 0

        result = (
            parsing.extract(data, sf.lang, sf.relpath)
            if sf.kind == "code" and sf.lang
            else parsing.ParseResult(False, [], [])
        )

        if result.ok:
            for sym in result.symbols:
                key = f"{sf.relpath}::{sym.qualname}#sym"
                if key in new_syms:
                    key = f"{sf.relpath}::{sym.qualname}#L{sym.start_line}#sym"
                sh = _manifest.span_sha(sym.text)
                sig = next(
                    (ln.strip() for ln in sym.text.splitlines() if ln.strip()),
                    sym.qualname,
                )[:200]
                new_syms[key] = {
                    "sha": sh,
                    "name": sym.name,
                    "qualname": sym.qualname,
                    "kind": sym.kind,
                    "start_line": sym.start_line,
                    "end_line": sym.end_line,
                    "sig": sig,
                    "calls": sym.calls,
                }
                if prev_syms.get(key, {}).get("sha") == sh:
                    continue
                meta = {
                    "layer": "symbol",
                    "repo": sf.repo,
                    "file": sf.relpath,
                    "lang": sym.lang,
                    "kind": sym.kind,
                    "name": sym.name,
                    "qualname": sym.qualname,
                    "start_line": sym.start_line,
                    "end_line": sym.end_line,
                    "sha": sh,
                    "calls": sym.calls,
                }
                items.append((parsing.signature_card(sym), key, meta))
                changed += 1 if key in prev_syms else 0
                added += 0 if key in prev_syms else 1
            entry = {
                "sha": _manifest.file_sha(data),
                "lang": sf.lang,
                "kind": "code",
                "repo": sf.repo,
                "imports": result.imports,
                "symbols": new_syms,
            }
        else:
            for i, (chunk, sl, el) in enumerate(cast_chunk.chunks_with_lines(text)):
                key = f"{sf.relpath}#chunk{i}"
                sh = _manifest.span_sha(chunk)
                new_syms[key] = {"sha": sh, "start_line": sl, "end_line": el}
                if prev_syms.get(key, {}).get("sha") == sh:
                    continue
                meta = {
                    "layer": "chunk",
                    "repo": sf.repo,
                    "file": sf.relpath,
                    "lang": sf.lang or "text",
                    "kind": "chunk",
                    "start_line": sl,
                    "end_line": el,
                    "sha": sh,
                }
                items.append((chunk, key, meta))
                changed += 1 if key in prev_syms else 0
                added += 0 if key in prev_syms else 1
            entry = {
                "sha": _manifest.file_sha(data),
                "lang": sf.lang or "text",
                "kind": "chunk",
                "repo": sf.repo,
                "imports": [],
                "symbols": new_syms,
            }
        return entry, items, added, changed

    def _post_index(self, manifest: dict, old_files: dict) -> list[str]:
        """Rebuild the structural map and flag stale notes after an index pass."""
        from . import graph as _graph

        g = _graph.build_graph(manifest)
        ranks = _graph.pagerank(g)
        repomap_md = _graph.render_map(manifest, ranks)
        self.idb.add(
            repomap_md, doc_key=_manifest.REPOMAP_KEY, metadata={"layer": "repomap"}
        )
        self._write_knowledge_file("MAP.md", repomap_md)
        return self._refresh_notes(manifest, old_files)

    def _refresh_notes(self, manifest: dict, old_files: dict) -> list[str]:
        """Flag notes whose covered files changed, and refresh the catalog."""
        stale = self.notes.list_stale(manifest)
        self.notes.flag_stale(stale)
        self.notes.rewrite_index(manifest)
        return stale

    # -- notes ----------------------------------------------------------------

    def note_put(self, note_id: str, markdown: str, covers: list[str] | None = None) -> dict:
        return self.notes.put(note_id, markdown, covers)

    def note_get(self, note_id: str) -> dict | None:
        return self.notes.get(note_id)

    def note_list_stale(self) -> list[str]:
        return self.notes.list_stale(_manifest.load_manifest(self.idb))

    # -- querying -------------------------------------------------------------

    def _build_where(self, layer: str | None, filters: dict | None) -> Callable[[dict], bool]:
        filters = filters or {}

        def where(meta: dict) -> bool:
            lyr = meta.get("layer")
            if lyr in _RESERVED_LAYERS:
                return False
            if layer and layer != "any" and lyr != layer:
                return False
            for fkey, fval in filters.items():
                if meta.get(fkey) != fval:
                    return False
            return True

        return where

    # -- freshness ------------------------------------------------------------

    def _dirty_path(self) -> Path:
        return self.idb_dir / "dirty"

    def mark_dirty(self, relpaths: list[str]) -> None:
        with self._dirty_path().open("a", encoding="utf-8") as fh:
            for rel in relpaths:
                fh.write(rel + "\n")

    def _read_dirty(self) -> list[str]:
        p = self._dirty_path()
        if not p.exists():
            return []
        return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def _last_scan_path(self) -> Path:
        return self.idb_dir / "last_scan"

    def _scan_due(self) -> bool:
        """True if auto-refresh is on and the TTL has elapsed since the last poll."""
        if not self._auto_refresh:
            return False
        try:
            last = float(self._last_scan_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return True  # never scanned
        return (time.time() - last) >= self._refresh_ttl

    def _refresh(self) -> None:
        """Pick up edits before a query: re-index if files are queued dirty, or
        (auto-refresh) if the poll TTL has elapsed. The stat gate in index() makes
        a no-change poll nearly free. Serialized by a lockfile across processes."""
        if not (self._read_dirty() or self._scan_due()):
            return
        lock = self.idb_dir / "reindex.lock"
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError:
            return  # another process is already reindexing
        try:
            self.index()
            try:
                self._last_scan_path().write_text(str(time.time()), encoding="utf-8")
            except OSError:
                pass
            try:
                self._dirty_path().unlink()
            except FileNotFoundError:
                pass
        finally:
            try:
                os.unlink(str(lock))
            except OSError:
                pass

    def search(
        self,
        query: str,
        intent: str | None = None,
        k: int = 8,
        layer: str | None = "symbol",
        filters: dict | None = None,
        hybrid: bool = True,
        auto_intent: bool = True,
    ) -> list[dict]:
        self._refresh()
        where = self._build_where(layer, filters)
        results = self.idb.query(
            query,
            intent=intent,
            k=k,
            auto_intent=auto_intent,
            where=where,
            hybrid=hybrid,
            log=False,
        )
        return [self._format_hit(r) for r in results]

    @staticmethod
    def _format_hit(r) -> dict:
        m = r.metadata or {}
        sl, el = m.get("start_line"), m.get("end_line")
        location = m.get("file")
        if location and sl:
            location = f"{location}:{sl}-{el}" if el else f"{location}:{sl}"
        return {
            "doc_key": r.doc_key,
            "location": location,
            "qualname": m.get("qualname") or m.get("name"),
            "kind": m.get("kind"),
            "lang": m.get("lang"),
            "repo": m.get("repo"),
            "layer": m.get("layer"),
            "start_line": sl,
            "end_line": el,
            "score": round(float(r.score), 4),
            "intent": r.intent,
            "intent_inferred": r.intent_inferred,
            "snippet": r.text,
        }

    def map(self, budget_tokens: int = 2000, rebuild: bool = False) -> str:
        """Return the PageRank-ranked repo map (cached from the last index)."""
        if not rebuild:
            rec = self.idb.get(_manifest.REPOMAP_KEY)
            if rec and rec.get("text"):
                return rec["text"]
        from . import graph as _graph

        m = _manifest.load_manifest(self.idb)
        ranks = _graph.pagerank(_graph.build_graph(m))
        return _graph.render_map(m, ranks, budget_tokens)

    def neighbors(self, symbol: str, direction: str = "callees", k: int = 20) -> list[dict]:
        """Trace callers/callees/importers of a symbol (no file reads)."""
        from . import graph as _graph

        m = _manifest.load_manifest(self.idb)
        g = _graph.build_graph(m)
        return _graph.neighbors(g, symbol, direction=direction, k=k)

    # -- comprehension --------------------------------------------------------

    def _read_span(self, relpath: str, start_line: int, end_line: int) -> str:
        try:
            lines = (
                (self.root / relpath).read_text(encoding="utf-8", errors="replace").splitlines()
            )
        except OSError:
            return ""
        return "\n".join(lines[max(0, start_line - 1) : end_line])

    def read(self, symbol: str) -> dict | None:
        """Return a symbol's full source span (no truncation, from the index)."""
        self._refresh()  # pick up pending edits so spans are fresh
        from . import graph as _graph

        g = _graph.build_graph(_manifest.load_manifest(self.idb))
        keys = _graph._resolve(g, symbol)
        if not keys:
            return None
        sd = g.symbols[keys[0]]
        return {
            "doc_key": keys[0],
            "qualname": sd["qualname"],
            "file": sd["file"],
            "kind": sd["kind"],
            "start_line": sd["start_line"],
            "end_line": sd["end_line"],
            "matches": len(keys),
            "code": self._read_span(sd["file"], sd["start_line"], sd["end_line"]),
        }

    def flow(self, symbol: str) -> dict | None:
        """Return the ordered call sequence inside a symbol's body."""
        self._refresh()  # pick up pending edits so spans are fresh
        from . import graph as _graph

        g = _graph.build_graph(_manifest.load_manifest(self.idb))
        keys = _graph._resolve(g, symbol)
        if not keys:
            return None
        sd = g.symbols[keys[0]]
        steps = []
        for name in sd.get("calls", []):
            targets = sorted(g.name_index.get(name, ()))
            loc = None
            if targets:
                t = g.symbols[targets[0]]
                loc = f"{t['file']}:{t['start_line']}"
            steps.append(
                {"call": name, "target": targets[0] if targets else None, "location": loc}
            )
        return {"symbol": sd["qualname"], "file": sd["file"], "steps": steps}

    def context(self, symbol: str, depth: int = 2, budget_tokens: int = 4000) -> dict | None:
        """Assemble the full bodies of a symbol and what it calls, in call order."""
        self._refresh()  # pick up pending edits so spans are fresh
        from . import graph as _graph

        g = _graph.build_graph(_manifest.load_manifest(self.idb))
        keys = _graph._resolve(g, symbol)
        if not keys:
            return None
        start = keys[0]
        order: list[str] = []
        seen: set[str] = set()
        frontier: list[tuple[str, int]] = [(start, 0)]
        while frontier:
            key, d = frontier.pop(0)
            if key in seen or key not in g.symbols:
                continue
            seen.add(key)
            order.append(key)
            if d >= depth:
                continue
            for name in g.symbols[key].get("calls", []):  # ordered
                for tgt in sorted(g.name_index.get(name, ())):
                    if tgt not in seen:
                        frontier.append((tgt, d + 1))
        budget = max(budget_tokens, 200) * 4
        blocks: list[str] = []
        included: list[str] = []
        used = 0
        for key in order:
            sd = g.symbols[key]
            code = self._read_span(sd["file"], sd["start_line"], sd["end_line"])
            block = (
                f"── {sd['file']}:{sd['start_line']}-{sd['end_line']}  "
                f"{sd['qualname']} ({sd['kind']}) ──\n{code}"
            )
            if used + len(block) > budget and blocks:
                blocks.append(f"… ({len(order) - len(included)} more omitted; raise budget)")
                break
            blocks.append(block)
            used += len(block)
            included.append(key)
        return {"root": start, "symbols": included, "text": "\n\n".join(blocks)}

    def _delete_keys(self, keys: list[str]) -> int:
        """Delete many doc_keys, using intent-db's batch API when available."""
        keys = list(keys)
        if not keys:
            return 0
        delete_many = getattr(self.idb, "delete_many", None)
        if delete_many is not None:
            return len(delete_many(keys))
        return sum(1 for k in keys if self.idb.delete(k))

    def feedback(
        self, query: str, doc_key: str, useful: bool = True, intent: str | None = None
    ) -> None:
        self.idb.record_feedback(query, doc_key, useful=useful, intent=intent)

    def stats(self) -> dict:
        s = dict(self.idb.stats())
        manifest = _manifest.load_manifest(self.idb)
        files = manifest.get("files", {})
        s["files"] = len(files)
        repos: dict[str, int] = {}
        for entry in files.values():
            key = entry.get("repo", ".")
            repos[key] = repos.get(key, 0) + 1
        s["repos"] = dict(sorted(repos.items()))
        s["embedder"] = self.embedder_spec
        return s
