"""Unit tests for workflow domain events."""
import pytest
from aiqe.workflow.events import (
    AgentCompleted,
    AgentFailed,
    AgentSkipped,
    AgentStarted,
    AgentStatus,
    BugFound,
    WorkflowCompleted,
    WorkflowFailed,
    WorkflowStarted,
    WorkflowStatus,
)


class TestWorkflowStatus:
    def test_all_statuses_exist(self):
        assert WorkflowStatus.PENDING
        assert WorkflowStatus.RUNNING
        assert WorkflowStatus.COMPLETED
        assert WorkflowStatus.FAILED
        assert WorkflowStatus.CANCELLED
        assert WorkflowStatus.CHECKPOINTED


class TestWorkflowStarted:
    def test_event_type(self):
        event = WorkflowStarted(
            workflow_id="wf_1",
            trigger="pr",
            repository="owner/repo",
            pr_number=42,
        )
        assert event.event_type == "workflow_started"

    def test_to_dict_includes_all_fields(self):
        event = WorkflowStarted(
            workflow_id="wf_1",
            trigger="pr",
            repository="owner/repo",
            pr_number=42,
            branch="feature/test",
        )
        d = event.to_dict()
        assert d["trigger"] == "pr"
        assert d["repository"] == "owner/repo"
        assert d["pr_number"] == 42
        assert d["event_type"] == "workflow_started"

    def test_immutable(self):
        event = WorkflowStarted(workflow_id="wf_1")
        with pytest.raises((AttributeError, TypeError)):
            event.trigger = "manual"  # type: ignore


class TestAgentFailed:
    def test_carries_affected_downstream(self):
        event = AgentFailed(
            workflow_id="wf_1",
            agent_name="project_analysis",
            error_type="TimeoutError",
            error_message="timed out after 30s",
            affected_downstream=["test_strategy", "test_case_generator"],
        )
        assert "test_strategy" in event.affected_downstream
        d = event.to_dict()
        assert d["agent_name"] == "project_analysis"
        assert len(d["affected_downstream"]) == 2


class TestBugFound:
    def test_downstream_bug_has_root_bug_id(self):
        event = BugFound(
            workflow_id="wf_1",
            bug_id="bug_002",
            severity="High",
            confidence=0.85,
            is_downstream=True,
            root_bug_id="bug_001",
        )
        assert event.is_downstream is True
        assert event.root_bug_id == "bug_001"
        d = event.to_dict()
        assert d["severity"] == "High"
        assert d["confidence"] == 0.85
