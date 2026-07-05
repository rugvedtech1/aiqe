"""
AIQE SQLite Repository Implementations.

Concrete implementations of all repository interfaces using
SQLAlchemy Core with aiosqlite for async SQLite access.

These implementations satisfy the Protocol interfaces defined
in persistence/interfaces.py without inheriting from them.
Structural typing via Protocol means no inheritance needed.

Data serialization:
    Complex fields (agent_records, evidence, dependency_chain, etc.)
    are serialized as JSON strings for SQLite storage and
    deserialized back to Python objects on read. SQLite has no
    native JSON column type — we use TEXT.

    Postgres implementations (Step 8.4) use JSONB for better
    query performance on JSON fields.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from aiqe.persistence.models import (
    audit_log,
    bugs,
    checkpoints,
    test_runs,
    workflow_contexts,
)
from aiqe.shared.exceptions import PersistenceError, RecordNotFoundError
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import utcnow

logger = get_logger(__name__)


def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return utcnow().isoformat()


def _json(value: Any) -> str:
    """Serialize value to JSON string."""
    return json.dumps(value, default=str)


def _from_json(value: str | None) -> Any:
    """Deserialize JSON string to Python object."""
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


class SQLiteWorkflowContextRepository:
    """
    SQLite implementation of WorkflowContextRepository.

    Args:
        engine: SQLAlchemy async engine connected to SQLite.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save(self, context: dict[str, Any]) -> None:
        """Save or update a WorkflowContext."""
        try:
            async with self._engine.begin() as conn:
                # Check if record exists
                existing = await conn.execute(
                    select(workflow_contexts.c.id).where(
                        workflow_contexts.c.id == context["id"]
                    )
                )
                row = existing.fetchone()

                if row:
                    # Update existing record
                    await conn.execute(
                        update(workflow_contexts)
                        .where(workflow_contexts.c.id == context["id"])
                        .values(
                            updated_at=_now_iso(),
                            status=context.get("status", "pending"),
                            started_at=context.get("started_at"),
                            completed_at=context.get("completed_at"),
                            duration_seconds=context.get("duration_seconds"),
                            error=context.get("error"),
                            bugs_count=context.get("bugs_count", 0),
                            agents_completed=context.get("agents_completed", 0),
                            agents_skipped=context.get("agents_skipped", 0),
                            agent_records=_json(
                                context.get("agent_records", {})
                            ),
                        )
                    )
                else:
                    # Insert new record
                    await conn.execute(
                        insert(workflow_contexts).values(
                            id=context["id"],
                            created_at=context.get("created_at", _now_iso()),
                            updated_at=_now_iso(),
                            trigger=context.get("trigger", "manual"),
                            repository=context.get("repository", ""),
                            branch=context.get("branch", ""),
                            pr_number=context.get("pr_number"),
                            status=context.get("status", "pending"),
                            started_at=context.get("started_at"),
                            completed_at=context.get("completed_at"),
                            duration_seconds=context.get("duration_seconds"),
                            error=context.get("error"),
                            bugs_count=context.get("bugs_count", 0),
                            agents_completed=context.get("agents_completed", 0),
                            agents_skipped=context.get("agents_skipped", 0),
                            agent_records=_json(
                                context.get("agent_records", {})
                            ),
                            workspace_path=context.get("workspace_path", ""),
                        )
                    )

            logger.debug(
                "workflow_context_saved",
                workflow_id=context["id"],
                status=context.get("status"),
            )

        except Exception as e:
            msg = f"Failed to save WorkflowContext {context.get('id')}: {e}"
            logger.error("workflow_context_save_failed", error=str(e))
            raise PersistenceError(msg) from e

    async def find_by_id(
        self, workflow_id: str
    ) -> dict[str, Any] | None:
        """Retrieve a WorkflowContext by ID."""
        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(
                    select(workflow_contexts).where(
                        workflow_contexts.c.id == workflow_id
                    )
                )
                row = result.mappings().fetchone()
                if row is None:
                    return None
                return self._row_to_dict(dict(row))
        except Exception as e:
            msg = f"Failed to find WorkflowContext {workflow_id}: {e}"
            raise PersistenceError(msg) from e

    async def find_by_repository(
        self, repository: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Find workflows for a repository, most recent first."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(workflow_contexts)
                .where(workflow_contexts.c.repository == repository)
                .order_by(workflow_contexts.c.created_at.desc())
                .limit(limit)
            )
            return [
                self._row_to_dict(dict(row))
                for row in result.mappings().fetchall()
            ]

    async def find_by_pr(
        self, repository: str, pr_number: int
    ) -> list[dict[str, Any]]:
        """Find workflows triggered by a specific PR."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(workflow_contexts)
                .where(
                    workflow_contexts.c.repository == repository,
                    workflow_contexts.c.pr_number == pr_number,
                )
                .order_by(workflow_contexts.c.created_at.desc())
            )
            return [
                self._row_to_dict(dict(row))
                for row in result.mappings().fetchall()
            ]

    async def find_active(self) -> list[dict[str, Any]]:
        """Find all running or checkpointed workflows."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(workflow_contexts)
                .where(
                    workflow_contexts.c.status.in_(
                        ["running", "checkpointed"]
                    )
                )
                .order_by(workflow_contexts.c.created_at.asc())
            )
            return [
                self._row_to_dict(dict(row))
                for row in result.mappings().fetchall()
            ]

    async def delete(self, workflow_id: str) -> bool:
        """Delete a workflow context."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                delete(workflow_contexts).where(
                    workflow_contexts.c.id == workflow_id
                )
            )
            return result.rowcount > 0

    def _row_to_dict(self, row: dict[str, Any]) -> dict[str, Any]:
        """Convert a database row to a domain dict."""
        row["agent_records"] = _from_json(row.get("agent_records", "{}"))
        return row


class SQLiteCheckpointRepository:
    """SQLite implementation of CheckpointRepository."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save(self, checkpoint: dict[str, Any]) -> None:
        """Save or update a stage checkpoint."""
        try:
            async with self._engine.begin() as conn:
                existing = await conn.execute(
                    select(checkpoints.c.id).where(
                        checkpoints.c.workflow_id == checkpoint["workflow_id"],
                        checkpoints.c.stage == checkpoint["stage"],
                    )
                )
                row = existing.fetchone()

                if row:
                    await conn.execute(
                        update(checkpoints)
                        .where(
                            checkpoints.c.workflow_id == checkpoint["workflow_id"],
                            checkpoints.c.stage == checkpoint["stage"],
                        )
                        .values(
                            state=_json(checkpoint.get("state", {})),
                            saved_at=checkpoint.get("saved_at", _now_iso()),
                        )
                    )
                else:
                    await conn.execute(
                        insert(checkpoints).values(
                            id=checkpoint.get("id", str(uuid.uuid4())),
                            workflow_id=checkpoint["workflow_id"],
                            stage=checkpoint["stage"],
                            stage_index=checkpoint.get("stage_index", 0),
                            state=_json(checkpoint.get("state", {})),
                            saved_at=checkpoint.get("saved_at", _now_iso()),
                        )
                    )
        except Exception as e:
            msg = f"Failed to save checkpoint: {e}"
            raise PersistenceError(msg) from e

    async def find_by_workflow(
        self, workflow_id: str
    ) -> list[dict[str, Any]]:
        """Find all checkpoints for a workflow in stage order."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(checkpoints)
                .where(checkpoints.c.workflow_id == workflow_id)
                .order_by(checkpoints.c.stage_index.asc())
            )
            rows = result.mappings().fetchall()
            return [
                {**dict(row), "state": _from_json(row["state"])}
                for row in rows
            ]

    async def find_by_stage(
        self, workflow_id: str, stage: str
    ) -> dict[str, Any] | None:
        """Find a specific stage checkpoint."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(checkpoints).where(
                    checkpoints.c.workflow_id == workflow_id,
                    checkpoints.c.stage == stage,
                )
            )
            row = result.mappings().fetchone()
            if row is None:
                return None
            return {**dict(row), "state": _from_json(row["state"])}

    async def delete_by_workflow(self, workflow_id: str) -> int:
        """Delete all checkpoints for a workflow."""
        async with self._engine.begin() as conn:
            result = await conn.execute(
                delete(checkpoints).where(
                    checkpoints.c.workflow_id == workflow_id
                )
            )
            return result.rowcount


