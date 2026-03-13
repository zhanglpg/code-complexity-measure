"""Tests validating complexity-accounting against alibaba/OpenSandbox.

These tests use pre-computed results from scanning the OpenSandbox server
Python codebase (https://github.com/alibaba/OpenSandbox) to verify that
the scanner produces sensible, stable output on a real-world project.
"""

import json
from pathlib import Path

import pytest

RESULTS_FILE = Path(__file__).parent / "opensandbox_results.json"


@pytest.fixture(scope="module")
def opensandbox_results():
    """Load the pre-computed scan results."""
    with open(RESULTS_FILE) as f:
        return json.load(f)


class TestOpenSandboxResults:
    """Validate complexity-accounting output against OpenSandbox codebase."""

    def test_results_file_exists(self):
        assert RESULTS_FILE.exists(), "opensandbox_results.json must exist"

    def test_summary_keys_present(self, opensandbox_results):
        """Summary contains all expected metric keys."""
        expected_keys = {
            "files_scanned",
            "total_functions",
            "total_cognitive_complexity",
            "total_cyclomatic_complexity",
            "net_complexity_score",
            "avg_cognitive_per_function",
            "hotspot_count",
            "churn_factor",
            "coupling_factor",
        }
        assert expected_keys.issubset(opensandbox_results["summary"].keys())

    def test_files_scanned(self, opensandbox_results):
        """Should scan a reasonable number of Python files."""
        summary = opensandbox_results["summary"]
        assert summary["files_scanned"] >= 30

    def test_total_functions_detected(self, opensandbox_results):
        """Should detect hundreds of functions in a real codebase."""
        summary = opensandbox_results["summary"]
        assert summary["total_functions"] >= 200

    def test_ncs_in_valid_range(self, opensandbox_results):
        """NCS should be a positive finite number."""
        ncs = opensandbox_results["summary"]["net_complexity_score"]
        assert 0 < ncs < 100

    def test_ncs_rating_moderate(self, opensandbox_results):
        """OpenSandbox NCS should be in the Moderate range (<=6)."""
        ncs = opensandbox_results["summary"]["net_complexity_score"]
        assert ncs <= 6, f"NCS {ncs} exceeds Moderate threshold"

    def test_hotspots_detected(self, opensandbox_results):
        """Real codebases should have some complexity hotspots."""
        assert opensandbox_results["summary"]["hotspot_count"] > 0

    def test_avg_cognitive_reasonable(self, opensandbox_results):
        """Average cognitive complexity per function should be low."""
        avg = opensandbox_results["summary"]["avg_cognitive_per_function"]
        assert 0 < avg < 10

    def test_coupling_factor_above_one(self, opensandbox_results):
        """A multi-module project should have coupling > 1."""
        cf = opensandbox_results["summary"]["coupling_factor"]
        assert cf >= 1.0

    def test_file_entries_have_functions(self, opensandbox_results):
        """Each scanned file entry should have a functions list."""
        for file_entry in opensandbox_results["files"]:
            assert "functions" in file_entry
            assert "path" in file_entry

    def test_docker_service_is_most_complex(self, opensandbox_results):
        """docker.py should be the most complex file by total cognitive."""
        files = opensandbox_results["files"]
        by_complexity = sorted(
            files,
            key=lambda f: sum(
                fn["cognitive_complexity"] for fn in f.get("functions", [])
            ),
            reverse=True,
        )
        most_complex = by_complexity[0]["path"]
        assert "docker.py" in most_complex

    def test_top_hotspot_function(self, opensandbox_results):
        """The highest-complexity function should be _container_to_sandbox."""
        all_funcs = []
        for file_entry in opensandbox_results["files"]:
            for fn in file_entry.get("functions", []):
                all_funcs.append(fn)
        top = max(all_funcs, key=lambda f: f["cognitive_complexity"])
        assert top["name"] == "_container_to_sandbox"
        assert top["cognitive_complexity"] >= 30

    def test_cognitive_vs_cyclomatic_correlation(self, opensandbox_results):
        """Cognitive and cyclomatic totals should both be substantial."""
        summary = opensandbox_results["summary"]
        assert summary["total_cognitive_complexity"] > 100
        assert summary["total_cyclomatic_complexity"] > 100

    def test_no_negative_complexities(self, opensandbox_results):
        """No function should have negative complexity values."""
        for file_entry in opensandbox_results["files"]:
            for fn in file_entry.get("functions", []):
                assert fn["cognitive_complexity"] >= 0
                assert fn["cyclomatic_complexity"] >= 0

    def test_function_metrics_have_required_fields(self, opensandbox_results):
        """Each function should have name, cognitive, and cyclomatic metrics."""
        required = {"name", "cognitive_complexity", "cyclomatic_complexity"}
        for file_entry in opensandbox_results["files"]:
            for fn in file_entry.get("functions", []):
                assert required.issubset(fn.keys()), (
                    f"Function missing fields: {required - fn.keys()}"
                )
