"""Tests for complexity_accounting.models module."""

import json
import math

import pytest

from complexity_accounting.models import (
    FunctionMetrics,
    FileMetrics,
    ScanResult,
    compute_mi,
    get_language,
)


# ---------------------------------------------------------------------------
# get_language
# ---------------------------------------------------------------------------

class TestGetLanguage:

    def test_python_extension(self):
        assert get_language("foo/bar.py") == "python"

    def test_go_extension(self):
        assert get_language("main.go") == "go"

    def test_java_extension(self):
        assert get_language("App.java") == "java"

    def test_javascript_js(self):
        assert get_language("index.js") == "javascript"

    def test_javascript_mjs(self):
        assert get_language("module.mjs") == "javascript"

    def test_javascript_cjs(self):
        assert get_language("common.cjs") == "javascript"

    def test_typescript_ts(self):
        assert get_language("app.ts") == "typescript"

    def test_typescript_tsx(self):
        assert get_language("component.tsx") == "typescript"

    def test_typescript_mts(self):
        assert get_language("mod.mts") == "typescript"

    def test_typescript_cts(self):
        assert get_language("mod.cts") == "typescript"

    def test_cpp_c(self):
        assert get_language("main.c") == "cpp"

    def test_cpp_cc(self):
        assert get_language("main.cc") == "cpp"

    def test_cpp_cpp(self):
        assert get_language("main.cpp") == "cpp"

    def test_cpp_cxx(self):
        assert get_language("main.cxx") == "cpp"

    def test_cpp_h(self):
        assert get_language("header.h") == "cpp"

    def test_cpp_hpp(self):
        assert get_language("header.hpp") == "cpp"

    def test_cpp_hxx(self):
        assert get_language("header.hxx") == "cpp"

    def test_rust_extension(self):
        assert get_language("lib.rs") == "rust"

    def test_unknown_extension_returns_none(self):
        assert get_language("README.md") is None

    def test_no_extension_returns_none(self):
        assert get_language("Makefile") is None

    def test_case_insensitive(self):
        assert get_language("App.PY") == "python"


# ---------------------------------------------------------------------------
# compute_mi
# ---------------------------------------------------------------------------

class TestComputeMi:

    def test_nloc_zero_returns_100(self):
        assert compute_mi(0, 5) == 100.0

    def test_nloc_negative_returns_100(self):
        assert compute_mi(-10, 5) == 100.0

    def test_sei_formula_with_halstead(self):
        # SEI formula: MI = max(0, min(100, (171 - 5.2*ln(HV) - 0.23*CC - 16.2*ln(LOC)) * 100/171))
        nloc, cc, hv = 50, 10, 200.0
        raw = 171.0 - 5.2 * math.log(hv) - 0.23 * cc - 16.2 * math.log(nloc)
        expected = round(max(0.0, min(100.0, raw * 100.0 / 171.0)), 2)
        assert compute_mi(nloc, cc, hv) == expected

    def test_vs_formula_without_halstead(self):
        # VS formula: MI = max(0, min(100, (171 - 21.4*ln(LOC) - 0.23*CC) * 100/171))
        nloc, cc = 50, 10
        raw = 171.0 - 21.4 * math.log(nloc) - 0.23 * cc
        expected = round(max(0.0, min(100.0, raw * 100.0 / 171.0)), 2)
        assert compute_mi(nloc, cc) == expected

    def test_halstead_zero_uses_vs_formula(self):
        # halstead_volume=0 should fall back to VS formula
        nloc, cc = 30, 5
        result_zero_hv = compute_mi(nloc, cc, 0.0)
        result_no_hv = compute_mi(nloc, cc)
        assert result_zero_hv == result_no_hv

    def test_halstead_negative_uses_vs_formula(self):
        nloc, cc = 30, 5
        result_neg_hv = compute_mi(nloc, cc, -10.0)
        result_no_hv = compute_mi(nloc, cc)
        assert result_neg_hv == result_no_hv

    def test_result_clamped_to_zero(self):
        # Very high complexity / volume should clamp to 0
        result = compute_mi(10000, 5000, 1e20)
        assert result == 0.0

    def test_result_clamped_to_100(self):
        # Tiny function should be close to or at 100
        result = compute_mi(1, 1)
        assert result <= 100.0
        assert result > 0.0
        # VS formula: max(0, min(100, (171 - 21.4*ln(1) - 0.23*1) * 100/171))
        raw = 171.0 - 21.4 * math.log(1) - 0.23 * 1
        expected = round(max(0.0, min(100.0, raw * 100.0 / 171.0)), 2)
        assert result == expected

    def test_higher_complexity_lowers_mi(self):
        mi_low = compute_mi(50, 2)
        mi_high = compute_mi(50, 100)
        assert mi_low > mi_high
        # Verify exact values using VS formula
        raw_low = 171.0 - 21.4 * math.log(50) - 0.23 * 2
        expected_low = round(max(0.0, min(100.0, raw_low * 100.0 / 171.0)), 2)
        assert mi_low == expected_low
        raw_high = 171.0 - 21.4 * math.log(50) - 0.23 * 100
        expected_high = round(max(0.0, min(100.0, raw_high * 100.0 / 171.0)), 2)
        assert mi_high == expected_high


