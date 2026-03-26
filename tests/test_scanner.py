"""Tests for the complexity scanner."""
import textwrap
import tempfile
import os
from pathlib import Path

import pytest

from conftest import requires_go, requires_java, requires_js

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


# ---------------------------------------------------------------------------
# P1: FunctionMetrics extended tests
# ---------------------------------------------------------------------------

def test_get_risk_level_custom_boundaries():
    from complexity_accounting.scanner import FunctionMetrics
    fn = FunctionMetrics("f", "f", "x.py", 1, 5, cognitive_complexity=12)
    assert fn.get_risk_level(low=5, moderate=15, high=25) == "moderate"
    assert fn.get_risk_level(low=5, moderate=10, high=15) == "high"


def test_get_risk_level_very_high():
    from complexity_accounting.scanner import FunctionMetrics
    fn = FunctionMetrics("f", "f", "x.py", 1, 5, cognitive_complexity=25)
    assert fn.get_risk_level() == "very_high"


# ---------------------------------------------------------------------------
# P1: FileMetrics extended tests
# ---------------------------------------------------------------------------

def test_hotspots_with_threshold():
    from complexity_accounting.scanner import FunctionMetrics, FileMetrics
    fns = [
        FunctionMetrics("a", "a", "x.py", 1, 5, cognitive_complexity=5),
        FunctionMetrics("b", "b", "x.py", 6, 10, cognitive_complexity=10),
        FunctionMetrics("c", "c", "x.py", 11, 15, cognitive_complexity=15),
        FunctionMetrics("d", "d", "x.py", 16, 20, cognitive_complexity=20),
    ]
    fm = FileMetrics("x.py", fns)
    hotspots = fm.hotspots(threshold=12)
    assert len(hotspots) == 2
    assert all(h.cognitive_complexity >= 12 for h in hotspots)


def test_hotspots_default_threshold():
    from complexity_accounting.scanner import FunctionMetrics, FileMetrics
    fns = [
        FunctionMetrics("a", "a", "x.py", 1, 5, cognitive_complexity=5),
        FunctionMetrics("b", "b", "x.py", 6, 10, cognitive_complexity=10),
        FunctionMetrics("c", "c", "x.py", 11, 15, cognitive_complexity=15),
    ]
    fm = FileMetrics("x.py", fns)
    hotspots = fm.hotspots()
    assert len(hotspots) == 2  # 10 and 15 (>= 10)


def test_file_metrics_properties():
    from complexity_accounting.scanner import FunctionMetrics, FileMetrics
    fns = [
        FunctionMetrics("a", "a", "x.py", 1, 5, cognitive_complexity=4, cyclomatic_complexity=2),
        FunctionMetrics("b", "b", "x.py", 6, 10, cognitive_complexity=8, cyclomatic_complexity=3),
    ]
    fm = FileMetrics("x.py", fns)
    assert fm.total_cognitive == 12
    assert fm.total_cyclomatic == 5
    assert fm.avg_cognitive == 6.0
    assert fm.max_cognitive == 8
    assert fm.function_count == 2


def test_file_metrics_empty():
    from complexity_accounting.scanner import FileMetrics
    fm = FileMetrics("empty.py")
    assert fm.avg_cognitive == 0.0
    assert fm.max_cognitive == 0
    assert fm.function_count == 0


# ---------------------------------------------------------------------------
# P1: ScanResult extended tests
# ---------------------------------------------------------------------------

