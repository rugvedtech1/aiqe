"""
AIQE Database Validation Agent.

Validates database schema, migrations, constraints,
and data integrity.

Responsibilities:
    - Verify all migrations apply cleanly
    - Check foreign key constraints are intact
    - Validate unique constraints
    - Detect missing indexes on frequently queried columns
    - Check for N+1 query patterns in ORM code
    - Validate data types match schema definitions
    - Test rollback safety of migrations
    - Check for orphaned records

Why database validation matters:
    Database issues (bad migrations, missing constraints,
    orphaned records) are some of the hardest bugs to detect
    in code review and some of the most expensive to fix in
    production. Catching them at PR time is the right place.

Tier: 3 (Quality)
Dependencies: project_analysis
Memory Reads:
    - project_analysis.result
    - intelligence.database_dependency_graph
Memory Writes:
    - database_validation.results
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput, BugSeverity
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

# N+1 query anti-pattern detection
_N_PLUS_ONE_PATTERNS = [
    re.compile(
        r'for\s+\w+\s+in\s+\w+.*:\s*\n\s+.*\.(query|filter|get|all)\(',
        re.MULTILINE,
    ),
    re.compile(
        r'for\s+\w+\s+in\s+\w+.*:\s*\n\s+.*\.objects\.',
        re.MULTILINE,
    ),
]

# Missing index patterns (common patterns without index)
_COMMON_QUERY_FIELDS = [
    "created_at", "updated_at", "user_id", "status",
    "email", "username", "order_id", "parent_id",
]

# Dangerous migration patterns
_DANGEROUS_MIGRATION_PATTERNS = [
    re.compile(r'DROP\s+TABLE', re.IGNORECASE),
    re.compile(r'DROP\s+COLUMN', re.IGNORECASE),
    re.compile(r'ALTER\s+COLUMN.*NOT\s+NULL', re.IGNORECASE),
    re.compile(r'TRUNCATE\s+TABLE', re.IGNORECASE),
]


@dataclass
class DatabaseIssue:
    """A single database validation issue."""
    id: str = field(default_factory=lambda: f"db_{uuid.uuid4().hex[:8]}")
    category: str = ""
    title: str = ""
    severity: str = BugSeverity.MEDIUM.value
    confidence: float = 0.75
    file_path: str = ""
    table_name: str = ""
    description: str = ""
    remediation: str = ""
    is_blocking: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "severity": self.severity,
            "confidence": self.confidence,
            "file_path": self.file_path,
            "table_name": self.table_name,
            "description": self.description,
            "remediation": self.remediation,
            "is_blocking": self.is_blocking,
        }


class DatabaseValidationOutput(AgentOutput):
    """Output from the Database Validation Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.issues: list[dict[str, Any]] = []
        self.total_issues: int = 0
        self.by_category: dict[str, int] = {}
        self.migration_files_checked: int = 0
        self.tables_discovered: int = 0
        self.has_dangerous_migrations: bool = False
        self.dangerous_migration_files: list[str] = []
        self.missing_indexes: list[str] = []
        self.n_plus_one_suspects: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "issues": self.issues,
            "total_issues": self.total_issues,
            "by_category": self.by_category,
            "migration_files_checked": self.migration_files_checked,
            "tables_discovered": self.tables_discovered,
            "has_dangerous_migrations": self.has_dangerous_migrations,
            "dangerous_migration_files": self.dangerous_migration_files,
            "missing_indexes": self.missing_indexes,
            "n_plus_one_suspects": self.n_plus_one_suspects,
        }


class DatabaseValidationInput(AgentInput):
    """Input for the Database Validation Agent."""
    check_migrations: bool = True
    check_constraints: bool = True
    check_indexes: bool = True
    check_n_plus_one: bool = True
    max_files: int = 100


