"""Tests for Halstead complexity metrics."""
import textwrap
import tempfile
import os
import math
from unittest.mock import MagicMock

import pytest

from conftest import requires_go, requires_java

from complexity_accounting.halstead import (
    HalsteadMetrics,
    compute_halstead_python,
    compute_halstead_tree_sitter,
    _TS_OPERATOR_TYPES,
    _TS_OPERATOR_NODE_TYPES,
    _TS_OPERAND_TYPES,
)
from complexity_accounting.scanner import scan_file, compute_mi


def _write_temp(source: str, suffix: str = ".py") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


# ── HalsteadMetrics properties ──────────────────────────────────────────


def test_halstead_metrics_basic():
    h = HalsteadMetrics(n1=5, n2=3, N1=10, N2=8)
    assert h.vocabulary == 8
    assert h.length == 18
    assert h.volume == 18 * math.log2(8)
    assert h.difficulty == (5 / 2.0) * (8 / 3.0)
    assert h.effort == h.difficulty * h.volume


def test_halstead_metrics_zero():
    h = HalsteadMetrics(n1=0, n2=0, N1=0, N2=0)
    assert h.vocabulary == 0
    assert h.length == 0
    assert h.volume == 0.0
    assert h.difficulty == 0.0
    assert h.effort == 0.0


def test_halstead_metrics_no_operands():
    h = HalsteadMetrics(n1=3, n2=0, N1=5, N2=0)
    assert h.vocabulary == 3
    assert h.length == 5
    assert h.difficulty == 0.0
    assert h.effort == 0.0


def test_halstead_metrics_volume_formula():
    """Volume = N * log2(n) where N = length, n = vocabulary."""
    h = HalsteadMetrics(n1=4, n2=6, N1=20, N2=30)
    expected_vocab = 10
    expected_length = 50
    expected_volume = 50 * math.log2(10)
    assert h.vocabulary == expected_vocab
    assert h.length == expected_length
    assert abs(h.volume - expected_volume) < 1e-10


def test_halstead_metrics_difficulty_formula():
    """Difficulty = (n1/2) * (N2/n2)."""
    h = HalsteadMetrics(n1=10, n2=5, N1=20, N2=15)
    expected_difficulty = (10 / 2.0) * (15 / 5.0)
    assert h.difficulty == expected_difficulty
    assert h.difficulty == 15.0


def test_halstead_metrics_effort_formula():
    """Effort = Difficulty * Volume."""
    h = HalsteadMetrics(n1=4, n2=2, N1=8, N2=6)
    expected_difficulty = (4 / 2.0) * (6 / 2.0)
    expected_volume = 14 * math.log2(6)
    expected_effort = expected_difficulty * expected_volume
    assert abs(h.effort - expected_effort) < 1e-10
    assert h.effort == h.difficulty * h.volume


def test_halstead_metrics_vocabulary_is_sum_of_distinct():
    h = HalsteadMetrics(n1=7, n2=13, N1=50, N2=80)
    assert h.vocabulary == 20
    assert h.vocabulary == h.n1 + h.n2


def test_halstead_metrics_length_is_sum_of_total():
    h = HalsteadMetrics(n1=7, n2=13, N1=50, N2=80)
    assert h.length == 130
    assert h.length == h.N1 + h.N2


def test_halstead_metrics_single_operator():
    """Metrics with exactly one distinct operator and one distinct operand."""
    h = HalsteadMetrics(n1=1, n2=1, N1=1, N2=1)
    assert h.vocabulary == 2
    assert h.length == 2
    assert h.volume == 2 * math.log2(2)
    assert h.volume == 2.0
    assert h.difficulty == 0.5
    assert h.effort == 1.0


# ── Python Halstead ─────────────────────────────────────────────────────


def test_python_halstead_simple():
    source = textwrap.dedent("""
        def add(a, b):
            return a + b
    """)
    h = compute_halstead_python(source)
    # def, return, + -> 3 distinct operators
    assert h.n1 == 3
    # a, b, add -> 3 distinct operands
    assert h.n2 == 3
    assert h.N1 == 3
    assert h.N2 == 5
    assert h.vocabulary == 6
    assert h.length == 8
    assert abs(h.volume - 8 * math.log2(6)) < 1e-10


def test_python_halstead_complex():
    source = textwrap.dedent("""
        def process(items):
            result = []
            for item in items:
                if item > 0:
                    result.append(item * 2)
            return result
    """)
    h = compute_halstead_python(source)
    # Operators: def, =, for, if, GreaterThan, ., (), Multiply, return -> 9 distinct
    assert h.n1 == 9
    # Operands: process, items, result, item, 0, 2, append -> 7 distinct
    assert h.n2 == 7
    assert h.N1 == 9
    assert h.N2 == 12
    assert h.vocabulary == 16
    assert h.length == 21
    assert h.volume == 21 * math.log2(16)
    assert h.volume == 84.0


