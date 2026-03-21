"""Tests for plugin architecture."""
from complexity_accounting.plugin import (
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
    assert ".kt" in plugin.extensions
    assert ".kts" in plugin.extensions


def test_mock_plugin_scan():
    plugin = MockKotlinPlugin()
    fm = plugin.scan_file("test.kt")
    assert fm.path == "test.kt"


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
    assert isinstance(result, list)
    # No third-party plugins installed in test env
    # Just verify it doesn't crash


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
    assert isinstance(result, dict)
