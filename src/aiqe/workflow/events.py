"""
AIQE Workflow Domain Events.

Every significant state change inside a workflow produces a domain event.
Events serve three purposes in AIQE:

1. Audit Trail (ADR-012)
   Every event is written to the workflow's audit log so the complete
   execution history can be reconstructed later.

2. Internal Communication
   The Workflow Engine publishes events so the Scheduler, Checkpoint
   Manager, and Notification system can react without tight coupling.

3. Release Intelligence Input
   The Release Intelligence Engine reads the event stream to build
   its "what happened in this workflow" report.

Design rules:
   - Events are immutable (frozen dataclasses).
   - Events describe what happened, never what should happen next.
   - Every event carries workflow_id for isolation (ADR-006).
   - Event names are past tense: WorkflowStarted, not WorkflowStart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from aiqe.shared.domain import DomainEvent


# ==================================================
# WORKFLOW STATUS ENUM
# ==================================================


class WorkflowStatus(str, Enum):
    """
    Lifecycle states of a WorkflowContext.

    State transitions:
        PENDING → RUNNING → COMPLETED
                          → FAILED
                          → CANCELLED
        RUNNING → CHECKPOINTED → RUNNING  (resume after provider failure)
    """
    PENDING = "pending"
    RUNNING = "running"
    CHECKPOINTED = "checkpointed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentStatus(str, Enum):
    """Lifecycle states of an agent execution within a workflow."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


