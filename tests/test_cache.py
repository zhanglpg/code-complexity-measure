"""Tests for content-hash caching."""
import textwrap
import tempfile
import os
import json

from complexity_accounting.cache import MetricsCache, _content_hash, _cache_key
from complexity_accounting.scanner import (
    scan_file, scan_directory, set_cache, get_cache,
    FileMetrics, FunctionMetrics, ClassMetrics, ScanResult,
)


def _write_temp(source: str, suffix: str = ".py") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, textwrap.dedent(source).encode())
    os.close(fd)
    return path


# ── Cache key / hash ────────────────────────────────────────────────────

def test_content_hash_deterministic():
    path = _write_temp("def foo(): pass\n")
    try:
        h1 = _content_hash(path)
        h2 = _content_hash(path)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex
    finally:
        os.unlink(path)


def test_content_hash_changes_on_modification():
    path = _write_temp("def foo(): pass\n")
    try:
        h1 = _content_hash(path)
        with open(path, "a") as f:
            f.write("# modified\n")
        h2 = _content_hash(path)
        assert h1 != h2
    finally:
        os.unlink(path)


def test_cache_key_deterministic():
    k1 = _cache_key("/some/file.py")
    k2 = _cache_key("/some/file.py")
    assert k1 == k2
    assert k1.endswith(".json")


# ── MetricsCache ────────────────────────────────────────────────────────

def test_cache_put_and_get():
    with tempfile.TemporaryDirectory() as cache_dir:
        cache = MetricsCache(cache_dir=cache_dir)
        path = _write_temp("def hello(): return 1\n")
        try:
            fm = scan_file(path)
            cache.put(path, fm)

            # Should get cached result
            cached = cache.get(path)
            assert cached is not None
            assert cached.path == fm.path
            assert len(cached.functions) == len(fm.functions)
            assert cached.functions[0].name == fm.functions[0].name
            assert cached.total_lines == fm.total_lines
        finally:
            os.unlink(path)


def test_cache_miss_on_modification():
    with tempfile.TemporaryDirectory() as cache_dir:
        cache = MetricsCache(cache_dir=cache_dir)
        path = _write_temp("def hello(): return 1\n")
        try:
            fm = scan_file(path)
            cache.put(path, fm)

            # Modify file
            with open(path, "w") as f:
                f.write("def goodbye(): return 2\n")

            # Should miss cache (content changed)
            cached = cache.get(path)
            assert cached is None
        finally:
            os.unlink(path)


def test_cache_miss_on_version_change():
    with tempfile.TemporaryDirectory() as cache_dir:
        cache = MetricsCache(cache_dir=cache_dir)
        path = _write_temp("def hello(): return 1\n")
        try:
            fm = scan_file(path)
            cache.put(path, fm)

            # Tamper with version in cache file
            cache_file = os.path.join(cache_dir, _cache_key(path))
            with open(cache_file, "r") as f:
                data = json.load(f)
            data["version"] = "0.0.0-fake"
            with open(cache_file, "w") as f:
                json.dump(data, f)

            cached = cache.get(path)
            assert cached is None
        finally:
            os.unlink(path)


def test_cache_disabled():
    with tempfile.TemporaryDirectory() as cache_dir:
        cache = MetricsCache(cache_dir=cache_dir, enabled=False)
        path = _write_temp("def hello(): return 1\n")
        try:
            fm = scan_file(path)
            cache.put(path, fm)
            assert cache.get(path) is None  # disabled
        finally:
            os.unlink(path)


def test_cache_clear():
    with tempfile.TemporaryDirectory() as cache_dir:
        cache = MetricsCache(cache_dir=cache_dir)
        path = _write_temp("def hello(): return 1\n")
        try:
            fm = scan_file(path)
            cache.put(path, fm)
            assert cache.get(path) is not None

            count = cache.clear()
            assert count >= 1
            assert cache.get(path) is None
        finally:
            os.unlink(path)


def test_cache_with_classes():
    with tempfile.TemporaryDirectory() as cache_dir:
        cache = MetricsCache(cache_dir=cache_dir)
        path = _write_temp("""
            class MyClass:
                def method(self):
                    return 42
        """)
        try:
            fm = scan_file(path)
            assert len(fm.classes) == 1
            cache.put(path, fm)

            cached = cache.get(path)
            assert cached is not None
            assert len(cached.classes) == 1
            assert cached.classes[0].name == "MyClass"
            assert cached.classes[0].method_count >= 1
        finally:
            os.unlink(path)


# ── Integration with scan_file/scan_directory ───────────────────────────

def test_set_and_get_cache():
    old_cache = get_cache()
    try:
        with tempfile.TemporaryDirectory() as cache_dir:
            cache = MetricsCache(cache_dir=cache_dir)
            set_cache(cache)
            assert get_cache() is cache
    finally:
        set_cache(old_cache)


def test_scan_file_uses_cache():
    old_cache = get_cache()
    try:
        with tempfile.TemporaryDirectory() as cache_dir:
            cache = MetricsCache(cache_dir=cache_dir)
            set_cache(cache)

            path = _write_temp("def test_func(): return 1\n")
            try:
                # First scan - cache miss
                fm1 = scan_file(path)
                assert fm1.functions[0].name == "test_func"

                # Second scan - should use cache
                fm2 = scan_file(path)
                assert fm2.functions[0].name == "test_func"
                assert fm2.path == fm1.path
            finally:
                os.unlink(path)
    finally:
        set_cache(old_cache)
