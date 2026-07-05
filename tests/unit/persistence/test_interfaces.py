"""Unit tests verifying implementations satisfy Protocol interfaces."""
import pytest
from aiqe.persistence.interfaces import (
    AuditLogRepository,
    BugRepository,
    CheckpointRepository,
    TestRunRepository,
    WorkflowContextRepository,
)


class TestProtocolSatisfaction:
    """
    Verify SQLite implementations satisfy Protocol interfaces
    using isinstance() checks (enabled by runtime_checkable).
    """

    @pytest.mark.asyncio
    async def test_sqlite_workflow_repo_satisfies_protocol(self, tmp_path):
        from aiqe.persistence.implementations.sqlite.connection import (
            create_tables, get_sqlite_engine
        )
        from aiqe.persistence.implementations.sqlite.repositories import (
            SQLiteWorkflowContextRepository
        )
        # Reset singleton for test isolation
        import aiqe.persistence.implementations.sqlite.connection as conn_mod
        conn_mod._engine = None

        engine = await get_sqlite_engine(tmp_path / "test.db")
        await create_tables(engine)
        repo = SQLiteWorkflowContextRepository(engine)
        assert isinstance(repo, WorkflowContextRepository)

    @pytest.mark.asyncio
    async def test_sqlite_bug_repo_satisfies_protocol(self, tmp_path):
        from aiqe.persistence.implementations.sqlite.connection import (
            create_tables, get_sqlite_engine
        )
        from aiqe.persistence.implementations.sqlite.repositories import (
            SQLiteBugRepository
        )
        import aiqe.persistence.implementations.sqlite.connection as conn_mod
        conn_mod._engine = None

        engine = await get_sqlite_engine(tmp_path / "test.db")
        await create_tables(engine)
        repo = SQLiteBugRepository(engine)
        assert isinstance(repo, BugRepository)
