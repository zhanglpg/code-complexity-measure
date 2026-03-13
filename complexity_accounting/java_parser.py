"""
Java complexity parser using tree-sitter.

Computes cognitive and cyclomatic complexity for Java source files,
producing the same FunctionMetrics/FileMetrics as the Python scanner.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .scanner import FunctionMetrics, FileMetrics

try:
    import tree_sitter as ts
    import tree_sitter_java as tsjava

    JAVA_LANGUAGE = ts.Language(tsjava.language())
except ImportError:
    JAVA_LANGUAGE = None


def _ensure_tree_sitter():
    if JAVA_LANGUAGE is None:
        raise ImportError(
            "Java support requires tree-sitter-java. "
            "Install with: pip install complexity-accounting[java]"
        )


# ---------------------------------------------------------------------------
# Cognitive Complexity for Java
# ---------------------------------------------------------------------------

def _compute_cognitive_complexity(node) -> tuple:
    """
    Compute cognitive complexity for a Java method/constructor body.

    Returns (complexity, max_nesting).
    """
    complexity = 0
    max_nesting = 0

    def walk(n, nesting):
        nonlocal complexity, max_nesting

        if n.type == "if_statement":
            # Check if this is an else-if (this if is the alternative of a parent if)
            is_else_if = (
                n.parent
                and n.parent.type == "if_statement"
                and n == n.parent.child_by_field_name("alternative")
            )

            if is_else_if:
                # else-if: +1 but no nesting increment (continuation of chain)
                complexity += 1
                for child in n.children:
                    if child.type == "block" and child == n.child_by_field_name("consequence"):
                        walk(child, nesting)
                    elif child.type == "if_statement":
                        walk(child, nesting)
                    elif child.type == "block" and child == n.child_by_field_name("alternative"):
                        walk(child, nesting)
                    else:
                        walk(child, nesting)
            else:
                complexity += 1 + nesting
                max_nesting = max(max_nesting, nesting + 1)
                for child in n.children:
                    if child.type == "block" and child == n.child_by_field_name("consequence"):
                        walk(child, nesting + 1)
                    elif child.type == "if_statement":
                        # else-if chain
                        walk(child, nesting)
                    elif child.type == "block" and child == n.child_by_field_name("alternative"):
                        # else block
                        walk(child, nesting + 1)
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

        if n.type == "enhanced_for_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "while_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "do_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "switch_expression":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "switch_block":
                    for case_child in child.children:
                        if case_child.type in ("switch_block_statement_group", "switch_rule"):
                            walk(case_child, nesting + 1)
                        else:
                            walk(case_child, nesting)
                else:
                    walk(child, nesting)
            return

        if n.type == "catch_clause":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "ternary_expression":
            complexity += 1
            for child in n.children:
                walk(child, nesting)
            return

        if n.type == "binary_expression":
            op_node = n.child_by_field_name("operator")
            if op_node and op_node.type in ("&&", "||"):
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

        if n.type == "lambda_expression":
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
# Cyclomatic Complexity for Java
# ---------------------------------------------------------------------------

def _compute_cyclomatic_complexity(node) -> int:
    """Compute McCabe cyclomatic complexity for a Java method body. Baseline = 1."""
    complexity = 1

    def walk(n):
        nonlocal complexity

        if n.type == "if_statement":
            complexity += 1
        elif n.type == "for_statement":
            complexity += 1
        elif n.type == "enhanced_for_statement":
            complexity += 1
        elif n.type == "while_statement":
            complexity += 1
        elif n.type == "do_statement":
            complexity += 1
        elif n.type == "switch_block_statement_group":
            # Each case group is a decision path
            complexity += 1
        elif n.type == "switch_rule":
            complexity += 1
        elif n.type == "catch_clause":
            complexity += 1
        elif n.type == "binary_expression":
            op_node = n.child_by_field_name("operator")
            if op_node and op_node.type in ("&&", "||"):
                complexity += 1
        elif n.type == "ternary_expression":
            complexity += 1

        for child in n.children:
            walk(child)

    walk(node)
    return complexity


# ---------------------------------------------------------------------------
# Function collection
# ---------------------------------------------------------------------------

def _count_params(formal_params_node) -> int:
    """Count parameters in a Java formal_parameters node."""
    count = 0
    for child in formal_params_node.children:
        if child.type in ("formal_parameter", "spread_parameter"):
            count += 1
    return count


def _collect_functions(tree, file_path: str, source: bytes) -> List[FunctionMetrics]:
    """Extract function metrics from a Java AST."""
    functions = []

    def visit(node, class_stack):
        if node.type in ("class_declaration", "interface_declaration", "enum_declaration"):
            name_node = node.child_by_field_name("name")
            class_name = name_node.text.decode() if name_node else "<unknown>"
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    visit(child, class_stack + [class_name])
            return

        if node.type in ("method_declaration", "constructor_declaration"):
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode() if name_node else "<unknown>"

            qualified = f"{'.'.join(class_stack)}.{name}" if class_stack else name

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
            return

        # Recurse into other nodes (e.g., program level)
        for child in node.children:
            visit(child, class_stack)

    visit(tree.root_node, [])
    return functions


# ---------------------------------------------------------------------------
# Line counting for Java
# ---------------------------------------------------------------------------

def count_java_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for Java source."""
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

def scan_java_file(file_path: str) -> FileMetrics:
    """Scan a single Java file and return its metrics."""
    _ensure_tree_sitter()

    path = Path(file_path)
    source = path.read_text(encoding="utf-8", errors="replace")
    source_bytes = source.encode("utf-8")

    total, code, comment_lines, blank = count_java_lines(source)

    parser = ts.Parser(JAVA_LANGUAGE)
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
