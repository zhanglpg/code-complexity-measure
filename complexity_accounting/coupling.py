"""
Import coupling analysis.

Computes efferent coupling (fan-out) per file by analyzing imports.
Supports Python (via libcst) and Go, Java, JavaScript, TypeScript, Rust,
C/C++ (via tree-sitter).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import libcst as cst


# Standard library module names for filtering (Python only)
try:
    _STDLIB_MODULES = sys.stdlib_module_names  # Python 3.10+
except AttributeError:
    _STDLIB_MODULES = frozenset({
        "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
        "asyncore", "atexit", "base64", "bdb", "binascii", "binhex",
        "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb", "chunk",
        "cmath", "cmd", "code", "codecs", "codeop", "collections",
        "colorsys", "compileall", "concurrent", "configparser", "contextlib",
        "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv",
        "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
        "difflib", "dis", "distutils", "doctest", "email", "encodings",
        "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
        "fnmatch", "formatter", "fractions", "ftplib", "functools", "gc",
        "getopt", "getpass", "gettext", "glob", "grp", "gzip", "hashlib",
        "heapq", "hmac", "html", "http", "idlelib", "imaplib", "imghdr",
        "imp", "importlib", "inspect", "io", "ipaddress", "itertools",
        "json", "keyword", "lib2to3", "linecache", "locale", "logging",
        "lzma", "mailbox", "mailcap", "marshal", "math", "mimetypes",
        "mmap", "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
        "numbers", "operator", "optparse", "os", "ossaudiodev", "pathlib",
        "pdb", "pickle", "pickletools", "pipes", "pkgutil", "platform",
        "plistlib", "poplib", "posix", "posixpath", "pprint", "profile",
        "pstats", "pty", "pwd", "py_compile", "pyclbr", "pydoc",
        "queue", "quopri", "random", "re", "readline", "reprlib",
        "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
        "selectors", "shelve", "shlex", "shutil", "signal", "site",
        "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "spwd",
        "sqlite3", "sre_compile", "sre_constants", "sre_parse", "ssl",
        "stat", "statistics", "string", "stringprep", "struct", "subprocess",
        "sunau", "symtable", "sys", "sysconfig", "syslog", "tabnanny",
        "tarfile", "telnetlib", "tempfile", "termios", "test", "textwrap",
        "threading", "time", "timeit", "tkinter", "token", "tokenize",
        "tomllib", "trace", "traceback", "tracemalloc", "tty", "turtle",
        "turtledemo", "types", "typing", "unicodedata", "unittest", "urllib",
        "uu", "uuid", "venv", "warnings", "wave", "weakref", "webbrowser",
        "winreg", "winsound", "wsgiref", "xdrlib", "xml", "xmlrpc",
        "zipapp", "zipfile", "zipimport", "zlib", "_thread",
    })


@dataclass
class CouplingMetrics:
    file_path: str
    efferent_coupling: int = 0
    imports: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Python coupling analysis (libcst)
# ---------------------------------------------------------------------------

class _ImportCollector(cst.CSTVisitor):
    """Collects imported module names from a Python file."""

    def __init__(self):
        self.modules: List[str] = []

    def visit_Import(self, node: cst.Import) -> None:
        if isinstance(node.names, cst.ImportStar):
            return
        for alias in node.names:
            if isinstance(alias.name, (cst.Attribute, cst.Name)):
                module = _dotted_name(alias.name)
                self.modules.append(module)

    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        if node.module:
            module = _dotted_name(node.module)
            self.modules.append(module)


def _dotted_name(node) -> str:
    """Convert a Name or Attribute node to a dotted string."""
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        return _dotted_name(node.value) + "." + node.attr.value
    return ""


def _top_level_module(name: str) -> str:
    return name.split(".")[0]


def analyze_file_coupling(file_path: str) -> CouplingMetrics:
    """Analyze imports in a single Python file."""
    source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    try:
        tree = cst.parse_module(source)
    except cst.ParserSyntaxError:
        return CouplingMetrics(file_path=file_path)

    collector = _ImportCollector()
    from libcst import metadata
    wrapper = metadata.MetadataWrapper(tree)
    wrapper.visit(collector)

    # Filter out stdlib modules
    external = []
    seen = set()
    for mod in collector.modules:
        top = _top_level_module(mod)
        if top not in _STDLIB_MODULES and top not in seen:
            seen.add(top)
            external.append(mod)

    return CouplingMetrics(
        file_path=file_path,
        efferent_coupling=len(external),
        imports=external,
    )


# ---------------------------------------------------------------------------
# Tree-sitter coupling analysis (all other languages)
# ---------------------------------------------------------------------------

# Import node type → extractor function (returns list of import strings)
_TS_IMPORT_EXTRACTORS = {
    # Go: import "fmt" or import ( "fmt" ; "os" )
    "import_declaration": "_extract_go_imports",
    # Java: import java.util.List;
    # Also used by: import_statement in JS/TS
    "import_statement": "_extract_js_imports",
    # Rust: use std::io::Read;
    "use_declaration": "_extract_rust_imports",
    # C/C++: #include <stdio.h> or #include "myheader.h"
    "preproc_include": "_extract_cpp_imports",
}

# Map language names to their import-related node types
_LANG_IMPORT_TYPES = {
    "go": {"import_declaration"},
    "java": {"import_declaration"},
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "rust": {"use_declaration"},
    "cpp": {"preproc_include"},
}


def _go_import_path(spec_node) -> str:
    """Extract the import path string from a Go import_spec node, or ''."""
    path_node = spec_node.child_by_field_name("path")
    return path_node.text.decode().strip('"') if path_node else ""


def _extract_go_imports(node) -> List[str]:
    """Extract import paths from a Go import_declaration."""
    imports = []
    for child in node.children:
        if child.type == "import_spec":
            path = _go_import_path(child)
            if path:
                imports.append(path)
        elif child.type == "import_spec_list":
            for spec in child.children:
                if spec.type == "import_spec":
                    path = _go_import_path(spec)
                    if path:
                        imports.append(path)
    return imports


def _extract_java_imports(node) -> List[str]:
    """Extract import path from a Java import_declaration."""
    # Java import_declaration has a scoped_identifier child
    for child in node.children:
        if child.type == "scoped_identifier":
            return [child.text.decode()]
        elif child.type == "identifier":
            return [child.text.decode()]
    return []


def _extract_js_imports(node) -> List[str]:
    """Extract import path from a JS/TS import_statement."""
    source = node.child_by_field_name("source")
    if source:
        # Strip quotes from string literal
        path = source.text.decode().strip("'\"")
        return [path]
    return []


def _extract_rust_imports(node) -> List[str]:
    """Extract import path from a Rust use_declaration."""
    # use_declaration children include the path
    for child in node.children:
        if child.type in ("scoped_identifier", "identifier", "use_as_clause",
                          "scoped_use_list", "use_wildcard"):
            return [child.text.decode()]
    return []


def _extract_cpp_imports(node) -> List[str]:
    """Extract include path from a C/C++ preproc_include."""
    path_node = node.child_by_field_name("path")
    if path_node:
        # Strip <> or "" from the path
        path = path_node.text.decode().strip('<>"')
        return [path]
    return []


_EXTRACTORS = {
    "go": _extract_go_imports,
    "java": _extract_java_imports,
    "javascript": _extract_js_imports,
    "typescript": _extract_js_imports,
    "rust": _extract_rust_imports,
    "cpp": _extract_cpp_imports,
}


_TS_LANG_REGISTRY = {
    "go": ("tree_sitter_go", "language"),
    "java": ("tree_sitter_java", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "rust": ("tree_sitter_rust", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
}


def _get_ts_language(lang_name: str):
    """Get tree-sitter language object for a given language name. Returns None if unavailable."""
    entry = _TS_LANG_REGISTRY.get(lang_name)
    if entry is None:
        return None
    mod_name, factory = entry
    try:
        import importlib
        import tree_sitter as ts
        mod = importlib.import_module(mod_name)
        return ts.Language(getattr(mod, factory)())
    except (ImportError, ValueError, AttributeError):
        return None


def analyze_file_coupling_treesitter(file_path: str, language: str) -> CouplingMetrics:
    """Analyze imports in a non-Python source file using tree-sitter."""
    import tree_sitter as ts

    lang_obj = _get_ts_language(language)
    if lang_obj is None:
        return CouplingMetrics(file_path=file_path)

    source = Path(file_path).read_text(encoding="utf-8", errors="replace")
    source_bytes = source.encode("utf-8")

    parser = ts.Parser(lang_obj)
    tree = parser.parse(source_bytes)

    import_types = _LANG_IMPORT_TYPES.get(language, set())
    extractor = _EXTRACTORS.get(language)
    if not extractor:
        return CouplingMetrics(file_path=file_path)

    imports = []
    seen = set()

    def visit(node):
        if node.type in import_types:
            for imp in extractor(node):
                if imp and imp not in seen:
                    seen.add(imp)
                    imports.append(imp)
            return  # Don't recurse into import nodes
        for child in node.children:
            visit(child)

    visit(tree.root_node)

    return CouplingMetrics(
        file_path=file_path,
        efferent_coupling=len(imports),
        imports=imports,
    )


# ---------------------------------------------------------------------------
# Unified analysis dispatch
# ---------------------------------------------------------------------------

def analyze_file_coupling_any(file_path: str) -> CouplingMetrics:
    """Analyze imports in any supported source file."""
    from .scanner import EXTENSION_LANGUAGE_MAP

    ext = Path(file_path).suffix.lower()
    language = EXTENSION_LANGUAGE_MAP.get(ext)

    if language is None:
        return CouplingMetrics(file_path=file_path)

    if language == "python":
        return analyze_file_coupling(file_path)

    return analyze_file_coupling_treesitter(file_path, language)


def analyze_directory_coupling(
    directory: str,
    exclude_patterns: Optional[List[str]] = None,
    include_tests: bool = False,
) -> Dict[str, CouplingMetrics]:
    """Analyze coupling for all supported source files in a directory."""
    root = Path(directory)
    if root.is_file():
        metrics = analyze_file_coupling_any(str(root))
        return {str(root): metrics}

    from .scanner import discover_files

    results: Dict[str, CouplingMetrics] = {}
    for file_path in discover_files(directory, exclude_patterns, include_tests):
        rel = str(Path(file_path).relative_to(root))
        try:
            results[rel] = analyze_file_coupling_any(file_path)
        except Exception:
            continue
    return results


def compute_coupling_factor(coupling_data: Dict[str, CouplingMetrics]) -> float:
    """
    Compute a coupling multiplier for NCS.

    Returns 1.0 (neutral) when no data is available.
    Formula: 1 + avg_coupling / max_coupling (bounded to [1.0, 2.0])
    """
    if not coupling_data:
        return 1.0
    values = [m.efferent_coupling for m in coupling_data.values()]
    max_c = max(values)
    if max_c == 0:
        return 1.0
    avg_c = sum(values) / len(values)
    return round(1.0 + avg_c / max_c, 4)
