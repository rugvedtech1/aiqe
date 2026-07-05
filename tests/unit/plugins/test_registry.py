"""Unit tests for PluginRegistry."""
import pytest
from unittest.mock import MagicMock
from aiqe.plugins.registry import PluginRegistry, LoadedPlugin
from aiqe.plugins.manifest import PluginManifest, PluginEntryPoint
from aiqe.shared.exceptions import PluginLoadError


def make_manifest(name: str = "test-plugin") -> PluginManifest:
    return PluginManifest(
        name=name,
        version="1.0.0",
        description="Test plugin",
        author="Test",
        plugin_type="custom",
        min_aiqe_version="0.1.0",
        required_capabilities=[],
        entry_point=PluginEntryPoint(
            module="test.module",
            class_name="TestPlugin",
        ),
    )


class TestPluginRegistry:
    def test_register_and_get(self):
        registry = PluginRegistry()
        loaded = LoadedPlugin(
            manifest=make_manifest("my-plugin"),
            instance=MagicMock(),
        )
        registry.register(loaded)
        retrieved = registry.get("my-plugin")
        assert retrieved.manifest.name == "my-plugin"

    def test_duplicate_registration_raises(self):
        registry = PluginRegistry()
        loaded = LoadedPlugin(
            manifest=make_manifest("dup-plugin"),
            instance=MagicMock(),
        )
        registry.register(loaded)
        with pytest.raises(PluginLoadError):
            registry.register(loaded)

    def test_get_unknown_raises(self):
        registry = PluginRegistry()
        with pytest.raises(PluginLoadError):
            registry.get("nonexistent")

    def test_get_by_type(self):
        registry = PluginRegistry()
        browser_manifest = make_manifest("browser-plugin")
        browser_manifest.__class__ = PluginManifest

        from dataclasses import replace
        browser = LoadedPlugin(
            manifest=PluginManifest(
                name="browser-plugin",
                version="1.0",
                description="",
                author="",
                plugin_type="browser",
                min_aiqe_version="0.1.0",
                required_capabilities=[],
                entry_point=PluginEntryPoint("m", "C"),
            ),
            instance=MagicMock(),
        )
        notification = LoadedPlugin(
            manifest=PluginManifest(
                name="notif-plugin",
                version="1.0",
                description="",
                author="",
                plugin_type="notification",
                min_aiqe_version="0.1.0",
                required_capabilities=[],
                entry_point=PluginEntryPoint("m", "C"),
            ),
            instance=MagicMock(),
        )
        registry.register(browser)
        registry.register(notification)

        browser_plugins = registry.get_by_type("browser")
        assert len(browser_plugins) == 1
        assert browser_plugins[0].manifest.name == "browser-plugin"

    def test_unregister(self):
        registry = PluginRegistry()
        loaded = LoadedPlugin(
            manifest=make_manifest("temp-plugin"),
            instance=MagicMock(),
        )
        registry.register(loaded)
        removed = registry.unregister("temp-plugin")
        assert removed is True
        assert not registry.is_registered("temp-plugin")

    def test_count(self):
        registry = PluginRegistry()
        assert registry.count == 0
        registry.register(LoadedPlugin(
            manifest=make_manifest("p1"),
            instance=MagicMock(),
        ))
        assert registry.count == 1
