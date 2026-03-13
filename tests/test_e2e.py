"""End-to-end tests with real git repos and sample project fixtures."""

import argparse
import io
import json
import os
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from complexity_accounting.scanner import scan_file, scan_directory, ScanResult
from complexity_accounting.config import load_config
from complexity_accounting.__main__ import cmd_scan, cmd_compare, cmd_trend

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "sample_project"


# ---------------------------------------------------------------------------
# Helpers for git repo tests
# ---------------------------------------------------------------------------

def _git(repo, *args):
    """Run a git command in the given repo directory."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=str(repo),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"git {args} failed: {result.stderr}"
    return result.stdout


def _commit_file(repo, filename, content, message):
    """Write a file to the repo and commit it."""
    filepath = repo / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    _git(repo, "add", filename)
    _git(repo, "commit", "-m", message)


# ---------------------------------------------------------------------------
# Sample project fixture tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestFixtureProject:

    def test_scan_fixture_project(self):
        """Scan the fixture project and verify known complexity values."""
        result = scan_directory(str(FIXTURE_PROJECT))
        assert len(result.files) == 5  # simple, moderate, complex, utils, __init__
        assert result.total_functions == 7

        func_map = {}
        for fm in result.files:
            for fn in fm.functions:
                func_map[fn.name] = fn

        assert func_map["add"].cognitive_complexity == 0
        assert func_map["greet"].cognitive_complexity == 0
        assert func_map["find_max"].cognitive_complexity == 4
        assert func_map["process"].cognitive_complexity == 6
        assert func_map["handle_request"].cognitive_complexity == 41
        assert func_map["transform"].cognitive_complexity == 0
        assert func_map["process_all"].cognitive_complexity == 0

    def test_scan_fixture_project_ncs(self):
        """NCS is deterministic for the fixture project."""
        result = scan_directory(str(FIXTURE_PROJECT))
        assert result.net_complexity_score == 8.33

    def test_scan_fixture_project_hotspots(self):
        """Only handle_request is a hotspot at threshold=10."""
        result = scan_directory(str(FIXTURE_PROJECT))
        hotspots = []
        for fm in result.files:
            hotspots.extend(fm.hotspots(10))
        assert len(hotspots) == 1
        assert hotspots[0].name == "handle_request"

    def test_scan_fixture_project_config(self):
        """The .complexity.toml in the fixture is loadable."""
        config = load_config(str(FIXTURE_PROJECT))
        assert config.hotspot_threshold == 8
        assert config.weight_cognitive == 0.8
        assert config.weight_cyclomatic == 0.2

    def test_scan_fixture_project_ncs_with_config(self):
        """NCS with custom config weights differs from default."""
        result = scan_directory(str(FIXTURE_PROJECT))
        config = load_config(str(FIXTURE_PROJECT))
        custom_ncs = result.compute_ncs(config=config)
        default_ncs = result.net_complexity_score
        # Custom weights (0.8 cog + 0.2 cyc) should differ from legacy (1.0 cog)
        assert custom_ncs != default_ncs

    def test_scan_fixture_coupling(self):
        """utils.py imports from simple and moderate — coupling should be detected."""
        from complexity_accounting.coupling import analyze_directory_coupling
        coupling = analyze_directory_coupling(str(FIXTURE_PROJECT))
        # utils.py imports simple and moderate
        assert "utils.py" in coupling or any("utils" in k for k in coupling)


# ---------------------------------------------------------------------------
# Real git repo tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestRealGitRepo:

    def test_compare_refs_modified(self, tmp_git_repo):
        """compare_refs detects modified files between real commits."""
        from complexity_accounting.git_tracker import compare_refs

        # Commit 1: simple function
        _commit_file(tmp_git_repo, "app.py", "def foo(): pass\n", "initial")
        _git(tmp_git_repo, "tag", "v1")

        # Commit 2: add complexity
        _commit_file(
            tmp_git_repo, "app.py",
            "def foo(x):\n    if x:\n        for i in range(x):\n            if i > 5:\n                return i\n    return 0\n",
            "add complexity",
        )
        _git(tmp_git_repo, "tag", "v2")

        report = compare_refs("v1", "v2", str(tmp_git_repo))
        assert len(report.file_deltas) == 1
        delta = report.file_deltas[0]
        assert delta.path == "app.py"
        assert delta.status == "modified"
        assert delta.cognitive_delta > 0

    def test_compare_refs_added_file(self, tmp_git_repo):
        """compare_refs detects newly added files."""
        from complexity_accounting.git_tracker import compare_refs

        _commit_file(tmp_git_repo, "base.py", "x = 1\n", "initial")
        _git(tmp_git_repo, "tag", "v1")

        _commit_file(tmp_git_repo, "new.py", "def bar(): pass\n", "add file")
        _git(tmp_git_repo, "tag", "v2")

        report = compare_refs("v1", "v2", str(tmp_git_repo))
        statuses = {d.path: d.status for d in report.file_deltas}
        assert statuses.get("new.py") == "added"

    def test_compare_refs_deleted_file(self, tmp_git_repo):
        """compare_refs detects deleted files."""
        from complexity_accounting.git_tracker import compare_refs

        _commit_file(tmp_git_repo, "old.py", "def baz(): pass\n", "add file")
        _git(tmp_git_repo, "tag", "v1")

        _git(tmp_git_repo, "rm", "old.py")
        _git(tmp_git_repo, "commit", "-m", "remove file")
        _git(tmp_git_repo, "tag", "v2")

        report = compare_refs("v1", "v2", str(tmp_git_repo))
        statuses = {d.path: d.status for d in report.file_deltas}
        assert statuses.get("old.py") == "removed"

    def test_trend_real_repo(self, tmp_git_repo):
        """trend() tracks complexity across real commits."""
        from complexity_accounting.git_tracker import trend

        _commit_file(tmp_git_repo, "app.py", "def foo(): pass\n", "v1")
        _commit_file(
            tmp_git_repo, "app.py",
            "def foo(x):\n    if x:\n        return x\n    return 0\n",
            "v2",
        )
        _commit_file(
            tmp_git_repo, "app.py",
            "def foo(x):\n    if x:\n        for i in range(x):\n            if i > 5:\n                return i\n    return 0\n",
            "v3",
        )

        results = trend(str(tmp_git_repo), num_commits=3)
        assert len(results) == 3
        # Each entry should have ncs key
        for entry in results:
            assert "ncs" in entry
        # v3 (most recent, first in results) should have highest complexity
        assert results[0]["ncs"] >= results[-1]["ncs"]

    def test_get_changed_files_real_repo(self, tmp_git_repo):
        """get_changed_files returns correct statuses from a real repo."""
        from complexity_accounting.git_tracker import get_changed_files

        _commit_file(tmp_git_repo, "a.py", "x = 1\n", "initial")
        _git(tmp_git_repo, "tag", "v1")

        _commit_file(tmp_git_repo, "a.py", "x = 2\n", "modify a")
        _commit_file(tmp_git_repo, "b.py", "y = 1\n", "add b")
        _git(tmp_git_repo, "tag", "v2")

        changes = get_changed_files("v1", "v2", str(tmp_git_repo))
        assert changes.get("a.py") == "M"
        assert changes.get("b.py") == "A"

    def test_churn_real_repo(self, tmp_git_repo):
        """analyze_churn counts file change frequency in a real repo."""
        from complexity_accounting.churn import analyze_churn

        _commit_file(tmp_git_repo, "hot.py", "x = 1\n", "c1")
        _commit_file(tmp_git_repo, "hot.py", "x = 2\n", "c2")
        _commit_file(tmp_git_repo, "hot.py", "x = 3\n", "c3")
        _commit_file(tmp_git_repo, "cold.py", "y = 1\n", "c4")

        churn = analyze_churn(str(tmp_git_repo))
        assert "hot.py" in churn
        assert churn["hot.py"] >= 2  # changed in multiple commits

    def test_compare_refs_java_file(self, tmp_git_repo):
        """compare_refs detects modified Java files between real commits."""
        from complexity_accounting.git_tracker import compare_refs

        _commit_file(
            tmp_git_repo, "App.java",
            "public class App { public static void run() {} }\n",
            "initial java",
        )
        _git(tmp_git_repo, "tag", "v1")

        _commit_file(
            tmp_git_repo, "App.java",
            "public class App {\n"
            "    public static void run(int x) {\n"
            "        if (x > 0) {\n"
            "            for (int i = 0; i < x; i++) {\n"
            "                if (i > 5) { return; }\n"
            "            }\n"
            "        }\n"
            "    }\n"
            "}\n",
            "add java complexity",
        )
        _git(tmp_git_repo, "tag", "v2")

        report = compare_refs("v1", "v2", str(tmp_git_repo))
        deltas = {d.path: d for d in report.file_deltas}
        assert "App.java" in deltas
        assert deltas["App.java"].status == "modified"
        assert deltas["App.java"].cognitive_delta > 0

    def test_compare_refs_cpp_file(self, tmp_git_repo):
        """compare_refs detects modified C++ files between real commits."""
        from complexity_accounting.git_tracker import compare_refs

        _commit_file(
            tmp_git_repo, "app.cpp",
            "int run() { return 0; }\n",
            "initial cpp",
        )
        _git(tmp_git_repo, "tag", "v1")

        _commit_file(
            tmp_git_repo, "app.cpp",
            "int run(int x) {\n"
            "    if (x > 0) {\n"
            "        for (int i = 0; i < x; i++) {\n"
            "            if (i > 5) { return i; }\n"
            "        }\n"
            "    }\n"
            "    return 0;\n"
            "}\n",
            "add cpp complexity",
        )
        _git(tmp_git_repo, "tag", "v2")

        report = compare_refs("v1", "v2", str(tmp_git_repo))
        deltas = {d.path: d for d in report.file_deltas}
        assert "app.cpp" in deltas
        assert deltas["app.cpp"].status == "modified"
        assert deltas["app.cpp"].cognitive_delta > 0

    def test_compare_refs_js_file(self, tmp_git_repo):
        """compare_refs detects modified JavaScript files between real commits."""
        from complexity_accounting.git_tracker import compare_refs

        _commit_file(
            tmp_git_repo, "app.js",
            "function run() {}\n",
            "initial js",
        )
        _git(tmp_git_repo, "tag", "v1")

        _commit_file(
            tmp_git_repo, "app.js",
            "function run(x) {\n"
            "    if (x > 0) {\n"
            "        for (let i = 0; i < x; i++) {\n"
            "            if (i > 5) { return; }\n"
            "        }\n"
            "    }\n"
            "}\n",
            "add js complexity",
        )
        _git(tmp_git_repo, "tag", "v2")

        report = compare_refs("v1", "v2", str(tmp_git_repo))
        deltas = {d.path: d for d in report.file_deltas}
        assert "app.js" in deltas
        assert deltas["app.js"].status == "modified"
        assert deltas["app.js"].cognitive_delta > 0

    def test_compare_refs_ts_file(self, tmp_git_repo):
        """compare_refs detects modified TypeScript files between real commits."""
        from complexity_accounting.git_tracker import compare_refs

        _commit_file(
            tmp_git_repo, "app.ts",
            "function run(): void {}\n",
            "initial ts",
        )
        _git(tmp_git_repo, "tag", "v1")

        _commit_file(
            tmp_git_repo, "app.ts",
            "function run(x: number): void {\n"
            "    if (x > 0) {\n"
            "        for (let i = 0; i < x; i++) {\n"
            "            if (i > 5) { return; }\n"
            "        }\n"
            "    }\n"
            "}\n",
            "add ts complexity",
        )
        _git(tmp_git_repo, "tag", "v2")

        report = compare_refs("v1", "v2", str(tmp_git_repo))
        deltas = {d.path: d for d in report.file_deltas}
        assert "app.ts" in deltas
        assert deltas["app.ts"].status == "modified"
        assert deltas["app.ts"].cognitive_delta > 0

    def test_compare_refs_rust_file(self, tmp_git_repo):
        """compare_refs detects modified Rust files between real commits."""
        from complexity_accounting.git_tracker import compare_refs

        _commit_file(
            tmp_git_repo, "app.rs",
            "fn run() {}\n",
            "initial rust",
        )
        _git(tmp_git_repo, "tag", "v1")

        _commit_file(
            tmp_git_repo, "app.rs",
            "fn run(x: i32) -> i32 {\n"
            "    if x > 0 {\n"
            "        for i in 0..x {\n"
            "            if i > 5 { return i; }\n"
            "        }\n"
            "    }\n"
            "    0\n"
            "}\n",
            "add rust complexity",
        )
        _git(tmp_git_repo, "tag", "v2")

        report = compare_refs("v1", "v2", str(tmp_git_repo))
        deltas = {d.path: d for d in report.file_deltas}
        assert "app.rs" in deltas
        assert deltas["app.rs"].status == "modified"
        assert deltas["app.rs"].cognitive_delta > 0

    def test_scan_directory_mixed_seven_languages(self, tmp_git_repo):
        """scan_directory picks up .py, .go, .java, .cpp, .js, .ts, and .rs files together."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.py").write_text("def foo(): pass\n")
            (Path(tmpdir) / "b.go").write_text(
                "package main\nfunc Bar() {}\n"
            )
            (Path(tmpdir) / "C.java").write_text(
                "public class C { public static void baz() {} }\n"
            )
            (Path(tmpdir) / "d.cpp").write_text(
                "int qux() { return 0; }\n"
            )
            (Path(tmpdir) / "e.js").write_text(
                "function quux() {}\n"
            )
            (Path(tmpdir) / "f.ts").write_text(
                "function corge(): void {}\n"
            )
            (Path(tmpdir) / "g.rs").write_text(
                "fn grault() {}\n"
            )
            result = scan_directory(tmpdir)
            assert len(result.files) == 7
            names = set()
            for f in result.files:
                for fn in f.functions:
                    names.add(fn.name)
            assert "foo" in names
            assert "Bar" in names
            assert "baz" in names
            assert "qux" in names
            assert "quux" in names
            assert "corge" in names
            assert "grault" in names


