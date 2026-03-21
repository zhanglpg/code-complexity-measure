"""
Plugin architecture for language support.

Third-party language plugins can be discovered via Python entry points.
Plugins register under the group 'complexity_accounting.languages' and must
implement the LanguagePlugin protocol.

Example plugin registration in pyproject.toml:

    [project.entry-points."complexity_accounting.languages"]
    kotlin = "complexity_kotlin:KotlinPlugin"
"""

from __future__ import annotations

import sys
from typing import Dict, List, Optional, Tuple

from .scanner import FileMetrics

if sys.version_info >= (3, 8):
    from typing import Protocol, runtime_checkable
else:
    from typing_extensions import Protocol, runtime_checkable


ENTRY_POINT_GROUP = "complexity_accounting.languages"


@runtime_checkable
class LanguagePlugin(Protocol):
    """Protocol that language plugins must implement."""

    @property
    def name(self) -> str:
        """Human-readable name of the language (e.g. 'Kotlin')."""
        ...

    @property
    def extensions(self) -> Tuple[str, ...]:
        """File extensions this plugin handles (e.g. ('.kt', '.kts'))."""
        ...

    def scan_file(self, file_path: str) -> FileMetrics:
        """Scan a single file and return its metrics."""
        ...


# ---------------------------------------------------------------------------
# Plugin discovery
# ---------------------------------------------------------------------------

_plugin_cache: Optional[Dict[str, LanguagePlugin]] = None


def _discover_plugins() -> Dict[str, LanguagePlugin]:
    """Discover installed language plugins via entry points."""
    global _plugin_cache
    if _plugin_cache is not None:
        return _plugin_cache

    plugins: Dict[str, LanguagePlugin] = {}

    try:
        if sys.version_info >= (3, 10):
            from importlib.metadata import entry_points
            eps = entry_points(group=ENTRY_POINT_GROUP)
        else:
            from importlib.metadata import entry_points
            all_eps = entry_points()
            eps = all_eps.get(ENTRY_POINT_GROUP, [])
    except Exception:
        _plugin_cache = {}
        return _plugin_cache

    for ep in eps:
        try:
            plugin_class = ep.load()
            plugin = plugin_class() if isinstance(plugin_class, type) else plugin_class
            if isinstance(plugin, LanguagePlugin):
                for ext in plugin.extensions:
                    plugins[ext] = plugin
        except Exception:
            pass  # graceful skip of broken plugins

    _plugin_cache = plugins
    return _plugin_cache


def get_plugin_for_extension(ext: str) -> Optional[LanguagePlugin]:
    """Get a plugin that handles the given file extension, or None."""
    plugins = _discover_plugins()
    return plugins.get(ext)


def list_plugins() -> List[Dict[str, str]]:
    """List all discovered plugins with their metadata."""
    plugins = _discover_plugins()
    seen = set()
    result = []
    for ext, plugin in sorted(plugins.items()):
        plugin_id = id(plugin)
        if plugin_id in seen:
            continue
        seen.add(plugin_id)
        result.append({
            "name": plugin.name,
            "extensions": ", ".join(plugin.extensions),
        })
    return result


def clear_plugin_cache() -> None:
    """Clear the plugin discovery cache. Useful for testing."""
    global _plugin_cache
    _plugin_cache = None