class SQLiteBugRepository:
    """SQLite implementation of BugRepository."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save(self, bug: dict[str, Any]) -> None:
        """Save a bug report."""
        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    insert(bugs).values(
                        id=bug.get("id", str(uuid.uuid4())),
                        workflow_id=bug["workflow_id"],
                        created_at=bug.get("created_at", _now_iso()),
                        severity=bug.get("severity", "Medium"),
                        confidence=bug.get("confidence", 0.0),
                        title=bug.get("title", ""),
                        root_cause=bug.get("root_cause", ""),
                        affected_feature=bug.get("affected_feature", ""),
                        affected_files=_json(bug.get("affected_files", [])),
                        suggested_fix=bug.get("suggested_fix", ""),
                        fix_confidence=bug.get("fix_confidence", 0.0),
                        is_downstream=bug.get("is_downstream", False),
                        root_bug_id=bug.get("root_bug_id"),
                        evidence=_json(bug.get("evidence", [])),
                        dependency_chain=_json(
                            bug.get("dependency_chain", [])
                        ),
                        related_tests=_json(bug.get("related_tests", [])),
                        repository=bug.get("repository", ""),
                    )
                )
        except Exception as e:
            msg = f"Failed to save bug {bug.get('id')}: {e}"
            raise PersistenceError(msg) from e

    async def find_by_workflow(
        self, workflow_id: str
    ) -> list[dict[str, Any]]:
        """Find all bugs from a workflow, Critical first."""
        severity_order = {
            "Critical": 0, "High": 1,
            "Medium": 2, "Low": 3, "Informational": 4,
        }
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(bugs)
                .where(bugs.c.workflow_id == workflow_id)
            )
            rows = [self._row_to_dict(dict(r))
                    for r in result.mappings().fetchall()]
            return sorted(
                rows,
                key=lambda b: severity_order.get(b.get("severity", ""), 99),
            )

    async def find_by_severity(
        self,
        severity: str,
        repository: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Find bugs by severity."""
        async with self._engine.connect() as conn:
            query = select(bugs).where(bugs.c.severity == severity)
            if repository:
                query = query.where(bugs.c.repository == repository)
            query = query.order_by(
                bugs.c.created_at.desc()
            ).limit(limit)
            result = await conn.execute(query)
            return [
                self._row_to_dict(dict(r))
                for r in result.mappings().fetchall()
            ]

    async def find_by_feature(
        self, feature: str, repository: str | None = None
    ) -> list[dict[str, Any]]:
        """Find bugs affecting a feature."""
        async with self._engine.connect() as conn:
            query = select(bugs).where(
                bugs.c.affected_feature == feature
            )
            if repository:
                query = query.where(bugs.c.repository == repository)
            query = query.order_by(bugs.c.created_at.desc())
            result = await conn.execute(query)
            return [
                self._row_to_dict(dict(r))
                for r in result.mappings().fetchall()
            ]

    async def count_by_workflow(
        self, workflow_id: str
    ) -> dict[str, int]:
        """Count bugs by severity for a workflow."""
        from sqlalchemy import func
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(
                    bugs.c.severity,
                    func.count(bugs.c.id).label("count"),
                )
                .where(bugs.c.workflow_id == workflow_id)
                .group_by(bugs.c.severity)
            )
            return {row["severity"]: row["count"]
                    for row in result.mappings().fetchall()}

    def _row_to_dict(self, row: dict[str, Any]) -> dict[str, Any]:
        """Deserialize JSON fields in a bug row."""
        row["affected_files"] = _from_json(row.get("affected_files", "[]"))
        row["evidence"] = _from_json(row.get("evidence", "[]"))
        row["dependency_chain"] = _from_json(
            row.get("dependency_chain", "[]")
        )
        row["related_tests"] = _from_json(row.get("related_tests", "[]"))
        return row


