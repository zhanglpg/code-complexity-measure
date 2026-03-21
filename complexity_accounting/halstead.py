"""
Halstead complexity metrics.

Computes operator/operand counts for Halstead Volume, Difficulty, and Effort.
Used to improve Maintainability Index accuracy with the full SEI formula.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Set


@dataclass
class HalsteadMetrics:
    """Halstead complexity metrics for a code region."""
    n1: int  # distinct operators
    n2: int  # distinct operands
    N1: int  # total operators
    N2: int  # total operands

    @property
    def vocabulary(self) -> int:
        """n = n1 + n2"""
        return self.n1 + self.n2

    @property
    def length(self) -> int:
        """N = N1 + N2"""
        return self.N1 + self.N2

    @property
    def volume(self) -> float:
        """V = N * log2(n)"""
        n = self.vocabulary
        if n <= 0:
            return 0.0
        return self.length * math.log2(n)

    @property
    def difficulty(self) -> float:
        """D = (n1/2) * (N2/n2)"""
        if self.n2 <= 0:
            return 0.0
        return (self.n1 / 2.0) * (self.N2 / self.n2)

    @property
    def effort(self) -> float:
        """E = D * V"""
        return self.difficulty * self.volume


# ---------------------------------------------------------------------------
# Python (libcst) Halstead analysis
# ---------------------------------------------------------------------------

def compute_halstead_python(source: str) -> HalsteadMetrics:
    """Compute Halstead metrics for Python source code using libcst."""
    import libcst as cst

    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return HalsteadMetrics(n1=0, n2=0, N1=0, N2=0)

    operators: list = []
    operands: list = []

    class HalsteadVisitor(cst.CSTVisitor):

        # --- Operators ---

        def visit_BinaryOperation(self, node: cst.BinaryOperation):
            operators.append(type(node.operator).__name__)

        def visit_UnaryOperation(self, node: cst.UnaryOperation):
            operators.append(type(node.operator).__name__)

        def visit_BooleanOperation(self, node: cst.BooleanOperation):
            operators.append(type(node.operator).__name__)

        def visit_Comparison(self, node: cst.Comparison):
            for target in node.comparisons:
                operators.append(type(target.operator).__name__)

        def visit_AugAssign(self, node: cst.AugAssign):
            operators.append(type(node.operator).__name__ + "=")

        def visit_AssignTarget(self, node: cst.AssignTarget):
            operators.append("=")

        def visit_If(self, node: cst.If):
            operators.append("if")

        def visit_For(self, node: cst.For):
            operators.append("for")

        def visit_While(self, node: cst.While):
            operators.append("while")

        def visit_Return(self, node: cst.Return):
            operators.append("return")

        def visit_FunctionDef(self, node: cst.FunctionDef):
            operators.append("def")

        def visit_ClassDef(self, node: cst.ClassDef):
            operators.append("class")

        def visit_Call(self, node: cst.Call):
            operators.append("()")

        def visit_Subscript(self, node: cst.Subscript):
            operators.append("[]")

        def visit_Attribute(self, node: cst.Attribute):
            operators.append(".")

        def visit_Yield(self, node: cst.Yield):
            operators.append("yield")

        def visit_Raise(self, node: cst.Raise):
            operators.append("raise")

        def visit_Assert(self, node: cst.Assert):
            operators.append("assert")

        def visit_Del(self, node: cst.Del):
            operators.append("del")

        def visit_Import(self, node: cst.Import):
            operators.append("import")

        def visit_ImportFrom(self, node: cst.ImportFrom):
            operators.append("from")

        def visit_Try(self, node: cst.Try):
            operators.append("try")

        def visit_ExceptHandler(self, node: cst.ExceptHandler):
            operators.append("except")

        def visit_With(self, node: cst.With):
            operators.append("with")

        def visit_IfExp(self, node: cst.IfExp):
            operators.append("ternary")

        # --- Operands ---

        def visit_Name(self, node: cst.Name):
            if node.value not in ("True", "False", "None"):
                operands.append(node.value)
            else:
                operands.append(node.value)

        def visit_Integer(self, node: cst.Integer):
            operands.append(node.value)

        def visit_Float(self, node: cst.Float):
            operands.append(node.value)

        def visit_SimpleString(self, node: cst.SimpleString):
            operands.append(node.value)

        def visit_FormattedString(self, node: cst.FormattedString):
            operands.append("f-string")

        def visit_ConcatenatedString(self, node: cst.ConcatenatedString):
            operands.append("concat-string")

    visitor = HalsteadVisitor()
    wrapper = cst.metadata.MetadataWrapper(tree)
    wrapper.visit(visitor)

    distinct_operators: Set[str] = set(operators)
    distinct_operands: Set[str] = set(operands)

    return HalsteadMetrics(
        n1=len(distinct_operators),
        n2=len(distinct_operands),
        N1=len(operators),
        N2=len(operands),
    )


# ---------------------------------------------------------------------------
# Tree-sitter Halstead analysis (generic, works for all tree-sitter langs)
# ---------------------------------------------------------------------------

# Operator node types common across tree-sitter grammars
_TS_OPERATOR_TYPES = frozenset({
    # Arithmetic / bitwise
    "+", "-", "*", "/", "%", "**", "^", "&", "|", "~", "<<", ">>",
    # Comparison
    "==", "!=", "<", ">", "<=", ">=", "===", "!==",
    # Logical
    "&&", "||", "!", "not", "and", "or",
    # Assignment
    "=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=",
    # Other
    ".", "->", "::", "?", "=>",
})

_TS_OPERATOR_NODE_TYPES = frozenset({
    "if_statement", "if_expression", "for_statement", "for_expression",
    "enhanced_for_statement", "for_in_statement", "for_range_loop",
    "while_statement", "while_expression", "do_statement",
    "return_statement", "return_expression",
    "function_declaration", "function_definition", "function_item",
    "method_declaration", "method_definition", "constructor_declaration",
    "class_declaration", "class_specifier", "struct_specifier",
    "call_expression", "subscript_expression", "index_expression",
    "try_statement", "catch_clause", "throw_statement",
    "switch_statement", "switch_expression", "match_expression",
    "break_statement", "break_expression",
    "continue_statement", "continue_expression",
    "yield_expression", "go_statement", "defer_statement",
    "impl_item", "trait_item",
})

_TS_OPERAND_TYPES = frozenset({
    "identifier", "type_identifier", "field_identifier",
    "number_literal", "integer_literal", "float_literal", "decimal_integer_literal",
    "decimal_floating_point_literal", "hex_integer_literal",
    "string_literal", "interpreted_string_literal", "raw_string_literal",
    "template_string", "string_content", "string_fragment",
    "true", "false", "null_literal", "none", "nil",
    "character_literal", "char_literal",
})


def compute_halstead_tree_sitter(root_node) -> HalsteadMetrics:
    """Compute Halstead metrics from a tree-sitter parse tree node."""
    operators = []
    operands = []

    def walk(node):
        node_type = node.type

        if node_type in _TS_OPERATOR_TYPES or node_type in _TS_OPERATOR_NODE_TYPES:
            operators.append(node_type)
        elif node_type in _TS_OPERAND_TYPES:
            text = node.text.decode() if node.text else node_type
            operands.append(text)

        for child in node.children:
            walk(child)

    walk(root_node)

    return HalsteadMetrics(
        n1=len(set(operators)),
        n2=len(set(operands)),
        N1=len(operators),
        N2=len(operands),
    )
