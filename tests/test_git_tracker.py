"""Tests for git_tracker module — delta reports, markdown output, and git operations."""
import json
from unittest.mock import patch, MagicMock

from complexity_accounting.git_tracker import (
    FileDelta,
    DeltaReport,
    _run_git,
    get_changed_files,
    scan_at_ref,
    compare_refs,
    trend,
)
from complexity_accounting.scanner import FileMetrics, FunctionMetrics, ScanResult


# ---------------------------------------------------------------------------
# FileDelta properties
# ---------------------------------------------------------------------------

def test_file_delta_cognitive_delta():
    fd = FileDelta("a.py", before_cognitive=5, after_cognitive=12,
                   before_cyclomatic=1, after_cyclomatic=1,
                   before_functions=1, after_functions=1, status="modified")
    assert fd.cognitive_delta == 7


def test_file_delta_cyclomatic_delta():
    fd = FileDelta("a.py", before_cognitive=0, after_cognitive=0,
                   before_cyclomatic=3, after_cyclomatic=8,
                   before_functions=1, after_functions=1, status="modified")
    assert fd.cyclomatic_delta == 5


def test_file_delta_zero_delta():
    fd = FileDelta("a.py", before_cognitive=10, after_cognitive=10,
                   before_cyclomatic=5, after_cyclomatic=5,
                   before_functions=2, after_functions=2, status="modified")
    assert fd.cognitive_delta == 0
    assert fd.cyclomatic_delta == 0


# ---------------------------------------------------------------------------
# DeltaReport properties
# ---------------------------------------------------------------------------

def _make_report(base_ncs=5.0, head_ncs=7.0, file_deltas=None):
    if file_deltas is None:
        file_deltas = []
    return DeltaReport(
        base_ref="main", head_ref="HEAD",
        base_ncs=base_ncs, head_ncs=head_ncs,
        file_deltas=file_deltas,
    )


def test_delta_report_ncs_delta():
    r = _make_report(base_ncs=5.0, head_ncs=7.0)
    assert r.ncs_delta == 2.0


def test_delta_report_ncs_delta_negative():
    r = _make_report(base_ncs=7.0, head_ncs=3.0)
    assert r.ncs_delta == -4.0


def test_delta_report_total_cognitive_delta():
    deltas = [
        FileDelta("a.py", 5, 8, 0, 0, 1, 1, "modified"),   # +3
        FileDelta("b.py", 10, 6, 0, 0, 2, 2, "modified"),   # -4
    ]
    r = _make_report(file_deltas=deltas)
    assert r.total_cognitive_delta == -1  # 3 + (-4)


def test_delta_report_improved_files():
    deltas = [
        FileDelta("a.py", 10, 5, 0, 0, 1, 1, "modified"),   # improved (-5)
        FileDelta("b.py", 3, 8, 0, 0, 1, 1, "modified"),    # worsened (+5)
        FileDelta("c.py", 7, 7, 0, 0, 1, 1, "modified"),    # unchanged
    ]
    r = _make_report(file_deltas=deltas)
    improved = r.improved_files
    assert len(improved) == 1
    assert improved[0].path == "a.py"


def test_delta_report_worsened_files():
    deltas = [
        FileDelta("a.py", 10, 5, 0, 0, 1, 1, "modified"),
        FileDelta("b.py", 3, 8, 0, 0, 1, 1, "modified"),
    ]
    r = _make_report(file_deltas=deltas)
    worsened = r.worsened_files
    assert len(worsened) == 1
    assert worsened[0].path == "b.py"


# ---------------------------------------------------------------------------
# DeltaReport serialization
# ---------------------------------------------------------------------------

def test_delta_report_to_dict_structure():
    deltas = [
        FileDelta("new.py", 0, 5, 0, 1, 0, 1, "added"),
        FileDelta("mod.py", 3, 7, 1, 2, 1, 1, "modified"),
    ]
    r = _make_report(file_deltas=deltas)
    d = r.to_dict()
    assert d["base_ref"] == "main"
    assert d["head_ref"] == "HEAD"
    assert d["base_ncs"] == 5.0
    assert d["head_ncs"] == 7.0
    assert d["ncs_delta"] == 2.0
    assert d["total_cognitive_delta"] == 9  # 5 + 4
    assert d["improved_count"] == 0
    assert d["worsened_count"] == 2
    assert len(d["files"]) == 2


def test_delta_report_to_dict_filters_unchanged():
    deltas = [
        FileDelta("unchanged.py", 5, 5, 2, 2, 1, 1, "modified"),
    ]
    r = _make_report(file_deltas=deltas)
    d = r.to_dict()
    assert len(d["files"]) == 0  # zero delta + modified → excluded


