"""Unit tests for PluginContext and sandbox enforcement."""
import pytest
from pathlib import Path
from aiqe.plugins.sandbox import PluginContext, RestrictedFilesystem
from aiqe.plugins.capabilities import Capabilities
from aiqe.shared.exceptions import CapabilityDeniedError


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def project(tmp_path):
    proj = tmp_path / "project"
    proj.mkdir()
    (proj / "main.py").write_text("print('hello')")
    return proj


@pytest.fixture
def context_with_fs(workspace, project):
    return PluginContext(
        plugin_name="test-plugin",
        granted_capabilities={
            Capabilities.FILESYSTEM_READ_PROJECT_FILES.id,
            Capabilities.FILESYSTEM_WRITE_TEMP.id,
        },
        workspace_path=workspace,
        project_path=project,
        workflow_id="wf_test",
    )


@pytest.fixture
def empty_context(workspace):
    return PluginContext(
        plugin_name="empty-plugin",
        granted_capabilities=set(),
        workspace_path=workspace,
        workflow_id="wf_test",
    )


class TestPluginContext:
    def test_has_granted_capability(self, context_with_fs):
        assert context_with_fs.has_capability(
            Capabilities.FILESYSTEM_READ_PROJECT_FILES.id
        )

    def test_does_not_have_ungranted_capability(self, context_with_fs):
        assert not context_with_fs.has_capability(
            Capabilities.SYSTEM_SHELL.id
        )

    def test_assert_capability_raises_when_denied(self, empty_context):
        with pytest.raises(CapabilityDeniedError):
            empty_context.assert_capability(
                Capabilities.BROWSER_NAVIGATE.id
            )

    def test_granted_capability_ids(self, context_with_fs):
        ids = context_with_fs.granted_capability_ids()
        assert Capabilities.FILESYSTEM_READ_PROJECT_FILES.id in ids
        assert Capabilities.FILESYSTEM_WRITE_TEMP.id in ids

    def test_workflow_id_accessible(self, context_with_fs):
        assert context_with_fs.workflow_id == "wf_test"

    def test_plugin_name_accessible(self, context_with_fs):
        assert context_with_fs.plugin_name == "test-plugin"


class TestRestrictedFilesystem:
    def test_read_project_file_with_capability(self, workspace, project):
        fs = RestrictedFilesystem(
            plugin_name="test",
            granted={Capabilities.FILESYSTEM_READ_PROJECT_FILES.id},
            workspace_path=workspace,
            project_path=project,
        )
        content = fs.read_project_file("main.py")
        assert "print" in content

    def test_read_project_file_without_capability_raises(self, workspace, project):
        fs = RestrictedFilesystem(
            plugin_name="test",
            granted=set(),
            workspace_path=workspace,
            project_path=project,
        )
        with pytest.raises(CapabilityDeniedError):
            fs.read_project_file("main.py")

    def test_write_temp_file_with_capability(self, workspace):
        fs = RestrictedFilesystem(
            plugin_name="test",
            granted={Capabilities.FILESYSTEM_WRITE_TEMP.id},
            workspace_path=workspace,
        )
        path = fs.write_temp_file("output.txt", "test content")
        assert path.exists()
        assert path.read_text() == "test content"

    def test_write_temp_file_without_capability_raises(self, workspace):
        fs = RestrictedFilesystem(
            plugin_name="test",
            granted=set(),
            workspace_path=workspace,
        )
        with pytest.raises(CapabilityDeniedError):
            fs.write_temp_file("output.txt", "content")

    def test_delete_temp_file_requires_capability(self, workspace):
        fs = RestrictedFilesystem(
            plugin_name="test",
            granted=set(),
            workspace_path=workspace,
        )
        with pytest.raises(CapabilityDeniedError):
            fs.delete_temp_file("some_file.txt")
