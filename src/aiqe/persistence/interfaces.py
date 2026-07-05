"""
AIQE Repository Interfaces.

These are the ONLY persistence abstractions the domain layer
and agents are allowed to import. No database driver, no SQL,
no ORM-specific types cross this boundary.

Why Python Protocols instead of ABCs?
    Protocols use structural typing (duck typing with type checking).
    Any class that implements the right methods satisfies the Protocol
    without inheriting from it. This means:
    - SQLite and Postgres implementations are completely independent.
    - Test doubles (fakes, mocks) don't need to inherit anything.
    - Third-party storage backends can implement the protocol without
      depending on the AIQE codebase at all.

    ABCs require inheritance. Protocols require only structure.
    For repository interfaces that will have multiple independent
    implementations, Protocols are the correct choice.

Usage:
    # In agent or workflow engine code:
    from aiqe.persistence.interfaces import WorkflowContextRepository

    # The repo is injected — agent never knows if it is SQLite or Postgres
    async def run(self, repo: WorkflowContextRepository) -> None:
        context = await repo.find_by_id(self.workflow_id)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


# ==================================================
# WORKFLOW CONTEXT REPOSITORY
# ==================================================

@runtime_checkable
class WorkflowContextRepository(Protocol):
    """
    Persistence interface for WorkflowContext entities.

    Handles save, retrieval, and status queries for workflow
    execution contexts. Each workflow context is persisted
    immediately when created and updated as its status changes.
    """

    async def save(self, context: dict[str, Any]) -> None:
        """
        Save or update a WorkflowContext.

        Called when a context is created, status changes,
        or the context completes/fails.

        Args:
            context: WorkflowContext.to_dict() output.
        """
        ...

    async def find_by_id(self, workflow_id: str) -> dict[str, Any] | None:
        """
        Retrieve a WorkflowContext by its unique ID.

        Args:
            workflow_id: The unique workflow identifier.

        Returns:
            WorkflowContext dict or None if not found.
        """
        ...

    async def find_by_repository(
        self,
        repository: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Find all workflows for a given repository.

        Args:
            repository: Repository in owner/repo format.
            limit: Maximum results to return.

        Returns:
            List of WorkflowContext dicts, most recent first.
        """
        ...

    async def find_by_pr(
        self,
        repository: str,
        pr_number: int,
    ) -> list[dict[str, Any]]:
        """
        Find all workflows triggered by a specific Pull Request.

        Args:
            repository: Repository in owner/repo format.
            pr_number: The PR number.

        Returns:
            List of WorkflowContext dicts, most recent first.
        """
        ...

    async def find_active(self) -> list[dict[str, Any]]:
        """
        Find all workflows currently in RUNNING or CHECKPOINTED state.

        Used by the engine on startup to detect interrupted workflows
        that need to be resumed.

        Returns:
            List of active WorkflowContext dicts.
        """
        ...

    async def delete(self, workflow_id: str) -> bool:
        """
        Delete a workflow context and all its associated data.

        Used for cleanup of old workflows and test teardown.

        Args:
            workflow_id: The workflow to delete.

        Returns:
            True if deleted, False if not found.
        """
        ...


# ==================================================
# CHECKPOINT REPOSITORY
# ==================================================

@runtime_checkable
class CheckpointRepository(Protocol):
    """
    Persistence interface for workflow stage checkpoints.

    In local/CLI mode, checkpoints are stored as JSON files
    (handled by CheckpointManager directly). This repository
    is used in enterprise mode where checkpoints go to Postgres
    for durability across worker restarts.
    """

    async def save(self, checkpoint: dict[str, Any]) -> None:
        """
        Save a stage checkpoint.

        Args:
            checkpoint: Checkpoint.to_dict() output.
        """
        ...

    async def find_by_workflow(
        self, workflow_id: str
    ) -> list[dict[str, Any]]:
        """
        Find all checkpoints for a workflow in stage order.

        Args:
            workflow_id: The workflow whose checkpoints to retrieve.

        Returns:
            List of checkpoint dicts ordered by stage_index.
        """
        ...

    async def find_by_stage(
        self, workflow_id: str, stage: str
    ) -> dict[str, Any] | None:
        """
        Find a specific stage checkpoint.

        Args:
            workflow_id: The workflow ID.
            stage: The stage name.

        Returns:
            Checkpoint dict or None if not found.
        """
        ...

    async def delete_by_workflow(self, workflow_id: str) -> int:
        """
        Delete all checkpoints for a completed workflow.

        Args:
            workflow_id: The workflow to clean up.

        Returns:
            Number of checkpoints deleted.
        """
        ...


# ==================================================
# BUG REPOSITORY
# ==================================================

