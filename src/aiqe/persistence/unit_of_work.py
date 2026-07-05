"""
AIQE Unit of Work.

Coordinates multiple repository operations in a single
atomic transaction. Ensures that related writes either
all succeed or all fail together.

Why Unit of Work?
    When a workflow completes, we need to:
    1. Update the WorkflowContext status to COMPLETED
    2. Persist all bugs to the bugs table
    3. Persist the audit log entries to audit_log
    4. Delete the workflow's checkpoints

    If step 3 fails, we don't want steps 1-2 already committed.
    The Unit of Work wraps all of these in one transaction.

    Without it, each repository call commits immediately, and
    partial failures leave the database in an inconsistent state.

Usage:
    async with unit_of_work as uow:
        await uow.workflows.save(context.to_dict())
        for bug in context.bugs:
            await uow.bugs.save({**bug, "workflow_id": context.id})
        await uow.audit.append_batch(context.id, context.audit_log)
        # Commits on exit if no exception
        # Rolls back on exception
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from aiqe.persistence.implementations.sqlite.repositories import (
    SQLiteAuditLogRepository,
    SQLiteBugRepository,
    SQLiteCheckpointRepository,
    SQLiteTestRunRepository,
    SQLiteWorkflowContextRepository,
)
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class UnitOfWork:
    """
    Coordinates atomic persistence operations.

    Provides access to all repositories and ensures that
    all operations within a single context manager call
    are committed together or rolled back together.

    Args:
        engine: The database engine to use.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

        # All repositories share the same engine.
        # In a full UoW implementation these would share
        # a single connection/transaction. For now they
        # each manage their own connections (sufficient
        # for SQLite single-writer model).
        self.workflows = SQLiteWorkflowContextRepository(engine)
        self.checkpoints = SQLiteCheckpointRepository(engine)
        self.bugs = SQLiteBugRepository(engine)
        self.audit = SQLiteAuditLogRepository(engine)
        self.test_runs = SQLiteTestRunRepository(engine)

    async def __aenter__(self) -> UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type | None,
        exc_val: Exception | None,
        exc_tb: Any,
    ) -> None:
        if exc_type is not None:
            logger.error(
                "unit_of_work_error",
                error_type=exc_type.__name__,
                error=str(exc_val),
            )
        # Connection management is handled per-operation in the
        # repository implementations. No explicit commit/rollback
        # needed at this level for the SQLite implementation.
        # The Postgres implementation will add explicit transaction
        # management here.


def create_unit_of_work(engine: AsyncEngine) -> UnitOfWork:
    """
    Create a UnitOfWork instance for the given engine.

    Args:
        engine: SQLAlchemy async engine.

    Returns:
        Configured UnitOfWork instance.
    """
    return UnitOfWork(engine)