# ---------------------------------------------------------------------------
# FunctionMetrics.risk_level and get_risk_level
# ---------------------------------------------------------------------------

def _make_func(cognitive=0, cyclomatic=1, nloc=10, mi=80.0):
    return FunctionMetrics(
        name="f",
        qualified_name="f",
        file_path="test.py",
        line=1,
        end_line=10,
        cognitive_complexity=cognitive,
        cyclomatic_complexity=cyclomatic,
        nloc=nloc,
        maintainability_index=mi,
    )


class TestFunctionMetricsRiskLevel:

    def test_low_risk(self):
        fn = _make_func(cognitive=3)
        assert fn.risk_level == "low"
        assert fn.cognitive_complexity == 3
        assert fn.name == "f"

    def test_low_boundary(self):
        fn = _make_func(cognitive=5)
        assert fn.risk_level == "low"
        assert fn.cognitive_complexity == 5
        assert fn.cyclomatic_complexity == 1

    def test_moderate_risk(self):
        fn = _make_func(cognitive=8)
        assert fn.risk_level == "moderate"
        assert fn.cognitive_complexity == 8

    def test_moderate_boundary(self):
        fn = _make_func(cognitive=10)
        assert fn.risk_level == "moderate"
        assert fn.cognitive_complexity == 10
        assert fn.name == "f"

    def test_high_risk(self):
        fn = _make_func(cognitive=15)
        assert fn.risk_level == "high"
        assert fn.cognitive_complexity == 15

    def test_high_boundary(self):
        fn = _make_func(cognitive=20)
        assert fn.risk_level == "high"
        assert fn.cognitive_complexity == 20
        assert fn.qualified_name == "f"

    def test_very_high_risk(self):
        fn = _make_func(cognitive=25)
        assert fn.risk_level == "very_high"
        assert fn.cognitive_complexity == 25
        assert fn.file_path == "test.py"


class TestFunctionMetricsGetRiskLevel:

    def test_custom_low_boundary(self):
        fn = _make_func(cognitive=3)
        assert fn.get_risk_level(low=2, moderate=5, high=10) == "moderate"
        assert fn.cognitive_complexity == 3

    def test_custom_moderate_boundary(self):
        fn = _make_func(cognitive=7)
        assert fn.get_risk_level(low=2, moderate=5, high=10) == "high"
        assert fn.cognitive_complexity == 7

    def test_custom_high_boundary(self):
        fn = _make_func(cognitive=15)
        assert fn.get_risk_level(low=2, moderate=5, high=10) == "very_high"
        assert fn.cognitive_complexity == 15

    def test_custom_all_low(self):
        fn = _make_func(cognitive=1)
        assert fn.get_risk_level(low=1, moderate=2, high=3) == "low"
        assert fn.cognitive_complexity == 1
        assert fn.risk_level == "low"


# ---------------------------------------------------------------------------
# FileMetrics properties and hotspots
# ---------------------------------------------------------------------------

def _make_file_metrics(complexities):
    """Create a FileMetrics with functions having the given cognitive complexities."""
    funcs = [
        _make_func(cognitive=cc, cyclomatic=cc + 1)
        for cc in complexities
    ]
    return FileMetrics(path="test.py", functions=funcs, total_lines=100, code_lines=80)


