"""
Rust complexity parser using tree-sitter.

Computes cognitive and cyclomatic complexity for Rust source files,
producing the same FunctionMetrics/FileMetrics as the Python scanner.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .scanner import FunctionMetrics, FileMetrics

try:
    import tree_sitter as ts
    import tree_sitter_rust as tsrust

    RUST_LANGUAGE = ts.Language(tsrust.language())
except ImportError:
    RUST_LANGUAGE = None


def _ensure_tree_sitter():
    if RUST_LANGUAGE is None:
        raise ImportError(
            "Rust support requires tree-sitter-rust. "
            "Install with: pip install complexity-accounting[rust]"
        )


# ---------------------------------------------------------------------------
# Cognitive Complexity for Rust
# ---------------------------------------------------------------------------

def _compute_cognitive_complexity(node) -> tuple:
    """
    Compute cognitive complexity for a Rust function body.

    Returns (complexity, max_nesting).
    """
    complexity = 0
    max_nesting = 0

    def walk(n, nesting):
        nonlocal complexity, max_nesting

        if n.type == "if_expression":
            # Check if this is an else-if (parent is else_clause)
            is_else_if = n.parent and n.parent.type == "else_clause"

            if is_else_if:
                # else-if: +1 but no nesting increment (continuation of chain)
                complexity += 1
                for child in n.children:
                    if child.type == "block":
                        walk(child, nesting)
                    elif child.type == "else_clause":
                        walk(child, nesting)
                    else:
                        walk(child, nesting)
            else:
                complexity += 1 + nesting
                max_nesting = max(max_nesting, nesting + 1)
                for child in n.children:
                    if child.type == "block":
                        walk(child, nesting + 1)
                    elif child.type == "else_clause":
                        walk(child, nesting)
                    else:
                        walk(child, nesting)
            return

        if n.type == "for_expression":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "while_expression":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "loop_expression":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "match_expression":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "match_block":
                    for arm in child.children:
                        if arm.type == "match_arm":
                            walk(arm, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "binary_expression":
            has_bool_op = False
            for child in n.children:
                if child.type in ("&&", "||"):
                    has_bool_op = True
                    break
            if has_bool_op:
                complexity += 1
                for child in n.children:
                    walk(child, nesting)
                return

        if n.type == "try_expression":
            # The ? operator is hidden control flow
            complexity += 1
            for child in n.children:
                walk(child, nesting)
            return

        if n.type == "break_expression":
            complexity += 1
            return

        if n.type == "continue_expression":
            complexity += 1
            return

        if n.type == "closure_expression":
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "unsafe_block":
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
# Cyclomatic Complexity for Rust
# ---------------------------------------------------------------------------

def _compute_cyclomatic_complexity(node) -> int:
    """Compute McCabe cyclomatic complexity for a Rust function body. Baseline = 1."""
    complexity = 1

    def walk(n):
        nonlocal complexity

        if n.type == "if_expression":
            complexity += 1
        elif n.type == "for_expression":
            complexity += 1
        elif n.type == "while_expression":
            complexity += 1
        elif n.type == "loop_expression":
            complexity += 1
        elif n.type == "match_arm":
            complexity += 1
        elif n.type == "binary_expression":
            for child in n.children:
                if child.type in ("&&", "||"):
                    complexity += 1
                    break
        elif n.type == "try_expression":
            complexity += 1

        for child in n.children:
            walk(child)

    walk(node)
    return complexity


# ---------------------------------------------------------------------------
# Function collection
# ---------------------------------------------------------------------------

def _count_params(params_node) -> int:
    """Count parameters in a Rust parameters node, excluding self."""
    count = 0
    for child in params_node.children:
        if child.type == "parameter":
            count += 1
        # self_parameter is intentionally excluded
    return count


def _collect_functions(tree, file_path: str, source: bytes) -> List[FunctionMetrics]:
    """Extract function metrics from a Rust AST."""
    functions = []

    def visit(node, scope_stack):
        if node.type == "impl_item":
            # Extract the type name for qualified names
            # impl Type { ... } or impl Trait for Type { ... }
            type_ids = [c for c in node.children if c.type == "type_identifier"]
            has_for = any(c.type == "for" for c in node.children)

            if has_for and len(type_ids) >= 2:
                # impl Trait for Type — use the second type_identifier
                impl_type = type_ids[1].text.decode()
            elif type_ids:
                impl_type = type_ids[0].text.decode()
            else:
                impl_type = "<unknown>"

            for child in node.children:
                if child.type == "declaration_list":
                    for decl_child in child.children:
                        visit(decl_child, scope_stack + [impl_type])
            return

        if node.type == "function_item":
            name_node = None
            for child in node.children:
                if child.type == "identifier":
                    name_node = child
                    break
            name = name_node.text.decode() if name_node else "<unknown>"
            qualified = f"{'.'.join(scope_stack)}.{name}" if scope_stack else name

            # Find the function body (block)
            body = None
            for child in node.children:
                if child.type == "block":
                    body = child

            # Find parameters
            params_node = None
            for child in node.children:
                if child.type == "parameters":
                    params_node = child
                    break

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

        # Recurse into other top-level nodes
        for child in node.children:
            visit(child, scope_stack)

    visit(tree.root_node, [])
    return functions


# ---------------------------------------------------------------------------
# Line counting for Rust
# ---------------------------------------------------------------------------

def count_rust_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for Rust source."""
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
            # Covers //, ///, //!
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

def scan_rust_file(file_path: str) -> FileMetrics:
    """Scan a single Rust file and return its metrics."""
    _ensure_tree_sitter()

    path = Path(file_path)
    source = path.read_text(encoding="utf-8", errors="replace")
    source_bytes = source.encode("utf-8")

    total, code, comment_lines, blank = count_rust_lines(source)

    parser = ts.Parser(RUST_LANGUAGE)
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
