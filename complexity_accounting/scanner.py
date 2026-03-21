"""
Core complexity scanner using libcst.

Computes per-function and per-file metrics:
  - Cognitive Complexity (SonarSource-inspired)
  - Cyclomatic Complexity (McCabe)
  - Lines of code (logical, not blank/comment)
  - Parameter count
  - Nesting depth (max)

The cognitive complexity algorithm follows SonarSource's specification:
  1. Increment for breaks in linear flow (if, for, while, except, etc.)
  2. Increment for nesting (each level adds +1 penalty)
  3. Increment for breaks in control flow (break, continue, recursion)
  4. No increment for else/elif (unlike cyclomatic)
  BUT: nested conditionals get nesting penalty
"""

from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

import libcst as cst
from libcst import metadata

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
# Helpers
# ---------------------------------------------------------------------------

def walk_node(node, visitor):
    """Recursively walk a libcst CST node subtree with a visitor."""
    node_type = type(node).__name__
    visit_method = getattr(visitor, f'visit_{node_type}', None)
    should_descend = True
    if visit_method:
        result = visit_method(node)
        if result is False:
            should_descend = False
    
    if should_descend:
        for child in node.children:
            if isinstance(child, cst.CSTNode):
                walk_node(child, visitor)
    
    leave_method = getattr(visitor, f'leave_{node_type}', None)
    if leave_method:
        leave_method(node)


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


# ---------------------------------------------------------------------------
# Cognitive Complexity Visitor (libcst)
# ---------------------------------------------------------------------------

class CognitiveComplexityVisitor(cst.CSTVisitor):
    """
    Walks a function body and computes cognitive complexity.
    
    Rules (SonarSource-inspired):
    - +1 for each: if, elif, for, while, except, assert with bool op,
      ternary (IfExp), and/or sequences
    - +nesting for if/for/while/except when nested
    - +1 for break, continue
    - No increment for else (but else-if chains don't nest)
    """
    
    def __init__(self):
        self.complexity = 0
        self.nesting = 0
        self.max_nesting = 0
        self._bool_op_stack = []  # stack of boolean operator types
    
    # -- nesting increments --
    
    def visit_If(self, node: cst.If) -> Optional[bool]:
        self.complexity += 1 + self.nesting
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        return True
    
    def leave_If(self, node: cst.If) -> None:
        self.nesting -= 1
    
    def visit_For(self, node: cst.For) -> Optional[bool]:
        self.complexity += 1 + self.nesting
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        return True
    
    def leave_For(self, node: cst.For) -> None:
        self.nesting -= 1
    
    def visit_While(self, node: cst.While) -> Optional[bool]:
        self.complexity += 1 + self.nesting
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        return True
    
    def leave_While(self, node: cst.While) -> None:
        self.nesting -= 1
    
    def visit_ExceptHandler(self, node: cst.ExceptHandler) -> Optional[bool]:
        self.complexity += 1 + self.nesting
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        return True
    
    def leave_ExceptHandler(self, node: cst.ExceptHandler) -> None:
        self.nesting -= 1
    
    def visit_With(self, node: cst.With) -> Optional[bool]:
        # 'with' doesn't increment complexity but does nest
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        return True
    
    def leave_With(self, node: cst.With) -> None:
        self.nesting -= 1
    
    # -- match/case (Python 3.10+) --

    def visit_Match(self, node: cst.Match) -> Optional[bool]:
        self.complexity += 1 + self.nesting
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        return True

    def leave_Match(self, node: cst.Match) -> None:
        self.nesting -= 1

    # -- flat increments (no nesting penalty) --

    def visit_IfExp(self, node: cst.IfExp) -> Optional[bool]:
        """Ternary expression: +1, no nesting."""
        self.complexity += 1
        return True
    
    # -- boolean operator sequences --
    
    def visit_BooleanOperation(self, node: cst.BooleanOperation) -> Optional[bool]:
        """
        SonarSource-style boolean operator scoring:
        - Same-operator chain (a and b and c): +1 total
        - Each operator change adds +1 (a and b or c): +2
        """
        op_type = type(node.operator)
        parent_op = self._bool_op_stack[-1] if self._bool_op_stack else None
        if op_type != parent_op:
            self.complexity += 1
        self._bool_op_stack.append(op_type)
        return True

    def leave_BooleanOperation(self, node: cst.BooleanOperation) -> None:
        self._bool_op_stack.pop()
    
    # -- flow breaks --
    
    def visit_Break(self, node: cst.Break) -> Optional[bool]:
        self.complexity += 1
        return False
    
    def visit_Continue(self, node: cst.Continue) -> Optional[bool]:
        self.complexity += 1
        return False
    
    # -- nested functions/lambdas increase nesting --
    
    def visit_FunctionDef(self, node: cst.FunctionDef) -> Optional[bool]:
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        return True
    
    def leave_FunctionDef(self, node: cst.FunctionDef) -> None:
        self.nesting -= 1
    
    def visit_Lambda(self, node: cst.Lambda) -> Optional[bool]:
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        return True
    
    def leave_Lambda(self, node: cst.Lambda) -> None:
        self.nesting -= 1


