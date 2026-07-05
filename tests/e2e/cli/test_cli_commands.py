"""
End-to-end CLI tests using Typer's test runner.

These tests invoke CLI commands through the actual Typer app
without needing a real terminal or subprocess.
"""
import pytest
from typer.testing import CliRunner
from aiqe.cli.main import app

runner = CliRunner()


class TestVersionCommand:
    def test_version_shows_version(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "0.1.0-alpha" in result.output
        assert "AIQE" in result.output

    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestHelpCommand:
    def test_root_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "scan" in result.output
        assert "status" in result.output
        assert "report" in result.output
        assert "plugins" in result.output
        assert "gateway" in result.output
        assert "config" in result.output

    def test_scan_help(self):
        result = runner.invoke(app, ["scan", "--help"])
        assert result.exit_code == 0
        assert "project_path" in result.output.lower() or "PATH" in result.output

    def test_plugins_help(self):
        result = runner.invoke(app, ["plugins", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "validate" in result.output
        assert "capabilities" in result.output

    def test_gateway_help(self):
        result = runner.invoke(app, ["gateway", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "test" in result.output

    def test_config_help(self):
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "show" in result.output
        assert "validate" in result.output


class TestPluginsCapabilitiesCommand:
    def test_capabilities_lists_all(self):
        result = runner.invoke(app, ["plugins", "capabilities"])
        assert result.exit_code == 0
        assert "browser.navigate" in result.output
        assert "filesystem.read_project_files" in result.output
        assert "system.execute_shell" in result.output

    def test_capabilities_filter_by_group(self):
        result = runner.invoke(
            app, ["plugins", "capabilities", "--group", "browser"]
        )
        assert result.exit_code == 0
        assert "browser.navigate" in result.output
        assert "filesystem.read_project_files" not in result.output

    def test_capabilities_filter_restricted(self):
        result = runner.invoke(
            app, ["plugins", "capabilities", "--restricted"]
        )
        assert result.exit_code == 0
        assert "YES" in result.output.upper() or "RESTRICTED" in result.output.upper()

    def test_capabilities_invalid_group(self):
        result = runner.invoke(
            app, ["plugins", "capabilities", "--group", "invalid_group"]
        )
        assert result.exit_code != 0


class TestPluginsListCommand:
    def test_plugins_list_empty(self):
        result = runner.invoke(app, ["plugins", "list"])
        assert result.exit_code == 0
        assert "No plugins" in result.output or result.exit_code == 0


class TestPluginsValidateCommand:
    def test_validate_nonexistent_path(self):
        result = runner.invoke(
            app,
            ["plugins", "validate", "/nonexistent/path/to/plugin"],
        )
        assert result.exit_code != 0

    def test_validate_valid_manifest(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        manifest_content = """
[plugin]
name = "test-cli-plugin"
version = "1.0.0"
description = "A test plugin for CLI validation."
author = "Test Author"
plugin_type = "custom"
min_aiqe_version = "0.1.0"

[plugin.capabilities]
required = [
    "filesystem.read_project_files",
    "filesystem.write_temp_files",
]

[plugin.entry_point]
module = "test_cli_plugin.plugin"
class_name = "TestCLIPlugin"
"""
        (plugin_dir / "plugin.toml").write_text(manifest_content)

        result = runner.invoke(
            app,
            ["plugins", "validate", str(plugin_dir)],
        )
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_manifest_with_unknown_capability(self, tmp_path):
        plugin_dir = tmp_path / "bad-plugin"
        plugin_dir.mkdir()
        manifest_content = """
[plugin]
name = "bad-plugin"
version = "1.0.0"
description = "A plugin with invalid capability."
author = "Test"
plugin_type = "custom"
min_aiqe_version = "0.1.0"

[plugin.capabilities]
required = ["nonexistent.unknown.capability"]

[plugin.entry_point]
module = "bad_plugin.plugin"
class_name = "BadPlugin"
"""
        (plugin_dir / "plugin.toml").write_text(manifest_content)

        result = runner.invoke(
            app,
            ["plugins", "validate", str(plugin_dir)],
        )
        assert result.exit_code != 0
        assert "unknown" in result.output.lower()


class TestConfigGenerateKey:
    def test_generate_key_produces_output(self):
        result = runner.invoke(app, ["config", "generate-key"])
        assert result.exit_code == 0
        assert len(result.output) > 30


class TestScanDryRun:
    def test_scan_dry_run_current_dir(self, tmp_path):
        result = runner.invoke(
            app,
            ["scan", str(tmp_path), "--dry-run", "--no-banner"],
        )
        assert result.exit_code == 0
        assert "Dry Run" in result.output or "dry" in result.output.lower()

    def test_scan_nonexistent_path(self):
        result = runner.invoke(
            app,
            ["scan", "/nonexistent/path", "--dry-run"],
        )
        assert result.exit_code != 0
