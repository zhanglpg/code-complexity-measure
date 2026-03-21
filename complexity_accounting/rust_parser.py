"""
Rust complexity parser using tree-sitter.

Computes cognitive and cyclomatic complexity for Rust source files,
producing the same FunctionMetrics/FileMetrics as the Python scanner.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .scanner import FunctionMetrics, FileMetrics, compute_mi
from .base_parser import TreeSitterParser

try:
    import tree_sitter as ts
    import tree_sitter_rust as tsrust

    RUST_LANGUAGE = ts.Language(tsrust.language())
except (ImportError, ValueError):
    RUST_LANGUAGE = None


class RustParser(TreeSitterParser):
    language = RUST_LANGUAGE
    language_name = "rust"
    install_extra = "rust"

    # Cognitive config
    if_type = "if_expression"
    loop_types = frozenset({"for_expression", "while_expression", "loop_expression"})
    switch_types = frozenset({"match_expression"})
    body_types = frozenset({"block"})
    else_clause_types = frozenset({"else_clause"})

    switch_body_types = frozenset({"match_block"})
    case_types = frozenset({"match_arm"})

    bool_op_types = frozenset({"&&", "||"})
    break_types = frozenset({"break_expression", "continue_expression"})
    extra_increment_types = frozenset({"try_expression"})
    lambda_types = frozenset({"closure_expression"})
    nesting_only_types = frozenset({"unsafe_block"})

    # Cyclomatic config
    cyclomatic_node_types = frozenset({
        "if_expression", "for_expression", "while_expression",
        "loop_expression", "match_arm", "try_expression",
    })

    def is_else_if(self, node) -> bool:
        return node.parent and node.parent.type == "else_clause"

    def collect_functions(self, tree, file_path: str, source_bytes: bytes) -> List[FunctionMetrics]:
        functions = []

        def visit(node, scope_stack):
            if node.type == "impl_item":
                type_ids = [c for c in node.children if c.type == "type_identifier"]
                has_for = any(c.type == "for" for c in node.children)

                if has_for and len(type_ids) >= 2:
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

                body = None
                for child in node.children:
                    if child.type == "block":
                        body = child

                params_node = None
                for child in node.children:
                    if child.type == "parameters":
                        params_node = child
                        break

                functions.append(self.build_function_metrics(
                    node, name, qualified, file_path, body,
                    _count_params(params_node) if params_node else 0,
                ))
                return

            for child in node.children:
                visit(child, scope_stack)

        visit(tree.root_node, [])
        return functions


def _count_params(params_node) -> int:
    """Count parameters in a Rust parameters node, excluding self."""
    count = 0
    for child in params_node.children:
        if child.type == "parameter":
            count += 1
    return count


# Singleton instance
_parser = RustParser()


def _ensure_tree_sitter():
    if RUST_LANGUAGE is None:
        raise ImportError(
            "Rust support requires tree-sitter-rust. "
            "Install with: pip install complexity-accounting[rust]"
        )


# ---------------------------------------------------------------------------
# Public API (backward-compatible)
# ---------------------------------------------------------------------------

def count_rust_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for Rust source."""
    return _parser.count_lines(source)


def scan_rust_file(file_path: str) -> FileMetrics:
    """Scan a single Rust file and return its metrics."""
    return _parser.scan_file(file_path)
