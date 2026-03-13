"""
Import coupling analysis.

Computes efferent coupling (fan-out) per file by analyzing Python imports.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import libcst as cst


# Standard library module names for filtering
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


def analyze_directory_coupling(
    directory: str,
    exclude_patterns: Optional[List[str]] = None,
) -> Dict[str, CouplingMetrics]:
    """Analyze coupling for all Python files in a directory."""
    from fnmatch import fnmatch

    if exclude_patterns is None:
        exclude_patterns = [
            "**/venv/**", "**/.venv/**", "**/node_modules/**",
            "**/__pycache__/**", "**/build/**", "**/dist/**",
            "**/.git/**", "**/migrations/**",
        ]

    root = Path(directory)
    if root.is_file():
        metrics = analyze_file_coupling(str(root))
        return {str(root): metrics}

    results: Dict[str, CouplingMetrics] = {}
    for py_file in sorted(root.rglob("*.py")):
        rel = str(py_file.relative_to(root))
        skip = any(
            fnmatch(rel, pat) or fnmatch(str(py_file), pat)
            for pat in exclude_patterns
        )
        if skip:
            continue
        try:
            results[rel] = analyze_file_coupling(str(py_file))
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