# ---------------------------------------------------------------------------
# Cyclomatic Complexity Visitor
# ---------------------------------------------------------------------------

class CyclomaticComplexityVisitor(cst.CSTVisitor):
    """McCabe cyclomatic complexity: +1 for each decision point."""
    
    def __init__(self):
        self.complexity = 1  # baseline
    
    def visit_If(self, node: cst.If) -> Optional[bool]:
        self.complexity += 1
        return True
    
    def visit_For(self, node: cst.For) -> Optional[bool]:
        self.complexity += 1
        return True
    
    def visit_While(self, node: cst.While) -> Optional[bool]:
        self.complexity += 1
        return True
    
    def visit_ExceptHandler(self, node: cst.ExceptHandler) -> Optional[bool]:
        self.complexity += 1
        return True
    
    def visit_BooleanOperation(self, node: cst.BooleanOperation) -> Optional[bool]:
        self.complexity += 1
        return True
    
    def visit_IfExp(self, node: cst.IfExp) -> Optional[bool]:
        self.complexity += 1
        return True
    
    def visit_Assert(self, node: cst.Assert) -> Optional[bool]:
        self.complexity += 1
        return True

    def visit_MatchCase(self, node: cst.MatchCase) -> Optional[bool]:
        self.complexity += 1
        return True


# ---------------------------------------------------------------------------
# File-level collector
# ---------------------------------------------------------------------------

