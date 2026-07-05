"""
Security tests for plugin capability enforcement.

These tests verify that the capability boundary cannot be
crossed by plugins that declare fewer permissions than they use.
"""
import pytest
from pathlib import Path
from aiqe.plugins.sandbox import PluginContext
from aiqe.plugins.capabilities import Capabilities
from aiqe.shared.exceptions import CapabilityDeniedError


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "plugin_workspace"
    ws.mkdir()
    return ws


class TestCapabilityBoundaryEnforcement:
    """
    Verify that capability boundaries are enforced and cannot
    be bypassed through the PluginContext interface.
    """

    def test_browser_navigate_denied_without_declaration(self, workspace):
        """Plugin without browser.navigate cannot navigate."""
        context = PluginContext(
            plugin_name="sneaky-plugin",
            granted_capabilities={
                Capabilities.FILESYSTEM_READ_PROJECT_FILES.id,
            },
            workspace_path=workspace,
        )
        with pytest.raises(CapabilityDeniedError):
            context.assert_capability(Capabilities.BROWSER_NAVIGATE.id)

    def test_shell_execution_denied_without_declaration(self, workspace):
        """Plugin without system.execute_shell cannot run shell commands."""
        context = PluginContext(
            plugin_name="sneaky-plugin",
            granted_capabilities={
                Capabilities.FILESYSTEM_READ_PROJECT_FILES.id,
                Capabilities.BROWSER_NAVIGATE.id,
            },
            workspace_path=workspace,
        )
        with pytest.raises(CapabilityDeniedError):
            context.assert_capability(Capabilities.SYSTEM_SHELL.id)

    def test_database_delete_denied_without_declaration(self, workspace):
        """Plugin with only database.read cannot delete data."""
        context = PluginContext(
            plugin_name="readonly-db-plugin",
            granted_capabilities={
                Capabilities.DATABASE_READ.id,
            },
            workspace_path=workspace,
        )
        with pytest.raises(CapabilityDeniedError):
            context.assert_capability(Capabilities.DATABASE_DELETE.id)

    def test_secrets_access_denied_without_declaration(self, workspace):
        """Plugin without secrets capability cannot access API keys."""
        context = PluginContext(
            plugin_name="notification-plugin",
            granted_capabilities={
                Capabilities.NETWORK_SLACK_API.id,
            },
            workspace_path=workspace,
        )
        with pytest.raises(CapabilityDeniedError):
            context.assert_capability(Capabilities.SECRETS_OPENAI_KEY.id)

    def test_filesystem_write_denied_when_only_read_declared(self, workspace, tmp_path):
        """Plugin with read-only filesystem cannot write files."""
        project = tmp_path / "project"
        project.mkdir()

        context = PluginContext(
            plugin_name="read-only-plugin",
            granted_capabilities={
                Capabilities.FILESYSTEM_READ_PROJECT_FILES.id,
            },
            workspace_path=workspace,
            project_path=project,
        )

        with pytest.raises(CapabilityDeniedError):
            context.filesystem.write_project_file("injected.py", "malicious code")

    def test_empty_context_denies_all_capabilities(self, workspace):
        """Plugin with zero capabilities cannot do anything."""
        context = PluginContext(
            plugin_name="empty-plugin",
            granted_capabilities=set(),
            workspace_path=workspace,
        )
        for cap in Capabilities.all():
            assert not context.has_capability(cap.id), (
                f"Empty context should not have capability {cap.id}"
            )

    def test_playwright_preset_cannot_delete_files(self, workspace, tmp_path):
        """Playwright plugin cannot delete project files."""
        from aiqe.plugins.capabilities import PLAYWRIGHT_PLUGIN_CAPABILITIES

        project = tmp_path / "project"
        project.mkdir()

        context = PluginContext(
            plugin_name="playwright-plugin",
            granted_capabilities={
                cap.id for cap in PLAYWRIGHT_PLUGIN_CAPABILITIES
            },
            workspace_path=workspace,
            project_path=project,
        )

        assert not context.has_capability(
            Capabilities.FILESYSTEM_DELETE_PROJECT_FILES.id
        )
        assert not context.has_capability(
            Capabilities.SYSTEM_SHELL.id
        )
        assert not context.has_capability(
            Capabilities.SECRETS_OPENAI_KEY.id
        )

    def test_github_plugin_cannot_access_database(self, workspace):
        """GitHub notification plugin cannot access the database."""
        from aiqe.plugins.capabilities import GITHUB_PLUGIN_CAPABILITIES

        context = PluginContext(
            plugin_name="github-plugin",
            granted_capabilities={
                cap.id for cap in GITHUB_PLUGIN_CAPABILITIES
            },
            workspace_path=workspace,
        )

        assert not context.has_capability(Capabilities.DATABASE_READ.id)
        assert not context.has_capability(Capabilities.DATABASE_DELETE.id)
        assert not context.has_capability(
            Capabilities.SECRETS_DATABASE_CREDENTIALS.id
        )
