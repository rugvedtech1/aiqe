"""
AIQE Agent Framework.

This package contains the BaseAgent abstract class, all 15 built-in
agents, their typed input/output contracts, and the registry setup.

Public API:
    BaseAgent           — abstract base class all agents inherit from
    AgentInput          — base input type
    AgentOutput         — base output type
    BugReport           — typed bug report structure
    BugSeverity         — severity enum (Critical/High/Medium/Low/Info)
    ReleaseRisk         — release risk enum
    Evidence            — evidence item for ADR-011
    OrchestratorAgent   — Tier 1 coordinator agent
    register_all_agents — call once at startup to register built-ins

Agent-specific input/output types are importable from aiqe.agents.types.
"""

from aiqe.agents.base import BaseAgent
from aiqe.agents.orchestrator.agent import OrchestratorAgent, OrchestratorInput, OrchestratorOutput
from aiqe.agents.registry_setup import register_all_agents
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
    "ProjectAnalysisInput",
    "ProjectAnalysisOutput",
    "ReleaseIntelligenceOutput",
    "ReleaseRisk",
    "TestStrategyInput",
    "TestStrategyOutput",
    "register_all_agents",
]