class TestFileMetricsProperties:

    def test_total_cognitive(self):
        fm = _make_file_metrics([3, 7, 12])
        assert fm.total_cognitive == 22

    def test_total_cyclomatic(self):
        fm = _make_file_metrics([3, 7, 12])
        # cyclomatic = cognitive + 1 for each
        assert fm.total_cyclomatic == 4 + 8 + 13

    def test_avg_cognitive(self):
        fm = _make_file_metrics([3, 7, 12])
        expected = 22 / 3
        assert abs(fm.avg_cognitive - expected) < 1e-9
        assert fm.function_count == 3
        assert fm.total_cognitive == 22

    def test_avg_cognitive_empty(self):
        fm = _make_file_metrics([])
        assert fm.avg_cognitive == 0.0

    def test_max_cognitive(self):
        fm = _make_file_metrics([3, 7, 12])
        assert fm.max_cognitive == 12

    def test_max_cognitive_empty(self):
        fm = _make_file_metrics([])
        assert fm.max_cognitive == 0

    def test_function_count(self):
        fm = _make_file_metrics([3, 7, 12])
        assert fm.function_count == 3

    def test_function_count_empty(self):
        fm = _make_file_metrics([])
        assert fm.function_count == 0


class TestFileMetricsHotspots:

    def test_default_threshold(self):
        fm = _make_file_metrics([3, 7, 10, 15, 25])
        hotspots = fm.hotspots()
        # threshold=10, so 10, 15, 25 qualify (>= 10)
        assert len(hotspots) == 3
        ccs = [h.cognitive_complexity for h in hotspots]
        assert 10 in ccs
        assert 15 in ccs
        assert 25 in ccs

    def test_custom_threshold(self):
        fm = _make_file_metrics([3, 7, 10, 15, 25])
        hotspots = fm.hotspots(threshold=15)
        assert len(hotspots) == 2
        ccs = [h.cognitive_complexity for h in hotspots]
        assert 15 in ccs
        assert 25 in ccs

    def test_no_hotspots(self):
        fm = _make_file_metrics([1, 2, 3])
        hotspots = fm.hotspots()
        assert len(hotspots) == 0
        assert fm.function_count == 3
        assert fm.max_cognitive == 3

    def test_all_hotspots(self):
        fm = _make_file_metrics([10, 20, 30])
        hotspots = fm.hotspots()
        assert len(hotspots) == 3
        assert fm.total_cognitive == 60
        assert fm.max_cognitive == 30

    def test_threshold_zero(self):
        fm = _make_file_metrics([0, 5, 10])
        hotspots = fm.hotspots(threshold=0)
        assert len(hotspots) == 3
        assert fm.total_cognitive == 15


# ---------------------------------------------------------------------------
# ScanResult properties
# ---------------------------------------------------------------------------

def _make_scan_result(file_complexities):
    """Create a ScanResult from a list of lists of cognitive complexities."""
    files = []
    for i, complexities in enumerate(file_complexities):
        funcs = [
            FunctionMetrics(
                name=f"f{j}",
                qualified_name=f"f{j}",
                file_path=f"file{i}.py",
                line=1,
                end_line=10,
                cognitive_complexity=cc,
                cyclomatic_complexity=cc + 1,
                nloc=10,
                maintainability_index=80.0 - cc,
            )
            for j, cc in enumerate(complexities)
        ]
        files.append(FileMetrics(path=f"file{i}.py", functions=funcs, total_lines=50))
    return ScanResult(files=files)


class TestScanResultProperties:

    def test_total_cognitive(self):
        sr = _make_scan_result([[3, 7], [12, 5]])
        assert sr.total_cognitive == 27

    def test_total_cyclomatic(self):
        sr = _make_scan_result([[3, 7], [12, 5]])
        # cyclomatic = cognitive + 1 for each
        assert sr.total_cyclomatic == 4 + 8 + 13 + 6

    def test_total_functions(self):
        sr = _make_scan_result([[3, 7], [12, 5]])
        assert sr.total_functions == 4

    def test_avg_maintainability_index(self):
        sr = _make_scan_result([[3, 7], [12, 5]])
        # MI values: 77, 73, 68, 75 => avg = 293/4
        expected = round(293.0 / 4, 2)
        assert sr.avg_maintainability_index == expected

    def test_avg_maintainability_index_empty(self):
        sr = ScanResult(files=[])
        assert sr.avg_maintainability_index == 100.0

    def test_total_cognitive_empty(self):
        sr = ScanResult(files=[])
        assert sr.total_cognitive == 0

    def test_total_functions_empty(self):
        sr = ScanResult(files=[])
        assert sr.total_functions == 0


