"""
AIQE Agent Registry.

The Agent Registry is the single source of truth for which agents
exist in AIQE, what tier they belong to, and how to instantiate them.

Design:
    The registry is a simple in-process dictionary keyed by agent name.
    Agents are registered at import time using the @register_agent
    decorator, similar to how FastAPI registers routes.

    This means adding a new agent to AIQE requires:
    1. Implementing the BaseAgent interface (Step 6).
    2. Decorating it with @register_agent.
    3. Importing the agent module so the decorator runs.

    The Orchestrator Agent asks the registry for agents by name.
    It never instantiates agents directly.

Why not a plugin system for built-in agents?
    Built-in agents (the 15 defined in ADR-004) are core AIQE code
    and are registered here. The Plugin System (Step 11) handles
    third-party extensions. This separation keeps the trust boundary
    clear: built-in agents have elevated trust, plugins do not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from aiqe.shared.exceptions import AgentNotFoundError
from aiqe.shared.logging import get_logger

if TYPE_CHECKING:
    from aiqe.agents.base import BaseAgent

logger = get_logger(__name__)


@dataclass
class AgentRegistration:
    """
    A registration record for one agent in the registry.

    Attributes:
        name: Unique agent identifier (e.g. 'project_analysis').
        display_name: Human-readable name for logs and reports.
        agent_class: The class implementing BaseAgent.
        tier: Which implementation tier (1-4, see ADR-004).
        dependencies: Names of agents that must complete before this one.
        description: What this agent does (one sentence).
        is_enabled: Whether this agent is active. Allows disabling
                    agents without removing their registration.
    """
    name: str
    display_name: str
    agent_class: type
    tier: int
    dependencies: list[str] = field(default_factory=list)
    description: str = ""
    is_enabled: bool = True


class AgentRegistry:
    """
    Central registry for all AIQE agents.

    Usage:
        registry = AgentRegistry()

        # Register an agent (usually done via @register_agent decorator)
        registry.register(AgentRegistration(
            name="project_analysis",
            display_name="Project Analysis Agent",
            agent_class=ProjectAnalysisAgent,
            tier=1,
            dependencies=[],
            description="Detects language, framework, dependencies, routes, and APIs.",
        ))

        # Resolve an agent by name
        registration = registry.get("project_analysis")
        agent = registration.agent_class()

        # Get all Tier 1 agents in dependency order
        tier1 = registry.get_tier(1)
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentRegistration] = {}

    def register(self, registration: AgentRegistration) -> None:
        """
        Register an agent with the registry.

        Args:
            registration: The AgentRegistration describing the agent.

        Raises:
            ValueError: If an agent with this name is already registered.
        """
        if registration.name in self._agents:
            msg = (
                f"Agent '{registration.name}' is already registered. "
                f"Each agent must have a unique name."
            )
            raise ValueError(msg)

        self._agents[registration.name] = registration
        logger.debug(
            "agent_registered",
            agent_name=registration.name,
            tier=registration.tier,
            dependencies=registration.dependencies,
        )

    def get(self, name: str) -> AgentRegistration:
        """
        Get an agent registration by name.

        Args:
            name: The agent's registered name.

        Returns:
            The AgentRegistration for this agent.

        Raises:
            AgentNotFoundError: If no agent with this name is registered.
        """
        registration = self._agents.get(name)
        if registration is None:
            available = list(self._agents.keys())
            msg = (
                f"Agent '{name}' is not registered. "
                f"Available agents: {available}"
            )
            raise AgentNotFoundError(msg, agent_name=name)
        return registration

    def get_tier(self, tier: int) -> list[AgentRegistration]:
        """
        Get all enabled agents belonging to a specific tier,
        sorted by name for consistent ordering.

        Args:
            tier: The tier number (1-4).

        Returns:
            List of AgentRegistration objects for this tier.
        """
        return sorted(
            [r for r in self._agents.values() if r.tier == tier and r.is_enabled],
            key=lambda r: r.name,
        )

    def get_all_enabled(self) -> list[AgentRegistration]:
        """
        Get all enabled agents across all tiers, sorted by tier then name.

        Returns:
            All enabled agent registrations in execution order.
        """
        return sorted(
            [r for r in self._agents.values() if r.is_enabled],
            key=lambda r: (r.tier, r.name),
        )

    def get_dependencies(self, name: str) -> list[AgentRegistration]:
        """
        Get all agents that the given agent depends on.

        Used by the Scheduler to determine task ordering and by the
        Workflow Engine for dependency failure isolation (ADR-007).

        Args:
            name: The agent whose dependencies to retrieve.

        Returns:
            List of AgentRegistrations this agent depends on.
        """
        registration = self.get(name)
        return [self.get(dep) for dep in registration.dependencies]

    def get_dependents(self, name: str) -> list[AgentRegistration]:
        """
        Get all agents that depend on the given agent.

        Used for dependency failure isolation: when agent X fails,
        all agents in get_dependents(X) are marked as SKIPPED.
        See ADR-007.

        Args:
            name: The agent whose dependents to retrieve.

        Returns:
            List of AgentRegistrations that depend on this agent.
        """
        return [
            r for r in self._agents.values()
            if name in r.dependencies and r.is_enabled
        ]

    def resolve_execution_order(self) -> list[list[str]]:
        """
        Compute the execution order respecting dependencies.

        Returns a list of "execution waves" — groups of agents that
        can run in parallel because none depends on another in the
        same group.

        Returns:
            List of waves. Each wave is a list of agent names that
            can execute concurrently.

        Example return value:
            [
                ["project_analysis"],          # Wave 1: no dependencies
                ["test_strategy"],             # Wave 2: needs project_analysis
                ["test_case_generator",        # Wave 3: can run in parallel
                 "feature_discovery"],
            ]
        """
        all_agents = {r.name: r for r in self.get_all_enabled()}
        completed: set[str] = set()
        waves: list[list[str]] = []

        remaining = set(all_agents.keys())
        max_iterations = len(remaining) + 1

        for _ in range(max_iterations):
            if not remaining:
                break

            wave: list[str] = []
            for name in sorted(remaining):
                registration = all_agents[name]
                deps_satisfied = all(
                    dep in completed for dep in registration.dependencies
                )
                if deps_satisfied:
                    wave.append(name)

            if not wave:
                unresolvable = sorted(remaining)
                msg = (
                    f"Circular dependency detected among agents: {unresolvable}. "
                    f"Check agent dependency declarations."
                )
                raise ValueError(msg)

            waves.append(wave)
            completed.update(wave)
            remaining -= set(wave)

        return waves

    def is_registered(self, name: str) -> bool:
        """Return True if an agent with this name is registered."""
        return name in self._agents

    @property
    def count(self) -> int:
        """Total number of registered agents."""
        return len(self._agents)


# Module-level singleton registry.
# Import this instance everywhere instead of creating new ones.
# The Orchestrator, Scheduler, and Engine all share this instance.
agent_registry = AgentRegistry()
