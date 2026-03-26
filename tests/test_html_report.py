"""Tests for HTML report generation."""
import textwrap
import tempfile
import os

from complexity_accounting.html_report import (
    generate_html_report, _ncs_rating, _esc, _risk_class, _short_path, _get_risk,
)
from complexity_accounting.scanner import scan_file, ScanResult


def _write_temp(source: str, suffix: str = ".py") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


def _minimal_scan_data(files=None):
    """Build a minimal scan_data dict suitable for generate_html_report."""
    if files is None:
        files = []
    total_functions = sum(f.get("function_count", 0) for f in files)
    return {
        "summary": {
            "files_scanned": len(files),
            "total_functions": total_functions,
            "avg_cognitive_per_function": 0,
            "hotspot_count": 0,
            "avg_maintainability_index": 100,
        },
        "files": files,
    }


# ── Helper functions ────────────────────────────────────────────────────

def test_ncs_rating_healthy():
    label, cls = _ncs_rating(2.0)
    assert label == "Healthy"
    assert cls == "healthy"


def test_ncs_rating_boundary_3():
    """NCS exactly 3 should be Healthy."""
    label, cls = _ncs_rating(3.0)
    assert label == "Healthy"
    assert cls == "healthy"


def test_ncs_rating_moderate():
    label, cls = _ncs_rating(5.0)
    assert label == "Moderate"
    assert cls == "moderate"


def test_ncs_rating_boundary_6():
    """NCS exactly 6 should be Moderate."""
    label, cls = _ncs_rating(6.0)
    assert label == "Moderate"
    assert cls == "moderate"


def test_ncs_rating_concerning():
    label, cls = _ncs_rating(8.0)
    assert label == "Concerning"
    assert cls == "concerning"


def test_ncs_rating_boundary_10():
    """NCS exactly 10 should be Concerning."""
    label, cls = _ncs_rating(10.0)
    assert label == "Concerning"
    assert cls == "concerning"


def test_ncs_rating_critical():
    label, cls = _ncs_rating(15.0)
    assert label == "Critical"
    assert cls == "critical"


def test_ncs_rating_zero():
    label, cls = _ncs_rating(0.0)
    assert label == "Healthy"
    assert cls == "healthy"


def test_html_escape():
    assert _esc('<script>') == '&lt;script&gt;'
    assert _esc('"hello"') == '&quot;hello&quot;'
    assert _esc('a & b') == 'a &amp; b'
    assert _esc('plain text') == 'plain text'
    assert _esc('') == ''


def test_risk_class_mapping():
    assert _risk_class("low") == "risk-low"
    assert _risk_class("moderate") == "risk-moderate"
    assert _risk_class("high") == "risk-high"
    assert _risk_class("very_high") == "risk-critical"
    assert _risk_class("unknown") == ""
    assert _risk_class("") == ""


def test_short_path_short():
    assert _short_path("src/main.py") == "src/main.py"


def test_short_path_exactly_50():
    path = "a" * 50
    assert _short_path(path) == path


def test_short_path_long():
    path = "a" * 51
    result = _short_path(path)
    assert result.startswith("...")
    assert len(result) == 50
    assert result == "..." + path[-47:]


def test_get_risk_levels():
    assert _get_risk(0) == "low"
    assert _get_risk(5) == "low"
    assert _get_risk(6) == "moderate"
    assert _get_risk(10) == "moderate"
    assert _get_risk(11) == "high"
    assert _get_risk(20) == "high"
    assert _get_risk(21) == "very_high"
    assert _get_risk(100) == "very_high"


# ── Report generation ──────────────────────────────────────────────────

