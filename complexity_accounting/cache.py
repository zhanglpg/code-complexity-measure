"""
Content-hash caching for complexity metrics.

Uses SHA-256 of file content (not timestamps) to determine if cached results
are still valid. Stores cached metrics as JSON in a configurable directory.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from . import __version__
from .models import FileMetrics, FunctionMetrics, ClassMetrics

# Default cache directory (relative to project root)
DEFAULT_CACHE_DIR = ".complexity-cache"


def _content_hash(file_path: str) -> str:
    """Compute SHA-256 hash of file content."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_key(file_path: str) -> str:
    """Generate a cache filename from a file path."""
    return hashlib.sha256(os.path.abspath(file_path).encode()).hexdigest() + ".json"


def _serialize_file_metrics(fm: FileMetrics) -> dict:
    """Serialize FileMetrics to a JSON-safe dict."""
    return {
        "path": fm.path,
        "functions": [asdict(fn) for fn in fm.functions],
        "classes": [
            {
                "name": cls.name,
                "file_path": cls.file_path,
                "line": cls.line,
                "end_line": cls.end_line,
                "method_names": [m.name for m in cls.methods],
            }
            for cls in fm.classes
        ],
        "total_lines": fm.total_lines,
        "code_lines": fm.code_lines,
        "comment_lines": fm.comment_lines,
        "blank_lines": fm.blank_lines,
    }


def _deserialize_file_metrics(data: dict) -> FileMetrics:
    """Deserialize FileMetrics from a cached dict."""
    functions = []
    for fn_data in data.get("functions", []):
        functions.append(FunctionMetrics(**fn_data))

    # Rebuild ClassMetrics by matching methods by name
    classes = []
    for cls_data in data.get("classes", []):
        method_names = set(cls_data.get("method_names", []))
        methods = [f for f in functions if f.name in method_names
                   and f.line >= cls_data.get("line", 0)
                   and f.end_line <= cls_data.get("end_line", 999999)]
        classes.append(ClassMetrics(
            name=cls_data["name"],
            file_path=cls_data["file_path"],
            line=cls_data["line"],
            end_line=cls_data["end_line"],
            methods=methods,
        ))

    return FileMetrics(
        path=data["path"],
        functions=functions,
        classes=classes,
        total_lines=data.get("total_lines", 0),
        code_lines=data.get("code_lines", 0),
        comment_lines=data.get("comment_lines", 0),
        blank_lines=data.get("blank_lines", 0),
    )


class MetricsCache:
    """Content-hash based cache for file complexity metrics."""

    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR, enabled: bool = True):
        self.cache_dir = cache_dir
        self.enabled = enabled

    def _ensure_dir(self):
        os.makedirs(self.cache_dir, exist_ok=True)

    def get(self, file_path: str) -> Optional[FileMetrics]:
        """Retrieve cached metrics for a file if content hash matches."""
        if not self.enabled:
            return None

        cache_file = os.path.join(self.cache_dir, _cache_key(file_path))
        if not os.path.exists(cache_file):
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)

            # Validate version and content hash
            if cached.get("version") != __version__:
                return None
            if cached.get("content_hash") != _content_hash(file_path):
                return None

            return _deserialize_file_metrics(cached["metrics"])
        except (json.JSONDecodeError, KeyError, TypeError, OSError):
            return None

    def put(self, file_path: str, metrics: FileMetrics) -> None:
        """Cache metrics for a file."""
        if not self.enabled:
            return

        self._ensure_dir()
        cache_file = os.path.join(self.cache_dir, _cache_key(file_path))

        data = {
            "version": __version__,
            "content_hash": _content_hash(file_path),
            "metrics": _serialize_file_metrics(metrics),
        }

        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except OSError:
            pass  # graceful degradation

    def clear(self) -> int:
        """Remove all cached files. Returns the number of files removed."""
        count = 0
        if os.path.isdir(self.cache_dir):
            for name in os.listdir(self.cache_dir):
                if name.endswith(".json"):
                    try:
                        os.remove(os.path.join(self.cache_dir, name))
                        count += 1
                    except OSError:
                        pass
        return count
