"""
Go complexity parser using tree-sitter.

Computes cognitive and cyclomatic complexity for Go source files,
producing the same FunctionMetrics/FileMetrics as the Python scanner.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .scanner import FunctionMetrics, FileMetrics, ClassMetrics, compute_mi
from .base_parser import TreeSitterParser

try:
    import tree_sitter as ts
    import tree_sitter_go as tsgo

    GO_LANGUAGE = ts.Language(tsgo.language())
except ImportError:
    GO_LANGUAGE = None


class GoParser(TreeSitterParser):
    language = GO_LANGUAGE
    language_name = "go"
    install_extra = "go"

    # Cognitive config
    if_type = "if_statement"
    loop_types = frozenset({"for_statement"})
    switch_types = frozenset({"expression_switch_statement", "type_switch_statement", "select_statement"})
    body_types = frozenset({"block"})
    else_clause_types = frozenset()  # Go has no else_clause wrapper

    switch_body_types = frozenset()  # cases are direct children
    case_types = frozenset({"expression_case", "default_case", "communication_case"})

    bool_op_types = frozenset({"&&", "||"})
    break_types = frozenset({"break_statement", "continue_statement"})
    extra_increment_types = frozenset({"go_statement", "defer_statement"})
    lambda_types = frozenset({"func_literal"})

    # Cyclomatic config
    cyclomatic_node_types = frozenset({
        "if_statement", "for_statement", "expression_case",
        "communication_case", "go_statement", "defer_statement",
    })

    def is_else_if(self, node) -> bool:
        if node.prev_named_sibling is None and node.parent and node.parent.type == "if_statement":
            for i, child in enumerate(node.parent.children):
                if child.type == "else" and i + 1 < len(node.parent.children) and node.parent.children[i + 1] == node:
                    return True
        return False

    def collect_functions(self, tree, file_path: str, source_bytes: bytes) -> List[FunctionMetrics]:
        functions = []

        for node in tree.root_node.children:
            if node.type == "function_declaration":
                name_node = node.child_by_field_name("name")
                name = name_node.text.decode() if name_node else "<unknown>"

                body = node.child_by_field_name("body")
                params_node = node.child_by_field_name("parameters")

                functions.append(self.build_function_metrics(
                    node, name, name, file_path, body,
                    _count_params(params_node) if params_node else 0,
                ))

            elif node.type == "method_declaration":
                name_node = node.child_by_field_name("name")
                name = name_node.text.decode() if name_node else "<unknown>"

                receiver = _extract_receiver_type(node)
                qualified = f"{receiver}.{name}" if receiver else name
                body = node.child_by_field_name("body")
                params_node = node.child_by_field_name("parameters")

                functions.append(self.build_function_metrics(
                    node, name, qualified, file_path, body,
                    _count_params(params_node) if params_node else 0,
                ))

        return functions

    def collect_classes(self, tree, file_path: str, source_bytes: bytes,
                        functions: List[FunctionMetrics]) -> List[ClassMetrics]:
        """Group Go methods by their receiver type into ClassMetrics."""
        from collections import defaultdict
        type_methods = defaultdict(list)
        type_lines = {}

        for fn in functions:
            # qualified_name like "MyType.Method" indicates a method
            if '.' in fn.qualified_name:
                type_name = fn.qualified_name.rsplit('.', 1)[0]
                type_methods[type_name].append(fn)
                if type_name not in type_lines:
                    type_lines[type_name] = (fn.line, fn.end_line)
                else:
                    prev = type_lines[type_name]
                    type_lines[type_name] = (min(prev[0], fn.line), max(prev[1], fn.end_line))

        classes = []
        for type_name, methods in type_methods.items():
            lines = type_lines[type_name]
            classes.append(ClassMetrics(
                name=type_name,
                file_path=file_path,
                line=lines[0],
                end_line=lines[1],
                methods=methods,
            ))
        return classes


def _extract_receiver_type(method_node) -> str:
    """Extract the receiver type name from a Go method_declaration."""
    for child in method_node.children:
        if child.type == "parameter_list":
            for param in child.children:
                if param.type == "parameter_declaration":
                    for tc in param.children:
                        if tc.type == "type_identifier":
                            return tc.text.decode()
                        if tc.type == "pointer_type":
                            for inner in tc.children:
                                if inner.type == "type_identifier":
                                    return inner.text.decode()
            break
    return ""


def _count_params(param_list_node) -> int:
    """Count parameters in a Go parameter_list node."""
    count = 0
    for child in param_list_node.children:
        if child.type == "parameter_declaration":
            ids = [c for c in child.children if c.type == "identifier"]
            count += max(len(ids), 1)
        elif child.type == "variadic_parameter_declaration":
            count += 1
    return count


# Singleton instance
_parser = GoParser()


def _ensure_tree_sitter():
    if GO_LANGUAGE is None:
        raise ImportError(
            "Go support requires tree-sitter-go. "
            "Install with: pip install complexity-accounting[go]"
        )


# ---------------------------------------------------------------------------
# Public API (backward-compatible)
# ---------------------------------------------------------------------------

def count_go_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for Go source."""
    return _parser.count_lines(source)


def scan_go_file(file_path: str) -> FileMetrics:
    """Scan a single Go file and return its metrics."""
    return _parser.scan_file(file_path)
