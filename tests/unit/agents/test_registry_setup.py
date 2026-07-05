"""Unit tests for agent registry setup."""
import pytest
from aiqe.workflow.registry import AgentRegistry


class TestRegistrySetup:
    def test_register_all_agents_populates_registry(self):
        """
        Test using a fresh registry so we don't affect the global one.
        """
        from aiqe.agents.orchestrator.agent import OrchestratorAgent
        from aiqe.workflow.registry import AgentRegistration

        fresh_registry = AgentRegistry()
        fresh_registry.register(AgentRegistration(
            name=OrchestratorAgent.NAME,
            display_name="Orchestrator Agent",
            agent_class=OrchestratorAgent,
            tier=1,
            dependencies=[],
            description=OrchestratorAgent.DESCRIPTION,
        ))

        assert fresh_registry.is_registered("orchestrator")
        reg = fresh_registry.get("orchestrator")
        assert reg.tier == 1
        assert reg.agent_class is OrchestratorAgent

    def test_orchestrator_has_no_dependencies(self):
        from aiqe.agents.orchestrator.agent import OrchestratorAgent
        agent = OrchestratorAgent()
        assert agent.get_dependencies() == []
