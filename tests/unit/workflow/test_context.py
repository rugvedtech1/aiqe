"""Unit tests for WorkflowContext."""
import asyncio
import pytest
from aiqe.workflow.context import WorkflowContext, AgentExecutionRecord
from aiqe.workflow.events import AgentStatus, WorkflowStatus
from aiqe.shared.exceptions import WorkflowContextError


@pytest.fixture
def context(tmp_path):
    ctx = WorkflowContext(
        trigger="manual",
        repository="owner/repo",
        branch="develop",
    )
    ctx.workspace_path = tmp_path / ctx.id
    ctx.workspace_path.mkdir()
    return ctx


class TestWorkflowContextLifecycle:
    def test_initial_status_is_pending(self, context):
        assert context.status == WorkflowStatus.PENDING

    @pytest.mark.asyncio
    async def test_start_transitions_to_running(self, context):
        await context.start()
        assert context.status == WorkflowStatus.RUNNING
        assert context.started_at is not None

    @pytest.mark.asyncio
    async def test_cannot_start_twice(self, context):
        await context.start()
        with pytest.raises(WorkflowContextError):
            await context.start()

    @pytest.mark.asyncio
    async def test_complete_transitions_correctly(self, context):
        await context.start()
        await context.complete()
        assert context.status == WorkflowStatus.COMPLETED
        assert context.completed_at is not None
        assert context.is_terminal

    @pytest.mark.asyncio
    async def test_fail_transitions_correctly(self, context):
        await context.start()
        await context.fail("provider unavailable", failed_stage="test_strategy")
        assert context.status == WorkflowStatus.FAILED
        assert context.error == "provider unavailable"
        assert context.is_terminal


class TestAgentRecords:
    def test_register_agent(self, context):
        record = context.register_agent("project_analysis")
        assert record.agent_name == "project_analysis"
        assert record.status == AgentStatus.PENDING

    def test_get_agent_record(self, context):
        context.register_agent("test_strategy")
        record = context.get_agent_record("test_strategy")
        assert record.agent_name == "test_strategy"

    def test_get_unregistered_agent_raises(self, context):
        with pytest.raises(WorkflowContextError):
            context.get_agent_record("nonexistent_agent")

    def test_get_output_of_incomplete_agent_raises(self, context):
        context.register_agent("project_analysis")
        with pytest.raises(WorkflowContextError):
            context.get_agent_output("project_analysis")

    def test_get_output_of_completed_agent(self, context):
        context.register_agent("project_analysis")
        record = context.get_agent_record("project_analysis")
        record.mark_completed(output={"language": "python"})
        output = context.get_agent_output("project_analysis")
        assert output == {"language": "python"}


class TestSharedMemory:
    @pytest.mark.asyncio
    async def test_set_and_get(self, context):
        await context.memory_set("feature_graph", {"nodes": 5})
        result = await context.memory_get("feature_graph")
        assert result == {"nodes": 5}

    @pytest.mark.asyncio
    async def test_get_missing_key_returns_default(self, context):
        result = await context.memory_get("missing_key", default="fallback")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_delete_key(self, context):
        await context.memory_set("temp", "value")
        await context.memory_delete("temp")
        result = await context.memory_get("temp")
        assert result is None


class TestBugRecording:
    @pytest.mark.asyncio
    async def test_record_bug(self, context):
        bug = {
            "id": "bug_001",
            "severity": "Critical",
            "confidence": 0.97,
            "title": "SQL Injection in login endpoint",
            "affected_feature": "authentication",
        }
        await context.record_bug(bug)
        assert len(context.bugs) == 1
        assert len(context.critical_bugs) == 1

    @pytest.mark.asyncio
    async def test_non_critical_bug_not_in_critical_list(self, context):
        bug = {"id": "b2", "severity": "Low", "confidence": 0.7, "title": "t"}
        await context.record_bug(bug)
        assert len(context.critical_bugs) == 0
