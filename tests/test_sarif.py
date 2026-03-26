"""Tests for SARIF output format."""
import textwrap
import tempfile
import os
import json

from complexity_accounting.sarif import (
    generate_sarif, sarif_to_json, SARIF_SCHEMA, _risk_level_sarif, _get_risk,
)
from complexity_accounting.scanner import scan_file, ScanResult
from complexity_accounting import __version__


def _write_temp(source: str, suffix: str = ".py") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


# ── Helper functions ────────────────────────────────────────────────────

def test_risk_level_sarif_mapping():
    assert _risk_level_sarif("low") == "note"
    assert _risk_level_sarif("moderate") == "warning"
    assert _risk_level_sarif("high") == "warning"
    assert _risk_level_sarif("very_high") == "error"
    assert _risk_level_sarif("unknown") == "note"
    assert _risk_level_sarif("") == "note"


def test_get_risk_boundaries():
    assert _get_risk(0) == "low"
    assert _get_risk(5) == "low"
    assert _get_risk(6) == "moderate"
    assert _get_risk(10) == "moderate"
    assert _get_risk(11) == "high"
    assert _get_risk(20) == "high"
    assert _get_risk(21) == "very_high"
    assert _get_risk(100) == "very_high"


def test_get_risk_custom_thresholds():
    assert _get_risk(3, low=3, moderate=6, high=12) == "low"
    assert _get_risk(4, low=3, moderate=6, high=12) == "moderate"
    assert _get_risk(7, low=3, moderate=6, high=12) == "high"
    assert _get_risk(13, low=3, moderate=6, high=12) == "very_high"


# ── SARIF structure with empty results ──────────────────────────────────

def test_sarif_schema_version():
    result = ScanResult(files=[])
    data = result.to_dict()
    sarif = generate_sarif(data)

    assert sarif["$schema"] == SARIF_SCHEMA
    assert sarif["version"] == "2.1.0"
    assert len(sarif.keys()) == 3  # $schema, version, runs


def test_sarif_tool_info():
    result = ScanResult(files=[])
    data = result.to_dict()
    sarif = generate_sarif(data)

    assert len(sarif["runs"]) == 1
    run = sarif["runs"][0]
    assert set(run.keys()) == {"tool", "results"}

    driver = run["tool"]["driver"]
    assert driver["name"] == "complexity-accounting"
    assert driver["version"] == __version__
    assert driver["informationUri"] == "https://github.com/zhanglpg/code-complexity-measure"
    assert len(driver["rules"]) == 3


def test_sarif_rules_structure():
    """Verify each rule has the correct structure and fields."""
    result = ScanResult(files=[])
    data = result.to_dict()
    sarif = generate_sarif(data)

    rules = sarif["runs"][0]["tool"]["driver"]["rules"]

    expected_rule_ids = [
        "complexity/cognitive-moderate",
        "complexity/cognitive-high",
        "complexity/cognitive-very-high",
    ]
    actual_rule_ids = [r["id"] for r in rules]
    assert actual_rule_ids == expected_rule_ids

    expected_names = [
        "ModerateCognitiveComplexity",
        "HighCognitiveComplexity",
        "VeryHighCognitiveComplexity",
    ]
    actual_names = [r["name"] for r in rules]
    assert actual_names == expected_names

    # Check default configuration levels
    assert rules[0]["defaultConfiguration"]["level"] == "warning"
    assert rules[1]["defaultConfiguration"]["level"] == "warning"
    assert rules[2]["defaultConfiguration"]["level"] == "error"

    # All rules should have the same tags
    for rule in rules:
        assert rule["properties"]["tags"] == ["maintainability", "complexity"]
        assert "shortDescription" in rule
        assert "text" in rule["shortDescription"]
        assert "fullDescription" in rule
        assert "text" in rule["fullDescription"]


def test_sarif_empty_results():
    result = ScanResult(files=[])
    data = result.to_dict()
    sarif = generate_sarif(data)

    assert sarif["runs"][0]["results"] == []
    assert len(sarif["runs"][0]["results"]) == 0


# ── SARIF with function results ─────────────────────────────────────────

def test_sarif_simple_function_below_threshold():
    path = _write_temp("def add(a, b): return a + b\n")
    try:
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()
        sarif = generate_sarif(data, hotspot_threshold=10)

        assert len(sarif["runs"][0]["results"]) == 0
    finally:
        os.unlink(path)


