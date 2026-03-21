"""Tests for __main__.py CLI commands."""
import argparse
import io
import json
import os
import sys
import tempfile
import textwrap
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch, MagicMock

from complexity_accounting.__main__ import cmd_scan, cmd_compare, cmd_trend, main
from complexity_accounting.scanner import FileMetrics, FunctionMetrics, ScanResult
from complexity_accounting.git_tracker import DeltaReport, FileDelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_scan_args(**overrides):
    """Build a minimal argparse.Namespace for cmd_scan."""
    defaults = dict(
        path="/tmp",
        json=False,
        threshold=None,
        top=20,
        fail_above=None,
        config=None,
        weights=None,
        churn_days=None,
        churn_commits=None,
        no_churn=True,
        no_coupling=True,
        ncs_model=None,
        brief=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _make_file_metrics(cognitive=3, cyclomatic=2, name="foo"):
    fn = FunctionMetrics(name, name, "test.py", 1, 10,
                         cognitive_complexity=cognitive,
                         cyclomatic_complexity=cyclomatic,
                         nloc=10, params=1, max_nesting=1)
    return FileMetrics("test.py", [fn], total_lines=10, code_lines=8,
                       comment_lines=1, blank_lines=1)


# ---------------------------------------------------------------------------
# cmd_scan tests
# ---------------------------------------------------------------------------

def test_cmd_scan_file_json():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert "summary" in result
        assert "net_complexity_score" in result["summary"]
        assert "files" in result
    finally:
        os.unlink(path)


def test_cmd_scan_directory_text():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "simple.py").write_text("def foo(): pass\n")
        args = _make_scan_args(path=tmpdir, json=False)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        output = out.getvalue()
        assert "COMPLEXITY ACCOUNTING REPORT" in output
        assert "Net Complexity Score" in output
        assert "Files scanned" in output


def test_cmd_scan_fail_above_exits():
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
        args = _make_scan_args(path=path, fail_above=0.001, json=True)
        out = io.StringIO()
        try:
            with redirect_stdout(out):
                cmd_scan(args)
            assert False, "Should have exited"
        except SystemExit as e:
            assert e.code == 1
    finally:
        os.unlink(path)


def test_cmd_scan_fail_above_passes():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, fail_above=100.0, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)  # Should not exit
    finally:
        os.unlink(path)


def test_cmd_scan_weights_parsing():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, weights="cognitive=0.8,cyclomatic=0.2", json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert "net_complexity_score" in result["summary"]
    finally:
        os.unlink(path)


def test_cmd_scan_path_not_found():
    args = _make_scan_args(path="/nonexistent/path/xyz")
    try:
        cmd_scan(args)
        assert False, "Should have exited"
    except SystemExit as e:
        assert e.code == 1


def test_cmd_scan_coupling_enabled():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, no_coupling=False, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert "coupling_factor" in result["summary"]
    finally:
        os.unlink(path)


def test_cmd_scan_coupling_graceful_failure():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        with patch("complexity_accounting.coupling.analyze_directory_coupling",
                    side_effect=RuntimeError("boom")):
            args = _make_scan_args(path=path, no_coupling=False, json=True)
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_scan(args)
            result = json.loads(out.getvalue())
            assert result["summary"]["coupling_factor"] == 1.0
    finally:
        os.unlink(path)


def test_cmd_scan_churn_enabled():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, no_churn=False, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert "churn_factor" in result["summary"]
    finally:
        os.unlink(path)


def test_cmd_scan_churn_graceful_failure():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        with patch("complexity_accounting.churn.analyze_churn",
                    side_effect=RuntimeError("boom")):
            args = _make_scan_args(path=path, no_churn=False, json=True)
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_scan(args)
            result = json.loads(out.getvalue())
            assert result["summary"]["churn_factor"] == 1.0
    finally:
        os.unlink(path)


def test_cmd_scan_ncs_rating_levels():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        # NCS for a simple function is 0.0 → Healthy
        args = _make_scan_args(path=path, json=False)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        output = out.getvalue()
        assert "Healthy" in output
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# cmd_compare tests
# ---------------------------------------------------------------------------

