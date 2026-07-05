"""
Integration tests for SQLite repository implementations.

These tests use a real SQLite in-memory database to verify
that all repository operations work correctly end-to-end.
"""
import pytest
import uuid
from aiqe.persistence.implementations.sqlite.connection import (
    create_tables, get_sqlite_engine
)
from aiqe.persistence.implementations.sqlite.repositories import (
    SQLiteWorkflowContextRepository,
    SQLiteCheckpointRepository,
    SQLiteBugRepository,
    SQLiteAuditLogRepository,
    SQLiteTestRunRepository,
)


@pytest.fixture
async def engine(tmp_path):
    import aiqe.persistence.implementations.sqlite.connection as conn_mod
    conn_mod._engine = None
    engine = await get_sqlite_engine(tmp_path / "test_aiqe.db")
    await create_tables(engine)
    return engine


@pytest.fixture
def workflow_id():
    return str(uuid.uuid4())


@pytest.fixture
def sample_context(workflow_id):
    return {
        "id": workflow_id,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "trigger": "pr",
        "repository": "owner/repo",
        "branch": "feature/test",
        "pr_number": 42,
        "status": "pending",
        "started_at": None,
        "completed_at": None,
        "duration_seconds": None,
        "error": None,
        "bugs_count": 0,
        "agents_completed": 0,
        "agents_skipped": 0,
        "agent_records": {},
        "workspace_path": "/tmp/test",
    }


