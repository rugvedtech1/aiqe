"""
AIQE Task Scheduler.

The Scheduler is responsible for:
1. Determining which agents are ready to run (dependencies satisfied).
2. Submitting ready agents as asyncio tasks.
3. Handling dependency failure isolation (ADR-007):
   when an agent fails, mark its dependents as SKIPPED.
4. Tracking the overall execution state of the workflow.

Design:
    The Scheduler does NOT run agents itself. It determines readiness
    and submits tasks to asyncio. The actual agent.run() call happens
    inside the submitted coroutine.

    This separation means the Scheduler can be tested in isolation
    (dependency resolution, skip propagation) without needing real
    agent implementations.

Dependency failure isolation (ADR-007):
    When agent X fails:
    - Find all agents that depend on X (direct and transitive).
    - Mark all of them as SKIPPED with reason and blocked_by=X.
    - Continue executing all agents that do NOT depend on X.
    - Record all skips in the workflow context audit log.
    - Group downstream failures under X in the bug report.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from aiqe.shared.exceptions import AgentError
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import Timer
from aiqe.workflow.context import WorkflowContext
from aiqe.workflow.events import AgentCompleted, AgentFailed, AgentSkipped, AgentStarted, AgentStatus
from aiqe.workflow.registry import AgentRegistry, agent_registry

logger = get_logger(__name__)

# Type alias for agent execution coroutines
AgentCoroutine = Callable[..., Coroutine[Any, Any, Any]]


@dataclass
class ScheduledTask:
    """
    Represents a single agent task scheduled for execution.

    Attributes:
        agent_name: The agent to execute.
        coroutine: The async function to call.
        priority: Execution priority (lower = higher priority).
    """
    agent_name: str
    coroutine: AgentCoroutine
    priority: int = 0


class WorkflowScheduler:
    """
    Dependency-aware task scheduler for AIQE workflow execution.

    Manages the execution lifecycle of all agents within one workflow.
    One WorkflowScheduler instance is created per WorkflowContext.

    Args:
        context: The workflow context this scheduler manages.
        registry: The agent registry to resolve dependencies from.
        max_concurrent: Maximum agents running simultaneously.
    """

    def __init__(
        self,
        context: WorkflowContext,
        registry: AgentRegistry | None = None,
        max_concurrent: int = 5,
    ) -> None:
        self._context = context
        self._registry = registry or agent_registry
        self._max_concurrent = max_concurrent
        self._completed: set[str] = set()
        self._failed: set[str] = set()
        self._skipped: set[str] = set()
        self._running: set[str] = set()
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def run_agent(
        self,
        agent_name: str,
        agent_coroutine: AgentCoroutine,
        **kwargs: Any,
    ) -> Any:
        """
        Execute one agent with full lifecycle tracking.

        This method:
        1. Checks that the agent is not blocked by a failed dependency.
        2. Records the agent as RUNNING in the workflow context.
        3. Emits AgentStarted event to the audit log.
        4. Executes the agent coroutine.
        5. On success: records COMPLETED, emits AgentCompleted.
        6. On failure: records FAILED, emits AgentFailed, propagates
           skip to all dependent agents.

        Args:
            agent_name: The registered name of the agent.
            agent_coroutine: The async callable to execute.
            **kwargs: Arguments forwarded to the agent coroutine.

        Returns:
            Whatever the agent coroutine returns.
        """
        # Check if this agent was skipped due to a dependency failure
        if agent_name in self._skipped:
            logger.info(
                "agent_already_skipped",
                workflow_id=self._context.id,
                agent_name=agent_name,
            )
            return None

        record = self._context.get_agent_record(agent_name)

        async with self._semaphore:
            self._running.add(agent_name)
            record.mark_running()

            started_event = AgentStarted(
                workflow_id=self._context.id,
                agent_name=agent_name,
                agent_tier=self._get_tier(agent_name),
            )
            self._context._append_audit(started_event.to_dict())

            logger.info(
                "agent_running",
                workflow_id=self._context.id,
                agent_name=agent_name,
            )

            with Timer() as timer:
                try:
                    output = await agent_coroutine(**kwargs)

                    record.mark_completed(output)
                    self._completed.add(agent_name)
                    self._running.discard(agent_name)

                    completed_event = AgentCompleted(
                        workflow_id=self._context.id,
                        agent_name=agent_name,
                        duration_seconds=timer.elapsed_seconds,
                        ai_tokens_used=record.ai_tokens_used,
                    )
                    self._context._append_audit(completed_event.to_dict())

                    logger.info(
                        "agent_succeeded",
                        workflow_id=self._context.id,
                        agent_name=agent_name,
                        duration_seconds=timer.elapsed_seconds,
                    )
                    return output

                except Exception as e:
                    error_msg = str(e)
                    error_type = type(e).__name__

                    record.mark_failed(error_msg)
                    self._failed.add(agent_name)
                    self._running.discard(agent_name)

                    # Find all downstream agents affected by this failure
                    affected = self._propagate_failure(agent_name)

                    failed_event = AgentFailed(
                        workflow_id=self._context.id,
                        agent_name=agent_name,
                        error_type=error_type,
                        error_message=error_msg,
                        duration_seconds=timer.elapsed_seconds,
                        affected_downstream=affected,
                    )
                    self._context._append_audit(failed_event.to_dict())

                    logger.error(
                        "agent_failed",
                        workflow_id=self._context.id,
                        agent_name=agent_name,
                        error_type=error_type,
                        error=error_msg,
                        affected_downstream=affected,
                        duration_seconds=timer.elapsed_seconds,
                    )
                    raise

    def _propagate_failure(self, failed_agent: str) -> list[str]:
        """
        Mark all agents downstream of a failed agent as SKIPPED.

        Implements the dependency failure isolation rule from ADR-007:
        when an agent fails, stop only the affected dependency chain.
        Continue testing all independent features.

        Args:
            failed_agent: The agent that failed.

        Returns:
            List of agent names that were marked as SKIPPED.
        """
        affected: list[str] = []
        queue = [failed_agent]
        visited: set[str] = set()

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            dependents = self._registry.get_dependents(current)
            for dependent in dependents:
                if dependent.name not in self._skipped:
                    self._skipped.add(dependent.name)
                    affected.append(dependent.name)

                    # Mark the record in the context
                    if dependent.name in self._context.agent_records:
                        record = self._context.agent_records[dependent.name]
                        record.mark_skipped(
                            reason=(
                                f"Dependency '{failed_agent}' failed. "
                                f"This agent requires '{failed_agent}' to complete "
                                f"successfully before it can run."
                            ),
                            blocked_by=failed_agent,
                        )

                        skip_event = AgentSkipped(
                            workflow_id=self._context.id,
                            agent_name=dependent.name,
                            blocked_by=failed_agent,
                            reason=f"Dependency '{failed_agent}' failed.",
                        )
                        self._context._append_audit(skip_event.to_dict())

                        logger.info(
                            "agent_skipped_due_to_dependency_failure",
                            workflow_id=self._context.id,
                            agent_name=dependent.name,
                            blocked_by=failed_agent,
                        )

                    queue.append(dependent.name)

        return affected

    def can_run(self, agent_name: str) -> bool:
        """
        Return True if an agent is ready to run.

        An agent is ready when:
        - It is not already running, completed, failed, or skipped.
        - All its dependencies are in the COMPLETED set.

        Args:
            agent_name: The agent to check.
        """
        if agent_name in self._running:
            return False
        if agent_name in self._completed:
            return False
        if agent_name in self._failed:
            return False
        if agent_name in self._skipped:
            return False

        registration = self._registry.get(agent_name)
        return all(dep in self._completed for dep in registration.dependencies)

    def _get_tier(self, agent_name: str) -> int:
        """Get the tier of an agent, returning 0 if not found."""
        try:
            return self._registry.get(agent_name).tier
        except Exception:
            return 0

    @property
    def all_finished(self) -> bool:
        """True when every registered agent has reached a terminal state."""
        all_names = {r.name for r in self._registry.get_all_enabled()}
        terminal = self._completed | self._failed | self._skipped
        return all_names <= terminal

    @property
    def summary(self) -> dict[str, Any]:
        """Current execution state summary for logging and reporting."""
        return {
            "completed": sorted(self._completed),
            "failed": sorted(self._failed),
            "skipped": sorted(self._skipped),
            "running": sorted(self._running),
            "total_completed": len(self._completed),
            "total_failed": len(self._failed),
            "total_skipped": len(self._skipped),
        }
