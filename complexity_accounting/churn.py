"""
Git churn analysis.

Counts how many times each file has been modified in a recent window.
"""

from __future__ import annotations

import math
import subprocess
from collections import Counter
from typing import Dict, Optional


def analyze_churn(
    repo_path: str,
    days: int = 90,
    max_commits: int = 100,
) -> Dict[str, int]:
    """
    Count file modification frequency from git history.

    Returns {relative_file_path: modification_count}.
    Returns empty dict if not a git repository or git is unavailable.
    """
    try:
        args = [
            "git", "log",
            f"--since={days} days ago",
            f"-n{max_commits}",
            "--numstat",
            "--format=",
        ]
        result = subprocess.run(
            args,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {}

    counts: Counter[str] = Counter()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            file_path = parts[2]
            counts[file_path] += 1

    return dict(counts)


def compute_churn_factor(churn_data: Dict[str, int]) -> float:
    """
    Compute a churn multiplier for NCS.

    Returns 1.0 (neutral) when no data is available.
    Formula: 1 + log1p(avg_churn) / 10  (dampened logarithmic scaling)
    """
    if not churn_data:
        return 1.0
    values = list(churn_data.values())
    avg = sum(values) / len(values)
    return round(1.0 + math.log1p(avg) / 10, 4)
