"""
Go complexity parser using tree-sitter.

Computes cognitive and cyclomatic complexity for Go source files,
producing the same FunctionMetrics/FileMetrics as the Python scanner.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .scanner import FunctionMetrics, FileMetrics

try:
    import tree_sitter as ts
    import tree_sitter_go as tsgo

    GO_LANGUAGE = ts.Language(tsgo.language())
except ImportError:
    GO_LANGUAGE = None


def _ensure_tree_sitter():
    if GO_LANGUAGE is None:
        raise ImportError(
            "Go support requires tree-sitter-go. "
            "Install with: pip install complexity-accounting[go]"
        )


# ---------------------------------------------------------------------------
# Cognitive Complexity for Go
# ---------------------------------------------------------------------------

def _compute_cognitive_complexity(node) -> tuple:
    """
    Compute cognitive complexity for a Go function body.

    Returns (complexity, max_nesting).
    """
    complexity = 0
    max_nesting = 0

    def walk(n, nesting):
        nonlocal complexity, max_nesting

        if n.type == "if_statement":
            # Check if this is an else-if (parent is if_statement's else clause)
            # In tree-sitter, else-if appears as: if_statement -> "else" -> if_statement
            # The parent relationship: if this if_statement's previous sibling is "else"
            is_else_if = False
            if n.prev_named_sibling is None and n.parent and n.parent.type == "if_statement":
                # This is in the else branch of parent if — check if preceded by "else" token
                for i, child in enumerate(n.parent.children):
                    if child.type == "else" and i + 1 < len(n.parent.children) and n.parent.children[i + 1] == n:
                        is_else_if = True
                        break

            if is_else_if:
                # else-if: +1 but no nesting increment (continuation of chain)
                complexity += 1
                for child in n.children:
                    walk(child, nesting)
            else:
                complexity += 1 + nesting
                max_nesting = max(max_nesting, nesting + 1)
                for child in n.children:
                    if child.type == "block":
                        walk(child, nesting + 1)
                    elif child.type == "if_statement":
                        # else-if chain
                        walk(child, nesting)
                    else:
                        walk(child, nesting)
            return

        if n.type == "for_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type in ("expression_switch_statement", "type_switch_statement"):
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type in ("expression_case", "default_case"):
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "select_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "communication_case":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "binary_expression":
            op_node = None
            for child in n.children:
                if child.type in ("&&", "||"):
                    op_node = child
                    break
            if op_node:
                complexity += 1
                for child in n.children:
                    walk(child, nesting)
                return

        if n.type == "go_statement":
            complexity += 1
            for child in n.children:
                walk(child, nesting)
            return

        if n.type == "defer_statement":
            complexity += 1
            for child in n.children:
                walk(child, nesting)
            return

        if n.type == "break_statement":
            complexity += 1
            return

        if n.type == "continue_statement":
            complexity += 1
            return

        if n.type == "func_literal":
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        for child in n.children:
            walk(child, nesting)

    walk(node, 0)
    return complexity, max_nesting


# ---------------------------------------------------------------------------
# Cyclomatic Complexity for Go
# ---------------------------------------------------------------------------

def _compute_cyclomatic_complexity(node) -> int:
    """Compute McCabe cyclomatic complexity for a Go function body. Baseline = 1."""
    complexity = 1

    def walk(n):
        nonlocal complexity

        if n.type == "if_statement":
            complexity += 1
        elif n.type == "for_statement":
            complexity += 1
        elif n.type in ("expression_case", "communication_case"):
            complexity += 1
        elif n.type == "binary_expression":
            for child in n.children:
                if child.type in ("&&", "||"):
                    complexity += 1
                    break
        elif n.type == "go_statement":
            complexity += 1
        elif n.type == "defer_statement":
            complexity += 1

        for child in n.children:
            walk(child)

    walk(node)
    return complexity


# ---------------------------------------------------------------------------
# Function collection
# ---------------------------------------------------------------------------

def _count_params(param_list_node) -> int:
    """Count parameters in a Go parameter_list node."""
    count = 0
    for child in param_list_node.children:
        if child.type == "parameter_declaration":
            # Each parameter_declaration may have multiple identifiers
            ids = [c for c in child.children if c.type == "identifier"]
            count += max(len(ids), 1)
        elif child.type == "variadic_parameter_declaration":
            count += 1
    return count


def _collect_functions(tree, file_path: str, source: bytes) -> List[FunctionMetrics]:
    """Extract function metrics from a Go AST."""
    functions = []

    for node in tree.root_node.children:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode() if name_node else "<unknown>"
            qualified = name

            body = node.child_by_field_name("body")
            params_node = node.child_by_field_name("parameters")

            cog, max_nest = _compute_cognitive_complexity(body) if body else (0, 0)
            cyc = _compute_cyclomatic_complexity(body) if body else 1

            functions.append(FunctionMetrics(
                name=name,
                qualified_name=qualified,
                file_path=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                cognitive_complexity=cog,
                cyclomatic_complexity=cyc,
                nloc=node.end_point[0] - node.start_point[0] + 1,
                params=_count_params(params_node) if params_node else 0,
                max_nesting=max_nest,
            ))

        elif node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode() if name_node else "<unknown>"

            # Get receiver type for qualified name
            receiver = ""
            for child in node.children:
                if child.type == "parameter_list":
                    # First parameter_list is the receiver
                    for param in child.children:
                        if param.type == "parameter_declaration":
                            # Get the type (could be pointer_type or type_identifier)
                            for tc in param.children:
                                if tc.type == "type_identifier":
                                    receiver = tc.text.decode()
                                elif tc.type == "pointer_type":
                                    for inner in tc.children:
                                        if inner.type == "type_identifier":
                                            receiver = inner.text.decode()
                    break

            qualified = f"{receiver}.{name}" if receiver else name

            body = node.child_by_field_name("body")
            params_node = node.child_by_field_name("parameters")

            cog, max_nest = _compute_cognitive_complexity(body) if body else (0, 0)
            cyc = _compute_cyclomatic_complexity(body) if body else 1

            functions.append(FunctionMetrics(
                name=name,
                qualified_name=qualified,
                file_path=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                cognitive_complexity=cog,
                cyclomatic_complexity=cyc,
                nloc=node.end_point[0] - node.start_point[0] + 1,
                params=_count_params(params_node) if params_node else 0,
                max_nesting=max_nest,
            ))

    return functions


# ---------------------------------------------------------------------------
# Line counting for Go
# ---------------------------------------------------------------------------

def count_go_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for Go source."""
    total = 0
    code = 0
    comment = 0
    blank = 0
    in_block_comment = False

    for raw_line in source.splitlines():
        total += 1
        line = raw_line.strip()

        if not line:
            blank += 1
            continue

        if in_block_comment:
            comment += 1
            if "*/" in line:
                in_block_comment = False
            continue

        if line.startswith("//"):
            comment += 1
            continue

        if "/*" in line:
            if "*/" in line[line.index("/*") + 2:]:
                # Single-line block comment — count as code if there's code around it
                code += 1
            else:
                in_block_comment = True
                comment += 1
            continue

        code += 1

    return total, code, comment, blank


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_go_file(file_path: str) -> FileMetrics:
    """Scan a single Go file and return its metrics."""
    _ensure_tree_sitter()

    path = Path(file_path)
    source = path.read_text(encoding="utf-8", errors="replace")
    source_bytes = source.encode("utf-8")

    total, code, comment_lines, blank = count_go_lines(source)

    parser = ts.Parser(GO_LANGUAGE)
    tree = parser.parse(source_bytes)

    functions = _collect_functions(tree, str(path), source_bytes)

    return FileMetrics(
        path=str(path),
        functions=functions,
        total_lines=total,
        code_lines=code,
        comment_lines=comment_lines,
        blank_lines=blank,
    )
