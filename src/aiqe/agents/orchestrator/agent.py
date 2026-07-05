"""
AIQE Orchestrator Agent.

The Orchestrator is the top-level coordinator for AIQE workflow
execution. It is the only agent that the Workflow Engine talks to
directly. All other agents are called through the Orchestrator.

Responsibilities:
    - Receive the workflow context from the Engine.
    - Build the execution plan from the Agent Registry.
    - Delegate to the Scheduler for actual execution.
    - Monitor progress and respond to agent failures.
    - Collect final results and hand off to the Report Agent.
    - Ensure the Human Review Gate is always the final step (ADR-009).

What the Orchestrator does NOT do:
    - Detect languages or frameworks (Project Analysis Agent).
    - Generate test cases (Test Case Generator Agent).
    - Execute browser tests (Browser Execution Agent).
    - Analyse bugs (Bug Analysis Agent).
    - Make AI calls directly (uses AI Gateway through agents).

The Orchestrator uses DETERMINISTIC logic only.
It never calls AI itself — it is a coordinator, not an analyst.
This follows the "deterministic before AI" principle (ADR-001).

Tier: 1 (Core)
Dependencies: None (it is the root of the dependency tree)
"""

from __future__ import annotations

from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput
from aiqe.shared.logging import get_logger
from aiqe.workflow.context import WorkflowContext
from aiqe.workflow.registry import agent_registry

logger = get_logger(__name__)


class OrchestratorInput(AgentInput):
    """
    Input for the Orchestrator Agent.

    The Orchestrator receives the full workflow context reference
    plus configuration for how to run the workflow.

    Attributes:
        context: The active WorkflowContext for this execution.
        enable_security_testing: Whether to run security tests.
        enable_performance_testing: Whether to run performance tests.
        enable_database_validation: Whether to run DB validation.
        max_concurrent_agents: Max agents running simultaneously.
    """
    context: Any = None  # WorkflowContext — Any to avoid circular typing
    enable_security_testing: bool = True
    enable_performance_testing: bool = False
    enable_database_validation: bool = True
    max_concurrent_agents: int = 3


class OrchestratorOutput(AgentOutput):
    """
    Output from the Orchestrator Agent.

    Attributes:
        execution_plan: The ordered list of agents that were/will run.
        agents_executed: Names of agents that successfully completed.
        agents_failed: Names of agents that failed.
        agents_skipped: Names of agents skipped due to failures.
        total_duration_seconds: Complete workflow duration.
        release_ready: Orchestrator's assessment (NOT a decision — ADR-009).
    """
    execution_plan: list[str] = []
    agents_executed: list[str] = []
    agents_failed: list[str] = []
    agents_skipped: list[str] = []
    total_duration_seconds: float = 0.0
    release_ready: bool = False


class OrchestratorAgent(BaseAgent):
    """
    AIQE Orchestrator Agent.

    Controls all agents, plans execution, and coordinates
    the full workflow lifecycle.

    This agent uses pure deterministic logic — no AI calls.
    It reads the Agent Registry, resolves the execution order,
    and delegates execution to the Scheduler through the Engine.
    """

    NAME = "orchestrator"
    DESCRIPTION = (
        "Controls all agents, plans execution order, coordinates "
        "workflow lifecycle, and ensures the Human Review Gate "
        "is always the final step."
    )
    TIER = 1
    DEPENDENCIES: list[str] = []  # Root — no dependencies

    async def run_impl(self, input_data: AgentInput) -> AgentOutput:
        """
        Plan and coordinate the workflow execution.

        In the current implementation (Step 6), the Orchestrator
        builds and returns the execution plan. Full orchestration
        of other agents happens in Step 15 when all Tier 1 agents
        exist and the AI Gateway (Step 10) is available.

        Args:
            input_data: OrchestratorInput with workflow context.

        Returns:
            OrchestratorOutput with the execution plan.
        """
        assert isinstance(input_data, OrchestratorInput), (
            f"OrchestratorAgent expects OrchestratorInput, "
            f"got {type(input_data).__name__}"
        )

        output = OrchestratorOutput()

        # Build execution plan from registry
        enabled_agents = agent_registry.get_all_enabled()
        execution_waves = agent_registry.resolve_execution_order()

        execution_plan = []
        for wave in execution_waves:
            execution_plan.extend(wave)

        output.execution_plan = execution_plan

        logger.info(
            "orchestrator_plan_built",
            workflow_id=input_data.workflow_id,
            total_agents=len(enabled_agents),
            wave_count=len(execution_waves),
            execution_plan=execution_plan,
        )

        output.reasoning = (
            f"Orchestrator built execution plan for {len(enabled_agents)} "
            f"agents across {len(execution_waves)} execution waves. "
            f"Agents will execute in dependency order: {execution_plan}. "
            f"Dependency failures will be isolated — only the affected "
            f"dependency chain will be stopped, independent agents will "
            f"continue executing (ADR-007). "
            f"Human Review Gate will be enforced as the final step (ADR-009)."
        )

        output.metadata["total_agents"] = len(enabled_agents)
        output.metadata["wave_count"] = len(execution_waves)
        output.metadata["waves"] = execution_waves
        output.confidence = 1.0  # Deterministic — no uncertainty

        return output

    def validate_input(self, input_data: AgentInput) -> None:
        """Orchestrator requires a workflow_id but context is optional at plan time."""
        if not input_data.workflow_id:
            raise ValueError(
                "OrchestratorAgent requires workflow_id in input."
            )
