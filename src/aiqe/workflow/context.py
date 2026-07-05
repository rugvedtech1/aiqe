"""
AIQE Workflow Context.

A WorkflowContext is the isolated execution container for a single
workflow run — one PR, one branch scan, one manual execution, or
one scheduled run. See ADR-006.

Isolation rules (enforced here, never in callers):
    - Each context has its own execution state, agent states,
      shared memory, checkpoints, logs, and artifact paths.
    - No context may read or write another context's mutable state.
    - The Memory & Learning Agent may read historical context data
      in READ-ONLY mode only — this is enforced at the repository
      layer, not here.

Why a dataclass + AggregateRoot?
    WorkflowContext is an Aggregate Root (ADR domain model).
    It owns its AgentExecutionRecords, its checkpoint history,
    and its test results. External code interacts with the context,
    not with the objects it contains directly.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiqe.shared.domain import AggregateRoot
from aiqe.shared.exceptions import WorkflowContextError
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import utcnow
from aiqe.workflow.events import (
    AgentStatus,
    BugFound,
    WorkflowCheckpointed,
    WorkflowCompleted,
    WorkflowFailed,
    WorkflowStarted,
    WorkflowStatus,
)

logger = get_logger(__name__)


@dataclass
class AgentExecutionRecord:
    """
    Records the execution state of one agent within a workflow.

    This is NOT an entity — it has no identity outside the
    WorkflowContext that owns it. It is a value-like record that
    the context uses to track agent progress.

    Attributes:
        agent_name: Registered name of the agent.
        status: Current execution status.
        started_at: When this agent started (None if not yet started).
        completed_at: When this agent finished (None if still running).
        error: Error message if status is FAILED.
        skip_reason: Why the agent was skipped (if SKIPPED).
        blocked_by: Agent name that caused this skip.
        output: Whatever the agent returned (type depends on agent).
        ai_tokens_used: Total tokens consumed by this agent's AI calls.
        duration_seconds: How long the agent ran.
    """
    agent_name: str
    status: AgentStatus = AgentStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    skip_reason: str | None = None
    blocked_by: str | None = None
    output: Any = None
    ai_tokens_used: int = 0
    duration_seconds: float = 0.0

    def mark_running(self) -> None:
        """Transition this record to RUNNING state."""
        self.status = AgentStatus.RUNNING
        self.started_at = utcnow()

    def mark_completed(self, output: Any, ai_tokens_used: int = 0) -> None:
        """Transition this record to COMPLETED state."""
        self.status = AgentStatus.COMPLETED
        self.completed_at = utcnow()
        self.output = output
        self.ai_tokens_used = ai_tokens_used
        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()

    def mark_failed(self, error: str) -> None:
        """Transition this record to FAILED state."""
        self.status = AgentStatus.FAILED
        self.completed_at = utcnow()
        self.error = error
        if self.started_at:
            self.duration_seconds = (
                self.completed_at - self.started_at
            ).total_seconds()

    def mark_skipped(self, reason: str, blocked_by: str) -> None:
        """Transition this record to SKIPPED state."""
        self.status = AgentStatus.SKIPPED
        self.skip_reason = reason
        self.blocked_by = blocked_by

    @property
    def is_terminal(self) -> bool:
        """True if this agent has reached a final state."""
        return self.status in {
            AgentStatus.COMPLETED,
            AgentStatus.FAILED,
            AgentStatus.SKIPPED,
            AgentStatus.TIMEOUT,
        }


@dataclass
class WorkflowContext(AggregateRoot):
    """
    Isolated execution container for a single AIQE workflow run.

    One WorkflowContext is created for each:
    - Pull Request test run
    - Branch scan
    - Local CLI execution
    - Scheduled run
    - Manual execution

    The context owns:
    - Status and lifecycle timestamps
    - All agent execution records
    - Shared memory (key-value store for inter-agent communication)
    - Bug records found during this workflow
    - Audit log entries
    - Paths to generated artifacts

    Isolation contract (ADR-006):
    - This context never reads from or writes to another context.
    - All mutable state is owned by this instance.
    - The workspace_path is unique per context and never shared.

    Attributes:
        trigger: What started this workflow (pr/branch/manual/scheduled).
        repository: Repository being analysed (owner/repo).
        branch: Branch being analysed.
        pr_number: PR number if trigger is 'pr'.
        status: Current lifecycle status.
        workspace_path: Isolated filesystem path for this context's artifacts.
        agent_records: Execution records for each registered agent.
        shared_memory: Key-value store for inter-agent data sharing.
        bugs: All bugs found during this workflow.
        audit_log: Ordered list of all events for ADR-012.
        error: Top-level error if the workflow failed.
        started_at: When this workflow began running.
        completed_at: When this workflow finished.
    """

    trigger: str = "manual"
    repository: str = ""
    branch: str = ""
    pr_number: int | None = None
    status: WorkflowStatus = WorkflowStatus.PENDING
    workspace_path: Path = field(default_factory=lambda: Path(".aiqe/workflows/unknown"))
    agent_records: dict[str, AgentExecutionRecord] = field(default_factory=dict)
    shared_memory: dict[str, Any] = field(default_factory=dict)
    bugs: list[dict[str, Any]] = field(default_factory=list)
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Internal asyncio lock — prevents race conditions when multiple
    # async tasks write to this context simultaneously.
    _lock: asyncio.Lock = field(
        default_factory=asyncio.Lock,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        """Ensure workspace directory exists after construction."""
        self.workspace_path.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # LIFECYCLE METHODS
    # --------------------------------------------------

    async def start(self) -> None:
        """
        Transition the workflow to RUNNING state.

        Records a WorkflowStarted domain event and writes the first
        audit log entry.
        """
        async with self._lock:
            if self.status != WorkflowStatus.PENDING:
                msg = (
                    f"Cannot start workflow {self.id}: "
                    f"current status is {self.status}, expected PENDING."
                )
                raise WorkflowContextError(msg, workflow_id=self.id)

            self.status = WorkflowStatus.RUNNING
            self.started_at = utcnow()

            event = WorkflowStarted(
                workflow_id=self.id,
                trigger=self.trigger,
                repository=self.repository,
                pr_number=self.pr_number,
                branch=self.branch,
            )
            self._append_audit(event.to_dict())
            self.record_event(event)

            logger.info(
                "workflow_started",
                workflow_id=self.id,
                trigger=self.trigger,
                repository=self.repository,
                branch=self.branch,
                pr_number=self.pr_number,
            )

    async def complete(self) -> None:
        """Transition the workflow to COMPLETED state."""
        async with self._lock:
            self.status = WorkflowStatus.COMPLETED
            self.completed_at = utcnow()

            duration = 0.0
            if self.started_at:
                duration = (self.completed_at - self.started_at).total_seconds()

            completed_count = sum(
                1 for r in self.agent_records.values()
                if r.status == AgentStatus.COMPLETED
            )
            skipped_count = sum(
                1 for r in self.agent_records.values()
                if r.status == AgentStatus.SKIPPED
            )

            event = WorkflowCompleted(
                workflow_id=self.id,
                duration_seconds=duration,
                agents_completed=completed_count,
                agents_skipped=skipped_count,
                bugs_found=len(self.bugs),
            )
            self._append_audit(event.to_dict())
            self.record_event(event)

            logger.info(
                "workflow_completed",
                workflow_id=self.id,
                duration_seconds=duration,
                bugs_found=len(self.bugs),
                agents_completed=completed_count,
                agents_skipped=skipped_count,
            )

    async def fail(self, error: str, failed_stage: str = "") -> None:
        """Transition the workflow to FAILED state."""
        async with self._lock:
            self.status = WorkflowStatus.FAILED
            self.error = error
            self.completed_at = utcnow()

            event = WorkflowFailed(
                workflow_id=self.id,
                error_message=error,
                failed_stage=failed_stage,
                is_checkpointed=self._has_checkpoint(),
            )
            self._append_audit(event.to_dict())
            self.record_event(event)

            logger.error(
                "workflow_failed",
                workflow_id=self.id,
                error=error,
                failed_stage=failed_stage,
            )

    async def checkpoint(self, stage: str, checkpoint_id: str) -> None:
        """Record that a checkpoint was saved for this stage."""
        async with self._lock:
            self.status = WorkflowStatus.CHECKPOINTED

            event = WorkflowCheckpointed(
                workflow_id=self.id,
                stage=stage,
                checkpoint_id=checkpoint_id,
            )
            self._append_audit(event.to_dict())
            self.record_event(event)

            logger.info(
                "workflow_checkpointed",
                workflow_id=self.id,
                stage=stage,
                checkpoint_id=checkpoint_id,
            )

    # --------------------------------------------------
    # AGENT RECORD MANAGEMENT
    # --------------------------------------------------

    def register_agent(self, agent_name: str) -> AgentExecutionRecord:
        """
        Register an agent for tracking within this workflow.

        Must be called before the agent is dispatched by the scheduler.

        Args:
            agent_name: The agent's registered name.

        Returns:
            The new AgentExecutionRecord for this agent.
        """
        record = AgentExecutionRecord(agent_name=agent_name)
        self.agent_records[agent_name] = record
        return record

    def get_agent_record(self, agent_name: str) -> AgentExecutionRecord:
        """
        Get the execution record for a specific agent.

        Args:
            agent_name: The agent's registered name.

        Returns:
            The AgentExecutionRecord for this agent.

        Raises:
            WorkflowContextError: If the agent was never registered.
        """
        record = self.agent_records.get(agent_name)
        if record is None:
            msg = (
                f"Agent '{agent_name}' has no execution record in "
                f"workflow {self.id}. Was it registered before dispatch?"
            )
            raise WorkflowContextError(msg, workflow_id=self.id)
        return record

    def get_agent_output(self, agent_name: str) -> Any:
        """
        Get the output produced by a completed agent.

        Used by downstream agents to read the output of their
        dependencies without accessing the record directly.

        Args:
            agent_name: The name of the completed agent.

        Returns:
            Whatever the agent returned as its output.

        Raises:
            WorkflowContextError: If agent is not completed.
        """
        record = self.get_agent_record(agent_name)
        if record.status != AgentStatus.COMPLETED:
            msg = (
                f"Cannot read output of agent '{agent_name}' in "
                f"workflow {self.id}: status is {record.status}, not COMPLETED."
            )
            raise WorkflowContextError(msg, workflow_id=self.id)
        return record.output

    # --------------------------------------------------
    # SHARED MEMORY
    # Inter-agent key-value store. Only this workflow's agents
    # may read/write here. Enforced by passing the context only
    # to agents registered for this workflow.
    # --------------------------------------------------

    async def memory_set(self, key: str, value: Any) -> None:
        """Store a value in this workflow's shared memory."""
        async with self._lock:
            self.shared_memory[key] = value

    async def memory_get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from this workflow's shared memory."""
        return self.shared_memory.get(key, default)

    async def memory_delete(self, key: str) -> None:
        """Delete a key from this workflow's shared memory."""
        async with self._lock:
            self.shared_memory.pop(key, None)

    # --------------------------------------------------
    # BUG RECORDING
    # --------------------------------------------------

    async def record_bug(self, bug: dict[str, Any]) -> None:
        """
        Record a bug found during this workflow.

        Critical bugs (severity=Critical) are flagged for immediate
        notification via the event system. See ADR-008.

        Args:
            bug: Bug dict containing at minimum: id, severity,
                 confidence, title, affected_feature.
        """
        async with self._lock:
            self.bugs.append(bug)

            event = BugFound(
                workflow_id=self.id,
                bug_id=bug.get("id", ""),
                severity=bug.get("severity", ""),
                confidence=bug.get("confidence", 0.0),
                title=bug.get("title", ""),
                affected_feature=bug.get("affected_feature", ""),
                root_cause_agent=bug.get("root_cause_agent", ""),
                is_downstream=bug.get("is_downstream", False),
                root_bug_id=bug.get("root_bug_id"),
            )
            self._append_audit(event.to_dict())
            self.record_event(event)

            logger.info(
                "bug_recorded",
                workflow_id=self.id,
                bug_id=bug.get("id"),
                severity=bug.get("severity"),
                confidence=bug.get("confidence"),
                title=bug.get("title"),
            )

    # --------------------------------------------------
    # AUDIT LOG
    # --------------------------------------------------

    def _append_audit(self, entry: dict[str, Any]) -> None:
        """Append an entry to the immutable audit log."""
        self.audit_log.append(entry)

    def get_audit_log(self) -> list[dict[str, Any]]:
        """
        Return a copy of the audit log.

        Always returns a copy — external callers cannot modify
        the audit log directly.
        """
        return list(self.audit_log)

    # --------------------------------------------------
    # HELPERS
    # --------------------------------------------------

    def _has_checkpoint(self) -> bool:
        """True if any checkpoint events exist in the audit log."""
        return any(
            e.get("event_type") == "workflow_checkpointed"
            for e in self.audit_log
        )

    @property
    def is_terminal(self) -> bool:
        """True if this workflow has reached a final state."""
        return self.status in {
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.CANCELLED,
        }

    @property
    def critical_bugs(self) -> list[dict[str, Any]]:
        """All bugs with severity=Critical found in this workflow."""
        return [b for b in self.bugs if b.get("severity") == "Critical"]

    @property
    def duration_seconds(self) -> float | None:
        """Total duration if the workflow has finished."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this context for persistence."""
        base = super().to_dict()
        return {
            **base,
            "trigger": self.trigger,
            "repository": self.repository,
            "branch": self.branch,
            "pr_number": self.pr_number,
            "status": self.status.value,
            "workspace_path": str(self.workspace_path),
            "bugs_count": len(self.bugs),
            "agent_records": {
                name: {
                    "status": rec.status.value,
                    "duration_seconds": rec.duration_seconds,
                    "error": rec.error,
                    "skip_reason": rec.skip_reason,
                    "blocked_by": rec.blocked_by,
                    "ai_tokens_used": rec.ai_tokens_used,
                }
                for name, rec in self.agent_records.items()
            },
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
        }
