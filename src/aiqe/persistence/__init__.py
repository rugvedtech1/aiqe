"""
AIQE Persistence Layer.

Implements the Repository Pattern (ADR-002) for all AIQE
persistent data. The domain layer interacts only with
repository interfaces — never with database drivers directly.

Public API:
    WorkflowContextRepository  — interface for workflow contexts
    CheckpointRepository       — interface for stage checkpoints
    BugRepository              — interface for bug reports
    AuditLogRepository         — interface for audit trail
    TestRunRepository          — interface for test run results
    RepositoryBundle           — all repos as one injectable object
    create_repository_bundle   — factory function
    get_repository_bundle      — singleton accessor
    UnitOfWork                 — atomic multi-repo operations
"""

from aiqe.persistence.factory import (
    RepositoryBundle,
    create_repository_bundle,
    get_repository_bundle,
)
from aiqe.persistence.interfaces import (
    AuditLogRepository,
    BugRepository,
    CheckpointRepository,
    TestRunRepository,
    WorkflowContextRepository,
)
from aiqe.persistence.unit_of_work import UnitOfWork

__all__ = [
    "AuditLogRepository",
    "BugRepository",
    "CheckpointRepository",
    "RepositoryBundle",
    "TestRunRepository",
    "UnitOfWork",
    "WorkflowContextRepository",
    "create_repository_bundle",
    "get_repository_bundle",
]