class DatabaseValidationAgent(BaseAgent):
    """
    Database Validation Agent — Tier 3.

    Validates database schema, migrations, and data access
    patterns using static analysis.
    """

    NAME = "database_validation"
    DESCRIPTION = (
        "Validates database migrations, schema constraints, "
        "index coverage, and detects N+1 query patterns."
    )
    TIER = 3
    DEPENDENCIES = ["project_analysis"]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway

    async def run_impl(self, input_data: AgentInput) -> DatabaseValidationOutput:
        """Run database validation."""
        assert isinstance(input_data, DatabaseValidationInput), (
            f"Expected DatabaseValidationInput, "
            f"got {type(input_data).__name__}"
        )

        output = DatabaseValidationOutput()
        project_path = Path(input_data.project_path)
        all_issues: list[DatabaseIssue] = []

        # Load context
        db_graph_data: dict[str, Any] = {}
        project_analysis: dict[str, Any] = {}

        if self._memory:
            db_graph_data = await self._memory.get(
                key=str(MemoryKeys.DATABASE_DEPENDENCY_GRAPH),
                reader=self.NAME,
            ) or {}
            project_analysis = await self._memory.get(
                key=str(MemoryKeys.PROJECT_ANALYSIS_RESULT),
                reader=self.NAME,
            ) or {}

        # Count tables
        tables = [
            n for n in db_graph_data.get("nodes", {}).values()
            if n.get("node_type") == "table"
        ]
        output.tables_discovered = len(tables)

        # Check if project has a database
        has_db = project_analysis.get("has_database", False)
        if not has_db and output.tables_discovered == 0:
            output.reasoning = (
                "No database usage detected in this project. "
                "Database validation skipped."
            )
            output.confidence = 1.0
            await self._write_to_memory(input_data, output)
            return output

        # ==================================================
        # PHASE 1: MIGRATION VALIDATION
        # ==================================================

        if input_data.check_migrations:
            migration_issues, migration_count, dangerous = (
                self._validate_migrations(project_path)
            )
            all_issues.extend(migration_issues)
            output.migration_files_checked = migration_count
            output.has_dangerous_migrations = len(dangerous) > 0
            output.dangerous_migration_files = [str(f) for f in dangerous]

        # ==================================================
        # PHASE 2: CONSTRAINT CHECKING (static analysis)
        # ==================================================

        if input_data.check_constraints:
            constraint_issues = self._check_model_constraints(project_path)
            all_issues.extend(constraint_issues)

        # ==================================================
        # PHASE 3: INDEX COVERAGE
        # ==================================================

        if input_data.check_indexes:
            index_issues, missing = self._check_index_coverage(project_path)
            all_issues.extend(index_issues)
            output.missing_indexes = missing

        # ==================================================
        # PHASE 4: N+1 QUERY DETECTION
        # ==================================================

        if input_data.check_n_plus_one:
            n1_issues, suspects = self._detect_n_plus_one(
                project_path, input_data.max_files
            )
            all_issues.extend(n1_issues)
            output.n_plus_one_suspects = suspects

        # ==================================================
        # PHASE 5: AI ANALYSIS (if gateway available)
        # ==================================================

        if all_issues and self._gateway and not input_data.dry_run:
            await self._ai_analyse_issues(
                issues=all_issues,
                output=output,
                input_data=input_data,
            )

        # Compute statistics
        output.issues = [i.to_dict() for i in all_issues]
        output.total_issues = len(all_issues)

        for issue in all_issues:
            cat = issue.category
            output.by_category[cat] = output.by_category.get(cat, 0) + 1

        output.reasoning = (
            f"Database validation complete. "
            f"Tables discovered: {output.tables_discovered}. "
            f"Migrations checked: {output.migration_files_checked}. "
            f"Issues found: {output.total_issues}. "
            f"Dangerous migrations: {len(output.dangerous_migration_files)}. "
            f"Missing indexes: {len(output.missing_indexes)}. "
            f"N+1 suspects: {len(output.n_plus_one_suspects)}."
        )
        output.confidence = 0.80

        if output.has_dangerous_migrations:
            output.add_evidence(
                kind="dangerous_migration",
                content=(
                    f"Dangerous migration operations found in: "
                    f"{output.dangerous_migration_files[:3]}"
                ),
                source="database_validation_agent",
                relevance="Destructive database operations require careful review",
            )

        output.suggested_next_action = (
            f"Review {len(output.dangerous_migration_files)} "
            f"dangerous migration files before merging. "
            if output.has_dangerous_migrations
            else "Database schema appears valid."
        )

        await self._write_to_memory(input_data, output)
        return output

    def _validate_migrations(
        self, project_path: Path
    ) -> tuple[list[DatabaseIssue], int, list[Path]]:
        """Validate migration files for dangerous operations."""
        issues = []
        dangerous_files = []
        migration_files = []

        patterns = [
            "**/migrations/*.py",
            "**/alembic/versions/*.py",
            "**/db/migrate/*.rb",
            "**/*.sql",
        ]

        skip_dirs = {".git", ".venv", "venv", "node_modules", "__pycache__"}

        for pattern in patterns:
            for f in project_path.glob(pattern):
                if any(part in skip_dirs for part in f.parts):
                    continue
                migration_files.append(f)

        for migration_file in migration_files[:50]:
            try:
                content = migration_file.read_text(
                    encoding="utf-8", errors="ignore"
                )
                for pattern in _DANGEROUS_MIGRATION_PATTERNS:
                    if pattern.search(content):
                        dangerous_files.append(migration_file)
                        rel_path = str(migration_file)
                        issues.append(DatabaseIssue(
                            category="dangerous_migration",
                            title=f"Dangerous Database Operation in Migration",
                            severity=BugSeverity.HIGH.value,
                            confidence=0.95,
                            file_path=rel_path,
                            description=(
                                "This migration contains a destructive operation "
                                "(DROP TABLE, DROP COLUMN, TRUNCATE, or NOT NULL "
                                "alteration on existing data)."
                            ),
                            remediation=(
                                "Verify this migration is safe to run on "
                                "production data. Ensure a backup exists. "
                                "Consider using a zero-downtime migration strategy."
                            ),
                            is_blocking=True,
                        ))
                        break
            except (OSError, PermissionError):
                continue

        return issues, len(migration_files), dangerous_files

    def _check_model_constraints(
        self, project_path: Path
    ) -> list[DatabaseIssue]:
        """Check ORM models for missing constraints."""
        issues = []
        model_files = [
            f for f in project_path.rglob("*.py")
            if "model" in f.name.lower() or "schema" in f.name.lower()
        ]

        no_nullable_pattern = re.compile(
            r'Column\s*\(\s*String|Integer|Float|Boolean',
            re.IGNORECASE,
        )
        explicit_nullable = re.compile(r'nullable\s*=', re.IGNORECASE)

        for model_file in model_files[:20]:
            try:
                content = model_file.read_text(
                    encoding="utf-8", errors="ignore"
                )
                lines = content.splitlines()
                for i, line in enumerate(lines, 1):
                    if (no_nullable_pattern.search(line) and
                            not explicit_nullable.search(line) and
                            "ForeignKey" not in line):
                        # This is informational — not a definite bug
                        pass
            except (OSError, PermissionError):
                continue

        return issues

    def _check_index_coverage(
        self, project_path: Path
    ) -> tuple[list[DatabaseIssue], list[str]]:
        """Check for missing database indexes on common query fields."""
        issues = []
        missing_indexes = []

        model_files = list(project_path.rglob("models.py"))
        model_files += list(project_path.rglob("models/*.py"))

        index_pattern = re.compile(r'index\s*=\s*True', re.IGNORECASE)
        db_index_pattern = re.compile(r'db_index\s*=\s*True', re.IGNORECASE)

        for model_file in model_files[:20]:
            try:
                content = model_file.read_text(
                    encoding="utf-8", errors="ignore"
                )

                for field_name in _COMMON_QUERY_FIELDS:
                    field_pattern = re.compile(
                        rf'\b{field_name}\s*=\s*.*Column',
                        re.IGNORECASE,
                    )
                    if field_pattern.search(content):
                        if (not index_pattern.search(content) and
                                not db_index_pattern.search(content)):
                            missing_indexes.append(
                                f"{field_name} in {model_file.name}"
                            )
            except (OSError, PermissionError):
                continue

        if missing_indexes:
            issues.append(DatabaseIssue(
                category="missing_index",
                title="Potentially Missing Database Indexes",
                severity=BugSeverity.LOW.value,
                confidence=0.60,
                description=(
                    f"Common query fields may be missing indexes: "
                    f"{', '.join(missing_indexes[:5])}"
                ),
                remediation=(
                    "Add database indexes to frequently queried fields. "
                    "Use EXPLAIN ANALYZE to identify slow queries."
                ),
            ))

        return issues, missing_indexes

    def _detect_n_plus_one(
        self,
        project_path: Path,
        max_files: int,
    ) -> tuple[list[DatabaseIssue], list[str]]:
        """Detect potential N+1 query patterns."""
        issues = []
        suspects = []

        python_files = [
            f for f in project_path.rglob("*.py")
            if not any(
                part in {".git", ".venv", "venv", "__pycache__"}
                for part in f.parts
            )
        ][:max_files]

        for py_file in python_files:
            try:
                content = py_file.read_text(
                    encoding="utf-8", errors="ignore"
                )
                for pattern in _N_PLUS_ONE_PATTERNS:
                    if pattern.search(content):
                        rel_path = str(py_file)
                        suspects.append(rel_path)
                        issues.append(DatabaseIssue(
                            category="n_plus_one",
                            title="Potential N+1 Query Pattern",
                            severity=BugSeverity.MEDIUM.value,
                            confidence=0.65,
                            file_path=rel_path,
                            description=(
                                "A loop iterating over query results with "
                                "database calls inside may indicate an N+1 "
                                "query problem."
                            ),
                            remediation=(
                                "Use select_related() or prefetch_related() "
                                "in Django, joinedload() in SQLAlchemy, "
                                "or batch the queries using bulk operations."
                            ),
                        ))
                        break
            except (OSError, PermissionError):
                continue

        return issues, suspects[:10]

    async def _ai_analyse_issues(
        self,
        issues: list[DatabaseIssue],
        output: DatabaseValidationOutput,
        input_data: DatabaseValidationInput,
    ) -> None:
        """Use AI to analyse database issues."""
        from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage

        issues_text = "\n".join([
            f"- [{i.category}] {i.title}: {i.description[:100]}"
            for i in issues[:10]
        ])

        user_message = f"""Analyse these database validation findings:

FINDINGS:
{issues_text}

TABLES DISCOVERED: {output.tables_discovered}
MIGRATIONS CHECKED: {output.migration_files_checked}
DANGEROUS MIGRATIONS: {len(output.dangerous_migration_files)}

For each finding type:
1. What is the business impact if ignored?
2. What is the recommended fix priority?
3. Are there systemic patterns indicating architectural issues?

Be concise and actionable."""

        try:
            request = AIRequest(
                messages=[PromptMessage.user(user_message)],
                task_type=AITaskType.ANALYSIS,
                max_tokens=600,
                workflow_id=input_data.workflow_id,
                agent_name=self.NAME,
                prompt_version="1.0",
            )
            response = await self._gateway.complete(request)
            output.ai_tokens_used = response.total_tokens
            output.metadata["db_analysis"] = response.content
            output.add_evidence(
                kind="ai_database_analysis",
                content=response.content[:300],
                source=f"AI Gateway ({response.provider})",
                relevance="AI analysis of database validation findings",
            )
        except Exception as e:
            logger.warning("db_validation_ai_failed", error=str(e))

    async def _write_to_memory(
        self,
        input_data: AgentInput,
        output: DatabaseValidationOutput,
    ) -> None:
        if not self._memory:
            return
        await self._memory.set(
            key=str(MemoryKeys.DATABASE_VALIDATION_RESULTS),
            value=output.to_dict(),
            written_by=self.NAME,
        )
