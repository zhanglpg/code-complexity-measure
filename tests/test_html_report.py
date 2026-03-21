"""Tests for HTML report generation."""
import textwrap
import tempfile
import os

from complexity_accounting.html_report import generate_html_report, _ncs_rating, _esc
from complexity_accounting.scanner import scan_file, ScanResult


def _write_temp(source: str, suffix: str = ".py") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


# ── Helper functions ────────────────────────────────────────────────────

def test_ncs_rating_healthy():
    label, cls = _ncs_rating(2.0)
    assert label == "Healthy"
    assert cls == "healthy"


def test_ncs_rating_moderate():
    label, cls = _ncs_rating(5.0)
    assert label == "Moderate"
    assert cls == "moderate"


def test_ncs_rating_concerning():
    label, cls = _ncs_rating(8.0)
    assert label == "Concerning"
    assert cls == "concerning"


def test_ncs_rating_critical():
    label, cls = _ncs_rating(15.0)
    assert label == "Critical"
    assert cls == "critical"


def test_html_escape():
    assert _esc('<script>') == '&lt;script&gt;'
    assert _esc('"hello"') == '&quot;hello&quot;'
    assert _esc('a & b') == 'a &amp; b'


# ── Report generation ──────────────────────────────────────────────────

def test_html_report_basic():
    path = _write_temp("""
        def simple():
            return 1

        def complex_func(x, y):
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
        ncs = result.compute_ncs()

        html = generate_html_report(data, ncs)

        assert "<!DOCTYPE html>" in html
        assert "Complexity Accounting Report" in html
        assert "simple" in html
        assert "complex_func" in html
        assert str(ncs) in html
    finally:
        os.unlink(path)


def test_html_report_with_classes():
    path = _write_temp("""
        class MyService:
            def process(self, x):
                if x > 0:
                    return x * 2
                return 0

            def validate(self, data):
                return data is not None
    """)
    try:
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()
        ncs = result.compute_ncs()

        html = generate_html_report(data, ncs)

        assert "MyService" in html
        assert "Class Metrics" in html
        assert "WMC" in html
    finally:
        os.unlink(path)


def test_html_report_with_explanation():
    path = _write_temp("def foo(): return 1\n")
    try:
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()
        ncs = result.compute_ncs()
        explanation = result.compute_ncs_explained()

        html = generate_html_report(data, ncs, explanation=explanation)

        assert "NCS Breakdown" in html
        assert "Base complexity" in html
        assert "Hotspot effect" in html
    finally:
        os.unlink(path)


def test_html_report_self_contained():
    """HTML report should be self-contained with embedded CSS/JS."""
    path = _write_temp("def foo(): return 1\n")
    try:
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()
        html = generate_html_report(data, result.compute_ncs())

        assert "<style>" in html
        assert "<script>" in html
        assert "sortTable" in html
        # No external references
        assert "http://" not in html.split("<style>")[1].split("</style>")[0]
    finally:
        os.unlink(path)


def test_html_report_empty_scan():
    result = ScanResult(files=[])
    data = result.to_dict()
    html = generate_html_report(data, 0.0)
    assert "<!DOCTYPE html>" in html
    assert "0.0" in html or "0" in html


def test_html_report_sortable_tables():
    path = _write_temp("""
        def foo():
            return 1

        def bar():
            if True:
                return 2
    """)
    try:
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()
        html = generate_html_report(data, result.compute_ncs())

        assert "sortable" in html
        assert "onclick" in html
    finally:
        os.unlink(path)