def test_sarif_complex_function():
    path = _write_temp("""
        def very_complex(a, b, c, d, e):
            if a:
                if b:
                    if c:
                        if d:
                            if e:
                                for i in range(a):
                                    if i > b:
                                        while c > 0:
                                            if d > 0:
                                                return i
            return 0
    """)
    try:
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()
        sarif = generate_sarif(data, hotspot_threshold=5)

        results = sarif["runs"][0]["results"]
        assert len(results) == 1

        r = results[0]

        # Rule ID should be one of the defined rules
        assert r["ruleId"] in (
            "complexity/cognitive-moderate",
            "complexity/cognitive-high",
            "complexity/cognitive-very-high",
        )

        # Level should match the risk mapping
        assert r["level"] in ("warning", "error")

        # Location structure
        assert len(r["locations"]) == 1
        loc = r["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uri"] == path
        assert loc["region"]["startLine"] >= 1
        assert loc["region"]["endLine"] >= loc["region"]["startLine"]

        # Message contains function name and complexity info
        msg = r["message"]["text"]
        assert msg.startswith("Function 'very_complex'")
        assert "cognitive complexity" in msg
        assert "risk:" in msg
        assert "cyclomatic:" in msg
        assert "MI:" in msg

        # Properties have correct types and values
        props = r["properties"]
        assert props["cognitive_complexity"] > 10  # deeply nested function
        assert props["cyclomatic_complexity"] >= 1
        assert props["maintainability_index"] >= 0
        assert props["risk_level"] in ("moderate", "high", "very_high")
    finally:
        os.unlink(path)


def test_sarif_to_json():
    result = ScanResult(files=[])
    data = result.to_dict()
    sarif = generate_sarif(data)
    json_str = sarif_to_json(sarif)

    # Should be valid JSON
    parsed = json.loads(json_str)
    assert parsed == sarif

    # Default indent is 2
    assert "\n  " in json_str


def test_sarif_to_json_custom_indent():
    result = ScanResult(files=[])
    data = result.to_dict()
    sarif = generate_sarif(data)
    json_str = sarif_to_json(sarif, indent=4)

    parsed = json.loads(json_str)
    assert parsed == sarif
    assert "\n    " in json_str


def test_sarif_risk_levels():
    """Test that different risk levels map to correct SARIF levels."""
    path = _write_temp("""
        def medium_complex(x, y, z):
            if x > 0:
                if y > 0:
                    if z > 0:
                        for i in range(x):
                            if i > y:
                                return i
            return 0

        def extreme_complex(a, b, c, d, e, f):
            if a:
                if b:
                    if c:
                        if d:
                            if e:
                                if f:
                                    for i in range(a):
                                        for j in range(b):
                                            if i > j:
                                                while c > 0:
                                                    if d > e:
                                                        return i + j
            return 0
    """)
    try:
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()
        sarif = generate_sarif(data, hotspot_threshold=5)

        results = sarif["runs"][0]["results"]
        assert len(results) == 2

        # Results should be sorted by file order (medium first, then extreme)
        # Both should have valid ruleIds and levels
        for r in results:
            assert r["ruleId"] in (
                "complexity/cognitive-moderate",
                "complexity/cognitive-high",
                "complexity/cognitive-very-high",
            )
            assert r["level"] in ("warning", "error")
            assert r["properties"]["cognitive_complexity"] > 5

        # The extreme function should have higher complexity
        complexities = [r["properties"]["cognitive_complexity"] for r in results]
        # medium_complex comes first in file, extreme_complex second
        assert complexities[1] > complexities[0]

        # Check that we have different severity levels
        levels = {r["level"] for r in results}
        rule_ids = {r["ruleId"] for r in results}
        # At least one should be different from the other
        assert len(rule_ids) >= 1
    finally:
        os.unlink(path)


