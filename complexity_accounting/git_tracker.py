"""
Git-aware complexity trend tracking.

Compares complexity across commits, branches, and PRs.
Generates delta reports suitable for CI/PR comments.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any

from .scanner import scan_directory, scan_file, ScanResult, FileMetrics, SUPPORTED_EXTENSIONS


@dataclass
class FileDelta:
    path: str
    before_cognitive: int
    after_cognitive: int
    before_cyclomatic: int
    after_cyclomatic: int
    before_functions: int
    after_functions: int
    status: str  # added, removed, modified, unchanged
    
    @property
    def cognitive_delta(self) -> int:
        return self.after_cognitive - self.before_cognitive
    
    @property
    def cyclomatic_delta(self) -> int:
        return self.after_cyclomatic - self.before_cyclomatic


@dataclass
class DeltaReport:
    base_ref: str
    head_ref: str
    base_ncs: float
    head_ncs: float
    file_deltas: List[FileDelta] = field(default_factory=list)
    
    @property
    def ncs_delta(self) -> float:
        return round(self.head_ncs - self.base_ncs, 2)
    
    @property
    def total_cognitive_delta(self) -> int:
        return sum(d.cognitive_delta for d in self.file_deltas)
    
    @property
    def improved_files(self) -> List[FileDelta]:
        return [d for d in self.file_deltas if d.cognitive_delta < 0]
    
    @property
    def worsened_files(self) -> List[FileDelta]:
        return [d for d in self.file_deltas if d.cognitive_delta > 0]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_ref": self.base_ref,
            "head_ref": self.head_ref,
            "base_ncs": self.base_ncs,
            "head_ncs": self.head_ncs,
            "ncs_delta": self.ncs_delta,
            "total_cognitive_delta": self.total_cognitive_delta,
            "improved_count": len(self.improved_files),
            "worsened_count": len(self.worsened_files),
            "files": [
                {
                    "path": d.path,
                    "status": d.status,
                    "cognitive_before": d.before_cognitive,
                    "cognitive_after": d.after_cognitive,
                    "cognitive_delta": d.cognitive_delta,
                }
                for d in self.file_deltas
                if d.cognitive_delta != 0 or d.status in ("added", "removed")
            ],
        }
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
    
    def to_markdown(self) -> str:
        """Generate a PR-comment-ready markdown summary."""
        lines = []
        
        # Header with verdict
        delta = self.ncs_delta
        if delta < 0:
            icon = "✅"
            verdict = "Complexity decreased"
        elif delta == 0:
            icon = "➖"
            verdict = "No complexity change"
        elif delta <= 1:
            icon = "⚠️"
            verdict = "Minor complexity increase"
        else:
            icon = "❌"
            verdict = "Significant complexity increase"
        
        lines.append(f"## {icon} Complexity Report")
        lines.append("")
        lines.append(f"**{verdict}** — NCS: {self.base_ncs} → {self.head_ncs} ({'+' if delta >= 0 else ''}{delta})")
        lines.append("")
        
        # Changed files table
        changed = [d for d in self.file_deltas if d.cognitive_delta != 0 or d.status in ("added", "removed")]
        if changed:
            lines.append("| File | Before | After | Delta |")
            lines.append("|------|--------|-------|-------|")
            for d in sorted(changed, key=lambda x: x.cognitive_delta, reverse=True):
                delta_str = f"+{d.cognitive_delta}" if d.cognitive_delta > 0 else str(d.cognitive_delta)
                icon = "⚠️" if d.cognitive_delta > 0 else "✅" if d.cognitive_delta < 0 else "➖"
                # Shorten path
                short = d.path
                if len(short) > 40:
                    short = "…" + short[-37:]
                lines.append(f"| `{short}` | {d.before_cognitive} | {d.after_cognitive} | {delta_str} {icon} |")
            lines.append("")
        
        lines.append(f"_Net change: {'+' if self.total_cognitive_delta >= 0 else ''}{self.total_cognitive_delta} cognitive complexity points_")
        
        return "\n".join(lines)


def _run_git(args: List[str], cwd: str) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def get_changed_files(base_ref: str, head_ref: str, repo_path: str) -> Dict[str, str]:
    """
    Get files changed between two refs.
    Returns dict of {path: status} where status is A/M/D.
    """
    output = _run_git(
        ["diff", "--name-status", base_ref, head_ref],
        cwd=repo_path,
    )
    changes = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) == 2:
            status, path = parts
            if any(path.endswith(ext) for ext in SUPPORTED_EXTENSIONS):
                changes[path] = status[0]  # A, M, D, R, etc.
    return changes


def scan_at_ref(ref: str, repo_path: str, files: Optional[List[str]] = None) -> Dict[str, FileMetrics]:
    """
    Scan files at a specific git ref.
    Checks out files to a temp directory for scanning.
    """
    metrics = {}
    
    if files is None:
        # Get all Python files at that ref
        output = _run_git(["ls-tree", "-r", "--name-only", ref], cwd=repo_path)
        files = [f for f in output.splitlines() if f.strip() and any(f.endswith(ext) for ext in SUPPORTED_EXTENSIONS)]
    
    if not files:
        return metrics
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for fpath in files:
            try:
                content = _run_git(["show", f"{ref}:{fpath}"], cwd=repo_path)
                tmp_file = Path(tmpdir) / fpath
                tmp_file.parent.mkdir(parents=True, exist_ok=True)
                tmp_file.write_text(content, encoding="utf-8")
                fm = scan_file(str(tmp_file))
                fm.path = fpath  # Use relative path
                for fn in fm.functions:
                    fn.file_path = fpath
                metrics[fpath] = fm
            except Exception:
                continue
    
    return metrics


def compare_refs(
    base_ref: str,
    head_ref: str,
    repo_path: str,
    changed_only: bool = True,
) -> DeltaReport:
    """
    Compare complexity between two git refs.
    
    Args:
        base_ref: Base reference (e.g., "main", "HEAD~5", commit SHA)
        head_ref: Head reference (e.g., "HEAD", branch name)
        repo_path: Path to the git repo
        changed_only: If True, only scan changed files (faster)
    """
    # Get changed files
    changes = get_changed_files(base_ref, head_ref, repo_path)
    
    if changed_only:
        files_to_scan = list(changes.keys())
    else:
        # Scan everything (slower but more accurate for NCS)
        output = _run_git(["ls-tree", "-r", "--name-only", head_ref], cwd=repo_path)
        files_to_scan = [f for f in output.splitlines() if f.strip() and f.endswith('.py')]
    
    # Scan at both refs
    base_files_to_scan = [f for f in files_to_scan if changes.get(f) != "A"]
    head_files_to_scan = [f for f in files_to_scan if changes.get(f) != "D"]
    
    base_metrics = scan_at_ref(base_ref, repo_path, base_files_to_scan)
    head_metrics = scan_at_ref(head_ref, repo_path, head_files_to_scan)
    
    # Build deltas
    all_paths = set(list(base_metrics.keys()) + list(head_metrics.keys()))
    file_deltas = []
    
    for path in sorted(all_paths):
        base_fm = base_metrics.get(path)
        head_fm = head_metrics.get(path)
        
        if base_fm and not head_fm:
            status = "removed"
        elif head_fm and not base_fm:
            status = "added"
        else:
            status = "modified"
        
        file_deltas.append(FileDelta(
            path=path,
            before_cognitive=base_fm.total_cognitive if base_fm else 0,
            after_cognitive=head_fm.total_cognitive if head_fm else 0,
            before_cyclomatic=base_fm.total_cyclomatic if base_fm else 0,
            after_cyclomatic=head_fm.total_cyclomatic if head_fm else 0,
            before_functions=base_fm.function_count if base_fm else 0,
            after_functions=head_fm.function_count if head_fm else 0,
            status=status,
        ))
    
    # Compute NCS for full scans
    base_scan = ScanResult(files=list(base_metrics.values()))
    head_scan = ScanResult(files=list(head_metrics.values()))
    
    return DeltaReport(
        base_ref=base_ref,
        head_ref=head_ref,
        base_ncs=base_scan.net_complexity_score,
        head_ncs=head_scan.net_complexity_score,
        file_deltas=file_deltas,
    )


def trend(repo_path: str, num_commits: int = 10, ref: str = "HEAD") -> List[Dict[str, Any]]:
    """
    Track complexity trend over the last N commits.
    Returns list of {commit, date, ncs, total_cognitive, total_functions}.
    """
    # Get commit list
    log_output = _run_git(
        ["log", f"-{num_commits}", "--format=%H %aI %s", ref],
        cwd=repo_path,
    )
    
    results = []
    for line in log_output.splitlines():
        if not line.strip():
            continue
        parts = line.split(" ", 2)
        sha = parts[0]
        date = parts[1] if len(parts) > 1 else ""
        msg = parts[2] if len(parts) > 2 else ""
        
        try:
            metrics = scan_at_ref(sha, repo_path)
            scan = ScanResult(files=list(metrics.values()))
            results.append({
                "commit": sha[:8],
                "date": date,
                "message": msg[:60],
                "ncs": scan.net_complexity_score,
                "total_cognitive": scan.total_cognitive,
                "total_functions": scan.total_functions,
                "files": len(scan.files),
            })
        except Exception as e:
            results.append({
                "commit": sha[:8],
                "date": date,
                "message": msg[:60],
                "error": str(e),
            })
    
    return results