@runtime_checkable
class BugRepository(Protocol):
    """
    Persistence interface for bug reports.

    Bugs are written incrementally as they are discovered during
    workflow execution. The Memory & Learning Agent reads historical
    bug data for regression detection.
    """

    async def save(self, bug: dict[str, Any]) -> None:
        """
        Save a bug report.

        Args:
            bug: BugReport.to_dict() output plus workflow_id.
        """
        ...

    async def find_by_workflow(
        self, workflow_id: str
    ) -> list[dict[str, Any]]:
        """
        Find all bugs from a specific workflow.

        Args:
            workflow_id: The workflow to query.

        Returns:
            List of bug dicts ordered by severity (Critical first).
        """
        ...

    async def find_by_severity(
        self,
        severity: str,
        repository: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Find bugs by severity, optionally filtered to a repository.

        Used by the Memory & Learning Agent for regression detection
        and by the Release Intelligence Engine for risk assessment.

        Args:
            severity: Severity level to filter by.
            repository: Optional owner/repo filter.
            limit: Maximum results to return.

        Returns:
            List of bug dicts, most recent first.
        """
        ...

    async def find_by_feature(
        self, feature: str, repository: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Find all bugs affecting a specific business feature.

        Used for historical failure analysis and risk assessment.

        Args:
            feature: Feature name to query.
            repository: Optional owner/repo filter.

        Returns:
            List of bug dicts for this feature, most recent first.
        """
        ...

    async def count_by_workflow(
        self, workflow_id: str
    ) -> dict[str, int]:
        """
        Count bugs by severity for a workflow.

        Returns:
            Dict of severity → count.
            Example: {"Critical": 2, "High": 5, "Medium": 3}
        """
        ...


# ==================================================
# AUDIT LOG REPOSITORY
# ==================================================

@runtime_checkable
class AuditLogRepository(Protocol):
    """
    Persistence interface for workflow audit log entries.

    The audit log is append-only — entries are never updated
    or deleted (except when an entire workflow is deleted).
    See ADR-012.
    """

    async def append(
        self, workflow_id: str, entry: dict[str, Any]
    ) -> None:
        """
        Append a single audit log entry.

        Args:
            workflow_id: The workflow this entry belongs to.
            entry: The audit log entry (DomainEvent.to_dict() output).
        """
        ...

    async def append_batch(
        self, workflow_id: str, entries: list[dict[str, Any]]
    ) -> None:
        """
        Append multiple audit log entries in one operation.

        Used when persisting a completed workflow's in-memory audit
        log to the database in a single transaction.

        Args:
            workflow_id: The workflow these entries belong to.
            entries: List of audit log entry dicts.
        """
        ...

    async def find_by_workflow(
        self,
        workflow_id: str,
        event_type: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Retrieve audit log entries for a workflow.

        Args:
            workflow_id: The workflow to query.
            event_type: Optional filter by event type.
            limit: Maximum entries to return.

        Returns:
            List of audit log entries in chronological order.
        """
        ...

    async def find_agent_executions(
        self, workflow_id: str
    ) -> list[dict[str, Any]]:
        """
        Retrieve all agent_started and agent_completed events.

        Used by the Report Agent to build the execution timeline.

        Args:
            workflow_id: The workflow to query.

        Returns:
            Agent lifecycle events in chronological order.
        """
        ...


# ==================================================
# TEST RUN REPOSITORY
# ==================================================

@runtime_checkable
class TestRunRepository(Protocol):
    """
    Persistence interface for individual test run results.

    Each test case execution produces a TestRun record.
    Historical test runs are used by the Memory & Learning Agent
    for trend analysis and flaky test detection.
    """

    async def save(self, test_run: dict[str, Any]) -> None:
        """
        Save a single test run result.

        Args:
            test_run: Test run dict containing test_id, workflow_id,
                      test_name, passed, duration_seconds, feature,
                      error (if failed), evidence.
        """
        ...

    async def save_batch(
        self, test_runs: list[dict[str, Any]]
    ) -> None:
        """
        Save multiple test runs in one operation.

        More efficient than saving individually for large test suites.

        Args:
            test_runs: List of test run dicts.
        """
        ...

    async def find_by_workflow(
        self, workflow_id: str
    ) -> list[dict[str, Any]]:
        """
        Find all test runs from a specific workflow.

        Args:
            workflow_id: The workflow to query.

        Returns:
            List of test run dicts.
        """
        ...

    async def find_failures(
        self,
        workflow_id: str | None = None,
        feature: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Find failed test runs.

        Args:
            workflow_id: Optional filter by workflow.
            feature: Optional filter by business feature.
            limit: Maximum results.

        Returns:
            List of failed test run dicts, most recent first.
        """
        ...

    async def find_flaky(
        self,
        repository: str,
        min_flake_rate: float = 0.1,
    ) -> list[dict[str, Any]]:
        """
        Find tests that have been flaky (sometimes pass, sometimes fail).

        Used by the Memory & Learning Agent for test quality improvement.

        Args:
            repository: The repository to analyse.
            min_flake_rate: Minimum failure rate to consider a test flaky.

        Returns:
            List of test name + flake rate dicts.
        """
        ...
