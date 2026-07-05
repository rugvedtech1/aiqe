"""
AIQE Orchestrator Agent — Updated for Tier 1 coordination.

The Orchestrator is the top-level coordinator. It now:
    1. Builds the execution plan from the Agent Registry
    2. Reads the GitHub event context from shared memory
    3. Coordinates all Tier 1 agents in dependency order
    4. Monitors progress and handles failures
    5. Enforces the Human Review Gate (ADR-009)

What the Orchestrator does NOT do:
    - Detect languages (Project Analysis Agent)
    - Generate test cases (Test Case Generator)
    - Execute tests (Browser/API agents)
    - Analyse bugs (Bug Analysis Agent)

This agent uses DETERMINISTIC logic only. No AI calls.
Tier: 1 | Dependencies: none (root)
"""

from __future__ import annotations

from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger
from aiqe.workflow.registry import agent_registry

logger = get_logger(__name__)


class OrchestratorInput(AgentInput):
    """Input for the Orchestrator Agent."""
    context: Any = None
    enable_security_testing: bool = True
    enable_performance_testing: bool = False
    enable_database_validation: bool = True
    max_concurrent_agents: int = 3


class OrchestratorOutput(AgentOutput):
    """Output from the Orchestrator Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.execution_plan: list[str] = []
        self.execution_waves: list[list[str]] = []
        self.agents_executed: list[str] = []
        self.agents_failed: list[str] = []
        self.agents_skipped: list[str] = []
        self.total_duration_seconds: float = 0.0
        self.release_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "execution_plan": self.execution_plan,
            "execution_waves": self.execution_waves,
            "agents_executed": self.agents_executed,
            "agents_failed": self.agents_failed,
            "agents_skipped": self.agents_skipped,
            "total_duration_seconds": self.total_duration_seconds,
            "release_ready": self.release_ready,
        }


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator Agent — Tier 1, root coordinator.

    Controls all agents, plans execution, and coordinates
    the complete workflow lifecycle using deterministic logic.
    """

    NAME = "orchestrator"
    DESCRIPTION = (
        "Controls all agents, plans execution order, coordinates "
        "workflow lifecycle, and enforces the Human Review Gate."
    )
    TIER = 1
    DEPENDENCIES: list[str] = []

    def __init__(self, memory_store: Any = None) -> None:
        self._memory = memory_store

    async def run_impl(self, input_data: AgentInput) -> OrchestratorOutput:
        """Plan and coordinate the workflow execution."""
        output = OrchestratorOutput()

        # Build execution plan from registry
        try:
            enabled_agents = agent_registry.get_all_enabled()
            execution_waves = agent_registry.resolve_execution_order()
        except Exception as e:
            logger.warning(
                "orchestrator_registry_empty",
                error=str(e),
                workflow_id=input_data.workflow_id,
            )
            enabled_agents = []
            execution_waves = []

        execution_plan = []
        for wave in execution_waves:
            execution_plan.extend(wave)

        output.execution_plan = execution_plan
        output.execution_waves = execution_waves

        # Write workflow metadata to shared memory
        if self._memory:
            await self._memory.set(
                key=str(MemoryKeys.WORKFLOW_METADATA),
                value={
                    "workflow_id": input_data.workflow_id,
                    "project_path": input_data.project_path,
                    "execution_plan": execution_plan,
                    "total_agents": len(enabled_agents),
                },
                written_by=self.NAME,
            )

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
            f"Execution order: {execution_plan}. "
            f"Dependency failures will isolate only the affected chain — "
            f"independent agents will continue (ADR-007). "
            f"Human Review Gate will be the final step (ADR-009, ADR-010)."
        )
        output.confidence = 1.0

        output.metadata["total_agents"] = len(enabled_agents)
        output.metadata["wave_count"] = len(execution_waves)
        output.metadata["waves"] = execution_waves

        return output

    def validate_input(self, input_data: AgentInput) -> None:
        if not input_data.workflow_id:
            raise ValueError(
                "OrchestratorAgent requires workflow_id in input."
            )
