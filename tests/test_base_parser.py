"""Tests for base_parser.py — tests count_lines and ensure_available without tree-sitter."""
import pytest

from complexity_accounting.base_parser import TreeSitterParser


class MinimalParser(TreeSitterParser):
    """Minimal subclass for testing non-tree-sitter methods."""
    language = None
    language_name = "test"
    install_extra = "test"


# ---------------------------------------------------------------------------
# ensure_available
# ---------------------------------------------------------------------------

def test_ensure_available_raises_when_no_language():
    parser = MinimalParser()
    with pytest.raises(ImportError) as exc_info:
        parser.ensure_available()
    assert "tree-sitter-test" in str(exc_info.value)
    assert "pip install" in str(exc_info.value)


# ---------------------------------------------------------------------------
# count_lines — C-style comments
# ---------------------------------------------------------------------------

def test_count_lines_empty():
    parser = MinimalParser()
    total, code, comment, blank = parser.count_lines("")
    assert total == 0
    assert code == 0
    assert comment == 0
    assert blank == 0


def test_count_lines_code_only():
    parser = MinimalParser()
    source = "int x = 1;\nreturn x;"
    total, code, comment, blank = parser.count_lines(source)
    assert total == 2
    assert code == 2
    assert comment == 0
    assert blank == 0


def test_count_lines_blank_lines():
    parser = MinimalParser()
    source = "int x;\n\n\nreturn x;"
    total, code, comment, blank = parser.count_lines(source)
    assert total == 4
    assert code == 2
    assert comment == 0
    assert blank == 2


def test_count_lines_line_comments():
    parser = MinimalParser()
    source = "// comment\nint x;\n// another"
    total, code, comment, blank = parser.count_lines(source)
    assert total == 3
    assert code == 1
    assert comment == 2
    assert blank == 0


def test_count_lines_block_comment_single_line():
    parser = MinimalParser()
    source = "int x = /* inline */ 1;"
    total, code, comment, blank = parser.count_lines(source)
    assert total == 1
    assert code == 1
    assert comment == 0
    assert blank == 0


def test_count_lines_block_comment_multiline():
    parser = MinimalParser()
    source = "/* start\n   continued\n   end */\nint x;"
    total, code, comment, blank = parser.count_lines(source)
    assert total == 4
    assert code == 1
    assert comment == 3
    assert blank == 0


def test_count_lines_mixed():
    parser = MinimalParser()
    source = "// header\n\nint x = 1;\n/* block\ncomment */\nreturn x;\n"
    total, code, comment, blank = parser.count_lines(source)
    assert total == 6
    assert code == 2
    assert comment == 3
    assert blank == 1


# ---------------------------------------------------------------------------
# get_language (base implementation)
# ---------------------------------------------------------------------------

def test_get_language_returns_none():
    parser = MinimalParser()
    from pathlib import Path
    result = parser.get_language(Path("test.cpp"))
    assert result is None


# ---------------------------------------------------------------------------
# Class attributes
# ---------------------------------------------------------------------------

def test_default_comment_style():
    parser = MinimalParser()
    assert parser.line_comment_prefix == "//"
    assert parser.block_comment_start == "/*"
    assert parser.block_comment_end == "*/"


def test_default_body_types():
    parser = MinimalParser()
    assert "block" in parser.body_types


def test_default_bool_op_types():
    parser = MinimalParser()
    assert "&&" in parser.bool_op_types
    assert "||" in parser.bool_op_types
