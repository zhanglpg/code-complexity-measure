"""Tests for import coupling analysis."""
import os
import tempfile
import textwrap

from complexity_accounting.coupling import (
    analyze_file_coupling,
    analyze_directory_coupling,
    compute_coupling_factor,
    CouplingMetrics,
)


def _write_temp(source: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


def test_basic_imports():
    path = _write_temp("""
        import requests
        import json
        from pathlib import Path
        from flask import Flask
    """)
    try:
        m = analyze_file_coupling(path)
        # json and pathlib are stdlib, should be filtered
        # requests and flask are external
        assert m.efferent_coupling == 2
        assert "requests" in m.imports
        assert "flask" in m.imports
    finally:
        os.unlink(path)


def test_no_imports():
    path = _write_temp("""
        def hello():
            return "world"
    """)
    try:
        m = analyze_file_coupling(path)
        assert m.efferent_coupling == 0
        assert m.imports == []
        assert len(m.imports) == 0
    finally:
        os.unlink(path)


def test_stdlib_only():
    path = _write_temp("""
        import os
        import sys
        from pathlib import Path
        from collections import defaultdict
    """)
    try:
        m = analyze_file_coupling(path)
        assert m.efferent_coupling == 0
        assert m.imports == []
        assert len(m.imports) == 0
    finally:
        os.unlink(path)


def test_dedup_top_level():
    path = _write_temp("""
        from requests import get
        from requests.auth import HTTPBasicAuth
    """)
    try:
        m = analyze_file_coupling(path)
        # Both are 'requests' top-level, counted once
        assert m.efferent_coupling == 1
        assert len(m.imports) == 1
    finally:
        os.unlink(path)


def test_compute_coupling_factor_empty():
    assert compute_coupling_factor({}) == 1.0


def test_compute_coupling_factor_all_zero():
    data = {"a.py": CouplingMetrics("a.py", 0, []), "b.py": CouplingMetrics("b.py", 0, [])}
    assert compute_coupling_factor(data) == 1.0


def test_compute_coupling_factor_nonzero():
    data = {
        "a.py": CouplingMetrics("a.py", 4, []),
        "b.py": CouplingMetrics("b.py", 2, []),
    }
    factor = compute_coupling_factor(data)
    # avg=3, max=4, factor = 1 + 3/4 = 1.75
    assert factor == 1.75


def test_directory_coupling():
    with tempfile.TemporaryDirectory() as tmpdir:
        from pathlib import Path

        (Path(tmpdir) / "a.py").write_text("import requests\n")
        (Path(tmpdir) / "b.py").write_text("import os\n")

        data = analyze_directory_coupling(tmpdir)
        assert len(data) == 2
        assert data["a.py"].efferent_coupling == 1
        assert data["b.py"].efferent_coupling == 0


# ---------------------------------------------------------------------------
# P2: Extended coupling tests
# ---------------------------------------------------------------------------

def test_relative_import():
    path = _write_temp("""
        from . import utils
        from ..core import base
    """)
    try:
        m = analyze_file_coupling(path)
        # Relative imports: '..core' resolves to 'core' which is not stdlib
        assert m.efferent_coupling == 1
        assert "core" in m.imports
        assert len(m.imports) == 1
    finally:
        os.unlink(path)


def test_star_import():
    path = _write_temp("""
        from somelib import *
    """)
    try:
        m = analyze_file_coupling(path)
        # Star import from external package counts as coupling
        assert m.efferent_coupling == 1
        assert "somelib" in m.imports
        assert len(m.imports) == 1
    finally:
        os.unlink(path)


def test_parser_syntax_error():
    fd, path = tempfile.mkstemp(suffix=".py")
    os.write(fd, b"def broken(:\n    pass\n")
    os.close(fd)
    try:
        m = analyze_file_coupling(path)
        assert m.efferent_coupling == 0
    finally:
        os.unlink(path)


def test_compute_coupling_factor_boundary():
    """All files with equal coupling → factor = 1 + avg/max = 2.0."""
    data = {
        "a.py": CouplingMetrics("a.py", 5, []),
        "b.py": CouplingMetrics("b.py", 5, []),
    }
    factor = compute_coupling_factor(data)
    assert factor == 2.0


def test_compute_coupling_factor_one_zero():
    data = {
        "a.py": CouplingMetrics("a.py", 0, []),
        "b.py": CouplingMetrics("b.py", 6, []),
    }
    factor = compute_coupling_factor(data)
    # avg=3, max=6, factor = 1 + 3/6 = 1.5
    assert factor == 1.5


# ---------------------------------------------------------------------------
# Coverage gap: star import early return (line 74)
# ---------------------------------------------------------------------------

def test_star_import_import_statement():
    """'import *' style — ImportStar handling in visit_Import."""
    path = _write_temp("""
        from somelib import *
        import requests
    """)
    try:
        m = analyze_file_coupling(path)
        # The star import is skipped; requests is counted
        assert "requests" in m.imports
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Coverage gap: _dotted_name fallback (line 92)
# ---------------------------------------------------------------------------

def test_dotted_name_nested_attribute():
    """Deep attribute import: from a.b.c import something."""
    path = _write_temp("""
        from a.b.c.d import something
    """)
    try:
        m = analyze_file_coupling(path)
        # a.b.c.d → top-level module is 'a', counted as 1 external coupling
        assert m.efferent_coupling == 1
        assert "a.b.c.d" in m.imports
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Coverage gap: analyze_directory_coupling exclusion + error (lines 155, 158-159)
# ---------------------------------------------------------------------------

def test_directory_coupling_with_exclusion():
    """Files matching exclude_patterns should be skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from pathlib import Path

        (Path(tmpdir) / "main.py").write_text("import requests\n")
        (Path(tmpdir) / "test_something.py").write_text("import pytest\n")

        data = analyze_directory_coupling(tmpdir, exclude_patterns=["test_*"])
        assert "main.py" in data
        assert "test_something.py" not in data


def test_directory_coupling_skips_broken_files():
    """Files that fail to parse should be skipped silently."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from pathlib import Path

        (Path(tmpdir) / "good.py").write_text("import requests\n")
        (Path(tmpdir) / "bad.py").write_bytes(b"\x00\x01\x02\x03")

        data = analyze_directory_coupling(tmpdir)
        # Should have at least the good file
        assert "good.py" in data


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
