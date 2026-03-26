"""Tests for plugin architecture."""
from complexity_accounting.plugin import (
    ENTRY_POINT_GROUP,
    LanguagePlugin,
    list_plugins,
    get_plugin_for_extension,
    clear_plugin_cache,
    _discover_plugins,
)
from complexity_accounting.scanner import FileMetrics, FunctionMetrics


# ── Protocol conformance ────────────────────────────────────────────────

class MockKotlinPlugin:
    """Example plugin that conforms to LanguagePlugin protocol."""

    @property
    def name(self) -> str:
        return "Kotlin"

    @property
    def extensions(self):
        return (".kt", ".kts")

    def scan_file(self, file_path: str) -> FileMetrics:
        return FileMetrics(path=file_path)


def test_mock_plugin_is_language_plugin():
    plugin = MockKotlinPlugin()
    assert isinstance(plugin, LanguagePlugin)


def test_mock_plugin_properties():
    plugin = MockKotlinPlugin()
    assert plugin.name == "Kotlin"
    assert plugin.extensions == (".kt", ".kts")
    assert len(plugin.extensions) == 2


def test_mock_plugin_scan():
    plugin = MockKotlinPlugin()
    fm = plugin.scan_file("test.kt")
    assert fm.path == "test.kt"
    assert fm.function_count == 0
    assert fm.total_lines == 0
    assert fm.functions == []


# ── Non-conforming classes ──────────────────────────────────────────────

class BadPlugin:
    """Does not implement the protocol."""
    pass


def test_bad_plugin_not_language_plugin():
    plugin = BadPlugin()
    assert not isinstance(plugin, LanguagePlugin)


# ── Discovery functions ─────────────────────────────────────────────────

def test_list_plugins_returns_list():
    clear_plugin_cache()
    result = list_plugins()
    assert result == []


def test_get_plugin_for_unknown_extension():
    clear_plugin_cache()
    plugin = get_plugin_for_extension(".xyz_unknown")
    assert plugin is None


def test_clear_plugin_cache():
    clear_plugin_cache()
    # Should not raise
    _discover_plugins()
    clear_plugin_cache()
    # Cache should be cleared
    assert get_plugin_for_extension(".kt") is None


def test_discover_plugins_returns_dict():
    clear_plugin_cache()
    result = _discover_plugins()
    assert result == {}


# ── Caching behaviour ──────────────────────────────────────────────────

def test_plugin_cache_returns_same_result():
    clear_plugin_cache()
    first = _discover_plugins()
    second = _discover_plugins()
    assert first is second


def test_clear_cache_resets_discovery():
    clear_plugin_cache()
    first = _discover_plugins()
    clear_plugin_cache()
    second = _discover_plugins()
    assert first is not second
    assert first == second


# ── Constants ───────────────────────────────────────────────────────────

def test_entry_point_group_constant():
    assert ENTRY_POINT_GROUP == "complexity_accounting.languages"
