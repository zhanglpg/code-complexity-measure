"""Tests for the complexity scanner."""
import textwrap
import tempfile
import os
from pathlib import Path

from complexity_accounting.scanner import scan_file, scan_directory, ScanResult


def _write_temp(source: str) -> str:
    """Write source to a temp .py file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


def test_simple_function():
    path = _write_temp("""
        def add(a, b):
            return a + b
    """)
    try:
        fm = scan_file(path)
        assert fm.function_count == 1
        fn = fm.functions[0]
        assert fn.name == "add"
        assert fn.cognitive_complexity == 0
        assert fn.cyclomatic_complexity == 1
        assert fn.params == 2
    finally:
        os.unlink(path)


def test_nested_ifs():
    path = _write_temp("""
        def check(x, y, z):
            if x > 0:        # +1
                if y > 0:    # +2 (1 + nesting=1)
                    if z > 0: # +3 (1 + nesting=2)
                        return True
            return False
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 6  # 1 + 2 + 3
        assert fn.max_nesting >= 3
    finally:
        os.unlink(path)


def test_for_with_break():
    path = _write_temp("""
        def find(items, target):
            for item in items:   # +1
                if item == target:  # +2 (1 + nesting=1)
                    break           # +1
            return None
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 4  # 1 + 2 + 1
    finally:
        os.unlink(path)


def test_boolean_ops():
    path = _write_temp("""
        def validate(a, b, c):
            if a and b and c:   # +1 (if) + 1 (boolean sequence)
                return True
            return False
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity >= 2
    finally:
        os.unlink(path)


def test_class_method():
    path = _write_temp("""
        class Foo:
            def bar(self, x):
                if x:
                    return True
                return False
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.qualified_name == "Foo.bar"
        assert fn.params == 1  # 'self' excluded
    finally:
        os.unlink(path)


def test_try_except():
    path = _write_temp("""
        def risky(x):
            try:
                return int(x)
            except ValueError:     # +1
                return 0
            except TypeError:      # +1
                return -1
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 2
    finally:
        os.unlink(path)


def test_while_continue():
    path = _write_temp("""
        def process(items):
            i = 0
            while i < len(items):   # +1
                if items[i] is None: # +2 (1 + nesting=1)
                    i += 1
                    continue         # +1
                handle(items[i])
                i += 1
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.cognitive_complexity == 4  # 1 + 2 + 1
    finally:
        os.unlink(path)


def test_net_complexity_score():
    """NCS formula: avg_cognitive * (1 + hotspot_ratio)"""
    result = ScanResult()
    # Empty scan
    assert result.net_complexity_score == 0.0


def test_scan_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple Python file
        p = Path(tmpdir) / "example.py"
        p.write_text(textwrap.dedent("""
            def simple():
                return 1

            def moderate(x, y):
                if x > 0:
                    if y > 0:
                        return x + y
                return 0
        """))
        
        result = scan_directory(tmpdir)
        assert len(result.files) == 1
        assert result.total_functions == 2


def test_risk_levels():
    path = _write_temp("""
        def low():
            if True:
                pass

        def very_high():
            if True:
                if True:
                    if True:
                        if True:
                            for x in []:
                                while True:
                                    if True:
                                        if True:
                                            pass
    """)
    try:
        fm = scan_file(path)
        assert fm.functions[0].risk_level == "low"
        assert fm.functions[1].risk_level in ("high", "very_high")
    finally:
        os.unlink(path)


if __name__ == "__main__":
    # Simple test runner
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
