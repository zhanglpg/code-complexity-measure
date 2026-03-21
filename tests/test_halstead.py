"""Tests for Halstead complexity metrics."""
import textwrap
import tempfile
import os
import math

from complexity_accounting.halstead import (
    HalsteadMetrics,
    compute_halstead_python,
    compute_halstead_tree_sitter,
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
    assert h.volume == 0.0
    assert h.difficulty == 0.0
    assert h.effort == 0.0


def test_halstead_metrics_no_operands():
    h = HalsteadMetrics(n1=3, n2=0, N1=5, N2=0)
    assert h.difficulty == 0.0


# ── Python Halstead ─────────────────────────────────────────────────────

def test_python_halstead_simple():
    source = textwrap.dedent("""
        def add(a, b):
            return a + b
    """)
    h = compute_halstead_python(source)
    assert h.n1 > 0  # at least def, return, +
    assert h.n2 > 0  # at least a, b
    assert h.volume > 0


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
    assert h.n1 >= 5  # def, =, for, if, >, ., (), return
    assert h.n2 >= 3  # items, result, item, 0, 2
    assert h.volume > 0


def test_python_halstead_syntax_error():
    h = compute_halstead_python("def (broken ===")
    assert h.volume == 0.0


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
