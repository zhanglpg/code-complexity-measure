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
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

import libcst as cst
from libcst import metadata

# Supported file extensions for scanning
SUPPORTED_EXTENSIONS = {'.py', '.go', '.java', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.mts', '.cts', '.c', '.cc', '.cpp', '.cxx', '.h', '.hpp', '.hxx', '.rs'}


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
class FileMetrics:
    path: str
    functions: List[FunctionMetrics] = field(default_factory=list)
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
    def net_complexity_score(self) -> float:
        """
        Legacy NCS using cognitive-only formula for backward compatibility.

        NCS = avg_cognitive * (1 + hotspot_ratio)
        """
        return self.compute_ncs()

    def compute_ncs(
        self,
        config=None,
        churn_factor: float = 1.0,
        coupling_factor: float = 1.0,
    ) -> float:
        """
        Compute Net Complexity Score with configurable weights and factors.

        NCS = (w_cog * avg_cognitive + w_cyc * avg_cyclomatic) * (1 + hotspot_ratio) * churn * coupling

        When called without arguments, produces the legacy cognitive-only result.
        """
        if self.total_functions == 0:
            return 0.0

        if config is not None:
            w_cog = config.weight_cognitive
            w_cyc = config.weight_cyclomatic
            threshold = config.hotspot_threshold
        else:
            # Legacy defaults: cognitive-only
            w_cog = 1.0
            w_cyc = 0.0
            threshold = 10

        avg_cog = self.total_cognitive / self.total_functions
        avg_cyc = self.total_cyclomatic / self.total_functions
        hotspots = sum(len(f.hotspots(threshold)) for f in self.files)
        hotspot_ratio = hotspots / self.total_functions

        base = w_cog * avg_cog + w_cyc * avg_cyc
        return round(base * (1 + hotspot_ratio) * churn_factor * coupling_factor, 2)
    
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
        self._in_boolean_op = False
    
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
    
    # -- flat increments (no nesting penalty) --
    
    def visit_IfExp(self, node: cst.IfExp) -> Optional[bool]:
        """Ternary expression: +1, no nesting."""
        self.complexity += 1
        return True
    
    # -- boolean operator sequences --
    
    def visit_BooleanOperation(self, node: cst.BooleanOperation) -> Optional[bool]:
        """
        Each sequence of same boolean operators counts as +1.
        Mixed operators (a and b or c) count as +1 for each switch.
        """
        if not self._in_boolean_op:
            self.complexity += 1
            self._in_boolean_op = True
        return True
    
    def leave_BooleanOperation(self, node: cst.BooleanOperation) -> None:
        self._in_boolean_op = False
    
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
        self._class_stack: List[str] = []
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
        return True
    
    def leave_ClassDef(self, node: cst.ClassDef) -> None:
        self._class_stack.pop()
    
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
        )
        self.functions.append(fm)
        
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
# Public API
# ---------------------------------------------------------------------------

def scan_file(file_path: str) -> FileMetrics:
    """Scan a single source file and return its metrics."""
    path = Path(file_path)

    if path.suffix == '.go':
        from .go_parser import scan_go_file
        return scan_go_file(file_path)

    if path.suffix == '.java':
        from .java_parser import scan_java_file
        return scan_java_file(file_path)

    if path.suffix in ('.js', '.mjs', '.cjs'):
        from .js_parser import scan_js_file
        return scan_js_file(file_path)

    if path.suffix in ('.ts', '.tsx', '.mts', '.cts'):
        from .ts_parser import scan_ts_file
        return scan_ts_file(file_path)

    if path.suffix in ('.c', '.cc', '.cpp', '.cxx', '.h', '.hpp', '.hxx'):
        from .cpp_parser import scan_cpp_file
        return scan_cpp_file(file_path)

    if path.suffix == '.rs':
        from .rust_parser import scan_rust_file
        return scan_rust_file(file_path)

    source = path.read_text(encoding="utf-8", errors="replace")
    
    total, code, comment, blank = count_lines(source)
    
    try:
        tree = cst.parse_module(source)
        wrapper = metadata.MetadataWrapper(tree)
        
        collector = FunctionCollector(str(path))
        collector.set_wrapper(wrapper)
        wrapper.visit(collector)
        
        functions = collector.functions
    except cst.ParserSyntaxError:
        # If file can't be parsed, return what we can
        functions = []
    
    return FileMetrics(
        path=str(path),
        functions=functions,
        total_lines=total,
        code_lines=code,
        comment_lines=comment,
        blank_lines=blank,
    )


