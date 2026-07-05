"""Unit tests for Plugin Manifest loading and validation."""
import pytest
from pathlib import Path
from aiqe.plugins.manifest import ManifestLoader, PluginManifest
from aiqe.shared.exceptions import PluginManifestError


VALID_MANIFEST = {
    "plugin": {
        "name": "test-playwright-plugin",
        "version": "1.0.0",
        "description": "A test browser plugin.",
        "author": "Test Author",
        "plugin_type": "browser",
        "min_aiqe_version": "0.1.0",
        "capabilities": {
            "required": [
                "browser.navigate",
                "browser.screenshots",
                "filesystem.read_project_files",
            ]
        },
        "entry_point": {
            "module": "test_plugin.plugin",
            "class_name": "TestPlaywrightPlugin",
        },
    }
}

MANIFEST_MISSING_NAME = {
    "plugin": {
        "name": "",
        "version": "1.0.0",
        "description": "Missing name",
        "author": "Test",
        "plugin_type": "browser",
        "capabilities": {"required": []},
        "entry_point": {"module": "mod", "class_name": "Cls"},
    }
}


@pytest.fixture
def loader():
    return ManifestLoader()


class TestManifestLoader:
    def test_valid_manifest_loads(self, loader):
        manifest = loader.load_from_dict(VALID_MANIFEST)
        assert manifest.name == "test-playwright-plugin"
        assert manifest.version == "1.0.0"
        assert manifest.plugin_type == "browser"
        assert len(manifest.required_capabilities) == 3

    def test_missing_name_raises(self, loader):
        with pytest.raises(PluginManifestError):
            loader.load_from_dict(MANIFEST_MISSING_NAME)

    def test_unknown_capability_raises(self, loader):
        bad = {
            "plugin": {
                **VALID_MANIFEST["plugin"],
                "capabilities": {
                    "required": ["nonexistent.capability"]
                },
            }
        }
        with pytest.raises(PluginManifestError, match="unknown capabilities"):
            loader.load_from_dict(bad)

    def test_invalid_plugin_type_raises(self, loader):
        bad = {
            "plugin": {
                **VALID_MANIFEST["plugin"],
                "plugin_type": "invalid_type",
            }
        }
        with pytest.raises(PluginManifestError, match="plugin_type"):
            loader.load_from_dict(bad)

    def test_missing_entry_point_raises(self, loader):
        bad = {
            "plugin": {
                **VALID_MANIFEST["plugin"],
                "entry_point": {},
            }
        }
        with pytest.raises(PluginManifestError, match="entry_point"):
            loader.load_from_dict(bad)

    def test_manifest_file_not_found_raises(self, loader, tmp_path):
        with pytest.raises(PluginManifestError, match="not found"):
            loader.load_from_path(tmp_path / "nonexistent" / "plugin.toml")

    def test_display_summary_contains_plugin_name(self, loader):
        manifest = loader.load_from_dict(VALID_MANIFEST)
        summary = manifest.display_summary()
        assert "test-playwright-plugin" in summary
        assert "Browser Navigation" in summary

    def test_has_restricted_capabilities_false_for_safe_plugin(self, loader):
        manifest = loader.load_from_dict(VALID_MANIFEST)
        assert not manifest.has_restricted_capabilities

    def test_has_restricted_capabilities_true_for_shell_access(self, loader):
        restricted_manifest = {
            "plugin": {
                **VALID_MANIFEST["plugin"],
                "capabilities": {
                    "required": ["system.execute_shell"]
                },
            }
        }
        manifest = loader.load_from_dict(restricted_manifest)
        assert manifest.has_restricted_capabilities
        assert manifest.max_risk_level == 4