# ---------------------------------------------------------------------------
# ScanResult.compute_ncs
# ---------------------------------------------------------------------------

class TestScanResultComputeNcs:

    def test_no_functions_returns_zero(self):
        sr = ScanResult(files=[])
        assert sr.compute_ncs() == 0.0
        assert sr.total_functions == 0
        assert sr.total_cognitive == 0

    def test_no_functions_with_empty_file(self):
        sr = ScanResult(files=[FileMetrics(path="empty.py")])
        assert sr.compute_ncs() == 0.0
        assert sr.total_functions == 0

    def test_ncs_positive_for_complex_code(self):
        sr = _make_scan_result([[10, 20]])
        ncs = sr.compute_ncs()
        assert ncs > 0.0

    def test_ncs_increases_with_complexity(self):
        sr_low = _make_scan_result([[2, 3]])
        sr_high = _make_scan_result([[20, 30]])
        assert sr_high.compute_ncs() > sr_low.compute_ncs()


# ---------------------------------------------------------------------------
# ScanResult.to_dict and to_json
# ---------------------------------------------------------------------------

class TestScanResultSerialization:

    def test_to_dict_has_summary_and_files(self):
        sr = _make_scan_result([[5, 15]])
        d = sr.to_dict()
        assert "summary" in d
        assert "files" in d
        assert len(d["files"]) == 1

    def test_to_dict_summary_keys(self):
        sr = _make_scan_result([[5, 15]])
        summary = sr.to_dict()["summary"]
        expected_keys = {
            "files_scanned",
            "total_functions",
            "total_cognitive_complexity",
            "total_cyclomatic_complexity",
            "net_complexity_score",
            "avg_cognitive_per_function",
            "hotspot_count",
            "avg_maintainability_index",
        }
        assert set(summary.keys()) == expected_keys

    def test_to_dict_summary_values(self):
        sr = _make_scan_result([[5, 15]])
        summary = sr.to_dict()["summary"]
        assert summary["files_scanned"] == 1
        assert summary["total_functions"] == 2
        assert summary["total_cognitive_complexity"] == 20
        assert summary["total_cyclomatic_complexity"] == 6 + 16
        assert summary["avg_cognitive_per_function"] == 10.0

    def test_to_dict_file_entry_keys(self):
        sr = _make_scan_result([[5]])
        file_entry = sr.to_dict()["files"][0]
        for key in ["path", "total_lines", "code_lines", "comment_lines",
                     "function_count", "total_cognitive", "total_cyclomatic",
                     "avg_cognitive", "max_cognitive", "functions", "classes"]:
            assert key in file_entry, f"Missing key: {key}"

    def test_to_dict_file_entry_values(self):
        sr = _make_scan_result([[5, 15]])
        file_entry = sr.to_dict()["files"][0]
        assert file_entry["path"] == "file0.py"
        assert file_entry["function_count"] == 2
        assert file_entry["total_cognitive"] == 20
        assert file_entry["max_cognitive"] == 15

    def test_to_dict_functions_list(self):
        sr = _make_scan_result([[5]])
        funcs = sr.to_dict()["files"][0]["functions"]
        assert len(funcs) == 1
        assert funcs[0]["name"] == "f0"
        assert funcs[0]["cognitive_complexity"] == 5

    def test_to_json_is_valid_json(self):
        sr = _make_scan_result([[5, 15]])
        j = sr.to_json()
        parsed = json.loads(j)
        assert "summary" in parsed
        assert "files" in parsed
        assert parsed["summary"]["total_functions"] == 2
        assert parsed["summary"]["files_scanned"] == 1

    def test_to_json_indent(self):
        sr = _make_scan_result([[5]])
        j4 = sr.to_json(indent=4)
        # With indent=4, lines should start with 4-space indentation
        assert "\n    " in j4
        parsed = json.loads(j4)
        assert parsed["summary"]["total_functions"] == 1

    def test_to_dict_hotspot_count(self):
        # 15 is a hotspot (>=10), 5 is not
        sr = _make_scan_result([[5, 15]])
        summary = sr.to_dict()["summary"]
        assert summary["hotspot_count"] == 1

    def test_to_dict_empty_scan(self):
        sr = ScanResult(files=[])
        d = sr.to_dict()
        assert d["summary"]["files_scanned"] == 0
        assert d["summary"]["total_functions"] == 0
        assert len(d["files"]) == 0