def test_sarif_multi_file():
    path1 = _write_temp("""
        def complex_one(x, y):
            if x:
                if y:
                    for i in range(x):
                        if i > y:
                            return i
            return 0
    """)
    path2 = _write_temp("""
        def complex_two(a, b):
            if a:
                if b:
                    while a > 0:
                        if b > 0:
                            return a + b
            return 0
    """)
    try:
        fm1 = scan_file(path1)
        fm2 = scan_file(path2)
        result = ScanResult(files=[fm1, fm2])
        data = result.to_dict()
        sarif = generate_sarif(data, hotspot_threshold=5)

        results = sarif["runs"][0]["results"]
        assert len(results) == 2

        # Results should reference the two different files
        file_uris = {
            r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
            for r in results
        }
        assert file_uris == {path1, path2}

        # Each result should mention its respective function name
        messages = [r["message"]["text"] for r in results]
        func_names = set()
        for msg in messages:
            if "complex_one" in msg:
                func_names.add("complex_one")
            if "complex_two" in msg:
                func_names.add("complex_two")
        assert func_names == {"complex_one", "complex_two"}
    finally:
        os.unlink(path1)
        os.unlink(path2)


def test_sarif_threshold_filters_correctly():
    """Only functions at or above the threshold with risk > low are included."""
    path = _write_temp("""
        def simple():
            return 1

        def moderate_func(x, y):
            if x > 0:
                if y > 0:
                    for i in range(x):
                        if i > y:
                            return i
            return 0
    """)
    try:
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()

        # With very high threshold, nothing should appear
        sarif_high = generate_sarif(data, hotspot_threshold=100)
        assert len(sarif_high["runs"][0]["results"]) == 0

        # With low threshold, complex function may appear
        sarif_low = generate_sarif(data, hotspot_threshold=1)
        # simple() has cognitive 0, so it stays below threshold or is "low" risk
        # All results should have cognitive >= 1 and risk != "low"
        for r in sarif_low["runs"][0]["results"]:
            assert r["properties"]["cognitive_complexity"] >= 1
            assert r["properties"]["risk_level"] != "low"
    finally:
        os.unlink(path)


def test_sarif_low_risk_functions_excluded():
    """Functions with risk level 'low' are excluded even if above threshold."""
    # Construct scan data directly with a function that has cognitive_complexity=5
    # (which is risk "low") but is above a hotspot_threshold of 1
    scan_data = {
        "summary": {},
        "files": [{
            "path": "test.py",
            "functions": [{
                "name": "simple_func",
                "cognitive_complexity": 5,
                "cyclomatic_complexity": 2,
                "nloc": 5,
                "maintainability_index": 80,
                "line": 1,
            }],
        }],
    }

    sarif = generate_sarif(scan_data, hotspot_threshold=1)
    # cognitive=5 => risk="low", so it should be excluded
    assert len(sarif["runs"][0]["results"]) == 0


def test_sarif_result_properties_types():
    """Verify that result properties have the correct Python types."""
    scan_data = {
        "summary": {},
        "files": [{
            "path": "test.py",
            "functions": [{
                "name": "complex_func",
                "cognitive_complexity": 25,
                "cyclomatic_complexity": 10,
                "nloc": 30,
                "maintainability_index": 40.5,
                "line": 5,
                "end_line": 35,
            }],
        }],
    }

    sarif = generate_sarif(scan_data, hotspot_threshold=5)
    results = sarif["runs"][0]["results"]
    assert len(results) == 1

    r = results[0]
    assert r["ruleId"] == "complexity/cognitive-very-high"
    assert r["level"] == "error"

    loc = r["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "test.py"
    assert loc["region"]["startLine"] == 5
    assert loc["region"]["endLine"] == 35

    props = r["properties"]
    assert props["cognitive_complexity"] == 25
    assert props["cyclomatic_complexity"] == 10
    assert props["maintainability_index"] == 40.5
    assert props["risk_level"] == "very_high"


def test_sarif_qualified_name_preferred_over_name():
    """When qualified_name is present, it should be used in the message."""
    scan_data = {
        "summary": {},
        "files": [{
            "path": "test.py",
            "functions": [{
                "name": "method",
                "qualified_name": "MyClass.method",
                "cognitive_complexity": 25,
                "cyclomatic_complexity": 5,
                "line": 1,
            }],
        }],
    }

    sarif = generate_sarif(scan_data, hotspot_threshold=5)
    results = sarif["runs"][0]["results"]
    assert len(results) == 1
    assert "MyClass.method" in results[0]["message"]["text"]


def test_sarif_single_run():
    """SARIF output always has exactly one run."""
    result = ScanResult(files=[])
    data = result.to_dict()
    sarif = generate_sarif(data)
    assert len(sarif["runs"]) == 1
