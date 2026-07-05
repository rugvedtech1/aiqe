"""
AIQE Persistence Factory.

Creates the correct repository implementations based on
the configured database mode (SQLite or Postgres).

This is the only place in AIQE that checks the database mode
config and selects an implementation. All other code receives
repositories through dependency injection and never checks
the config directly.

Why a factory instead of direct instantiation?
    If agent code directly imports SQLiteWorkflowContextRepository,
    switching to Postgres requires changing every agent import.
    With a factory, the switch happens in one place: here.
    All agent and workflow code receives the same interface
    regardless of the backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine

from aiqe.persistence.implementations.sqlite.connection import (
    create_tables,
    get_sqlite_engine,
)
from aiqe.persistence.implementations.sqlite.repositories import (
    SQLiteAuditLogRepository,
    SQLiteBugRepository,
    SQLiteCheckpointRepository,
    SQLiteTestRunRepository,
    SQLiteWorkflowContextRepository,
)
from aiqe.persistence.interfaces import (
    AuditLogRepository,
    BugRepository,
    CheckpointRepository,
    TestRunRepository,
    WorkflowContextRepository,
)
from aiqe.persistence.unit_of_work import UnitOfWork, create_unit_of_work
from aiqe.shared.config import DatabaseMode, get_settings
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RepositoryBundle:
    """
    A complete set of all repository implementations.

    Passed to the Workflow Engine and agents via dependency
    injection. All repositories in a bundle use the same
    underlying engine/connection pool.

    Attributes:
        workflows: WorkflowContext persistence.
        checkpoints: Stage checkpoint persistence.
        bugs: Bug report persistence.
        audit: Audit log persistence (append-only).
        test_runs: Test run result persistence.
        engine: The underlying database engine.
    """
    workflows: WorkflowContextRepository
    checkpoints: CheckpointRepository
    bugs: BugRepository
    audit: AuditLogRepository
    test_runs: TestRunRepository
    engine: AsyncEngine

    def unit_of_work(self) -> UnitOfWork:
        """Create a UnitOfWork for coordinated atomic operations."""
        return create_unit_of_work(self.engine)


async def create_repository_bundle() -> RepositoryBundle:
    """
    Create a RepositoryBundle configured from environment settings.

    Reads AIQE_DATABASE_MODE from config and creates the
    appropriate implementations. Creates all tables on first run.

    Returns:
        Configured RepositoryBundle ready for use.

    Raises:
        ConfigurationError: If database config is invalid.
        PersistenceError: If database connection or table creation fails.
    """
    settings = get_settings()
    mode = settings.database.mode

    if mode == DatabaseMode.SQLITE:
        engine = await get_sqlite_engine(settings.database.sqlite_path)
        await create_tables(engine)

        bundle = RepositoryBundle(
            workflows=SQLiteWorkflowContextRepository(engine),
            checkpoints=SQLiteCheckpointRepository(engine),
            bugs=SQLiteBugRepository(engine),
            audit=SQLiteAuditLogRepository(engine),
            test_runs=SQLiteTestRunRepository(engine),
            engine=engine,
        )

        logger.info(
            "repository_bundle_created",
            mode="sqlite",
            db_path=str(settings.database.sqlite_path),
        )
        return bundle

    elif mode == DatabaseMode.POSTGRES:
        # Postgres implementation coming in enterprise phase
        # For now raise a clear error rather than silently falling back
        from aiqe.shared.exceptions import ConfigurationError
        msg = (
            "PostgreSQL mode is not yet implemented. "
            "Set AIQE_DATABASE_MODE=sqlite for local development."
        )
        raise ConfigurationError(msg)

    else:
        from aiqe.shared.exceptions import ConfigurationError
        msg = f"Unknown database mode: {mode}"
        raise ConfigurationError(msg)


# Module-level bundle singleton
_bundle: RepositoryBundle | None = None


async def get_repository_bundle() -> RepositoryBundle:
    """
    Get the global RepositoryBundle singleton.

    Initializes on first call. Subsequent calls return the
    cached bundle without re-initializing.

    Returns:
        The global RepositoryBundle.
    """
    global _bundle
    if _bundle is None:
        _bundle = await create_repository_bundle()
    return _bundle
