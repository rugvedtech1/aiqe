"""Unit tests for AgentRegistry."""
import pytest
from aiqe.workflow.registry import AgentRegistry, AgentRegistration
from aiqe.shared.exceptions import AgentNotFoundError


class MockAgent:
    pass


class MockAgentB:
    pass


@pytest.fixture
def registry():
    return AgentRegistry()


@pytest.fixture
def sample_registration():
    return AgentRegistration(
        name="project_analysis",
        display_name="Project Analysis Agent",
        agent_class=MockAgent,
        tier=1,
        dependencies=[],
        description="Detects language and framework.",
    )


class TestAgentRegistry:
    def test_register_and_get(self, registry, sample_registration):
        registry.register(sample_registration)
        retrieved = registry.get("project_analysis")
        assert retrieved.name == "project_analysis"
        assert retrieved.tier == 1

    def test_duplicate_registration_raises(self, registry, sample_registration):
        registry.register(sample_registration)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(sample_registration)

    def test_get_unknown_agent_raises(self, registry):
        with pytest.raises(AgentNotFoundError):
            registry.get("nonexistent")

    def test_get_tier_returns_correct_agents(self, registry):
        registry.register(AgentRegistration(
            name="orchestrator", display_name="O", agent_class=MockAgent,
            tier=1, dependencies=[],
        ))
        registry.register(AgentRegistration(
            name="browser_execution", display_name="B", agent_class=MockAgentB,
            tier=2, dependencies=[],
        ))
        tier1 = registry.get_tier(1)
        assert len(tier1) == 1
        assert tier1[0].name == "orchestrator"

    def test_is_registered(self, registry, sample_registration):
        assert not registry.is_registered("project_analysis")
        registry.register(sample_registration)
        assert registry.is_registered("project_analysis")

    def test_resolve_execution_order_simple(self, registry):
        registry.register(AgentRegistration(
            name="agent_a", display_name="A", agent_class=MockAgent,
            tier=1, dependencies=[],
        ))
        registry.register(AgentRegistration(
            name="agent_b", display_name="B", agent_class=MockAgentB,
            tier=1, dependencies=["agent_a"],
        ))
        waves = registry.resolve_execution_order()
        assert waves[0] == ["agent_a"]
        assert waves[1] == ["agent_b"]

    def test_circular_dependency_raises(self, registry):
        registry.register(AgentRegistration(
            name="agent_a", display_name="A", agent_class=MockAgent,
            tier=1, dependencies=["agent_b"],
        ))
        registry.register(AgentRegistration(
            name="agent_b", display_name="B", agent_class=MockAgentB,
            tier=1, dependencies=["agent_a"],
        ))
        with pytest.raises(ValueError, match="Circular dependency"):
            registry.resolve_execution_order()

    def test_get_dependents(self, registry):
        registry.register(AgentRegistration(
            name="agent_a", display_name="A", agent_class=MockAgent,
            tier=1, dependencies=[],
        ))
        registry.register(AgentRegistration(
            name="agent_b", display_name="B", agent_class=MockAgentB,
            tier=1, dependencies=["agent_a"],
        ))
        dependents = registry.get_dependents("agent_a")
        assert len(dependents) == 1
        assert dependents[0].name == "agent_b"
