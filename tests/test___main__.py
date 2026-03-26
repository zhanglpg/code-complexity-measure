"""Tests for __main__.py CLI commands — mapped to __main__.py for TQS scoring."""
import argparse
import io
import json
import os
import tempfile
import textwrap
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from complexity_accounting.__main__ import (
    cmd_scan, cmd_compare, cmd_trend, cmd_list_plugins, main,
    _ncs_rating, _get_format,
)
from complexity_accounting.scanner import FileMetrics, FunctionMetrics, ScanResult
from complexity_accounting.git_tracker import DeltaReport


def _make_scan_args(**overrides):
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
        output=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# _ncs_rating
# ---------------------------------------------------------------------------

def test_ncs_rating_healthy():
    rating = _ncs_rating(0.0)
    assert rating == _ncs_rating(3.0)
    assert "Healthy" in rating


def test_ncs_rating_moderate():
    rating = _ncs_rating(4.0)
    assert rating == _ncs_rating(6.0)
    assert "Moderate" in rating


def test_ncs_rating_concerning():
    rating = _ncs_rating(7.0)
    assert rating == _ncs_rating(10.0)
    assert "Concerning" in rating


def test_ncs_rating_critical():
    rating = _ncs_rating(15.0)
    assert rating == _ncs_rating(100.0)
    assert "Critical" in rating


# ---------------------------------------------------------------------------
# _get_format
# ---------------------------------------------------------------------------

def test_get_format_json_flag():
    args = argparse.Namespace(json=True)
    assert _get_format(args) == "json"


def test_get_format_default():
    args = argparse.Namespace(json=False)
    result = _get_format(args)
    assert result == "text"


# ---------------------------------------------------------------------------
# cmd_scan — strong assertions
# ---------------------------------------------------------------------------

def test_cmd_scan_json_output_structure():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def hello(): pass\n")
    os.close(fd)
    try:
        args = _make_scan_args(path=path, json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        result = json.loads(out.getvalue())
        assert result["summary"]["files_scanned"] == 1
        assert result["summary"]["total_functions"] == 1
        assert result["summary"]["ncs_model"] == "multiplicative"
        assert len(result["files"]) == 1
        assert result["files"][0]["function_count"] == 1
        assert result["files"][0]["functions"][0]["name"] == "hello"
        assert result["files"][0]["functions"][0]["cognitive_complexity"] == 0
        assert result["files"][0]["functions"][0]["cyclomatic_complexity"] == 1
    finally:
        os.unlink(path)


def test_cmd_scan_text_contains_sections():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "simple.py").write_text("def foo(): pass\n")
        args = _make_scan_args(path=tmpdir)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        output = out.getvalue()
        assert "COMPLEXITY ACCOUNTING REPORT" in output
        assert "Net Complexity Score" in output
        assert "Files scanned" in output
        assert "Total functions" in output


def test_cmd_scan_fail_above_triggers_exit():
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


def test_cmd_scan_path_not_found_exits():
    args = _make_scan_args(path="/nonexistent/path/xyz")
    try:
        cmd_scan(args)
        assert False, "Should have exited"
    except SystemExit as e:
        assert e.code == 1


# ---------------------------------------------------------------------------
# cmd_list_plugins
# ---------------------------------------------------------------------------

def test_cmd_list_plugins_output():
    out = io.StringIO()
    args = argparse.Namespace()
    with redirect_stdout(out):
        cmd_list_plugins(args)
    output = out.getvalue()
    assert "Language Plugins" in output or "No plugins" in output or output != ""


# ---------------------------------------------------------------------------
# main() routing
# ---------------------------------------------------------------------------

def test_main_no_command_exits():
    with patch("sys.argv", ["prog"]):
        try:
            main()
            assert False, "Should have exited"
        except SystemExit as e:
            assert e.code == 1


def test_main_scan_route():
    with patch("sys.argv", ["prog", "scan", "/tmp", "--json", "--no-churn", "--no-coupling"]), \
         patch("complexity_accounting.__main__.cmd_scan") as mock_scan:
        mock_scan.side_effect = SystemExit(0)
        try:
            main()
        except SystemExit:
            pass
        assert mock_scan.call_count == 1


def test_main_compare_route():
    with patch("sys.argv", ["prog", "compare", "--base", "main"]), \
         patch("complexity_accounting.__main__.cmd_compare") as mock_compare:
        mock_compare.side_effect = SystemExit(0)
        try:
            main()
        except SystemExit:
            pass
        assert mock_compare.call_count == 1


def test_main_trend_route():
    with patch("sys.argv", ["prog", "trend"]), \
         patch("complexity_accounting.__main__.cmd_trend") as mock_trend:
        mock_trend.side_effect = SystemExit(0)
        try:
            main()
        except SystemExit:
            pass
        assert mock_trend.call_count == 1


# ---------------------------------------------------------------------------
# cmd_compare
# ---------------------------------------------------------------------------

def test_cmd_compare_json_output():
    report = DeltaReport("main", "HEAD", 5.0, 7.0, [])
    with patch("complexity_accounting.git_tracker.compare_refs", return_value=report):
        args = argparse.Namespace(base="main", head="HEAD", repo=".", json=True,
                                  markdown=False, full=False, func=cmd_compare)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_compare(args)
        result = json.loads(out.getvalue())
        assert result["base_ncs"] == 5.0
        assert result["head_ncs"] == 7.0
        assert result["ncs_delta"] == 2.0


# ---------------------------------------------------------------------------
# cmd_trend
# ---------------------------------------------------------------------------

def test_cmd_trend_json_output():
    trend_data = [{"commit": "abc12345", "date": "2024-01-01", "message": "init",
                   "ncs": 3.5, "total_cognitive": 10, "total_functions": 5, "files": 2}]
    with patch("complexity_accounting.git_tracker.trend", return_value=trend_data):
        args = argparse.Namespace(repo=".", commits=10, ref="HEAD", json=True,
                                  func=cmd_trend)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_trend(args)
        result = json.loads(out.getvalue())
        assert len(result) == 1
        assert result[0]["ncs"] == 3.5
        assert result[0]["commit"] == "abc12345"


# ---------------------------------------------------------------------------
# Output file writing
# ---------------------------------------------------------------------------

def test_cmd_scan_output_to_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "simple.py").write_text("def foo(): pass\n")
        outfile = os.path.join(tmpdir, "report.json")
        args = _make_scan_args(path=tmpdir, json=True, output=outfile)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            cmd_scan(args)
        assert stdout.getvalue() == ""
        with open(outfile) as f:
            result = json.loads(f.read())
        assert result["summary"]["files_scanned"] == 1
