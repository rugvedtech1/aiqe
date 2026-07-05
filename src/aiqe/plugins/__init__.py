"""
AIQE Plugin System.

Implements the capability-based least-privilege plugin model
defined in ADR-003.

Public API:
    BasePlugin       — abstract base all plugins inherit from
    PluginContext    — restricted capability context given to plugins
    PluginManifest   — validated plugin manifest
    ManifestLoader   — loads and validates plugin.toml files
    PluginLoader     — the ADR-003 security loading pipeline
    PluginRegistry   — tracks all loaded plugins
    Capabilities     — all valid capability constants
    CapabilityGroup  — capability group enum
    get_plugin_loader   — get a configured loader instance
    get_plugin_registry — get the global registry singleton

Capability pre-built sets:
    PLAYWRIGHT_PLUGIN_CAPABILITIES
    GITHUB_PLUGIN_CAPABILITIES
    SLACK_PLUGIN_CAPABILITIES
    SECURITY_SCAN_PLUGIN_CAPABILITIES
"""

from aiqe.plugins.base import BasePlugin
from aiqe.plugins.capabilities import (
    Capabilities,
    Capability,
    CapabilityGroup,
    GITHUB_PLUGIN_CAPABILITIES,
    PLAYWRIGHT_PLUGIN_CAPABILITIES,
    SECURITY_SCAN_PLUGIN_CAPABILITIES,
    SLACK_PLUGIN_CAPABILITIES,
)
from aiqe.plugins.loader import PluginLoader, get_plugin_loader
from aiqe.plugins.manifest import ManifestLoader, PluginManifest
from aiqe.plugins.registry import (
    LoadedPlugin,
    PluginRegistry,
    get_plugin_registry,
)
from aiqe.plugins.sandbox import PluginContext, RestrictedFilesystem, RestrictedNetwork

__all__ = [
    "BasePlugin",
    "Capabilities",
    "Capability",
    "CapabilityGroup",
    "GITHUB_PLUGIN_CAPABILITIES",
    "LoadedPlugin",
    "ManifestLoader",
    "PLAYWRIGHT_PLUGIN_CAPABILITIES",
    "PluginContext",
    "PluginLoader",
    "PluginManifest",
    "PluginRegistry",
    "RestrictedFilesystem",
    "RestrictedNetwork",
    "SECURITY_SCAN_PLUGIN_CAPABILITIES",
    "SLACK_PLUGIN_CAPABILITIES",
    "get_plugin_loader",
    "get_plugin_registry",
]
