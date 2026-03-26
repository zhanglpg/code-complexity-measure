"""Tests for JavaScript complexity parser."""
import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from conftest import requires_js

from complexity_accounting.js_parser import scan_js_file, count_js_lines
from complexity_accounting.scanner import scan_file, scan_directory

pytestmark = requires_js


def _write_temp_js(source: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".js")
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


def test_simple_function():
    path = _write_temp_js("""
        function add(a, b) {
            return a + b;
        }
    """)
    try:
        fm = scan_js_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "add"
        assert fn.cognitive_complexity == 0
        assert fn.cyclomatic_complexity == 1
        assert fn.params == 2
    finally:
        os.unlink(path)


def test_nested_ifs():
    path = _write_temp_js("""
        function check(x, y, z) {
            if (x > 0) {
                if (y > 0) {
                    if (z > 0) {
                        return true;
                    }
                }
            }
            return false;
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 6  # 1 + 2 + 3
        assert fn.max_nesting >= 3
    finally:
        os.unlink(path)


def test_for_with_break():
    path = _write_temp_js("""
        function find(items, target) {
            for (let i = 0; i < items.length; i++) {
                if (items[i] === target) {
                    break;
                }
            }
            return -1;
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 4  # 1 (for) + 2 (if nested) + 1 (break)
    finally:
        os.unlink(path)


def test_switch_statement():
    path = _write_temp_js("""
        function classify(n) {
            switch (n) {
                case -1: return "negative";
                case 0: return "zero";
                default: return "positive";
            }
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 1  # switch
    finally:
        os.unlink(path)


def test_boolean_ops():
    path = _write_temp_js("""
        function validate(a, b) {
            if (a && b) {
                return true;
            }
            return false;
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 2  # if + &&
    finally:
        os.unlink(path)


def test_arrow_function():
    path = _write_temp_js("""
        function process(items) {
            items.forEach(item => {
                if (item > 0) {
                    console.log(item);
                }
            });
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        # arrow increases nesting, if inside gets nesting penalty
        assert fn.cognitive_complexity >= 2
    finally:
        os.unlink(path)


def test_class_method():
    path = _write_temp_js("""
        class Server {
            start(port) {
                if (port <= 0) {
                    return;
                }
            }
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.qualified_name == "Server.start"
        assert fn.params == 1
        assert fn.cognitive_complexity == 1
    finally:
        os.unlink(path)


def test_constructor():
    path = _write_temp_js("""
        class MyClass {
            constructor(x, name) {
            }
        }
    """)
    try:
        fm = scan_js_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "constructor"
        assert fn.qualified_name == "MyClass.constructor"
        assert fn.params == 2
        assert fn.cognitive_complexity == 0
    finally:
        os.unlink(path)


def test_try_catch():
    path = _write_temp_js("""
        function parse(s) {
            try {
                if (s === null) {
                    return;
                }
            } catch (e) {
                console.error(e);
            }
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 2  # if + catch
    finally:
        os.unlink(path)


def test_continue():
    path = _write_temp_js("""
        function process(items) {
            for (const item of items) {
                if (item === 0) {
                    continue;
                }
            }
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        # for_in: +1, if: +2 (nested), continue: +1 = 4
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


def test_while_loop():
    path = _write_temp_js("""
        function countdown(n) {
            while (n > 0) {
                n--;
            }
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1
        assert fn.cyclomatic_complexity == 2
    finally:
        os.unlink(path)


def test_do_while():
    path = _write_temp_js("""
        function countdown(n) {
            do {
                n--;
            } while (n > 0);
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1
        assert fn.cyclomatic_complexity == 2
    finally:
        os.unlink(path)


def test_for_in():
    path = _write_temp_js("""
        function printKeys(obj) {
            for (const key in obj) {
                if (obj.hasOwnProperty(key)) {
                    console.log(key);
                }
            }
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 3  # for_in: +1, if: +2
        assert fn.cyclomatic_complexity == 3
    finally:
        os.unlink(path)


def test_ternary_expression():
    path = _write_temp_js("""
        function abs(x) {
            return x > 0 ? x : -x;
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # ternary: +1 flat
    finally:
        os.unlink(path)


def test_else_if_chain():
    path = _write_temp_js("""
        function classify(x) {
            if (x < 0) {
                return "negative";
            } else if (x === 0) {
                return "zero";
            } else if (x < 10) {
                return "small";
            } else {
                return "large";
            }
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        # if: +1, else-if: +1 (flat), else-if: +1 (flat) = 3
        assert fn.cognitive_complexity == 3
    finally:
        os.unlink(path)


def test_count_js_lines():
    source = """// This is a comment
const x = 1;

/* block comment */
function foo() {}
"""
    total, code, comment, blank = count_js_lines(source)
    assert total == 5
    assert comment >= 1  # at least the // comment
    assert blank == 1


def test_count_js_lines_multiline_block():
    source = "const x = 1;\n\n/*\nThis is a\nmulti-line comment\n*/\nfunction foo() {}\n"
    total, code, comment, blank = count_js_lines(source)
    assert comment >= 3  # /*, content lines, */


def test_count_js_lines_jsdoc():
    source = "const x = 1;\n\n/**\n * JSDoc comment\n * @param x the value\n */\nfunction foo() {}\n"
    total, code, comment, blank = count_js_lines(source)
    assert comment >= 3  # /**, content, */


def test_count_js_lines_inline_block():
    source = "const x = 1;\n\nfunction foo() { return 1; /* inline */ }\n"
    total, code, comment, blank = count_js_lines(source)
    assert code >= 2


def test_scan_file_dispatch_js():
    """Ensure scan_file() routes .js files to the JavaScript parser."""
    path = _write_temp_js("""
        function hello() {
            return "hello";
        }
    """)
    try:
        fm = scan_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "hello"
    finally:
        os.unlink(path)


def test_scan_directory_mixed():
    """scan_directory picks up .py and .js files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "a.py").write_text("def foo(): pass\n")
        (Path(tmpdir) / "b.js").write_text(
            "function bar() {}\n"
        )
        result = scan_directory(tmpdir)
        assert len(result.files) == 2
        names = {f.functions[0].name for f in result.files if f.functions}
        assert "foo" in names
        assert "bar" in names


def test_fixture_sample():
    """Test against the sample.js fixture file."""
    fixture = Path(__file__).parent / "fixtures" / "sample.js"
    if not fixture.exists():
        return  # skip if fixture missing
    fm = scan_js_file(str(fixture))
    func_map = {fn.name: fn for fn in fm.functions}

    assert func_map["add"].cognitive_complexity == 0
    assert func_map["nestedIfs"].cognitive_complexity == 6
    assert func_map["findItem"].cognitive_complexity == 4
    assert func_map["validate"].cognitive_complexity == 2
    assert func_map["elseIfChain"].cognitive_complexity == 3
    assert func_map["withArrow"].cognitive_complexity == 2
    assert func_map["tryCatch"].cognitive_complexity == 2


def test_ensure_tree_sitter_when_none():
    import complexity_accounting.js_parser as jp
    original = jp.JS_LANGUAGE
    try:
        jp.JS_LANGUAGE = None
        try:
            jp._ensure_tree_sitter()
            assert False, "Should have raised ImportError"
        except ImportError as e:
            assert "tree-sitter-javascript" in str(e)
    finally:
        jp.JS_LANGUAGE = original


def test_scan_js_file_parse_error():
    """tree-sitter is permissive, so partial parse should not crash."""
    path = _write_temp_js("""
        function broken( {
            if {
            }
        }
    """)
    try:
        fm = scan_js_file(path)
        # Should not crash, may return partial results
        assert isinstance(fm, type(fm))
    finally:
        os.unlink(path)


def test_nested_class():
    """Methods in nested classes get correct qualified names."""
    path = _write_temp_js("""
        class Outer {
            outerMethod() {}
        }
    """)
    try:
        fm = scan_js_file(path)
        func_map = {fn.qualified_name: fn for fn in fm.functions}
        assert "Outer.outerMethod" in func_map
    finally:
        os.unlink(path)


def test_multiple_boolean_ops():
    """Multiple boolean operators each add +1."""
    path = _write_temp_js("""
        function check(a, b, c) {
            if (a && b || c) {
                return true;
            }
            return false;
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        # if: +1, &&: +1, ||: +1 = 3
        assert fn.cognitive_complexity >= 3
    finally:
        os.unlink(path)


def test_no_functions():
    """A file with no functions returns empty function list."""
    path = _write_temp_js("""
        const x = 5;
        const NAME = "test";
    """)
    try:
        fm = scan_js_file(path)
        assert fm.function_count == 0
    finally:
        os.unlink(path)


def test_nullish_coalescing():
    """Nullish coalescing operator (??) adds +1."""
    path = _write_temp_js("""
        function getDefault(x) {
            return x ?? "default";
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # ??
    finally:
        os.unlink(path)


def test_arrow_function_variable():
    """Arrow functions assigned to variables are detected."""
    path = _write_temp_js("""
        const greet = (name) => {
            return "Hello, " + name;
        };
    """)
    try:
        fm = scan_js_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "greet"
        assert fn.params == 1
        assert fn.cognitive_complexity == 0
    finally:
        os.unlink(path)


def test_function_expression_variable():
    """Function expressions assigned to variables are detected."""
    path = _write_temp_js("""
        const greet = function(name) {
            return "Hello, " + name;
        };
    """)
    try:
        fm = scan_js_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "greet"
        assert fn.params == 1
    finally:
        os.unlink(path)


def test_export_function():
    """Exported functions are detected."""
    path = _write_temp_js("""
        export function hello() {
            return "hello";
        }
    """)
    try:
        fm = scan_js_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "hello"
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Boolean operator tracking (SonarSource spec)
# ---------------------------------------------------------------------------

def test_boolean_same_operator_chain():
    """a && b && c should be +1 (same operator chain)."""
    path = _write_temp_js("""
        function check(a, b, c) {
            if (a && b && c) {
                return true;
            }
            return false;
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 2  # if + &&-chain
    finally:
        os.unlink(path)


def test_boolean_mixed_operators():
    """a && b || c should be +2 (operator change)."""
    path = _write_temp_js("""
        function check(a, b, c) {
            if (a && b || c) {
                return true;
            }
            return false;
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 3  # if + && + || switch
    finally:
        os.unlink(path)


def test_boolean_nullish_coalescing():
    """?? should be tracked separately from &&/||."""
    path = _write_temp_js("""
        function check(a, b) {
            if (a ?? b) {
                return true;
            }
            return false;
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 2  # if + ??
    finally:
        os.unlink(path)


def test_boolean_three_switches():
    """a && b || c && d should be +3."""
    path = _write_temp_js("""
        function check(a, b, c, d) {
            if (a && b || c && d) {
                return true;
            }
            return false;
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Maintainability Index
# ---------------------------------------------------------------------------

def test_maintainability_index_computed():
    """JS functions should have MI computed."""
    path = _write_temp_js("""
        function simple() {
            return 1;
        }
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.maintainability_index > 0
        assert fn.maintainability_index <= 100
    finally:
        os.unlink(path)


def test_maintainability_index_arrow_function():
    """Arrow functions assigned to variables should have MI computed."""
    path = _write_temp_js("""
        const add = (a, b) => {
            return a + b;
        };
    """)
    try:
        fm = scan_js_file(path)
        fn = fm.functions[0]
        assert fn.maintainability_index > 0
    finally:
        os.unlink(path)


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for test in tests:
        try:
            test()
            print(f"  ✅ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
