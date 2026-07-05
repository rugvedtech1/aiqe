"""Unit tests for CheckpointManager."""
import pytest
from aiqe.workflow.checkpoints import CheckpointManager, WORKFLOW_STAGES
from aiqe.shared.exceptions import CheckpointError


@pytest.fixture
def checkpoint_manager(tmp_path):
    return CheckpointManager(
        workflow_id="wf_test_001",
        workspace_path=tmp_path,
    )


class TestCheckpointManager:
    @pytest.mark.asyncio
    async def test_save_and_restore(self, checkpoint_manager):
        state = {"detected_language": "python", "framework": "fastapi"}
        checkpoint = await checkpoint_manager.save("project_analysis", state)
        assert checkpoint.stage == "project_analysis"
        assert checkpoint.workflow_id == "wf_test_001"

        restored = await checkpoint_manager.restore("project_analysis")
        assert restored is not None
        assert restored.state == state

    @pytest.mark.asyncio
    async def test_restore_missing_returns_none(self, checkpoint_manager):
        result = await checkpoint_manager.restore("project_analysis")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_stage_raises(self, checkpoint_manager):
        with pytest.raises(CheckpointError):
            await checkpoint_manager.save("invalid_stage_name", {})

    @pytest.mark.asyncio
    async def test_get_completed_stages(self, checkpoint_manager):
        await checkpoint_manager.save("project_analysis", {"a": 1})
        await checkpoint_manager.save("test_strategy", {"b": 2})
        completed = await checkpoint_manager.get_completed_stages()
        assert "project_analysis" in completed
        assert "test_strategy" in completed

    @pytest.mark.asyncio
    async def test_get_resume_stage(self, checkpoint_manager):
        await checkpoint_manager.save("project_analysis", {})
        resume = await checkpoint_manager.get_resume_stage()
        assert resume == "dependency_intelligence"

    @pytest.mark.asyncio
    async def test_clear_removes_all_checkpoints(self, checkpoint_manager):
        await checkpoint_manager.save("project_analysis", {})
        await checkpoint_manager.clear()
        result = await checkpoint_manager.restore("project_analysis")
        assert result is None
