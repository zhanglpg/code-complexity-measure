"""Tests for git churn analysis."""
import math
import tempfile
from unittest.mock import patch, MagicMock
import subprocess

from complexity_accounting.churn import analyze_churn, compute_churn_factor


def test_churn_factor_empty():
    assert compute_churn_factor({}) == 1.0


def test_churn_factor_calculation():
    data = {"a.py": 5, "b.py": 3, "c.py": 2}
    # avg = 10/3 ≈ 3.333
    expected = round(1.0 + math.log1p(10 / 3) / 10, 4)
    assert compute_churn_factor(data) == expected


def test_churn_factor_single_file():
    data = {"main.py": 10}
    expected = round(1.0 + math.log1p(10) / 10, 4)
    assert compute_churn_factor(data) == expected


def test_analyze_churn_not_a_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = analyze_churn(tmpdir)
        assert result == {}


def test_analyze_churn_parses_numstat():
    mock_output = (
        "3\t1\tscanner.py\n"
        "5\t2\t__main__.py\n"
        "\n"
        "1\t0\tscanner.py\n"
        "2\t3\tconfig.py\n"
    )
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = mock_output

    with patch("complexity_accounting.churn.subprocess.run", return_value=mock_result):
        data = analyze_churn("/fake/repo")
        assert data["scanner.py"] == 2
        assert data["__main__.py"] == 1
        assert data["config.py"] == 1


# ---------------------------------------------------------------------------
# P2: Extended churn tests
# ---------------------------------------------------------------------------

def test_analyze_churn_subprocess_timeout():
    with patch("complexity_accounting.churn.subprocess.run",
               side_effect=subprocess.TimeoutExpired("git", 30)):
        result = analyze_churn("/fake/repo")
    assert result == {}


def test_analyze_churn_oserror():
    with patch("complexity_accounting.churn.subprocess.run",
               side_effect=OSError("No such file")):
        result = analyze_churn("/fake/repo")
    assert result == {}


def test_analyze_churn_malformed_output():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "malformed line\n5\t2\tvalid.py\nshort\n"
    with patch("complexity_accounting.churn.subprocess.run", return_value=mock_result):
        data = analyze_churn("/fake/repo")
    assert "valid.py" in data
    assert len(data) == 1  # malformed lines skipped


def test_analyze_churn_file_renames():
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "3\t1\t{old => new}/file.py\n"
    with patch("complexity_accounting.churn.subprocess.run", return_value=mock_result):
        data = analyze_churn("/fake/repo")
    assert len(data) == 1  # rename path counted as-is


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
