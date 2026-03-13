"""Tests for Go complexity parser."""
import os
import tempfile
import textwrap
from pathlib import Path

from complexity_accounting.go_parser import scan_go_file, count_go_lines
from complexity_accounting.scanner import scan_file, scan_directory


def _write_temp_go(source: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".go")
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


def test_simple_function():
    path = _write_temp_go("""
        package main

        func Add(a int, b int) int {
            return a + b
        }
    """)
    try:
        fm = scan_go_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "Add"
        assert fn.cognitive_complexity == 0
        assert fn.cyclomatic_complexity == 1
        assert fn.params == 2
    finally:
        os.unlink(path)


def test_nested_ifs():
    path = _write_temp_go("""
        package main

        func Check(x, y, z int) bool {
            if x > 0 {
                if y > 0 {
                    if z > 0 {
                        return true
                    }
                }
            }
            return false
        }
    """)
    try:
        fm = scan_go_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 6  # 1 + 2 + 3
        assert fn.max_nesting >= 3
    finally:
        os.unlink(path)


def test_for_with_break():
    path = _write_temp_go("""
        package main

        func Find(items []string, target string) int {
            for i, item := range items {
                if item == target {
                    break
                }
                _ = i
            }
            return -1
        }
    """)
    try:
        fm = scan_go_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 4  # 1 (for) + 2 (if nested) + 1 (break)
    finally:
        os.unlink(path)


def test_switch_statement():
    path = _write_temp_go("""
        package main

        func Classify(n int) string {
            switch {
            case n < 0:
                return "negative"
            case n == 0:
                return "zero"
            default:
                return "positive"
            }
        }
    """)
    try:
        fm = scan_go_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 1  # switch + cases
    finally:
        os.unlink(path)


def test_boolean_ops():
    path = _write_temp_go("""
        package main

        func Validate(a, b bool) bool {
            if a && b {
                return true
            }
            return false
        }
    """)
    try:
        fm = scan_go_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 2  # if + &&
    finally:
        os.unlink(path)


def test_method_with_receiver():
    path = _write_temp_go("""
        package main

        type Server struct{}

        func (s *Server) Start(port int) error {
            if port <= 0 {
                return nil
            }
            return nil
        }
    """)
    try:
        fm = scan_go_file(path)
        fn = fm.functions[0]
        assert fn.qualified_name == "Server.Start"
        assert fn.params == 1  # port only, not receiver
        assert fn.cognitive_complexity == 1
    finally:
        os.unlink(path)


def test_goroutine():
    path = _write_temp_go("""
        package main

        func Launch() {
            go func() {}()
        }
    """)
    try:
        fm = scan_go_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 1  # go statement
    finally:
        os.unlink(path)


def test_defer():
    path = _write_temp_go("""
        package main

        func Cleanup() {
            defer close()
        }

        func close() {}
    """)
    try:
        fm = scan_go_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 1  # defer
    finally:
        os.unlink(path)


def test_continue():
    path = _write_temp_go("""
        package main

        func Process(items []int) {
            for _, item := range items {
                if item == 0 {
                    continue
                }
            }
        }
    """)
    try:
        fm = scan_go_file(path)
        fn = fm.functions[0]
        # for: +1, if: +2 (nested), continue: +1 = 4
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


def test_count_go_lines():
    source = """package main

// This is a comment
func main() {
    /* block comment */
    x := 1
}
"""
    total, code, comment, blank = count_go_lines(source)
    assert total == 7
    assert comment >= 1  # at least the // line comment
    assert blank == 1


def test_scan_file_dispatch_go():
    """Ensure scan_file() routes .go files to the Go parser."""
    path = _write_temp_go("""
        package main

        func Hello() string {
            return "hello"
        }
    """)
    try:
        fm = scan_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "Hello"
    finally:
        os.unlink(path)


def test_scan_directory_mixed():
    """scan_directory picks up both .py and .go files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "a.py").write_text("def foo(): pass\n")
        (Path(tmpdir) / "b.go").write_text(
            "package main\nfunc Bar() {}\n"
        )
        result = scan_directory(tmpdir)
        assert len(result.files) == 2
        names = {f.functions[0].name for f in result.files if f.functions}
        assert "foo" in names
        assert "Bar" in names


def test_fixture_sample():
    """Test against the sample.go fixture file."""
    fixture = Path(__file__).parent / "fixtures" / "sample.go"
    if not fixture.exists():
        return  # skip if fixture missing
    fm = scan_go_file(str(fixture))
    func_map = {fn.name: fn for fn in fm.functions}

    assert func_map["Add"].cognitive_complexity == 0
    assert func_map["NestedIfs"].cognitive_complexity == 6
    assert func_map["FindItem"].cognitive_complexity == 4
    assert func_map["Validate"].cognitive_complexity >= 2
    assert func_map["Start"].qualified_name == "Server.Start"


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
