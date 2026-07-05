"""
AIQE Plugin Registry.

Tracks all loaded plugins and their manifests.
The registry is the source of truth for what plugins are
currently available and what capabilities they have.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aiqe.plugins.base import BasePlugin
from aiqe.plugins.manifest import PluginManifest
from aiqe.shared.exceptions import PluginLoadError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LoadedPlugin:
    """
    A plugin that has been loaded and is ready to use.

    Attributes:
        manifest: The validated plugin manifest.
        instance: The instantiated plugin class.
        is_healthy: Whether the last health check passed.
    """
    manifest: PluginManifest
    instance: BasePlugin
    is_healthy: bool = True


class PluginRegistry:
    """
    Registry of all loaded AIQE plugins.

    Tracks plugins by name and type, providing lookup
    methods for the Plugin Loader and Workflow Engine.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, LoadedPlugin] = {}

    def register(self, loaded: LoadedPlugin) -> None:
        """
        Register a loaded plugin.

        Args:
            loaded: The loaded plugin with manifest and instance.

        Raises:
            PluginLoadError: If a plugin with this name is already registered.
        """
        if loaded.manifest.name in self._plugins:
            msg = (
                f"Plugin '{loaded.manifest.name}' is already registered. "
                f"Each plugin must have a unique name."
            )
            raise PluginLoadError(msg, plugin_name=loaded.manifest.name)

        self._plugins[loaded.manifest.name] = loaded

        logger.info(
            "plugin_registered",
            plugin_name=loaded.manifest.name,
            plugin_type=loaded.manifest.plugin_type,
            version=loaded.manifest.version,
            capabilities=loaded.manifest.capability_ids,
        )

    def get(self, plugin_name: str) -> LoadedPlugin:
        """
        Get a registered plugin by name.

        Args:
            plugin_name: The plugin's registered name.

        Returns:
            The LoadedPlugin.

        Raises:
            PluginLoadError: If no plugin with this name is registered.
        """
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            available = list(self._plugins.keys())
            msg = (
                f"Plugin '{plugin_name}' is not registered. "
                f"Available plugins: {available}"
            )
            raise PluginLoadError(msg, plugin_name=plugin_name)
        return plugin

    def get_by_type(self, plugin_type: str) -> list[LoadedPlugin]:
        """
        Get all registered plugins of a specific type.

        Args:
            plugin_type: The plugin type to filter by.

        Returns:
            List of LoadedPlugins of this type.
        """
        return [
            p for p in self._plugins.values()
            if p.manifest.plugin_type == plugin_type
        ]

    def is_registered(self, plugin_name: str) -> bool:
        """True if a plugin with this name is registered."""
        return plugin_name in self._plugins

    def unregister(self, plugin_name: str) -> bool:
        """
        Remove a plugin from the registry.

        Args:
            plugin_name: The plugin to remove.

        Returns:
            True if removed, False if not found.
        """
        if plugin_name in self._plugins:
            del self._plugins[plugin_name]
            logger.info(
                "plugin_unregistered",
                plugin_name=plugin_name,
            )
            return True
        return False

    def all_plugins(self) -> list[LoadedPlugin]:
        """Return all registered plugins."""
        return list(self._plugins.values())

    @property
    def count(self) -> int:
        """Total number of registered plugins."""
        return len(self._plugins)

    def summary(self) -> list[dict[str, Any]]:
        """Summary of all registered plugins for reporting."""
        return [
            {
                "name": p.manifest.name,
                "version": p.manifest.version,
                "type": p.manifest.plugin_type,
                "author": p.manifest.author,
                "capabilities": p.manifest.capability_ids,
                "is_healthy": p.is_healthy,
            }
            for p in self._plugins.values()
        ]


# Module-level singleton
_plugin_registry = PluginRegistry()


def get_plugin_registry() -> PluginRegistry:
    """Get the global PluginRegistry singleton."""
    return _plugin_registry