class TestSQLiteWorkflowContextRepository:
    @pytest.mark.asyncio
    async def test_save_and_find_by_id(self, engine, sample_context, workflow_id):
        repo = SQLiteWorkflowContextRepository(engine)
        await repo.save(sample_context)
        found = await repo.find_by_id(workflow_id)
        assert found is not None
        assert found["id"] == workflow_id
        assert found["trigger"] == "pr"
        assert found["pr_number"] == 42

    @pytest.mark.asyncio
    async def test_find_by_id_not_found(self, engine):
        repo = SQLiteWorkflowContextRepository(engine)
        result = await repo.find_by_id("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_status(self, engine, sample_context, workflow_id):
        repo = SQLiteWorkflowContextRepository(engine)
        await repo.save(sample_context)
        updated = {**sample_context, "status": "completed", "bugs_count": 3}
        await repo.save(updated)
        found = await repo.find_by_id(workflow_id)
        assert found["status"] == "completed"
        assert found["bugs_count"] == 3

    @pytest.mark.asyncio
    async def test_find_by_repository(self, engine, sample_context):
        repo = SQLiteWorkflowContextRepository(engine)
        await repo.save(sample_context)
        results = await repo.find_by_repository("owner/repo")
        assert len(results) == 1
        assert results[0]["repository"] == "owner/repo"

    @pytest.mark.asyncio
    async def test_find_by_pr(self, engine, sample_context):
        repo = SQLiteWorkflowContextRepository(engine)
        await repo.save(sample_context)
        results = await repo.find_by_pr("owner/repo", 42)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_find_active(self, engine, sample_context, workflow_id):
        repo = SQLiteWorkflowContextRepository(engine)
        running = {**sample_context, "status": "running"}
        await repo.save(running)
        active = await repo.find_active()
        assert any(w["id"] == workflow_id for w in active)

    @pytest.mark.asyncio
    async def test_delete(self, engine, sample_context, workflow_id):
        repo = SQLiteWorkflowContextRepository(engine)
        await repo.save(sample_context)
        deleted = await repo.delete(workflow_id)
        assert deleted is True
        found = await repo.find_by_id(workflow_id)
        assert found is None


class TestSQLiteBugRepository:
    @pytest.mark.asyncio
    async def test_save_and_find_by_workflow(self, engine, workflow_id):
        repo = SQLiteBugRepository(engine)
        bug = {
            "id": str(uuid.uuid4()),
            "workflow_id": workflow_id,
            "severity": "Critical",
            "confidence": 0.97,
            "title": "SQL Injection in login",
            "root_cause": "Unsanitised input",
            "affected_feature": "authentication",
            "affected_files": ["app/auth.py"],
            "suggested_fix": "Use parameterised queries",
            "fix_confidence": 0.95,
            "is_downstream": False,
            "evidence": [],
            "dependency_chain": [],
            "related_tests": [],
            "repository": "owner/repo",
        }
        await repo.save(bug)
        bugs = await repo.find_by_workflow(workflow_id)
        assert len(bugs) == 1
        assert bugs[0]["severity"] == "Critical"
        assert bugs[0]["affected_files"] == ["app/auth.py"]

    @pytest.mark.asyncio
    async def test_count_by_workflow(self, engine, workflow_id):
        repo = SQLiteBugRepository(engine)
        for severity in ["Critical", "High", "High", "Low"]:
            await repo.save({
                "id": str(uuid.uuid4()),
                "workflow_id": workflow_id,
                "severity": severity,
                "confidence": 0.8,
                "title": f"{severity} bug",
                "root_cause": "",
                "affected_feature": "",
                "affected_files": [],
                "suggested_fix": "",
                "fix_confidence": 0.5,
                "is_downstream": False,
                "evidence": [],
                "dependency_chain": [],
                "related_tests": [],
                "repository": "owner/repo",
            })
        counts = await repo.count_by_workflow(workflow_id)
        assert counts.get("Critical") == 1
        assert counts.get("High") == 2
        assert counts.get("Low") == 1


class TestSQLiteAuditLogRepository:
    @pytest.mark.asyncio
    async def test_append_and_find(self, engine, workflow_id):
        repo = SQLiteAuditLogRepository(engine)
        entry = {
            "event_id": str(uuid.uuid4()),
            "event_type": "workflow_started",
            "occurred_at": "2026-01-01T00:00:00+00:00",
            "workflow_id": workflow_id,
            "trigger": "pr",
        }
        await repo.append(workflow_id, entry)
        entries = await repo.find_by_workflow(workflow_id)
        assert len(entries) == 1
        assert entries[0]["event_type"] == "workflow_started"

    @pytest.mark.asyncio
    async def test_append_batch(self, engine, workflow_id):
        repo = SQLiteAuditLogRepository(engine)
        entries = [
            {
                "event_id": str(uuid.uuid4()),
                "event_type": f"event_{i}",
                "occurred_at": "2026-01-01T00:00:00+00:00",
                "workflow_id": workflow_id,
            }
            for i in range(5)
        ]
        await repo.append_batch(workflow_id, entries)
        found = await repo.find_by_workflow(workflow_id)
        assert len(found) == 5

    @pytest.mark.asyncio
    async def test_find_agent_executions(self, engine, workflow_id):
        repo = SQLiteAuditLogRepository(engine)
        for event_type in ["agent_started", "agent_completed", "workflow_started"]:
            await repo.append(workflow_id, {
                "event_id": str(uuid.uuid4()),
                "event_type": event_type,
                "occurred_at": "2026-01-01T00:00:00+00:00",
                "workflow_id": workflow_id,
            })
        agent_events = await repo.find_agent_executions(workflow_id)
        assert len(agent_events) == 2
        types = {e["event_type"] for e in agent_events}
        assert "agent_started" in types
        assert "agent_completed" in types


class TestSQLiteTestRunRepository:
    @pytest.mark.asyncio
    async def test_save_and_find(self, engine, workflow_id):
        repo = SQLiteTestRunRepository(engine)
        run = {
            "id": str(uuid.uuid4()),
            "workflow_id": workflow_id,
            "test_id": "test_login_success",
            "test_name": "Test login with valid credentials",
            "test_type": "e2e",
            "feature": "authentication",
            "passed": True,
            "duration_seconds": 1.23,
            "evidence": [],
            "executed_at": "2026-01-01T00:00:00+00:00",
            "repository": "owner/repo",
        }
        await repo.save(run)
        found = await repo.find_by_workflow(workflow_id)
        assert len(found) == 1
        assert found[0]["test_name"] == "Test login with valid credentials"

    @pytest.mark.asyncio
    async def test_find_failures(self, engine, workflow_id):
        repo = SQLiteTestRunRepository(engine)
        for passed in [True, False, False]:
            await repo.save({
                "id": str(uuid.uuid4()),
                "workflow_id": workflow_id,
                "test_id": f"test_{passed}",
                "test_name": f"Test {'pass' if passed else 'fail'}",
                "test_type": "unit",
                "feature": "auth",
                "passed": passed,
                "duration_seconds": 0.5,
                "evidence": [],
                "executed_at": "2026-01-01T00:00:00+00:00",
                "repository": "owner/repo",
            })
        failures = await repo.find_failures(workflow_id=workflow_id)
        assert len(failures) == 2

    @pytest.mark.asyncio
    async def test_save_batch(self, engine, workflow_id):
        repo = SQLiteTestRunRepository(engine)
        runs = [
            {
                "id": str(uuid.uuid4()),
                "workflow_id": workflow_id,
                "test_id": f"test_{i}",
                "test_name": f"Test {i}",
                "test_type": "unit",
                "feature": "core",
                "passed": i % 2 == 0,
                "duration_seconds": 0.1,
                "evidence": [],
                "executed_at": "2026-01-01T00:00:00+00:00",
                "repository": "owner/repo",
            }
            for i in range(10)
        ]
        await repo.save_batch(runs)
        found = await repo.find_by_workflow(workflow_id)
        assert len(found) == 10