def test_html_report_empty_scan():
    """Empty scan produces valid HTML with zero values."""
    result = ScanResult(files=[])
    data = result.to_dict()
    html = generate_html_report(data, 0.0)

    # Document structure
    assert html.startswith("<!DOCTYPE html>")
    assert html.count("<!DOCTYPE html>") == 1
    assert html.count("<html") == 1
    assert html.count("</html>") == 1
    assert html.count("<head>") == 1
    assert html.count("</head>") == 1
    assert html.count("<body>") == 1
    assert html.count("</body>") == 1

    # NCS badge for 0.0 should be healthy
    assert 'class="ncs-badge healthy"' in html
    assert '<span class="ncs-value">0.0</span>' in html
    assert '<span class="ncs-label">Healthy</span>' in html

    # Summary table values
    assert "Files scanned</td><td>0</td>" in html
    assert "Total functions</td><td>0</td>" in html
    assert "Hotspot count</td><td>0</td>" in html

    # No hotspots section since no functions exist
    assert "Top" not in html or "Most Complex Functions" not in html

    # Files table should exist but be empty of data rows
    assert html.count("class=\"files\"") == 1


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

        # Document structure
        assert html.startswith("<!DOCTYPE html>")
        assert html.count("<title>Complexity Accounting Report</title>") == 1
        assert html.count("<h1>Complexity Accounting Report</h1>") == 1

        # Summary section exists
        assert html.count('class="summary"') == 1
        assert html.count('class="summary-table"') == 1

        # Both functions appear in the report
        assert "simple" in html
        assert "complex_func" in html

        # NCS value displayed
        assert f'<span class="ncs-value">{ncs}</span>' in html

        # Files table section exists
        assert html.count('class="files"') == 1
        assert html.count("Files scanned</td><td>1</td>") == 1
        assert "Total functions</td><td>2</td>" in html

        # Table headers for functions
        assert html.count(">Cognitive</th>") == 1
        assert html.count(">Cyclomatic</th>") == 1
        assert html.count(">LOC</th>") == 1
        assert html.count(">MI</th>") == 1
        assert html.count(">Risk</th>") == 1

        # Table headers for files
        assert html.count(">Total Cognitive</th>") >= 1
        assert html.count(">Code Lines</th>") == 1
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

        # Class Metrics section exists
        assert html.count('class="classes"') == 1
        assert html.count(">Class Metrics</h2>") == 1
        assert "MyService" in html

        # Class table headers
        assert html.count(">Methods</th>") == 1
        assert html.count(">WMC</th>") == 1
        assert html.count(">Total Cognitive</th>") >= 1
        assert html.count(">Avg Complexity</th>") == 1
    finally:
        os.unlink(path)


def test_html_report_no_classes_section_when_no_classes():
    """When there are no classes, the Class Metrics section should not appear."""
    path = _write_temp("""
        def standalone():
            return 42
    """)
    try:
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()
        html = generate_html_report(data, result.compute_ncs())

        assert "Class Metrics" not in html
        assert html.count('class="classes"') == 0
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

        # Breakdown section exists
        assert html.count('class="breakdown"') == 1
        assert "NCS Breakdown" in html
        assert html.count('class="breakdown-table"') == 1

        # All breakdown rows present
        assert html.count("Base complexity</td>") == 1
        assert html.count("Hotspot effect</td>") == 1
        assert html.count("Churn effect</td>") == 1
        assert html.count("Coupling effect</td>") == 1
        assert html.count("MI effect</td>") == 1
        assert html.count("Final NCS</td>") == 1

        # Final NCS row has the total class
        assert 'class="total"' in html
    finally:
        os.unlink(path)


def test_html_report_without_explanation():
    """When no explanation is provided, breakdown section should not appear."""
    path = _write_temp("def foo(): return 1\n")
    try:
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()
        html = generate_html_report(data, result.compute_ncs())

        assert html.count('class="breakdown"') == 0
        assert "NCS Breakdown" not in html
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

        assert html.count("<style>") == 1
        assert html.count("</style>") == 1
        assert html.count("<script>") == 1
        assert html.count("</script>") == 1

        # JS sort function present
        assert html.count("function sortTable") == 1

        # CSS variables present
        assert "--bg:" in html
        assert "--healthy:" in html
        assert "--critical:" in html

        # No external references in CSS
        css_block = html.split("<style>")[1].split("</style>")[0]
        assert "http://" not in css_block
        assert "https://" not in css_block
    finally:
        os.unlink(path)


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

        # sortable class on data tables
        assert html.count("sortable") >= 2  # at least functions table + files table
        # onclick handlers on th elements
        assert html.count("onclick=\"sortTable(this,") >= 1 or html.count("onclick=\"sortTable(this, ") >= 1
    finally:
        os.unlink(path)


