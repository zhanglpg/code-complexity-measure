"""
Shared base class for tree-sitter language parsers.

Provides common scaffolding for cognitive/cyclomatic complexity computation,
line counting (C-style comments), and file scanning. Language-specific parsers
subclass TreeSitterParser and configure node-type mappings.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .scanner import FunctionMetrics, FileMetrics, compute_mi


class TreeSitterParser:
    """Base class for tree-sitter-based complexity parsers.

    Subclasses must set class-level configuration and implement:
      - collect_functions(tree, file_path, source_bytes) -> List[FunctionMetrics]
      - is_else_if(node) -> bool
    """

    # --- Subclass must set these -------------------------------------------
    language = None            # tree-sitter Language object
    language_name: str = ""    # e.g. "go", "java"
    install_extra: str = ""    # pip extra name, e.g. "go"

    # --- Cognitive complexity config ----------------------------------------
    if_type: str = "if_statement"
    loop_types: frozenset = frozenset()
    switch_types: frozenset = frozenset()
    catch_types: frozenset = frozenset()

    # Body node types (consequence blocks that increment nesting)
    body_types: frozenset = frozenset({"block"})
    # Else-clause wrapper types (JS/TS/Rust/C++ use "else_clause"; Go/Java: empty)
    else_clause_types: frozenset = frozenset()

    # Switch internals
    switch_body_types: frozenset = frozenset()   # container for cases
    case_types: frozenset = frozenset()           # individual case nodes

    # Boolean operators
    binary_expr_type: str = "binary_expression"
    bool_op_types: frozenset = frozenset({"&&", "||"})
    bool_op_field: Optional[str] = None  # "operator" to use child_by_field_name

    # Simple +1 increments (no nesting change): break, continue
    break_types: frozenset = frozenset({"break_statement", "continue_statement"})
    # Simple +1 increments with child recursion (go_statement, try_expression, etc.)
    extra_increment_types: frozenset = frozenset()
    # Lambda/closure types (increase nesting, no complexity increment)
    lambda_types: frozenset = frozenset()
    # Nesting-only types (increase nesting, no complexity increment, e.g. unsafe_block)
    nesting_only_types: frozenset = frozenset()

    # --- Cyclomatic complexity config ---------------------------------------
    cyclomatic_node_types: frozenset = frozenset()  # each increments by 1

    # --- Comment style (for line counting) ----------------------------------
    line_comment_prefix: str = "//"
    block_comment_start: str = "/*"
    block_comment_end: str = "*/"

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def ensure_available(self):
        if self.language is None:
            raise ImportError(
                f"{self.language_name.title()} support requires tree-sitter-{self.language_name}. "
                f"Install with: pip install complexity-accounting[{self.install_extra}]"
            )

    def get_language(self, path: Path):
        """Return the tree-sitter language to use for *path*. Override for TSX."""
        return self.language

    def scan_file(self, file_path: str) -> FileMetrics:
        import tree_sitter as ts

        self.ensure_available()
        path = Path(file_path)
        source = path.read_text(encoding="utf-8", errors="replace")
        source_bytes = source.encode("utf-8")

        total, code, comment_lines, blank = self.count_lines(source)

        parser = ts.Parser(self.get_language(path))
        tree = parser.parse(source_bytes)

        functions = self.collect_functions(tree, str(path), source_bytes)

        return FileMetrics(
            path=str(path),
            functions=functions,
            total_lines=total,
            code_lines=code,
            comment_lines=comment_lines,
            blank_lines=blank,
        )

    # -----------------------------------------------------------------------
    # Line counting (C-style comments: // and /* */)
    # -----------------------------------------------------------------------

    def count_lines(self, source: str) -> tuple:
        """Returns (total, code, comment, blank) line counts."""
        total = 0
        code = 0
        comment = 0
        blank = 0
        in_block_comment = False
        bcs = self.block_comment_start
        bce = self.block_comment_end

        for raw_line in source.splitlines():
            total += 1
            line = raw_line.strip()

            if not line:
                blank += 1
                continue

            if in_block_comment:
                comment += 1
                if bce in line:
                    in_block_comment = False
                continue

            if line.startswith(self.line_comment_prefix):
                comment += 1
                continue

            if bcs in line:
                if bce in line[line.index(bcs) + len(bcs):]:
                    code += 1
                else:
                    in_block_comment = True
                    comment += 1
                continue

            code += 1

        return total, code, comment, blank

    # -----------------------------------------------------------------------
    # Function metrics helper
    # -----------------------------------------------------------------------

    def build_function_metrics(
        self, node, name: str, qualified_name: str,
        file_path: str, body, params_count: int,
    ) -> FunctionMetrics:
        cog, max_nest = self.compute_cognitive_complexity(body) if body else (0, 0)
        cyc = self.compute_cyclomatic_complexity(body) if body else 1
        nloc = node.end_point[0] - node.start_point[0] + 1
        return FunctionMetrics(
            name=name,
            qualified_name=qualified_name,
            file_path=file_path,
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            cognitive_complexity=cog,
            cyclomatic_complexity=cyc,
            nloc=nloc,
            params=params_count,
            max_nesting=max_nest,
            maintainability_index=compute_mi(nloc, cyc),
        )

    # -----------------------------------------------------------------------
    # Cognitive complexity (generic walker with configurable node types)
    # -----------------------------------------------------------------------

    def is_else_if(self, node) -> bool:
        """Return True if *node* (an if-type node) is an else-if continuation."""
        raise NotImplementedError

    def compute_cognitive_complexity(self, node) -> tuple:
        """Compute cognitive complexity for a function body node.

        Returns (complexity, max_nesting).
        """
        complexity = 0
        max_nesting = 0

        def walk(n, nesting, parent_bool_op=None):
            nonlocal complexity, max_nesting

            # --- If statement ---
            if n.type == self.if_type:
                if self.is_else_if(n):
                    complexity += 1
                    for child in n.children:
                        walk(child, nesting)
                else:
                    complexity += 1 + nesting
                    max_nesting = max(max_nesting, nesting + 1)
                    self._walk_if_children(n, nesting, walk)
                return

            # --- Loops ---
            if n.type in self.loop_types:
                complexity += 1 + nesting
                max_nesting = max(max_nesting, nesting + 1)
                for child in n.children:
                    if child.type in self.body_types:
                        walk(child, nesting + 1)
                    else:
                        walk(child, nesting)
                return

            # --- Switch / match ---
            if n.type in self.switch_types:
                complexity += 1 + nesting
                max_nesting = max(max_nesting, nesting + 1)
                self._walk_switch_children(n, nesting, walk)
                return

            # --- Catch ---
            if n.type in self.catch_types:
                complexity += 1 + nesting
                max_nesting = max(max_nesting, nesting + 1)
                for child in n.children:
                    if child.type in self.body_types:
                        walk(child, nesting + 1)
                    else:
                        walk(child, nesting)
                return

            # --- Boolean operators ---
            if n.type == self.binary_expr_type:
                op_type = self._get_bool_op(n)
                if op_type and op_type in self.bool_op_types:
                    if op_type != parent_bool_op:
                        complexity += 1
                    for child in n.children:
                        walk(child, nesting, parent_bool_op=op_type)
                    return

            # --- Extra increment types (e.g. go_statement, ternary, try) ---
            if n.type in self.extra_increment_types:
                complexity += 1
                for child in n.children:
                    walk(child, nesting)
                return

            # --- Break / continue (leaf) ---
            if n.type in self.break_types:
                complexity += 1
                return

            # --- Lambda / closure (nesting, no complexity) ---
            if n.type in self.lambda_types:
                max_nesting = max(max_nesting, nesting + 1)
                for child in n.children:
                    if child.type in self.body_types:
                        walk(child, nesting + 1)
                    else:
                        walk(child, nesting)
                return

            # --- Nesting-only types (e.g. unsafe_block) ---
            if n.type in self.nesting_only_types:
                max_nesting = max(max_nesting, nesting + 1)
                for child in n.children:
                    if child.type in self.body_types:
                        walk(child, nesting + 1)
                    else:
                        walk(child, nesting)
                return

            # --- Default: recurse ---
            for child in n.children:
                walk(child, nesting)

        walk(node, 0)
        return complexity, max_nesting

    def _walk_if_children(self, node, nesting, walk_fn):
        """Walk children of a non-else-if if-statement."""
        for child in node.children:
            if child.type in self.body_types:
                walk_fn(child, nesting + 1)
            elif child.type in self.else_clause_types:
                for ec_child in child.children:
                    if ec_child.type in self.body_types:
                        walk_fn(ec_child, nesting + 1)
                    elif ec_child.type == self.if_type:
                        walk_fn(ec_child, nesting)
                    else:
                        walk_fn(ec_child, nesting)
            else:
                walk_fn(child, nesting)

    def _walk_switch_children(self, node, nesting, walk_fn):
        """Walk children of a switch/match statement."""
        for child in node.children:
            if child.type in self.case_types:
                walk_fn(child, nesting + 1)
            elif child.type in self.switch_body_types:
                for sub in child.children:
                    if sub.type in self.case_types:
                        walk_fn(sub, nesting + 1)
                    else:
                        walk_fn(sub, nesting)
            else:
                walk_fn(child, nesting)

    def _get_bool_op(self, node):
        """Extract the boolean operator type from a binary expression node."""
        if self.bool_op_field:
            op_node = node.child_by_field_name(self.bool_op_field)
            return op_node.type if op_node else None
        for child in node.children:
            if child.type in self.bool_op_types:
                return child.type
        return None

    # -----------------------------------------------------------------------
    # Cyclomatic complexity (fully config-driven)
    # -----------------------------------------------------------------------

    def compute_cyclomatic_complexity(self, node) -> int:
        """Compute McCabe cyclomatic complexity for a function body. Baseline = 1."""
        complexity = 1

        def walk(n):
            nonlocal complexity

            if n.type in self.cyclomatic_node_types:
                complexity += 1
            elif n.type == self.binary_expr_type:
                op_type = self._get_bool_op(n)
                if op_type and op_type in self.bool_op_types:
                    complexity += 1

            for child in n.children:
                walk(child)

        walk(node)
        return complexity

    # -----------------------------------------------------------------------
    # Abstract method
    # -----------------------------------------------------------------------

    def collect_functions(self, tree, file_path: str, source_bytes: bytes) -> List[FunctionMetrics]:
        """Extract function metrics from the parsed tree. Subclass must implement."""
        raise NotImplementedError
