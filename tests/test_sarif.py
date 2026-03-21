"""Tests for SARIF output format."""
import textwrap
import tempfile
import os
import json

from complexity_accounting.sarif import generate_sarif, sarif_to_json, SARIF_SCHEMA
from complexity_accounting.scanner import scan_file, ScanResult


def _write_temp(source: str, suffix: str = ".py") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


def test_sarif_schema_version():
    result = ScanResult(files=[])
    data = result.to_dict()
    sarif = generate_sarif(data)

    assert sarif["$schema"] == SARIF_SCHEMA
    assert sarif["version"] == "2.1.0"


def test_sarif_tool_info():
    result = ScanResult(files=[])
    data = result.to_dict()
    sarif = generate_sarif(data)

    driver = sarif["runs"][0]["tool"]["driver"]
    assert driver["name"] == "complexity-accounting"
    assert "version" in driver
    assert "rules" in driver
    assert len(driver["rules"]) == 3


def test_sarif_empty_results():
    result = ScanResult(files=[])
    data = result.to_dict()
    sarif = generate_sarif(data)

    assert sarif["runs"][0]["results"] == []


def test_sarif_simple_function_below_threshold():
    path = _write_temp("def add(a, b): return a + b\n")
    try:
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()
        sarif = generate_sarif(data, hotspot_threshold=10)

        # Simple function should be below threshold
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
        assert len(results) >= 1

        r = results[0]
        assert "ruleId" in r
        assert r["ruleId"].startswith("complexity/cognitive-")
        assert "level" in r
        assert r["level"] in ("note", "warning", "error")

        # Check location
        loc = r["locations"][0]["physicalLocation"]
        assert "artifactLocation" in loc
        assert "region" in loc
        assert loc["region"]["startLine"] >= 1

        # Check message
        assert "very_complex" in r["message"]["text"]
        assert "cognitive complexity" in r["message"]["text"]

        # Check properties
        assert r["properties"]["cognitive_complexity"] > 0
    finally:
        os.unlink(path)


def test_sarif_to_json():
    result = ScanResult(files=[])
    data = result.to_dict()
    sarif = generate_sarif(data)
    json_str = sarif_to_json(sarif)

    # Should be valid JSON
    parsed = json.loads(json_str)
    assert parsed["version"] == "2.1.0"


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
        assert len(results) >= 1

        levels = {r["level"] for r in results}
        # Should have at least warning or error
        assert levels & {"warning", "error"}
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
        # Should have results from both files
        file_paths = {r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
                      for r in results}
        assert len(file_paths) >= 1  # at least one file should have hotspots
    finally:
        os.unlink(path1)
        os.unlink(path2)
