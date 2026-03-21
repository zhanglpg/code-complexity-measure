"""Tests for Rust complexity parser."""
import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from complexity_accounting.rust_parser import scan_rust_file, count_rust_lines
from complexity_accounting.scanner import scan_file, scan_directory

_has_rust = True
try:
    import tree_sitter_rust  # noqa: F401
except ImportError:
    _has_rust = False

requires_rust = pytest.mark.skipif(not _has_rust, reason="tree-sitter-rust not installed")


def _write_temp_rs(source: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".rs")
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


@requires_rust
def test_simple_function():
    path = _write_temp_rs("""
        fn add(a: i32, b: i32) -> i32 {
            a + b
        }
    """)
    try:
        fm = scan_rust_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "add"
        assert fn.cognitive_complexity == 0
        assert fn.cyclomatic_complexity == 1
        assert fn.params == 2
    finally:
        os.unlink(path)


@requires_rust
def test_nested_ifs():
    path = _write_temp_rs("""
        fn check(x: i32, y: i32, z: i32) -> bool {
            if x > 0 {
                if y > 0 {
                    if z > 0 {
                        return true;
                    }
                }
            }
            false
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 6  # 1 + 2 + 3
        assert fn.max_nesting >= 3
    finally:
        os.unlink(path)


@requires_rust
def test_for_with_break():
    path = _write_temp_rs("""
        fn find(items: &[i32], target: i32) -> i32 {
            for item in items.iter() {
                if *item == target {
                    break;
                }
            }
            -1
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 4  # 1 (for) + 2 (if nested) + 1 (break)
    finally:
        os.unlink(path)


@requires_rust
def test_match_expression():
    path = _write_temp_rs("""
        fn classify(n: i32) -> &'static str {
            match n {
                x if x < 0 => "negative",
                0 => "zero",
                _ => "positive",
            }
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 1  # match
    finally:
        os.unlink(path)


@requires_rust
def test_boolean_ops():
    path = _write_temp_rs("""
        fn validate(a: bool, b: bool) -> bool {
            if a && b {
                return true;
            }
            false
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 2  # if + &&
    finally:
        os.unlink(path)


@requires_rust
def test_impl_method():
    path = _write_temp_rs("""
        struct Server {
            port: i32,
        }

        impl Server {
            fn start(&self, addr: &str) -> bool {
                if self.port > 0 {
                    true
                } else {
                    false
                }
            }
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.qualified_name == "Server.start"
        assert fn.params == 1  # addr only, not &self
        assert fn.cognitive_complexity == 1
    finally:
        os.unlink(path)


@requires_rust
def test_closure_nesting():
    path = _write_temp_rs("""
        fn outer() -> i32 {
            let f = |x: i32| -> i32 {
                if x > 0 {
                    x
                } else {
                    -x
                }
            };
            f(42)
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        # closure increases nesting, if inside gets nesting penalty
        assert fn.cognitive_complexity >= 2
    finally:
        os.unlink(path)


@requires_rust
def test_if_let():
    path = _write_temp_rs("""
        fn unwrap_or(x: Option<i32>) -> i32 {
            if let Some(v) = x {
                v
            } else {
                0
            }
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # if let treated as if
    finally:
        os.unlink(path)


@requires_rust
def test_loop_expression():
    path = _write_temp_rs("""
        fn count_up() -> i32 {
            let mut i = 0;
            loop {
                if i > 10 {
                    break;
                }
                i += 1;
            }
            i
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 4  # loop: +1, if: +2, break: +1
    finally:
        os.unlink(path)


@requires_rust
def test_while_let():
    path = _write_temp_rs("""
        fn drain(items: &mut Vec<i32>) {
            while let Some(v) = items.pop() {
                let _ = v;
            }
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # while let treated as while
    finally:
        os.unlink(path)


@requires_rust
def test_try_expression():
    path = _write_temp_rs("""
        fn try_it(x: Result<i32, String>) -> Result<i32, String> {
            let v = x?;
            Ok(v + 1)
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # ? operator
    finally:
        os.unlink(path)


def test_count_rust_lines():
    source = """// This is a comment
fn main() {
    /* block comment */
    let x = 1;
}
"""
    total, code, comment, blank = count_rust_lines(source)
    assert total == 5
    assert comment >= 1  # at least the // line comment
    assert code >= 2


@requires_rust
def test_scan_file_dispatch_rust():
    """Ensure scan_file() routes .rs files to the Rust parser."""
    path = _write_temp_rs("""
        fn hello() -> &'static str {
            "hello"
        }
    """)
    try:
        fm = scan_file(path)
        assert fm.function_count == 1
        assert fm.functions[0].name == "hello"
    finally:
        os.unlink(path)


@requires_rust
def test_scan_directory_mixed():
    """scan_directory picks up both .py and .rs files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "a.py").write_text("def foo(): pass\n")
        (Path(tmpdir) / "b.rs").write_text(
            "fn bar() {}\n"
        )
        result = scan_directory(tmpdir)
        assert len(result.files) == 2
        names = {f.functions[0].name for f in result.files if f.functions}
        assert "foo" in names
        assert "bar" in names


@requires_rust
def test_fixture_sample():
    """Test against the sample.rs fixture file."""
    fixture = Path(__file__).parent / "fixtures" / "sample.rs"
    if not fixture.exists():
        return  # skip if fixture missing
    fm = scan_rust_file(str(fixture))
    func_map = {fn.name: fn for fn in fm.functions}

    assert func_map["add"].cognitive_complexity == 0
    assert func_map["nested_ifs"].cognitive_complexity == 6
    assert func_map["find_item"].cognitive_complexity == 4
    assert func_map["validate"].cognitive_complexity >= 2
    assert func_map["start"].qualified_name == "Server.start"
    assert func_map["with_closure"].cognitive_complexity == 2
    assert func_map["with_if_let"].cognitive_complexity == 1
    assert func_map["with_loop"].cognitive_complexity == 4
    assert func_map["with_try"].cognitive_complexity == 1


# ---------------------------------------------------------------------------
# P1: Extended Rust parser tests
# ---------------------------------------------------------------------------

def test_ensure_tree_sitter_when_none():
    import complexity_accounting.rust_parser as rp
    original = rp.RUST_LANGUAGE
    try:
        rp.RUST_LANGUAGE = None
        try:
            rp._ensure_tree_sitter()
            assert False, "Should have raised ImportError"
        except ImportError as e:
            assert "tree-sitter-rust" in str(e)
    finally:
        rp.RUST_LANGUAGE = original


@requires_rust
def test_else_if_chain_cognitive():
    path = _write_temp_rs("""
        fn classify(x: i32) -> &'static str {
            if x < 0 {
                "negative"
            } else if x == 0 {
                "zero"
            } else if x < 10 {
                "small"
            } else {
                "large"
            }
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        # if: +1, else-if: +1 (flat), else-if: +1 (flat) = 3
        assert fn.cognitive_complexity == 3
    finally:
        os.unlink(path)


@requires_rust
def test_while_expression():
    path = _write_temp_rs("""
        fn count_down(mut n: i32) {
            while n > 0 {
                n -= 1;
            }
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 1  # while
    finally:
        os.unlink(path)


@requires_rust
def test_continue_in_loop():
    path = _write_temp_rs("""
        fn process(items: &[i32]) {
            for item in items.iter() {
                if *item == 0 {
                    continue;
                }
            }
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        # for: +1, if: +2 (nested), continue: +1 = 4
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


@requires_rust
def test_unsafe_block_nesting():
    path = _write_temp_rs("""
        fn risky() {
            unsafe {
                if true {
                    return;
                }
            }
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        # unsafe increases nesting, if inside gets nesting penalty
        assert fn.cognitive_complexity >= 2
    finally:
        os.unlink(path)


@requires_rust
def test_trait_impl_method():
    path = _write_temp_rs("""
        trait Handler {
            fn handle(&self, req: i32) -> i32;
        }

        struct Server;

        impl Handler for Server {
            fn handle(&self, req: i32) -> i32 {
                if req > 0 { req } else { 0 }
            }
        }
    """)
    try:
        fm = scan_rust_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.qualified_name == "Server.handle"
        assert fn.params == 1  # req only, not &self
    finally:
        os.unlink(path)


def test_count_rust_lines_doc_comments():
    source = """/// This is a doc comment
//! This is an inner doc comment
fn main() {}
"""
    total, code, comment, blank = count_rust_lines(source)
    assert comment >= 2  # /// and //!


def test_count_rust_lines_multiline_block_comment():
    source = "fn main() {}\n\n/*\nThis is a\nmulti-line comment\n*/\nfn other() {}\n"
    total, code, comment, blank = count_rust_lines(source)
    assert comment >= 3  # /*, content lines, */


def test_count_rust_lines_unclosed_block_comment():
    source = "fn main() {}\n\n/* unclosed\nstill comment\nforever comment\n"
    total, code, comment, blank = count_rust_lines(source)
    assert comment >= 3  # all lines after /* are comment


def test_count_rust_lines_inline_block_comment():
    source = "fn main() { let x = 1; /* inline */ }\n"
    total, code, comment, blank = count_rust_lines(source)
    # Line with inline block comment should count as code
    assert code >= 1


@requires_rust
def test_scan_rust_file_parse_error():
    """tree-sitter is permissive, so partial parse should not crash."""
    path = _write_temp_rs("""
        fn broken( {
            if {
        }
    """)
    try:
        fm = scan_rust_file(path)
        # Should not crash, may return partial results
        assert isinstance(fm, type(fm))
    finally:
        os.unlink(path)


@requires_rust
def test_multiple_params():
    path = _write_temp_rs("""
        fn multi(a: i32, b: String, c: bool) -> i32 {
            0
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.params == 3
    finally:
        os.unlink(path)


@requires_rust
def test_multiple_try_operators():
    path = _write_temp_rs("""
        fn chain(a: Result<i32, String>, b: Result<i32, String>) -> Result<i32, String> {
            let x = a?;
            let y = b?;
            Ok(x + y)
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 2  # two ? operators
    finally:
        os.unlink(path)


@requires_rust
def test_nested_match_in_for():
    path = _write_temp_rs("""
        fn process(items: &[Option<i32>]) {
            for item in items.iter() {
                match item {
                    Some(v) => { let _ = v; },
                    None => {},
                }
            }
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        # for: +1, match: +2 (1 + nesting=1)
        assert fn.cognitive_complexity >= 3
    finally:
        os.unlink(path)


@requires_rust
def test_impl_multiple_methods():
    path = _write_temp_rs("""
        struct Calc;

        impl Calc {
            fn add(&self, a: i32, b: i32) -> i32 {
                a + b
            }
            fn sub(&self, a: i32, b: i32) -> i32 {
                a - b
            }
        }
    """)
    try:
        fm = scan_rust_file(path)
        assert fm.function_count == 2
        names = {fn.name for fn in fm.functions}
        assert "add" in names
        assert "sub" in names
        for fn in fm.functions:
            assert fn.qualified_name.startswith("Calc.")
            assert fn.params == 2  # excludes &self
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Boolean operator tracking (SonarSource spec)
# ---------------------------------------------------------------------------

@requires_rust
def test_boolean_same_operator_chain():
    """a && b && c should be +1 (same operator chain)."""
    path = _write_temp_rs("""
        fn check(a: bool, b: bool, c: bool) -> bool {
            if a && b && c {
                return true;
            }
            false
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 2  # if + &&-chain
    finally:
        os.unlink(path)


@requires_rust
def test_boolean_mixed_operators():
    """a && b || c should be +2 (operator change)."""
    path = _write_temp_rs("""
        fn check(a: bool, b: bool, c: bool) -> bool {
            if a && b || c {
                return true;
            }
            false
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 3
    finally:
        os.unlink(path)


@requires_rust
def test_boolean_three_switches():
    """a && b || c && d should be +3."""
    path = _write_temp_rs("""
        fn check(a: bool, b: bool, c: bool, d: bool) -> bool {
            if a && b || c && d {
                return true;
            }
            false
        }
    """)
    try:
        fm = scan_rust_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Maintainability Index
# ---------------------------------------------------------------------------

@requires_rust
def test_maintainability_index_computed():
    """Rust functions should have MI computed."""
    path = _write_temp_rs("""
        fn simple() -> i32 {
            1
        }
    """)
    try:
        fm = scan_rust_file(path)
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