def test_cmd_compare_json():
    report = DeltaReport("main", "HEAD", 5.0, 7.0, [])
    with patch("complexity_accounting.git_tracker.compare_refs", return_value=report):
        args = argparse.Namespace(base="main", head="HEAD", repo=".", json=True,
                                  markdown=False, full=False, func=cmd_compare)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_compare(args)
        result = json.loads(out.getvalue())
        assert result["base_ncs"] == 5.0


def test_cmd_compare_markdown():
    report = DeltaReport("main", "HEAD", 5.0, 7.0, [])
    with patch("complexity_accounting.git_tracker.compare_refs", return_value=report):
        args = argparse.Namespace(base="main", head="HEAD", repo=".", json=False,
                                  markdown=True, full=False, func=cmd_compare)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_compare(args)
        output = out.getvalue()
        assert "Complexity Report" in output


# ---------------------------------------------------------------------------
# cmd_trend tests
# ---------------------------------------------------------------------------

def test_cmd_trend_json():
    trend_data = [{"commit": "abc12345", "date": "2024-01-01", "message": "init",
                   "ncs": 3.5, "total_cognitive": 10, "total_functions": 5, "files": 2}]
    with patch("complexity_accounting.git_tracker.trend", return_value=trend_data):
        args = argparse.Namespace(repo=".", commits=10, ref="HEAD", json=True,
                                  func=cmd_trend)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_trend(args)
        result = json.loads(out.getvalue())
        assert isinstance(result, list)
        assert result[0]["ncs"] == 3.5


def test_cmd_trend_text():
    trend_data = [{"commit": "abc12345", "date": "2024-01-01", "message": "init",
                   "ncs": 3.5, "total_cognitive": 10, "total_functions": 5, "files": 2}]
    with patch("complexity_accounting.git_tracker.trend", return_value=trend_data):
        args = argparse.Namespace(repo=".", commits=10, ref="HEAD", json=False,
                                  func=cmd_trend)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_trend(args)
        output = out.getvalue()
        assert "Commit" in output
        assert "NCS" in output


def test_cmd_trend_error_entries():
    trend_data = [{"commit": "abc12345", "date": "2024-01-01", "message": "bad",
                   "error": "scan failed"}]
    with patch("complexity_accounting.git_tracker.trend", return_value=trend_data):
        args = argparse.Namespace(repo=".", commits=10, ref="HEAD", json=False,
                                  func=cmd_trend)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_trend(args)
        output = out.getvalue()
        assert "err" in output


# ---------------------------------------------------------------------------
# main() routing
# ---------------------------------------------------------------------------

def test_main_no_command():
    with patch("sys.argv", ["prog"]):
        try:
            main()
            assert False, "Should have exited"
        except SystemExit as e:
            assert e.code == 1


def test_main_scan_routing():
    with patch("sys.argv", ["prog", "scan", "/tmp", "--json", "--no-churn", "--no-coupling"]), \
         patch("complexity_accounting.__main__.cmd_scan") as mock_scan:
        mock_scan.side_effect = SystemExit(0)
        try:
            main()
        except SystemExit:
            pass
        mock_scan.assert_called_once()


def test_main_compare_routing():
    with patch("sys.argv", ["prog", "compare", "--base", "main"]), \
         patch("complexity_accounting.__main__.cmd_compare") as mock_compare:
        mock_compare.side_effect = SystemExit(0)
        try:
            main()
        except SystemExit:
            pass
        mock_compare.assert_called_once()


def test_main_trend_routing():
    with patch("sys.argv", ["prog", "trend"]), \
         patch("complexity_accounting.__main__.cmd_trend") as mock_trend:
        mock_trend.side_effect = SystemExit(0)
        try:
            main()
        except SystemExit:
            pass
        mock_trend.assert_called_once()


# ---------------------------------------------------------------------------
# --ncs-model tests
# ---------------------------------------------------------------------------

