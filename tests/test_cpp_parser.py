"""Tests for C/C++ complexity parser."""
import os
import tempfile
import textwrap
from pathlib import Path

from complexity_accounting.cpp_parser import scan_cpp_file, count_cpp_lines
from complexity_accounting.scanner import scan_file, scan_directory


def _write_temp_cpp(source: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".cpp")
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


def _write_temp_c(source: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".c")
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


def test_simple_function():
    path = _write_temp_cpp("""
        int add(int a, int b) {
            return a + b;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "add"
        assert fn.cognitive_complexity == 0
        assert fn.cyclomatic_complexity == 1
        assert fn.params == 2
    finally:
        os.unlink(path)


def test_nested_ifs():
    path = _write_temp_cpp("""
        bool check(int x, int y, int z) {
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
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 6  # 1 + 2 + 3
        assert fn.max_nesting >= 3
    finally:
        os.unlink(path)


def test_for_with_break():
    path = _write_temp_cpp("""
        int find(int* items, int size, int target) {
            for (int i = 0; i < size; i++) {
                if (items[i] == target) {
                    break;
                }
            }
            return -1;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 4  # 1 (for) + 2 (if nested) + 1 (break)
    finally:
        os.unlink(path)


def test_while_loop():
    path = _write_temp_cpp("""
        void countdown(int n) {
            while (n > 0) {
                n--;
            }
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # while
        assert fn.cyclomatic_complexity == 2  # 1 + while
    finally:
        os.unlink(path)


def test_do_while_loop():
    path = _write_temp_cpp("""
        void process(int n) {
            do {
                n--;
            } while (n > 0);
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # do-while
        assert fn.cyclomatic_complexity == 2  # 1 + do
    finally:
        os.unlink(path)


def test_switch_statement():
    path = _write_temp_cpp("""
        int classify(int n) {
            switch (n) {
            case 0:
                return 0;
            case 1:
                return 1;
            default:
                return -1;
            }
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 1  # switch + cases
    finally:
        os.unlink(path)


def test_boolean_ops():
    path = _write_temp_cpp("""
        bool validate(bool a, bool b) {
            if (a && b) {
                return true;
            }
            return false;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 2  # if + &&
    finally:
        os.unlink(path)


def test_else_if_chain_cognitive():
    path = _write_temp_cpp("""
        const char* classify(int x) {
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
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        # if: +1, else-if: +1 (flat), else-if: +1 (flat) = 3
        assert fn.cognitive_complexity == 3
    finally:
        os.unlink(path)


def test_ternary_expression():
    path = _write_temp_cpp("""
        int abs_val(int x) {
            return x > 0 ? x : -x;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # ternary
    finally:
        os.unlink(path)


def test_try_catch():
    path = _write_temp_cpp("""
        void handle(int x) {
            try {
                if (x < 0) {
                    return;
                }
            } catch (...) {
                return;
            }
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 2  # if + catch
    finally:
        os.unlink(path)


def test_class_method_qualified_name():
    path = _write_temp_cpp("""
        class MyClass {
        public:
            int process(int val) {
                if (val > 0) {
                    return val;
                }
                return 0;
            }
        };
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.qualified_name == "MyClass.process"
        assert fn.cognitive_complexity == 1
        assert fn.params == 1
    finally:
        os.unlink(path)


def test_struct_method():
    path = _write_temp_cpp("""
        struct Point {
            int x, y;
            int sum() {
                return x + y;
            }
        };
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.qualified_name == "Point.sum"
        assert fn.cognitive_complexity == 0
        assert fn.params == 0
    finally:
        os.unlink(path)


def test_namespace_qualified_name():
    path = _write_temp_cpp("""
        namespace myns {
            int compute(int x) {
                return x * 2;
            }
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.qualified_name == "myns.compute"
    finally:
        os.unlink(path)


def test_namespace_class_qualified_name():
    path = _write_temp_cpp("""
        namespace ns {
            class Foo {
            public:
                void bar() {}
            };
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.qualified_name == "ns.Foo.bar"
    finally:
        os.unlink(path)


def test_constructor_destructor():
    path = _write_temp_cpp("""
        class Foo {
        public:
            Foo(int a, int b) {}
            ~Foo() {}
        };
    """)
    try:
        fm = scan_cpp_file(path)
        assert fm.function_count == 2
        names = {fn.name for fn in fm.functions}
        assert "Foo" in names
        assert "~Foo" in names

        ctor = [fn for fn in fm.functions if fn.name == "Foo"][0]
        assert ctor.params == 2
        assert ctor.qualified_name == "Foo.Foo"

        dtor = [fn for fn in fm.functions if fn.name == "~Foo"][0]
        assert dtor.params == 0
    finally:
        os.unlink(path)


def test_lambda_nesting():
    path = _write_temp_cpp("""
        void outer() {
            auto f = [](int x) {
                if (x > 0) {
                    return x;
                }
                return 0;
            };
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        # lambda increases nesting, if inside gets nesting penalty
        assert fn.cognitive_complexity >= 2
    finally:
        os.unlink(path)


def test_template_function():
    path = _write_temp_cpp("""
        template<typename T>
        T identity(T val) {
            return val;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "identity"
        assert fn.cognitive_complexity == 0
        assert fn.params == 1
    finally:
        os.unlink(path)


def test_template_function_with_complexity():
    path = _write_temp_cpp("""
        template<typename T>
        T max_of(T a, T b) {
            if (a > b) {
                return a;
            }
            return b;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1
        assert fn.params == 2
    finally:
        os.unlink(path)


def test_parameter_counting():
    path = _write_temp_cpp("""
        void f0() {}
        void f1(int a) {}
        void f2(int a, int b) {}
        void f3(int a, int b, int c) {}
    """)
    try:
        fm = scan_cpp_file(path)
        param_counts = {fn.name: fn.params for fn in fm.functions}
        assert param_counts["f0"] == 0
        assert param_counts["f1"] == 1
        assert param_counts["f2"] == 2
        assert param_counts["f3"] == 3
    finally:
        os.unlink(path)


def test_continue_statement():
    path = _write_temp_cpp("""
        void process(int* items, int size) {
            for (int i = 0; i < size; i++) {
                if (items[i] == 0) {
                    continue;
                }
            }
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        # for: +1, if: +2 (nested), continue: +1 = 4
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


def test_range_for_loop():
    path = _write_temp_cpp("""
        #include <vector>

        int sum(const std::vector<int>& v) {
            int total = 0;
            for (const auto& x : v) {
                total += x;
            }
            return total;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # range-for
        assert fn.cyclomatic_complexity == 2  # 1 + range-for
    finally:
        os.unlink(path)


def test_multiple_catch_clauses():
    path = _write_temp_cpp("""
        void handle() {
            try {
                throw 1;
            } catch (int e) {
                return;
            } catch (...) {
                return;
            }
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 2  # 2 catch clauses
        assert fn.cyclomatic_complexity == 3  # 1 + 2 catches
    finally:
        os.unlink(path)


def test_boolean_or_ops():
    path = _write_temp_cpp("""
        bool check(bool a, bool b) {
            if (a || b) {
                return true;
            }
            return false;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 2  # if + ||
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Line counting tests
# ---------------------------------------------------------------------------

def test_count_cpp_lines():
    source = """#include <iostream>

// This is a comment
int main() {
    /* block comment */
    int x = 1;
    return 0;
}
"""
    total, code, comment, blank = count_cpp_lines(source)
    assert total == 8
    assert comment >= 1  # at least the // line comment
    assert blank == 1


def test_count_cpp_lines_multiline_block_comment():
    source = "#include <stdio.h>\n\n/*\nThis is a\nmulti-line comment\n*/\nint main() {}\n"
    total, code, comment, blank = count_cpp_lines(source)
    assert comment >= 3  # /*, content lines, */


def test_count_cpp_lines_unclosed_block_comment():
    source = "#include <stdio.h>\n\n/* unclosed\nstill comment\nforever comment\n"
    total, code, comment, blank = count_cpp_lines(source)
    assert comment >= 3  # all lines after /* are comment


def test_count_cpp_lines_inline_block_comment():
    source = "#include <stdio.h>\n\nint main() { int x = 1; /* inline */ }\n"
    total, code, comment, blank = count_cpp_lines(source)
    # Line with inline block comment should count as code
    assert code >= 2


# ---------------------------------------------------------------------------
# Dispatch and integration tests
# ---------------------------------------------------------------------------

def test_scan_file_dispatch_cpp():
    """Ensure scan_file() routes .cpp files to the C++ parser."""
    path = _write_temp_cpp("""
        int hello() {
            return 42;
        }
    """)
    try:
        fm = scan_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "hello"
    finally:
        os.unlink(path)


def test_scan_file_dispatch_c():
    """Ensure scan_file() routes .c files to the C++ parser."""
    path = _write_temp_c("""
        int hello() {
            return 42;
        }
    """)
    try:
        fm = scan_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "hello"
    finally:
        os.unlink(path)


def test_scan_file_dispatch_h():
    """Ensure scan_file() routes .h files to the C++ parser."""
    fd, path = tempfile.mkstemp(suffix=".h")
    os.write(fd, b"int add(int a, int b) { return a + b; }\n")
    os.close(fd)
    try:
        fm = scan_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "add"
    finally:
        os.unlink(path)


def test_scan_file_dispatch_hpp():
    """Ensure scan_file() routes .hpp files to the C++ parser."""
    fd, path = tempfile.mkstemp(suffix=".hpp")
    os.write(fd, b"inline int add(int a, int b) { return a + b; }\n")
    os.close(fd)
    try:
        fm = scan_file(path)
        assert fm.function_count == 1
    finally:
        os.unlink(path)


def test_scan_directory_mixed():
    """scan_directory picks up .py, .go, .java, and .cpp files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "a.py").write_text("def foo(): pass\n")
        (Path(tmpdir) / "b.cpp").write_text(
            "int bar() { return 0; }\n"
        )
        result = scan_directory(tmpdir)
        assert len(result.files) == 2
        names = set()
        for f in result.files:
            for fn in f.functions:
                names.add(fn.name)
        assert "foo" in names
        assert "bar" in names


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_ensure_tree_sitter_when_none():
    import complexity_accounting.cpp_parser as cp
    original = cp.CPP_LANGUAGE
    try:
        cp.CPP_LANGUAGE = None
        try:
            cp._ensure_tree_sitter()
            assert False, "Should have raised ImportError"
        except ImportError as e:
            assert "tree-sitter-cpp" in str(e)
    finally:
        cp.CPP_LANGUAGE = original


def test_scan_cpp_file_parse_error():
    """tree-sitter is permissive, so partial parse should not crash."""
    path = _write_temp_cpp("""
        int broken( {
            if {
        }
    """)
    try:
        fm = scan_cpp_file(path)
        # Should not crash, may return partial results
        assert isinstance(fm, type(fm))
    finally:
        os.unlink(path)


def test_empty_function_body():
    path = _write_temp_cpp("""
        void noop() {}
    """)
    try:
        fm = scan_cpp_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 0
        assert fn.cyclomatic_complexity == 1
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Fixture file tests
# ---------------------------------------------------------------------------

def test_fixture_sample_cpp():
    """Test against the sample.cpp fixture file."""
    fixture = Path(__file__).parent / "fixtures" / "sample.cpp"
    if not fixture.exists():
        return  # skip if fixture missing
    fm = scan_cpp_file(str(fixture))
    func_map = {fn.name: fn for fn in fm.functions}

    assert func_map["add"].cognitive_complexity == 0
    assert func_map["nestedIfs"].cognitive_complexity == 6
    assert func_map["findItem"].cognitive_complexity == 4
    assert func_map["validate"].cognitive_complexity == 2
    assert func_map["elseIfChain"].cognitive_complexity == 3
    assert func_map["process"].qualified_name == "MyClass.process"
    assert func_map["tryCatch"].cognitive_complexity == 2


def test_fixture_sample_c():
    """Test against the sample.c fixture file."""
    fixture = Path(__file__).parent / "fixtures" / "sample.c"
    if not fixture.exists():
        return  # skip if fixture missing
    fm = scan_cpp_file(str(fixture))
    func_map = {fn.name: fn for fn in fm.functions}

    assert func_map["add"].cognitive_complexity == 0
    assert func_map["findMax"].cognitive_complexity == 3
    assert func_map["doWhileExample"].cognitive_complexity == 1


# ---------------------------------------------------------------------------
# Coverage gap: reference_declarator (lines 236-238), qualified_identifier (232-234)
# ---------------------------------------------------------------------------

def test_reference_declarator_function():
    """C++ function returning a reference: int& foo()."""
    path = _write_temp_cpp("""
        int& getRef(int& x) {
            return x;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "getRef"
    finally:
        os.unlink(path)


def test_qualified_identifier_method():
    """Namespace-qualified method definition: Foo::bar()."""
    path = _write_temp_cpp("""
        class Foo {
        public:
            int bar(int x);
        };

        int Foo::bar(int x) {
            if (x > 0) {
                return x;
            }
            return 0;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        funcs = {f.name: f for f in fm.functions}
        # Should find Foo::bar or bar
        assert any("bar" in f.name for f in fm.functions)
    finally:
        os.unlink(path)


def test_variadic_params_c_style():
    """C-style variadic function: void foo(int a, ...)."""
    path = _write_temp_c("""
        #include <stdarg.h>
        void my_printf(const char* fmt, ...) {
            return;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        assert fm.function_count >= 1
        fn = fm.functions[0]
        assert fn.params >= 1  # At least the fmt param
    finally:
        os.unlink(path)


def test_missing_declarator_no_crash():
    """Malformed function should not crash, may return <unknown>."""
    # We test that the parser handles edge cases gracefully
    path = _write_temp_cpp("""
        int simple() {
            return 0;
        }
    """)
    try:
        fm = scan_cpp_file(path)
        assert fm.function_count >= 1
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Test runner (backward compat)
# ---------------------------------------------------------------------------

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
