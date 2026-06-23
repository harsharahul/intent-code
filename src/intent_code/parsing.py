"""Tree-sitter symbol and edge extraction.

A single generic depth-first walk over the parse tree (not per-language `.scm`
query files): for each node whose type marks a definition we record a `Symbol`
with a scope-derived qualname, line span, content, and the call names found in
its body. Import statements are collected at file level. Call edges are
**name-based and type-unresolved** (Aider-style) — good for ranking, not a
correct call graph.

tree-sitter is optional. If the core binding or a grammar is unavailable,
`extract` returns `ParseResult(ok=False, ...)` and the caller falls back to
text chunking.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Grammar module + the function returning its PyCapsule language pointer.
_LOADERS: dict[str, tuple[str, str]] = {
    "python": ("tree_sitter_python", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
    "go": ("tree_sitter_go", "language"),
    "rust": ("tree_sitter_rust", "language"),
    "java": ("tree_sitter_java", "language"),
    "c": ("tree_sitter_c", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
    "ruby": ("tree_sitter_ruby", "language"),
    "c_sharp": ("tree_sitter_c_sharp", "language"),
}

SYMBOL_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition", "class_definition"},
    "javascript": {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "method_definition",
    },
    "typescript": {
        "function_declaration",
        "class_declaration",
        "method_definition",
        "interface_declaration",
        "enum_declaration",
        "abstract_class_declaration",
    },
    "go": {"function_declaration", "method_declaration", "type_declaration"},
    "rust": {
        "function_item",
        "struct_item",
        "enum_item",
        "trait_item",
        "impl_item",
        "mod_item",
    },
    "java": {
        "method_declaration",
        "constructor_declaration",
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
    },
    "c": {"function_definition", "struct_specifier"},
    "cpp": {"function_definition", "class_specifier", "struct_specifier"},
    "ruby": {"method", "singleton_method", "class", "module"},
    "c_sharp": {
        "method_declaration",
        "class_declaration",
        "interface_declaration",
        "struct_declaration",
        "enum_declaration",
    },
}
SYMBOL_NODE_TYPES["tsx"] = SYMBOL_NODE_TYPES["typescript"]

IMPORT_NODE_TYPES: dict[str, set[str]] = {
    "python": {"import_statement", "import_from_statement"},
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "tsx": {"import_statement"},
    "go": {"import_spec"},
    "rust": {"use_declaration"},
    "java": {"import_declaration"},
    "c": {"preproc_include"},
    "cpp": {"preproc_include"},
    "ruby": set(),
    "c_sharp": {"using_directive"},
}

CALL_NODE_TYPES: dict[str, set[str]] = {
    "python": {"call"},
    "javascript": {"call_expression"},
    "typescript": {"call_expression"},
    "tsx": {"call_expression"},
    "go": {"call_expression"},
    "rust": {"call_expression", "macro_invocation"},
    "java": {"method_invocation", "object_creation_expression"},
    "c": {"call_expression"},
    "cpp": {"call_expression"},
    "ruby": {"call", "method_call"},
    "c_sharp": {"invocation_expression", "object_creation_expression"},
}

_KIND_MAP: dict[str, str] = {
    "function_definition": "function",
    "function_declaration": "function",
    "function_item": "function",
    "generator_function_declaration": "function",
    "method_definition": "method",
    "method_declaration": "method",
    "method": "method",
    "singleton_method": "method",
    "constructor_declaration": "constructor",
    "class_definition": "class",
    "class_declaration": "class",
    "class_specifier": "class",
    "abstract_class_declaration": "class",
    "class": "class",
    "struct_item": "struct",
    "struct_specifier": "struct",
    "struct_declaration": "struct",
    "enum_item": "enum",
    "enum_declaration": "enum",
    "trait_item": "trait",
    "interface_declaration": "interface",
    "impl_item": "impl",
    "mod_item": "module",
    "module": "module",
    "type_declaration": "type",
}

_IDENT_TYPES = {
    "identifier",
    "type_identifier",
    "field_identifier",
    "property_identifier",
    "constant",
    "scoped_identifier",
    "word",
    "name",
}

_CONTAINER_KINDS = {"class", "struct", "interface", "impl", "trait"}


@dataclass
class Symbol:
    file: str
    lang: str
    kind: str
    name: str
    qualname: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    text: str
    calls: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    ok: bool
    symbols: list[Symbol]
    imports: list[str]


_LANG_CACHE: dict[str, object] = {}


def get_language(lang: str):
    """Return a tree_sitter.Language for ``lang`` or None if unavailable."""
    if lang in _LANG_CACHE:
        return _LANG_CACHE[lang]
    spec = _LOADERS.get(lang)
    if spec is None:
        _LANG_CACHE[lang] = None
        return None
    module_name, func_name = spec
    try:
        import importlib

        from tree_sitter import Language

        mod = importlib.import_module(module_name)
        language = Language(getattr(mod, func_name)())
    except Exception:
        language = None
    _LANG_CACHE[lang] = language
    return language


def _kind_of(node_type: str, scope: tuple) -> str:
    base = _KIND_MAP.get(node_type, node_type)
    if base == "function" and any(k in _CONTAINER_KINDS for _, k in scope):
        return "method"
    return base


def _first_ident(node, source: bytes) -> str | None:
    stack = [node]
    while stack:
        n = stack.pop()
        if n.type in _IDENT_TYPES:
            return source[n.start_byte : n.end_byte].decode("utf-8", "replace")
        stack.extend(reversed(n.children))
    return None


def _last_ident(node, source: bytes) -> str | None:
    found: str | None = None
    stack = [node]
    # pre-order; keep updating so the final (rightmost-deepest) identifier wins
    order = []
    while stack:
        n = stack.pop()
        order.append(n)
        stack.extend(reversed(n.children))
    for n in order:
        if n.type in _IDENT_TYPES:
            found = source[n.start_byte : n.end_byte].decode("utf-8", "replace")
    return found


def _name_of(node, source: bytes) -> str | None:
    # The "name" field is the identifier itself in essentially every grammar.
    n = node.child_by_field_name("name")
    if n is not None:
        return source[n.start_byte : n.end_byte].decode("utf-8", "replace")
    decl = node.child_by_field_name("declarator")
    if decl is not None:
        ident = _first_ident(decl, source)
        if ident:
            return ident
    return _first_ident(node, source)


def _callee_name(node, source: bytes) -> str | None:
    for f in ("function", "name", "method", "constructor", "type"):
        c = node.child_by_field_name(f)
        if c is not None:
            return _last_ident(c, source)
    return _last_ident(node, source)


def extract(source: bytes, lang: str, relpath: str) -> ParseResult:
    """Parse ``source`` and extract symbols + imports for ``lang``."""
    language = get_language(lang)
    if language is None:
        return ParseResult(ok=False, symbols=[], imports=[])

    try:
        from tree_sitter import Parser

        parser = Parser(language)
        tree = parser.parse(source)
    except Exception:
        return ParseResult(ok=False, symbols=[], imports=[])

    sym_types = SYMBOL_NODE_TYPES.get(lang, set())
    imp_types = IMPORT_NODE_TYPES.get(lang, set())
    call_types = CALL_NODE_TYPES.get(lang, set())

    def text_of(node) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8", "replace")

    symbols: list[Symbol] = []
    imports: list[str] = []

    # Iterative DFS to avoid recursion limits on deeply nested files.
    stack: list[tuple[object, tuple, Symbol | None]] = [(tree.root_node, (), None)]
    while stack:
        node, scope, current = stack.pop()
        ntype = node.type

        if ntype in imp_types:
            imports.append(text_of(node).strip())

        if ntype in call_types and current is not None:
            callee = _callee_name(node, source)
            if callee:
                current.calls.append(callee)

        if ntype in sym_types:
            name = _name_of(node, source) or "<anon>"
            kind = _kind_of(ntype, scope)
            qual = ".".join([s[0] for s in scope] + [name])
            sym = Symbol(
                file=relpath,
                lang=lang,
                kind=kind,
                name=name,
                qualname=qual,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                text=text_of(node),
            )
            symbols.append(sym)
            child_scope = scope + ((name, kind),)
            for child in reversed(node.children):
                stack.append((child, child_scope, sym))
        else:
            for child in reversed(node.children):
                stack.append((child, scope, current))

    for sym in symbols:
        sym.calls = sorted(set(sym.calls))

    return ParseResult(ok=bool(symbols), symbols=symbols, imports=sorted(set(imports)))


def signature_card(sym: Symbol, max_chars: int = 1500) -> str:
    """The text embedded + returned for a symbol: a header line + body head."""
    header = f"{sym.qualname} ({sym.kind}) in {sym.file}:{sym.start_line}-{sym.end_line}"
    body = sym.text
    if len(body) > max_chars:
        body = body[:max_chars].rstrip() + "\n…"
    return f"{header}\n{body}"
