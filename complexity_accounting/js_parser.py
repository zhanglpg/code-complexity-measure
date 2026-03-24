"""
JavaScript complexity parser using tree-sitter.

Computes cognitive and cyclomatic complexity for JavaScript source files,
producing the same FunctionMetrics/FileMetrics as the Python scanner.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .base_parser import TreeSitterParser, FunctionMetrics, FileMetrics, compute_mi

try:
    import tree_sitter as ts
    import tree_sitter_javascript as tsjs

    JS_LANGUAGE = ts.Language(tsjs.language())
except ImportError:
    JS_LANGUAGE = None


class JsParser(TreeSitterParser):
    language = JS_LANGUAGE
    language_name = "javascript"
    install_extra = "js"

    # Cognitive config
    if_type = "if_statement"
    loop_types = frozenset({"for_statement", "for_in_statement", "while_statement", "do_statement"})
    switch_types = frozenset({"switch_statement"})
    catch_types = frozenset({"catch_clause"})
    body_types = frozenset({"statement_block"})
    else_clause_types = frozenset({"else_clause"})

    switch_body_types = frozenset({"switch_body"})
    case_types = frozenset({"switch_case", "switch_default"})

    bool_op_types = frozenset({"&&", "||", "??"})
    bool_op_field = "operator"
    break_types = frozenset({"break_statement", "continue_statement"})
    extra_increment_types = frozenset({"ternary_expression"})
    lambda_types = frozenset({"arrow_function"})

    # Class-level metrics
    class_node_types = frozenset({"class_declaration"})

    # Cyclomatic config
    cyclomatic_node_types = frozenset({
        "if_statement", "for_statement", "for_in_statement",
        "while_statement", "do_statement", "switch_case",
        "catch_clause", "ternary_expression",
    })

    _js_class_types = frozenset({"class_declaration"})

    def is_else_if(self, node) -> bool:
        return (
            node.parent
            and node.parent.type == "else_clause"
            and node.parent.parent
            and node.parent.parent.type == "if_statement"
        )

    def collect_functions(self, tree, file_path: str, source_bytes: bytes) -> List[FunctionMetrics]:
        return self._collect_js_ts_functions(tree, file_path, _count_params)


def _count_params(formal_params_node) -> int:
    """Count parameters in a JavaScript formal_parameters node."""
    count = 0
    for child in formal_params_node.children:
        if child.type in (
            "identifier",
            "assignment_pattern",
            "rest_pattern",
            "array_pattern",
            "object_pattern",
        ):
            count += 1
    return count


# Singleton instance
_parser = JsParser()


def _ensure_tree_sitter():
    if JS_LANGUAGE is None:
        raise ImportError(
            "JavaScript support requires tree-sitter-javascript. "
            "Install with: pip install complexity-accounting[js]"
        )


# ---------------------------------------------------------------------------
# Public API (backward-compatible)
# ---------------------------------------------------------------------------

def count_js_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for JavaScript source."""
    return _parser.count_lines(source)


def scan_js_file(file_path: str) -> FileMetrics:
    """Scan a single JavaScript file and return its metrics."""
    return _parser.scan_file(file_path)
