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
