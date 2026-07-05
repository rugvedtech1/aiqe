"""
AIQE Agent Registry Setup.

Registers all built-in AIQE agents with the global registry.
Import and call register_all_agents() once at application startup.
"""

from __future__ import annotations

from aiqe.agents.orchestrator.agent import OrchestratorAgent
from aiqe.agents.project_analysis.agent import ProjectAnalysisAgent
from aiqe.agents.test_case_generator.agent import TestCaseGeneratorAgent
from aiqe.agents.test_strategy.agent import TestStrategyAgent
from aiqe.shared.logging import get_logger
from aiqe.workflow.registry import AgentRegistration, agent_registry

logger = get_logger(__name__)


def register_all_agents() -> None:
    """Register all built-in AIQE agents with the global registry."""

    agents_to_register = [
        # ==================================================
        # TIER 1 — CORE
        # ==================================================
        AgentRegistration(
            name=OrchestratorAgent.NAME,
            display_name="Orchestrator Agent",
            agent_class=OrchestratorAgent,
            tier=1,
            dependencies=[],
            description=OrchestratorAgent.DESCRIPTION,
        ),
        AgentRegistration(
            name=ProjectAnalysisAgent.NAME,
            display_name="Project Analysis Agent",
            agent_class=ProjectAnalysisAgent,
            tier=1,
            dependencies=["orchestrator"],
            description=ProjectAnalysisAgent.DESCRIPTION,
        ),
        AgentRegistration(
            name=TestStrategyAgent.NAME,
            display_name="Test Strategy Agent",
            agent_class=TestStrategyAgent,
            tier=1,
            dependencies=["project_analysis"],
            description=TestStrategyAgent.DESCRIPTION,
        ),
        AgentRegistration(
            name=TestCaseGeneratorAgent.NAME,
            display_name="Test Case Generator Agent",
            agent_class=TestCaseGeneratorAgent,
            tier=1,
            dependencies=["test_strategy", "project_analysis"],
            description=TestCaseGeneratorAgent.DESCRIPTION,
        ),

        # Tier 2-4 placeholders — implemented in Steps 16-18
    ]

    registered_count = 0
    for registration in agents_to_register:
        if agent_registry.is_registered(registration.name):
            continue
        agent_registry.register(registration)
        registered_count += 1

    logger.info(
        "agents_registered",
        count=registered_count,
        total_in_registry=agent_registry.count,
    )