def test_compute_ncs_with_config():
    from complexity_accounting.config import Config
    path = _write_temp("""
        def simple():
            return 1

        def complex_func(x, y):
            if x:
                if y:
                    for i in range(10):
                        if i > 5:
                            return i
            return 0
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        config = Config(weight_cognitive=0.5, weight_cyclomatic=0.5, hotspot_threshold=5)
        ncs_with = result.compute_ncs(config, churn_factor=1.2, coupling_factor=1.5)
        ncs_legacy = result.net_complexity_score
        # They should differ since we're using different weights and factors
        assert ncs_with != ncs_legacy
        assert ncs_with > 0
    finally:
        os.unlink(path)


def test_compute_ncs_zero_functions():
    result = ScanResult()
    assert result.compute_ncs() == 0.0


def test_compute_ncs_legacy_defaults():
    """compute_ncs() without config uses cognitive-only weights."""
    path = _write_temp("""
        def foo(x):
            if x:
                return True
            return False
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        # Legacy property and compute_ncs() without config should match
        assert result.net_complexity_score == result.compute_ncs()
    finally:
        os.unlink(path)


def test_scan_result_to_dict_structure():
    path = _write_temp("""
        def foo():
            return 1
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        d = result.to_dict()
        assert "summary" in d
        assert "files" in d
        s = d["summary"]
        for key in ("files_scanned", "total_functions", "total_cognitive_complexity",
                     "total_cyclomatic_complexity", "net_complexity_score",
                     "avg_cognitive_per_function", "hotspot_count"):
            assert key in s, f"Missing key: {key}"
    finally:
        os.unlink(path)


def test_scan_result_to_json_roundtrip():
    import json
    path = _write_temp("""
        def foo():
            return 1
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        parsed = json.loads(result.to_json())
        assert parsed == result.to_dict()
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# P1: count_lines tests
# ---------------------------------------------------------------------------

def test_count_lines_multiline_docstring():
    from complexity_accounting.scanner import count_lines
    source = '''def foo():
    """
    This is a
    multi-line docstring.
    """
    return 1
'''
    total, code, comment, blank = count_lines(source)
    assert comment == 4  # opening """, two content lines, closing """
    assert code == 2  # def foo(): and return 1


def test_count_lines_single_quotes_docstring():
    from complexity_accounting.scanner import count_lines
    source = "def foo():\n    '''Single quotes docstring.'''\n    return 1\n"
    total, code, comment, blank = count_lines(source)
    assert comment == 1  # single-line '''...'''


def test_count_lines_mixed_content():
    from complexity_accounting.scanner import count_lines
    source = """# Comment
def foo():
    '''docstring'''
    x = 1

    return x
"""
    total, code, comment, blank = count_lines(source)
    assert total == 6
    assert comment == 2  # # Comment + docstring
    assert blank == 1  # empty line
    assert code == 3  # def, x=1, return


# ---------------------------------------------------------------------------
# P1: Cognitive complexity edge cases
# ---------------------------------------------------------------------------

def test_cognitive_nested_lambda():
    path = _write_temp("""
        def outer():
            f = lambda x: x if x > 0 else -x
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # Lambda increases nesting, ternary (IfExp) adds +1
        assert fn.cognitive_complexity >= 1
    finally:
        os.unlink(path)


def test_cognitive_with_statement_nesting():
    path = _write_temp("""
        def read_file():
            with open("x") as f:
                if f:
                    return f.read()
            return None
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # with adds nesting, if inside gets +2 (1 + nesting=1)
        assert fn.cognitive_complexity == 2
    finally:
        os.unlink(path)


def test_cognitive_ternary_in_nesting():
    path = _write_temp("""
        def compute(items):
            for item in items:
                if item > 0:
                    result = item if item < 100 else 100
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # for: +1, if: +2 (nested), ternary: +1 (flat, no nesting penalty)
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# P1: Cyclomatic complexity tests
# ---------------------------------------------------------------------------

def test_cyclomatic_assert():
    path = _write_temp("""
        def validate(x):
            assert x > 0
            return x
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.cyclomatic_complexity == 2  # baseline 1 + assert
    finally:
        os.unlink(path)


def test_cyclomatic_mixed_boolean():
    path = _write_temp("""
        def check(a, b, c):
            if a and b or c:
                return True
            return False
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # baseline 1 + if + and + or = 4
        assert fn.cyclomatic_complexity >= 3
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# P1: Error handling tests
# ---------------------------------------------------------------------------

def test_scan_file_syntax_error():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def broken(:\n    pass\n")
    os.close(fd)
    try:
        fm = scan_file(path)
        assert fm.functions == []
        assert fm.total_lines > 0
    finally:
        os.unlink(path)


def test_scan_directory_exclusion_patterns():
    with tempfile.TemporaryDirectory() as tmpdir:
        venv_dir = Path(tmpdir) / "venv" / "lib"
        venv_dir.mkdir(parents=True)
        (venv_dir / "pkg.py").write_text("def venv_func(): pass\n")
        (Path(tmpdir) / "app.py").write_text("def app_func(): pass\n")

        result = scan_directory(tmpdir)
        paths = [f.path for f in result.files]
        assert any("app.py" in p for p in paths)
        assert not any("venv" in p for p in paths)


def test_scan_directory_custom_exclusion():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "test_foo.py").write_text("def t(): pass\n")
        (Path(tmpdir) / "app.py").write_text("def a(): pass\n")

        result = scan_directory(tmpdir, exclude_patterns=["**/test_*"])
        paths = [f.path for f in result.files]
        assert any("app.py" in p for p in paths)
        assert not any("test_foo" in p for p in paths)


def test_scan_directory_excludes_test_files_by_default():
    """Test files matching common test patterns are excluded by default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "app.py").write_text("def app(): pass\n")
        (Path(tmpdir) / "test_app.py").write_text("def test_app(): pass\n")
        (Path(tmpdir) / "utils_test.py").write_text("def test_utils(): pass\n")
        tests_dir = Path(tmpdir) / "tests"
        tests_dir.mkdir()
        (tests_dir / "conftest.py").write_text("def fixture(): pass\n")

        result = scan_directory(tmpdir)
        paths = [f.path for f in result.files]
        assert any("app.py" in p for p in paths)
        assert not any("test_app.py" in p for p in paths)
        assert not any("utils_test.py" in p for p in paths)
        assert not any("conftest.py" in p for p in paths)


def test_scan_directory_includes_test_files_when_flag_set():
    """With include_tests=True, test files are included."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "app.py").write_text("def app(): pass\n")
        (Path(tmpdir) / "test_app.py").write_text("def test_app(): pass\n")

        result = scan_directory(tmpdir, include_tests=True)
        paths = [f.path for f in result.files]
        assert any("app.py" in p for p in paths)
        assert any("test_app.py" in p for p in paths)


@requires_go
@requires_java
@requires_js
def test_scan_directory_excludes_multi_language_test_files():
    """Test file exclusion works across supported languages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "app.go").write_text("package main\nfunc main() {}\n")
        (Path(tmpdir) / "app_test.go").write_text("package main\nfunc TestApp() {}\n")
        (Path(tmpdir) / "App.java").write_text("class App { void run() {} }\n")
        (Path(tmpdir) / "AppTest.java").write_text("class AppTest { void testRun() {} }\n")
        (Path(tmpdir) / "app.js").write_text("function app() {}\n")
        (Path(tmpdir) / "app.test.js").write_text("function testApp() {}\n")

        result = scan_directory(tmpdir)
        paths = [f.path for f in result.files]
        assert any("app.go" in p and "test" not in p for p in paths)
        assert not any("app_test.go" in p for p in paths)
        assert any("App.java" in p for p in paths)
        assert not any("AppTest.java" in p for p in paths)
        assert any("app.js" in p and "test" not in p for p in paths)
        assert not any("app.test.js" in p for p in paths)


def test_scan_directory_error_handling():
    with tempfile.TemporaryDirectory() as tmpdir:
        good = Path(tmpdir) / "good.py"
        good.write_text("def ok(): pass\n")
        bad = Path(tmpdir) / "bad.py"
        bad.write_text("def ok(): pass\n")
        os.chmod(str(bad), 0o000)
        try:
            result = scan_directory(tmpdir)
            # Should have scanned at least the good file
            assert len(result.files) >= 1
        finally:
            os.chmod(str(bad), 0o644)


# ---------------------------------------------------------------------------
# P3: Additive NCS model tests
# ---------------------------------------------------------------------------

def test_compute_ncs_additive_model():
    from complexity_accounting.config import Config
    path = _write_temp("""
        def simple():
            return 1

        def complex_func(x, y):
            if x:
                if y:
                    for i in range(10):
                        if i > 5:
                            return i
            return 0
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        config = Config(ncs_model="additive", weight_cognitive=0.7, weight_cyclomatic=0.3)
        ncs = result.compute_ncs(config, churn_factor=1.2, coupling_factor=1.5)
        assert ncs > 0
    finally:
        os.unlink(path)


def test_compute_ncs_additive_zero_functions():
    from complexity_accounting.config import Config
    result = ScanResult()
    config = Config(ncs_model="additive")
    assert result.compute_ncs(config) == 0.0


def test_compute_ncs_additive_vs_multiplicative():
    from complexity_accounting.config import Config
    path = _write_temp("""
        def simple():
            return 1

        def complex_func(x, y):
            if x:
                if y:
                    for i in range(10):
                        if i > 5:
                            return i
            return 0
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        config_mult = Config(ncs_model="multiplicative")
        config_add = Config(ncs_model="additive")
        ncs_mult = result.compute_ncs(config_mult, churn_factor=1.2, coupling_factor=1.5)
        ncs_add = result.compute_ncs(config_add, churn_factor=1.2, coupling_factor=1.5)
        # With non-trivial factors, the two models should produce different results
        assert ncs_mult != ncs_add
        assert ncs_mult > 0
        assert ncs_add > 0
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# P4: Language-specific defaults tests
# ---------------------------------------------------------------------------

def test_get_language_mapping():
    from complexity_accounting.scanner import get_language
    assert get_language("foo.py") == "python"
    assert get_language("bar.ts") == "typescript"
    assert get_language("baz.tsx") == "typescript"
    assert get_language("main.go") == "go"
    assert get_language("App.java") == "java"
    assert get_language("index.js") == "javascript"
    assert get_language("lib.rs") == "rust"
    assert get_language("core.cpp") == "cpp"
    assert get_language("unknown.xyz") is None


def test_compute_ncs_language_specific_hotspot():
    from complexity_accounting.config import Config
    # Create a file with a function at cognitive=6 (above default threshold of 5 but below 15)
    path = _write_temp("""
        def complex_func(x, y):
            if x:
                if y:
                    for i in range(10):
                        if i > 5:
                            return i
            return 0
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        # With threshold=5, this function IS a hotspot
        config_low = Config(hotspot_threshold=5)
        ncs_low = result.compute_ncs(config_low)

        # With a language override setting threshold=50, it should NOT be a hotspot
        config_lang = Config(
            hotspot_threshold=5,
            language_overrides={"python": {"hotspot_threshold": 50}},
        )
        ncs_lang = result.compute_ncs(config_lang)

        # The language override should reduce the hotspot penalty
        assert ncs_lang <= ncs_low
    finally:
        os.unlink(path)


def test_hotspot_severity_proportional():
    """Weighted severity: a CC=100 function should produce higher NCS than CC=11."""
    from complexity_accounting.config import Config
    from complexity_accounting.models import FunctionMetrics, FileMetrics, ScanResult

    def _make_result(cc: int) -> ScanResult:
        fn = FunctionMetrics(
            name="f", qualified_name="f", file_path="test.py",
            line=1, end_line=10, cognitive_complexity=cc,
            cyclomatic_complexity=cc // 2 or 1, nloc=10,
        )
        fm = FileMetrics(path="test.py", functions=[fn], total_lines=10, code_lines=10)
        return ScanResult(files=[fm])

    config = Config(hotspot_threshold=10)
    ncs_11 = _make_result(11).compute_ncs(config)
    ncs_100 = _make_result(100).compute_ncs(config)

    # Both are above threshold, but severity should make CC=100 score much higher
    assert ncs_100 > ncs_11
    # The difference should be substantial (not just rounding)
    assert ncs_100 > ncs_11 * 2


# ---------------------------------------------------------------------------
# P5: compute_ncs_explained tests
# ---------------------------------------------------------------------------

def test_compute_ncs_explained_multiplicative():
    from complexity_accounting.config import Config
    path = _write_temp("""
        def simple():
            return 1

        def complex_func(x, y):
            if x:
                if y:
                    for i in range(10):
                        if i > 5:
                            return i
            return 0
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        config = Config()
        exp = result.compute_ncs_explained(config, churn_factor=1.2, coupling_factor=1.1)
        assert exp["model"] == "multiplicative"
        assert exp["ncs"] == result.compute_ncs(config, churn_factor=1.2, coupling_factor=1.1)
        assert exp["base_complexity"] > 0
        assert "dominant_factor" in exp
        assert exp["avg_cognitive"] > 0
    finally:
        os.unlink(path)


def test_compute_ncs_explained_additive():
    from complexity_accounting.config import Config
    path = _write_temp("""
        def simple():
            return 1

        def complex_func(x, y):
            if x:
                if y:
                    return True
            return False
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        config = Config(ncs_model="additive")
        exp = result.compute_ncs_explained(config, churn_factor=1.1, coupling_factor=1.2)
        assert exp["model"] == "additive"
        assert exp["ncs"] == result.compute_ncs(config, churn_factor=1.1, coupling_factor=1.2)
    finally:
        os.unlink(path)


def test_compute_ncs_explained_zero_functions():
    result = ScanResult()
    exp = result.compute_ncs_explained()
    assert exp["ncs"] == 0.0
    assert exp["dominant_factor"] == "none"


def test_compute_ncs_explained_dominant_factor():
    from complexity_accounting.config import Config
    path = _write_temp("""
        def simple():
            return 1
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        config = Config()
        # With high churn and no hotspots, churn should dominate
        exp = result.compute_ncs_explained(config, churn_factor=2.0, coupling_factor=1.0)
        # The dominant factor should be churn since hotspot_ratio is 0
        assert exp["dominant_factor"] == "churn"
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Coverage gap: nested FunctionDef in cognitive complexity visitor (lines 443-448)
# ---------------------------------------------------------------------------

def test_cognitive_nested_function_def():
    """Inner function definitions should increase nesting in cognitive visitor."""
    path = _write_temp("""
        def outer(x):
            def inner(y):
                if y > 0:  # nested inside inner → nesting from outer
                    return y
            if x > 0:  # +1
                return inner(x)
            return 0
    """)
    try:
        fm = scan_file(path)
        # outer has if x > 0 → cognitive 1
        # inner has if y > 0 → cognitive 1 (nesting inside inner itself)
        assert fm.function_count >= 1
        # The outer function should be collected; inner may or may not be
        outer = [f for f in fm.functions if f.name == "outer"][0]
        assert outer.cognitive_complexity >= 1
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Coverage gap: _count_params with *args and **kwargs (lines 534, 536)
# ---------------------------------------------------------------------------

def test_count_params_star_args():
    """Functions with *args should count the star param."""
    path = _write_temp("""
        def func_with_args(a, b, *args):
            pass
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.params == 3  # a, b, *args
    finally:
        os.unlink(path)


def test_count_params_kwargs():
    """Functions with **kwargs should count the kwarg param."""
    path = _write_temp("""
        def func_with_kwargs(a, **kwargs):
            pass
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.params == 2  # a, **kwargs
    finally:
        os.unlink(path)


def test_count_params_star_and_kwargs():
    """Functions with *args, keyword-only, and **kwargs."""
    path = _write_temp("""
        def func_all(a, *args, key_only=1, **kwargs):
            pass
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.params == 4  # a, *args, key_only, **kwargs
    finally:
        os.unlink(path)


def test_count_params_self_excluded():
    """Methods should exclude self from param count."""
    path = _write_temp("""
        class Foo:
            def method(self, a, b, *args, **kwargs):
                pass
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.params == 4  # a, b, *args, **kwargs (self excluded)
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Coverage gap: scan_directory error handling (lines 735-737)
# ---------------------------------------------------------------------------

def test_scan_directory_skips_unreadable_file():
    """scan_directory should skip files that raise on scan and continue."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write a valid file
        good = Path(tmpdir) / "good.py"
        good.write_text("def hello(): pass\n")

        # Write a file that will cause a parse error (binary content)
        bad = Path(tmpdir) / "bad.py"
        bad.write_bytes(b"\x00\x01\x02\x03\x04")

        result = scan_directory(tmpdir)
        # Should have at least the good file; bad file may parse or be skipped
        assert len(result.files) >= 1


# ---------------------------------------------------------------------------
# Coverage gap: scanner.main() legacy CLI (lines 747-832)
# ---------------------------------------------------------------------------

def test_scanner_legacy_main_json():
    """Test the legacy main() CLI in scanner.py with --json flag."""
    from complexity_accounting.scanner import main as scanner_main
    import io
    from contextlib import redirect_stdout
    from unittest.mock import patch

    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        with patch("sys.argv", ["scanner", path, "--json"]):
            out = io.StringIO()
            with redirect_stdout(out):
                scanner_main()
            import json
            result = json.loads(out.getvalue())
            assert "summary" in result
    finally:
        os.unlink(path)


def test_scanner_legacy_main_text():
    """Test the legacy main() CLI in scanner.py with text output."""
    from complexity_accounting.scanner import main as scanner_main
    import io
    from contextlib import redirect_stdout
    from unittest.mock import patch

    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        with patch("sys.argv", ["scanner", path]):
            out = io.StringIO()
            with redirect_stdout(out):
                scanner_main()
            output = out.getvalue()
            assert "COMPLEXITY ACCOUNTING REPORT" in output
    finally:
        os.unlink(path)


def test_scanner_legacy_main_directory():
    """Test the legacy main() CLI scanning a directory."""
    from complexity_accounting.scanner import main as scanner_main
    import io
    from contextlib import redirect_stdout
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "a.py").write_text("def foo(): pass\n")
        with patch("sys.argv", ["scanner", tmpdir, "--json"]):
            out = io.StringIO()
            with redirect_stdout(out):
                scanner_main()
            import json
            result = json.loads(out.getvalue())
            assert result["summary"]["files_scanned"] >= 1


def test_scanner_legacy_main_not_found():
    """Test the legacy main() CLI with nonexistent path."""
    from complexity_accounting.scanner import main as scanner_main
    from unittest.mock import patch

    with patch("sys.argv", ["scanner", "/nonexistent/path"]):
        try:
            scanner_main()
            assert False, "Should have exited"
        except SystemExit as e:
            assert e.code == 1


def test_scanner_legacy_main_fail_above():
    """Test the legacy main() CLI --fail-above."""
    from complexity_accounting.scanner import main as scanner_main
    import io
    from contextlib import redirect_stdout
    from unittest.mock import patch

    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        with patch("sys.argv", ["scanner", path, "--fail-above", "0.001"]):
            out = io.StringIO()
            try:
                with redirect_stdout(out):
                    scanner_main()
            except SystemExit:
                pass  # Expected — NCS may or may not exceed threshold
    finally:
        os.unlink(path)


def test_scanner_legacy_main_threshold():
    """Test the legacy main() CLI --threshold flag."""
    from complexity_accounting.scanner import main as scanner_main
    import io
    from contextlib import redirect_stdout
    from unittest.mock import patch

    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, textwrap.dedent("""
        def complex_func(x, y, z):
            if x:
                if y:
                    if z:
                        for i in range(10):
                            while True:
                                if i > 5:
                                    break
    """).encode())
    os.close(fd)
    try:
        with patch("sys.argv", ["scanner", path, "--threshold", "5"]):
            out = io.StringIO()
            with redirect_stdout(out):
                scanner_main()
            output = out.getvalue()
            assert "COMPLEXITY ACCOUNTING REPORT" in output
    finally:
        os.unlink(path)


def test_scanner_legacy_main_top():
    """Test the legacy main() CLI --top flag."""
    from complexity_accounting.scanner import main as scanner_main
    import io
    from contextlib import redirect_stdout
    from unittest.mock import patch

    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\ndef world(): pass\n")
    os.close(fd)
    try:
        with patch("sys.argv", ["scanner", path, "--top", "1"]):
            out = io.StringIO()
            with redirect_stdout(out):
                scanner_main()
            output = out.getvalue()
            assert "COMPLEXITY ACCOUNTING REPORT" in output
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Boolean operator tracking (SonarSource spec)
# ---------------------------------------------------------------------------

def test_boolean_same_operator_chain():
    """a and b and c should be +1 (same operator chain)."""
    path = _write_temp("""
        def check(a, b, c):
            if a and b and c:
                return True
            return False
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # if: +1, and-chain: +1 = 2
        assert fn.cognitive_complexity == 2
    finally:
        os.unlink(path)


def test_boolean_mixed_operators():
    """a and b or c should be +2 (operator change)."""
    path = _write_temp("""
        def check(a, b, c):
            if a and b or c:
                return True
            return False
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # if: +1, and: +1, or (switch): +1 = 3
        assert fn.cognitive_complexity == 3
    finally:
        os.unlink(path)


def test_boolean_three_operator_switches():
    """a and b or c and d should be +3 (two switches)."""
    path = _write_temp("""
        def check(a, b, c, d):
            if a and b or c and d:
                return True
            return False
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # if: +1, and: +1, or (switch): +1, and (switch): +1 = 4
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Python match/case support
# ---------------------------------------------------------------------------

def test_match_case_cognitive():
    """match adds +1+nesting, case arms don't add cognitive."""
    path = _write_temp("""
        def classify(x):
            match x:
                case 1:
                    return "one"
                case 2:
                    return "two"
                case _:
                    return "other"
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # match: +1 (nesting=0) = 1
        assert fn.cognitive_complexity == 1
    finally:
        os.unlink(path)


def test_match_case_cyclomatic():
    """Each case arm adds +1 to cyclomatic."""
    path = _write_temp("""
        def classify(x):
            match x:
                case 1:
                    return "one"
                case 2:
                    return "two"
                case _:
                    return "other"
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # baseline: 1, case 1: +1, case 2: +1, case _: +1 = 4
        assert fn.cyclomatic_complexity == 4
    finally:
        os.unlink(path)


def test_match_case_nested():
    """match inside if increases nesting penalty."""
    path = _write_temp("""
        def classify(x, flag):
            if flag:
                match x:
                    case 1:
                        return "one"
                    case _:
                        return "other"
            return None
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # if: +1 (nesting=0), match: +1+1 (nesting=1) = 3
        assert fn.cognitive_complexity == 3
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Maintainability Index
# ---------------------------------------------------------------------------

def test_maintainability_index_simple():
    """A simple function should have high MI."""
    path = _write_temp("""
        def add(a, b):
            return a + b
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.maintainability_index > 50
    finally:
        os.unlink(path)


def test_maintainability_index_complex():
    """A complex function should have lower MI."""
    path = _write_temp("""
        def handle(request, data, config, options, flags):
            if request.method == "POST":
                if data.get("key"):
                    for item in data["items"]:
                        if item.get("valid"):
                            for sub in item["children"]:
                                if sub.get("active"):
                                    if config.get("strict"):
                                        if options.get("verbose"):
                                            for flag in flags:
                                                if flag == "debug":
                                                    print("debug")
            return None
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.maintainability_index < 80
    finally:
        os.unlink(path)


def test_maintainability_index_in_scan_result():
    """ScanResult should include avg MI in to_dict output."""
    from complexity_accounting.scanner import FunctionMetrics, FileMetrics
    fm = FileMetrics(path="test.py", functions=[
        FunctionMetrics(
            name="f", qualified_name="f", file_path="test.py",
            line=1, end_line=5, cognitive_complexity=2,
            cyclomatic_complexity=3, nloc=5, params=1, max_nesting=1,
            maintainability_index=75.0,
        ),
    ])
    result = ScanResult(files=[fm])
    d = result.to_dict()
    assert "avg_maintainability_index" in d["summary"]
    assert d["summary"]["avg_maintainability_index"] == 75.0


def test_compute_mi_function():
    """compute_mi returns sensible values."""
    from complexity_accounting.scanner import compute_mi
    # Tiny function: high MI
    assert compute_mi(3, 1) > 80
    # Large complex function: lower MI
    assert compute_mi(200, 30) < compute_mi(10, 2)
    # Edge: 0 lines
    assert compute_mi(0, 1) == 100.0


def test_avg_maintainability_index_zero_functions():
    """ScanResult with no functions returns 100.0 MI."""
    result = ScanResult(files=[])
    assert result.avg_maintainability_index == 100.0


def test_avg_maintainability_index_multiple_functions():
    """avg MI is averaged across all functions."""
    from complexity_accounting.scanner import FunctionMetrics, FileMetrics
    fm = FileMetrics(path="test.py", functions=[
        FunctionMetrics(
            name="f1", qualified_name="f1", file_path="test.py",
            line=1, end_line=5, maintainability_index=80.0,
        ),
        FunctionMetrics(
            name="f2", qualified_name="f2", file_path="test.py",
            line=6, end_line=10, maintainability_index=60.0,
        ),
    ])
    result = ScanResult(files=[fm])
    assert result.avg_maintainability_index == 70.0


def test_ncs_explained_includes_mi_fields():
    """compute_ncs_explained includes MI-related fields."""
    from complexity_accounting.config import Config
    path = _write_temp("""
        def simple():
            return 1
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        config = Config()
        exp = result.compute_ncs_explained(config)
        assert "mi_factor" in exp
        assert "mi_contribution" in exp
        assert "avg_maintainability_index" in exp
        assert exp["mi_factor"] >= 1.0
    finally:
        os.unlink(path)


def test_ncs_explained_zero_functions_mi_fields():
    """Zero-function explained result includes MI defaults."""
    result = ScanResult()
    exp = result.compute_ncs_explained()
    assert exp["mi_factor"] == 1.0
    assert exp["avg_maintainability_index"] == 100.0
    assert exp["mi_contribution"] == 0.0


def test_ncs_additive_includes_mi_penalty():
    """Additive NCS model includes MI penalty term."""
    from complexity_accounting.config import Config
    path = _write_temp("""
        def simple():
            return 1
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        config_no_mi = Config(ncs_model="additive", weight_mi=0.0)
        config_mi = Config(ncs_model="additive", weight_mi=0.5)
        ncs_no_mi = result.compute_ncs(config_no_mi)
        ncs_mi = result.compute_ncs(config_mi)
        # MI penalty should increase NCS (since MI < 100)
        assert ncs_mi > ncs_no_mi
    finally:
        os.unlink(path)


def test_ncs_additive_explained_mi_contribution():
    """Additive model explained output includes MI contribution."""
    from complexity_accounting.config import Config
    path = _write_temp("""
        def func(x):
            if x > 0:
                return x
            return -x
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        config = Config(ncs_model="additive", weight_mi=0.1)
        exp = result.compute_ncs_explained(config)
        assert exp["model"] == "additive"
        assert "mi_contribution" in exp
        # MI penalty should be > 0 since MI is < 100
        assert exp["mi_contribution"] > 0
    finally:
        os.unlink(path)


def test_ncs_multiplicative_mi_factor_high_mi():
    """With high MI (>50), mi_factor should be 1.0 (no penalty)."""
    from complexity_accounting.config import Config
    path = _write_temp("""
        def simple():
            return 1
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        config = Config()
        exp = result.compute_ncs_explained(config)
        # Simple function has MI > 50, so mi_factor = 1.0
        assert exp["avg_maintainability_index"] > 50
        assert exp["mi_factor"] == 1.0
        assert exp["mi_contribution"] == 0.0
    finally:
        os.unlink(path)


def test_ncs_dominant_factor_mi():
    """MI can be the dominant factor when it has the largest contribution."""
    from complexity_accounting.scanner import FunctionMetrics, FileMetrics
    from complexity_accounting.config import Config
    # Craft a function with very low MI
    fm = FileMetrics(path="test.py", functions=[
        FunctionMetrics(
            name="f", qualified_name="f", file_path="test.py",
            line=1, end_line=5, cognitive_complexity=1,
            cyclomatic_complexity=1, nloc=5, params=0, max_nesting=0,
            maintainability_index=10.0,  # Very low MI
        ),
    ])
    result = ScanResult(files=[fm])
    config = Config()
    exp = result.compute_ncs_explained(config)
    # MI factor should be > 1 and could be dominant
    assert exp["mi_factor"] > 1.0
    assert exp["mi_contribution"] > 0


def test_boolean_ops_standalone_or():
    """a or b or c should be +1 (same operator chain)."""
    path = _write_temp("""
        def check(a, b, c):
            if a or b or c:
                return True
            return False
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # if: +1, or-chain: +1 = 2
        assert fn.cognitive_complexity == 2
    finally:
        os.unlink(path)


def test_boolean_ops_separate_conditions():
    """Boolean ops in separate if statements each start fresh."""
    path = _write_temp("""
        def check(a, b, c, d):
            if a and b:
                pass
            if c or d:
                pass
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # if: +1, and: +1, if: +1, or: +1 = 4
        assert fn.cognitive_complexity == 4
    finally:
        os.unlink(path)


def test_match_with_nested_if():
    """if inside a match case arm gets nesting penalty from match."""
    path = _write_temp("""
        def process(cmd, flag):
            match cmd:
                case "start":
                    if flag:
                        return True
                case _:
                    return False
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        # match: +1, if inside match (nesting=1): +1+1 = 3
        assert fn.cognitive_complexity == 3
    finally:
        os.unlink(path)


def test_scan_result_to_dict_includes_mi():
    """to_dict includes maintainability_index in function details."""
    path = _write_temp("""
        def foo():
            return 1
    """)
    try:
        result = ScanResult(files=[scan_file(path)])
        d = result.to_dict()
        fn_data = d["files"][0]["functions"][0]
        assert "maintainability_index" in fn_data
        assert fn_data["maintainability_index"] > 0
    finally:
        os.unlink(path)


def test_package_version():
    """Test __version__ is a valid semver string."""
    import complexity_accounting
    assert complexity_accounting.__version__ == "1.6.1"
    parts = complexity_accounting.__version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


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