class TaskPriority(str, Enum):
    """Priority levels for scheduled agent tasks."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


# ==================================================
# WORKFLOW LIFECYCLE EVENTS
# ==================================================


@dataclass(frozen=True)
class WorkflowStarted(DomainEvent):
    """
    Emitted when a new WorkflowContext begins execution.

    Attributes:
        trigger: What triggered this workflow (pr, branch, manual, scheduled).
        repository: The repository being analysed (owner/repo format).
        pr_number: Pull request number if trigger is 'pr'.
        branch: Branch name being analysed.
    """
    trigger: str = ""
    repository: str = ""
    pr_number: int | None = None
    branch: str = ""

    @property
    def event_type(self) -> str:
        return "workflow_started"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "trigger": self.trigger,
            "repository": self.repository,
            "pr_number": self.pr_number,
            "branch": self.branch,
        }


@dataclass(frozen=True)
class WorkflowCompleted(DomainEvent):
    """
    Emitted when a workflow finishes successfully.

    Attributes:
        duration_seconds: Total workflow execution time.
        agents_completed: Number of agents that completed successfully.
        agents_skipped: Number of agents skipped due to dependency failures.
        tests_executed: Total number of tests executed.
        bugs_found: Total number of bugs found across all severity levels.
    """
    duration_seconds: float = 0.0
    agents_completed: int = 0
    agents_skipped: int = 0
    tests_executed: int = 0
    bugs_found: int = 0

    @property
    def event_type(self) -> str:
        return "workflow_completed"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "duration_seconds": self.duration_seconds,
            "agents_completed": self.agents_completed,
            "agents_skipped": self.agents_skipped,
            "tests_executed": self.tests_executed,
            "bugs_found": self.bugs_found,
        }


@dataclass(frozen=True)
class WorkflowFailed(DomainEvent):
    """
    Emitted when a workflow fails unrecoverably.

    Attributes:
        error_type: The exception class name.
        error_message: Human-readable error description.
        failed_stage: Which stage or agent caused the failure.
        is_checkpointed: Whether the workflow state was saved before failing.
    """
    error_type: str = ""
    error_message: str = ""
    failed_stage: str = ""
    is_checkpointed: bool = False

    @property
    def event_type(self) -> str:
        return "workflow_failed"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "failed_stage": self.failed_stage,
            "is_checkpointed": self.is_checkpointed,
        }


@dataclass(frozen=True)
class WorkflowCheckpointed(DomainEvent):
    """
    Emitted when a workflow saves a checkpoint.

    After this event, the workflow can resume from this stage
    even if the process is killed or the provider fails.

    Attributes:
        stage: The name of the stage that was checkpointed.
        checkpoint_id: Unique ID of the saved checkpoint.
    """
    stage: str = ""
    checkpoint_id: str = ""

    @property
    def event_type(self) -> str:
        return "workflow_checkpointed"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {**base, "stage": self.stage, "checkpoint_id": self.checkpoint_id}


# ==================================================
# AGENT LIFECYCLE EVENTS
# ==================================================


@dataclass(frozen=True)
class AgentStarted(DomainEvent):
    """
    Emitted when an agent begins execution within a workflow.

    Attributes:
        agent_name: The registered name of the agent.
        agent_tier: Which tier this agent belongs to (1-4).
        input_summary: Brief description of agent inputs (no secrets).
    """
    agent_name: str = ""
    agent_tier: int = 1
    input_summary: str = ""

    @property
    def event_type(self) -> str:
        return "agent_started"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "agent_name": self.agent_name,
            "agent_tier": self.agent_tier,
            "input_summary": self.input_summary,
        }


@dataclass(frozen=True)
class AgentCompleted(DomainEvent):
    """
    Emitted when an agent finishes execution successfully.

    Attributes:
        agent_name: The registered name of the agent.
        duration_seconds: How long the agent took to execute.
        output_summary: Brief description of what the agent produced.
        ai_tokens_used: Total tokens consumed by AI calls in this agent.
    """
    agent_name: str = ""
    duration_seconds: float = 0.0
    output_summary: str = ""
    ai_tokens_used: int = 0

    @property
    def event_type(self) -> str:
        return "agent_completed"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "agent_name": self.agent_name,
            "duration_seconds": self.duration_seconds,
            "output_summary": self.output_summary,
            "ai_tokens_used": self.ai_tokens_used,
        }


@dataclass(frozen=True)
class AgentFailed(DomainEvent):
    """
    Emitted when an agent fails during execution.

    The Workflow Engine uses this event to trigger dependency graph
    failure isolation — downstream agents that depend on this agent
    are marked as SKIPPED with a reference to this event.

    Attributes:
        agent_name: The registered name of the failed agent.
        error_type: Exception class name.
        error_message: Human-readable failure description.
        duration_seconds: How long the agent ran before failing.
        affected_downstream: List of agent names that will be skipped.
    """
    agent_name: str = ""
    error_type: str = ""
    error_message: str = ""
    duration_seconds: float = 0.0
    affected_downstream: list[str] = field(default_factory=list)

    @property
    def event_type(self) -> str:
        return "agent_failed"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "agent_name": self.agent_name,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "duration_seconds": self.duration_seconds,
            "affected_downstream": self.affected_downstream,
        }


@dataclass(frozen=True)
class AgentSkipped(DomainEvent):
    """
    Emitted when an agent is skipped due to a dependency failure.

    This is NOT a failure event — the agent did not fail, it was
    skipped because a prerequisite agent failed. The reason field
    explains which dependency failed and why. See ADR-007.

    Attributes:
        agent_name: The agent that was skipped.
        reason: Why this agent was skipped.
        blocked_by: The agent name whose failure caused this skip.
    """
    agent_name: str = ""
    reason: str = ""
    blocked_by: str = ""

    @property
    def event_type(self) -> str:
        return "agent_skipped"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "agent_name": self.agent_name,
            "reason": self.reason,
            "blocked_by": self.blocked_by,
        }


# ==================================================
# TEST EXECUTION EVENTS
# ==================================================


@dataclass(frozen=True)
class TestExecuted(DomainEvent):
    """
    Emitted when a single test case is executed.

    Attributes:
        test_id: Unique identifier for the test case.
        test_name: Human-readable test name.
        test_type: Category (unit, integration, e2e, api, security, etc.)
        passed: Whether the test passed.
        duration_seconds: Test execution time.
        feature: The business feature this test covers.
    """
    test_id: str = ""
    test_name: str = ""
    test_type: str = ""
    passed: bool = False
    duration_seconds: float = 0.0
    feature: str = ""

    @property
    def event_type(self) -> str:
        return "test_executed"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "test_id": self.test_id,
            "test_name": self.test_name,
            "test_type": self.test_type,
            "passed": self.passed,
            "duration_seconds": self.duration_seconds,
            "feature": self.feature,
        }


# ==================================================
# BUG EVENTS
# ==================================================


@dataclass(frozen=True)
class BugFound(DomainEvent):
    """
    Emitted when the Bug Analysis Agent identifies a bug.

    Critical bugs also trigger the immediate notification path
    (ADR-008). All others are included in the final report.

    Attributes:
        bug_id: Unique identifier for this bug.
        severity: Critical / High / Medium / Low / Informational.
        confidence: AI confidence score 0.0-1.0.
        title: Short description of the bug.
        affected_feature: Which business feature is affected.
        root_cause_agent: Which agent discovered this bug.
        is_downstream: Whether this is a downstream effect of another bug.
        root_bug_id: If downstream, the ID of the root cause bug.
    """
    bug_id: str = ""
    severity: str = ""
    confidence: float = 0.0
    title: str = ""
    affected_feature: str = ""
    root_cause_agent: str = ""
    is_downstream: bool = False
    root_bug_id: str | None = None

    @property
    def event_type(self) -> str:
        return "bug_found"

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "bug_id": self.bug_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "title": self.title,
            "affected_feature": self.affected_feature,
            "root_cause_agent": self.root_cause_agent,
            "is_downstream": self.is_downstream,
            "root_bug_id": self.root_bug_id,
        }
