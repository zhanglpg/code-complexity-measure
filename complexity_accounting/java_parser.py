"""
Java complexity parser using tree-sitter.

Computes cognitive and cyclomatic complexity for Java source files,
producing the same FunctionMetrics/FileMetrics as the Python scanner.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .models import FunctionMetrics, FileMetrics, compute_mi
from .base_parser import TreeSitterParser

try:
    import tree_sitter as ts
    import tree_sitter_java as tsjava

    JAVA_LANGUAGE = ts.Language(tsjava.language())
except ImportError:
    JAVA_LANGUAGE = None


class JavaParser(TreeSitterParser):
    language = JAVA_LANGUAGE
    language_name = "java"
    install_extra = "java"

    # Cognitive config
    if_type = "if_statement"
    loop_types = frozenset({"for_statement", "enhanced_for_statement", "while_statement", "do_statement"})
    switch_types = frozenset({"switch_expression"})
    catch_types = frozenset({"catch_clause"})
    body_types = frozenset({"block"})
    else_clause_types = frozenset()  # Java has no else_clause wrapper

    switch_body_types = frozenset({"switch_block"})
    case_types = frozenset({"switch_block_statement_group", "switch_rule"})

    bool_op_types = frozenset({"&&", "||"})
    bool_op_field = "operator"
    break_types = frozenset({"break_statement", "continue_statement"})
    extra_increment_types = frozenset({"ternary_expression"})
    lambda_types = frozenset({"lambda_expression"})

    # Class-level metrics
    class_node_types = frozenset({"class_declaration", "interface_declaration", "enum_declaration"})

    # Cyclomatic config
    cyclomatic_node_types = frozenset({
        "if_statement", "for_statement", "enhanced_for_statement",
        "while_statement", "do_statement",
        "switch_block_statement_group", "switch_rule",
        "catch_clause", "ternary_expression",
    })

    def is_else_if(self, node) -> bool:
        return (
            node.parent
            and node.parent.type == "if_statement"
            and node == node.parent.child_by_field_name("alternative")
        )

    def collect_functions(self, tree, file_path: str, source_bytes: bytes) -> List[FunctionMetrics]:
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

                functions.append(self.build_function_metrics(
                    node, name, qualified, file_path, body,
                    _count_params(params_node) if params_node else 0,
                ))
                return

            for child in node.children:
                visit(child, class_stack)

        visit(tree.root_node, [])
        return functions


def _count_params(formal_params_node) -> int:
    """Count parameters in a Java formal_parameters node."""
    count = 0
    for child in formal_params_node.children:
        if child.type in ("formal_parameter", "spread_parameter"):
            count += 1
    return count


# Singleton instance
_parser = JavaParser()


def _ensure_tree_sitter():
    if JAVA_LANGUAGE is None:
        raise ImportError(
            "Java support requires tree-sitter-java. "
            "Install with: pip install complexity-accounting[java]"
        )


# ---------------------------------------------------------------------------
# Public API (backward-compatible)
# ---------------------------------------------------------------------------

def count_java_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for Java source."""
    return _parser.count_lines(source)


def scan_java_file(file_path: str) -> FileMetrics:
    """Scan a single Java file and return its metrics."""
    return _parser.scan_file(file_path)