def scan_directory(
    directory: str,
    exclude_patterns: Optional[List[str]] = None,
) -> ScanResult:
    """
    Recursively scan all Python files in a directory.
    
    Args:
        directory: Path to scan
        exclude_patterns: Glob patterns to exclude (e.g. ["**/test_*", "**/venv/**"])
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

    for source_file in sorted(root.rglob("*")):
        if source_file.suffix not in SUPPORTED_EXTENSIONS:
            continue
        # Check exclusions
        rel = str(source_file.relative_to(root))
        skip = any(
            fnmatch(rel, pat) or fnmatch(str(source_file), pat)
            for pat in exclude_patterns
        )
        if skip:
            continue

        try:
            fm = scan_file(str(source_file))
            result.files.append(fm)
        except Exception as e:
            # Skip files that can't be read
            print(f"Warning: skipping {source_file}: {e}", file=sys.stderr)
    
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Complexity Accounting Tool — measure Net Complexity Score"
    )
    parser.add_argument("path", help="File or directory to scan")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--threshold", type=int, default=10,
                       help="Cognitive complexity threshold for hotspots (default: 10)")
    parser.add_argument("--top", type=int, default=20,
                       help="Show top N complex functions (default: 20)")
    parser.add_argument("--fail-above", type=float, default=None,
                       help="Exit with code 1 if NCS exceeds this value")
    
    args = parser.parse_args()
    target = Path(args.path)
    
    if target.is_file():
        result = ScanResult(files=[scan_file(str(target))])
    elif target.is_dir():
        result = scan_directory(str(target))
    else:
        print(f"Error: {target} not found", file=sys.stderr)
        sys.exit(1)
    
    if args.json:
        print(result.to_json())
    else:
        # Human-readable summary
        print("=" * 60)
        print("  COMPLEXITY ACCOUNTING REPORT")
        print("=" * 60)
        print()
        
        s = result.to_dict()["summary"]
        ncs = s["net_complexity_score"]
        
        # NCS rating
        if ncs <= 3:
            rating = "🟢 Healthy"
        elif ncs <= 6:
            rating = "🟡 Moderate"
        elif ncs <= 10:
            rating = "🟠 Concerning"
        else:
            rating = "🔴 Critical"
        
        print(f"  Net Complexity Score:  {ncs}  {rating}")
        print(f"  Files scanned:        {s['files_scanned']}")
        print(f"  Total functions:      {s['total_functions']}")
        print(f"  Avg cognitive/func:   {s['avg_cognitive_per_function']}")
        print(f"  Hotspots (>={args.threshold}):     {s['hotspot_count']}")
        print()
        
        # Top complex functions
        all_funcs = []
        for fm in result.files:
            for fn in fm.functions:
                all_funcs.append(fn)
        
        all_funcs.sort(key=lambda f: f.cognitive_complexity, reverse=True)
        top = all_funcs[:args.top]
        
        if top:
            print(f"  Top {min(len(top), args.top)} most complex functions:")
            print(f"  {'─' * 56}")
            for fn in top:
                risk = {"low": "  ", "moderate": "⚠️", "high": "🔥", "very_high": "💀"}
                icon = risk.get(fn.risk_level, "  ")
                # Shorten path for display
                short_path = fn.file_path
                if len(short_path) > 30:
                    short_path = "..." + short_path[-27:]
                print(f"  {icon} {fn.cognitive_complexity:3d}  {fn.qualified_name:30s}  {short_path}:{fn.line}")
            print()
        
        print("=" * 60)
    
    # CI gate
    if args.fail_above is not None and result.net_complexity_score > args.fail_above:
        print(f"\n❌ FAILED: NCS {result.net_complexity_score} exceeds threshold {args.fail_above}")
        sys.exit(1)


if __name__ == "__main__":
    main()