def test_html_report_multiple_files():
    """Report with multiple scanned files shows all of them in the Files section."""
    path1 = _write_temp("""
        def alpha():
            return 1
    """)
    path2 = _write_temp("""
        def beta():
            if True:
                return 2
    """)
    try:
        fm1 = scan_file(path1)
        fm2 = scan_file(path2)
        result = ScanResult(files=[fm1, fm2])
        data = result.to_dict()
        ncs = result.compute_ncs()
        html = generate_html_report(data, ncs)

        # Summary reports 2 files scanned
        assert "Files scanned</td><td>2</td>" in html
        assert "Total functions</td><td>2</td>" in html

        # Both functions are listed
        assert "alpha" in html
        assert "beta" in html
    finally:
        os.unlink(path1)
        os.unlink(path2)


def test_html_report_ncs_rating_css_classes():
    """Different NCS values produce the correct CSS class on the badge."""
    scan_data = _minimal_scan_data()

    html_healthy = generate_html_report(scan_data, 1.0)
    assert 'class="ncs-badge healthy"' in html_healthy

    html_moderate = generate_html_report(scan_data, 5.0)
    assert 'class="ncs-badge moderate"' in html_moderate

    html_concerning = generate_html_report(scan_data, 8.0)
    assert 'class="ncs-badge concerning"' in html_concerning

    html_critical = generate_html_report(scan_data, 15.0)
    assert 'class="ncs-badge critical"' in html_critical


def test_html_report_churn_and_coupling_factors():
    """When summary has churn/coupling factors, they appear in the summary table."""
    scan_data = _minimal_scan_data()
    scan_data["summary"]["churn_factor"] = 1.25
    scan_data["summary"]["coupling_factor"] = 0.8

    html = generate_html_report(scan_data, 3.0)

    assert "Churn factor</td><td>1.25</td>" in html
    assert "Coupling factor</td><td>0.8</td>" in html


def test_html_report_no_churn_coupling_when_absent():
    """When summary lacks churn/coupling factors, those rows do not appear."""
    scan_data = _minimal_scan_data()
    html = generate_html_report(scan_data, 2.0)

    assert "Churn factor" not in html
    assert "Coupling factor" not in html


def test_html_report_html_escaping_in_function_names():
    """Function names with special characters are HTML-escaped."""
    scan_data = _minimal_scan_data(files=[{
        "path": "test.py",
        "function_count": 1,
        "total_cognitive": 15,
        "avg_cognitive": 15,
        "max_cognitive": 15,
        "code_lines": 10,
        "functions": [{
            "name": "<script>alert(1)</script>",
            "cognitive_complexity": 15,
            "cyclomatic_complexity": 5,
            "nloc": 10,
            "maintainability_index": 50,
            "line": 1,
            "risk_level": "high",
        }],
    }])
    scan_data["summary"]["total_functions"] = 1

    html = generate_html_report(scan_data, 5.0)

    # The raw script tag should NOT appear; the escaped version should
    assert "<script>alert(1)</script>" not in html.split("</style>")[1].split("<script>")[0]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_html_report_top_n_limits_functions():
    """top_n parameter limits how many functions appear in the hotspot table."""
    functions = []
    for i in range(10):
        functions.append({
            "name": f"func_{i}",
            "cognitive_complexity": 20 - i,
            "cyclomatic_complexity": 5,
            "nloc": 10,
            "maintainability_index": 50,
            "line": i * 10 + 1,
            "risk_level": "high",
        })

    scan_data = _minimal_scan_data(files=[{
        "path": "test.py",
        "function_count": 10,
        "total_cognitive": 155,
        "avg_cognitive": 15.5,
        "max_cognitive": 20,
        "code_lines": 100,
        "functions": functions,
    }])
    scan_data["summary"]["total_functions"] = 10

    html = generate_html_report(scan_data, 5.0, top_n=3)

    # The heading should show "Top 3"
    assert "Top 3 Most Complex Functions" in html

    # Only the top 3 most complex functions should appear in the hotspots table
    assert "func_0" in html  # complexity 20
    assert "func_1" in html  # complexity 19
    assert "func_2" in html  # complexity 18
    assert "func_3" not in html  # complexity 17 - should be cut off
