"""
Core complexity scanner.

Provides the public API for scanning files and directories:
  - scan_file(path) -> FileMetrics
  - scan_directory(path) -> ScanResult

Python files are parsed using libcst; other languages are dispatched
to their respective tree-sitter-based parsers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

import libcst as cst
from libcst import metadata

# Re-export data models for backward compatibility
from .models import (
    FunctionMetrics, ClassMetrics, FileMetrics, ScanResult,
    compute_mi, get_language,
    SUPPORTED_EXTENSIONS, TEST_FILE_PATTERNS, EXTENSION_LANGUAGE_MAP,
)


# ---------------------------------------------------------------------------
# Python CST helpers
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
        self._bool_op_stack = []

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
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        return True

    def leave_With(self, node: cst.With) -> None:
        self.nesting -= 1

    def visit_Match(self, node: cst.Match) -> Optional[bool]:
        self.complexity += 1 + self.nesting
        self.nesting += 1
        self.max_nesting = max(self.max_nesting, self.nesting)
        return True

    def leave_Match(self, node: cst.Match) -> None:
        self.nesting -= 1

    def visit_IfExp(self, node: cst.IfExp) -> Optional[bool]:
        self.complexity += 1
        return True

    def visit_BooleanOperation(self, node: cst.BooleanOperation) -> Optional[bool]:
        op_type = type(node.operator)
        parent_op = self._bool_op_stack[-1] if self._bool_op_stack else None
        if op_type != parent_op:
            self.complexity += 1
        self._bool_op_stack.append(op_type)
        return True

    def leave_BooleanOperation(self, node: cst.BooleanOperation) -> None:
        self._bool_op_stack.pop()

    def visit_Break(self, node: cst.Break) -> Optional[bool]:
        self.complexity += 1
        return False

    def visit_Continue(self, node: cst.Continue) -> Optional[bool]:
        self.complexity += 1
        return False

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
        self.complexity = 1

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
    """Visits a module and collects metrics for each function/method."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.functions: List[FunctionMetrics] = []
        self.classes: List[ClassMetrics] = []
        self._class_stack: List[str] = []
        self._class_methods_stack: List[List[FunctionMetrics]] = []
        self._class_nodes_stack: List[cst.ClassDef] = []
        self._wrapper = None

    def set_wrapper(self, wrapper):
        self._wrapper = wrapper

    def _get_line(self, node) -> int:
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

        cog_visitor = CognitiveComplexityVisitor()
        walk_node(node.body, cog_visitor)

        cyc_visitor = CyclomaticComplexityVisitor()
        walk_node(node.body, cyc_visitor)

        line = self._get_line(node)
        end_line = self._get_end_line(node)
        nloc = max(end_line - line + 1, 0)

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

        if self._class_methods_stack:
            self._class_methods_stack[-1].append(fm)

        return False


# ---------------------------------------------------------------------------
# Python line counting
# ---------------------------------------------------------------------------

def count_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for Python source."""
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

_active_cache = None


def set_cache(cache):
    """Set the active cache instance for scan operations."""
    global _active_cache
    _active_cache = cache


def get_cache():
    """Get the active cache instance."""
    return _active_cache


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

_DEFAULT_EXCLUDES = [
    "**/venv/**", "**/.venv/**", "**/node_modules/**",
    "**/__pycache__/**", "**/build/**", "**/dist/**",
    "**/.git/**", "**/migrations/**",
]


def discover_files(
    directory: str,
    exclude_patterns: Optional[List[str]] = None,
    include_tests: bool = False,
) -> List[str]:
    """Find all supported source files in a directory, respecting exclude and test patterns."""
    from fnmatch import fnmatch

    if exclude_patterns is None:
        exclude_patterns = _DEFAULT_EXCLUDES

    root = Path(directory)
    files = []
    for source_file in sorted(root.rglob("*")):
        if source_file.suffix not in SUPPORTED_EXTENSIONS:
            continue
        rel = str(source_file.relative_to(root))
        if any(fnmatch(rel, pat) or fnmatch(str(source_file), pat) for pat in exclude_patterns):
            continue
        if not include_tests and any(fnmatch(rel, pat) for pat in TEST_FILE_PATTERNS):
            continue
        files.append(str(source_file))
    return files


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_file(file_path: str) -> FileMetrics:
    """Scan a single source file and return its metrics."""
    if _active_cache is not None:
        cached = _active_cache.get(file_path)
        if cached is not None:
            return cached

    result = _scan_file_uncached(file_path)

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

    # Python file parsing
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
    """Recursively scan all supported source files in a directory."""
    files_to_scan = discover_files(directory, exclude_patterns, include_tests)
    result = ScanResult()

    if workers == 1 or len(files_to_scan) <= 4:
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
