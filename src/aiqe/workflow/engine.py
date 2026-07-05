"""
AIQE Workflow Engine.

The engine is the top-level coordinator for AIQE workflow execution.
It creates WorkflowContexts, manages their lifecycle, enforces
isolation between concurrent workflows, and provides the entry
point that the CLI and FastAPI layer call.

Responsibilities:
    - Create and destroy WorkflowContexts (ADR-006)
    - Enforce that contexts never access each other's state
    - Start workflows, hand off to the Scheduler
    - Checkpoint before handing off to AI providers (ADR-001)
    - Resume workflows from checkpoints after provider failures
    - Route Critical bug notifications immediately (ADR-008)
    - Maintain a registry of all active workflows

What the engine does NOT do:
    - Run agents directly (that is the Scheduler's job)
    - Make AI calls (that is the Gateway's job, Step 10)
    - Generate tests (that is the agent's job)

This separation means the engine can be tested without AI providers,
browsers, or real project code.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from aiqe.shared.config import get_settings
from aiqe.shared.exceptions import WorkflowContextError
from aiqe.shared.logging import bind_workflow_context, clear_workflow_context, get_logger
from aiqe.shared.utils import Timer, ensure_directory, utcnow
from aiqe.workflow.checkpoints import CheckpointManager
from aiqe.workflow.context import WorkflowContext
from aiqe.workflow.events import WorkflowStatus
from aiqe.workflow.registry import AgentRegistry, agent_registry
from aiqe.workflow.scheduler import WorkflowScheduler

logger = get_logger(__name__)


class WorkflowEngine:
    """
    AIQE Workflow Engine.

    Manages the full lifecycle of WorkflowContexts. One engine
    instance runs per AIQE process. In enterprise mode with multiple
    worker processes, each process has its own engine — coordination
    happens through the shared Postgres database.

    Args:
        workspace_root: Root directory for all workflow workspaces.
                        Each workflow gets a subdirectory here.
        registry: Agent registry to use. Defaults to the global singleton.
        max_concurrent_workflows: Max simultaneous workflow executions.
    """

    def __init__(
        self,
        workspace_root: Path | None = None,
        registry: AgentRegistry | None = None,
        max_concurrent_workflows: int = 5,
    ) -> None:
        settings = get_settings()
        self._workspace_root = workspace_root or (
            settings.core.workspace_dir / "workflows"
        )
        ensure_directory(self._workspace_root)

        self._registry = registry or agent_registry
        self._max_concurrent = max_concurrent_workflows

        # Active workflow contexts keyed by workflow_id.
        # The isolation guarantee: only this engine creates and
        # destroys contexts. No external code holds references
        # that cross context boundaries.
        self._active_contexts: dict[str, WorkflowContext] = {}
        self._engine_lock = asyncio.Lock()

    async def create_context(
        self,
        trigger: str = "manual",
        repository: str = "",
        branch: str = "",
        pr_number: int | None = None,
    ) -> WorkflowContext:
        """
        Create a new isolated WorkflowContext.

        Each call creates a completely independent context with its
        own workspace directory, shared memory, and audit log.
        Contexts never share mutable state. See ADR-006.

        Args:
            trigger: What triggered this workflow
                     ('pr', 'branch', 'manual', 'scheduled').
            repository: Repository being analysed (owner/repo).
            branch: Branch being tested.
            pr_number: PR number if trigger is 'pr'.

        Returns:
            A new WorkflowContext ready to be started.
        """
        context = WorkflowContext(
            trigger=trigger,
            repository=repository,
            branch=branch,
            pr_number=pr_number,
        )

        # Each context gets its own subdirectory — guaranteed unique
        # because it is named after the context's UUID.
        context.workspace_path = self._workspace_root / context.id
        context.workspace_path.mkdir(parents=True, exist_ok=True)

        async with self._engine_lock:
            self._active_contexts[context.id] = context

        # Register all enabled agents in this context so their
        # records exist before the scheduler dispatches them.
        for registration in self._registry.get_all_enabled():
            context.register_agent(registration.name)

        logger.info(
            "workflow_context_created",
            workflow_id=context.id,
            trigger=trigger,
            repository=repository,
            branch=branch,
            pr_number=pr_number,
            workspace=str(context.workspace_path),
        )

        return context

    async def run(
        self,
        context: WorkflowContext,
        agent_executors: dict[str, Any] | None = None,
    ) -> WorkflowContext:
        """
        Execute a workflow from start to finish.

        This is the main entry point called by the CLI and FastAPI layer.
        It handles the full lifecycle:
            1. Start the context.
            2. Bind logging context so all logs carry workflow_id.
            3. Execute agents via the Scheduler.
            4. Complete or fail the context.
            5. Clean up logging context.

        In a real execution, agent_executors maps agent names to their
        async callables. The Orchestrator Agent (Step 15) will provide
        this mapping. For now the engine accepts it as a parameter so
        it can be tested with mock agents.

        Args:
            context: The WorkflowContext to run (must be PENDING).
            agent_executors: Dict mapping agent_name to async callable.
                             Used for testing and by the Orchestrator.

        Returns:
            The completed (or failed) WorkflowContext.
        """
        bind_workflow_context(
            workflow_id=context.id,
            trigger=context.trigger,
            repository=context.repository,
        )

        try:
            await context.start()
            checkpoint_manager = CheckpointManager(
                workflow_id=context.id,
                workspace_path=context.workspace_path,
            )

            scheduler = WorkflowScheduler(
                context=context,
                registry=self._registry,
                max_concurrent=self._max_concurrent,
            )

            with Timer() as total_timer:
                if agent_executors:
                    await self._execute_agents(
                        context=context,
                        scheduler=scheduler,
                        checkpoint_manager=checkpoint_manager,
                        agent_executors=agent_executors,
                    )

            logger.info(
                "workflow_execution_finished",
                workflow_id=context.id,
                duration_seconds=total_timer.elapsed_seconds,
                status=context.status.value,
                scheduler_summary=scheduler.summary,
            )

            if context.status == WorkflowStatus.RUNNING:
                await context.complete()

        except Exception as e:
            logger.error(
                "workflow_engine_error",
                workflow_id=context.id,
                error_type=type(e).__name__,
                error=str(e),
            )
            if not context.is_terminal:
                await context.fail(
                    error=str(e),
                    failed_stage="engine",
                )
        finally:
            clear_workflow_context()
            async with self._engine_lock:
                self._active_contexts.pop(context.id, None)

        return context

    async def _execute_agents(
        self,
        context: WorkflowContext,
        scheduler: WorkflowScheduler,
        checkpoint_manager: CheckpointManager,
        agent_executors: dict[str, Any],
    ) -> None:
        """
        Execute agents in dependency order using the Scheduler.

        Iterates through execution waves (groups of agents whose
        dependencies are all satisfied) and runs each wave
        concurrently up to max_concurrent limit.

        Args:
            context: The active workflow context.
            scheduler: The workflow's task scheduler.
            checkpoint_manager: The workflow's checkpoint manager.
            agent_executors: Agent name → async callable mapping.
        """
        waves = self._registry.resolve_execution_order()

        for wave_index, wave in enumerate(waves):
            # Filter out agents that have been skipped due to earlier failures
            runnable = [
                name for name in wave
                if scheduler.can_run(name) and name in agent_executors
            ]

            if not runnable:
                logger.debug(
                    "wave_skipped",
                    workflow_id=context.id,
                    wave_index=wave_index,
                    wave=wave,
                    reason="no runnable agents in this wave",
                )
                continue

            logger.info(
                "executing_wave",
                workflow_id=context.id,
                wave_index=wave_index,
                agents=runnable,
            )

            # Run all agents in this wave concurrently
            tasks = [
                asyncio.create_task(
                    scheduler.run_agent(
                        agent_name=name,
                        agent_coroutine=agent_executors[name],
                    ),
                    name=f"agent:{name}:{context.id}",
                )
                for name in runnable
            ]

            # Wait for all tasks in this wave.
            # We use gather with return_exceptions=True so one agent
            # failure doesn't cancel siblings in the same wave.
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Checkpoint after each wave completes
            completed_in_wave = [
                name for name, result in zip(runnable, results)
                if not isinstance(result, Exception)
            ]
            if completed_in_wave:
                checkpoint = await checkpoint_manager.save(
                    stage=completed_in_wave[-1],
                    state={"completed_agents": completed_in_wave},
                )
                await context.checkpoint(
                    stage=completed_in_wave[-1],
                    checkpoint_id=checkpoint.id,
                )

    async def resume(self, workflow_id: str) -> WorkflowContext | None:
        """
        Resume a checkpointed workflow from its last saved stage.

        Called when a workflow was interrupted (provider failure,
        process restart) and needs to continue from where it stopped.

        Args:
            workflow_id: The ID of the workflow to resume.

        Returns:
            The resumed context if found, None otherwise.
        """
        workspace_path = self._workspace_root / workflow_id
        if not workspace_path.exists():
            logger.warning(
                "resume_workspace_not_found",
                workflow_id=workflow_id,
                workspace_path=str(workspace_path),
            )
            return None

        checkpoint_manager = CheckpointManager(
            workflow_id=workflow_id,
            workspace_path=workspace_path,
        )

        resume_stage = await checkpoint_manager.get_resume_stage()
        logger.info(
            "workflow_resuming",
            workflow_id=workflow_id,
            resume_from_stage=resume_stage,
        )

        return None  # Full resume implementation comes with Persistence layer

    def get_active_context(self, workflow_id: str) -> WorkflowContext | None:
        """
        Get an active workflow context by ID.

        Returns None if the workflow is not currently active (already
        completed, failed, or never existed).

        This method enforces isolation — it returns None rather than
        raising an error for unknown IDs, because callers checking for
        a context from another workflow should not get an exception that
        reveals the other workflow's existence.
        """
        return self._active_contexts.get(workflow_id)

    @property
    def active_workflow_count(self) -> int:
        """Number of workflows currently executing."""
        return len(self._active_contexts)


# Module-level engine singleton for CLI and FastAPI use.
# The engine is initialized with settings from the environment.
_engine: WorkflowEngine | None = None


def get_engine() -> WorkflowEngine:
    """
    Get the global WorkflowEngine singleton.

    Initializes on first call. Thread-safe for read access.
    The engine itself uses asyncio locks for concurrent write safety.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = WorkflowEngine(
            max_concurrent_workflows=settings.core.max_concurrent_workflows,
        )
    return _engine
