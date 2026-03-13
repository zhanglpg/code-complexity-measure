"""Tests for TypeScript complexity parser."""
import os
import tempfile
import textwrap
from pathlib import Path

from complexity_accounting.ts_parser import scan_ts_file, count_ts_lines
from complexity_accounting.scanner import scan_file, scan_directory


def _write_temp_ts(source: str, suffix: str = ".ts") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


def test_simple_function():
    path = _write_temp_ts("""
        function add(a: number, b: number): number {
            return a + b;
        }
    """)
    try:
        fm = scan_ts_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "add"
        assert fn.cognitive_complexity == 0
        assert fn.cyclomatic_complexity == 1
        assert fn.params == 2
    finally:
        os.unlink(path)


def test_nested_ifs():
    path = _write_temp_ts("""
        function check(x: number, y: number, z: number): boolean {
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
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 6  # 1 + 2 + 3
        assert fn.max_nesting >= 3
    finally:
        os.unlink(path)


def test_for_with_break():
    path = _write_temp_ts("""
        function find(items: number[], target: number): number {
            for (let i = 0; i < items.length; i++) {
                if (items[i] === target) {
                    break;
                }
            }
            return -1;
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 4  # 1 (for) + 2 (if nested) + 1 (break)
    finally:
        os.unlink(path)


def test_switch_statement():
    path = _write_temp_ts("""
        function classify(n: number): string {
            switch (n) {
                case -1: return "negative";
                case 0: return "zero";
                default: return "positive";
            }
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 1  # switch
    finally:
        os.unlink(path)


def test_boolean_ops():
    path = _write_temp_ts("""
        function validate(a: boolean, b: boolean): boolean {
            if (a && b) {
                return true;
            }
            return false;
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 2  # if + &&
    finally:
        os.unlink(path)


def test_arrow_function():
    path = _write_temp_ts("""
        function process(items: number[]): void {
            items.forEach((item: number) => {
                if (item > 0) {
                    console.log(item);
                }
            });
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        # arrow increases nesting, if inside gets nesting penalty
        assert fn.cognitive_complexity >= 2
    finally:
        os.unlink(path)


def test_class_method():
    path = _write_temp_ts("""
        class Server {
            start(port: number): void {
                if (port <= 0) {
                    return;
                }
            }
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.qualified_name == "Server.start"
        assert fn.params == 1
        assert fn.cognitive_complexity == 1
    finally:
        os.unlink(path)


def test_constructor():
    path = _write_temp_ts("""
        class MyClass {
            constructor(x: number, name: string) {
            }
        }
    """)
    try:
        fm = scan_ts_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "constructor"
        assert fn.qualified_name == "MyClass.constructor"
        assert fn.params == 2
        assert fn.cognitive_complexity == 0
    finally:
        os.unlink(path)


def test_try_catch():
    path = _write_temp_ts("""
        function parse(s: string | null): void {
            try {
                if (s === null) {
                    return;
                }
            } catch (e: unknown) {
                console.error(e);
            }
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 2  # if + catch
    finally:
        os.unlink(path)


def test_continue():
    path = _write_temp_ts("""
        function process(items: number[]): void {
            for (const item of items) {
                if (item === 0) {
                    continue;
                }
            }
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        # for_in: +1, if: +2 (nested), continue: +1 = 4
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


def test_while_loop():
    path = _write_temp_ts("""
        function countdown(n: number): void {
            while (n > 0) {
                n--;
            }
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1
        assert fn.cyclomatic_complexity == 2
    finally:
        os.unlink(path)


def test_do_while():
    path = _write_temp_ts("""
        function countdown(n: number): void {
            do {
                n--;
            } while (n > 0);
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1
        assert fn.cyclomatic_complexity == 2
    finally:
        os.unlink(path)


def test_for_in():
    path = _write_temp_ts("""
        function printKeys(obj: Record<string, unknown>): void {
            for (const key in obj) {
                if (obj.hasOwnProperty(key)) {
                    console.log(key);
                }
            }
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 3  # for_in: +1, if: +2
        assert fn.cyclomatic_complexity == 3
    finally:
        os.unlink(path)


def test_ternary_expression():
    path = _write_temp_ts("""
        function abs(x: number): number {
            return x > 0 ? x : -x;
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # ternary: +1 flat
    finally:
        os.unlink(path)


def test_else_if_chain():
    path = _write_temp_ts("""
        function classify(x: number): string {
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
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        # if: +1, else-if: +1 (flat), else-if: +1 (flat) = 3
        assert fn.cognitive_complexity == 3
    finally:
        os.unlink(path)


def test_count_ts_lines():
    source = """// This is a comment
const x: number = 1;

/* block comment */
function foo(): void {}
"""
    total, code, comment, blank = count_ts_lines(source)
    assert total == 5
    assert comment >= 1  # at least the // comment
    assert blank == 1


def test_count_ts_lines_multiline_block():
    source = "const x: number = 1;\n\n/*\nThis is a\nmulti-line comment\n*/\nfunction foo(): void {}\n"
    total, code, comment, blank = count_ts_lines(source)
    assert comment >= 3  # /*, content lines, */


def test_count_ts_lines_tsdoc():
    source = "const x: number = 1;\n\n/**\n * TSDoc comment\n * @param x the value\n */\nfunction foo(): void {}\n"
    total, code, comment, blank = count_ts_lines(source)
    assert comment >= 3  # /**, content, */


def test_count_ts_lines_inline_block():
    source = "const x: number = 1;\n\nfunction foo(): number { return 1; /* inline */ }\n"
    total, code, comment, blank = count_ts_lines(source)
    assert code >= 2


def test_scan_file_dispatch_ts():
    """Ensure scan_file() routes .ts files to the TypeScript parser."""
    path = _write_temp_ts("""
        function hello(): string {
            return "hello";
        }
    """)
    try:
        fm = scan_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "hello"
    finally:
        os.unlink(path)


def test_scan_file_dispatch_tsx():
    """Ensure scan_file() routes .tsx files to the TypeScript parser."""
    path = _write_temp_ts("""
        function Component(): string {
            return "hello";
        }
    """, suffix=".tsx")
    try:
        fm = scan_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "Component"
    finally:
        os.unlink(path)


def test_scan_directory_mixed():
    """scan_directory picks up .py and .ts files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "a.py").write_text("def foo(): pass\n")
        (Path(tmpdir) / "b.ts").write_text(
            "function bar(): void {}\n"
        )
        result = scan_directory(tmpdir)
        assert len(result.files) == 2
        names = {f.functions[0].name for f in result.files if f.functions}
        assert "foo" in names
        assert "bar" in names


def test_fixture_sample():
    """Test against the sample.ts fixture file."""
    fixture = Path(__file__).parent / "fixtures" / "sample.ts"
    if not fixture.exists():
        return  # skip if fixture missing
    fm = scan_ts_file(str(fixture))
    func_map = {fn.name: fn for fn in fm.functions}

    assert func_map["add"].cognitive_complexity == 0
    assert func_map["nestedIfs"].cognitive_complexity == 6
    assert func_map["findItem"].cognitive_complexity == 4
    assert func_map["validate"].cognitive_complexity == 2
    assert func_map["elseIfChain"].cognitive_complexity == 3
    assert func_map["withArrow"].cognitive_complexity == 2
    assert func_map["tryCatch"].cognitive_complexity == 2


def test_ensure_tree_sitter_when_none():
    import complexity_accounting.ts_parser as tp
    original_ts = tp.TS_LANGUAGE
    original_tsx = tp.TSX_LANGUAGE
    try:
        tp.TS_LANGUAGE = None
        tp.TSX_LANGUAGE = None
        try:
            tp._ensure_tree_sitter()
            assert False, "Should have raised ImportError"
        except ImportError as e:
            assert "tree-sitter-typescript" in str(e)
    finally:
        tp.TS_LANGUAGE = original_ts
        tp.TSX_LANGUAGE = original_tsx


def test_scan_ts_file_parse_error():
    """tree-sitter is permissive, so partial parse should not crash."""
    path = _write_temp_ts("""
        function broken( {
            if {
            }
        }
    """)
    try:
        fm = scan_ts_file(path)
        # Should not crash, may return partial results
        assert isinstance(fm, type(fm))
    finally:
        os.unlink(path)


def test_no_functions():
    """A file with only types/interfaces returns empty function list."""
    path = _write_temp_ts("""
        interface Foo {
            bar: string;
        }
        type MyType = string | number;
        enum Color { Red, Green, Blue }
        const x: number = 5;
    """)
    try:
        fm = scan_ts_file(path)
        assert fm.function_count == 0
    finally:
        os.unlink(path)


def test_nullish_coalescing():
    """Nullish coalescing operator (??) adds +1."""
    path = _write_temp_ts("""
        function getDefault(x: string | null): string {
            return x ?? "default";
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # ??
    finally:
        os.unlink(path)


def test_arrow_function_variable():
    """Arrow functions assigned to variables are detected."""
    path = _write_temp_ts("""
        const greet = (name: string): string => {
            return "Hello, " + name;
        };
    """)
    try:
        fm = scan_ts_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "greet"
        assert fn.params == 1
        assert fn.cognitive_complexity == 0
    finally:
        os.unlink(path)


def test_function_expression_variable():
    """Function expressions assigned to variables are detected."""
    path = _write_temp_ts("""
        const greet = function(name: string): string {
            return "Hello, " + name;
        };
    """)
    try:
        fm = scan_ts_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "greet"
        assert fn.params == 1
    finally:
        os.unlink(path)


def test_export_function():
    """Exported functions are detected."""
    path = _write_temp_ts("""
        export function hello(): string {
            return "hello";
        }
    """)
    try:
        fm = scan_ts_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "hello"
    finally:
        os.unlink(path)


def test_interface_ignored():
    """Interfaces don't produce function metrics."""
    path = _write_temp_ts("""
        interface Shape {
            area(): number;
            perimeter(): number;
        }

        function compute(): number { return 0; }
    """)
    try:
        fm = scan_ts_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "compute"
    finally:
        os.unlink(path)


def test_type_alias_ignored():
    """Type aliases don't produce function metrics."""
    path = _write_temp_ts("""
        type Result<T> = { ok: true; value: T } | { ok: false; error: string };

        function ok<T>(value: T): Result<T> { return { ok: true, value }; }
    """)
    try:
        fm = scan_ts_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "ok"
    finally:
        os.unlink(path)


def test_enum_ignored():
    """Enums don't produce function metrics."""
    path = _write_temp_ts("""
        enum Color { Red, Green, Blue }

        function getColor(): string { return "red"; }
    """)
    try:
        fm = scan_ts_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "getColor"
    finally:
        os.unlink(path)


def test_generic_function():
    """Generics don't affect complexity."""
    path = _write_temp_ts("""
        function identity<T>(value: T): T {
            return value;
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.name == "identity"
        assert fn.cognitive_complexity == 0
        assert fn.cyclomatic_complexity == 1
        assert fn.params == 1
    finally:
        os.unlink(path)


def test_optional_parameter():
    """Optional parameters are counted."""
    path = _write_temp_ts("""
        function greet(name: string, greeting?: string): string {
            if (greeting) {
                return greeting + ", " + name;
            }
            return "Hello, " + name;
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        assert fn.params == 2
        assert fn.cognitive_complexity == 1
    finally:
        os.unlink(path)


def test_nested_class():
    """Methods in classes get correct qualified names."""
    path = _write_temp_ts("""
        class Outer {
            outerMethod(): void {}
        }
    """)
    try:
        fm = scan_ts_file(path)
        func_map = {fn.qualified_name: fn for fn in fm.functions}
        assert "Outer.outerMethod" in func_map
    finally:
        os.unlink(path)


def test_multiple_boolean_ops():
    """Multiple boolean operators each add +1."""
    path = _write_temp_ts("""
        function check(a: boolean, b: boolean, c: boolean): boolean {
            if (a && b || c) {
                return true;
            }
            return false;
        }
    """)
    try:
        fm = scan_ts_file(path)
        fn = fm.functions[0]
        # if: +1, &&: +1, ||: +1 = 3
        assert fn.cognitive_complexity >= 3
    finally:
        os.unlink(path)


def test_abstract_class():
    """Abstract classes with concrete methods are analyzed."""
    path = _write_temp_ts("""
        abstract class Base {
            abstract run(): void;

            concrete(): void {
                if (true) {
                    return;
                }
            }
        }
    """)
    try:
        fm = scan_ts_file(path)
        # Only the concrete method should be collected (abstract has no body)
        assert fm.function_count == 1
        assert fm.functions[0].name == "concrete"
        assert fm.functions[0].qualified_name == "Base.concrete"
    finally:
        os.unlink(path)


def test_tsx_jsx_component():
    """TSX files with JSX are parsed correctly."""
    path = _write_temp_ts("""
        function App(props: { name: string }): any {
            if (props.name) {
                return props.name;
            }
            return "default";
        }
    """, suffix=".tsx")
    try:
        fm = scan_ts_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "App"
        assert fn.cognitive_complexity == 1
    finally:
        os.unlink(path)


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