def test_python_halstead_syntax_error():
    h = compute_halstead_python("def (broken ===")
    assert h.n1 == 0
    assert h.n2 == 0
    assert h.N1 == 0
    assert h.N2 == 0
    assert h.volume == 0.0
    assert h.difficulty == 0.0
    assert h.effort == 0.0


def test_python_halstead_empty_code():
    """Empty source code should produce zero metrics."""
    h = compute_halstead_python("")
    assert h.n1 == 0
    assert h.n2 == 0
    assert h.N1 == 0
    assert h.N2 == 0
    assert h.vocabulary == 0
    assert h.length == 0
    assert h.volume == 0.0


def test_python_halstead_single_expression():
    """A single assignment expression: x = 1 + 2."""
    h = compute_halstead_python("x = 1 + 2")
    # Operators: =, Add -> 2 distinct
    assert h.n1 == 2
    # Operands: x, 1, 2 -> 3 distinct
    assert h.n2 == 3
    assert h.N1 == 2
    assert h.N2 == 3
    assert h.vocabulary == 5
    assert h.length == 5
    assert abs(h.volume - 5 * math.log2(5)) < 1e-10


def test_python_halstead_only_operand():
    """Source with only an operand (a bare name), no operators."""
    h = compute_halstead_python("x")
    assert h.n1 == 0
    assert h.n2 == 1
    assert h.N1 == 0
    assert h.N2 == 1
    # vocabulary = 1, volume = 1 * log2(1) = 0
    assert h.vocabulary == 1
    assert h.volume == 0.0


def test_python_halstead_class_def():
    """Class definitions should count 'class' as an operator."""
    source = textwrap.dedent("""
        class Foo:
            pass
    """)
    h = compute_halstead_python(source)
    assert h.n1 >= 1  # at least 'class'
    assert h.n2 >= 1  # at least 'Foo'
    assert h.N1 >= 1
    assert h.N2 >= 1


def test_python_halstead_while_loop():
    """While loop counts 'while' as an operator."""
    source = textwrap.dedent("""
        x = 10
        while x > 0:
            x = x - 1
    """)
    h = compute_halstead_python(source)
    # Operators include: =, while, GreaterThan, Subtract
    assert h.n1 >= 4
    # Operands include: x, 10, 0, 1
    assert h.n2 >= 3
    assert h.volume > 0.0


def test_python_halstead_augmented_assignment():
    """Augmented assignment (+=) should be counted as operator."""
    source = "x = 0\nx += 1"
    h = compute_halstead_python(source)
    # Operators: =, AddAssign= -> at least 2 distinct
    assert h.n1 >= 2
    assert h.N1 >= 2


def test_python_halstead_comparison_operators():
    """Multiple comparison operators should each be counted."""
    source = textwrap.dedent("""
        a = 1
        b = 2
        c = a == b
        d = a != b
    """)
    h = compute_halstead_python(source)
    # Operators include: = (x4), Equal, NotEqual -> at least 3 distinct
    assert h.n1 >= 3
    assert h.N1 >= 6


# ── compute_halstead_tree_sitter with mock nodes ────────────────────────


def _make_mock_node(node_type, text=None, children=None):
    """Build a mock tree-sitter node for testing."""
    node = MagicMock()
    node.type = node_type
    node.text = text.encode() if text else None
    node.children = children or []
    return node


def test_tree_sitter_halstead_empty_tree():
    """A root node with no children yields zero metrics."""
    root = _make_mock_node("module", children=[])
    h = compute_halstead_tree_sitter(root)
    assert h.n1 == 0
    assert h.n2 == 0
    assert h.N1 == 0
    assert h.N2 == 0
    assert h.volume == 0.0


def test_tree_sitter_halstead_single_operator():
    """A tree with a single operator node."""
    op_node = _make_mock_node("+", text="+", children=[])
    root = _make_mock_node("expression", children=[op_node])
    h = compute_halstead_tree_sitter(root)
    assert h.n1 == 1
    assert h.n2 == 0
    assert h.N1 == 1
    assert h.N2 == 0


def test_tree_sitter_halstead_single_operand():
    """A tree with a single identifier operand."""
    id_node = _make_mock_node("identifier", text="foo", children=[])
    root = _make_mock_node("module", children=[id_node])
    h = compute_halstead_tree_sitter(root)
    assert h.n1 == 0
    assert h.n2 == 1
    assert h.N1 == 0
    assert h.N2 == 1


def test_tree_sitter_halstead_mixed():
    """A tree with operators and operands computes correct metrics."""
    # Build: x + y
    x_node = _make_mock_node("identifier", text="x", children=[])
    plus_node = _make_mock_node("+", text="+", children=[])
    y_node = _make_mock_node("identifier", text="y", children=[])
    expr = _make_mock_node("binary_expression", children=[x_node, plus_node, y_node])
    root = _make_mock_node("module", children=[expr])
    h = compute_halstead_tree_sitter(root)
    # 1 operator (+), 2 distinct operands (x, y)
    assert h.n1 == 1
    assert h.n2 == 2
    assert h.N1 == 1
    assert h.N2 == 2
    assert h.vocabulary == 3
    assert h.length == 3
    assert abs(h.volume - 3 * math.log2(3)) < 1e-10


