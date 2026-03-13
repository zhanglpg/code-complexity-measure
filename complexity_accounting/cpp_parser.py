"""
C/C++ complexity parser using tree-sitter.

Computes cognitive and cyclomatic complexity for C/C++ source files,
producing the same FunctionMetrics/FileMetrics as the Python scanner.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .scanner import FunctionMetrics, FileMetrics

try:
    import tree_sitter as ts
    import tree_sitter_cpp as tscpp

    CPP_LANGUAGE = ts.Language(tscpp.language())
except ImportError:
    CPP_LANGUAGE = None


def _ensure_tree_sitter():
    if CPP_LANGUAGE is None:
        raise ImportError(
            "C/C++ support requires tree-sitter-cpp. "
            "Install with: pip install complexity-accounting[cpp]"
        )


# ---------------------------------------------------------------------------
# Cognitive Complexity for C/C++
# ---------------------------------------------------------------------------

def _compute_cognitive_complexity(node) -> tuple:
    """
    Compute cognitive complexity for a C/C++ function body.

    Returns (complexity, max_nesting).
    """
    complexity = 0
    max_nesting = 0

    def walk(n, nesting):
        nonlocal complexity, max_nesting

        if n.type == "if_statement":
            # Check if this is an else-if (parent is else_clause)
            is_else_if = n.parent and n.parent.type == "else_clause"

            if is_else_if:
                # else-if: +1 but no nesting increment (continuation of chain)
                complexity += 1
                for child in n.children:
                    if child.type == "compound_statement":
                        walk(child, nesting)
                    elif child.type == "else_clause":
                        walk(child, nesting)
                    else:
                        walk(child, nesting)
            else:
                complexity += 1 + nesting
                max_nesting = max(max_nesting, nesting + 1)
                for child in n.children:
                    if child.type == "compound_statement":
                        walk(child, nesting + 1)
                    elif child.type == "else_clause":
                        walk(child, nesting)
                    else:
                        walk(child, nesting)
            return

        if n.type in ("for_statement", "for_range_loop"):
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "compound_statement":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "while_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "compound_statement":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "do_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "compound_statement":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "switch_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "compound_statement":
                    # The switch body contains case_statement nodes
                    for case_child in child.children:
                        if case_child.type == "case_statement":
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
                if child.type == "compound_statement":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "conditional_expression":
            complexity += 1
            for child in n.children:
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

        if n.type == "break_statement":
            complexity += 1
            return

        if n.type == "continue_statement":
            complexity += 1
            return

        if n.type == "lambda_expression":
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "compound_statement":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        for child in n.children:
            walk(child, nesting)

    walk(node, 0)
    return complexity, max_nesting


# ---------------------------------------------------------------------------
# Cyclomatic Complexity for C/C++
# ---------------------------------------------------------------------------

def _compute_cyclomatic_complexity(node) -> int:
    """Compute McCabe cyclomatic complexity for a C/C++ function body. Baseline = 1."""
    complexity = 1

    def walk(n):
        nonlocal complexity

        if n.type == "if_statement":
            complexity += 1
        elif n.type in ("for_statement", "for_range_loop"):
            complexity += 1
        elif n.type == "while_statement":
            complexity += 1
        elif n.type == "do_statement":
            complexity += 1
        elif n.type == "case_statement":
            complexity += 1
        elif n.type == "catch_clause":
            complexity += 1
        elif n.type == "binary_expression":
            for child in n.children:
                if child.type in ("&&", "||"):
                    complexity += 1
                    break
        elif n.type == "conditional_expression":
            complexity += 1

        for child in n.children:
            walk(child)

    walk(node)
    return complexity


# ---------------------------------------------------------------------------
# Function collection
# ---------------------------------------------------------------------------

def _get_function_name(func_node) -> str:
    """Extract the function name from a function_definition node."""
    declarator = func_node.child_by_field_name("declarator")
    if declarator is None:
        return "<unknown>"
    return _extract_name_from_declarator(declarator)


def _extract_name_from_declarator(declarator) -> str:
    """Recursively extract the name from a declarator node."""
    if declarator.type == "function_declarator":
        # The first child that is an identifier or field_identifier or destructor_name
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

    # Find the parameter_list inside the function_declarator
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


def _collect_functions(tree, file_path: str, source: bytes) -> List[FunctionMetrics]:
    """Extract function metrics from a C/C++ AST."""
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
            # Unwrap template to find inner function_definition or class
            for child in node.children:
                if child.type in ("function_definition", "class_specifier", "struct_specifier"):
                    visit(child, scope_stack)
            return

        if node.type == "function_definition":
            name = _get_function_name(node)
            qualified = f"{'.'.join(scope_stack)}.{name}" if scope_stack else name

            body = node.child_by_field_name("body")

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
                params=_count_params(node),
                max_nesting=max_nest,
            ))
            return

        # Recurse into other nodes
        for child in node.children:
            visit(child, scope_stack)

    visit(tree.root_node, [])
    return functions


# ---------------------------------------------------------------------------
# Line counting for C/C++
# ---------------------------------------------------------------------------

def count_cpp_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for C/C++ source."""
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

def scan_cpp_file(file_path: str) -> FileMetrics:
    """Scan a single C/C++ file and return its metrics."""
    _ensure_tree_sitter()

    path = Path(file_path)
    source = path.read_text(encoding="utf-8", errors="replace")
    source_bytes = source.encode("utf-8")

    total, code, comment_lines, blank = count_cpp_lines(source)

    parser = ts.Parser(CPP_LANGUAGE)
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
