"""
HTML report generator for complexity accounting results.

Produces a self-contained HTML file with embedded CSS and minimal JavaScript.
No external dependencies required.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _ncs_rating(ncs: float) -> tuple:
    """Return (label, css_class) for an NCS value."""
    if ncs <= 3:
        return "Healthy", "healthy"
    elif ncs <= 6:
        return "Moderate", "moderate"
    elif ncs <= 10:
        return "Concerning", "concerning"
    else:
        return "Critical", "critical"


def _risk_class(risk: str) -> str:
    return {"low": "risk-low", "moderate": "risk-moderate",
            "high": "risk-high", "very_high": "risk-critical"}.get(risk, "")


def generate_html_report(
    scan_data: Dict[str, Any],
    ncs: float,
    config: Any = None,
    explanation: Optional[Dict[str, Any]] = None,
    top_n: int = 20,
) -> str:
    """Generate a self-contained HTML complexity report.

    Args:
        scan_data: Output of ScanResult.to_dict()
        ncs: Computed Net Complexity Score
        config: Config object (optional, for thresholds)
        explanation: NCS breakdown dict (optional)
        top_n: Number of top functions to show
    """
    summary = scan_data["summary"]
    files = scan_data["files"]
    rating_label, rating_class = _ncs_rating(ncs)

    # Collect all functions and sort by complexity
    all_funcs = []
    for f in files:
        for fn in f.get("functions", []):
            fn["_file_path"] = f["path"]
            all_funcs.append(fn)
    all_funcs.sort(key=lambda f: f.get("cognitive_complexity", 0), reverse=True)
    top_funcs = all_funcs[:top_n]

    # Collect all classes
    all_classes = []
    for f in files:
        for cls in f.get("classes", []):
            cls["_file_path"] = f["path"]
            all_classes.append(cls)
    all_classes.sort(key=lambda c: c.get("total_cognitive", 0), reverse=True)

    # Build HTML
    html_parts = [_HTML_HEAD]

    # Summary section
    html_parts.append(f"""
    <div class="summary">
        <h2>Summary</h2>
        <div class="ncs-badge {rating_class}">
            <span class="ncs-value">{ncs}</span>
            <span class="ncs-label">{rating_label}</span>
        </div>
        <table class="summary-table">
            <tr><td>Files scanned</td><td>{summary['files_scanned']}</td></tr>
            <tr><td>Total functions</td><td>{summary['total_functions']}</td></tr>
            <tr><td>Avg cognitive/function</td><td>{summary['avg_cognitive_per_function']}</td></tr>
            <tr><td>Hotspot count</td><td>{summary['hotspot_count']}</td></tr>
            <tr><td>Avg Maintainability Index</td><td>{summary.get('avg_maintainability_index', 'N/A')}</td></tr>
    """)
    if "churn_factor" in summary:
        html_parts.append(f"<tr><td>Churn factor</td><td>{summary['churn_factor']}</td></tr>")
    if "coupling_factor" in summary:
        html_parts.append(f"<tr><td>Coupling factor</td><td>{summary['coupling_factor']}</td></tr>")
    html_parts.append("</table></div>")

    # NCS Breakdown
    if explanation:
        html_parts.append(f"""
        <div class="breakdown">
            <h2>NCS Breakdown ({explanation.get('model', 'multiplicative')})</h2>
            <table class="breakdown-table">
                <tr><td>Base complexity</td><td>{explanation['base_complexity']:.2f}</td></tr>
                <tr><td>Hotspot effect</td><td>{explanation['hotspot_contribution']:+.2f} (ratio={explanation['hotspot_ratio']:.2f})</td></tr>
                <tr><td>Churn effect</td><td>{explanation['churn_contribution']:+.2f} (factor={explanation['churn_factor']:.3f})</td></tr>
                <tr><td>Coupling effect</td><td>{explanation['coupling_contribution']:+.2f} (factor={explanation['coupling_factor']:.3f})</td></tr>
                <tr><td>MI effect</td><td>{explanation['mi_contribution']:+.2f} (avg_mi={explanation['avg_maintainability_index']:.1f})</td></tr>
                <tr class="total"><td>Final NCS</td><td>{explanation['ncs']:.2f}</td></tr>
            </table>
        </div>
        """)

    # Top complex functions
    if top_funcs:
        html_parts.append(f"""
        <div class="hotspots">
            <h2>Top {min(len(top_funcs), top_n)} Most Complex Functions</h2>
            <table class="data-table sortable">
                <thead>
                    <tr>
                        <th onclick="sortTable(this, 0)">Function</th>
                        <th onclick="sortTable(this, 1)" class="num">Cognitive</th>
                        <th onclick="sortTable(this, 2)" class="num">Cyclomatic</th>
                        <th onclick="sortTable(this, 3)" class="num">LOC</th>
                        <th onclick="sortTable(this, 4)" class="num">MI</th>
                        <th onclick="sortTable(this, 5)">Risk</th>
                        <th onclick="sortTable(this, 6)">File</th>
                    </tr>
                </thead>
                <tbody>
        """)
        for fn in top_funcs:
            risk = fn.get("risk_level", _get_risk(fn.get("cognitive_complexity", 0)))
            html_parts.append(f"""
                <tr>
                    <td>{_esc(fn.get('qualified_name', fn.get('name', '')))}</td>
                    <td class="num">{fn.get('cognitive_complexity', 0)}</td>
                    <td class="num">{fn.get('cyclomatic_complexity', 1)}</td>
                    <td class="num">{fn.get('nloc', 0)}</td>
                    <td class="num">{fn.get('maintainability_index', 100)}</td>
                    <td class="{_risk_class(risk)}">{risk}</td>
                    <td class="filepath">{_esc(_short_path(fn.get('_file_path', '')))}:{fn.get('line', 0)}</td>
                </tr>
            """)
        html_parts.append("</tbody></table></div>")

    # Class metrics
    if all_classes:
        html_parts.append(f"""
        <div class="classes">
            <h2>Class Metrics</h2>
            <table class="data-table sortable">
                <thead>
                    <tr>
                        <th onclick="sortTable(this, 0)">Class</th>
                        <th onclick="sortTable(this, 1)" class="num">Methods</th>
                        <th onclick="sortTable(this, 2)" class="num">WMC</th>
                        <th onclick="sortTable(this, 3)" class="num">Total Cognitive</th>
                        <th onclick="sortTable(this, 4)" class="num">Avg Complexity</th>
                        <th onclick="sortTable(this, 5)">File</th>
                    </tr>
                </thead>
                <tbody>
        """)
        for cls in all_classes:
            html_parts.append(f"""
                <tr>
                    <td>{_esc(cls.get('name', ''))}</td>
                    <td class="num">{cls.get('method_count', 0)}</td>
                    <td class="num">{cls.get('wmc', 0)}</td>
                    <td class="num">{cls.get('total_cognitive', 0)}</td>
                    <td class="num">{cls.get('avg_method_complexity', 0)}</td>
                    <td class="filepath">{_esc(_short_path(cls.get('_file_path', '')))}:{cls.get('line', 0)}</td>
                </tr>
            """)
        html_parts.append("</tbody></table></div>")

    # File summary
    html_parts.append("""
        <div class="files">
            <h2>Files</h2>
            <table class="data-table sortable">
                <thead>
                    <tr>
                        <th onclick="sortTable(this, 0)">File</th>
                        <th onclick="sortTable(this, 1)" class="num">Functions</th>
                        <th onclick="sortTable(this, 2)" class="num">Total Cognitive</th>
                        <th onclick="sortTable(this, 3)" class="num">Avg Cognitive</th>
                        <th onclick="sortTable(this, 4)" class="num">Max Cognitive</th>
                        <th onclick="sortTable(this, 5)" class="num">Code Lines</th>
                    </tr>
                </thead>
                <tbody>
    """)
    for f in sorted(files, key=lambda x: x.get("total_cognitive", 0), reverse=True):
        html_parts.append(f"""
            <tr>
                <td class="filepath">{_esc(_short_path(f['path']))}</td>
                <td class="num">{f.get('function_count', 0)}</td>
                <td class="num">{f.get('total_cognitive', 0)}</td>
                <td class="num">{f.get('avg_cognitive', 0)}</td>
                <td class="num">{f.get('max_cognitive', 0)}</td>
                <td class="num">{f.get('code_lines', 0)}</td>
            </tr>
        """)
    html_parts.append("</tbody></table></div>")

    html_parts.append(_HTML_FOOT)
    return "".join(html_parts)


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _short_path(path: str) -> str:
    if len(path) > 50:
        return "..." + path[-47:]
    return path


def _get_risk(cognitive: int) -> str:
    if cognitive <= 5:
        return "low"
    elif cognitive <= 10:
        return "moderate"
    elif cognitive <= 20:
        return "high"
    return "very_high"


# ---------------------------------------------------------------------------
# HTML template parts
# ---------------------------------------------------------------------------

_HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Complexity Accounting Report</title>
<style>
:root {
    --bg: #1a1a2e;
    --surface: #16213e;
    --text: #e0e0e0;
    --text-muted: #a0a0a0;
    --border: #2a2a4a;
    --healthy: #4caf50;
    --moderate: #ff9800;
    --concerning: #ff5722;
    --critical: #f44336;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 2rem;
    max-width: 1200px;
    margin: 0 auto;
}
h1 { margin-bottom: 1.5rem; font-size: 1.5rem; }
h2 { margin-bottom: 1rem; font-size: 1.2rem; color: var(--text-muted); }
.summary, .breakdown, .hotspots, .classes, .files {
    background: var(--surface);
    border-radius: 8px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    border: 1px solid var(--border);
}
.ncs-badge {
    display: inline-flex;
    flex-direction: column;
    align-items: center;
    padding: 1rem 2rem;
    border-radius: 8px;
    margin-bottom: 1rem;
}
.ncs-badge.healthy { background: rgba(76, 175, 80, 0.15); border: 2px solid var(--healthy); }
.ncs-badge.moderate { background: rgba(255, 152, 0, 0.15); border: 2px solid var(--moderate); }
.ncs-badge.concerning { background: rgba(255, 87, 34, 0.15); border: 2px solid var(--concerning); }
.ncs-badge.critical { background: rgba(244, 67, 54, 0.15); border: 2px solid var(--critical); }
.ncs-value { font-size: 2rem; font-weight: bold; }
.ncs-label { font-size: 0.9rem; color: var(--text-muted); }
.summary-table, .breakdown-table { width: auto; border-collapse: collapse; }
.summary-table td, .breakdown-table td {
    padding: 0.3rem 1rem 0.3rem 0;
    border: none;
}
.summary-table td:first-child, .breakdown-table td:first-child {
    color: var(--text-muted);
}
.breakdown-table .total td { font-weight: bold; border-top: 1px solid var(--border); }
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td {
    padding: 0.5rem 0.75rem;
    text-align: left;
    border-bottom: 1px solid var(--border);
}
.data-table th {
    cursor: pointer;
    user-select: none;
    color: var(--text-muted);
    font-weight: 600;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.data-table th:hover { color: var(--text); }
.data-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.data-table .filepath { font-family: monospace; font-size: 0.85rem; color: var(--text-muted); }
.risk-low { color: var(--healthy); }
.risk-moderate { color: var(--moderate); }
.risk-high { color: var(--concerning); }
.risk-critical { color: var(--critical); }
</style>
</head>
<body>
<h1>Complexity Accounting Report</h1>
"""

_HTML_FOOT = """
<script>
function sortTable(th, colIdx) {
    const table = th.closest('table');
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const isNum = th.classList.contains('num');
    const asc = th.dataset.sort !== 'asc';
    th.dataset.sort = asc ? 'asc' : 'desc';
    // Reset other headers
    table.querySelectorAll('th').forEach(h => { if (h !== th) delete h.dataset.sort; });
    rows.sort((a, b) => {
        let va = a.cells[colIdx].textContent.trim();
        let vb = b.cells[colIdx].textContent.trim();
        if (isNum) { va = parseFloat(va) || 0; vb = parseFloat(vb) || 0; }
        if (va < vb) return asc ? -1 : 1;
        if (va > vb) return asc ? 1 : -1;
        return 0;
    });
    rows.forEach(r => tbody.appendChild(r));
}
</script>
</body>
</html>
"""
