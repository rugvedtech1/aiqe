"""
AIQE Agent Framework.

Contains all 15 built-in AIQE agents, the BaseAgent abstract class,
typed input/output contracts, and the registry setup.

Tier 1 (implemented in Step 15):
    OrchestratorAgent       — controls all agents, plans execution
    ProjectAnalysisAgent    — detects language, framework, builds intelligence model
    TestStrategyAgent       — risk analysis, test prioritisation
    TestCaseGeneratorAgent  — generates test cases per type

Tier 2-4: Steps 16-18.

Public API:
    BaseAgent               — abstract base all agents inherit from
    AgentInput/Output       — base typed contracts
    register_all_agents     — call once at startup
"""

from aiqe.agents.base import BaseAgent
from aiqe.agents.orchestrator.agent import OrchestratorAgent, OrchestratorInput, OrchestratorOutput
from aiqe.agents.project_analysis.agent import ProjectAnalysisAgent
from aiqe.agents.registry_setup import register_all_agents
from aiqe.agents.test_case_generator.agent import TestCaseGeneratorAgent, TestCaseGeneratorOutput
from aiqe.agents.test_strategy.agent import TestStrategyAgent
from aiqe.agents.types import (
    AgentInput,
    AgentOutput,
    BugReport,
    BugSeverity,
    Evidence,
    ProjectAnalysisInput,
    ProjectAnalysisOutput,
    ReleaseIntelligenceOutput,
    ReleaseRisk,
    TestCaseGeneratorInput,
    TestStrategyInput,
    TestStrategyOutput,
)

__all__ = [
    "AgentInput",
    "AgentOutput",
    "BaseAgent",
    "BugReport",
    "BugSeverity",
    "Evidence",
    "OrchestratorAgent",
    "OrchestratorInput",
    "OrchestratorOutput",
    "ProjectAnalysisAgent",
    "ProjectAnalysisInput",
    "ProjectAnalysisOutput",
    "ReleaseIntelligenceOutput",
    "ReleaseRisk",
    "TestCaseGeneratorAgent",
    "TestCaseGeneratorInput",
    "TestCaseGeneratorOutput",
    "TestStrategyAgent",
    "TestStrategyInput",
    "TestStrategyOutput",
    "register_all_agents",
]
