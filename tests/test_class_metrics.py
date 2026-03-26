"""Tests for class-level metrics (WMC, method count, total complexity)."""
import textwrap
import tempfile
import os

import pytest

from complexity_accounting.scanner import scan_file, ClassMetrics
from conftest import (
    requires_java, requires_ts, requires_js, requires_go, requires_rust, requires_cpp,
)


def _write_temp(source: str, suffix: str = ".py") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


# ── Python ──────────────────────────────────────────────────────────────

def test_python_class_metrics():
    path = _write_temp("""
        class Calculator:
            def add(self, a, b):
                return a + b

            def complex_calc(self, x, y):
                if x > 0:
                    if y > 0:
                        return x + y
                return 0
    """)
    try:
        fm = scan_file(path)
        assert len(fm.classes) == 1
        cls = fm.classes[0]
        assert cls.name == "Calculator"
        assert cls.method_count == 2
        assert cls.wmc >= 2  # at least baseline cyclomatic
        assert cls.total_cognitive >= 3  # complex_calc has nested ifs
    finally:
        os.unlink(path)


def test_python_multiple_classes():
    path = _write_temp("""
        class A:
            def foo(self):
                pass

        class B:
            def bar(self):
                if True:
                    pass

            def baz(self):
                pass
    """)
    try:
        fm = scan_file(path)
        assert len(fm.classes) == 2
        names = [c.name for c in fm.classes]
        assert "A" in names
        assert "B" in names
        b_cls = next(c for c in fm.classes if c.name == "B")
        assert b_cls.method_count == 2
    finally:
        os.unlink(path)


def test_python_no_classes():
    path = _write_temp("""
        def standalone():
            return 42
    """)
    try:
        fm = scan_file(path)
        assert len(fm.classes) == 0
    finally:
        os.unlink(path)


def test_python_class_in_json_output():
    path = _write_temp("""
        class Greeter:
            def greet(self, name):
                return f"Hello, {name}"
    """)
    try:
        from complexity_accounting.scanner import ScanResult
        fm = scan_file(path)
        result = ScanResult(files=[fm])
        data = result.to_dict()
        file_data = data["files"][0]
        assert "classes" in file_data
        assert len(file_data["classes"]) == 1
        cls_data = file_data["classes"][0]
        assert cls_data["name"] == "Greeter"
        assert cls_data["method_count"] == 1
        assert "wmc" in cls_data
        assert "total_cognitive" in cls_data
        assert "avg_method_complexity" in cls_data
    finally:
        os.unlink(path)


def test_class_metrics_properties():
    """Test ClassMetrics dataclass properties."""
    from complexity_accounting.scanner import FunctionMetrics
    methods = [
        FunctionMetrics(
            name="foo", qualified_name="A.foo", file_path="test.py",
            line=1, end_line=3, cognitive_complexity=5, cyclomatic_complexity=3,
        ),
        FunctionMetrics(
            name="bar", qualified_name="A.bar", file_path="test.py",
            line=4, end_line=6, cognitive_complexity=10, cyclomatic_complexity=4,
        ),
    ]
    cls = ClassMetrics(
        name="A", file_path="test.py", line=1, end_line=6, methods=methods,
    )
    assert cls.method_count == 2
    assert cls.wmc == 7  # 3 + 4
    assert cls.total_cognitive == 15  # 5 + 10
    assert cls.total_cyclomatic == 7
    assert cls.avg_method_complexity == 7.5  # 15 / 2


def test_class_metrics_empty():
    cls = ClassMetrics(name="Empty", file_path="test.py", line=1, end_line=1)
    assert cls.method_count == 0
    assert cls.wmc == 0
    assert cls.total_cognitive == 0
    assert cls.avg_method_complexity == 0.0


# ── Java ────────────────────────────────────────────────────────────────

@requires_java
def test_java_class_metrics():
    path = _write_temp("""
        public class MyService {
            public void process(int x) {
                if (x > 0) {
                    System.out.println(x);
                }
            }

            public int compute(int a, int b) {
                return a + b;
            }
        }
    """, suffix=".java")
    try:
        fm = scan_file(path)
        assert len(fm.classes) == 1
        cls = fm.classes[0]
        assert cls.name == "MyService"
        assert cls.method_count == 2
    finally:
        os.unlink(path)


# ── TypeScript ──────────────────────────────────────────────────────────

@requires_ts
def test_ts_class_metrics():
    path = _write_temp("""
        class UserService {
            getUser(id: number): string {
                if (id > 0) {
                    return "user";
                }
                return "unknown";
            }

            deleteUser(id: number): void {
                console.log(id);
            }
        }
    """, suffix=".ts")
    try:
        fm = scan_file(path)
        assert len(fm.classes) == 1
        cls = fm.classes[0]
        assert cls.name == "UserService"
        assert cls.method_count == 2
    finally:
        os.unlink(path)


# ── JavaScript ──────────────────────────────────────────────────────────

@requires_js
def test_js_class_metrics():
    path = _write_temp("""
        class Animal {
            speak() {
                return "...";
            }

            eat(food) {
                if (food) {
                    return true;
                }
                return false;
            }
        }
    """, suffix=".js")
    try:
        fm = scan_file(path)
        assert len(fm.classes) == 1
        cls = fm.classes[0]
        assert cls.name == "Animal"
        assert cls.method_count == 2
    finally:
        os.unlink(path)


# ── Go ──────────────────────────────────────────────────────────────────

@requires_go
def test_go_class_metrics():
    """Go groups methods by receiver type."""
    path = _write_temp("""
        package main

        type Server struct {
            port int
        }

        func (s *Server) Start() {
            if s.port > 0 {
                return
            }
        }

        func (s *Server) Stop() {
            return
        }

        func standalone() {
            return
        }
    """, suffix=".go")
    try:
        fm = scan_file(path)
        assert len(fm.classes) == 1
        cls = fm.classes[0]
        assert cls.name == "Server"
        assert cls.method_count == 2
    finally:
        os.unlink(path)


# ── Rust ────────────────────────────────────────────────────────────────

@requires_rust
def test_rust_class_metrics():
    path = _write_temp("""
        struct Counter {
            count: i32,
        }

        impl Counter {
            fn new() -> Counter {
                Counter { count: 0 }
            }

            fn increment(&mut self) {
                if self.count < 100 {
                    self.count += 1;
                }
            }
        }
    """, suffix=".rs")
    try:
        fm = scan_file(path)
        assert len(fm.classes) >= 1
        # Find the impl Counter class
        counter_cls = next((c for c in fm.classes if c.name == "Counter"), None)
        assert counter_cls is not None
        assert counter_cls.method_count == 2
    finally:
        os.unlink(path)


# ── C++ ─────────────────────────────────────────────────────────────────

@requires_cpp
def test_cpp_class_metrics():
    path = _write_temp("""
        class Widget {
        public:
            void draw() {
                if (visible) {
                    render();
                }
            }

            void update() {
                return;
            }
        private:
            bool visible;
        };
    """, suffix=".cpp")
    try:
        fm = scan_file(path)
        assert len(fm.classes) == 1
        cls = fm.classes[0]
        assert cls.name == "Widget"
        assert cls.method_count == 2
    finally:
        os.unlink(path)
