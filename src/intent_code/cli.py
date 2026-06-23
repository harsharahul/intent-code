"""Command-line interface for intent-code.

Examples::

    intent-code index .
    intent-code search . "where is the retry handled" --intent debugging
    intent-code map .
    intent-code neighbors . intentdb.db.IntentDB.query --direction callers
    intent-code serve-mcp .
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .index import CodeIndex
from .protocol import PROTOCOL_MD

_MCP_ENTRY = {"command": "intent-code", "args": ["serve-mcp", "."]}


def _open(args) -> CodeIndex:
    return CodeIndex(
        args.repo,
        embedder=getattr(args, "embedder", None),
        local_knowledge=getattr(args, "local", False),
    )


def _write_mcp_json(repo: str) -> str:
    path = Path(repo) / ".mcp.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return "left unchanged (could not parse existing .mcp.json)"
        servers = data.setdefault("mcpServers", {})
        if "code" in servers:
            return "already present"
        servers["code"] = _MCP_ENTRY
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return "merged into existing .mcp.json"
    path.write_text(
        json.dumps({"mcpServers": {"code": _MCP_ENTRY}}, indent=2) + "\n",
        encoding="utf-8",
    )
    return "created .mcp.json"


def cmd_init(args) -> int:
    with CodeIndex(
        args.repo, embedder=args.embedder, local_knowledge=args.local
    ) as ci:
        report = ci.index(full=True)
        protocol_path = ci.idb_dir / "AGENT_PROTOCOL.md"
        protocol_path.write_text(PROTOCOL_MD, encoding="utf-8")
    mcp_status = _write_mcp_json(args.repo)
    print(
        json.dumps(
            {
                "index": report.to_dict(),
                "mcp_json": mcp_status,
                "protocol": str(protocol_path),
                "next": "restart Claude Code; the 'code' MCP tools will be available",
            },
            indent=2,
        )
    )
    return 0


def _add_repo(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("repo", nargs="?", default=".", help="path to the repo (default: .)")


def cmd_index(args) -> int:
    with _open(args) as ci:
        report = ci.index(full=args.full)
    print(json.dumps(report.to_dict(), indent=2))
    return 0


def cmd_search(args) -> int:
    filters: dict = {}
    if args.lang:
        filters["lang"] = args.lang
    if args.kind:
        filters["kind"] = args.kind
    if args.file:
        filters["file"] = args.file
    with _open(args) as ci:
        hits = ci.search(
            args.query,
            intent=args.intent,
            k=args.k,
            layer=args.layer,
            filters=filters or None,
            hybrid=not args.no_hybrid,
        )
    if args.json:
        print(json.dumps(hits, indent=2))
        return 0
    if not hits:
        print("(no results)")
        return 0
    used = hits[0].get("intent")
    if used:
        how = "inferred" if hits[0].get("intent_inferred") else "requested"
        print(f"intent: {used} ({how})\n")
    for i, h in enumerate(hits, 1):
        head = h["location"] or h["doc_key"]
        label = h.get("qualname") or ""
        kind = h.get("kind") or h.get("layer") or ""
        print(f"{i}. [{h['score']:+.4f}] {head}  {label} ({kind})")
        snippet = " ".join(h["snippet"].split())
        if len(snippet) > 140:
            snippet = snippet[:137] + "..."
        print(f"     {snippet}")
    return 0


def cmd_stats(args) -> int:
    with _open(args) as ci:
        print(json.dumps(ci.stats(), indent=2))
    return 0


def cmd_feedback(args) -> int:
    with _open(args) as ci:
        ci.feedback(
            args.query, args.doc_key, useful=not args.not_useful, intent=args.intent
        )
    print("recorded")
    return 0


def cmd_map(args) -> int:
    with _open(args) as ci:
        text = ci.map(budget_tokens=args.budget, rebuild=args.rebuild)
    print(text)
    return 0


def cmd_neighbors(args) -> int:
    with _open(args) as ci:
        result = ci.neighbors(args.symbol, direction=args.direction, k=args.k)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0
    if not result:
        print("(none)")
        return 0
    for n in result:
        loc = n.get("file", "")
        if n.get("start_line"):
            loc = f"{loc}:{n['start_line']}"
        label = n.get("qualname") or n.get("file")
        print(f"- {n['relation']}: {label}  {loc}")
    return 0


def cmd_note_get(args) -> int:
    with _open(args) as ci:
        note = ci.note_get(args.note_id)
    if not note:
        print("(not found)")
        return 1
    if args.json:
        print(json.dumps(note, indent=2))
    else:
        print(note["markdown"])
    return 0


def cmd_note_put(args) -> int:
    from pathlib import Path as _Path

    if args.file:
        markdown = _Path(args.file).read_text(encoding="utf-8")
    elif args.text:
        markdown = args.text
    else:
        markdown = sys.stdin.read()
    with _open(args) as ci:
        result = ci.note_put(args.note_id, markdown, covers=args.covers or [])
    print(json.dumps(result, indent=2))
    return 0


def cmd_note_list_stale(args) -> int:
    with _open(args) as ci:
        print(json.dumps(ci.note_list_stale(), indent=2))
    return 0


def cmd_note_rm(args) -> int:
    with _open(args) as ci:
        ok = ci.notes.remove(args.note_id)
    print("removed" if ok else "not found")
    return 0 if ok else 1


def cmd_serve_mcp(args) -> int:
    from .mcp_server import serve

    serve(args.repo)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="intent-code",
        description="Intent-aware code-knowledge index for LLM agents.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser(
        "init", help="index the repo and wire Claude Code (.mcp.json + protocol)"
    )
    _add_repo(sp)
    sp.add_argument("--embedder", help="embedder spec (default: auto-detect)")
    sp.add_argument(
        "--local",
        action="store_true",
        help="keep generated docs under .intentdb (do not commit them)",
    )
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("index", help="(re)index a repository (incremental)")
    _add_repo(sp)
    sp.add_argument("--full", action="store_true", help="force a full rebuild")
    sp.add_argument("--embedder", help="embedder spec (default: auto-detect)")
    sp.add_argument(
        "--local",
        action="store_true",
        help="keep generated docs under .intentdb (do not commit them)",
    )
    sp.set_defaults(func=cmd_index)

    sp = sub.add_parser("search", help="search the index")
    _add_repo(sp)
    sp.add_argument("query")
    sp.add_argument("--intent", help="retrieve under a code intent")
    sp.add_argument("-k", type=int, default=8, help="number of results")
    sp.add_argument(
        "--layer",
        default="symbol",
        choices=["symbol", "chunk", "note", "any"],
        help="which layer to search (default: symbol)",
    )
    sp.add_argument("--lang", help="filter by language")
    sp.add_argument("--kind", help="filter by symbol kind (function/class/...)")
    sp.add_argument("--file", help="filter by file path")
    sp.add_argument("--no-hybrid", action="store_true", help="disable BM25 fusion")
    sp.add_argument("--json", action="store_true", help="machine-readable output")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("map", help="print the PageRank-ranked repo map")
    _add_repo(sp)
    sp.add_argument("--budget", type=int, default=2000, help="token budget")
    sp.add_argument("--rebuild", action="store_true", help="recompute, don't use cache")
    sp.set_defaults(func=cmd_map)

    sp = sub.add_parser("neighbors", help="callers/callees/importers of a symbol")
    _add_repo(sp)
    sp.add_argument("symbol", help="doc_key, qualname, or symbol name")
    sp.add_argument(
        "--direction",
        default="callees",
        choices=["callers", "callees", "importers"],
    )
    sp.add_argument("-k", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_neighbors)

    sp = sub.add_parser("stats", help="index statistics")
    _add_repo(sp)
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("feedback", help="record whether a hit was useful")
    _add_repo(sp)
    sp.add_argument("query")
    sp.add_argument("doc_key")
    sp.add_argument("--intent")
    sp.add_argument("--not-useful", action="store_true")
    sp.set_defaults(func=cmd_feedback)

    sp = sub.add_parser("note", help="manage knowledge notes (gotchas / flow)")
    nsub = sp.add_subparsers(dest="note_command", required=True)

    g = nsub.add_parser("get", help="print a note")
    _add_repo(g)
    g.add_argument("note_id")
    g.add_argument("--json", action="store_true")
    g.set_defaults(func=cmd_note_get)

    g = nsub.add_parser("put", help="write/update a note (from --file, --text, or stdin)")
    _add_repo(g)
    g.add_argument("note_id")
    g.add_argument("--file", help="read markdown from a file")
    g.add_argument("--text", help="markdown content")
    g.add_argument("--covers", action="append", help="file the note covers (repeatable)")
    g.set_defaults(func=cmd_note_put)

    g = nsub.add_parser("list-stale", help="notes whose covered files changed")
    _add_repo(g)
    g.set_defaults(func=cmd_note_list_stale)

    g = nsub.add_parser("rm", help="delete a note")
    _add_repo(g)
    g.add_argument("note_id")
    g.set_defaults(func=cmd_note_rm)

    sp = sub.add_parser("serve-mcp", help="serve the index as an MCP stdio server")
    _add_repo(sp)
    sp.set_defaults(func=cmd_serve_mcp)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
