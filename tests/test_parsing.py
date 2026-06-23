from __future__ import annotations

import pytest

from intent_code import parsing

PY = b'''import os
from x import y


class Foo:
    def bar(self, n):
        return helper(n)


def helper(n):
    return n + 1
'''

JS = b'''import {a} from "x";

class Widget {
  render() { return build(); }
}

function build() { return 1; }
'''


def test_extract_python_symbols_edges():
    res = parsing.extract(PY, "python", "m.py")
    if not res.ok:
        pytest.skip("tree-sitter python grammar unavailable")
    quals = {s.qualname: s for s in res.symbols}
    assert quals["Foo"].kind == "class"
    assert quals["Foo.bar"].kind == "method"
    assert quals["helper"].kind == "function"
    assert "helper" in quals["Foo.bar"].calls
    assert any("import os" in imp for imp in res.imports)
    assert quals["Foo.bar"].start_line == 6


def test_extract_javascript():
    res = parsing.extract(JS, "javascript", "w.js")
    if not res.ok:
        pytest.skip("tree-sitter javascript grammar unavailable")
    quals = {s.qualname for s in res.symbols}
    assert "Widget" in quals
    assert "Widget.render" in quals
    assert "build" in quals


def test_signature_card_has_header():
    res = parsing.extract(PY, "python", "m.py")
    if not res.ok:
        pytest.skip("tree-sitter python grammar unavailable")
    sym = next(s for s in res.symbols if s.qualname == "helper")
    card = parsing.signature_card(sym)
    assert card.startswith("helper (function) in m.py:")
    assert "return n + 1" in card


def test_unknown_lang_not_ok():
    res = parsing.extract(b"x", "no-such-lang", "x.zzz")
    assert res.ok is False