def test_tree_sitter_halstead_repeated_operands():
    """Repeated operands: distinct count differs from total count."""
    x1 = _make_mock_node("identifier", text="x", children=[])
    x2 = _make_mock_node("identifier", text="x", children=[])
    plus = _make_mock_node("+", text="+", children=[])
    root = _make_mock_node("module", children=[x1, plus, x2])
    h = compute_halstead_tree_sitter(root)
    assert h.n1 == 1   # distinct operators: +
    assert h.n2 == 1   # distinct operands: x
    assert h.N1 == 1   # total operators
    assert h.N2 == 2   # total operands (x appears twice)
    assert h.vocabulary == 2
    assert h.length == 3


def test_tree_sitter_halstead_operator_node_types():
    """Node types in _TS_OPERATOR_NODE_TYPES are counted as operators."""
    if_node = _make_mock_node("if_statement", children=[])
    ret_node = _make_mock_node("return_statement", children=[])
    root = _make_mock_node("module", children=[if_node, ret_node])
    h = compute_halstead_tree_sitter(root)
    assert h.n1 == 2   # if_statement, return_statement
    assert h.n2 == 0
    assert h.N1 == 2
    assert h.N2 == 0


def test_tree_sitter_halstead_number_literal():
    """Number literals are counted as operands."""
    num = _make_mock_node("number_literal", text="42", children=[])
    root = _make_mock_node("module", children=[num])
    h = compute_halstead_tree_sitter(root)
    assert h.n1 == 0
    assert h.n2 == 1
    assert h.N1 == 0
    assert h.N2 == 1


def test_tree_sitter_halstead_operand_without_text():
    """If a node has no text, its type is used as the operand string."""
    node = _make_mock_node("identifier", text=None, children=[])
    root = _make_mock_node("module", children=[node])
    h = compute_halstead_tree_sitter(root)
    assert h.n2 == 1
    assert h.N2 == 1


def test_tree_sitter_operator_sets_are_disjoint():
    """Operator types and operand types should not overlap."""
    all_operators = _TS_OPERATOR_TYPES | _TS_OPERATOR_NODE_TYPES
    overlap = all_operators & _TS_OPERAND_TYPES
    assert overlap == set()


def test_tree_sitter_operator_sets_not_empty():
    """The operator/operand type sets should contain entries."""
    assert len(_TS_OPERATOR_TYPES) > 10
    assert len(_TS_OPERATOR_NODE_TYPES) > 10
    assert len(_TS_OPERAND_TYPES) > 5


# ── MI with Halstead ────────────────────────────────────────────────────


def test_mi_with_halstead_volume():
    """MI with Halstead Volume should use the full SEI formula."""
    mi_without = compute_mi(50, 5)
    mi_with = compute_mi(50, 5, halstead_volume=100.0)
    # Both should be in valid range
    assert 0 <= mi_without <= 100
    assert 0 <= mi_with <= 100
    # They should differ (different formulas)
    assert mi_without != mi_with


def test_mi_without_halstead_unchanged():
    """MI without Halstead should match the original formula."""
    mi = compute_mi(50, 5)
    expected = 171.0 - 21.4 * math.log(50) - 0.23 * 5
    expected = round(max(0.0, min(100.0, expected * 100.0 / 171.0)), 2)
    assert mi == expected


def test_mi_with_zero_halstead():
    """MI with zero or None Halstead should fall back to simplified formula."""
    mi_none = compute_mi(50, 5, halstead_volume=None)
    mi_zero = compute_mi(50, 5, halstead_volume=0.0)
    mi_neg = compute_mi(50, 5, halstead_volume=-1.0)
    mi_base = compute_mi(50, 5)
    assert mi_none == mi_base
    assert mi_zero == mi_base
    assert mi_neg == mi_base


# ── Integration: scan_file includes halstead_volume ─────────────────────


def test_python_scan_includes_halstead():
    path = _write_temp("""
        def calculate(x, y):
            result = x + y
            if result > 0:
                return result * 2
            return 0
    """)
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.halstead_volume is not None
        assert fn.halstead_volume > 0
    finally:
        os.unlink(path)


@requires_go
def test_go_scan_includes_halstead():
    path = _write_temp("""
        package main

        func compute(x int, y int) int {
            if x > y {
                return x + y
            }
            return 0
        }
    """, suffix=".go")
    try:
        fm = scan_file(path)
        fn = fm.functions[0]
        assert fn.halstead_volume is not None
        assert fn.halstead_volume > 0
    finally:
        os.unlink(path)


@requires_java
def test_java_scan_includes_halstead():
    path = _write_temp("""
        public class Calc {
            public int add(int a, int b) {
                return a + b;
            }
        }
    """, suffix=".java")
    try:
        fm = scan_file(path)
        assert len(fm.functions) >= 1
        fn = fm.functions[0]
        assert fn.halstead_volume is not None
        assert fn.halstead_volume > 0
    finally:
        os.unlink(path)