class FunctionCollector(cst.CSTVisitor):
    """
    Visits a module and collects metrics for each function/method.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.functions: List[FunctionMetrics] = []
        self.classes: List[ClassMetrics] = []
        self._class_stack: List[str] = []
        self._class_methods_stack: List[List[FunctionMetrics]] = []
        self._class_nodes_stack: List[cst.ClassDef] = []
        self._wrapper = None  # holds the wrapper for position info
    
    def set_wrapper(self, wrapper):
        self._wrapper = wrapper
    
    def _get_line(self, node) -> int:
        """Get line number from node position."""
        try:
            pos = self._wrapper.resolve(metadata.PositionProvider)[node]
            return pos.start.line
        except Exception:
            return 0
    
    def _get_end_line(self, node) -> int:
        try:
            pos = self._wrapper.resolve(metadata.PositionProvider)[node]
            return pos.end.line
        except Exception:
            return 0
    
    def _count_params(self, params: cst.Parameters) -> int:
        count = len(params.params)
        if params.star_arg and isinstance(params.star_arg, cst.Param):
            count += 1
        if params.star_kwarg:
            count += 1
        count += len(params.kwonly_params)
        # Exclude 'self' and 'cls'
        if params.params:
            first = params.params[0]
            if isinstance(first.name, cst.Name) and first.name.value in ("self", "cls"):
                count -= 1
        return count
    
    def visit_ClassDef(self, node: cst.ClassDef) -> Optional[bool]:
        self._class_stack.append(node.name.value)
        self._class_methods_stack.append([])
        self._class_nodes_stack.append(node)
        return True

    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        class_name = self._class_stack.pop()
        methods = self._class_methods_stack.pop()
        self._class_nodes_stack.pop()
        line = self._get_line(node)
        end_line = self._get_end_line(node)
        self.classes.append(ClassMetrics(
            name=class_name,
            file_path=self.file_path,
            line=line,
            end_line=end_line,
            methods=methods,
        ))
    
    def visit_FunctionDef(self, node: cst.FunctionDef) -> Optional[bool]:
        name = node.name.value
        if self._class_stack:
            qualified = f"{'.'.join(self._class_stack)}.{name}"
        else:
            qualified = name
        
        # Compute cognitive complexity on the function body
        cog_visitor = CognitiveComplexityVisitor()
        walk_node(node.body, cog_visitor)
        
        # Compute cyclomatic complexity
        cyc_visitor = CyclomaticComplexityVisitor()
        walk_node(node.body, cyc_visitor)
        
        # Line counts
        line = self._get_line(node)
        end_line = self._get_end_line(node)
        nloc = max(end_line - line + 1, 0)
        
        # Compute Halstead metrics for improved MI
        halstead_vol = None
        try:
            from .halstead import compute_halstead_python
            module = self._wrapper.module
            func_source = module.code_for_node(node)
            h = compute_halstead_python(func_source)
            halstead_vol = h.volume if h.volume > 0 else None
        except Exception:
            pass

        fm = FunctionMetrics(
            name=name,
            qualified_name=qualified,
            file_path=self.file_path,
            line=line,
            end_line=end_line,
            cognitive_complexity=cog_visitor.complexity,
            cyclomatic_complexity=cyc_visitor.complexity,
            nloc=nloc,
            params=self._count_params(node.params),
            max_nesting=cog_visitor.max_nesting,
            maintainability_index=compute_mi(nloc, cyc_visitor.complexity, halstead_vol),
            halstead_volume=halstead_vol,
        )
        self.functions.append(fm)

        # Track methods within class context
        if self._class_methods_stack:
            self._class_methods_stack[-1].append(fm)

        # Don't descend into nested functions for top-level collection
        # (they're handled by the cognitive visitor internally)
        return False


# ---------------------------------------------------------------------------
# Line counting
# ---------------------------------------------------------------------------

def count_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts."""
    total = 0
    code = 0
    comment = 0
    blank = 0
    in_docstring = False
    docstring_char = None
    
    for raw_line in source.splitlines():
        total += 1
        line = raw_line.strip()
        
        if not line:
            blank += 1
            continue
        
        if in_docstring:
            comment += 1
            if docstring_char in line and line.endswith(docstring_char):
                in_docstring = False
            continue
        
        if line.startswith('"""') or line.startswith("'''"):
            dc = line[:3]
            # Check if it's a single-line docstring
            if line.count(dc) >= 2:
                comment += 1
            else:
                in_docstring = True
                docstring_char = dc
                comment += 1
            continue
        
        if line.startswith('#'):
            comment += 1
            continue
        
        code += 1
    
    return total, code, comment, blank


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

# Module-level cache instance, set by scan_directory or externally
_active_cache = None


def set_cache(cache):
    """Set the active cache instance for scan operations."""
    global _active_cache
    _active_cache = cache


def get_cache():
    """Get the active cache instance."""
    return _active_cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_file(file_path: str) -> FileMetrics:
    """Scan a single source file and return its metrics."""
    # Check cache first
    if _active_cache is not None:
        cached = _active_cache.get(file_path)
        if cached is not None:
            return cached

    result = _scan_file_uncached(file_path)

    # Store in cache
    if _active_cache is not None:
        _active_cache.put(file_path, result)

    return result


# Dispatch table: language name -> (module, function_name) for lazy imports
_SCANNER_DISPATCH = {
    "go": (".go_parser", "scan_go_file"),
    "java": (".java_parser", "scan_java_file"),
    "javascript": (".js_parser", "scan_js_file"),
    "typescript": (".ts_parser", "scan_ts_file"),
    "cpp": (".cpp_parser", "scan_cpp_file"),
    "rust": (".rust_parser", "scan_rust_file"),
}