class SQLiteAuditLogRepository:
    """SQLite implementation of AuditLogRepository."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def append(
        self, workflow_id: str, entry: dict[str, Any]
    ) -> None:
        """Append a single audit log entry."""
        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    insert(audit_log).values(
                        id=str(uuid.uuid4()),
                        workflow_id=workflow_id,
                        event_id=entry.get("event_id", str(uuid.uuid4())),
                        event_type=entry.get("event_type", "unknown"),
                        occurred_at=entry.get("occurred_at", _now_iso()),
                        payload=_json(entry),
                    )
                )
        except Exception as e:
            msg = f"Failed to append audit log entry: {e}"
            raise PersistenceError(msg) from e

    async def append_batch(
        self, workflow_id: str, entries: list[dict[str, Any]]
    ) -> None:
        """Append multiple audit log entries in one transaction."""
        if not entries:
            return
        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    insert(audit_log),
                    [
                        {
                            "id": str(uuid.uuid4()),
                            "workflow_id": workflow_id,
                            "event_id": e.get(
                                "event_id", str(uuid.uuid4())
                            ),
                            "event_type": e.get("event_type", "unknown"),
                            "occurred_at": e.get("occurred_at", _now_iso()),
                            "payload": _json(e),
                        }
                        for e in entries
                    ],
                )
        except Exception as e:
            msg = f"Failed to batch append audit log: {e}"
            raise PersistenceError(msg) from e

    async def find_by_workflow(
        self,
        workflow_id: str,
        event_type: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Retrieve audit log entries for a workflow."""
        async with self._engine.connect() as conn:
            query = select(audit_log).where(
                audit_log.c.workflow_id == workflow_id
            )
            if event_type:
                query = query.where(
                    audit_log.c.event_type == event_type
                )
            query = query.order_by(
                audit_log.c.occurred_at.asc()
            ).limit(limit)
            result = await conn.execute(query)
            return [
                _from_json(row["payload"])
                for row in result.mappings().fetchall()
            ]

    async def find_agent_executions(
        self, workflow_id: str
    ) -> list[dict[str, Any]]:
        """Retrieve agent lifecycle events for a workflow."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(audit_log)
                .where(
                    audit_log.c.workflow_id == workflow_id,
                    audit_log.c.event_type.in_(
                        ["agent_started", "agent_completed",
                         "agent_failed", "agent_skipped"]
                    ),
                )
                .order_by(audit_log.c.occurred_at.asc())
            )
            return [
                _from_json(row["payload"])
                for row in result.mappings().fetchall()
            ]


class SQLiteTestRunRepository:
    """SQLite implementation of TestRunRepository."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save(self, test_run: dict[str, Any]) -> None:
        """Save a single test run result."""
        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    insert(test_runs).values(
                        id=test_run.get("id", str(uuid.uuid4())),
                        workflow_id=test_run["workflow_id"],
                        test_id=test_run.get("test_id", ""),
                        test_name=test_run.get("test_name", ""),
                        test_type=test_run.get("test_type", ""),
                        feature=test_run.get("feature", ""),
                        passed=test_run.get("passed", False),
                        duration_seconds=test_run.get(
                            "duration_seconds", 0.0
                        ),
                        error=test_run.get("error"),
                        evidence=_json(test_run.get("evidence", [])),
                        executed_at=test_run.get("executed_at", _now_iso()),
                        repository=test_run.get("repository", ""),
                    )
                )
        except Exception as e:
            msg = f"Failed to save test run: {e}"
            raise PersistenceError(msg) from e

    async def save_batch(
        self, test_runs_data: list[dict[str, Any]]
    ) -> None:
        """Save multiple test runs in one transaction."""
        if not test_runs_data:
            return
        try:
            async with self._engine.begin() as conn:
                await conn.execute(
                    insert(test_runs),
                    [
                        {
                            "id": tr.get("id", str(uuid.uuid4())),
                            "workflow_id": tr["workflow_id"],
                            "test_id": tr.get("test_id", ""),
                            "test_name": tr.get("test_name", ""),
                            "test_type": tr.get("test_type", ""),
                            "feature": tr.get("feature", ""),
                            "passed": tr.get("passed", False),
                            "duration_seconds": tr.get(
                                "duration_seconds", 0.0
                            ),
                            "error": tr.get("error"),
                            "evidence": _json(tr.get("evidence", [])),
                            "executed_at": tr.get(
                                "executed_at", _now_iso()
                            ),
                            "repository": tr.get("repository", ""),
                        }
                        for tr in test_runs_data
                    ],
                )
        except Exception as e:
            msg = f"Failed to batch save test runs: {e}"
            raise PersistenceError(msg) from e

    async def find_by_workflow(
        self, workflow_id: str
    ) -> list[dict[str, Any]]:
        """Find all test runs for a workflow."""
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(test_runs).where(
                    test_runs.c.workflow_id == workflow_id
                )
            )
            return [
                self._row_to_dict(dict(r))
                for r in result.mappings().fetchall()
            ]

    async def find_failures(
        self,
        workflow_id: str | None = None,
        feature: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Find failed test runs."""
        async with self._engine.connect() as conn:
            query = select(test_runs).where(
                test_runs.c.passed == False  # noqa: E712
            )
            if workflow_id:
                query = query.where(
                    test_runs.c.workflow_id == workflow_id
                )
            if feature:
                query = query.where(
                    test_runs.c.feature == feature
                )
            query = query.order_by(
                test_runs.c.executed_at.desc()
            ).limit(limit)
            result = await conn.execute(query)
            return [
                self._row_to_dict(dict(r))
                for r in result.mappings().fetchall()
            ]

    async def find_flaky(
        self,
        repository: str,
        min_flake_rate: float = 0.1,
    ) -> list[dict[str, Any]]:
        """Find flaky tests by analysing historical pass/fail rates."""
        from sqlalchemy import func, case
        async with self._engine.connect() as conn:
            result = await conn.execute(
                select(
                    test_runs.c.test_id,
                    test_runs.c.test_name,
                    func.count(test_runs.c.id).label("total_runs"),
                    func.sum(
                        case((test_runs.c.passed == False, 1), else_=0)  # noqa: E712
                    ).label("failure_count"),
                )
                .where(test_runs.c.repository == repository)
                .group_by(test_runs.c.test_id, test_runs.c.test_name)
                .having(func.count(test_runs.c.id) > 1)
            )
            flaky = []
            for row in result.mappings().fetchall():
                total = row["total_runs"]
                failures = row["failure_count"] or 0
                flake_rate = failures / total if total > 0 else 0
                if flake_rate >= min_flake_rate:
                    flaky.append({
                        "test_id": row["test_id"],
                        "test_name": row["test_name"],
                        "total_runs": total,
                        "failure_count": failures,
                        "flake_rate": round(flake_rate, 3),
                    })
            return sorted(flaky, key=lambda x: x["flake_rate"], reverse=True)

    def _row_to_dict(self, row: dict[str, Any]) -> dict[str, Any]:
        """Deserialize JSON fields in a test run row."""
        row["evidence"] = _from_json(row.get("evidence", "[]"))
        return row
