"""
Data models for complexity metrics.

Contains FunctionMetrics, ClassMetrics, FileMetrics, ScanResult, and
the Maintainability Index computation. These are pure data containers
with no parsing or scanning logic.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any


# Supported file extensions for scanning
SUPPORTED_EXTENSIONS = {'.py', '.go', '.java', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.mts', '.cts', '.c', '.cc', '.cpp', '.cxx', '.h', '.hpp', '.hxx', '.rs'}

# Patterns for test files — excluded by default from complexity scoring.
# Each pattern is listed with and without **/ prefix so fnmatch works
# for both root-level and nested files.
TEST_FILE_PATTERNS = [
    "test_*", "**/test_*",
    "*_test.py", "**/*_test.py",
    "*_test.go", "**/*_test.go",
    "*_test.rs", "**/*_test.rs",
    "*_test.c", "**/*_test.c",
    "*_test.cc", "**/*_test.cc",
    "*_test.cpp", "**/*_test.cpp",
    "*Test.java", "**/*Test.java",
    "*Tests.java", "**/*Tests.java",
    "*.test.js", "**/*.test.js",
    "*.spec.js", "**/*.spec.js",
    "*.test.mjs", "**/*.test.mjs",
    "*.spec.mjs", "**/*.spec.mjs",
    "*.test.ts", "**/*.test.ts",
    "*.spec.ts", "**/*.spec.ts",
    "*.test.tsx", "**/*.test.tsx",
    "*.spec.tsx", "**/*.spec.tsx",
    "*.test.mts", "**/*.test.mts",
    "*.spec.mts", "**/*.spec.mts",
    "tests/**", "**/tests/**",
    "__tests__/**", "**/__tests__/**",
]

# Map file extensions to canonical language names (for language-specific config)
EXTENSION_LANGUAGE_MAP = {
    '.py': 'python',
    '.go': 'go',
    '.java': 'java',
    '.js': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
    '.ts': 'typescript', '.tsx': 'typescript', '.mts': 'typescript', '.cts': 'typescript',
    '.c': 'cpp', '.cc': 'cpp', '.cpp': 'cpp', '.cxx': 'cpp',
    '.h': 'cpp', '.hpp': 'cpp', '.hxx': 'cpp',
    '.rs': 'rust',
}


def get_language(file_path: str) -> Optional[str]:
    """Return the canonical language name for a file path, or None if unknown."""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_LANGUAGE_MAP.get(ext)


# ---------------------------------------------------------------------------
# Maintainability Index
# ---------------------------------------------------------------------------

def compute_mi(nloc: int, cyclomatic: int, halstead_volume: Optional[float] = None) -> float:
    """
    Compute Maintainability Index.

    When halstead_volume is provided, uses the full SEI formula:
      MI = max(0, min(100, (171 - 5.2*ln(HV) - 0.23*CC - 16.2*ln(LOC)) * 100/171))

    Otherwise falls back to the simplified Visual Studio formula:
      MI = max(0, min(100, (171 - 21.4*ln(LOC) - 0.23*CC) * 100/171))

    Scale: 0-100, higher is more maintainable.
    """
    if nloc <= 0:
        return 100.0
    if halstead_volume is not None and halstead_volume > 0:
        raw = 171.0 - 5.2 * math.log(halstead_volume) - 0.23 * cyclomatic - 16.2 * math.log(nloc)
    else:
        raw = 171.0 - 21.4 * math.log(nloc) - 0.23 * cyclomatic
    return round(max(0.0, min(100.0, raw * 100.0 / 171.0)), 2)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FunctionMetrics:
    name: str
    qualified_name: str  # e.g. ClassName.method_name
    file_path: str
    line: int
    end_line: int
    cognitive_complexity: int = 0
    cyclomatic_complexity: int = 1  # baseline 1 for the function itself
    nloc: int = 0  # non-blank, non-comment lines
    params: int = 0
    max_nesting: int = 0
    maintainability_index: float = 100.0
    halstead_volume: Optional[float] = None

    @property
    def risk_level(self) -> str:
        return self.get_risk_level()

    def get_risk_level(self, low: int = 5, moderate: int = 10, high: int = 20) -> str:
        """Return risk level with configurable boundaries."""
        cc = self.cognitive_complexity
        if cc <= low:
            return "low"
        elif cc <= moderate:
            return "moderate"
        elif cc <= high:
            return "high"
        else:
            return "very_high"


@dataclass
class ClassMetrics:
    """Per-class metrics: WMC (Weighted Methods per Class), method count, total complexity."""
    name: str
    file_path: str
    line: int
    end_line: int
    methods: List[FunctionMetrics] = field(default_factory=list)

    @property
    def method_count(self) -> int:
        return len(self.methods)

    @property
    def total_cognitive(self) -> int:
        return sum(m.cognitive_complexity for m in self.methods)

    @property
    def total_cyclomatic(self) -> int:
        return sum(m.cyclomatic_complexity for m in self.methods)

    @property
    def wmc(self) -> int:
        """Weighted Methods per Class = sum of cyclomatic complexities."""
        return self.total_cyclomatic

    @property
    def avg_method_complexity(self) -> float:
        if not self.methods:
            return 0.0
        return self.total_cognitive / len(self.methods)


@dataclass
class FileMetrics:
    path: str
    functions: List[FunctionMetrics] = field(default_factory=list)
    classes: List[ClassMetrics] = field(default_factory=list)
    total_lines: int = 0
    code_lines: int = 0
    comment_lines: int = 0
    blank_lines: int = 0

    @property
    def total_cognitive(self) -> int:
        return sum(f.cognitive_complexity for f in self.functions)

    @property
    def total_cyclomatic(self) -> int:
        return sum(f.cyclomatic_complexity for f in self.functions)

    @property
    def avg_cognitive(self) -> float:
        if not self.functions:
            return 0.0
        return self.total_cognitive / len(self.functions)

    @property
    def max_cognitive(self) -> int:
        if not self.functions:
            return 0
        return max(f.cognitive_complexity for f in self.functions)

    @property
    def function_count(self) -> int:
        return len(self.functions)

    def hotspots(self, threshold: int = 10) -> List[FunctionMetrics]:
        """Functions with cognitive complexity above threshold."""
        return [f for f in self.functions if f.cognitive_complexity >= threshold]


@dataclass
class ScanResult:
    files: List[FileMetrics] = field(default_factory=list)

    @property
    def total_cognitive(self) -> int:
        return sum(f.total_cognitive for f in self.files)

    @property
    def total_cyclomatic(self) -> int:
        return sum(f.total_cyclomatic for f in self.files)

    @property
    def total_functions(self) -> int:
        return sum(f.function_count for f in self.files)

    @property
    def avg_maintainability_index(self) -> float:
        if self.total_functions == 0:
            return 100.0
        total_mi = sum(
            fn.maintainability_index
            for f in self.files
            for fn in f.functions
        )
        return round(total_mi / self.total_functions, 2)

    @property
    def net_complexity_score(self) -> float:
        """
        Legacy NCS using cognitive-only formula for backward compatibility.

        NCS = avg_cognitive * (1 + hotspot_ratio)
        """
        return self.compute_ncs()

    def _compute_internals(self, config=None, churn_factor: float = 1.0, coupling_factor: float = 1.0):
        """Shared computation of intermediate NCS values."""
        if config is not None:
            w_cog = config.weight_cognitive
            w_cyc = config.weight_cyclomatic
            model = config.ncs_model
        else:
            w_cog = 1.0
            w_cyc = 0.0
            model = "multiplicative"

        avg_cog = self.total_cognitive / self.total_functions
        avg_cyc = self.total_cyclomatic / self.total_functions
        avg_mi = self.avg_maintainability_index

        # Language-aware hotspot counting
        hotspots = 0
        for f in self.files:
            lang = get_language(f.path)
            t = config.get_hotspot_threshold(lang) if config else 10
            hotspots += len(f.hotspots(t))
        hotspot_ratio = hotspots / self.total_functions

        # MI factor: penalizes when avg MI drops below 50 (scale 1.0–2.0)
        mi_factor = 1.0 + max(0.0, (50.0 - avg_mi) / 50.0)

        base = w_cog * avg_cog + w_cyc * avg_cyc
        return model, w_cog, w_cyc, avg_cog, avg_cyc, hotspot_ratio, base, churn_factor, coupling_factor, mi_factor, avg_mi

    def compute_ncs(
        self,
        config=None,
        churn_factor: float = 1.0,
        coupling_factor: float = 1.0,
    ) -> float:
        """
        Compute Net Complexity Score with configurable weights and factors.

        Multiplicative (default):
          NCS = (w_cog * avg_cognitive + w_cyc * avg_cyclomatic) * (1 + hotspot_ratio) * churn * coupling

        Additive:
          NCS = w_cog * avg_cog + w_cyc * avg_cyc + w_hotspot * penalty + w_churn * penalty + w_coupling * penalty

        When called without arguments, produces the legacy cognitive-only result.
        """
        if self.total_functions == 0:
            return 0.0

        model, w_cog, w_cyc, avg_cog, avg_cyc, hotspot_ratio, base, cf, cpf, mif, avg_mi = (
            self._compute_internals(config, churn_factor, coupling_factor)
        )

        if model == "additive" and config is not None:
            hotspot_penalty = hotspot_ratio * 10
            churn_penalty = (cf - 1.0) * 10
            coupling_penalty = (cpf - 1.0) * 10
            mi_penalty = (100.0 - avg_mi) / 10.0
            return round(
                base
                + config.weight_hotspot * hotspot_penalty
                + config.weight_churn * churn_penalty
                + config.weight_coupling * coupling_penalty
                + config.weight_mi * mi_penalty,
                2,
            )

        return round(base * (1 + hotspot_ratio) * cf * cpf * mif, 2)

    def compute_ncs_explained(
        self,
        config=None,
        churn_factor: float = 1.0,
        coupling_factor: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Compute NCS with a full breakdown of each factor's contribution.

        Returns a dict with intermediate values and the dominant factor.
        """
        if self.total_functions == 0:
            return {
                "ncs": 0.0,
                "model": "multiplicative",
                "base_complexity": 0.0,
                "avg_cognitive": 0.0,
                "avg_cyclomatic": 0.0,
                "hotspot_ratio": 0.0,
                "churn_factor": churn_factor,
                "coupling_factor": coupling_factor,
                "mi_factor": 1.0,
                "avg_maintainability_index": 100.0,
                "hotspot_contribution": 0.0,
                "churn_contribution": 0.0,
                "coupling_contribution": 0.0,
                "mi_contribution": 0.0,
                "dominant_factor": "none",
            }

        model, w_cog, w_cyc, avg_cog, avg_cyc, hotspot_ratio, base, cf, cpf, mif, avg_mi = (
            self._compute_internals(config, churn_factor, coupling_factor)
        )

        if model == "additive" and config is not None:
            hotspot_contrib = config.weight_hotspot * (hotspot_ratio * 10)
            churn_contrib = config.weight_churn * ((cf - 1.0) * 10)
            coupling_contrib = config.weight_coupling * ((cpf - 1.0) * 10)
            mi_contrib = config.weight_mi * ((100.0 - avg_mi) / 10.0)
            ncs = round(base + hotspot_contrib + churn_contrib + coupling_contrib + mi_contrib, 2)
        else:
            after_hotspot = base * (1 + hotspot_ratio)
            after_churn = after_hotspot * cf
            after_coupling = after_churn * cpf
            ncs = round(after_coupling * mif, 2)
            hotspot_contrib = after_hotspot - base
            churn_contrib = after_churn - after_hotspot
            coupling_contrib = after_coupling - after_churn
            mi_contrib = (after_coupling * mif) - after_coupling

        contribs = {
            "hotspot": hotspot_contrib,
            "churn": churn_contrib,
            "coupling": coupling_contrib,
            "mi": mi_contrib,
        }
        dominant = max(contribs, key=lambda k: abs(contribs[k]))
        if all(v == 0 for v in contribs.values()):
            dominant = "none"

        return {
            "ncs": ncs,
            "model": model,
            "base_complexity": round(base, 4),
            "avg_cognitive": round(avg_cog, 4),
            "avg_cyclomatic": round(avg_cyc, 4),
            "hotspot_ratio": round(hotspot_ratio, 4),
            "churn_factor": round(cf, 4),
            "coupling_factor": round(cpf, 4),
            "mi_factor": round(mif, 4),
            "avg_maintainability_index": round(avg_mi, 2),
            "hotspot_contribution": round(hotspot_contrib, 4),
            "churn_contribution": round(churn_contrib, 4),
            "coupling_contribution": round(coupling_contrib, 4),
            "mi_contribution": round(mi_contrib, 4),
            "dominant_factor": dominant,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "summary": {
                "files_scanned": len(self.files),
                "total_functions": self.total_functions,
                "total_cognitive_complexity": self.total_cognitive,
                "total_cyclomatic_complexity": self.total_cyclomatic,
                "net_complexity_score": self.net_complexity_score,
                "avg_cognitive_per_function": round(
                    self.total_cognitive / max(self.total_functions, 1), 2
                ),
                "hotspot_count": sum(len(f.hotspots()) for f in self.files),
                "avg_maintainability_index": self.avg_maintainability_index,
            },
            "files": [
                {
                    "path": fm.path,
                    "total_lines": fm.total_lines,
                    "code_lines": fm.code_lines,
                    "comment_lines": fm.comment_lines,
                    "function_count": fm.function_count,
                    "total_cognitive": fm.total_cognitive,
                    "total_cyclomatic": fm.total_cyclomatic,
                    "avg_cognitive": round(fm.avg_cognitive, 2),
                    "max_cognitive": fm.max_cognitive,
                    "functions": [asdict(fn) for fn in fm.functions],
                    "classes": [
                        {
                            "name": cls.name,
                            "file_path": cls.file_path,
                            "line": cls.line,
                            "end_line": cls.end_line,
                            "method_count": cls.method_count,
                            "wmc": cls.wmc,
                            "total_cognitive": cls.total_cognitive,
                            "total_cyclomatic": cls.total_cyclomatic,
                            "avg_method_complexity": round(cls.avg_method_complexity, 2),
                        }
                        for cls in fm.classes
                    ],
                }
                for fm in self.files
            ],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