def _scan_file_uncached(file_path: str) -> FileMetrics:
    """Scan a single source file without cache lookup."""
    path = Path(file_path)
    language = EXTENSION_LANGUAGE_MAP.get(path.suffix.lower())

    # Dispatch to language-specific parser
    if language and language != "python":
        entry = _SCANNER_DISPATCH.get(language)
        if entry:
            import importlib
            mod = importlib.import_module(entry[0], package="complexity_accounting")
            return getattr(mod, entry[1])(file_path)

    # Check for plugin support for unknown extensions
    if language is None and path.suffix not in SUPPORTED_EXTENSIONS:
        try:
            from .plugin import get_plugin_for_extension
            plugin = get_plugin_for_extension(path.suffix)
            if plugin is not None:
                return plugin.scan_file(file_path)
        except Exception:
            pass

    source = path.read_text(encoding="utf-8", errors="replace")
    
    total, code, comment, blank = count_lines(source)
    
    try:
        tree = cst.parse_module(source)
        wrapper = metadata.MetadataWrapper(tree)

        collector = FunctionCollector(str(path))
        collector.set_wrapper(wrapper)
        wrapper.visit(collector)

        functions = collector.functions
        classes = collector.classes
    except cst.ParserSyntaxError:
        # If file can't be parsed, return what we can
        functions = []
        classes = []

    return FileMetrics(
        path=str(path),
        functions=functions,
        classes=classes,
        total_lines=total,
        code_lines=code,
        comment_lines=comment,
        blank_lines=blank,
    )


def scan_directory(
    directory: str,
    exclude_patterns: Optional[List[str]] = None,
    include_tests: bool = False,
    workers: Optional[int] = None,
) -> ScanResult:
    """
    Recursively scan all supported source files in a directory.

    Args:
        directory: Path to scan
        exclude_patterns: Glob patterns to exclude (e.g. ["**/test_*", "**/venv/**"])
        include_tests: If False (default), test files are excluded from scanning
        workers: Number of parallel workers. None = auto, 1 = sequential.
    """
    if exclude_patterns is None:
        exclude_patterns = [
            "**/venv/**", "**/.venv/**", "**/node_modules/**",
            "**/__pycache__/**", "**/build/**", "**/dist/**",
            "**/.git/**", "**/migrations/**",
        ]

    root = Path(directory)
    result = ScanResult()

    from fnmatch import fnmatch

    files_to_scan = []
    for source_file in sorted(root.rglob("*")):
        if source_file.suffix not in SUPPORTED_EXTENSIONS:
            continue
        rel = str(source_file.relative_to(root))
        skip = any(
            fnmatch(rel, pat) or fnmatch(str(source_file), pat)
            for pat in exclude_patterns
        )
        if skip:
            continue
        if not include_tests and any(fnmatch(rel, pat) for pat in TEST_FILE_PATTERNS):
            continue
        files_to_scan.append(str(source_file))

    if workers == 1 or len(files_to_scan) <= 4:
        # Sequential scanning
        for fp in files_to_scan:
            try:
                result.files.append(scan_file(fp))
            except Exception as e:
                print(f"Warning: skipping {fp}: {e}", file=sys.stderr)
    else:
        from concurrent.futures import ProcessPoolExecutor, as_completed
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(scan_file, fp): fp for fp in files_to_scan}
            for future in as_completed(futures):
                try:
                    result.files.append(future.result())
                except Exception as e:
                    print(f"Warning: skipping {futures[future]}: {e}", file=sys.stderr)
        # Sort by path for deterministic output
        result.files.sort(key=lambda fm: fm.path)

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """Legacy entry point for 'complexity-scan' command. Delegates to the full CLI."""
    sys.argv = [sys.argv[0], "scan"] + sys.argv[1:]
    from .__main__ import main as cli_main
    cli_main()


if __name__ == "__main__":
    main()
