"""
AIQE Workflow Engine.

The workflow package implements the core execution model for AIQE.
It is built on Python asyncio with no external framework dependency.

Public API:
    WorkflowContext   — isolated execution container (ADR-006)
    WorkflowEngine    — creates and runs workflow contexts
    AgentRegistry     — registers and resolves agents
    WorkflowScheduler — dependency-aware task executor (ADR-007)
    CheckpointManager — stage-level crash recovery (ADR-001)
    get_engine        — get the global engine singleton
    agent_registry    — get the global registry singleton

All domain events are importable from aiqe.workflow.events.
"""

from aiqe.workflow.checkpoints import CheckpointManager, WORKFLOW_STAGES
from aiqe.workflow.context import AgentExecutionRecord, WorkflowContext
from aiqe.workflow.engine import WorkflowEngine, get_engine
from aiqe.workflow.events import (
    AgentCompleted,
    AgentFailed,
    AgentSkipped,
    AgentStarted,
    AgentStatus,
    BugFound,
    TaskPriority,
    WorkflowCheckpointed,
    WorkflowCompleted,
    WorkflowFailed,
    WorkflowStarted,
    WorkflowStatus,
)
from aiqe.workflow.registry import AgentRegistration, AgentRegistry, agent_registry
from aiqe.workflow.scheduler import WorkflowScheduler

__all__ = [
    "AgentCompleted",
    "AgentExecutionRecord",
    "AgentFailed",
    "AgentRegistration",
    "AgentRegistry",
    "AgentSkipped",
    "AgentStarted",
    "AgentStatus",
    "BugFound",
    "CheckpointManager",
    "TaskPriority",
    "WorkflowCheckpointed",
    "WorkflowCompleted",
    "WorkflowContext",
    "WorkflowEngine",
    "WorkflowFailed",
    "WorkflowScheduler",
    "WorkflowStarted",
    "WorkflowStatus",
    "WORKFLOW_STAGES",
    "agent_registry",
    "get_engine",
]