def test_cmd_scan_ncs_model_additive():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, textwrap.dedent("""
        def complex_func(x, y):
            if x:
                if y:
                    for i in range(10):
                        if i > 5:
                            return i
            return 0
    """).encode())
    os.close(fd)
    try:
        args = _make_scan_args(path=path, ncs_model="additive", json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert "net_complexity_score" in result["summary"]
        assert result["summary"]["ncs_model"] == "additive"
    finally:
        os.unlink(path)


def test_cmd_scan_ncs_model_multiplicative_default():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert result["summary"]["ncs_model"] == "multiplicative"
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# --brief tests (explain is now the default)
# ---------------------------------------------------------------------------

def test_cmd_scan_default_explain_text():
    """By default (no --brief), text output includes NCS breakdown."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, textwrap.dedent("""
        def complex_func(x, y):
            if x:
                if y:
                    return True
            return False
    """).encode())
    os.close(fd)
    try:
        args = _make_scan_args(path=path)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        output = out.getvalue()
        assert "NCS Breakdown" in output
        assert "Base complexity" in output
        assert "Hotspot effect" in output
        assert "Churn effect" in output
        assert "Coupling effect" in output
        assert "Final NCS" in output
    finally:
        os.unlink(path)


def test_cmd_scan_default_explain_json():
    """By default (no --brief), JSON output includes explanation."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, textwrap.dedent("""
        def complex_func(x, y):
            if x:
                if y:
                    return True
            return False
    """).encode())
    os.close(fd)
    try:
        args = _make_scan_args(path=path, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert "explanation" in result
        exp = result["explanation"]
        assert "ncs" in exp
        assert "model" in exp
        assert "base_complexity" in exp
        assert "dominant_factor" in exp
        assert "hotspot_contribution" in exp
        assert "churn_contribution" in exp
        assert "coupling_contribution" in exp
    finally:
        os.unlink(path)


def test_cmd_scan_brief_json():
    """With --brief, JSON output should not contain explanation."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, json=True, brief=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert "explanation" not in result
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Coverage gap: NCS rating branches (lines 105, 109)
# ---------------------------------------------------------------------------

def test_cmd_scan_ncs_rating_moderate():
    """NCS between 3-6 should show Moderate rating."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, json=False)
        # Mock compute_ncs to return a moderate NCS
        with patch.object(ScanResult, "compute_ncs", return_value=4.5), \
             patch.object(ScanResult, "compute_ncs_explained", return_value=None):
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_scan(args)
            output = out.getvalue()
            assert "Moderate" in output
    finally:
        os.unlink(path)


def test_cmd_scan_ncs_rating_critical():
    """NCS > 10 should show Critical rating."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, json=False)
        with patch.object(ScanResult, "compute_ncs", return_value=15.0), \
             patch.object(ScanResult, "compute_ncs_explained", return_value=None):
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_scan(args)
            output = out.getvalue()
            assert "Critical" in output
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Coverage gap: non-multiplicative model and factor display (lines 117, 119, 121)
# ---------------------------------------------------------------------------

def test_cmd_scan_additive_model_display():
    """With additive model, text output should show model name."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, textwrap.dedent("""
        def func(x):
            if x:
                return True
            return False
    """).encode())
    os.close(fd)
    try:
        args = _make_scan_args(path=path, ncs_model="additive")
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        output = out.getvalue()
        assert "NCS model" in output
        assert "additive" in output
    finally:
        os.unlink(path)


def test_cmd_scan_churn_factor_display():
    """When churn factor != 1.0, it should be displayed in text output."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, no_churn=False)
        with patch("complexity_accounting.churn.analyze_churn", return_value={"a.py": 5}), \
             patch("complexity_accounting.churn.compute_churn_factor", return_value=1.5):
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_scan(args)
            output = out.getvalue()
            assert "Churn factor" in output
    finally:
        os.unlink(path)


def test_cmd_scan_coupling_factor_display():
    """When coupling factor != 1.0, it should be displayed in text output."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, no_coupling=False)
        with patch("complexity_accounting.coupling.analyze_directory_coupling", return_value={"a.py": MagicMock()}), \
             patch("complexity_accounting.coupling.compute_coupling_factor", return_value=1.8):
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_scan(args)
            output = out.getvalue()
            assert "Coupling factor" in output
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Coverage gap: cmd_compare default output (line 200)
# ---------------------------------------------------------------------------

def test_cmd_compare_default_output():
    """cmd_compare with neither --json nor --markdown should default to markdown."""
    report = DeltaReport("main", "HEAD", 5.0, 7.0, [])
    with patch("complexity_accounting.git_tracker.compare_refs", return_value=report):
        args = argparse.Namespace(base="main", head="HEAD", repo=".", json=False,
                                  markdown=False, full=False, func=cmd_compare)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_compare(args)
        output = out.getvalue()
        assert "Complexity Report" in output


# ---------------------------------------------------------------------------
# Coverage gap: --churn-days and --churn-commits CLI overrides (lines 36, 38)
# ---------------------------------------------------------------------------

def test_cmd_scan_churn_days_override():
    """--churn-days should pass through to config."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, churn_days=30, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert "net_complexity_score" in result["summary"]
    finally:
        os.unlink(path)


def test_cmd_scan_churn_commits_override():
    """--churn-commits should pass through to config."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, churn_commits=50, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert "net_complexity_score" in result["summary"]
    finally:
        os.unlink(path)


def test_cmd_scan_brief_text():
    """With --brief, text output should not contain NCS breakdown."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, textwrap.dedent("""
        def complex_func(x, y):
            if x:
                if y:
                    return True
            return False
    """).encode())
    os.close(fd)
    try:
        args = _make_scan_args(path=path, brief=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        output = out.getvalue()
        assert "COMPLEXITY ACCOUNTING REPORT" in output
        assert "NCS Breakdown" not in output
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Maintainability Index in output
# ---------------------------------------------------------------------------

def test_cmd_scan_mi_in_json():
    """JSON output includes avg_maintainability_index."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert "avg_maintainability_index" in result["summary"]
        assert result["summary"]["avg_maintainability_index"] > 0
    finally:
        os.unlink(path)


def test_cmd_scan_mi_in_explanation_json():
    """JSON explanation includes MI-related fields."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, textwrap.dedent("""
        def func(x):
            if x:
                return x
            return 0
    """).encode())
    os.close(fd)
    try:
        args = _make_scan_args(path=path, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        exp = result["explanation"]
        assert "mi_factor" in exp
        assert "mi_contribution" in exp
        assert "avg_maintainability_index" in exp
    finally:
        os.unlink(path)


def test_cmd_scan_mi_in_text():
    """Text output includes Avg MI line."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        output = out.getvalue()
        assert "Avg MI:" in output
    finally:
        os.unlink(path)


def test_cmd_scan_mi_effect_in_breakdown():
    """Text NCS breakdown includes MI effect line."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, textwrap.dedent("""
        def func(x):
            if x:
                return x
            return 0
    """).encode())
    os.close(fd)
    try:
        args = _make_scan_args(path=path)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        output = out.getvalue()
        assert "MI effect:" in output
        assert "avg_mi=" in output
    finally:
        os.unlink(path)


def test_cmd_scan_mi_in_function_details_json():
    """JSON function details include maintainability_index."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        fn_data = result["files"][0]["functions"][0]
        assert "maintainability_index" in fn_data
    finally:
        os.unlink(path)


def test_cmd_scan_additive_mi_in_explanation():
    """Additive model JSON explanation includes MI contribution."""
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, textwrap.dedent("""
        def func(x):
            if x:
                return x
            return 0
    """).encode())
    os.close(fd)
    try:
        args = _make_scan_args(path=path, json=True, ncs_model="additive")
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        exp = result["explanation"]
        assert exp["model"] == "additive"
        assert "mi_contribution" in exp
        # MI is < 100 so penalty > 0
        assert exp["mi_contribution"] > 0
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

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
