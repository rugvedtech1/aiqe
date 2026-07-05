"""
AIQE Agent Registry Setup.

Registers all built-in AIQE agents with the global registry.
Import and call register_all_agents() once at application startup.
"""

from __future__ import annotations

from aiqe.agents.api_validation.agent import APIValidationAgent
from aiqe.agents.automation_generator.agent import AutomationGeneratorAgent
from aiqe.agents.browser_execution.agent import BrowserExecutionAgent
from aiqe.agents.database_validation.agent import DatabaseValidationAgent
from aiqe.agents.orchestrator.agent import OrchestratorAgent
from aiqe.agents.performance.agent import PerformanceAgent
from aiqe.agents.project_analysis.agent import ProjectAnalysisAgent
from aiqe.agents.security_testing.agent import SecurityTestingAgent
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

        # ==================================================
        # TIER 2 — EXECUTION
        # ==================================================
        AgentRegistration(
            name=AutomationGeneratorAgent.NAME,
            display_name="Automation Generator Agent",
            agent_class=AutomationGeneratorAgent,
            tier=2,
            dependencies=["test_case_generator", "project_analysis"],
            description=AutomationGeneratorAgent.DESCRIPTION,
        ),
        AgentRegistration(
            name=BrowserExecutionAgent.NAME,
            display_name="Browser Execution Agent",
            agent_class=BrowserExecutionAgent,
            tier=2,
            dependencies=["automation_generator"],
            description=BrowserExecutionAgent.DESCRIPTION,
        ),
        AgentRegistration(
            name=APIValidationAgent.NAME,
            display_name="API Validation Agent",
            agent_class=APIValidationAgent,
            tier=2,
            dependencies=["automation_generator", "project_analysis"],
            description=APIValidationAgent.DESCRIPTION,
        ),

        # ==================================================
        # TIER 3 — QUALITY
        # ==================================================
        AgentRegistration(
            name=SecurityTestingAgent.NAME,
            display_name="Security Testing Agent",
            agent_class=SecurityTestingAgent,
            tier=3,
            dependencies=["project_analysis", "test_case_generator"],
            description=SecurityTestingAgent.DESCRIPTION,
        ),
        AgentRegistration(
            name=PerformanceAgent.NAME,
            display_name="Performance Agent",
            agent_class=PerformanceAgent,
            tier=3,
            dependencies=["project_analysis", "api_validation"],
            description=PerformanceAgent.DESCRIPTION,
        ),
        AgentRegistration(
            name=DatabaseValidationAgent.NAME,
            display_name="Database Validation Agent",
            agent_class=DatabaseValidationAgent,
            tier=3,
            dependencies=["project_analysis"],
            description=DatabaseValidationAgent.DESCRIPTION,
        ),

        # Tier 4 — Step 18
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
