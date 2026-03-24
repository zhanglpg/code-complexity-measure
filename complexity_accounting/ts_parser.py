"""
TypeScript complexity parser using tree-sitter.

Computes cognitive and cyclomatic complexity for TypeScript source files,
producing the same FunctionMetrics/FileMetrics as the Python scanner.
Supports both .ts and .tsx files.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .base_parser import TreeSitterParser, FunctionMetrics, FileMetrics, compute_mi

try:
    import tree_sitter as ts
    import tree_sitter_typescript as tsts

    TS_LANGUAGE = ts.Language(tsts.language_typescript())
    TSX_LANGUAGE = ts.Language(tsts.language_tsx())
except ImportError:
    TS_LANGUAGE = None
    TSX_LANGUAGE = None


class TsParser(TreeSitterParser):
    language = TS_LANGUAGE
    language_name = "typescript"
    install_extra = "ts"

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
    class_node_types = frozenset({"class_declaration", "abstract_class_declaration"})

    # Cyclomatic config
    cyclomatic_node_types = frozenset({
        "if_statement", "for_statement", "for_in_statement",
        "while_statement", "do_statement", "switch_case",
        "catch_clause", "ternary_expression",
    })

    def get_language(self, path: Path):
        return TSX_LANGUAGE if path.suffix == ".tsx" else TS_LANGUAGE

    _js_skip_types = frozenset({
        "interface_declaration", "type_alias_declaration",
        "enum_declaration", "abstract_method_signature",
    })
    _js_class_types = frozenset({"class_declaration", "abstract_class_declaration"})

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
    """Count parameters in a TypeScript formal_parameters node."""
    count = 0
    for child in formal_params_node.children:
        if child.type in (
            "required_parameter",
            "optional_parameter",
            "rest_pattern",
            "identifier",
            "assignment_pattern",
            "array_pattern",
            "object_pattern",
        ):
            count += 1
    return count


# Singleton instance
_parser = TsParser()


def _ensure_tree_sitter():
    if TS_LANGUAGE is None:
        raise ImportError(
            "TypeScript support requires tree-sitter-typescript. "
            "Install with: pip install complexity-accounting[ts]"
        )


# ---------------------------------------------------------------------------
# Public API (backward-compatible)
# ---------------------------------------------------------------------------

def count_ts_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for TypeScript source."""
    return _parser.count_lines(source)


def scan_ts_file(file_path: str) -> FileMetrics:
    """Scan a single TypeScript file and return its metrics."""
    return _parser.scan_file(file_path)