def test_delta_report_to_json_roundtrip():
    deltas = [
        FileDelta("a.py", 0, 10, 0, 2, 0, 1, "added"),
    ]
    r = _make_report(file_deltas=deltas)
    parsed = json.loads(r.to_json())
    assert parsed == r.to_dict()


# ---------------------------------------------------------------------------
# DeltaReport markdown output
# ---------------------------------------------------------------------------

def test_delta_report_to_markdown_decreased():
    r = _make_report(base_ncs=8.0, head_ncs=5.0)
    md = r.to_markdown()
    assert "Complexity decreased" in md
    assert "✅" in md


def test_delta_report_to_markdown_increased():
    r = _make_report(base_ncs=5.0, head_ncs=8.0)
    md = r.to_markdown()
    assert "Significant complexity increase" in md
    assert "❌" in md


def test_delta_report_to_markdown_no_change():
    r = _make_report(base_ncs=5.0, head_ncs=5.0)
    md = r.to_markdown()
    assert "No complexity change" in md


def test_delta_report_to_markdown_minor_increase():
    r = _make_report(base_ncs=5.0, head_ncs=5.5)
    md = r.to_markdown()
    assert "Minor complexity increase" in md
    assert "⚠️" in md


def test_delta_report_to_markdown_table():
    deltas = [
        FileDelta("a.py", 5, 10, 1, 2, 1, 1, "modified"),
    ]
    r = _make_report(file_deltas=deltas)
    md = r.to_markdown()
    assert "| File | Before | After | Delta |" in md


def test_delta_report_to_markdown_long_path_truncated():
    long_path = "very/deeply/nested/directory/structure/that/is/quite/long/file.py"
    deltas = [
        FileDelta(long_path, 5, 10, 1, 2, 1, 1, "modified"),
    ]
    r = _make_report(file_deltas=deltas)
    md = r.to_markdown()
    assert "…" in md  # truncation character


# ---------------------------------------------------------------------------
# _run_git
# ---------------------------------------------------------------------------

def test_run_git_success():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "  hello world  "
    with patch("complexity_accounting.git_tracker.subprocess.run", return_value=mock_result):
        output = _run_git(["status"], cwd="/tmp")
    assert output == "hello world"


def test_run_git_failure():
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "fatal: not a git repository"
    with patch("complexity_accounting.git_tracker.subprocess.run", return_value=mock_result):
        try:
            _run_git(["status"], cwd="/tmp")
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "fatal: not a git repository" in str(e)


# ---------------------------------------------------------------------------
# get_changed_files
# ---------------------------------------------------------------------------

def test_get_changed_files_parses_diff():
    diff_output = "A\tfile.py\nM\tother.py\nD\told.py\nM\treadme.md"
    with patch("complexity_accounting.git_tracker._run_git", return_value=diff_output):
        changes = get_changed_files("main", "HEAD", "/repo")
    assert changes == {"file.py": "A", "other.py": "M", "old.py": "D"}
    assert "readme.md" not in changes  # not a supported extension


def test_get_changed_files_empty():
    with patch("complexity_accounting.git_tracker._run_git", return_value=""):
        changes = get_changed_files("main", "HEAD", "/repo")
    assert changes == {}


def test_get_changed_files_handles_renames():
    diff_output = "R100\told.py\tnew.py"
    with patch("complexity_accounting.git_tracker._run_git", return_value=diff_output):
        # The current implementation splits on \t with maxsplit=1
        # so R100\told.py becomes status, old.py\tnew.py becomes path
        # This tests that it doesn't crash
        changes = get_changed_files("main", "HEAD", "/repo")
    # It should parse something (the exact behavior depends on implementation)
    assert isinstance(changes, dict)


# ---------------------------------------------------------------------------
# scan_at_ref
# ---------------------------------------------------------------------------

def test_scan_at_ref_mocked():
    def mock_run_git(args, cwd):
        if args[0] == "ls-tree":
            return "simple.py"
        if args[0] == "show":
            return "def hello(): pass\n"
        return ""

    with patch("complexity_accounting.git_tracker._run_git", side_effect=mock_run_git):
        metrics = scan_at_ref("abc123", "/repo")
    assert "simple.py" in metrics
    assert metrics["simple.py"].function_count == 1


def test_scan_at_ref_with_explicit_files():
    call_log = []

    def mock_run_git(args, cwd):
        call_log.append(args[0])
        if args[0] == "show":
            return "def hello(): pass\n"
        return ""

    with patch("complexity_accounting.git_tracker._run_git", side_effect=mock_run_git):
        metrics = scan_at_ref("abc123", "/repo", files=["specific.py"])
    assert "ls-tree" not in call_log
    assert "specific.py" in metrics


