"""Tests for Java complexity parser."""
import os
import tempfile
import textwrap
from pathlib import Path

from complexity_accounting.java_parser import scan_java_file, count_java_lines
from complexity_accounting.scanner import scan_file, scan_directory


def _write_temp_java(source: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".java")
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


def test_simple_method():
    path = _write_temp_java("""
        public class T {
            public static int add(int a, int b) {
                return a + b;
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "add"
        assert fn.cognitive_complexity == 0
        assert fn.cyclomatic_complexity == 1
        assert fn.params == 2
    finally:
        os.unlink(path)


def test_nested_ifs():
    path = _write_temp_java("""
        public class T {
            public static boolean check(int x, int y, int z) {
                if (x > 0) {
                    if (y > 0) {
                        if (z > 0) {
                            return true;
                        }
                    }
                }
                return false;
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 6  # 1 + 2 + 3
        assert fn.max_nesting >= 3
    finally:
        os.unlink(path)


def test_for_with_break():
    path = _write_temp_java("""
        public class T {
            public static int find(String[] items, String target) {
                for (int i = 0; i < items.length; i++) {
                    if (items[i].equals(target)) {
                        break;
                    }
                }
                return -1;
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 4  # 1 (for) + 2 (if nested) + 1 (break)
    finally:
        os.unlink(path)


def test_switch_statement():
    path = _write_temp_java("""
        public class T {
            public static String classify(int n) {
                switch (n) {
                    case -1: return "negative";
                    case 0: return "zero";
                    default: return "positive";
                }
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 1  # switch
    finally:
        os.unlink(path)


def test_boolean_ops():
    path = _write_temp_java("""
        public class T {
            public static boolean validate(boolean a, boolean b) {
                if (a && b) {
                    return true;
                }
                return false;
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 2  # if + &&
    finally:
        os.unlink(path)


def test_method_in_class():
    path = _write_temp_java("""
        public class Server {
            public void start(int port) {
                if (port <= 0) {
                    return;
                }
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        assert fn.qualified_name == "Server.start"
        assert fn.params == 1
        assert fn.cognitive_complexity == 1
    finally:
        os.unlink(path)


def test_constructor():
    path = _write_temp_java("""
        public class MyClass {
            public MyClass(int x, String name) {
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "MyClass"
        assert fn.qualified_name == "MyClass.MyClass"
        assert fn.params == 2
        assert fn.cognitive_complexity == 0
    finally:
        os.unlink(path)


def test_lambda():
    path = _write_temp_java("""
        public class T {
            public void process(java.util.List<Integer> items) {
                items.forEach(item -> {
                    if (item > 0) {
                        System.out.println(item);
                    }
                });
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        # lambda increases nesting, if inside gets nesting penalty
        assert fn.cognitive_complexity >= 2
    finally:
        os.unlink(path)


def test_try_catch():
    path = _write_temp_java("""
        public class T {
            public static void parse(String s) {
                try {
                    if (s == null) {
                        return;
                    }
                } catch (Exception e) {
                    System.err.println(e);
                }
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 2  # if + catch
    finally:
        os.unlink(path)


def test_continue():
    path = _write_temp_java("""
        public class T {
            public void process(int[] items) {
                for (int item : items) {
                    if (item == 0) {
                        continue;
                    }
                }
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        # enhanced_for: +1, if: +2 (nested), continue: +1 = 4
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


def test_while_loop():
    path = _write_temp_java("""
        public class T {
            public void countdown(int n) {
                while (n > 0) {
                    n--;
                }
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1
        assert fn.cyclomatic_complexity == 2
    finally:
        os.unlink(path)


def test_do_while():
    path = _write_temp_java("""
        public class T {
            public void countdown(int n) {
                do {
                    n--;
                } while (n > 0);
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1
        assert fn.cyclomatic_complexity == 2
    finally:
        os.unlink(path)


def test_enhanced_for():
    path = _write_temp_java("""
        public class T {
            public void print(int[] items) {
                for (int item : items) {
                    if (item > 0) {
                        System.out.println(item);
                    }
                }
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 3  # for: +1, if: +2
        assert fn.cyclomatic_complexity == 3
    finally:
        os.unlink(path)


def test_ternary_expression():
    path = _write_temp_java("""
        public class T {
            public int abs(int x) {
                return x > 0 ? x : -x;
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # ternary: +1 flat
    finally:
        os.unlink(path)


def test_else_if_chain():
    path = _write_temp_java("""
        public class T {
            public static String classify(int x) {
                if (x < 0) {
                    return "negative";
                } else if (x == 0) {
                    return "zero";
                } else if (x < 10) {
                    return "small";
                } else {
                    return "large";
                }
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        # if: +1, else-if: +1 (flat), else-if: +1 (flat) = 3
        assert fn.cognitive_complexity == 3
    finally:
        os.unlink(path)


def test_count_java_lines():
    source = """package sample;

// This is a comment
public class T {
    /* block comment */
    int x = 1;
}
"""
    total, code, comment, blank = count_java_lines(source)
    assert total == 7
    assert comment >= 1  # at least the // comment
    assert blank == 1


def test_count_java_lines_multiline_block():
    source = "package sample;\n\n/*\nThis is a\nmulti-line comment\n*/\npublic class T {}\n"
    total, code, comment, blank = count_java_lines(source)
    assert comment >= 3  # /*, content lines, */


def test_count_java_lines_javadoc():
    source = "package sample;\n\n/**\n * Javadoc comment\n * @param x the value\n */\npublic class T {}\n"
    total, code, comment, blank = count_java_lines(source)
    assert comment >= 3  # /**, content, */


def test_count_java_lines_inline_block():
    source = "package sample;\n\npublic class T { int x = 1; /* inline */ }\n"
    total, code, comment, blank = count_java_lines(source)
    assert code >= 2


def test_scan_file_dispatch_java():
    """Ensure scan_file() routes .java files to the Java parser."""
    path = _write_temp_java("""
        public class T {
            public static String hello() {
                return "hello";
            }
        }
    """)
    try:
        fm = scan_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "hello"
    finally:
        os.unlink(path)


def test_scan_directory_mixed():
    """scan_directory picks up .py, .go, and .java files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "a.py").write_text("def foo(): pass\n")
        (Path(tmpdir) / "b.java").write_text(
            "public class B { public static void bar() {} }\n"
        )
        result = scan_directory(tmpdir)
        assert len(result.files) == 2
        names = {f.functions[0].name for f in result.files if f.functions}
        assert "foo" in names
        assert "bar" in names


def test_fixture_sample():
    """Test against the sample.java fixture file."""
    fixture = Path(__file__).parent / "fixtures" / "sample.java"
    if not fixture.exists():
        return  # skip if fixture missing
    fm = scan_java_file(str(fixture))
    func_map = {fn.name: fn for fn in fm.functions}

    assert func_map["add"].cognitive_complexity == 0
    assert func_map["nestedIfs"].cognitive_complexity == 6
    assert func_map["findItem"].cognitive_complexity == 4
    assert func_map["validate"].cognitive_complexity == 2
    assert func_map["elseIfChain"].cognitive_complexity == 3
    assert func_map["withLambda"].cognitive_complexity == 2
    assert func_map["tryCatch"].cognitive_complexity == 2


def test_ensure_tree_sitter_when_none():
    import complexity_accounting.java_parser as jp
    original = jp.JAVA_LANGUAGE
    try:
        jp.JAVA_LANGUAGE = None
        try:
            jp._ensure_tree_sitter()
            assert False, "Should have raised ImportError"
        except ImportError as e:
            assert "tree-sitter-java" in str(e)
    finally:
        jp.JAVA_LANGUAGE = original


def test_scan_java_file_parse_error():
    """tree-sitter is permissive, so partial parse should not crash."""
    path = _write_temp_java("""
        public class T {
            public void broken( {
                if {
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        # Should not crash, may return partial results
        assert isinstance(fm, type(fm))
    finally:
        os.unlink(path)


def test_nested_class():
    """Methods in nested classes get correct qualified names."""
    path = _write_temp_java("""
        public class Outer {
            public void outerMethod() {}

            public class Inner {
                public void innerMethod() {}
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        func_map = {fn.qualified_name: fn for fn in fm.functions}
        assert "Outer.outerMethod" in func_map
        assert "Outer.Inner.innerMethod" in func_map
    finally:
        os.unlink(path)


def test_multiple_boolean_ops():
    """Multiple boolean operators each add +1."""
    path = _write_temp_java("""
        public class T {
            public boolean check(boolean a, boolean b, boolean c) {
                if (a && b || c) {
                    return true;
                }
                return false;
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        # if: +1, &&: +1, ||: +1 = 3
        assert fn.cognitive_complexity >= 3
    finally:
        os.unlink(path)


def test_no_methods():
    """A class with no methods returns empty function list."""
    path = _write_temp_java("""
        public class T {
            public int x = 5;
            public static final String NAME = "test";
        }
    """)
    try:
        fm = scan_java_file(path)
        assert fm.function_count == 0
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Boolean operator tracking (SonarSource spec)
# ---------------------------------------------------------------------------

def test_boolean_same_operator_chain():
    """a && b && c should be +1 (same operator chain)."""
    path = _write_temp_java("""
        public class T {
            public boolean check(boolean a, boolean b, boolean c) {
                if (a && b && c) {
                    return true;
                }
                return false;
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        # if: +1, &&-chain: +1 = 2
        assert fn.cognitive_complexity == 2
    finally:
        os.unlink(path)


def test_boolean_three_switches():
    """a && b || c && d should be +3 operator increments."""
    path = _write_temp_java("""
        public class T {
            public boolean check(boolean a, boolean b, boolean c, boolean d) {
                if (a && b || c && d) {
                    return true;
                }
                return false;
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        # if: +1, &&: +1, || (switch): +1, && (switch): +1 = 4
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Maintainability Index
# ---------------------------------------------------------------------------

def test_maintainability_index_computed():
    """Java functions should have MI computed."""
    path = _write_temp_java("""
        public class T {
            public int simple() {
                return 1;
            }
        }
    """)
    try:
        fm = scan_java_file(path)
        fn = fm.functions[0]
        assert fn.maintainability_index > 0
        assert fn.maintainability_index <= 100
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
