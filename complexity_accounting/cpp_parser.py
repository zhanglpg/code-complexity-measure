"""
C/C++ complexity parser using tree-sitter.

Computes cognitive and cyclomatic complexity for C/C++ source files,
producing the same FunctionMetrics/FileMetrics as the Python scanner.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .scanner import FunctionMetrics, FileMetrics, compute_mi
from .base_parser import TreeSitterParser

try:
    import tree_sitter as ts
    import tree_sitter_cpp as tscpp

    CPP_LANGUAGE = ts.Language(tscpp.language())
except ImportError:
    CPP_LANGUAGE = None


class CppParser(TreeSitterParser):
    language = CPP_LANGUAGE
    language_name = "c/c++"
    install_extra = "cpp"

    # Cognitive config
    if_type = "if_statement"
    loop_types = frozenset({"for_statement", "for_range_loop", "while_statement", "do_statement"})
    switch_types = frozenset({"switch_statement"})
    catch_types = frozenset({"catch_clause"})
    body_types = frozenset({"compound_statement"})
    else_clause_types = frozenset({"else_clause"})

    switch_body_types = frozenset({"compound_statement"})
    case_types = frozenset({"case_statement"})

    bool_op_types = frozenset({"&&", "||"})
    break_types = frozenset({"break_statement", "continue_statement"})
    extra_increment_types = frozenset({"conditional_expression"})
    lambda_types = frozenset({"lambda_expression"})

    # Cyclomatic config
    cyclomatic_node_types = frozenset({
        "if_statement", "for_statement", "for_range_loop",
        "while_statement", "do_statement", "case_statement",
        "catch_clause", "conditional_expression",
    })

    def is_else_if(self, node) -> bool:
        return node.parent and node.parent.type == "else_clause"

    def collect_functions(self, tree, file_path: str, source_bytes: bytes) -> List[FunctionMetrics]:
        functions = []

        def visit(node, scope_stack):
            if node.type == "namespace_definition":
                name_node = None
                for child in node.children:
                    if child.type == "namespace_identifier":
                        name_node = child
                        break
                ns_name = name_node.text.decode() if name_node else "<anonymous>"
                for child in node.children:
                    if child.type == "declaration_list":
                        for decl_child in child.children:
                            visit(decl_child, scope_stack + [ns_name])
                return

            if node.type in ("class_specifier", "struct_specifier"):
                name_node = None
                for child in node.children:
                    if child.type == "type_identifier":
                        name_node = child
                        break
                class_name = name_node.text.decode() if name_node else "<anonymous>"
                for child in node.children:
                    if child.type == "field_declaration_list":
                        for field_child in child.children:
                            visit(field_child, scope_stack + [class_name])
                return

            if node.type == "template_declaration":
                for child in node.children:
                    if child.type in ("function_definition", "class_specifier", "struct_specifier"):
                        visit(child, scope_stack)
                return

            if node.type == "function_definition":
                name = _get_function_name(node)
                qualified = f"{'.'.join(scope_stack)}.{name}" if scope_stack else name

                body = node.child_by_field_name("body")

                functions.append(self.build_function_metrics(
                    node, name, qualified, file_path, body,
                    _count_params(node),
                ))
                return

            for child in node.children:
                visit(child, scope_stack)

        visit(tree.root_node, [])
        return functions


def _get_function_name(func_node) -> str:
    """Extract the function name from a function_definition node."""
    declarator = func_node.child_by_field_name("declarator")
    if declarator is None:
        return "<unknown>"
    return _extract_name_from_declarator(declarator)


def _extract_name_from_declarator(declarator) -> str:
    """Recursively extract the name from a declarator node."""
    if declarator.type == "function_declarator":
        for child in declarator.children:
            if child.type == "identifier":
                return child.text.decode()
            if child.type == "field_identifier":
                return child.text.decode()
            if child.type == "destructor_name":
                return "~" + child.children[1].text.decode() if len(child.children) > 1 else child.text.decode()
            if child.type == "qualified_identifier":
                return child.text.decode()
        return "<unknown>"
    if declarator.type == "reference_declarator":
        for child in declarator.children:
            if child.type == "function_declarator":
                return _extract_name_from_declarator(child)
    return "<unknown>"


def _count_params(func_node) -> int:
    """Count parameters in a C/C++ function definition."""
    declarator = func_node.child_by_field_name("declarator")
    if declarator is None:
        return 0

    param_list = None
    if declarator.type == "function_declarator":
        param_list = declarator.child_by_field_name("parameters")
    elif declarator.type == "reference_declarator":
        for child in declarator.children:
            if child.type == "function_declarator":
                param_list = child.child_by_field_name("parameters")
                break

    if param_list is None:
        return 0

    count = 0
    for child in param_list.children:
        if child.type in ("parameter_declaration", "optional_parameter_declaration"):
            count += 1
        elif child.type == "variadic_parameter_declaration":
            count += 1
    return count


# Singleton instance
_parser = CppParser()


def _ensure_tree_sitter():
    if CPP_LANGUAGE is None:
        raise ImportError(
            "C/C++ support requires tree-sitter-cpp. "
            "Install with: pip install complexity-accounting[cpp]"
        )


# ---------------------------------------------------------------------------
# Public API (backward-compatible)
# ---------------------------------------------------------------------------

def count_cpp_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for C/C++ source."""
    return _parser.count_lines(source)


def scan_cpp_file(file_path: str) -> FileMetrics:
    """Scan a single C/C++ file and return its metrics."""
    return _parser.scan_file(file_path)