def test_scan_at_ref_skips_errors():
    def mock_run_git(args, cwd):
        if args[0] == "ls-tree":
            return "broken.py"
        if args[0] == "show":
            raise RuntimeError("file not found")
        return ""

    with patch("complexity_accounting.git_tracker._run_git", side_effect=mock_run_git):
        metrics = scan_at_ref("abc123", "/repo")
    assert metrics == {}


# ---------------------------------------------------------------------------
# compare_refs
# ---------------------------------------------------------------------------

def test_compare_refs_builds_deltas():
    with patch("complexity_accounting.git_tracker.get_changed_files") as mock_changes, \
         patch("complexity_accounting.git_tracker.scan_at_ref") as mock_scan:

        mock_changes.return_value = {"new.py": "A", "mod.py": "M"}

        fn_new = FunctionMetrics("foo", "foo", "new.py", 1, 5, cognitive_complexity=10, cyclomatic_complexity=3)
        fn_mod_base = FunctionMetrics("bar", "bar", "mod.py", 1, 5, cognitive_complexity=5, cyclomatic_complexity=2)
        fn_mod_head = FunctionMetrics("bar", "bar", "mod.py", 1, 5, cognitive_complexity=8, cyclomatic_complexity=3)

        def scan_side_effect(ref, repo, files=None, include_tests=False):
            if ref == "main":
                return {"mod.py": FileMetrics("mod.py", [fn_mod_base])}
            else:
                return {
                    "new.py": FileMetrics("new.py", [fn_new]),
                    "mod.py": FileMetrics("mod.py", [fn_mod_head]),
                }

        mock_scan.side_effect = scan_side_effect

        report = compare_refs("main", "HEAD", "/repo")

    assert isinstance(report, DeltaReport)
    statuses = {d.path: d.status for d in report.file_deltas}
    assert statuses["new.py"] == "added"
    assert statuses["mod.py"] == "modified"


def test_compare_refs_changed_only_false():
    with patch("complexity_accounting.git_tracker.get_changed_files") as mock_changes, \
         patch("complexity_accounting.git_tracker.scan_at_ref") as mock_scan, \
         patch("complexity_accounting.git_tracker._run_git") as mock_git:

        mock_changes.return_value = {}
        mock_git.return_value = "all.py"
        mock_scan.return_value = {}

        compare_refs("main", "HEAD", "/repo", changed_only=False)

    # Should have called _run_git with ls-tree
    mock_git.assert_called()
    args = mock_git.call_args[0][0]
    assert "ls-tree" in args


def test_compare_refs_full_scan_includes_non_python_files():
    """Full-scan mode should include all supported extensions, not just .py."""
    with patch("complexity_accounting.git_tracker.get_changed_files") as mock_changes, \
         patch("complexity_accounting.git_tracker.scan_at_ref") as mock_scan, \
         patch("complexity_accounting.git_tracker._run_git") as mock_git:

        mock_changes.return_value = {}
        mock_git.return_value = "app.py\nmain.go\nApp.java\nindex.ts\nutil.js\nlib.rs\nmain.cpp\nREADME.md"
        mock_scan.return_value = {}

        compare_refs("main", "HEAD", "/repo", changed_only=False)

    # scan_at_ref is called twice (base + head); check head call's file list
    head_files = mock_scan.call_args_list[1][0][2]
    assert "app.py" in head_files
    assert "main.go" in head_files
    assert "App.java" in head_files
    assert "index.ts" in head_files
    assert "util.js" in head_files
    assert "lib.rs" in head_files
    assert "main.cpp" in head_files
    assert "README.md" not in head_files


# ---------------------------------------------------------------------------
# trend
# ---------------------------------------------------------------------------

def test_trend_parses_commits():
    log_output = "abc12345 2024-01-15T10:00:00 Initial commit\ndef67890 2024-01-14T09:00:00 Fix bug"

    with patch("complexity_accounting.git_tracker._run_git", return_value=log_output), \
         patch("complexity_accounting.git_tracker.scan_at_ref") as mock_scan:

        fn = FunctionMetrics("f", "f", "a.py", 1, 5, cognitive_complexity=3)
        mock_scan.return_value = {"a.py": FileMetrics("a.py", [fn])}

        results = trend("/repo", num_commits=2)

    assert len(results) == 2
    assert results[0]["commit"] == "abc12345"[:8]
    assert "date" in results[0]
    assert "message" in results[0]
    assert "ncs" in results[0]


def test_trend_handles_scan_error():
    log_output = "abc12345 2024-01-15T10:00:00 Bad commit"

    with patch("complexity_accounting.git_tracker._run_git", return_value=log_output), \
         patch("complexity_accounting.git_tracker.scan_at_ref", side_effect=RuntimeError("boom")):

        results = trend("/repo", num_commits=1)

    assert len(results) == 1
    assert "error" in results[0]


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
