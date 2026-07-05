"""
AIQE Agent Registry Setup.

This module registers all built-in AIQE agents with the global
Agent Registry. Import this module once at application startup
(CLI entrypoint or FastAPI startup) to ensure all agents are
available before the Orchestrator builds the execution plan.

Why a separate setup module instead of auto-registration?
    Auto-registration (importing all agent modules automatically)
    creates hidden import-time side effects that are hard to test
    and debug. An explicit setup module makes the registration
    step visible and controllable.

    In tests, you can import only the agents you need and register
    them in a fresh registry, without loading the full production set.

Usage:
    from aiqe.agents.registry_setup import register_all_agents
    register_all_agents()  # Call once at startup
"""

from __future__ import annotations

from aiqe.agents.orchestrator.agent import OrchestratorAgent
from aiqe.shared.logging import get_logger
from aiqe.workflow.registry import AgentRegistration, agent_registry

logger = get_logger(__name__)


def register_all_agents() -> None:
    """
    Register all built-in AIQE agents with the global registry.

    Called once at application startup. Safe to call multiple times
    (will skip already-registered agents with a warning).

    Agents are registered in tier order for clarity, but the registry
    resolves actual execution order via dependency declarations.
    """
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

        # ==================================================
        # TIER 1 — CORE (placeholders — implemented in Step 15)
        # ==================================================
        # AgentRegistration(
        #     name="project_analysis",
        #     display_name="Project Analysis Agent",
        #     agent_class=ProjectAnalysisAgent,
        #     tier=1,
        #     dependencies=["orchestrator"],
        #     description="Detects language, framework, dependencies.",
        # ),
        # AgentRegistration(
        #     name="test_strategy",
        #     display_name="Test Strategy Agent",
        #     agent_class=TestStrategyAgent,
        #     tier=1,
        #     dependencies=["project_analysis"],
        #     description="Risk analysis, coverage, priority, regression.",
        # ),
        # AgentRegistration(
        #     name="test_case_generator",
        #     display_name="Test Case Generator Agent",
        #     agent_class=TestCaseGeneratorAgent,
        #     tier=1,
        #     dependencies=["test_strategy"],
        #     description="Generates positive, negative, boundary, edge cases.",
        # ),
    ]

    registered_count = 0
    for registration in agents_to_register:
        if agent_registry.is_registered(registration.name):
            logger.warning(
                "agent_already_registered_skip",
                agent_name=registration.name,
            )
            continue

        agent_registry.register(registration)
        registered_count += 1

    logger.info(
        "agents_registered",
        count=registered_count,
        total_in_registry=agent_registry.count,
    )
