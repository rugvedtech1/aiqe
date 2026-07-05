"""
AIQE Database Table Definitions.

Uses SQLAlchemy Core (Table objects), not the ORM.

Why SQLAlchemy Core instead of ORM?
    The ORM couples domain objects to ORM-managed lifecycles:
    sessions, lazy loading, identity maps, relationship proxies.
    These add complexity that AIQE does not need — our repository
    pattern already defines the access layer.

    SQLAlchemy Core gives us:
    - Portable SQL that works on SQLite and Postgres identically
    - Explicit table definitions we fully control
    - Async support via aiosqlite and asyncpg
    - No ORM overhead, no session management leaking into agents

Table design decisions:
    - All primary keys are UUIDs (strings) — consistent with
      domain entity IDs generated in shared/domain.py
    - All timestamps are ISO 8601 strings for SQLite compatibility
      (Postgres stores them as TIMESTAMP WITH TIME ZONE)
    - JSON columns store complex nested data (agent states, evidence)
      as TEXT in SQLite and JSONB in Postgres
    - No foreign key constraints in SQLite (not enforced anyway)
      but Postgres implementations add them for data integrity
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

# Single metadata instance shared across all tables.
# This is what SQLAlchemy uses to track all table definitions
# and generate CREATE TABLE statements.
metadata = MetaData()


# ==================================================
# WORKFLOW CONTEXTS TABLE
# ==================================================

workflow_contexts = Table(
    "workflow_contexts",
    metadata,

    # Identity
    Column("id", String(36), primary_key=True, nullable=False),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),

    # Trigger information
    Column("trigger", String(32), nullable=False, default="manual"),
    Column("repository", String(255), nullable=False, default=""),
    Column("branch", String(255), nullable=False, default=""),
    Column("pr_number", Integer, nullable=True),

    # Lifecycle
    Column("status", String(32), nullable=False, default="pending"),
    Column("started_at", String(32), nullable=True),
    Column("completed_at", String(32), nullable=True),
    Column("duration_seconds", Float, nullable=True),
    Column("error", Text, nullable=True),

    # Counts (denormalised for fast reporting)
    Column("bugs_count", Integer, nullable=False, default=0),
    Column("agents_completed", Integer, nullable=False, default=0),
    Column("agents_skipped", Integer, nullable=False, default=0),

    # JSON columns
    Column("agent_records", Text, nullable=False, default="{}"),
    Column("workspace_path", String(512), nullable=False, default=""),

    # Indexes for common queries
    Index("ix_wc_repository", "repository"),
    Index("ix_wc_status", "status"),
    Index("ix_wc_pr", "repository", "pr_number"),
    Index("ix_wc_created_at", "created_at"),
)


# ==================================================
# CHECKPOINTS TABLE
# ==================================================

checkpoints = Table(
    "checkpoints",
    metadata,

    Column("id", String(36), primary_key=True, nullable=False),
    Column("workflow_id", String(36), nullable=False),
    Column("stage", String(64), nullable=False),
    Column("stage_index", Integer, nullable=False),
    Column("state", Text, nullable=False, default="{}"),
    Column("saved_at", String(32), nullable=False),

    # Unique constraint: one checkpoint per stage per workflow
    Index(
        "ix_cp_workflow_stage",
        "workflow_id",
        "stage",
        unique=True,
    ),
    Index("ix_cp_workflow_id", "workflow_id"),
)


# ==================================================
# BUGS TABLE
# ==================================================

bugs = Table(
    "bugs",
    metadata,

    Column("id", String(36), primary_key=True, nullable=False),
    Column("workflow_id", String(36), nullable=False),
    Column("created_at", String(32), nullable=False),

    # Bug classification
    Column("severity", String(32), nullable=False),
    Column("confidence", Float, nullable=False, default=0.0),
    Column("title", String(512), nullable=False, default=""),
    Column("root_cause", Text, nullable=False, default=""),

    # Affected areas
    Column("affected_feature", String(255), nullable=False, default=""),
    Column("affected_files", Text, nullable=False, default="[]"),

    # Fix information
    Column("suggested_fix", Text, nullable=False, default=""),
    Column("fix_confidence", Float, nullable=False, default=0.0),

    # Downstream tracking
    Column("is_downstream", Boolean, nullable=False, default=False),
    Column("root_bug_id", String(36), nullable=True),

    # JSON columns
    Column("evidence", Text, nullable=False, default="[]"),
    Column("dependency_chain", Text, nullable=False, default="[]"),
    Column("related_tests", Text, nullable=False, default="[]"),

    # Repository denormalised for cross-workflow queries
    Column("repository", String(255), nullable=False, default=""),

    Index("ix_bugs_workflow_id", "workflow_id"),
    Index("ix_bugs_severity", "severity"),
    Index("ix_bugs_feature", "affected_feature"),
    Index("ix_bugs_repository", "repository"),
)


# ==================================================
# AUDIT LOG TABLE
# ==================================================

audit_log = Table(
    "audit_log",
    metadata,

    Column("id", String(36), primary_key=True, nullable=False),
    Column("workflow_id", String(36), nullable=False),
    Column("event_id", String(36), nullable=False),
    Column("event_type", String(64), nullable=False),
    Column("occurred_at", String(32), nullable=False),
    Column("payload", Text, nullable=False, default="{}"),

    Index("ix_al_workflow_id", "workflow_id"),
    Index("ix_al_event_type", "event_type"),
    Index("ix_al_occurred_at", "occurred_at"),
)


# ==================================================
# TEST RUNS TABLE
# ==================================================

test_runs = Table(
    "test_runs",
    metadata,

    Column("id", String(36), primary_key=True, nullable=False),
    Column("workflow_id", String(36), nullable=False),
    Column("test_id", String(255), nullable=False),
    Column("test_name", String(512), nullable=False, default=""),
    Column("test_type", String(64), nullable=False, default=""),
    Column("feature", String(255), nullable=False, default=""),
    Column("passed", Boolean, nullable=False, default=False),
    Column("duration_seconds", Float, nullable=False, default=0.0),
    Column("error", Text, nullable=True),
    Column("evidence", Text, nullable=False, default="[]"),
    Column("executed_at", String(32), nullable=False),

    # Repository denormalised for flaky test queries
    Column("repository", String(255), nullable=False, default=""),

    Index("ix_tr_workflow_id", "workflow_id"),
    Index("ix_tr_test_id", "test_id"),
    Index("ix_tr_feature", "feature"),
    Index("ix_tr_passed", "passed"),
    Index("ix_tr_repository_test", "repository", "test_id"),
)
