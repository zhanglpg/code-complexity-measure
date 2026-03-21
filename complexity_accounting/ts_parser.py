"""
TypeScript complexity parser using tree-sitter.

Computes cognitive and cyclomatic complexity for TypeScript source files,
producing the same FunctionMetrics/FileMetrics as the Python scanner.
Supports both .ts and .tsx files.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .scanner import FunctionMetrics, FileMetrics, compute_mi

try:
    import tree_sitter as ts
    import tree_sitter_typescript as tsts

    TS_LANGUAGE = ts.Language(tsts.language_typescript())
    TSX_LANGUAGE = ts.Language(tsts.language_tsx())
except ImportError:
    TS_LANGUAGE = None
    TSX_LANGUAGE = None


def _ensure_tree_sitter():
    if TS_LANGUAGE is None:
        raise ImportError(
            "TypeScript support requires tree-sitter-typescript. "
            "Install with: pip install complexity-accounting[ts]"
        )


# ---------------------------------------------------------------------------
# Cognitive Complexity for TypeScript
# ---------------------------------------------------------------------------

def _compute_cognitive_complexity(node) -> tuple:
    """
    Compute cognitive complexity for a TypeScript function body.

    Returns (complexity, max_nesting).
    """
    complexity = 0
    max_nesting = 0

    def walk(n, nesting, parent_bool_op=None):
        nonlocal complexity, max_nesting

        if n.type == "if_statement":
            # Check if this is an else-if (this if is the alternative of a parent if)
            is_else_if = (
                n.parent
                and n.parent.type == "else_clause"
                and n.parent.parent
                and n.parent.parent.type == "if_statement"
            )

            if is_else_if:
                # else-if: +1 but no nesting increment (continuation of chain)
                complexity += 1
                for child in n.children:
                    walk(child, nesting)
            else:
                complexity += 1 + nesting
                max_nesting = max(max_nesting, nesting + 1)
                for child in n.children:
                    if child.type == "statement_block" and child == n.child_by_field_name("consequence"):
                        walk(child, nesting + 1)
                    elif child.type == "else_clause":
                        # Check if the else clause contains an if (else-if chain)
                        for ec_child in child.children:
                            if ec_child.type == "if_statement":
                                walk(ec_child, nesting)
                            elif ec_child.type == "statement_block":
                                walk(ec_child, nesting + 1)
                            else:
                                walk(ec_child, nesting)
                    else:
                        walk(child, nesting)
            return

        if n.type == "for_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "statement_block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "for_in_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "statement_block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "while_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "statement_block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "do_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "statement_block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        if n.type == "switch_statement":
            complexity += 1 + nesting
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "switch_body":
                    for case_child in child.children:
                        if case_child.type in ("switch_case", "switch_default"):
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
                if child.type == "statement_block":
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
            if op_node and op_node.type in ("&&", "||", "??"):
                if op_node.type != parent_bool_op:
                    complexity += 1
                for child in n.children:
                    walk(child, nesting, parent_bool_op=op_node.type)
                return

        if n.type == "break_statement":
            complexity += 1
            return

        if n.type == "continue_statement":
            complexity += 1
            return

        if n.type == "arrow_function":
            max_nesting = max(max_nesting, nesting + 1)
            for child in n.children:
                if child.type == "statement_block":
                    walk(child, nesting + 1)
                else:
                    walk(child, nesting)
            return

        for child in n.children:
            walk(child, nesting)

    walk(node, 0)
    return complexity, max_nesting


# ---------------------------------------------------------------------------
# Cyclomatic Complexity for TypeScript
# ---------------------------------------------------------------------------

def _compute_cyclomatic_complexity(node) -> int:
    """Compute McCabe cyclomatic complexity for a TypeScript function body. Baseline = 1."""
    complexity = 1

    def walk(n):
        nonlocal complexity

        if n.type == "if_statement":
            complexity += 1
        elif n.type == "for_statement":
            complexity += 1
        elif n.type == "for_in_statement":
            complexity += 1
        elif n.type == "while_statement":
            complexity += 1
        elif n.type == "do_statement":
            complexity += 1
        elif n.type == "switch_case":
            complexity += 1
        elif n.type == "catch_clause":
            complexity += 1
        elif n.type == "binary_expression":
            op_node = n.child_by_field_name("operator")
            if op_node and op_node.type in ("&&", "||", "??"):
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
    """Count parameters in a TypeScript formal_parameters node."""
    count = 0
    for child in formal_params_node.children:
        if child.type in (
            "required_parameter",
            "optional_parameter",
            "rest_pattern",
            # JS-style nodes that may appear in some contexts
            "identifier",
            "assignment_pattern",
            "array_pattern",
            "object_pattern",
        ):
            count += 1
    return count


def _collect_functions(tree, file_path: str, source: bytes) -> List[FunctionMetrics]:
    """Extract function metrics from a TypeScript AST."""
    functions = []

    def visit(node, class_stack):
        # Handle export statements — unwrap and visit the declaration inside
        if node.type == "export_statement":
            for child in node.children:
                visit(child, class_stack)
            return

        # Skip TypeScript-specific declarations that don't contain executable code
        if node.type in (
            "interface_declaration",
            "type_alias_declaration",
            "enum_declaration",
            "abstract_method_signature",
        ):
            return

        if node.type in ("class_declaration", "abstract_class_declaration"):
            name_node = node.child_by_field_name("name")
            class_name = name_node.text.decode() if name_node else "<unknown>"
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    visit(child, class_stack + [class_name])
            return

        if node.type == "method_definition":
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode() if name_node else "<unknown>"

            qualified = f"{'.'.join(class_stack)}.{name}" if class_stack else name

            body = node.child_by_field_name("body")
            params_node = node.child_by_field_name("parameters")

            cog, max_nest = _compute_cognitive_complexity(body) if body else (0, 0)
            cyc = _compute_cyclomatic_complexity(body) if body else 1

            nloc = node.end_point[0] - node.start_point[0] + 1
            functions.append(FunctionMetrics(
                name=name,
                qualified_name=qualified,
                file_path=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                cognitive_complexity=cog,
                cyclomatic_complexity=cyc,
                nloc=nloc,
                params=_count_params(params_node) if params_node else 0,
                max_nesting=max_nest,
                maintainability_index=compute_mi(nloc, cyc),
            ))
            return

        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode() if name_node else "<unknown>"

            qualified = f"{'.'.join(class_stack)}.{name}" if class_stack else name

            body = node.child_by_field_name("body")
            params_node = node.child_by_field_name("parameters")

            cog, max_nest = _compute_cognitive_complexity(body) if body else (0, 0)
            cyc = _compute_cyclomatic_complexity(body) if body else 1

            nloc = node.end_point[0] - node.start_point[0] + 1
            functions.append(FunctionMetrics(
                name=name,
                qualified_name=qualified,
                file_path=file_path,
                line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                cognitive_complexity=cog,
                cyclomatic_complexity=cyc,
                nloc=nloc,
                params=_count_params(params_node) if params_node else 0,
                max_nesting=max_nest,
                maintainability_index=compute_mi(nloc, cyc),
            ))
            return

        # Variable declarations with arrow functions or function expressions
        if node.type in ("lexical_declaration", "variable_declaration"):
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    value_node = child.child_by_field_name("value")
                    if value_node and value_node.type in ("arrow_function", "function_expression"):
                        name = name_node.text.decode() if name_node else "<unknown>"
                        qualified = f"{'.'.join(class_stack)}.{name}" if class_stack else name

                        body = value_node.child_by_field_name("body")
                        params_node = value_node.child_by_field_name("parameters")

                        cog, max_nest = _compute_cognitive_complexity(body) if body else (0, 0)
                        cyc = _compute_cyclomatic_complexity(body) if body else 1

                        nloc = child.end_point[0] - child.start_point[0] + 1
                        functions.append(FunctionMetrics(
                            name=name,
                            qualified_name=qualified,
                            file_path=file_path,
                            line=child.start_point[0] + 1,
                            end_line=child.end_point[0] + 1,
                            cognitive_complexity=cog,
                            cyclomatic_complexity=cyc,
                            nloc=nloc,
                            params=_count_params(params_node) if params_node else 0,
                            max_nesting=max_nest,
                            maintainability_index=compute_mi(nloc, cyc),
                        ))
            return

        # Recurse into other nodes (e.g., program level)
        for child in node.children:
            visit(child, class_stack)

    visit(tree.root_node, [])
    return functions


# ---------------------------------------------------------------------------
# Line counting for TypeScript
# ---------------------------------------------------------------------------

def count_ts_lines(source: str) -> tuple:
    """Returns (total, code, comment, blank) line counts for TypeScript source."""
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

def scan_ts_file(file_path: str) -> FileMetrics:
    """Scan a single TypeScript file and return its metrics."""
    _ensure_tree_sitter()

    path = Path(file_path)
    source = path.read_text(encoding="utf-8", errors="replace")
    source_bytes = source.encode("utf-8")

    total, code, comment_lines, blank = count_ts_lines(source)

    # Use TSX grammar for .tsx files, TypeScript grammar for all others
    language = TSX_LANGUAGE if path.suffix == ".tsx" else TS_LANGUAGE
    parser = ts.Parser(language)
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