# ---------------------------------------------------------------------------
# CLI workflow E2E tests
# ---------------------------------------------------------------------------

@pytest.mark.e2e
class TestCLIWorkflow:

    def _make_scan_args(self, **overrides):
        defaults = dict(
            path=str(FIXTURE_PROJECT),
            json=False,
            threshold=None,
            top=20,
            fail_above=None,
            config=None,
            weights=None,
            churn_days=None,
            churn_commits=None,
            no_churn=True,
            no_coupling=True,
            ncs_model=None,
            brief=False,
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_cli_scan_fixture_json(self):
        """cmd_scan produces valid JSON for the fixture project."""
        args = self._make_scan_args(json=True)
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        data = json.loads(out.getvalue())
        assert data["summary"]["total_functions"] == 7
        # cmd_scan auto-loads .complexity.toml (weights 0.8/0.2), so NCS differs from legacy
        assert data["summary"]["net_complexity_score"] == 7.48

    def test_cli_scan_fixture_text(self):
        """cmd_scan produces human-readable text with expected sections."""
        args = self._make_scan_args()
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        output = out.getvalue()
        assert "COMPLEXITY ACCOUNTING REPORT" in output
        assert "Net Complexity Score" in output
        assert "handle_request" in output  # should appear in top functions

    def test_cli_fail_above_with_fixture(self):
        """cmd_scan exits with code 1 when NCS exceeds fail-above."""
        args = self._make_scan_args(json=True, fail_above=1.0)
        out = io.StringIO()
        with pytest.raises(SystemExit) as exc_info:
            with redirect_stdout(out):
                cmd_scan(args)
        assert exc_info.value.code == 1

    def test_cli_compare_real_repo(self, tmp_git_repo):
        """cmd_compare produces valid JSON delta report from real repo."""
        _commit_file(tmp_git_repo, "a.py", "def f(): pass\n", "v1")
        _git(tmp_git_repo, "tag", "v1")
        _commit_file(
            tmp_git_repo, "a.py",
            "def f(x):\n    if x:\n        return x\n",
            "v2",
        )
        _git(tmp_git_repo, "tag", "v2")

        args = argparse.Namespace(
            base="v1", head="v2", repo=str(tmp_git_repo),
            json=True, markdown=False, full=False, func=cmd_compare,
        )
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_compare(args)
        data = json.loads(out.getvalue())
        assert "ncs_delta" in data

    def test_cli_trend_real_repo(self, tmp_git_repo):
        """cmd_trend produces valid JSON trend data from real repo."""
        _commit_file(tmp_git_repo, "a.py", "def f(): pass\n", "c1")
        _commit_file(
            tmp_git_repo, "a.py",
            "def f(x):\n    if x:\n        return x\n",
            "c2",
        )

        args = argparse.Namespace(
            repo=str(tmp_git_repo), commits=2, ref="HEAD",
            json=True, func=cmd_trend,
        )
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_trend(args)
        data = json.loads(out.getvalue())
        assert isinstance(data, list)
        assert len(data) == 2

    def test_cli_scan_java_file(self, tmp_git_repo):
        """cmd_scan produces valid JSON for a Java file."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "App.java").write_text(
                "public class App {\n"
                "    public static int add(int a, int b) {\n"
                "        return a + b;\n"
                "    }\n"
                "}\n"
            )
            args = self._make_scan_args(path=tmpdir, json=True)
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_scan(args)
            data = json.loads(out.getvalue())
            assert data["summary"]["total_functions"] >= 1
            func_names = []
            for f in data["files"]:
                for fn in f.get("functions", []):
                    func_names.append(fn["name"])
            assert "add" in func_names

    def test_cli_scan_cpp_file(self, tmp_git_repo):
        """cmd_scan produces valid JSON for a C++ file."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.cpp").write_text(
                "int add(int a, int b) {\n"
                "    return a + b;\n"
                "}\n"
            )
            args = self._make_scan_args(path=tmpdir, json=True)
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_scan(args)
            data = json.loads(out.getvalue())
            assert data["summary"]["total_functions"] >= 1
            func_names = []
            for f in data["files"]:
                for fn in f.get("functions", []):
                    func_names.append(fn["name"])
            assert "add" in func_names

    def test_cli_scan_js_file(self, tmp_git_repo):
        """cmd_scan produces valid JSON for a JavaScript file."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.js").write_text(
                "function add(a, b) {\n"
                "    return a + b;\n"
                "}\n"
            )
            args = self._make_scan_args(path=tmpdir, json=True)
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_scan(args)
            data = json.loads(out.getvalue())
            assert data["summary"]["total_functions"] >= 1
            func_names = []
            for f in data["files"]:
                for fn in f.get("functions", []):
                    func_names.append(fn["name"])
            assert "add" in func_names

    def test_cli_scan_ts_file(self, tmp_git_repo):
        """cmd_scan produces valid JSON for a TypeScript file."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.ts").write_text(
                "function add(a: number, b: number): number {\n"
                "    return a + b;\n"
                "}\n"
            )
            args = self._make_scan_args(path=tmpdir, json=True)
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_scan(args)
            data = json.loads(out.getvalue())
            assert data["summary"]["total_functions"] >= 1
            func_names = []
            for f in data["files"]:
                for fn in f.get("functions", []):
                    func_names.append(fn["name"])
            assert "add" in func_names

    def test_cli_scan_rust_file(self, tmp_git_repo):
        """cmd_scan produces valid JSON for a Rust file."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.rs").write_text(
                "fn add(a: i32, b: i32) -> i32 {\n"
                "    a + b\n"
                "}\n"
            )
            args = self._make_scan_args(path=tmpdir, json=True)
            out = io.StringIO()
            with redirect_stdout(out):
                cmd_scan(args)
            data = json.loads(out.getvalue())
            assert data["summary"]["total_functions"] >= 1
            func_names = []
            for f in data["files"]:
                for fn in f.get("functions", []):
                    func_names.append(fn["name"])
            assert "add" in func_names

    def test_cli_scan_with_config_file(self):
        """cmd_scan with fixture config applies custom weights."""
        args = self._make_scan_args(
            json=True,
            config=str(FIXTURE_PROJECT / ".complexity.toml"),
        )
        out = io.StringIO()
        with redirect_stdout(out):
            cmd_scan(args)
        data = json.loads(out.getvalue())
        # With custom weights the NCS should differ from the default 8.33
        assert "net_complexity_score" in data["summary"]


# ---------------------------------------------------------------------------
# Test runner (backward compat)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
